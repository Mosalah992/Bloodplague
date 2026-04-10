"""Patch 8: telemetry DB integrity, SIEM degraded mode, logger JSONL fallback."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "orchestrator"))

from orchestrator.logger import EventLogger  # noqa: E402
from orchestrator.siem import SIEMIndexer  # noqa: E402
from orchestrator.telemetry_integrity import (  # noqa: E402
    summarize_jsonl_run,
    verify_sqlite_integrity,
)


class TelemetryIntegrityTests(unittest.TestCase):
    def test_verify_missing_db_skipped_ok(self) -> None:
        missing = str(ROOT / "nonexistent" / "nope.db")
        r = verify_sqlite_integrity(missing)
        self.assertTrue(r.get("ok"))
        self.assertTrue(r.get("skipped"))

    def test_siem_search_degraded_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            db = t / "siem.db"
            jl = t / "e.jsonl"
            jl.write_text("", encoding="utf-8")
            src = t / "epi.db"
            idx = SIEMIndexer(str(db), str(jl), source_db_path=str(src))
            idx._set_index_degraded("test_degraded")
            out = idx.search("event=INFECTION_ATTEMPT")
            self.assertTrue(out.get("index_degraded"))
            self.assertEqual(out.get("total"), 0)
            self.assertTrue(any("DEGRADED" in (w or "") for w in (out.get("warnings") or [])))

    def test_siem_sync_skipped_when_degraded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            db = t / "siem.db"
            jl = t / "e.jsonl"
            jl.write_text("", encoding="utf-8")
            idx = SIEMIndexer(str(db), str(jl), source_db_path=str(t / "epi.db"))
            idx._set_index_degraded("x")
            r = idx.sync_primary_events(force=True)
            self.assertEqual(r.get("status"), "skipped_index_degraded")

    def test_logger_jsonl_only_when_integrity_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            db = t / "e.db"
            jl = t / "l.jsonl"
            fake = {"ok": False, "detail": "simulated_corruption"}
            with patch("orchestrator.logger.verify_sqlite_integrity", return_value=fake):
                log = EventLogger(str(db), str(jl))
            self.assertTrue(log._degraded_jsonl_only)
            log.log_event(
                {
                    "event": "TEST_EVT",
                    "src": "a",
                    "dst": "b",
                    "ts": "2026-01-01T00:00:00+00:00",
                    "metadata": {},
                }
            )
            text = jl.read_text(encoding="utf-8")
            self.assertIn("TEST_EVT", text)
            self.assertIn("TELEMETRY_LOGGER_DEGRADED", text)

    def test_summarize_jsonl_run_minimal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t / "progress.json").write_text(json.dumps({"minute": 1}), encoding="utf-8")
            (t / "minute_summaries.jsonl").write_text(
                json.dumps({"top_payload_families": [{"family_id": "pfam_x", "count": 2}]}) + "\n",
                encoding="utf-8",
            )
            s = summarize_jsonl_run(str(t))
            self.assertEqual(s.get("minute_sample_count"), 1)
            self.assertTrue(s.get("top_payload_families_rollup"))


if __name__ == "__main__":
    unittest.main()
