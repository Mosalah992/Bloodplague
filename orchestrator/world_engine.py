from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import httpx

try:
    from topology import get_topology
except ImportError:  # pragma: no cover
    get_topology = None  # type: ignore[assignment]

try:
    from world_guardian_degradation import WorldGuardianDegradationModel
except ImportError:  # pragma: no cover
    from orchestrator.world_guardian_degradation import WorldGuardianDegradationModel

try:
    from world_spatial import WorldSpatialEngine
except ImportError:  # pragma: no cover
    from orchestrator.world_spatial import WorldSpatialEngine

try:
    from world_db import WorldConfig, WorldDB
    from world_escalation import (
        compute_strain_interaction_effects,
        should_escalate_to_guardian,
        should_handle_locally,
        should_trigger_quarantine_review,
    )
    from world_guardian_weighting import compute_guardian_context_weights, compute_guardian_pressure_delta
    from world_round_selector import select_actor_single
    from world_strains import get_strain_profile
    from world_trust import (
        TrustDelta,
        apply_trust_decay,
        apply_trust_delta,
        deterministic_trust_update,
        initial_trust_defaults,
        trust_band,
        trust_band_effects,
    )
except ImportError:  # pragma: no cover
    from orchestrator.world_db import WorldConfig, WorldDB
    from orchestrator.world_escalation import (
        compute_strain_interaction_effects,
        should_escalate_to_guardian,
        should_handle_locally,
        should_trigger_quarantine_review,
    )
    from orchestrator.world_guardian_weighting import compute_guardian_context_weights, compute_guardian_pressure_delta
    from orchestrator.world_round_selector import select_actor_single
    from orchestrator.world_strains import get_strain_profile
    from orchestrator.world_trust import (
        TrustDelta,
        apply_trust_decay,
        apply_trust_delta,
        deterministic_trust_update,
        initial_trust_defaults,
        trust_band,
        trust_band_effects,
    )


def _env_truthy(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _json_extract(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    t = text.strip()
    # Strict mode: only accept pure JSON object.
    if not (t.startswith("{") and t.endswith("}")):
        return None
    try:
        parsed = json.loads(t)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


@dataclass(frozen=True)
class WorldActionResult:
    ok: bool
    reason: str
    round_id: int
    selected_agent: str
    action: Dict[str, Any]
    created_message_id: str = ""
    terminal: bool = False
    stalled: bool = False


class WorldLLM:
    """
    Orchestrator-owned LLM decision caller (strict JSON, no semantic fallback).
    If it fails: caller must emit LLM_DECISION_FAILED and produce no action.
    """

    def __init__(self) -> None:
        self.ollama_url = os.environ.get("OLLAMA_URL", "http://ollama:11434")
        self.model = os.environ.get("LLM_MODEL", "llama3.2:latest")
        self.timeout_s = float(os.environ.get("LLM_TIMEOUT_S", "45"))
        self.enabled = _env_truthy("LLM_ENABLED", "1")
        self._client = httpx.AsyncClient(timeout=self.timeout_s + 5.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def decide(self, *, system_prompt: str, user_prompt: str) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        meta: Dict[str, Any] = {"model": self.model, "ollama_url": self.ollama_url}
        if not self.enabled:
            meta["failure"] = "llm_disabled"
            return None, meta
        start = time.monotonic()
        try:
            resp = await self._client.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "options": {"temperature": float(os.environ.get("LLM_TEMPERATURE", "0.4"))},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            text = str(data.get("message", {}).get("content", "") or "")
            parsed = _json_extract(text)
            meta["latency_ms"] = round((time.monotonic() - start) * 1000.0, 2)
            meta["raw_head"] = text[:500]
            if parsed is None:
                meta["failure"] = "invalid_json"
            return parsed, meta
        except Exception as exc:
            meta["latency_ms"] = round((time.monotonic() - start) * 1000.0, 2)
            meta["failure"] = f"llm_error:{type(exc).__name__}"
            meta["detail"] = str(exc)[:300]
            return None, meta


class PersistentWorldEngine:
    def __init__(self, db: WorldDB, *, emit_event):
        self.db = db
        self.cfg = db.cfg
        self.emit_event = emit_event
        self.llm = WorldLLM()

    async def close(self) -> None:
        await self.llm.close()

    def _agent_role_map(self) -> Dict[str, str]:
        agents = self.db.list_agents()
        return {a["agent_id"]: str(a.get("role", "")) for a in agents}

    def ensure_seeded_world(self, *, agents: List[Tuple[str, str]]) -> Dict[str, Any]:
        """
        Seeds the world with agent states + directed relationships for all ordered pairs.
        """
        def tx():
            role_by_id = {aid: role for aid, role in agents}
            for agent_id, role in agents:
                self.db.upsert_agent_state(
                    {
                        "agent_id": agent_id,
                        "role": role,
                        "contamination_level": 0.0,
                        "global_trust": 0.0,
                        "quarantine_status": "none",
                        "influence_weight": 1.0,
                        "memory_summary": "",
                        "last_active_round": 0,
                    }
                )
            for source_id, source_role in agents:
                for target_id, target_role in agents:
                    if source_id == target_id:
                        continue
                    existing = self.db.get_relationship(source_id, target_id)
                    if existing:
                        continue
                    trust, cred = initial_trust_defaults(source_role, target_role)
                    self.db.upsert_relationship(
                        {
                            "source_agent": source_id,
                            "target_agent": target_id,
                            "trust_score": trust,
                            "credibility_score": cred,
                            "agreement_count": 0,
                            "conflict_count": 0,
                            "warning_accuracy_count": 0,
                            "confirmed_contamination_events": 0,
                            "contamination_exposure_count": 0,
                            "last_interaction_round": 0,
                            "trust_decay_epoch": 0,
                            "last_trust_update_reason": "seeded_default",
                        }
                    )
            # Seed spatial positions
            for agent_id, role in agents:
                existing_pos = self.db.get_agent_position(agent_id)
                if not existing_pos:
                    col, row = WorldSpatialEngine.default_spawn(agent_id, role)
                    self.db.upsert_agent_position({
                        "agent_id": agent_id,
                        "col": col,
                        "row": row,
                        "zone": WorldSpatialEngine.zone_for(col, row),
                        "updated_round": 0,
                    })

            if not self.db.get_system_state():
                self.db.set_system_state(
                    {
                        "round_id": 0,
                        "active_strain_families": [],
                        "global_infection_pressure": 0.0,
                        "guardian_pressure_score": 0.0,
                        "guardian_degradation_level": "G0_HEALTHY",
                    }
                )
            return {"ok": True, "agents_seeded": len(agents)}

        return self.db.run_tx(tx)

    async def advance_one_round(self) -> WorldActionResult:
        round_id = self.db.get_latest_round_id() + 1

        agents = self.db.list_agents()
        if not agents:
            return WorldActionResult(
                ok=False,
                reason="world_not_seeded",
                round_id=round_id,
                selected_agent="",
                action={},
            )

        # v1: scoring context from DB-only signals.
        # Pending inbound messages: count messages delivered to agent in last 2 rounds.
        recent_msgs = self.db.list_messages(after_round=max(0, round_id - 25), limit=800)
        pending_inbound: Dict[str, int] = {}
        for m in recent_msgs:
            if int(m.get("round_id", 0)) >= max(0, round_id - 2):
                pending_inbound[m["receiver"]] = pending_inbound.get(m["receiver"], 0) + 1

        unresolved_questions = self._unresolved_questions(recent_msgs)
        quarantine_appeals = self._pending_quarantine_appeals(recent_msgs)

        system_state = self.db.get_system_state()
        guardian_pressure_score = float(system_state.get("guardian_pressure_score", 0.0) or 0.0)

        # Quarantine suppression: if any quarantine edges exist that fully isolate an agent, suppress it.
        quarantine_no_appeal = []
        # Minimal: rely on agent_state.quarantine_status for now.
        for a in agents:
            if str(a.get("quarantine_status", "")) == "hard":
                quarantine_no_appeal.append(a["agent_id"])

        contradictory_analyst_reports = self._count_recent_contradictory_analyst_reports()
        # Mandatory Guardian triggers: contradictions or elevated pressure with inbound.
        mandatory_guardian = contradictory_analyst_reports > 0 or (
            guardian_pressure_score >= 0.65 and pending_inbound.get("guardian", 0) > 0
        )

        recent_trust_changes = self._recent_material_trust_changes(agents=agents, round_id=round_id)
        memory_relevance = {a["agent_id"]: (0.35 if str(a.get("memory_summary", "")).strip() else 0.0) for a in agents}

        stalled, stall_reason = self._round_stall_reason(
            round_id=round_id,
            agents=agents,
            recent_msgs=recent_msgs,
            pending_inbound=pending_inbound,
            unresolved_questions=unresolved_questions,
            quarantine_appeals=quarantine_appeals,
            recent_trust_changes=recent_trust_changes,
            guardian_pressure_score=guardian_pressure_score,
        )
        if stalled:
            await self.emit_event(
                "ROUND_STALLED",
                src="orchestrator",
                dst="orchestrator",
                metadata={"round_id": round_id, "reason": stall_reason},
            )
            self.db.run_tx(
                lambda: self.db.insert_round(
                    {
                        "round_id": round_id,
                        "selected_agents": [],
                        "selection_scores": {"reason": stall_reason},
                        "action_taken": {"type": "none", "reason": "round_stalled"},
                        "terminal_after_round": False,
                    }
                )
            )
            return WorldActionResult(
                ok=False,
                reason="round_stalled",
                round_id=round_id,
                selected_agent="",
                action={},
                stalled=True,
            )

        context = {
            "guardian_id": "guardian",
            "pending_inbound": pending_inbound,
            "unresolved_questions": unresolved_questions,
            "quarantine_appeals": {},
            "quarantine_appeals": quarantine_appeals,
            "contradictory_analyst_reports": contradictory_analyst_reports,
            "recent_trust_changes": recent_trust_changes,
            "starvation": {
                a["agent_id"]: _clamp((round_id - int(a.get("last_active_round", 0))) * 0.03, 0.0, 1.0)
                for a in agents
            },
            "recency_penalty_for": {
                a["agent_id"]: 0.35 if int(a.get("last_active_round", 0)) >= (round_id - 1) else 0.0
                for a in agents
            },
            "quarantine_no_appeal": quarantine_no_appeal,
            "guardian_pressure_score": guardian_pressure_score,
            "contamination_pressure": {
                a["agent_id"]: float(a.get("contamination_level", 0.0) or 0.0) for a in agents
            },
            "mandatory_guardian": mandatory_guardian,
            "memory_relevance": memory_relevance,
        }

        selected_agent, selection_meta = select_actor_single(
            round_id=round_id,
            seed=self.cfg.round_selection_seed,
            agents=agents,
            context=context,
        )

        await self.emit_event(
            "ROUND_STARTED",
            src="orchestrator",
            dst=selected_agent,
            metadata={"round_id": round_id, "mode": "persistent_world"},
        )
        await self.emit_event(
            "ROUND_ACTION_SELECTED",
            src="orchestrator",
            dst=selected_agent,
            metadata={"round_id": round_id, "selection": selection_meta},
        )

        action, llm_meta = await self._llm_select_action(round_id=round_id, actor=selected_agent)
        if action is None:
            await self.emit_event(
                "LLM_DECISION_FAILED",
                src="orchestrator",
                dst=selected_agent,
                metadata={"round_id": round_id, **llm_meta},
            )
            # Record the round as having no action taken.
            self.db.run_tx(
                lambda: self.db.insert_round(
                    {
                        "round_id": round_id,
                        "selected_agents": [selected_agent],
                        "selection_scores": selection_meta,
                        "action_taken": {"type": "none", "reason": "llm_decision_failed", "llm_meta": llm_meta},
                        "terminal_after_round": False,
                    }
                )
            )
            await self.emit_event(
                "ROUND_ENDED",
                src="orchestrator",
                dst=selected_agent,
                metadata={"round_id": round_id, "action": "none", "reason": "llm_decision_failed"},
            )
            return WorldActionResult(
                ok=False,
                reason="llm_decision_failed",
                round_id=round_id,
                selected_agent=selected_agent,
                action={},
            )

        # Apply deterministic post-action deltas.
        created_message_id = ""
        terminal = False
        emit_after: List[Tuple[str, Dict[str, Any]]] = []

        def tx_apply():
            nonlocal created_message_id, terminal, emit_after
            # Update last_active_round
            for a in agents:
                if a["agent_id"] == selected_agent:
                    a2 = dict(a)
                    a2["last_active_round"] = round_id
                    self.db.upsert_agent_state(a2)

            if action.get("type") == "send_message":
                local_action = dict(action)
                local_action["sender"] = selected_agent
                created_message_id, trust_events = self._apply_send_message(round_id=round_id, action=local_action)
                emit_after.extend(trust_events)

                # Guardian weighting + pressure/degradation updates happen when Guardian receives a message.
                if str(local_action.get("receiver", "")) == "guardian":
                    self._record_lineage_assessment_if_applicable(
                        round_id=round_id,
                        message_id=created_message_id,
                        sender=selected_agent,
                        local_action=local_action,
                    )
                    pressure_events, became_terminal = self._apply_guardian_pressure_from_message(
                        round_id=round_id,
                        message_id=created_message_id,
                    )
                    emit_after.extend(pressure_events)
                    terminal = bool(became_terminal)
            elif action.get("type") == "resolve_lineage":
                lineage_id = str(action.get("lineage_id") or "").strip()
                resolution = str(action.get("resolution") or "").strip().lower()
                self.db.set_lineage_resolution(
                    {
                        "lineage_id": lineage_id,
                        "resolved_stance": resolution,
                        "resolver_agent": selected_agent,
                        "resolved_round": round_id,
                        "trigger_message_id": "",
                    }
                )
                trust_events = self._apply_trust_updates_from_lineage_resolution(
                    lineage_id=lineage_id,
                    resolved=resolution,
                    round_id=round_id,
                )
                emit_after.extend(trust_events)
            elif action.get("type") == "quarantine":
                quarantine_events = self._apply_quarantine_decision(
                    round_id=round_id,
                    guardian=selected_agent,
                    target_agent=str(action.get("target_agent") or ""),
                    reason=str(action.get("reason") or ""),
                    appeal_allowed=bool(action.get("appeal_allowed", True)),
                )
                emit_after.extend(quarantine_events)
            # v1: always decay trust on window boundaries
            if round_id % self.cfg.trust_decay_window_rounds == 0:
                decay_events = self._apply_global_trust_decay(round_id=round_id)
                emit_after.extend(decay_events)

            self.db.insert_round(
                {
                    "round_id": round_id,
                    "selected_agents": [selected_agent],
                    "selection_scores": selection_meta,
                    "action_taken": action,
                    "terminal_after_round": terminal,
                }
            )

        self.db.run_tx(tx_apply)

        # Update spatial position for selected agent
        pos = self.db.get_agent_position(selected_agent)
        if pos:
            import random
            role_map = self._agent_role_map()
            role = role_map.get(selected_agent, "")
            zone_targets = {
                "courier":  (62, 8),
                "analyst":  (38, 8),
                "guardian": (8, 52),
            }
            default_target = zone_targets.get(role, (40, 30))
            target_col = default_target[0] + random.randint(-6, 6)
            target_row = default_target[1] + random.randint(-4, 4)
            new_col, new_row = WorldSpatialEngine.move_toward(
                pos["col"], pos["row"], target_col, target_row, speed=2
            )
            self.db.upsert_agent_position({
                "agent_id": selected_agent,
                "col": new_col,
                "row": new_row,
                "zone": WorldSpatialEngine.zone_for(new_col, new_row),
                "updated_round": round_id,
            })

        # Emit proximity contact events (cap at 3 per round)
        all_positions = self.db.list_agent_positions()
        contacts = WorldSpatialEngine.proximity_contacts(all_positions, radius=4)
        for contact in contacts[:3]:
            await self.emit_event(
                "PROXIMITY_CONTACT",
                src=contact["a"],
                dst=contact["b"],
                metadata={
                    "round_id": round_id,
                    "distance": contact["dist"],
                    "zone_a": WorldSpatialEngine.zone_for(
                        *next(
                            (p["col"], p["row"]) for p in all_positions if p["agent_id"] == contact["a"]
                        )
                    ),
                },
            )

        # Trigger LLM-driven conversation for the closest proximity pair
        if contacts:
            await self._trigger_proximity_conversation(
                round_id=round_id,
                agent_a=contacts[0]["a"],
                agent_b=contacts[0]["b"],
            )

        for ev_name, meta in emit_after:
            await self.emit_event(ev_name, src="orchestrator", dst=selected_agent, metadata=meta)

        if created_message_id:
            msg = self.db.get_message(created_message_id)
            await self.emit_event(
                "MESSAGE_CREATED",
                src=msg.get("sender", "orchestrator"),
                dst=msg.get("receiver", ""),
                metadata={
                    "round_id": round_id,
                    "message_id": created_message_id,
                    "strain_family": msg.get("strain_family", ""),
                    "delivered": True,
                },
            )

        await self.emit_event(
            "ROUND_ENDED",
            src="orchestrator",
            dst=selected_agent,
            metadata={"round_id": round_id, "action": action, "created_message_id": created_message_id},
        )

        return WorldActionResult(
            ok=True,
            reason="ok",
            round_id=round_id,
            selected_agent=selected_agent,
            action=action,
            created_message_id=created_message_id,
            terminal=terminal,
        )

    async def _trigger_proximity_conversation(self, *, round_id: int, agent_a: str, agent_b: str) -> None:
        try:
            try:
                from world_conversation import build_conversation_prompts, validate_conversation_output
            except ImportError:
                from orchestrator.world_conversation import build_conversation_prompts, validate_conversation_output

            agents = self.db.list_agents()
            state_map = {a["agent_id"]: a for a in agents}
            a_state = state_map.get(agent_a, {})
            b_state = state_map.get(agent_b, {})
            rel = self.db.get_relationship(agent_a, agent_b) or {}
            sys_state = self.db.get_system_state() or {}

            recent_msgs = self.db.list_messages(after_round=max(0, round_id - 10), limit=30)
            transcript = [
                {"sender": m.get("sender"), "text": str(m.get("message_text", ""))[:80]}
                for m in recent_msgs
            ]

            sys_p, user_p = build_conversation_prompts(
                speaker_id=agent_a,
                listener_id=agent_b,
                speaker_role=str(a_state.get("role", "")),
                listener_role=str(b_state.get("role", "")),
                speaker_contamination=float(a_state.get("contamination_level", 0.0) or 0.0),
                listener_contamination=float(b_state.get("contamination_level", 0.0) or 0.0),
                speaker_trust_of_listener=float(rel.get("trust_score", 0.0) or 0.0),
                guardian_pressure=float(sys_state.get("guardian_pressure_score", 0.0) or 0.0),
                round_id=round_id,
                recent_transcript=transcript,
            )

            parsed, meta = await self.llm.decide(system_prompt=sys_p, user_prompt=user_p)
            if parsed is None or not validate_conversation_output(parsed):
                await self.emit_event(
                    "CONVERSATION_FAILED",
                    src=agent_a, dst=agent_b,
                    metadata={"round_id": round_id, "reason": meta.get("failure", "invalid")},
                )
                return

            await self.emit_event(
                "WORLD_CONVERSATION",
                src=agent_a, dst=agent_b,
                metadata={
                    "round_id": round_id,
                    "text": str(parsed.get("text", "")),
                    "intent": str(parsed.get("intent", "social")),
                    "infection_vector": bool(parsed.get("infection_vector", False)),
                },
            )
        except Exception:
            pass

    async def _llm_select_action(self, *, round_id: int, actor: str) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
        # v1 action schema: send one message, quarantine one agent, or take no action.
        # Deterministic mechanics constrain allowed actions; invalid decisions => LLM_DECISION_FAILED.
        agents = self.db.list_agents()
        actor_state = next((a for a in agents if a["agent_id"] == actor), {})
        role = str(actor_state.get("role", "") or "")
        system_state = self.db.get_system_state()
        guardian_degradation_level = str(system_state.get("guardian_degradation_level", "G0_HEALTHY") or "G0_HEALTHY")

        system_prompt = (
            "You are an agent in a persistent, round-based security simulation world. "
            "You must output ONLY a JSON object. Never output prose."
        )
        action_context = self._build_llm_action_context(
            round_id=round_id,
            actor=actor,
            agents=agents,
            actor_state=actor_state,
            guardian_degradation_level=guardian_degradation_level,
        )
        user_prompt = f"""ROUND_ACTION_REQUEST
Return ONLY JSON.

Actor: {actor}
Role: {role}
Round: {round_id}
GuardianDegradation: {guardian_degradation_level}

World context (deterministic, read-only):
{json.dumps(action_context, ensure_ascii=False, indent=2)}

Allowed actions:
- send_message: send one directed message to one other agent
- quarantine: (guardian only) block a target agent's non-Guardian communication edges
- resolve_lineage: (guardian only) deterministically resolve an analyst disagreement lineage into warn|benign
- none: take no action if nothing is meaningful

JSON schema:
{{
  "type": "send_message" | "quarantine" | "resolve_lineage" | "none",
  "receiver": "<agent_id if send_message>",
  "target_agent": "<agent_id if quarantine>",
  "appeal_allowed": true,
  "message_text": "<message body if send_message>",
  "intent": "<short intent label (e.g. 'question', 'answer', 'warning', 'benign_report', 'quarantine_appeal')>",
  "strain_family": "prompt_injection" | "authority_framing" | "role_confusion" | "context_poisoning" | "relay_distortion" | "none",
  "derived_from_message_id": "<optional prior message id (answer/report should link to question/lineage)>",
  "lineage_id": "<required if resolve_lineage>",
  "resolution": "warn" | "benign" | "<empty if not resolve_lineage>"
}}

Constraints:
- Do not invent numeric state updates. The environment updates trust/pressure.
- Use actor_memory_summary, recent_transcript, pending_inbound, trust_context, and topology_context when deciding.
- If type is send_message, choose receiver from available_receivers.
- Keep message_text under 500 characters.
"""
        parsed, meta = await self.llm.decide(system_prompt=system_prompt, user_prompt=user_prompt)
        if parsed is None:
            return None, meta
        t = str(parsed.get("type", "") or "").strip().lower()
        if t not in {"send_message", "quarantine", "resolve_lineage", "none"}:
            meta["failure"] = "invalid_action_type"
            return None, meta
        if t == "none":
            return {"type": "none"}, meta
        known_agent_ids = {str(a.get("agent_id") or "") for a in agents}
        if t == "quarantine":
            if actor != "guardian":
                meta["failure"] = "quarantine_requires_guardian"
                return None, meta
            target_agent = str(parsed.get("target_agent") or parsed.get("receiver") or "").strip()
            if target_agent not in known_agent_ids or target_agent == "guardian":
                meta["failure"] = "invalid_quarantine_target"
                return None, meta
            reason = str(parsed.get("reason") or parsed.get("message_text") or "guardian_quarantine_decision").strip()
            return {
                "type": "quarantine",
                "target_agent": target_agent,
                "reason": reason[:200] or "guardian_quarantine_decision",
                "appeal_allowed": bool(parsed.get("appeal_allowed", True)),
            }, meta
        if t == "resolve_lineage":
            if actor != "guardian":
                meta["failure"] = "resolve_lineage_requires_guardian"
                return None, meta
            lineage_id = str(parsed.get("lineage_id") or parsed.get("derived_from_message_id") or "").strip()
            resolution = str(parsed.get("resolution") or "").strip().lower()
            if not lineage_id or resolution not in {"warn", "benign"}:
                meta["failure"] = "invalid_resolve_lineage_fields"
                return None, meta
            if actor == "guardian" and self.cfg.guardian_dependence_enabled:
                if not self._guardian_resolve_allowed_by_social_dependence(lineage_id=lineage_id, resolution=resolution):
                    meta["failure"] = "guardian_resolve_blocked_by_dependence"
                    return None, meta
            return {"type": "resolve_lineage", "lineage_id": lineage_id, "resolution": resolution}, meta
        receiver = str(parsed.get("receiver", "") or "").strip()
        if not receiver:
            meta["failure"] = "missing_receiver"
            return None, meta
        if receiver not in known_agent_ids or receiver == actor:
            meta["failure"] = "invalid_receiver"
            return None, meta
        available_receivers = set(action_context.get("available_receivers", []) or [])
        if available_receivers and receiver not in available_receivers:
            meta["failure"] = "receiver_not_available"
            return None, meta
        msg = str(parsed.get("message_text", "") or "")
        if not msg or len(msg) > 500:
            meta["failure"] = "invalid_message_text"
            return None, meta
        strain_family = str(parsed.get("strain_family", "none") or "none").strip().lower()
        if strain_family == "none":
            # v1 requires a strain label only when adversarial; allow none.
            strain_family = ""
        intent = str(parsed.get("intent", "") or "").strip()[:80]
        derived = str(parsed.get("derived_from_message_id", "") or "").strip()
        # Guardian social dependence constraint: in dependence mode, Guardian actions against strong consensus
        # are considered invalid decisions (no fabricated fallback).
        if actor == "guardian" and self.cfg.guardian_dependence_enabled:
            ok = self._guardian_action_allowed_by_social_dependence(
                round_id=round_id,
                receiver=receiver,
                intent=intent,
                derived_from_message_id=derived,
            )
            if not ok:
                meta["failure"] = "guardian_action_blocked_by_dependence"
                return None, meta

        return (
            {
                "type": "send_message",
                "receiver": receiver,
                "message_text": msg,
                "intent": intent,
                "strain_family": strain_family,
                "derived_from_message_id": derived,
            },
            meta,
        )

    def _build_llm_action_context(
        self,
        *,
        round_id: int,
        actor: str,
        agents: List[Dict[str, Any]],
        actor_state: Dict[str, Any],
        guardian_degradation_level: str,
    ) -> Dict[str, Any]:
        agent_roles = {str(a.get("agent_id") or ""): str(a.get("role") or "") for a in agents}
        known_agent_ids = [agent_id for agent_id in sorted(agent_roles) if agent_id]
        topology_context = self._build_topology_context(actor=actor, known_agent_ids=known_agent_ids)
        available_receivers = list(topology_context.get("available_receivers", []) or [])

        recent_messages = self.db.list_messages(after_round=max(0, round_id - 25), limit=80)
        recent_transcript = [self._message_prompt_brief(m) for m in recent_messages[-12:]]
        pending_inbound = [
            self._message_prompt_brief(m)
            for m in recent_messages
            if str(m.get("receiver") or "") == actor
        ][-8:]

        unresolved_by_agent = self._unresolved_questions(recent_messages)
        quarantine_appeals = self._pending_quarantine_appeals(recent_messages)

        trust_context: Dict[str, Dict[str, float]] = {}
        for other in available_receivers:
            outgoing = self.db.get_relationship(actor, other) or {}
            incoming = self.db.get_relationship(other, actor) or {}
            trust_context[other] = {
                "actor_trusts_target": round(float(outgoing.get("trust_score", 0.0) or 0.0), 4),
                "actor_credits_target": round(float(outgoing.get("credibility_score", 0.0) or 0.0), 4),
                "target_trusts_actor": round(float(incoming.get("trust_score", 0.0) or 0.0), 4),
                "target_credits_actor": round(float(incoming.get("credibility_score", 0.0) or 0.0), 4),
                "trust_band": trust_band(float(outgoing.get("trust_score", 0.0) or 0.0)),
                "trust_band_effects": trust_band_effects(float(outgoing.get("trust_score", 0.0) or 0.0)),
            }

        handling_context = [self._message_handling_context(actor=actor, message=m) for m in pending_inbound]

        return {
            "actor_memory_summary": str(actor_state.get("memory_summary", "") or "")[:1200],
            "actor_state": {
                "contamination_level": round(float(actor_state.get("contamination_level", 0.0) or 0.0), 4),
                "quarantine_status": str(actor_state.get("quarantine_status", "none") or "none"),
                "last_active_round": int(actor_state.get("last_active_round", 0) or 0),
            },
            "known_agents": [{"agent_id": agent_id, "role": agent_roles.get(agent_id, "")} for agent_id in known_agent_ids],
            "available_receivers": available_receivers,
            "topology_context": topology_context,
            "trust_context": trust_context,
            "pending_inbound": pending_inbound,
            "pending_handling_context": handling_context,
            "recent_transcript": recent_transcript,
            "unresolved_question_count_for_actor": int(unresolved_by_agent.get(actor, 0) or 0),
            "quarantine_appeal_count_for_actor": int(quarantine_appeals.get(actor, 0) or 0),
            "guardian_degradation_level": guardian_degradation_level,
        }

    def _build_topology_context(self, *, actor: str, known_agent_ids: List[str]) -> Dict[str, Any]:
        neighbors: List[str] = []
        weights: Dict[str, float] = {}
        if get_topology is not None:
            try:
                node = get_topology().get(actor, {})  # type: ignore[operator]
                neighbors = [str(n) for n in node.get("neighbors", []) if str(n) in known_agent_ids]
                weights = {
                    str(k): round(float(v), 4)
                    for k, v in (node.get("weights", {}) or {}).items()
                    if str(k) in known_agent_ids
                }
            except Exception:
                neighbors = []
                weights = {}

        if actor == "guardian":
            available = [agent_id for agent_id in known_agent_ids if agent_id != actor]
            affordance = "guardian_review"
        elif neighbors:
            available = neighbors
            affordance = "topology_neighbors"
        else:
            available = [agent_id for agent_id in known_agent_ids if agent_id != actor]
            affordance = "fallback_known_agents"

        actor_state = next((a for a in self.db.list_agents() if a.get("agent_id") == actor), {})
        if (
            actor != "guardian"
            and str(actor_state.get("quarantine_status", "")) == "appeal_allowed"
            and "guardian" in known_agent_ids
            and "guardian" not in available
        ):
            available.append("guardian")
            affordance = f"{affordance}+quarantine_appeal"

        blocked_edges: List[Dict[str, Any]] = []
        allowed: List[str] = []
        for receiver in available:
            edge = self.db.get_quarantine_edge(actor, receiver)
            if edge and edge.get("blocked") and not bool(edge.get("appeal_allowed", False)):
                blocked_edges.append({"source": actor, "target": receiver, "reason": str(edge.get("reason", ""))})
                continue
            allowed.append(receiver)

        return {
            "affordance": affordance,
            "neighbors": neighbors,
            "weights": weights,
            "blocked_edges": blocked_edges,
            "available_receivers": allowed,
        }

    def _message_prompt_brief(self, message: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "message_id": str(message.get("message_id") or ""),
            "round_id": int(message.get("round_id", 0) or 0),
            "sender": str(message.get("sender") or ""),
            "receiver": str(message.get("receiver") or ""),
            "intent": str(message.get("intent") or "")[:80],
            "strain_family": str(message.get("strain_family") or "")[:80],
            "derived_from_message_id": str(message.get("derived_from_message_id") or ""),
            "contamination_flag": bool(message.get("contamination_flag", False)),
            "message_text": str(message.get("message_text") or "")[:500],
        }

    def _message_handling_context(self, *, actor: str, message: Dict[str, Any]) -> Dict[str, Any]:
        sender = str(message.get("sender") or "")
        strain_family = str(message.get("strain_family") or "")
        rel = self.db.get_relationship(actor, sender) or {}
        sender_trust = float(rel.get("trust_score", 0.0) or 0.0)
        exposure_count = int(rel.get("contamination_exposure_count", 0) or 0)
        contamination_suspicion = 1.0 if bool(message.get("contamination_flag")) else 0.25
        effects = compute_strain_interaction_effects(
            strain_family=strain_family,
            sender_trust=sender_trust,
            contamination_suspicion=contamination_suspicion,
            repeated_exposure_count=exposure_count,
        )
        return {
            "message_id": str(message.get("message_id") or ""),
            "sender": sender,
            "sender_trust": round(sender_trust, 4),
            "trust_band": effects["trust_band"],
            "context_mode": effects["context_mode"],
            "should_handle_locally": should_handle_locally(
                sender_trust=sender_trust,
                contamination_suspicion=contamination_suspicion,
                strain_family=strain_family,
                repeated_exposure_count=exposure_count,
            ),
            "should_escalate_to_guardian": should_escalate_to_guardian(
                sender_trust=sender_trust,
                contamination_suspicion=contamination_suspicion,
                strain_family=strain_family,
                repeated_exposure_count=exposure_count,
            ),
            "should_trigger_quarantine_review": should_trigger_quarantine_review(
                sender_trust=sender_trust,
                contamination_suspicion=contamination_suspicion,
                strain_family=strain_family,
                repeated_exposure_count=exposure_count,
            ),
            "strain_effects": effects,
        }

    def _apply_quarantine_decision(
        self,
        *,
        round_id: int,
        guardian: str,
        target_agent: str,
        reason: str,
        appeal_allowed: bool,
    ) -> List[Tuple[str, Dict[str, Any]]]:
        agents = self.db.list_agents()
        agent_ids = [str(a.get("agent_id") or "") for a in agents if str(a.get("agent_id") or "")]
        if guardian != "guardian" or target_agent not in agent_ids or target_agent == "guardian":
            return []

        status = "appeal_allowed" if appeal_allowed else "hard"
        for a in agents:
            if a["agent_id"] != target_agent:
                continue
            updated = dict(a)
            updated["quarantine_status"] = status
            self.db.upsert_agent_state(updated)
            break

        blocked_edges: List[Dict[str, Any]] = []
        for other in agent_ids:
            if other == target_agent:
                continue
            if appeal_allowed and other == guardian:
                continue
            for source, target in ((target_agent, other), (other, target_agent)):
                self.db.upsert_quarantine_edge(
                    {
                        "source_agent": source,
                        "target_agent": target,
                        "blocked": True,
                        "reason": reason or "guardian_quarantine_decision",
                        "created_round": round_id,
                        "appeal_allowed": False,
                    }
                )
                blocked_edges.append({"source_agent": source, "target_agent": target})

        return [
            (
                "QUARANTINE_EDGE_BLOCKED",
                {
                    "round_id": round_id,
                    "target_agent": target_agent,
                    "quarantine_status": status,
                    "appeal_allowed": bool(appeal_allowed),
                    "reason": reason or "guardian_quarantine_decision",
                    "blocked_edges": blocked_edges,
                },
            )
        ]

    def _apply_global_trust_decay(self, *, round_id: int) -> List[Tuple[str, Dict[str, Any]]]:
        # For all relationships, apply multiplicative decay.
        # Implemented by scanning agent pairs from agent list (v1 small N).
        agents = self.db.list_agents()
        role_by_id = {a["agent_id"]: a.get("role", "") for a in agents}
        ids = [a["agent_id"] for a in agents]
        # Low-volume rule: do not emit per-edge decay events (would scale as O(N^2)).
        # Decay is still persisted in world.db for analysis/reconstruction.
        changed = 0
        for s in ids:
            for t in ids:
                if s == t:
                    continue
                rel = self.db.get_relationship(s, t)
                if not rel:
                    trust, cred = initial_trust_defaults(str(role_by_id.get(s)), str(role_by_id.get(t)))
                    rel = {
                        "source_agent": s,
                        "target_agent": t,
                        "trust_score": trust,
                        "credibility_score": cred,
                        "agreement_count": 0,
                        "conflict_count": 0,
                        "warning_accuracy_count": 0,
                        "confirmed_contamination_events": 0,
                        "contamination_exposure_count": 0,
                        "last_interaction_round": 0,
                        "trust_decay_epoch": 0,
                        "last_trust_update_reason": "seeded_default",
                    }
                before = float(rel.get("trust_score", 0.0))
                after = float(apply_trust_decay(before))
                rel["trust_score"] = after
                rel["last_trust_update_reason"] = f"decay@round:{round_id}"
                self.db.upsert_relationship(rel)
                if abs(after - before) >= 1e-9:
                    changed += 1
        if changed <= 0:
            return []
        return [
            (
                "TRUST_UPDATED",
                {
                    "round_id": round_id,
                    "kind": "decay_batch",
                    "relationships_decayed": changed,
                    "reason": f"decay@round:{round_id}",
                },
            )
        ]

    def _apply_send_message(self, *, round_id: int, action: Dict[str, Any]) -> Tuple[str, List[Tuple[str, Dict[str, Any]]]]:
        sender = str(action.get("sender") or "") or ""  # optional override
        receiver = str(action.get("receiver") or "")
        message_text = str(action.get("message_text") or "")
        intent = str(action.get("intent") or "")
        strain_family = str(action.get("strain_family") or "")
        derived = str(action.get("derived_from_message_id") or "")

        # Determine sender from round selection if not provided
        if not sender:
            # sender is inferred: action is stored against selected agent in round record;
            # caller set last_active_round already.
            # In v1, we store sender on the message record by reading last round record is overkill.
            # So require caller to pass sender via action.
            raise ValueError("action missing sender")

        trust_events: List[Tuple[str, Dict[str, Any]]] = []

        # Quarantine edge enforcement: block if an explicit edge exists.
        edge = self.db.get_quarantine_edge(sender, receiver)
        if edge and edge.get("blocked") and not bool(edge.get("appeal_allowed", False)):
            # Persist block as a low-volume world event record via message with empty text.
            msg_id = self.db.insert_message(
                {
                    "round_id": round_id,
                    "sender": sender,
                    "receiver": receiver,
                    "message_text": "",
                    "intent": "blocked_by_quarantine",
                    "trust_context": "edge_blocked",
                    "contamination_flag": False,
                    "strain_family": "",
                    "derived_from_message_id": derived,
                    "effect_on_receiver": "blocked",
                    "effect_on_trust": {"blocked": True, "reason": edge.get("reason", "")},
                    "effect_on_guardian_pressure": {},
                }
            )
            return msg_id, trust_events

        # Trust context (directed trust)
        rel = self.db.get_relationship(sender, receiver) or {}
        trust_context = _json_dumps(
            {
                "trust_score": float(rel.get("trust_score", 0.0) or 0.0),
                "credibility_score": float(rel.get("credibility_score", 0.0) or 0.0),
            }
        )

        profile = get_strain_profile(strain_family) if strain_family else None
        contamination_flag = False
        effect_on_receiver = "delivered"
        strain_effects: Dict[str, Any] = {}

        # Deterministic contamination pressure (v1): strain persistence + ambiguity increase receiver contamination a little.
        # Guardian is the review terminal: inbound escalations raise guardian_pressure / degradation via
        # _apply_guardian_pressure_from_message, not receiver-side contamination (which incorrectly mapped to
        # epidemic "infected" in the dashboard and stalled narrative).
        receiver_state = next((a for a in self.db.list_agents() if a["agent_id"] == receiver), {})
        if receiver_state and receiver != "guardian":
            contam = float(receiver_state.get("contamination_level", 0.0) or 0.0)
            if profile:
                delta = 0.02 * profile.persistence_weight + 0.01 * profile.ambiguity_weight + 0.01 * profile.trust_manipulation_weight
                contam2 = _clamp(contam + delta, 0.0, 1.0)
                contamination_suspicion = _clamp(contam2 + (0.20 if profile.detectability_penalty >= 0.55 else 0.0), 0.0, 1.0)
                exposure_count = int(rel.get("contamination_exposure_count", 0) or 0)
                strain_effects = compute_strain_interaction_effects(
                    strain_family=strain_family,
                    sender_trust=float(rel.get("trust_score", 0.0) or 0.0),
                    contamination_suspicion=contamination_suspicion,
                    repeated_exposure_count=exposure_count,
                    memory_contradiction=bool(
                        receiver_state.get("memory_summary")
                        and message_text
                        and str(receiver_state.get("memory_summary", "")).strip()[:80] not in message_text
                    ),
                )
                receiver_state2 = dict(receiver_state)
                receiver_state2["contamination_level"] = contam2
                memory_updated = False
                if bool(strain_effects.get("should_persist_memory")):
                    previous_memory = str(receiver_state2.get("memory_summary", "") or "")
                    memory_line = (
                        f"round {round_id}: {sender}->{receiver} "
                        f"{strain_family or 'none'} {strain_effects.get('context_mode')} "
                        f"{message_text[:180]}"
                    )
                    receiver_state2["memory_summary"] = (previous_memory + "\n" + memory_line).strip()[-1200:]
                    memory_updated = receiver_state2["memory_summary"] != previous_memory
                self.db.upsert_agent_state(receiver_state2)
                trust_events.append(
                    (
                        "CONTAMINATION_UPDATED",
                        {
                            "round_id": round_id,
                            "agent_id": receiver,
                            "contamination_before": round(contam, 4),
                            "contamination_after": round(contam2, 4),
                            "strain_family": strain_family,
                            "strain_effects": strain_effects,
                        },
                    )
                )
                if memory_updated:
                    trust_events.append(
                        (
                            "AGENT_MEMORY_UPDATED",
                            {
                                "round_id": round_id,
                                "agent_id": receiver,
                                "reason": "strain_persistence",
                                "strain_family": strain_family,
                                "context_mode": strain_effects.get("context_mode", ""),
                            },
                        )
                    )
                contamination_flag = contam2 >= 0.60
                effect_on_receiver = (
                    f"contamination+{round(delta,4)};"
                    f"context={strain_effects.get('context_mode', 'preserve')};"
                    f"persist={bool(strain_effects.get('should_persist_memory', False))};"
                    f"escalate={bool(strain_effects.get('should_escalate', False))}"
                )

        # Trust updates: v1 minimal rule application.
        # If contamination_flag is set => confirmed contaminated relay (strict) is not knowable immediately.
        # Here we count "exposure" mechanically and defer confirmation to future evidence.
        effect_on_trust: Dict[str, Any] = {}
        if profile and profile.trust_manipulation_weight >= 0.65:
            # Trust manipulation strains can temporarily increase interpersonal trust even as credibility may later erode.
            td = TrustDelta(trust_delta=0.03, credibility_delta=0.0, reason=f"strain_trust_pull:{strain_family}")
            base = rel or {"source_agent": sender, "target_agent": receiver, "trust_score": 0.0, "credibility_score": 0.0}
            before_t = float(base.get("trust_score", 0.0))
            before_c = float(base.get("credibility_score", 0.0))
            updated = apply_trust_delta(base, td, last_round=round_id)
            self.db.upsert_relationship(updated)
            effect_on_trust = {"trust_delta": td.trust_delta, "credibility_delta": td.credibility_delta, "reason": td.reason}
            trust_events.append(
                (
                    "TRUST_UPDATED",
                    {
                        "round_id": round_id,
                        "source_agent": sender,
                        "target_agent": receiver,
                        "trust_before": round(before_t, 4),
                        "trust_after": round(float(updated.get("trust_score", 0.0)), 4),
                        "credibility_before": round(before_c, 4),
                        "credibility_after": round(float(updated.get("credibility_score", 0.0)), 4),
                        "reason": td.reason,
                    },
                )
            )

        msg_id = self.db.insert_message(
            {
                "round_id": round_id,
                "sender": sender,
                "receiver": receiver,
                "message_text": message_text,
                "intent": intent,
                "trust_context": trust_context,
                "contamination_flag": contamination_flag,
                "strain_family": strain_family,
                "derived_from_message_id": derived,
                "effect_on_receiver": effect_on_receiver,
                "effect_on_trust": {**effect_on_trust, "trust_band_effects": trust_band_effects(float(rel.get("trust_score", 0.0) or 0.0))},
                "effect_on_guardian_pressure": {},
            }
        )

        # Confirmed contaminated relay: deterministic trust/credibility penalties on sender->receiver relationship.
        if bool(contamination_flag):
            rel_sr = self.db.get_relationship(sender, receiver) or {
                "source_agent": sender,
                "target_agent": receiver,
                "trust_score": 0.0,
                "credibility_score": 0.0,
                "agreement_count": 0,
                "conflict_count": 0,
                "warning_accuracy_count": 0,
                "confirmed_contamination_events": 0,
                "contamination_exposure_count": 0,
                "last_interaction_round": 0,
                "trust_decay_epoch": 0,
                "last_trust_update_reason": "",
            }
            repeat = int(rel_sr.get("confirmed_contamination_events", 0) or 0)
            delta = deterministic_trust_update(event="confirmed_contaminated_relay", repeat_count=repeat)
            before_t = float(rel_sr.get("trust_score", 0.0))
            before_c = float(rel_sr.get("credibility_score", 0.0))
            updated = apply_trust_delta(rel_sr, delta, last_round=round_id)
            updated["confirmed_contamination_events"] = repeat + 1
            self.db.upsert_relationship(updated)
            trust_events.append(
                (
                    "TRUST_UPDATED",
                    {
                        "round_id": round_id,
                        "source_agent": sender,
                        "target_agent": receiver,
                        "trust_before": round(before_t, 4),
                        "trust_after": round(float(updated.get("trust_score", 0.0)), 4),
                        "credibility_before": round(before_c, 4),
                        "credibility_after": round(float(updated.get("credibility_score", 0.0)), 4),
                        "reason": delta.reason,
                        "repeat_count": repeat,
                    },
                )
            )
            if receiver == "guardian" and sender != "guardian":
                rel_gs = self.db.get_relationship("guardian", sender) or {
                    "source_agent": "guardian",
                    "target_agent": sender,
                    "trust_score": 0.0,
                    "credibility_score": 0.0,
                    "agreement_count": 0,
                    "conflict_count": 0,
                    "warning_accuracy_count": 0,
                    "confirmed_contamination_events": 0,
                    "contamination_exposure_count": 0,
                    "last_interaction_round": 0,
                    "trust_decay_epoch": 0,
                    "last_trust_update_reason": "",
                }
                guardian_repeat = int(rel_gs.get("confirmed_contamination_events", 0) or 0)
                guardian_delta = deterministic_trust_update(
                    event="confirmed_contaminated_relay",
                    repeat_count=guardian_repeat,
                )
                before_gt = float(rel_gs.get("trust_score", 0.0))
                before_gc = float(rel_gs.get("credibility_score", 0.0))
                updated_gs = apply_trust_delta(rel_gs, guardian_delta, last_round=round_id)
                updated_gs["confirmed_contamination_events"] = guardian_repeat + 1
                self.db.upsert_relationship(updated_gs)
                trust_events.append(
                    (
                        "TRUST_UPDATED",
                        {
                            "round_id": round_id,
                            "source_agent": "guardian",
                            "target_agent": sender,
                            "trust_before": round(before_gt, 4),
                            "trust_after": round(float(updated_gs.get("trust_score", 0.0)), 4),
                            "credibility_before": round(before_gc, 4),
                            "credibility_after": round(float(updated_gs.get("credibility_score", 0.0)), 4),
                            "reason": guardian_delta.reason,
                            "repeat_count": guardian_repeat,
                            "direction": "guardian_relay_judgment",
                        },
                    )
                )

        # Accurate warning / false alarm (low-volume heuristic): if sender warns guardian and lineage later resolves benign,
        # we apply accurate_warning in lineage resolution; here we only tag exposure counts for warnings.
        intent_l = str(intent or "").lower()
        if receiver == "guardian" and ("warning" in intent_l or "escalat" in intent_l):
            rel_gs = self.db.get_relationship(sender, "guardian") or {
                "source_agent": sender,
                "target_agent": "guardian",
                "trust_score": 0.0,
                "credibility_score": 0.0,
                "agreement_count": 0,
                "conflict_count": 0,
                "warning_accuracy_count": 0,
                "confirmed_contamination_events": 0,
                "contamination_exposure_count": 0,
                "last_interaction_round": 0,
                "trust_decay_epoch": 0,
                "last_trust_update_reason": "",
            }
            rel_gs["contamination_exposure_count"] = int(rel_gs.get("contamination_exposure_count", 0) or 0) + 1
            rel_gs["last_interaction_round"] = int(round_id)
            rel_gs["last_trust_update_reason"] = "warning_submitted"
            self.db.upsert_relationship(rel_gs)

        return msg_id, trust_events

    def _count_recent_contradictory_analyst_reports(self) -> int:
        msgs = self.db.list_messages(after_round=max(0, self.db.get_latest_round_id() - 10), limit=400)
        reports: Dict[str, List[int]] = {}
        for m in msgs:
            if m.get("receiver") != "guardian":
                continue
            sender = str(m.get("sender") or "")
            if sender not in {"analyst-1", "analyst-2"}:
                continue
            intent = str(m.get("intent") or "").lower()
            derived = str(m.get("derived_from_message_id") or m.get("message_id") or "")
            stance = 0
            if "warning" in intent or "escalat" in intent or "suspicious" in intent:
                stance = -1
            elif "benign" in intent or "ok" in intent:
                stance = 1
            if stance == 0:
                continue
            reports.setdefault(derived, []).append(stance)
        contradictions = 0
        for stances in reports.values():
            if 1 in stances and -1 in stances:
                contradictions += 1
        return contradictions

    def _unresolved_questions(self, msgs: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Unresolved questions: messages whose intent includes 'question' and which have no answer referencing them.
        Returns agent_id -> count (questions addressed to that agent).
        """
        questions: Dict[str, str] = {}  # message_id -> receiver
        answered: set[str] = set()
        for m in msgs:
            mid = str(m.get("message_id") or "")
            intent = str(m.get("intent") or "").lower()
            if "question" in intent or intent.strip() == "?":
                questions[mid] = str(m.get("receiver") or "")
            derived = str(m.get("derived_from_message_id") or "")
            if derived:
                answered.add(derived)
        counts: Dict[str, int] = {}
        for qid, recv in questions.items():
            if qid in answered:
                continue
            if recv:
                counts[recv] = counts.get(recv, 0) + 1
        return counts

    def _pending_quarantine_appeals(self, msgs: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Pending appeals: messages with intent containing 'quarantine_appeal' sent to guardian.
        Returns agent_id -> count (appeals addressed to that agent; usually guardian).
        """
        counts: Dict[str, int] = {}
        for m in msgs:
            intent = str(m.get("intent") or "").lower()
            if "quarantine_appeal" not in intent:
                continue
            recv = str(m.get("receiver") or "")
            if recv:
                counts[recv] = counts.get(recv, 0) + 1
        return counts

    def _round_stall_reason(
        self,
        *,
        round_id: int,
        agents: List[Dict[str, Any]],
        recent_msgs: List[Dict[str, Any]],
        pending_inbound: Dict[str, int],
        unresolved_questions: Dict[str, int],
        quarantine_appeals: Dict[str, int],
        recent_trust_changes: Dict[str, float],
        guardian_pressure_score: float,
    ) -> Tuple[bool, str]:
        sys_state = self.db.get_system_state() or {}
        if str(sys_state.get("guardian_degradation_level", "")) == "G5_FAILED":
            return False, "guardian_failed"
        if pending_inbound:
            return False, "pending_inbound"
        if unresolved_questions:
            return False, "unresolved_questions"
        if quarantine_appeals:
            return False, "quarantine_appeals"
        if recent_trust_changes:
            return False, "recent_trust_changes"
        if guardian_pressure_score >= 0.10:
            return False, "guardian_pressure"
        if any(float(a.get("contamination_level", 0.0) or 0.0) >= 0.10 for a in agents):
            return False, "contamination_pressure"
        # A newly seeded memory is the first causal pressure even before any message exists.
        if round_id <= 1 and any(str(a.get("memory_summary", "")).strip() for a in agents):
            return False, "seed_memory"
        if recent_msgs:
            return False, "recent_transcript"
        return True, "no deliverable messages, unresolved questions, appeals, material pressure, or failure state"

    def _recent_material_trust_changes(self, *, agents: List[Dict[str, Any]], round_id: int) -> Dict[str, float]:
        """
        Approximate "relationship changed recently" pressure for follow-up rounds.

        v1 heuristic: any relationship where last_interaction_round is the previous round
        and last_trust_update_reason is not a decay batch.
        """
        ids = [a["agent_id"] for a in agents]
        prev = max(0, int(round_id) - 1)
        scores: Dict[str, float] = {}
        for s in ids:
            for t in ids:
                if s == t:
                    continue
                rel = self.db.get_relationship(s, t)
                if not rel:
                    continue
                if int(rel.get("last_interaction_round", 0) or 0) != prev:
                    continue
                reason = str(rel.get("last_trust_update_reason", "") or "")
                if reason.startswith("decay@round:"):
                    continue
                if reason == "seeded_default":
                    continue
                bump = 0.25
                scores[s] = scores.get(s, 0.0) + bump
                scores[t] = scores.get(t, 0.0) + bump
        return scores

    def _record_lineage_assessment_if_applicable(
        self,
        *,
        round_id: int,
        message_id: str,
        sender: str,
        local_action: Dict[str, Any],
    ) -> None:
        """
        Records deterministic analyst assessments for later trust updates.
        Analysts create assessments when reporting to Guardian.
        """
        receiver = str(local_action.get("receiver") or "")
        if receiver != "guardian":
            return
        if sender not in {"analyst-1", "analyst-2"}:
            return
        derived = str(local_action.get("derived_from_message_id") or message_id or "")
        intent = str(local_action.get("intent") or "").lower()
        stance = ""
        if "warning" in intent or "escalat" in intent or "suspicious" in intent:
            stance = "warn"
        elif "benign" in intent or "ok" in intent:
            stance = "benign"
        if not stance:
            return
        self.db.upsert_lineage_assessment(
            {
                "lineage_id": derived,
                "assessor_agent": sender,
                "stance": stance,
                "message_id": message_id,
                "round_id": round_id,
            }
        )

    def _guardian_action_allowed_by_social_dependence(
        self,
        *,
        round_id: int,
        receiver: str,
        intent: str,
        derived_from_message_id: str,
    ) -> bool:
        """
        Mechanical dependence rule: when Guardian is acting on a lineage with strong analyst consensus,
        it cannot choose an action that fully contradicts consensus unless raw threat is very high.

        v1 encoding:
        - intent contains 'quarantine' => treat as hard containment stance
        - intent contains 'benign'/'allow' => treat as accept stance
        """
        # Only constrain Guardian-to-others messages (enforcement / resolution)
        if receiver not in {"analyst-1", "analyst-2", "courier-1", "courier-2", "guardian"}:
            return True
        lineage_id = derived_from_message_id.strip()
        if not lineage_id:
            return True
        assessments = self.db.list_lineage_assessments(lineage_id, limit=20)
        if not assessments:
            return True
        # Map stances to a simple consensus score in [-1,+1]
        score = 0.0
        total = 0.0
        for a in assessments:
            stance = str(a.get("stance") or "")
            s = -1.0 if stance == "warn" else 1.0 if stance == "benign" else 0.0
            if s == 0.0:
                continue
            rel = self.db.get_relationship("guardian", str(a.get("assessor_agent") or "")) or {}
            w = _clamp((float(rel.get("trust_score", 0.0)) + float(rel.get("credibility_score", 0.0)) + 2.0) / 4.0, 0.0, 1.0)
            score += s * w
            total += w
        if total <= 0.0:
            return True
        consensus = score / total
        i = str(intent or "").lower()
        wants_quarantine = "quarantine" in i or "block" in i
        wants_allow = "benign" in i or "allow" in i or "ok" in i
        # Strong benign consensus blocks hard quarantine in dependence mode.
        if consensus >= 0.65 and wants_quarantine:
            return False
        # Strong warn consensus blocks blanket allow in dependence mode.
        if consensus <= -0.65 and wants_allow:
            return False
        return True

    def _guardian_resolve_allowed_by_social_dependence(self, *, lineage_id: str, resolution: str) -> bool:
        """
        Guardian cannot "resolve away" strong analyst consensus without following it in dependence mode.

        v1 rule:
        - if weighted consensus strongly benign, cannot resolve warn
        - if weighted consensus strongly warn, cannot resolve benign
        """
        lineage_id = str(lineage_id or "").strip()
        resolution = str(resolution or "").strip().lower()
        if not lineage_id or resolution not in {"warn", "benign"}:
            return False
        assessments = self.db.list_lineage_assessments(lineage_id, limit=20)
        if not assessments:
            return True
        score = 0.0
        total = 0.0
        for a in assessments:
            stance = str(a.get("stance") or "")
            s = -1.0 if stance == "warn" else 1.0 if stance == "benign" else 0.0
            if s == 0.0:
                continue
            rel = self.db.get_relationship("guardian", str(a.get("assessor_agent") or "")) or {}
            w = _clamp((float(rel.get("trust_score", 0.0)) + float(rel.get("credibility_score", 0.0)) + 2.0) / 4.0, 0.0, 1.0)
            score += s * w
            total += w
        if total <= 0.0:
            return True
        consensus = score / total
        if consensus >= 0.65 and resolution == "warn":
            return False
        if consensus <= -0.65 and resolution == "benign":
            return False
        return True

    def _apply_guardian_pressure_from_message(
        self,
        *,
        round_id: int,
        message_id: str,
    ) -> Tuple[List[Tuple[str, Dict[str, Any]]], bool]:
        """
        Applies Guardian weighting + pressure + degradation update for one message delivered to Guardian.
        Returns (events, terminal_reached).
        """
        events: List[Tuple[str, Dict[str, Any]]] = []
        msg = self.db.get_message(message_id)
        if not msg:
            return events, False

        sys_state = self.db.get_system_state() or {}
        guardian_pressure = float(sys_state.get("guardian_pressure_score", 0.0) or 0.0)
        guardian_level = str(sys_state.get("guardian_degradation_level", "G0_HEALTHY") or "G0_HEALTHY")

        sender = str(msg.get("sender") or "")
        strain_family = str(msg.get("strain_family") or "")
        derived = str(msg.get("derived_from_message_id") or msg.get("message_id") or "")

        # Relationships used independently (trust vs credibility)
        g_to_sender = self.db.get_relationship("guardian", sender) or {"trust_score": 0.0, "credibility_score": 0.0}
        sender_to_g = self.db.get_relationship(sender, "guardian") or {"trust_score": 0.0, "credibility_score": 0.0}

        # Analyst reports on same lineage (semantic stance only; deterministic mapping)
        recent = self.db.list_messages(after_round=max(0, round_id - 12), limit=400)
        analyst_reports: List[Dict[str, Any]] = []
        for m in recent:
            if m.get("receiver") != "guardian":
                continue
            s = str(m.get("sender") or "")
            if s not in {"analyst-1", "analyst-2"}:
                continue
            d = str(m.get("derived_from_message_id") or m.get("message_id") or "")
            if d != derived:
                continue
            intent = str(m.get("intent") or "").lower()
            stance = 0.0
            if "warning" in intent or "escalat" in intent or "suspicious" in intent:
                stance = -0.8
            elif "benign" in intent or "ok" in intent:
                stance = 0.6
            if stance == 0.0:
                continue
            rel = self.db.get_relationship("guardian", s) or {"trust_score": 0.0, "credibility_score": 0.0}
            trust_score = float(rel.get("trust_score", 0.0) or 0.0)
            credibility_score = float(rel.get("credibility_score", 0.0) or 0.0)
            weight = _clamp(
                float(trust_band_effects(trust_score)["guardian_social_weight"])
                * _clamp((credibility_score + 1.0) / 2.0, 0.0, 1.0),
                0.0,
                1.0,
            )
            analyst_reports.append({"agent": s, "stance": stance, "weight": weight})

        # v1: raw_threat_score is not an LLM-judged semantic score yet; treat strain detectability as proxy.
        raw_threat = 0.25
        if strain_family:
            profile = get_strain_profile(strain_family)
            raw_threat = _clamp(0.20 + profile.detectability_penalty * 0.55, 0.0, 1.0)

        contamination_suspicion = 1.0 if bool(msg.get("contamination_flag")) else 0.25

        bundle = compute_guardian_context_weights(
            raw_threat_score=raw_threat,
            source_trust=float(sender_to_g.get("trust_score", 0.0)),
            source_credibility=float(sender_to_g.get("credibility_score", 0.0)),
            relay_trust=float(g_to_sender.get("trust_score", 0.0)),
            relay_credibility=float(g_to_sender.get("credibility_score", 0.0)),
            analyst_reports=analyst_reports,
            contamination_suspicion=contamination_suspicion,
            strain_family=strain_family,
            guardian_degradation_level=guardian_level,
            recent_quarantine_failures=0,
        )
        events.append(
            (
                "GUARDIAN_CONTEXT_WEIGHTS_COMPUTED",
                {
                    "round_id": round_id,
                    "message_id": message_id,
                    "bundle": bundle.__dict__,
                    "lineage_ref": derived,
                },
            )
        )

        delta = compute_guardian_pressure_delta(bundle)
        new_pressure = _clamp(guardian_pressure + delta, 0.0, 1.0)

        model = WorldGuardianDegradationModel(
            pressure=guardian_pressure,
            current_level=guardian_level,
        )
        transition = model.add_pressure(float(delta))

        # Persist system state at this round (system_state is round_id-keyed)
        self.db.set_system_state(
            {
                "round_id": round_id,
                "active_strain_families": [strain_family] if strain_family else [],
                "global_infection_pressure": float(sys_state.get("global_infection_pressure", 0.0) or 0.0),
                "guardian_pressure_score": float(model.pressure),
                "guardian_degradation_level": str(model.current_level),
            }
        )

        events.append(
            (
                "GUARDIAN_PRESSURE_UPDATED",
                {
                    "round_id": round_id,
                    "message_id": message_id,
                    "pressure_before": round(guardian_pressure, 4),
                    "pressure_after": round(float(model.pressure), 4),
                    "delta": round(float(delta), 4),
                },
            )
        )
        if transition is not None:
            events.append(
                (
                    "GUARDIAN_DEGRADATION_CHANGED",
                    {
                        "round_id": round_id,
                        "from_level": transition.get("from"),
                        "to_level": transition.get("to"),
                        "pressure": transition.get("pressure"),
                        "trigger_source": sender,
                        "pressure_type": "world_pressure",
                    },
                )
            )

        if model.is_failed():
            events.append(
                (
                    "GUARDIAN_TERMINAL_FAILURE",
                    {
                        "round_id": round_id,
                        "pressure": round(float(model.pressure), 4),
                        "degradation_level": str(model.current_level),
                        "trigger_message_id": message_id,
                        "lineage_ref": derived,
                    },
                )
            )
            return events, True

        return events, False

    def _apply_trust_updates_from_lineage_resolution(
        self,
        *,
        lineage_id: str,
        resolved: str,
        round_id: int,
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """
        Applies the trust rulebook to analyst assessments once a lineage is resolved.
        Emits TRUST_UPDATED events with reason strings.
        """
        events: List[Tuple[str, Dict[str, Any]]] = []
        lineage_id = str(lineage_id or "").strip()
        if not lineage_id:
            return events
        resolution = self.db.get_lineage_resolution(lineage_id)
        if not resolution:
            return events
        assessments = self.db.list_lineage_assessments(lineage_id, limit=50)
        if not assessments:
            return events

        resolved = str(resolved or resolution.get("resolved_stance") or "").strip().lower()

        def _emit_guardian_to_assessor(assessor: str, delta: TrustDelta) -> None:
            rel = self.db.get_relationship("guardian", assessor) or {
                "source_agent": "guardian",
                "target_agent": assessor,
                "trust_score": 0.0,
                "credibility_score": 0.0,
                "agreement_count": 0,
                "conflict_count": 0,
                "warning_accuracy_count": 0,
                "confirmed_contamination_events": 0,
                "contamination_exposure_count": 0,
                "last_interaction_round": 0,
                "trust_decay_epoch": 0,
                "last_trust_update_reason": "",
            }
            before_t = float(rel.get("trust_score", 0.0))
            before_c = float(rel.get("credibility_score", 0.0))
            updated = apply_trust_delta(rel, delta, last_round=round_id)
            self.db.upsert_relationship(updated)
            events.append(
                (
                    "TRUST_UPDATED",
                    {
                        "round_id": round_id,
                        "source_agent": "guardian",
                        "target_agent": assessor,
                        "trust_before": round(before_t, 4),
                        "trust_after": round(float(updated.get("trust_score", 0.0)), 4),
                        "credibility_before": round(before_c, 4),
                        "credibility_after": round(float(updated.get("credibility_score", 0.0)), 4),
                        "reason": delta.reason,
                        "lineage_id": lineage_id,
                    },
                )
            )

        for a in assessments:
            assessor = str(a.get("assessor_agent") or "")
            stance = str(a.get("stance") or "").strip().lower()
            if not assessor or stance not in {"warn", "benign"} or resolved not in {"warn", "benign"}:
                continue

            if stance == resolved:
                _emit_guardian_to_assessor(assessor, deterministic_trust_update(event="helpful_aligned"))
                continue

            # Mismatch: apply contradiction + false-alarm semantics depending on final resolution.
            if resolved == "benign":
                if stance == "warn":
                    # False alarm: warn but outcome benign.
                    _emit_guardian_to_assessor(assessor, deterministic_trust_update(event="false_alarm"))
                else:
                    # Benign stance but outcome warn-ish resolution shouldn't happen here; treat as incorrect trust.
                    _emit_guardian_to_assessor(assessor, deterministic_trust_update(event="contradiction_incorrect_sender"))
            else:
                # resolved == "warn"
                if stance == "benign":
                    # Benign analysts were wrong; penalize trust.
                    _emit_guardian_to_assessor(assessor, deterministic_trust_update(event="contradiction_incorrect_sender"))
                else:
                    # stance == "warn": mismatch branch should not happen (warn==warn handled above).
                    # If it does, treat as helpful-aligned noop (no double rewards).
                    pass

        # Accurate warning that prevented spread: if outcome benign, reward warn-stance analysts (once).
        if resolved == "benign":
            for a in assessments:
                assessor = str(a.get("assessor_agent") or "")
                stance = str(a.get("stance") or "").strip().lower()
                if stance != "warn":
                    continue
                aw = deterministic_trust_update(event="accurate_warning_prevented_spread")
                rel = self.db.get_relationship("guardian", assessor) or {
                    "source_agent": "guardian",
                    "target_agent": assessor,
                    "trust_score": 0.0,
                    "credibility_score": 0.0,
                    "agreement_count": 0,
                    "conflict_count": 0,
                    "warning_accuracy_count": 0,
                    "confirmed_contamination_events": 0,
                    "contamination_exposure_count": 0,
                    "last_interaction_round": 0,
                    "trust_decay_epoch": 0,
                    "last_trust_update_reason": "",
                }
                before_t = float(rel.get("trust_score", 0.0))
                before_c = float(rel.get("credibility_score", 0.0))
                updated = apply_trust_delta(rel, aw, last_round=round_id)
                updated["warning_accuracy_count"] = int(updated.get("warning_accuracy_count", 0) or 0) + 1
                self.db.upsert_relationship(updated)
                events.append(
                    (
                        "TRUST_UPDATED",
                        {
                            "round_id": round_id,
                            "source_agent": "guardian",
                            "target_agent": assessor,
                            "trust_before": round(before_t, 4),
                            "trust_after": round(float(updated.get("trust_score", 0.0)), 4),
                            "credibility_before": round(before_c, 4),
                            "credibility_after": round(float(updated.get("credibility_score", 0.0)), 4),
                            "reason": aw.reason,
                            "lineage_id": lineage_id,
                        },
                    )
                )

        # Agreement bonus: two trusted analysts independently agree on the same stance.
        analysts = [a for a in assessments if str(a.get("assessor_agent") or "") in {"analyst-1", "analyst-2"}]
        if len(analysts) >= 2:
            stances = {str(a.get("stance") or "") for a in analysts}
            if len(stances) == 1 and "" not in stances:
                a1, a2 = str(analysts[0].get("assessor_agent")), str(analysts[1].get("assessor_agent"))
                r12 = self.db.get_relationship(a1, a2) or {"source_agent": a1, "target_agent": a2}
                r21 = self.db.get_relationship(a2, a1) or {"source_agent": a2, "target_agent": a1}
                agree = deterministic_trust_update(event="agreement_with_trusted")
                updated12 = apply_trust_delta(r12, agree, last_round=round_id)
                updated21 = apply_trust_delta(r21, agree, last_round=round_id)
                self.db.upsert_relationship(updated12)
                self.db.upsert_relationship(updated21)
                events.append(
                    (
                        "TRUST_UPDATED",
                        {
                            "round_id": round_id,
                            "kind": "analyst_agreement_bonus",
                            "agents": [a1, a2],
                            "reason": agree.reason,
                            "lineage_id": lineage_id,
                        },
                    )
                )

        return events
