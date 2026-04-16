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
