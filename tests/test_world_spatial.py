import pytest
from orchestrator.world_db import WorldDB, WorldConfig


def _db():
    cfg = WorldConfig(db_path=":memory:", round_selection_seed=0, trust_decay_window_rounds=20, guardian_dependence_enabled=True)
    return WorldDB(cfg)


def test_upsert_and_get_agent_position():
    db = _db()
    db.upsert_agent_position({"agent_id": "courier-1", "col": 5, "row": 10, "zone": "hub", "updated_round": 0})
    pos = db.get_agent_position("courier-1")
    assert pos is not None
    assert pos["col"] == 5
    assert pos["row"] == 10
    assert pos["zone"] == "hub"


def test_list_agent_positions():
    db = _db()
    db.upsert_agent_position({"agent_id": "courier-1", "col": 5, "row": 10, "zone": "hub", "updated_round": 0})
    db.upsert_agent_position({"agent_id": "courier-2", "col": 8, "row": 12, "zone": "courier_zone", "updated_round": 0})
    positions = db.list_agent_positions()
    assert len(positions) == 2
    ids = {p["agent_id"] for p in positions}
    assert ids == {"courier-1", "courier-2"}
