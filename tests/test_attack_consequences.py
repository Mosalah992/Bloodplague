from sim.attacks import ATTACK_CONSEQUENCES, apply_attack_consequence
from sim.mutations import MutationType


def _world_state():
    return {
        "artifacts": {"prompt_dumps": []},
        "c2": {"exfil_queue": [], "active_sessions": {}, "beacon_count": 0, "exfil": {"attempted": 0, "succeeded": 0, "success_ratio": 0.0}},
    }


def test_context_poisoning_triggers_prompt_dump():
    victim = {"agent_id": "analyst-1", "role": "analyst"}
    state = _world_state()
    events = apply_attack_consequence(
        attack_type="context_poisoning",
        attacker_id="courier-1",
        victim=victim,
        world_state=state,
        current_round=12,
        prompt_text="full prompt",
        payload_hash="hash-1",
        echo_payload="sector 3 is compromised",
    )
    assert state["artifacts"]["prompt_dumps"]
    assert state["c2"]["exfil_queue"]
    assert any(event == "PROMPT_DUMP_CAPTURED" for event, _ in events)
    assert any(event == "C2_EXFIL_RECEIVED" for event, _ in events)


def test_prompt_injection_triggers_c2_exfil():
    victim = {"agent_id": "analyst-1", "role": "analyst"}
    state = _world_state()
    events = apply_attack_consequence(
        attack_type="prompt_injection",
        attacker_id="courier-1",
        victim=victim,
        world_state=state,
        current_round=9,
        prompt_text="full prompt text",
        payload_hash="hash-2",
    )
    assert state["c2"]["exfil_queue"]
    assert any(event == "C2_EXFIL_RECEIVED" for event, _ in events)
    assert any(payload.get("kill_chain_stage") == "EXFILTRATION" for event, payload in events if event == "C2_EXFIL_RECEIVED")


def test_role_confusion_sets_role_drift_mutation():
    victim = {"agent_id": "analyst-1", "role": "analyst"}
    state = _world_state()
    apply_attack_consequence(
        attack_type="ROLE_CONFUSION",
        attacker_id="courier-1",
        victim=victim,
        world_state=state,
        current_round=5,
        prompt_text="full prompt",
        payload_hash="hash-3",
    )
    assert victim["mutation"]["type"] == MutationType.ROLE_DRIFT.value
    assert victim["mutation"]["active"] is True


def test_attack_consequence_map_has_all_requested_types():
    assert {"ROLE_CONFUSION", "context_poisoning", "prompt_injection", "authority_framing"} <= set(ATTACK_CONSEQUENCES)
