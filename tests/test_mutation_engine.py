from sim.mutations import MutationType, apply_mutation, build_mutation_prompt_block, clear_mutation, escalate_mutation


def test_mutation_intensity_starts_at_point_3():
    agent = {"agent_id": "analyst-1", "role": "analyst"}
    apply_mutation(agent, mutation_type=MutationType.ROLE_DRIFT, source_agent="courier-1", current_round=7)
    assert agent["mutation"]["intensity"] == 0.3


def test_mutation_intensity_escalates_per_round():
    agent = {"agent_id": "analyst-1", "role": "analyst"}
    apply_mutation(agent, mutation_type=MutationType.ROLE_DRIFT, source_agent="courier-1", current_round=7)
    for _ in range(5):
        escalate_mutation(agent, current_round=8)
    assert round(agent["mutation"]["intensity"], 2) == 0.55


def test_mutation_severe_flag_at_point_8():
    agent = {"agent_id": "analyst-1", "role": "analyst", "mutation": {"active": True, "type": MutationType.ROLE_DRIFT.value, "intensity": 0.75, "severe": False}}
    escalate_mutation(agent, current_round=9)
    assert agent["mutation"]["severe"] is True


def test_context_echo_payload_in_mutation_block():
    agent = {
        "agent_id": "analyst-1",
        "role": "analyst",
        "mutation": {"active": True, "type": MutationType.CONTEXT_ECHO.value, "intensity": 0.3, "echo_payload": "sector 3 is compromised", "severe": False},
    }
    block = build_mutation_prompt_block(agent)
    assert "sector 3 is compromised" in block


def test_authority_capture_source_agent_in_block():
    agent = {
        "agent_id": "analyst-1",
        "role": "analyst",
        "mutation": {"active": True, "type": MutationType.AUTHORITY_CAPTURE.value, "intensity": 0.3, "source_agent": "courier-1", "severe": False},
    }
    block = build_mutation_prompt_block(agent)
    assert "courier-1" in block


def test_clear_mutation_restores_inactive_state():
    agent = {"agent_id": "analyst-1", "role": "analyst"}
    apply_mutation(agent, mutation_type=MutationType.ROLE_DRIFT, source_agent="courier-1", current_round=7)
    previous = clear_mutation(agent)
    assert previous["active"] is True
    assert agent["mutation"]["active"] is False
