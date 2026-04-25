import { EditTool, TileType } from '../../pixel/office/types.js';
import {
  ISO_HALF_W,
  ISO_HALF_H,
  WORLD_COLS,
  WORLD_ROWS,
} from '../../pixel/constants.js';
import { tileToIso, type CameraState } from '../../pixel/world/worldCamera.js';
import type { CatalogEntry } from '../../pixel/shared/assets/types.js';

export interface WorldLayoutAsset extends CatalogEntry {
  sourceGroupId: string;
  sourceGroupLabel: string;
}

export interface PlacedWorldAsset {
  uid: string;
  assetId: string;
  col: number;
  row: number;
  rotationDeg?: number;
}

export interface WorldLayoutRenderable {
  source: HTMLCanvasElement | HTMLImageElement;
  width: number;
  height: number;
}

export interface StoredWorldLayout {
  assets?: PlacedWorldAsset[];
  tileOverrides?: Array<{ col: number; row: number; type: number }>;
}

interface ZoneLayoutBounds {
  colMin: number;
  rowMin: number;
  colMax: number;
  rowMax: number;
}

export const WORLD_LAYOUT_STORAGE_KEY = 'epidemic.world.layout_studio.v5';

const WORLD_LAYOUT_ZONES: Record<string, ZoneLayoutBounds> = {
  hub: { colMin: 0, rowMin: 0, colMax: 6, rowMax: 10 },
  analyst_bay: { colMin: 7, rowMin: 0, colMax: 18, rowMax: 5 },
  courier_zone: { colMin: 19, rowMin: 0, colMax: 29, rowMax: 7 },
  quarantine_block: { colMin: 12, rowMin: 6, colMax: 18, rowMax: 10 },
  guardian_fortress: { colMin: 0, rowMin: 11, colMax: 29, rowMax: 17 },
};

export const WORLD_ASSET_GROUPS = [
  { id: 'dungeon', label: 'Dungeon' },
  { id: 'plague', label: 'Plague Lands' },
  { id: 'blood', label: 'Blood Plague' },
  { id: 'guardian', label: 'Guardian Castle' },
];

export const WORLD_TILE_OPTIONS = [
  { label: 'Dungeon stone', value: TileType.FLOOR_1 },
  { label: 'Dungeon tile', value: TileType.FLOOR_2 },
  { label: 'Plague dirt', value: TileType.FLOOR_3 },
  { label: 'Cracked stone', value: TileType.FLOOR_4 },
  { label: 'Mossy stone', value: TileType.FLOOR_5 },
  { label: 'Blood cobble', value: TileType.FLOOR_6 },
  { label: 'Guardian tile', value: TileType.FLOOR_7 },
  { label: 'Dungeon planks', value: TileType.FLOOR_8 },
  { label: 'Inset stone', value: TileType.FLOOR_9 },
  { label: 'Castle wall', value: TileType.WALL },
];

const NON_BLOCKING_ASSET_PATTERNS = [
  'floor', 'path', 'slab', 'pool', 'mire', 'grove', 'moss', 'patch',
  'cloud', 'scatter', 'bone-heap', 'bone-scatter', 'stones', 'hole',
  'ritual-circle', 'stepping-stones', 'dirt-floor', 'earthen-floor',
  'cobble', 'sanctuary',
];

const LAYOUT_ASSET_SCALE = {
  ground: 0.72,
  prop: 0.62,
  wall: 0.74,
  landmark: 0.95,
};

export function normalizeHalfTurn(value: unknown): 0 | 180 {
  const deg = Number(value ?? 0);
  return Math.abs((((deg % 360) + 360) % 360) - 180) < 90 ? 180 : 0;
}

function layoutUid(assetId: string, col: number, row: number, rotationDeg: number, index: number): string {
  return `bundled-${index}-${assetId}-${col}-${row}-${rotationDeg}`;
}

function zoneInteriorTiles(bounds: ZoneLayoutBounds, type: number): Array<{ col: number; row: number; type: number }> {
  const tiles: Array<{ col: number; row: number; type: number }> = [];
  for (let row = bounds.rowMin + 1; row < bounds.rowMax; row += 1) {
    for (let col = bounds.colMin + 1; col < bounds.colMax; col += 1) {
      tiles.push({ col, row, type });
    }
  }
  return tiles;
}

function applyTileRect(
  tileMap: Map<string, number>,
  bounds: {
    colMin: number;
    rowMin: number;
    colMax: number;
    rowMax: number;
    type: number;
  },
): void {
  const { colMin, rowMin, colMax, rowMax, type } = bounds;
  for (let row = rowMin; row <= rowMax; row += 1) {
    for (let col = colMin; col <= colMax; col += 1) {
      if (col < 0 || col >= WORLD_COLS || row < 0 || row >= WORLD_ROWS) continue;
      tileMap.set(`${col},${row}`, type);
    }
  }
}

export function createBundledWorldLayout(): StoredWorldLayout {
  const tileMap = new Map<string, number>();
  const applyTiles = (tiles: Array<{ col: number; row: number; type: number }>) => {
    for (const tile of tiles) {
      tileMap.set(`${tile.col},${tile.row}`, tile.type);
    }
  };

  applyTiles(zoneInteriorTiles(WORLD_LAYOUT_ZONES.hub, TileType.FLOOR_2));
  applyTiles(zoneInteriorTiles(WORLD_LAYOUT_ZONES.analyst_bay, TileType.FLOOR_9));
  applyTiles(zoneInteriorTiles(WORLD_LAYOUT_ZONES.courier_zone, TileType.FLOOR_6));
  applyTiles(zoneInteriorTiles(WORLD_LAYOUT_ZONES.quarantine_block, TileType.FLOOR_4));
  applyTiles(zoneInteriorTiles(WORLD_LAYOUT_ZONES.guardian_fortress, TileType.FLOOR_7));

  applyTileRect(tileMap, { colMin: 3, rowMin: 2, colMax: 4, rowMax: 9, type: TileType.FLOOR_8 });
  applyTileRect(tileMap, { colMin: 10, rowMin: 2, colMax: 16, rowMax: 3, type: TileType.FLOOR_2 });
  applyTileRect(tileMap, { colMin: 21, rowMin: 2, colMax: 27, rowMax: 3, type: TileType.FLOOR_3 });
  applyTileRect(tileMap, { colMin: 13, rowMin: 7, colMax: 16, rowMax: 9, type: TileType.FLOOR_3 });
  applyTileRect(tileMap, { colMin: 12, rowMin: 12, colMax: 17, rowMax: 16, type: TileType.FLOOR_8 });
  applyTileRect(tileMap, { colMin: 0, rowMin: 11, colMax: 29, rowMax: 16, type: TileType.FLOOR_7 });

  const assets: Array<Omit<PlacedWorldAsset, 'uid'>> = [
    // Hub: sparse staging path and cache.
    { assetId: 'layout-studio-dungeon-barrel-stack', col: 2, row: 2, rotationDeg: 0 },
    { assetId: 'layout-studio-dungeon-work-table', col: 3, row: 4, rotationDeg: 0 },
    { assetId: 'layout-studio-dungeon-treasure-chest', col: 2, row: 8, rotationDeg: 0 },

    // Analyst bay: orderly research lane.
    { assetId: 'layout-studio-dungeon-candle-shelf', col: 10, row: 1, rotationDeg: 0 },
    { assetId: 'layout-studio-dungeon-alchemy-workbench', col: 11, row: 4, rotationDeg: 0 },
    { assetId: 'layout-studio-dungeon-work-table', col: 16, row: 4, rotationDeg: 180 },

    // Courier zone: compact breach front.
    { assetId: 'layout-studio-blood-castle-gate-wall', col: 21, row: 2, rotationDeg: 0 },
    { assetId: 'layout-studio-blood-castle-wall', col: 25, row: 2, rotationDeg: 0 },
    { assetId: 'layout-studio-plague-plague-shrine', col: 22, row: 5, rotationDeg: 0 },
    { assetId: 'layout-studio-plague-plague-beacon', col: 20, row: 7, rotationDeg: 0 },
    { assetId: 'layout-studio-blood-blood-plague-cloud-01', col: 28, row: 3, rotationDeg: 0 },

    // Quarantine block: sealed containment.
    { assetId: 'layout-studio-plague-iron-gate', col: 14, row: 8, rotationDeg: 0 },
    { assetId: 'layout-studio-plague-bone-altar', col: 15, row: 7, rotationDeg: 0 },
    { assetId: 'layout-studio-plague-plague-pool', col: 17, row: 7, rotationDeg: 0 },
    { assetId: 'layout-studio-plague-bone-cage', col: 17, row: 9, rotationDeg: 0 },

    // Guardian fortress: controlled defensive approach.
    { assetId: 'layout-studio-plague-plague-beacon', col: 4, row: 11, rotationDeg: 0 },
    { assetId: 'layout-studio-dungeon-stone-arch', col: 14, row: 11, rotationDeg: 0 },
    { assetId: 'layout-studio-plague-fire-bowl', col: 12, row: 11, rotationDeg: 0 },
    { assetId: 'layout-studio-plague-fire-bowl', col: 17, row: 11, rotationDeg: 0 },
    { assetId: 'layout-studio-guardian-guardian-statue-03', col: 8, row: 16, rotationDeg: 0 },
    { assetId: 'layout-studio-guardian-guardian-statue-06', col: 22, row: 16, rotationDeg: 0 },
    { assetId: 'layout-studio-guardian-guardian-castle', col: 25, row: 14, rotationDeg: 0 },
  ];

  return {
    assets: assets.map((asset, index) => ({
      uid: layoutUid(asset.assetId, asset.col, asset.row, normalizeHalfTurn(asset.rotationDeg), index),
      assetId: asset.assetId,
      col: asset.col,
      row: asset.row,
      rotationDeg: normalizeHalfTurn(asset.rotationDeg),
    })),
    tileOverrides: Array.from(tileMap.entries()).map(([key, type]) => {
      const [col, row] = key.split(',').map(Number);
      return { col, row, type };
    }),
  };
}

export const BUNDLED_WORLD_LAYOUT = createBundledWorldLayout();

export function cloneStoredWorldLayout(layout: StoredWorldLayout): StoredWorldLayout {
  return {
    assets: Array.isArray(layout.assets)
      ? layout.assets.map((asset) => ({
        ...asset,
        rotationDeg: normalizeHalfTurn(asset.rotationDeg),
      }))
      : [],
    tileOverrides: Array.isArray(layout.tileOverrides)
      ? layout.tileOverrides.map((override) => ({
        col: Number(override.col),
        row: Number(override.row),
        type: Number(override.type),
      }))
      : [],
  };
}

function isWorldTileInBounds(col: number, row: number): boolean {
  return Number.isFinite(col)
    && Number.isFinite(row)
    && col >= 0
    && col < WORLD_COLS
    && row >= 0
    && row < WORLD_ROWS;
}

export function sanitizeStoredWorldLayout(layout: StoredWorldLayout): StoredWorldLayout {
  const cloned = cloneStoredWorldLayout(layout);
  return {
    assets: (cloned.assets ?? []).filter((asset) => isWorldTileInBounds(asset.col, asset.row)),
    tileOverrides: (cloned.tileOverrides ?? []).filter((override) => isWorldTileInBounds(override.col, override.row)),
  };
}

export function cleanWorldLayoutImage(image: HTMLImageElement): WorldLayoutRenderable {
  const width = image.naturalWidth || image.width || 1;
  const height = image.naturalHeight || image.height || 1;
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  if (!ctx) return { source: image, width, height };

  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(image, 0, 0);
  const imageData = ctx.getImageData(0, 0, width, height);
  const { data } = imageData;
  const alphaAt = (x: number, y: number) => data[(y * width + x) * 4 + 3] ?? 0;

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const i = (y * width + x) * 4;
      const alpha = data[i + 3];
      if (alpha === 0) continue;
      const nearEdge = x < 2 || y < 2 || x >= width - 2 || y >= height - 2;
      const nearBlack = data[i] < 8 && data[i + 1] < 8 && data[i + 2] < 12;
      let neighbors = 0;
      for (let oy = -1; oy <= 1; oy += 1) {
        for (let ox = -1; ox <= 1; ox += 1) {
          if (ox === 0 && oy === 0) continue;
          const nx = x + ox;
          const ny = y + oy;
          if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
          if (alphaAt(nx, ny) > 28) neighbors += 1;
        }
      }
      if (alpha < 18 || (alpha < 70 && neighbors <= 1) || (nearEdge && nearBlack && alpha < 140)) {
        data[i + 3] = 0;
      }
    }
  }

  let left = width;
  let top = height;
  let right = 0;
  let bottom = 0;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const alpha = data[(y * width + x) * 4 + 3] ?? 0;
      if (alpha <= 8) continue;
      left = Math.min(left, x);
      top = Math.min(top, y);
      right = Math.max(right, x + 1);
      bottom = Math.max(bottom, y + 1);
    }
  }
  ctx.putImageData(imageData, 0, 0);

  if (right <= left || bottom <= top) return { source: canvas, width, height };
  left = Math.max(0, left - 1);
  top = Math.max(0, top - 1);
  right = Math.min(width, right + 1);
  bottom = Math.min(height, bottom + 1);

  const cropW = right - left;
  const cropH = bottom - top;
  const cropped = document.createElement('canvas');
  cropped.width = cropW;
  cropped.height = cropH;
  const cropCtx = cropped.getContext('2d');
  if (!cropCtx) return { source: canvas, width, height };
  cropCtx.imageSmoothingEnabled = false;
  cropCtx.drawImage(canvas, left, top, cropW, cropH, 0, 0, cropW, cropH);
  return { source: cropped, width: cropW, height: cropH };
}

function assetBlocksAgents(assetId: string | undefined): boolean {
  if (!assetId) return false;
  const slug = assetId.toLowerCase();
  return !NON_BLOCKING_ASSET_PATTERNS.some((pat) => slug.includes(pat));
}

export function readStoredWorldLayout(): StoredWorldLayout {
  try {
    const raw = window.localStorage.getItem(WORLD_LAYOUT_STORAGE_KEY);
    if (!raw) return cloneStoredWorldLayout(BUNDLED_WORLD_LAYOUT);
    const parsed = sanitizeStoredWorldLayout(JSON.parse(raw) as StoredWorldLayout);
    if ((parsed.assets?.length ?? 0) === 0 && (parsed.tileOverrides?.length ?? 0) === 0) {
      const fallback = cloneStoredWorldLayout(BUNDLED_WORLD_LAYOUT);
      const serializedFallback = JSON.stringify(fallback);
      if (serializedFallback !== raw) {
        window.localStorage.setItem(WORLD_LAYOUT_STORAGE_KEY, serializedFallback);
      }
      return fallback;
    }
    const serialized = JSON.stringify(parsed);
    if (serialized !== raw) {
      window.localStorage.setItem(WORLD_LAYOUT_STORAGE_KEY, serialized);
    }
    return parsed;
  } catch {
    return cloneStoredWorldLayout(BUNDLED_WORLD_LAYOUT);
  }
}

export function sourceGroupForAsset(id: string): { id: string; label: string } {
  const slug = id.replace(/^layout-studio-/, '');
  const group = WORLD_ASSET_GROUPS.find((item) => slug.startsWith(`${item.id}-`));
  return group ?? { id: 'world', label: 'World' };
}

export function worldOptionLabel(asset: { id: string; label: string }): string {
  const group = sourceGroupForAsset(asset.id).label;
  if (asset.label.toLowerCase().startsWith(group.toLowerCase())) return asset.label;
  if (group === 'Guardian Castle' && asset.label.toLowerCase().startsWith('guardian ')) return asset.label;
  if (group === 'Blood Plague' && asset.label.toLowerCase().startsWith('blood ')) return asset.label;
  return `${group} ${asset.label}`;
}

function worldAssetFootprint(asset?: CatalogEntry): { width: number; height: number } {
  if (!asset) return { width: 1, height: 1 };
  const fpW = Math.max(1, Math.round(asset.footprintW ?? Math.ceil(asset.width / 16)));
  const fpH = Math.max(1, Math.round(asset.footprintH ?? Math.ceil(asset.height / 16)));
  return {
    width: Math.max(1, Math.ceil(fpW * 0.55)),
    height: Math.max(1, Math.ceil(fpH * 0.55)),
  };
}

function assetFootprintBounds(
  item: PlacedWorldAsset,
  catalog: Map<string, WorldLayoutAsset>,
): { minCol: number; maxCol: number; minRow: number; maxRow: number } {
  const footprint = worldAssetFootprint(catalog.get(item.assetId));
  const halfW = Math.floor(footprint.width / 2);
  const minCol = item.col - halfW;
  const maxCol = item.col + (footprint.width - 1 - halfW);
  const minRow = item.row - (footprint.height - 1);
  const maxRow = item.row;
  return { minCol, maxCol, minRow, maxRow };
}

export function findWorldAssetAt(
  assets: PlacedWorldAsset[],
  catalog: Map<string, WorldLayoutAsset>,
  col: number,
  row: number,
): PlacedWorldAsset | null {
  for (let i = assets.length - 1; i >= 0; i -= 1) {
    const item = assets[i];
    const bounds = assetFootprintBounds(item, catalog);
    if (col >= bounds.minCol && col <= bounds.maxCol && row >= bounds.minRow && row <= bounds.maxRow) {
      return item;
    }
  }
  return null;
}

export function computeLayoutBlockedTiles(
  assets: PlacedWorldAsset[],
  catalog: Map<string, WorldLayoutAsset>,
): Set<string> {
  const blocked = new Set<string>();
  for (const item of assets) {
    if (!assetBlocksAgents(item.assetId)) continue;
    const bounds = assetFootprintBounds(item, catalog);
    for (let row = bounds.minRow; row <= bounds.maxRow; row += 1) {
      for (let col = bounds.minCol; col <= bounds.maxCol; col += 1) {
        if (col < 0 || col >= WORLD_COLS || row < 0 || row >= WORLD_ROWS) continue;
        blocked.add(`${col},${row}`);
      }
    }
  }
  return blocked;
}

function layoutAssetKind(asset?: WorldLayoutAsset): keyof typeof LAYOUT_ASSET_SCALE {
  const slug = String(asset?.id ?? '').toLowerCase();
  if (slug.includes('castle')) return 'landmark';
  if (
    asset?.category === 'wall' ||
    slug.includes('wall') ||
    slug.includes('gate') ||
    slug.includes('arch') ||
    slug.includes('door')
  ) {
    return 'wall';
  }
  if (NON_BLOCKING_ASSET_PATTERNS.some((pat) => slug.includes(pat))) return 'ground';
  return 'prop';
}

function layoutAssetDrawScale(
  asset: WorldLayoutAsset | undefined,
  footprint: { width: number; height: number },
  image: WorldLayoutRenderable,
): number {
  const kind = layoutAssetKind(asset);
  const projectedWidth = (footprint.width + footprint.height) * ISO_HALF_W;
  const projectedDepth = (footprint.width + footprint.height) * ISO_HALF_H;
  const widthBudget = projectedWidth * (kind === 'ground' ? 0.82 : 0.62);
  const heightBudget = (() => {
    if (kind === 'ground') return Math.max(24, projectedDepth * 0.65);
    if (kind === 'landmark') return Math.max(86, Math.min(150, projectedDepth * 0.78));
    if (kind === 'wall') return Math.max(54, Math.min(128, projectedDepth * 0.68));
    return Math.max(42, Math.min(116, projectedDepth * 0.62));
  })();
  const fitWidth = widthBudget / Math.max(1, image.width);
  const fitHeight = heightBudget / Math.max(1, image.height);
  return Math.max(0.18, Math.min(LAYOUT_ASSET_SCALE[kind], fitWidth, fitHeight));
}

function drawWorldLayoutAsset(
  ctx: CanvasRenderingContext2D,
  item: PlacedWorldAsset,
  image: WorldLayoutRenderable,
  selected: boolean,
  catalog: Map<string, WorldLayoutAsset>,
  alpha = 1,
): void {
  const asset = catalog.get(item.assetId);
  const kind = layoutAssetKind(asset);
  const footprint = worldAssetFootprint(asset);
  const [ix, iy] = tileToIso(item.col, item.row);

  const scale = layoutAssetDrawScale(asset, footprint, image);
  const drawW = image.width * scale;
  const drawH = image.height * scale;
  const groundX = ix;
  const groundY = iy + ISO_HALF_H * 2;

  if (kind !== 'ground') {
    const contactW = Math.max(8, Math.min(drawW * 0.46, ISO_HALF_W * (footprint.width + footprint.height) * 0.22));
    const contactH = Math.max(3, Math.min(drawH * 0.075, ISO_HALF_H * (footprint.width + footprint.height) * 0.10));
    const grad = ctx.createRadialGradient(groundX, groundY - 3, 0, groundX, groundY - 3, contactW);
    grad.addColorStop(0, `rgba(0, 0, 0, ${kind === 'landmark' ? 0.16 : 0.12})`);
    grad.addColorStop(0.72, `rgba(0, 0, 0, ${kind === 'landmark' ? 0.07 : 0.05})`);
    grad.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.ellipse(groundX, groundY - 3, contactW, contactH, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  const x = groundX - drawW / 2;
  const y = groundY - drawH;
  const rotation = normalizeHalfTurn(item.rotationDeg);

  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.imageSmoothingEnabled = false;
  ctx.translate(x + drawW / 2, y + drawH / 2);
  ctx.rotate((rotation * Math.PI) / 180);
  ctx.drawImage(image.source, -drawW / 2, -drawH / 2, drawW, drawH);

  if (selected) {
    ctx.strokeStyle = '#22d3ee';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 3]);
    ctx.strokeRect(-drawW / 2 - 2, -drawH / 2 - 2, drawW + 4, drawH + 4);
  }

  ctx.restore();
}

export function renderWorldLayoutAssets(
  ctx: CanvasRenderingContext2D,
  cam: CameraState,
  items: PlacedWorldAsset[],
  images: Map<string, WorldLayoutRenderable>,
  catalog: Map<string, WorldLayoutAsset>,
  editor: {
    isEditMode: boolean;
    selectedUid: string | null;
    activeTool: string;
    selectedAssetId: string;
    hoverTile: { col: number; row: number } | null;
  },
  applyCameraTransform = true,
): void {
  ctx.save();
  if (applyCameraTransform) {
    ctx.setTransform(cam.zoom, 0, 0, cam.zoom, -cam.x * cam.zoom, -cam.y * cam.zoom);
  }

  const sorted = [...items].sort((a, b) => (a.col + a.row) - (b.col + b.row));
  for (const item of sorted) {
    const image = images.get(item.assetId);
    if (!image || image.width === 0 || image.height === 0) continue;
    drawWorldLayoutAsset(ctx, item, image, item.uid === editor.selectedUid, catalog, 1);
  }

  if (
    editor.isEditMode &&
    editor.activeTool === EditTool.FURNITURE_PLACE &&
    editor.selectedAssetId &&
    editor.hoverTile
  ) {
    const image = images.get(editor.selectedAssetId);
    if (image && image.width > 0 && image.height > 0) {
      drawWorldLayoutAsset(
        ctx,
        {
          uid: 'world-layout-preview',
          assetId: editor.selectedAssetId,
          col: editor.hoverTile.col,
          row: editor.hoverTile.row,
        },
        image,
        false,
        catalog,
        0.48,
      );
    }
  }

  ctx.restore();
}
