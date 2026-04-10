import type { OfficeState } from '../office/engine/officeState.js';
import { getCatalogEntry } from '../office/layout/furnitureCatalog.js';
import { TILE_SIZE } from '../office/types.js';
import { getPixelAgentSpec, getPixelAgentSpecByNumericId, PIXEL_AGENT_ORDER } from '../identity.js';
import type { PixelLabVisualState, PixelLaneAnchor, PixelTransientLane } from '../epidemicAdapter.js';

interface ScreenPoint {
  x: number;
  y: number;
}

function getOffsets(
  officeState: OfficeState,
  canvasWidth: number,
  canvasHeight: number,
  zoom: number,
  panX: number,
  panY: number,
): { offsetX: number; offsetY: number } {
  const layout = officeState.getLayout();
  const mapWidth = layout.cols * TILE_SIZE * zoom;
  const mapHeight = layout.rows * TILE_SIZE * zoom;
  return {
    offsetX: Math.floor((canvasWidth - mapWidth) / 2) + Math.round(panX),
    offsetY: Math.floor((canvasHeight - mapHeight) / 2) + Math.round(panY),
  };
}

function tileToScreen(
  col: number,
  row: number,
  zoom: number,
  offsetX: number,
  offsetY: number,
): ScreenPoint {
  return {
    x: offsetX + (col + 0.5) * TILE_SIZE * zoom,
    y: offsetY + (row + 0.5) * TILE_SIZE * zoom,
  };
}

function resolveAnchor(
  officeState: OfficeState,
  anchor: PixelLaneAnchor,
  zoom: number,
  offsetX: number,
  offsetY: number,
): ScreenPoint | null {
  if (anchor.kind === 'tile') {
    return tileToScreen(anchor.col, anchor.row, zoom, offsetX, offsetY);
  }

  if (anchor.kind === 'furniture') {
    const item = officeState.getLayout().furniture.find((entry) => entry.uid === anchor.uid);
    if (!item) return null;
    const catalogEntry = getCatalogEntry(item.type);
    if (!catalogEntry) return null;
    return tileToScreen(
      item.col + catalogEntry.footprintW / 2 - 0.5,
      item.row + catalogEntry.footprintH / 2 - 0.5,
      zoom,
      offsetX,
      offsetY,
    );
  }

  const spec = getPixelAgentSpec(anchor.agentKey);
  if (!spec) return null;
  const character = officeState.characters.get(spec.numericId);
  if (!character) return null;
  return {
    x: offsetX + character.x * zoom,
    y: offsetY + character.y * zoom,
  };
}

function drawLane(
  ctx: CanvasRenderingContext2D,
  from: ScreenPoint,
  to: ScreenPoint,
  color: string,
  progress: number,
  width: number,
  alpha = 1,
): void {
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.lineCap = 'round';
  ctx.shadowBlur = 12;
  ctx.shadowColor = color;
  ctx.beginPath();
  ctx.moveTo(from.x, from.y);
  ctx.lineTo(to.x, to.y);
  ctx.stroke();

  const pulseX = from.x + (to.x - from.x) * progress;
  const pulseY = from.y + (to.y - from.y) * progress;
  ctx.fillStyle = '#f8fafc';
  ctx.beginPath();
  ctx.arc(pulseX, pulseY, width * 1.55, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function drawSweep(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  color: string,
  progress: number,
  alpha: number,
): void {
  const sweepX = width * progress;
  const gradient = ctx.createLinearGradient(sweepX - width * 0.2, 0, sweepX + width * 0.15, 0);
  gradient.addColorStop(0, 'rgba(0,0,0,0)');
  gradient.addColorStop(0.5, color);
  gradient.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, width, height);
  ctx.restore();
}

function drawGuardianHalo(
  ctx: CanvasRenderingContext2D,
  point: ScreenPoint,
  radius: number,
  intact: boolean,
): void {
  ctx.save();
  ctx.strokeStyle = intact ? '#fbbf24' : '#f87171';
  ctx.lineWidth = 2;
  ctx.shadowBlur = 16;
  ctx.shadowColor = intact ? '#f59e0b' : '#ef4444';
  if (intact) {
    ctx.beginPath();
    ctx.arc(point.x, point.y - radius * 0.55, radius, 0, Math.PI * 2);
    ctx.stroke();
  } else {
    const segments = [
      [0.1, 0.95],
      [1.45, 2.1],
      [3.2, 4.0],
      [4.8, 5.55],
    ];
    for (const [start, end] of segments) {
      ctx.beginPath();
      ctx.arc(point.x, point.y - radius * 0.55, radius, start, end);
      ctx.stroke();
    }
  }
  ctx.restore();
}

function drawPromptLock(ctx: CanvasRenderingContext2D, point: ScreenPoint): void {
  ctx.save();
  ctx.fillStyle = 'rgba(127, 29, 29, 0.88)';
  ctx.strokeStyle = '#fecaca';
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.roundRect(point.x - 10, point.y - 34, 20, 16, 4);
  ctx.fill();
  ctx.stroke();
  ctx.beginPath();
  ctx.arc(point.x, point.y - 34, 7, Math.PI, 0);
  ctx.stroke();
  ctx.restore();
}

function drawTransientLane(
  ctx: CanvasRenderingContext2D,
  officeState: OfficeState,
  lane: PixelTransientLane,
  now: number,
  zoom: number,
  offsetX: number,
  offsetY: number,
): void {
  const from = resolveAnchor(officeState, lane.from, zoom, offsetX, offsetY);
  const to = resolveAnchor(officeState, lane.to, zoom, offsetX, offsetY);
  if (!from || !to) return;
  const elapsed = now - lane.startedAt;
  const progress = Math.max(0, Math.min(1, elapsed / lane.duration));
  const fade = 1 - progress;
  drawLane(ctx, from, to, lane.color, progress, lane.width, fade);
}

function drawBranchLinks(
  ctx: CanvasRenderingContext2D,
  officeState: OfficeState,
  zoom: number,
  offsetX: number,
  offsetY: number,
): void {
  for (const character of officeState.characters.values()) {
    if (!character.isSubagent || character.parentAgentId == null) continue;
    const parent = officeState.characters.get(character.parentAgentId);
    if (!parent) continue;

    const parentSpec = getPixelAgentSpecByNumericId(parent.id);
    const color = parentSpec?.accent || '#c084fc';
    const from = {
      x: offsetX + parent.x * zoom,
      y: offsetY + (parent.y - TILE_SIZE * 0.25) * zoom,
    };
    const to = {
      x: offsetX + character.x * zoom,
      y: offsetY + (character.y - TILE_SIZE * 0.25) * zoom,
    };

    ctx.save();
    ctx.globalAlpha = 0.7;
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    ctx.moveTo(from.x, from.y);
    ctx.lineTo(to.x, to.y);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(to.x, to.y, Math.max(2.5, zoom * 0.55), 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }
}

export function renderPixelLabOverlay(
  ctx: CanvasRenderingContext2D,
  officeState: OfficeState,
  visualState: PixelLabVisualState,
  zoom: number,
  panX: number,
  panY: number,
): void {
  const width = ctx.canvas.width;
  const height = ctx.canvas.height;
  const now = performance.now();
  const { offsetX, offsetY } = getOffsets(officeState, width, height, zoom, panX, panY);

  ctx.clearRect(0, 0, width, height);

  if (visualState.officeFx.shieldUntil > now) {
    const progress = 1 - (visualState.officeFx.shieldUntil - now) / 1200;
    drawSweep(ctx, width, height, 'rgba(96, 165, 250, 0.28)', progress, 0.65);
  }

  if (visualState.officeFx.vaccineUntil > now) {
    const progress = 1 - (visualState.officeFx.vaccineUntil - now) / 1600;
    drawSweep(ctx, width, height, 'rgba(74, 222, 128, 0.22)', progress, 0.75);
  }

  if (visualState.officeFx.ransomUntil > now) {
    const progress = 1 - (visualState.officeFx.ransomUntil - now) / 1500;
    drawSweep(ctx, width, height, 'rgba(248, 113, 113, 0.18)', progress, 0.8);
  }

  for (const lane of visualState.lanes) {
    if (lane.expiresAt > now) {
      drawTransientLane(ctx, officeState, lane, now, zoom, offsetX, offsetY);
    }
  }

  drawBranchLinks(ctx, officeState, zoom, offsetX, offsetY);

  for (const key of PIXEL_AGENT_ORDER) {
    const spec = getPixelAgentSpec(key);
    if (!spec) continue;
    const character = officeState.characters.get(spec.numericId);
    if (!character) continue;
    const overlay = visualState.agents[key];
    const point = { x: offsetX + character.x * zoom, y: offsetY + character.y * zoom };
    const ringRadius = Math.max(10, zoom * 3.8);

    if (overlay?.infected) {
      ctx.save();
      ctx.fillStyle = spec.infectionTint;
      ctx.beginPath();
      ctx.arc(point.x, point.y - zoom * 4, ringRadius * 1.3, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    if (overlay?.quarantined) {
      ctx.save();
      ctx.strokeStyle = 'rgba(96, 165, 250, 0.9)';
      ctx.lineWidth = 2;
      ctx.setLineDash([4, 4]);
      ctx.strokeRect(
        point.x - ringRadius,
        point.y - ringRadius * 2,
        ringRadius * 2,
        ringRadius * 2.35,
      );
      ctx.restore();
    }

    if (overlay?.pulseUntil > now) {
      ctx.save();
      ctx.strokeStyle = '#4ade80';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(point.x, point.y - zoom * 4, ringRadius * 0.9, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    if (overlay?.attackUntil > now) {
      ctx.save();
      ctx.strokeStyle = '#f87171';
      ctx.lineWidth = 3;
      ctx.shadowBlur = 14;
      ctx.shadowColor = '#ef4444';
      ctx.beginPath();
      ctx.arc(point.x, point.y - zoom * 5, ringRadius, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    if (overlay?.defendUntil > now) {
      ctx.save();
      ctx.strokeStyle = '#fbbf24';
      ctx.lineWidth = 2;
      ctx.shadowBlur = 12;
      ctx.shadowColor = '#fbbf24';
      ctx.beginPath();
      ctx.arc(point.x, point.y - zoom * 5, ringRadius * 1.15, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    if (overlay?.beaconUntil > now) {
      const progress = ((now - overlay.beaconStartedAt) % 700) / 700;
      const from = resolveAnchor(officeState, { kind: 'agent', agentKey: key }, zoom, offsetX, offsetY);
      const to = resolveAnchor(officeState, visualState.anchors.c2, zoom, offsetX, offsetY);
      if (from && to) {
        drawLane(ctx, from, to, '#22d3ee', progress, 2.2, 0.65);
      }
    }

    if (overlay?.taskingUntil > now) {
      const progress = ((now - overlay.taskingStartedAt) % 800) / 800;
      const from = resolveAnchor(officeState, visualState.anchors.c2, zoom, offsetX, offsetY);
      const to = resolveAnchor(officeState, { kind: 'agent', agentKey: key }, zoom, offsetX, offsetY);
      if (from && to) {
        drawLane(ctx, from, to, '#fbbf24', progress, 2.2, 0.65);
      }
    }

    if (spec.key === 'guardian') {
      drawGuardianHalo(ctx, point, ringRadius * 0.8, !overlay?.promptLocked && !overlay?.infected);
      if (overlay?.promptLocked) {
        drawPromptLock(ctx, point);
      }
    }
  }
}
