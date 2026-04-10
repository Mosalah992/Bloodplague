"""Regression: soak-time failures from naive/aware datetime sorts and lineage cycles."""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT / "orchestrator"
sys.path.insert(0, str(ORCH))

from siem import SIEMIndexer, _parse_timestamp  # noqa: E402


class ParseTimestampTests(unittest.TestCase):
    def test_naive_iso_becomes_utc_aware(self) -> None:
        dt = _parse_timestamp("2024-06-01T12:00:00")
        self.assertIsNotNone(dt)
        assert dt is not None
        self.assertIsNotNone(dt.tzinfo)
        aware_max = datetime.max.replace(tzinfo=timezone.utc)
        self.assertIsInstance(sorted([dt, aware_max]), list)

    def test_z_suffix_is_aware(self) -> None:
        dt = _parse_timestamp("2024-06-01T12:00:00Z")
        self.assertIsNotNone(dt)
        assert dt is not None
        self.assertEqual(dt.tzinfo, timezone.utc)


class LineageCycleTests(unittest.TestCase):
    def test_cyclic_parent_map_does_not_recursion_error(self) -> None:
        idx = SIEMIndexer.__new__(SIEMIndexer)  # type: ignore[misc]
        # Minimal synthetic events: A -> B -> A (cycle)
        events = [
            {
                "payload_hash": "hA",
                "parent_payload_hash": "hB",
                "ts": "2024-01-01T00:00:01Z",
                "src": "a",
                "dst": "b",
                "event_id": "1",
            },
            {
                "payload_hash": "hB",
                "parent_payload_hash": "hA",
                "ts": "2024-01-01T00:00:02Z",
                "src": "b",
                "dst": "c",
                "event_id": "2",
            },
        ]
        model = SIEMIndexer._build_payload_lineage_model(idx, events)  # type: ignore[arg-type]
        lookup = model.get("node_lookup", {})
        self.assertIn("hA", lookup)
        self.assertIn("hB", lookup)
        self.assertGreaterEqual(int(lookup["hA"].get("lineage_depth", 0)), 0)


if __name__ == "__main__":
    unittest.main()
