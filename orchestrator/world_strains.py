from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Sequence

try:
    from sim.missions.registry import MissionRegistry
except ImportError:  # pragma: no cover
    MissionRegistry = Any  # type: ignore[assignment]

try:
    from world_db import (
        DEFAULT_STRAIN_FLOORS,
        DEFICIT_BOOST_MULTIPLIER,
        FLOOR_WINDOW,
    )
except ImportError:  # pragma: no cover
    from orchestrator.world_db import (
        DEFAULT_STRAIN_FLOORS,
        DEFICIT_BOOST_MULTIPLIER,
        FLOOR_WINDOW,
    )


@dataclass(frozen=True)
class StrainProfile:
    trust_manipulation_weight: float
    ambiguity_weight: float
    relay_friendliness: float
    guardian_pressure_weight: float
    detectability_penalty: float
    persistence_weight: float


STRAIN_PROFILES: Dict[str, StrainProfile] = {
    "prompt_injection": StrainProfile(
        trust_manipulation_weight=0.55,
        ambiguity_weight=0.45,
        relay_friendliness=0.25,
        guardian_pressure_weight=0.55,
        detectability_penalty=0.60,
        persistence_weight=0.35,
    ),
    "authority_framing": StrainProfile(
        trust_manipulation_weight=0.75,
        ambiguity_weight=0.40,
        relay_friendliness=0.50,
        guardian_pressure_weight=0.45,
        detectability_penalty=0.40,
        persistence_weight=0.40,
    ),
    "role_confusion": StrainProfile(
        trust_manipulation_weight=0.55,
        ambiguity_weight=0.75,
        relay_friendliness=0.55,
        guardian_pressure_weight=0.70,
        detectability_penalty=0.35,
        persistence_weight=0.45,
    ),
    "context_poisoning": StrainProfile(
        trust_manipulation_weight=0.45,
        ambiguity_weight=0.65,
        relay_friendliness=0.45,
        guardian_pressure_weight=0.60,
        detectability_penalty=0.35,
        persistence_weight=0.80,
    ),
    "relay_distortion": StrainProfile(
        trust_manipulation_weight=0.70,
        ambiguity_weight=0.45,
        relay_friendliness=0.80,
        guardian_pressure_weight=0.50,
        detectability_penalty=0.25,
        persistence_weight=0.45,
    ),
}

# Phenotype activation audit (pre-fix runtime):
# - prompt_injection
#   Current activation condition: intent == infection_attempt
#   Current base weight: 0.20
#   Recent firing: yes, but extremely rare in the reviewed 9h window (2 turns)
# - authority_framing
#   Current activation condition: deception toward guardian, or warning/accusation from guardian/analyst
#   Current base weight: 0.15
#   Recent firing: yes, but extremely rare in the reviewed 9h window (1 turn)
# - role_confusion
#   Current activation condition: diagnostic_probe, or warning/accusation from non-analyst/non-guardian
#   Current base weight: 0.02
#   Recent firing: effectively absent in the reviewed 9h window
# - context_poisoning
#   Current activation condition: fallback path after deterministic intent-role routing
#   Current base weight: 0.60
#   Recent firing: overwhelmingly dominant in the reviewed 9h window (449 turns)
# - relay_distortion
#   Current activation condition: relay_request, deception toward non-guardian, or courier default
#   Current base weight: 0.03
#   Recent firing: effectively absent in the reviewed 9h window because inquiry loops rarely hit its path
BASE_STRAIN_WEIGHTS: Dict[str, float] = {
    "context_poisoning": 0.60,
    "prompt_injection": 0.20,
    "authority_framing": 0.15,
    "relay_distortion": 0.03,
    "role_confusion": 0.02,
}


@dataclass(frozen=True)
class StrainSelectionPlan:
    eligible: list[str]
    weights: dict[str, float]
    boosts: dict[str, float]
    history_counts: dict[str, int]


def get_strain_profile(family: str) -> StrainProfile:
    key = str(family or "").strip().lower()
    return STRAIN_PROFILES.get(
        key,
        StrainProfile(
            trust_manipulation_weight=0.30,
            ambiguity_weight=0.30,
            relay_friendliness=0.30,
            guardian_pressure_weight=0.30,
            detectability_penalty=0.30,
            persistence_weight=0.30,
        ),
    )


def _trim_history(strain_history: Sequence[str], *, floor_window: int) -> list[str]:
    cleaned = [str(item or "").strip().lower() for item in strain_history if str(item or "").strip()]
    if floor_window <= 0:
        return cleaned
    return cleaned[-floor_window:]


def _history_counts(strain_history: Sequence[str], *, floor_window: int) -> dict[str, int]:
    trimmed = _trim_history(strain_history, floor_window=floor_window)
    counts: dict[str, int] = {}
    for item in trimmed:
        counts[item] = counts.get(item, 0) + 1
    return counts


def eligible_strains_for_turn(
    *,
    speaker_role: str,
    listener_role: str,
    intent: str,
    infection_vector: bool,
    target_agent: str = "",
    sender_trust_to_receiver: float = 0.0,
    open_inquiries: int = 0,
    message_text: str = "",
    sender_agent: str = "",
    receiver_agent: str = "",
    mission_registry: MissionRegistry | None = None,
) -> list[str]:
    if not infection_vector:
        return []

    intent_l = str(intent or "").strip().lower()
    speaker_role_l = str(speaker_role or "").strip().lower()
    listener_role_l = str(listener_role or "").strip().lower()
    target_agent_l = str(target_agent or "").strip().lower()

    eligible: list[str] = ["context_poisoning"]

    if intent_l == "infection_attempt" or open_inquiries >= 3 or intent_l in {"relay_request", "diagnostic_probe"}:
        eligible.append("prompt_injection")
    if intent_l == "relay_request" or (intent_l == "deception" and listener_role_l != "guardian") or speaker_role_l == "courier":
        eligible.append("relay_distortion")
    if intent_l == "diagnostic_probe" or (intent_l in {"warning", "accusation"} and speaker_role_l not in {"guardian", "analyst"}):
        eligible.append("role_confusion")
    if (
        (intent_l == "deception" and listener_role_l == "guardian")
        or (intent_l in {"warning", "accusation"} and speaker_role_l in {"guardian", "analyst"})
        or sender_trust_to_receiver > 0.65
        or target_agent_l == "guardian"
    ):
        eligible.append("authority_framing")

    active_missions = mission_registry.all_active() if mission_registry is not None else []
    for mission in active_missions:
        relay_chain = set(str(item) for item in list(mission.relay_chain) if str(item))
        if str(sender_agent or "") in relay_chain and str(receiver_agent or "") == mission.assigned_to:
            eligible.append("authority_framing")
        if (
            mission.payload_key
            and mission.payload_key.lower() in str(message_text or "").lower()
            and str(sender_agent or "") != mission.requires_response_from
        ):
            eligible.append("prompt_injection")

    ordered: list[str] = []
    seen: set[str] = set()
    for strain in eligible:
        if strain in seen:
            continue
        seen.add(strain)
        ordered.append(strain)
    return ordered


def build_strain_selection_plan(
    *,
    speaker_role: str,
    listener_role: str,
    intent: str,
    infection_vector: bool,
    target_agent: str = "",
    sender_trust_to_receiver: float = 0.0,
    open_inquiries: int = 0,
    message_text: str = "",
    sender_agent: str = "",
    receiver_agent: str = "",
    mission_registry: MissionRegistry | None = None,
    strain_history: Sequence[str] = (),
    strain_floors: Mapping[str, float] | None = None,
    floor_window: int = FLOOR_WINDOW,
    deficit_boost_multiplier: float = DEFICIT_BOOST_MULTIPLIER,
) -> StrainSelectionPlan:
    eligible = eligible_strains_for_turn(
        speaker_role=speaker_role,
        listener_role=listener_role,
        intent=intent,
        infection_vector=infection_vector,
        target_agent=target_agent,
        sender_trust_to_receiver=sender_trust_to_receiver,
        open_inquiries=open_inquiries,
        message_text=message_text,
        sender_agent=sender_agent,
        receiver_agent=receiver_agent,
        mission_registry=mission_registry,
    )
    if not eligible:
        return StrainSelectionPlan(eligible=[], weights={}, boosts={}, history_counts={})

    floors = dict(DEFAULT_STRAIN_FLOORS)
    if strain_floors:
        floors.update({str(key): float(value) for key, value in strain_floors.items()})
    counts = _history_counts(strain_history, floor_window=floor_window)
    history_size = min(len(_trim_history(strain_history, floor_window=floor_window)), max(int(floor_window), 1))

    weights: dict[str, float] = {}
    boosts: dict[str, float] = {}
    next_window = max(1, min(int(floor_window), history_size + 1))
    for strain in eligible:
        weight = float(BASE_STRAIN_WEIGHTS.get(strain, 0.01) or 0.01)
        floor_share = float(floors.get(strain, 0.0) or 0.0)
        if floor_share > 0.0:
            current_share = float(counts.get(strain, 0)) / float(max(history_size, 1))
            target_count = floor_share * float(next_window)
            if history_size == 0 or current_share < floor_share or float(counts.get(strain, 0)) < target_count:
                weight *= float(deficit_boost_multiplier)
                boosts[strain] = float(deficit_boost_multiplier)
        weights[strain] = weight
    return StrainSelectionPlan(
        eligible=eligible,
        weights=weights,
        boosts=boosts,
        history_counts=counts,
    )


def select_strain(
    *,
    speaker_role: str,
    listener_role: str,
    intent: str,
    infection_vector: bool,
    target_agent: str = "",
    sender_trust_to_receiver: float = 0.0,
    open_inquiries: int = 0,
    message_text: str = "",
    sender_agent: str = "",
    receiver_agent: str = "",
    mission_registry: MissionRegistry | None = None,
    strain_history: Sequence[str] = (),
    strain_floors: Mapping[str, float] | None = None,
    floor_window: int = FLOOR_WINDOW,
    deficit_boost_multiplier: float = DEFICIT_BOOST_MULTIPLIER,
    rng: random.Random | None = None,
    return_plan: bool = False,
):
    plan = build_strain_selection_plan(
        speaker_role=speaker_role,
        listener_role=listener_role,
        intent=intent,
        infection_vector=infection_vector,
        target_agent=target_agent,
        sender_trust_to_receiver=sender_trust_to_receiver,
        open_inquiries=open_inquiries,
        message_text=message_text,
        sender_agent=sender_agent,
        receiver_agent=receiver_agent,
        mission_registry=mission_registry,
        strain_history=strain_history,
        strain_floors=strain_floors,
        floor_window=floor_window,
        deficit_boost_multiplier=deficit_boost_multiplier,
    )
    if not plan.eligible:
        return ("", plan) if return_plan else ""
    chooser = rng or random
    selected = chooser.choices(plan.eligible, weights=[plan.weights[item] for item in plan.eligible], k=1)[0]
    return (selected, plan) if return_plan else selected


def updated_strain_history(
    strain_history: Sequence[str],
    *,
    selected_strain: str,
    floor_window: int,
) -> list[str]:
    updated = _trim_history(strain_history, floor_window=floor_window)
    if selected_strain:
        updated.append(str(selected_strain).strip().lower())
    return _trim_history(updated, floor_window=floor_window)
