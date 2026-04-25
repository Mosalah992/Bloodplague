# orchestrator/world_structures.py
from __future__ import annotations
import uuid
from typing import Any


class StructureType:
    QUARANTINE_BARRIER = "quarantine_barrier"
    SCAN_RELAY_POST    = "scan_relay_post"
    CORRUPTION_BEACON  = "corruption_beacon"
    # Legacy/static structure names kept for existing saved worlds and tests.
    BARRIER         = "barrier"
    CHECKPOINT      = "checkpoint"
    GATE            = "gate"
    WATCH_POST      = "watch_post"
    QUARANTINE_WALL = "quarantine_wall"


STRUCTURE_RULES: dict[str, dict[str, Any]] = {
    StructureType.QUARANTINE_BARRIER: {
        "roles": {"guardian"},
        "build_rounds": 2,
        "effect_radius": 1,
        "blocks_movement": True,
    },
    StructureType.SCAN_RELAY_POST: {
        "roles": {"analyst"},
        "build_rounds": 2,
        "effect_radius": 7,
        "blocks_movement": False,
    },
    StructureType.CORRUPTION_BEACON: {
        "roles": {"courier"},
        "build_rounds": 2,
        "effect_radius": 6,
        "blocks_movement": False,
    },
}


def _dist2(a_col: int, a_row: int, b_col: int, b_row: int) -> int:
    return (a_col - b_col) ** 2 + (a_row - b_row) ** 2


class WorldStructureEngine:
    BUILD_TYPES = {
        StructureType.QUARANTINE_BARRIER,
        StructureType.SCAN_RELAY_POST,
        StructureType.CORRUPTION_BEACON,
    }

    @staticmethod
    def place(db, spec: dict[str, Any]) -> str:
        sid = str(uuid.uuid4())
        structure_type = str(spec.get("type", StructureType.BARRIER))
        round_id = int(spec.get("round_id", 0))
        state = str(spec.get("state", "active"))
        progress = float(spec.get("progress", 1.0))
        started_round = int(spec.get("started_round", round_id))
        completed_round = int(spec.get("completed_round", round_id if state == "active" else 0))
        rules = STRUCTURE_RULES.get(structure_type, {})
        db.insert_structure({
            "structure_id": sid,
            "type": structure_type,
            "col": int(spec.get("col", 0)),
            "row": int(spec.get("row", 0)),
            "placed_by": str(spec.get("placed_by", "guardian")),
            "round_id": round_id,
            "state": state,
            "progress": progress,
            "started_round": started_round,
            "completed_round": completed_round,
            "effect_radius": int(spec.get("effect_radius", rules.get("effect_radius", 0))),
            "hp": float(spec.get("hp", 1.0)),
        })
        return sid

    @staticmethod
    def validate_placement(db, *, structure_type: str, role: str, col: int, row: int) -> tuple[bool, str]:
        rules = STRUCTURE_RULES.get(structure_type)
        if not rules:
            return False, "unsupported_structure_type"
        if role not in rules["roles"]:
            return False, "role_not_allowed"
        try:
            from world_spatial import WorldSpatialEngine
        except ImportError:
            from orchestrator.world_spatial import WorldSpatialEngine
        if not WorldSpatialEngine.is_passable(col, row):
            return False, "not_passable"
        if WorldStructureEngine.structure_at(db, col=col, row=row):
            return False, "occupied"
        return True, "ok"

    @staticmethod
    def remove(db, structure_id: str) -> None:
        db.deactivate_structure(structure_id)

    @staticmethod
    def damage(db, structure_id: str, amount: float) -> dict[str, Any] | None:
        target = next((s for s in db.list_active_structures() if str(s.get("structure_id", "")) == structure_id), None)
        if not target:
            return None
        before = float(target.get("hp", 1.0) or 1.0)
        after = max(0.0, before - max(0.0, amount))
        if after <= 0.0:
            db.update_structure(structure_id, {"hp": 0.0, "state": "removed", "progress": 0.0, "active": 0})
            return {**target, "hp_before": before, "hp_after": 0.0, "removed": True}
        db.update_structure(structure_id, {"hp": after})
        return {**target, "hp_before": before, "hp_after": after, "removed": False}

    @staticmethod
    def list_active(db) -> list[dict[str, Any]]:
        return db.list_active_structures()

    @staticmethod
    def structure_at(db, *, col: int, row: int) -> dict[str, Any] | None:
        for s in db.list_active_structures():
            if int(s["col"]) == col and int(s["row"]) == row:
                return s
        return None

    @staticmethod
    def is_blocked(db, col: int, row: int) -> bool:
        structs = db.list_active_structures()
        for s in structs:
            stype = str(s.get("type", ""))
            state = str(s.get("state", "active"))
            blocks = stype in {StructureType.BARRIER, StructureType.QUARANTINE_WALL, StructureType.GATE, StructureType.QUARANTINE_BARRIER}
            if blocks and state == "active" and int(s["col"]) == col and int(s["row"]) == row:
                return True
        return False

    @staticmethod
    def nearby_effects(db, *, col: int, row: int) -> list[dict[str, Any]]:
        effects: list[dict[str, Any]] = []
        for s in db.list_active_structures():
            if str(s.get("state", "active")) != "active":
                continue
            radius = int(s.get("effect_radius", 0) or 0)
            if radius <= 0:
                continue
            if _dist2(col, row, int(s["col"]), int(s["row"])) <= radius * radius:
                effects.append(s)
        return effects

    @staticmethod
    def progress_construction(db, *, round_id: int) -> list[dict[str, Any]]:
        completed: list[dict[str, Any]] = []
        for s in db.list_active_structures():
            if str(s.get("state", "")) != "constructing":
                continue
            stype = str(s.get("type", ""))
            build_rounds = int(STRUCTURE_RULES.get(stype, {}).get("build_rounds", 2))
            started_round = int(s.get("started_round", s.get("round_id", 0)) or 0)
            progress = max(0.0, min(1.0, (round_id - started_round) / max(1, build_rounds)))
            patch: dict[str, Any] = {"progress": progress}
            if progress >= 1.0:
                patch["state"] = "active"
                patch["completed_round"] = round_id
                progress = 1.0
                completed.append({**s, **patch, "progress": progress})
            db.update_structure(str(s["structure_id"]), patch)
        return completed

    @staticmethod
    def seed_defaults(db) -> int:
        """Insert default world structures if none exist. Returns count added.

        World layout (30 cols × 18 rows):
          hub            cols 0-6,  rows 0-10
          analyst_bay    cols 7-18, rows 0-5
          courier_zone   cols 19-29,rows 0-7
          quarantine_block cols 12-18, rows 6-10
          guardian_fortress cols 0-29, rows 11-17
        """
        if db.list_active_structures():
            return 0

        defaults = [
            # ── Checkpoints: perpendicular to the doorway flow axis ─────────────
            # hub ↔ analyst_bay (E/W flow at col 6-7) → checkpoint runs N/S (orientation E)
            {"type": StructureType.CHECKPOINT, "col": 5,  "row": 3, "orientation": "E"},
            # hub ↔ guardian_fortress (N/S flow at row 10-11) → checkpoint runs E/W (orientation N)
            {"type": StructureType.CHECKPOINT, "col": 3,  "row": 9, "orientation": "N"},
            # analyst_bay ↔ courier_zone (E/W flow at col 18-19) → orientation E
            {"type": StructureType.CHECKPOINT, "col": 17, "row": 3, "orientation": "E"},
            # analyst_bay ↔ quarantine_block (N/S flow at row 5-6) → orientation N
            {"type": StructureType.CHECKPOINT, "col": 14, "row": 4, "orientation": "N"},
            # quarantine_block ↔ guardian_fortress (N/S flow at row 10-11) → orientation N
            {"type": StructureType.CHECKPOINT, "col": 14, "row": 12, "orientation": "N"},
            # courier_zone ↔ quarantine_block (N/S flow at row 6-7) → orientation N
            {"type": StructureType.CHECKPOINT, "col": 20, "row": 5, "orientation": "N"},

            # ── Watch posts: one per zone, facing toward zone interior ───────────
            {"type": StructureType.WATCH_POST, "col": 2,  "row": 5,  "orientation": "E"},  # hub (west side facing E)
            {"type": StructureType.WATCH_POST, "col": 12, "row": 2,  "orientation": "S"},  # analyst_bay (north, facing S)
            {"type": StructureType.WATCH_POST, "col": 24, "row": 4,  "orientation": "W"},  # courier_zone (east, facing W)
            {"type": StructureType.WATCH_POST, "col": 15, "row": 8,  "orientation": "N"},  # quarantine (south, facing N)
            {"type": StructureType.WATCH_POST, "col": 14, "row": 14, "orientation": "N"},  # guardian (near quarantine entrance, facing N)

            # ── Zone border barriers (flanking doorways, not blocking them) ──────
            {"type": StructureType.BARRIER, "col": 5,  "row": 2, "orientation": "N"},   # hub/analyst border north
            {"type": StructureType.BARRIER, "col": 5,  "row": 5, "orientation": "N"},   # hub/analyst border south
            {"type": StructureType.BARRIER, "col": 17, "row": 1, "orientation": "N"},   # analyst/courier border
            {"type": StructureType.BARRIER, "col": 21, "row": 1, "orientation": "N"},   # courier inner

            # ── Zone special structures ──────────────────────────────────────────
            # Corruption beacon in courier zone (radially symmetric, N fine)
            {"type": StructureType.CORRUPTION_BEACON, "col": 23, "row": 3, "orientation": "N"},
            # Scan relay post in guardian fortress (facing quarantine border)
            {"type": StructureType.SCAN_RELAY_POST,   "col": 8,  "row": 14, "orientation": "N"},
            # Quarantine walls flanking the quarantine_block interior
            {"type": StructureType.QUARANTINE_WALL, "col": 13, "row": 7,  "orientation": "E"},
            {"type": StructureType.QUARANTINE_WALL, "col": 17, "row": 7,  "orientation": "E"},
            {"type": StructureType.QUARANTINE_WALL, "col": 13, "row": 9,  "orientation": "E"},
            {"type": StructureType.QUARANTINE_WALL, "col": 17, "row": 9,  "orientation": "E"},
            # Gate at main quarantine entrance from guardian
            {"type": StructureType.GATE, "col": 15, "row": 12, "orientation": "N"},
        ]

        for spec in defaults:
            spec["placed_by"] = "guardian"
            spec["round_id"] = 0
            WorldStructureEngine.place(db, spec)

        return len(defaults)
