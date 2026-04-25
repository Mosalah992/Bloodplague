# World-Sim Beautification + Rotatable Structures

**Date:** 2026-04-25  
**Status:** Approved  
**Scope:** `frontend/src/pixel/world/`, `orchestrator/`, backend structure DB

---

## Overview

Transform the currently sparse isometric world from placeholder colored zones into a richly themed, populated world. Uses the full 138-asset `layout-studio` library + 48 office furniture pieces. Zones read their function at a glance via themed decoration, and structures support all four cardinal rotations backed by persisted data.

---

## 1. Data Model — orientation as first-class state

### Backend

- Add `orientation VARCHAR(1) NOT NULL DEFAULT 'N'` to the `world_structures` table.
- Migration: `ALTER TABLE world_structures ADD COLUMN orientation VARCHAR(1) NOT NULL DEFAULT 'N'`.
- Extend `/api/world/structures` response to include `orientation`.
- Placement engine (`orchestrator/strain_engine.py` or dedicated placement module) assigns orientation at placement time:
  - **Wall-like structures** (`quarantine_wall`, `quarantine_barrier`, `checkpoint`, `gate`): choose N/S for horizontal runs, E/W for vertical runs based on adjacent placed structures.
  - **Statues / posts** (`watch_post`, `scan_relay_post`): face toward zone interior (away from boundary wall).
  - **Beacons** (`corruption_beacon`): always N (radially symmetric).
  - **Barriers**: default N.
- Placement events include `orientation` in the JSONL payload (forensic reconstructability preserved).

### Frontend

- Extend `WorldStructure` interface in `worldState.ts` with `orientation: 'N' | 'E' | 'S' | 'W'`.
- Remove the auto-N/E neighbor heuristic from `structureLayer.ts`.

---

## 2. Rendering — Simulation Structures (Layer A)

**Stone sprite structures** already have `_N _E _S _W` variants. Wire all four:

```ts
function structureSpriteName(struct: WorldStructure): string {
  const base = STRUCTURE_BASE_SPRITES[struct.type] ?? 'stoneColumn_N';
  if (!ORIENTED_STRUCTURE_TYPES.has(struct.type)) return `${base}_N`;
  return `${base}_${struct.orientation ?? 'N'}`;
}
```

**Asset-PNG structures** (castle, statue, beacon, plague assets): apply canvas rotation transform. 90° rotations of pixel art stay crisp with `imageSmoothingEnabled = false`:

```ts
ctx.save();
ctx.translate(cx, cy);
ctx.rotate(orientationToRadians(struct.orientation));
ctx.imageSmoothingEnabled = false;
ctx.drawImage(img, -drawW / 2, -drawH / 2, drawW, drawH);
ctx.restore();
```

Where `orientationToRadians`: N=0, E=π/2, S=π, W=-π/2.

**PixelLab generation** (accepted): for the 4 structure types whose source PNG is visually asymmetric (`watch_post`, `scan_relay_post`, `gate`, `corruption_beacon`), generate proper isometric directional sprites via PixelLab rather than rotating a single source image. Generated assets stored to `public/pixel-assets/furniture/layout-studio/` with `{name}-{N|E|S|W}.png` naming. Canvas rotation is the fallback while generation is in-flight.

---

## 3. Rendering — Decorative Dressing Layer (Layer B)

New file: `frontend/src/pixel/world/worldDecorLayer.ts`

**Design contract:**
- Zero backend writes. No SIEM events. No fake structures.
- Deterministic: `hash(zoneId, col, row)` → always same prop, always same rotation. World looks identical every render cycle.
- Non-blocking: decor tiles are pre-computed once at load; render is a single sorted draw pass.
- Non-walkable: purely visual; agent pathfinding unchanged.

**Per-zone asset tables:**

| Zone | Dominant assets | Density |
|------|-----------------|---------|
| `guardian_fortress` | `blood-blood-castle`, `guardian-guardian-statue-{01-04}`, `dungeon-brazier`, `dungeon-stone-arch`, `dungeon-wall-torch`, `dungeon-candle-pair` | 14% walkable tiles |
| `quarantine_block` | `dungeon-prison-bars`, `dungeon-skull-post`, `blood-blood-plague-cloud-{01-04}`, `dungeon-broken-floor-slab`, `dungeon-rubble-pile`, `dungeon-ritual-circle` | 16% walkable tiles |
| `courier_zone` | `server-rack-on-f{0-2}` (animated), `neon-rack-tall`, `cable-bundle-h/v`, `patch-panel-wide`, `cable-sprawl-cyan/red` | 18% walkable tiles |
| `analyst_bay` | `glass-monitor-wall`, `evidence-board`, `holo-map-table`, `analyst-pc-on-f{0-2}`, `sticky-notes`, `digital-clock-on-f{0-3}` | 16% walkable tiles |
| `hub` | `ops-command-display`, `control-center-monitor`, `exec-chair-front`, `glass-panel-blue` (sparse) | 8% walkable tiles |

**Clearance rules:** 2-tile radius around doorways, agent spawn points, and active simulation structures is always kept clear.

**Animation:** props with on-frames (server racks, PCs, digital clocks) cycle at 6 FPS driven by `elapsed`. Braziers and torches use `opacity = 0.7 + 0.3 * sin(elapsed * 8 + offset)` flicker.

---

## 4. Visual Polish

- **Per-zone ambient tint**: single low-alpha overlay rect per zone, drawn before agents:
  - Guardian Fortress: `#1e3a8a18` (cool steel)
  - Quarantine Block: `#7f1d1d20` (sickly crimson)
  - Courier Zone: `#06402810` (cyber green)
  - Analyst Bay: `#3f1d6018` (amber-violet)
  - Hub: neutral (no tint)
- **Drop shadow** under all structures and decor: `ctx.shadowBlur = 6; ctx.shadowColor = 'rgba(0,0,0,0.5)'`
- **Doorway glow lines**: 4px-wide translucent glow across cleared-tile openings at zone borders
- **Effect radius rings** for `corruption_beacon` / `scan_relay_post`: keep existing pulse, soften alpha to 0.10

---

## 5. World Population

- **Always-on**: decorative dressing layer always active; world never empty.
- **Optional backend seed** (`WORLD_SEED_STRUCTURES=1`, default off): on first-round init the placement engine drops:
  - 2 barriers at each zone border crossing
  - 1 checkpoint per inter-zone doorway (oriented perpendicular)
  - 1 watch_post per zone (oriented toward zone interior)
  - 1 corruption_beacon in `courier_zone`, 1 scan_relay_post in `guardian_fortress`
  - All with explicit orientation in JSONL

---

## 6. PixelLab Generation Plan

Generate one asset per target shape per direction. 8 structure types × 4 directions = 32 total, but most are symmetric so only 12 unique generations needed:

| Asset | Directions needed |
|-------|------------------|
| `guardian-guardian-statue-01` | E, S, W (N already exists) |
| `guardian-guardian-statue-03` | E, S, W |
| `blood-castle-gate-wall` | E, S, W |
| `plague-plague-beacon` | (symmetric, canvas rotation fine) |
| `dungeon-iron-gate` | E, S, W |

Use `mcp__pixellab__create_map_object` with matching style prompts for each. Store to `static-assets/furniture/layout-studio/{name}-{dir}.png` and copy to `public/pixel-assets/...` during the Vite build step.

---

## 7. Files Changed

| File | Change |
|------|--------|
| `orchestrator/main.py` | Expose `orientation` in `/api/world/structures` |
| `orchestrator/epidemic_tracker.py` or placement engine | Assign `orientation` on structure placement |
| DB migration | Add `orientation` column |
| `frontend/src/pixel/world/worldState.ts` | Add `orientation` to `WorldStructure` |
| `frontend/src/pixel/world/structureLayer.ts` | Use `orientation` field; add canvas rotation for asset-PNGs; add ambient zone tints; add doorway glows |
| `frontend/src/pixel/world/worldDecorLayer.ts` | New file: deterministic dressing layer |
| `frontend/src/pixel/world/worldRenderer.ts` | Call `renderDecorLayer` before agents, after floor tiles |
| `frontend/src/pixel/constants.ts` | Add zone tint color constants |
| `public/pixel-assets/furniture/layout-studio/` | Add PixelLab-generated directional variants |

---

## 8. Test Plan

- **TypeScript compile**: `tsc --noEmit` clean.
- **Rotation bbox test**: `orientationToRadians(dir)` returns correct radians for all 4 values.
- **Decor determinism**: fixed seed + empty agents state → SHA-256 of rendered canvas matches expected hash across two renders.
- **Migration test**: existing DB rows get `orientation = 'N'`; no nulls.
- **Placement engine test** (`test_structure_orientation_assignment.py`): wall runs orient consistently; gates orient perpendicular to doorway.
- **Manual**: visit each zone in dev server (`npm run dev`), confirm:
  - Thematic decoration reads correctly per zone
  - Structures render at all 4 orientations
  - No decor appears in doorways or on structures
  - Agent pathfinding unchanged

---

## 9. Out of Scope

- Operator placement/rotation UI (Layout Studio for world view)
- Pathfinding changes (decor is non-blocking visual)
- Per-tile height / elevation (all tiles remain flat)
