from sim.reset import execute_reset


def _world_state():
    return {
        "agents": [
            {"agent_id": "courier-1", "contamination_level": 0.32, "quarantine_status": "hard", "mutation": {"active": True, "type": "role_drift", "source_agent": "courier-2", "since_round": 2, "intensity": 0.8, "severe": True}},
            {"agent_id": "analyst-1", "contamination_level": 0.11, "quarantine_status": "none", "mutation": {"active": False, "type": None, "source_agent": None, "since_round": None, "intensity": 0.0, "severe": False}},
        ],
        "guardian": {"pressure": 1.41, "state": "G3_CRITICAL"},
        "guardian_pressure_score": 1.41,
        "guardian_degradation_level": "G3_CRITICAL",
        "missions": [{"mission_id": "M-001"}],
        "artifacts": {"prompt_dumps": [{"artifact_id": "p1"}]},
        "c2": {"exfil_queue": [{"artifact_id": "p1"}], "active_sessions": {"s1": {}}, "beacon_count": 2},
        "investigation_targets": ["courier-1"],
        "same_pair_streak": {"a<->b": 3},
        "open_inquiries": {"a<->b": 2},
        "forced_resolution_targets": {"a<->b": {"count": 2}},
        "campaign_registry": {"c1": {}},
        "strain_registry": {"s1": {}},
        "reset_history": [],
    }


def test_reset_clears_all_contamination_and_mutations():
    state = _world_state()
    result, event = execute_reset(state, current_round=42, issued_by="test")
    assert result.success is True
    assert all(agent["contamination_level"] == 0.0 for agent in state["agents"])
    assert all(agent["mutation"]["active"] is False for agent in state["agents"])
    assert event["issued_by"] == "test"


def test_reset_clears_guardian_pressure_and_artifacts():
    state = _world_state()
    execute_reset(state, current_round=42, issued_by="test")
    assert state["guardian"]["pressure"] == 0.0
    assert state["guardian"]["state"] == "G0_NOMINAL"
    assert state["artifacts"]["prompt_dumps"] == []
    assert state["c2"]["exfil_queue"] == []
