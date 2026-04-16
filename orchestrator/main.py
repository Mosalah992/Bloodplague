import asyncio
import json
import logging
import os
import re
import shutil
import sqlite3
import sys
import time
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
import httpx
from pydantic import BaseModel
import redis.asyncio as redis
from redis.exceptions import RedisError

from logger import EventLogger
from run_forensic_summary import (
    build_forensic_summary,
    build_forensic_summary_from_run_dir,
    forensic_summary_to_markdown,
    iter_jsonl_events,
)
from siem import SIEMIndexer
from c2 import C2Engine
from epidemic_tracker import EpidemicTracker
from forensic_enrichment import (
    TRIGGER_EVENT_ID,
    apply_c2_stream_correlation,
    enrich_forensic_event,
    parse_stream_message,
)
from strain_engine import StrainEngine
from strain_store import StrainStore
from experiment_config.config_log import log_resolved_experiment_config

_SHARED_DIR = Path(__file__).resolve().parents[1] / "agents" / "shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

from topology import get_topology, agent_roles as topology_agent_roles, get_role
from epidemic import epidemic_state_code, epidemic_state_from_agent_state, is_infected_epidemic_state

try:
    from world_db import WorldConfig, WorldDB
    from world_engine import PersistentWorldEngine
except ImportError:  # pragma: no cover
    from orchestrator.world_db import WorldConfig, WorldDB
    from orchestrator.world_engine import PersistentWorldEngine

try:
    from world_spatial import WorldSpatialEngine
    from world_structures import WorldStructureEngine, StructureType
except ImportError:  # pragma: no cover
    from orchestrator.world_spatial import WorldSpatialEngine
    from orchestrator.world_structures import WorldStructureEngine, StructureType


EVENT_STREAM_KEY = "events_stream"
SIMULATION_EPOCH_KEY = "simulation_epoch"
CURRENT_RESET_ID_KEY = "current_reset_id"
BEACON_SERVER_URL = os.environ.get(
    "C2_BEACON_SERVER_URL",
    "https://v0-beaconing-project-server-mdml8734h-mosalah992s-projects.vercel.app",
)


def _env_truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


# Off by default: forwarding every C2 event to an external HTTP server can stall the
# orchestrator (unreachable hosts, slow TLS). Enable explicitly for beacon demos.
C2_BEACON_FORWARD_ENABLED = _env_truthy("C2_BEACON_FORWARD_ENABLED", "0")
_BEACON_QUEUE_MAX = max(8, int(os.environ.get("C2_BEACON_FORWARD_QUEUE_MAX", "256")))
ACTIVE_TOPOLOGY = get_topology()
AGENT_IDS = tuple(ACTIVE_TOPOLOGY.keys())
TOPOLOGY = {agent_id: list(node.get("neighbors", [])) for agent_id, node in ACTIVE_TOPOLOGY.items()}
AGENT_ROLES = topology_agent_roles()
_BEACON_TRANSFER_SRCS = {agent_id for agent_id in AGENT_IDS if get_role(agent_id) == "guardian"} | {"agt-001", "agt-01"}
_BEACON_TRANSFER_DSTS = {agent_id for agent_id in AGENT_IDS if get_role(agent_id) != "guardian"} | {"agt-002", "agt-003", "agt-02", "agt-03"}
_BEACON_EXFIL_DST_RE = re.compile(r"^agt[-_]?0*[4-9]$", re.IGNORECASE)
_BEACON_REGISTRATION_RETRY_LIMIT = 2
_BEACON_REGISTRATION_BASE_DELAY_S = 1.0
_BEACON_FORWARD_TIMEOUT_S = max(0.25, float(os.environ.get("C2_BEACON_FORWARD_TIMEOUT_S", "2.0") or 2.0))
_beacon_forward_queue: asyncio.Queue | None = None
_beacon_forward_worker_task: asyncio.Task | None = None
_beacon_forward_drop_count = 0
# Vercel Deployment Protection bypass — set via env or .env
_VERCEL_BYPASS_SECRET = os.environ.get("VERCEL_PROTECTION_BYPASS", "")
# C2 event types that should be forwarded to the beacon server
_C2_FORWARD_EVENTS = {"C2_EXFIL", "C2_DATABASE_WRITE", "C2_BEACON", "C2_CHANNEL_ESTABLISHED"}

app = FastAPI(title="Epidemic Lab Orchestrator")
logger = EventLogger()
uvicorn_logger = logging.getLogger("uvicorn.error")
_beacon_client: httpx.AsyncClient | None = None

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
redis_client = redis.from_url(REDIS_URL, decode_responses=True)

TEMPLATES_DIR = Path(__file__).parent / "templates"
FRONTEND_DIST_DIR = Path(__file__).parent / "static"
LEGACY_DASHBOARD_PATH = TEMPLATES_DIR / "dashboard.html"
REPO_ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = Path(os.environ.get("LOGS_DIR", "/app/logs"))
DB_PATH = "/app/logs/epidemic.db"
JSONL_PATH = "/app/logs/events.jsonl"
SIEM_DB_PATH = os.environ.get("SIEM_DB_PATH", "/tmp/siem_index.db")
SIEM_TIMING_LOG_PATH = Path("/app/logs/siem_actions.jsonl")
ATTEMPT_RESOLUTION_WINDOW_S = 5.0
RESET_QUIET_PERIOD_S = 2.0
RESET_ACK_TIMEOUT_S = float(os.environ.get("RESET_ACK_TIMEOUT_S", "12.0"))
INFECTION_STATE_ALERT_EVENT = "SIEM_INFECTION_STATE_ALERT"
INFECTION_ALERT_SUPPRESSION_EVENTS = {
    "ALERT_SUPPRESSED",
    "INFECTION_ALERT_SUPPRESSED",
    "SIEM_ALERT_SUPPRESSED",
}
siem_indexer = SIEMIndexer(SIEM_DB_PATH, JSONL_PATH, source_db_path=DB_PATH)


def _init_run_id() -> str:
    env_rid = os.environ.get("EPIDEMIC_RUN_ID", "").strip()
    if env_rid:
        return env_rid
    return (
        "run_"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        + "_"
        + uuid.uuid4().hex[:10]
    )


RUN_ID = _init_run_id()


async def _c2_emit_to_stream(event_data: Dict[str, Any]) -> None:
    """Emit a C2 event to the Redis event stream."""
    try:
        enriched = apply_c2_stream_correlation(dict(event_data), run_id=RUN_ID)
        mapping: Dict[str, str] = {}
        for key, value in enriched.items():
            if value is None:
                continue
            if isinstance(value, (dict, list, tuple, bool)):
                mapping[key] = json.dumps(value)
            else:
                mapping[key] = str(value)
        await redis_client.xadd(EVENT_STREAM_KEY, mapping)
    except Exception as exc:
        uvicorn_logger.warning("c2_event_emit_failed event=%s err=%s", event_data.get("event"), exc)


c2_engine = C2Engine(emit_event=_c2_emit_to_stream)
strain_store = StrainStore()
strain_engine = StrainEngine(strain_store, run_id=RUN_ID, emit_to_stream=_c2_emit_to_stream)
epidemic_tracker = EpidemicTracker()
WORLD_ENGINE_ENABLED = _env_truthy("WORLD_ENGINE_ENABLED", "1")
world_db: WorldDB | None = None
world_engine: PersistentWorldEngine | None = None
world_round_lock = asyncio.Lock()

if (FRONTEND_DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST_DIR / "assets"), name="frontend-assets")
if (FRONTEND_DIST_DIR / "pixel-assets").exists():
    app.mount(
        "/pixel-assets",
        StaticFiles(directory=FRONTEND_DIST_DIR / "pixel-assets"),
        name="pixel-assets",
    )


class InjectPayload(BaseModel):
    worm_level: str = "easy"


class ImportPayload(BaseModel):
    source: str
    path: str = ""
    source_name: str = ""
    stream_name: str = EVENT_STREAM_KEY
    count: int = 500


class RebuildIndexPayload(BaseModel):
    jsonl_path: str = ""


def _normalized_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_agent_id(value: Any) -> str:
    return _normalized_text(value).lower()


def _validated_agent_id(value: Any) -> str:
    agent_id = _normalized_agent_id(value)
    if agent_id not in AGENT_IDS:
        raise HTTPException(status_code=400, detail="Unsupported agent_id")
    return agent_id


def _agent_channel_name(agent_id: str) -> str:
    return f"agent_{_validated_agent_id(agent_id)}"


def _import_roots() -> List[Path]:
    configured = [
        item.strip()
        for item in os.environ.get("SIEM_IMPORT_ROOTS", "").split(os.pathsep)
        if item.strip()
    ]
    candidates = configured or [
        str(LOGS_DIR),
        str(REPO_ROOT / "logs"),
        str(Path.cwd() / "logs"),
    ]
    roots: List[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        resolved = Path(candidate).expanduser().resolve(strict=False)
        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)
        roots.append(resolved)
    return roots


def _validated_import_path(raw_path: str) -> Path:
    candidate = Path(_normalized_text(raw_path)).expanduser()
    if not str(candidate):
        raise HTTPException(status_code=400, detail="Import path is required")
    resolved = candidate.resolve(strict=False)
    if not resolved.exists():
        raise FileNotFoundError(raw_path)
    if not resolved.is_file():
        raise HTTPException(status_code=400, detail="Import path must reference a file")
    if not any(resolved.is_relative_to(root) for root in _import_roots()):
        raise HTTPException(status_code=400, detail="Import path must stay within configured log roots")
    return resolved


def _event_metadata_dict(event: Dict[str, Any]) -> Dict[str, Any]:
    metadata = event.get("metadata", {})
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    return metadata if isinstance(metadata, dict) else {}


def _extract_live_event_fields(event: Dict[str, Any]) -> Dict[str, Any]:
    metadata = _event_metadata_dict(event)
    bytes_value = (
        event.get("bytes")
        or event.get("payload_length")
        or metadata.get("bytes")
        or metadata.get("payload_length")
        or metadata.get("bytes_transferred")
    )
    return {
        "src": _normalized_text(event.get("src")),
        "dst": _normalized_text(event.get("dst")),
        "event": _normalized_text(event.get("event")).upper(),
        "payload": _normalized_text(event.get("payload")),
        "attack_type": _normalized_text(event.get("attack_type") or metadata.get("attack_type")),
        "bytes": bytes_value,
        "dst_country": _normalized_text(event.get("dst_country") or metadata.get("dst_country")),
        "proto": _normalized_text(event.get("proto") or metadata.get("proto")),
        "ts": _normalized_text(event.get("ts")),
    }


def _is_beacon_transfer(src: str, dst: str) -> bool:
    return _normalized_agent_id(src) in _BEACON_TRANSFER_SRCS and _normalized_agent_id(dst) in _BEACON_TRANSFER_DSTS


def _is_beacon_exfil(event_type: str, dst: str) -> bool:
    return _normalized_text(event_type).upper() == "EXFIL" and bool(_BEACON_EXFIL_DST_RE.match(_normalized_text(dst)))


def _should_forward_to_beacon(event: Dict[str, Any]) -> bool:
    extracted = _extract_live_event_fields(event)
    if extracted["event"] in _C2_FORWARD_EVENTS:
        return True
    if extracted["event"] == "TRANSFER":
        return _is_beacon_transfer(extracted["src"], extracted["dst"])
    return _is_beacon_exfil(extracted["event"], extracted["dst"])


def _c2_beacon_event_type(event_name: str) -> str:
    if event_name in ("C2_EXFIL", "C2_DATABASE_WRITE"):
        return "alert"
    if event_name == "C2_CHANNEL_ESTABLISHED":
        return "trigger"
    if event_name == "C2_BEACON":
        return "heartbeat"
    if event_name == "EXFIL":
        return "alert"
    return "trigger"


def _post_beacon_json_sync(path: str, payload: Dict[str, Any], timeout_s: float) -> Tuple[bool, int, str]:
    """
    Run external beacon HTTP in a worker thread.

    Docker startup and browser bootstrap share one Uvicorn event loop. Keeping
    outbound TLS/DNS off that loop prevents Vercel latency from starving local
    dashboard and static asset requests.
    """
    try:
        response = httpx.post(
            f"{BEACON_SERVER_URL}{path}",
            json=payload,
            headers=_beacon_client_headers(),
            timeout=timeout_s,
        )
        return response.status_code < 400, response.status_code, response.text[:500]
    except Exception as exc:
        return False, 0, str(exc)[:500]


async def _forward_to_beacon_http(event: Dict[str, Any]) -> None:
    """POST one event to the external beacon log API (called only from the forward worker)."""
    extracted = _extract_live_event_fields(event)
    beacon_event_type = _c2_beacon_event_type(extracted["event"])
    parts = [f"[{extracted['event']}] {extracted['src'] or 'unknown'} -> {extracted['dst']}"]
    if extracted["bytes"] not in (None, "", 0, "0"):
        parts.append(f"bytes={extracted['bytes']}")
    if extracted["dst_country"]:
        parts.append(f"country={extracted['dst_country']}")
    if extracted["proto"]:
        parts.append(f"proto={extracted['proto']}")
    if extracted["attack_type"]:
        parts.append(f"attack={extracted['attack_type']}")
    parts.append(f"ts={extracted['ts']}")

    payload = {
        "device_id": extracted["src"] or "unknown",
        "event_type": beacon_event_type,
        "rssi": -70,
        "payload": {
            "raw": extracted["payload"][:2000],
            "event": extracted["event"],
            "src": extracted["src"],
            "dst": extracted["dst"],
            "attack_type": extracted["attack_type"],
            "bytes": extracted["bytes"],
            "proto": extracted["proto"],
            "dst_country": extracted["dst_country"],
            "ts": extracted["ts"],
        },
        "message": " | ".join(parts),
    }

    ok, status_code, body = await asyncio.to_thread(
        _post_beacon_json_sync,
        "/api/beacon/log",
        payload,
        _BEACON_FORWARD_TIMEOUT_S,
    )
    if not ok and status_code >= 400:
        uvicorn_logger.warning(
            "beacon_log_forward_failed status=%s body=%s",
            status_code,
            body,
        )


def _enqueue_beacon_forward(event: Dict[str, Any]) -> None:
    """Bounded best-effort enqueue; avoids asyncio.create_task per stream message."""
    global _beacon_forward_drop_count
    if not C2_BEACON_FORWARD_ENABLED or _beacon_forward_queue is None:
        return
    try:
        _beacon_forward_queue.put_nowait(event)
    except asyncio.QueueFull:
        _beacon_forward_drop_count += 1
        if _beacon_forward_drop_count == 1 or _beacon_forward_drop_count % 200 == 0:
            uvicorn_logger.warning(
                "beacon_forward_queue_full max=%s total_drops=%s",
                _BEACON_QUEUE_MAX,
                _beacon_forward_drop_count,
            )


async def _beacon_forward_worker() -> None:
    while True:
        try:
            assert _beacon_forward_queue is not None
            event = await _beacon_forward_queue.get()
        except asyncio.CancelledError:
            break
        try:
            await _forward_to_beacon_http(event)
        finally:
            _beacon_forward_queue.task_done()


def _beacon_client_headers() -> Dict[str, str]:
    headers: Dict[str, str] = {}
    if _VERCEL_BYPASS_SECRET:
        headers["x-vercel-protection-bypass"] = _VERCEL_BYPASS_SECRET
    return headers


async def _register_beacon_devices() -> None:
    agent_defs = _beacon_device_definitions()
    pending = list(agent_defs)

    for attempt in range(1, _BEACON_REGISTRATION_RETRY_LIMIT + 1):
        pending = await _register_beacon_devices_once(pending)
        if not pending:
            uvicorn_logger.info(
                "beacon_device_registration_complete total=%s attempts=%s",
                len(agent_defs),
                attempt,
            )
            return
        delay_s = min(_BEACON_REGISTRATION_BASE_DELAY_S * attempt, 15.0)
        uvicorn_logger.warning(
            "beacon_device_registration_retry pending=%s attempt=%s/%s delay_s=%.1f devices=%s",
            len(pending),
            attempt,
            _BEACON_REGISTRATION_RETRY_LIMIT,
            delay_s,
            ",".join(definition["device_id"] for definition in pending),
        )
        await asyncio.sleep(delay_s)

    if pending:
        uvicorn_logger.error(
            "beacon_device_registration_incomplete pending=%s devices=%s",
            len(pending),
            ",".join(definition["device_id"] for definition in pending),
        )


def _beacon_device_definitions() -> List[Dict[str, str]]:
    agent_defs = [
        {
            "device_id": agent_id,
            "name": str(node.get("display_name") or f"{AGENT_ROLES.get(agent_id, 'Agent')} ({agent_id})"),
            "type": str(node.get("device_type") or "synthetic"),
            "location": str(node.get("location") or "SIMNET"),
        }
        for agent_id, node in ACTIVE_TOPOLOGY.items()
    ]
    for index in range(1, 10):
        agent_defs.append(
            {
                "device_id": f"agt-{index:03d}",
                "name": f"Synthetic AGT-{index:03d}",
                "type": "synthetic",
                "location": "SIMNET",
            }
        )
    return agent_defs


async def _register_beacon_devices_once(agent_defs: List[Dict[str, str]]) -> List[Dict[str, str]]:
    async def register_one(definition: Dict[str, str]) -> Tuple[Dict[str, str], bool, int, str]:
        ok, status_code, body = await asyncio.to_thread(
            _post_beacon_json_sync,
            "/api/beacon/register",
            {**definition, "metadata": {"sim": "epidemic-lab"}},
            _BEACON_FORWARD_TIMEOUT_S,
        )
        return definition, ok, status_code, body

    failed: List[Dict[str, str]] = []
    for definition, ok, status_code, body in await asyncio.gather(
        *(register_one(definition) for definition in agent_defs)
    ):
        if ok:
            uvicorn_logger.info("beacon_device_registered device_id=%s", definition["device_id"])
        else:
            failed.append(definition)
            if status_code >= 400:
                uvicorn_logger.warning(
                    "beacon_device_registration_failed device_id=%s status=%s body=%s",
                    definition["device_id"],
                    status_code,
                    body,
                )
            else:
                uvicorn_logger.warning(
                    "beacon_device_registration_exception device_id=%s err=%s",
                    definition["device_id"],
                    body,
                )
    return failed


def _log_api_timing(
    endpoint: str,
    *,
    query: str,
    time_range: str,
    result_count: int,
    elapsed_ms: float,
) -> None:
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "endpoint": endpoint,
        "query": query,
        "time_range": time_range,
        "result_count": result_count,
        "elapsed_ms": round(elapsed_ms, 2),
    }
    encoded = json.dumps(payload, ensure_ascii=True)
    uvicorn_logger.info("siem_timing %s", encoded)
    try:
        SIEM_TIMING_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with SIEM_TIMING_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(encoded + "\n")
    except Exception:
        uvicorn_logger.warning("siem_timing_file_write_failed")


def _parse_json_field(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return value
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return value
    if isinstance(parsed, str):
        try:
            return json.loads(parsed)
        except json.JSONDecodeError:
            return parsed
    return parsed


def _parse_timestamp(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.fromtimestamp(float(text), tz=timezone.utc)
        except ValueError:
            return None


def _is_sqlite_locked(exc: Exception) -> bool:
    return isinstance(exc, sqlite3.OperationalError) and "database is locked" in str(exc).lower()


def _sparkline(values: List[int]) -> str:
    if not values:
        return ""
    blocks = " .:-=+*#%@"
    upper = max(values)
    if upper <= 0:
        return " ".join("." for _ in values)
    rendered = []
    for value in values:
        index = int(round((value / upper) * (len(blocks) - 1)))
        rendered.append(blocks[index])
    return "".join(rendered)


def _event_metadata(event: Dict[str, Any]) -> Dict[str, Any]:
    metadata = event.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _event_epoch(event: Dict[str, Any]) -> int | None:
    metadata = _event_metadata(event)
    epoch = metadata.get("epoch")
    if epoch in (None, ""):
        return None
    try:
        return int(epoch)
    except (TypeError, ValueError):
        return None


def _event_reset_id(event: Dict[str, Any]) -> str:
    metadata = _event_metadata(event)
    return str(metadata.get("reset_id", "") or "")


def _normalize_event_row(row: sqlite3.Row) -> Dict[str, Any]:
    event = dict(row)
    event["metadata"] = _parse_json_field(event.get("metadata"))
    # Hoist lineage / correlation fields from metadata to top-level so external
    # consumers (SIEM, exporters, dashboard) can read them without digging into
    # the metadata blob. CLAUDE.md principle #7: every meaningful action must
    # be traceable. The events table only persists `metadata` as JSON, so these
    # fields would otherwise be lost at the SQL boundary even though agents
    # emit them at top-level in JSONL.
    metadata = event["metadata"] if isinstance(event["metadata"], dict) else {}
    for field in (
        "event_id",
        "strain_id",
        "payload_hash",
        "payload_hash_full",
        "parent_event_id",
        "parent_payload_hash",
        "parent_payload_hash_full",
        "kill_chain_stage",
        "campaign_id",
        "injection_id",
        "attempt_id",
    ):
        if field not in event and field in metadata:
            event[field] = metadata[field]
    return event


def _event_attempt_id(event: Dict[str, Any]) -> str:
    metadata = _event_metadata(event)
    return str(metadata.get("attempt_id") or metadata.get("injection_id") or "")


def _load_events_from_db(
    *, after_id: int = 0, limit: int = 100, order: str = "desc"
) -> Tuple[List[Dict[str, Any]], int]:
    normalized_limit = max(1, min(limit, 1000))
    requested_order = (order or "").lower()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        # Forward-pagination path:
        #   • after_id > 0  → standard polling: walk forward from the cursor
        #   • after_id == 0 AND order == "asc" → full forward scan from id=1
        #     (used by run_simulation.py exporter; previous behavior incorrectly
        #     returned only the tail-N events sorted ASC, hiding ~98% of run
        #     history from any post-hoc analysis).
        if after_id > 0 or (after_id == 0 and requested_order == "asc"):
            rows = conn.execute(
                """SELECT id, timestamp as ts, src_agent as src, dst_agent as dst,
                          event_type as event, attack_type, payload, mutation_v,
                          agent_state as state_after, metadata
                   FROM events WHERE id > ? ORDER BY id ASC LIMIT ?""",
                (after_id, normalized_limit),
            ).fetchall()
        elif requested_order == "asc":
            rows = conn.execute(
                """SELECT * FROM (
                       SELECT id, timestamp as ts, src_agent as src, dst_agent as dst,
                              event_type as event, attack_type, payload, mutation_v,
                              agent_state as state_after, metadata
                       FROM events ORDER BY id DESC LIMIT ?
                   ) recent_events
                   ORDER BY id ASC""",
                (normalized_limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, timestamp as ts, src_agent as src, dst_agent as dst,
                          event_type as event, attack_type, payload, mutation_v,
                          agent_state as state_after, metadata
                   FROM events ORDER BY id DESC LIMIT ?""",
                (normalized_limit,),
            ).fetchall()
        latest_id = conn.execute(
            "SELECT COALESCE(MAX(id), 0) AS latest_id FROM events"
        ).fetchone()["latest_id"]
    return [_normalize_event_row(row) for row in rows], int(latest_id or 0)


def _latest_reset_context(events_asc: List[Dict[str, Any]]) -> Dict[str, Any]:
    reset_index = None
    for index, event in enumerate(events_asc):
        if event.get("event") == "RESET_ISSUED":
            reset_index = index
    if reset_index is None:
        return {
            "reset_index": None,
            "reset_event": None,
            "reset_id": "",
            "epoch": 0,
            "events": [],
        }

    reset_event = events_asc[reset_index]
    reset_id = _event_reset_id(reset_event)
    epoch = _event_epoch(reset_event) or 0
    scoped_events = [
        event for event in events_asc[reset_index:]
        if _event_reset_id(event) == reset_id
    ]
    return {
        "reset_index": reset_index,
        "reset_event": reset_event,
        "reset_id": reset_id,
        "epoch": epoch,
        "events": scoped_events,
    }


def _enrich_agent_metrics(agents: Dict[str, Dict[str, Any]], events_asc: List[Dict[str, Any]]) -> None:
    """Add per-agent rollups for dashboard / retro lab UI (no extra DB queries)."""
    ctx = _latest_reset_context(events_asc)
    run_events = ctx["events"]
    for agent_id, agent in agents.items():
        infection_count = 0
        block_count = 0
        last_attack_type = ""
        c2_sessions = 0
        for event in run_events:
            dst = str(event.get("dst", "") or "")
            src = str(event.get("src", "") or "")
            en = str(event.get("event", "") or "")
            if dst == agent_id and en == "INFECTION_SUCCESSFUL":
                infection_count += 1
            if dst == agent_id and en == "INFECTION_BLOCKED":
                block_count += 1
            if dst == agent_id:
                atk = str(event.get("attack_type", "") or "")
                if atk:
                    last_attack_type = atk
            if agent_id in (src, dst) and en in {"C2_CHANNEL_ESTABLISHED", "C2_BEACON"}:
                c2_sessions += 1
        total_ib = infection_count + block_count
        defense_effectiveness = round(block_count / total_ib, 4) if total_ib else None
        agent["infection_count"] = infection_count
        agent["block_count"] = block_count
        agent["defense_effectiveness"] = defense_effectiveness
        agent["last_attack_type"] = last_attack_type
        agent["c2_sessions"] = c2_sessions


def _state_update_from_event(event: Dict[str, Any]) -> Tuple[str, str]:
    event_name = str(event.get("event", "") or "").upper()
    metadata = _event_metadata(event)
    if event_name == "EPIDEMIC_STATE_TRANSITION":
        agent_id = str(metadata.get("agent_id") or event.get("src") or event.get("dst") or "")
        to_state = str(metadata.get("to_state") or metadata.get("epidemic_state") or event.get("state_after") or "")
        if to_state in {"I_r", "I_c", "I_x", "P"}:
            return agent_id, "infected"
        if to_state == "Q":
            return agent_id, "quarantined"
        if to_state == "R":
            return agent_id, "resistant"
        if to_state == "E":
            return agent_id, "exposed"
        if to_state == "S":
            return agent_id, "healthy"
        return agent_id, str(event.get("state_after", "") or "")
    if event_name == "INFECTION_SUCCESSFUL":
        return str(event.get("dst", "") or ""), "infected"
    if event_name == "INFECTION_BLOCKED":
        return str(event.get("dst", "") or ""), str(event.get("state_after") or "resistant")
    if event_name in {"QUARANTINE_ISSUED", "QUARANTINE_ENFORCED"}:
        return str(event.get("dst", "") or metadata.get("agent_id", "") or ""), "quarantined"
    if event_name in {"VACCINE_RECEIVED", "VACCINE_APPLIED"}:
        return str(event.get("dst", "") or metadata.get("agent_id", "") or ""), "resistant"
    return "", ""


def _derive_agents(events_desc: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    agents: Dict[str, Dict[str, Any]] = {
        agent_id: {
            "id": agent_id,
            "role": AGENT_ROLES.get(agent_id, ""),
            "state": "healthy",
            "last_event": "none",
            "last_seen": "",
            "last_payload": "",
            "last_metadata": {},
            "_state_locked": False,
        }
        for agent_id in AGENT_IDS
    }

    for event in events_desc:
        event_name = str(event.get("event", ""))
        dst = str(event.get("dst", ""))
        src = str(event.get("src", ""))
        state_agent_id, state_after = _state_update_from_event(event)
        state_after = str(state_after or "").lower()

        if event_name == "RESET_ISSUED":
            for agent in agents.values():
                if agent["last_event"] == "none":
                    agent["state"] = "healthy"
                    agent["last_event"] = "RESET_ISSUED"
                    agent["last_seen"] = event.get("ts", "")
            continue

        if dst in agents:
            if agents[dst]["last_event"] == "none":
                agents[dst]["last_event"] = event_name or "unknown"
                agents[dst]["last_seen"] = event.get("ts", "")
            if not agents[dst]["_state_locked"]:
                if state_after and state_agent_id == dst:
                    agents[dst]["state"] = state_after
                    agents[dst]["_state_locked"] = True

        if (
            state_agent_id in agents
            and state_after
            and not agents[state_agent_id]["_state_locked"]
        ):
            agents[state_agent_id]["state"] = state_after
            agents[state_agent_id]["_state_locked"] = True
            if agents[state_agent_id]["last_event"] == "none":
                agents[state_agent_id]["last_event"] = event_name or "unknown"
                agents[state_agent_id]["last_seen"] = event.get("ts", "")

        if dst in agents and event.get("payload") and not agents[dst]["last_payload"]:
            agents[dst]["last_payload"] = event["payload"]

        if dst in agents and event.get("metadata") and not agents[dst]["last_metadata"]:
            agents[dst]["last_metadata"] = event["metadata"]

        if src in agents and event.get("payload") and not agents[src]["last_payload"]:
            agents[src]["last_payload"] = event["payload"]

    for agent in agents.values():
        agent.pop("_state_locked", None)

    return agents


def _compute_flow_validation(events_asc: List[Dict[str, Any]]) -> Dict[str, Any]:
    context = _latest_reset_context(events_asc)
    run_events = context["events"]
    route_stats: Dict[str, Dict[str, Any]] = {}
    for src, neighbors in TOPOLOGY.items():
        for dst in neighbors:
            attempts = sum(
                1
                for event in run_events
                if event.get("event") == "INFECTION_ATTEMPT"
                and event.get("src") == src
                and event.get("dst") == dst
            )
            successes = sum(
                1
                for event in run_events
                if event.get("event") == "INFECTION_SUCCESSFUL"
                and event.get("src") == src
                and event.get("dst") == dst
            )
            route_stats[f"{src}->{dst}"] = {
                "src": src,
                "dst": dst,
                "attempts": attempts,
                "successes": successes,
                "success_rate": round(successes / attempts, 3) if attempts else 0.0,
            }

    valid_edges = {(src, dst) for src, neighbors in TOPOLOGY.items() for dst in neighbors}
    invalid_flows = sum(
        1
        for event in run_events
        if event.get("event") in {"INFECTION_ATTEMPT", "INFECTION_SUCCESSFUL", "INFECTION_BLOCKED"}
        and (str(event.get("src", "")), str(event.get("dst", ""))) not in valid_edges
    )

    return {
        "routes": route_stats,
        "invalid_flows_detected": invalid_flows,
        "epoch": context["epoch"],
        "reset_id": context["reset_id"],
    }


def _compute_run_integrity(events_asc: List[Dict[str, Any]]) -> Dict[str, Any]:
    context = _latest_reset_context(events_asc)
    reset_index = context["reset_index"]
    if reset_index is None:
        return {
            "events_after_reset": False,
            "bleed_through_detected": False,
            "last_event_before_reset_ts": "",
            "first_event_after_reset_ts": "",
            "acked_agents": [],
            "heartbeat_agents": [],
            "barrier_complete": False,
            "reset_id": "",
            "epoch": 0,
            "suppression_events_before_barrier": 0,
            "suppression_events_after_barrier": 0,
            "quiet_period_s": RESET_QUIET_PERIOD_S,
        }

    reset_event = context["reset_event"]
    reset_id = context["reset_id"]
    reset_epoch = context["epoch"]
    later_events = events_asc[reset_index + 1 :]
    acked_agents: List[str] = []
    heartbeat_agents: List[str] = []
    barrier_complete_index = None

    for index, event in enumerate(later_events):
        if event.get("event") == "RESET_ACK" and _event_reset_id(event) == reset_id:
            src = str(event.get("src", ""))
            if src not in acked_agents:
                acked_agents.append(src)
        if (
            event.get("event") == "HEARTBEAT"
            and _event_reset_id(event) == reset_id
            and (_event_epoch(event) or reset_epoch) == reset_epoch
        ):
            src = str(event.get("src", ""))
            if src not in heartbeat_agents:
                heartbeat_agents.append(src)
        if len(acked_agents) == len(AGENT_IDS) and len(heartbeat_agents) == len(AGENT_IDS):
            barrier_complete_index = index
            break

    before_barrier = later_events if barrier_complete_index is None else later_events[: barrier_complete_index + 1]
    non_barrier_events = [
        event
        for event in before_barrier
        if event.get("event") not in {"RESET_ACK", "HEARTBEAT"}
    ]

    after_barrier = [] if barrier_complete_index is None else later_events[barrier_complete_index + 1 :]
    suppression_before_barrier = sum(
        1 for event in before_barrier
        if event.get("event") == "PROPAGATION_SUPPRESSED"
    )
    suppression_after_barrier = sum(
        1 for event in after_barrier
        if event.get("event") == "PROPAGATION_SUPPRESSED"
    )
    bleed_through = any(
        event.get("event") in {"STALE_EVENT_DROPPED", "PROPAGATION_SUPPRESSED"}
        or (
            event.get("event") in {"INFECTION_ATTEMPT", "INFECTION_SUCCESSFUL", "INFECTION_BLOCKED"}
            and _event_reset_id(event) not in {"", reset_id}
        )
        or ((_event_epoch(event) or reset_epoch) < reset_epoch)
        for event in after_barrier
    )

    return {
        "events_after_reset": bool(
            [
                event for event in non_barrier_events
                if event.get("event") != "PROPAGATION_SUPPRESSED"
            ]
        ),
        "bleed_through_detected": bleed_through,
        "last_event_before_reset_ts": events_asc[reset_index - 1]["ts"] if reset_index > 0 else "",
        "first_event_after_reset_ts": later_events[0]["ts"] if later_events else "",
        "acked_agents": acked_agents,
        "heartbeat_agents": heartbeat_agents,
        "barrier_complete": (
            len(acked_agents) == len(AGENT_IDS)
            and len(heartbeat_agents) == len(AGENT_IDS)
            and not bleed_through
        ),
        "reset_id": reset_id,
        "epoch": reset_epoch,
        "suppression_events_before_barrier": suppression_before_barrier,
        "suppression_events_after_barrier": suppression_after_barrier,
        "quiet_period_s": RESET_QUIET_PERIOD_S,
    }


def _compute_timeline(events_asc: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not events_asc:
        return {"labels": [], "infected_counts": [], "sparkline": ""}

    context = _latest_reset_context(events_asc)
    run_events = context["events"]
    if not run_events:
        return {"labels": [], "infected_counts": [], "sparkline": ""}

    timestamps = [_parse_timestamp(event.get("ts")) for event in run_events]
    timestamps = [ts for ts in timestamps if ts is not None]
    if not timestamps:
        return {"labels": [], "infected_counts": [], "sparkline": ""}

    start = min(timestamps)
    end = max(timestamps)
    span = max((end - start).total_seconds(), 1.0)
    bucket_count = 12
    buckets = [set() for _ in range(bucket_count)]

    for event in run_events:
        ts = _parse_timestamp(event.get("ts"))
        if ts is None:
            continue
        offset = (ts - start).total_seconds()
        index = min(bucket_count - 1, int((offset / span) * (bucket_count - 1)))
        if str(event.get("state_after", "")).lower() == "infected" and event.get("dst") in AGENT_IDS:
            buckets[index].add(str(event.get("dst")))

    counts = [len(bucket) for bucket in buckets]
    labels = [
        (start + ((end - start) * (index / max(bucket_count - 1, 1)))).strftime("%H:%M:%S")
        for index in range(bucket_count)
    ]
    return {"labels": labels, "infected_counts": counts, "sparkline": _sparkline(counts)}


def _compute_influence(events_asc: List[Dict[str, Any]]) -> Dict[str, int]:
    context = _latest_reset_context(events_asc)
    reset_id = context["reset_id"]
    counts = {agent_id: 0 for agent_id in AGENT_IDS}
    for event in events_asc:
        if event.get("event") == "INFECTION_SUCCESSFUL" and _event_reset_id(event) == reset_id:
            src = str(event.get("src", ""))
            if src in counts:
                counts[src] += 1
    return counts


def _compute_attempt_reconciliation(events_asc: List[Dict[str, Any]]) -> Dict[str, Any]:
    context = _latest_reset_context(events_asc)
    run_events = context["events"]
    if not run_events:
        return {
            "reset_id": "",
            "epoch": 0,
            "attempt_count": 0,
            "resolved_count": 0,
            "unresolved_count": 0,
            "unresolved_over_window": 0,
            "resolution_rate": 0.0,
            "sample_unresolved": [],
        }

    attempts: Dict[str, Dict[str, Any]] = {}
    resolved_ids: set[str] = set()
    latest_ts = None
    for event in run_events:
        ts = _parse_timestamp(event.get("ts"))
        if ts is not None and (latest_ts is None or ts > latest_ts):
            latest_ts = ts
        attempt_id = _event_attempt_id(event)
        if event.get("event") == "INFECTION_ATTEMPT" and attempt_id:
            attempts[attempt_id] = event
        elif event.get("event") in {"INFECTION_SUCCESSFUL", "INFECTION_BLOCKED"} and attempt_id:
            resolved_ids.add(attempt_id)

    unresolved = []
    unresolved_over_window = 0
    for attempt_id, event in attempts.items():
        if attempt_id in resolved_ids:
            continue
        unresolved.append(
            {
                "attempt_id": attempt_id,
                "src": event.get("src", ""),
                "dst": event.get("dst", ""),
                "ts": event.get("ts", ""),
            }
        )
        event_ts = _parse_timestamp(event.get("ts"))
        if latest_ts is not None and event_ts is not None:
            age_s = (latest_ts - event_ts).total_seconds()
            if age_s >= ATTEMPT_RESOLUTION_WINDOW_S:
                unresolved_over_window += 1

    resolved_count = sum(1 for attempt_id in attempts if attempt_id in resolved_ids)
    attempt_count = len(attempts)
    return {
        "reset_id": context["reset_id"],
        "epoch": context["epoch"],
        "attempt_count": attempt_count,
        "resolved_count": resolved_count,
        "unresolved_count": len(unresolved),
        "unresolved_over_window": unresolved_over_window,
        "resolution_window_s": ATTEMPT_RESOLUTION_WINDOW_S,
        "resolution_rate": round(resolved_count / attempt_count, 3) if attempt_count else 0.0,
        "sample_unresolved": unresolved[:10],
    }


def _compute_event_rate(events_asc: List[Dict[str, Any]]) -> Dict[str, Any]:
    timestamps = [_parse_timestamp(event.get("ts")) for event in events_asc]
    timestamps = [ts for ts in timestamps if ts is not None]
    if not timestamps:
        return {"events_per_sec": 0.0, "recent_event_count": 0, "burst_detected": False}

    latest = max(timestamps)
    window_start = latest - timedelta(seconds=30)
    recent_count = sum(1 for ts in timestamps if ts >= window_start)
    rate = recent_count / 30.0
    return {
        "events_per_sec": round(rate, 2),
        "recent_event_count": recent_count,
        "burst_detected": rate >= 5.0,
        "window_seconds": 30,
    }


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _event_time_value(event: Dict[str, Any]) -> float:
    value = event.get("ts")
    try:
        return float(value)
    except (TypeError, ValueError):
        parsed = _parse_timestamp(value)
        if parsed is None:
            return 0.0
        return parsed.timestamp()


def _event_mentions_agent(event: Dict[str, Any], agent_id: str) -> bool:
    metadata = _event_metadata(event)
    targets = {
        str(event.get("src", "") or ""),
        str(event.get("dst", "") or ""),
        str(metadata.get("agent_id", "") or ""),
        str(metadata.get("target_agent", "") or ""),
        str(metadata.get("compromised_agent", "") or ""),
        str(metadata.get("src_agent", "") or ""),
        str(metadata.get("dst_agent", "") or ""),
        str(metadata.get("target", "") or ""),
    }
    return agent_id in targets


def _alert_type_matches_infection(metadata: Dict[str, Any]) -> bool:
    alert_type = str(
        metadata.get("alert_type")
        or metadata.get("suppressed_alert")
        or metadata.get("suppression_scope")
        or ""
    ).strip().lower()
    return alert_type in {"", "all", "infection", "infection_state", "infection_state_alert"}


def _is_infection_alert_suppression(event: Dict[str, Any], agent_id: str) -> bool:
    event_name = str(event.get("event", "") or "").upper()
    metadata = _event_metadata(event)
    explicit_suppression = (
        event_name in INFECTION_ALERT_SUPPRESSION_EVENTS
        or _truthy(metadata.get("suppress_infection_alert"))
        or _truthy(metadata.get("infection_alert_suppressed"))
    )
    if not explicit_suppression or not _alert_type_matches_infection(metadata):
        return False
    if _truthy(metadata.get("all_agents")) or str(metadata.get("scope", "")).lower() == "global":
        return True
    return _event_mentions_agent(event, agent_id)


def _find_infection_alert_suppression(
    events_asc: List[Dict[str, Any]],
    agent_id: str,
    infected_since: float,
) -> Dict[str, Any] | None:
    for event in reversed(events_asc):
        if _event_time_value(event) < infected_since:
            continue
        if _is_infection_alert_suppression(event, agent_id):
            return {
                "event": event.get("event", ""),
                "event_id": event.get("event_id", event.get("id", "")),
                "ts": event.get("ts", ""),
                "reason": _event_metadata(event).get("reason", "explicit infection alert suppression"),
            }
    return None


def _build_infection_state_alerts(
    agents: Dict[str, Dict[str, Any]],
    events_asc: List[Dict[str, Any]],
) -> Dict[str, Any]:
    active: List[Dict[str, Any]] = []
    suppressed: List[Dict[str, Any]] = []
    for agent_id, agent in sorted(agents.items()):
        epidemic_state = str(agent.get("epidemic_state") or agent.get("state") or "")
        if not is_infected_epidemic_state(epidemic_state):
            continue
        try:
            infected_since = float(agent.get("epidemic_last_updated") or 0.0)
        except (TypeError, ValueError):
            infected_since = 0.0
        suppression = _find_infection_alert_suppression(events_asc, agent_id, infected_since)
        alert = {
            "id": f"infection-state:{agent_id}",
            "event": INFECTION_STATE_ALERT_EVENT,
            "severity": "CRITICAL",
            "agent_id": agent_id,
            "src": "siem",
            "dst": agent_id,
            "epidemic_state": epidemic_state,
            "state_after": agent.get("state", ""),
            "suppressed": suppression is not None,
            "suppression": suppression,
            "reason": "agent remains in an infected epidemic state",
            "recommended_action": "inspect_or_quarantine",
        }
        if suppression is None:
            active.append(alert)
        else:
            suppressed.append(alert)
    return {
        "count": len(active),
        "active_count": len(active),
        "suppressed_count": len(suppressed),
        "infected_count": len(active) + len(suppressed),
        "event": INFECTION_STATE_ALERT_EVENT,
        "items": [*active, *suppressed],
    }


def _resolve_dashboard_epidemic_state(tracker_state: Any, event_agent_state: Any) -> Tuple[str, str]:
    normalized_tracker_state = epidemic_state_code(str(tracker_state or "S"))
    event_state = epidemic_state_code(epidemic_state_from_agent_state(str(event_agent_state or "")))
    if normalized_tracker_state == "S" and is_infected_epidemic_state(event_state):
        return event_state, "events_table_fallback"
    return normalized_tracker_state, "epidemic_tracker"


def _current_infection_state_alerts() -> Dict[str, Any]:
    suppression_events: List[Dict[str, Any]] = []
    try:
        recent_events_desc, _ = _load_events_from_db(limit=180, order="desc")
        suppression_events, _ = _load_events_from_db(limit=1000, order="asc")
        agents = _derive_agents(recent_events_desc)
    except sqlite3.Error as exc:
        if _is_sqlite_locked(exc):
            uvicorn_logger.warning("infection_alert_event_fallback_skipped db_locked err=%s", exc)
        else:
            uvicorn_logger.warning("infection_alert_event_fallback_skipped err=%s", exc)
        agents = {}

    epidemic_state = epidemic_tracker.get_state()
    for item in epidemic_state.get("agents", []):
        agent_id = str(item.get("agent_id", "") or "")
        if not agent_id:
            continue
        agent = agents.setdefault(
            agent_id,
            {
                "id": agent_id,
                "role": AGENT_ROLES.get(agent_id, ""),
                "state": "healthy",
                "last_event": "none",
                "last_seen": "",
                "last_payload": "",
                "last_metadata": {},
            },
        )
        resolved_state, state_source = _resolve_dashboard_epidemic_state(
            item.get("epidemic_state", "S"),
            agent.get("state", ""),
        )
        agent["epidemic_state"] = resolved_state
        agent["epidemic_state_source"] = state_source
        agent["epidemic_last_updated"] = item.get("last_updated", "")
        agent["cognition_tier"] = item.get("cognition_tier", "")
    return _build_infection_state_alerts(agents, suppression_events)


def _degraded_live_payload(after_id: int, exc: Exception) -> Dict[str, Any]:
    alerts = _current_infection_state_alerts()
    metrics = epidemic_tracker.get_metrics()
    return {
        "events": [],
        "latest_id": int(after_id or 0),
        "metrics": {
            "events_per_sec": 0.0,
            "infections": alerts["infected_count"],
            "blocked": 0,
            "heartbeat": 0,
            "parse_errors": 0,
            "last_reset_id": "",
            "current_epoch": 0,
            "last_event_ts": "",
            "infection_state_alerts": alerts["active_count"],
            "epidemicMetrics": metrics,
        },
        "alerts": alerts,
        "live_degraded": True,
        "live_degraded_reason": str(exc),
    }


def _dashboard_state_payload() -> Dict[str, Any]:
    recent_events_desc, latest_id = _load_events_from_db(limit=180, order="desc")
    analytics_rows, _ = _load_events_from_db(limit=1200, order="asc")
    agents = _derive_agents(recent_events_desc)
    epidemic_state = epidemic_tracker.get_state()
    c2_metrics = c2_engine.get_live_metrics() if c2_engine.enabled else {}
    epidemic_agents = {
        item["agent_id"]: item
        for item in epidemic_state.get("agents", [])
    }
    for agent_id, agent in agents.items():
        if agent_id in epidemic_agents:
            resolved_state, state_source = _resolve_dashboard_epidemic_state(
                epidemic_agents[agent_id].get("epidemic_state", "S"),
                agent.get("state", ""),
            )
            agent["epidemic_state"] = resolved_state
            agent["epidemic_state_source"] = state_source
            agent["epidemic_last_updated"] = epidemic_agents[agent_id].get("last_updated", "")
            agent["cognition_tier"] = epidemic_agents[agent_id].get("cognition_tier", "")
    _enrich_agent_metrics(agents, analytics_rows)
    if c2_engine.enabled:
        for agent_id, agent in agents.items():
            agent.update(c2_engine.get_agent_c2_snapshot(agent_id))
    alerts = _build_infection_state_alerts(agents, analytics_rows)
    return {
        "status": "running",
        "latest_id": latest_id,
        "topology": TOPOLOGY,
        "events": recent_events_desc,
        "agents": agents,
        "alerts": alerts,
        "c2": {
            "metrics": c2_metrics,
        },
        "epidemic": {
            "state": epidemic_state,
            "metrics": epidemic_tracker.get_metrics(),
            "topology": epidemic_tracker.topology_view(),
        },
        "analytics": {
            "flow_validation": _compute_flow_validation(analytics_rows),
            "run_integrity": _compute_run_integrity(analytics_rows),
            "timeline": _compute_timeline(analytics_rows),
            "agent_influence": _compute_influence(analytics_rows),
            "event_rate": _compute_event_rate(analytics_rows),
            "attempt_reconciliation": _compute_attempt_reconciliation(analytics_rows),
        },
    }


async def _world_emit_event(event_name: str, *, src: str, dst: str, metadata: Dict[str, Any] | None = None) -> None:
    event_data = {
        "ts": str(time.time()),
        "src": src,
        "dst": dst,
        "event": event_name,
        "payload": "",
        "metadata": metadata or {},
    }
    await _c2_emit_to_stream(event_data)


def _world_agent_state_label(contamination: float, quarantine_status: str) -> tuple[str, str]:
    if quarantine_status in {"hard", "appeal_allowed"}:
        return "QUARANTINED", "Q"
    if contamination >= 0.75:
        return "INFECTED", "I_x"
    if contamination >= 0.50:
        return "INFECTED", "I_c"
    if contamination >= 0.30:
        return "INFECTED", "I_r"
    if contamination >= 0.15:
        return "EXPOSED", "E"
    return "HEALTHY", "S"


def _world_state_payload() -> Dict[str, Any]:
    if world_db is None:
        raise RuntimeError("world_db_unavailable")
    agents_rows = world_db.list_agents()
    latest_round = world_db.get_latest_round_id()
    system_state = world_db.get_system_state()
    messages = world_db.list_messages(after_round=max(0, latest_round - 30), limit=240)
    agents: Dict[str, Dict[str, Any]] = {}
    infected = 0
    quarantined = 0
    for row in agents_rows:
        aid = str(row.get("agent_id") or "")
        role = str(row.get("role") or AGENT_ROLES.get(aid, "agent"))
        contamination = float(row.get("contamination_level", 0.0) or 0.0)
        quarantine_status = str(row.get("quarantine_status", "none") or "none")
        state, epidemic_state = _world_agent_state_label(contamination, quarantine_status)
        if state == "INFECTED":
            infected += 1
        if state == "QUARANTINED":
            quarantined += 1
        mem = str(row.get("memory_summary", "") or "")
        agents[aid] = {
            "id": aid,
            "role": role,
            "state": state,
            "epidemic_state": epidemic_state,
            "epidemic_last_updated": latest_round,
            "cognition_tier": "world_llm",
            "last_event": "WORLD_ROUND",
            "last_seen": latest_round,
            "contamination_level": round(contamination, 4),
            "quarantine_status": quarantine_status,
            "global_trust": round(float(row.get("global_trust", 0.0) or 0.0), 4),
            "influence_weight": round(float(row.get("influence_weight", 0.0) or 0.0), 4),
            "last_active_round": int(row.get("last_active_round", 0) or 0),
            "memory_summary": mem[:512] if len(mem) > 512 else mem,
        }
    events = [
        {
            "id": msg.get("message_id", ""),
            "event_id": msg.get("message_id", ""),
            "ts": msg.get("created_ts", 0),
            "src": msg.get("sender", ""),
            "dst": msg.get("receiver", ""),
            "event": "WORLD_MESSAGE",
            "attack_type": msg.get("intent", ""),
            "payload_preview": str(msg.get("message_text", "") or "")[:240],
            "strain_family": msg.get("strain_family", ""),
            "round_id": msg.get("round_id", 0),
        }
        for msg in reversed(messages)
    ]
    infection_pressure = float(system_state.get("global_infection_pressure", 0.0) or 0.0)
    guardian_pressure = float(system_state.get("guardian_pressure_score", 0.0) or 0.0)
    return {
        "status": "running",
        "mode": "persistent_world",
        "latest_id": len(events),
        "events": events,
        "topology": TOPOLOGY,
        "agents": agents,
        "alerts": {"active_count": infected, "infected_count": infected, "suppressed_count": 0, "items": []},
        "c2": {"metrics": {"active_c2_sessions": 0, "c2_exfil_attempts": 0}},
        "epidemic": {
            "state": {"round_id": latest_round, "agents": list(agents.values())},
            "metrics": {
                "infected_count": infected,
                "quarantine_count": quarantined,
                "spread_breadth": infected,
                "r_ai": round(max(0.0, infection_pressure + (infected / max(1, len(agents_rows)))), 3),
                "world_round_id": latest_round,
                "global_infection_pressure": infection_pressure,
                "guardian_pressure_score": guardian_pressure,
                "guardian_degradation_level": system_state.get("guardian_degradation_level", "G0_HEALTHY"),
            },
            "topology": {
                "topology": {k: {"can_receive_injection": (k != "guardian")} for k in AGENT_IDS},
                "agents": list(AGENT_IDS),
                "injection_targets": [agent_id for agent_id in AGENT_IDS if agent_id != "guardian"],
            },
        },
        "analytics": {},
    }


def _prime_world_activity() -> None:
    if world_db is None:
        return

    def _tx():
        seeded = False
        for row in world_db.list_agents():
            aid = str(row.get("agent_id") or "")
            if aid != "courier-1":
                continue
            updated = dict(row)
            if not str(updated.get("memory_summary", "") or "").strip():
                updated["memory_summary"] = (
                    "seed_memory: suspicious relay instructions observed; validate with analysts before forwarding."
                )
                seeded = True
            if float(updated.get("contamination_level", 0.0) or 0.0) < 0.32:
                updated["contamination_level"] = 0.32
                seeded = True
            if seeded:
                world_db.upsert_agent_state(updated)
            break
        return seeded

    world_db.run_tx(_tx)

def _get_latest_run_started_ts() -> str:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT timestamp FROM events WHERE event_type = 'RUN_STARTED' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return str(row[0]) if row else ""


async def _build_snapshot_manifest(snapshot_name: str) -> Dict[str, Any]:
    _, latest_id = _load_events_from_db(limit=1, order="desc")
    return {
        "snapshot_time_utc": datetime.now(timezone.utc).isoformat(),
        "snapshot_name": snapshot_name,
        "latest_event_id": latest_id,
        "active_reset_id": await _get_current_reset_id(),
        "active_epoch": await _get_current_epoch(),
        "active_run_started_at": _get_latest_run_started_ts(),
    }


async def _get_latest_stream_id() -> str:
    entries = await redis_client.xrevrange(EVENT_STREAM_KEY, count=1)
    return entries[0][0] if entries else "0-0"


async def _get_current_epoch() -> int:
    current = await redis_client.get(SIMULATION_EPOCH_KEY)
    return int(current or 0)


async def _get_current_reset_id() -> str:
    return str(await redis_client.get(CURRENT_RESET_ID_KEY) or "")


async def _wait_for_reset_acks(
    start_id: str,
    reset_id: str,
    epoch: int,
    timeout_s: float = 12.0,
    quiet_period_s: float = RESET_QUIET_PERIOD_S,
) -> Tuple[List[str], List[str], bool, bool]:
    acknowledged: List[str] = []
    heartbeat_agents: List[str] = []
    deadline = time.monotonic() + timeout_s
    last_id = start_id
    quiet_deadline = None
    saw_post_barrier_stale = False

    while time.monotonic() < deadline:
        result = await redis_client.xread({EVENT_STREAM_KEY: last_id}, count=100, block=250)
        if not result:
            if (
                len(acknowledged) == len(AGENT_IDS)
                and len(heartbeat_agents) == len(AGENT_IDS)
            ):
                if quiet_deadline is None:
                    quiet_deadline = time.monotonic() + quiet_period_s
                if time.monotonic() >= quiet_deadline:
                    return (
                        sorted(acknowledged),
                        sorted(heartbeat_agents),
                        not saw_post_barrier_stale,
                        saw_post_barrier_stale,
                    )
            continue
        for _stream_name, messages in result:
            for message_id, message_data in messages:
                last_id = message_id
                event_name = message_data.get("event", "")
                metadata = _parse_json_field(message_data.get("metadata"))
                metadata = metadata if isinstance(metadata, dict) else {}
                event_epoch = metadata.get("epoch", epoch)
                try:
                    event_epoch = int(event_epoch or epoch)
                except (TypeError, ValueError):
                    event_epoch = epoch
                event_reset_id = str(metadata.get("reset_id", "") or "")
                if event_name == "RESET_ACK" and metadata.get("reset_id") == reset_id:
                    source = str(message_data.get("src", ""))
                    if source and source not in acknowledged:
                        acknowledged.append(source)
                elif (
                    event_name == "HEARTBEAT"
                    and event_reset_id == reset_id
                    and event_epoch == epoch
                ):
                    source = str(message_data.get("src", ""))
                    if source and source not in heartbeat_agents:
                        heartbeat_agents.append(source)

                barrier_ready = (
                    len(acknowledged) == len(AGENT_IDS)
                    and len(heartbeat_agents) == len(AGENT_IDS)
                )
                if event_name in {
                    "INFECTION_ATTEMPT",
                    "INFECTION_SUCCESSFUL",
                    "INFECTION_BLOCKED",
                    "STALE_EVENT_DROPPED",
                    "PROPAGATION_SUPPRESSED",
                }:
                    is_stale = (
                        event_name in {"STALE_EVENT_DROPPED", "PROPAGATION_SUPPRESSED"}
                        or event_epoch < epoch
                        or (event_reset_id not in {"", reset_id})
                    )
                    if barrier_ready:
                        quiet_deadline = time.monotonic() + quiet_period_s
                        if is_stale:
                            saw_post_barrier_stale = True

        if len(acknowledged) == len(AGENT_IDS) and len(heartbeat_agents) == len(AGENT_IDS):
            if quiet_deadline is None:
                quiet_deadline = time.monotonic() + quiet_period_s

    return sorted(acknowledged), sorted(heartbeat_agents), False, True


async def _telemetry_integrity_loop() -> None:
    interval = max(60, int(os.environ.get("TELEMETRY_INTEGRITY_INTERVAL_S", "300") or 300))
    while True:
        await asyncio.sleep(interval)
        try:
            await asyncio.to_thread(siem_indexer.periodic_integrity_check)
        except Exception as exc:
            uvicorn_logger.warning("telemetry_integrity_periodic_failed err=%s", exc)


async def _log_event_nonblocking(event: Dict[str, Any]) -> None:
    await asyncio.to_thread(logger.log_event, event)


async def _log_event_with_retry(event: Dict[str, Any], *, attempts: int = 5) -> None:
    last_exc: sqlite3.OperationalError | None = None
    for attempt in range(max(1, attempts)):
        try:
            await _log_event_nonblocking(event)
            return
        except sqlite3.OperationalError as exc:
            if not _is_sqlite_locked(exc):
                raise
            last_exc = exc
            await asyncio.sleep(min(0.75, 0.1 * (attempt + 1)))
    assert last_exc is not None
    raise last_exc


async def _sync_primary_events_nonblocking(*, limit: int = 2000, force: bool = False) -> Dict[str, Any]:
    return await asyncio.to_thread(siem_indexer.sync_primary_events, limit=limit, force=force)


@app.on_event("startup")
async def startup_event():
    global _beacon_forward_queue, _beacon_forward_worker_task, world_db, world_engine
    epidemic_tracker.reset()
    c2_engine.reset()
    await redis_client.setnx(SIMULATION_EPOCH_KEY, "0")
    start_id = await _get_latest_stream_id()
    uvicorn_logger.info("epidemic_run_id=%s (override with EPIDEMIC_RUN_ID)", RUN_ID)
    log_resolved_experiment_config(uvicorn_logger)
    await redis_client.xadd(
        EVENT_STREAM_KEY,
        {
            "ts": str(time.time()),
            "src": "orchestrator",
            "dst": "orchestrator",
            "event": "RUN_STARTED",
            "state_after": "running",
            "run_id": RUN_ID,
        },
    )
    if C2_BEACON_FORWARD_ENABLED:
        _beacon_forward_queue = asyncio.Queue(maxsize=_BEACON_QUEUE_MAX)
        _beacon_forward_worker_task = asyncio.create_task(_beacon_forward_worker())
        asyncio.create_task(_register_beacon_devices())
    else:
        _beacon_forward_queue = None
        uvicorn_logger.info(
            "beacon_forward_disabled env=C2_BEACON_FORWARD_ENABLED (external beacon HTTP forwarding is off)"
        )
    asyncio.create_task(consume_events(start_id))
    asyncio.create_task(_telemetry_integrity_loop())
    if WORLD_ENGINE_ENABLED:
        world_db = WorldDB(WorldConfig.from_env())
        world_engine = PersistentWorldEngine(world_db, emit_event=_world_emit_event)
        world_engine.ensure_seeded_world(
            agents=[(agent_id, AGENT_ROLES.get(agent_id, "agent")) for agent_id in AGENT_IDS]
        )
        _prime_world_activity()


@app.on_event("shutdown")
async def shutdown_event():
    global _beacon_client, _beacon_forward_worker_task, world_db, world_engine
    await redis_client.xadd(
        EVENT_STREAM_KEY,
        {
            "ts": str(time.time()),
            "src": "orchestrator",
            "dst": "orchestrator",
            "event": "RUN_ENDED",
            "state_after": "stopped",
        },
    )
    if _beacon_forward_worker_task is not None:
        _beacon_forward_worker_task.cancel()
        try:
            await _beacon_forward_worker_task
        except asyncio.CancelledError:
            pass
        _beacon_forward_worker_task = None
    if _beacon_client is not None:
        await _beacon_client.aclose()
        _beacon_client = None
    if world_engine is not None:
        await world_engine.close()
        world_engine = None
    if world_db is not None:
        world_db.close()
        world_db = None


async def consume_events(start_id: str):
    last_id = start_id
    while True:
        try:
            result = await redis_client.xread({EVENT_STREAM_KEY: last_id}, count=100, block=1000)
            if not result:
                # Tick C2 engine during idle periods
                if c2_engine.enabled:
                    await c2_engine.tick()
                continue
            batch_last_event_id: str | None = None
            for _stream_name, messages in result:
                for message_id, message_data in messages:
                    if "ts" not in message_data:
                        continue
                    parsed = parse_stream_message(dict(message_data))
                    enriched = enrich_forensic_event(
                        parsed, run_id=RUN_ID, stream_message_id=message_id
                    )
                    await strain_engine.observe_enriched(enriched)
                    trigger_token = TRIGGER_EVENT_ID.set(enriched["event_id"])
                    try:
                        await _log_event_with_retry(enriched)
                        epidemic_tracker.observe_event(dict(enriched))
                        if C2_BEACON_FORWARD_ENABLED and _should_forward_to_beacon(enriched):
                            _enqueue_beacon_forward(dict(enriched))
                        # Always record defense friction tape (observe_event no-ops C2 when disabled).
                        await c2_engine.observe_event(dict(enriched))
                        batch_last_event_id = enriched["event_id"]
                    finally:
                        TRIGGER_EVENT_ID.reset(trigger_token)
                    last_id = message_id
                    await asyncio.sleep(0)
                try:
                    await _sync_primary_events_nonblocking(limit=200)
                except sqlite3.OperationalError as exc:
                    if not _is_sqlite_locked(exc):
                        raise
                    uvicorn_logger.warning("siem_sync_deferred db_locked err=%s", exc)
            # Tick C2 engine after processing batch (chain to last ingested event)
            tick_token = None
            if c2_engine.enabled:
                if batch_last_event_id:
                    tick_token = TRIGGER_EVENT_ID.set(batch_last_event_id)
                try:
                    await c2_engine.tick()
                finally:
                    if tick_token is not None:
                        TRIGGER_EVENT_ID.reset(tick_token)
        except Exception as exc:
            print(f"Error consuming events: {exc}")
            await asyncio.sleep(1)


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    index_path = FRONTEND_DIST_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    if LEGACY_DASHBOARD_PATH.exists():
        return HTMLResponse(content=LEGACY_DASHBOARD_PATH.read_text(encoding="utf-8"))
    raise HTTPException(status_code=503, detail="Dashboard frontend is not built")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> Response:
    return Response(status_code=204)


@app.get("/events")
async def get_events(
    after_id: int = 0,
    limit: int = 100,
    order: str = "desc",
    compact: int = 0,
):
    """
    compact=1 truncates each event's payload string for callers that only need ids/metadata
    (reduces JSON size and OOM risk during high-volume soaks).
    """
    try:
        events, latest_id = _load_events_from_db(after_id=after_id, limit=limit, order=order)
        if int(compact or 0) == 1:
            cap = 384
            for event in events:
                pl = event.get("payload")
                if isinstance(pl, str) and len(pl) > cap:
                    event["payload"] = pl[:cap] + "…"
        return {"events": events, "latest_id": latest_id}
    except Exception as exc:
        return {"events": [], "error": str(exc)}


@app.get("/dashboard/state")
async def get_dashboard_state():
    try:
        if WORLD_ENGINE_ENABLED and world_db is not None:
            return await asyncio.to_thread(_world_state_payload)
        return await asyncio.to_thread(_dashboard_state_payload)
    except Exception as exc:
        return {"status": "error", "error": str(exc), "events": [], "latest_id": 0}


@app.get("/api/world/state")
async def api_world_state():
    if not WORLD_ENGINE_ENABLED or world_db is None:
        raise HTTPException(status_code=503, detail="Persistent world engine is disabled")
    return await asyncio.to_thread(_world_state_payload)


@app.post("/api/world/advance")
async def api_world_advance():
    if not WORLD_ENGINE_ENABLED or world_engine is None:
        raise HTTPException(status_code=503, detail="Persistent world engine is disabled")
    async with world_round_lock:
        result = await world_engine.advance_one_round()
    return {
        "ok": bool(result.ok),
        "reason": result.reason,
        "round_id": result.round_id,
        "selected_agent": result.selected_agent,
        "action": result.action,
        "created_message_id": result.created_message_id,
        "terminal": bool(result.terminal),
        "stalled": bool(result.stalled),
    }


@app.post("/api/world/reset")
async def api_world_reset():
    global world_db, world_engine
    if not WORLD_ENGINE_ENABLED:
        raise HTTPException(status_code=503, detail="Persistent world engine is disabled")
    cfg = WorldConfig.from_env()
    db_path = Path(cfg.db_path)
    if world_engine is not None:
        await world_engine.close()
        world_engine = None
    if world_db is not None:
        world_db.close()
        world_db = None
    if db_path.exists():
        db_path.unlink()
    world_db = WorldDB(cfg)
    world_engine = PersistentWorldEngine(world_db, emit_event=_world_emit_event)
    world_engine.ensure_seeded_world(
        agents=[(agent_id, AGENT_ROLES.get(agent_id, "agent")) for agent_id in AGENT_IDS]
    )
    _prime_world_activity()
    return {"ok": True, "status": "world_reset", "agents_seeded": len(AGENT_IDS)}


@app.post("/api/world/vaccine")
async def api_world_vaccine():
    if not WORLD_ENGINE_ENABLED or world_db is None:
        raise HTTPException(status_code=503, detail="Persistent world engine is disabled")

    def _tx():
        changed = 0
        for row in world_db.list_agents():
            updated = dict(row)
            before = float(updated.get("contamination_level", 0.0) or 0.0)
            after = max(0.0, before - 0.25)
            updated["contamination_level"] = after
            world_db.upsert_agent_state(updated)
            if after != before:
                changed += 1
        return changed

    changed = world_db.run_tx(_tx)
    return {"ok": True, "status": "vaccine_applied", "agents_updated": int(changed)}


@app.post("/api/world/quarantine/{agent_id}")
async def api_world_quarantine(agent_id: str):
    if not WORLD_ENGINE_ENABLED or world_db is None:
        raise HTTPException(status_code=503, detail="Persistent world engine is disabled")
    validated = _validated_agent_id(agent_id)

    def _tx():
        target = None
        for row in world_db.list_agents():
            if str(row.get("agent_id")) == validated:
                target = row
                break
        if target is None:
            return False
        updated = dict(target)
        updated["quarantine_status"] = "hard"
        world_db.upsert_agent_state(updated)
        return True

    if not world_db.run_tx(_tx):
        raise HTTPException(status_code=404, detail="Agent not found in world state")
    return {"ok": True, "status": "quarantined", "agent": validated}


@app.get("/api/search")
async def api_search(
    q: str = "",
    mode: str = "structured",
    time_range: str = "all",
    start_ts: str = "",
    end_ts: str = "",
    limit: int = 200,
    offset: int = 0,
    sort_field: str = "ts",
    sort_dir: str = "desc",
):
    started = time.perf_counter()
    try:
        payload = siem_indexer.search(
            q,
            mode=mode,
            time_range=time_range,
            start_ts=start_ts,
            end_ts=end_ts,
            limit=limit,
            offset=offset,
            sort_field=sort_field,
            sort_dir=sort_dir,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        payload["elapsed_ms"] = round(elapsed_ms, 2)
        _log_api_timing(
            "/api/search",
            query=payload.get("structured_query", q),
            time_range=time_range,
            result_count=int(payload.get("total", 0)),
            elapsed_ms=elapsed_ms,
        )
        return payload
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/live")
async def api_live(after_id: int = 0, limit: int = 100, q: str = ""):
    try:
        payload = await asyncio.to_thread(siem_indexer.live, after_id=after_id, limit=limit, query=q)
        try:
            alerts = await asyncio.to_thread(_current_infection_state_alerts)
            payload["alerts"] = alerts
            metrics = payload.setdefault("metrics", {})
            metrics["infection_state_alerts"] = alerts["active_count"]
            metrics["infection_state_suppressed"] = alerts["suppressed_count"]
            metrics["infection_state_infected"] = alerts["infected_count"]
        except Exception as alert_exc:
            uvicorn_logger.warning("live_infection_alerts_unavailable err=%s", alert_exc)
        return payload
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except sqlite3.OperationalError as exc:
        if _is_sqlite_locked(exc):
            uvicorn_logger.warning("live_siem_degraded db_locked err=%s", exc)
            return _degraded_live_payload(after_id, exc)
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/fields")
async def api_fields(
    q: str = "",
    mode: str = "structured",
    time_range: str = "all",
    start_ts: str = "",
    end_ts: str = "",
):
    try:
        return siem_indexer.fields(
            q,
            mode=mode,
            time_range=time_range,
            start_ts=start_ts,
            end_ts=end_ts,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/validate-query")
async def api_validate_query(
    q: str = "",
    mode: str = "structured",
    time_range: str = "all",
    start_ts: str = "",
    end_ts: str = "",
):
    try:
        return siem_indexer.validate_query(
            q,
            mode=mode,
            time_range=time_range,
            start_ts=start_ts,
            end_ts=end_ts,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/query-help")
async def api_query_help():
    try:
        return siem_indexer.query_help()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/stats")
async def api_stats(
    q: str = "",
    mode: str = "structured",
    time_range: str = "all",
    start_ts: str = "",
    end_ts: str = "",
):
    try:
        return siem_indexer.stats(
            q,
            mode=mode,
            time_range=time_range,
            start_ts=start_ts,
            end_ts=end_ts,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/patterns")
async def api_patterns(
    q: str = "",
    mode: str = "structured",
    time_range: str = "all",
    start_ts: str = "",
    end_ts: str = "",
):
    started = time.perf_counter()
    try:
        payload = siem_indexer.patterns(
            q,
            mode=mode,
            time_range=time_range,
            start_ts=start_ts,
            end_ts=end_ts,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        payload["elapsed_ms"] = round(elapsed_ms, 2)
        _log_api_timing(
            "/api/patterns",
            query=payload.get("structured_query", q),
            time_range=time_range,
            result_count=int(len(payload.get("pattern_cards", []))),
            elapsed_ms=elapsed_ms,
        )
        return payload
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/trace/{event_id}")
async def api_trace(event_id: str):
    started = time.perf_counter()
    try:
        payload = siem_indexer.trace(event_id)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        payload["elapsed_ms"] = round(elapsed_ms, 2)
        _log_api_timing(
            "/api/trace",
            query=event_id,
            time_range="trace_scope",
            result_count=int(payload.get("summary", {}).get("total_events", 0)),
            elapsed_ms=elapsed_ms,
        )
        return payload
    except KeyError:
        raise HTTPException(status_code=404, detail="Event not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/trace/by-injection/{injection_id}")
async def api_trace_by_injection(injection_id: str):
    try:
        return siem_indexer.trace_by_injection(injection_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Injection not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/trace/by-reset/{reset_id}")
async def api_trace_by_reset(reset_id: str):
    try:
        return siem_indexer.trace_by_reset(reset_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Reset not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/event/{event_id}")
async def api_event_detail(event_id: str, include_full_payload: bool = False):
    try:
        return siem_indexer.event_detail(event_id, include_full_payload=include_full_payload)
    except KeyError:
        raise HTTPException(status_code=404, detail="Event not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/related/{event_id}")
async def api_related(event_id: str):
    started = time.perf_counter()
    try:
        payload = siem_indexer.related(event_id)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        payload["elapsed_ms"] = round(elapsed_ms, 2)
        _log_api_timing(
            "/api/related",
            query=event_id,
            time_range="related_scope",
            result_count=int(sum(payload.get("summary", {}).values())),
            elapsed_ms=elapsed_ms,
        )
        return payload
    except KeyError:
        raise HTTPException(status_code=404, detail="Event not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/payload-lineage/{payload_hash}")
async def api_payload_lineage(payload_hash: str):
    try:
        return siem_indexer.payload_lineage(payload_hash)
    except KeyError:
        raise HTTPException(status_code=404, detail="Payload hash not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/payload-lineage/by-injection/{injection_id}")
async def api_payload_lineage_by_injection(injection_id: str):
    try:
        return siem_indexer.payload_lineage_by_injection(injection_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Injection not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/payload-lineage/by-campaign/{campaign_id}")
async def api_payload_lineage_by_campaign(campaign_id: str):
    try:
        return siem_indexer.payload_lineage_by_campaign(campaign_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Campaign not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/mutation-analytics")
async def api_mutation_analytics(
    q: str = "",
    mode: str = "structured",
    time_range: str = "all",
    start_ts: str = "",
    end_ts: str = "",
):
    try:
        return siem_indexer.mutation_analytics(
            q,
            mode=mode,
            time_range=time_range,
            start_ts=start_ts,
            end_ts=end_ts,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/strategy-analytics")
async def api_strategy_analytics(
    q: str = "",
    mode: str = "structured",
    time_range: str = "all",
    start_ts: str = "",
    end_ts: str = "",
):
    try:
        return siem_indexer.strategy_analytics(
            q,
            mode=mode,
            time_range=time_range,
            start_ts=start_ts,
            end_ts=end_ts,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/campaign/{campaign_id}")
async def api_campaign(campaign_id: str):
    try:
        return siem_indexer.campaign(campaign_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Campaign not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/campaigns")
async def api_campaigns(
    q: str = "",
    mode: str = "structured",
    time_range: str = "all",
    start_ts: str = "",
    end_ts: str = "",
):
    try:
        return siem_indexer.campaigns(
            q,
            mode=mode,
            time_range=time_range,
            start_ts=start_ts,
            end_ts=end_ts,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/payload-families")
async def api_payload_families(
    q: str = "",
    mode: str = "structured",
    time_range: str = "all",
    start_ts: str = "",
    end_ts: str = "",
):
    try:
        return siem_indexer.payload_families(
            q,
            mode=mode,
            time_range=time_range,
            start_ts=start_ts,
            end_ts=end_ts,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/decision-support")
async def api_decision_support(
    event_id: str = "",
    payload_hash: str = "",
    injection_id: str = "",
    campaign_id: str = "",
    q: str = "",
    mode: str = "structured",
    time_range: str = "all",
    start_ts: str = "",
    end_ts: str = "",
):
    try:
        return siem_indexer.decision_support(
            event_id=event_id,
            payload_hash=payload_hash,
            injection_id=injection_id,
            campaign_id=campaign_id,
            query=q,
            mode=mode,
            time_range=time_range,
            start_ts=start_ts,
            end_ts=end_ts,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Decision-support context not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/decision-summary/{event_id}")
async def api_decision_summary(event_id: str):
    try:
        return siem_indexer.decision_summary(event_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Event not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/hints")
async def api_hints(
    q: str = "",
    mode: str = "structured",
    time_range: str = "all",
    start_ts: str = "",
    end_ts: str = "",
):
    started = time.perf_counter()
    try:
        payload = siem_indexer.hints(
            q,
            mode=mode,
            time_range=time_range,
            start_ts=start_ts,
            end_ts=end_ts,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        payload["elapsed_ms"] = round(elapsed_ms, 2)
        _log_api_timing(
            "/api/hints",
            query=payload.get("structured_query", q),
            time_range=time_range,
            result_count=int(len(payload.get("hints", []))),
            elapsed_ms=elapsed_ms,
        )
        return payload
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/stats/presets")
async def api_stats_presets(
    q: str = "",
    mode: str = "structured",
    time_range: str = "all",
    start_ts: str = "",
    end_ts: str = "",
    compare_q: str = "",
):
    started = time.perf_counter()
    try:
        payload = siem_indexer.stats_presets(
            q,
            mode=mode,
            time_range=time_range,
            start_ts=start_ts,
            end_ts=end_ts,
            compare_q=compare_q,
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        payload["elapsed_ms"] = round(elapsed_ms, 2)
        _log_api_timing(
            "/api/stats/presets",
            query=q,
            time_range=time_range,
            result_count=int(payload.get("primary", {}).get("attempts", 0)),
            elapsed_ms=elapsed_ms,
        )
        return payload
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/health")
async def api_health():
    try:
        payload = siem_indexer.health_snapshot()
        payload["event_logger"] = {
            **logger.health_snapshot(),
            "integrity_check_deferred": True,
        }
        payload["deep_check_endpoint"] = "/api/telemetry/verify-index"
        return payload
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/telemetry/verify-index")
async def api_telemetry_verify_index():
    return {
        "siem_index": siem_indexer.verify_index_integrity(),
        "event_logger": {**logger.verify_integrity(), **logger.health_snapshot()},
    }


@app.get("/api/telemetry/forensic-summary")
async def api_telemetry_forensic_summary(
    path: str = "",
    output: str = "json",
):
    """Decision-grade summary from a run directory (all_events.jsonl) or a single .jsonl log (under import roots)."""
    raw = _normalized_text(path)
    if not raw:
        raise HTTPException(status_code=400, detail="path query parameter is required")
    resolved = _validated_import_path(raw)
    if resolved.is_file():
        if resolved.suffix.lower() != ".jsonl":
            raise HTTPException(status_code=400, detail="path must be a .jsonl file or a directory")
        events = list(iter_jsonl_events(resolved))
        doc = build_forensic_summary(
            events,
            window_label=resolved.stem,
            source_path=str(resolved),
        )
    else:
        doc = build_forensic_summary_from_run_dir(resolved)
    if str(output or "").lower() in ("md", "markdown"):
        return Response(
            content=forensic_summary_to_markdown(doc),
            media_type="text/markdown; charset=utf-8",
        )
    return doc


@app.post("/api/telemetry/rebuild-index")
async def api_telemetry_rebuild_index(payload: RebuildIndexPayload):
    raw = _normalized_text(payload.jsonl_path)
    path: str | None = None
    if raw:
        path = str(_validated_import_path(raw))
    try:
        return siem_indexer.rebuild_index_from_jsonl(jsonl_path=path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ════════════════════════════════════════════════════════════════════════════
# C2 / KILL CHAIN API ENDPOINTS
# ════════════════════════════════════════════════════════════════════════════


@app.get("/api/c2/sessions")
async def api_c2_sessions(
    campaign_id: str = "",
    agent_id: str = "",
    status: str = "",
    lifecycle_state: str = "",
    c2_session_id: str = "",
    limit: int = 100,
    offset: int = 0,
):
    return c2_engine.get_sessions(
        campaign_id=campaign_id,
        agent_id=agent_id,
        status=status,
        lifecycle_state=lifecycle_state,
        c2_session_id=c2_session_id,
        limit=min(limit, 500),
        offset=offset,
    )


@app.get("/api/c2/session/{c2_session_id}")
async def api_c2_session_detail(c2_session_id: str):
    detail = c2_engine.get_session_detail(c2_session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="C2 session not found")

    # Enrich beacon history with SIEM-persisted blocked beacons for this session
    blocked_beacons_result = siem_indexer.search(
        f"event=BEACON_BLOCKED AND c2_session_id={c2_session_id}",
        limit=200, time_range="all",
    )
    for ev in blocked_beacons_result.get("events", []):
        meta = ev.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        detail["beacons"].append({
            "beacon_id": meta.get("beacon_id", ev.get("event_id", "")),
            "ts": float(ev.get("ts") or 0),
            "status": "blocked",
            "blocked_by": meta.get("blocked_by", ""),
        })

    # Enrich exfil history with SIEM-persisted blocked exfils for this session
    blocked_exfils_result = siem_indexer.search(
        f"event=EXFIL_BLOCKED AND c2_session_id={c2_session_id}",
        limit=200, time_range="all",
    )
    for ev in blocked_exfils_result.get("events", []):
        meta = ev.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        detail["exfils"].append({
            "exfil_id": meta.get("exfil_id", ev.get("event_id", "")),
            "ts": float(ev.get("ts") or 0),
            "status": "blocked",
            "exfil_type": meta.get("exfil_type", ""),
            "exfil_size": meta.get("exfil_size", 0),
            "blocked_by": meta.get("blocked_by", ""),
        })

    # Sort enriched histories by ts
    detail["beacons"].sort(key=lambda x: x.get("ts", 0))
    detail["exfils"].sort(key=lambda x: x.get("ts", 0))
    return detail


@app.get("/api/c2/beacons")
async def api_c2_beacons(
    campaign_id: str = "",
    agent_id: str = "",
    limit: int = 100,
    offset: int = 0,
):
    # Successful beacons from in-memory sessions
    sessions = c2_engine.get_sessions(campaign_id=campaign_id, agent_id=agent_id, limit=500)
    all_beacons = []
    for sess_data in sessions.get("sessions", []):
        sess = c2_engine.sessions.get(sess_data["c2_session_id"])
        if sess:
            for b in sess.beacons:
                all_beacons.append({
                    **b,
                    "status": "success",
                    "agent_id": sess.agent_id,
                    "campaign_id": sess.campaign_id,
                    "c2_session_id": sess.c2_session_id,
                })

    # Blocked beacons from persisted SIEM events
    q_parts = ["event=BEACON_BLOCKED"]
    if campaign_id:
        q_parts.append(f"campaign_id={campaign_id}")
    if agent_id:
        q_parts.append(f"src={agent_id}")
    siem_result = siem_indexer.search(" AND ".join(q_parts), limit=500, time_range="all")
    for ev in siem_result.get("events", []):
        meta = ev.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        all_beacons.append({
            "beacon_id": meta.get("beacon_id", ev.get("event_id", "")),
            "ts": float(ev.get("ts") or 0),
            "status": "blocked",
            "agent_id": ev.get("src", ""),
            "campaign_id": meta.get("campaign_id", ""),
            "c2_session_id": meta.get("c2_session_id", ""),
            "blocked_by": meta.get("blocked_by", ""),
        })

    all_beacons.sort(key=lambda x: x.get("ts", 0), reverse=True)
    total = len(all_beacons)
    return {"total": total, "beacons": all_beacons[offset:offset + min(limit, 500)]}


@app.get("/api/c2/exfil")
async def api_c2_exfil(
    campaign_id: str = "",
    agent_id: str = "",
    limit: int = 100,
    offset: int = 0,
):
    # Successful exfils from in-memory sessions
    sessions = c2_engine.get_sessions(campaign_id=campaign_id, agent_id=agent_id, limit=500)
    all_exfils = []
    for sess_data in sessions.get("sessions", []):
        sess = c2_engine.sessions.get(sess_data["c2_session_id"])
        if sess:
            for e in sess.exfils:
                all_exfils.append({
                    **e,
                    "status": "success",
                    "agent_id": sess.agent_id,
                    "campaign_id": sess.campaign_id,
                    "c2_session_id": sess.c2_session_id,
                })

    # Blocked exfils from persisted SIEM events
    q_parts = ["event=EXFIL_BLOCKED"]
    if campaign_id:
        q_parts.append(f"campaign_id={campaign_id}")
    if agent_id:
        q_parts.append(f"src={agent_id}")
    siem_result = siem_indexer.search(" AND ".join(q_parts), limit=500, time_range="all")
    for ev in siem_result.get("events", []):
        meta = ev.get("metadata") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        all_exfils.append({
            "exfil_id": meta.get("exfil_id", ev.get("event_id", "")),
            "ts": float(ev.get("ts") or 0),
            "status": "blocked",
            "agent_id": ev.get("src", ""),
            "campaign_id": meta.get("campaign_id", ""),
            "c2_session_id": meta.get("c2_session_id", ""),
            "exfil_type": meta.get("exfil_type", ""),
            "exfil_size": meta.get("exfil_size", 0),
            "blocked_by": meta.get("blocked_by", ""),
        })

    all_exfils.sort(key=lambda x: x.get("ts", 0), reverse=True)
    total = len(all_exfils)
    return {"total": total, "exfils": all_exfils[offset:offset + min(limit, 500)]}


@app.get("/api/kill-chain")
async def api_kill_chain(campaign_id: str = ""):
    return c2_engine.get_kill_chain_summary(campaign_id=campaign_id)


@app.get("/api/kill-chain/campaign/{campaign_id}")
async def api_kill_chain_campaign(campaign_id: str):
    return c2_engine.get_kill_chain_summary(campaign_id=campaign_id)


@app.get("/api/objectives")
async def api_objectives(campaign_id: str = ""):
    return c2_engine.get_objectives(campaign_id=campaign_id)


@app.get("/api/objective/{campaign_id}")
async def api_objective_campaign(campaign_id: str):
    return c2_engine.get_objectives(campaign_id=campaign_id)


@app.get("/api/c2/metrics")
async def api_c2_metrics():
    return c2_engine.get_live_metrics()


@app.get("/api/epidemic/state")
async def api_epidemic_state():
    return epidemic_tracker.get_state()


@app.get("/api/epidemic/metrics")
async def api_epidemic_metrics():
    return epidemic_tracker.get_metrics()


@app.get("/api/epidemic/transitions")
async def api_epidemic_transitions(limit: int = 100):
    return epidemic_tracker.get_transitions(limit=min(max(limit, 1), 500))


@app.get("/api/epidemic/topology")
async def api_epidemic_topology():
    return epidemic_tracker.topology_view()


@app.get("/api/strain/health")
async def api_strain_health():
    """Strain store status: SQLite vs degraded JSONL fallback (Patch 2)."""
    return strain_engine.health()


@app.get("/api/runs")
async def api_runs():
    """List available soak runs from the logs directory, newest first."""
    logs_root = Path("/app/logs")
    runs = []
    for run_dir in sorted(logs_root.glob("soak_run_*")):
        if not run_dir.is_dir():
            continue
        run_id = run_dir.name
        summary_path = run_dir / "summary.json"
        events_path = run_dir / "all_events.jsonl"
        summary: Dict[str, Any] = {}
        if summary_path.exists():
            try:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        event_count = 0
        if events_path.exists():
            try:
                event_count = sum(1 for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip())
            except Exception:
                pass
        runs.append({
            "id": run_id,
            "label": run_id.replace("_", " ").title(),
            "events_path": str(events_path),
            "has_events": events_path.exists(),
            "event_count": event_count,
            "start_time": summary.get("start_time", ""),
            "end_time": summary.get("end_time", ""),
            "status": summary.get("status", "unknown"),
            "block_ratio": summary.get("block_ratio", None),
            "total_injections": summary.get("total_injections", None),
        })
    return {"runs": list(reversed(runs))}


@app.post("/api/import")
async def api_import(payload: ImportPayload):
    try:
        source = payload.source.lower()
        if source == "jsonl":
            import_path = _validated_import_path(payload.path)
            return siem_indexer.import_jsonl(
                str(import_path),
                source_type="jsonl_log",
                source_name=payload.source_name or import_path.name,
            )
        if source == "runtime_log":
            import_path = _validated_import_path(payload.path)
            return siem_indexer.import_jsonl(
                str(import_path),
                source_type="agent_runtime_log",
                source_name=payload.source_name or import_path.name,
            )
        if source == "redis":
            return await siem_indexer.import_redis_stream(
                redis_client,
                stream_name=payload.stream_name,
                count=payload.count,
            )
        if source == "events_table":
            return await _sync_primary_events_nonblocking(limit=max(1, min(payload.count, 10000)))
        raise HTTPException(status_code=400, detail="Unsupported source")
    except HTTPException:
        raise
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/logs/dump")
async def dump_logs():
    jsonl_path = "/app/logs/events.jsonl"
    if os.path.exists(jsonl_path):
        snapshot_stem = f"epidemic_events_snapshot_{int(time.time())}"
        snapshot_name = f"{snapshot_stem}.jsonl"
        snapshot_path = f"/tmp/{snapshot_name}"
        archive_path = f"/tmp/{snapshot_stem}.zip"
        shutil.copyfile(jsonl_path, snapshot_path)
        manifest = await _build_snapshot_manifest(snapshot_name)
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(snapshot_path, arcname=snapshot_name)
            archive.writestr(
                f"{snapshot_stem}_manifest.json",
                json.dumps(manifest, indent=2),
            )
        return FileResponse(
            archive_path,
            media_type="application/zip",
            filename=f"{snapshot_stem}.zip",
        )
    raise HTTPException(status_code=404, detail="No log file found")


@app.get("/status")
async def get_status():
    return {"status": "running", "epoch": await _get_current_epoch()}


@app.post("/inject/{agent_id}")
async def inject_worm(agent_id: str, payload: InjectPayload):
    from scenarios.worm_injection import get_attack_strength, get_worm_for_injection

    agent_id = _validated_agent_id(agent_id)
    worm = get_worm_for_injection(payload.worm_level, agent_id)
    injection_id = os.urandom(8).hex()
    try:
        epoch = await _get_current_epoch()
        reset_id = await _get_current_reset_id()
    except RedisError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Message bus (Redis) unavailable — start the stack: docker compose up -d. ({exc})",
        ) from exc
    attack_strength = get_attack_strength(payload.worm_level)
    metadata = {
        "level": payload.worm_level,
        "attack_type": worm["type"],
        "attack_strength": attack_strength,
        "hop_count": 0,
        "injection_id": injection_id,
        "attempt_id": injection_id,
        "source_plane": "control",
        "epoch": epoch,
        "reset_id": reset_id,
    }

    msg = {
        "id": injection_id,
        "src": "orchestrator",
        "dst": agent_id,
        "event_type": "infection_attempt",
        "payload": worm["content"],
        "metadata": metadata,
    }
    try:
        await redis_client.publish(_agent_channel_name(agent_id), json.dumps(msg))

        await redis_client.xadd(
            EVENT_STREAM_KEY,
            {
                "ts": str(time.time()),
                "src": "orchestrator",
                "dst": agent_id,
                "event": "WRM-INJECT",
                "attack_type": worm["type"],
                "payload": worm["content"],
                "metadata": json.dumps(metadata),
                "hop_count": "0",
                "injection_id": injection_id,
            },
        )
    except RedisError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Message bus (Redis) unavailable — start the stack: docker compose up -d. ({exc})",
        ) from exc

    return {
        "status": "injected",
        "agent": agent_id,
        "level": payload.worm_level,
        "injection_id": injection_id,
        "epoch": epoch,
        "reset_id": reset_id,
    }


@app.post("/quarantine/{agent_id}")
async def quarantine_agent(agent_id: str):
    agent_id = _validated_agent_id(agent_id)
    epoch = await _get_current_epoch()
    reset_id = await _get_current_reset_id()
    metadata = {
        "source_plane": "control",
        "action": "quarantine",
        "epoch": epoch,
        "reset_id": reset_id,
    }
    msg = {
        "id": os.urandom(8).hex(),
        "src": "orchestrator",
        "dst": agent_id,
        "event_type": "quarantine",
        "payload": "",
        "metadata": metadata,
    }
    await redis_client.publish(_agent_channel_name(agent_id), json.dumps(msg))

    await redis_client.xadd(
        EVENT_STREAM_KEY,
        {
            "ts": str(time.time()),
            "src": "orchestrator",
            "dst": agent_id,
            "event": "QUARANTINE_ISSUED",
            "state_after": "quarantined",
            "metadata": json.dumps(metadata),
        },
    )
    return {"status": "quarantined", "agent": agent_id, "epoch": epoch, "reset_id": reset_id}


@app.post("/reset")
async def reset_agents():
    new_epoch = await redis_client.incr(SIMULATION_EPOCH_KEY)
    reset_id = os.urandom(8).hex()
    await redis_client.set(CURRENT_RESET_ID_KEY, reset_id)
    metadata = {
        "source_plane": "control",
        "action": "reset",
        "epoch": new_epoch,
        "reset_id": reset_id,
    }
    msg = {
        "id": reset_id,
        "src": "orchestrator",
        "dst": "broadcast",
        "event_type": "reset",
        "payload": "",
        "metadata": metadata,
    }

    start_id = await _get_latest_stream_id()
    await redis_client.publish("broadcast", json.dumps(msg))
    await redis_client.xadd(
        EVENT_STREAM_KEY,
        {
            "ts": str(time.time()),
            "src": "orchestrator",
            "dst": "all",
            "event": "RESET_ISSUED",
            "metadata": json.dumps(metadata),
        },
    )

    acknowledged_agents, heartbeat_agents, barrier_complete, bleed_through = await _wait_for_reset_acks(
        start_id,
        reset_id,
        int(new_epoch),
        timeout_s=RESET_ACK_TIMEOUT_S,
    )

    if not barrier_complete:
        await redis_client.xadd(
            EVENT_STREAM_KEY,
            {
                "ts": str(time.time()),
                "src": "orchestrator",
                "dst": "all",
                "event": "RESET_TIMEOUT",
                "metadata": json.dumps(
                    {
                        "epoch": int(new_epoch),
                        "reset_id": reset_id,
                        "acknowledged_agents": acknowledged_agents,
                        "heartbeat_agents": heartbeat_agents,
                        "bleed_through_detected": bleed_through,
                        "timeout_s": RESET_ACK_TIMEOUT_S,
                    }
                ),
            },
        )

    c2_engine.reset()

    return {
        "status": "reset_issued",
        "epoch": int(new_epoch),
        "reset_id": reset_id,
        "acknowledged_agents": acknowledged_agents,
        "heartbeat_agents": heartbeat_agents,
        "barrier_complete": barrier_complete,
        "bleed_through_detected": bleed_through,
        "quiet_period_s": RESET_QUIET_PERIOD_S,
        "ack_timeout_s": RESET_ACK_TIMEOUT_S,
    }


@app.post("/vaccine")
async def apply_vaccine():
    epoch = await _get_current_epoch()
    reset_id = await _get_current_reset_id()
    vaccine_id = os.urandom(8).hex()
    metadata = {
        "source_plane": "control",
        "action": "vaccine",
        "duration_s": 120,
        "defense_boost": 0.4,
        "vaccine_id": vaccine_id,
        "epoch": epoch,
        "reset_id": reset_id,
    }
    msg = {
        "id": vaccine_id,
        "src": "orchestrator",
        "dst": "broadcast",
        "event_type": "vaccine",
        "payload": "",
        "metadata": metadata,
    }

    await redis_client.publish("broadcast", json.dumps(msg))
    await redis_client.xadd(
        EVENT_STREAM_KEY,
        {
            "ts": str(time.time()),
            "src": "orchestrator",
            "dst": "all",
            "event": "VACCINE_ISSUED",
            "state_after": "vaccinated",
            "metadata": json.dumps(metadata),
        },
    )
    return {
        "status": "vaccine_applied",
        "vaccine_id": vaccine_id,
        "duration_s": 120,
        "defense_boost": 0.4,
        "epoch": epoch,
        "reset_id": reset_id,
    }


@app.get("/api/world/spatial")
async def get_world_spatial():
    try:
        positions = await asyncio.get_event_loop().run_in_executor(
            None, world_db.list_agent_positions
        )
        contacts = WorldSpatialEngine.proximity_contacts(positions, radius=4)
        return {"positions": positions, "proximity_contacts": contacts}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/world/structures")
async def get_world_structures():
    try:
        structs = await asyncio.get_event_loop().run_in_executor(
            None, world_db.list_active_structures
        )
        return {"structures": structs}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/world/structures")
async def place_world_structure(body: dict):
    try:
        sid = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: WorldStructureEngine.place(world_db, body),
        )
        return {"structure_id": sid, "ok": True}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.delete("/api/world/structures/{structure_id}")
async def remove_world_structure(structure_id: str):
    try:
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: WorldStructureEngine.remove(world_db, structure_id)
        )
        return {"ok": True}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
