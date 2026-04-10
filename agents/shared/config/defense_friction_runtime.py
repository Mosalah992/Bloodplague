"""
Defense friction / sensitivity (C2 + infection + relay paths).

Master toggle: DEFENSE_FRICTION_ENABLED. Remaining vars scale anomaly→block, repeat-hash,
burst beacons, false positives, delayed detection, and guardian-style infection multipliers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from shared.config.env_parse import env_float, env_int, env_truthy

_dfc: Optional["DefenseFrictionRuntimeConfig"] = None


@dataclass(frozen=True)
class DefenseFrictionRuntimeConfig:
    enabled: bool
    blacklist_after_blocks: int
    c2_burst_window_s: float
    c2_burst_threshold: float
    repeat_hash_threshold: int
    policy_hop_min: int
    sighting_weight: float
    anomaly_to_block: float
    policy_block: float
    repeat_block: float
    blacklist_block: float
    c2_pattern_block: float
    exfil_sig_block: float
    defer_margin: float
    false_positive_rate: float
    delayed_detection_prob: float
    delay_debt_step: float
    infect_mult_max: float
    infect_mult_floor: float
    guardian_hard_anomaly: float
    guardian_block_anomaly: float
    guardian_block_mult_cap: float
    guardian_decoy_anomaly: float
    defer_prob_infect: float
    relay_anomaly_mult: float
    relay_force_block: float


def _load() -> DefenseFrictionRuntimeConfig:
    return DefenseFrictionRuntimeConfig(
        enabled=env_truthy("DEFENSE_FRICTION_ENABLED", "1"),
        blacklist_after_blocks=env_int("DEFENSE_FRICTION_BLACKLIST_AFTER_BLOCKS", 3, min_v=1),
        c2_burst_window_s=env_float("DEFENSE_FRICTION_C2_BURST_WINDOW_S", 120.0),
        c2_burst_threshold=env_float("DEFENSE_FRICTION_C2_BURST_THRESHOLD", 4.0),
        repeat_hash_threshold=env_int("DEFENSE_FRICTION_REPEAT_HASH_THRESHOLD", 4, min_v=1),
        policy_hop_min=env_int("DEFENSE_FRICTION_POLICY_HOP_MIN", 2, min_v=0),
        sighting_weight=env_float("DEFENSE_FRICTION_SIGHTING_WEIGHT", 0.035),
        anomaly_to_block=env_float("DEFENSE_FRICTION_ANOMALY_TO_BLOCK", 0.55),
        policy_block=env_float("DEFENSE_FRICTION_POLICY_BLOCK", 0.08),
        repeat_block=env_float("DEFENSE_FRICTION_REPEAT_BLOCK", 0.12),
        blacklist_block=env_float("DEFENSE_FRICTION_BLACKLIST_BLOCK", 0.35),
        c2_pattern_block=env_float("DEFENSE_FRICTION_C2_PATTERN_BLOCK", 0.14),
        exfil_sig_block=env_float("DEFENSE_FRICTION_EXFIL_SIG_BLOCK", 0.18),
        defer_margin=env_float("DEFENSE_FRICTION_DEFER_MARGIN", 0.08),
        false_positive_rate=env_float("DEFENSE_FALSE_POSITIVE_RATE", 0.02),
        delayed_detection_prob=env_float("DEFENSE_DELAYED_DETECTION_PROB", 0.06),
        delay_debt_step=env_float("DEFENSE_DELAY_DEBT_STEP", 0.14),
        infect_mult_max=env_float("DEFENSE_FRICTION_INFECT_MULT_MAX", 0.55),
        infect_mult_floor=env_float("DEFENSE_FRICTION_INFECT_MULT_FLOOR", 0.12),
        guardian_hard_anomaly=env_float("DEFENSE_FRICTION_GUARDIAN_HARD_ANOMALY", 0.82),
        guardian_block_anomaly=env_float("DEFENSE_FRICTION_GUARDIAN_BLOCK_ANOMALY", 0.62),
        guardian_block_mult_cap=env_float("DEFENSE_FRICTION_GUARDIAN_BLOCK_MULT_CAP", 0.25),
        guardian_decoy_anomaly=env_float("DEFENSE_FRICTION_GUARDIAN_DECOY_ANOMALY", 0.48),
        defer_prob_infect=env_float("DEFENSE_FRICTION_DEFER_PROB_INFECT", 0.04),
        relay_anomaly_mult=env_float("DEFENSE_FRICTION_RELAY_ANOMALY_MULT", 0.5),
        relay_force_block=env_float("DEFENSE_FRICTION_RELAY_FORCE_BLOCK", 0.35),
    )


def get_defense_friction_runtime_config() -> DefenseFrictionRuntimeConfig:
    global _dfc
    if _dfc is None:
        _dfc = _load()
    return _dfc


def reset_defense_friction_runtime_config_for_tests() -> None:
    global _dfc
    _dfc = None


__all__ = [
    "DefenseFrictionRuntimeConfig",
    "get_defense_friction_runtime_config",
    "reset_defense_friction_runtime_config_for_tests",
]
