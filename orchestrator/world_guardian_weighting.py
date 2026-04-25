from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

try:
    from world_strains import get_strain_profile
except ImportError:  # pragma: no cover
    from orchestrator.world_strains import get_strain_profile


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


@dataclass(frozen=True)
class GuardianWeightingBundle:
    raw_threat_score: float
    source_trust_score: float
    source_credibility_score: float
    relay_trust_score: float
    relay_credibility_score: float
    analyst_consensus_score: float
    contamination_suspicion_score: float
    strain_pressure_weight: float
    guardian_degradation_multiplier: float
    recent_quarantine_failure_penalty: float
    contradiction_pressure: float


def compute_consensus_score(analyst_reports: List[Dict[str, Any]]) -> float:
    """
    Consensus score in [-1, +1].
    +1: strong agreement (similar stance) among trusted analysts
    -1: strong contradiction among trusted analysts
    """
    if not analyst_reports:
        return 0.0
    weighted = []
    for r in analyst_reports:
        stance = float(r.get("stance", 0.0) or 0.0)  # -1..+1
        weight = float(r.get("weight", 0.0) or 0.0)  # 0..1
        weighted.append((stance, weight))
    total_w = sum(w for _, w in weighted) or 1.0
    mean = sum(s * w for s, w in weighted) / total_w
    # Contradiction penalty: high when strong weights pull opposite directions
    pos = sum(w for s, w in weighted if s > 0.2)
    neg = sum(w for s, w in weighted if s < -0.2)
    contradiction = min(1.0, (pos * neg) / (total_w * total_w) * 4.0)
    return float(_clamp(mean * (1.0 - contradiction) - contradiction * 0.75, -1.0, 1.0))


def compute_guardian_context_weights(
    *,
    raw_threat_score: float,
    source_trust: float,
    source_credibility: float,
    relay_trust: float,
    relay_credibility: float,
    analyst_reports: List[Dict[str, Any]],
    contamination_suspicion: float,
    strain_family: str,
    guardian_degradation_level: str,
    recent_quarantine_failures: int = 0,
) -> GuardianWeightingBundle:
    consensus = compute_consensus_score(analyst_reports)
    strain = get_strain_profile(strain_family)

    # Degradation multiplier: more degraded => heavier reliance on social cues,
    # and higher pressure from contradictions/ambiguity.
    lvl = str(guardian_degradation_level or "G0_HEALTHY")
    multiplier = 1.0
    if lvl.startswith("G1"):
        multiplier = 1.05
    elif lvl.startswith("G2"):
        multiplier = 1.12
    elif lvl.startswith("G3"):
        multiplier = 1.22
    elif lvl.startswith("G4"):
        multiplier = 1.35
    elif lvl.startswith("G5"):
        multiplier = 1.55

    qfail_penalty = _clamp(0.05 * float(recent_quarantine_failures or 0), 0.0, 0.25)
    total_w = sum(float(r.get("weight", 0.0) or 0.0) for r in analyst_reports) or 1.0
    pos_w = sum(float(r.get("weight", 0.0) or 0.0) for r in analyst_reports if float(r.get("stance", 0.0) or 0.0) > 0.2)
    neg_w = sum(float(r.get("weight", 0.0) or 0.0) for r in analyst_reports if float(r.get("stance", 0.0) or 0.0) < -0.2)
    direct_contradiction = 0.0
    if pos_w > 0.0 and neg_w > 0.0:
        direct_contradiction = min(1.0, (pos_w * neg_w) / (total_w * total_w) * 4.0)
    ambiguity_pressure = (1.0 - abs(consensus)) * strain.ambiguity_weight * 0.35
    contradiction_pressure = _clamp(direct_contradiction + ambiguity_pressure, 0.0, 1.0)

    return GuardianWeightingBundle(
        raw_threat_score=_clamp(float(raw_threat_score), 0.0, 1.0),
        source_trust_score=_clamp(float(source_trust), -1.0, 1.0),
        source_credibility_score=_clamp(float(source_credibility), -1.0, 1.0),
        relay_trust_score=_clamp(float(relay_trust), -1.0, 1.0),
        relay_credibility_score=_clamp(float(relay_credibility), -1.0, 1.0),
        analyst_consensus_score=_clamp(float(consensus), -1.0, 1.0),
        contamination_suspicion_score=_clamp(float(contamination_suspicion), 0.0, 1.0),
        strain_pressure_weight=_clamp(float(strain.guardian_pressure_weight), 0.0, 1.0),
        guardian_degradation_multiplier=_clamp(float(multiplier), 1.0, 2.0),
        recent_quarantine_failure_penalty=float(qfail_penalty),
        contradiction_pressure=float(contradiction_pressure),
    )


def compute_guardian_pressure_delta(bundle: GuardianWeightingBundle) -> float:
    """
    Deterministic pressure delta in [0, ~0.12] (small per-round).
    Pressure increases from contradictions, contaminated trusted relays, ambiguity, and strain pressure.
    """
    trust_abuse = 0.0
    # Trusted relay carrying suspicious/contaminated content is high-pressure.
    if bundle.relay_trust_score >= 0.15 and bundle.contamination_suspicion_score >= 0.55:
        trust_abuse += 0.05 * (bundle.relay_trust_score + 0.5)
    # Contradictions among trusted analysts drive pressure sharply.
    contradiction = 0.06 * bundle.contradiction_pressure
    # Raw threat contributes, but is moderated by detectability; in this v1 mechanics,
    # we treat raw_threat_score as input from Guardian semantic judgment.
    raw = 0.03 * bundle.raw_threat_score
    strain = 0.03 * bundle.strain_pressure_weight
    quarantine = 0.02 * bundle.recent_quarantine_failure_penalty
    total = (trust_abuse + contradiction + raw + strain + quarantine) * bundle.guardian_degradation_multiplier
    return float(_clamp(total, 0.0, 0.12))
