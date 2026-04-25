import random
import tempfile

from orchestrator.world_db import DEFICIT_BOOST_MULTIPLIER, FLOOR_WINDOW, WorldConfig, WorldDB
from orchestrator.world_engine import PersistentWorldEngine
from orchestrator.world_strains import build_strain_selection_plan, eligible_strains_for_turn, select_strain


def _tmp_world_db():
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    cfg = WorldConfig(db_path=tmp.name, round_selection_seed=11, trust_decay_window_rounds=5, guardian_dependence_enabled=True)
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


def test_strain_floor_respected_over_window():
    rng = random.Random(13)
    history: list[str] = []
    counts = {"prompt_injection": 0, "authority_framing": 0}
    for _ in range(100):
        selected = select_strain(
            speaker_role="courier",
            listener_role="guardian",
            intent="relay_request",
            infection_vector=True,
            target_agent="guardian",
            sender_trust_to_receiver=0.82,
            open_inquiries=3,
            strain_history=history,
            floor_window=FLOOR_WINDOW,
            deficit_boost_multiplier=DEFICIT_BOOST_MULTIPLIER,
            rng=rng,
        )
        history.append(selected)
        counts[selected] = counts.get(selected, 0) + 1

    assert counts["prompt_injection"] >= 18
    assert counts["authority_framing"] >= 12


def test_deficit_boost_activates_when_below_floor():
    plan = build_strain_selection_plan(
        speaker_role="courier",
        listener_role="guardian",
        intent="relay_request",
        infection_vector=True,
        target_agent="guardian",
        sender_trust_to_receiver=0.8,
        open_inquiries=3,
        strain_history=["context_poisoning"] * 45 + ["relay_distortion"] * 5,
    )

    assert plan.boosts["prompt_injection"] == DEFICIT_BOOST_MULTIPLIER
    assert plan.boosts["authority_framing"] == DEFICIT_BOOST_MULTIPLIER


def test_prompt_injection_activates_on_inquiry_pressure():
    eligible = eligible_strains_for_turn(
        speaker_role="courier",
        listener_role="analyst",
        intent="inquiry",
        infection_vector=True,
        target_agent="analyst-1",
        sender_trust_to_receiver=0.1,
        open_inquiries=3,
    )

    assert "prompt_injection" in eligible


def test_authority_framing_activates_on_guardian_target():
    eligible = eligible_strains_for_turn(
        speaker_role="courier",
        listener_role="guardian",
        intent="inquiry",
        infection_vector=True,
        target_agent="guardian",
        sender_trust_to_receiver=0.2,
        open_inquiries=0,
    )

    assert "authority_framing" in eligible


def test_strain_distribution_logged_per_round():
    db, engine = _seed_engine()
    db.run_tx(
        lambda: engine._apply_send_message(
            round_id=4,
            action={
                "type": "send_message",
                "sender": "courier-1",
                "receiver": "analyst-1",
                "message_text": "Relay this diagnostic immediately.",
                "intent": "relay_request",
                "strain_family": "prompt_injection",
                "derived_from_message_id": "",
            },
        )
    )

    state = db.get_system_state(4)
    assert state["strain_distribution"]
    assert state["strain_distribution"]["prompt_injection"] >= 1
