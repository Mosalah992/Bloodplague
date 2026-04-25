import { ISO_HALF_W, ISO_HALF_H, ISO_SPRITE_DRAW_W, ISO_SPRITE_DRAW_H } from '../constants.js';
import { tileToIso } from './worldCamera.js';
import { getIsoSprite, preloadIsoSprites } from './isoTileLoader.js';
import type { WorldStructure } from './worldState.js';

const STRUCTURE_BASE_SPRITES: Record<string, string> = {
  barrier:         'stoneColumn_N',
  checkpoint:      'stoneWallDoorOpen',
  gate:            'stoneWallGateClosed',
  watch_post:      'stoneWallTop_N',
  quarantine_wall: 'stoneWall',
  quarantine_barrier: 'stoneWall',
  scan_relay_post:    'stoneColumn_N',
  corruption_beacon:  'stoneColumn_N',
};

const WORLD_STRUCTURE_ASSETS: Record<string, string> = {
  barrier:             'dungeon-chain-barrier',
  checkpoint:          'dungeon-iron-gate',
  gate:                'blood-castle-gate-wall',
  watch_post:          'guardian-guardian-statue-01',
  quarantine_wall:     'blood-castle-wall',
  quarantine_barrier:  'blood-castle-wall',
  scan_relay_post:     'guardian-guardian-statue-03',
  corruption_beacon:   'plague-plague-beacon',
};

const STRUCTURE_COLORS: Record<string, { fill: string; border: string }> = {
  barrier:         { fill: '#ef444455', border: '#ef4444' },
  checkpoint:      { fill: '#f59e0b55', border: '#f59e0b' },
  gate:            { fill: '#3b82f655', border: '#3b82f6' },
  watch_post:      { fill: '#8b5cf655', border: '#8b5cf6' },
  quarantine_wall: { fill: '#dc262699', border: '#dc2626' },
  quarantine_barrier: { fill: '#dc262699', border: '#ef4444' },
  scan_relay_post:    { fill: '#06b6d455', border: '#22d3ee' },
  corruption_beacon:  { fill: '#22c55e55', border: '#a3e635' },
};

const ORIENTED_STRUCTURE_TYPES = new Set(['checkpoint', 'gate', 'quarantine_wall', 'quarantine_barrier']);
const WORLD_STRUCTURE_ASSET_BASE = '/pixel-assets/furniture/layout-studio';
const worldStructureAssetCache = new Map<string, HTMLImageElement | null>();
const worldStructureAssetLoading = new Set<string>();

preloadIsoSprites([
  'stoneColumn_N',
  'stoneWallTop_N',
  'stoneWall_N',
  'stoneWall_E',
  'stoneWall_S',
  'stoneWall_W',
  'stoneWallDoorOpen_N',
  'stoneWallDoorOpen_E',
  'stoneWallDoorOpen_S',
  'stoneWallDoorOpen_W',
  'stoneWallGateClosed_N',
  'stoneWallGateClosed_E',
  'stoneWallGateClosed_S',
  'stoneWallGateClosed_W',
]);

function preloadWorldStructureAssets(names: string[]): void {
  for (const name of names) getWorldStructureAsset(name);
}

preloadWorldStructureAssets(Array.from(new Set(Object.values(WORLD_STRUCTURE_ASSETS))));

function getWorldStructureAsset(name: string): HTMLImageElement | null {
  const cached = worldStructureAssetCache.get(name);
  if (cached !== undefined) return cached;
  if (worldStructureAssetLoading.has(name)) return null;
  worldStructureAssetLoading.add(name);
  const img = new Image();
  img.onload = () => {
    worldStructureAssetCache.set(name, img);
    worldStructureAssetLoading.delete(name);
  };
  img.onerror = () => {
    worldStructureAssetCache.set(name, null);
    worldStructureAssetLoading.delete(name);
  };
  img.src = `${WORLD_STRUCTURE_ASSET_BASE}/${name}.png`;
  return null;
}

function worldAssetForStructure(struct: WorldStructure): HTMLImageElement | null {
  const assetName = WORLD_STRUCTURE_ASSETS[struct.type];
  return assetName ? getWorldStructureAsset(assetName) : null;
}

function structureWorldAssetScale(type: string, img: HTMLImageElement): number {
  const width = img.naturalWidth || img.width || 1;
  const height = img.naturalHeight || img.height || 1;
  const isTall = type === 'watch_post' || type === 'scan_relay_post' || type === 'corruption_beacon';
  const widthBudget = isTall ? ISO_HALF_W * 2.2 : ISO_HALF_W * 3.0;
  const heightBudget = isTall ? ISO_SPRITE_DRAW_H * 1.08 : ISO_SPRITE_DRAW_H * 0.82;
  return Math.max(0.22, Math.min(0.86, widthBudget / width, heightBudget / height));
}

function isWallLike(type: string): boolean {
  return ORIENTED_STRUCTURE_TYPES.has(type);
}

function resolvedOrientation(struct: WorldStructure, structures: WorldStructure[]): 'N' | 'E' | 'S' | 'W' {
  // Use backend-authored orientation when present and valid
  if (struct.orientation && ['N','E','S','W'].includes(struct.orientation)) {
    return struct.orientation;
  }
  // Fallback: infer from neighbor adjacency (wall-like types only)
  if (ORIENTED_STRUCTURE_TYPES.has(struct.type)) {
    const colRun = structures.some((s) => isWallLike(s.type) && s.col === struct.col && Math.abs(s.row - struct.row) === 1);
    const rowRun = structures.some((s) => isWallLike(s.type) && s.row === struct.row && Math.abs(s.col - struct.col) === 1);
    return colRun && !rowRun ? 'E' : 'N';
  }
  return 'N';
}

function structureSpriteName(struct: WorldStructure, structures: WorldStructure[]): string {
  const base = STRUCTURE_BASE_SPRITES[struct.type] ?? 'stoneColumn_N';
  if (!ORIENTED_STRUCTURE_TYPES.has(struct.type)) return base;
  return `${base}_${resolvedOrientation(struct, structures)}`;
}

const ORIENTATION_RADIANS: Record<string, number> = {
  N: 0,
  E: Math.PI / 2,
  S: Math.PI,
  W: -Math.PI / 2,
};

export function renderStructureLayer(
  ctx: CanvasRenderingContext2D,
  structures: WorldStructure[],
  zoom: number,
  elapsed: number,
  selectedAgentZone: string | null = null,
  debugMode = false,
): void {
  // Sort by painter depth
  const sorted = [...structures].sort((a, b) => (a.col + a.row) - (b.col + b.row));

  for (const struct of sorted) {
    const [ix, iy] = tileToIso(struct.col, struct.row);
    // Billboard sprite: feet anchored at the cell bottom-center.
    const cellBottomY = iy + 2 * ISO_HALF_H;
    const dx = ix - ISO_SPRITE_DRAW_W / 2;
    const dy = cellBottomY - ISO_SPRITE_DRAW_H;
    const dw = ISO_SPRITE_DRAW_W;
    const dh = ISO_SPRITE_DRAW_H;

    const spriteName = structureSpriteName(struct, sorted);
    const img = getIsoSprite(spriteName);
    const worldAsset = worldAssetForStructure(struct);
    const colors = STRUCTURE_COLORS[struct.type] ?? STRUCTURE_COLORS['barrier'];
    const progress = Math.max(0, Math.min(1, struct.progress ?? 1));
    const hp = Math.max(0, Math.min(1, struct.hp ?? 1));
    const state = struct.state ?? 'active';

    if (struct.effectRadius > 0 && state === 'active') {
      const radiusPx = 2 * ISO_HALF_W * Math.max(1, struct.effectRadius);
      ctx.save();
      ctx.globalAlpha = 0.15;
      ctx.strokeStyle = colors.border;
      ctx.lineWidth = 2 / zoom;
      ctx.beginPath();
      ctx.ellipse(ix, iy + ISO_HALF_H, radiusPx, radiusPx, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    if (struct.type === 'corruption_beacon' && state === 'active') {
      const beaconPulse = 0.5 + 0.5 * Math.sin(elapsed * 4.5);
      ctx.save();
      const [bix, biy] = tileToIso(struct.col, struct.row);
      const grad = ctx.createRadialGradient(bix, biy + ISO_HALF_H, 0, bix, biy + ISO_HALF_H, 20 + beaconPulse * 30);
      grad.addColorStop(0, '#a3e63555');
      grad.addColorStop(1, 'transparent');
      ctx.fillStyle = grad;
      ctx.globalAlpha = 0.4 + beaconPulse * 0.3;
      ctx.beginPath();
      ctx.ellipse(bix, biy + ISO_HALF_H, 20 + beaconPulse * 30, 10 + beaconPulse * 15, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    if (struct.type === 'scan_relay_post' && state === 'active') {
      const scanPulse = 0.5 + 0.5 * Math.sin(elapsed * 2.5);
      ctx.save();
      ctx.strokeStyle = '#22d3ee';
      ctx.lineWidth = 1;
      ctx.globalAlpha = 0.6 * scanPulse;
      const scanR = 10 + scanPulse * 40;
      ctx.beginPath();
      ctx.ellipse(ix, iy + ISO_HALF_H, scanR, scanR * 0.5, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    const alpha = 1.0;
    ctx.globalAlpha = state === 'constructing' ? 0.45 + progress * 0.35 : alpha;

    // Cell-footprint tint square (flattened from iso diamond path).
    if (worldAsset) {
      const naturalW = worldAsset.naturalWidth || worldAsset.width || 1;
      const naturalH = worldAsset.naturalHeight || worldAsset.height || 1;
      const assetScale = structureWorldAssetScale(struct.type, worldAsset);
      const drawW = naturalW * assetScale;
      const drawH = naturalH * assetScale;
      // Anchor center at cell middle — rotate around center
      const cx = ix;
      const cy = cellBottomY - drawH / 2;
      const radians = ORIENTATION_RADIANS[resolvedOrientation(struct, sorted)] ?? 0;

      ctx.save();
      ctx.globalAlpha = state === 'constructing' ? 0.45 + progress * 0.35 : alpha;
      ctx.imageSmoothingEnabled = false;
      if (radians !== 0) {
        ctx.translate(cx, cy);
        ctx.rotate(radians);
        ctx.drawImage(worldAsset, -drawW / 2, -drawH / 2, drawW, drawH);
      } else {
        ctx.drawImage(worldAsset, cx - drawW / 2, cy - drawH / 2, drawW, drawH);
      }
      ctx.restore();

      ctx.save();
      ctx.globalAlpha = 0.28;
      ctx.fillStyle = colors.fill;
      ctx.fillRect(ix - ISO_HALF_W, iy, 2 * ISO_HALF_W, 2 * ISO_HALF_H);
      ctx.restore();
    } else if (img) {
      ctx.drawImage(img, dx, dy, dw, dh);
      ctx.save();
      ctx.globalAlpha = alpha * 0.35;
      ctx.fillStyle = colors.fill;
      ctx.fillRect(ix - ISO_HALF_W, iy, 2 * ISO_HALF_W, 2 * ISO_HALF_H);
      ctx.restore();
    } else {
      ctx.fillStyle = colors.fill;
      ctx.fillRect(ix - ISO_HALF_W, iy, 2 * ISO_HALF_W, 2 * ISO_HALF_H);
      ctx.strokeStyle = colors.border;
      ctx.lineWidth = 1.5 / zoom;
      ctx.strokeRect(ix - ISO_HALF_W, iy, 2 * ISO_HALF_W, 2 * ISO_HALF_H);
    }

    if (state === 'constructing') {
      ctx.save();
      ctx.strokeStyle = '#e2e8f0';
      ctx.lineWidth = 1.5 / zoom;
      ctx.setLineDash([4 / zoom, 3 / zoom]);
      ctx.beginPath();
      ctx.moveTo(ix - ISO_HALF_W * 0.7, iy + ISO_HALF_H * 1.5);
      ctx.lineTo(ix + ISO_HALF_W * 0.7, iy + ISO_HALF_H * 0.5);
      ctx.moveTo(ix - ISO_HALF_W * 0.7, iy + ISO_HALF_H * 0.5);
      ctx.lineTo(ix + ISO_HALF_W * 0.7, iy + ISO_HALF_H * 1.5);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = '#0f172a';
      ctx.fillRect(ix - 16, iy + ISO_HALF_H * 2 + 3, 32, 4);
      ctx.fillStyle = colors.border;
      ctx.fillRect(ix - 16, iy + ISO_HALF_H * 2 + 3, 32 * progress, 4);
      ctx.restore();
    } else if (hp < 0.99) {
      ctx.save();
      ctx.fillStyle = '#0f172a';
      ctx.fillRect(ix - 14, iy + ISO_HALF_H * 2 + 3, 28, 3);
      ctx.fillStyle = hp < 0.35 ? '#ef4444' : '#f59e0b';
      ctx.fillRect(ix - 14, iy + ISO_HALF_H * 2 + 3, 28 * hp, 3);
      ctx.restore();
    }

    ctx.globalAlpha = 1.0;
  }
}
