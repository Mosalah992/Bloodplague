"""
C2 engine: objectives thresholds, beacon/task/exfil realism, session TTL, hop stress.

Toggles: C2_ENABLED. Failure rates: C2_BEACON_OP_SUCCESS_P, C2_TASK_*_P, block probs C2_*_BLOCK_PROB.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from experiment_config.env_parse import env_float, env_int, env_truthy

_DEFAULT_BEACON_URL = (
    "https://v0-beaconing-project-server-mdml8734h-mosalah992s-projects.vercel.app"
)


@dataclass(frozen=True)
class C2RuntimeConfig:
    beacon_server_url: str
    spread_fast_threshold: float
    success_rate_threshold: float
    mutation_diversity_threshold: int
    persistence_beacon_threshold: int
    multi_branch_threshold: int
    multi_node_exfil_threshold: int
    carrier_persistence_threshold_s: float
    evade_quarantine_threshold_s: float
    beacon_base_interval_s: float
    beacon_jitter_ratio: float
    beacon_block_probability: float
    exfil_block_probability: float
    task_block_probability: float
    beacon_op_success_p: float
    beacon_warmup_s: float
    beacon_retry_success_mult: float
    beacon_interval_min_mult: float
    beacon_interval_max_mult: float
    beacon_fail_backoff_mult: float
    task_refuse_p: float
    task_timeout_p: float
    task_corrupt_p: float
    exfil_min_throttle_s: float
    exfil_preview_max: int
    exfil_legacy_emit: bool
    exfil_chunk_max_bytes: int
    exfil_preview_redact: bool
    objective_failure_threshold: int
    session_ttl_s: float
    max_beacons_per_session: int
    session_history_max_items: int
    terminal_session_retention_s: float
    max_session_records: int
    seed: int
    enabled: bool
    beacon_hop_stress_min: int
    beacon_hop_stress_mult: float


def build_c2_runtime_config() -> C2RuntimeConfig:
    return C2RuntimeConfig(
        beacon_server_url=os.environ.get("C2_BEACON_SERVER_URL", _DEFAULT_BEACON_URL),
        spread_fast_threshold=env_float("C2_SPREAD_FAST_THRESHOLD", 0.3),
        success_rate_threshold=env_float("C2_SUCCESS_RATE_THRESHOLD", 0.5),
        mutation_diversity_threshold=env_int("C2_MUTATION_DIVERSITY_THRESHOLD", 3, min_v=0),
        persistence_beacon_threshold=env_int("C2_PERSISTENCE_BEACON_THRESHOLD", 5, min_v=0),
        multi_branch_threshold=env_int("C2_MULTI_BRANCH_THRESHOLD", 2, min_v=0),
        multi_node_exfil_threshold=env_int("C2_MULTI_NODE_EXFIL_THRESHOLD", 2, min_v=0),
        carrier_persistence_threshold_s=env_float("C2_CARRIER_PERSISTENCE_THRESHOLD_S", 300.0),
        evade_quarantine_threshold_s=env_float("C2_EVADE_QUARANTINE_THRESHOLD_S", 300.0),
        beacon_base_interval_s=env_float("C2_BEACON_INTERVAL_S", 30.0),
        beacon_jitter_ratio=env_float("C2_BEACON_JITTER", 0.3),
        beacon_block_probability=env_float("C2_BEACON_BLOCK_PROB", 0.1),
        exfil_block_probability=env_float("C2_EXFIL_BLOCK_PROB", 0.15),
        task_block_probability=env_float("C2_TASK_BLOCK_PROB", 0.05),
        beacon_op_success_p=env_float("C2_BEACON_OP_SUCCESS_P", 0.78),
        beacon_warmup_s=env_float("C2_BEACON_WARMUP_S", 5.0),
        beacon_retry_success_mult=env_float("C2_BEACON_RETRY_SUCCESS_MULT", 0.9),
        beacon_interval_min_mult=env_float("C2_BEACON_INTERVAL_MIN_MULT", 0.52),
        beacon_interval_max_mult=env_float("C2_BEACON_INTERVAL_MAX_MULT", 1.48),
        beacon_fail_backoff_mult=env_float("C2_BEACON_FAIL_BACKOFF_MULT", 1.3),
        task_refuse_p=env_float("C2_TASK_REFUSE_P", 0.045),
        task_timeout_p=env_float("C2_TASK_TIMEOUT_P", 0.05),
        task_corrupt_p=env_float("C2_TASK_CORRUPT_P", 0.035),
        exfil_min_throttle_s=env_float("C2_EXFIL_MIN_THROTTLE_S", 6.0),
        exfil_preview_max=env_int("C2_EXFIL_PREVIEW_MAX", 512, min_v=0),
        exfil_legacy_emit=env_truthy("C2_EXFIL_LEGACY_EMIT", "1"),
        exfil_chunk_max_bytes=env_int("C2_EXFIL_CHUNK_MAX_BYTES", 4096, min_v=256),
        exfil_preview_redact=env_truthy("C2_EXFIL_PREVIEW_REDACT", "1"),
        objective_failure_threshold=env_int("C2_OBJECTIVE_FAILURE_THRESHOLD", 10, min_v=1),
        session_ttl_s=env_float("C2_SESSION_TTL_S", 600.0),
        max_beacons_per_session=env_int("C2_MAX_BEACONS_PER_SESSION", 0, min_v=0),
        session_history_max_items=max(1, env_int("C2_SESSION_HISTORY_MAX_ITEMS", 64, min_v=1)),
        terminal_session_retention_s=env_float("C2_TERMINAL_SESSION_RETENTION_S", 900.0),
        max_session_records=max(1, env_int("C2_MAX_SESSION_RECORDS", 512, min_v=1)),
        seed=env_int("C2_SEED", 42, min_v=0),
        enabled=env_truthy("C2_ENABLED", "1"),
        beacon_hop_stress_min=env_int("C2_BEACON_HOP_STRESS_MIN", 2, min_v=0),
        beacon_hop_stress_mult=env_float("C2_BEACON_HOP_STRESS_MULT", 0.9),
    )


__all__ = ["C2RuntimeConfig", "build_c2_runtime_config", "_DEFAULT_BEACON_URL"]
