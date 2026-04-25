import {
  WORLD_COLS, WORLD_ROWS,
  ISO_HALF_W, ISO_HALF_H,
  WORLD_ZONES,
} from '../constants.js';
import { getZoneMap, getZoneDef } from './worldMap.js';
import { renderStructureLayer } from './structureLayer.js';
import { renderAgentLayer } from './agentWorldRenderer.js';
import { tileToIso, type CameraState } from './worldCamera.js';
import type { WorldState } from './worldState.js';
import { TileType } from '../office/types.js';

// Top-down floor palette keyed by TileType. Solid colors give a clean D2-style
// ground plane — iso sprite assets are billboard-only now.
const FLOOR_TINT_BY_TYPE: Record<number, string> = {
  [TileType.FLOOR_1]: '#3a3f52',
  [TileType.FLOOR_2]: '#434a5f',
  [TileType.FLOOR_3]: '#5a4530',
  [TileType.FLOOR_4]: '#2d3346',
  [TileType.FLOOR_5]: '#3d4558',
  [TileType.FLOOR_6]: '#4d3a2a',
  [TileType.FLOOR_7]: '#3f4659',
  [TileType.FLOOR_8]: '#5b4028',
  [TileType.FLOOR_9]: '#4a3826',
};

const CONTAMINATION_MAX_ALPHA = 0.55;
const CHOKEPOINTS = [
  { col: 9,  row: 5  },
  { col: 20, row: 9  },
  { col: 27, row: 4  },
  { col: 27, row: 12 },
  { col: 20, row: 19 },
  { col: 5,  row: 20 },
];

// Cell-footprint path: axis-aligned square at (ix, iy) top-center anchor.
// Name kept for blast-radius reasons; shape is now a square.
function drawIsoDiamond(
  ctx: CanvasRenderingContext2D,
  iso_x: number, iso_y: number,
): void {
  ctx.beginPath();
  ctx.rect(iso_x - ISO_HALF_W, iso_y, 2 * ISO_HALF_W, 2 * ISO_HALF_H);
}


function drawWorldLegibility(
  ctx: CanvasRenderingContext2D,
  state: WorldState,
  elapsed: number,
): void {
  const selectedAgentZone = state.selectedWorldAgentId ? state.getZoneForAgent(state.selectedWorldAgentId) : null;

  for (const zone of WORLD_ZONES) {
    const isVisible = !state.selectedWorldAgentId || state.debugMode || zone.id === selectedAgentZone;
    if (!isVisible) continue;

    const alert = zone.id === 'guardian_fortress' ? state.guardianPressure : 0;
    // Top-down zone rect: axis-aligned rectangle covering the cell range.
    const [tlx, tly] = tileToIso(zone.colMin, zone.rowMin);
    const zx = tlx - ISO_HALF_W;
    const zy = tly;
    const zw = (zone.colMax - zone.colMin + 1) * 2 * ISO_HALF_W;
    const zh = (zone.rowMax - zone.rowMin + 1) * 2 * ISO_HALF_H;
    ctx.save();
    ctx.strokeStyle = alert > 0.2 ? '#ef4444aa' : zone.borderColor + '88';
    ctx.lineWidth = alert > 0.2 ? 2.5 : 1.5;
    if (zone.id === 'courier_zone') ctx.setLineDash([6, 4]);
    if (zone.id === 'analyst_bay') ctx.setLineDash([2, 3]);
    if (zone.id === 'guardian_fortress') ctx.setLineDash([8, 3]);
    ctx.strokeRect(zx, zy, zw, zh);
    if (alert > 0.2) {
      ctx.globalAlpha = Math.min(0.28, 0.08 + alert * 0.22 + Math.sin(elapsed * 4) * 0.03);
      ctx.fillStyle = '#ef4444';
      ctx.fillRect(zx, zy, zw, zh);
    }
    ctx.restore();
  }

  for (const point of CHOKEPOINTS) {
    const [ix, iy] = tileToIso(point.col, point.row);
    ctx.save();
    ctx.strokeStyle = '#facc15aa';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.ellipse(ix, iy + ISO_HALF_H, 18, 7, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }

  for (const struct of state.structures) {
    if (struct.type !== 'quarantine_barrier' && struct.type !== 'quarantine_wall') continue;
    const [ix, iy] = tileToIso(struct.col, struct.row);
    ctx.save();
    ctx.globalAlpha = struct.state === 'active' ? 0.32 : 0.12;
    ctx.fillStyle = '#dc2626';
    drawIsoDiamond(ctx, ix, iy);
    ctx.fill();
    ctx.restore();
  }
}

function drawContactEffects(ctx: CanvasRenderingContext2D, state: WorldState): void {
  for (const effect of state.contactEffects) {
    const isPerceivedA = !state.selectedWorldAgentId || state.debugMode || state.selectedWorldAgentId === effect.a || state.nearbyAgents.has(effect.a) || state.reachableAgents.has(effect.a);
    const isPerceivedB = !state.selectedWorldAgentId || state.debugMode || state.selectedWorldAgentId === effect.b || state.nearbyAgents.has(effect.b) || state.reachableAgents.has(effect.b);
    if (!isPerceivedA && !isPerceivedB) continue;

    const a = state.agentPositions.get(effect.a);
    const b = state.agentPositions.get(effect.b);
    if (!a || !b) continue;
    const [ax, ay] = tileToIso(a.col, a.row);
    const [bx, by] = tileToIso(b.col, b.row);
    const t = Math.max(0, Math.min(1, effect.age / effect.duration));
    const alpha = (1 - t) * (effect.kind === 'proximity' ? 0.55 : 0.8);
    const pulse = Math.sin(t * Math.PI);
    const color = effect.intent === 'warning'
      ? '#f59e0b'
      : effect.intent === 'question'
        ? '#60a5fa'
        : effect.strainFamily === 'context_poisoning'
          ? '#84cc16'
          : '#22d3ee';
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = color;
    ctx.lineWidth = effect.kind === 'proximity' ? 1.2 : 2.2;
    ctx.setLineDash(effect.kind === 'proximity' ? [4, 4] : []);
    ctx.beginPath();
    ctx.moveTo(ax, ay + ISO_HALF_H);
    ctx.lineTo(bx, by + ISO_HALF_H);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.beginPath();
    ctx.ellipse(ax, ay + ISO_HALF_H, 10 + pulse * 20, 5 + pulse * 10, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.beginPath();
    ctx.ellipse(bx, by + ISO_HALF_H, 10 + pulse * 14, 5 + pulse * 7, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }
}

type WorldTerrainOverlay = (ctx: CanvasRenderingContext2D, elapsed: number) => void;

export function renderWorld(
  ctx: CanvasRenderingContext2D,
  state: WorldState,
  cam: CameraState,
  renderTerrainOverlay?: WorldTerrainOverlay,
): void {
  ctx.save();
  ctx.setTransform(cam.zoom, 0, 0, cam.zoom, -cam.x * cam.zoom, -cam.y * cam.zoom);

  const zoneMap = getZoneMap();

  // Viewport culling in cell units.
  const cellW = 2 * ISO_HALF_W;
  const cellH = 2 * ISO_HALF_H;
  const cMinView = Math.max(0, Math.floor(cam.x / cellW) - 1);
  const cMaxView = Math.min(WORLD_COLS - 1, Math.ceil((cam.x + cam.viewportW / cam.zoom) / cellW) + 1);
  const rMinView = Math.max(0, Math.floor(cam.y / cellH) - 1);
  const rMaxView = Math.min(WORLD_ROWS - 1, Math.ceil((cam.y + cam.viewportH / cam.zoom) / cellH) + 1);

  const elapsed = performance.now() / 1000;

  for (let r = rMinView; r <= rMaxView; r++) {
    for (let c = cMinView; c <= cMaxView; c++) {
      const [ix, iy] = tileToIso(c, r);
      const tile = state.getTileType(c, r);
      const zoneId = zoneMap[r]?.[c] ?? 'hub';
      const zone = getZoneDef(zoneId);

      const isWall = tile === TileType.WALL;
      const agentZone = state.selectedWorldAgentId ? state.getZoneForAgent(state.selectedWorldAgentId) : null;
      const isVisible = !state.selectedWorldAgentId || state.debugMode || zoneId === agentZone;

      if (isWall) {
        ctx.fillStyle = isVisible ? '#1a1a2e' : '#0a0a14';
        drawIsoDiamond(ctx, ix, iy);
        ctx.fill();
        // Subtle zone-colored inner ring to hint allegiance
        ctx.save();
        ctx.strokeStyle = isVisible ? zone.borderColor + '66' : '#1e293b';
        ctx.lineWidth = 1;
        ctx.stroke();
        ctx.restore();
      } else {
        const baseColor = FLOOR_TINT_BY_TYPE[tile as number] ?? zone.floorColor;
        ctx.fillStyle = isVisible ? baseColor : '#09090f';
        drawIsoDiamond(ctx, ix, iy);
        ctx.fill();
        // Zone tint wash for color coherence within a sector.
        if (isVisible) {
          ctx.save();
          ctx.globalAlpha = 0.22;
          ctx.fillStyle = zone.floorColor;
          drawIsoDiamond(ctx, ix, iy);
          ctx.fill();
          ctx.restore();
        }
        // Thin grid line for tile legibility.
        ctx.save();
        ctx.strokeStyle = isVisible ? 'rgba(0,0,0,0.28)' : 'rgba(0,0,0,0.1)';
        ctx.lineWidth = 0.5;
        ctx.stroke();
        ctx.restore();
      }

      const contam = state.getContaminationLevel(c, r);
      if (contam > 0.01) {
        ctx.save();
        ctx.globalAlpha = contam * CONTAMINATION_MAX_ALPHA;
        ctx.fillStyle = zone.threatColor;
        drawIsoDiamond(ctx, ix, iy);
        ctx.fill();
        ctx.restore();
      }
    }
  }

  drawWorldLegibility(ctx, state, elapsed);
  renderTerrainOverlay?.(ctx, elapsed);

  // Structures and agents drawn on top
  const selectedAgentZone = state.selectedWorldAgentId ? state.getZoneForAgent(state.selectedWorldAgentId) : null;
  renderStructureLayer(ctx, state.structures, cam.zoom, elapsed, selectedAgentZone, state.debugMode);
  drawContactEffects(ctx, state);
  renderAgentLayer(ctx, state, elapsed);

  ctx.restore();
}
