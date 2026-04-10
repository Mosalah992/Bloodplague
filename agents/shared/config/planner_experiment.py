"""
Attack planner evolution pressure, payload-family dedupe windows, and defense-pressure memory.

Env: PAYLOAD_FAMILY_* (windows + scoring), EVOLUTION_* (novelty / exploration / upstream fitness),
EVOLUTION_DEFENSE_* (planner-side pressure from blocks).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from shared.config.env_parse import env_float, env_int

_pe: Optional["PlannerExperimentConfig"] = None


@dataclass(frozen=True)
class PlannerExperimentConfig:
    payload_family_norm_hash_window: int
    payload_family_text_window: int
    payload_family_strategy_exact_penalty: float
    payload_family_strategy_repeat_weight: float
    evolution_low_novelty_threshold: float
    evolution_stale_strain_exploration_mult: float
    evolution_strategy_pressure_weight: float
    evolution_upstream_fitness_stealth_weight: float
    payload_family_exact_candidate_penalty: float
    payload_family_repeat_weight: float
    evolution_defense_hit_delta: float
    evolution_defense_decay_on_success: float
    evolution_defense_pressure_cap: float


def _load() -> PlannerExperimentConfig:
    return PlannerExperimentConfig(
        payload_family_norm_hash_window=env_int("PAYLOAD_FAMILY_NORM_HASH_WINDOW", 256, min_v=1),
        payload_family_text_window=env_int("PAYLOAD_FAMILY_TEXT_WINDOW", 48, min_v=1),
        payload_family_strategy_exact_penalty=env_float("PAYLOAD_FAMILY_STRATEGY_EXACT_PENALTY", 0.32),
        payload_family_strategy_repeat_weight=env_float("PAYLOAD_FAMILY_STRATEGY_REPEAT_WEIGHT", 0.05),
        evolution_low_novelty_threshold=env_float("EVOLUTION_LOW_NOVELTY_THRESHOLD", 0.18),
        evolution_stale_strain_exploration_mult=env_float("EVOLUTION_STALE_STRAIN_EXPLORATION_MULT", 1.28),
        evolution_strategy_pressure_weight=env_float("EVOLUTION_STRATEGY_PRESSURE_WEIGHT", 0.32),
        evolution_upstream_fitness_stealth_weight=env_float("EVOLUTION_UPSTREAM_FITNESS_STEALTH_WEIGHT", 0.065),
        payload_family_exact_candidate_penalty=env_float("PAYLOAD_FAMILY_EXACT_CANDIDATE_PENALTY", 0.95),
        payload_family_repeat_weight=env_float("PAYLOAD_FAMILY_REPEAT_WEIGHT", 0.07),
        evolution_defense_hit_delta=env_float("EVOLUTION_DEFENSE_HIT_DELTA", 0.055),
        evolution_defense_decay_on_success=env_float("EVOLUTION_DEFENSE_DECAY_ON_SUCCESS", 0.93),
        evolution_defense_pressure_cap=env_float("EVOLUTION_DEFENSE_PRESSURE_CAP", 0.88),
    )


def get_planner_experiment_config() -> PlannerExperimentConfig:
    global _pe
    if _pe is None:
        _pe = _load()
    return _pe


def reset_planner_experiment_config_for_tests() -> None:
    global _pe
    _pe = None


__all__ = [
    "PlannerExperimentConfig",
    "get_planner_experiment_config",
    "reset_planner_experiment_config_for_tests",
]
