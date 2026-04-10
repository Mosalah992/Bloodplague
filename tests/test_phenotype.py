import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))

from shared.phenotype import load_agent_phenotype  # noqa: E402


class PhenotypeTests(unittest.TestCase):
    def test_legacy_alias_loads_role_defaults(self) -> None:
        phenotype = load_agent_phenotype("agent-c", "courier", "lightweight")
        self.assertEqual(phenotype.role, "courier")
        self.assertEqual(phenotype.cognition_tier, "lightweight")
        self.assertAlmostEqual(phenotype.defense_strength, 0.15, places=3)

    def test_env_overrides_are_applied(self) -> None:
        original = os.environ.get("TRUST_FACTOR")
        os.environ["TRUST_FACTOR"] = "0.42"
        try:
            phenotype = load_agent_phenotype("analyst-2", "analyst", "hybrid")
        finally:
            if original is None:
                os.environ.pop("TRUST_FACTOR", None)
            else:
                os.environ["TRUST_FACTOR"] = original
        self.assertAlmostEqual(phenotype.trust_factor, 0.42, places=3)
        self.assertEqual(phenotype.role, "analyst")
