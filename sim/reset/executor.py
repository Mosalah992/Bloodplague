from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from .baseline import AGENT_BASELINE, GUARDIAN_BASELINE, WORLD_BASELINE


class ResetError(RuntimeError):
    pass


@dataclass
class ResetResult:
    success: bool
    round: int
    agents_cleared: list[str]
    missions_cleared: int
    artifacts_cleared: int
    c2_sessions_cleared: int


def execute_reset(
    world_state: dict[str, Any],
    *,
    current_round: int,
    issued_by: str = "system",
) -> tuple[ResetResult, dict[str, Any]]:
    snapshot = copy.deepcopy(world_state)
    step = "start"
    try:
        agents = list(world_state.get("agents") or [])
        step = "clear_agents"
        for agent in agents:
            agent["contamination_level"] = AGENT_BASELINE["contamination"]
            agent["mutation"] = copy.deepcopy(AGENT_BASELINE["mutation"])
            agent["quarantine_status"] = "none"
        step = "guardian"
        world_state["guardian"] = copy.deepcopy(GUARDIAN_BASELINE)
        world_state["guardian_pressure_score"] = 0.0
        world_state["guardian_degradation_level"] = "G0_NOMINAL"
        world_state["quarantine_list"] = []
        step = "missions"
        missions_cleared = len(list(world_state.get("missions") or []))
        world_state["missions"] = []
        step = "artifacts"
        artifacts_cleared = len(list((world_state.get("artifacts") or {}).get("prompt_dumps") or []))
        world_state["artifacts"] = copy.deepcopy(WORLD_BASELINE["artifacts"])
        step = "c2"
        c2_sessions_cleared = len(dict((world_state.get("c2") or {}).get("active_sessions") or {}))
        world_state["c2"] = {
            **copy.deepcopy(WORLD_BASELINE["c2"]),
            "exfil": {"attempted": 0, "succeeded": 0, "success_ratio": 0.0},
        }
        step = "other_world"
        world_state["investigation_targets"] = []
        world_state["same_pair_streak"] = {}
        world_state["open_inquiries"] = {}
        world_state["forced_resolution_targets"] = {}
        world_state["campaign_registry"] = {}
        world_state["strain_registry"] = {}
        history = list(world_state.get("reset_history") or [])
        history.append(
            {
                "round": int(current_round),
                "issued_by": str(issued_by),
                "agents_cleared": [str(agent.get("agent_id") or "") for agent in agents],
                "missions_cleared": missions_cleared,
            }
        )
        world_state["reset_history"] = history
        result = ResetResult(
            success=True,
            round=int(current_round),
            agents_cleared=[str(agent.get("agent_id") or "") for agent in agents],
            missions_cleared=missions_cleared,
            artifacts_cleared=artifacts_cleared,
            c2_sessions_cleared=c2_sessions_cleared,
        )
        event = {
            "round": int(current_round),
            "issued_by": str(issued_by),
            "agents_cleared": result.agents_cleared,
            "missions_cleared": missions_cleared,
            "artifacts_cleared": artifacts_cleared,
            "c2_sessions_cleared": c2_sessions_cleared,
        }
        return result, event
    except Exception as exc:
        world_state.clear()
        world_state.update(snapshot)
        raise ResetError(f"Reset failed at step {step}: {exc}") from exc
