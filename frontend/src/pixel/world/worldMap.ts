import { WORLD_COLS, WORLD_ROWS, WORLD_ZONES, type ZoneId, type ZoneDef } from '../constants.js';
import { TileType } from '../office/types.js';

export interface WorldTileInfo {
  type: number;
  zone: ZoneId;
  walkable: boolean;
  contaminationLevel: number;
}

const _tileMap: number[][] = [];
const _zoneMap: ZoneId[][] = [];

function buildMaps(): void {
  for (let r = 0; r < WORLD_ROWS; r++) {
    _tileMap.push(new Array(WORLD_COLS).fill(TileType.FLOOR_1) as number[]);
    _zoneMap.push(new Array(WORLD_COLS).fill('hub') as ZoneId[]);
  }

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

  // Open doorways (3-tile gaps)
  const openings: [number, number][] = [
    [19, 10], [19, 11], [19, 12],
    [10, 40], [11, 40], [12, 40],
    [55, 8],  [55, 9],  [55, 10],
    [40, 20], [41, 20], [42, 20],
    [55, 24], [56, 24], [57, 24],
    [40, 40], [41, 40], [42, 40],
  ];
  for (const [c, r] of openings) {
    if (r >= 0 && r < WORLD_ROWS && c >= 0 && c < WORLD_COLS) {
      _tileMap[r][c] = TileType.FLOOR_1;
    }
  }
}

buildMaps();

export function getTileMap(): number[][] { return _tileMap; }
export function getZoneMap(): ZoneId[][] { return _zoneMap; }

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
