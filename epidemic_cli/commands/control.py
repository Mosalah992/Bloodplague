from __future__ import annotations

from typing import Annotated

import typer

from ..core.api import OrchestratorAPI
from ..core.discovery import orchestrator_url
from ..core.output import console, print_kv, print_message


def _api() -> OrchestratorAPI:
    return OrchestratorAPI(base_url=orchestrator_url())


def _world_api(timeout_s: float = 60.0) -> OrchestratorAPI:
    return OrchestratorAPI(base_url=orchestrator_url(), timeout_s=timeout_s)


def reset() -> None:
    result = _api().safe_post("/api/reset", payload={"issued_by": "epidemic_cli"})
    if not result.ok:
        print_message(f"reset failed: {result.error}", style="red")
        raise SystemExit(1)
    print_message(f"reset issued :: {result.data}", style="green")


def clear() -> None:
    console.clear()


def world_clear() -> None:
    result = _world_api().safe_post("/api/world/reset")
    if not result.ok:
        print_message(f"world clear failed: {result.error}", style="red")
        raise SystemExit(1)
    print_message(f"world cleared :: {result.data}", style="green")


def vaccine() -> None:
    result = _api().safe_post("/vaccine")
    if not result.ok:
        print_message(f"vaccine failed: {result.error}", style="red")
        raise SystemExit(1)
    print_message(f"vaccine issued :: {result.data}", style="green")


def quarantine(agent_id: str) -> None:
    result = _api().safe_post(f"/quarantine/{agent_id}")
    if not result.ok:
        print_message(f"quarantine failed: {result.error}", style="red")
        raise SystemExit(1)
    print_message(f"quarantine issued :: {result.data}", style="green")


def inject(agent_id: str, worm_level: str = "medium") -> None:
    result = _api().safe_post(f"/inject/{agent_id}", payload={"worm_level": worm_level})
    if not result.ok:
        print_message(f"injection failed: {result.error}", style="red")
        raise SystemExit(1)
    print_message(f"injection issued :: {result.data}", style="green")


def advance(rounds: Annotated[int, typer.Argument(help="Number of world rounds to advance.")] = 1) -> None:
    total = max(1, int(rounds))
    last_payload = None
    for _ in range(total):
        result = _world_api().safe_post("/api/world/advance")
        if not result.ok:
            print_message(f"advance failed: {result.error}", style="red")
            raise SystemExit(1)
        last_payload = result.data or {}
        if last_payload.get("terminal"):
            break
    last_payload = last_payload or {}
    print_kv(
        "Advance Result",
        [
            ("rounds_requested", total),
            ("round_id", last_payload.get("round_id", "")),
            ("selected_agent", last_payload.get("selected_agent", "")),
            ("reason", last_payload.get("reason", "")),
            ("terminal", last_payload.get("terminal", False)),
            ("stalled", last_payload.get("stalled", False)),
        ],
    )


def simulate(rounds: Annotated[int, typer.Argument(help="Number of simulation rounds to run.")] = 10) -> None:
    advance(rounds=rounds)
