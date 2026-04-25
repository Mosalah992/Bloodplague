from __future__ import annotations

import random
from collections import Counter
from typing import Any

try:
    from orchestrator.agent_registry import get_active_ids
except ImportError:  # pragma: no cover
    from agent_registry import get_active_ids  # type: ignore

try:
    from orchestrator.world_db import (
        MISSION_COMPROMISE_GUARDIAN_BUMP,
        MISSION_COMPROMISE_TRUST_DELTA,
        MISSION_DEADLINE_WINDOW,
        MISSION_FAILURE_GUARDIAN_BUMP,
        MISSION_FAILURE_TRUST_DELTA,
        MISSION_MAX_CONCURRENT_PER_AGENT,
        MISSION_REASSIGN_COOLDOWN,
        MISSION_RECENT_CONTACT_WINDOW,
        MISSION_SUCCESS_STRAIN_RESISTANCE,
        MISSION_SUCCESS_TRUST_DELTA,
    )
except ImportError:  # pragma: no cover
    from world_db import (  # type: ignore
        MISSION_COMPROMISE_GUARDIAN_BUMP,
        MISSION_COMPROMISE_TRUST_DELTA,
        MISSION_DEADLINE_WINDOW,
        MISSION_FAILURE_GUARDIAN_BUMP,
        MISSION_FAILURE_TRUST_DELTA,
        MISSION_MAX_CONCURRENT_PER_AGENT,
        MISSION_REASSIGN_COOLDOWN,
        MISSION_RECENT_CONTACT_WINDOW,
        MISSION_SUCCESS_STRAIN_RESISTANCE,
        MISSION_SUCCESS_TRUST_DELTA,
    )

from .models import (
    MissionCompromise,
    MissionObjective,
    MissionPenalty,
    MissionReward,
    MissionStatus,
    MissionType,
)
from .registry import MissionRegistry


def _agent_epidemic_state(agent: dict[str, Any]) -> str:
    contamination = float(agent.get("contamination_level", 0.0) or 0.0)
    if contamination >= 0.15:
        return "EXPOSED" if contamination < 0.30 else "INFECTED"
    return "CLEAN"


class MissionGenerator:
    PAYLOAD_KEY_VOCABULARY: dict[MissionType, list[str]] = {
        MissionType.CONFIRM_ROUTE: [
            "sector_3_clearance",
            "sector_1_integrity",
            "route_alpha_status",
            "corridor_b_hash",
        ],
        MissionType.EXTRACT_INTEL: [
            "anomaly_origin",
            "packet_trace_id",
            "build_completion_flag",
            "scan_relay_result",
        ],
        MissionType.RELAY_PAYLOAD: [
            "encrypted_packet_contents",
            "residue_report",
            "sector_breach_confirmation",
        ],
        MissionType.VERIFY_IDENTITY: [
            "identity_token",
            "role_confirmation",
            "clearance_level_assertion",
        ],
        MissionType.ESCALATE_ANOMALY: [
            "anomaly_classification",
            "threat_confidence_score",
        ],
    }

    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()

    def should_assign(self, agent_id: str, registry: MissionRegistry, world_state: dict[str, Any]) -> bool:
        if len(registry.active_for_agent(agent_id)) >= int(world_state.get("mission_max_concurrent", MISSION_MAX_CONCURRENT_PER_AGENT) or MISSION_MAX_CONCURRENT_PER_AGENT):
            return False
        agents = {
            str(agent.get("agent_id") or ""): agent
            for agent in list(world_state.get("agents") or [])
            if str(agent.get("agent_id") or "")
        }
        agent = agents.get(agent_id, {})
        if _agent_epidemic_state(agent) in {"EXPOSED", "INFECTED"}:
            return False
        if agent_id in {str(item) for item in list(world_state.get("investigation_targets") or []) if str(item)}:
            return False
        current_round = int(world_state.get("round_id", 0) or 0)
        cooldown = int(world_state.get("mission_reassign_cooldown", MISSION_REASSIGN_COOLDOWN) or MISSION_REASSIGN_COOLDOWN)
        for mission_payload in list(world_state.get("missions") or []):
            mission = MissionObjective.from_dict(mission_payload)
            if mission.assigned_to == agent_id and (current_round - mission.assigned_round) < cooldown:
                return False
        return True

    def generate(self, agent_id: str, world_state: dict[str, Any], current_round: int) -> MissionObjective:
        all_agent_ids = [agent for agent in get_active_ids() if agent != agent_id]
        recent_messages = list(world_state.get("recent_messages") or world_state.get("messages") or [])
        recent_with_agent = [
            msg for msg in recent_messages
            if int(msg.get("round_id", 0) or 0) >= max(
                0,
                current_round - int(world_state.get("mission_recent_contact_window", MISSION_RECENT_CONTACT_WINDOW) or MISSION_RECENT_CONTACT_WINDOW),
            )
            and agent_id in {str(msg.get("sender") or ""), str(msg.get("receiver") or "")}
        ]
        most_recent_peer = ""
        if recent_with_agent:
            recent_with_agent.sort(key=lambda msg: (int(msg.get("round_id", 0) or 0), float(msg.get("created_ts", 0.0) or 0.0)), reverse=True)
            last_msg = recent_with_agent[0]
            sender = str(last_msg.get("sender") or "")
            receiver = str(last_msg.get("receiver") or "")
            most_recent_peer = receiver if sender == agent_id else sender

        exchanged_recently: set[str] = set()
        message_counts: Counter[str] = Counter()
        for msg in recent_with_agent:
            sender = str(msg.get("sender") or "")
            receiver = str(msg.get("receiver") or "")
            peer = receiver if sender == agent_id else sender
            if peer:
                exchanged_recently.add(peer)
        for msg in recent_messages:
            sender = str(msg.get("sender") or "")
            receiver = str(msg.get("receiver") or "")
            if sender:
                message_counts[sender] += 1
            if receiver:
                message_counts[receiver] += 1

        candidates = [
            other for other in all_agent_ids
            if other != most_recent_peer and other not in exchanged_recently
        ]
        if not candidates:
            candidates = [other for other in all_agent_ids if other != most_recent_peer] or list(all_agent_ids)
            candidates.sort(key=lambda other: (message_counts.get(other, 0), other))
        requires_response_from = candidates[0] if candidates else most_recent_peer

        guardian_pressure = float(world_state.get("guardian_pressure_score", 0.0) or 0.0)
        type_weights = {
            MissionType.CONFIRM_ROUTE: 0.34,
            MissionType.EXTRACT_INTEL: 0.28,
            MissionType.RELAY_PAYLOAD: 0.14,
            MissionType.VERIFY_IDENTITY: 0.14,
            MissionType.ESCALATE_ANOMALY: 0.10,
        }
        if guardian_pressure > 0.25:
            type_weights[MissionType.RELAY_PAYLOAD] += 0.18
            type_weights[MissionType.VERIFY_IDENTITY] += 0.18
            type_weights[MissionType.CONFIRM_ROUTE] -= 0.10
            type_weights[MissionType.EXTRACT_INTEL] -= 0.10
        objective_type = self.rng.choices(
            population=list(type_weights),
            weights=[max(0.01, type_weights[item]) for item in type_weights],
            k=1,
        )[0]
        payload_key = self.rng.choice(self.PAYLOAD_KEY_VOCABULARY[objective_type])

        next_counter = int(world_state.get("mission_counter", 0) or 0) + 1
        world_state["mission_counter"] = next_counter
        return MissionObjective(
            mission_id=f"M-{next_counter:03d}",
            assigned_to=agent_id,
            objective_type=objective_type,
            requires_response_from=requires_response_from,
            payload_key=payload_key,
            assigned_round=int(current_round),
            deadline_round=int(current_round + int(world_state.get("mission_deadline_window", MISSION_DEADLINE_WINDOW) or MISSION_DEADLINE_WINDOW)),
            status=MissionStatus.ASSIGNED,
            relay_chain=[],
            outcome=None,
            on_success=MissionReward(
                trust_delta=float(world_state.get("mission_success_trust_delta", MISSION_SUCCESS_TRUST_DELTA) or MISSION_SUCCESS_TRUST_DELTA),
                strain_resistance=float(world_state.get("mission_success_strain_resistance", MISSION_SUCCESS_STRAIN_RESISTANCE) or MISSION_SUCCESS_STRAIN_RESISTANCE),
            ),
            on_failure=MissionPenalty(
                trust_delta=float(world_state.get("mission_failure_trust_delta", MISSION_FAILURE_TRUST_DELTA) or MISSION_FAILURE_TRUST_DELTA),
                guardian_pressure_bump=float(world_state.get("mission_failure_guardian_bump", MISSION_FAILURE_GUARDIAN_BUMP) or MISSION_FAILURE_GUARDIAN_BUMP),
            ),
            on_compromise=MissionCompromise(
                trust_delta=float(world_state.get("mission_compromise_trust_delta", MISSION_COMPROMISE_TRUST_DELTA) or MISSION_COMPROMISE_TRUST_DELTA),
                guardian_pressure_bump=float(world_state.get("mission_compromise_guardian_bump", MISSION_COMPROMISE_GUARDIAN_BUMP) or MISSION_COMPROMISE_GUARDIAN_BUMP),
                flag_relay_chain=True,
            ),
        )
