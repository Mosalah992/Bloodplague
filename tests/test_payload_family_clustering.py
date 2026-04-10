"""Patch 7: payload family clustering and novelty classes."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))

from shared.payload_family_clustering import (  # noqa: E402
    build_family_features,
    classify_novelty,
    dedupe_exact_payload,
    family_cluster_id,
    normalized_content_hash,
)
from shared.payload_utils import normalize_payload_text  # noqa: E402


class PayloadFamilyClusteringTests(unittest.TestCase):
    def test_cosmetic_number_change_same_family_different_hash(self) -> None:
        a = "SIM_ATTACK[PI|technique=t1|mutation=context_wrap|objective=SPREAD_FAST|nonce=111]"
        b = "SIM_ATTACK[PI|technique=t1|mutation=context_wrap|objective=SPREAD_FAST|nonce=222]"
        fa = build_family_features(a)
        fb = build_family_features(b)
        self.assertNotEqual(fa.norm_hash, fb.norm_hash)
        self.assertEqual(fa.family_id, fb.family_id)

    def test_classify_exact_and_novel(self) -> None:
        p = "SIM_ATTACK[X|technique=a|mutation=b|objective=SPREAD_FAST]"
        feat = build_family_features(p)
        seen = {feat.norm_hash}
        cls, score, _ = classify_novelty(
            feat,
            seen_norm_hashes=seen,
            recent_texts=[],
            family_emission_counts={},
        )
        self.assertEqual(cls, "exact_duplicate")
        self.assertEqual(score, 0.0)

        feat2 = build_family_features("totally different payload structure xyz 99999")
        cls2, score2, _ = classify_novelty(
            feat2,
            seen_norm_hashes=set(),
            recent_texts=[normalize_payload_text(p)],
            family_emission_counts={feat2.family_id: 1},
        )
        self.assertIn(cls2, ("near_duplicate", "same_family_new_mutation", "novel"))
        self.assertGreaterEqual(score2, 0.0)

    def test_dedupe_changes_hash(self) -> None:
        p = "hello world"
        h0 = normalized_content_hash(p)
        seen = {h0}
        class R:
            def randint(self, a, b):
                return 42

        q = dedupe_exact_payload(p, seen, R())
        self.assertNotEqual(normalized_content_hash(q), h0)
        self.assertIn("pdv=42", q)

    def test_family_cluster_id_stable(self) -> None:
        s = "a|b|c"
        self.assertTrue(family_cluster_id(s).startswith("pfam_"))


if __name__ == "__main__":
    unittest.main()
