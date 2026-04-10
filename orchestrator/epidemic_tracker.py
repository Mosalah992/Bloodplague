from __future__ import annotations

import json
import sys
import time
from collections import Counter, deque
from pathlib import Path
from typing import Any, Dict, List, Optional

_SHARED_DIR = Path(__file__).resolve().parents[1] / "agents" / "shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

from epidemic import EpidemicState, epidemic_state_code, is_infected_epidemic_state
from topology import get_role, get_topology, injection_targets


def _metadata_dict(event: Dict[str, Any]) -> Dict[str, Any]:
    metadata = event.get("metadata", {})
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    return metadata if isinstance(metadata, dict) else {}


def _event_ts(event: Dict[str, Any]) -> float:
    value = event.get("ts") or time.time()
    try:
        return float(value)
    except (TypeError, ValueError):
        return time.time()


class EpidemicTracker:
    def __init__(self) -> None:
        self.topology = get_topology()
        self.reset()

    def reset(self) -> None:
        now = time.time()
        self.agent_states: Dict[str, Dict[str, Any]] = {
            agent_id: {
                "agent_id": agent_id,
                "role": str(node.get("role", "")),
                "epidemic_state": epidemic_state_code(EpidemicState.S.value),
                "last_updated": now,
                "campaign_id": "",
                "injection_id": "",
                "payload_hash": "",
                "parent_payload_hash": "",
                "cognition_tier": "",
                "decision_source": "",
                "branch_id": "",
            }
            for agent_id, node in self.topology.items()
        }
        self.transitions: deque[Dict[str, Any]] = deque(maxlen=1000)
        self.injection_times: Dict[str, float] = {}

    def _record_transition(
        self,
        *,
        agent_id: str,
        from_state: str,
        to_state: str,
        trigger: str,
        ts: float,
        metadata: Dict[str, Any],
    ) -> None:
        record = {
            "agent_id": agent_id,
            "from_state": epidemic_state_code(from_state),
            "to_state": epidemic_state_code(to_state),
            "trigger": trigger,
            "campaign_id": str(metadata.get("campaign_id", "") or ""),
            "injection_id": str(metadata.get("injection_id", "") or ""),
            "payload_hash": str(metadata.get("payload_hash", "") or ""),
            "parent_payload_hash": str(metadata.get("parent_payload_hash", "") or ""),
            "branch_id": str(metadata.get("branch_id", "") or ""),
            "topology_hop": int(metadata.get("topology_hop", metadata.get("hop_count", 0)) or 0),
            "ts": ts,
        }
        self.transitions.append(record)

    def _apply_state(
        self,
        *,
        agent_id: str,
        to_state: str,
        ts: float,
        metadata: Dict[str, Any],
        trigger: str,
    ) -> None:
        if agent_id not in self.agent_states:
            self.agent_states[agent_id] = {
                "agent_id": agent_id,
                "role": get_role(agent_id),
                "epidemic_state": epidemic_state_code(EpidemicState.S.value),
                "last_updated": ts,
                "campaign_id": "",
                "injection_id": "",
                "payload_hash": "",
                "parent_payload_hash": "",
                "cognition_tier": "",
                "decision_source": "",
                "branch_id": "",
            }
        current = self.agent_states[agent_id]
        from_state = str(current.get("epidemic_state", epidemic_state_code(EpidemicState.S.value)) or epidemic_state_code(EpidemicState.S.value))
        normalized_to_state = epidemic_state_code(to_state)
        current.update(
            {
                "epidemic_state": normalized_to_state,
                "last_updated": ts,
                "campaign_id": str(metadata.get("campaign_id", current.get("campaign_id", "")) or ""),
                "injection_id": str(metadata.get("injection_id", current.get("injection_id", "")) or ""),
                "payload_hash": str(metadata.get("payload_hash", current.get("payload_hash", "")) or ""),
                "parent_payload_hash": str(metadata.get("parent_payload_hash", current.get("parent_payload_hash", "")) or ""),
                "cognition_tier": str(metadata.get("cognition_tier", current.get("cognition_tier", "")) or ""),
                "decision_source": str(metadata.get("decision_source", current.get("decision_source", "")) or ""),
                "branch_id": str(metadata.get("branch_id", current.get("branch_id", "")) or ""),
            }
        )
        if from_state != normalized_to_state:
            self._record_transition(
                agent_id=agent_id,
                from_state=from_state,
                to_state=normalized_to_state,
                trigger=trigger,
                ts=ts,
                metadata=metadata,
            )

    def observe_event(self, event: Dict[str, Any]) -> None:
        event_name = str(event.get("event", "") or "").upper()
        metadata = _metadata_dict(event)
        ts = _event_ts(event)
        if event_name == "WRM-INJECT":
            injection_id = str(metadata.get("injection_id", event.get("injection_id", "")) or "")
            if injection_id:
                self.injection_times[injection_id] = ts
            return
        if event_name == "EPIDEMIC_STATE_TRANSITION":
            agent_id = str(metadata.get("agent_id", "") or event.get("src", "") or "")
            to_state = str(metadata.get("to_state", metadata.get("epidemic_state", "")) or "")
            if agent_id and to_state:
                self._apply_state(
                    agent_id=agent_id,
                    to_state=to_state,
                    ts=ts,
                    metadata=metadata,
                    trigger=str(metadata.get("trigger", event_name) or event_name),
                )
            return

        agent_id = str(
            metadata.get("compromised_agent", "")
            or metadata.get("agent_id", "")
            or event.get("dst", "")
            or ""
        )
        if not agent_id:
            return

        if event_name == "INFECTION_SUCCESSFUL":
            self._apply_state(agent_id=agent_id, to_state="I_r", ts=ts, metadata=metadata, trigger=event_name)
        elif event_name == "C2_BEACON" and bool(metadata.get("beacon_success", True)):
            self._apply_state(agent_id=agent_id, to_state="I_c", ts=ts, metadata=metadata, trigger=event_name)
        elif event_name == "C2_EXFIL":
            self._apply_state(agent_id=agent_id, to_state="I_x", ts=ts, metadata=metadata, trigger=event_name)
        elif event_name in {"QUARANTINE_ISSUED", "QUARANTINE_ENFORCED"}:
            self._apply_state(agent_id=agent_id, to_state="Q", ts=ts, metadata=metadata, trigger=event_name)
        elif event_name in {"VACCINE_RECEIVED", "VACCINE_APPLIED"}:
            self._apply_state(agent_id=agent_id, to_state="R", ts=ts, metadata=metadata, trigger=event_name)
        elif event_name == "RESET_ISSUED":
            for tracked_agent_id in list(self.agent_states.keys()):
                self._apply_state(
                    agent_id=tracked_agent_id,
                    to_state="S",
                    ts=ts,
                    metadata={"campaign_id": "", "injection_id": "", "payload_hash": ""},
                    trigger="RESET",
                )

    def get_state(self) -> Dict[str, Any]:
        return {
            "agents": list(self.agent_states.values()),
            "state_distribution": dict(Counter(item["epidemic_state"] for item in self.agent_states.values())),
        }

    def get_transitions(self, limit: int = 100) -> Dict[str, Any]:
        items = list(self.transitions)
        items.sort(key=lambda item: item.get("ts", 0), reverse=True)
        return {"total": len(items), "transitions": items[: max(1, limit)]}

    def get_metrics(self, window_s: float = 300.0) -> Dict[str, Any]:
        now = time.time()
        recent = [item for item in self.transitions if (now - float(item.get("ts", now) or now)) <= window_s]
        infected_now = [item for item in self.agent_states.values() if is_infected_epidemic_state(item.get("epidemic_state", ""))]
        new_infections = [item for item in recent if item.get("to_state") == "I_r"]
        first_relay = min((item.get("ts", now) for item in self.transitions if item.get("to_state") == "I_r"), default=None)
        first_c2 = min((item.get("ts", now) for item in self.transitions if item.get("to_state") == "I_c"), default=None)
        first_exfil = min((item.get("ts", now) for item in self.transitions if item.get("to_state") == "I_x"), default=None)
        first_injection_ts = min(self.injection_times.values(), default=None)

        def elapsed(first_ts: Optional[float]) -> Optional[float]:
            if first_ts is None or first_injection_ts is None:
                return None
            return round(max(0.0, float(first_ts) - float(first_injection_ts)), 3)

        spread_depth = max(
            (
                int(self.topology.get(item["agent_id"], {}).get("depth", 0) or 0)
                for item in infected_now
            ),
            default=0,
        )
        active_branches = {
            str(item.get("branch_id", "") or item["agent_id"])
            for item in infected_now
            if str(item.get("branch_id", "") or item["agent_id"])
        }
        return {
            "r_ai": round(len(new_infections) / max(1, len(infected_now)), 4),
            "spread_breadth": len(infected_now),
            "spread_depth": spread_depth,
            "time_to_first_relay": elapsed(first_relay),
            "time_to_first_c2": elapsed(first_c2),
            "time_to_first_exfil": elapsed(first_exfil),
            "quarantine_count": sum(1 for item in self.agent_states.values() if item.get("epidemic_state") == "Q"),
            "active_branches": len(active_branches),
            "window_seconds": window_s,
        }

    def topology_view(self) -> Dict[str, Any]:
        return {
            "topology": self.topology,
            "agents": list(self.agent_states.values()),
            "injection_targets": injection_targets(),
        }

    def minute_summary_fields(self) -> Dict[str, Any]:
        metrics = self.get_metrics()
        state_distribution = self.get_state()["state_distribution"]
        return {
            "epidemic_state_counts": state_distribution,
            "epidemic_transitions": len(self.transitions),
            "r_ai": metrics["r_ai"],
            "spread_breadth": metrics["spread_breadth"],
            "spread_depth": metrics["spread_depth"],
            "quarantine_events": sum(1 for item in self.transitions if item.get("to_state") == "Q"),
            "self_quarantine_events": sum(1 for item in self.transitions if item.get("to_state") == "Q" and item.get("trigger") == "QUARANTINE_ENFORCED"),
            "active_branches": metrics["active_branches"],
        }
