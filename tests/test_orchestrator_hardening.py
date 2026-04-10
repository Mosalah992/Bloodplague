import asyncio
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path

from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[1]
ORCHESTRATOR_DIR = ROOT / "orchestrator"
AGENTS_DIR = ROOT / "agents"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ORCHESTRATOR_DIR))
sys.path.insert(0, str(AGENTS_DIR))


def _load_main_module():
    fake_logger = types.ModuleType("logger")
    fake_siem = types.ModuleType("siem")
    fake_c2 = types.ModuleType("c2")

    class DummyEventLogger:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def close(self) -> None:
            pass

    class DummySIEMIndexer:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def import_jsonl(self, *args, **kwargs):
            return {"status": "ok"}

        async def import_redis_stream(self, *args, **kwargs):
            return {"status": "ok"}

        def sync_primary_events(self, *args, **kwargs):
            return {"status": "ok"}

    class DummyC2Engine:
        def __init__(self, emit_event) -> None:
            self.emit_event = emit_event

        def reset(self) -> None:
            pass

    fake_logger.EventLogger = DummyEventLogger
    fake_siem.SIEMIndexer = DummySIEMIndexer
    fake_c2.C2Engine = DummyC2Engine

    saved = {name: sys.modules.get(name) for name in ("logger", "siem", "c2")}
    sys.modules["logger"] = fake_logger
    sys.modules["siem"] = fake_siem
    sys.modules["c2"] = fake_c2

    try:
        spec = importlib.util.spec_from_file_location("_test_main_hardening", ORCHESTRATOR_DIR / "main.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


class OrchestratorHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.main = _load_main_module()

    def test_validated_agent_id_rejects_unknown_values(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            self.main._validated_agent_id("../../../weird")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_validated_import_path_rejects_escape_outside_allowed_roots(self) -> None:
        allowed_root = ROOT / "logs"
        blocked_file = ROOT / "README.md"

        original_roots = os.environ.get("SIEM_IMPORT_ROOTS")
        os.environ["SIEM_IMPORT_ROOTS"] = str(allowed_root)
        try:
            with self.assertRaises(HTTPException) as ctx:
                self.main._validated_import_path(str(blocked_file))
        finally:
            if original_roots is None:
                os.environ.pop("SIEM_IMPORT_ROOTS", None)
            else:
                os.environ["SIEM_IMPORT_ROOTS"] = original_roots

        self.assertEqual(ctx.exception.status_code, 400)

    def test_api_import_preserves_validation_http_status(self) -> None:
        allowed_root = ROOT / "logs"
        blocked_file = ROOT / "README.md"

        original_roots = os.environ.get("SIEM_IMPORT_ROOTS")
        os.environ["SIEM_IMPORT_ROOTS"] = str(allowed_root)
        try:
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(
                    self.main.api_import(
                        self.main.ImportPayload(source="jsonl", path=str(blocked_file))
                    )
                )
        finally:
            if original_roots is None:
                os.environ.pop("SIEM_IMPORT_ROOTS", None)
            else:
                os.environ["SIEM_IMPORT_ROOTS"] = original_roots

        self.assertEqual(ctx.exception.status_code, 400)

    def test_infected_agent_creates_unsuppressed_siem_alert(self) -> None:
        alerts = self.main._build_infection_state_alerts(
            {
                "analyst-1": {
                    "id": "analyst-1",
                    "state": "infected",
                    "epidemic_state": "I_r",
                    "epidemic_last_updated": 10.0,
                }
            },
            [],
        )

        self.assertEqual(alerts["active_count"], 1)
        self.assertEqual(alerts["suppressed_count"], 0)
        self.assertEqual(alerts["items"][0]["event"], "SIEM_INFECTION_STATE_ALERT")
        self.assertFalse(alerts["items"][0]["suppressed"])

    def test_explicit_infection_alert_suppression_hides_state_alert(self) -> None:
        alerts = self.main._build_infection_state_alerts(
            {
                "analyst-1": {
                    "id": "analyst-1",
                    "state": "infected",
                    "epidemic_state": "I_r",
                    "epidemic_last_updated": 10.0,
                }
            },
            [
                {
                    "event": "SIEM_ALERT_SUPPRESSED",
                    "ts": 11.0,
                    "src": "guardian",
                    "dst": "analyst-1",
                    "metadata": {"alert_type": "infection_state_alert", "reason": "operator hold"},
                }
            ],
        )

        self.assertEqual(alerts["active_count"], 0)
        self.assertEqual(alerts["suppressed_count"], 1)
        self.assertTrue(alerts["items"][0]["suppressed"])

    def test_propagation_suppression_does_not_hide_infection_state_alert(self) -> None:
        alerts = self.main._build_infection_state_alerts(
            {
                "analyst-1": {
                    "id": "analyst-1",
                    "state": "infected",
                    "epidemic_state": "I_r",
                    "epidemic_last_updated": 10.0,
                }
            },
            [
                {
                    "event": "PROPAGATION_SUPPRESSED",
                    "ts": 11.0,
                    "src": "analyst-1",
                    "dst": "guardian",
                    "metadata": {"suppression_s": 60},
                }
            ],
        )

        self.assertEqual(alerts["active_count"], 1)
        self.assertEqual(alerts["suppressed_count"], 0)

    def test_infection_attempt_does_not_mark_destination_infected(self) -> None:
        agents = self.main._derive_agents(
            [
                {
                    "event": "INFECTION_ATTEMPT",
                    "src": "analyst-2",
                    "dst": "guardian",
                    "state_after": "infected",
                    "ts": 10.0,
                }
            ]
        )

        self.assertEqual(agents["guardian"]["state"], "healthy")
        self.assertEqual(agents["guardian"]["last_event"], "INFECTION_ATTEMPT")

    def test_infection_success_marks_destination_infected(self) -> None:
        agents = self.main._derive_agents(
            [
                {
                    "event": "INFECTION_SUCCESSFUL",
                    "src": "analyst-2",
                    "dst": "analyst-1",
                    "state_after": "infected",
                    "ts": 10.0,
                }
            ]
        )

        self.assertEqual(agents["analyst-1"]["state"], "infected")

    def test_dashboard_state_uses_event_fallback_after_tracker_restart(self) -> None:
        state, source = self.main._resolve_dashboard_epidemic_state("S", "infected")

        self.assertEqual(state, "I_r")
        self.assertEqual(source, "events_table_fallback")

    def test_degraded_live_payload_keeps_infection_state_alerts(self) -> None:
        self.main.epidemic_tracker.reset()
        self.main.epidemic_tracker.agent_states["analyst-1"]["epidemic_state"] = "I_r"

        payload = self.main._degraded_live_payload(42, Exception("database is locked"))

        self.assertTrue(payload["live_degraded"])
        self.assertEqual(payload["latest_id"], 42)
        self.assertGreaterEqual(payload["alerts"]["active_count"], 1)
        self.assertGreaterEqual(payload["metrics"]["infection_state_alerts"], 1)


if __name__ == "__main__":
    unittest.main()
