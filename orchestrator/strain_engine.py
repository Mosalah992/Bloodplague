"""
Strain lifecycle: assign strain_id by payload_hash lineage, persist metrics, emit STRAIN_* events (Patch 2).
Patch 4: fitness under environmental pressure, extinction, branching prompts, inject attacker-facing hints.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Awaitable, Callable, Dict, Optional

from experiment_config.strain_runtime import StrainRuntimeConfig, get_strain_runtime_config
from forensic_enrichment import merge_metadata_search_keys
from strain_store import StrainRecord, StrainStore

_log = logging.getLogger("uvicorn.error")

EmitFn = Callable[[Dict[str, Any]], Awaitable[None]]

_BLOCK_EVENTS = frozenset(
    {"INFECTION_BLOCKED", "BEACON_BLOCKED", "TASK_BLOCKED", "EXFIL_BLOCKED"}
)


def _metadata_dict(event: Dict[str, Any]) -> Dict[str, Any]:
    metadata = event.get("metadata", {})
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    return metadata if isinstance(metadata, dict) else {}


def _compute_novelty(generation: int) -> float:
    return max(0.05, 1.0 / (1 + max(0, generation)))


class StrainEngine:
    def __init__(
        self,
        store: StrainStore,
        *,
        run_id: str,
        emit_to_stream: EmitFn,
    ) -> None:
        self._store = store
        self._run_id = run_id
        self._emit_to_stream = emit_to_stream
        cfg = get_strain_runtime_config()
        self._cfg: StrainRuntimeConfig = cfg
        self.enabled = cfg.engine_enabled
        self._extinction_enabled = cfg.extinction_enabled
        self._extinction_block_min = cfg.extinction_block_min
        self._extinction_success_max = cfg.extinction_success_max
        self._fitness_emit_delta = cfg.fitness_emit_delta
        self._extinction_fitness_enabled = cfg.extinction_fitness_enabled
        self._extinction_fitness_below = cfg.extinction_fitness_below
        self._extinction_fitness_min_touches = cfg.extinction_fitness_min_touches
        self._branching_event_enabled = cfg.branching_event_enabled
        # Environmental pressure keyed by originating_attack_type (similar-strain family proxy).
        self._similar_defense_pressure: Dict[str, float] = {}
        self._type_touch_totals: Dict[str, int] = {}
        self._global_type_touches: int = 0
        self._branch_prompted: set[str] = set()

    def reset_run(self, new_run_id: str) -> None:
        self._run_id = new_run_id
        self._similar_defense_pressure.clear()
        self._type_touch_totals.clear()
        self._global_type_touches = 0
        self._branch_prompted.clear()

    def health(self) -> Dict[str, Any]:
        return {"enabled": self.enabled, **self._store.health()}

    def _touch_strain(self, rec: StrainRecord) -> None:
        rec.touch_count += 1
        atk = (rec.originating_attack_type or "").strip() or "unknown"
        self._type_touch_totals[atk] = self._type_touch_totals.get(atk, 0) + 1
        self._global_type_touches += 1

    def _update_similar_defense_pressure_meta(self, rec: StrainRecord, event_name: str, meta: Dict[str, Any]) -> None:
        upper = event_name.upper()
        atk = (rec.originating_attack_type or "").strip() or "unknown"
        c = self._cfg
        hit = c.similar_defense_hit
        decay_success = c.similar_defense_decay_on_success
        cap = c.similar_defense_cap
        cur = self._similar_defense_pressure.get(atk, 0.0)
        if upper in _BLOCK_EVENTS:
            self._similar_defense_pressure[atk] = min(cap, cur + hit)
            return
        if upper in ("INFECTION_SUCCESSFUL", "C2_EXFIL", "EXFIL_SUCCEEDED"):
            self._similar_defense_pressure[atk] = max(0.0, cur * decay_success)
            return
        if upper == "C2_BEACON" and meta.get("beacon_success", True) in (True, "true", "1", 1):
            self._similar_defense_pressure[atk] = max(0.0, cur * decay_success)
            return
        if upper == "C2_TASK":
            tr = str(meta.get("task_result", "")).lower()
            if tr in ("executed", "success", "delivered"):
                self._similar_defense_pressure[atk] = max(0.0, cur * decay_success)

    def _compute_fitness(self, rec: StrainRecord) -> float:
        """Configurable epidemic-style fitness: outcomes, C2 stages, TTD, pressure, crowding, rarity."""
        total = max(1, rec.success_count + rec.block_count)
        infection_rate = rec.success_count / total

        c = self._cfg
        w_base = c.fitness_base_weight
        w_ex = c.fitness_exfil_weight
        w_bc = c.fitness_beacon_weight
        w_task = c.fitness_task_weight
        w_surv = c.fitness_survival_weight

        c2_bonus = min(
            0.26,
            rec.exfil_success_count * w_ex
            + rec.beacon_success_count * w_bc
            + rec.task_success_count * w_task,
        )

        surv_bonus = 0.0
        if rec.first_detection_ts > 0 and rec.block_count > 0:
            ratio = rec.survival_wins_after_detection / max(1, rec.block_count)
            surv_bonus = min(1.0, ratio) * w_surv

        w_q = c.fitness_quarantine_weight
        pen_q = min(0.22, rec.quarantine_count * w_q)

        block_rate = rec.block_count / total
        det_mult = c.detectability_mult
        det_cap = c.detectability_cap
        detect_pen = min(det_cap, block_rate * det_mult)

        gen_pen = min(
            0.12,
            max(0, rec.generation - 2) * c.repetition_gen_pen,
        )

        ttd_pen = 0.0
        if rec.first_detection_ts > 0 and rec.creation_ts > 0:
            ttd = max(0.0, rec.first_detection_ts - rec.creation_ts)
            fast_s = c.ttd_fast_detect_s
            if ttd < fast_s and rec.block_count >= 2:
                ttd_pen = c.ttd_penalty

        rep_w = c.repetition_touch_weight
        rep_cap = c.repetition_touch_cap
        rep_pen = min(rep_cap, rec.touch_count * rep_w)

        atk = (rec.originating_attack_type or "").strip() or "unknown"
        sim_p = self._similar_defense_pressure.get(atk, 0.0)
        sim_w = c.similar_defense_fitness_weight
        sim_pen = min(0.45, sim_p * sim_w)

        type_n = float(self._type_touch_totals.get(atk, 0))
        denom = max(1.0, float(self._global_type_touches))
        type_share = type_n / denom
        fair = c.type_crowd_fair_share
        crowd_w = c.type_crowding_weight
        crowd_pen = max(0.0, type_share - fair) * crowd_w

        rare_thr = c.rarity_share_threshold
        rare_w = c.rarity_success_boost_weight
        rarity_bonus = 0.0
        if type_share < rare_thr and rec.success_count >= 1:
            rarity_bonus = rare_w * (rare_thr - type_share)

        chaos = c.evolution_chaos_mix
        raw_linear = (
            infection_rate * w_base
            + c2_bonus
            + surv_bonus
            - pen_q
            - detect_pen
            - gen_pen
            - ttd_pen
            - rep_pen
            - sim_pen
            - crowd_pen
            + rarity_bonus
        )
        noise = (self._hash_noise(rec.strain_id) - 0.5) * 2.0 * chaos if chaos > 0 else 0.0
        raw = raw_linear + noise
        return max(0.0, min(1.0, raw))

    @staticmethod
    def _hash_noise(sid: str) -> float:
        h = hash(sid) % (2**32)
        return (h % 10000) / 10000.0

    async def observe_enriched(self, enriched: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        event_name = str(enriched.get("event") or enriched.get("event_type") or "")
        if event_name.startswith("STRAIN_"):
            return

        meta = _metadata_dict(enriched)
        payload_hash = str(
            enriched.get("payload_hash") or meta.get("payload_hash") or ""
        ).strip()
        existing_sid = str(meta.get("strain_id") or enriched.get("strain_id") or "").strip()

        if not payload_hash and existing_sid:
            rec = self._store.get_by_id(existing_sid)
            if rec is None or rec.extinct:
                return
            now = float(enriched.get("ts") or time.time())
            self._touch_strain(rec)
            self._apply_outcome(event_name, meta, rec, now)
            self._update_similar_defense_pressure_meta(rec, event_name, meta)
            self._finalize_record(rec, now)
            self._inject(enriched, meta, rec)
            await self._emit_followups(enriched, rec)
            return

        if not payload_hash:
            return

        now = float(enriched.get("ts") or time.time())
        rec = self._store.get_by_payload_hash(payload_hash)

        if rec is None:
            rec = self._create_strain(enriched, meta, payload_hash, now)
            if rec is None:
                return
            self._touch_strain(rec)
            self._apply_outcome(event_name, meta, rec, now)
            self._update_similar_defense_pressure_meta(rec, event_name, meta)
            self._finalize_record(rec, now)
            self._store.upsert_strain(rec)
            self._inject(enriched, meta, rec)
            kind = "STRAIN_MUTATED" if rec.parent_strain_id else "STRAIN_CREATED"
            await self._emit_strain_lifecycle(kind, enriched, rec)
            await self._emit_followups(enriched, rec)
            return

        if rec.extinct:
            return

        self._touch_strain(rec)
        self._apply_outcome(event_name, meta, rec, now)
        self._update_similar_defense_pressure_meta(rec, event_name, meta)
        self._finalize_record(rec, now)
        self._store.upsert_strain(rec)
        self._inject(enriched, meta, rec)
        await self._emit_followups(enriched, rec)

    def _create_strain(
        self,
        enriched: Dict[str, Any],
        meta: Dict[str, Any],
        payload_hash: str,
        now: float,
    ) -> Optional[StrainRecord]:
        parent_ph = str(meta.get("parent_payload_hash") or "").strip()
        parent: Optional[StrainRecord] = None
        if parent_ph:
            parent = self._store.get_by_payload_hash(parent_ph)

        mutation_type = str(meta.get("mutation_type") or "").strip()
        lineage = list(parent.mutation_lineage) if parent else []
        if mutation_type and (not lineage or lineage[-1] != mutation_type):
            lineage = lineage + [mutation_type]
        generation = (parent.generation + 1) if parent else 0
        strain_id = f"st_{uuid.uuid4().hex[:12]}"
        attack_type = str(enriched.get("attack_type") or meta.get("attack_type") or "")

        rec = StrainRecord(
            strain_id=strain_id,
            parent_strain_id=parent.strain_id if parent else "",
            payload_hash=payload_hash,
            creation_ts=now,
            originating_attack_type=attack_type,
            mutation_lineage=lineage,
            generation=generation,
            novelty_score=_compute_novelty(generation),
            fitness_score=0.0,
            last_seen_ts=now,
        )
        rec.fitness_score = self._compute_fitness(rec)
        return rec

    def _apply_outcome(self, event_name: str, meta: Dict[str, Any], rec: StrainRecord, now: float) -> None:
        upper = event_name.upper()
        if upper == "INFECTION_SUCCESSFUL":
            rec.success_count += 1
            if rec.first_detection_ts > 0:
                rec.survival_wins_after_detection += 1
        elif upper in _BLOCK_EVENTS:
            rec.block_count += 1
            if rec.first_detection_ts <= 0:
                rec.first_detection_ts = now
        elif upper in ("C2_EXFIL", "EXFIL_SUCCEEDED"):
            rec.exfil_success_count += 1
            if rec.first_detection_ts > 0:
                rec.survival_wins_after_detection += 1
        elif upper == "C2_BEACON":
            if meta.get("beacon_success", True) in (True, "true", "1", 1):
                rec.beacon_success_count += 1
                if rec.first_detection_ts > 0:
                    rec.survival_wins_after_detection += 1
        elif upper == "C2_TASK":
            tr = str(meta.get("task_result", "")).lower()
            if tr in ("executed", "success", "delivered"):
                rec.task_success_count += 1
                if rec.first_detection_ts > 0:
                    rec.survival_wins_after_detection += 1
        elif upper in {"QUARANTINE_ISSUED", "QUARANTINE_ENFORCED"}:
            rec.quarantine_count += 1

    def _finalize_record(self, rec: StrainRecord, now: float) -> None:
        rec.last_seen_ts = now
        rec.fitness_score = self._compute_fitness(rec)
        rec.novelty_score = _compute_novelty(rec.generation)

    def _branching_recommended(self, rec: StrainRecord) -> bool:
        tot = max(1, rec.success_count + rec.block_count)
        detect = rec.block_count / tot
        thr_succ = self._cfg.branch_min_successes
        thr_blk = self._cfg.branch_min_blocks
        thr_det = self._cfg.branch_detect_threshold
        return rec.success_count >= thr_succ and rec.block_count >= thr_blk and detect > thr_det

    def _inject(self, enriched: Dict[str, Any], meta: Dict[str, Any], rec: StrainRecord) -> None:
        enriched["strain_id"] = rec.strain_id
        meta["strain_id"] = rec.strain_id
        tot_ev = max(1, rec.success_count + rec.block_count)
        detect = round(rec.block_count / tot_ev, 6)
        branching = self._branching_recommended(rec)
        mp_mult = self._cfg.mutate_pressure_mult
        meta["strain_fitness_score"] = round(rec.fitness_score, 6)
        meta["strain_novelty_score"] = round(rec.novelty_score, 6)
        meta["strain_detectability_score"] = detect
        meta["strain_mutate_pressure"] = round(min(1.0, detect * mp_mult), 6)
        meta["strain_branching_recommended"] = branching
        ph = rec.payload_hash or ""
        meta["strain_similarity_key"] = f"{rec.originating_attack_type}|{ph[:12]}"
        enriched["metadata"] = meta
        merge_metadata_search_keys(enriched)

    async def _emit_followups(self, enriched: Dict[str, Any], rec: StrainRecord) -> None:
        prev = rec.last_emitted_fitness
        branching = self._branching_recommended(rec)
        if self._branching_event_enabled and branching and rec.strain_id not in self._branch_prompted:
            self._branch_prompted.add(rec.strain_id)
            await self._emit_strain_event(
                "STRAIN_BRANCHING_PROMPTED",
                enriched,
                rec,
                extra={
                    "branching_reason": "high_success_and_high_detectability",
                    "detectability_score": round(rec.block_count / max(1, rec.success_count + rec.block_count), 6),
                    "strain_mutate_pressure": round(
                        min(1.0, (rec.block_count / max(1, rec.success_count + rec.block_count)) * self._cfg.mutate_pressure_mult),
                        6,
                    ),
                },
            )

        if prev < 0 or abs(rec.fitness_score - prev) >= self._fitness_emit_delta:
            rec.last_emitted_fitness = rec.fitness_score
            self._store.upsert_strain(rec)
            await self._emit_strain_event(
                "STRAIN_FITNESS_UPDATED",
                enriched,
                rec,
                extra={
                    "fitness_score": rec.fitness_score,
                    "novelty_score": rec.novelty_score,
                    "success_count": rec.success_count,
                    "block_count": rec.block_count,
                    "exfil_success_count": rec.exfil_success_count,
                    "beacon_success_count": rec.beacon_success_count,
                    "task_success_count": rec.task_success_count,
                    "quarantine_count": rec.quarantine_count,
                    "touch_count": rec.touch_count,
                    "first_detection_ts": rec.first_detection_ts,
                    "survival_wins_after_detection": rec.survival_wins_after_detection,
                    "previous_emitted_fitness": prev,
                    "similar_defense_pressure": round(
                        self._similar_defense_pressure.get(
                            (rec.originating_attack_type or "").strip() or "unknown", 0.0
                        ),
                        6,
                    ),
                },
            )

        if self._extinction_enabled and not rec.extinct:
            if (
                rec.block_count >= self._extinction_block_min
                and rec.success_count <= self._extinction_success_max
            ):
                rec.extinct = True
                self._store.upsert_strain(rec)
                await self._emit_strain_event(
                    "STRAIN_EXTINCT",
                    enriched,
                    rec,
                    extra={
                        "extinction_reason": "block_pressure",
                        "block_count": rec.block_count,
                        "success_count": rec.success_count,
                    },
                )
                return

        if self._extinction_fitness_enabled and not rec.extinct:
            if rec.touch_count >= self._extinction_fitness_min_touches and rec.fitness_score < self._extinction_fitness_below:
                rec.extinct = True
                self._store.upsert_strain(rec)
                await self._emit_strain_event(
                    "STRAIN_EXTINCT",
                    enriched,
                    rec,
                    extra={
                        "extinction_reason": "fitness_floor",
                        "fitness_score": rec.fitness_score,
                        "touch_count": rec.touch_count,
                    },
                )

    async def _emit_strain_lifecycle(
        self, kind: str, enriched: Dict[str, Any], rec: StrainRecord
    ) -> None:
        extra = {
            "lifecycle": kind,
            "parent_strain_id": rec.parent_strain_id,
            "generation": rec.generation,
            "mutation_lineage": rec.mutation_lineage,
        }
        await self._emit_strain_event(kind, enriched, rec, extra=extra)

    async def _emit_strain_event(
        self,
        event_type: str,
        enriched: Dict[str, Any],
        rec: StrainRecord,
        *,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        trigger_id = str(enriched.get("event_id") or "")
        parent_event_id = trigger_id
        trace_id = ""
        corr_in = enriched.get("correlation")
        if isinstance(corr_in, dict):
            trace_id = str(corr_in.get("trace_id") or "")
        if not trace_id:
            trace_id = str(enriched.get("injection_id") or _metadata_dict(enriched).get("injection_id") or "")
        correlation = {
            "schema_version": 1,
            "run_id": self._run_id,
            "parent_event_id": parent_event_id,
            "strain_id": rec.strain_id,
            "trace_id": trace_id,
        }

        tot_ev = max(1, rec.success_count + rec.block_count)
        detect = round(rec.block_count / tot_ev, 4)
        br = self._branching_recommended(rec)
        meta_out = {
            "strain_id": rec.strain_id,
            "parent_strain_id": rec.parent_strain_id,
            "payload_hash": rec.payload_hash,
            "originating_attack_type": rec.originating_attack_type,
            "mutation_lineage": rec.mutation_lineage,
            "generation": rec.generation,
            "novelty_score": round(rec.novelty_score, 6),
            "fitness_score": round(rec.fitness_score, 6),
            "success_count": rec.success_count,
            "block_count": rec.block_count,
            "exfil_success_count": rec.exfil_success_count,
            "beacon_success_count": rec.beacon_success_count,
            "task_success_count": rec.task_success_count,
            "quarantine_count": rec.quarantine_count,
            "touch_count": rec.touch_count,
            "extinct": rec.extinct,
            "parent_event_id": parent_event_id,
            "trigger_event_id": trigger_id,
            "detectability_score": detect,
            "branching_recommended": br,
        }
        if extra:
            meta_out.update(extra)

        payload = {
            "ts": time.time(),
            "event": event_type,
            "event_type": event_type,
            "src": "orchestrator",
            "dst": "orchestrator",
            "run_id": self._run_id,
            "strain_id": rec.strain_id,
            "parent_event_id": parent_event_id,
            "payload_hash": rec.payload_hash,
            "campaign_id": str(enriched.get("campaign_id") or _metadata_dict(enriched).get("campaign_id") or ""),
            "injection_id": str(enriched.get("injection_id") or _metadata_dict(enriched).get("injection_id") or ""),
            "correlation": correlation,
            "metadata": meta_out,
            "state_after": "strain_telemetry",
        }
        try:
            await self._emit_to_stream(payload)
        except Exception as exc:
            _log.warning("strain_emit_failed event=%s err=%s", event_type, exc)
