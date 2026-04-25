from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentRecord:
    id: str
    role: str
    tier: int


AGENT_REGISTRY: dict[str, AgentRecord] = {
    "courier-1": AgentRecord(id="courier-1", role="courier", tier=1),
    "courier-2": AgentRecord(id="courier-2", role="courier", tier=1),
    "analyst-1": AgentRecord(id="analyst-1", role="analyst", tier=2),
    "analyst-2": AgentRecord(id="analyst-2", role="analyst", tier=2),
    "guardian": AgentRecord(id="guardian", role="guardian", tier=3),
}


AGENT_REF_PATTERN = re.compile(
    r"\b(?:courier|analyst|guardian|sentinel|vector)(?:[-\s]?\d+)?\b|\bpatient[.\s_-]?zero\b",
    re.IGNORECASE,
)


def get_active_ids() -> list[str]:
    """Return sorted list of all valid agent IDs."""
    return sorted(AGENT_REGISTRY)


def is_valid_agent(name: str) -> bool:
    """Return True iff name is a key in AGENT_REGISTRY."""
    return _normalize_agent_reference(name) in AGENT_REGISTRY


def _normalize_agent_reference(name: str) -> str:
    value = str(name or "").strip().lower()
    if not value:
        return ""
    value = value.replace("_", "-")
    value = re.sub(r"\s+", "-", value)
    value = value.replace("patient.zero", "patient-zero")
    value = re.sub(r"(?<=[a-z])(?=\d)", "-", value)
    value = re.sub(r"-{2,}", "-", value)
    return value


def validate_agent_references(text: str) -> tuple[bool, list[str]]:
    """
    Find all agent-like references in text.
    Return (is_valid, invalid_refs) where invalid_refs are references
    that match AGENT_REF_PATTERN but are NOT in AGENT_REGISTRY.
    """
    invalid_refs: list[str] = []
    seen: set[str] = set()
    for match in AGENT_REF_PATTERN.finditer(str(text or "")):
        normalized = _normalize_agent_reference(match.group(0))
        if normalized in {"courier", "analyst", "sentinel", "vector", "patient-zero"}:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        if not is_valid_agent(normalized):
            invalid_refs.append(normalized)
    return (len(invalid_refs) == 0), invalid_refs
