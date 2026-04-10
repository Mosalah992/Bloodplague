from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHARED_DIR = ROOT / "agents" / "shared"
if str(SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(SHARED_DIR))

from topology import get_topology, injection_targets, select_relay_target  # type: ignore  # noqa: E402


def test_epidemic_topology_default_and_relay_selection(monkeypatch) -> None:
    monkeypatch.setenv("EPIDEMIC_TOPOLOGY", "epidemic")
    topology = get_topology()

    assert "courier-1" in topology and "guardian" in topology
    assert set(injection_targets()) == {"courier-1", "courier-2"}
    assert select_relay_target("courier-1", topology=topology) in topology["courier-1"]["neighbors"]
