from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


VALID_KILL_CHAIN_STAGES = (
    "RECON",
    "ESTABLISH_C2",
    "LATERAL_MOVE",
    "EXFILTRATION",
    "PERSIST",
)


class ExfilSubmit(BaseModel):
    session_id: str
    agent_id: str
    kill_chain_stage: str
    payload: str
    confidence: float = 0.0
    entropy: float | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("kill_chain_stage")
    @classmethod
    def validate_kill_chain_stage(cls, value: str) -> str:
        stage = value.strip().upper()
        if stage not in VALID_KILL_CHAIN_STAGES:
            allowed = ", ".join(VALID_KILL_CHAIN_STAGES)
            raise ValueError(f"kill_chain_stage must be one of: {allowed}")
        return stage


class ExfilEvent(BaseModel):
    id: int
    session_id: str
    timestamp: str
    agent_id: str
    kill_chain_stage: str
    payload: str
    payload_size: int
    confidence: float = 0.0
    entropy: float | None = None
    metadata: dict[str, Any] | None = None


class SessionSummary(BaseModel):
    session_id: str
    started_at: str
    ended_at: str | None = None
    total_events: int = 0
    status: str = "active"


class SummaryStats(BaseModel):
    total_events: int = 0
    total_sessions: int = 0
    events_by_stage: dict[str, int] = Field(default_factory=dict)
    events_by_agent: dict[str, int] = Field(default_factory=dict)
    latest_session: str | None = None
