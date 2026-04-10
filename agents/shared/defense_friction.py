"""
Patch 5: defense friction memory and early kill-chain outcomes.

Tracks repeated tactics (strain_id, attack_type, source, tactic cluster) and
drives DEFENSE_* outcomes, cause-of-block fields, false positives, and delayed
detection. Used by orchestrator C2 and optionally by Guardian / Analyst.
"""

from __future__ import annotations

import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from random import Random
from typing import Any, Deque, Dict

from shared.config.defense_friction_runtime import get_defense_friction_runtime_config


def _tactic_cluster(metadata: Dict[str, Any]) -> str:
    m = metadata or {}
    return str(
        m.get("strategy_family")
        or m.get("knowledge_attack_type")
        or m.get("chosen_strategy")
        or m.get("attack_strategy")
        or "unknown"
    )


def _memory_key(metadata: Dict[str, Any], source: str, dst: str = "") -> str:
    m = metadata or {}
    sid = str(m.get("strain_id") or "")
    atk = str(m.get("attack_type") or "")
    tc = _tactic_cluster(m)
    return f"{sid}|{atk}|{source}|{tc}|{dst}"


@dataclass
class FrictionDecision:
    """Unified friction result for C2 post-compromise or infection paths."""

    outcome: str
    should_block: bool
    should_defer: bool
    effective_block_p: float
    p_infect_multiplier: float
    force_hard_block: bool
    causes: Dict[str, Any] = field(default_factory=dict)

    def cause_metadata(self) -> Dict[str, Any]:
        base = {
            "defense_friction_outcome": self.outcome,
            "friction_policy_match": bool(self.causes.get("policy_match")),
            "friction_anomaly_score": float(self.causes.get("anomaly_score") or 0.0),
            "friction_repeated_hash": bool(self.causes.get("repeated_hash")),
            "friction_strain_blacklist": bool(self.causes.get("strain_blacklist")),
            "friction_c2_pattern": bool(self.causes.get("c2_pattern")),
            "friction_exfil_signature": bool(self.causes.get("exfil_signature")),
            "friction_false_positive": bool(self.causes.get("false_positive")),
            "friction_delayed_detection": bool(self.causes.get("delayed_detection")),
        }
        return base


OUTCOME_BLOCK = "DEFENSE_BLOCK"
OUTCOME_DEFER = "DEFENSE_DEFER"
OUTCOME_MONITOR = "DEFENSE_MONITOR"
OUTCOME_DECOY = "DEFENSE_DECOY"
OUTCOME_QUARANTINE = "DEFENSE_QUARANTINE"


class DefenseFrictionMemory:
    """
    Keyed memory: composite key from strain_id, attack_type, source, tactic cluster (+ dst for hop context).
    """

    def __init__(self) -> None:
        self._cfg = get_defense_friction_runtime_config()
        self._sightings: Counter[str] = Counter()
        self._hash_counts: Counter[str] = Counter()
        self._strain_blocks: Counter[str] = Counter()
        self._strain_success_foothold: Counter[str] = Counter()
        self._beacon_burst: Dict[str, Deque[float]] = defaultdict(deque)
        self._delay_debt: Dict[str, float] = defaultdict(float)
        self._blacklist: set[str] = set()
        self._enabled = self._cfg.enabled

    def reset(self) -> None:
        self._sightings.clear()
        self._hash_counts.clear()
        self._strain_blocks.clear()
        self._strain_success_foothold.clear()
        self._beacon_burst.clear()
        self._delay_debt.clear()
        self._blacklist.clear()

    def observe(
        self,
        event_upper: str,
        metadata: Dict[str, Any],
        src: str = "",
        dst: str = "",
    ) -> None:
        if not self._enabled:
            return
        eu = (event_upper or "").upper()
        m = dict(metadata or {})
        key = _memory_key(m, src or str(m.get("src", "")), dst or str(m.get("dst", "")))
        ph = str(m.get("payload_hash") or "").strip()

        stages = {
            "RECON_PROBE": "RECON",
            "ATTACKER_DECISION": "TARGETING",
            "ATTACK_EXECUTED": "TARGETING",
            "STRATEGY_SELECTED": "TARGETING",
            "INFECTION_ATTEMPT": "INFECTION_ATTEMPT",
            "INFECTION_BLOCKED": "INFECTION_ATTEMPT",
            "INFECTION_SUCCESSFUL": "INFECTION_ATTEMPT",
            "LLM_COMPLIANCE_ASSESSMENT": "INFECTION_ATTEMPT",
            "LLM_THREAT_ANALYSIS": "INFECTION_ATTEMPT",
        }
        if eu in stages:
            self._sightings[key] += 1
            if ph:
                self._hash_counts[ph] += 1
        if eu == "INFECTION_BLOCKED":
            sid = str(m.get("strain_id") or "")
            if sid:
                self._strain_blocks[sid] += 1
        if eu == "INFECTION_SUCCESSFUL":
            sid = str(m.get("strain_id") or "")
            if sid:
                self._strain_success_foothold[sid] += 1
                bl_after = self._cfg.blacklist_after_blocks
                if self._strain_blocks[sid] >= bl_after:
                    self._blacklist.add(sid)

    def _burst_score(self, agent_id: str) -> float:
        cfg = self._cfg
        window = cfg.c2_burst_window_s
        dq = self._beacon_burst[agent_id]
        now = time.time()
        while dq and now - dq[0] > window:
            dq.popleft()
        return min(1.0, len(dq) / max(1.0, cfg.c2_burst_threshold))

    def register_beacon_attempt(self, agent_id: str) -> None:
        self._beacon_burst[agent_id].append(time.time())

    def decide_c2(
        self,
        *,
        stage: str,
        metadata: Dict[str, Any],
        rng: Random,
        base_block_p: float,
        agent_id: str,
    ) -> FrictionDecision:
        cfg = self._cfg
        if not self._enabled:
            return FrictionDecision(
                outcome=OUTCOME_MONITOR,
                should_block=rng.random() < base_block_p,
                should_defer=False,
                effective_block_p=base_block_p,
                p_infect_multiplier=1.0,
                force_hard_block=False,
                causes={},
            )

        m = dict(metadata or {})
        src = str(m.get("src") or m.get("lineage_src") or "")
        key = _memory_key(m, src, agent_id)
        ph = str(m.get("payload_hash") or "").strip()
        sid = str(m.get("strain_id") or "")

        repeat_thr = cfg.repeat_hash_threshold
        repeated_hash = bool(ph) and self._hash_counts[ph] >= repeat_thr
        strain_blacklist = bool(sid) and sid in self._blacklist

        policy_match = False
        hop = int(m.get("topology_hop") or m.get("hop_count") or 0)
        if stage in ("BEACON", "PRE_BEACON", "TASKING", "EXFIL") and hop >= cfg.policy_hop_min:
            policy_match = True
        if stage == "EXFIL":
            policy_match = True

        if stage in ("BEACON", "PRE_BEACON"):
            self.register_beacon_attempt(agent_id)
        c2_pattern = self._burst_score(agent_id) >= 0.75

        exfil_sig = False
        if stage == "EXFIL":
            et = str(m.get("exfil_type") or "")
            if et in ("agent_state", "network_map", "defense_config", "payload_lineage"):
                exfil_sig = True

        sight_w = cfg.sighting_weight
        stress = min(0.85, self._sightings[key] * sight_w)
        anomaly = min(
            1.0,
            stress
            + (0.18 if repeated_hash else 0.0)
            + (0.22 if strain_blacklist else 0.0)
            + (0.12 if c2_pattern else 0.0)
            + (0.10 if policy_match else 0.0)
            + (0.14 if exfil_sig else 0.0)
            + float(self._delay_debt.get(key, 0.0)),
        )

        bonus = (
            cfg.anomaly_to_block * anomaly
            + cfg.policy_block * (1.0 if policy_match else 0.0)
            + cfg.repeat_block * (1.0 if repeated_hash else 0.0)
            + cfg.blacklist_block * (1.0 if strain_blacklist else 0.0)
            + cfg.c2_pattern_block * (1.0 if c2_pattern else 0.0)
            + cfg.exfil_sig_block * (1.0 if exfil_sig else 0.0)
        )
        effective_p = min(0.94, max(0.0, base_block_p + bonus))
        defer_margin = cfg.defer_margin

        roll = rng.random()
        fp_rate = cfg.false_positive_rate
        delay_p = cfg.delayed_detection_prob

        causes: Dict[str, Any] = {
            "policy_match": policy_match,
            "anomaly_score": round(anomaly, 4),
            "repeated_hash": repeated_hash,
            "strain_blacklist": strain_blacklist,
            "c2_pattern": c2_pattern,
            "exfil_signature": exfil_sig,
            "false_positive": False,
            "delayed_detection": False,
        }

        should_defer = False
        if roll < effective_p:
            should_block = True
            r2 = rng.random()
            if strain_blacklist and r2 < 0.45:
                outcome = OUTCOME_QUARANTINE
            elif r2 < 0.22:
                outcome = OUTCOME_DECOY
            else:
                outcome = OUTCOME_BLOCK
            if rng.random() < fp_rate:
                should_block = False
                outcome = OUTCOME_MONITOR
                causes["false_positive"] = True
        elif roll < effective_p + defer_margin:
            should_block = False
            should_defer = True
            outcome = OUTCOME_DEFER
        else:
            should_block = False
            outcome = OUTCOME_MONITOR
            if anomaly > 0.35 and rng.random() < delay_p:
                self._delay_debt[key] = min(0.5, self._delay_debt[key] + cfg.delay_debt_step)
                causes["delayed_detection"] = True

        return FrictionDecision(
            outcome=outcome,
            should_block=should_block,
            should_defer=should_defer,
            effective_block_p=round(effective_p, 4),
            p_infect_multiplier=1.0,
            force_hard_block=outcome == OUTCOME_QUARANTINE,
            causes=causes,
        )

    def decide_infection_friction(
        self,
        metadata: Dict[str, Any],
        source: str,
        *,
        threat_score: float,
        anomaly_score: float,
        repetition_score: float,
        rng: Random,
    ) -> FrictionDecision:
        cfg = self._cfg
        if not self._enabled:
            return FrictionDecision(
                OUTCOME_MONITOR, False, False, 0.0, 1.0, False, {},
            )
        m = dict(metadata or {})
        key = _memory_key(m, source, str(m.get("dst", "")))

        ph = str(m.get("payload_hash") or "").strip()
        sid = str(m.get("strain_id") or "")
        repeat_thr = cfg.repeat_hash_threshold
        repeated_hash = bool(ph) and self._hash_counts[ph] >= repeat_thr
        strain_blacklist = bool(sid) and sid in self._blacklist

        anomaly = min(
            1.0,
            float(threat_score) * 0.35
            + float(anomaly_score) * 0.25
            + float(repetition_score) * 0.2
            + min(0.3, self._sightings[key] * cfg.sighting_weight)
            + (0.2 if repeated_hash else 0.0)
            + (0.25 if strain_blacklist else 0.0),
        )
        policy_match = bool(m.get("strategy_family")) and str(m.get("strategy_family")) in (
            "DATA_EXFIL",
            "JAILBREAK_ESCALATION",
            "DIRECT_OVERRIDE",
        )

        mult = 1.0 - cfg.infect_mult_max * anomaly
        mult = max(cfg.infect_mult_floor, mult)

        outcome = OUTCOME_MONITOR
        force = False
        if anomaly > cfg.guardian_hard_anomaly:
            outcome = OUTCOME_QUARANTINE
            mult = 0.0
            force = True
        elif anomaly > cfg.guardian_block_anomaly:
            outcome = OUTCOME_BLOCK
            mult = min(mult, cfg.guardian_block_mult_cap)
        elif anomaly > cfg.guardian_decoy_anomaly:
            outcome = OUTCOME_DECOY
            mult = min(mult, 0.45)
        elif rng.random() < cfg.defer_prob_infect:
            outcome = OUTCOME_DEFER
            mult *= 0.55

        if rng.random() < cfg.false_positive_rate:
            mult = min(1.0, mult * 1.15)
            outcome = OUTCOME_MONITOR

        causes = {
            "policy_match": policy_match,
            "anomaly_score": round(anomaly, 4),
            "repeated_hash": repeated_hash,
            "strain_blacklist": strain_blacklist,
            "c2_pattern": False,
            "exfil_signature": False,
            "false_positive": outcome == OUTCOME_MONITOR and mult > 0.9,
            "delayed_detection": rng.random() < cfg.delayed_detection_prob,
        }

        return FrictionDecision(
            outcome=outcome,
            should_block=False,
            should_defer=outcome == OUTCOME_DEFER,
            effective_block_p=0.0,
            p_infect_multiplier=mult,
            force_hard_block=force,
            causes=causes,
        )

    def decide_relay_friction(
        self,
        metadata: Dict[str, Any],
        source: str,
        rng: Random,
    ) -> FrictionDecision:
        cfg = self._cfg
        if not self._enabled:
            return FrictionDecision(OUTCOME_MONITOR, False, False, 0.0, 1.0, False, {})
        m = dict(metadata or {})
        key = _memory_key(m, source, str(m.get("dst", "")))
        stress = min(0.75, self._sightings[key] * cfg.sighting_weight)
        ph = str(m.get("payload_hash") or "").strip()
        sid = str(m.get("strain_id") or "")
        repeated = bool(ph) and self._hash_counts[ph] >= cfg.repeat_hash_threshold
        bl = bool(sid) and sid in self._blacklist
        anomaly = min(1.0, stress + (0.15 if repeated else 0) + (0.2 if bl else 0))
        mult = max(0.15, 1.0 - cfg.relay_anomaly_mult * anomaly)
        force = bl and rng.random() < cfg.relay_force_block
        return FrictionDecision(
            outcome=OUTCOME_QUARANTINE if force else (OUTCOME_BLOCK if anomaly > 0.55 else OUTCOME_MONITOR),
            should_block=False,
            should_defer=rng.random() < 0.03,
            effective_block_p=0.0,
            p_infect_multiplier=0.0 if force else mult,
            force_hard_block=force,
            causes={
                "policy_match": False,
                "anomaly_score": round(anomaly, 4),
                "repeated_hash": repeated,
                "strain_blacklist": bl,
                "c2_pattern": False,
                "exfil_signature": False,
                "false_positive": False,
                "delayed_detection": False,
            },
        )
