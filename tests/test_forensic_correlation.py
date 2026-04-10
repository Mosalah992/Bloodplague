import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ORCH = ROOT / "orchestrator"
AGENTS = ROOT / "agents"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ORCH))
sys.path.insert(0, str(AGENTS))

from orchestrator.logger import EventLogger  # noqa: E402
from forensic_enrichment import (  # noqa: E402
    TRIGGER_EVENT_ID,
    apply_c2_stream_correlation,
    enrich_forensic_event,
    merge_metadata_search_keys,
    new_local_event_id,
    parse_stream_message,
)


class ForensicEnrichmentTests(unittest.TestCase):
    def test_enrich_event_id_and_event_type(self) -> None:
        raw = {
            "ts": 1700000000.0,
            "event": "INFECTION_ATTEMPT",
            "src": "agent-c",
            "dst": "agent-b",
            "metadata": json.dumps(
                {
                    "campaign_id": "cmp_1",
                    "injection_id": "inj_1",
                    "attempt_id": "att_9",
                    "payload_hash": "abc123",
                }
            ),
        }
        parsed = parse_stream_message(raw)
        out = enrich_forensic_event(
            parsed, run_id="run_test", stream_message_id="1700000001000-0"
        )
        self.assertEqual(out["event_id"], "run_test:1700000001000-0")
        self.assertEqual(out["event_type"], "INFECTION_ATTEMPT")
        self.assertEqual(out["event"], "INFECTION_ATTEMPT")
        self.assertEqual(out["run_id"], "run_test")
        self.assertEqual(out["agent_id"], "agent-c")
        self.assertEqual(out["attack_id"], "att_9")
        self.assertEqual(out["campaign_id"], "cmp_1")
        self.assertEqual(out["injection_id"], "inj_1")
        self.assertEqual(out["payload_hash"], "abc123")
        self.assertIn("correlation", out)
        self.assertEqual(out["correlation"]["schema_version"], 1)
        self.assertEqual(out["correlation"]["trace_id"], "cmp_1:inj_1")

    def test_parse_stream_message_coerces_ts(self) -> None:
        raw = {"ts": "1700000001.5", "event": "HEARTBEAT", "metadata": "{}"}
        out = parse_stream_message(raw)
        self.assertEqual(out["ts"], 1700000001.5)
        self.assertEqual(out["metadata"], {})

    def test_merge_metadata_search_keys(self) -> None:
        event = {
            "run_id": "r1",
            "event_id": "r1:1-0",
            "parent_event_id": "r1:0-0",
            "attack_id": "a1",
            "metadata": {"campaign_id": "c1"},
            "correlation": {"stream_message_id": "1-0", "trace_id": "t1"},
        }
        merge_metadata_search_keys(event)
        meta = event["metadata"]
        self.assertEqual(meta["run_id"], "r1")
        self.assertEqual(meta["parent_event_id"], "r1:0-0")
        self.assertEqual(meta["attack_id"], "a1")
        self.assertEqual(meta["event_id"], "r1:1-0")
        self.assertEqual(meta["stream_message_id"], "1-0")
        self.assertEqual(meta["trace_id"], "t1")

    def test_c2_parent_lineage_via_context(self) -> None:
        parent = "run_x:999-0"
        token = TRIGGER_EVENT_ID.set(parent)
        try:
            c2_payload = {
                "event": "C2_BEACON",
                "ts": str(1700000002.0),
                "src": "c2_engine",
                "dst": "agent-b",
                "metadata": json.dumps({"campaign_id": "cmp_z"}),
            }
            out = apply_c2_stream_correlation(c2_payload, run_id="run_x")
            self.assertEqual(out["parent_event_id"], parent)
            self.assertEqual(out["run_id"], "run_x")
            self.assertEqual(out["correlation"]["parent_event_id"], parent)
            self.assertEqual(out["metadata"].get("parent_event_id"), parent)
        finally:
            TRIGGER_EVENT_ID.reset(token)

    def test_kill_chain_stage_populated_for_infection_success(self) -> None:
        raw = {
            "ts": 1700000003.0,
            "event": "INFECTION_SUCCESSFUL",
            "src": "agent-c",
            "dst": "agent-b",
            "metadata": json.dumps({"campaign_id": "c"}),
        }
        parsed = parse_stream_message(raw)
        out = enrich_forensic_event(parsed, run_id="run_kc", stream_message_id="3-0")
        self.assertTrue(str(out.get("kill_chain_stage", "")).strip())

    def test_jsonl_traceability_grouping_and_parent_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            db_path = tmp / "e.db"
            jsonl_path = tmp / "e.jsonl"
            logger = EventLogger(str(db_path), str(jsonl_path))
            try:
                parent = enrich_forensic_event(
                    parse_stream_message(
                        {
                            "ts": 1700000100.0,
                            "event": "INFECTION_SUCCESSFUL",
                            "src": "agent-c",
                            "dst": "agent-b",
                            "metadata": json.dumps(
                                {
                                    "injection_id": "inj_chain",
                                    "payload_hash": "phash1",
                                    "strain_id": "st1",
                                }
                            ),
                        }
                    ),
                    run_id="run_j",
                    stream_message_id="100-0",
                )
                logger.log_event(parent)

                tok = TRIGGER_EVENT_ID.set(parent["event_id"])
                try:
                    c2_out = apply_c2_stream_correlation(
                        {
                            "event": "C2_BEACON",
                            "ts": str(1700000101.0),
                            "src": "c2_engine",
                            "dst": "agent-b",
                            "metadata": json.dumps({"injection_id": "inj_chain"}),
                        },
                        run_id="run_j",
                    )
                finally:
                    TRIGGER_EVENT_ID.reset(tok)
                # Simulate re-ingest after Redis round-trip (metadata string, flat fields)
                child_roundtrip = {
                    "ts": str(c2_out["ts"]),
                    "event": c2_out["event"],
                    "src": c2_out["src"],
                    "dst": c2_out["dst"],
                    "run_id": c2_out["run_id"],
                    "parent_event_id": c2_out["parent_event_id"],
                    "metadata": json.dumps(c2_out["metadata"])
                    if isinstance(c2_out["metadata"], dict)
                    else c2_out["metadata"],
                    "correlation": json.dumps(c2_out["correlation"])
                    if isinstance(c2_out["correlation"], dict)
                    else c2_out["correlation"],
                }
                child_parsed = parse_stream_message(child_roundtrip)
                child_enriched = enrich_forensic_event(
                    child_parsed, run_id="run_j", stream_message_id="101-0"
                )
                logger.log_event(child_enriched)
            finally:
                logger.close()

            lines = jsonl_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)
            row_parent = json.loads(lines[0])
            row_child = json.loads(lines[1])
            self.assertIn("logger_ts", row_parent)
            self.assertEqual(row_parent["metadata"].get("payload_hash"), "phash1")
            self.assertEqual(row_parent["metadata"].get("strain_id"), "st1")

            by_hash: dict[str, list[dict]] = {}
            for line in lines:
                r = json.loads(line)
                h = str(r.get("payload_hash") or r.get("metadata", {}).get("payload_hash") or "")
                if h:
                    by_hash.setdefault(h, []).append(r)
            self.assertIn("phash1", by_hash)

            self.assertEqual(row_child.get("parent_event_id"), row_parent["event_id"])

    def test_new_local_event_id_format(self) -> None:
        eid = new_local_event_id("run_z")
        self.assertTrue(eid.startswith("run_z:local-"))
        self.assertEqual(len(eid), len("run_z:local-") + 32)


if __name__ == "__main__":
    unittest.main()
