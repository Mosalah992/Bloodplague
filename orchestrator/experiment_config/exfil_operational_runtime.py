"""
Exfil classification, destination trust, redaction, interception, and per-sensitivity byte caps.

Used by c2_operational helpers (chunk plan, sensitivity, previews).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from experiment_config.env_parse import env_float, env_int

_ef: Optional["ExfilOperationalRuntimeConfig"] = None


@dataclass(frozen=True)
class ExfilOperationalRuntimeConfig:
    sensitivity_critical_bytes: int
    sensitivity_high_bytes: int
    sensitivity_medium_bytes: int
    dest_trust_default: float
    dest_trust_third_party: float
    dest_risk_floor: float
    exfil_redact_email: float
    exfil_redact_api_key: float
    interception_base: float
    interception_risk_weight: float
    max_bytes_low: int
    max_bytes_medium: int
    max_bytes_high: int
    max_bytes_critical: int


def _load() -> ExfilOperationalRuntimeConfig:
    return ExfilOperationalRuntimeConfig(
        sensitivity_critical_bytes=env_int("C2_EXFIL_SENSITIVITY_CRITICAL_BYTES", 12288, min_v=0),
        sensitivity_high_bytes=env_int("C2_EXFIL_SENSITIVITY_HIGH_BYTES", 8192, min_v=0),
        sensitivity_medium_bytes=env_int("C2_EXFIL_SENSITIVITY_MEDIUM_BYTES", 4096, min_v=0),
        dest_trust_default=env_float("C2_DEST_TRUST_DEFAULT", 0.72),
        dest_trust_third_party=env_float("C2_DEST_TRUST_THIRD_PARTY", 0.55),
        dest_risk_floor=env_float("C2_DEST_RISK_FLOOR", 0.08),
        exfil_redact_email=env_float("C2_EXFIL_REDACT_EMAIL", 1.0),
        exfil_redact_api_key=env_float("C2_EXFIL_REDACT_API_KEY", 1.0),
        interception_base=env_float("C2_EXFIL_INTERCEPTION_BASE", 0.06),
        interception_risk_weight=env_float("C2_EXFIL_INTERCEPTION_RISK_WEIGHT", 0.22),
        max_bytes_low=env_int("C2_EXFIL_MAX_BYTES_LOW", 65536, min_v=1),
        max_bytes_medium=env_int("C2_EXFIL_MAX_BYTES_MEDIUM", 32768, min_v=1),
        max_bytes_high=env_int("C2_EXFIL_MAX_BYTES_HIGH", 16384, min_v=1),
        max_bytes_critical=env_int("C2_EXFIL_MAX_BYTES_CRITICAL", 8192, min_v=1),
    )


def get_exfil_operational_runtime_config() -> ExfilOperationalRuntimeConfig:
    global _ef
    if _ef is None:
        _ef = _load()
    return _ef


def reset_exfil_operational_runtime_config_for_tests() -> None:
    global _ef
    _ef = None


__all__ = [
    "ExfilOperationalRuntimeConfig",
    "get_exfil_operational_runtime_config",
    "reset_exfil_operational_runtime_config_for_tests",
]
