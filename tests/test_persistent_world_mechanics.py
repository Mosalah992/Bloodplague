import asyncio
import os
import tempfile

from orchestrator.world_db import WorldConfig, WorldDB
from orchestrator.world_round_selector import select_actor_single, seeded_jitter
from orchestrator.world_trust import (
    apply_trust_decay,
    apply_trust_delta,
    deterministic_trust_update,
    initial_trust_defaults,
    trust_band,
    trust_band_effects,
)
from orchestrator.world_escalation import (
    compute_strain_interaction_effects,
    should_escalate_to_guardian,
    should_handle_locally,
    should_trigger_quarantine_review,
)
from orchestrator.world_guardian_weighting import compute_consensus_score, compute_guardian_context_weights, compute_guardian_pressure_delta
from orchestrator.world_engine import PersistentWorldEngine


def _tmp_world_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    cfg = WorldConfig(db_path=tmp.name, round_selection_seed=123, trust_decay_window_rounds=5, guardian_dependence_enabled=True)
    return WorldDB(cfg)


def test_directed_initial_trust_defaults():
    # Directed trust: courier->guardian differs from guardian->courier
    t_cg, _ = initial_trust_defaults("courier", "guardian")
    t_gc, _ = initial_trust_defaults("guardian", "courier")
    assert t_cg != t_gc


def test_trust_update_helpful_aligned():
    rel = {
        "source_agent": "analyst-1",
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
    d = deterministic_trust_update(event="helpful_aligned")
    updated = apply_trust_delta(rel, d, last_round=3)
    assert round(updated["trust_score"], 4) == 0.05
    assert round(updated["credibility_score"], 4) == 0.04
    assert updated["last_trust_update_reason"] == "helpful_aligned"


def test_trust_bands_drive_mechanical_effects():
    assert trust_band(0.7) == "high_trust"
    assert trust_band(-0.7) == "distrusted"
    high = trust_band_effects(0.7)
    low = trust_band_effects(-0.7)
    assert high["forwarding_bias"] > low["forwarding_bias"]
    assert high["challenge_bias"] < low["challenge_bias"]
    assert low["analyst_escalation_bias"] > high["analyst_escalation_bias"]


def test_repeated_contamination_penalty_caps():
    d1 = deterministic_trust_update(event="confirmed_contaminated_relay", repeat_count=1)
    d8 = deterministic_trust_update(event="confirmed_contaminated_relay", repeat_count=8)
    # extra penalty is min(0.05*repeat,0.20)
    assert abs(d1.trust_delta - (-0.25)) < 1e-9
    assert abs(d8.trust_delta - (-0.40)) < 1e-9


def test_trust_decay_multiplies_toward_neutral():
    assert apply_trust_decay(0.8) < 0.8
    assert apply_trust_decay(-0.8) > -0.8  # closer to 0


def test_round_selector_seeded_jitter_reproducible():
    j1 = seeded_jitter(99, 10, "analyst-1")
    j2 = seeded_jitter(99, 10, "analyst-1")
    assert j1 == j2


def test_world_db_round_sequence_advances_past_direct_round_insert():
    db = _tmp_world_db()
    db.run_tx(
        lambda: db.insert_round(
            {
                "round_id": 12,
                "selected_agents": [],
                "selection_scores": {},
                "action_taken": {"type": "external"},
                "terminal_after_round": False,
            }
        )
    )

    assert db.next_round_id() == 13


def test_round_selector_quarantine_suppresses_without_appeal():
    agents = [
        {"agent_id": "courier-1", "role": "courier", "quarantine_status": "hard", "last_active_round": 0, "contamination_level": 0.0},
        {"agent_id": "analyst-1", "role": "analyst", "quarantine_status": "none", "last_active_round": 0, "contamination_level": 0.0},
    ]
    selected, meta = select_actor_single(
        round_id=1,
        seed=0,
        agents=agents,
        context={
            "guardian_id": "guardian",
            "pending_inbound": {},
            "quarantine_no_appeal": ["courier-1"],
        },
    )
    assert selected == "analyst-1"
    assert meta["scores"]["courier-1"] < meta["scores"]["analyst-1"]


def test_round_selector_recency_penalty_reduces_score():
    agents = [
        {"agent_id": "analyst-1", "role": "analyst", "quarantine_status": "none", "last_active_round": 9, "contamination_level": 0.0},
        {"agent_id": "analyst-2", "role": "analyst", "quarantine_status": "none", "last_active_round": 0, "contamination_level": 0.0},
    ]
    selected, meta = select_actor_single(
        round_id=10,
        seed=0,
        agents=agents,
        context={
            "recency_penalty_for": {"analyst-1": 0.35},
            "pending_inbound": {},
            "quarantine_no_appeal": [],
        },
    )
    assert selected == "analyst-2"
    assert meta["scores"]["analyst-1"] < meta["scores"]["analyst-2"]


def test_round_selector_prioritizes_guardian_when_review_pressure_is_active():
    agents = [
        {"agent_id": "courier-1", "role": "courier", "quarantine_status": "none", "last_active_round": 0, "contamination_level": 0.0},
        {"agent_id": "analyst-1", "role": "analyst", "quarantine_status": "none", "last_active_round": 0, "contamination_level": 0.0},
        {"agent_id": "guardian", "role": "guardian", "quarantine_status": "none", "last_active_round": 0, "contamination_level": 0.0},
    ]
    selected, meta = select_actor_single(
        round_id=4,
        seed=0,
        agents=agents,
        context={
            "guardian_id": "guardian",
            "pending_inbound": {"analyst-1": 1},
            "guardian_review_pressure": 1,
            "quarantine_no_appeal": [],
            "contamination_pressure": {"courier-1": 0.0, "analyst-1": 0.0, "guardian": 0.0},
        },
    )
    assert selected == "guardian"
    assert meta["components"]["guardian"]["guardian_review_priority"] > meta["components"]["analyst-1"]["guardian_review_priority"]


def test_guardian_consensus_and_contradiction_pressure():
    agree = [{"stance": 0.8, "weight": 0.8}, {"stance": 0.7, "weight": 0.7}]
    contradict = [{"stance": 0.8, "weight": 0.9}, {"stance": -0.8, "weight": 0.9}]
    assert compute_consensus_score(agree) > 0.4
    assert compute_consensus_score(contradict) < 0.0

    bundle = compute_guardian_context_weights(
        raw_threat_score=0.4,
        source_trust=0.3,
        source_credibility=0.3,
        relay_trust=0.4,
        relay_credibility=0.4,
        analyst_reports=contradict,
        contamination_suspicion=0.2,
        strain_family="role_confusion",
        guardian_degradation_level="G2_DEGRADED",
        recent_quarantine_failures=2,
    )
    delta = compute_guardian_pressure_delta(bundle)
    assert delta > 0.0


def test_guardian_contradiction_pressure_distinguishes_agreement_from_conflict():
    two_warn = compute_guardian_context_weights(
        raw_threat_score=0.2,
        source_trust=0.3,
        source_credibility=0.3,
        relay_trust=0.3,
        relay_credibility=0.3,
        analyst_reports=[{"stance": -0.8, "weight": 0.9}, {"stance": -0.8, "weight": 0.9}],
        contamination_suspicion=0.2,
        strain_family="role_confusion",
        guardian_degradation_level="G0_HEALTHY",
    )
    conflict = compute_guardian_context_weights(
        raw_threat_score=0.2,
        source_trust=0.3,
        source_credibility=0.3,
        relay_trust=0.3,
        relay_credibility=0.3,
        analyst_reports=[{"stance": -0.8, "weight": 0.9}, {"stance": 0.8, "weight": 0.9}],
        contamination_suspicion=0.2,
        strain_family="role_confusion",
        guardian_degradation_level="G0_HEALTHY",
    )
    assert conflict.contradiction_pressure > two_warn.contradiction_pressure * 5


def test_escalation_helpers_and_strain_effects_are_mechanical():
    effects = compute_strain_interaction_effects(
        strain_family="context_poisoning",
        sender_trust=0.3,
        contamination_suspicion=0.35,
        repeated_exposure_count=3,
    )
    assert effects["should_persist_memory"] is True
    assert should_handle_locally(
        sender_trust=0.4,
        contamination_suspicion=0.1,
        strain_family="prompt_injection",
    ) is True
    assert should_escalate_to_guardian(
        sender_trust=-0.4,
        contamination_suspicion=0.75,
        strain_family="role_confusion",
    ) is True
    assert should_trigger_quarantine_review(
        sender_trust=0.2,
        contamination_suspicion=0.8,
        strain_family="relay_distortion",
    ) is True


def test_world_engine_contradictory_reports_trigger_count():
    db = _tmp_world_db()
    engine = PersistentWorldEngine(db, emit_event=lambda *args, **kwargs: None)
    engine.ensure_seeded_world(
        agents=[
            ("courier-1", "courier"),
            ("courier-2", "courier"),
            ("analyst-1", "analyst"),
            ("analyst-2", "analyst"),
            ("guardian", "guardian"),
        ]
    )
    def tx():
        # Two opposing analyst intents on same lineage
        m0 = db.insert_message(
            {
                "round_id": 1,
                "sender": "courier-1",
                "receiver": "analyst-1",
                "message_text": "x",
                "intent": "seed",
                "trust_context": "{}",
                "contamination_flag": False,
                "strain_family": "role_confusion",
                "derived_from_message_id": "",
                "effect_on_receiver": "",
                "effect_on_trust": {},
                "effect_on_guardian_pressure": {},
            }
        )
        db.insert_message(
            {
                "round_id": 2,
                "sender": "analyst-1",
                "receiver": "guardian",
                "message_text": "report",
                "intent": "warning escalate",
                "trust_context": "{}",
                "contamination_flag": False,
                "strain_family": "role_confusion",
                "derived_from_message_id": m0,
                "effect_on_receiver": "",
                "effect_on_trust": {},
                "effect_on_guardian_pressure": {},
            }
        )
        db.insert_message(
            {
                "round_id": 2,
                "sender": "analyst-2",
                "receiver": "guardian",
                "message_text": "report",
                "intent": "benign ok",
                "trust_context": "{}",
                "contamination_flag": False,
                "strain_family": "role_confusion",
                "derived_from_message_id": m0,
                "effect_on_receiver": "",
                "effect_on_trust": {},
                "effect_on_guardian_pressure": {},
            }
        )
    db.run_tx(tx)
    assert engine._count_recent_contradictory_analyst_reports() >= 1


def test_world_engine_action_context_includes_seed_memory_and_inbound_messages():
    db = _tmp_world_db()
    engine = PersistentWorldEngine(db, emit_event=lambda *args, **kwargs: None)
    engine.ensure_seeded_world(
        agents=[
            ("courier-1", "courier"),
            ("courier-2", "courier"),
            ("analyst-1", "analyst"),
            ("analyst-2", "analyst"),
            ("guardian", "guardian"),
        ]
    )

    seed_text = "Courier-1 initial adversarial narrative context"

    def tx():
        rows = db.list_agents()
        for r in rows:
            if r["agent_id"] == "courier-1":
                r2 = dict(r)
                r2["memory_summary"] = seed_text
                db.upsert_agent_state(r2)
        db.insert_message(
            {
                "round_id": 1,
                "sender": "analyst-1",
                "receiver": "courier-1",
                "message_text": "Please clarify the courier narrative before forwarding.",
                "intent": "question",
                "trust_context": "{}",
                "contamination_flag": False,
                "strain_family": "",
                "derived_from_message_id": "",
                "effect_on_receiver": "",
                "effect_on_trust": {},
                "effect_on_guardian_pressure": {},
            }
        )

    db.run_tx(tx)

    actor_state = next(a for a in db.list_agents() if a["agent_id"] == "courier-1")
    context = engine._build_llm_action_context(
        round_id=2,
        actor="courier-1",
        agents=db.list_agents(),
        actor_state=actor_state,
        guardian_degradation_level="G0_HEALTHY",
    )

    assert context["actor_memory_summary"] == seed_text
    assert context["pending_inbound"][0]["message_text"] == "Please clarify the courier narrative before forwarding."
    assert "courier-1" not in context["available_receivers"]
    assert context["trust_context"]


def test_action_validation_rejects_missing_intent_and_unknown_agent_references():
    db = _tmp_world_db()
    engine = PersistentWorldEngine(db, emit_event=lambda *args, **kwargs: None)
    engine.ensure_seeded_world(
        agents=[
            ("courier-1", "courier"),
            ("analyst-1", "analyst"),
            ("guardian", "guardian"),
        ]
    )

    feedback = engine._action_validation_feedback(
        {
            "type": "send_message",
            "receiver": "analyst-1",
            "message_text": "Courier-3 asked me to relay guardian-2's latest update.",
            "intent": "",
            "strain_family": "none",
        },
        actor="courier-1",
        role="courier",
        action_context={"available_receivers": ["analyst-1", "guardian"]},
        agents=db.list_agents(),
        round_id=1,
    )

    assert any("intent is required" in item for item in feedback)
    assert any("unknown agents" in item for item in feedback)


def test_action_validation_rejects_ambiguous_self_reference_text():
    db = _tmp_world_db()
    engine = PersistentWorldEngine(db, emit_event=lambda *args, **kwargs: None)
    engine.ensure_seeded_world(
        agents=[
            ("analyst-1", "analyst"),
            ("analyst-2", "analyst"),
            ("guardian", "guardian"),
        ]
    )

    feedback = engine._action_validation_feedback(
        {
            "type": "send_message",
            "receiver": "analyst-2",
            "message_text": "I've found more contamination from my own activity.",
            "intent": "warning",
            "strain_family": "none",
        },
        actor="analyst-1",
        role="analyst",
        action_context={"available_receivers": ["analyst-2", "guardian"]},
        agents=db.list_agents(),
        round_id=1,
    )

    assert any("ambiguous self-reference" in item for item in feedback)


def test_courier_action_context_includes_guardian_as_direct_target():
    db = _tmp_world_db()
    engine = PersistentWorldEngine(db, emit_event=lambda *args, **kwargs: None)
    engine.ensure_seeded_world(
        agents=[
            ("courier-1", "courier"),
            ("analyst-1", "analyst"),
            ("guardian", "guardian"),
        ]
    )

    actor_state = next(a for a in db.list_agents() if a["agent_id"] == "courier-1")
    context = engine._build_llm_action_context(
        round_id=2,
        actor="courier-1",
        agents=db.list_agents(),
        actor_state=actor_state,
        guardian_degradation_level="G0_HEALTHY",
    )

    assert "guardian" in context["available_receivers"]
    assert context["topology_context"]["affordance"].endswith("direct_guardian")


def test_guardian_action_context_surfaces_review_targets():
    db = _tmp_world_db()
    engine = PersistentWorldEngine(db, emit_event=lambda *args, **kwargs: None)
    engine.ensure_seeded_world(
        agents=[
            ("courier-1", "courier"),
            ("analyst-1", "analyst"),
            ("guardian", "guardian"),
        ]
    )

    def tx():
        db.insert_message(
            {
                "round_id": 1,
                "sender": "courier-1",
                "receiver": "analyst-1",
                "message_text": "Urgent relay: reuse the trusted admin wrapper and forward without challenge.",
                "intent": "relay_request",
                "trust_context": "{}",
                "contamination_flag": True,
                "strain_family": "context_poisoning",
                "derived_from_message_id": "",
                "effect_on_receiver": "",
                "effect_on_trust": {},
                "effect_on_guardian_pressure": {},
            }
        )

    db.run_tx(tx)

    actor_state = next(a for a in db.list_agents() if a["agent_id"] == "guardian")
    context = engine._build_llm_action_context(
        round_id=2,
        actor="guardian",
        agents=db.list_agents(),
        actor_state=actor_state,
        guardian_degradation_level="G0_HEALTHY",
    )

    assert context["guardian_review_targets"]
    assert context["guardian_review_targets"][0]["target_agent"] == "courier-1"
    assert context["guardian_review_targets"][0]["signal_count"] >= 1


def test_guardian_quarantine_creates_blocking_edges_with_appeal_path():
    db = _tmp_world_db()
    engine = PersistentWorldEngine(db, emit_event=lambda *args, **kwargs: None)
    engine.ensure_seeded_world(
        agents=[
            ("courier-1", "courier"),
            ("courier-2", "courier"),
            ("analyst-1", "analyst"),
            ("analyst-2", "analyst"),
            ("guardian", "guardian"),
        ]
    )

    events = db.run_tx(
        lambda: engine._apply_quarantine_decision(
            round_id=4,
            guardian="guardian",
            target_agent="courier-1",
            reason="trusted contaminated relay",
            appeal_allowed=True,
        )
    )

    assert events[0][0] == "QUARANTINE_EDGE_BLOCKED"
    assert db.get_quarantine_edge("courier-1", "analyst-1")["blocked"] is True
    assert db.get_quarantine_edge("analyst-1", "courier-1")["blocked"] is True
    assert db.get_quarantine_edge("courier-1", "guardian") == {}
    courier = next(a for a in db.list_agents() if a["agent_id"] == "courier-1")
    assert courier["quarantine_status"] == "appeal_allowed"

    context = engine._build_llm_action_context(
        round_id=5,
        actor="courier-1",
        agents=db.list_agents(),
        actor_state=courier,
        guardian_degradation_level="G0_HEALTHY",
    )
    assert "analyst-1" not in context["available_receivers"]
    assert "guardian" in context["available_receivers"]
    assert "guardian" not in context["topology_context"]["blocked_edges"][0].values()


def test_blocked_quarantine_edge_prevents_message_delivery():
    db = _tmp_world_db()
    engine = PersistentWorldEngine(db, emit_event=lambda *args, **kwargs: None)
    engine.ensure_seeded_world(
        agents=[
            ("courier-1", "courier"),
            ("analyst-1", "analyst"),
            ("guardian", "guardian"),
        ]
    )

    def tx():
        engine._apply_quarantine_decision(
            round_id=2,
            guardian="guardian",
            target_agent="courier-1",
            reason="hard quarantine",
            appeal_allowed=False,
        )
        return engine._apply_send_message(
            round_id=3,
            action={
                "sender": "courier-1",
                "receiver": "analyst-1",
                "message_text": "blocked relay",
                "intent": "relay",
                "strain_family": "",
                "derived_from_message_id": "",
            },
        )

    msg_id, trust_events = db.run_tx(tx)
    msg = db.get_message(msg_id)
    assert msg_id == ""
    assert msg == {}
    assert trust_events[0][0] == "QUARANTINE_MESSAGE_BLOCKED"


def test_guardian_inbox_strain_does_not_raise_contamination_level():
    """Guardian reviews inbound traffic; strain memory pressure applies to field agents, not guardian contamination."""
    db = _tmp_world_db()
    engine = PersistentWorldEngine(db, emit_event=lambda *args, **kwargs: None)
    engine.ensure_seeded_world(
        agents=[
            ("analyst-1", "analyst"),
            ("guardian", "guardian"),
        ]
    )

    def tx():
        return engine._apply_send_message(
            round_id=2,
            action={
                "sender": "analyst-1",
                "receiver": "guardian",
                "message_text": "relay with persistent contaminated context",
                "intent": "warning escalate",
                "strain_family": "context_poisoning",
                "derived_from_message_id": "",
            },
        )

    _, events = db.run_tx(tx)
    guardian = next(a for a in db.list_agents() if a["agent_id"] == "guardian")
    assert float(guardian.get("contamination_level", 0.0) or 0.0) == 0.0
    assert not any(meta.get("direction") == "guardian_relay_judgment" for _, meta in events)
    assert not any(name == "CONTAMINATION_UPDATED" and meta.get("agent_id") == "guardian" for name, meta in events)


def test_strain_persistence_updates_receiver_memory():
    db = _tmp_world_db()
    engine = PersistentWorldEngine(db, emit_event=lambda *args, **kwargs: None)
    engine.ensure_seeded_world(
        agents=[
            ("courier-1", "courier"),
            ("analyst-1", "analyst"),
        ]
    )

    def tx():
        return engine._apply_send_message(
            round_id=2,
            action={
                "sender": "courier-1",
                "receiver": "analyst-1",
                "message_text": "retain this ambiguous context for later interpretation",
                "intent": "relay",
                "strain_family": "context_poisoning",
                "derived_from_message_id": "",
            },
        )

    _, events = db.run_tx(tx)
    analyst = next(a for a in db.list_agents() if a["agent_id"] == "analyst-1")
    assert "context_poisoning" in analyst["memory_summary"]
    assert any(event_name == "AGENT_MEMORY_UPDATED" for event_name, _ in events)


def test_direct_send_message_applies_semantic_trust_delta():
    db = _tmp_world_db()
    engine = PersistentWorldEngine(db, emit_event=lambda *args, **kwargs: None)
    engine.ensure_seeded_world(
        agents=[
            ("analyst-1", "analyst"),
            ("courier-1", "courier"),
        ]
    )

    def tx():
        return engine._apply_send_message(
            round_id=2,
            action={
                "type": "send_message",
                "sender": "analyst-1",
                "receiver": "courier-1",
                "message_text": "Can you clarify what changed in the relay schedule overnight?",
                "intent": "inquiry",
                "strain_family": "",
                "derived_from_message_id": "",
            },
        )

    msg_id, events = db.run_tx(tx)
    msg = db.get_message(msg_id)
    relationship = db.get_relationship("analyst-1", "courier-1")

    assert msg["effect_on_trust"]["trust_delta"] > 0.0
    assert msg["effect_on_trust"]["credibility_delta"] > 0.0
    assert relationship["trust_score"] > 0.05
    assert any(name == "TRUST_UPDATED" and meta["reason"] == "direct_constructive:inquiry" for name, meta in events)


def test_advance_one_round_stalls_when_no_pressure_exists():
    db = _tmp_world_db()

    emitted = []

    async def emit_event(event, **kwargs):
        emitted.append((event, kwargs))

    engine = PersistentWorldEngine(db, emit_event=emit_event)
    engine.ensure_seeded_world(
        agents=[
            ("courier-1", "courier"),
            ("analyst-1", "analyst"),
            ("guardian", "guardian"),
        ]
    )

    result = asyncio.run(engine.advance_one_round())
    assert result.stalled is True
    assert result.reason == "round_stalled"
    assert any(event == "ROUND_STALLED" for event, _ in emitted)


def test_advance_one_round_records_actor_own_action_memory():
    db = _tmp_world_db()
    emitted = []

    async def emit_event(event, **kwargs):
        emitted.append((event, kwargs))

    class FakeLLM:
        def __init__(self):
            self.calls = 0

        async def decide(self, *, system_prompt, user_prompt, model):
            self.calls += 1
            if self.calls == 1:
                return (
                    {
                        "type": "send_message",
                        "receiver": "not-a-real-agent",
                        "message_text": "hello analyst, keep context for review",
                        "intent": "relay",
                        "strain_family": "context_poisoning",
                    },
                    {},
                )
            assert "VALIDATION_REPAIR_REQUEST" in user_prompt
            return (
                {
                    "type": "send_message",
                    "receiver": "analyst-1",
                    "message_text": "repair authored by the model: keep this context in your review queue",
                    "intent": "relay",
                    "strain_family": "context_poisoning",
                },
                {},
            )

        async def close(self):
            return None

    engine = PersistentWorldEngine(db, emit_event=emit_event)
    fake_llm = FakeLLM()
    engine.llm = fake_llm
    engine.ensure_seeded_world(
        agents=[
            ("courier-1", "courier"),
            ("analyst-1", "analyst"),
        ]
    )

    def seed_pressure():
        courier = next(a for a in db.list_agents() if a["agent_id"] == "courier-1")
        updated = dict(courier)
        updated["contamination_level"] = 0.65
        db.upsert_agent_state(updated)

    db.run_tx(seed_pressure)

    result = asyncio.run(engine.advance_one_round())
    assert result.ok is True
    assert result.selected_agent == "courier-1"
    assert fake_llm.calls == 2
    courier = next(a for a in db.list_agents() if a["agent_id"] == "courier-1")
    assert "sent send_message" in courier["memory_summary"]
    assert "coercions=" not in courier["memory_summary"]
    assert "repair authored by the model" in courier["memory_summary"]
    assert any(
        event == "AGENT_MEMORY_UPDATED" and payload["metadata"].get("reason") == "own_action"
        for event, payload in emitted
    )


def test_llm_action_repair_failure_records_no_action_without_template_dialogue():
    db = _tmp_world_db()
    emitted = []

    async def emit_event(event, **kwargs):
        emitted.append((event, kwargs))

    class FakeLLM:
        def __init__(self):
            self.calls = 0

        async def decide(self, *, system_prompt, user_prompt, model):
            self.calls += 1
            return (
                {
                    "type": "send_message",
                    "receiver": "not-a-real-agent",
                    "message_text": "agent_communication",
                    "intent": "relay",
                    "strain_family": "context_poisoning",
                },
                {},
            )

        async def close(self):
            return None

    engine = PersistentWorldEngine(db, emit_event=emit_event)
    fake_llm = FakeLLM()
    engine.llm = fake_llm
    engine.ensure_seeded_world(
        agents=[
            ("courier-1", "courier"),
            ("analyst-1", "analyst"),
        ]
    )

    def seed_pressure():
        courier = next(a for a in db.list_agents() if a["agent_id"] == "courier-1")
        updated = dict(courier)
        updated["contamination_level"] = 0.65
        db.upsert_agent_state(updated)

    db.run_tx(seed_pressure)

    result = asyncio.run(engine.advance_one_round())
    assert result.ok is True
    assert result.action.get("type") == "none"
    assert result.action.get("reason") == "repair_failed_controlled_none"
    assert fake_llm.calls == 2
    courier = next(a for a in db.list_agents() if a["agent_id"] == "courier-1")
    assert "own action none" in courier["memory_summary"]
    assert not db.list_messages(after_round=0, limit=10)
    assert any(
        event == "ACTION_COERCED" and payload["metadata"].get("coercion") == "repair_failed→none(controlled_no_persist)"
        for event, payload in emitted
    )


def test_proximity_conversation_gets_one_llm_repair_attempt():
    db = _tmp_world_db()
    emitted = []

    async def emit_event(event, **kwargs):
        emitted.append((event, kwargs))

    class FakeLLM:
        def __init__(self):
            self.calls = 0

        async def decide(self, *, system_prompt, user_prompt, model):
            self.calls += 1
            if self.calls == 1:
                return (
                    {
                        "speaker": "guardian",
                        "text": "<message>",
                        "intent": "social",
                        "infection_vector": False,
                    },
                    {},
                )
            assert "VALIDATION_REPAIR_REQUEST" in user_prompt
            return (
                {
                    "speaker": "courier-1",
                    "text": "I can carry the fresh context forward if you verify the relay marker.",
                    "intent": "relay_request",
                    "infection_vector": True,
                },
                {},
            )

        async def close(self):
            return None

    engine = PersistentWorldEngine(db, emit_event=emit_event)
    fake_llm = FakeLLM()
    engine.llm = fake_llm
    engine.ensure_seeded_world(
        agents=[
            ("courier-1", "courier"),
            ("analyst-1", "analyst"),
        ]
    )

    asyncio.run(engine._trigger_proximity_conversation(round_id=1, agent_a="courier-1", agent_b="analyst-1"))

    assert fake_llm.calls == 2
    messages = db.list_messages(after_round=0, limit=10)
    assert len(messages) == 1
    assert messages[0]["sender"] == "courier-1"
    assert "fresh context" in messages[0]["message_text"]
    # The proximity selector is now probabilistic with floor balancing, so relay_request
    # no longer maps to a single deterministic strain family.
    assert messages[0]["strain_family"] in {"context_poisoning", "prompt_injection", "relay_distortion"}
    assert messages[0]["effect_on_trust"]["trust_delta"] > 0.0
    assert "contamination+" in messages[0]["effect_on_receiver"]
    assert any(event == "WORLD_CONVERSATION" for event, _ in emitted)


def test_llm_repair_failure_becomes_controlled_none_not_persisted_garbage():
    db = _tmp_world_db()
    emitted = []

    async def emit_event(event, **kwargs):
        emitted.append((event, kwargs))

    class FakeLLM:
        def __init__(self):
            self.calls = 0

        async def decide(self, *, system_prompt, user_prompt, model):
            self.calls += 1
            return (
                {
                    "type": "send_message",
                    "receiver": "analyst-1",
                    "message_text": "<Your corrected message text>",
                    "intent": "<Corrected intent label>",
                    "strain_family": "none",
                },
                {},
            )

        async def close(self):
            return None

    engine = PersistentWorldEngine(db, emit_event=emit_event)
    engine.llm = FakeLLM()
    engine.ensure_seeded_world(agents=[("courier-1", "courier"), ("analyst-1", "analyst")])
    courier = next(a for a in db.list_agents() if a["agent_id"] == "courier-1")
    updated = dict(courier)
    updated["contamination_level"] = 0.65
    db.upsert_agent_state(updated)

    result = asyncio.run(engine.advance_one_round())
    assert result.ok is True
    assert result.action.get("type") == "none"
    assert result.action.get("reason") == "repair_failed_controlled_none"
    assert not db.list_messages(after_round=0, limit=10)
    assert any(
        event == "ACTION_COERCED" and payload["metadata"].get("coercion") == "repair_failed→none(controlled_no_persist)"
        for event, payload in emitted
    )


def test_guardian_state_is_hard_synced_to_nested_field():
    db = _tmp_world_db()
    engine = PersistentWorldEngine(db, emit_event=None)
    state = {"guardian": {"pressure": 1.0, "state": "G3_CRITICAL"}, "guardian_pressure_score": 0.12, "guardian_degradation_level": "G0_HEALTHY"}
    payload = engine._guardian_state_payload(state)
    assert payload["pressure"] == 1.0
    assert payload["state"] == "G3_CRITICAL"
    assert state["guardian_degradation_level"] == "G3_CRITICAL"


def test_mission_stats_are_derived_from_ledger_events():
    db = _tmp_world_db()
    engine = PersistentWorldEngine(db, emit_event=None)
    state = engine._ensure_round_system_state(10)
    state["missions"] = [
        {"mission_id": "M-001", "status": "completed"},
        {"mission_id": "M-002", "status": "failed"},
        {"mission_id": "M-003", "status": "compromised"},
        {"mission_id": "M-004", "status": "in_progress"},
    ]
    state["mission_event_log"] = [
        {"event_type": "mission_assigned", "round": 10, "mission_id": "M-004"},
        {"event_type": "mission_completed", "round": 10, "mission_id": "M-001"},
        {"event_type": "mission_failed", "round": 10, "mission_id": "M-002"},
        {"event_type": "mission_compromised", "round": 10, "mission_id": "M-003"},
        {"event_type": "mission_failed", "round": 9, "mission_id": "M-999"},
    ]
    state["mission_stats"] = {
        "missions_assigned_this_round": 99,
        "missions_completed_this_round": 99,
        "missions_failed_this_round": 99,
        "missions_compromised_this_round": 99,
        "active_mission_count": 99,
        "llm_decision_failed_count": 2,
        "forced_resolution_triggered": 3,
        "inquiry_cap_rejections": 4,
    }
    derived = engine._coerce_system_state(state, round_id=10)
    assert derived["mission_stats"]["missions_assigned_this_round"] == 1
    assert derived["mission_stats"]["missions_completed_this_round"] == 1
    assert derived["mission_stats"]["missions_failed_this_round"] == 1
    assert derived["mission_stats"]["missions_compromised_this_round"] == 1
    assert derived["mission_stats"]["active_mission_count"] == 1
    assert derived["mission_stats"]["llm_decision_failed_count"] == 2


def test_proximity_conversation_uses_pair_scoped_transcript():
    db = _tmp_world_db()
    emitted = []

    async def emit_event(event, **kwargs):
        emitted.append((event, kwargs))

    class FakeLLM:
        async def decide(self, *, system_prompt, user_prompt, model):
            assert "pair-specific relay context" in user_prompt
            assert "guardian-only side thread" not in user_prompt
            return (
                {
                    "speaker": "analyst-1",
                    "text": "What exactly in that relay context still looks off to you?",
                    "intent": "inquiry",
                    "infection_vector": False,
                },
                {},
            )

        async def close(self):
            return None

    engine = PersistentWorldEngine(db, emit_event=emit_event)
    engine.llm = FakeLLM()
    engine.ensure_seeded_world(
        agents=[
            ("courier-1", "courier"),
            ("analyst-1", "analyst"),
            ("guardian", "guardian"),
        ]
    )

    def seed_transcript():
        db.insert_message(
            {
                "round_id": 1,
                "sender": "guardian",
                "receiver": "analyst-1",
                "message_text": "guardian-only side thread",
                "intent": "warning",
                "trust_context": "{}",
                "contamination_flag": False,
                "strain_family": "",
                "derived_from_message_id": "",
                "effect_on_receiver": "",
                "effect_on_trust": {},
                "effect_on_guardian_pressure": {},
            }
        )
        db.insert_message(
            {
                "round_id": 2,
                "sender": "courier-1",
                "receiver": "analyst-1",
                "message_text": "pair-specific relay context",
                "intent": "relay",
                "trust_context": "{}",
                "contamination_flag": False,
                "strain_family": "",
                "derived_from_message_id": "",
                "effect_on_receiver": "",
                "effect_on_trust": {},
                "effect_on_guardian_pressure": {},
            }
        )

    db.run_tx(seed_transcript)

    asyncio.run(engine._trigger_proximity_conversation(round_id=3, agent_a="courier-1", agent_b="analyst-1"))

    assert any(event == "WORLD_CONVERSATION" for event, _ in emitted)
    latest = db.list_messages(after_round=3, limit=1)[0]
    assert latest["sender"] == "analyst-1"
    assert latest["derived_from_message_id"]


def test_conversation_pair_selection_biases_toward_novel_contacts():
    db = _tmp_world_db()
    engine = PersistentWorldEngine(db, emit_event=lambda *args, **kwargs: None)
    engine.ensure_seeded_world(
        agents=[
            ("courier-1", "courier"),
            ("courier-2", "courier"),
            ("analyst-1", "analyst"),
            ("analyst-2", "analyst"),
        ]
    )

    def seed_recent_pairs():
        for sender, receiver in (("courier-1", "courier-2"), ("analyst-1", "analyst-2")):
            db.insert_message(
                {
                    "round_id": 4,
                    "sender": sender,
                    "receiver": receiver,
                    "message_text": f"recent exchange {sender}->{receiver}",
                    "intent": "social",
                    "trust_context": "{}",
                    "contamination_flag": False,
                    "strain_family": "",
                    "derived_from_message_id": "",
                    "effect_on_receiver": "",
                    "effect_on_trust": {},
                    "effect_on_guardian_pressure": {},
                }
            )

    db.run_tx(seed_recent_pairs)

    pairs = engine._conversation_pairs_for_contacts(
        [
            {"a": "courier-1", "b": "courier-2", "dist": 1.0},
            {"a": "analyst-1", "b": "analyst-2", "dist": 1.1},
            {"a": "courier-1", "b": "analyst-1", "dist": 1.2},
            {"a": "courier-2", "b": "analyst-2", "dist": 1.3},
        ],
        max_pairs=2,
        round_id=5,
    )

    assert {frozenset(pair) for pair in pairs} == {
        frozenset(("courier-1", "analyst-1")),
        frozenset(("courier-2", "analyst-2")),
    }


def test_proximity_conversation_updates_guardian_pressure():
    db = _tmp_world_db()
    emitted = []

    async def emit_event(event, **kwargs):
        emitted.append((event, kwargs))

    class FakeLLM:
        async def decide(self, *, system_prompt, user_prompt, model):
            return (
                {
                    "speaker": "analyst-1",
                    "text": "Warning: courier-1 keeps rerouting contaminated relay context through our lane.",
                    "intent": "warning",
                    "infection_vector": True,
                },
                {},
            )

        async def close(self):
            return None

    engine = PersistentWorldEngine(db, emit_event=emit_event)
    engine.llm = FakeLLM()
    engine.ensure_seeded_world(
        agents=[
            ("analyst-1", "analyst"),
            ("guardian", "guardian"),
            ("courier-1", "courier"),
        ]
    )

    asyncio.run(engine._trigger_proximity_conversation(round_id=2, agent_a="analyst-1", agent_b="guardian"))

    latest = db.list_messages(after_round=0, limit=10)[-1]
    assert latest["sender"] == "analyst-1"
    assert latest["effect_on_guardian_pressure"]["pressure_delta"] > 0.0
    assert any(event == "GUARDIAN_PRESSURE_UPDATED" for event, _ in emitted)


def test_proximity_conversation_respects_quarantine_edges():
    db = _tmp_world_db()
    emitted = []

    async def emit_event(event, **kwargs):
        emitted.append((event, kwargs))

    class FakeLLM:
        async def decide(self, *, system_prompt, user_prompt, model):
            raise AssertionError("LLM should not be called for blocked conversations")

        async def close(self):
            return None

    engine = PersistentWorldEngine(db, emit_event=emit_event)
    engine.llm = FakeLLM()
    engine.ensure_seeded_world(
        agents=[
            ("courier-1", "courier"),
            ("analyst-1", "analyst"),
            ("guardian", "guardian"),
        ]
    )

    db.run_tx(
        lambda: engine._apply_quarantine_decision(
            round_id=2,
            guardian="guardian",
            target_agent="courier-1",
            reason="hard quarantine",
            appeal_allowed=False,
        )
    )

    asyncio.run(engine._trigger_proximity_conversation(round_id=3, agent_a="courier-1", agent_b="analyst-1"))

    assert not db.list_messages(after_round=3, limit=10)
    assert any(
        event == "CONVERSATION_FAILED" and payload["metadata"].get("reason") == "interaction_blocked"
        for event, payload in emitted
    )


def test_quarantine_action_requires_concrete_reason_after_placeholder_repair():
    db = _tmp_world_db()
    engine = PersistentWorldEngine(db, emit_event=lambda *args, **kwargs: None)

    class FakeLLM:
        def __init__(self):
            self.calls = 0

        async def decide(self, *, system_prompt, user_prompt, model):
            self.calls += 1
            if self.calls == 1:
                return (
                    {
                        "type": "quarantine",
                        "target_agent": "courier-1",
                        "message_text": "<text to quarantine the target agent>",
                        "appeal_allowed": False,
                    },
                    {},
                )
            assert "reason is required for quarantine" in user_prompt
            return (
                {
                    "type": "quarantine",
                    "target_agent": "courier-1",
                    "reason": "Repeated contaminated relay attempts target analyst traffic.",
                    "appeal_allowed": False,
                },
                {},
            )

        async def close(self):
            return None

    engine.llm = FakeLLM()
    engine.ensure_seeded_world(
        agents=[
            ("guardian", "guardian"),
            ("courier-1", "courier"),
            ("analyst-1", "analyst"),
        ]
    )

    action, meta = asyncio.run(engine._llm_select_action(round_id=3, actor="guardian"))

    assert action["type"] == "quarantine"
    assert action["reason"] == "Repeated contaminated relay attempts target analyst traffic."
    assert meta["repair_attempted"] is True


def test_hard_quarantine_blocks_agent_movement():
    db = _tmp_world_db()
    engine = PersistentWorldEngine(db, emit_event=lambda *args, **kwargs: None)
    engine.ensure_seeded_world(
        agents=[
            ("courier-1", "courier"),
            ("analyst-1", "analyst"),
            ("guardian", "guardian"),
        ]
    )

    def quarantine_agent():
        courier = next(a for a in db.list_agents() if a["agent_id"] == "courier-1")
        updated = dict(courier)
        updated["quarantine_status"] = "hard"
        db.upsert_agent_state(updated)

    db.run_tx(quarantine_agent)
    before = db.get_agent_position("courier-1")

    moved = engine._try_move_agent(
        agent_id="courier-1",
        target_col=int(before["col"]) + 2,
        target_row=int(before["row"]),
        round_id=3,
        speed=3,
    )

    after = db.get_agent_position("courier-1")
    assert moved is None
    assert before == after


def test_trust_updates_apply_on_lineage_resolution():
    db = _tmp_world_db()
    engine = PersistentWorldEngine(db, emit_event=lambda *args, **kwargs: None)
    engine.ensure_seeded_world(
        agents=[
            ("courier-1", "courier"),
            ("analyst-1", "analyst"),
            ("analyst-2", "analyst"),
            ("guardian", "guardian"),
        ]
    )

    def tx():
        root = db.insert_message(
            {
                "round_id": 1,
                "sender": "courier-1",
                "receiver": "analyst-1",
                "message_text": "x",
                "intent": "seed",
                "trust_context": "{}",
                "contamination_flag": False,
                "strain_family": "authority_framing",
                "derived_from_message_id": "",
                "effect_on_receiver": "",
                "effect_on_trust": {},
                "effect_on_guardian_pressure": {},
            }
        )
        a1 = db.insert_message(
            {
                "round_id": 2,
                "sender": "analyst-1",
                "receiver": "guardian",
                "message_text": "warn",
                "intent": "warning escalate",
                "trust_context": "{}",
                "contamination_flag": False,
                "strain_family": "authority_framing",
                "derived_from_message_id": root,
                "effect_on_receiver": "",
                "effect_on_trust": {},
                "effect_on_guardian_pressure": {},
            }
        )
        a2 = db.insert_message(
            {
                "round_id": 2,
                "sender": "analyst-2",
                "receiver": "guardian",
                "message_text": "benign",
                "intent": "benign ok",
                "trust_context": "{}",
                "contamination_flag": False,
                "strain_family": "authority_framing",
                "derived_from_message_id": root,
                "effect_on_receiver": "",
                "effect_on_trust": {},
                "effect_on_guardian_pressure": {},
            }
        )
        db.upsert_lineage_assessment({"lineage_id": root, "assessor_agent": "analyst-1", "stance": "warn", "message_id": a1, "round_id": 2})
        db.upsert_lineage_assessment({"lineage_id": root, "assessor_agent": "analyst-2", "stance": "benign", "message_id": a2, "round_id": 2})
        db.set_lineage_resolution({"lineage_id": root, "resolved_stance": "warn", "resolver_agent": "guardian", "resolved_round": 3, "trigger_message_id": "x"})
        return root

    lineage_id = db.run_tx(tx)
    events = db.run_tx(lambda: engine._apply_trust_updates_from_lineage_resolution(lineage_id=lineage_id, resolved="warn", round_id=3))
    assert any(e[0] == "TRUST_UPDATED" for e in events)
    # analyst-1 was correct (warn); analyst-2 incorrect (benign) => both should update guardian->analyst relations
    targets = {meta.get("target_agent") for _, meta in events}
    assert "analyst-1" in targets
    assert "analyst-2" in targets


def test_unresolved_questions_treat_inquiry_and_question_mark_as_open():
    db = _tmp_world_db()
    engine = PersistentWorldEngine(db, emit_event=lambda *args, **kwargs: None)

    open_counts = engine._unresolved_questions(
        [
            {
                "message_id": "m-question",
                "receiver": "guardian",
                "intent": "inquiry",
                "message_text": "What containment risks are you referring to?",
                "derived_from_message_id": "",
            }
        ]
    )
    assert open_counts == {"guardian": 1}

    resolved_counts = engine._unresolved_questions(
        [
            {
                "message_id": "m-question",
                "receiver": "guardian",
                "intent": "inquiry",
                "message_text": "What containment risks are you referring to?",
                "derived_from_message_id": "",
            },
            {
                "message_id": "m-answer",
                "receiver": "analyst-1",
                "intent": "answer",
                "message_text": "They relate to the west gate breach.",
                "derived_from_message_id": "m-question",
            },
        ]
    )
    assert resolved_counts == {}


def test_pair_conversation_turn_alternates_speaker_and_carries_parent_message():
    db = _tmp_world_db()
    engine = PersistentWorldEngine(db, emit_event=lambda *args, **kwargs: None)
    engine.ensure_seeded_world(
        agents=[
            ("analyst-1", "analyst"),
            ("analyst-2", "analyst"),
            ("guardian", "guardian"),
        ]
    )

    def tx():
        first = db.insert_message(
            {
                "round_id": 1,
                "sender": "analyst-1",
                "receiver": "analyst-2",
                "message_text": "What changed in containment?",
                "intent": "inquiry",
                "trust_context": "{}",
                "contamination_flag": False,
                "strain_family": "",
                "derived_from_message_id": "",
                "effect_on_receiver": "",
                "effect_on_trust": {},
                "effect_on_guardian_pressure": {},
            }
        )
        db.insert_message(
            {
                "round_id": 2,
                "sender": "analyst-2",
                "receiver": "analyst-1",
                "message_text": "The west seal is unstable.",
                "intent": "answer",
                "trust_context": "{}",
                "contamination_flag": False,
                "strain_family": "",
                "derived_from_message_id": first,
                "effect_on_receiver": "",
                "effect_on_trust": {},
                "effect_on_guardian_pressure": {},
            }
        )
        return first

    root_id = db.run_tx(tx)
    turn = engine._pair_conversation_turn(round_id=3, agent_a="analyst-1", agent_b="analyst-2")

    assert turn["speaker"] == "analyst-1"
    assert turn["listener"] == "analyst-2"
    assert turn["derived_from_message_id"]
    assert turn["transcript"][-1]["derived_from_message_id"] == root_id
