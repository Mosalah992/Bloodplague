import random
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))

from shared.topology import get_topology, injection_targets, relay_decision, select_relay_target  # noqa: E402


class TopologyTests(unittest.TestCase):
    def test_default_topology_is_epidemic_mesh(self) -> None:
        topology = get_topology()
        self.assertEqual(set(injection_targets()), {"courier-1", "courier-2"})
        self.assertEqual(set(topology["analyst-1"]["neighbors"]), {"analyst-2", "guardian"})
        self.assertIn("guardian", topology)

    def test_epidemic_topology_exposes_dual_injection_targets(self) -> None:
        topology = get_topology("epidemic")
        self.assertEqual(set(injection_targets("epidemic")), {"courier-1", "courier-2"})
        self.assertEqual(set(topology["analyst-1"]["neighbors"]), {"analyst-2", "guardian"})

    def test_relay_selection_excludes_quarantined_neighbors(self) -> None:
        decision = relay_decision(
            "courier-1",
            topology=get_topology("epidemic"),
            state={"courier-2": "quarantined", "analyst-1": "relay_infected"},
            rng=random.Random(7),
        )
        self.assertEqual(decision["selected"], "analyst-1")
        self.assertIn("courier-2", decision["excluded_neighbors"])

    def test_select_relay_target_returns_none_when_all_neighbors_quarantined(self) -> None:
        selected = select_relay_target(
            "courier-2",
            topology=get_topology("epidemic"),
            state={"courier-1": "quarantined", "analyst-2": "q"},
            rng=random.Random(11),
        )
        self.assertIsNone(selected)
