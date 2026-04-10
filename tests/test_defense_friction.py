"""
Patch 5: defense friction memory and C2-stage blocking before full kill-chain success.
"""

import os
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT / "orchestrator"
AGENTS = ROOT / "agents"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ORCH))
sys.path.insert(0, str(AGENTS))
sys.path.insert(0, str(AGENTS / "shared"))

from defense_friction import DefenseFrictionMemory  # noqa: E402
from c2 import C2Engine  # noqa: E402


class DefenseFrictionMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["DEFENSE_FRICTION_ENABLED"] = "1"
        os.environ["DEFENSE_FRICTION_SIGHTING_WEIGHT"] = "0.2"
        os.environ["DEFENSE_FRICTION_ANOMALY_TO_BLOCK"] = "0.9"
        os.environ["DEFENSE_FRICTION_DEFER_MARGIN"] = "0.0"
        os.environ["DEFENSE_FALSE_POSITIVE_RATE"] = "0"
        os.environ["DEFENSE_DELAYED_DETECTION_PROB"] = "0"
        self.mem = DefenseFrictionMemory()

    def tearDown(self) -> None:
        for k in (
            "DEFENSE_FRICTION_ENABLED",
            "DEFENSE_FRICTION_SIGHTING_WEIGHT",
            "DEFENSE_FRICTION_ANOMALY_TO_BLOCK",
            "DEFENSE_FRICTION_DEFER_MARGIN",
            "DEFENSE_FALSE_POSITIVE_RATE",
            "DEFENSE_DELAYED_DETECTION_PROB",
        ):
            os.environ.pop(k, None)

    def test_repeated_observations_raise_block_probability(self) -> None:
        md = {
            "payload_hash": "ph_repeat",
            "strain_id": "st_x",
            "attack_type": "T1",
            "strategy_family": "DIRECT_OVERRIDE",
            "campaign_id": "c1",
        }
        for _ in range(25):
            self.mem.observe("INFECTION_ATTEMPT", md, "courier", "analyst")
        rng = random.Random(0)
        d = self.mem.decide_c2(
            stage="PRE_BEACON",
            metadata={**md, "topology_hop": 2, "src": "courier"},
            rng=rng,
            base_block_p=0.01,
            agent_id="guardian",
        )
        self.assertGreater(d.effective_block_p, 0.35)
        self.assertTrue(d.should_block or d.outcome.startswith("DEFENSE_"))

    def test_cause_metadata_keys(self) -> None:
        md = {
            "payload_hash": "p1",
            "strain_id": "s1",
            "attack_type": "A",
            "strategy_family": "DATA_EXFIL",
            "topology_hop": 3,
        }
        self.mem.observe("INFECTION_ATTEMPT", md, "src1", "dst1")
        rng = random.Random(42)
        d = self.mem.decide_c2(
            stage="EXFIL",
            metadata={**md, "exfil_type": "agent_state", "src": "src1"},
            rng=rng,
            base_block_p=0.1,
            agent_id="agent-a",
        )
        cm = d.cause_metadata()
        self.assertIn("friction_policy_match", cm)
        self.assertIn("friction_exfil_signature", cm)
        self.assertIn("friction_anomaly_score", cm)


class C2FrictionIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._out: list[dict] = []

        async def emit(ev: dict) -> None:
            self._out.append(dict(ev))

        os.environ["DEFENSE_FRICTION_ENABLED"] = "1"
        os.environ["C2_ENABLED"] = "1"
        os.environ["C2_BEACON_BLOCK_PROB"] = "0"
        os.environ["DEFENSE_FRICTION_SIGHTING_WEIGHT"] = "0.25"
        os.environ["DEFENSE_FRICTION_ANOMALY_TO_BLOCK"] = "0.95"
        os.environ["DEFENSE_FRICTION_DEFER_MARGIN"] = "0"
        os.environ["DEFENSE_FALSE_POSITIVE_RATE"] = "0"
        os.environ["DEFENSE_DELAYED_DETECTION_PROB"] = "0"
        self._engine = C2Engine(emit_event=emit)

    async def asyncTearDown(self) -> None:
        for k in (
            "DEFENSE_FRICTION_ENABLED",
            "C2_BEACON_BLOCK_PROB",
            "DEFENSE_FRICTION_SIGHTING_WEIGHT",
            "DEFENSE_FRICTION_ANOMALY_TO_BLOCK",
            "DEFENSE_FRICTION_DEFER_MARGIN",
            "DEFENSE_FALSE_POSITIVE_RATE",
            "DEFENSE_DELAYED_DETECTION_PROB",
        ):
            os.environ.pop(k, None)

    async def test_beacon_can_block_before_channel_despite_zero_base_prob(self) -> None:
        md = {
            "campaign_id": "cmp_fr",
            "injection_id": "inj_fr",
            "payload_hash": "hash_fr",
            "strain_id": "st_fr",
            "attack_type": "PI",
            "strategy_family": "JAILBREAK_ESCALATION",
            "payload_preview": "x",
        }
        for _ in range(30):
            await self._engine.observe_event(
                {
                    "event": "INFECTION_ATTEMPT",
                    "src": "courier",
                    "dst": "analyst",
                    "metadata": md,
                }
            )
        await self._engine.on_infection_successful(
            {
                "event": "INFECTION_SUCCESSFUL",
                "src": "analyst",
                "dst": "guardian",
                "metadata": md,
            }
        )
        self._engine._pending_beacons.clear()
        self._engine._pending_beacons["guardian"] = 0.0
        await self._engine._execute_beacon("guardian")
        types = [x.get("event") for x in self._out]
        self.assertIn("BEACON_BLOCKED", types, f"expected beacon block before C2 channel; got {types[:12]}")
        self.assertNotIn("C2_CHANNEL_ESTABLISHED", types)


if __name__ == "__main__":
    unittest.main()
