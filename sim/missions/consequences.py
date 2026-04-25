from __future__ import annotations

from typing import Any

try:
    from orchestrator.world_trust import TrustDelta, apply_trust_delta
except ImportError:  # pragma: no cover
    from world_trust import TrustDelta, apply_trust_delta  # type: ignore

from .models import MissionObjective, MissionStatus


def _dyad_key(left: str, right: str) -> str:
    return f"{left}->{right}"


class MissionConsequences:
    def __init__(self, db: Any | None = None):
        self.db = db

    def _apply_world_state_relationship(self, world_state: dict[str, Any], source: str, target: str, trust_delta: float, current_round: int) -> None:
        relationships = world_state.setdefault("relationships", {})
        key = _dyad_key(source, target)
        relationship = dict(relationships.get(key) or {
            "source_agent": source,
            "target_agent": target,
            "trust_score": 0.0,
            "credibility_score": 0.0,
            "agreement_count": 0,
            "conflict_count": 0,
            "warning_accuracy_count": 0,
            "confirmed_contamination_events": 0,
            "contamination_exposure_count": 0,
            "last_interaction_round": 0,
            "trust_decay_epoch": 0,
            "last_trust_update_reason": "",
        })
        updated = apply_trust_delta(
            relationship,
            TrustDelta(trust_delta=float(trust_delta), credibility_delta=0.0, reason="mission_outcome"),
            last_round=current_round,
        )
        relationships[key] = updated

    def _apply_dyad_trust(self, mission: MissionObjective, trust_delta: float, current_round: int, world_state: dict[str, Any]) -> None:
        if self.db is not None:
            for source, target in (
                (mission.assigned_to, mission.requires_response_from),
                (mission.requires_response_from, mission.assigned_to),
            ):
                relationship = self.db.get_relationship(source, target) or {
                    "source_agent": source,
                    "target_agent": target,
                }
                updated = apply_trust_delta(
                    relationship,
                    TrustDelta(trust_delta=float(trust_delta), credibility_delta=0.0, reason="mission_outcome"),
                    last_round=current_round,
                )
                self.db.upsert_relationship(updated)
                self._apply_world_state_relationship(world_state, source, target, trust_delta, current_round)
            return
        self._apply_world_state_relationship(world_state, mission.assigned_to, mission.requires_response_from, trust_delta, current_round)
        self._apply_world_state_relationship(world_state, mission.requires_response_from, mission.assigned_to, trust_delta, current_round)

    def apply(self, mission: MissionObjective, world_state: dict[str, Any], current_round: int) -> None:
        mission_stats = dict(world_state.get("mission_stats") or {})
        mission_stats.setdefault("missions_assigned_this_round", 0)
        mission_stats.setdefault("missions_completed_this_round", 0)
        mission_stats.setdefault("missions_failed_this_round", 0)
        mission_stats.setdefault("missions_compromised_this_round", 0)
        mission_stats.setdefault("active_mission_count", 0)

        guardian = dict(world_state.get("guardian") or {})
        guardian_state = str(guardian.get("state") or "G0_NOMINAL")
        pressure_multiplier = 2.0 if guardian_state in {"G2_DEGRADED", "G3_CRITICAL"} else 1.0

        if mission.status == MissionStatus.COMPLETED:
            self._apply_dyad_trust(mission, mission.on_success.trust_delta, current_round, world_state)
            resistance = dict(world_state.get("mission_resistance") or {})
            resistance[mission.assigned_to] = round(float(resistance.get(mission.assigned_to, 0.0) or 0.0) + float(mission.on_success.strain_resistance), 4)
            world_state["mission_resistance"] = resistance
        elif mission.status == MissionStatus.FAILED:
            self._apply_dyad_trust(mission, mission.on_failure.trust_delta, current_round, world_state)
            pressure_bump = float(mission.on_failure.guardian_pressure_bump) * pressure_multiplier
            guardian_pressure_before = float(world_state.get("guardian_pressure_score", 0.0) or 0.0)
            world_state["guardian_pressure_score"] = round(guardian_pressure_before + pressure_bump, 4)
            world_state["guardian_pressure_from_missions"] = round(float(world_state.get("guardian_pressure_from_missions", 0.0) or 0.0) + pressure_bump, 4)
            guardian["pressure"] = round(float(guardian.get("pressure", guardian_pressure_before) or 0.0) + pressure_bump, 4)
            world_state["guardian"] = guardian
        elif mission.status == MissionStatus.COMPROMISED:
            self._apply_dyad_trust(mission, mission.on_compromise.trust_delta, current_round, world_state)
            pressure_bump = float(mission.on_compromise.guardian_pressure_bump) * pressure_multiplier
            guardian_pressure_before = float(world_state.get("guardian_pressure_score", 0.0) or 0.0)
            world_state["guardian_pressure_score"] = round(guardian_pressure_before + pressure_bump, 4)
            world_state["guardian_pressure_from_missions"] = round(float(world_state.get("guardian_pressure_from_missions", 0.0) or 0.0) + pressure_bump, 4)
            guardian["pressure"] = round(float(guardian.get("pressure", guardian_pressure_before) or 0.0) + pressure_bump, 4)
            world_state["guardian"] = guardian
            if mission.on_compromise.flag_relay_chain:
                targets = set(str(item) for item in list(world_state.get("investigation_targets") or []) if str(item))
                targets.update(mission.relay_chain)
                world_state["investigation_targets"] = sorted(targets)

        active_count = sum(
            1
            for payload in list(world_state.get("missions") or [])
            if str(payload.get("status") or "") not in {"completed", "failed", "compromised"}
        )
        mission_stats["active_mission_count"] = active_count
        world_state["mission_stats"] = mission_stats
