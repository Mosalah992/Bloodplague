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

  const ZONE_FLOORS: Record<ZoneId, number> = {
    hub: TileType.FLOOR_1,
    analyst_bay: TileType.FLOOR_2,
    courier_zone: TileType.FLOOR_3,
    guardian_fortress: TileType.FLOOR_4,
    quarantine_block: TileType.FLOOR_5,
  };

  for (const zone of WORLD_ZONES) {
    for (let r = zone.rowMin; r <= zone.rowMax; r++) {
      for (let c = zone.colMin; c <= zone.colMax; c++) {
        _zoneMap[r][c] = zone.id;
        _tileMap[r][c] = ZONE_FLOORS[zone.id] ?? TileType.FLOOR_1;
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

  // Open doorways (2-tile gaps at zone boundaries)
  const openings: [number, number][] = [
    [6, 3], [6, 4], [7, 3], [7, 4],        // hub ↔ analyst_bay
    [3,10], [4,10], [3,11], [4,11],        // hub ↔ guardian_fortress
    [18,3], [18,4], [19,3], [19,4],        // analyst_bay ↔ courier_zone
    [14,5], [15,5], [14,6], [15,6],        // analyst_bay ↔ quarantine_block
    [18,6], [19,6], [18,7], [19,7],        // courier_zone ↔ quarantine_block
    [14,10], [15,10], [14,11], [15,11],    // quarantine_block ↔ guardian_fortress
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
