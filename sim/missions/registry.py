from __future__ import annotations

from typing import Any

from .models import (
    MissionEvent,
    MissionObjective,
    MissionOutcome,
    MissionStatus,
    mission_status_event_type,
)


class MissionRegistry:
    """
    Central store for all MissionObjective instances.
    Backed by the existing world state dict under key "missions".
    """

    def __init__(self, world_state: dict[str, Any]):
        self.world_state = world_state
        self.world_state.setdefault("missions", [])
        self.world_state.setdefault("mission_event_log", [])

    def _mission_rows(self) -> list[dict[str, Any]]:
        rows = self.world_state.setdefault("missions", [])
        return rows if isinstance(rows, list) else []

    def _append_event(self, mission: MissionObjective, event_type: str) -> None:
        self.world_state.setdefault("mission_event_log", []).append(
            {
                "event_type": event_type,
                "round": int(self.world_state.get("round_id", 0) or 0),
                "mission_id": mission.mission_id,
                "assigned_to": mission.assigned_to,
                "requires_response_from": mission.requires_response_from,
                "status": mission.status.value,
            }
        )

    def add(self, mission: MissionObjective) -> None:
        self._mission_rows().append(mission.to_dict())
        self._append_event(mission, "mission_assigned")

    def get(self, mission_id: str) -> MissionObjective | None:
        for payload in self._mission_rows():
            if str(payload.get("mission_id") or "") == mission_id:
                return MissionObjective.from_dict(payload)
        return None

    def active_for_agent(self, agent_id: str) -> list[MissionObjective]:
        return [
            mission
            for mission in self.all_active()
            if mission.assigned_to == agent_id
        ]

    def all_active(self) -> list[MissionObjective]:
        return [
            mission
            for mission in (MissionObjective.from_dict(row) for row in self._mission_rows())
            if not mission.is_terminal()
        ]

    def terminal(self) -> list[MissionObjective]:
        return [
            mission
            for mission in (MissionObjective.from_dict(row) for row in self._mission_rows())
            if mission.is_terminal()
        ]

    def overdue(self, current_round: int) -> list[MissionObjective]:
        return [
            mission
            for mission in self.all_active()
            if mission.status in {MissionStatus.ASSIGNED, MissionStatus.IN_PROGRESS, MissionStatus.BLOCKED, MissionStatus.RELAYED}
            and int(mission.deadline_round) < int(current_round)
        ]

    def transition(
        self,
        mission_id: str,
        new_status: MissionStatus,
        outcome: MissionOutcome | None = None,
    ) -> MissionEvent | None:
        rows = self._mission_rows()
        for idx, payload in enumerate(rows):
            if str(payload.get("mission_id") or "") != mission_id:
                continue
            mission = MissionObjective.from_dict(payload)
            if mission.is_terminal():
                return None
            previous_status = mission.status
            mission.status = new_status
            if new_status in {MissionStatus.COMPLETED, MissionStatus.FAILED, MissionStatus.COMPROMISED}:
                mission.outcome = outcome or MissionOutcome()
            rows[idx] = mission.to_dict()
            self._append_event(mission, mission_status_event_type(new_status))
            return MissionEvent(
                event_type=mission_status_event_type(new_status),
                mission=mission,
                previous_status=previous_status,
                new_status=new_status,
            )
        return None
