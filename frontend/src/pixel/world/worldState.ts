import { OfficeState } from '../office/engine/officeState.js';
import { getTileMap, getZoneForTile, isWorldWalkable } from './worldMap.js';
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

export class WorldState extends OfficeState {
  agentPositions: Map<string, AgentWorldPosition> = new Map();
  structures: WorldStructure[] = [];
  contaminationTiles: Map<string, number> = new Map();

  constructor() {
    super();
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
    return this.agentPositions.get(agentId)?.zone ?? 'hub';
  }
}
