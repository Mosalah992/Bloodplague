import { OfficeState } from '../office/engine/officeState.js';
import { TileType } from '../office/types.js';
import { getTileMap, getZoneForTile } from './worldMap.js';
import { WORLD_TILE_SIZE, type ZoneId } from '../constants.js';
import {
  AgentAnimationController,
  directionFromVector,
  interactionKindFromAction,
  type AgentAnimationPose,
  type AgentInteractionKind,
} from './agentAnimationController.js';

type TileTypeVal = (typeof TileType)[keyof typeof TileType];

export interface AgentWorldPosition {
  agentId: string;
  col: number;
  row: number;
  targetCol: number;
  targetRow: number;
  lastCol: number;
  lastRow: number;
  velocityCol: number;
  velocityRow: number;
  backendState: string;
  backendAction: string;
  backendTarget: string;
  moveAge: number;
  zone: ZoneId;
}

export interface AgentSemanticState {
  agentId: string;
  role: string;
  epidemicState: string;
  contaminationLevel: number;
  quarantineStatus: string;
  lastIntent: string;
  strainFamily: string;
  interactionTarget: string;
  action: string;
  actionTarget: string;
  semanticAge: number;
}

export interface AgentPositionPatch {
  velocityCol?: number;
  velocityRow?: number;
  state?: string;
  action?: string;
  target?: string;
}

export interface WorldContactEffect {
  id: string;
  a: string;
  b: string;
  intent: string;
  strainFamily: string;
  age: number;
  duration: number;
  kind: 'message' | 'proximity';
}

export interface WorldStructure {
  structureId: string;
  type: string;
  col: number;
  row: number;
  placedBy: string;
  state: string;
  progress: number;
  startedRound: number;
  completedRound: number;
  effectRadius: number;
  hp: number;
  orientation: 'N' | 'E' | 'S' | 'W';
}

function _directionFromDelta(dc: number, dr: number): string {
  return directionFromVector(dc, dr);
}

function _interactionFromIntent(intent: string, strainFamily: string): AgentInteractionKind {
  const intentKey = `${intent} ${strainFamily}`.toLowerCase();
  if (intentKey.includes('infect') || intentKey.includes('poison') || intentKey.includes('contamination')) {
    return 'infection_attempt';
  }
  if (intentKey.includes('attack') || intentKey.includes('exploit') || intentKey.includes('payload')) {
    return 'attack';
  }
  return 'message';
}

export class WorldState extends OfficeState {
  agentPositions: Map<string, AgentWorldPosition> = new Map();
  agentFacings: Map<string, string> = new Map();
  agentSemantics: Map<string, AgentSemanticState> = new Map();
  agentAnimations: Map<string, AgentAnimationController> = new Map();
  contactEffects: WorldContactEffect[] = [];
  structures: WorldStructure[] = [];
  contaminationTiles: Map<string, number> = new Map();
  tileOverrides: Map<string, TileTypeVal> = new Map();
  layoutBlockedTiles: Set<string> = new Set();
  guardianPressure = 0;
  guardianDegradation = 'G0_HEALTHY';
  globalInfectionPressure = 0;

  /** World map selection (agent id string); distinct from OfficeState.selectedAgentId (numeric character id). */
  selectedWorldAgentId: string | null = null;
  debugMode = false;
  nearbyAgents: Set<string> = new Set();
  reachableAgents: Set<string> = new Set();
  private effectSeq = 0;

  constructor() {
    super();
    this.tileMap = getTileMap() as TileTypeVal[][];
    this.blockedTiles = this._buildWorldBlockedTiles();
    this.walkableTiles = this._buildWorldWalkableTiles();
  }

  private _buildWorldBlockedTiles(): Set<string> {
    const blocked = new Set<string>();
    const map = getTileMap();
    for (let r = 0; r < map.length; r++) {
      for (let c = 0; c < map[r].length; c++) {
        if (this.getTileType(c, r) === TileType.WALL) blocked.add(`${c},${r}`);
      }
    }
    for (const key of this.layoutBlockedTiles) blocked.add(key);
    return blocked;
  }

  private _buildWorldWalkableTiles(): Array<{ col: number; row: number }> {
    const walkable: Array<{ col: number; row: number }> = [];
    const map = getTileMap();
    for (let r = 0; r < map.length; r++) {
      for (let c = 0; c < map[r].length; c++) {
        if (this.getTileType(c, r) === TileType.WALL) continue;
        if (this.layoutBlockedTiles.has(`${c},${r}`)) continue;
        walkable.push({ col: c, row: r });
      }
    }
    return walkable;
  }

  setAgentPosition(agentId: string, col: number, row: number, patch: AgentPositionPatch = {}): void {
    const controller = this.ensureAgentAnimation(agentId);
    const prev = this.agentPositions.get(agentId);
    if (prev) {
      const nextAction = patch.action ?? prev.backendAction;
      const nextTarget = patch.target ?? prev.backendTarget;
      const actionChanged = patch.action !== undefined && (
        nextAction !== prev.backendAction || nextTarget !== prev.backendTarget
      );
      const dc = col - prev.targetCol;
      const dr = row - prev.targetRow;
      if (dc !== 0 || dr !== 0) {
        this.agentFacings.set(agentId, _directionFromDelta(dc, dr));
        prev.moveAge = 0;
        prev.lastCol = prev.col;
        prev.lastRow = prev.row;
      }
      prev.targetCol = col;
      prev.targetRow = row;
      prev.backendState = patch.state ?? prev.backendState;
      prev.backendAction = nextAction;
      prev.backendTarget = nextTarget;
      if (patch.velocityCol !== undefined || patch.velocityRow !== undefined) {
        prev.velocityCol = Number(patch.velocityCol ?? 0);
        prev.velocityRow = Number(patch.velocityRow ?? 0);
        if (Math.hypot(prev.velocityCol, prev.velocityRow) > 0.001) {
          this.agentFacings.set(agentId, _directionFromDelta(prev.velocityCol, prev.velocityRow));
        }
      }
      prev.zone = getZoneForTile(col, row);
      const interactionKind = interactionKindFromAction(prev.backendAction);
      if (interactionKind && actionChanged) controller.triggerInteraction(interactionKind, prev.backendTarget);
      return;
    }

    this.agentFacings.set(agentId, 'south');
    this.agentPositions.set(agentId, {
      agentId,
      col,
      row,
      targetCol: col,
      targetRow: row,
      lastCol: col,
      lastRow: row,
      velocityCol: Number(patch.velocityCol ?? 0),
      velocityRow: Number(patch.velocityRow ?? 0),
      backendState: patch.state ?? '',
      backendAction: patch.action ?? '',
      backendTarget: patch.target ?? '',
      moveAge: 0,
      zone: getZoneForTile(col, row),
    });
    const interactionKind = interactionKindFromAction(patch.action);
    if (interactionKind) controller.triggerInteraction(interactionKind, patch.target ?? '');
  }

  setAgentSemantic(agentId: string, patch: Partial<Omit<AgentSemanticState, 'agentId'>>): void {
    const prev = this.agentSemantics.get(agentId);
    const action = patch.action ?? prev?.action ?? '';
    const actionTarget = patch.actionTarget ?? prev?.actionTarget ?? '';
    const actionChanged = patch.action !== undefined && (
      action !== (prev?.action ?? '') || actionTarget !== (prev?.actionTarget ?? '')
    );
    this.agentSemantics.set(agentId, {
      agentId,
      role: patch.role ?? prev?.role ?? 'agent',
      epidemicState: patch.epidemicState ?? prev?.epidemicState ?? 'S',
      contaminationLevel: patch.contaminationLevel ?? prev?.contaminationLevel ?? 0,
      quarantineStatus: patch.quarantineStatus ?? prev?.quarantineStatus ?? 'none',
      lastIntent: patch.lastIntent ?? prev?.lastIntent ?? '',
      strainFamily: patch.strainFamily ?? prev?.strainFamily ?? '',
      interactionTarget: patch.interactionTarget ?? prev?.interactionTarget ?? '',
      action,
      actionTarget,
      semanticAge: 0,
    });
    const interactionKind = interactionKindFromAction(action);
    if (interactionKind && actionChanged) this.triggerAgentInteraction(agentId, interactionKind, actionTarget);
  }

  setWorldMetrics(metrics: {
    guardianPressure?: number;
    guardianDegradation?: string;
    globalInfectionPressure?: number;
  }): void {
    if (metrics.guardianPressure !== undefined) this.guardianPressure = Math.max(0, Math.min(1, metrics.guardianPressure));
    if (metrics.guardianDegradation !== undefined) this.guardianDegradation = metrics.guardianDegradation;
    if (metrics.globalInfectionPressure !== undefined) {
      this.globalInfectionPressure = Math.max(0, Math.min(1, metrics.globalInfectionPressure));
    }
  }

  noteMessageEvent(
    src: string,
    dst: string,
    intent: string,
    strainFamily: string,
    duration = 2.8,
  ): void {
    if (!src || !dst) return;
    this.contactEffects.push({
      id: `world-effect-${++this.effectSeq}`,
      a: src,
      b: dst,
      intent,
      strainFamily,
      age: 0,
      duration,
      kind: 'message',
    });
    this.contactEffects = this.contactEffects.slice(-18);
    this.setAgentSemantic(src, { lastIntent: intent, strainFamily, interactionTarget: dst });
    this.triggerAgentInteraction(src, _interactionFromIntent(intent, strainFamily), dst);
    const srcPos = this.agentPositions.get(src);
    const dstPos = this.agentPositions.get(dst);
    if (srcPos && dstPos) {
      this.agentFacings.set(src, _directionFromDelta(dstPos.targetCol - srcPos.col, dstPos.targetRow - srcPos.row));
      this.agentFacings.set(dst, _directionFromDelta(srcPos.targetCol - dstPos.col, srcPos.targetRow - dstPos.row));
    }
  }

  noteProximityContact(a: string, b: string): void {
    if (!a || !b) return;
    this.contactEffects.push({
      id: `world-effect-${++this.effectSeq}`,
      a,
      b,
      intent: 'proximity',
      strainFamily: '',
      age: 0,
      duration: 1.6,
      kind: 'proximity',
    });
    this.contactEffects = this.contactEffects.slice(-18);
    this.triggerAgentInteraction(a, 'proximity', b);
    this.triggerAgentInteraction(b, 'proximity', a);
  }

  override update(dt: number): void {
    super.update(dt);
    const tilesPerSecond = 4.5;
    for (const pos of this.agentPositions.values()) {
      const prevCol = pos.col;
      const prevRow = pos.row;
      const dc = pos.targetCol - pos.col;
      const dr = pos.targetRow - pos.row;
      const dist = Math.hypot(dc, dr);
      if (dist < 0.01) {
        pos.col = pos.targetCol;
        pos.row = pos.targetRow;
        pos.velocityCol = 0;
        pos.velocityRow = 0;
        this.ensureAgentAnimation(pos.agentId).update({
          dt,
          velocityCol: 0,
          velocityRow: 0,
          targetDistance: 0,
          backendState: pos.backendState,
          backendAction: pos.backendAction,
          targetId: pos.backendTarget,
        });
        continue;
      }
      const arrivalEase = Math.max(0.28, Math.min(1, dist / 1.8));
      const easedStep = dist * (1 - Math.exp(-8 * dt)) * arrivalEase;
      const minimumStep = Math.min(dist, tilesPerSecond * dt * 0.28);
      const maxStep = Math.min(dist, tilesPerSecond * dt * (0.6 + arrivalEase * 0.55));
      const step = Math.min(maxStep, Math.max(minimumStep, easedStep));
      pos.col += (dc / dist) * step;
      pos.row += (dr / dist) * step;
      pos.moveAge += dt;
      pos.velocityCol = dt > 0 ? (pos.col - prevCol) / dt : 0;
      pos.velocityRow = dt > 0 ? (pos.row - prevRow) / dt : 0;

      const numericId = this._numericAgentId(pos.agentId);
      const ch = numericId === null ? null : this.characters.get(numericId);
      if (ch) {
        ch.tileCol = Math.round(pos.col);
        ch.tileRow = Math.round(pos.row);
        ch.x = pos.col * WORLD_TILE_SIZE + WORLD_TILE_SIZE / 2;
        ch.y = pos.row * WORLD_TILE_SIZE + WORLD_TILE_SIZE / 2;
      }

      this.ensureAgentAnimation(pos.agentId).update({
        dt,
        velocityCol: pos.velocityCol,
        velocityRow: pos.velocityRow,
        targetDistance: Math.hypot(pos.targetCol - pos.col, pos.targetRow - pos.row),
        backendState: pos.backendState,
        backendAction: pos.backendAction,
        targetId: pos.backendTarget,
      });
    }
    for (const semantic of this.agentSemantics.values()) {
      semantic.semanticAge += dt;
    }
    for (const effect of this.contactEffects) {
      effect.age += dt;
    }
    this.contactEffects = this.contactEffects.filter((effect) => effect.age < effect.duration);
  }

  private _numericAgentId(agentId: string): number | null {
    switch (agentId) {
      case 'courier-1': return 1;
      case 'courier-2': return 2;
      case 'analyst-1': return 3;
      case 'analyst-2': return 4;
      case 'guardian': return 5;
      default: return null;
    }
  }

  setStructures(structs: WorldStructure[]): void {
    this.structures = structs;
    this.blockedTiles = this._buildWorldBlockedTiles();
    for (const s of structs) {
      const blocks = ['barrier', 'quarantine_wall', 'gate', 'quarantine_barrier'].includes(s.type);
      if (blocks && s.state === 'active') this.blockedTiles.add(`${s.col},${s.row}`);
    }
    this.walkableTiles = this._buildWorldWalkableTiles();
  }

  getTileType(col: number, row: number): TileTypeVal {
    if (row < 0 || row >= getTileMap().length || col < 0 || col >= (getTileMap()[row]?.length ?? 0)) {
      return TileType.VOID;
    }
    return this.tileOverrides.get(`${col},${row}`) ?? (getTileMap()[row][col] as TileTypeVal);
  }

  setTileOverride(col: number, row: number, type: TileTypeVal | null): void {
    if (row < 0 || row >= getTileMap().length || col < 0 || col >= (getTileMap()[row]?.length ?? 0)) return;
    const key = `${col},${row}`;
    if (type === null) {
      this.tileOverrides.delete(key);
    } else {
      this.tileOverrides.set(key, type);
    }
    this.blockedTiles = this._buildWorldBlockedTiles();
    for (const s of this.structures) {
      const blocks = ['barrier', 'quarantine_wall', 'gate', 'quarantine_barrier'].includes(s.type);
      if (blocks && s.state === 'active') this.blockedTiles.add(`${s.col},${s.row}`);
    }
    this.walkableTiles = this._buildWorldWalkableTiles();
  }

  setTileOverrides(overrides: Array<{ col: number; row: number; type: TileTypeVal }>): void {
    this.tileOverrides.clear();
    for (const override of overrides) {
      if (
        override.row >= 0 &&
        override.row < getTileMap().length &&
        override.col >= 0 &&
        override.col < (getTileMap()[override.row]?.length ?? 0)
      ) {
        this.tileOverrides.set(`${override.col},${override.row}`, override.type);
      }
    }
    this.blockedTiles = this._buildWorldBlockedTiles();
    for (const s of this.structures) {
      const blocks = ['barrier', 'quarantine_wall', 'gate', 'quarantine_barrier'].includes(s.type);
      if (blocks && s.state === 'active') this.blockedTiles.add(`${s.col},${s.row}`);
    }
    this.walkableTiles = this._buildWorldWalkableTiles();
  }

  setLayoutBlockedTiles(keys: Iterable<string>): void {
    this.layoutBlockedTiles = new Set(keys);
    this.blockedTiles = this._buildWorldBlockedTiles();
    for (const s of this.structures) {
      const blocks = ['barrier', 'quarantine_wall', 'gate', 'quarantine_barrier'].includes(s.type);
      if (blocks && s.state === 'active') this.blockedTiles.add(`${s.col},${s.row}`);
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

  triggerAgentInteraction(agentId: string, kind: AgentInteractionKind, targetId = ''): void {
    this.ensureAgentAnimation(agentId).triggerInteraction(kind, targetId);
  }

  getAgentAnimationPose(agentId: string): AgentAnimationPose | null {
    return this.agentAnimations.get(agentId)?.getPose() ?? null;
  }

  private ensureAgentAnimation(agentId: string): AgentAnimationController {
    let controller = this.agentAnimations.get(agentId);
    if (!controller) {
      controller = new AgentAnimationController(agentId);
      this.agentAnimations.set(agentId, controller);
    }
    return controller;
  }
}
