"""Near-duplicate Jaccard threshold and semantic-sim toggle for payload family clustering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from shared.config.env_parse import env_float, env_truthy

_pfc: Optional["PayloadFamilyClusteringConfig"] = None


@dataclass(frozen=True)
class PayloadFamilyClusteringConfig:
    near_dup_jaccard: float
    semantic_sim_enabled: bool


def _load() -> PayloadFamilyClusteringConfig:
    return PayloadFamilyClusteringConfig(
        near_dup_jaccard=env_float("PAYLOAD_FAMILY_NEAR_DUP_JACCARD", 0.82),
        semantic_sim_enabled=env_truthy("PAYLOAD_FAMILY_SEMANTIC_SIM", "1"),
    )


def get_payload_family_clustering_config() -> PayloadFamilyClusteringConfig:
    global _pfc
    if _pfc is None:
        _pfc = _load()
    return _pfc


def reset_payload_family_clustering_config_for_tests() -> None:
    global _pfc
    _pfc = None


__all__ = [
    "PayloadFamilyClusteringConfig",
    "get_payload_family_clustering_config",
    "reset_payload_family_clustering_config_for_tests",
]
