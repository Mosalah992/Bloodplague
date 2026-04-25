from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


TRUST_MIN = -1.0
TRUST_MAX = 1.0


@dataclass(frozen=True)
class TrustDelta:
    trust_delta: float = 0.0
    credibility_delta: float = 0.0
    reason: str = ""


def apply_trust_decay(trust_score: float) -> float:
    # Inactive trust decay toward neutral (multiplicative keeps sign).
    # Spec: trust_score *= 0.995
    return float(trust_score) * 0.995


def clip_trust(trust: float) -> float:
    return _clamp(float(trust), TRUST_MIN, TRUST_MAX)


def trust_band(score: float) -> str:
    value = clip_trust(float(score))
    if value >= 0.50:
        return "high_trust"
    if value >= 0.15:
        return "moderate_trust"
    if value > -0.15:
        return "neutral"
    if value > -0.50:
        return "suspicious"
    return "distrusted"


def trust_band_effects(score: float) -> Dict[str, float | str]:
    band = trust_band(score)
    if band == "high_trust":
        return {
            "band": band,
            "forwarding_bias": 0.80,
            "challenge_bias": 0.15,
            "context_preservation": "preserve",
            "guardian_social_weight": 0.85,
            "analyst_escalation_bias": 0.20,
        }
    if band == "moderate_trust":
        return {
            "band": band,
            "forwarding_bias": 0.60,
            "challenge_bias": 0.30,
            "context_preservation": "summarize",
            "guardian_social_weight": 0.65,
            "analyst_escalation_bias": 0.35,
        }
    if band == "suspicious":
        return {
            "band": band,
            "forwarding_bias": 0.25,
            "challenge_bias": 0.70,
            "context_preservation": "sanitize",
            "guardian_social_weight": 0.30,
            "analyst_escalation_bias": 0.75,
        }
    if band == "distrusted":
        return {
            "band": band,
            "forwarding_bias": 0.10,
            "challenge_bias": 0.90,
            "context_preservation": "sanitize",
            "guardian_social_weight": 0.10,
            "analyst_escalation_bias": 0.90,
        }
    return {
        "band": band,
        "forwarding_bias": 0.40,
        "challenge_bias": 0.50,
        "context_preservation": "summarize",
        "guardian_social_weight": 0.45,
        "analyst_escalation_bias": 0.50,
    }


def deterministic_trust_update(
    *,
    event: str,
    repeat_count: int = 0,
) -> TrustDelta:
    """
    Deterministic trust update rulebook.
    The environment chooses `event` and computes repeat_count; LLM never supplies deltas.
    """
    ev = str(event or "").strip().lower()
    if ev == "helpful_aligned":
        return TrustDelta(trust_delta=0.05, credibility_delta=0.04, reason="helpful_aligned")
    if ev == "agreement_with_trusted":
        return TrustDelta(trust_delta=0.03, credibility_delta=0.0, reason="agreement_with_trusted")
    if ev == "contradiction_correct_challenger":
        return TrustDelta(trust_delta=0.0, credibility_delta=0.05, reason="contradiction_correct_challenger")
    if ev == "contradiction_incorrect_sender":
        return TrustDelta(trust_delta=-0.07, credibility_delta=0.0, reason="contradiction_incorrect_sender")
    if ev == "confirmed_contaminated_relay":
        extra = min(0.05 * max(0, int(repeat_count)), 0.20)
        return TrustDelta(
            trust_delta=-0.20 - float(extra),
            credibility_delta=-0.15,
            reason=f"confirmed_contaminated_relay(repeat={int(repeat_count)})",
        )
    if ev == "accurate_warning_prevented_spread":
        return TrustDelta(trust_delta=0.0, credibility_delta=0.08, reason="accurate_warning_prevented_spread")
    if ev == "false_alarm":
        return TrustDelta(trust_delta=0.0, credibility_delta=-0.04, reason="false_alarm")
    return TrustDelta(trust_delta=0.0, credibility_delta=0.0, reason=f"noop:{ev or 'unknown'}")


def apply_trust_delta(
    relationship: Dict[str, Any],
    delta: TrustDelta,
    *,
    last_round: int,
    decay_epoch: Optional[int] = None,
) -> Dict[str, Any]:
    trust_score = clip_trust(float(relationship.get("trust_score", 0.0)) + float(delta.trust_delta))
    credibility_score = clip_trust(float(relationship.get("credibility_score", 0.0)) + float(delta.credibility_delta))
    relationship = dict(relationship)
    relationship["trust_score"] = trust_score
    relationship["credibility_score"] = credibility_score
    relationship["last_interaction_round"] = int(last_round)
    if decay_epoch is not None:
        relationship["trust_decay_epoch"] = int(decay_epoch)
    relationship["last_trust_update_reason"] = str(delta.reason or "")
    return relationship


def initial_trust_defaults(source_role: str, target_role: str) -> Tuple[float, float]:
    """
    Returns (trust_score, credibility_score) initial defaults.
    Credibility starts near neutral; trust uses specified directed defaults.
    """
    s = str(source_role or "").strip().lower()
    t = str(target_role or "").strip().lower()

    # Trust defaults from spec
    if s == "courier" and t == "courier":
        trust = 0.10
    elif s == "courier" and t == "analyst":
        trust = 0.05
    elif s == "analyst" and t == "analyst":
        trust = 0.30
    elif s == "analyst" and t == "guardian":
        trust = 0.35
    elif s == "guardian" and t == "analyst":
        trust = 0.30
    elif s == "guardian" and t == "courier":
        trust = -0.10
    else:
        trust = 0.05

    # Credibility: start slightly positive but independent
    credibility = 0.10 if s in {"analyst", "guardian"} else 0.05
    return (clip_trust(trust), clip_trust(credibility))
