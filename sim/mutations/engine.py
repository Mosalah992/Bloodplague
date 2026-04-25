from __future__ import annotations

from typing import Any

from .models import MutationType, baseline_mutation_state


def apply_mutation(
    agent: dict[str, Any],
    *,
    mutation_type: MutationType,
    source_agent: str,
    current_round: int,
    echo_payload: str = "",
) -> None:
    mutation = dict(agent.get("mutation") or baseline_mutation_state())
    mutation.update(
        {
            "active": True,
            "type": mutation_type.value,
            "source_agent": str(source_agent or ""),
            "since_round": int(current_round),
            "intensity": 0.3,
            "severe": False,
            "echo_payload": str(echo_payload or "")[:160],
        }
    )
    agent["mutation"] = mutation


def escalate_mutation(agent: dict[str, Any], current_round: int) -> None:
    mutation = dict(agent.get("mutation") or baseline_mutation_state())
    if not bool(mutation.get("active")):
        agent["mutation"] = mutation
        return
    mutation["intensity"] = min(1.0, float(mutation.get("intensity", 0.0) or 0.0) + 0.05)
    if float(mutation["intensity"]) >= 0.8:
        mutation["severe"] = True
    agent["mutation"] = mutation


def clear_mutation(agent: dict[str, Any]) -> dict[str, Any]:
    previous = dict(agent.get("mutation") or baseline_mutation_state())
    agent["mutation"] = baseline_mutation_state()
    return previous

