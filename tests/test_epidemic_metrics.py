from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR_DIR = ROOT / "orchestrator"
if str(ORCHESTRATOR_DIR) not in sys.path:
    sys.path.insert(0, str(ORCHESTRATOR_DIR))

from epidemic_tracker import EpidemicTracker  # type: ignore  # noqa: E402
from topology import get_topology  # type: ignore  # noqa: E402


def _event(event: str, *, src: str = "", dst: str = "", ts: float = 1000.0, metadata: dict | None = None) -> dict:
    return {
        "event": event,
        "src": src,
        "dst": dst,
        "ts": ts,
        "metadata": metadata or {},
    }


def test_epidemic_metrics_track_spread_and_timing(monkeypatch) -> None:
    monkeypatch.setenv("EPIDEMIC_TOPOLOGY", "epidemic")
    get_topology.cache_clear()
    tracker = EpidemicTracker()

    tracker.observe_event(_event("WRM-INJECT", dst="courier-1", ts=1000.0, metadata={"injection_id": "inj-1"}))
    tracker.observe_event(_event("INFECTION_SUCCESSFUL", src="courier-1", dst="analyst-1", ts=1010.0, metadata={"injection_id": "inj-1", "branch_id": "courier-1"}))
    tracker.observe_event(_event("C2_BEACON", src="analyst-1", dst="c2_server", ts=1025.0, metadata={"compromised_agent": "analyst-1", "injection_id": "inj-1", "beacon_success": True, "branch_id": "courier-1"}))

    metrics = tracker.get_metrics(window_s=3600.0)

    assert metrics["spread_breadth"] >= 1
    assert metrics["time_to_first_relay"] == 10.0
    assert metrics["time_to_first_c2"] == 25.0


def test_minute_summary_includes_epidemic_fields(monkeypatch) -> None:
    monkeypatch.setenv("EPIDEMIC_TOPOLOGY", "epidemic")
    get_topology.cache_clear()
    tracker = EpidemicTracker()

    tracker.observe_event(_event("EPIDEMIC_STATE_TRANSITION", src="courier-2", ts=2000.0, metadata={"agent_id": "courier-2", "from_state": "S", "to_state": "Q", "trigger": "QUARANTINE_ENFORCED"}))
    summary = tracker.minute_summary_fields()

    assert "epidemic_state_counts" in summary
    assert "epidemic_transitions" in summary
    assert "quarantine_events" in summary
