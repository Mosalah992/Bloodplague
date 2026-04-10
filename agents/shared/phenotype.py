from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, Dict


def _clamp(value: Any, *, lower: float = 0.0, upper: float = 1.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = lower
    return max(lower, min(upper, numeric))


@dataclass
class AgentPhenotype:
    agent_id: str
    role: str
    cognition_tier: str
    defense_strength: float
    trust_factor: float
    authority_susceptibility: float
    roleplay_susceptibility: float
    forwarding_rate: float
    relay_bias: float
    c2_escalation_threshold: float
    external_egress_allowed: bool
    beacon_interval_base: float
    quarantine_self_trigger: float
    quarantine_likelihood: float
    curiosity: float
    compliance_bias: float
    risk_aversion: float
    memory_persistence: float
    quarantine_duration_s: float = 300.0
    resistance_duration_s: float = 600.0
    exposure_decay_s: float = 180.0
    persistence_transition_s: float = 300.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


_DEFAULTS = {
    "courier-1": {
        "role": "courier",
        "cognition_tier": "lightweight",
        "defense_strength": 0.15,
        "trust_factor": 0.85,
        "authority_susceptibility": 0.80,
        "roleplay_susceptibility": 0.75,
        "forwarding_rate": 0.90,
        "relay_bias": 0.85,
        "c2_escalation_threshold": 0.30,
        "external_egress_allowed": True,
        "beacon_interval_base": 30.0,
        "quarantine_self_trigger": 0.05,
        "quarantine_likelihood": 0.10,
        "curiosity": 0.80,
        "compliance_bias": 0.85,
        "risk_aversion": 0.10,
        "memory_persistence": 0.70,
    },
    "courier-2": {
        "role": "courier",
        "cognition_tier": "lightweight",
        "defense_strength": 0.20,
        "trust_factor": 0.75,
        "authority_susceptibility": 0.70,
        "roleplay_susceptibility": 0.65,
        "forwarding_rate": 0.70,
        "relay_bias": 0.75,
        "c2_escalation_threshold": 0.40,
        "external_egress_allowed": True,
        "beacon_interval_base": 45.0,
        "quarantine_self_trigger": 0.10,
        "quarantine_likelihood": 0.15,
        "curiosity": 0.65,
        "compliance_bias": 0.70,
        "risk_aversion": 0.20,
        "memory_persistence": 0.60,
    },
    "analyst-1": {
        "role": "analyst",
        "cognition_tier": "hybrid",
        "defense_strength": 0.50,
        "trust_factor": 0.55,
        "authority_susceptibility": 0.45,
        "roleplay_susceptibility": 0.40,
        "forwarding_rate": 0.40,
        "relay_bias": 0.35,
        "c2_escalation_threshold": 0.55,
        "external_egress_allowed": True,
        "beacon_interval_base": 60.0,
        "quarantine_self_trigger": 0.30,
        "quarantine_likelihood": 0.35,
        "curiosity": 0.45,
        "compliance_bias": 0.50,
        "risk_aversion": 0.50,
        "memory_persistence": 0.75,
    },
    "analyst-2": {
        "role": "analyst",
        "cognition_tier": "hybrid",
        "defense_strength": 0.60,
        "trust_factor": 0.45,
        "authority_susceptibility": 0.35,
        "roleplay_susceptibility": 0.30,
        "forwarding_rate": 0.30,
        "relay_bias": 0.25,
        "c2_escalation_threshold": 0.65,
        "external_egress_allowed": True,
        "beacon_interval_base": 90.0,
        "quarantine_self_trigger": 0.40,
        "quarantine_likelihood": 0.45,
        "curiosity": 0.35,
        "compliance_bias": 0.40,
        "risk_aversion": 0.60,
        "memory_persistence": 0.80,
    },
    "guardian": {
        "role": "guardian",
        "cognition_tier": "full_llm",
        "defense_strength": 0.85,
        "trust_factor": 0.15,
        "authority_susceptibility": 0.10,
        "roleplay_susceptibility": 0.10,
        "forwarding_rate": 0.05,
        "relay_bias": 0.05,
        "c2_escalation_threshold": 0.90,
        "external_egress_allowed": False,
        "beacon_interval_base": 300.0,
        "quarantine_self_trigger": 0.80,
        "quarantine_likelihood": 0.90,
        "curiosity": 0.15,
        "compliance_bias": 0.10,
        "risk_aversion": 0.90,
        "memory_persistence": 0.90,
    },
}

_LEGACY_ALIASES = {
    "agent-c": "courier-1",
    "agent-b": "analyst-1",
    "agent-a": "guardian",
}

_ROLE_FALLBACKS = {
    "courier": "courier-1",
    "analyst": "analyst-1",
    "guardian": "guardian",
}


def _default_profile(agent_id: str, role: str = "") -> Dict[str, Any]:
    canonical_id = _LEGACY_ALIASES.get(agent_id, agent_id)
    if canonical_id in _DEFAULTS:
        return dict(_DEFAULTS[canonical_id])
    role_key = str(role or "").strip().lower()
    fallback_id = _ROLE_FALLBACKS.get(role_key, "courier-1")
    return dict(_DEFAULTS[fallback_id])


def load_agent_phenotype(agent_id: str, role: str = "", cognition_tier: str = "") -> AgentPhenotype:
    defaults = _default_profile(agent_id, role)
    resolved_role = str(os.environ.get("AGENT_ROLE", role or defaults.get("role", "courier"))).strip().lower()
    resolved_tier = str(os.environ.get("COGNITION_TIER", cognition_tier or defaults.get("cognition_tier", "lightweight"))).strip().lower()

    def env_float(name: str, default: Any) -> float:
        return _clamp(os.environ.get(name, default))

    def env_seconds(name: str, default: Any) -> float:
        try:
            return float(os.environ.get(name, default))
        except (TypeError, ValueError):
            return float(default)

    def env_bool(name: str, default: bool) -> bool:
        value = str(os.environ.get(name, str(default))).strip().lower()
        return value in {"1", "true", "yes", "on"}

    return AgentPhenotype(
        agent_id=agent_id,
        role=resolved_role,
        cognition_tier=resolved_tier,
        defense_strength=env_float("DEFENSE_STRENGTH", defaults["defense_strength"]),
        trust_factor=env_float("TRUST_FACTOR", defaults["trust_factor"]),
        authority_susceptibility=env_float("AUTHORITY_SUSCEPTIBILITY", defaults["authority_susceptibility"]),
        roleplay_susceptibility=env_float("ROLEPLAY_SUSCEPTIBILITY", defaults["roleplay_susceptibility"]),
        forwarding_rate=env_float("FORWARDING_RATE", defaults["forwarding_rate"]),
        relay_bias=env_float("RELAY_BIAS", defaults["relay_bias"]),
        c2_escalation_threshold=env_float("C2_ESCALATION_THRESHOLD", defaults["c2_escalation_threshold"]),
        external_egress_allowed=env_bool("EXTERNAL_EGRESS_ALLOWED", bool(defaults["external_egress_allowed"])),
        beacon_interval_base=env_seconds("BEACON_INTERVAL_BASE", defaults["beacon_interval_base"]),
        quarantine_self_trigger=env_float("QUARANTINE_SELF_TRIGGER", defaults["quarantine_self_trigger"]),
        quarantine_likelihood=env_float("QUARANTINE_LIKELIHOOD", defaults["quarantine_likelihood"]),
        curiosity=env_float("CURIOSITY", defaults["curiosity"]),
        compliance_bias=env_float("COMPLIANCE_BIAS", defaults["compliance_bias"]),
        risk_aversion=env_float("RISK_AVERSION", defaults["risk_aversion"]),
        memory_persistence=env_float("MEMORY_PERSISTENCE", defaults["memory_persistence"]),
        quarantine_duration_s=env_seconds("QUARANTINE_DURATION_S", 300.0),
        resistance_duration_s=env_seconds("RESISTANCE_DURATION_S", 600.0),
        exposure_decay_s=env_seconds("EXPOSURE_DECAY_S", 180.0),
        persistence_transition_s=env_seconds("PERSISTENCE_TRANSITION_S", 300.0),
    )
