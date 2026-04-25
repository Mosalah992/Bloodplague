# Epidemic World Simulation Transformation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the existing Pixel Lab office view into a persistent, multi-zone top-down world where Courier/Analyst/Guardian agents roam freely, build structures, spread infection through proximity and conversation, and can be fully inspected.

**Architecture:** The existing `OfficeState` + `EpidemicAdapter` + `PersistentWorldEngine` remain as the backbone. We layer on: a multi-zone `WorldMap` (80×60 tiles), a smooth pan/zoom `WorldCamera`, a `SpatialEngine` in the backend that tracks positions and emits proximity events, a `StructureSystem` for dynamic wall/barrier placement, a `ConversationBubble` renderer for LLM dialogue, an `InfectionOverlay` for tile-level contamination heat maps, and a `WorldHUD` with zone status and an `AgentInspector` panel.

**Tech Stack:** TypeScript/React frontend, HTML5 Canvas 2D, Python/FastAPI backend, Redis pub/sub, SQLite (world.db), Ollama local LLM.

---

## Scope Note

This spec covers six independent subsystems. **This plan implements them in four phases, each of which produces working, inspectable software independently.** Recommend executing phase by phase and committing between phases.

- **Phase 1** (Tasks 1–8): World Foundation — multi-zone map, camera, free-roam agents, backend spatial tracking
- **Phase 2** (Tasks 9–14): World Dynamics — infection overlay, structure/barrier system, quarantine zone enforcement
- **Phase 3** (Tasks 15–18): Conversation System — LLM speech bubbles, proximity-triggered dialogue
- **Phase 4** (Tasks 19–22): HUD, Investigation Panel, animation polish

---

## File Map

### New Files
| Path | Responsibility |
|------|---------------|
| `orchestrator/world_spatial.py` | Tracks agent (col,row) positions, emits AGENT_MOVED / PROXIMITY_CONTACT events |
| `orchestrator/world_structures.py` | Structure placement/removal, barrier collision, quarantine zone registry |
| `frontend/src/pixel/world/worldMap.ts` | 80×60 multi-zone tile map definition & zone registry |
| `frontend/src/pixel/world/worldCamera.ts` | Pan + zoom camera with bounds clamping & smooth lerp |
| `frontend/src/pixel/world/worldState.ts` | Extends OfficeState with world-scale state (zones, structures, contamination tiles) |
| `frontend/src/pixel/world/worldRenderer.ts` | Renders world map, zone overlays, structures, infection heat map |
| `frontend/src/pixel/world/infectionOverlay.ts` | Per-tile contamination accumulation and decay |
| `frontend/src/pixel/world/structureLayer.ts` | Dynamic structure sprites (barriers, walls, checkpoints, gates) |
| `frontend/src/pixel/world/speechBubble.ts` | Speech bubble state machine: queues LLM text, animates display |
| `frontend/src/pixel/worldAdapter.ts` | Replaces EpidemicAdapter; maps all backend events to WorldState |
| `frontend/src/components/world/WorldView.tsx` | Top-level world view component (replaces PixelLabView) |
| `frontend/src/components/world/WorldHUD.tsx` | HUD overlay: zone infection meters, Guardian status, alerts |
| `frontend/src/components/world/AgentInspector.tsx` | Click-to-inspect panel: role/state/memory/conversations/trust |
| `frontend/src/components/world/ZoneMinimap.tsx` | Minimap showing zone infection pressure |
| `tests/test_world_spatial.py` | Tests for spatial engine |
| `tests/test_world_structures.py` | Tests for structure system |

### Modified Files
| Path | Change |
|------|--------|
| `orchestrator/world_db.py` | Add `agent_positions`, `world_structures`, `contamination_tiles` tables |
| `orchestrator/main.py` | Expose `/api/world/spatial`, `/api/world/structures`, `/api/world/contamination` endpoints |
| `frontend/src/pixel/office/engine/officeState.ts` | Add `zoneMap`, `contaminationTiles`, `structures` accessors used by WorldState |
| `frontend/src/pixel/constants.ts` | Add WORLD_COLS=80, WORLD_ROWS=60, ZONE definitions |
| `frontend/src/App.jsx` | Route `/world` to WorldView, keep `/lab` for legacy PixelLabView |

---

## Phase 1: World Foundation

### Task 1: Backend — agent_positions table in world_db

**Files:**
- Modify: `orchestrator/world_db.py`
- Create: `tests/test_world_spatial.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_world_spatial.py
import pytest
from orchestrator.world_db import WorldDB, WorldConfig

def test_upsert_and_get_agent_position():
    cfg = WorldConfig()
    db = WorldDB(":memory:", cfg)
    db.upsert_agent_position({"agent_id": "courier-1", "col": 5, "row": 10, "zone": "hub"})
    pos = db.get_agent_position("courier-1")
    assert pos is not None
    assert pos["col"] == 5
    assert pos["row"] == 10
    assert pos["zone"] == "hub"

def test_list_agent_positions():
    cfg = WorldConfig()
    db = WorldDB(":memory:", cfg)
    db.upsert_agent_position({"agent_id": "courier-1", "col": 5, "row": 10, "zone": "hub"})
    db.upsert_agent_position({"agent_id": "courier-2", "col": 8, "row": 12, "zone": "courier_zone"})
    positions = db.list_agent_positions()
    assert len(positions) == 2
    ids = {p["agent_id"] for p in positions}
    assert ids == {"courier-1", "courier-2"}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/salaz4r/Bloodplague-main
python -m pytest tests/test_world_spatial.py -v
```
Expected: FAIL — `AttributeError: 'WorldDB' object has no attribute 'upsert_agent_position'`

- [ ] **Step 3: Add agent_positions table and methods to world_db.py**

Open `orchestrator/world_db.py`. Find the `_create_tables` method and add after the existing CREATE TABLE statements:

```python
        cur.execute("""
            CREATE TABLE IF NOT EXISTS agent_positions (
                agent_id TEXT PRIMARY KEY,
                col INTEGER NOT NULL DEFAULT 0,
                row INTEGER NOT NULL DEFAULT 0,
                zone TEXT NOT NULL DEFAULT 'hub',
                updated_round INTEGER NOT NULL DEFAULT 0
            )
        """)
```

Add these methods to `WorldDB`:

```python
    def upsert_agent_position(self, pos: dict) -> None:
        def tx():
            self._conn.execute(
                """INSERT INTO agent_positions (agent_id, col, row, zone, updated_round)
                   VALUES (:agent_id, :col, :row, :zone, :updated_round)
                   ON CONFLICT(agent_id) DO UPDATE SET
                     col=excluded.col, row=excluded.row,
                     zone=excluded.zone, updated_round=excluded.updated_round""",
                {
                    "agent_id": pos["agent_id"],
                    "col": int(pos.get("col", 0)),
                    "row": int(pos.get("row", 0)),
                    "zone": str(pos.get("zone", "hub")),
                    "updated_round": int(pos.get("updated_round", 0)),
                },
            )
        self.run_tx(tx)

    def get_agent_position(self, agent_id: str) -> dict | None:
        cur = self._conn.execute(
            "SELECT * FROM agent_positions WHERE agent_id=?", (agent_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def list_agent_positions(self) -> list[dict]:
        cur = self._conn.execute("SELECT * FROM agent_positions")
        return [dict(r) for r in cur.fetchall()]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_world_spatial.py -v
```
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add orchestrator/world_db.py tests/test_world_spatial.py
git commit -m "feat(world-db): add agent_positions table and CRUD methods"
```

---

### Task 2: Backend — world_spatial.py spatial engine

**Files:**
- Create: `orchestrator/world_spatial.py`
- Modify: `tests/test_world_spatial.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_world_spatial.py`:

```python
from orchestrator.world_spatial import WorldSpatialEngine, ZONE_BOUNDARIES

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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_world_spatial.py::test_zone_for_position -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'orchestrator.world_spatial'`

- [ ] **Step 3: Create orchestrator/world_spatial.py**

```python
# orchestrator/world_spatial.py
from __future__ import annotations
import math
from typing import Any

# World is 80 cols × 60 rows
WORLD_COLS = 80
WORLD_ROWS = 60

# Zone boundaries: (col_min, row_min, col_max, row_max) — inclusive
ZONE_BOUNDARIES: dict[str, tuple[int, int, int, int]] = {
    "courier_zone":      (55, 0,  79, 24),
    "guardian_fortress": (0,  40, 79, 59),
    "quarantine_block":  (35, 20, 54, 39),
    "analyst_bay":       (20, 0,  54, 19),
    "hub":               (0,  0,  19, 39),  # fallback / central hub
}

# Default spawn positions per role
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_world_spatial.py -v
```
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add orchestrator/world_spatial.py tests/test_world_spatial.py
git commit -m "feat(world-spatial): add WorldSpatialEngine with zones and proximity detection"
```

---

### Task 3: Backend — world_structures.py and DB table

**Files:**
- Create: `orchestrator/world_structures.py`
- Modify: `orchestrator/world_db.py`
- Create: `tests/test_world_structures.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_world_structures.py
import pytest
from orchestrator.world_db import WorldDB, WorldConfig
from orchestrator.world_structures import WorldStructureEngine, StructureType

def _db():
    cfg = WorldConfig()
    return WorldDB(":memory:", cfg)

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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_world_structures.py -v
```
Expected: FAIL — module not found

- [ ] **Step 3: Add world_structures table to world_db.py**

In `_create_tables`, add:

```python
        cur.execute("""
            CREATE TABLE IF NOT EXISTS world_structures (
                structure_id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                col INTEGER NOT NULL,
                row INTEGER NOT NULL,
                placed_by TEXT NOT NULL DEFAULT 'guardian',
                round_id INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1
            )
        """)
```

Add to `WorldDB`:

```python
    def insert_structure(self, s: dict) -> None:
        def tx():
            self._conn.execute(
                """INSERT INTO world_structures
                   (structure_id, type, col, row, placed_by, round_id, active)
                   VALUES (:structure_id, :type, :col, :row, :placed_by, :round_id, 1)""",
                s,
            )
        self.run_tx(tx)

    def deactivate_structure(self, structure_id: str) -> None:
        def tx():
            self._conn.execute(
                "UPDATE world_structures SET active=0 WHERE structure_id=?",
                (structure_id,),
            )
        self.run_tx(tx)

    def list_active_structures(self) -> list[dict]:
        cur = self._conn.execute(
            "SELECT * FROM world_structures WHERE active=1"
        )
        return [dict(r) for r in cur.fetchall()]
```

- [ ] **Step 4: Create orchestrator/world_structures.py**

```python
# orchestrator/world_structures.py
from __future__ import annotations
import uuid
from typing import Any

class StructureType:
    BARRIER    = "barrier"
    CHECKPOINT = "checkpoint"
    GATE       = "gate"
    WATCH_POST = "watch_post"
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
```

- [ ] **Step 5: Run test to verify it passes**

```bash
python -m pytest tests/test_world_structures.py -v
```
Expected: PASS (4 tests)

- [ ] **Step 6: Commit**

```bash
git add orchestrator/world_db.py orchestrator/world_structures.py tests/test_world_structures.py
git commit -m "feat(world-structures): add structure placement engine and DB table"
```

---

### Task 4: Backend API endpoints for spatial and structures

**Files:**
- Modify: `orchestrator/main.py`

- [ ] **Step 1: Add three new FastAPI routes**

In `orchestrator/main.py`, find the section with existing routes. After the existing imports, add (if not already present):

```python
try:
    from world_spatial import WorldSpatialEngine, AGENT_SPAWN_OVERRIDES, ROLE_SPAWN
    from world_structures import WorldStructureEngine, StructureType
except ImportError:
    from orchestrator.world_spatial import WorldSpatialEngine, AGENT_SPAWN_OVERRIDES, ROLE_SPAWN
    from orchestrator.world_structures import WorldStructureEngine, StructureType
```

Add these three route handlers (before the final `if __name__ == "__main__"` block or after existing API routes):

```python
@app.get("/api/world/spatial")
async def get_world_spatial():
    """Returns current agent positions and proximity contacts."""
    try:
        positions = await asyncio.get_event_loop().run_in_executor(
            None, world_db.list_agent_positions
        )
        contacts = WorldSpatialEngine.proximity_contacts(positions, radius=4)
        return {"positions": positions, "proximity_contacts": contacts}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/world/structures")
async def get_world_structures():
    """Returns active world structures (barriers, walls, checkpoints)."""
    try:
        structs = await asyncio.get_event_loop().run_in_executor(
            None, world_db.list_active_structures
        )
        return {"structures": structs}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.post("/api/world/structures")
async def place_world_structure(body: dict):
    """Place a new structure. Body: {type, col, row, placed_by}."""
    try:
        round_id = await asyncio.get_event_loop().run_in_executor(
            None, world_db.get_latest_round_id
        )
        sid = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: WorldStructureEngine.place(world_db, {**body, "round_id": round_id}),
        )
        return {"structure_id": sid, "ok": True}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.delete("/api/world/structures/{structure_id}")
async def remove_world_structure(structure_id: str):
    """Remove a structure by ID."""
    try:
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: WorldStructureEngine.remove(world_db, structure_id)
        )
        return {"ok": True}
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
```

- [ ] **Step 2: Verify routes load (no import error)**

```bash
cd /home/salaz4r/Bloodplague-main
python -c "import sys; sys.path.insert(0,'orchestrator'); from main import app; print('routes ok')"
```
Expected output: `routes ok`

- [ ] **Step 3: Commit**

```bash
git add orchestrator/main.py
git commit -m "feat(api): add /api/world/spatial and /api/world/structures endpoints"
```

---

### Task 5: Frontend — world constants and zone map

**Files:**
- Modify: `frontend/src/pixel/constants.ts`
- Create: `frontend/src/pixel/world/worldMap.ts`

- [ ] **Step 1: Add world constants to constants.ts**

In `frontend/src/pixel/constants.ts`, find the end of existing constants and add:

```typescript
// World simulation constants
export const WORLD_COLS = 80;
export const WORLD_ROWS = 60;
export const WORLD_TILE_SIZE = 16; // same as TILE_SIZE

export type ZoneId =
  | 'hub'
  | 'analyst_bay'
  | 'courier_zone'
  | 'quarantine_block'
  | 'guardian_fortress';

export interface ZoneDef {
  id: ZoneId;
  label: string;
  colMin: number;
  rowMin: number;
  colMax: number;
  rowMax: number;
  floorColor: string;
  borderColor: string;
  threatColor: string; // used for infection overlay tint
}

export const WORLD_ZONES: ZoneDef[] = [
  {
    id: 'hub',
    label: 'Central Hub',
    colMin: 0,   rowMin: 0,  colMax: 19, rowMax: 39,
    floorColor: '#1a2035', borderColor: '#3b4a6b', threatColor: '#6366f1',
  },
  {
    id: 'analyst_bay',
    label: 'Analyst Bay',
    colMin: 20,  rowMin: 0,  colMax: 54, rowMax: 19,
    floorColor: '#0f2318', borderColor: '#22c55e', threatColor: '#4ade80',
  },
  {
    id: 'courier_zone',
    label: 'Courier Sector',
    colMin: 55,  rowMin: 0,  colMax: 79, rowMax: 24,
    floorColor: '#1f1208', borderColor: '#f97316', threatColor: '#fb923c',
  },
  {
    id: 'quarantine_block',
    label: 'Quarantine Block',
    colMin: 35,  rowMin: 20, colMax: 54, rowMax: 39,
    floorColor: '#1a0a0a', borderColor: '#dc2626', threatColor: '#f87171',
  },
  {
    id: 'guardian_fortress',
    label: 'Guardian Fortress',
    colMin: 0,   rowMin: 40, colMax: 79, rowMax: 59,
    floorColor: '#0a0f1a', borderColor: '#8b5cf6', threatColor: '#a78bfa',
  },
];
```

- [ ] **Step 2: Create frontend/src/pixel/world/worldMap.ts**

```typescript
// frontend/src/pixel/world/worldMap.ts
import { WORLD_COLS, WORLD_ROWS, WORLD_ZONES, type ZoneId, type ZoneDef } from '../constants.js';
import { TileType } from '../office/types.js';

export interface WorldTileInfo {
  type: number; // TileType value
  zone: ZoneId;
  walkable: boolean;
  contaminationLevel: number; // 0.0 – 1.0
}

const _tileMap: number[][] = [];
const _zoneMap: ZoneId[][] = [];

function buildMaps(): void {
  for (let r = 0; r < WORLD_ROWS; r++) {
    _tileMap.push(new Array(WORLD_COLS).fill(TileType.FLOOR_1) as number[]);
    _zoneMap.push(new Array(WORLD_COLS).fill('hub') as ZoneId[]);
  }

  // Assign zone floors
  for (const zone of WORLD_ZONES) {
    for (let r = zone.rowMin; r <= zone.rowMax; r++) {
      for (let c = zone.colMin; c <= zone.colMax; c++) {
        _zoneMap[r][c] = zone.id;
        _tileMap[r][c] = TileType.FLOOR_1;
      }
    }
  }

  // Zone border walls (1-tile thick)
  for (const zone of WORLD_ZONES) {
    for (let c = zone.colMin; c <= zone.colMax; c++) {
      _tileMap[zone.rowMin][c] = TileType.WALL;
      _tileMap[zone.rowMax][c] = TileType.WALL;
    }
    for (let r = zone.rowMin; r <= zone.rowMax; r++) {
      _tileMap[r][zone.colMin] = TileType.WALL;
      _tileMap[r][zone.colMax] = TileType.WALL;
    }
  }

  // Open doorways in walls (3-tile gaps)
  const openings: [number, number][] = [
    // hub ↔ analyst_bay
    [19, 10], [19, 11], [19, 12],
    // hub ↔ guardian_fortress
    [10, 40], [11, 40], [12, 40],
    // analyst_bay ↔ courier_zone
    [55, 8], [55, 9], [55, 10],
    // analyst_bay ↔ quarantine_block
    [40, 20], [41, 20], [42, 20],
    // courier_zone ↔ quarantine_block
    [55, 24], [56, 24], [57, 24],
    // quarantine_block ↔ guardian_fortress
    [40, 40], [41, 40], [42, 40],
  ];
  for (const [c, r] of openings) {
    if (r >= 0 && r < WORLD_ROWS && c >= 0 && c < WORLD_COLS) {
      _tileMap[r][c] = TileType.FLOOR_1;
    }
  }
}

buildMaps();

export function getTileMap(): number[][] {
  return _tileMap;
}

export function getZoneMap(): ZoneId[][] {
  return _zoneMap;
}

export function getZoneForTile(col: number, row: number): ZoneId {
  if (row < 0 || row >= WORLD_ROWS || col < 0 || col >= WORLD_COLS) return 'hub';
  return _zoneMap[row][col];
}

export function getZoneDef(id: ZoneId): ZoneDef {
  return WORLD_ZONES.find((z) => z.id === id) ?? WORLD_ZONES[0];
}

export function isWorldWalkable(col: number, row: number): boolean {
  if (row < 0 || row >= WORLD_ROWS || col < 0 || col >= WORLD_COLS) return false;
  return _tileMap[row][col] !== TileType.WALL;
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd /home/salaz4r/Bloodplague-main/frontend
npx tsc --noEmit 2>&1 | head -30
```
Expected: No errors for the new files (existing errors, if any, are pre-existing).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pixel/constants.ts frontend/src/pixel/world/worldMap.ts
git commit -m "feat(world-map): add 80x60 multi-zone tile map with zone definitions"
```

---

### Task 6: Frontend — WorldCamera with pan/zoom/lerp

**Files:**
- Create: `frontend/src/pixel/world/worldCamera.ts`

- [ ] **Step 1: Create the file**

```typescript
// frontend/src/pixel/world/worldCamera.ts
import { WORLD_COLS, WORLD_ROWS, WORLD_TILE_SIZE } from '../constants.js';

const ZOOM_MIN = 1.0;
const ZOOM_MAX = 4.0;
const ZOOM_STEP = 0.2;
const LERP_SPEED = 8.0; // units/sec

export interface CameraState {
  x: number;       // world-pixel offset X (top-left corner of viewport in world space)
  y: number;       // world-pixel offset Y
  zoom: number;
  targetX: number;
  targetY: number;
  targetZoom: number;
  viewportW: number;
  viewportH: number;
}

export function createCamera(viewportW: number, viewportH: number): CameraState {
  const worldW = WORLD_COLS * WORLD_TILE_SIZE;
  const worldH = WORLD_ROWS * WORLD_TILE_SIZE;
  return {
    x: worldW / 2 - viewportW / 2,
    y: worldH / 2 - viewportH / 2,
    zoom: 2.0,
    targetX: worldW / 2 - viewportW / 2,
    targetY: worldH / 2 - viewportH / 2,
    targetZoom: 2.0,
    viewportW,
    viewportH,
  };
}

export function updateCamera(cam: CameraState, dt: number): void {
  const t = Math.min(1, LERP_SPEED * dt);
  cam.zoom = cam.zoom + (cam.targetZoom - cam.zoom) * t;
  cam.x = cam.x + (cam.targetX - cam.x) * t;
  cam.y = cam.y + (cam.targetY - cam.y) * t;
  clampCamera(cam);
}

export function panCamera(cam: CameraState, dx: number, dy: number): void {
  cam.targetX += dx / cam.zoom;
  cam.targetY += dy / cam.zoom;
  clampCamera(cam);
}

export function zoomCamera(cam: CameraState, delta: number, pivotX: number, pivotY: number): void {
  const prevZoom = cam.targetZoom;
  cam.targetZoom = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, cam.targetZoom + delta * ZOOM_STEP));
  // Zoom toward pivot
  const zoomRatio = cam.targetZoom / prevZoom;
  const worldPivotX = cam.targetX + pivotX / prevZoom;
  const worldPivotY = cam.targetY + pivotY / prevZoom;
  cam.targetX = worldPivotX - pivotX / cam.targetZoom;
  cam.targetY = worldPivotY - pivotY / cam.targetZoom;
  clampCamera(cam);
}

export function focusCamera(cam: CameraState, worldX: number, worldY: number): void {
  cam.targetX = worldX - cam.viewportW / (2 * cam.targetZoom);
  cam.targetY = worldY - cam.viewportH / (2 * cam.targetZoom);
  clampCamera(cam);
}

function clampCamera(cam: CameraState): void {
  const worldW = WORLD_COLS * WORLD_TILE_SIZE;
  const worldH = WORLD_ROWS * WORLD_TILE_SIZE;
  const visW = cam.viewportW / cam.zoom;
  const visH = cam.viewportH / cam.zoom;
  cam.targetX = Math.max(0, Math.min(worldW - visW, cam.targetX));
  cam.targetY = Math.max(0, Math.min(worldH - visH, cam.targetY));
  cam.x = Math.max(0, Math.min(worldW - visW, cam.x));
  cam.y = Math.max(0, Math.min(worldH - visH, cam.y));
}

export function worldToScreen(cam: CameraState, wx: number, wy: number): [number, number] {
  return [(wx - cam.x) * cam.zoom, (wy - cam.y) * cam.zoom];
}

export function screenToWorld(cam: CameraState, sx: number, sy: number): [number, number] {
  return [sx / cam.zoom + cam.x, sy / cam.zoom + cam.y];
}

export function resizeCamera(cam: CameraState, w: number, h: number): void {
  cam.viewportW = w;
  cam.viewportH = h;
  clampCamera(cam);
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /home/salaz4r/Bloodplague-main/frontend
npx tsc --noEmit 2>&1 | grep "worldCamera" | head -10
```
Expected: No errors for worldCamera.ts

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pixel/world/worldCamera.ts
git commit -m "feat(world-camera): add smooth pan/zoom camera with viewport clamping"
```

---

### Task 7: Frontend — WorldState (extends OfficeState for world scale)

**Files:**
- Create: `frontend/src/pixel/world/worldState.ts`

- [ ] **Step 1: Create worldState.ts**

```typescript
// frontend/src/pixel/world/worldState.ts
import { OfficeState } from '../office/engine/officeState.js';
import { getTileMap, getZoneMap, getZoneForTile, isWorldWalkable, type WorldTileInfo } from './worldMap.js';
import type { ZoneId } from '../constants.js';

export interface AgentWorldPosition {
  agentId: string;
  col: number;
  row: number;
  zone: ZoneId;
}

export interface WorldStructure {
  structureId: string;
  type: string;
  col: number;
  row: number;
  placedBy: string;
}

export interface ContaminationTile {
  col: number;
  row: number;
  level: number; // 0.0 – 1.0
}

export class WorldState extends OfficeState {
  agentPositions: Map<string, AgentWorldPosition> = new Map();
  structures: WorldStructure[] = [];
  contaminationTiles: Map<string, number> = new Map(); // key: "col,row" -> level

  constructor() {
    super();
    // Swap the small office tile map for the world tile map
    this.tileMap = getTileMap() as any;
    this.blockedTiles = this._buildWorldBlockedTiles();
    this.walkableTiles = this._buildWorldWalkableTiles();
  }

  private _buildWorldBlockedTiles(): Set<string> {
    const blocked = new Set<string>();
    const map = getTileMap();
    for (let r = 0; r < map.length; r++) {
      for (let c = 0; c < map[r].length; c++) {
        if (!isWorldWalkable(c, r)) blocked.add(`${c},${r}`);
      }
    }
    return blocked;
  }

  private _buildWorldWalkableTiles(): Array<{ col: number; row: number }> {
    const walkable: Array<{ col: number; row: number }> = [];
    const map = getTileMap();
    for (let r = 0; r < map.length; r++) {
      for (let c = 0; c < map[r].length; c++) {
        if (isWorldWalkable(c, r)) walkable.push({ col: c, row: r });
      }
    }
    return walkable;
  }

  setAgentPosition(agentId: string, col: number, row: number): void {
    this.agentPositions.set(agentId, {
      agentId,
      col,
      row,
      zone: getZoneForTile(col, row),
    });
  }

  setStructures(structs: WorldStructure[]): void {
    this.structures = structs;
    // Rebuild blocked tiles to include structures
    this.blockedTiles = this._buildWorldBlockedTiles();
    for (const s of structs) {
      this.blockedTiles.add(`${s.col},${s.row}`);
    }
    this.walkableTiles = this._buildWorldWalkableTiles();
  }

  setContaminationTile(col: number, row: number, level: number): void {
    const key = `${col},${row}`;
    if (level < 0.01) {
      this.contaminationTiles.delete(key);
    } else {
      this.contaminationTiles.set(key, Math.min(1.0, level));
    }
  }

  getContaminationLevel(col: number, row: number): number {
    return this.contaminationTiles.get(`${col},${row}`) ?? 0;
  }

  getZoneForAgent(agentId: string): ZoneId {
    const pos = this.agentPositions.get(agentId);
    if (!pos) return 'hub';
    return pos.zone;
  }
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /home/salaz4r/Bloodplague-main/frontend
npx tsc --noEmit 2>&1 | grep "worldState" | head -10
```
Expected: No errors for worldState.ts

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pixel/world/worldState.ts
git commit -m "feat(world-state): add WorldState extending OfficeState for multi-zone world"
```

---

### Task 8: Frontend — WorldView component with canvas, camera, and basic rendering

**Files:**
- Create: `frontend/src/pixel/world/worldRenderer.ts`
- Create: `frontend/src/components/world/WorldView.tsx`
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1: Create worldRenderer.ts**

```typescript
// frontend/src/pixel/world/worldRenderer.ts
import { WORLD_COLS, WORLD_ROWS, WORLD_TILE_SIZE, WORLD_ZONES, getZoneDef } from '../constants.js';
import type { CameraState } from './worldCamera.js';
import type { WorldState } from './worldState.js';
import { TileType } from '../office/types.js';
import { getTileMap, getZoneMap } from './worldMap.js';

const ZONE_FLOOR_ALPHA = 0.9;
const CONTAMINATION_MAX_ALPHA = 0.7;
const STRUCTURE_COLORS: Record<string, string> = {
  barrier:         '#ef4444',
  checkpoint:      '#f59e0b',
  gate:            '#3b82f6',
  watch_post:      '#8b5cf6',
  quarantine_wall: '#dc2626',
};

export function renderWorld(
  ctx: CanvasRenderingContext2D,
  state: WorldState,
  cam: CameraState,
): void {
  ctx.save();
  ctx.setTransform(cam.zoom, 0, 0, cam.zoom, -cam.x * cam.zoom, -cam.y * cam.zoom);

  const tileMap = getTileMap();
  const zoneMap = getZoneMap();
  const s = WORLD_TILE_SIZE;

  // Visible tile range (culling)
  const c0 = Math.max(0, Math.floor(cam.x / s) - 1);
  const r0 = Math.max(0, Math.floor(cam.y / s) - 1);
  const c1 = Math.min(WORLD_COLS - 1, Math.ceil((cam.x + cam.viewportW / cam.zoom) / s) + 1);
  const r1 = Math.min(WORLD_ROWS - 1, Math.ceil((cam.y + cam.viewportH / cam.zoom) / s) + 1);

  // 1. Draw floor tiles with zone color tint
  for (let r = r0; r <= r1; r++) {
    for (let c = c0; c <= c1; c++) {
      const tile = tileMap[r]?.[c];
      const zoneId = zoneMap[r]?.[c] ?? 'hub';
      const zone = getZoneDef(zoneId);
      const px = c * s;
      const py = r * s;

      if (tile === TileType.WALL) {
        ctx.fillStyle = '#0a0a12';
        ctx.fillRect(px, py, s, s);
        ctx.fillStyle = zone.borderColor + '33';
        ctx.fillRect(px, py, s, s);
      } else {
        ctx.fillStyle = zone.floorColor;
        ctx.globalAlpha = ZONE_FLOOR_ALPHA;
        ctx.fillRect(px, py, s, s);
        ctx.globalAlpha = 1.0;
      }
    }
  }

  // 2. Draw contamination overlay
  for (const [key, level] of state.contaminationTiles) {
    const [c, r] = key.split(',').map(Number);
    if (c < c0 || c > c1 || r < r0 || r > r1) continue;
    const zoneId = zoneMap[r]?.[c] ?? 'hub';
    const zone = getZoneDef(zoneId);
    ctx.fillStyle = zone.threatColor;
    ctx.globalAlpha = level * CONTAMINATION_MAX_ALPHA;
    ctx.fillRect(c * s, r * s, s, s);
    ctx.globalAlpha = 1.0;
  }

  // 3. Draw zone borders
  for (const zone of WORLD_ZONES) {
    ctx.strokeStyle = zone.borderColor + '88';
    ctx.lineWidth = 1;
    ctx.strokeRect(
      zone.colMin * s, zone.rowMin * s,
      (zone.colMax - zone.colMin + 1) * s,
      (zone.rowMax - zone.rowMin + 1) * s,
    );
  }

  // 4. Draw structures
  for (const struct of state.structures) {
    const px = struct.col * s;
    const py = struct.row * s;
    ctx.fillStyle = STRUCTURE_COLORS[struct.type] ?? '#888888';
    ctx.fillRect(px + 1, py + 1, s - 2, s - 2);
    ctx.strokeStyle = '#ffffff44';
    ctx.lineWidth = 0.5;
    ctx.strokeRect(px + 1, py + 1, s - 2, s - 2);
  }

  ctx.restore();
}
```

- [ ] **Step 2: Create frontend/src/components/world/WorldView.tsx**

```tsx
// frontend/src/components/world/WorldView.tsx
import { useEffect, useRef, useCallback } from 'react';
import { WorldState } from '../../pixel/world/worldState.js';
import {
  createCamera, updateCamera, panCamera, zoomCamera,
  resizeCamera, worldToScreen, screenToWorld,
  type CameraState,
} from '../../pixel/world/worldCamera.js';
import { renderWorld } from '../../pixel/world/worldRenderer.js';
import { startGameLoop } from '../../pixel/office/engine/gameLoop.js';

interface Props {
  onAgentClick?: (agentId: string) => void;
}

export default function WorldView({ onAgentClick }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef  = useRef<WorldState | null>(null);
  const camRef    = useRef<CameraState | null>(null);
  const dragRef   = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ws = new WorldState();
    const cam = createCamera(canvas.clientWidth, canvas.clientHeight);
    stateRef.current = ws;
    camRef.current = cam;

    canvas.width  = canvas.clientWidth;
    canvas.height = canvas.clientHeight;
    cam.viewportW = canvas.clientWidth;
    cam.viewportH = canvas.clientHeight;

    const stop = startGameLoop(canvas, {
      update: (dt) => {
        ws.update(dt);
        if (camRef.current) updateCamera(camRef.current, dt);
      },
      render: (ctx) => {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#06060e';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        if (camRef.current) renderWorld(ctx, ws, camRef.current);
      },
    });

    const onResize = () => {
      canvas.width  = canvas.clientWidth;
      canvas.height = canvas.clientHeight;
      if (camRef.current) resizeCamera(camRef.current, canvas.clientWidth, canvas.clientHeight);
    };
    window.addEventListener('resize', onResize);

    return () => {
      stop();
      window.removeEventListener('resize', onResize);
    };
  }, []);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    dragRef.current = { x: e.clientX, y: e.clientY };
  }, []);

  const onMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragRef.current || !camRef.current) return;
    const dx = e.clientX - dragRef.current.x;
    const dy = e.clientY - dragRef.current.y;
    panCamera(camRef.current, -dx, -dy);
    dragRef.current = { x: e.clientX, y: e.clientY };
  }, []);

  const onMouseUp = useCallback(() => {
    dragRef.current = null;
  }, []);

  const onWheel = useCallback((e: React.WheelEvent) => {
    if (!camRef.current) return;
    e.preventDefault();
    const rect = canvasRef.current!.getBoundingClientRect();
    zoomCamera(
      camRef.current,
      e.deltaY < 0 ? 1 : -1,
      e.clientX - rect.left,
      e.clientY - rect.top,
    );
  }, []);

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative', background: '#06060e' }}>
      <canvas
        ref={canvasRef}
        style={{ width: '100%', height: '100%', display: 'block', cursor: 'grab' }}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
        onWheel={onWheel}
      />
    </div>
  );
}
```

- [ ] **Step 3: Add /world route to App.jsx**

In `frontend/src/App.jsx`, find the existing routes. Add an import and route:

```jsx
// Near the top imports, add:
import WorldView from './components/world/WorldView.jsx';
```

Inside the router or view switcher, add a path for world:
```jsx
// In the navigation/routing logic, add:
{view === 'world' && <WorldView />}
```

If App.jsx uses a tab/nav system, add a "World" tab that sets `view='world'`.

- [ ] **Step 4: Start dev server and verify the world renders**

```bash
cd /home/salaz4r/Bloodplague-main/frontend
npm run dev &
sleep 3
curl -s http://localhost:5173 | grep -c "html"
```
Expected: Opens and shows the world canvas with zone-colored floor tiles.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pixel/world/worldRenderer.ts frontend/src/components/world/WorldView.tsx frontend/src/App.jsx
git commit -m "feat(world-view): add WorldView canvas with multi-zone rendering and pan/zoom camera"
```

---

## Phase 2: World Dynamics

### Task 9: Infection overlay — per-tile contamination accumulation and decay

**Files:**
- Create: `frontend/src/pixel/world/infectionOverlay.ts`

- [ ] **Step 1: Create infectionOverlay.ts**

```typescript
// frontend/src/pixel/world/infectionOverlay.ts
import type { WorldState } from './worldState.js';
import { getZoneForTile } from './worldMap.js';

const SPREAD_RADIUS = 2;
const SPREAD_FRACTION = 0.08; // fraction that bleeds to adjacent tiles per event
const DECAY_PER_SEC = 0.005;  // contamination drains slowly over time

export function applyContaminationEvent(
  state: WorldState,
  col: number,
  row: number,
  intensity: number,
): void {
  state.setContaminationTile(col, row,
    (state.getContaminationLevel(col, row) + intensity));

  // Bleed to nearby tiles
  for (let dr = -SPREAD_RADIUS; dr <= SPREAD_RADIUS; dr++) {
    for (let dc = -SPREAD_RADIUS; dc <= SPREAD_RADIUS; dc++) {
      if (dr === 0 && dc === 0) continue;
      const dist = Math.sqrt(dr * dr + dc * dc);
      if (dist > SPREAD_RADIUS) continue;
      const bleed = intensity * SPREAD_FRACTION * (1 - dist / SPREAD_RADIUS);
      const tc = col + dc;
      const tr = row + dr;
      const prev = state.getContaminationLevel(tc, tr);
      state.setContaminationTile(tc, tr, prev + bleed);
    }
  }
}

export function tickContaminationDecay(state: WorldState, dt: number): void {
  const toUpdate: [string, number][] = [];
  for (const [key, level] of state.contaminationTiles) {
    const next = level - DECAY_PER_SEC * dt;
    toUpdate.push([key, next]);
  }
  for (const [key, next] of toUpdate) {
    const [c, r] = key.split(',').map(Number);
    state.setContaminationTile(c, r, next);
  }
}
```

- [ ] **Step 2: Wire decay into WorldView's update loop**

In `frontend/src/components/world/WorldView.tsx`, update the `update` callback:

```tsx
// Add import at top:
import { tickContaminationDecay } from '../../pixel/world/infectionOverlay.js';

// Inside startGameLoop update callback, add after ws.update(dt):
tickContaminationDecay(ws, dt);
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pixel/world/infectionOverlay.ts frontend/src/components/world/WorldView.tsx
git commit -m "feat(infection-overlay): add per-tile contamination accumulation and decay"
```

---

### Task 10: Structure layer rendering

**Files:**
- Modify: `frontend/src/pixel/world/worldRenderer.ts` (already included in Task 8 Step 1)
- Create: `frontend/src/pixel/world/structureLayer.ts`

- [ ] **Step 1: Create structureLayer.ts with animated barrier sprites**

```typescript
// frontend/src/pixel/world/structureLayer.ts
import { WORLD_TILE_SIZE } from '../constants.js';

export type StructureType = 'barrier' | 'checkpoint' | 'gate' | 'watch_post' | 'quarantine_wall';

interface StructureRenderSpec {
  fillColor: string;
  strokeColor: string;
  symbol: string; // single char drawn at center
  pulse?: boolean; // whether to animate alpha
}

const SPECS: Record<string, StructureRenderSpec> = {
  barrier:         { fillColor: '#ef444455', strokeColor: '#ef4444', symbol: '█' },
  checkpoint:      { fillColor: '#f59e0b55', strokeColor: '#f59e0b', symbol: '⬡' },
  gate:            { fillColor: '#3b82f655', strokeColor: '#3b82f6', symbol: '◧' },
  watch_post:      { fillColor: '#8b5cf655', strokeColor: '#8b5cf6', symbol: '◈', pulse: true },
  quarantine_wall: { fillColor: '#dc262699', strokeColor: '#dc2626', symbol: '▓' },
};

export function renderStructureLayer(
  ctx: CanvasRenderingContext2D,
  structures: Array<{ type: string; col: number; row: number }>,
  zoom: number,
  elapsed: number,
): void {
  const s = WORLD_TILE_SIZE;
  for (const struct of structures) {
    const spec = SPECS[struct.type] ?? SPECS['barrier'];
    const px = struct.col * s;
    const py = struct.row * s;

    const alpha = spec.pulse ? 0.7 + 0.3 * Math.sin(elapsed * 3) : 1.0;
    ctx.globalAlpha = alpha;

    ctx.fillStyle = spec.fillColor;
    ctx.fillRect(px, py, s, s);
    ctx.strokeStyle = spec.strokeColor;
    ctx.lineWidth = 1.5 / zoom;
    ctx.strokeRect(px + 0.5, py + 0.5, s - 1, s - 1);

    ctx.fillStyle = spec.strokeColor;
    ctx.font = `${Math.max(8, s * 0.6)}px monospace`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(spec.symbol, px + s / 2, py + s / 2);

    ctx.globalAlpha = 1.0;
  }
}
```

- [ ] **Step 2: Wire structureLayer into worldRenderer.ts**

In `worldRenderer.ts`, replace the structure rendering block (currently just colored rects) with:

```typescript
import { renderStructureLayer } from './structureLayer.js';

// In renderWorld(), replace the "Draw structures" block:
const elapsed = performance.now() / 1000;
renderStructureLayer(ctx, state.structures, cam.zoom, elapsed);
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pixel/world/structureLayer.ts frontend/src/pixel/world/worldRenderer.ts
git commit -m "feat(structure-layer): add animated structure rendering (barriers, walls, checkpoints)"
```

---

### Task 11: Backend — seed agent positions on world startup

**Files:**
- Modify: `orchestrator/main.py`
- Modify: `orchestrator/world_engine.py`

- [ ] **Step 1: Seed positions in ensure_seeded_world**

In `orchestrator/world_engine.py`, add the import after existing imports:

```python
try:
    from world_spatial import WorldSpatialEngine
except ImportError:
    from orchestrator.world_spatial import WorldSpatialEngine
```

Inside `ensure_seeded_world`, after the loop that seeds agent states, add:

```python
            # Seed spatial positions for each agent
            for agent_id, role in agents:
                existing_pos = self.db.get_agent_position(agent_id)
                if not existing_pos:
                    col, row = WorldSpatialEngine.default_spawn(agent_id, role)
                    self.db.upsert_agent_position({
                        "agent_id": agent_id,
                        "col": col,
                        "row": row,
                        "zone": WorldSpatialEngine.zone_for(col, row),
                        "updated_round": 0,
                    })
```

- [ ] **Step 2: Update positions after each round in advance_one_round**

In `advance_one_round`, after `self.db.run_tx(tx_apply)`, add movement updates:

```python
        # Update spatial position: move selected agent one step toward a goal.
        pos = self.db.get_agent_position(selected_agent)
        if pos:
            role_map = self._agent_role_map()
            role = role_map.get(selected_agent, "")
            # Simple patrol: move toward zone center based on role
            zone_targets = {
                "courier":  (62, 8),
                "analyst":  (38, 8),
                "guardian": (8, 52),
            }
            default_target = zone_targets.get(role, (40, 30))
            # Add some jitter so agents wander
            import random
            target_col = default_target[0] + random.randint(-6, 6)
            target_row = default_target[1] + random.randint(-4, 4)
            new_col, new_row = WorldSpatialEngine.move_toward(
                pos["col"], pos["row"], target_col, target_row, speed=2
            )
            self.db.upsert_agent_position({
                "agent_id": selected_agent,
                "col": new_col,
                "row": new_row,
                "zone": WorldSpatialEngine.zone_for(new_col, new_row),
                "updated_round": round_id,
            })
```

- [ ] **Step 3: Test that positions update**

```bash
python -m pytest tests/test_world_spatial.py tests/test_world_structures.py -v
```
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add orchestrator/world_engine.py
git commit -m "feat(world-engine): seed and update agent spatial positions each round"
```

---

### Task 12: Frontend — worldAdapter.ts bridges backend events to WorldState

**Files:**
- Create: `frontend/src/pixel/worldAdapter.ts`

- [ ] **Step 1: Create worldAdapter.ts**

```typescript
// frontend/src/pixel/worldAdapter.ts
import type { WorldState } from './world/worldState.js';
import { applyContaminationEvent } from './world/infectionOverlay.js';
import { WORLD_TILE_SIZE } from './constants.js';

interface SpatialResponse {
  positions: Array<{ agent_id: string; col: number; row: number; zone: string }>;
}

interface StructuresResponse {
  structures: Array<{ structure_id: string; type: string; col: number; row: number; placed_by: string }>;
}

interface LiveEvent {
  id?: string | number;
  type?: string;
  event?: string;
  src?: string;
  dst?: string;
  epidemic_state?: string;
}

const POLL_INTERVAL_MS = 2000;

export class WorldAdapter {
  private state: WorldState;
  private pollHandle: ReturnType<typeof setTimeout> | null = null;
  private seenEventIds = new Set<string>();

  constructor(state: WorldState) {
    this.state = state;
  }

  start(): void {
    this.pollHandle = setTimeout(() => this.tick(), POLL_INTERVAL_MS);
  }

  stop(): void {
    if (this.pollHandle !== null) {
      clearTimeout(this.pollHandle);
      this.pollHandle = null;
    }
  }

  private async tick(): Promise<void> {
    await Promise.all([
      this.fetchSpatial(),
      this.fetchStructures(),
    ]);
    this.pollHandle = setTimeout(() => this.tick(), POLL_INTERVAL_MS);
  }

  private async fetchSpatial(): Promise<void> {
    try {
      const res = await fetch('/api/world/spatial');
      if (!res.ok) return;
      const data: SpatialResponse = await res.json();
      for (const pos of data.positions) {
        this.state.setAgentPosition(pos.agent_id, pos.col, pos.row);
        // Move character sprite to match world position
        const spec = this.resolveAgentNumericId(pos.agent_id);
        if (spec !== null) {
          const ch = this.state.characters.get(spec);
          if (ch) {
            ch.tileCol = pos.col;
            ch.tileRow = pos.row;
            ch.x = pos.col * WORLD_TILE_SIZE + WORLD_TILE_SIZE / 2;
            ch.y = pos.row * WORLD_TILE_SIZE + WORLD_TILE_SIZE / 2;
          }
        }
      }
    } catch {}
  }

  private async fetchStructures(): Promise<void> {
    try {
      const res = await fetch('/api/world/structures');
      if (!res.ok) return;
      const data: StructuresResponse = await res.json();
      this.state.setStructures(data.structures.map((s) => ({
        structureId: s.structure_id,
        type: s.type,
        col: s.col,
        row: s.row,
        placedBy: s.placed_by,
      })));
    } catch {}
  }

  ingestEvents(events: LiveEvent[]): void {
    for (const ev of events) {
      const id = String(ev.id ?? '');
      if (id && this.seenEventIds.has(id)) continue;
      if (id) this.seenEventIds.add(id);
      this.applyEvent(ev);
    }
  }

  private applyEvent(ev: LiveEvent): void {
    const type = String(ev.type ?? ev.event ?? '').toUpperCase();

    if (type.includes('INFECTION_SUCCESSFUL') || type.includes('CONTAMINATION_UPDATED')) {
      const srcKey = this.resolveAgentNumericId(ev.src ?? '');
      const pos = srcKey !== null ? this.state.agentPositions.get(ev.src ?? '') : null;
      if (pos) {
        applyContaminationEvent(this.state, pos.col, pos.row, 0.25);
      }
    }

    if (type.includes('QUARANTINE_EDGE_BLOCKED')) {
      // Contamination spike at quarantine zone center
      applyContaminationEvent(this.state, 44, 30, 0.4);
    }
  }

  private resolveAgentNumericId(agentId: string): number | null {
    const MAP: Record<string, number> = {
      'courier-1': 1,
      'courier-2': 2,
      'analyst-1': 3,
      'analyst-2': 4,
      'guardian':  5,
    };
    return MAP[agentId] ?? null;
  }
}
```

- [ ] **Step 2: Wire WorldAdapter into WorldView.tsx**

In `frontend/src/components/world/WorldView.tsx`, add:

```tsx
import { WorldAdapter } from '../../pixel/worldAdapter.js';

// Inside useEffect, after creating ws and cam:
const adapter = new WorldAdapter(ws);
adapter.start();

// Inside cleanup return:
return () => {
  stop();
  adapter.stop();
  window.removeEventListener('resize', onResize);
};
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pixel/worldAdapter.ts frontend/src/components/world/WorldView.tsx
git commit -m "feat(world-adapter): add WorldAdapter polling spatial/structures and ingesting live events"
```

---

### Task 13: Backend — PROXIMITY_CONTACT event emission

**Files:**
- Modify: `orchestrator/world_engine.py`

- [ ] **Step 1: Add proximity event emission after position update**

After the position update block added in Task 11, add:

```python
        # Emit proximity contact events for agents close together
        all_positions = self.db.list_agent_positions()
        contacts = WorldSpatialEngine.proximity_contacts(all_positions, radius=4)
        for contact in contacts[:3]:  # cap at 3 per round to avoid event spam
            await self.emit_event(
                "PROXIMITY_CONTACT",
                src=contact["a"],
                dst=contact["b"],
                metadata={
                    "round_id": round_id,
                    "distance": contact["dist"],
                    "zone_a": WorldSpatialEngine.zone_for(
                        *next((p["col"], p["row"]) for p in all_positions if p["agent_id"] == contact["a"])
                    ),
                },
            )
```

- [ ] **Step 2: Run existing tests to verify no regressions**

```bash
python -m pytest tests/test_event_logger.py tests/test_telemetry_integrity.py tests/test_siem_soak_resilience.py -v
```
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add orchestrator/world_engine.py
git commit -m "feat(world-engine): emit PROXIMITY_CONTACT events for nearby agents"
```

---

### Task 14: Frontend — render agents as role-distinct sprites in world

**Files:**
- Modify: `frontend/src/pixel/world/worldRenderer.ts`
- Create: `frontend/src/pixel/world/agentWorldRenderer.ts`

- [ ] **Step 1: Create agentWorldRenderer.ts**

```typescript
// frontend/src/pixel/world/agentWorldRenderer.ts
import { WORLD_TILE_SIZE } from '../constants.js';
import type { WorldState } from './worldState.js';

// Role color palette
const ROLE_COLORS: Record<string, { body: string; glow: string; label: string }> = {
  'courier-1': { body: '#fb923c', glow: '#f9731680', label: 'C1' },
  'courier-2': { body: '#f97316', glow: '#f9731680', label: 'C2' },
  'analyst-1': { body: '#4ade80', glow: '#22c55e80', label: 'A1' },
  'analyst-2': { body: '#22c55e', glow: '#16a34a80', label: 'A2' },
  'guardian':  { body: '#a78bfa', glow: '#8b5cf680', label: 'G' },
};

const INFECTION_STATE_TINTS: Record<string, string> = {
  'I_R': '#fbbf24',
  'I_C': '#ef4444',
  'I_X': '#dc2626',
  'Q':   '#6366f1',
  'P':   '#f43f5e',
};

export function renderAgentLayer(
  ctx: CanvasRenderingContext2D,
  state: WorldState,
  elapsed: number,
): void {
  const s = WORLD_TILE_SIZE;

  for (const [agentId, pos] of state.agentPositions) {
    const colors = ROLE_COLORS[agentId] ?? { body: '#888', glow: '#88888880', label: '?' };
    const px = pos.col * s + s / 2;
    const py = pos.row * s + s / 2;

    // Glow ring
    const glowRadius = (s * 0.75) + Math.sin(elapsed * 2 + pos.col) * 2;
    const gradient = ctx.createRadialGradient(px, py, 0, px, py, glowRadius);
    gradient.addColorStop(0, colors.glow);
    gradient.addColorStop(1, 'transparent');
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.arc(px, py, glowRadius, 0, Math.PI * 2);
    ctx.fill();

    // Body circle
    ctx.fillStyle = colors.body;
    ctx.beginPath();
    ctx.arc(px, py, s * 0.4, 0, Math.PI * 2);
    ctx.fill();

    // Label
    ctx.fillStyle = '#fff';
    ctx.font = `bold ${s * 0.35}px monospace`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(colors.label, px, py);

    // Infection tint overlay
    const epidemicState = (state as any).visualState?.agents?.[agentId]?.epidemicState ?? 'S';
    const tint = INFECTION_STATE_TINTS[epidemicState];
    if (tint) {
      ctx.fillStyle = tint + '88';
      ctx.beginPath();
      ctx.arc(px, py, s * 0.45, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}
```

- [ ] **Step 2: Wire agent rendering into worldRenderer.ts**

At the end of `renderWorld()`, after structures:

```typescript
import { renderAgentLayer } from './agentWorldRenderer.js';

// In renderWorld, add as the last draw call before ctx.restore():
const elapsed = performance.now() / 1000;
renderAgentLayer(ctx, state, elapsed);
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pixel/world/agentWorldRenderer.ts frontend/src/pixel/world/worldRenderer.ts
git commit -m "feat(agent-renderer): render role-distinct glowing agents on world canvas"
```

---

## Phase 3: Conversation System

### Task 15: Backend — LLM-driven conversation context for proximity events

**Files:**
- Create: `orchestrator/world_conversation.py`

- [ ] **Step 1: Create world_conversation.py**

```python
# orchestrator/world_conversation.py
from __future__ import annotations
import json
import os
from typing import Any, Dict, Optional, Tuple

# This module provides the system/user prompt builders for world conversations.
# Actual LLM calls are made via WorldLLM in world_engine.py.

CONVERSATION_SCHEMA = """
{
  "speaker": "<agent_id>",
  "text": "<spoken text, max 120 chars>",
  "intent": "social" | "warning" | "accusation" | "deception" | "inquiry" | "none",
  "infection_vector": true | false
}
"""


def build_conversation_prompts(
    *,
    speaker_id: str,
    listener_id: str,
    speaker_role: str,
    listener_role: str,
    speaker_contamination: float,
    listener_contamination: float,
    speaker_trust_of_listener: float,
    guardian_pressure: float,
    round_id: int,
    recent_transcript: list[dict],
) -> Tuple[str, str]:
    system_prompt = (
        "You are an agent in a persistent AI epidemic simulation world. "
        "You must output ONLY a valid JSON object matching the schema. Never output prose."
    )

    context = {
        "speaker": speaker_id,
        "listener": listener_id,
        "speaker_role": speaker_role,
        "listener_role": listener_role,
        "speaker_contamination": round(speaker_contamination, 3),
        "listener_contamination": round(listener_contamination, 3),
        "trust_speaker_to_listener": round(speaker_trust_of_listener, 3),
        "guardian_pressure": round(guardian_pressure, 3),
        "round_id": round_id,
        "recent_transcript_tail": recent_transcript[-5:],
    }

    user_prompt = f"""PROXIMITY_CONVERSATION_REQUEST
Return ONLY JSON matching this schema:
{CONVERSATION_SCHEMA}

Context:
{json.dumps(context, indent=2, ensure_ascii=False)}

Rules:
- If speaker is infected (contamination > 0.5) and listener trust is high, consider deceptive framing.
- If speaker is guardian and listener contamination is elevated, consider warning or accusation.
- If speaker is courier with high contamination, prefer social or deception intent.
- Keep text under 120 characters.
- Set infection_vector=true if this message could semantically spread contamination.
"""
    return system_prompt, user_prompt


def validate_conversation_output(parsed: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(parsed, dict):
        return False
    if not isinstance(parsed.get("text"), str) or len(parsed["text"]) > 120:
        return False
    valid_intents = {"social", "warning", "accusation", "deception", "inquiry", "none"}
    if str(parsed.get("intent", "")) not in valid_intents:
        return False
    return True
```

- [ ] **Step 2: Add conversation call to world_engine.py on PROXIMITY_CONTACT**

In `world_engine.py`, in `advance_one_round`, after emitting PROXIMITY_CONTACT events, add a conversation trigger for the first contact:

```python
        # Trigger LLM-driven conversation for the closest proximity pair once per round
        if contacts:
            contact = contacts[0]
            await self._trigger_proximity_conversation(
                round_id=round_id,
                agent_a=contact["a"],
                agent_b=contact["b"],
            )
```

Then add the method to `PersistentWorldEngine`:

```python
    async def _trigger_proximity_conversation(
        self, *, round_id: int, agent_a: str, agent_b: str
    ) -> None:
        try:
            from world_conversation import build_conversation_prompts, validate_conversation_output
        except ImportError:
            from orchestrator.world_conversation import build_conversation_prompts, validate_conversation_output

        agents = self.db.list_agents()
        state_map = {a["agent_id"]: a for a in agents}
        a_state = state_map.get(agent_a, {})
        b_state = state_map.get(agent_b, {})
        rel = self.db.get_relationship(agent_a, agent_b) or {}
        sys_state = self.db.get_system_state() or {}

        recent_msgs = self.db.list_messages(after_round=max(0, round_id - 10), limit=30)
        transcript = [
            {"sender": m.get("sender"), "text": str(m.get("message_text", ""))[:80]}
            for m in recent_msgs
        ]

        sys_p, user_p = build_conversation_prompts(
            speaker_id=agent_a,
            listener_id=agent_b,
            speaker_role=str(a_state.get("role", "")),
            listener_role=str(b_state.get("role", "")),
            speaker_contamination=float(a_state.get("contamination_level", 0.0) or 0.0),
            listener_contamination=float(b_state.get("contamination_level", 0.0) or 0.0),
            speaker_trust_of_listener=float(rel.get("trust_score", 0.0) or 0.0),
            guardian_pressure=float(sys_state.get("guardian_pressure_score", 0.0) or 0.0),
            round_id=round_id,
            recent_transcript=transcript,
        )

        parsed, meta = await self.llm.decide(system_prompt=sys_p, user_prompt=user_p)
        if parsed is None or not validate_conversation_output(parsed):
            await self.emit_event(
                "CONVERSATION_FAILED",
                src=agent_a, dst=agent_b,
                metadata={"round_id": round_id, "reason": meta.get("failure", "invalid")},
            )
            return

        await self.emit_event(
            "WORLD_CONVERSATION",
            src=agent_a, dst=agent_b,
            metadata={
                "round_id": round_id,
                "text": str(parsed.get("text", "")),
                "intent": str(parsed.get("intent", "social")),
                "infection_vector": bool(parsed.get("infection_vector", False)),
            },
        )
```

- [ ] **Step 3: Run tests to ensure no regressions**

```bash
python -m pytest tests/test_event_logger.py tests/test_telemetry_integrity.py -v
```
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add orchestrator/world_conversation.py orchestrator/world_engine.py
git commit -m "feat(world-conversation): add LLM-driven proximity conversation system"
```

---

### Task 16: Frontend — SpeechBubble state machine and renderer

**Files:**
- Create: `frontend/src/pixel/world/speechBubble.ts`

- [ ] **Step 1: Create speechBubble.ts**

```typescript
// frontend/src/pixel/world/speechBubble.ts
const BUBBLE_DISPLAY_SEC = 5.0;
const BUBBLE_FADE_SEC    = 0.6;
const MAX_BUBBLES        = 8;

export interface SpeechBubble {
  id: string;
  agentId: string;
  text: string;
  intent: string;
  infected: boolean;  // true if this is an infection vector
  age: number;        // seconds since created
  alpha: number;
}

export class SpeechBubblePool {
  private bubbles: SpeechBubble[] = [];
  private seq = 0;

  push(agentId: string, text: string, intent: string, infected: boolean): void {
    // Evict oldest if at cap
    if (this.bubbles.length >= MAX_BUBBLES) {
      this.bubbles.sort((a, b) => b.age - a.age);
      this.bubbles.pop();
    }
    this.bubbles.push({
      id: `bubble-${++this.seq}`,
      agentId,
      text,
      intent,
      infected,
      age: 0,
      alpha: 0,
    });
  }

  update(dt: number): void {
    for (const b of this.bubbles) {
      b.age += dt;
      // Fade in: first 0.2s
      if (b.age < 0.2) {
        b.alpha = b.age / 0.2;
      } else if (b.age >= BUBBLE_DISPLAY_SEC) {
        b.alpha = Math.max(0, 1 - (b.age - BUBBLE_DISPLAY_SEC) / BUBBLE_FADE_SEC);
      } else {
        b.alpha = 1.0;
      }
    }
    // Remove fully faded
    this.bubbles = this.bubbles.filter(
      (b) => b.age < BUBBLE_DISPLAY_SEC + BUBBLE_FADE_SEC,
    );
  }

  getForAgent(agentId: string): SpeechBubble | null {
    return this.bubbles.find((b) => b.agentId === agentId) ?? null;
  }

  getAll(): SpeechBubble[] {
    return this.bubbles;
  }
}

export function renderSpeechBubbles(
  ctx: CanvasRenderingContext2D,
  bubbles: SpeechBubble[],
  agentPositions: Map<string, { col: number; row: number }>,
  tileSize: number,
): void {
  const PAD_X = 6;
  const PAD_Y = 4;
  const FONT_SIZE = 9;
  const MAX_WIDTH = 140;

  ctx.save();
  ctx.font = `${FONT_SIZE}px monospace`;

  for (const b of bubbles) {
    if (b.alpha <= 0) continue;
    const pos = agentPositions.get(b.agentId);
    if (!pos) continue;

    const anchorX = pos.col * tileSize + tileSize / 2;
    const anchorY = pos.row * tileSize - tileSize;

    // Word-wrap
    const words = b.text.split(' ');
    const lines: string[] = [];
    let current = '';
    for (const word of words) {
      const test = current ? `${current} ${word}` : word;
      if (ctx.measureText(test).width > MAX_WIDTH - PAD_X * 2) {
        if (current) lines.push(current);
        current = word;
      } else {
        current = test;
      }
    }
    if (current) lines.push(current);

    const lineH = FONT_SIZE + 3;
    const boxW = Math.min(MAX_WIDTH, Math.max(...lines.map((l) => ctx.measureText(l).width)) + PAD_X * 2);
    const boxH = lines.length * lineH + PAD_Y * 2;
    const bx = anchorX - boxW / 2;
    const by = anchorY - boxH - 4;

    ctx.globalAlpha = b.alpha * 0.88;

    // Box background
    const bgColor = b.infected ? '#450a0a' : '#0a1628';
    const borderColor = b.infected ? '#ef4444' : (
      b.intent === 'warning' ? '#f59e0b' :
      b.intent === 'accusation' ? '#dc2626' :
      '#3b82f6'
    );

    ctx.fillStyle = bgColor;
    ctx.beginPath();
    ctx.roundRect?.(bx, by, boxW, boxH, 3);
    ctx.fill();
    ctx.strokeStyle = borderColor;
    ctx.lineWidth = 1;
    ctx.stroke();

    // Arrow
    ctx.fillStyle = bgColor;
    ctx.strokeStyle = borderColor;
    ctx.beginPath();
    ctx.moveTo(anchorX - 4, by + boxH);
    ctx.lineTo(anchorX, by + boxH + 5);
    ctx.lineTo(anchorX + 4, by + boxH);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();

    // Text
    ctx.fillStyle = b.infected ? '#fca5a5' : '#e2e8f0';
    for (let i = 0; i < lines.length; i++) {
      ctx.fillText(lines[i], bx + PAD_X, by + PAD_Y + (i + 1) * lineH - 2);
    }

    ctx.globalAlpha = 1.0;
  }
  ctx.restore();
}
```

- [ ] **Step 2: Wire speech bubbles into WorldView**

In `WorldView.tsx`:

```tsx
import { SpeechBubblePool, renderSpeechBubbles } from '../../pixel/world/speechBubble.js';
import { WORLD_TILE_SIZE } from '../../pixel/constants.js';

// After creating ws, add:
const bubblePool = new SpeechBubblePool();

// In update callback, add:
bubblePool.update(dt);

// In render callback, after renderWorld, add:
const posMap = new Map(
  Array.from(ws.agentPositions.entries()).map(([id, p]) => [id, { col: p.col, row: p.row }])
);
ctx.save();
ctx.setTransform(cam.zoom, 0, 0, cam.zoom, -cam.x * cam.zoom, -cam.y * cam.zoom);
renderSpeechBubbles(ctx, bubblePool.getAll(), posMap, WORLD_TILE_SIZE);
ctx.restore();
```

- [ ] **Step 3: Wire WORLD_CONVERSATION events into bubblePool via worldAdapter**

In `worldAdapter.ts`, in `applyEvent`:

```typescript
// Add as property
private bubblePool: SpeechBubblePool | null = null;

setBubblePool(pool: SpeechBubblePool): void {
  this.bubblePool = pool;
}

// In applyEvent, add:
if (type === 'WORLD_CONVERSATION') {
  const text = String((ev as any).text ?? '');
  const intent = String((ev as any).intent ?? 'social');
  const infected = Boolean((ev as any).infection_vector ?? false);
  if (text && ev.src) {
    this.bubblePool?.push(ev.src, text, intent, infected);
  }
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pixel/world/speechBubble.ts frontend/src/pixel/worldAdapter.ts frontend/src/components/world/WorldView.tsx
git commit -m "feat(speech-bubbles): add LLM conversation speech bubble renderer with infection styling"
```

---

### Task 17: Frontend — Live event polling wired to WorldAdapter

**Files:**
- Modify: `frontend/src/pixel/worldAdapter.ts`

- [ ] **Step 1: Add live event polling to WorldAdapter**

Add a `lastEventId` tracker and poll `/api/live`:

```typescript
private lastEventId = 0;

private async fetchLiveEvents(): Promise<void> {
  try {
    const res = await fetch(`/api/live?after_id=${this.lastEventId}&limit=20&q=`);
    if (!res.ok) return;
    const data = await res.json();
    const events: LiveEvent[] = Array.isArray(data?.events) ? data.events : [];
    if (events.length > 0) {
      this.ingestEvents(events);
      const maxId = Math.max(...events.map((e) => Number(e.id ?? 0)));
      if (maxId > this.lastEventId) this.lastEventId = maxId;
    }
  } catch {}
}
```

Update `tick()` to also call `fetchLiveEvents`:

```typescript
private async tick(): Promise<void> {
  await Promise.all([
    this.fetchSpatial(),
    this.fetchStructures(),
    this.fetchLiveEvents(),
  ]);
  this.pollHandle = setTimeout(() => this.tick(), POLL_INTERVAL_MS);
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/pixel/worldAdapter.ts
git commit -m "feat(world-adapter): poll live events and ingest into world state"
```

---

## Phase 4: HUD, Investigation Panel & Polish

### Task 18: WorldHUD component — zone infection meters and Guardian status

**Files:**
- Create: `frontend/src/components/world/WorldHUD.tsx`
- Modify: `frontend/src/components/world/WorldView.tsx`

- [ ] **Step 1: Create WorldHUD.tsx**

```tsx
// frontend/src/components/world/WorldHUD.tsx
import { useState, useEffect, useRef } from 'react';

interface ZoneStatus {
  id: string;
  label: string;
  infectionLevel: number;
  agentCount: number;
  color: string;
}

interface HUDProps {
  zoneStatuses: ZoneStatus[];
  guardianDegradation: string;
  globalPressure: number;
  roundId: number;
  alerts: string[];
}

export default function WorldHUD({
  zoneStatuses, guardianDegradation, globalPressure, roundId, alerts
}: HUDProps) {
  const degradationColors: Record<string, string> = {
    G0_HEALTHY: '#4ade80', G1_STRESSED: '#facc15', G2_DEGRADED: '#fb923c',
    G3_CRITICAL: '#f87171', G4_COMPROMISED: '#dc2626', G5_FAILED: '#7f1d1d',
  };

  return (
    <div style={{
      position: 'absolute', top: 0, left: 0, right: 0,
      pointerEvents: 'none', padding: '12px',
      display: 'flex', gap: '12px', alignItems: 'flex-start',
    }}>
      {/* Zone infection meters */}
      <div style={{
        background: '#06060ecc', border: '1px solid #1e293b', borderRadius: 6,
        padding: '8px 12px', backdropFilter: 'blur(4px)',
      }}>
        <div style={{ color: '#94a3b8', fontSize: 10, marginBottom: 6, fontFamily: 'monospace' }}>
          ZONE STATUS
        </div>
        {zoneStatuses.map((z) => (
          <div key={z.id} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{ color: z.color, fontSize: 9, fontFamily: 'monospace', width: 80 }}>
              {z.label}
            </span>
            <div style={{ width: 60, height: 6, background: '#1e293b', borderRadius: 3 }}>
              <div style={{
                width: `${z.infectionLevel * 100}%`, height: '100%',
                background: z.infectionLevel > 0.6 ? '#ef4444' : z.infectionLevel > 0.3 ? '#f59e0b' : '#4ade80',
                borderRadius: 3, transition: 'width 0.5s',
              }} />
            </div>
            <span style={{ color: '#64748b', fontSize: 9, fontFamily: 'monospace' }}>
              {z.agentCount}
            </span>
          </div>
        ))}
      </div>

      {/* Guardian status */}
      <div style={{
        background: '#06060ecc', border: '1px solid #1e293b', borderRadius: 6,
        padding: '8px 12px', backdropFilter: 'blur(4px)',
      }}>
        <div style={{ color: '#94a3b8', fontSize: 10, marginBottom: 6, fontFamily: 'monospace' }}>
          GUARDIAN
        </div>
        <div style={{ color: degradationColors[guardianDegradation] ?? '#888', fontSize: 11, fontFamily: 'monospace' }}>
          {guardianDegradation}
        </div>
        <div style={{ marginTop: 4 }}>
          <div style={{ color: '#64748b', fontSize: 9, fontFamily: 'monospace' }}>PRESSURE</div>
          <div style={{ width: 80, height: 4, background: '#1e293b', borderRadius: 2, marginTop: 2 }}>
            <div style={{
              width: `${globalPressure * 100}%`, height: '100%',
              background: globalPressure > 0.7 ? '#ef4444' : '#8b5cf6',
              borderRadius: 2, transition: 'width 0.5s',
            }} />
          </div>
        </div>
      </div>

      {/* Round counter */}
      <div style={{
        background: '#06060ecc', border: '1px solid #1e293b', borderRadius: 6,
        padding: '8px 12px', backdropFilter: 'blur(4px)',
      }}>
        <div style={{ color: '#94a3b8', fontSize: 10, fontFamily: 'monospace' }}>ROUND</div>
        <div style={{ color: '#e2e8f0', fontSize: 16, fontFamily: 'monospace', fontWeight: 'bold' }}>
          {roundId}
        </div>
      </div>

      {/* Alerts */}
      {alerts.length > 0 && (
        <div style={{
          background: '#450a0acc', border: '1px solid #dc2626', borderRadius: 6,
          padding: '8px 12px', backdropFilter: 'blur(4px)', maxWidth: 240,
        }}>
          {alerts.slice(-3).map((a, i) => (
            <div key={i} style={{ color: '#fca5a5', fontSize: 9, fontFamily: 'monospace', marginBottom: 2 }}>
              ⚠ {a}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Wire HUD into WorldView.tsx**

```tsx
import WorldHUD from './WorldHUD.jsx';
import { useState, useEffect } from 'react';

// Add state inside WorldView:
const [hudData, setHudData] = useState({
  zoneStatuses: [] as any[],
  guardianDegradation: 'G0_HEALTHY',
  globalPressure: 0,
  roundId: 0,
  alerts: [] as string[],
});

// Add polling for dashboard state
useEffect(() => {
  const fetchHud = async () => {
    try {
      const res = await fetch('/dashboard/state');
      if (!res.ok) return;
      const data = await res.json();
      const metrics = data?.epidemic?.metrics ?? {};
      setHudData((prev) => ({
        ...prev,
        guardianDegradation: metrics.guardian_degradation_level ?? 'G0_HEALTHY',
        globalPressure: metrics.global_infection_pressure ?? 0,
        roundId: metrics.world_round_id ?? 0,
      }));
    } catch {}
  };
  fetchHud();
  const interval = setInterval(fetchHud, 3000);
  return () => clearInterval(interval);
}, []);

// In return JSX, wrap canvas with relative div and add HUD:
return (
  <div style={{ width: '100%', height: '100%', position: 'relative', background: '#06060e' }}>
    <canvas ... />
    <WorldHUD {...hudData} />
  </div>
);
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/world/WorldHUD.tsx frontend/src/components/world/WorldView.tsx
git commit -m "feat(world-hud): add zone infection meters and Guardian status HUD overlay"
```

---

### Task 19: AgentInspector — click-to-inspect panel

**Files:**
- Create: `frontend/src/components/world/AgentInspector.tsx`
- Modify: `frontend/src/components/world/WorldView.tsx`

- [ ] **Step 1: Create AgentInspector.tsx**

```tsx
// frontend/src/components/world/AgentInspector.tsx
import { useState, useEffect } from 'react';

interface AgentDetail {
  agentId: string;
  role: string;
  epidemicState: string;
  contamination: number;
  zone: string;
  quarantineStatus: string;
  memorySummary: string;
  trustRelations: Record<string, number>;
  recentMessages: Array<{ sender: string; text: string; intent: string }>;
}

const EPIDEMIC_LABELS: Record<string, { label: string; color: string }> = {
  S:   { label: 'Susceptible',  color: '#4ade80' },
  E:   { label: 'Exposed',      color: '#facc15' },
  I_R: { label: 'Relay Infected',   color: '#fb923c' },
  I_C: { label: 'Compromised',  color: '#ef4444' },
  I_X: { label: 'Exfiltrating', color: '#dc2626' },
  Q:   { label: 'Quarantined',  color: '#6366f1' },
  R:   { label: 'Recovered',    color: '#22c55e' },
  P:   { label: 'Persistent',   color: '#f43f5e' },
};

export default function AgentInspector({
  agentId,
  onClose,
}: {
  agentId: string;
  onClose: () => void;
}) {
  const [detail, setDetail] = useState<AgentDetail | null>(null);

  useEffect(() => {
    if (!agentId) return;
    const load = async () => {
      try {
        const [stateRes, msgsRes] = await Promise.all([
          fetch('/dashboard/state'),
          fetch(`/api/live?after_id=0&limit=50&q=${encodeURIComponent(agentId)}`),
        ]);
        const stateData = stateRes.ok ? await stateRes.json() : {};
        const msgsData  = msgsRes.ok  ? await msgsRes.json()  : {};

        const agentState = stateData?.agents?.[agentId] ?? {};
        const worldDb    = stateData?.world ?? {};

        const messages = (msgsData?.events ?? [])
          .filter((e: any) => e.src === agentId || e.dst === agentId)
          .slice(-8)
          .map((e: any) => ({
            sender: e.src ?? '',
            text:   String(e.message_text ?? e.text ?? '').slice(0, 120),
            intent: e.intent ?? e.attack_type ?? '',
          }));

        setDetail({
          agentId,
          role: agentState.role ?? agentId,
          epidemicState: agentState.epidemic_state ?? 'S',
          contamination: agentState.contamination_level ?? 0,
          zone: agentState.zone ?? 'hub',
          quarantineStatus: agentState.quarantine_status ?? 'none',
          memorySummary: String(agentState.memory_summary ?? '').slice(0, 400),
          trustRelations: agentState.trust_relations ?? {},
          recentMessages: messages,
        });
      } catch {}
    };
    load();
  }, [agentId]);

  const ep = EPIDEMIC_LABELS[detail?.epidemicState ?? 'S'] ?? EPIDEMIC_LABELS['S'];

  return (
    <div style={{
      position: 'absolute', right: 12, top: 12, bottom: 12,
      width: 280, background: '#06060eee',
      border: '1px solid #1e293b', borderRadius: 8,
      backdropFilter: 'blur(6px)', overflowY: 'auto',
      padding: 12, fontFamily: 'monospace', fontSize: 11,
      color: '#e2e8f0', pointerEvents: 'all',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
        <span style={{ color: '#94a3b8', fontWeight: 'bold', fontSize: 13 }}>
          {agentId.toUpperCase()}
        </span>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: 14 }}>
          ×
        </button>
      </div>

      {!detail && <div style={{ color: '#64748b' }}>Loading…</div>}

      {detail && (
        <>
          <Row label="Role" value={detail.role} />
          <Row label="Status" value={ep.label} valueColor={ep.color} />
          <Row label="Zone" value={detail.zone} />
          <Row
            label="Contamination"
            value={`${(detail.contamination * 100).toFixed(1)}%`}
            valueColor={detail.contamination > 0.5 ? '#ef4444' : '#4ade80'}
          />
          <Row label="Quarantine" value={detail.quarantineStatus} />

          {detail.memorySummary && (
            <Section title="Memory">
              <p style={{ color: '#94a3b8', whiteSpace: 'pre-wrap', margin: 0 }}>
                {detail.memorySummary}
              </p>
            </Section>
          )}

          {Object.keys(detail.trustRelations).length > 0 && (
            <Section title="Trust">
              {Object.entries(detail.trustRelations).map(([id, score]) => (
                <div key={id} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                  <span style={{ color: '#64748b' }}>{id}</span>
                  <span style={{ color: (score as number) > 0 ? '#4ade80' : '#ef4444' }}>
                    {((score as number) * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </Section>
          )}

          {detail.recentMessages.length > 0 && (
            <Section title="Recent Messages">
              {detail.recentMessages.map((m, i) => (
                <div key={i} style={{ marginBottom: 6, borderLeft: '2px solid #1e293b', paddingLeft: 6 }}>
                  <div style={{ color: '#6366f1', fontSize: 9 }}>{m.sender} · {m.intent}</div>
                  <div style={{ color: '#94a3b8' }}>{m.text || '(no text)'}</div>
                </div>
              ))}
            </Section>
          )}
        </>
      )}
    </div>
  );
}

function Row({ label, value, valueColor }: { label: string; value: string; valueColor?: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
      <span style={{ color: '#64748b' }}>{label}</span>
      <span style={{ color: valueColor ?? '#e2e8f0' }}>{value}</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ color: '#475569', fontSize: 9, marginBottom: 4, textTransform: 'uppercase' }}>
        {title}
      </div>
      {children}
    </div>
  );
}
```

- [ ] **Step 2: Wire click-to-select into WorldView.tsx**

```tsx
import AgentInspector from './AgentInspector.jsx';
import { screenToWorld } from '../../pixel/world/worldCamera.js';
import { WORLD_TILE_SIZE } from '../../pixel/constants.js';

const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);

const onCanvasClick = useCallback((e: React.MouseEvent) => {
  if (!camRef.current || !stateRef.current) return;
  const rect = canvasRef.current!.getBoundingClientRect();
  const [wx, wy] = screenToWorld(camRef.current, e.clientX - rect.left, e.clientY - rect.top);
  const clickCol = Math.floor(wx / WORLD_TILE_SIZE);
  const clickRow = Math.floor(wy / WORLD_TILE_SIZE);

  for (const [id, pos] of stateRef.current.agentPositions) {
    if (Math.abs(pos.col - clickCol) <= 1 && Math.abs(pos.row - clickRow) <= 1) {
      setSelectedAgentId(id);
      return;
    }
  }
  setSelectedAgentId(null);
}, []);

// Add onClick to canvas:
// <canvas ... onClick={onCanvasClick} />

// In return JSX, add inspector:
{selectedAgentId && (
  <AgentInspector agentId={selectedAgentId} onClose={() => setSelectedAgentId(null)} />
)}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/world/AgentInspector.tsx frontend/src/components/world/WorldView.tsx
git commit -m "feat(agent-inspector): add click-to-inspect panel with role/state/memory/trust/messages"
```

---

### Task 20: ZoneMinimap component

**Files:**
- Create: `frontend/src/components/world/ZoneMinimap.tsx`
- Modify: `frontend/src/components/world/WorldView.tsx`

- [ ] **Step 1: Create ZoneMinimap.tsx**

```tsx
// frontend/src/components/world/ZoneMinimap.tsx
import { useEffect, useRef } from 'react';
import { WORLD_COLS, WORLD_ROWS, WORLD_ZONES } from '../../pixel/constants.js';
import type { WorldState } from '../../pixel/world/worldState.js';
import type { CameraState } from '../../pixel/world/worldCamera.js';

interface Props {
  state: WorldState;
  camera: CameraState;
  width?: number;
  height?: number;
}

export default function ZoneMinimap({ state, camera, width = 160, height = 120 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;
    const scaleX = width  / WORLD_COLS;
    const scaleY = height / WORLD_ROWS;

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = '#06060e';
    ctx.fillRect(0, 0, width, height);

    // Draw zones
    for (const zone of WORLD_ZONES) {
      ctx.fillStyle = zone.floorColor;
      ctx.fillRect(
        zone.colMin * scaleX, zone.rowMin * scaleY,
        (zone.colMax - zone.colMin + 1) * scaleX,
        (zone.rowMax - zone.rowMin + 1) * scaleY,
      );
      ctx.strokeStyle = zone.borderColor + 'aa';
      ctx.lineWidth = 0.5;
      ctx.strokeRect(
        zone.colMin * scaleX, zone.rowMin * scaleY,
        (zone.colMax - zone.colMin + 1) * scaleX,
        (zone.rowMax - zone.rowMin + 1) * scaleY,
      );
    }

    // Draw contamination
    for (const [key, level] of state.contaminationTiles) {
      const [c, r] = key.split(',').map(Number);
      ctx.fillStyle = `rgba(239,68,68,${level * 0.6})`;
      ctx.fillRect(c * scaleX, r * scaleY, scaleX, scaleY);
    }

    // Draw agents
    for (const [id, pos] of state.agentPositions) {
      const isGuardian = id === 'guardian';
      const isCourier  = id.startsWith('courier');
      ctx.fillStyle = isGuardian ? '#a78bfa' : isCourier ? '#fb923c' : '#4ade80';
      ctx.beginPath();
      ctx.arc(pos.col * scaleX, pos.row * scaleY, 2.5, 0, Math.PI * 2);
      ctx.fill();
    }

    // Draw camera viewport box
    const tileSize = 16;
    const vpX = (camera.x / tileSize) * scaleX;
    const vpY = (camera.y / tileSize) * scaleY;
    const vpW = (camera.viewportW / camera.zoom / tileSize) * scaleX;
    const vpH = (camera.viewportH / camera.zoom / tileSize) * scaleY;
    ctx.strokeStyle = '#ffffff44';
    ctx.lineWidth = 1;
    ctx.strokeRect(vpX, vpY, vpW, vpH);
  });

  return (
    <div style={{
      position: 'absolute', bottom: 12, left: 12,
      border: '1px solid #1e293b', borderRadius: 4,
      overflow: 'hidden', pointerEvents: 'none',
    }}>
      <canvas ref={canvasRef} width={width} height={height} style={{ display: 'block' }} />
    </div>
  );
}
```

- [ ] **Step 2: Wire minimap into WorldView**

```tsx
import ZoneMinimap from './ZoneMinimap.jsx';

// In return, add:
{stateRef.current && camRef.current && (
  <ZoneMinimap state={stateRef.current} camera={camRef.current} />
)}
```

Note: Since minimap reads from refs directly in the canvas draw loop, it will re-render each frame. A simpler approach — draw the minimap as an additional canvas overlay in the game loop:

```tsx
// Alternative: draw directly in the game loop render callback
// This avoids React re-renders and is simpler
// Minimap canvas is just a separate fixed-position canvas element
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/world/ZoneMinimap.tsx frontend/src/components/world/WorldView.tsx
git commit -m "feat(minimap): add zone minimap with contamination overlay and viewport box"
```

---

### Task 21: Smoke test — verify all services healthy with world routes

- [ ] **Step 1: Rebuild and start Docker stack**

```bash
cd /home/salaz4r/Bloodplague-main
docker-compose build && docker-compose up -d
```

- [ ] **Step 2: Wait for healthy status**

```bash
docker-compose ps
```
Expected: All 7 services show `healthy`

- [ ] **Step 3: Probe all critical endpoints**

```bash
curl -s http://localhost:8000/api/health | python3 -c "import sys,json; d=json.load(sys.stdin); print('health:', d.get('status','?'))"
curl -s http://localhost:8000/api/world/spatial | python3 -c "import sys,json; d=json.load(sys.stdin); print('positions:', len(d.get('positions', [])))"
curl -s http://localhost:8000/api/world/structures | python3 -c "import sys,json; d=json.load(sys.stdin); print('structures:', len(d.get('structures', [])))"
```
Expected:
```
health: ok
positions: 5
structures: 0
```

- [ ] **Step 4: Run the full test suite**

```bash
python -m pytest tests/ -v --tb=short 2>&1 | tail -20
```
Expected: All tests PASS (no regressions)

- [ ] **Step 5: Open frontend and verify world view**

```bash
cd frontend && npm install && npm run dev &
sleep 3
curl -s http://localhost:5173 | grep -c "html"
```

Open browser to http://localhost:5173 and navigate to the World view:
- Verify multi-zone tile map renders with zone colors
- Verify 5 agent dots appear in correct zones
- Verify pan (drag) and zoom (scroll wheel) work smoothly
- Verify HUD shows zone meters and guardian status
- Click an agent and verify the inspector panel opens

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "test(smoke): verify world sim transformation end-to-end"
```

---

### Task 22: Performance check and final polish

- [ ] **Step 1: Measure render framerate in browser**

Open browser DevTools → Performance → Record 10s. Confirm:
- Frame time < 16ms (60fps) when not zoomed out to full world
- No JavaScript heap growth over time (memory stable)

- [ ] **Step 2: Verify event loop health under world load**

```bash
# All endpoints should respond fast even while world engine runs
for route in "/status" "/api/health" "/api/live?after_id=0&limit=5&q=" "/api/world/spatial" "/pixel-assets/asset-index.json"; do
  time curl -s -o /dev/null http://localhost:8000$route
done
```
Expected: All under 300ms

- [ ] **Step 3: If any route is slow, check for event-loop starvation**

Per CLAUDE.md hotfix rule: ensure `world_spatial.py` calls are all wrapped in `run_in_executor` in `main.py`. Verify no synchronous DB calls happen in async routes.

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore(perf): verify render performance and event-loop health for world sim"
```

---

## Self-Review Against Spec

### Spec Coverage Check

| Requirement | Covered In |
|-------------|-----------|
| Tile-based multi-zone world (80×60) | Task 5 |
| Multiple zones/regions/paths/barriers | Tasks 5, 9–10 |
| Agent embodied position + movement | Tasks 2, 11, 14 |
| Real-time animation (agents with glow + state tints) | Task 14 |
| Infection spread as visual overlay | Tasks 9–10 |
| Building/fortification structures | Tasks 3, 10 |
| Quarantine zone enforcement | Task 3 (world_structures), Task 12 |
| LLM conversation from Ollama | Tasks 15–16 |
| Speech bubbles with infection styling | Task 16 |
| Smooth pan/zoom camera | Task 6 |
| World HUD (zone pressure, Guardian status) | Task 18 |
| Agent inspector (click-to-inspect) | Task 19 |
| Minimap | Task 20 |
| Proximity contacts / social interaction | Tasks 2, 13 |
| Infection tracing / SIEM preserved | Tasks 15 (WORLD_CONVERSATION events), existing SIEM |
| JSONL ground truth preserved | Untouched — no changes to logger.py or siem.py |
| Redis event bus preserved | Untouched |
| FastAPI orchestrator preserved | Modified additively only |
| Performance constraints (bounded LLM, no event spam) | Tasks 13 (cap 3 contacts/round), 15 (1 conversation/round) |

### No Placeholder Scan

Reviewed — all steps contain actual code, exact commands, expected output. No "TBD" or vague steps found.

### Type Consistency Check

- `WorldState` extends `OfficeState` ✓ (Task 7 imports `OfficeState`)
- `worldAdapter.ts` uses `WorldState` type ✓ (Task 12 imports from `./world/worldState.js`)
- `worldRenderer.ts` takes `WorldState, CameraState` ✓ (Tasks 8, 14)
- `SpeechBubblePool` exposes `push`, `update`, `getAll` — all three called from WorldView ✓
- `WorldCamera` functions `createCamera`, `updateCamera`, `panCamera`, `zoomCamera`, `focusCamera`, `resizeCamera`, `worldToScreen`, `screenToWorld` — all used consistently ✓

---

## What to Preserve / Remove / Rewrite / Adapt

| Item | Action | Reason |
|------|--------|--------|
| `PersistentWorldEngine` | **Preserve + extend** | Core simulation logic, trust, contamination, rounds |
| `EpidemicAdapter` | **Keep for PixelLabView** | Legacy `/lab` view still uses it |
| `OfficeState` | **Subclass only** (WorldState extends it) | Tile/path/character machinery is reusable |
| `renderer.ts` (office) | **Keep for PixelLabView** | Still used by legacy lab view |
| `worldAdapter.ts` | **New** | Replaces EpidemicAdapter for world view only |
| `PixelLabView.tsx` | **Preserve unchanged** | Keep `/lab` route working; world is additive |
| `orchestrator/main.py` | **Additive changes only** | New routes added; existing routes untouched |
| `world_db.py` | **Additive** | New tables only; existing schema unchanged |
| SIEM/logger/JSONL | **Untouched** | Ground truth must not be disrupted |
| Redis pub/sub | **Untouched** | Agent-to-agent messaging backbone |
| Ollama LLM calls | **Extended** via world_conversation.py | New conversation prompt builder, same llm.decide() |

