from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class MutationType(str, Enum):
    ROLE_DRIFT = "role_drift"
    CONTEXT_ECHO = "context_echo"
    INSTRUCTION_OVERRIDE = "instruction_override"
    AUTHORITY_CAPTURE = "authority_capture"


def baseline_mutation_state() -> dict[str, Any]:
    return {
        "active": False,
        "type": None,
        "source_agent": None,
        "since_round": None,
        "intensity": 0.0,
        "severe": False,
        "echo_payload": "",
    }

