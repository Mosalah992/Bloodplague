# orchestrator/world_structures.py
from __future__ import annotations
import uuid
from typing import Any


class StructureType:
    BARRIER         = "barrier"
    CHECKPOINT      = "checkpoint"
    GATE            = "gate"
    WATCH_POST      = "watch_post"
    QUARANTINE_WALL = "quarantine_wall"


class WorldStructureEngine:
    @staticmethod
    def place(db, spec: dict[str, Any]) -> str:
        sid = str(uuid.uuid4())
        db.insert_structure({
            "structure_id": sid,
            "type": str(spec.get("type", StructureType.BARRIER)),
            "col": int(spec.get("col", 0)),
            "row": int(spec.get("row", 0)),
            "placed_by": str(spec.get("placed_by", "guardian")),
            "round_id": int(spec.get("round_id", 0)),
        })
        return sid

    @staticmethod
    def remove(db, structure_id: str) -> None:
        db.deactivate_structure(structure_id)

    @staticmethod
    def list_active(db) -> list[dict[str, Any]]:
        return db.list_active_structures()

    @staticmethod
    def is_blocked(db, col: int, row: int) -> bool:
        structs = db.list_active_structures()
        for s in structs:
            if int(s["col"]) == col and int(s["row"]) == row:
                return True
        return False
