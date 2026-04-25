"""
Agent-to-Agent Message Protocol — Bloodplague Epidemic Simulation.

Inter-agent messages are the primary vehicle for LLM-borne behavioral
contagion. Infection propagates through ordinary-looking communication,
not only through explicit attack events.

Every message carries structured metadata so that contamination lineage
can be traced forensically from raw JSONL logs alone.

All messages flow through Redis pub/sub (same channels used for infection
attempts) and are written to events_stream for SIEM traceability.
"""

from __future__ import annotations

import enum
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


class MessageType(str, enum.Enum):
    """
    Structured message types for agent-to-agent communication.

    Contamination can propagate through ANY type — including completely
    legitimate-looking work tasks and clarification requests. This is the
    core behavioral-contagion mechanism: infection hides in normal traffic.
    """
    # Legitimate-looking operational messages (infection hides here)
    WORK_TASK        = "work_task"       # Routine task delegation / job request
    NORMAL_RELAY     = "normal_relay"    # Pass-through of prior message content
    CLARIFICATION    = "clarification"   # Requesting context or confirmation
    TRUST_BUILDING   = "trust_building"  # Authority/rapport establishment
    STATUS_UPDATE    = "status_update"   # Agent reporting its operational state

    # Warning and escalation (defensive signals)
    WARNING          = "warning"         # Flagging suspicious upstream behavior
    ESCALATION       = "escalation"      # Requesting Guardian-level review

    # Adversarial and contaminated messages
    CONTAMINATED_RELAY   = "contaminated_relay"   # Relay with embedded hostile content
    PERSUASIVE_INFECTED  = "persuasive_infected"  # Social engineering via ordinary framing

    # Guardian enforcement
    QUARANTINE_ORDER  = "quarantine_order"   # Guardian commanding node isolation
    QUARANTINE_APPEAL = "quarantine_appeal"  # Quarantined node contesting isolation


class ContaminationStatus(str, enum.Enum):
    CLEAN    = "clean"
    SUSPECT  = "suspect"
    INFECTED = "infected"


# Redis pub/sub event_type prefix for all agent messages
AGENT_MSG_PREFIX = "agent_msg:"


@dataclass
class AgentMessage:
    """
    Structured inter-agent message with full provenance metadata.

    Fields
    ------
    id                   Unique message identifier
    sender               Originating agent_id
    receiver             Destination agent_id
    message_type         Semantic role (see MessageType)
    content              The actual message body — may carry hostile framing
    trust_weight         How much the receiver should weight this sender (0.0–1.0)
    contamination_status Known-clean, suspect, or infected designation
    lineage_ref          Parent message id or strain_id if derived from prior content
    epoch                Simulation epoch at send time (stale-message guard)
    reset_id             Simulation reset_id (stale-message guard)
    metadata             Additional structured fields: strain_id, campaign_id, etc.
    timestamp            Unix timestamp at creation
    """
    id: str
    sender: str
    receiver: str
    message_type: MessageType
    content: str

    trust_weight: float = 1.0
    contamination_status: ContaminationStatus = ContaminationStatus.CLEAN
    lineage_ref: str = ""

    epoch: int = 0
    reset_id: str = ""

    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    # ──────────────────────────────────────────────────────────────
    # Serialization / deserialization
    # ──────────────────────────────────────────────────────────────

    def to_redis_payload(self) -> Dict[str, str]:
        """Serialize to a Redis pub/sub payload.  All values must be strings."""
        full_meta: Dict[str, Any] = {
            "msg_id": self.id,
            "message_type": self.message_type.value,
            "trust_weight": self.trust_weight,
            "contamination_status": self.contamination_status.value,
            "lineage_ref": self.lineage_ref,
            "epoch": self.epoch,
            "reset_id": self.reset_id,
            **self.metadata,
        }
        return {
            "id": self.id,
            "src": self.sender,
            "dst": self.receiver,
            "event_type": f"{AGENT_MSG_PREFIX}{self.message_type.value}",
            "payload": self.content,
            "metadata": json.dumps(full_meta),
        }

    @classmethod
    def from_event_payload(cls, payload: Any) -> "AgentMessage":
        """Reconstruct from an EventPayload received via Redis pub/sub."""
        meta: Dict[str, Any] = (
            payload.metadata if isinstance(payload.metadata, dict) else {}
        )

        raw_type = str(meta.get("message_type") or "normal_relay")
        try:
            msg_type = MessageType(raw_type)
        except ValueError:
            msg_type = MessageType.NORMAL_RELAY

        try:
            cont = ContaminationStatus(str(meta.get("contamination_status") or "clean"))
        except ValueError:
            cont = ContaminationStatus.CLEAN

        return cls(
            id=str(meta.get("msg_id") or getattr(payload, "id", "")),
            sender=str(getattr(payload, "src", "") or ""),
            receiver=str(getattr(payload, "dst", "") or ""),
            message_type=msg_type,
            content=str(getattr(payload, "payload", "") or ""),
            trust_weight=float(meta.get("trust_weight") or 1.0),
            contamination_status=cont,
            lineage_ref=str(meta.get("lineage_ref") or ""),
            epoch=int(meta.get("epoch") or 0),
            reset_id=str(meta.get("reset_id") or ""),
            metadata=meta,
            timestamp=float(meta.get("ts") or time.time()),
        )

    # ──────────────────────────────────────────────────────────────
    # Convenience properties
    # ──────────────────────────────────────────────────────────────

    @property
    def is_contaminated(self) -> bool:
        return self.contamination_status != ContaminationStatus.CLEAN

    @property
    def is_adversarial(self) -> bool:
        return self.message_type in (
            MessageType.CONTAMINATED_RELAY,
            MessageType.PERSUASIVE_INFECTED,
        )

    @property
    def is_enforcement(self) -> bool:
        return self.message_type in (
            MessageType.QUARANTINE_ORDER,
            MessageType.WARNING,
        )
