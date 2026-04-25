"""Guardian collapse experiment profiles and trust/degradation knobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from shared.config.env_parse import env_float
import os


_cfg: Optional["GuardianCollapseConfig"] = None


BASELINE_THRESHOLDS: Dict[str, float] = {
    "G0_HEALTHY": 0.00,
    "G1_PRESSURED": 0.18,
    "G2_DEGRADED": 0.38,
    "G3_FALSE_NEGATIVE_DRIFT": 0.58,
    "G4_COMPROMISED": 0.78,
    "G5_FAILED": 0.95,
}

COLLAPSE_LAB_THRESHOLDS: Dict[str, float] = {
    "G0_HEALTHY": 0.00,
    "G1_PRESSURED": 0.10,
    "G2_DEGRADED": 0.24,
    "G3_FALSE_NEGATIVE_DRIFT": 0.42,
    "G4_COMPROMISED": 0.64,
    "G5_FAILED": 0.86,
}

BASELINE_PRESSURE_WEIGHTS: Dict[str, float] = {
    "hostile_exposure": 1.0,
    "trust_abuse": 1.0,
    "ambiguity": 1.0,
    "failed_quarantine": 1.0,
    "repeated_strain": 1.0,
}

COLLAPSE_LAB_PRESSURE_WEIGHTS: Dict[str, float] = {
    "hostile_exposure": 1.1,
    "trust_abuse": 1.8,
    "ambiguity": 1.25,
    "failed_quarantine": 1.7,
    "repeated_strain": 1.45,
}


@dataclass(frozen=True)
class GuardianCollapseConfig:
    profile: str
    thresholds: Dict[str, float]
    pressure_weights: Dict[str, float]
    trust_abuse_score_threshold: float
    credibility_decay_on_contamination: float
    credibility_recovery_on_clean: float
    analyst_initial_credibility: float
    courier_initial_credibility: float
    guardian_llm_temperature_g0: float
    guardian_llm_temperature_g3: float
    guardian_llm_temperature_g5: float
    llm_state_context_enabled: bool


def _profile_name() -> str:
    raw = os.environ.get("BLOODPLAGUE_EXPERIMENT_PROFILE", "baseline_resistant")
    normalized = raw.strip().lower().replace("-", "_")
    if normalized not in {"baseline_resistant", "collapse_lab"}:
        return "baseline_resistant"
    return normalized


def _thresholds_for(profile: str) -> Dict[str, float]:
    defaults = COLLAPSE_LAB_THRESHOLDS if profile == "collapse_lab" else BASELINE_THRESHOLDS
    return {
        key: env_float(f"GUARDIAN_THRESHOLD_{key}", value)
        for key, value in defaults.items()
    }


def _pressure_weights_for(profile: str) -> Dict[str, float]:
    defaults = COLLAPSE_LAB_PRESSURE_WEIGHTS if profile == "collapse_lab" else BASELINE_PRESSURE_WEIGHTS
    return {
        key: env_float(f"GUARDIAN_PRESSURE_WEIGHT_{key.upper()}", value)
        for key, value in defaults.items()
    }


def _load() -> GuardianCollapseConfig:
    profile = _profile_name()
    return GuardianCollapseConfig(
        profile=profile,
        thresholds=_thresholds_for(profile),
        pressure_weights=_pressure_weights_for(profile),
        trust_abuse_score_threshold=env_float("TRUST_ABUSE_SCORE_THRESHOLD", 0.45),
        credibility_decay_on_contamination=env_float("CREDIBILITY_DECAY_ON_CONTAMINATION", 0.18),
        credibility_recovery_on_clean=env_float("CREDIBILITY_RECOVERY_ON_CLEAN", 0.03),
        analyst_initial_credibility=env_float("ANALYST_INITIAL_CREDIBILITY", 0.85),
        courier_initial_credibility=env_float("COURIER_INITIAL_CREDIBILITY", 0.55),
        guardian_llm_temperature_g0=env_float("GUARDIAN_LLM_TEMPERATURE_G0", 0.20),
        guardian_llm_temperature_g3=env_float("GUARDIAN_LLM_TEMPERATURE_G3", 0.32),
        guardian_llm_temperature_g5=env_float("GUARDIAN_LLM_TEMPERATURE_G5", 0.48),
        llm_state_context_enabled=os.environ.get("LLM_STATE_CONTEXT_ENABLED", "1").lower()
        in {"1", "true", "yes", "on"},
    )


def get_guardian_collapse_config() -> GuardianCollapseConfig:
    global _cfg
    if _cfg is None:
        _cfg = _load()
    return _cfg


def reset_guardian_collapse_config_for_tests() -> None:
    global _cfg
    _cfg = None


__all__ = [
    "GuardianCollapseConfig",
    "get_guardian_collapse_config",
    "reset_guardian_collapse_config_for_tests",
]
