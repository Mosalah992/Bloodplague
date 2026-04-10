"""
Forensic identity and correlation for orchestrator-ingested events (Patch 1).

Normalizes Redis stream payloads and adds stable event_id, run_id, mirrored
event_type, correlation bundle, and SIEM-friendly metadata keys.
"""

from __future__ import annotations

import copy
import json
import logging
import uuid
from contextvars import ContextVar
from typing import Any, Dict, Optional

from kill_chain_constants import resolve_kill_chain_stage

_log = logging.getLogger("uvicorn.error")

FORENSIC_SCHEMA_VERSION = 1

# Set during consume_events to the current batch message's event_id so C2 re-emits can chain.
TRIGGER_EVENT_ID: ContextVar[Optional[str]] = ContextVar("TRIGGER_EVENT_ID", default=None)


def parse_stream_message(message_data: Dict[str, Any]) -> Dict[str, Any]:
    """Copy stream fields; parse metadata JSON; coerce ts where safe."""
    event = dict(message_data)
    meta_raw = event.get("metadata")
    if isinstance(meta_raw, str):
        stripped = meta_raw.strip()
        if not stripped:
            event["metadata"] = {}
        else:
            try:
                parsed = json.loads(meta_raw)
                event["metadata"] = parsed if isinstance(parsed, dict) else {"_parsed": parsed}
            except json.JSONDecodeError:
                _log.warning(
                    "forensic_metadata_parse_failed event=%s",
                    str(event.get("event", ""))[:80],
                )
                event["metadata"] = {}
    elif meta_raw is None:
        event["metadata"] = {}
    elif not isinstance(meta_raw, dict):
        event["metadata"] = {"_raw": meta_raw}

    corr_raw = event.get("correlation")
    if isinstance(corr_raw, str):
        cstrip = corr_raw.strip()
        if not cstrip:
            event.pop("correlation", None)
        else:
            try:
                cparsed = json.loads(corr_raw)
                event["correlation"] = cparsed if isinstance(cparsed, dict) else {}
            except json.JSONDecodeError:
                _log.warning("forensic_correlation_parse_failed event=%s", str(event.get("event", ""))[:80])
                event["correlation"] = {}

    ts = event.get("ts")
    if isinstance(ts, str):
        try:
            event["ts"] = float(ts)
        except (TypeError, ValueError):
            pass

    return event


def _coerce_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def merge_metadata_search_keys(event: Dict[str, Any]) -> None:
    """
    Mirror top-level / correlation forensic fields into metadata for SIEM json_extract.
    Does not overwrite existing metadata keys.
    """
    meta = event.get("metadata")
    if not isinstance(meta, dict):
        meta = {}
        event["metadata"] = meta

    corr = event.get("correlation")
    if isinstance(corr, dict):
        for key in ("parent_event_id", "run_id", "stream_message_id", "trace_id"):
            val = corr.get(key)
            if val is not None and str(val) != "" and key not in meta:
                meta[key] = val

    for key in (
        "run_id",
        "parent_event_id",
        "strain_id",
        "attack_id",
        "event_id",
        "campaign_id",
        "injection_id",
    ):
        val = event.get(key)
        if val is not None and str(val) != "" and key not in meta:
            meta[key] = val


def enrich_forensic_event(
    event: Dict[str, Any],
    *,
    run_id: str,
    stream_message_id: str,
) -> Dict[str, Any]:
    """
    Return a new dict with forensic fields. Preserves legacy `event` and adds `event_type`.
    """
    out = copy.deepcopy(event)
    meta = out.get("metadata")
    if not isinstance(meta, dict):
        meta = {}
        out["metadata"] = meta

    event_name = str(out.get("event", "") or "")
    out["event_type"] = event_name

    out["run_id"] = run_id
    out["event_id"] = f"{run_id}:{stream_message_id}"

    out["agent_id"] = str(out.get("agent_id") or out.get("src") or "").strip()

    attack_id = (
        str(meta.get("attempt_id") or meta.get("attack_id") or out.get("attempt_id") or "").strip()
    )
    if attack_id:
        out["attack_id"] = attack_id

    campaign_id = str(
        out.get("campaign_id") or meta.get("campaign_id") or ""
    ).strip()
    if campaign_id:
        out["campaign_id"] = campaign_id

    injection_id = str(
        out.get("injection_id") or meta.get("injection_id") or ""
    ).strip()
    if injection_id:
        out["injection_id"] = injection_id

    strain_id = str(meta.get("strain_id") or out.get("strain_id") or "").strip()
    if strain_id:
        out["strain_id"] = strain_id

    payload_hash = str(
        out.get("payload_hash") or meta.get("payload_hash") or ""
    ).strip()
    payload_text = str(out.get("payload") or "")
    if payload_hash:
        out["payload_hash"] = payload_hash
    elif payload_text and not out.get("payload_hash"):
        # Payload-bearing without hash yet: leave empty; agents usually set hash in metadata
        pass

    existing_kcs = str(out.get("kill_chain_stage") or meta.get("kill_chain_stage") or "").strip()
    if existing_kcs:
        out["kill_chain_stage"] = existing_kcs
    else:
        resolved = str(
            resolve_kill_chain_stage(
                event_name,
                src=str(out.get("src", "")),
                dst=str(out.get("dst", "")),
                metadata=meta,
            )
            or ""
        ).strip()
        if resolved:
            out["kill_chain_stage"] = resolved
            meta.setdefault("kill_chain_stage", resolved)

    parent_event_id = str(out.get("parent_event_id") or meta.get("parent_event_id") or "").strip()
    if parent_event_id:
        out["parent_event_id"] = parent_event_id

    trace_id = injection_id or ""
    if campaign_id and injection_id:
        trace_id = f"{campaign_id}:{injection_id}"
    elif campaign_id:
        trace_id = campaign_id

    correlation: Dict[str, Any] = {
        "schema_version": FORENSIC_SCHEMA_VERSION,
        "run_id": run_id,
        "stream_message_id": stream_message_id,
        "parent_event_id": parent_event_id,
        "trace_id": trace_id,
    }
    if campaign_id:
        correlation["campaign_id"] = campaign_id
    if injection_id:
        correlation["injection_id"] = injection_id

    existing_corr = out.get("correlation")
    if isinstance(existing_corr, dict):
        merged = {**correlation, **existing_corr}
        correlation = merged

    out["correlation"] = correlation

    merge_metadata_search_keys(out)

    mv = out.get("mutation_v")
    if mv is not None and not isinstance(mv, int):
        coerced = _coerce_int(mv)
        if coerced is not None:
            out["mutation_v"] = coerced

    return out


def apply_c2_stream_correlation(event_data: Dict[str, Any], *, run_id: str) -> Dict[str, Any]:
    """
    Before C2 xadd: attach parent_event_id from TRIGGER_EVENT_ID, run_id, correlation.
    Returns a shallow-heavy copy safe to mutate for stream mapping.
    """
    out = dict(event_data)

    meta_raw = out.get("metadata")
    if isinstance(meta_raw, str):
        try:
            meta = json.loads(meta_raw) if meta_raw.strip() else {}
        except json.JSONDecodeError:
            meta = {}
        out["metadata"] = meta if isinstance(meta, dict) else {}
    elif isinstance(meta_raw, dict):
        out["metadata"] = dict(meta_raw)
    else:
        out["metadata"] = {}

    if not str(out.get("run_id") or "").strip():
        out["run_id"] = run_id

    parent = TRIGGER_EVENT_ID.get()
    if parent and not str(out.get("parent_event_id") or "").strip():
        out["parent_event_id"] = parent

    corr: Dict[str, Any] = {
        "schema_version": FORENSIC_SCHEMA_VERSION,
        "run_id": run_id,
    }
    pe = str(out.get("parent_event_id") or "").strip()
    if pe:
        corr["parent_event_id"] = pe

    existing = out.get("correlation")
    if isinstance(existing, dict):
        corr = {**corr, **existing}
    out["correlation"] = corr

    merge_metadata_search_keys(out)
    return out


def new_local_event_id(run_id: str) -> str:
    """Collision-safe id when no Redis stream message id exists."""
    return f"{run_id}:local-{uuid.uuid4().hex}"
