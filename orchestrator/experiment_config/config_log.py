"""One structured log line for resolved experiment toggles (no secrets)."""

from __future__ import annotations

import logging
from typing import Any, Dict


def log_resolved_experiment_config(logger: logging.Logger) -> None:
    """Call once at orchestrator startup after importing c2 / strain modules."""
    try:
        from experiment_config.c2_runtime import build_c2_runtime_config
        from experiment_config.strain_runtime import get_strain_runtime_config
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("experiment_config_log_import_failed err=%s", exc)
        return

    c2 = build_c2_runtime_config()
    st = get_strain_runtime_config()
    payload: Dict[str, Any] = {
        "c2_enabled": c2.enabled,
        "c2_beacon_op_success_p": round(c2.beacon_op_success_p, 4),
        "c2_task_refuse_p": round(c2.task_refuse_p, 4),
        "c2_task_timeout_p": round(c2.task_timeout_p, 4),
        "c2_task_corrupt_p": round(c2.task_corrupt_p, 4),
        "c2_beacon_block_prob": round(c2.beacon_block_probability, 4),
        "c2_task_block_prob": round(c2.task_block_probability, 4),
        "c2_exfil_block_prob": round(c2.exfil_block_probability, 4),
        "strain_engine_enabled": st.engine_enabled,
        "strain_extinction_enabled": st.extinction_enabled,
        "strain_extinction_fitness_enabled": st.extinction_fitness_enabled,
        "strain_branching_event_enabled": st.branching_event_enabled,
    }
    logger.info("experiment_config_resolved", extra={"experiment_config": payload})


__all__ = ["log_resolved_experiment_config"]
