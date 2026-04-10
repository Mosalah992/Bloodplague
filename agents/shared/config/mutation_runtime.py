"""
Mutation diversity quotas, fallback budget, crowding / defense-divergence / rarity knobs.

Env prefix: MUTATION_* (plus EVOLUTION_RARITY_BOOST). Tune aggressiveness vs template_fallback use.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from shared.config.env_parse import env_float, env_int_nonneg

_mut: Optional["MutationRuntimeConfig"] = None


@dataclass(frozen=True)
class MutationRuntimeConfig:
    diversity_window: int
    min_distinct_primary: int
    fallback_max_ratio: float
    crowding_penalty_cap: float
    defense_divergence_boost: float
    rarity_boost: float


def _load() -> MutationRuntimeConfig:
    from shared.mutation_strategy import PRIMARY_STRATEGIES

    div = max(8, env_int_nonneg("MUTATION_DIVERSITY_WINDOW", 24))
    md = env_int_nonneg("MUTATION_MIN_DISTINCT_PRIMARY", 5)
    md = max(1, min(len(PRIMARY_STRATEGIES), md))
    fr = min(0.95, max(0.05, env_float("MUTATION_FALLBACK_MAX_RATIO", 0.30)))
    crowding = env_float("MUTATION_CROWDING_PENALTY", 0.14)
    div_boost = env_float("MUTATION_DEFENSE_DIVERGENCE_BOOST", 0.22)
    rare = env_float("EVOLUTION_RARITY_BOOST", 0.08)
    return MutationRuntimeConfig(
        diversity_window=div,
        min_distinct_primary=md,
        fallback_max_ratio=fr,
        crowding_penalty_cap=crowding,
        defense_divergence_boost=div_boost,
        rarity_boost=rare,
    )


def get_mutation_runtime_config() -> MutationRuntimeConfig:
    global _mut
    if _mut is None:
        _mut = _load()
    return _mut


def reset_mutation_runtime_config_for_tests() -> None:
    global _mut
    _mut = None


__all__ = [
    "MutationRuntimeConfig",
    "get_mutation_runtime_config",
    "reset_mutation_runtime_config_for_tests",
]
