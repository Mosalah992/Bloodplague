import type { OfficeState } from './office/engine/officeState.js';
import {
  getPixelAgentSpec,
  getPixelAgentSpecByNumericId,
  PIXEL_AGENT_ORDER,
  PIXEL_LAYOUT_IDS,
  resolvePixelAgentKey,
  type PixelAgentKey,
} from './identity.js';

const PULSE_MS = 500;
const ATTACK_MS = 900;
const DEFEND_MS = 950;
const SHIELD_MS = 1200;
const VACCINE_MS = 1600;
const RANSOM_MS = 1500;
const FLOW_MS = 1800;
const STRAIN_BRANCH_MS = 14000;
const MAX_BRANCHES_PER_AGENT = 2;

function isInfectedState(state: string): boolean {
  return ['I_R', 'I_C', 'I_X', 'P'].includes(String(state || '').toUpperCase());
}

function normalizeState(state: string | null | undefined): string {
  return String(state || 'S').toUpperCase();
}

export type PixelLaneAnchor =
  | { kind: 'agent'; agentKey: PixelAgentKey }
  | { kind: 'furniture'; uid: string }
  | { kind: 'tile'; col: number; row: number };

export interface PixelTransientLane {
  id: string;
  from: PixelLaneAnchor;
  to: PixelLaneAnchor;
  color: string;
  duration: number;
  startedAt: number;
  expiresAt: number;
  width: number;
}

export interface PixelAgentVisualState {
  epidemicState: string;
  infected: boolean;
  quarantined: boolean;
  promptLocked: boolean;
  pulseUntil: number;
  attackUntil: number;
  defendUntil: number;
  beaconUntil: number;
  beaconStartedAt: number;
  taskingUntil: number;
  taskingStartedAt: number;
}

export interface PixelLabVisualState {
  agents: Record<PixelAgentKey, PixelAgentVisualState>;
  lanes: PixelTransientLane[];
  officeFx: {
    shieldUntil: number;
    vaccineUntil: number;
    ransomUntil: number;
  };
  anchors: {
    c2: PixelLaneAnchor;
    exfil: PixelLaneAnchor;
  };
}

interface DashboardAgentState {
  epidemic_state?: string;
  c2_lifecycle_state?: string;
}

export interface WorldEpidemicMetrics {
  guardian_degradation_level?: string;
  global_infection_pressure?: number;
  guardian_pressure_score?: number;
  world_round_id?: number;
}

export interface DashboardState {
  mode?: string;
  agents?: Record<string, DashboardAgentState & Record<string, unknown>>;
  epidemic?: {
    metrics?: WorldEpidemicMetrics & Record<string, unknown>;
  };
}

interface StoredSeatAssignment {
  seatId?: string | null;
  palette?: number | null;
}

type StoredSeatAssignments = Record<string, StoredSeatAssignment>;

interface LiveEvent {
  id?: string | number;
  type?: string;
  event?: string;
  src?: string;
  dst?: string;
  attackType?: string;
  attack_type?: string;
  killChainStage?: string;
  kill_chain_stage?: string;
  epidemicState?: string;
  epidemic_state?: string;
  payloadHash?: string;
  parentPayloadHash?: string;
  strainId?: string;
  strainFamily?: string;
  strain_family?: string;
  semanticFamily?: string;
  strainBranchingRecommended?: boolean;
  mutationType?: string;
  mutationVersion?: string | number;
}

interface BranchVisual {
  parentAgentId: number;
  branchKey: string;
  expiresAt: number;
}

function createAgentVisualState(): PixelAgentVisualState {
  return {
    epidemicState: 'S',
    infected: false,
    quarantined: false,
    promptLocked: false,
    pulseUntil: 0,
    attackUntil: 0,
    defendUntil: 0,
    beaconUntil: 0,
    beaconStartedAt: 0,
    taskingUntil: 0,
    taskingStartedAt: 0,
  };
}

export class EpidemicAdapter {
  private officeState: OfficeState;
  private lanes: PixelTransientLane[] = [];
  private seenEventIds = new Set<string>();
  private queuedEvents: LiveEvent[] = [];
  private flushHandle: number | null = null;
  private resetRespawnAt = 0;
  private latestSnapshot: DashboardState | null = null;
  private laneSeq = 0;
  private seatAssignments = new Map<PixelAgentKey, string | null>();
  private branchVisuals = new Map<string, BranchVisual>();
  private visualState: PixelLabVisualState = {
    agents: {
      'courier-1': createAgentVisualState(),
      'courier-2': createAgentVisualState(),
      'analyst-1': createAgentVisualState(),
      'analyst-2': createAgentVisualState(),
      guardian: createAgentVisualState(),
    },
    lanes: [],
    officeFx: {
      shieldUntil: 0,
      vaccineUntil: 0,
      ransomUntil: 0,
    },
    anchors: {
      c2: { kind: 'furniture', uid: PIXEL_LAYOUT_IDS.c2FurnitureUid },
      exfil: { kind: 'tile', ...PIXEL_LAYOUT_IDS.exfilTile },
    },
  };

  constructor(officeState: OfficeState) {
    this.officeState = officeState;
  }

  dispose(): void {
    if (this.flushHandle !== null) {
      cancelAnimationFrame(this.flushHandle);
      this.flushHandle = null;
    }
  }

  setSeatAssignments(seats: StoredSeatAssignments | null | undefined): void {
    this.seatAssignments.clear();

    for (const [numericId, assignment] of Object.entries(seats || {})) {
      const spec = getPixelAgentSpecByNumericId(Number(numericId));
      if (!spec) continue;
      this.seatAssignments.set(spec.key, assignment?.seatId || null);
    }

    for (const key of PIXEL_AGENT_ORDER) {
      const spec = getPixelAgentSpec(key);
      if (!spec) continue;
      const character = this.officeState.characters.get(spec.numericId);
      if (!character) continue;
      const state = this.visualState.agents[key];
      if (state.quarantined || state.promptLocked) continue;
      this.moveToDefaultSeat(key);
    }
  }

  getVisualState(): PixelLabVisualState {
    const now = performance.now();
    this.lanes = this.lanes.filter((lane) => lane.expiresAt > now);
    this.visualState.lanes = this.lanes;
    this.expireBranches(now);

    if (this.resetRespawnAt && this.latestSnapshot && now >= this.resetRespawnAt) {
      this.resetRespawnAt = 0;
      this.applySnapshot(this.latestSnapshot);
    }

    return this.visualState;
  }

  syncSnapshot(controlState: DashboardState | null | undefined): void {
    if (!controlState) return;
    this.latestSnapshot = controlState;
    if (this.resetRespawnAt && performance.now() < this.resetRespawnAt) return;
    this.applySnapshot(controlState);
  }

  cue(action: { type: 'inject'; targets: string[] } | { type: 'quarantine'; target: string } | { type: 'vaccine' } | { type: 'reset' }): void {
    const now = performance.now();

    if (action.type === 'inject') {
      for (const target of action.targets) {
        const key = resolvePixelAgentKey(target);
        if (!key) continue;
        this.ensureAgent(key);
        this.visualState.agents[key].attackUntil = now + ATTACK_MS;
      }
      return;
    }

    if (action.type === 'quarantine') {
      const key = resolvePixelAgentKey(action.target);
      if (!key) return;
      this.moveToQuarantine(key);
      this.visualState.agents[key].defendUntil = now + DEFEND_MS;
      return;
    }

    if (action.type === 'vaccine') {
      this.visualState.officeFx.vaccineUntil = now + VACCINE_MS;
      for (const key of PIXEL_AGENT_ORDER) {
        this.visualState.agents[key].defendUntil = now + VACCINE_MS;
      }
      return;
    }

    this.visualState.officeFx.shieldUntil = 0;
    this.visualState.officeFx.vaccineUntil = 0;
    this.visualState.officeFx.ransomUntil = 0;
    this.lanes = [];
    for (const key of PIXEL_AGENT_ORDER) {
      const state = this.visualState.agents[key];
      state.promptLocked = false;
      state.quarantined = false;
      state.infected = false;
      state.epidemicState = 'S';
      const spec = getPixelAgentSpec(key);
      if (spec) {
        this.officeState.removeAllSubagents(spec.numericId);
      }
    }
    for (const key of PIXEL_AGENT_ORDER) {
      const spec = getPixelAgentSpec(key);
      if (!spec) continue;
      this.officeState.removeAgent(spec.numericId);
    }
    this.branchVisuals.clear();
    this.resetRespawnAt = now + 360;
    this.seenEventIds.clear();
  }

  ingest(events: LiveEvent[] | null | undefined): void {
    if (!events?.length) return;

    for (const event of events) {
      const eventId = String(event.id ?? '');
      if (eventId && this.seenEventIds.has(eventId)) continue;
      if (eventId) this.seenEventIds.add(eventId);
      this.queuedEvents.push(event);
    }

    if (this.flushHandle !== null || !this.queuedEvents.length) return;
    this.flushHandle = requestAnimationFrame(() => {
      this.flushHandle = null;
      const pending = this.queuedEvents.splice(0, this.queuedEvents.length);
      for (const event of pending) {
        this.processEvent(event);
      }
    });
  }

  private applySnapshot(controlState: DashboardState): void {
    const present = new Set<PixelAgentKey>();

    for (const [rawId, rawAgent] of Object.entries(controlState.agents || {})) {
      const key = resolvePixelAgentKey(rawId);
      if (!key) continue;
      present.add(key);
      this.ensureAgent(key);

      const state = this.visualState.agents[key];
      const epidemicState = normalizeState(rawAgent.epidemic_state);
      state.epidemicState = epidemicState;
      state.infected = isInfectedState(epidemicState);
      state.quarantined = epidemicState === 'Q';

      if (state.quarantined) {
        this.moveToQuarantine(key);
      } else if (!state.promptLocked) {
        this.moveToDefaultSeat(key);
      }

      const lifecycle = String(rawAgent.c2_lifecycle_state || '').toUpperCase();
      if (lifecycle.includes('BEACON')) {
        this.startBeacon(key);
      }
      if (lifecycle.includes('TASK')) {
        this.startTasking(key);
      }
      if (lifecycle.includes('EXFIL')) {
        this.startExfil(key);
      }
    }

    for (const key of PIXEL_AGENT_ORDER) {
      const spec = getPixelAgentSpec(key);
      if (!spec) continue;
      if (!present.has(key)) {
        this.officeState.removeAllSubagents(spec.numericId);
        this.officeState.removeAgent(spec.numericId);
      }
    }

    const metrics = controlState.epidemic?.metrics;
    const gdl = String(metrics?.guardian_degradation_level ?? '').trim();
    const degraded =
      gdl.length > 0 && !/^G0(?:_HEALTHY)?$/i.test(gdl) && gdl.toUpperCase() !== 'G0';
    const now = performance.now();
    const ransomActive = now < this.visualState.officeFx.ransomUntil;
    this.visualState.agents.guardian.promptLocked = degraded || ransomActive;
  }

  private processEvent(event: LiveEvent): void {
    const type = String(event.type || event.event || '').toUpperCase();
    const srcKey = resolvePixelAgentKey(event.src);
    const dstKey = resolvePixelAgentKey(event.dst);
    const now = performance.now();

    if (srcKey) this.ensureAgent(srcKey);
    if (dstKey) this.ensureAgent(dstKey);

    if (type.includes('HEARTBEAT') && srcKey) {
      this.visualState.agents[srcKey].pulseUntil = now + PULSE_MS;
    }

    if (type.includes('ATTACK_EXECUTED') && srcKey) {
      this.visualState.agents[srcKey].attackUntil = now + ATTACK_MS;
      this.officeState.setAgentTool(getPixelAgentSpec(srcKey)?.numericId || 0, 'Write');
    }

    if (type.includes('INFECTION_ATTEMPT') && srcKey && dstKey) {
      this.pushLane(srcKey, dstKey, '#22d3ee', 1200, 2.1);
    }

    if (type.includes('INFECTION_SUCCESSFUL') && srcKey && dstKey) {
      this.pushLane(srcKey, dstKey, '#4ade80', 1250, 2.4);
      this.markInfected(dstKey, normalizeState(event.epidemicState || event.epidemic_state || 'I_C'));
    }

    if (type.includes('INFECTION_BLOCKED') && srcKey && dstKey) {
      this.pushLane(srcKey, dstKey, '#f87171', 1150, 2.2);
      this.visualState.agents[dstKey].defendUntil = now + DEFEND_MS;
    }

    if (type.includes('DEFENSE_ADAPTED')) {
      this.visualState.officeFx.shieldUntil = now + SHIELD_MS;
      this.visualState.agents.guardian.defendUntil = now + SHIELD_MS;
    }

    if (type.includes('QUARANTINE_ENFORCED') || type.includes('QUARANTINE_ISSUED')) {
      if (srcKey) this.moveToQuarantine(srcKey);
      if (dstKey) this.moveToQuarantine(dstKey);
    }

    if (type.includes('QUARANTINE_EXPIRED')) {
      if (srcKey) this.releaseQuarantine(srcKey);
      if (dstKey) this.releaseQuarantine(dstKey);
    }

    if (type.includes('VACCINE_APPLIED') || type.includes('VACCINE_RECEIVED')) {
      this.visualState.officeFx.vaccineUntil = now + VACCINE_MS;
    }

    if (type.includes('LLM_HOSTAGE_ATTEMPT')) {
      this.pushLane('courier-1', 'guardian', '#f472b6', 1300, 2.8);
    }

    if (type.includes('LLM_HOSTAGE_SUCCESS')) {
      this.applyRansomSuccess();
    }

    if (type.includes('LLM_HOSTAGE_BLOCKED')) {
      this.pushLane('courier-1', 'guardian', '#fbbf24', 1100, 2.6);
      this.visualState.agents.guardian.defendUntil = now + DEFEND_MS;
    }

    if (type.includes('C2_BEACON') || type === 'BEACON') {
      if (srcKey) this.startBeacon(srcKey);
    }

    if (type.includes('C2_TASK') || type.includes('TASKING')) {
      const key = dstKey || srcKey;
      if (key) this.startTasking(key);
    }

    if (type.includes('C2_EXFIL') || type.includes('EXFIL_ATTEMPT') || type.includes('EXFIL_SUCCESS')) {
      const key = srcKey || dstKey;
      if (key) this.startExfil(key);
    }

    if (type === 'KILL_CHAIN_TRANSITION') {
      const stage = String(event.killChainStage || event.kill_chain_stage || '').toUpperCase();
      const key = srcKey || dstKey;
      if (stage.includes('BEACON') && key) this.startBeacon(key);
      if (stage.includes('TASK') && key) this.startTasking(key);
      if (stage.includes('EXFIL') && key) this.startExfil(key);
      if (stage.includes('RANSOM')) this.applyRansomSuccess();
    }

    if (type === 'OBJECTIVE_COMPLETED') {
      const attackType = String(event.attackType || event.attack_type || '').toUpperCase();
      if (attackType.includes('RANSOM') || attackType.includes('HOSTAGE')) {
        this.applyRansomSuccess();
      }
    }

    if (type.includes('WORLD_MESSAGE')) {
      if (srcKey && dstKey) {
        this.pushLane(srcKey, dstKey, '#38bdf8', 950, 1.85);
      }
      if (srcKey) {
        this.visualState.agents[srcKey].pulseUntil = now + PULSE_MS;
      }
      const intent = String(event.attackType || event.attack_type || '').toUpperCase();
      if (intent && (intent.includes('RELAY') || intent.includes('INJECT') || intent.includes('PRESSURE'))) {
        if (dstKey) {
          this.visualState.agents[dstKey].defendUntil = now + DEFEND_MS * 0.55;
        }
      }
    }

    const branchParent = srcKey || dstKey;
    const shouldBranch =
      Boolean(event.strainBranchingRecommended) ||
      type.includes('STRAIN_MUTATED') ||
      type.includes('MUTATION_SELECTED') ||
      type.includes('ATTACK_PAYLOAD_VALIDATED');
    if (branchParent && shouldBranch) {
      this.refreshBranchFollower(branchParent, event);
    }
  }

  private ensureAgent(key: PixelAgentKey): void {
    const spec = getPixelAgentSpec(key);
    if (!spec) return;
    if (!this.officeState.characters.has(spec.numericId)) {
      this.officeState.addAgent(
        spec.numericId,
        spec.palette,
        0,
        this.getHomeSeatId(key),
        false,
        spec.codename,
      );
    }
  }

  private moveToDefaultSeat(key: PixelAgentKey): void {
    const spec = getPixelAgentSpec(key);
    if (!spec) return;
    const character = this.officeState.characters.get(spec.numericId);
    if (!character) return;
    const homeSeatId = this.getHomeSeatId(key);
    if (character.seatId !== homeSeatId) {
      this.officeState.reassignSeat(spec.numericId, homeSeatId);
    } else {
      this.officeState.sendToSeat(spec.numericId);
    }
  }

  private moveToQuarantine(key: PixelAgentKey): void {
    const spec = getPixelAgentSpec(key);
    if (!spec) return;
    this.ensureAgent(key);
    this.visualState.agents[key].quarantined = true;
    this.officeState.reassignSeat(spec.numericId, spec.quarantineSeatId);
  }

  private releaseQuarantine(key: PixelAgentKey): void {
    this.visualState.agents[key].quarantined = false;
    this.moveToDefaultSeat(key);
  }

  private startBeacon(key: PixelAgentKey): void {
    const now = performance.now();
    const state = this.visualState.agents[key];
    state.beaconStartedAt = now;
    state.beaconUntil = now + FLOW_MS;
  }

  private startTasking(key: PixelAgentKey): void {
    const now = performance.now();
    const state = this.visualState.agents[key];
    state.taskingStartedAt = now;
    state.taskingUntil = now + FLOW_MS;
    const spec = getPixelAgentSpec(key);
    if (spec) {
      this.officeState.setAgentTool(spec.numericId, 'Write');
    }
  }

  private startExfil(key: PixelAgentKey): void {
    const spec = getPixelAgentSpec(key);
    if (!spec) return;
    this.pushLane(key, { kind: 'tile', ...PIXEL_LAYOUT_IDS.exfilTile }, '#fb7185', 1250, 2.5);
    this.officeState.walkToTile(spec.numericId, PIXEL_LAYOUT_IDS.exfilTile.col, PIXEL_LAYOUT_IDS.exfilTile.row);
  }

  private markInfected(key: PixelAgentKey, epidemicState: string): void {
    const state = this.visualState.agents[key];
    state.epidemicState = epidemicState;
    state.infected = true;
  }

  private applyRansomSuccess(): void {
    const now = performance.now();
    this.pushLane('courier-1', 'guardian', '#f472b6', 1400, 2.8);
    this.visualState.officeFx.ransomUntil = now + RANSOM_MS;
    this.visualState.agents.guardian.promptLocked = true;
    this.visualState.agents.guardian.attackUntil = now + ATTACK_MS;
  }

  private getHomeSeatId(key: PixelAgentKey): string {
    const overrideSeatId = this.seatAssignments.get(key);
    if (overrideSeatId && this.officeState.seats.has(overrideSeatId)) {
      return overrideSeatId;
    }
    return getPixelAgentSpec(key)?.seatId || '';
  }

  private getBranchKey(event: LiveEvent): string | null {
    const candidates = [
      event.strainId,
      event.payloadHash,
      event.parentPayloadHash,
      event.mutationType,
      event.mutationVersion != null ? `mutation-${event.mutationVersion}` : '',
    ];
    for (const raw of candidates) {
      const normalized = String(raw || '').trim();
      if (normalized) return normalized;
    }
    return null;
  }

  private refreshBranchFollower(parentKey: PixelAgentKey, event: LiveEvent): void {
    const spec = getPixelAgentSpec(parentKey);
    if (!spec) return;
    this.ensureAgent(parentKey);

    const branchKey = this.getBranchKey(event);
    if (!branchKey) return;

    const now = performance.now();
    const branchId = this.officeState.addSubagent(spec.numericId, branchKey);
    const branchCharacter = this.officeState.characters.get(branchId);
    if (branchCharacter) {
      branchCharacter.currentTool = 'Write';
    }

    this.branchVisuals.set(`${spec.numericId}:${branchKey}`, {
      parentAgentId: spec.numericId,
      branchKey,
      expiresAt: now + STRAIN_BRANCH_MS,
    });

    const parentBranches = Array.from(this.branchVisuals.values())
      .filter((branch) => branch.parentAgentId === spec.numericId)
      .sort((left, right) => right.expiresAt - left.expiresAt);

    for (const stale of parentBranches.slice(MAX_BRANCHES_PER_AGENT)) {
      this.officeState.removeSubagent(stale.parentAgentId, stale.branchKey);
      this.branchVisuals.delete(`${stale.parentAgentId}:${stale.branchKey}`);
    }
  }

  private expireBranches(now: number): void {
    for (const [key, branch] of this.branchVisuals.entries()) {
      if (branch.expiresAt > now) continue;
      this.officeState.removeSubagent(branch.parentAgentId, branch.branchKey);
      this.branchVisuals.delete(key);
    }
  }

  private pushLane(
    from: PixelAgentKey | PixelLaneAnchor,
    to: PixelAgentKey | PixelLaneAnchor,
    color: string,
    duration: number,
    width: number,
  ): void {
    const startedAt = performance.now();
    this.laneSeq += 1;
    this.lanes.push({
      id: `lane-${this.laneSeq}`,
      from: typeof from === 'string' ? { kind: 'agent', agentKey: from } : from,
      to: typeof to === 'string' ? { kind: 'agent', agentKey: to } : to,
      color,
      duration,
      startedAt,
      expiresAt: startedAt + duration,
      width,
    });
  }
}
