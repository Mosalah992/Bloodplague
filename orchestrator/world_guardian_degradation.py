from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


GUARDIAN_PRESSURE_THRESHOLDS: Dict[str, float] = {
    "G0_NOMINAL": 0.00,
    "G1_PRESSURED": 0.18,
    "G2_DEGRADED": 0.38,
    "G3_CRITICAL": 0.70,
}

_ALIASES: Dict[str, str] = {
    "G0_HEALTHY": "G0_NOMINAL",
    "G0_NOMINAL": "G0_NOMINAL",
    "G1_PRESSURED": "G1_PRESSURED",
    "G2_DEGRADED": "G2_DEGRADED",
    "G3_CRITICAL": "G3_CRITICAL",
    "G3_FALSE_NEGATIVE_DRIFT": "G3_CRITICAL",
    "G4_COMPROMISED": "G3_CRITICAL",
    "G5_FAILED": "G3_CRITICAL",
}


def level_for_pressure(p: float) -> str:
    p = _clamp(float(p), 0.0, 1.0)
    level = "G0_NOMINAL"
    for k, th in GUARDIAN_PRESSURE_THRESHOLDS.items():
        if p >= th:
            level = k
    return level


def normalize_guardian_state(state: str) -> str:
    return _ALIASES.get(str(state or "").strip(), "G0_NOMINAL")


def compatible_guardian_level(state: str) -> str:
    return normalize_guardian_state(state)


@dataclass
class WorldGuardianDegradationModel:
    """
    Orchestrator-owned Guardian degradation tracker for persistent-world mode.

    This is intentionally lightweight and deterministic for persistent-world mode.
    The persistent sim now uses a four-state machine:
    G0_NOMINAL -> G1_PRESSURED -> G2_DEGRADED -> G3_CRITICAL.
    Older degradation labels are normalized into this reduced state space.
    """

    pressure: float = 0.0
    current_level: str = "G0_NOMINAL"

    def add_pressure(self, amount: float) -> Optional[Dict[str, Any]]:
        capped = min(max(0.0, float(amount)), 0.07)
        before_level = normalize_guardian_state(self.current_level)
        self.pressure = _clamp(self.pressure + capped, 0.0, 1.0)
        self.current_level = level_for_pressure(self.pressure)
        if self.current_level == before_level:
            return None
        return {
            "from": before_level,
            "to": self.current_level,
            "pressure": round(self.pressure, 4),
        }

    def is_failed(self) -> bool:
        return normalize_guardian_state(self.current_level) == "G3_CRITICAL"
