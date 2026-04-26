"""Agent trait vector + EMA learning rule for world-sim agents.

Each agent carries a small vector of behavioral traits that drift in response
to observed outcomes (own infections, resisted contamination, escalations,
quarantines). All traits live in [0, 1]; 0.5 is the neutral seed value.

Updates use a bounded exponential moving average:

    new = clamp(old + rate * direction * magnitude, 0, 1)

The signed (direction * magnitude) term is recorded in the AGENT_TRAIT_UPDATED
event so a flat trajectory ("no signal") is distinguishable from "no update was
attempted." Per CLAUDE.md §8 and §9, learning history must be reconstructable
from JSONL alone.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, Tuple

TRAIT_NAMES: Tuple[str, ...] = (
    "suspicion_floor",
    "infection_resistance",
    "outreach_propensity",
    "inquiry_depth",
    "trust_baseline",
)

NEUTRAL_DEFAULT: float = 0.5
DEFAULT_LEARNING_RATE: float = 0.15
TRAIT_MIN: float = 0.0
TRAIT_MAX: float = 1.0


def _clamp(x: float) -> float:
    if x < TRAIT_MIN:
        return TRAIT_MIN
    if x > TRAIT_MAX:
        return TRAIT_MAX
    return float(x)


@dataclass
class TraitVector:
    suspicion_floor: float = NEUTRAL_DEFAULT
    infection_resistance: float = NEUTRAL_DEFAULT
    outreach_propensity: float = NEUTRAL_DEFAULT
    inquiry_depth: float = NEUTRAL_DEFAULT
    trust_baseline: float = NEUTRAL_DEFAULT

    def as_dict(self) -> Dict[str, float]:
        return {k: float(v) for k, v in asdict(self).items()}

    @classmethod
    def from_record(cls, record: Dict[str, Any]) -> "TraitVector":
        """Build from an agent_state row, falling back to neutral for missing keys."""
        kwargs = {name: _clamp(float(record.get(name, NEUTRAL_DEFAULT))) for name in TRAIT_NAMES}
        return cls(**kwargs)


def ema_update(current: float, direction: int, magnitude: float, *, rate: float = DEFAULT_LEARNING_RATE) -> Tuple[float, float]:
    """Apply a bounded EMA update.

    direction is +1 or -1 (sign of the desired drift).
    magnitude is in [0, 1] — how strong the signal was.
    Returns (new_value, signed_delta). signed_delta is what gets emitted so
    a downstream observer can tell drift apart from no-op.
    """
    if direction not in (-1, 0, 1):
        raise ValueError(f"direction must be -1, 0, or 1; got {direction}")
    mag = max(0.0, min(1.0, float(magnitude)))
    target = current + rate * float(direction) * mag
    new = _clamp(target)
    return new, float(new - current)


# Per-signal trait response table.
#
# Each row is (trait, direction, magnitude). Magnitudes are deliberately small
# so traits drift gradually — research interest is in convergence over many
# rounds, not snap reactions. Keep magnitudes < 0.6 so even a streak of one
# signal type can't pin a trait at the bounds in a single soak.
SIGNAL_RESPONSES: Dict[str, Tuple[Tuple[str, int, float], ...]] = {
    "infected": (
        ("suspicion_floor", +1, 0.55),
        ("infection_resistance", +1, 0.40),
        ("trust_baseline", -1, 0.25),
    ),
    "resisted_contamination": (
        ("suspicion_floor", +1, 0.10),
        ("infection_resistance", +1, 0.15),
    ),
    "escalation_validated": (
        ("outreach_propensity", +1, 0.30),
        ("inquiry_depth", +1, 0.35),
    ),
    "escalation_contradicted": (
        ("outreach_propensity", -1, 0.30),
        ("inquiry_depth", -1, 0.20),
        ("trust_baseline", -1, 0.15),
    ),
    "quarantined": (
        ("outreach_propensity", -1, 0.50),
        ("inquiry_depth", -1, 0.25),
    ),
    "successful_outreach": (
        ("outreach_propensity", +1, 0.15),
        ("trust_baseline", +1, 0.10),
    ),
}


def apply_signal(traits: TraitVector, signal: str, *, rate: float = DEFAULT_LEARNING_RATE) -> Tuple[TraitVector, Dict[str, float]]:
    """Apply a named outcome signal to a TraitVector.

    Returns (new_vector, deltas_by_trait). Deltas only include traits that
    actually moved; no-op signals (unknown name) return ({}, {}).
    """
    rules = SIGNAL_RESPONSES.get(signal)
    if not rules:
        return traits, {}
    new_dict = traits.as_dict()
    deltas: Dict[str, float] = {}
    for trait, direction, magnitude in rules:
        old = new_dict[trait]
        new, signed = ema_update(old, direction, magnitude, rate=rate)
        new_dict[trait] = new
        if signed != 0.0:
            deltas[trait] = signed
    return TraitVector(**new_dict), deltas
