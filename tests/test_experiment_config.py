"""
Centralized experiment config: env defaults, overrides, and test isolation resets.
"""

import os
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

from experiment_config.c2_runtime import build_c2_runtime_config  # noqa: E402
from experiment_config.exfil_operational_runtime import (  # noqa: E402
    get_exfil_operational_runtime_config,
    reset_exfil_operational_runtime_config_for_tests,
)
from experiment_config.strain_runtime import (  # noqa: E402
    get_strain_runtime_config,
    reset_strain_runtime_config_for_tests,
)
from shared.config import reset_shared_experiment_config_for_tests  # noqa: E402
from shared.config.mutation_runtime import (  # noqa: E402
    get_mutation_runtime_config,
    reset_mutation_runtime_config_for_tests,
)
from shared.mutation_strategy import diversity_window_size  # noqa: E402


class ExperimentConfigTests(unittest.TestCase):
    def tearDown(self) -> None:
        reset_shared_experiment_config_for_tests()
        reset_strain_runtime_config_for_tests()
        reset_exfil_operational_runtime_config_for_tests()

    def test_mutation_diversity_window_env_override(self) -> None:
        os.environ["MUTATION_DIVERSITY_WINDOW"] = "40"
        reset_mutation_runtime_config_for_tests()
        self.assertEqual(diversity_window_size(), max(8, 40))

    def test_strain_engine_enabled_default(self) -> None:
        reset_strain_runtime_config_for_tests()
        if "STRAIN_ENGINE_ENABLED" in os.environ:
            del os.environ["STRAIN_ENGINE_ENABLED"]
        reset_strain_runtime_config_for_tests()
        self.assertTrue(get_strain_runtime_config().engine_enabled)

    def test_exfil_operational_interception_base_override(self) -> None:
        os.environ["C2_EXFIL_INTERCEPTION_BASE"] = "0.12"
        reset_exfil_operational_runtime_config_for_tests()
        self.assertAlmostEqual(get_exfil_operational_runtime_config().interception_base, 0.12)

    def test_c2_build_matches_documented_defaults_shape(self) -> None:
        cfg = build_c2_runtime_config()
        self.assertGreater(cfg.beacon_op_success_p, 0.0)
        self.assertLess(cfg.beacon_op_success_p, 1.0)
        self.assertGreaterEqual(cfg.exfil_chunk_max_bytes, 256)


if __name__ == "__main__":
    unittest.main()
