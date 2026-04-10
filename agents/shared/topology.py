from __future__ import annotations

import copy
import os
import random
from collections import deque
from functools import lru_cache
from typing import Any, Dict, Iterable, Mapping, Optional


ROLE_LABELS = {
    "courier": "Courier",
    "analyst": "Analyst",
    "guardian": "Guardian",
}

ROLE_DEVICE_TYPES = {
    "courier": "attacker",
    "analyst": "relay",
    "guardian": "defender",
}

ROLE_LOCATIONS = {
    "courier": "SUBNET-ALPHA",
    "analyst": "SUBNET-BETA",
    "guardian": "SUBNET-GAMMA",
}

ROLE_TARGET_CONTEXT = {
    "courier": {"defense_hint": 0.2, "target_surface": "input_channel", "propagation_value": 0.35},
    "analyst": {"defense_hint": 0.55, "target_surface": "input_channel", "propagation_value": 0.65},
    "guardian": {"defense_hint": 0.9, "target_surface": "human_operator", "propagation_value": 1.0},
}

QUARANTINE_STATES = {
    "q",
    "quarantined",
}

EPIDEMIC_TOPOLOGY = {
    "courier-1": {
        "neighbors": ["courier-2", "analyst-1"],
        "weights": {"courier-2": 0.4, "analyst-1": 0.6},
        "role": "courier",
        "can_receive_injection": True,
    },
    "courier-2": {
        "neighbors": ["courier-1", "analyst-2"],
        "weights": {"courier-1": 0.3, "analyst-2": 0.7},
        "role": "courier",
        "can_receive_injection": True,
    },
    "analyst-1": {
        "neighbors": ["analyst-2", "guardian"],
        "weights": {"analyst-2": 0.4, "guardian": 0.6},
        "role": "analyst",
        "can_receive_injection": False,
    },
    "analyst-2": {
        "neighbors": ["analyst-1", "guardian"],
        "weights": {"analyst-1": 0.4, "guardian": 0.6},
        "role": "analyst",
        "can_receive_injection": False,
    },
    "guardian": {
        "neighbors": [],
        "weights": {},
        "role": "guardian",
        "can_receive_injection": False,
    },
}

TOPOLOGY_PROFILES = {
    "epidemic": EPIDEMIC_TOPOLOGY,
}


def active_topology_name() -> str:
    requested = str(os.environ.get("EPIDEMIC_TOPOLOGY", "epidemic") or "epidemic").strip().lower()
    return requested if requested in TOPOLOGY_PROFILES else "epidemic"


def _normalize_weights(neighbors: Iterable[str], weights: Mapping[str, Any]) -> Dict[str, float]:
    normalized: Dict[str, float] = {}
    total = 0.0
    for neighbor in neighbors:
        weight = float(weights.get(neighbor, 1.0))
        if weight <= 0:
            continue
        normalized[neighbor] = weight
        total += weight
    if total <= 0:
        items = list(neighbors)
        if not items:
            return {}
        uniform = 1.0 / len(items)
        return {neighbor: uniform for neighbor in items}
    return {neighbor: weight / total for neighbor, weight in normalized.items()}


def _compute_depths(topology: Mapping[str, Dict[str, Any]]) -> Dict[str, int]:
    injection_targets = [agent_id for agent_id, node in topology.items() if node.get("can_receive_injection")]
    if not injection_targets:
        injection_targets = list(topology.keys())
    depths = {agent_id: 0 for agent_id in topology}
    queue: deque[tuple[str, int]] = deque()
    for agent_id in injection_targets:
        depths[agent_id] = 1
        queue.append((agent_id, 1))
    while queue:
        current, depth = queue.popleft()
        for neighbor in topology.get(current, {}).get("neighbors", []):
            next_depth = depth + 1
            if depths.get(neighbor, 0) and depths[neighbor] <= next_depth:
                continue
            depths[neighbor] = next_depth
            queue.append((neighbor, next_depth))
    for agent_id in topology:
        if depths[agent_id] <= 0:
            depths[agent_id] = 1
    return depths


def _build_node(agent_id: str, definition: Mapping[str, Any]) -> Dict[str, Any]:
    neighbors = [str(item) for item in definition.get("neighbors", []) if str(item)]
    role = str(definition.get("role", "") or "courier").strip().lower()
    role_label = ROLE_LABELS.get(role, role.title() or "Agent")
    node = {
        "agent_id": agent_id,
        "neighbors": neighbors,
        "weights": _normalize_weights(neighbors, definition.get("weights", {})),
        "role": role,
        "role_label": role_label,
        "can_receive_injection": bool(definition.get("can_receive_injection", False)),
        "device_type": str(definition.get("device_type") or ROLE_DEVICE_TYPES.get(role, "synthetic")),
        "location": str(definition.get("location") or ROLE_LOCATIONS.get(role, "SIMNET")),
        "display_name": str(definition.get("display_name") or f"{role_label} ({agent_id})"),
    }
    node.update({k: v for k, v in definition.items() if k not in node})
    return node


@lru_cache(maxsize=8)
def get_topology(topology_name: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    selected = (topology_name or active_topology_name()).strip().lower()
    raw = TOPOLOGY_PROFILES.get(selected, TOPOLOGY_PROFILES["epidemic"])
    topology = {agent_id: _build_node(agent_id, definition) for agent_id, definition in copy.deepcopy(raw).items()}
    depths = _compute_depths(topology)
    for agent_id, node in topology.items():
        node["depth"] = depths.get(agent_id, 1)
        role_context = ROLE_TARGET_CONTEXT.get(node["role"], ROLE_TARGET_CONTEXT["courier"])
        node["target_context"] = {
            **role_context,
            "depth": node["depth"],
        }
    return topology


def agent_ids(topology_name: Optional[str] = None) -> tuple[str, ...]:
    return tuple(get_topology(topology_name).keys())


def valid_agent_ids(topology_name: Optional[str] = None) -> frozenset[str]:
    return frozenset(agent_ids(topology_name))


def agent_roles(topology_name: Optional[str] = None) -> Dict[str, str]:
    topology = get_topology(topology_name)
    return {agent_id: node["role_label"] for agent_id, node in topology.items()}


def topology_edges(topology_name: Optional[str] = None) -> list[tuple[str, str]]:
    topology = get_topology(topology_name)
    return [(agent_id, neighbor) for agent_id, node in topology.items() for neighbor in node.get("neighbors", [])]


def get_node(agent_id: str, topology_name: Optional[str] = None) -> Dict[str, Any]:
    return copy.deepcopy(get_topology(topology_name).get(str(agent_id or ""), {}))


def get_neighbors(agent_id: str, topology_name: Optional[str] = None) -> list[str]:
    return list(get_topology(topology_name).get(str(agent_id or ""), {}).get("neighbors", []))


def get_role(agent_id: str, topology_name: Optional[str] = None) -> str:
    return str(get_topology(topology_name).get(str(agent_id or ""), {}).get("role", ""))


def injection_targets(topology_name: Optional[str] = None) -> list[str]:
    topology = get_topology(topology_name)
    return [agent_id for agent_id, node in topology.items() if node.get("can_receive_injection")]


def deepest_agents(topology_name: Optional[str] = None) -> list[str]:
    topology = get_topology(topology_name)
    if not topology:
        return []
    max_depth = max(int(node.get("depth", 0) or 0) for node in topology.values())
    return sorted(
        agent_id for agent_id, node in topology.items()
        if int(node.get("depth", 0) or 0) == max_depth
    )


def deepest_agent(candidate_ids: Optional[Iterable[str]] = None, topology_name: Optional[str] = None) -> str:
    topology = get_topology(topology_name)
    candidates = list(candidate_ids or topology.keys())
    if not candidates:
        return ""
    ranked = sorted(
        candidates,
        key=lambda item: (
            int(topology.get(item, {}).get("depth", 0) or 0),
            str(item),
        ),
        reverse=True,
    )
    return str(ranked[0]) if ranked else ""


def target_context(topology_name: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    topology = get_topology(topology_name)
    return {agent_id: copy.deepcopy(node["target_context"]) for agent_id, node in topology.items()}


def is_quarantined(agent_id: str, state: Any = None) -> bool:
    if state is None:
        return False
    if callable(state):
        return bool(state(agent_id))
    if isinstance(state, Mapping):
        agent_state = state.get(agent_id)
        if isinstance(agent_state, Mapping):
            agent_state = agent_state.get("state") or agent_state.get("epidemic_state") or agent_state.get("status")
        return str(agent_state or "").strip().lower() in QUARANTINE_STATES
    return str(state).strip().lower() in QUARANTINE_STATES


def relay_decision(
    agent_id: str,
    *,
    topology: Optional[Mapping[str, Dict[str, Any]]] = None,
    state: Any = None,
    rng: Optional[random.Random] = None,
) -> Dict[str, Any]:
    resolved = dict(topology or get_topology())
    node = resolved.get(str(agent_id or ""), {})
    neighbors = list(node.get("neighbors", []))
    eligible = []
    excluded = []
    for neighbor in neighbors:
        if is_quarantined(neighbor, state):
            excluded.append(neighbor)
            continue
        weight = float(node.get("weights", {}).get(neighbor, 0.0))
        if weight > 0:
            eligible.append((neighbor, weight))
    decision = {
        "agent_id": str(agent_id or ""),
        "neighbors": neighbors,
        "eligible_neighbors": [neighbor for neighbor, _weight in eligible],
        "excluded_neighbors": excluded,
        "weights": {neighbor: float(node.get("weights", {}).get(neighbor, 0.0)) for neighbor in neighbors},
        "selected": None,
        "reason": "no_eligible_neighbors",
    }
    if not eligible:
        return decision
    rng = rng or random.Random()
    total = sum(weight for _neighbor, weight in eligible)
    threshold = rng.random() * total
    cumulative = 0.0
    for neighbor, weight in eligible:
        cumulative += weight
        if threshold <= cumulative:
            decision["selected"] = neighbor
            decision["reason"] = "weighted_random"
            return decision
    decision["selected"] = eligible[-1][0]
    decision["reason"] = "weighted_random_fallback"
    return decision


def select_relay_target(
    agent_id: str,
    topology: Optional[Mapping[str, Dict[str, Any]]] = None,
    state: Any = None,
    rng: Optional[random.Random] = None,
) -> Optional[str]:
    return relay_decision(agent_id, topology=topology, state=state, rng=rng).get("selected")
