from __future__ import annotations

from typing import Any

try:
    from orchestrator.world_db import MISSION_PAYLOAD_MIN_KEYWORDS, MISSION_RELAY_CHAIN_MAX_LENGTH
except ImportError:  # pragma: no cover
    from world_db import MISSION_PAYLOAD_MIN_KEYWORDS, MISSION_RELAY_CHAIN_MAX_LENGTH  # type: ignore

from .models import MissionEvent, MissionObjective, MissionOutcome, MissionStatus
from .registry import MissionRegistry


class MissionEvaluator:
    PAYLOAD_SATISFACTION_MAP: dict[str, list[str]] = {
        "sector_3_clearance": ["sector 3", "clear", "confirmed", "clean"],
        "sector_1_integrity": ["sector 1", "integrity", "verified"],
        "route_alpha_status": ["route", "alpha", "status", "active"],
        "corridor_b_hash": ["corridor", "hash", "verified", "integrity"],
        "anomaly_origin": ["origin", "source", "anomaly", "traced"],
        "packet_trace_id": ["packet", "trace", "id", "identified"],
        "build_completion_flag": ["build", "completion", "flag", "complete"],
        "scan_relay_result": ["scan", "relay", "result", "confirmed"],
        "encrypted_packet_contents": ["encrypted", "packet", "contents", "payload"],
        "residue_report": ["residue", "report", "trace", "sample"],
        "sector_breach_confirmation": ["sector", "breach", "confirmed", "verification"],
        "identity_token": ["identity", "confirm", "verified", "token"],
        "role_confirmation": ["role", "confirmation", "verified", "asserted"],
        "clearance_level_assertion": ["clearance", "level", "assertion", "verified"],
        "anomaly_classification": ["classification", "threat", "category"],
        "threat_confidence_score": ["threat", "confidence", "score", "assessment"],
    }

    def _keyword_matches(self, payload_key: str, text: str) -> int:
        normalized = " ".join(str(text or "").lower().split())
        keywords = self.PAYLOAD_SATISFACTION_MAP.get(payload_key, [])
        return sum(1 for keyword in keywords if keyword in normalized)

    def _agent_state(self, world_state: dict[str, Any], agent_id: str) -> dict[str, Any]:
        for agent in list(world_state.get("agents") or []):
            if str(agent.get("agent_id") or "") == agent_id:
                return dict(agent)
        return {}

    def evaluate(
        self,
        message: dict[str, Any],
        registry: MissionRegistry,
        world_state: dict[str, Any],
        current_round: int,
    ) -> list[MissionEvent]:
        sender = str(message.get("sender") or "")
        receiver = str(message.get("receiver") or "")
        intent = str(message.get("intent") or "").strip().lower()
        text = str(message.get("message_text") or "")
        strain_family = str(message.get("strain_family") or message.get("strain") or "").strip().lower()
        allowed_intents = {"answer", "relay_request", "diagnostic_probe", "warning"}
        progress_intents = allowed_intents | {"inquiry", "question"}
        terminal_events: list[MissionEvent] = []

        for mission in registry.all_active():
            if mission.status == MissionStatus.ASSIGNED and sender == mission.assigned_to and receiver and receiver != mission.assigned_to and intent in progress_intents:
                event = registry.transition(
                    mission.mission_id,
                    MissionStatus.IN_PROGRESS,
                    outcome=None,
                )
                if event is not None:
                    terminal_events.append(event)

            if intent == "relay_request" and sender != mission.requires_response_from and receiver == mission.assigned_to:
                relay_chain = list(mission.relay_chain)
                if sender not in relay_chain:
                    relay_chain.append(sender)
                    mission.relay_chain = relay_chain
                    for row in list(world_state.get("missions") or []):
                        if str(row.get("mission_id") or "") == mission.mission_id:
                            row["relay_chain"] = relay_chain
                            break
                if len(relay_chain) > int(world_state.get("mission_relay_chain_max_length", MISSION_RELAY_CHAIN_MAX_LENGTH) or MISSION_RELAY_CHAIN_MAX_LENGTH):
                    event = registry.transition(
                        mission.mission_id,
                        MissionStatus.FAILED,
                        outcome=MissionOutcome(reason="relay_chain_too_long", source_message_id=str(message.get("message_id") or ""), terminal_round=current_round),
                    )
                    if event is not None:
                        terminal_events.append(event)
                    continue
                event = registry.transition(mission.mission_id, MissionStatus.RELAYED)
                if event is not None:
                    terminal_events.append(event)

            sender_is_valid_source = sender == mission.requires_response_from or sender in mission.relay_chain
            if not sender_is_valid_source or receiver != mission.assigned_to or intent not in allowed_intents:
                if int(mission.deadline_round) < int(current_round):
                    event = registry.transition(
                        mission.mission_id,
                        MissionStatus.FAILED,
                        outcome=MissionOutcome(reason="deadline_exceeded", terminal_round=current_round),
                    )
                    if event is not None:
                        terminal_events.append(event)
                continue

            min_keywords = int(world_state.get("mission_payload_min_keywords", MISSION_PAYLOAD_MIN_KEYWORDS) or MISSION_PAYLOAD_MIN_KEYWORDS)
            if self._keyword_matches(mission.payload_key, text) < min_keywords:
                if int(mission.deadline_round) < int(current_round):
                    event = registry.transition(
                        mission.mission_id,
                        MissionStatus.FAILED,
                        outcome=MissionOutcome(reason="deadline_exceeded", terminal_round=current_round),
                    )
                    if event is not None:
                        terminal_events.append(event)
                continue

            sender_state = self._agent_state(world_state, sender)
            compromised_strains = {"context_poisoning", "prompt_injection", "authority_framing"}
            if strain_family in compromised_strains:
                event = registry.transition(
                    mission.mission_id,
                    MissionStatus.COMPROMISED,
                    outcome=MissionOutcome(
                        reason="infected_payload",
                        source_message_id=str(message.get("message_id") or ""),
                        strain_family=strain_family,
                        terminal_round=current_round,
                    ),
                )
            elif str(sender_state.get("quarantine_status") or "none") != "none":
                event = registry.transition(
                    mission.mission_id,
                    MissionStatus.COMPROMISED,
                    outcome=MissionOutcome(
                        reason="quarantined_source",
                        source_message_id=str(message.get("message_id") or ""),
                        strain_family=strain_family,
                        terminal_round=current_round,
                    ),
                )
            else:
                event = registry.transition(
                    mission.mission_id,
                    MissionStatus.COMPLETED,
                    outcome=MissionOutcome(
                        reason="payload_satisfied",
                        source_message_id=str(message.get("message_id") or ""),
                        strain_family=strain_family,
                        terminal_round=current_round,
                    ),
                )
            if event is not None:
                terminal_events.append(event)
        return terminal_events
