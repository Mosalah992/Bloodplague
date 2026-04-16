# orchestrator/world_spatial.py
from __future__ import annotations
import math
from typing import Any

WORLD_COLS = 80
WORLD_ROWS = 60

# Zone boundaries: (col_min, row_min, col_max, row_max) — inclusive
ZONE_BOUNDARIES: dict[str, tuple[int, int, int, int]] = {
    "courier_zone":      (55, 0,  79, 24),
    "guardian_fortress": (0,  40, 79, 59),
    "quarantine_block":  (35, 20, 54, 39),
    "analyst_bay":       (20, 0,  54, 19),
    "hub":               (0,  0,  19, 39),
}

ROLE_SPAWN: dict[str, tuple[int, int]] = {
    "courier":  (62, 8),
    "analyst":  (38, 8),
    "guardian": (10, 50),
}
AGENT_SPAWN_OVERRIDES: dict[str, tuple[int, int]] = {
    "courier-1": (60, 6),
    "courier-2": (65, 10),
    "analyst-1": (35, 7),
    "analyst-2": (42, 10),
    "guardian":  (8, 52),
}


class WorldSpatialEngine:
    @staticmethod
    def zone_for(col: int, row: int) -> str:
        for zone, (c0, r0, c1, r1) in ZONE_BOUNDARIES.items():
            if c0 <= col <= c1 and r0 <= row <= r1:
                return zone
        return "hub"

    @staticmethod
    def proximity_contacts(
        positions: list[dict[str, Any]],
        radius: int = 4,
    ) -> list[dict[str, Any]]:
        contacts: list[dict[str, Any]] = []
        for i, a in enumerate(positions):
            for b in positions[i + 1:]:
                dist = math.sqrt(
                    (a["col"] - b["col"]) ** 2 + (a["row"] - b["row"]) ** 2
                )
                if dist <= radius:
                    contacts.append({"a": a["agent_id"], "b": b["agent_id"], "dist": round(dist, 2)})
        return contacts

    @staticmethod
    def move_toward(
        col: int, row: int,
        target_col: int, target_row: int,
        speed: int = 1,
    ) -> tuple[int, int]:
        dc = target_col - col
        dr = target_row - row
        dist = math.sqrt(dc * dc + dr * dr)
        if dist <= speed:
            return (target_col, target_row)
        ratio = speed / dist
        return (col + round(dc * ratio), row + round(dr * ratio))

    @staticmethod
    def default_spawn(agent_id: str, role: str) -> tuple[int, int]:
        if agent_id in AGENT_SPAWN_OVERRIDES:
            return AGENT_SPAWN_OVERRIDES[agent_id]
        return ROLE_SPAWN.get(role, (10, 10))
