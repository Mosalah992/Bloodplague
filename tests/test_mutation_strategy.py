import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))

from shared.mutation_strategy import (  # noqa: E402
    PRIMARY_STRATEGIES,
    TEMPLATE_FALLBACK,
    apply_structural_mutation,
    build_mutation_candidate_list,
    canonical_mutation_name,
    crowding_penalty,
    default_mutation_profile,
    fallback_budget_allows,
    fallback_max_ratio,
    payload_fingerprint,
    token_jaccard,
)


class MutationStrategyTests(unittest.TestCase):
    def test_canonical_aliases(self) -> None:
        self.assertEqual(canonical_mutation_name("reframe"), "instruction_reversal")
        self.assertEqual(canonical_mutation_name("encoding"), "chain_obfuscation")

    def test_build_candidates_contains_primaries(self) -> None:
        strat = {"preferred_mutations": ["reframe", "context_wrap"]}
        c = build_mutation_candidate_list(strat)
        self.assertIn("context_wrap", c)
        self.assertIn("instruction_reversal", c)

    def test_apply_structural_non_empty(self) -> None:
        p = "SIM_ATTACK[x]"
        for s in PRIMARY_STRATEGIES[:3]:
            out = apply_structural_mutation(
                p,
                s,
                relay_target="agt-2",
                strategy_family="DIRECT_OVERRIDE",
                technique="t1",
                objective="SPREAD_FAST",
            )
            self.assertIn(p, out or "")

    def test_fingerprint_stable(self) -> None:
        self.assertEqual(payload_fingerprint("  Hello   World "), payload_fingerprint("hello world"))

    def test_token_jaccard(self) -> None:
        self.assertGreater(token_jaccard("alpha beta gamma", "alpha beta delta"), 0.3)

    def test_fallback_budget(self) -> None:
        self.assertTrue(fallback_budget_allows([]))
        # window all fallback -> at ratio 1.0 should deny if max 0.3
        self.assertFalse(fallback_budget_allows([1, 1, 1, 1]))
        self.assertLess(fallback_max_ratio(), 1.0)

    def test_crowding_penalty(self) -> None:
        recent = ["context_wrap"] * 20
        self.assertGreaterEqual(crowding_penalty("context_wrap", recent), 0.0)

    def test_default_profile(self) -> None:
        d = default_mutation_profile("unknown_xyz")
        self.assertIn("retry_bias", d)

    def test_template_fallback_constant(self) -> None:
        self.assertEqual(TEMPLATE_FALLBACK, "template_fallback")


if __name__ == "__main__":
    unittest.main()
