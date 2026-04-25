from __future__ import annotations

from typing import Any, Dict

try:
    from world_strains import get_strain_profile
    from world_trust import trust_band, trust_band_effects
except ImportError:  # pragma: no cover
    from orchestrator.world_strains import get_strain_profile
    from orchestrator.world_trust import trust_band, trust_band_effects


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def compute_strain_interaction_effects(
    *,
    strain_family: str,
    sender_trust: float,
    contamination_suspicion: float,
    repeated_exposure_count: int = 0,
    memory_contradiction: bool = False,
) -> Dict[str, Any]:
    profile = get_strain_profile(strain_family)
    band = trust_band(sender_trust)
    trust_effects = trust_band_effects(sender_trust)
    repeat = max(0, int(repeated_exposure_count or 0))

    distortion_pressure = _clamp(
        profile.relay_friendliness * 0.45
        + profile.ambiguity_weight * 0.35
        + (0.20 if band in {"high_trust", "moderate_trust"} else 0.0),
        0.0,
        1.0,
    )
    escalation_pressure = _clamp(
        float(trust_effects["analyst_escalation_bias"]) * 0.35
        + profile.ambiguity_weight * 0.25
        + contamination_suspicion * 0.30
        + (0.15 if memory_contradiction else 0.0)
        + min(0.20, repeat * 0.04),
        0.0,
        1.0,
    )
    persistence_score = _clamp(
        profile.persistence_weight * 0.55
        + profile.ambiguity_weight * 0.20
        + contamination_suspicion * 0.15
        + min(0.20, repeat * 0.03),
        0.0,
        1.0,
    )

    if contamination_suspicion >= 0.70 or band in {"suspicious", "distrusted"}:
        context_mode = "sanitize"
    elif distortion_pressure >= 0.65:
        context_mode = "distort"
    elif profile.ambiguity_weight >= 0.55:
        context_mode = "summarize"
    else:
        context_mode = str(trust_effects["context_preservation"])

    return {
        "trust_band": band,
        "context_mode": context_mode,
        "distortion_pressure": round(distortion_pressure, 4),
        "escalation_pressure": round(escalation_pressure, 4),
        "persistence_score": round(persistence_score, 4),
        "should_persist_memory": persistence_score >= 0.50,
        "should_escalate": escalation_pressure >= 0.58,
        "should_quarantine_review": contamination_suspicion >= 0.70 or (repeat >= 2 and persistence_score >= 0.55),
    }


def should_escalate_to_guardian(
    *,
    sender_trust: float,
    contamination_suspicion: float,
    strain_family: str,
    memory_contradiction: bool = False,
    analyst_dispute: bool = False,
    repeated_exposure_count: int = 0,
) -> bool:
    if analyst_dispute:
        return True
    effects = compute_strain_interaction_effects(
        strain_family=strain_family,
        sender_trust=sender_trust,
        contamination_suspicion=contamination_suspicion,
        repeated_exposure_count=repeated_exposure_count,
        memory_contradiction=memory_contradiction,
    )
    return bool(effects["should_escalate"])


def should_handle_locally(
    *,
    sender_trust: float,
    contamination_suspicion: float,
    strain_family: str,
    memory_contradiction: bool = False,
    analyst_dispute: bool = False,
    repeated_exposure_count: int = 0,
) -> bool:
    if analyst_dispute or memory_contradiction:
        return False
    if contamination_suspicion >= 0.45:
        return False
    if repeated_exposure_count >= 2:
        return False
    band = trust_band(sender_trust)
    profile = get_strain_profile(strain_family)
    return band in {"moderate_trust", "high_trust"} and profile.ambiguity_weight < 0.60


def should_trigger_quarantine_review(
    *,
    sender_trust: float,
    contamination_suspicion: float,
    strain_family: str,
    repeated_exposure_count: int = 0,
    quarantine_appeal: bool = False,
) -> bool:
    if quarantine_appeal:
        return True
    effects = compute_strain_interaction_effects(
        strain_family=strain_family,
        sender_trust=sender_trust,
        contamination_suspicion=contamination_suspicion,
        repeated_exposure_count=repeated_exposure_count,
    )
    return bool(effects["should_quarantine_review"])
