/**
 * Deterministic decorative dressing layer for the world sim.
 *
 * Contract:
 *  - Zero backend writes. No SIEM events.
 *  - hash(zoneId, col, row) → always same prop, always same rotation.
 *  - Props are pre-sorted by painter depth at build time.
 *  - Non-blocking: no new fetch, no awaits.
 *  - Non-walkable: purely visual, pathfinding unchanged.
 *
 * Asset paths: /pixel-assets/furniture/ (root) and /pixel-assets/furniture/layout-studio/
 */

import { WORLD_ZONES, ISO_HALF_W, ISO_HALF_H, type ZoneId } from '../constants.js';
import { tileToIso } from './worldCamera.js';
import { isWorldWalkable, getZoneMap } from './worldMap.js';

// ── Asset base paths ─────────────────────────────────────────────────────────
const ROOT_ASSETS = '/pixel-assets/furniture';
const LS_ASSETS   = `${ROOT_ASSETS}/layout-studio`;

// ── Image cache ──────────────────────────────────────────────────────────────
const _cache   = new Map<string, HTMLImageElement | null>();
const _loading = new Set<string>();

function getImg(url: string): HTMLImageElement | null {
  const hit = _cache.get(url);
  if (hit !== undefined) return hit;
  if (_loading.has(url)) return null;
  _loading.add(url);
  const img = new Image();
  img.onload  = () => { _cache.set(url, img);   _loading.delete(url); };
  img.onerror = () => { _cache.set(url, null);  _loading.delete(url); };
  img.src = url;
  return null;
}

// ── Per-zone asset tables ─────────────────────────────────────────────────────

interface PropDef {
  /** path relative to ROOT_ASSETS, or full URL if starts with '/' */
  path: string;
  /** animation frame paths at same base; undefined = static */
  frames?: string[];
  /** fractional height relative to 2*ISO_HALF_H for vertical sizing */
  scale: number;
  /** draw density: fraction of eligible tiles populated */
  density: number;
  /** flickering alpha via sin — torches/braziers */
  flicker?: boolean;
}

const LS = (name: string) => `${LS_ASSETS}/${name}.png`;
const RT = (name: string) => `${ROOT_ASSETS}/${name}.png`;

const ZONE_PROPS: Record<ZoneId, PropDef[]> = {
  guardian_fortress: [
    { path: LS('guardian-guardian-castle'),        scale: 1.8, density: 0.010 },
    { path: LS('guardian-guardian-statue-01'),     scale: 1.2, density: 0.018 },
    { path: LS('guardian-guardian-statue-02'),     scale: 1.2, density: 0.012 },
    { path: LS('guardian-guardian-statue-03'),     scale: 1.1, density: 0.014 },
    { path: LS('guardian-guardian-statue-04'),     scale: 1.1, density: 0.012 },
    { path: LS('dungeon-brazier'),                 scale: 0.7, density: 0.030, flicker: true },
    { path: LS('dungeon-stone-arch'),              scale: 1.0, density: 0.018 },
    { path: LS('dungeon-wall-torch'),              scale: 0.6, density: 0.030, flicker: true },
    { path: LS('dungeon-candle-pair'),             scale: 0.5, density: 0.022, flicker: true },
    { path: LS('dungeon-low-stone-wall'),          scale: 0.5, density: 0.014 },
    { path: LS('dungeon-barrel-stack'),            scale: 0.7, density: 0.016 },
    { path: LS('dungeon-treasure-chest'),          scale: 0.6, density: 0.008 },
    // animated: guardian PC
    {
      path: RT('guardian-pc'),
      frames: [RT('guardian-pc-on-f0'), RT('guardian-pc-on-f1'), RT('guardian-pc-on-f2')],
      scale: 0.8, density: 0.016,
    },
  ],
  quarantine_block: [
    { path: LS('dungeon-prison-bars'),             scale: 0.9, density: 0.025 },
    { path: LS('dungeon-skull-post'),              scale: 0.8, density: 0.022 },
    { path: LS('blood-blood-plague-cloud-01'),     scale: 0.7, density: 0.020 },
    { path: LS('blood-blood-plague-cloud-02'),     scale: 0.7, density: 0.018 },
    { path: LS('blood-blood-plague-cloud-03'),     scale: 0.7, density: 0.016 },
    { path: LS('dungeon-broken-floor-slab'),       scale: 0.5, density: 0.030 },
    { path: LS('dungeon-rubble-pile'),             scale: 0.6, density: 0.022 },
    { path: LS('dungeon-ritual-circle'),           scale: 0.6, density: 0.012 },
    { path: LS('plague-bone-heap'),                scale: 0.6, density: 0.018 },
    { path: LS('plague-skull-pair'),               scale: 0.5, density: 0.016 },
    { path: LS('plague-candle-altar'),             scale: 0.7, density: 0.012, flicker: true },
    { path: LS('plague-plague-shrine'),            scale: 0.8, density: 0.010 },
    { path: LS('plague-grave-marker'),             scale: 0.7, density: 0.014 },
    { path: LS('dungeon-spike-rack'),              scale: 0.7, density: 0.010 },
    { path: RT('quarantine-pod'),                  scale: 1.0, density: 0.010 },
  ],
  courier_zone: [
    // animated server racks
    {
      path: RT('server'),
      frames: [RT('server-rack-on-f0'), RT('server-rack-on-f1'), RT('server-rack-on-f2')],
      scale: 1.1, density: 0.030,
    },
    { path: RT('neon-rack-tall'),                  scale: 1.2, density: 0.022 },
    { path: RT('cable-bundle-h'),                  scale: 0.5, density: 0.030 },
    { path: RT('cable-bundle-v'),                  scale: 0.5, density: 0.026 },
    { path: RT('patch-panel-wide'),                scale: 0.6, density: 0.022 },
    { path: RT('cable-sprawl-cyan'),               scale: 0.5, density: 0.024 },
    { path: RT('cable-sprawl-red'),                scale: 0.5, density: 0.018 },
    { path: RT('vertical-cable-pillar'),           scale: 1.0, density: 0.016 },
    { path: RT('floor-cable-node'),                scale: 0.4, density: 0.020 },
    { path: RT('status-light-strip'),              scale: 0.4, density: 0.016 },
  ],
  analyst_bay: [
    { path: RT('glass-monitor-wall'),              scale: 1.1, density: 0.018 },
    { path: RT('evidence-board'),                  scale: 1.0, density: 0.016 },
    { path: RT('holo-map-table'),                  scale: 0.9, density: 0.014 },
    // animated analyst PC
    {
      path: RT('analyst-pc'),
      frames: [RT('analyst-pc-on-f0'), RT('analyst-pc-on-f1'), RT('analyst-pc-on-f2')],
      scale: 0.8, density: 0.028,
    },
    { path: RT('sticky-notes'),                    scale: 0.4, density: 0.022 },
    // animated digital clock
    {
      path: RT('digital-clock'),
      frames: [
        RT('digital-clock-on-f0'), RT('digital-clock-on-f1'),
        RT('digital-clock-on-f2'), RT('digital-clock-on-f3'),
      ],
      scale: 0.5, density: 0.018,
    },
    { path: RT('gadget-console'),                  scale: 0.7, density: 0.012 },
  ],
  hub: [
    { path: RT('ops-command-display'),             scale: 1.1, density: 0.018 },
    { path: RT('control-center-monitor'),          scale: 0.9, density: 0.020 },
    { path: RT('exec-chair-front'),                scale: 0.7, density: 0.016 },
    { path: RT('glass-panel-blue'),                scale: 1.0, density: 0.012 },
    { path: RT('ops-chair-side'),                  scale: 0.6, density: 0.014 },
    { path: RT('exfil-console'),                   scale: 0.8, density: 0.008 },
  ],
};

// ── Clearance set — no props within 2 tiles of doorways ──────────────────────
// Mirrors the openings array in worldMap.ts
const DOORWAY_TILES: [number, number][] = [
  [6, 3], [6, 4], [7, 3], [7, 4],
  [3,10], [4,10], [3,11], [4,11],
  [18,3], [18,4], [19,3], [19,4],
  [14,5], [15,5], [14,6], [15,6],
  [18,6], [19,6], [18,7], [19,7],
  [14,10],[15,10],[14,11],[15,11],
];

function buildClearanceSet(): Set<string> {
  const s = new Set<string>();
  for (const [dc, dr] of DOORWAY_TILES) {
    for (let drow = -2; drow <= 2; drow++) {
      for (let dcol = -2; dcol <= 2; dcol++) {
        s.add(`${dc + dcol},${dr + drow}`);
      }
    }
  }
  return s;
}
const CLEARANCE = buildClearanceSet();

// ── Fast integer hash (FNV-1a 32-bit) ────────────────────────────────────────
function hash32(zoneId: string, col: number, row: number): number {
  let h = 2166136261 >>> 0;
  for (let i = 0; i < zoneId.length; i++) {
    h ^= zoneId.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  h ^= (col & 0xff);        h = Math.imul(h, 16777619) >>> 0;
  h ^= (col >>> 8) & 0xff;  h = Math.imul(h, 16777619) >>> 0;
  h ^= (row & 0xff);        h = Math.imul(h, 16777619) >>> 0;
  h ^= (row >>> 8) & 0xff;  h = Math.imul(h, 16777619) >>> 0;
  return h;
}

// ── Placed decor record ───────────────────────────────────────────────────────
interface DecorTile {
  col: number;
  row: number;
  propDef: PropDef;
  /** seed offset for flicker/animation phase */
  seed: number;
}

// ── Build decor tile list (once per render start, cached until structures change) ──
let _cachedDecor: DecorTile[] | null = null;

export function buildDecorTiles(): DecorTile[] {
  if (_cachedDecor) return _cachedDecor;

  const tiles: DecorTile[] = [];

  for (const zone of WORLD_ZONES) {
    const props = ZONE_PROPS[zone.id];
    if (!props) continue;
    // Preload all images for this zone
    for (const p of props) {
      getImg(p.path);
      if (p.frames) for (const f of p.frames) getImg(f);
    }

    for (let r = zone.rowMin + 1; r < zone.rowMax; r++) {
      for (let c = zone.colMin + 1; c < zone.colMax; c++) {
        if (!isWorldWalkable(c, r)) continue;
        if (CLEARANCE.has(`${c},${r}`)) continue;

        const h = hash32(zone.id, c, r);
        const roll = (h & 0xffff) / 0xffff; // 0..1 uniform

        // Weighted selection across all props in this zone
        const totalDensity = props.reduce((sum, p) => sum + p.density, 0);
        if (roll >= totalDensity) continue;

        let cumulative = 0;
        let chosen: PropDef | null = null;
        const propRoll = roll;
        for (const p of props) {
          cumulative += p.density;
          if (propRoll < cumulative) { chosen = p; break; }
        }
        if (!chosen) continue;

        tiles.push({ col: c, row: r, propDef: chosen, seed: h });
      }
    }
  }

  // Sort by painter depth (row + col ascending for correct overlap)
  tiles.sort((a, b) => (a.col + a.row) - (b.col + b.row));
  _cachedDecor = tiles;
  return tiles;
}

/** Call when structures change to force a rebuild of decor placement. */
export function invalidateDecorCache(): void {
  _cachedDecor = null;
}

// ── Animation frame selection ────────────────────────────────────────────────
const FRAME_FPS = 6;

function activeFrameUrl(prop: PropDef, elapsed: number, seed: number): string {
  if (!prop.frames || prop.frames.length === 0) return prop.path;
  const frameCount = prop.frames.length;
  const offset = (seed & 0x1f) / 32; // stagger start phase by up to 1 cycle
  const frame = Math.floor(((elapsed + offset) * FRAME_FPS) % frameCount);
  return prop.frames[frame];
}

// ── Main render ───────────────────────────────────────────────────────────────
export function renderDecorLayer(
  ctx: CanvasRenderingContext2D,
  elapsed: number,
  selectedAgentZone: string | null = null,
  debugMode = false,
): void {
  const tiles = buildDecorTiles();

  for (const tile of tiles) {
    const { col, row, propDef, seed } = tile;

    // Fog-of-war: dim tiles outside selected agent's zone
    const zoneHere = getZoneForCol(col, row);
    const visible = !selectedAgentZone || debugMode || zoneHere === selectedAgentZone;

    const url = activeFrameUrl(propDef, elapsed, seed);
    const img = getImg(url) ?? (propDef.frames ? getImg(propDef.path) : null);
    if (!img) continue;

    const [ix, iy] = tileToIso(col, row);
    const cellH = 2 * ISO_HALF_H;

    const naturalW = img.naturalWidth  || img.width  || 1;
    const naturalH = img.naturalHeight || img.height || 1;
    const drawH = cellH * propDef.scale;
    const drawW = naturalW * (drawH / naturalH);

    // Feet anchored at cell bottom-center
    const ax = ix - drawW / 2;
    const ay = iy + cellH - drawH;

    ctx.save();
    ctx.imageSmoothingEnabled = false;

    // Drop shadow
    ctx.shadowBlur  = 5;
    ctx.shadowColor = 'rgba(0,0,0,0.45)';

    let alpha = visible ? 1.0 : 0.18;

    if (propDef.flicker) {
      const flickerOffset = (seed & 0xff) / 255 * Math.PI * 2;
      alpha *= 0.7 + 0.3 * Math.sin(elapsed * 8 + flickerOffset);
    }

    ctx.globalAlpha = alpha;
    ctx.drawImage(img, ax, ay, drawW, drawH);
    ctx.restore();
  }
}

function getZoneForCol(col: number, row: number): ZoneId {
  return getZoneMap()[row]?.[col] ?? 'hub';
}
