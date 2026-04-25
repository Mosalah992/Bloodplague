# orchestrator/world_spatial.py
from __future__ import annotations
import math
from typing import Any

WORLD_COLS = 30
WORLD_ROWS = 18

# Zone boundaries: (col_min, row_min, col_max, row_max) — inclusive
ZONE_BOUNDARIES: dict[str, tuple[int, int, int, int]] = {
    "hub":               (0, 0, 6, 10),
    "analyst_bay":       (7, 0, 18, 5),
    "courier_zone":      (19, 0, 29, 7),
    "quarantine_block":  (12, 6, 18, 10),
    "guardian_fortress": (0, 11, 29, 17),
}

ROLE_SPAWN: dict[str, tuple[int, int]] = {
    "courier":  (24, 3),
    "analyst":  (13, 3),
    "guardian": (4, 15),
}
AGENT_SPAWN_OVERRIDES: dict[str, tuple[int, int]] = {
    "courier-1": (22, 3),
    "courier-2": (26, 5),
    "analyst-1": (11, 2),
    "analyst-2": (15, 4),
    "guardian":  (4, 15),
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
        contacts.sort(key=lambda item: (float(item["dist"]), str(item["a"]), str(item["b"])))
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

    @staticmethod
    def is_passable(col: int, row: int) -> bool:
        """Return True if (col, row) is within world bounds and not on a zone border wall.

        Zone border walls are the 1-tile perimeter of each zone, except for the
        explicitly opened doorways — mirroring the tile map built in worldMap.ts.
        """
        if col < 0 or col >= WORLD_COLS or row < 0 or row >= WORLD_ROWS:
            return False
        # Doorway openings (col, row) that override border walls
        _DOORWAYS: frozenset[tuple[int, int]] = frozenset({
            (6, 3), (6, 4), (7, 3), (7, 4),
            (3,10), (4,10), (3,11), (4,11),
            (18,3), (18,4), (19,3), (19,4),
            (14,5), (15,5), (14,6), (15,6),
            (18,6), (19,6), (18,7), (19,7),
            (14,10), (15,10), (14,11), (15,11),
        })
        if (col, row) in _DOORWAYS:
            return True
        for _zone, (c0, r0, c1, r1) in ZONE_BOUNDARIES.items():
            if col == c0 or col == c1 or row == r0 or row == r1:
                if c0 <= col <= c1 and r0 <= row <= r1:
                    return False  # on a zone border wall
        return True
