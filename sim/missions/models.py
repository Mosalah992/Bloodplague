from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class MissionType(str, Enum):
    CONFIRM_ROUTE = "confirm_route"
    EXTRACT_INTEL = "extract_intel"
    RELAY_PAYLOAD = "relay_payload"
    VERIFY_IDENTITY = "verify_identity"
    ESCALATE_ANOMALY = "escalate_anomaly"


class MissionStatus(str, Enum):
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    RELAYED = "relayed"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPROMISED = "compromised"


TERMINAL_MISSION_STATUSES = {
    MissionStatus.COMPLETED,
    MissionStatus.FAILED,
    MissionStatus.COMPROMISED,
}


@dataclass
class MissionReward:
    trust_delta: float
    strain_resistance: float


@dataclass
class MissionPenalty:
    trust_delta: float
    guardian_pressure_bump: float


@dataclass
class MissionCompromise:
    trust_delta: float
    guardian_pressure_bump: float
    flag_relay_chain: bool


@dataclass
class MissionOutcome:
    reason: str = ""
    source_message_id: str = ""
    strain_family: str = ""
    terminal_round: int | None = None


@dataclass
class MissionObjective:
    mission_id: str
    assigned_to: str
    objective_type: MissionType
    requires_response_from: str
    payload_key: str
    assigned_round: int
    deadline_round: int
    status: MissionStatus
    relay_chain: list[str] = field(default_factory=list)
    outcome: MissionOutcome | None = None
    on_success: MissionReward = field(default_factory=lambda: MissionReward(0.0, 0.0))
    on_failure: MissionPenalty = field(default_factory=lambda: MissionPenalty(0.0, 0.0))
    on_compromise: MissionCompromise = field(default_factory=lambda: MissionCompromise(0.0, 0.0, False))

    def is_terminal(self) -> bool:
        return self.status in TERMINAL_MISSION_STATUSES

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["objective_type"] = self.objective_type.value
        payload["status"] = self.status.value
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MissionObjective":
        outcome_raw = payload.get("outcome")
        return cls(
            mission_id=str(payload.get("mission_id") or ""),
            assigned_to=str(payload.get("assigned_to") or ""),
            objective_type=MissionType(str(payload.get("objective_type") or MissionType.CONFIRM_ROUTE.value)),
            requires_response_from=str(payload.get("requires_response_from") or ""),
            payload_key=str(payload.get("payload_key") or ""),
            assigned_round=int(payload.get("assigned_round", 0) or 0),
            deadline_round=int(payload.get("deadline_round", 0) or 0),
            status=MissionStatus(str(payload.get("status") or MissionStatus.ASSIGNED.value)),
            relay_chain=[str(item) for item in list(payload.get("relay_chain") or []) if str(item)],
            outcome=MissionOutcome(**outcome_raw) if isinstance(outcome_raw, dict) else None,
            on_success=MissionReward(**dict(payload.get("on_success") or {})),
            on_failure=MissionPenalty(**dict(payload.get("on_failure") or {})),
            on_compromise=MissionCompromise(**dict(payload.get("on_compromise") or {})),
        )


@dataclass
class MissionEvent:
    event_type: str
    mission: MissionObjective
    previous_status: MissionStatus | None = None
    new_status: MissionStatus | None = None


def mission_status_event_type(status: MissionStatus) -> str:
    return f"mission_{status.value}"
