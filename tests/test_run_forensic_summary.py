"""Patch 9: deterministic forensic run summaries."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "orchestrator"))
sys.path.insert(0, str(ROOT / "agents"))
sys.path.insert(0, str(ROOT / "agents" / "shared"))

from run_forensic_summary import (  # noqa: E402
    build_forensic_summary,
    forensic_summary_to_markdown,
    normalize_event_line,
)


def _evt(name: str, *, dst: str = "b", metadata: dict | None = None) -> dict:
    return normalize_event_line(
        {"event": name, "src": "a", "dst": dst, "metadata": metadata or {}}
    )


class RunForensicSummaryTests(unittest.TestCase):
    def test_deterministic_json_sorting(self) -> None:
        events = [
            _evt("INFECTION_ATTEMPT", dst="agent-c"),
            _evt("INFECTION_BLOCKED", dst="agent-c"),
            _evt("INFECTION_SUCCESSFUL", dst="agent-b"),
            _evt("C2_BEACON_FAILED"),
            _evt("C2_BEACON"),
            _evt("EXFIL_ATTEMPTED"),
            _evt("EXFIL_PARTIAL"),
            _evt("EXFIL_BLOCKED"),
            _evt(
                "STRAIN_FITNESS_UPDATED",
                metadata={
                    "strain_id": "st_aaa",
                    "fitness_score": 0.71,
                    "novelty_score": 0.2,
                    "touch_count": 5,
                    "success_count": 2,
                    "block_count": 1,
                },
            ),
            _evt(
                "STRAIN_FITNESS_UPDATED",
                metadata={
                    "strain_id": "st_bbb",
                    "fitness_score": 0.55,
                    "touch_count": 3,
                },
            ),
            _evt("DEFENSE_RESULT_EVALUATED", metadata={"defense_result": "blocked", "friction_stage": "EXFIL"}),
            _evt("INFECTION_ATTEMPT", metadata={"mutation_type": "context_wrap", "payload_family_id": "pfam_x"}),
            _evt("INFECTION_ATTEMPT", metadata={"mutation_type": "role_shift", "payload_family_id": "pfam_x"}),
        ]
        a = json.dumps(build_forensic_summary(events), sort_keys=True)
        b = json.dumps(build_forensic_summary(events), sort_keys=True)
        self.assertEqual(a, b)

    def test_markdown_contains_sections(self) -> None:
        doc = build_forensic_summary([_evt("INFECTION_ATTEMPT"), _evt("INFECTION_SUCCESSFUL")])
        md = forensic_summary_to_markdown(doc)
        self.assertIn("## Infection outcomes", md)
        self.assertIn("## Forecast", md)

    def test_from_run_dir_missing_file(self) -> None:
        from run_forensic_summary import build_forensic_summary_from_run_dir  # noqa: E402

        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            doc = build_forensic_summary_from_run_dir(d)
            self.assertIn("error", doc)


if __name__ == "__main__":
    unittest.main()
