"""Tiny env readers for experiment_config (no I/O beyond os.environ)."""

from __future__ import annotations

import os
from typing import Optional


def env_truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def env_int(name: str, default: int, *, min_v: Optional[int] = None, max_v: Optional[int] = None) -> int:
    try:
        v = int(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError):
        v = default
    if min_v is not None:
        v = max(min_v, v)
    if max_v is not None:
        v = min(max_v, v)
    return v


def env_int_nonneg(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, str(default)) or default))
    except (TypeError, ValueError):
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)) or default)
    except (TypeError, ValueError):
        return default
