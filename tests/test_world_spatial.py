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


from orchestrator.world_spatial import WorldSpatialEngine, ZONE_BOUNDARIES
import math

def test_zone_for_position():
    assert WorldSpatialEngine.zone_for(col=5, row=5) == "hub"
    assert WorldSpatialEngine.zone_for(col=70, row=5) == "courier_zone"
    assert WorldSpatialEngine.zone_for(col=5, row=50) == "guardian_fortress"

def test_proximity_contacts():
    contacts = WorldSpatialEngine.proximity_contacts(
        positions=[
            {"agent_id": "courier-1", "col": 10, "row": 10, "zone": "hub"},
            {"agent_id": "analyst-1", "col": 11, "row": 10, "zone": "hub"},
            {"agent_id": "guardian",  "col": 30, "row": 30, "zone": "hub"},
        ],
        radius=3,
    )
    pairs = {(c["a"], c["b"]) for c in contacts}
    assert ("courier-1", "analyst-1") in pairs or ("analyst-1", "courier-1") in pairs
    assert not any("guardian" in (c["a"], c["b"]) for c in contacts)

def test_move_toward():
    new_pos = WorldSpatialEngine.move_toward(
        col=10, row=10, target_col=14, target_row=10, speed=2
    )
    assert new_pos == (12, 10)
