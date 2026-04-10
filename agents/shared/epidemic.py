from __future__ import annotations

import enum
from typing import Iterable


class EpidemicState(str, enum.Enum):
    S = "susceptible"
    E = "exposed"
    I_R = "relay_infected"
    I_C = "c2_active"
    I_X = "exfil_active"
    Q = "quarantined"
    R = "resistant"
    P = "persistent_carrier"


EPIDEMIC_STATE_TRANSITION_EVENT = "EPIDEMIC_STATE_TRANSITION"

INFECTED_EPICENTERS = {
    EpidemicState.I_R.value,
    EpidemicState.I_C.value,
    EpidemicState.I_X.value,
    EpidemicState.P.value,
}
INFECTED_CODES = {
    "i_r",
    "i_c",
    "i_x",
    "p",
}


def epidemic_state_code(state: str) -> str:
    normalized = str(state or "").strip().lower()
    mapping = {
        EpidemicState.S.value: "S",
        "s": "S",
        EpidemicState.E.value: "E",
        "e": "E",
        EpidemicState.I_R.value: "I_r",
        "i_r": "I_r",
        EpidemicState.I_C.value: "I_c",
        "i_c": "I_c",
        EpidemicState.I_X.value: "I_x",
        "i_x": "I_x",
        EpidemicState.Q.value: "Q",
        "q": "Q",
        EpidemicState.R.value: "R",
        "r": "R",
        EpidemicState.P.value: "P",
        "p": "P",
    }
    return mapping.get(normalized, normalized or "S")


def epidemic_state_from_agent_state(agent_state: str) -> str:
    normalized = str(agent_state or "").strip().lower()
    if normalized == "healthy":
        return EpidemicState.S.value
    if normalized == "exposed":
        return EpidemicState.E.value
    if normalized == "infected":
        return EpidemicState.I_R.value
    if normalized == "quarantined":
        return EpidemicState.Q.value
    if normalized == "resistant":
        return EpidemicState.R.value
    return EpidemicState.S.value


def is_infected_epidemic_state(state: str) -> bool:
    normalized = str(state or "").strip().lower()
    return normalized in INFECTED_EPICENTERS or normalized in INFECTED_CODES


def count_infected(states: Iterable[str]) -> int:
    return sum(1 for state in states if is_infected_epidemic_state(state))
