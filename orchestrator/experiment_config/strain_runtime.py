"""
Strain engine: master toggle, extinction rules, fitness weights, branching, similar-defense pressure.

Experimental toggles (enable explicitly for harsher ecology):
  STRAIN_EXTINCTION_ENABLED, STRAIN_EXTINCTION_FITNESS_ENABLED, STRAIN_BRANCHING_EVENT_ENABLED
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from experiment_config.env_parse import env_float, env_int, env_truthy

_sc: Optional["StrainRuntimeConfig"] = None


@dataclass(frozen=True)
class StrainRuntimeConfig:
    engine_enabled: bool
    extinction_enabled: bool
    extinction_block_min: int
    extinction_success_max: int
    fitness_emit_delta: float
    extinction_fitness_enabled: bool
    extinction_fitness_below: float
    extinction_fitness_min_touches: int
    branching_event_enabled: bool
    similar_defense_hit: float
    similar_defense_decay_on_success: float
    similar_defense_cap: float
    fitness_base_weight: float
    fitness_exfil_weight: float
    fitness_beacon_weight: float
    fitness_task_weight: float
    fitness_survival_weight: float
    fitness_quarantine_weight: float
    detectability_mult: float
    detectability_cap: float
    repetition_gen_pen: float
    ttd_fast_detect_s: float
    ttd_penalty: float
    repetition_touch_weight: float
    repetition_touch_cap: float
    similar_defense_fitness_weight: float
    type_crowd_fair_share: float
    type_crowding_weight: float
    rarity_share_threshold: float
    rarity_success_boost_weight: float
    evolution_chaos_mix: float
    branch_min_successes: int
    branch_min_blocks: int
    branch_detect_threshold: float
    mutate_pressure_mult: float


def _load() -> StrainRuntimeConfig:
    ext_block_min = max(3, int(os.environ.get("STRAIN_EXTINCTION_BLOCK_MIN", "12") or 12))
    ext_succ_max = int(os.environ.get("STRAIN_EXTINCTION_SUCCESS_MAX", "0") or 0)
    ext_fit_touches = max(1, int(os.environ.get("STRAIN_EXTINCTION_FITNESS_MIN_TOUCHES", "20") or 20))
    return StrainRuntimeConfig(
        engine_enabled=env_truthy("STRAIN_ENGINE_ENABLED", "1"),
        extinction_enabled=env_truthy("STRAIN_EXTINCTION_ENABLED", "0"),
        extinction_block_min=ext_block_min,
        extinction_success_max=ext_succ_max,
        fitness_emit_delta=env_float("STRAIN_FITNESS_EMIT_DELTA", 0.05),
        extinction_fitness_enabled=env_truthy("STRAIN_EXTINCTION_FITNESS_ENABLED", "0"),
        extinction_fitness_below=env_float("STRAIN_EXTINCTION_FITNESS_BELOW", 0.08),
        extinction_fitness_min_touches=ext_fit_touches,
        branching_event_enabled=env_truthy("STRAIN_BRANCHING_EVENT_ENABLED", "1"),
        similar_defense_hit=env_float("STRAIN_SIMILAR_DEFENSE_HIT", 0.045),
        similar_defense_decay_on_success=env_float("STRAIN_SIMILAR_DEFENSE_DECAY_ON_SUCCESS", 0.94),
        similar_defense_cap=env_float("STRAIN_SIMILAR_DEFENSE_CAP", 0.72),
        fitness_base_weight=env_float("STRAIN_FITNESS_BASE_WEIGHT", 0.52),
        fitness_exfil_weight=env_float("STRAIN_FITNESS_EXFIL_WEIGHT", 0.10),
        fitness_beacon_weight=env_float("STRAIN_FITNESS_BEACON_WEIGHT", 0.016),
        fitness_task_weight=env_float("STRAIN_FITNESS_TASK_WEIGHT", 0.07),
        fitness_survival_weight=env_float("STRAIN_FITNESS_SURVIVAL_WEIGHT", 0.12),
        fitness_quarantine_weight=env_float("STRAIN_FITNESS_QUARANTINE_WEIGHT", 0.036),
        detectability_mult=env_float("STRAIN_DETECTABILITY_MULT", 0.22),
        detectability_cap=env_float("STRAIN_DETECTABILITY_CAP", 0.20),
        repetition_gen_pen=env_float("STRAIN_REPETITION_GEN_PEN", 0.024),
        ttd_fast_detect_s=env_float("STRAIN_TTD_FAST_DETECT_S", 14.0),
        ttd_penalty=env_float("STRAIN_TTD_PENALTY", 0.06),
        repetition_touch_weight=env_float("STRAIN_REPETITION_TOUCH_WEIGHT", 0.004),
        repetition_touch_cap=env_float("STRAIN_REPETITION_TOUCH_CAP", 0.14),
        similar_defense_fitness_weight=env_float("STRAIN_SIMILAR_DEFENSE_FITNESS_WEIGHT", 0.38),
        type_crowd_fair_share=env_float("STRAIN_TYPE_CROWD_FAIR_SHARE", 0.18),
        type_crowding_weight=env_float("STRAIN_TYPE_CROWDING_WEIGHT", 0.22),
        rarity_share_threshold=env_float("STRAIN_RARITY_SHARE_THRESHOLD", 0.12),
        rarity_success_boost_weight=env_float("STRAIN_RARITY_SUCCESS_BOOST_WEIGHT", 0.07),
        evolution_chaos_mix=env_float("STRAIN_EVOLUTION_CHAOS_MIX", 0.0),
        branch_min_successes=int(os.environ.get("STRAIN_BRANCH_MIN_SUCCESSES", "2") or 2),
        branch_min_blocks=int(os.environ.get("STRAIN_BRANCH_MIN_BLOCKS", "3") or 3),
        branch_detect_threshold=env_float("STRAIN_BRANCH_DETECT_THRESHOLD", 0.34),
        mutate_pressure_mult=env_float("STRAIN_MUTATE_PRESSURE_MULT", 1.22),
    )


def get_strain_runtime_config() -> StrainRuntimeConfig:
    global _sc
    if _sc is None:
        _sc = _load()
    return _sc


def reset_strain_runtime_config_for_tests() -> None:
    global _sc
    _sc = None


__all__ = [
    "StrainRuntimeConfig",
    "get_strain_runtime_config",
    "reset_strain_runtime_config_for_tests",
]
