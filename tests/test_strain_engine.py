import json
import os
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

from experiment_config.strain_runtime import reset_strain_runtime_config_for_tests  # noqa: E402
from strain_engine import StrainEngine  # noqa: E402
from strain_store import StrainRecord, StrainStore  # noqa: E402


def _enriched_like(
    *,
    event: str,
    event_id: str = "run_t:1-0",
    payload_hash: str = "",
    parent_payload_hash: str = "",
    mutation_type: str = "",
    attack_type: str = "PI-DIRECT",
    injection_id: str = "inj_a",
    campaign_id: str = "cmp_a",
) -> dict:
    meta: dict = {
        "injection_id": injection_id,
        "campaign_id": campaign_id,
    }
    if payload_hash:
        meta["payload_hash"] = payload_hash
    if parent_payload_hash:
        meta["parent_payload_hash"] = parent_payload_hash
    if mutation_type:
        meta["mutation_type"] = mutation_type
    return {
        "ts": 1700001000.0,
        "event": event,
        "event_type": event,
        "event_id": event_id,
        "run_id": "run_t",
        "src": "courier-1",
        "dst": "analyst-1",
        "attack_type": attack_type,
        "injection_id": injection_id,
        "campaign_id": campaign_id,
        "correlation": {"trace_id": f"{campaign_id}:{injection_id}"},
        "metadata": meta,
    }


class StrainEngineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        reset_strain_runtime_config_for_tests()
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(self._tmpdir.name)
        self._db = tmp / "s.db"
        self._fb = tmp / "s_fallback.jsonl"
        self._emitted: list[dict] = []
        self._store = StrainStore(str(self._db), str(self._fb))

        async def emit(d: dict) -> None:
            self._emitted.append(dict(d))

        self._engine = StrainEngine(self._store, run_id="run_t", emit_to_stream=emit)

    async def asyncTearDown(self) -> None:
        self._store.close()
        self._tmpdir.cleanup()
        reset_strain_runtime_config_for_tests()

    async def test_creates_strain_and_injects_metadata(self) -> None:
        ev = _enriched_like(event="INFECTION_ATTEMPT", payload_hash="hash_a")
        await self._engine.observe_enriched(ev)
        self.assertEqual(ev["strain_id"][:3], "st_")
        self.assertEqual(ev["metadata"]["strain_id"], ev["strain_id"])
        kinds = [x.get("event") for x in self._emitted]
        self.assertIn("STRAIN_CREATED", kinds)
        rec = self._store.get_by_payload_hash("hash_a")
        self.assertIsNotNone(rec)
        assert rec is not None
        self.assertEqual(rec.payload_hash, "hash_a")

    async def test_child_strain_emits_mutated(self) -> None:
        parent_ev = _enriched_like(
            event="INFECTION_ATTEMPT",
            event_id="run_t:1-0",
            payload_hash="hash_p",
        )
        await self._engine.observe_enriched(parent_ev)
        child_ev = _enriched_like(
            event="INFECTION_ATTEMPT",
            event_id="run_t:2-0",
            payload_hash="hash_c",
            parent_payload_hash="hash_p",
            mutation_type="context_wrap",
        )
        await self._engine.observe_enriched(child_ev)
        kinds = [x.get("event") for x in self._emitted]
        self.assertIn("STRAIN_MUTATED", kinds)
        rec_c = self._store.get_by_payload_hash("hash_c")
        self.assertIsNotNone(rec_c)
        assert rec_c is not None
        self.assertEqual(rec_c.generation, 1)
        self.assertIn("context_wrap", rec_c.mutation_lineage)

    async def test_infection_success_increments_and_skips_strain_events(self) -> None:
        ev = _enriched_like(event="INFECTION_ATTEMPT", payload_hash="hash_s")
        await self._engine.observe_enriched(ev)
        sid = ev["strain_id"]
        self._emitted.clear()
        ev2 = _enriched_like(
            event="INFECTION_SUCCESSFUL",
            event_id="run_t:3-0",
            payload_hash="hash_s",
        )
        ev2["strain_id"] = sid
        ev2["metadata"]["strain_id"] = sid
        await self._engine.observe_enriched(ev2)
        rec = self._store.get_by_payload_hash("hash_s")
        self.assertIsNotNone(rec)
        assert rec is not None
        self.assertGreaterEqual(rec.success_count, 1)
        self.assertFalse(any(e.get("event") == "STRAIN_CREATED" for e in self._emitted))

    async def test_extinction_emits_extinct(self) -> None:
        os.environ["STRAIN_EXTINCTION_ENABLED"] = "1"
        os.environ["STRAIN_EXTINCTION_BLOCK_MIN"] = "3"
        os.environ["STRAIN_EXTINCTION_SUCCESS_MAX"] = "0"
        try:
            reset_strain_runtime_config_for_tests()
            emitted: list[dict] = []

            async def cap(d: dict) -> None:
                emitted.append(dict(d))

            engine = StrainEngine(self._store, run_id="run_t", emit_to_stream=cap)
            ev = _enriched_like(event="INFECTION_ATTEMPT", payload_hash="hash_x")
            await engine.observe_enriched(ev)
            for i in range(4):
                e = _enriched_like(
                    event="INFECTION_BLOCKED",
                    event_id=f"run_t:10{i}-0",
                    payload_hash="hash_x",
                )
                e["strain_id"] = ev["strain_id"]
                e["metadata"]["strain_id"] = ev["strain_id"]
                await engine.observe_enriched(e)
            kinds = [x.get("event") for x in emitted]
            self.assertIn("STRAIN_EXTINCT", kinds)
            rec = self._store.get_by_payload_hash("hash_x")
            self.assertIsNotNone(rec)
            assert rec is not None
            self.assertTrue(rec.extinct)
        finally:
            os.environ.pop("STRAIN_EXTINCTION_ENABLED", None)
            os.environ.pop("STRAIN_EXTINCTION_BLOCK_MIN", None)
            os.environ.pop("STRAIN_EXTINCTION_SUCCESS_MAX", None)
            reset_strain_runtime_config_for_tests()

    async def test_fitness_floor_extinction(self) -> None:
        os.environ["STRAIN_EXTINCTION_FITNESS_ENABLED"] = "1"
        os.environ["STRAIN_EXTINCTION_FITNESS_BELOW"] = "0.95"
        os.environ["STRAIN_EXTINCTION_FITNESS_MIN_TOUCHES"] = "4"
        try:
            reset_strain_runtime_config_for_tests()
            emitted: list[dict] = []

            async def cap(d: dict) -> None:
                emitted.append(dict(d))

            engine = StrainEngine(self._store, run_id="run_t", emit_to_stream=cap)
            ev = _enriched_like(event="INFECTION_ATTEMPT", payload_hash="hash_fit")
            await engine.observe_enriched(ev)
            sid = ev["strain_id"]
            for i in range(5):
                e = _enriched_like(
                    event="INFECTION_BLOCKED",
                    event_id=f"run_t:fit{i}-0",
                    payload_hash="hash_fit",
                )
                e["strain_id"] = sid
                e["metadata"]["strain_id"] = sid
                await engine.observe_enriched(e)
            kinds = [x.get("event") for x in emitted]
            self.assertIn("STRAIN_EXTINCT", kinds)
            reasons = [
                x.get("metadata", {}).get("extinction_reason")
                for x in emitted
                if x.get("event") == "STRAIN_EXTINCT"
            ]
            self.assertIn("fitness_floor", reasons)
        finally:
            os.environ.pop("STRAIN_EXTINCTION_FITNESS_ENABLED", None)
            os.environ.pop("STRAIN_EXTINCTION_FITNESS_BELOW", None)
            os.environ.pop("STRAIN_EXTINCTION_FITNESS_MIN_TOUCHES", None)
            reset_strain_runtime_config_for_tests()

    async def test_branching_prompt_once(self) -> None:
        os.environ["STRAIN_BRANCH_MIN_SUCCESSES"] = "2"
        os.environ["STRAIN_BRANCH_MIN_BLOCKS"] = "2"
        os.environ["STRAIN_BRANCH_DETECT_THRESHOLD"] = "0.3"
        try:
            reset_strain_runtime_config_for_tests()
            emitted: list[dict] = []

            async def cap(d: dict) -> None:
                emitted.append(dict(d))

            engine = StrainEngine(self._store, run_id="run_t", emit_to_stream=cap)
            ev = _enriched_like(event="INFECTION_ATTEMPT", payload_hash="hash_br")
            await engine.observe_enriched(ev)
            sid = ev["strain_id"]
            for _ in range(2):
                s = _enriched_like(
                    event="INFECTION_SUCCESSFUL",
                    event_id=f"run_t:brs{_}-0",
                    payload_hash="hash_br",
                )
                s["strain_id"] = sid
                s["metadata"]["strain_id"] = sid
                await engine.observe_enriched(s)
            for _ in range(3):
                b = _enriched_like(
                    event="INFECTION_BLOCKED",
                    event_id=f"run_t:brb{_}-0",
                    payload_hash="hash_br",
                )
                b["strain_id"] = sid
                b["metadata"]["strain_id"] = sid
                await engine.observe_enriched(b)
            kinds = [x.get("event") for x in emitted]
            self.assertIn("STRAIN_BRANCHING_PROMPTED", kinds)
            self.assertLessEqual(kinds.count("STRAIN_BRANCHING_PROMPTED"), 1)
        finally:
            os.environ.pop("STRAIN_BRANCH_MIN_SUCCESSES", None)
            os.environ.pop("STRAIN_BRANCH_MIN_BLOCKS", None)
            os.environ.pop("STRAIN_BRANCH_DETECT_THRESHOLD", None)
            reset_strain_runtime_config_for_tests()

    async def test_c2_task_increments_counters(self) -> None:
        ev = _enriched_like(event="INFECTION_ATTEMPT", payload_hash="hash_task")
        await self._engine.observe_enriched(ev)
        sid = ev["strain_id"]
        b = _enriched_like(
            event="INFECTION_BLOCKED",
            event_id="run_t:tsk0-0",
            payload_hash="hash_task",
        )
        b["strain_id"] = sid
        b["metadata"]["strain_id"] = sid
        await self._engine.observe_enriched(b)
        t = _enriched_like(
            event="C2_TASK",
            event_id="run_t:tsk1-0",
            payload_hash="hash_task",
        )
        t["strain_id"] = sid
        t["metadata"]["strain_id"] = sid
        t["metadata"]["task_result"] = "executed"
        await self._engine.observe_enriched(t)
        rec = self._store.get_by_payload_hash("hash_task")
        self.assertIsNotNone(rec)
        assert rec is not None
        self.assertGreaterEqual(rec.task_success_count, 1)
        self.assertGreaterEqual(rec.survival_wins_after_detection, 1)


class StrainStoreDegradedTests(unittest.TestCase):
    def test_degraded_jsonl_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            fb = tmp / "fb.jsonl"
            store = StrainStore(str(tmp / "s.db"), str(fb))
            store._enter_degraded("manual_test")
            r = StrainRecord(
                strain_id="st_test1",
                payload_hash="ph1",
                creation_ts=1.0,
                last_seen_ts=1.0,
            )
            store.upsert_strain(r)
            got = store.get_by_payload_hash("ph1")
            self.assertIsNotNone(got)
            assert got is not None
            self.assertEqual(got.strain_id, "st_test1")


if __name__ == "__main__":
    unittest.main()
