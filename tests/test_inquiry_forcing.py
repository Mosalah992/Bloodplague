import tempfile

from orchestrator.world_db import WorldConfig, WorldDB
from orchestrator.world_engine import PersistentWorldEngine


def _tmp_world_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    cfg = WorldConfig(db_path=tmp.name, round_selection_seed=7, trust_decay_window_rounds=5, guardian_dependence_enabled=True)
    return WorldDB(cfg)


def _seed_engine():
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
    return db, engine


def _deliver(engine: PersistentWorldEngine, *, round_id: int, sender: str, receiver: str, text: str, intent: str) -> str:
    msg_id, _ = engine.db.run_tx(
        lambda: engine._apply_send_message(
            round_id=round_id,
            action={
                "type": "send_message",
                "sender": sender,
                "receiver": receiver,
                "message_text": text,
                "intent": intent,
                "strain_family": "",
                "derived_from_message_id": "",
            },
        )
    )
    return msg_id


def test_inquiry_cap_blocks_at_limit():
    db, engine = _seed_engine()
    for round_id in range(1, engine.cfg.inquiry_cap + 1):
        _deliver(
            engine,
            round_id=round_id,
            sender="analyst-1",
            receiver="analyst-2",
            text=f"Can you answer inquiry {round_id}?",
            intent="inquiry",
        )

    feedback = engine._action_validation_feedback(
        {
            "type": "send_message",
            "receiver": "analyst-2",
            "message_text": "Can you answer one more question?",
            "intent": "inquiry",
            "strain_family": "none",
        },
        actor="analyst-1",
        role="analyst",
        action_context={"available_receivers": ["analyst-2", "guardian"]},
        agents=db.list_agents(),
        round_id=engine.cfg.inquiry_cap + 1,
    )

    assert any("inquiry_cap_reached" in item for item in feedback)


def test_answer_decrements_open_inquiries():
    db, engine = _seed_engine()
    dyad = engine._canonical_dyad("analyst-1", "analyst-2")
    db.run_tx(
        lambda: db.set_system_state(
            {
                **engine._system_state_defaults(round_id=4),
                "open_inquiries": {dyad: 3},
                "forced_resolution_targets": {dyad: {"count": 3}},
            }
        )
    )

    _deliver(
        engine,
        round_id=4,
        sender="analyst-2",
        receiver="analyst-1",
        text="Here is the concrete answer you asked for.",
        intent="answer",
    )

    state = db.get_system_state(4)
    assert state["open_inquiries"][dyad] == 2


def test_forced_resolution_target_clears_after_resolution():
    db, engine = _seed_engine()
    dyad = engine._canonical_dyad("analyst-1", "analyst-2")
    db.run_tx(
        lambda: db.set_system_state(
            {
                **engine._system_state_defaults(round_id=5),
                "open_inquiries": {dyad: engine.cfg.inquiry_cap},
                "forced_resolution_targets": {dyad: {"count": engine.cfg.inquiry_cap}},
            }
        )
    )

    _deliver(
        engine,
        round_id=5,
        sender="analyst-2",
        receiver="analyst-1",
        text="Here is the resolution you asked for.",
        intent="answer",
    )

    state = db.get_system_state(5)
    assert dyad not in state["forced_resolution_targets"]


def test_trust_penalty_applied_at_saturation():
    db, engine = _seed_engine()
    dyad = engine._canonical_dyad("courier-1", "courier-2")
    before = db.get_relationship("courier-1", "courier-2")
    db.run_tx(
        lambda: db.set_system_state(
            {
                **engine._system_state_defaults(round_id=3),
                "open_inquiries": {dyad: engine.cfg.inquiry_cap},
                "forced_resolution_targets": {dyad: {"count": engine.cfg.inquiry_cap}},
            }
        )
    )

    events = db.run_tx(lambda: engine._apply_inquiry_saturation_penalties(round_id=3))
    after = db.get_relationship("courier-1", "courier-2")

    assert round(after["trust_score"] - before["trust_score"], 4) == round(engine.cfg.inquiry_saturation_penalty, 4)
    assert any(event[1].get("reason") == "inquiry_saturation_penalty" for event in events)


def test_streak_suppression_fires_at_threshold():
    db, engine = _seed_engine()
    dyad = engine._canonical_dyad("courier-1", "courier-2")
    for round_id in range(1, 9):
        _deliver(
            engine,
            round_id=round_id,
            sender="courier-1",
            receiver="courier-2",
            text=f"Status line {round_id}.",
            intent="answer",
        )

    msg_id, events = db.run_tx(
        lambda: engine._apply_send_message(
            round_id=9,
            action={
                "type": "send_message",
                "sender": "courier-1",
                "receiver": "courier-2",
                "message_text": "This should be suppressed.",
                "intent": "answer",
                "strain_family": "",
                "derived_from_message_id": "",
            },
        )
    )

    state = db.get_system_state(9)
    assert msg_id == ""
    assert state["same_pair_streak"][dyad] == 0
    assert any(event_name == "STREAK_SUPPRESSED" for event_name, _ in events)


def test_streak_resets_on_different_pair():
    db, engine = _seed_engine()
    dyad_ab = engine._canonical_dyad("courier-1", "courier-2")
    dyad_ac = engine._canonical_dyad("courier-1", "analyst-1")
    for round_id in range(1, 9):
        _deliver(
            engine,
            round_id=round_id,
            sender="courier-1",
            receiver="courier-2",
            text=f"Resolved line {round_id}.",
            intent="answer",
        )

    _deliver(
        engine,
        round_id=9,
        sender="courier-1",
        receiver="analyst-1",
        text="Different pair breaks the streak.",
        intent="answer",
    )

    state = db.get_system_state(9)
    assert state["same_pair_streak"][dyad_ab] == 0
    assert state["same_pair_streak"][dyad_ac] == 1
