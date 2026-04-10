"""
Patch 6: C2 operational friction helpers, kill-chain mapping, and stable exfil hashing.
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

from kill_chain import (  # noqa: E402
    BEACON_FILTER_EVENTS,
    EVENT_TO_KILL_CHAIN_STAGE,
    EXFIL_FILTER_EVENTS,
    TASKING_FILTER_EVENTS,
)
from c2_operational import (  # noqa: E402
    build_synthetic_exfil_body,
    classify_exfil_sensitivity,
    compute_chunk_plan,
    redact_exfil_preview,
    sha256_bytes,
)


class C2OperationalFrictionTests(unittest.TestCase):
    def test_kill_chain_maps_new_c2_exfil_events(self) -> None:
        self.assertEqual(EVENT_TO_KILL_CHAIN_STAGE["C2_BEACON_FAILED"], "BEACON")
        self.assertEqual(EVENT_TO_KILL_CHAIN_STAGE["C2_TASK_FAILED"], "TASKING")
        for ev in ("EXFIL_ATTEMPTED", "EXFIL_PARTIAL", "EXFIL_SUCCEEDED", "EXFIL_BLOCKED"):
            self.assertEqual(EVENT_TO_KILL_CHAIN_STAGE[ev], "EXFILTRATION")
        self.assertIn("C2_BEACON_FAILED", BEACON_FILTER_EVENTS)
        self.assertIn("EXFIL_ATTEMPTED", EXFIL_FILTER_EVENTS)
        self.assertIn("C2_TASK_FAILED", TASKING_FILTER_EVENTS)

    def test_exfil_content_hash_stable(self) -> None:
        prev = os.environ.get("C2_SEED", "42")
        os.environ["C2_SEED"] = "12345"
        try:
            body = build_synthetic_exfil_body(
                agent_id="agent-a",
                campaign_id="cmp1",
                injection_id="inj1",
                exfil_type="agent_state",
                seed_text="hello",
                target_size=512,
            )
            h1 = sha256_bytes(body)
            h2 = sha256_bytes(body)
            self.assertEqual(len(h1), 64)
            self.assertEqual(h1, h2)
            body2 = build_synthetic_exfil_body(
                agent_id="agent-a",
                campaign_id="cmp1",
                injection_id="inj1",
                exfil_type="agent_state",
                seed_text="hello",
                target_size=512,
            )
            self.assertEqual(h1, sha256_bytes(body2))
        finally:
            os.environ["C2_SEED"] = prev

    def test_chunk_plan_and_sensitivity(self) -> None:
        cs, cc = compute_chunk_plan(5000, 4096)
        self.assertEqual(cc, 2)
        self.assertEqual(cs, 4096)
        self.assertEqual(classify_exfil_sensitivity("agent_state", 500), "LOW")
        self.assertIn(classify_exfil_sensitivity("agent_state", 9000), ("HIGH", "CRITICAL"))

    def test_redact_exfil_preview_truncates(self) -> None:
        long = "a" * 200
        out = redact_exfil_preview(long, max_len=50, enabled=False)
        self.assertLessEqual(len(out), 50)
        self.assertTrue(out.endswith("..."))


if __name__ == "__main__":
    unittest.main()
