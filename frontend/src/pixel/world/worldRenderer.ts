import { WORLD_COLS, WORLD_ROWS, WORLD_TILE_SIZE, WORLD_ZONES } from '../constants.js';
import { getTileMap, getZoneMap, getZoneDef } from './worldMap.js';
import { renderStructureLayer } from './structureLayer.js';
import { renderAgentLayer } from './agentWorldRenderer.js';
import type { CameraState } from './worldCamera.js';
import type { WorldState } from './worldState.js';
import { TileType } from '../office/types.js';

const ZONE_FLOOR_ALPHA = 0.9;
const CONTAMINATION_MAX_ALPHA = 0.7;

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

  const c0 = Math.max(0, Math.floor(cam.x / s) - 1);
  const r0 = Math.max(0, Math.floor(cam.y / s) - 1);
  const c1 = Math.min(WORLD_COLS - 1, Math.ceil((cam.x + cam.viewportW / cam.zoom) / s) + 1);
  const r1 = Math.min(WORLD_ROWS - 1, Math.ceil((cam.y + cam.viewportH / cam.zoom) / s) + 1);

  // 1. Floor tiles with zone color tint
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

  // 2. Contamination overlay
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

  // 3. Zone borders
  for (const zone of WORLD_ZONES) {
    ctx.strokeStyle = zone.borderColor + '88';
    ctx.lineWidth = 1;
    ctx.strokeRect(
      zone.colMin * s, zone.rowMin * s,
      (zone.colMax - zone.colMin + 1) * s,
      (zone.rowMax - zone.rowMin + 1) * s,
    );
  }

  // 4. Structures
  const elapsed = performance.now() / 1000;
  renderStructureLayer(ctx, state.structures, cam.zoom, elapsed);

  // 5. Agents
  renderAgentLayer(ctx, state, elapsed);

  ctx.restore();
}
