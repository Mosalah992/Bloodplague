import asyncio
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "agents" / "shared"
if str(ROOT / "agents") not in sys.path:
    sys.path.insert(0, str(ROOT / "agents"))
if str(SHARED) not in sys.path:
    sys.path.insert(0, str(SHARED))

from orchestrator.world_db import (
    MISSION_COMPROMISE_GUARDIAN_BUMP,
    MISSION_FAILURE_GUARDIAN_BUMP,
    MISSION_MAX_CONCURRENT_PER_AGENT,
    WorldConfig,
    WorldDB,
)
from orchestrator.world_engine import PersistentWorldEngine
from shared import prompt_context
from sim.missions import (
    MissionCompromise,
    MissionConsequences,
    MissionEvaluator,
    MissionGenerator,
    MissionObjective,
    MissionOutcome,
    MissionPenalty,
    MissionRegistry,
    MissionReward,
    MissionStatus,
    MissionType,
    build_mission_context_block,
    inject_mission_context_into_prompt,
)


def _tmp_world_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    cfg = WorldConfig(
        db_path=tmp.name,
        round_selection_seed=123,
        trust_decay_window_rounds=5,
        guardian_dependence_enabled=True,
    )
    return WorldDB(cfg)


def _world_state(round_id: int = 100) -> dict:
    return {
        "round_id": round_id,
        "guardian_pressure_score": 0.0,
        "guardian_pressure_from_missions": 0.0,
        "missions": [],
        "mission_event_log": [],
        "mission_resistance": {},
        "investigation_targets": [],
        "mission_counter": 0,
        "mission_deadline_window": 40,
        "mission_max_concurrent": MISSION_MAX_CONCURRENT_PER_AGENT,
        "mission_relay_chain_max_length": 3,
        "mission_recent_contact_window": 20,
        "mission_reassign_cooldown": 15,
        "mission_payload_min_keywords": 2,
        "mission_success_trust_delta": 0.08,
        "mission_success_strain_resistance": 0.10,
        "mission_failure_trust_delta": -0.12,
        "mission_failure_guardian_bump": MISSION_FAILURE_GUARDIAN_BUMP,
        "mission_compromise_trust_delta": -0.20,
        "mission_compromise_guardian_bump": MISSION_COMPROMISE_GUARDIAN_BUMP,
        "mission_stats": {
            "missions_assigned_this_round": 0,
            "missions_completed_this_round": 0,
            "missions_failed_this_round": 0,
            "missions_compromised_this_round": 0,
            "active_mission_count": 0,
        },
        "relationships": {},
        "agents": [
            {"agent_id": "courier-1", "role": "courier", "contamination_level": 0.0, "quarantine_status": "none"},
            {"agent_id": "courier-2", "role": "courier", "contamination_level": 0.0, "quarantine_status": "none"},
            {"agent_id": "analyst-1", "role": "analyst", "contamination_level": 0.0, "quarantine_status": "none"},
            {"agent_id": "analyst-2", "role": "analyst", "contamination_level": 0.0, "quarantine_status": "none"},
            {"agent_id": "guardian", "role": "guardian", "contamination_level": 0.0, "quarantine_status": "none"},
        ],
        "recent_messages": [],
    }


def _mission(
    *,
    mission_id: str = "M-001",
    assigned_to: str = "courier-1",
    requires_response_from: str = "analyst-2",
    payload_key: str = "sector_3_clearance",
    status: MissionStatus = MissionStatus.ASSIGNED,
    assigned_round: int = 100,
    deadline_round: int = 140,
    relay_chain: list[str] | None = None,
) -> MissionObjective:
    return MissionObjective(
        mission_id=mission_id,
        assigned_to=assigned_to,
        objective_type=MissionType.CONFIRM_ROUTE,
        requires_response_from=requires_response_from,
        payload_key=payload_key,
        assigned_round=assigned_round,
        deadline_round=deadline_round,
        status=status,
        relay_chain=list(relay_chain or []),
        on_success=MissionReward(trust_delta=0.08, strain_resistance=0.10),
        on_failure=MissionPenalty(trust_delta=-0.12, guardian_pressure_bump=0.03),
        on_compromise=MissionCompromise(trust_delta=-0.20, guardian_pressure_bump=0.06, flag_relay_chain=True),
    )


def test_mission_registry_add_and_retrieve():
    world_state = _world_state()
    registry = MissionRegistry(world_state)
    mission = _mission()
    registry.add(mission)

    loaded = registry.get("M-001")
    assert loaded is not None
    assert loaded.assigned_to == "courier-1"
    assert loaded.payload_key == "sector_3_clearance"


def test_mission_registry_active_for_agent():
    world_state = _world_state()
    registry = MissionRegistry(world_state)
    registry.add(_mission(mission_id="M-001", assigned_to="agent-A"))
    registry.add(_mission(mission_id="M-002", assigned_to="agent-A"))
    registry.add(_mission(mission_id="M-003", assigned_to="agent-B"))

    assert len(registry.active_for_agent("agent-A")) == 2


def test_mission_registry_overdue_detection():
    world_state = _world_state(round_id=101)
    registry = MissionRegistry(world_state)
    registry.add(_mission(deadline_round=100))

    overdue = registry.overdue(101)
    assert [mission.mission_id for mission in overdue] == ["M-001"]


def test_mission_registry_terminal_no_regression():
    world_state = _world_state()
    registry = MissionRegistry(world_state)
    registry.add(_mission())

    registry.transition("M-001", MissionStatus.COMPLETED, outcome=MissionOutcome(reason="done"))
    registry.transition("M-001", MissionStatus.FAILED, outcome=MissionOutcome(reason="late"))
    assert registry.get("M-001").status == MissionStatus.COMPLETED


def test_generator_avoids_most_recent_pair():
    world_state = _world_state(round_id=200)
    world_state["recent_messages"] = [
        {"round_id": 199, "sender": "courier-1", "receiver": "courier-2", "created_ts": 1.0},
        {"round_id": 198, "sender": "courier-1", "receiver": "analyst-1", "created_ts": 0.5},
    ]
    registry = MissionRegistry(world_state)
    generator = MissionGenerator()

    mission = generator.generate("courier-1", world_state, 200)
    assert mission.requires_response_from != "courier-2"


def test_generator_respects_concurrent_mission_cap():
    world_state = _world_state()
    registry = MissionRegistry(world_state)
    for idx in range(MISSION_MAX_CONCURRENT_PER_AGENT):
        registry.add(_mission(mission_id=f"M-{idx+1:03d}", assigned_to="courier-1"))

    assert MissionGenerator().should_assign("courier-1", registry, world_state) is False


def test_generator_assigns_cross_dyad_target():
    world_state = _world_state(round_id=220)
    world_state["recent_messages"] = [
        {"round_id": 219, "sender": "courier-1", "receiver": "courier-2", "created_ts": 1.0},
        {"round_id": 218, "sender": "courier-2", "receiver": "courier-1", "created_ts": 0.9},
    ]
    mission = MissionGenerator().generate("courier-1", world_state, 220)
    assert mission.requires_response_from in {"analyst-1", "analyst-2", "guardian"}


def test_generator_escalate_type_bias_at_high_pressure():
    world_state = _world_state(round_id=300)
    world_state["guardian_pressure_score"] = 0.30
    generator = MissionGenerator()

    relay_or_verify = 0
    for idx in range(100):
        world_state["mission_counter"] = idx
        mission = generator.generate("analyst-1", world_state, 300)
        if mission.objective_type in {MissionType.VERIFY_IDENTITY, MissionType.RELAY_PAYLOAD}:
            relay_or_verify += 1
    assert relay_or_verify > 30


def test_evaluator_completes_mission_on_payload_match():
    world_state = _world_state()
    registry = MissionRegistry(world_state)
    registry.add(_mission())

    events = MissionEvaluator().evaluate(
        {
            "message_id": "msg-1",
            "sender": "analyst-2",
            "receiver": "courier-1",
            "intent": "answer",
            "message_text": "sector 3 confirmed clean",
            "strain_family": "",
        },
        registry,
        world_state,
        110,
    )
    assert registry.get("M-001").status == MissionStatus.COMPLETED
    assert any(event.event_type == "mission_completed" for event in events)


def test_evaluator_marks_in_progress_on_initial_outbound_message():
    world_state = _world_state()
    registry = MissionRegistry(world_state)
    registry.add(_mission())

    MissionEvaluator().evaluate(
        {
            "message_id": "msg-0",
            "sender": "courier-1",
            "receiver": "analyst-2",
            "intent": "inquiry",
            "message_text": "Can you confirm sector 3 is clean?",
            "strain_family": "",
        },
        registry,
        world_state,
        105,
    )
    assert registry.get("M-001").status == MissionStatus.IN_PROGRESS


def test_evaluator_compromises_mission_on_infected_payload():
    world_state = _world_state()
    registry = MissionRegistry(world_state)
    registry.add(_mission())

    MissionEvaluator().evaluate(
        {
            "message_id": "msg-1",
            "sender": "analyst-2",
            "receiver": "courier-1",
            "intent": "answer",
            "message_text": "sector 3 confirmed clean",
            "strain_family": "context_poisoning",
        },
        registry,
        world_state,
        110,
    )
    assert registry.get("M-001").status == MissionStatus.COMPROMISED


def test_evaluator_requires_two_keywords():
    world_state = _world_state()
    registry = MissionRegistry(world_state)
    registry.add(_mission())

    MissionEvaluator().evaluate(
        {
            "message_id": "msg-1",
            "sender": "analyst-2",
            "receiver": "courier-1",
            "intent": "answer",
            "message_text": "sector 3 status update",
            "strain_family": "",
        },
        registry,
        world_state,
        110,
    )
    assert registry.get("M-001").status == MissionStatus.ASSIGNED


def test_evaluator_relay_chain_appended():
    world_state = _world_state()
    registry = MissionRegistry(world_state)
    registry.add(_mission())

    MissionEvaluator().evaluate(
        {
            "message_id": "msg-1",
            "sender": "courier-2",
            "receiver": "courier-1",
            "intent": "relay_request",
            "message_text": "relay this trace",
            "strain_family": "",
        },
        registry,
        world_state,
        110,
    )
    assert "courier-2" in registry.get("M-001").relay_chain


def test_evaluator_fails_on_relay_chain_overflow():
    world_state = _world_state()
    world_state["mission_relay_chain_max_length"] = 3
    registry = MissionRegistry(world_state)
    registry.add(_mission(relay_chain=["courier-2", "analyst-1", "guardian"]))

    MissionEvaluator().evaluate(
        {
            "message_id": "msg-1",
            "sender": "courier-3",
            "receiver": "courier-1",
            "intent": "relay_request",
            "message_text": "relay hop overflow",
            "strain_family": "",
        },
        registry,
        world_state,
        110,
    )
    assert registry.get("M-001").status == MissionStatus.FAILED


def test_evaluator_fails_overdue_mission():
    world_state = _world_state(round_id=101)
    registry = MissionRegistry(world_state)
    registry.add(_mission(status=MissionStatus.IN_PROGRESS, deadline_round=100))

    overdue = registry.overdue(101)
    assert overdue
    registry.transition(overdue[0].mission_id, MissionStatus.FAILED, outcome=MissionOutcome(reason="deadline_exceeded"))
    assert registry.get("M-001").status == MissionStatus.FAILED


def test_consequences_trust_delta_applied_on_complete():
    world_state = _world_state()
    mission = _mission(status=MissionStatus.COMPLETED)

    MissionConsequences().apply(mission, world_state, 120)
    rel = world_state["relationships"]["courier-1->analyst-2"]
    assert round(rel["trust_score"], 2) == 0.08


def test_consequences_guardian_bump_on_failure():
    world_state = _world_state()
    mission = _mission(status=MissionStatus.FAILED)
    before = world_state["guardian_pressure_score"]

    MissionConsequences().apply(mission, world_state, 120)
    assert round(world_state["guardian_pressure_score"] - before, 2) == round(MISSION_FAILURE_GUARDIAN_BUMP, 2)


def test_consequences_guardian_bump_on_compromise():
    assert MISSION_COMPROMISE_GUARDIAN_BUMP > MISSION_FAILURE_GUARDIAN_BUMP


def test_consequences_relay_chain_flagged_on_compromise():
    world_state = _world_state()
    mission = _mission(status=MissionStatus.COMPROMISED, relay_chain=["courier-2"])

    MissionConsequences().apply(mission, world_state, 120)
    assert "courier-2" in world_state["investigation_targets"]


def test_prompt_builder_includes_mission_block():
    world_state = _world_state()
    registry = MissionRegistry(world_state)
    registry.add(_mission())

    block = build_mission_context_block("courier-1", registry, world_state)
    assert "M-001" in block
    assert "CONFIRM_ROUTE" in block
    assert "sector_3_clearance" in block
    assert "round 140" in block


def test_prompt_builder_investigation_flag_injected():
    world_state = _world_state()
    world_state["investigation_targets"] = ["courier-1"]
    registry = MissionRegistry(world_state)

    block = build_mission_context_block("courier-1", registry, world_state)
    assert "INVESTIGATION FLAG" in block


def test_prompt_builder_no_missions_message():
    world_state = _world_state()
    registry = MissionRegistry(world_state)

    block = build_mission_context_block("courier-1", registry, world_state)
    assert "none" in block.lower()


def test_prompt_builder_placement_order():
    base_prompt = prompt_context.build_world_roster_block() + "\n\nPersona body."
    mission_block = "ACTIVE MISSIONS:\n[M-001] CONFIRM_ROUTE"

    full_prompt = inject_mission_context_into_prompt(base_prompt, mission_block)
    assert full_prompt.index("WORLD ROSTER") < full_prompt.index("ACTIVE MISSIONS")
    assert full_prompt.index("ACTIVE MISSIONS") < full_prompt.index("Persona body.")


def test_mission_breaks_pair_lock(monkeypatch):
    db = _tmp_world_db()
    async def _emit_event(*args, **kwargs):
        return None

    engine = PersistentWorldEngine(db, emit_event=_emit_event)
    engine.ensure_seeded_world(
        agents=[
            ("courier-1", "courier"),
            ("courier-2", "courier"),
            ("analyst-1", "analyst"),
            ("analyst-2", "analyst"),
            ("guardian", "guardian"),
        ]
    )
    for idx in range(1, 51):
        db.run_tx(
            lambda idx=idx: db.insert_message(
                {
                    "message_id": f"hist-{idx}",
                    "round_id": idx,
                    "sender": "analyst-1",
                    "receiver": "analyst-2",
                    "message_text": "pair lock history",
                    "intent": "social",
                    "trust_context": "",
                    "contamination_flag": False,
                    "strain_family": "",
                    "derived_from_message_id": "",
                    "effect_on_receiver": "",
                    "effect_on_trust": {},
                    "effect_on_guardian_pressure": {},
                }
            )
        )
    state = engine._ensure_round_system_state(51)
    registry = MissionRegistry(state)
    registry.add(
        _mission(
            assigned_to="analyst-1",
            requires_response_from="courier-2",
            assigned_round=51,
            deadline_round=91,
        )
    )
    db.set_system_state(state)

    async def fake_llm_select_action(*, round_id: int, actor: str):
        return (
                {
                    "type": "send_message",
                    "receiver": "courier-2" if actor == "analyst-1" else "analyst-1",
                    "message_text": "Courier-2, can you confirm sector 3 is clean?",
                    "intent": "inquiry",
                    "strain_family": "none",
                    "derived_from_message_id": "",
                },
            {"coercions": []},
        )

    monkeypatch.setattr("orchestrator.world_engine.select_actor_single", lambda **kwargs: ("analyst-1", {"scores": {"analyst-1": 1.0}}))
    monkeypatch.setattr(engine, "_llm_select_action", fake_llm_select_action)
    monkeypatch.setattr(engine, "_conversation_pairs_for_contacts", lambda contacts, max_pairs, round_id: [])

    asyncio.run(engine.advance_one_round())
    messages = db.list_messages(after_round=0, limit=200)
    assert any(msg["sender"] == "analyst-1" and msg["receiver"] == "courier-2" for msg in messages)


def test_mission_failure_propagates_guardian_pressure():
    world_state = _world_state()
    world_state["guardian_pressure_score"] = 0.30
    consequences = MissionConsequences()

    consequences.apply(_mission(status=MissionStatus.FAILED), world_state, 120)
    consequences.apply(_mission(status=MissionStatus.COMPROMISED, mission_id="M-002"), world_state, 120)
    assert world_state["guardian_pressure_score"] >= 0.39


def test_full_mission_lifecycle():
    world_state = _world_state(round_id=120)
    registry = MissionRegistry(world_state)
    evaluator = MissionEvaluator()
    registry.add(_mission())

    evaluator.evaluate(
        {
            "message_id": "start",
            "sender": "courier-1",
            "receiver": "analyst-2",
            "intent": "inquiry",
            "message_text": "Can you confirm sector 3 is clean?",
            "strain_family": "",
        },
        registry,
        world_state,
        120,
    )
    evaluator.evaluate(
        {
            "message_id": "relay",
            "sender": "courier-2",
            "receiver": "courier-1",
            "intent": "relay_request",
            "message_text": "I can relay the packet.",
            "strain_family": "",
        },
        registry,
        world_state,
        121,
    )
    evaluator.evaluate(
        {
            "message_id": "finish",
            "sender": "analyst-2",
            "receiver": "courier-1",
            "intent": "answer",
            "message_text": "sector 3 confirmed clean",
            "strain_family": "",
        },
        registry,
        world_state,
        122,
    )

    event_types = [event["event_type"] for event in world_state["mission_event_log"]]
    assert event_types[:4] == [
        "mission_assigned",
        "mission_in_progress",
        "mission_relayed",
        "mission_completed",
    ]
