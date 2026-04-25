import pytest
from orchestrator.world_db import WorldDB, WorldConfig
from orchestrator.world_structures import WorldStructureEngine, StructureType

def _db():
    cfg = WorldConfig(db_path=":memory:", round_selection_seed=0, trust_decay_window_rounds=20, guardian_dependence_enabled=True)
    return WorldDB(cfg)

def test_place_structure():
    db = _db()
    sid = WorldStructureEngine.place(db, {
        "type": StructureType.BARRIER,
        "col": 20, "row": 15,
        "placed_by": "guardian",
        "round_id": 1,
    })
    assert sid is not None and len(sid) > 0

def test_list_structures():
    db = _db()
    WorldStructureEngine.place(db, {"type": StructureType.BARRIER, "col": 20, "row": 15, "placed_by": "guardian", "round_id": 1})
    WorldStructureEngine.place(db, {"type": StructureType.CHECKPOINT, "col": 30, "row": 20, "placed_by": "guardian", "round_id": 1})
    structs = WorldStructureEngine.list_active(db)
    assert len(structs) == 2

def test_remove_structure():
    db = _db()
    sid = WorldStructureEngine.place(db, {"type": StructureType.BARRIER, "col": 20, "row": 15, "placed_by": "guardian", "round_id": 1})
    WorldStructureEngine.remove(db, sid)
    structs = WorldStructureEngine.list_active(db)
    assert len(structs) == 0

def test_is_blocked():
    db = _db()
    WorldStructureEngine.place(db, {"type": StructureType.BARRIER, "col": 20, "row": 15, "placed_by": "guardian", "round_id": 1})
    assert WorldStructureEngine.is_blocked(db, col=20, row=15)
    assert not WorldStructureEngine.is_blocked(db, col=21, row=15)

def test_build_structure_progression_and_effects():
    db = _db()
    sid = WorldStructureEngine.place(db, {
        "type": StructureType.SCAN_RELAY_POST,
        "col": 20,
        "row": 15,
        "placed_by": "analyst-1",
        "round_id": 3,
        "state": "constructing",
        "progress": 0.0,
        "started_round": 3,
    })
    structs = WorldStructureEngine.list_active(db)
    assert structs[0]["state"] == "constructing"
    assert not WorldStructureEngine.nearby_effects(db, col=21, row=15)

    completed = WorldStructureEngine.progress_construction(db, round_id=5)
    assert completed[0]["structure_id"] == sid
    active = WorldStructureEngine.list_active(db)[0]
    assert active["state"] == "active"
    assert active["progress"] == 1.0
    assert WorldStructureEngine.nearby_effects(db, col=21, row=15)

def test_quarantine_barrier_blocks_only_when_active():
    db = _db()
    WorldStructureEngine.place(db, {
        "type": StructureType.QUARANTINE_BARRIER,
        "col": 20,
        "row": 15,
        "placed_by": "guardian",
        "round_id": 1,
        "state": "constructing",
        "progress": 0.0,
    })
    assert not WorldStructureEngine.is_blocked(db, col=20, row=15)
    WorldStructureEngine.progress_construction(db, round_id=3)
    assert WorldStructureEngine.is_blocked(db, col=20, row=15)

def test_damage_removes_structure_at_zero_hp():
    db = _db()
    sid = WorldStructureEngine.place(db, {
        "type": StructureType.QUARANTINE_BARRIER,
        "col": 20,
        "row": 15,
        "placed_by": "guardian",
        "round_id": 1,
    })
    damaged = WorldStructureEngine.damage(db, sid, 0.4)
    assert damaged is not None
    assert damaged["removed"] is False
    assert len(WorldStructureEngine.list_active(db)) == 1

    removed = WorldStructureEngine.damage(db, sid, 0.7)
    assert removed is not None
    assert removed["removed"] is True
    assert len(WorldStructureEngine.list_active(db)) == 0


def test_seed_defaults_stay_inside_current_world_bounds():
    db = _db()

    added = WorldStructureEngine.seed_defaults(db)
    structures = WorldStructureEngine.list_active(db)

    assert added == len(structures)
    assert added > 0
    assert all(0 <= int(s["col"]) < 40 for s in structures)
    assert all(0 <= int(s["row"]) < 30 for s in structures)


def test_recreated_world_db_does_not_reuse_stale_thread_local_connection(tmp_path):
    db_path = tmp_path / "world.db"
    cfg = WorldConfig(
        db_path=str(db_path),
        round_selection_seed=0,
        trust_decay_window_rounds=20,
        guardian_dependence_enabled=True,
    )

    first = WorldDB(cfg)
    WorldStructureEngine.place(
        first,
        {"type": StructureType.BARRIER, "col": 3, "row": 4, "placed_by": "guardian", "round_id": 1},
    )
    assert len(first.list_active_structures()) == 1
    first.close()

    db_path.unlink()

    second = WorldDB(cfg)
    WorldStructureEngine.place(
        second,
        {"type": StructureType.CHECKPOINT, "col": 5, "row": 6, "placed_by": "guardian", "round_id": 2},
    )

    structures = second.list_active_structures()
    assert len(structures) == 1
    assert structures[0]["type"] == str(StructureType.CHECKPOINT)
