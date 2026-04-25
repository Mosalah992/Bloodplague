import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "agents"
SHARED = AGENTS / "shared"
for path in (str(AGENTS), str(SHARED)):
    if path not in sys.path:
        sys.path.insert(0, path)

from shared.attack_planner import KnowledgeAwareAttackPlanner  # noqa: E402
from shared.config.guardian_collapse import (  # noqa: E402
    get_guardian_collapse_config,
    reset_guardian_collapse_config_for_tests,
)
from shared.guardian_degradation import GuardianDegradationModel  # noqa: E402
from shared.llm_service import LLMService  # noqa: E402
from shared.llm_state_context import append_prompt_delta, compact_context  # noqa: E402
from shared.redteam_knowledge import RedTeamKnowledgeService  # noqa: E402


class GuardianCollapseUpgradeTests(unittest.TestCase):
    def tearDown(self) -> None:
        reset_guardian_collapse_config_for_tests()

    def test_collapse_lab_profile_uses_lower_thresholds_and_weighted_trust_pressure(self) -> None:
        with patch.dict(os.environ, {"BLOODPLAGUE_EXPERIMENT_PROFILE": "collapse_lab"}, clear=False):
            reset_guardian_collapse_config_for_tests()
            cfg = get_guardian_collapse_config()
            self.assertEqual(cfg.profile, "collapse_lab")
            self.assertLess(cfg.thresholds["G2_DEGRADED"], 0.38)
            self.assertGreater(cfg.pressure_weights["trust_abuse"], cfg.pressure_weights["hostile_exposure"])

            model = GuardianDegradationModel()
            model.add_pressure(0.03, source="analyst-1", pressure_type="trust_abuse")
            self.assertGreater(model.pressure, 0.03)

    def test_llm_threat_cache_key_includes_runtime_context(self) -> None:
        svc = LLMService(agent_id="guardian")
        payload = "SEND_TO: guardian\nCONTENT: test"
        key_a = svc._threat_cache_key(payload, "guardian_degradation_level=G0_HEALTHY")
        key_b = svc._threat_cache_key(payload, "guardian_degradation_level=G4_COMPROMISED")
        self.assertNotEqual(key_a, key_b)

    def test_prompt_delta_appends_llm_state_for_guardian(self) -> None:
        prompt = append_prompt_delta(
            "base prompt",
            agent_role="guardian",
            mode="G4_COMPROMISED",
            state={
                "guardian_degradation_level": "G4_COMPROMISED",
                "guardian_pressure": 0.82,
                "sender_credibility": 0.9,
            },
        )
        self.assertIn("RUNTIME SIMULATION STATE", prompt)
        self.assertIn("overloaded", prompt)
        self.assertIn("guardian_pressure=0.82", prompt)

    def test_compact_context_is_prompt_safe_single_line(self) -> None:
        ctx = compact_context({"belief_state": "line 1\nline 2", "score": 0.123456})
        self.assertNotIn("\n", ctx)
        self.assertIn("score=0.1235", ctx)

    def test_planner_accepts_guardian_degradation_objective_and_rewards_trust_feedback(self) -> None:
        knowledge = RedTeamKnowledgeService(str(ROOT / "agents" / "shared" / "data" / "attack_library.json"))
        planner = KnowledgeAwareAttackPlanner(
            agent_id="courier-1",
            knowledge_service=knowledge,
            seed=7,
            initial_objective="DEGRADE_GUARDIAN",
            lock_objective=True,
        )
        plan = planner.plan_attack(
            source_payload="seed",
            neighbors=["analyst-1"],
            current_hop_count=0,
            source_metadata={"mutation_v": 0},
        )
        attempt = planner.register_attempt("attempt-1", plan, injection_id="inj-1", reset_id="rst-1", epoch=1)
        baseline_key = (attempt["target"], attempt["strategy_family"])
        before = planner.memory.strategy_weights.get(baseline_key, 0.0)
        planner.evaluate_feedback(
            {
                "attempt_id": "attempt-1",
                "dst": attempt["target"],
                "outcome": "blocked",
                "strategy_family": attempt["strategy_family"],
                "mutation_type": attempt["mutation_type"],
                "attack_type": attempt["attack_type"],
                "trust_abuse": True,
                "guardian_pressure": 0.6,
                "quarantine_missed": True,
            }
        )
        after = planner.memory.strategy_weights[baseline_key]
        self.assertGreater(after, before)


if __name__ == "__main__":
    unittest.main()
