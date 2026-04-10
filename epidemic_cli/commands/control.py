from __future__ import annotations

from ..core.api import OrchestratorAPI
from ..core.discovery import orchestrator_url
from ..core.output import print_message


def _api() -> OrchestratorAPI:
    return OrchestratorAPI(base_url=orchestrator_url())


def reset() -> None:
    result = _api().safe_post("/reset")
    if not result.ok:
        print_message(f"reset failed: {result.error}", style="red")
        raise SystemExit(1)
    print_message(f"reset issued :: {result.data}", style="green")


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
