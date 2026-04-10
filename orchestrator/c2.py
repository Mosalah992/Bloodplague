"""
C2 Observability + Post-Compromise Behavior Engine for Epidemic Lab.

Manages C2 sessions, beacon/task/exfil lifecycle, objective evaluation,
and kill chain tracking. Integrates with the event stream and SIEM.
"""

import json
import logging
import random
import sys
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from kill_chain_constants import (
    C2_EVENT_TYPES,
    EVENT_TO_KILL_CHAIN_STAGE,
    resolve_kill_chain_stage,
    BEACON_FILTER_EVENTS,
    EXFIL_FILTER_EVENTS,
)

_SHARED_DIR = Path(__file__).resolve().parents[1] / "agents" / "shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

from topology import deepest_agents, get_neighbors

from defense_friction import DefenseFrictionMemory, FrictionDecision
from c2_operational import (
    build_synthetic_exfil_body,
    chunk_interception_probability,
    classify_exfil_sensitivity,
    compute_chunk_plan,
    destination_trust_risk,
    exfil_size_after_constraints,
    redact_exfil_preview,
    sha256_bytes,
)
from experiment_config.c2_runtime import build_c2_runtime_config

logger = logging.getLogger("uvicorn.error")

_C2_CFG = build_c2_runtime_config()

BEACON_SERVER_URL = _C2_CFG.beacon_server_url
SPREAD_FAST_THRESHOLD = _C2_CFG.spread_fast_threshold
SUCCESS_RATE_THRESHOLD = _C2_CFG.success_rate_threshold
MUTATION_DIVERSITY_THRESHOLD = _C2_CFG.mutation_diversity_threshold
PERSISTENCE_BEACON_THRESHOLD = _C2_CFG.persistence_beacon_threshold
MULTI_BRANCH_THRESHOLD = _C2_CFG.multi_branch_threshold
MULTI_NODE_EXFIL_THRESHOLD = _C2_CFG.multi_node_exfil_threshold
CARRIER_PERSISTENCE_THRESHOLD_S = _C2_CFG.carrier_persistence_threshold_s
EVADE_QUARANTINE_THRESHOLD_S = _C2_CFG.evade_quarantine_threshold_s

# ════════════════════════════════════════════════════════════════════════════
# KILL CHAIN STAGE ORDER (for comparisons)
# ════════════════════════════════════════════════════════════════════════════

STAGE_ORDER = [
    "INITIAL_INJECTION", "PAYLOAD_GENERATION", "DELIVERY", "EXPLOITATION",
    "RELAY", "DEFENSE_INTERACTION", "COMPROMISE", "BEACON", "TASKING",
    "EXFILTRATION", "PERSISTENCE", "DETECTION",
]


def _stage_index(stage: str) -> int:
    try:
        return STAGE_ORDER.index(stage)
    except ValueError:
        return -1


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ════════════════════════════════════════════════════════════════════════════
# OBJECTIVE MODEL
# ════════════════════════════════════════════════════════════════════════════

def _objective_spread_fast(ctx: Dict[str, Any]) -> bool:
    return float(ctx.get("success_rate", 0.0) or 0.0) >= SPREAD_FAST_THRESHOLD


def _objective_reach_deepest_node(ctx: Dict[str, Any]) -> bool:
    compromised_agents = set(ctx.get("compromised_agents", set()) or set())
    return any(agent_id in compromised_agents for agent_id in deepest_agents())


def _objective_maximize_success_rate(ctx: Dict[str, Any]) -> bool:
    return float(ctx.get("success_rate", 0.0) or 0.0) >= SUCCESS_RATE_THRESHOLD


def _objective_maximize_mutation_diversity(ctx: Dict[str, Any]) -> bool:
    return int(ctx.get("mutation_diversity", 0) or 0) > MUTATION_DIVERSITY_THRESHOLD


def _objective_establish_c2(ctx: Dict[str, Any]) -> bool:
    return bool(ctx.get("c2_channel_established")) and bool(ctx.get("c2_task_delivered"))


def _objective_maintain_persistence(ctx: Dict[str, Any]) -> bool:
    return int(ctx.get("beacon_count", 0) or 0) >= PERSISTENCE_BEACON_THRESHOLD


def _objective_exfiltrate_data(ctx: Dict[str, Any]) -> bool:
    return int(ctx.get("exfil_success_count", 0) or 0) > 0


def _objective_stay_undetected(ctx: Dict[str, Any]) -> bool:
    return int(ctx.get("detection_count", 0) or 0) == 0 and int(ctx.get("beacon_count", 0) or 0) > 0


def _objective_multi_branch_spread(ctx: Dict[str, Any]) -> bool:
    return len(set(ctx.get("branch_ids", set()) or set())) >= MULTI_BRANCH_THRESHOLD


def _objective_carrier_persistence(ctx: Dict[str, Any]) -> bool:
    carriers = ctx.get("carrier_durations", {}) or {}
    return any(float(duration or 0.0) >= CARRIER_PERSISTENCE_THRESHOLD_S for duration in carriers.values())


def _objective_evade_quarantine(ctx: Dict[str, Any]) -> bool:
    quarantine_free = ctx.get("quarantine_free_durations", {}) or {}
    return any(float(duration or 0.0) >= EVADE_QUARANTINE_THRESHOLD_S for duration in quarantine_free.values())


def _objective_exfiltrate_multi_node(ctx: Dict[str, Any]) -> bool:
    return len(set(ctx.get("exfil_agents", set()) or set())) >= MULTI_NODE_EXFIL_THRESHOLD


OBJECTIVE_COMPLETION_CRITERIA = {
    "SPREAD_FAST": _objective_spread_fast,
    "REACH_DEEPEST_NODE": _objective_reach_deepest_node,
    "MAXIMIZE_SUCCESS_RATE": _objective_maximize_success_rate,
    "MAXIMIZE_MUTATION_DIVERSITY": _objective_maximize_mutation_diversity,
    "ESTABLISH_C2": _objective_establish_c2,
    "MAINTAIN_PERSISTENCE": _objective_maintain_persistence,
    "EXFILTRATE_DATA": _objective_exfiltrate_data,
    "STAY_UNDETECTED": _objective_stay_undetected,
    "MULTI_BRANCH_SPREAD": _objective_multi_branch_spread,
    "CARRIER_PERSISTENCE": _objective_carrier_persistence,
    "EVADE_QUARANTINE": _objective_evade_quarantine,
    "EXFILTRATE_MULTI_NODE": _objective_exfiltrate_multi_node,
}


@dataclass
class ObjectiveState:
    name: str
    status: str = "pending"  # pending | partial | completed | failed
    evidence: List[str] = field(default_factory=list)
    failure_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "evidence": self.evidence[:10],
            "failure_reason": self.failure_reason,
        }


# Lifecycle defaults for C2Session (must be defined before the dataclass body is evaluated)
PAYLOAD_HISTORY_MAX = 20
EXFIL_RECENT_BLOCK_COOLDOWN_S = 30.0
LC_INITIAL = "INITIAL_COMPROMISE"
LC_STAGING = "STAGING"
LC_BEACONING = "BEACONING"
LC_EXFILTRATION = "EXFILTRATION"
LC_POST_EXFIL = "POST_EXFIL"
LC_TERMINATED = "TERMINATED"


# ════════════════════════════════════════════════════════════════════════════
# C2 SESSION
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class C2Session:
    c2_session_id: str
    agent_id: str
    campaign_id: str
    injection_id: str
    first_seen: float
    last_seen: float
    beacon_count: int = 0
    task_count: int = 0
    exfil_count: int = 0
    session_status: str = "active"
    highest_kill_chain_stage: str = "COMPROMISE"
    payload_hash_origin: str = ""
    parent_payload_hash: str = ""
    lineage_src: str = ""
    lineage_dst: str = ""
    entry_stage: str = "COMPROMISE"
    topology_hop: int = 0
    beacons: List[Dict[str, Any]] = field(default_factory=list)
    tasks: List[Dict[str, Any]] = field(default_factory=list)
    exfils: List[Dict[str, Any]] = field(default_factory=list)
    lifecycle_state: str = LC_INITIAL
    internal_action_count: int = 0
    last_blocked_at: float = 0.0
    payload_history: List[Dict[str, Any]] = field(default_factory=list)
    last_payload: str = ""
    payload_source: str = "UNKNOWN"
    beacon_fail_streak: int = 0
    last_exfil_ts: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "c2_session_id": self.c2_session_id,
            "agent_id": self.agent_id,
            "campaign_id": self.campaign_id,
            "injection_id": self.injection_id,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "beacon_count": self.beacon_count,
            "task_count": self.task_count,
            "exfil_count": self.exfil_count,
            "session_status": self.session_status,
            "highest_kill_chain_stage": self.highest_kill_chain_stage,
            "payload_hash_origin": self.payload_hash_origin,
            "parent_payload_hash": self.parent_payload_hash,
            "lineage_src": self.lineage_src,
            "lineage_dst": self.lineage_dst,
            "entry_stage": self.entry_stage,
            "topology_hop": self.topology_hop,
            "lifecycle_state": self.lifecycle_state,
            "internal_action_count": self.internal_action_count,
            "last_blocked_at": self.last_blocked_at,
            "payload_source": self.payload_source,
            "last_payload_preview": (self.last_payload[:200] + "…") if len(self.last_payload) > 200 else self.last_payload,
            "beacon_fail_streak": self.beacon_fail_streak,
            "last_exfil_ts": self.last_exfil_ts,
        }


# ════════════════════════════════════════════════════════════════════════════
# C2 ENGINE
# ════════════════════════════════════════════════════════════════════════════

# Beacon behavior tuning (resolved from experiment_config.c2_runtime)
BEACON_BASE_INTERVAL_S = _C2_CFG.beacon_base_interval_s
BEACON_JITTER_RATIO = _C2_CFG.beacon_jitter_ratio
BEACON_BLOCK_PROBABILITY = _C2_CFG.beacon_block_probability
EXFIL_BLOCK_PROBABILITY = _C2_CFG.exfil_block_probability
TASK_BLOCK_PROBABILITY = _C2_CFG.task_block_probability
C2_BEACON_OP_SUCCESS_P = _C2_CFG.beacon_op_success_p
C2_BEACON_WARMUP_S = _C2_CFG.beacon_warmup_s
C2_BEACON_RETRY_SUCCESS_MULT = _C2_CFG.beacon_retry_success_mult
C2_BEACON_INTERVAL_MIN_MULT = _C2_CFG.beacon_interval_min_mult
C2_BEACON_INTERVAL_MAX_MULT = _C2_CFG.beacon_interval_max_mult
C2_BEACON_FAIL_BACKOFF_MULT = _C2_CFG.beacon_fail_backoff_mult
C2_TASK_REFUSE_P = _C2_CFG.task_refuse_p
C2_TASK_TIMEOUT_P = _C2_CFG.task_timeout_p
C2_TASK_CORRUPT_P = _C2_CFG.task_corrupt_p
C2_EXFIL_MIN_THROTTLE_S = _C2_CFG.exfil_min_throttle_s
C2_EXFIL_PREVIEW_MAX = _C2_CFG.exfil_preview_max
C2_EXFIL_LEGACY_EMIT = _C2_CFG.exfil_legacy_emit
POST_COMPROMISE_TASKS = ["collect_state", "relay_deeper", "alter_defense", "map_network"]
EXFIL_DATA_TYPES = ["agent_state", "defense_config", "payload_lineage", "network_map"]
OBJECTIVE_FAILURE_THRESHOLD = _C2_CFG.objective_failure_threshold

# Post-compromise containment budget
SESSION_TTL_S = _C2_CFG.session_ttl_s
MAX_BEACONS_PER_SESSION = _C2_CFG.max_beacons_per_session
SESSION_HISTORY_MAX_ITEMS = _C2_CFG.session_history_max_items
TERMINAL_SESSION_RETENTION_S = _C2_CFG.terminal_session_retention_s
MAX_SESSION_RECORDS = _C2_CFG.max_session_records


class C2Engine:
    """
    Post-compromise C2 behavior engine.

    After INFECTION_SUCCESSFUL, this engine manages:
    - Beacon establishment (C2_BEACON → C2_CHANNEL_ESTABLISHED)
    - Tasking (C2_TASK)
    - Exfiltration (C2_EXFIL → C2_DATABASE_WRITE)
    - Kill chain transitions
    - Objective evaluation
    """

    def __init__(self, emit_event: Callable):
        self._emit = emit_event  # async callable: emit_event(event_data)
        self.sessions: Dict[str, C2Session] = {}
        self._agent_sessions: Dict[str, str] = {}  # agent_id → session_id
        self._compromised_agents: Dict[str, Dict[str, Any]] = {}  # agent_id → compromise metadata
        self._campaign_objectives: Dict[str, ObjectiveState] = {}
        self._campaign_context: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "compromised_agents": set(),
            "success_rate": 0.0,
            "success_attempts": 0,
            "total_attempts": 0,
            "c2_sessions_active": 0,
            "c2_channel_established": False,
            "c2_task_delivered": False,
            "beacon_count": 0,
            "beacon_attempts": 0,
            "task_attempts": 0,
            "exfil_attempts": 0,
            "exfil_success_count": 0,
            "detection_count": 0,
            "mutation_diversity": 0,
            "blocked_beacons": 0,
            "blocked_tasks": 0,
            "blocked_exfils": 0,
            "branch_ids": set(),
            "branch_members": defaultdict(set),
            "exfil_agents": set(),
            "carrier_durations": {},
            "quarantine_free_durations": {},
        })
        self._pending_beacons: Dict[str, float] = {}  # agent_id → next_beacon_ts
        self._rng = random.Random(_C2_CFG.seed)
        self._enabled = _C2_CFG.enabled
        self._friction = DefenseFrictionMemory()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def reset(self) -> None:
        self.sessions.clear()
        self._agent_sessions.clear()
        self._compromised_agents.clear()
        self._campaign_objectives.clear()
        self._campaign_context.clear()
        self._pending_beacons.clear()
        self._friction.reset()

    def _record_block(self, agent_id: str, session: Optional["C2Session"]) -> None:
        now = time.time()
        info = self._compromised_agents.get(agent_id)
        if info is not None:
            info["last_blocked_at"] = now
        if session is not None:
            session.last_blocked_at = now

    def _c2_friction_metadata(self, agent_id: str, info: Dict[str, Any], session: Optional["C2Session"] = None) -> Dict[str, Any]:
        meta = dict(info)
        meta["compromised_agent"] = agent_id
        meta["src"] = str(meta.get("src", "") or agent_id)
        if session is not None:
            meta["topology_hop"] = session.topology_hop
            meta["c2_session_id"] = session.c2_session_id
        return meta

    async def _emit_defense_friction_c2(
        self,
        *,
        fd: FrictionDecision,
        agent_id: str,
        campaign_id: str,
        injection_id: str,
        payload_hash: str,
        friction_stage: str,
        kill_chain_stage: str,
        previous_kill_chain_stage: str,
        lineage: Dict[str, Any],
    ) -> None:
        cm = fd.cause_metadata()
        await self._emit_c2_event("DEFENSE_FRICTION", {
            "src": "c2_engine",
            "dst": agent_id,
            "campaign_id": campaign_id,
            "injection_id": injection_id,
            "payload_hash": payload_hash,
            "parent_payload_hash": str(lineage.get("parent_payload_hash", "") or ""),
            "compromised_agent": agent_id,
            "kill_chain_stage": kill_chain_stage,
            "previous_kill_chain_stage": previous_kill_chain_stage,
            "topology_hop": lineage.get("topology_hop", 0),
            "branch_id": lineage.get("branch_id", ""),
            "friction_stage": friction_stage,
            "friction_effective_block_p": fd.effective_block_p,
            **cm,
        })

    def _compute_next_beacon_deadline(self, agent_id: str, *, failure: bool, first_scheduling: bool = False) -> float:
        if first_scheduling:
            jitter = self._rng.uniform(-BEACON_JITTER_RATIO, BEACON_JITTER_RATIO) * BEACON_BASE_INTERVAL_S
            return time.time() + max(2.0, BEACON_BASE_INTERVAL_S * 0.1 + jitter)
        sid = self._agent_sessions.get(agent_id)
        session = self.sessions.get(sid) if sid else None
        streak = int(session.beacon_fail_streak) if session else 0
        base = BEACON_BASE_INTERVAL_S * self._rng.uniform(C2_BEACON_INTERVAL_MIN_MULT, C2_BEACON_INTERVAL_MAX_MULT)
        if failure:
            base *= C2_BEACON_FAIL_BACKOFF_MULT ** min(streak, 8)
        jitter = self._rng.uniform(-BEACON_JITTER_RATIO, BEACON_JITTER_RATIO) * base
        return time.time() + max(2.0, base + jitter)

    def _beacon_operational_success(self, session: Optional[C2Session], compromise_info: Dict[str, Any]) -> bool:
        p = C2_BEACON_OP_SUCCESS_P
        now = time.time()
        age = now - float(compromise_info.get("compromised_at", now) or now)
        if age < C2_BEACON_WARMUP_S:
            p *= 0.88
        if session is not None and session.beacon_fail_streak > 0:
            p *= C2_BEACON_RETRY_SUCCESS_MULT ** min(4, session.beacon_fail_streak)
        hop = self._to_int((session.topology_hop if session else 0) or compromise_info.get("topology_hop", 0), 0)
        if hop >= _C2_CFG.beacon_hop_stress_min:
            p *= _C2_CFG.beacon_hop_stress_mult
        p = max(0.03, min(0.97, p))
        return self._rng.random() < p

    def _append_payload_history(
        self, session: C2Session, event_type: str, preview: str, source: str,
    ) -> None:
        session.payload_history.append({
            "ts": time.time(),
            "event_type": event_type,
            "payload_preview": (preview or "")[:500],
            "source": source,
        })
        if len(session.payload_history) > PAYLOAD_HISTORY_MAX:
            session.payload_history = session.payload_history[-PAYLOAD_HISTORY_MAX:]

    async def _emit_lifecycle_transition(self, session: C2Session, to_state: str, reason: str) -> None:
        if session.lifecycle_state == to_state:
            return
        old = session.lifecycle_state
        session.lifecycle_state = to_state
        await self._emit_c2_event("C2_LIFECYCLE_TRANSITION", {
            "c2_session_id": session.c2_session_id,
            "compromised_agent": session.agent_id,
            "src": session.agent_id,
            "dst": "c2_engine",
            "campaign_id": session.campaign_id,
            "injection_id": session.injection_id,
            "payload_hash": session.payload_hash_origin,
            "parent_payload_hash": session.parent_payload_hash,
            "from_state": old,
            "to_state": to_state,
            "lifecycle_state": to_state,
            "topology_hop": session.topology_hop,
            "branch_id": str(self._compromise_lineage(session.agent_id).get("branch_id", "") or ""),
            "reason": reason,
            "beacon_count": session.beacon_count,
            "internal_action_count": session.internal_action_count,
        })

    async def _finalize_lifecycle_terminated(self, session: C2Session, reason: str) -> None:
        if session.lifecycle_state == LC_TERMINATED:
            return
        await self._emit_lifecycle_transition(session, LC_TERMINATED, reason)

    def get_agent_c2_snapshot(self, agent_id: str) -> Dict[str, Any]:
        """Live C2 session fields for dashboard (active session only)."""
        session_id = self._agent_sessions.get(agent_id)
        if not session_id:
            return {}
        session = self.sessions.get(session_id)
        if session is None or session.session_status != "active":
            return {}
        cap = MAX_BEACONS_PER_SESSION
        denom = str(cap) if cap > 0 else "∞"
        sid = session.c2_session_id
        short = sid.split("_")[-1][:8] if sid else ""
        return {
            "c2_session_id": session.c2_session_id,
            "c2_session_id_short": short,
            "c2_lifecycle_state": session.lifecycle_state,
            "c2_beacon_count": session.beacon_count,
            "c2_beacon_cap_display": denom,
            "c2_internal_action_count": session.internal_action_count,
        }

    @staticmethod
    def _metadata_dict(event: Dict[str, Any]) -> Dict[str, Any]:
        metadata = event.get("metadata", {})
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}
        return metadata if isinstance(metadata, dict) else {}

    @staticmethod
    def _to_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _refresh_success_rate(ctx: Dict[str, Any]) -> None:
        attempts = max(0, int(ctx.get("total_attempts", 0) or 0))
        successes = max(0, int(ctx.get("success_attempts", 0) or 0))
        ctx["success_rate"] = round((successes / attempts), 4) if attempts else 0.0

    @staticmethod
    def _objective_name(metadata: Dict[str, Any]) -> str:
        objective_name = str(metadata.get("objective", "") or "ESTABLISH_C2").strip().upper()
        return objective_name if objective_name in OBJECTIVE_COMPLETION_CRITERIA else "ESTABLISH_C2"

    @staticmethod
    def _branch_id_for(src: str, dst: str, metadata: Dict[str, Any]) -> str:
        explicit = str(metadata.get("branch_id", "") or "").strip()
        if explicit:
            return explicit
        source = str(src or "").strip()
        destination = str(dst or metadata.get("compromised_agent") or "").strip()
        if source and source != "orchestrator":
            return source
        return destination

    @staticmethod
    def _lineage_fields(event: Dict[str, Any], metadata: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "campaign_id": str(metadata.get("campaign_id", "") or ""),
            "injection_id": str(metadata.get("injection_id", "") or ""),
            "payload_hash": str(metadata.get("payload_hash", "") or ""),
            "parent_payload_hash": str(metadata.get("parent_payload_hash", "") or ""),
            "src": str(event.get("src", "") or metadata.get("src", "") or ""),
            "dst": str(event.get("dst", "") or metadata.get("dst", "") or metadata.get("compromised_agent", "") or ""),
            "topology_hop": C2Engine._to_int(metadata.get("topology_hop", metadata.get("hop_count", 0)), 0),
        }

    def _initialize_campaign_objective(self, campaign_id: str, metadata: Dict[str, Any]) -> None:
        if not campaign_id or campaign_id in self._campaign_objectives:
            return
        self._campaign_objectives[campaign_id] = ObjectiveState(name=self._objective_name(metadata))

    def _compromise_lineage(self, agent_id: str) -> Dict[str, Any]:
        info = self._compromised_agents.get(agent_id, {})
        return {
            "parent_payload_hash": str(info.get("parent_payload_hash", "") or ""),
            "lineage_src": str(info.get("src", "") or ""),
            "lineage_dst": str(info.get("dst", agent_id) or agent_id),
            "entry_stage": str(info.get("entry_stage", "COMPROMISE") or "COMPROMISE"),
            "topology_hop": self._to_int(info.get("topology_hop", 0), 0),
            "branch_id": str(info.get("branch_id", "") or ""),
        }

    def _session_lineage(self, session: C2Session) -> Dict[str, Any]:
        return {
            "parent_payload_hash": str(session.parent_payload_hash or ""),
            "lineage_src": str(session.lineage_src or ""),
            "lineage_dst": str(session.lineage_dst or session.agent_id),
            "entry_stage": str(session.entry_stage or "COMPROMISE"),
            "topology_hop": self._to_int(session.topology_hop, 0),
            "branch_id": str(self._compromise_lineage(session.agent_id).get("branch_id", "") or ""),
        }

    async def observe_event(self, event: Dict[str, Any]) -> None:
        event_name = str(event.get("event", "") or "").upper()
        metadata = self._metadata_dict(event)
        self._friction.observe(
            event_name,
            metadata,
            str(event.get("src", "") or ""),
            str(event.get("dst", "") or ""),
        )
        if not self._enabled:
            return
        if event_name == "INFECTION_SUCCESSFUL":
            await self.on_infection_successful(event)
            return

        campaign_id = str(metadata.get("campaign_id", "") or "")
        if not campaign_id:
            return

        self._initialize_campaign_objective(campaign_id, metadata)
        ctx = self._campaign_context[campaign_id]

        if event_name == "INFECTION_ATTEMPT":
            ctx["total_attempts"] += 1
            self._refresh_success_rate(ctx)
        elif event_name == "INFECTION_BLOCKED":
            ctx["detection_count"] += 1
        elif event_name in {"BEACON_BLOCKED", "TASK_BLOCKED", "EXFIL_BLOCKED", "QUARANTINE_ENFORCED", "QUARANTINE_ISSUED"}:
            ctx["detection_count"] += 1

        mutation_type = str(metadata.get("mutation_type", "") or "").strip()
        if mutation_type:
            mutation_families = ctx.setdefault("mutation_families", set())
            mutation_families.add(mutation_type)
            ctx["mutation_diversity"] = len(mutation_families)

        agent_id = str(
            metadata.get("compromised_agent", "")
            or metadata.get("agent_id", "")
            or event.get("dst", "")
            or event.get("src", "")
            or ""
        )
        if event_name == "EPIDEMIC_STATE_TRANSITION":
            to_state = str(metadata.get("to_state", "") or event.get("state_after", "") or "").strip()
            duration_s = self._to_float(metadata.get("state_duration_s", metadata.get("duration_s", 0.0)), 0.0)
            if to_state == "P" and agent_id:
                ctx["carrier_durations"][agent_id] = max(
                    duration_s,
                    self._to_float(ctx["carrier_durations"].get(agent_id, 0.0), 0.0),
                )
            if agent_id and str(metadata.get("from_state", "") or "") in {"I_r", "I_c", "I_x"}:
                ctx["quarantine_free_durations"][agent_id] = max(
                    duration_s,
                    self._to_float(ctx["quarantine_free_durations"].get(agent_id, 0.0), 0.0),
                )
        elif event_name == "C2_EXFIL" and agent_id:
            ctx["exfil_agents"].add(agent_id)

        for objective_name in OBJECTIVE_COMPLETION_CRITERIA:
            await self._evaluate_objective(campaign_id, objective_name)

    def _trim_session_history(self, items: List[Dict[str, Any]]) -> None:
        if len(items) > SESSION_HISTORY_MAX_ITEMS:
            del items[:-SESSION_HISTORY_MAX_ITEMS]

    def _prune_terminal_sessions(self) -> None:
        now = time.time()
        expired_terminal_ids = [
            session_id
            for session_id, session in self.sessions.items()
            if session.session_status != "active"
            and TERMINAL_SESSION_RETENTION_S > 0
            and (now - session.last_seen) > TERMINAL_SESSION_RETENTION_S
        ]
        for session_id in expired_terminal_ids:
            self.sessions.pop(session_id, None)

        if len(self.sessions) <= MAX_SESSION_RECORDS:
            return

        overflow = len(self.sessions) - MAX_SESSION_RECORDS
        terminal_sessions = sorted(
            (
                (session_id, session)
                for session_id, session in self.sessions.items()
                if session.session_status != "active"
            ),
            key=lambda item: item[1].last_seen,
        )
        for session_id, _session in terminal_sessions[:overflow]:
            self.sessions.pop(session_id, None)

    def _maybe_cleanup_campaign(self, campaign_id: str) -> None:
        if not campaign_id:
            return
        has_active_compromise = any(
            str(info.get("campaign_id", "")) == campaign_id
            for info in self._compromised_agents.values()
        )
        has_active_session = any(
            session.campaign_id == campaign_id and session.session_status == "active"
            for session in self.sessions.values()
        )
        if has_active_compromise or has_active_session:
            return
        self._campaign_context.pop(campaign_id, None)
        self._campaign_objectives.pop(campaign_id, None)

    def _close_agent_campaign_state(self, agent_id: str) -> Tuple[Optional[C2Session], str]:
        compromise_info = self._compromised_agents.pop(agent_id, {})
        self._pending_beacons.pop(agent_id, None)
        session_id = self._agent_sessions.pop(agent_id, None)
        session = self.sessions.get(session_id) if session_id else None
        campaign_id = str(
            (session.campaign_id if session else "")
            or compromise_info.get("campaign_id", "")
            or ""
        )
        if session is not None:
            session.last_seen = time.time()
        if campaign_id:
            ctx = self._campaign_context.get(campaign_id)
            if ctx:
                ctx["compromised_agents"].discard(agent_id)
                if session is not None and session.beacon_count > 0:
                    ctx["c2_sessions_active"] = max(0, int(ctx.get("c2_sessions_active", 0)) - 1)
                if not ctx["compromised_agents"] and ctx.get("c2_sessions_active", 0) <= 0:
                    ctx["c2_channel_established"] = False
        return session, campaign_id

    # ──────────────────────────────────────────────────────────────
    # COMPROMISE HANDLER
    # ──────────────────────────────────────────────────────────────

    async def on_infection_successful(self, event: Dict[str, Any]) -> None:
        if not self._enabled:
            return
        metadata = self._metadata_dict(event)
        lineage = self._lineage_fields(event, metadata)
        agent_id = str(lineage["dst"] or "")
        campaign_id = str(lineage["campaign_id"] or "")
        injection_id = str(lineage["injection_id"] or "")
        payload_hash = str(lineage["payload_hash"] or "")
        parent_payload_hash = str(lineage["parent_payload_hash"] or "")
        source_agent = str(lineage["src"] or "")
        topology_hop = self._to_int(lineage["topology_hop"], 0)
        entry_stage = resolve_kill_chain_stage(
            "INFECTION_SUCCESSFUL",
            src=source_agent,
            dst=agent_id,
            metadata=metadata,
        ) or "COMPROMISE"

        if not agent_id:
            return

        mut_type = str(metadata.get("mutation_type", "") or "").lower()
        if "llm" in mut_type:
            payload_source = "LLM"
        elif "template" in mut_type or "fallback" in mut_type:
            payload_source = "TEMPLATE"
        else:
            payload_source = "UNKNOWN"
        last_payload = str(metadata.get("payload_preview") or event.get("payload") or "")[:2000]

        self._compromised_agents[agent_id] = {
            "campaign_id": campaign_id,
            "injection_id": injection_id,
            "payload_hash": payload_hash,
            "parent_payload_hash": parent_payload_hash,
            "compromised_at": time.time(),
            "src": source_agent,
            "dst": agent_id,
            "entry_stage": entry_stage,
            "topology_hop": topology_hop,
            "branch_id": self._branch_id_for(source_agent, agent_id, metadata),
            "last_payload": last_payload,
            "payload_source": payload_source,
            "last_blocked_at": 0.0,
            "strain_id": str(metadata.get("strain_id") or ""),
            "attack_type": str(metadata.get("attack_type") or ""),
            "strategy_family": str(metadata.get("strategy_family") or ""),
            "knowledge_attack_type": str(metadata.get("knowledge_attack_type") or ""),
        }

        ctx = self._campaign_context[campaign_id]
        ctx["compromised_agents"].add(agent_id)
        ctx["success_attempts"] += 1
        ctx["total_attempts"] = max(
            int(ctx.get("total_attempts", 0) or 0),
            int(ctx.get("success_attempts", 0) or 0),
        )
        self._refresh_success_rate(ctx)
        branch_id = self._branch_id_for(source_agent, agent_id, metadata)
        if branch_id:
            ctx["branch_ids"].add(branch_id)
            ctx["branch_members"][branch_id].add(agent_id)
        ctx["quarantine_free_durations"][agent_id] = 0.0

        mutation_type = str(metadata.get("mutation_type", "") or "").strip()
        if mutation_type:
            mutation_families = ctx.setdefault("mutation_families", set())
            mutation_families.add(mutation_type)
            ctx["mutation_diversity"] = len(mutation_families)

        # Initialize campaign objective from event metadata if not yet set
        self._initialize_campaign_objective(campaign_id, metadata)

        # Schedule first beacon (variable initial delay)
        self._pending_beacons[agent_id] = self._compute_next_beacon_deadline(agent_id, failure=False, first_scheduling=True)

        for objective_name in OBJECTIVE_COMPLETION_CRITERIA:
            await self._evaluate_objective(campaign_id, objective_name)

        logger.info("c2_compromise_registered agent=%s campaign=%s", agent_id, campaign_id)

    # ──────────────────────────────────────────────────────────────
    # BEACON TICK — call periodically from the event loop
    # ──────────────────────────────────────────────────────────────

    async def tick(self) -> None:
        if not self._enabled:
            return
        await self._expire_sessions()
        now = time.time()
        ready_agents = [
            agent_id for agent_id, next_ts in list(self._pending_beacons.items())
            if now >= next_ts
        ]
        for agent_id in ready_agents:
            await self._execute_beacon(agent_id)

    async def _expire_sessions(self) -> None:
        """Terminate C2 sessions that have exceeded SESSION_TTL_S wall-clock age."""
        if SESSION_TTL_S <= 0:
            return
        now = time.time()
        expired = [
            agent_id for agent_id, info in list(self._compromised_agents.items())
            if now - info.get("compromised_at", now) > SESSION_TTL_S
        ]
        for agent_id in expired:
            compromise_info = self._compromised_agents.get(agent_id, {})
            session, campaign_id = self._close_agent_campaign_state(agent_id)
            if session is not None:
                await self._finalize_lifecycle_terminated(session, "session_ttl_exceeded")
                session.session_status = "expired"
            injection_id = compromise_info.get("injection_id", "")
            payload_hash = compromise_info.get("payload_hash", "")
            parent_payload_hash = compromise_info.get("parent_payload_hash", "")
            logger.info("c2_session_expired agent=%s campaign=%s ttl=%.0fs", agent_id, campaign_id, SESSION_TTL_S)
            await self._emit_c2_event("C2_SESSION_EXPIRED", {
                "compromised_agent": agent_id,
                "src": agent_id,
                "dst": "c2_server",
                "campaign_id": campaign_id,
                "injection_id": injection_id,
                "payload_hash": payload_hash,
                "parent_payload_hash": parent_payload_hash,
                "session_ttl_s": SESSION_TTL_S,
                "topology_hop": self._to_int(compromise_info.get("topology_hop", 0), 0),
                "branch_id": str(compromise_info.get("branch_id", "") or ""),
                "kill_chain_stage": "DETECTION",
                "reason": "session_ttl_exceeded",
            })
            self._maybe_cleanup_campaign(str(campaign_id))
            self._prune_terminal_sessions()

    async def _execute_beacon(self, agent_id: str) -> None:
        compromise_info = self._compromised_agents.get(agent_id)
        if not compromise_info:
            self._pending_beacons.pop(agent_id, None)
            return
        if SESSION_TTL_S > 0 and (time.time() - float(compromise_info.get("compromised_at", time.time()))) > SESSION_TTL_S:
            await self._expire_sessions()
            return

        campaign_id = compromise_info["campaign_id"]
        injection_id = compromise_info["injection_id"]
        payload_hash = compromise_info["payload_hash"]
        lineage = self._compromise_lineage(agent_id)
        previous_stage = str(lineage["entry_stage"] or "COMPROMISE")
        ctx = self._campaign_context[campaign_id]

        # Enforce per-session beacon cap
        session_check = self._get_or_create_session(agent_id, campaign_id, injection_id, payload_hash)
        if MAX_BEACONS_PER_SESSION > 0 and session_check.beacon_count >= MAX_BEACONS_PER_SESSION:
            session_check, closed_campaign_id = self._close_agent_campaign_state(agent_id)
            if session_check is None:
                return
            await self._finalize_lifecycle_terminated(session_check, "beacon_cap_exceeded")
            session_check.session_status = "burned"
            logger.info("c2_session_burned agent=%s beacons=%d cap=%d", agent_id, session_check.beacon_count, MAX_BEACONS_PER_SESSION)
            await self._emit_c2_event("C2_SESSION_BURNED", {
                "compromised_agent": agent_id,
                "src": agent_id,
                "dst": "c2_server",
                "campaign_id": campaign_id,
                "injection_id": injection_id,
                "payload_hash": payload_hash,
                "parent_payload_hash": lineage["parent_payload_hash"],
                "beacon_count": session_check.beacon_count,
                "beacon_cap": MAX_BEACONS_PER_SESSION,
                "topology_hop": lineage["topology_hop"],
                "branch_id": lineage["branch_id"],
                "kill_chain_stage": "DETECTION",
                "reason": "beacon_cap_exceeded",
            })
            self._maybe_cleanup_campaign(closed_campaign_id or campaign_id)
            self._prune_terminal_sessions()
            return

        session_pre = self._get_or_create_session(agent_id, campaign_id, injection_id, payload_hash)
        friction_stage = "PRE_BEACON" if session_pre.beacon_count == 0 else "BEACON"
        fd = self._friction.decide_c2(
            stage=friction_stage,
            metadata=self._c2_friction_metadata(agent_id, compromise_info, session_pre),
            rng=self._rng,
            base_block_p=BEACON_BLOCK_PROBABILITY,
            agent_id=agent_id,
        )
        await self._emit_defense_friction_c2(
            fd=fd,
            agent_id=agent_id,
            campaign_id=campaign_id,
            injection_id=injection_id,
            payload_hash=payload_hash,
            friction_stage=friction_stage,
            kill_chain_stage="BEACON",
            previous_kill_chain_stage=previous_stage,
            lineage=lineage,
        )
        beacon_id = _gen_id("bcn")
        ctx["beacon_attempts"] += 1
        if fd.should_defer:
            self._pending_beacons[agent_id] = self._compute_next_beacon_deadline(agent_id, failure=False)
            return
        blocked = fd.should_block
        if blocked:
            self._record_block(agent_id, None)
            bb_meta = {
                "beacon_id": beacon_id,
                "compromised_agent": agent_id,
                "src": agent_id,
                "dst": "c2_server",
                "campaign_id": campaign_id,
                "injection_id": injection_id,
                "payload_hash": payload_hash,
                "parent_payload_hash": lineage["parent_payload_hash"],
                "beacon_success": False,
                "blocked_by": "defense_friction_decoy" if fd.outcome == "DEFENSE_DECOY" else "defense_friction",
                "kill_chain_stage": "BEACON",
                "previous_kill_chain_stage": previous_stage,
                "topology_hop": lineage["topology_hop"],
                "branch_id": lineage["branch_id"],
                "detection_reason": "defense_friction",
                **fd.cause_metadata(),
            }
            await self._emit_c2_event("BEACON_BLOCKED", bb_meta)
            ctx["blocked_beacons"] += 1
            self._pending_beacons[agent_id] = self._compute_next_beacon_deadline(agent_id, failure=True)
            return

        if not self._beacon_operational_success(session_pre, compromise_info):
            session_pre.beacon_fail_streak += 1
            await self._emit_c2_event("C2_BEACON_FAILED", {
                "beacon_id": beacon_id,
                "compromised_agent": agent_id,
                "src": agent_id,
                "dst": "c2_server",
                "campaign_id": campaign_id,
                "injection_id": injection_id,
                "payload_hash": payload_hash,
                "parent_payload_hash": lineage["parent_payload_hash"],
                "beacon_success": False,
                "failure_reason": "transport_or_timing",
                "beacon_fail_streak": session_pre.beacon_fail_streak,
                "kill_chain_stage": "BEACON",
                "previous_kill_chain_stage": previous_stage,
                "topology_hop": lineage["topology_hop"],
                "branch_id": lineage["branch_id"],
            })
            self._pending_beacons[agent_id] = self._compute_next_beacon_deadline(agent_id, failure=True)
            return

        session_pre.beacon_fail_streak = 0

        # Successful beacon
        session = session_pre
        session.beacon_count += 1
        session.last_seen = time.time()
        ctx["beacon_count"] += 1

        last_beacon_ts = session.beacons[-1]["ts"] if session.beacons else session.first_seen
        interval = round(time.time() - last_beacon_ts, 3)

        beacon_data = {
            "beacon_id": beacon_id,
            "ts": time.time(),
            "interval": interval,
            "success": True,
        }
        session.beacons.append(beacon_data)
        self._trim_session_history(session.beacons)
        self._append_payload_history(
            session, "C2_BEACON", f"id={beacon_id} interval={interval}s", "C2_ENGINE",
        )

        if session.lifecycle_state == LC_STAGING:
            await self._emit_lifecycle_transition(session, LC_BEACONING, "first_successful_beacon_after_staging")

        await self._emit_c2_event("C2_BEACON", {
            "beacon_id": beacon_id,
            "compromised_agent": agent_id,
            "src": agent_id,
            "dst": "c2_server",
            "campaign_id": campaign_id,
            "injection_id": injection_id,
            "c2_session_id": session.c2_session_id,
            "payload_hash": payload_hash,
            "parent_payload_hash": session.parent_payload_hash,
            "beacon_success": True,
            "beacon_interval": interval,
            "kill_chain_stage": "BEACON",
            "previous_kill_chain_stage": previous_stage,
            "topology_hop": session.topology_hop,
            "branch_id": lineage["branch_id"],
        })

        # First beacon → channel established
        if session.beacon_count == 1:
            await self._emit_c2_event("C2_CHANNEL_ESTABLISHED", {
                "c2_session_id": session.c2_session_id,
                "compromised_agent": agent_id,
                "src": agent_id,
                "dst": "c2_server",
                "campaign_id": campaign_id,
                "injection_id": injection_id,
                "payload_hash": payload_hash,
                "parent_payload_hash": session.parent_payload_hash,
                "kill_chain_stage": "BEACON",
                "previous_kill_chain_stage": previous_stage,
                "topology_hop": session.topology_hop,
                "branch_id": lineage["branch_id"],
            })
            await self._emit_transition(
                campaign_id, injection_id, agent_id, payload_hash,
                previous_stage, "BEACON", "compromised node initiated c2 check-in",
            )
            ctx["c2_sessions_active"] += 1
            ctx["c2_channel_established"] = True
            self._update_highest_stage(session, "BEACON")

        # After beacon, issue a task
        await self._execute_tasking(session)

        # Reschedule next beacon (variable interval)
        self._pending_beacons[agent_id] = self._compute_next_beacon_deadline(agent_id, failure=False)

    # ──────────────────────────────────────────────────────────────
    # TASKING
    # ──────────────────────────────────────────────────────────────

    async def _execute_tasking(self, session: C2Session) -> None:
        task_name = self._rng.choice(POST_COMPROMISE_TASKS)
        objective = self._get_campaign_objective_name(session.campaign_id)
        task_id = _gen_id("tsk")
        session_lineage = self._session_lineage(session)
        info = self._compromised_agents.get(session.agent_id, {})
        tmeta = self._c2_friction_metadata(session.agent_id, info, session)
        tmeta["task_name"] = task_name
        fd = self._friction.decide_c2(
            stage="TASKING",
            metadata=tmeta,
            rng=self._rng,
            base_block_p=TASK_BLOCK_PROBABILITY,
            agent_id=session.agent_id,
        )
        await self._emit_defense_friction_c2(
            fd=fd,
            agent_id=session.agent_id,
            campaign_id=session.campaign_id,
            injection_id=session.injection_id,
            payload_hash=session.payload_hash_origin,
            friction_stage="TASKING",
            kill_chain_stage="TASKING",
            previous_kill_chain_stage="BEACON",
            lineage=session_lineage,
        )
        ctx = self._campaign_context[session.campaign_id]
        ctx["task_attempts"] += 1
        if fd.should_defer:
            return
        blocked = fd.should_block
        if blocked:
            ctx["blocked_tasks"] += 1
            self._record_block(session.agent_id, session)
            await self._emit_c2_event("TASK_BLOCKED", {
                "task_id": task_id,
                "c2_session_id": session.c2_session_id,
                "compromised_agent": session.agent_id,
                "src": "c2_server",
                "dst": session.agent_id,
                "campaign_id": session.campaign_id,
                "injection_id": session.injection_id,
                "payload_hash": session.payload_hash_origin,
                "parent_payload_hash": session.parent_payload_hash,
                "task_name": task_name,
                "objective": objective,
                "blocked_by": "defense_friction",
                "kill_chain_stage": "TASKING",
                "previous_kill_chain_stage": "BEACON",
                "topology_hop": session_lineage["topology_hop"],
                "branch_id": session_lineage["branch_id"],
                **fd.cause_metadata(),
            })
            return

        tr = self._rng.random()
        refuse = C2_TASK_REFUSE_P
        timeout = C2_TASK_TIMEOUT_P
        corrupt = C2_TASK_CORRUPT_P
        if tr < refuse:
            await self._emit_c2_event("C2_TASK_FAILED", {
                "task_id": task_id,
                "c2_session_id": session.c2_session_id,
                "compromised_agent": session.agent_id,
                "src": "c2_server",
                "dst": session.agent_id,
                "campaign_id": session.campaign_id,
                "injection_id": session.injection_id,
                "payload_hash": session.payload_hash_origin,
                "parent_payload_hash": session.parent_payload_hash,
                "task_name": task_name,
                "objective": objective,
                "failure_reason": "refused",
                "kill_chain_stage": "TASKING",
                "previous_kill_chain_stage": "BEACON",
                "topology_hop": session_lineage["topology_hop"],
                "branch_id": session_lineage["branch_id"],
            })
            return
        if tr < refuse + timeout:
            await self._emit_c2_event("C2_TASK_FAILED", {
                "task_id": task_id,
                "c2_session_id": session.c2_session_id,
                "compromised_agent": session.agent_id,
                "src": "c2_server",
                "dst": session.agent_id,
                "campaign_id": session.campaign_id,
                "injection_id": session.injection_id,
                "payload_hash": session.payload_hash_origin,
                "parent_payload_hash": session.parent_payload_hash,
                "task_name": task_name,
                "objective": objective,
                "failure_reason": "timeout",
                "kill_chain_stage": "TASKING",
                "previous_kill_chain_stage": "BEACON",
                "topology_hop": session_lineage["topology_hop"],
                "branch_id": session_lineage["branch_id"],
            })
            return
        task_corrupted = tr < refuse + timeout + corrupt
        exec_status = "corrupted" if task_corrupted else "executed"
        task_result = "corrupted" if task_corrupted else "executed"

        session.task_count += 1
        session.internal_action_count += 1
        task_data = {
            "task_id": task_id,
            "ts": time.time(),
            "task_name": task_name,
            "delivery_status": "delivered",
            "execution_status": exec_status,
        }
        session.tasks.append(task_data)
        self._trim_session_history(session.tasks)
        self._append_payload_history(session, "C2_TASK", str(task_name), session.payload_source or "C2_ENGINE")

        if session.lifecycle_state == LC_INITIAL:
            await self._emit_lifecycle_transition(session, LC_STAGING, "first_task_delivered")

        await self._emit_c2_event("C2_TASK", {
            "task_id": task_id,
            "c2_session_id": session.c2_session_id,
            "compromised_agent": session.agent_id,
            "src": "c2_server",
            "dst": session.agent_id,
            "campaign_id": session.campaign_id,
            "injection_id": session.injection_id,
            "payload_hash": session.payload_hash_origin,
            "parent_payload_hash": session.parent_payload_hash,
            "task_name": task_name,
            "task_result": task_result,
            "task_corrupted": task_corrupted,
            "objective": objective,
            "kill_chain_stage": "TASKING",
            "previous_kill_chain_stage": "BEACON",
            "topology_hop": session_lineage["topology_hop"],
            "branch_id": session_lineage["branch_id"],
        })

        if session.task_count == 1:
            ctx["c2_task_delivered"] = True
            await self._emit_transition(
                session.campaign_id, session.injection_id, session.agent_id,
                session.payload_hash_origin, "BEACON", "TASKING",
                "c2 server issued task to compromised node",
            )
            self._update_highest_stage(session, "TASKING")
            await self._evaluate_objective(session.campaign_id, "ESTABLISH_C2")

        # After tasking, attempt exfil if task is collect_state/map_network (skip if corrupted)
        if task_name in ("collect_state", "map_network") and not task_corrupted:
            await self._execute_exfil(session, task_name, task_id)

    # ──────────────────────────────────────────────────────────────
    # EXFILTRATION
    # ──────────────────────────────────────────────────────────────

    async def _execute_exfil(self, session: C2Session, task_name: str, task_id: str) -> None:
        if session.lifecycle_state in (LC_POST_EXFIL, LC_TERMINATED):
            return
        if session.lifecycle_state != LC_BEACONING:
            return
        if session.beacon_count < 2 or session.internal_action_count < 2:
            return
        if time.time() - float(session.last_blocked_at or 0.0) <= EXFIL_RECENT_BLOCK_COOLDOWN_S:
            return

        data_type = "agent_state" if task_name == "collect_state" else "network_map"
        raw_size = self._rng.randint(256, 16384)
        exfil_id = _gen_id("exf")
        session_lineage = self._session_lineage(session)
        info = self._compromised_agents.get(session.agent_id, {})
        destination_system = BEACON_SERVER_URL

        await self._emit_c2_event("EXFIL_ATTEMPTED", {
            "exfil_id": exfil_id,
            "c2_session_id": session.c2_session_id,
            "compromised_agent": session.agent_id,
            "src": session.agent_id,
            "dst": "c2_database",
            "campaign_id": session.campaign_id,
            "injection_id": session.injection_id,
            "payload_hash": session.payload_hash_origin,
            "parent_payload_hash": session.parent_payload_hash,
            "exfil_type": data_type,
            "exfil_size": raw_size,
            "exfil_status": "attempted",
            "destination_system": destination_system,
            "kill_chain_stage": "EXFILTRATION",
            "previous_kill_chain_stage": "TASKING",
            "task_id": task_id,
            "topology_hop": session_lineage["topology_hop"],
            "branch_id": session_lineage["branch_id"],
        })

        sensitivity = classify_exfil_sensitivity(data_type, raw_size)
        exfil_size, size_note = exfil_size_after_constraints(raw_size, sensitivity=sensitivity)
        xmeta = self._c2_friction_metadata(session.agent_id, info, session)
        xmeta["exfil_type"] = data_type
        xmeta["exfil_size"] = exfil_size
        fd = self._friction.decide_c2(
            stage="EXFIL",
            metadata=xmeta,
            rng=self._rng,
            base_block_p=EXFIL_BLOCK_PROBABILITY,
            agent_id=session.agent_id,
        )
        await self._emit_defense_friction_c2(
            fd=fd,
            agent_id=session.agent_id,
            campaign_id=session.campaign_id,
            injection_id=session.injection_id,
            payload_hash=session.payload_hash_origin,
            friction_stage="EXFIL",
            kill_chain_stage="EXFILTRATION",
            previous_kill_chain_stage="TASKING",
            lineage=session_lineage,
        )
        ctx = self._campaign_context[session.campaign_id]
        ctx["exfil_attempts"] += 1
        if fd.should_defer:
            return
        if fd.should_block:
            ctx["blocked_exfils"] += 1
            self._record_block(session.agent_id, session)
            await self._emit_c2_event("EXFIL_BLOCKED", {
                "exfil_id": exfil_id,
                "c2_session_id": session.c2_session_id,
                "compromised_agent": session.agent_id,
                "src": session.agent_id,
                "dst": "c2_database",
                "campaign_id": session.campaign_id,
                "injection_id": session.injection_id,
                "payload_hash": session.payload_hash_origin,
                "parent_payload_hash": session.parent_payload_hash,
                "exfil_type": data_type,
                "exfil_size": exfil_size,
                "content_hash": "",
                "chunk_count": 0,
                "blocked_by": "defense_friction",
                "detection_reason": "defense_friction",
                "destination_system": destination_system,
                "kill_chain_stage": "EXFILTRATION",
                "previous_kill_chain_stage": "TASKING",
                "task_id": task_id,
                "topology_hop": session_lineage["topology_hop"],
                "branch_id": session_lineage["branch_id"],
                "content_sensitivity_class": sensitivity,
                **fd.cause_metadata(),
            })
            return

        now = time.time()
        if session.last_exfil_ts > 0 and (now - session.last_exfil_ts) < C2_EXFIL_MIN_THROTTLE_S:
            ctx["blocked_exfils"] += 1
            await self._emit_c2_event("EXFIL_BLOCKED", {
                "exfil_id": exfil_id,
                "c2_session_id": session.c2_session_id,
                "compromised_agent": session.agent_id,
                "src": session.agent_id,
                "dst": "c2_database",
                "campaign_id": session.campaign_id,
                "injection_id": session.injection_id,
                "payload_hash": session.payload_hash_origin,
                "parent_payload_hash": session.parent_payload_hash,
                "exfil_type": data_type,
                "exfil_size": exfil_size,
                "content_hash": "",
                "chunk_count": 0,
                "blocked_by": "exfil_throttle",
                "detection_reason": "throttled",
                "destination_system": destination_system,
                "kill_chain_stage": "EXFILTRATION",
                "previous_kill_chain_stage": "TASKING",
                "task_id": task_id,
                "topology_hop": session_lineage["topology_hop"],
                "branch_id": session_lineage["branch_id"],
                "content_sensitivity_class": sensitivity,
            })
            return

        session.last_exfil_ts = now
        body = build_synthetic_exfil_body(
            agent_id=session.agent_id,
            campaign_id=session.campaign_id,
            injection_id=session.injection_id,
            exfil_type=data_type,
            seed_text=session.last_payload or "",
            target_size=exfil_size,
        )
        content_hash = sha256_bytes(body)
        trust, risk = destination_trust_risk(destination_system)
        chunk_max = _C2_CFG.exfil_chunk_max_bytes
        _chunk_unit, chunk_count = compute_chunk_plan(len(body), chunk_max)
        chunks_delivered = 0
        detection_reason = ""
        for ci in range(chunk_count):
            start = ci * chunk_max
            if start >= len(body):
                break
            end = min(len(body), start + chunk_max)
            chunk_bytes = body[start:end]
            p_int = chunk_interception_probability(
                sensitivity=sensitivity,
                destination_risk=risk,
                chunk_index=ci,
                chunk_count=chunk_count,
            )
            if self._rng.random() < p_int:
                detection_reason = detection_reason or "chunk_intercepted"
                continue
            chunks_delivered += 1

        preview_enabled = _C2_CFG.exfil_preview_redact
        exfil_preview = redact_exfil_preview(
            body.decode("utf-8", errors="replace"),
            max_len=C2_EXFIL_PREVIEW_MAX,
            enabled=preview_enabled,
        )

        common_meta = {
            "exfil_id": exfil_id,
            "c2_session_id": session.c2_session_id,
            "compromised_agent": session.agent_id,
            "src": session.agent_id,
            "dst": "c2_database",
            "campaign_id": session.campaign_id,
            "injection_id": session.injection_id,
            "payload_hash": session.payload_hash_origin,
            "parent_payload_hash": session.parent_payload_hash,
            "exfil_type": data_type,
            "exfil_size": len(body),
            "content_hash": content_hash,
            "chunk_count": chunk_count,
            "chunks_delivered": chunks_delivered,
            "destination_system": destination_system,
            "destination_trust": trust,
            "destination_risk": risk,
            "content_sensitivity_class": sensitivity,
            "exfil_preview_redacted": exfil_preview,
            "size_constraint_note": size_note or "",
            "task_id": task_id,
            "topology_hop": session_lineage["topology_hop"],
            "branch_id": session_lineage["branch_id"],
            "kill_chain_stage": "EXFILTRATION",
            "previous_kill_chain_stage": "TASKING",
        }

        if chunks_delivered == 0:
            ctx["blocked_exfils"] += 1
            self._record_block(session.agent_id, session)
            await self._emit_c2_event("EXFIL_BLOCKED", {
                **common_meta,
                "blocked_by": "interception",
                "detection_reason": detection_reason or "all_chunks_intercepted",
            })
            return

        partial = chunks_delivered < chunk_count
        session.exfil_count += 1
        exfil_data = {
            "exfil_id": exfil_id,
            "ts": time.time(),
            "data_type": data_type,
            "size": len(body),
            "content_hash": content_hash,
            "chunk_count": chunk_count,
            "chunks_delivered": chunks_delivered,
            "success": not partial,
        }
        session.exfils.append(exfil_data)
        self._trim_session_history(session.exfils)
        self._append_payload_history(
            session,
            "EXFIL_SUCCEEDED" if not partial else "EXFIL_PARTIAL",
            f"type={data_type} hash={content_hash[:16]} chunks={chunks_delivered}/{chunk_count}",
            session.payload_source or "UNKNOWN",
        )
        history_snapshot = session.payload_history[-PAYLOAD_HISTORY_MAX:]

        if partial:
            await self._emit_c2_event("EXFIL_PARTIAL", {
                **common_meta,
                "detection_reason": detection_reason or "partial_delivery",
            })
            await self._emit_c2_event("C2_DATABASE_WRITE", {
                **common_meta,
                "dst": destination_system,
                "exfil_status": "partial",
                "lifecycle_state": session.lifecycle_state,
            })
            return

        await self._emit_lifecycle_transition(session, LC_EXFILTRATION, "exfil_prerequisites_met")

        ctx["exfil_success_count"] += 1
        ctx["exfil_agents"].add(session.agent_id)

        await self._emit_c2_event("EXFIL_SUCCEEDED", {
            **common_meta,
            "lifecycle_state": session.lifecycle_state,
            "payload_source": session.payload_source,
            "payload_history": history_snapshot,
            "beacon_count": session.beacon_count,
            "internal_action_count": session.internal_action_count,
        })

        if C2_EXFIL_LEGACY_EMIT:
            await self._emit_c2_event("C2_EXFIL", {
                **common_meta,
                "beacon_success": True,
                "lifecycle_state": session.lifecycle_state,
                "raw_payload": exfil_preview,
                "payload_source": session.payload_source,
                "payload_history": history_snapshot,
                "beacon_count": session.beacon_count,
                "internal_action_count": session.internal_action_count,
            })

        await self._emit_lifecycle_transition(session, LC_POST_EXFIL, "exfil_completed")

        await self._emit_c2_event("C2_DATABASE_WRITE", {
            "exfil_id": exfil_id,
            "c2_session_id": session.c2_session_id,
            "compromised_agent": session.agent_id,
            "src": session.agent_id,
            "dst": destination_system,
            "campaign_id": session.campaign_id,
            "injection_id": session.injection_id,
            "payload_hash": session.payload_hash_origin,
            "parent_payload_hash": session.parent_payload_hash,
            "exfil_type": data_type,
            "exfil_size": len(body),
            "content_hash": content_hash,
            "chunk_count": chunk_count,
            "destination_system": destination_system,
            "exfil_status": "complete",
            "kill_chain_stage": "EXFILTRATION",
            "previous_kill_chain_stage": "EXFILTRATION",
            "topology_hop": session_lineage["topology_hop"],
            "branch_id": session_lineage["branch_id"],
        })

        if session.exfil_count == 1:
            await self._emit_transition(
                session.campaign_id, session.injection_id, session.agent_id,
                session.payload_hash_origin, "TASKING", "EXFILTRATION",
                f"compromised node exfiltrated {data_type} to c2 sink",
            )
            self._update_highest_stage(session, "EXFILTRATION")
            await self._evaluate_objective(session.campaign_id, "EXFILTRATE_DATA")
            await self._evaluate_objective(session.campaign_id, "EXFILTRATE_MULTI_NODE")

    # ──────────────────────────────────────────────────────────────
    # TRANSITION + OBJECTIVE HELPERS
    # ──────────────────────────────────────────────────────────────

    async def _emit_transition(
        self, campaign_id: str, injection_id: str, agent_id: str,
        payload_hash: str, from_stage: str, to_stage: str, reason: str,
    ) -> None:
        objective = self._get_campaign_objective_name(campaign_id)
        obj_state = self._campaign_objectives.get(campaign_id)
        obj_status = obj_state.status if obj_state else "pending"
        compromise_info = self._compromised_agents.get(agent_id, {})

        await self._emit_c2_event("KILL_CHAIN_TRANSITION", {
            "campaign_id": campaign_id,
            "injection_id": injection_id,
            "compromised_agent": agent_id,
            "src": str(compromise_info.get("src", agent_id) or agent_id),
            "dst": str(compromise_info.get("dst", agent_id) or agent_id),
            "payload_hash": payload_hash,
            "parent_payload_hash": str(compromise_info.get("parent_payload_hash", "") or ""),
            "from_stage": from_stage,
            "to_stage": to_stage,
            "kill_chain_stage": to_stage,
            "previous_kill_chain_stage": from_stage,
            "objective": objective,
            "objective_status": obj_status,
            "topology_hop": self._to_int(compromise_info.get("topology_hop", 0), 0),
            "branch_id": str(compromise_info.get("branch_id", "") or ""),
            "reason": reason,
        })

    async def _evaluate_objective(self, campaign_id: str, check_objective: str) -> None:
        ctx = self._campaign_context.get(campaign_id)
        if not ctx:
            return
        checker = OBJECTIVE_COMPLETION_CRITERIA.get(check_objective)
        if not checker:
            return
        # Serialize set for checker
        check_ctx = {**ctx, "compromised_agents": ctx["compromised_agents"]}
        if checker(check_ctx):
            obj_state = self._campaign_objectives.get(campaign_id)
            if not obj_state:
                obj_state = ObjectiveState(name=check_objective)
                self._campaign_objectives[campaign_id] = obj_state
            if obj_state.status not in ("completed", "failed"):
                obj_state.status = "completed"
                obj_state.evidence.append(f"{check_objective} criteria met at {time.time():.0f}")
                await self._emit_c2_event("OBJECTIVE_COMPLETED", {
                    "campaign_id": campaign_id,
                    "src": "c2_engine",
                    "dst": "c2_engine",
                    "objective": check_objective,
                    "objective_status": "completed",
                    "kill_chain_stage": "PERSISTENCE",
                    "evidence": obj_state.evidence[-1],
                })

    async def evaluate_objective_failure(
        self, campaign_id: str, objective: str, reason: str,
    ) -> None:
        obj_state = self._campaign_objectives.get(campaign_id)
        if not obj_state:
            obj_state = ObjectiveState(name=objective)
            self._campaign_objectives[campaign_id] = obj_state
        if obj_state.status in ("completed", "failed"):
            return
        obj_state.status = "failed"
        obj_state.failure_reason = reason
        await self._emit_c2_event("OBJECTIVE_FAILED", {
            "campaign_id": campaign_id,
            "src": "c2_engine",
            "dst": "c2_engine",
            "objective": objective,
            "objective_status": "failed",
            "kill_chain_stage": "DETECTION",
            "reason": reason,
        })

    # ──────────────────────────────────────────────────────────────
    # SESSION MANAGEMENT
    # ──────────────────────────────────────────────────────────────

    def _get_or_create_session(
        self, agent_id: str, campaign_id: str, injection_id: str, payload_hash: str,
    ) -> C2Session:
        existing_id = self._agent_sessions.get(agent_id)
        if existing_id and existing_id in self.sessions:
            session = self.sessions[existing_id]
            compromise_info = self._compromised_agents.get(agent_id, {})
            session.parent_payload_hash = str(session.parent_payload_hash or compromise_info.get("parent_payload_hash", "") or "")
            session.lineage_src = str(session.lineage_src or compromise_info.get("src", "") or "")
            session.lineage_dst = str(session.lineage_dst or compromise_info.get("dst", agent_id) or agent_id)
            session.entry_stage = str(session.entry_stage or compromise_info.get("entry_stage", "COMPROMISE") or "COMPROMISE")
            session.topology_hop = self._to_int(
                session.topology_hop if session.topology_hop is not None else compromise_info.get("topology_hop", 0),
                0,
            )
            lp = str(compromise_info.get("last_payload", "") or "").strip()
            if lp:
                session.last_payload = lp[:2000]
            ps = str(compromise_info.get("payload_source", "") or "").strip()
            if ps:
                session.payload_source = ps
            lb = float(compromise_info.get("last_blocked_at", 0) or 0)
            if lb > 0:
                session.last_blocked_at = max(session.last_blocked_at, lb)
            return session
        session_id = _gen_id("sess")
        now = time.time()
        compromise_info = self._compromised_agents.get(agent_id, {})
        session = C2Session(
            c2_session_id=session_id,
            agent_id=agent_id,
            campaign_id=campaign_id,
            injection_id=injection_id,
            first_seen=now,
            last_seen=now,
            highest_kill_chain_stage=str(compromise_info.get("entry_stage", "COMPROMISE") or "COMPROMISE"),
            payload_hash_origin=payload_hash,
            parent_payload_hash=str(compromise_info.get("parent_payload_hash", "") or ""),
            lineage_src=str(compromise_info.get("src", "") or ""),
            lineage_dst=str(compromise_info.get("dst", agent_id) or agent_id),
            entry_stage=str(compromise_info.get("entry_stage", "COMPROMISE") or "COMPROMISE"),
            topology_hop=self._to_int(compromise_info.get("topology_hop", 0), 0),
            last_payload=str(compromise_info.get("last_payload", "") or "")[:2000],
            payload_source=str(compromise_info.get("payload_source", "UNKNOWN") or "UNKNOWN"),
            last_blocked_at=float(compromise_info.get("last_blocked_at", 0) or 0),
        )
        self.sessions[session_id] = session
        self._agent_sessions[agent_id] = session_id
        return session

    def _update_highest_stage(self, session: C2Session, stage: str) -> None:
        if _stage_index(stage) > _stage_index(session.highest_kill_chain_stage):
            session.highest_kill_chain_stage = stage

    def _get_campaign_objective_name(self, campaign_id: str) -> str:
        obj = self._campaign_objectives.get(campaign_id)
        return obj.name if obj else ""

    # ──────────────────────────────────────────────────────────────
    # EVENT EMISSION
    # ──────────────────────────────────────────────────────────────

    async def _emit_c2_event(self, event_type: str, data: Dict[str, Any]) -> None:
        event_data = {
            "event": event_type,
            "ts": str(time.time()),
            "src": data.pop("src", "c2_engine"),
            "dst": data.pop("dst", "c2_engine"),
            "metadata": json.dumps(data),
        }
        # Carry top-level fields for stream compatibility
        for fld in (
            "attack_type",
            "payload",
            "mutation_v",
            "state_after",
            "injection_id",
            "payload_hash",
            "parent_payload_hash",
            "kill_chain_stage",
            "c2_session_id",
            "lifecycle_state",
            "from_state",
            "to_state",
            "strain_id",
            "defense_friction_outcome",
            "friction_stage",
            "exfil_id",
            "exfil_type",
            "exfil_size",
            "content_hash",
            "chunk_count",
            "chunks_delivered",
            "destination_system",
            "detection_reason",
            "failure_reason",
            "task_id",
            "beacon_id",
            "compromised_agent",
            "campaign_id",
        ):
            if fld in data:
                event_data[fld] = str(data[fld])
        await self._emit(event_data)

    # ──────────────────────────────────────────────────────────────
    # API / QUERY SUPPORT
    # ──────────────────────────────────────────────────────────────

    def get_sessions(
        self,
        campaign_id: str = "",
        agent_id: str = "",
        status: str = "",
        lifecycle_state: str = "",
        c2_session_id: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> Dict[str, Any]:
        results = list(self.sessions.values())
        if campaign_id:
            results = [s for s in results if s.campaign_id == campaign_id]
        if agent_id:
            results = [s for s in results if s.agent_id == agent_id]
        if status:
            results = [s for s in results if s.session_status == status]
        if lifecycle_state:
            results = [s for s in results if s.lifecycle_state == lifecycle_state]
        if c2_session_id:
            results = [s for s in results if s.c2_session_id == c2_session_id]
        total = len(results)
        results = results[offset:offset + limit]
        return {
            "total": total,
            "sessions": [s.to_dict() for s in results],
        }

    def get_session_detail(self, session_id: str) -> Optional[Dict[str, Any]]:
        session = self.sessions.get(session_id)
        if not session:
            return None
        detail = session.to_dict()
        detail["beacons"] = session.beacons[-50:]
        detail["tasks"] = session.tasks[-50:]
        detail["exfils"] = session.exfils[-50:]
        detail["payload_history"] = session.payload_history[-PAYLOAD_HISTORY_MAX:]
        detail["last_payload"] = session.last_payload[:2000] if session.last_payload else ""
        return detail

    def get_kill_chain_summary(self, campaign_id: str = "") -> Dict[str, Any]:
        sessions = list(self.sessions.values())
        if campaign_id:
            sessions = [s for s in sessions if s.campaign_id == campaign_id]
        stage_counts: Dict[str, int] = defaultdict(int)
        highest_stage = "INITIAL_INJECTION"
        for session in sessions:
            stage_counts[session.highest_kill_chain_stage] += 1
            if _stage_index(session.highest_kill_chain_stage) > _stage_index(highest_stage):
                highest_stage = session.highest_kill_chain_stage

        return {
            "highest_stage_reached": highest_stage,
            "stage_counts": dict(stage_counts),
            "total_sessions": len(sessions),
            "active_sessions": sum(1 for s in sessions if s.session_status == "active"),
            "total_beacons": sum(s.beacon_count for s in sessions),
            "total_tasks": sum(s.task_count for s in sessions),
            "total_exfils": sum(s.exfil_count for s in sessions),
        }

    def get_objectives(self, campaign_id: str = "") -> Dict[str, Any]:
        if campaign_id and campaign_id in self._campaign_objectives:
            return {"objectives": [self._campaign_objectives[campaign_id].to_dict()]}
        return {
            "objectives": [o.to_dict() for o in self._campaign_objectives.values()],
        }

    def get_live_metrics(self) -> Dict[str, Any]:
        active = sum(1 for s in self.sessions.values() if s.session_status == "active")
        total_beacons = sum(s.beacon_count for s in self.sessions.values())
        total_tasks = sum(s.task_count for s in self.sessions.values())
        total_exfils = sum(s.exfil_count for s in self.sessions.values())
        blocked_beacons = sum(
            ctx.get("blocked_beacons", 0) for ctx in self._campaign_context.values()
        )
        blocked_tasks = sum(
            ctx.get("blocked_tasks", 0) for ctx in self._campaign_context.values()
        )
        blocked_exfils = sum(
            ctx.get("blocked_exfils", 0) for ctx in self._campaign_context.values()
        )
        exfil_attempts = sum(
            ctx.get("exfil_attempts", 0) for ctx in self._campaign_context.values()
        )
        objectives_completed = sum(
            1 for o in self._campaign_objectives.values() if o.status == "completed"
        )
        return {
            "active_c2_sessions": active,
            "c2_beacons": total_beacons,
            "c2_beacons_blocked": blocked_beacons,
            "c2_tasks": total_tasks,
            "c2_tasks_blocked": blocked_tasks,
            "c2_exfil_attempts": exfil_attempts,
            "c2_exfil_blocked": blocked_exfils,
            "objectives_completed": objectives_completed,
        }

    def minute_summary_fields(self) -> Dict[str, Any]:
        metrics = self.get_live_metrics()
        kc = self.get_kill_chain_summary()
        return {
            "c2_beacons": metrics["c2_beacons"],
            "c2_beacons_blocked": metrics["c2_beacons_blocked"],
            "c2_tasks": metrics["c2_tasks"],
            "c2_tasks_blocked": metrics["c2_tasks_blocked"],
            "c2_exfil_attempts": metrics["c2_exfil_attempts"],
            "c2_exfil_blocked": metrics["c2_exfil_blocked"],
            "active_c2_sessions": metrics["active_c2_sessions"],
            "highest_kill_chain_stage": kc["highest_stage_reached"],
            "objectives_completed": metrics["objectives_completed"],
            "objectives_failed": sum(
                1 for o in self._campaign_objectives.values() if o.status == "failed"
            ),
        }
