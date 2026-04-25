import type { WorldState } from './world/worldState.js';
import type { SpeechBubblePool } from './world/speechBubble.js';
import { applyContaminationEvent } from './world/infectionOverlay.js';
import { invalidateDecorCache } from './world/worldDecorLayer.js';
import { WORLD_COLS, WORLD_ROWS } from './constants.js';

interface SpatialResponse {
  positions: Array<{
    agent_id?: string;
    id?: string;
    col?: number;
    row?: number;
    position?: { col?: number; row?: number; x?: number; y?: number };
    zone: string;
    velocity?: { col?: number; row?: number; x?: number; y?: number };
    velocity_col?: number;
    velocity_row?: number;
    state?: string;
    action?: string | { type?: string; target?: string; target_agent?: string; receiver?: string };
    target?: string;
    target_agent?: string;
  }>;
  proximity_contacts?: Array<{ a: string; b: string; dist?: number }>;
}

interface StructuresResponse {
  structures: Array<{
    structure_id: string;
    type: string;
    col: number;
    row: number;
    placed_by: string;
    state?: string;
    progress?: number;
    started_round?: number;
    completed_round?: number;
    effect_radius?: number;
    hp?: number;
    orientation?: string;
  }>;
}

interface WorldStateResponse {
  topology?: Record<string, unknown>;
  agents?: Record<string, {
    role?: string;
    epidemic_state?: string;
    contamination_level?: number;
    quarantine_status?: string;
    state?: string;
    action?: string | { type?: string; target?: string; target_agent?: string; receiver?: string };
    target?: string;
    target_agent?: string;
  }>;
  events?: Array<{
    id?: string | number;
    event_id?: string | number;
    src?: string;
    dst?: string;
    attack_type?: string;
    intent?: string;
    payload_preview?: string;
    strain_family?: string;
    metadata?: {
      intent?: string;
      strain_family?: string;
      family?: string;
      llm_authored?: boolean;
      model?: string;
      prompt_context_hash?: string;
      raw_llm_output_hash?: string;
      validation_status?: string;
    };
  }>;
  epidemic?: {
    metrics?: {
      guardian_pressure_score?: number;
      guardian_degradation_level?: string;
      global_infection_pressure?: number;
    };
    topology?: {
      topology?: Record<string, unknown>;
      agents?: string[];
    };
  };
}

interface LiveEvent {
  id?: string | number;
  stream_id?: string | number;
  type?: string;
  event?: string;
  src?: string;
  dst?: string;
  text?: string;
  intent?: string;
  attack_type?: string;
  infection_vector?: boolean;
  epidemic_state?: string;
  metadata?: {
    text?: string;
    intent?: string;
    infection_vector?: boolean;
    strain_family?: string;
    family?: string;
    distance?: number;
    llm_authored?: boolean;
    model?: string;
    prompt_context_hash?: string;
    raw_llm_output_hash?: string;
    validation_status?: string;
  };
}

const POLL_INTERVAL_MS = 2000;
const ORCHESTRATOR_COMMENTARY_INTERVAL_TICKS = 6; // ~12 s at 2 s/tick
const STREAM_REFRESH_DEBOUNCE_MS = 90;
const STREAM_RECONNECT_MS = 3000;
const PROXIMITY_DEDUP_TTL_MS = 3000;
const FETCH_LOG_THROTTLE_MS = 30000;

const fetchWarnTimestamps = new Map<string, number>();
function logFetchFailure(endpoint: string, error: unknown): void {
  const now = Date.now();
  const last = fetchWarnTimestamps.get(endpoint) ?? 0;
  if (now - last < FETCH_LOG_THROTTLE_MS) return;
  fetchWarnTimestamps.set(endpoint, now);
  const message = error instanceof Error ? error.message : String(error);
  // eslint-disable-next-line no-console
  console.warn(`[worldAdapter] ${endpoint} failed: ${message}`);
}

const DEMO_PATHS_BY_ROLE: Record<string, number[][][]> = {
  courier: [
    [[22, 3], [20, 3], [19, 4], [19, 7], [20, 7], [24, 5]],
    [[26, 5], [24, 4], [22, 4], [20, 6], [19, 7], [23, 6]],
  ],
  analyst: [
    [[11, 2], [13, 3], [15, 4], [14, 6], [12, 4], [11, 2]],
    [[15, 4], [17, 4], [18, 3], [14, 5], [12, 3], [15, 4]],
  ],
  guardian: [
    [[4, 15], [8, 15], [12, 14], [14, 11], [18, 13], [12, 15]],
    [[8, 16], [12, 16], [16, 15], [20, 14], [24, 14], [16, 16]],
  ],
  agent: [
    [[8, 8], [10, 7], [12, 8], [14, 10], [11, 12], [8, 10]],
  ],
};

interface DemoAgent {
  id: string;
  role: string;
}

function actionType(value: unknown): string {
  if (typeof value === 'string') return value;
  if (value && typeof value === 'object' && 'type' in value) {
    return String((value as { type?: string }).type ?? '');
  }
  return '';
}

function actionTarget(value: unknown, fallback = ''): string {
  if (value && typeof value === 'object') {
    const action = value as { target?: string; target_agent?: string; receiver?: string };
    return String(action.target ?? action.target_agent ?? action.receiver ?? fallback);
  }
  return fallback;
}

function normalizedRole(value: unknown): string {
  const role = String(value ?? '').toLowerCase();
  if (role.includes('courier')) return 'courier';
  if (role.includes('analyst')) return 'analyst';
  if (role.includes('guardian')) return 'guardian';
  return 'agent';
}

function stableIndex(value: string, modulo: number): number {
  if (modulo <= 1) return 0;
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash * 33 + value.charCodeAt(i)) >>> 0;
  }
  return hash % modulo;
}

function isWorldPositionInBounds(col: number, row: number): boolean {
  return Number.isFinite(col)
    && Number.isFinite(row)
    && col >= 0
    && col < WORLD_COLS
    && row >= 0
    && row < WORLD_ROWS;
}

function clampWorldPosition(col: number, row: number): { col: number; row: number } {
  return {
    col: Math.max(0, Math.min(WORLD_COLS - 1, col)),
    row: Math.max(0, Math.min(WORLD_ROWS - 1, row)),
  };
}

export class WorldAdapter {
  private state: WorldState;
  private bubblePool: SpeechBubblePool | null = null;
  private onOrchestratorLine: ((line: string) => void) | null = null;
  private pollHandle: ReturnType<typeof setTimeout> | null = null;
  private stream: EventSource | null = null;
  private streamConnected = false;
  private streamReconnectHandle: ReturnType<typeof setTimeout> | null = null;
  private streamRefreshHandle: ReturnType<typeof setTimeout> | null = null;
  private seenEventIds = new Set<string>();
  private seenWorldMessageIds = new Set<string>();
  private proximityDedup = new Map<string, number>();
  private lastEventId = 0;
  private backendMisses = 0;
  private commentaryTick = 0;
  private demoMode = false;
  private demoElapsed = 0;
  private demoPhase = -1;
  private demoAgents: DemoAgent[] = [];
  private refreshInflight = false;
  private pendingRefreshIncludesCommentary = false;

  constructor(state: WorldState) {
    this.state = state;
  }

  setBubblePool(pool: SpeechBubblePool): void {
    this.bubblePool = pool;
  }

  setOrchestratorLineCallback(cb: (line: string) => void): void {
    this.onOrchestratorLine = cb;
  }

  start(): void {
    this.startWorldStream();
    this.tick().catch((err) => {
      // eslint-disable-next-line no-console
      console.warn('[worldAdapter] initial tick failed:', err);
    });
  }

  stop(): void {
    if (this.pollHandle !== null) {
      clearTimeout(this.pollHandle);
      this.pollHandle = null;
    }
    if (this.streamRefreshHandle !== null) {
      clearTimeout(this.streamRefreshHandle);
      this.streamRefreshHandle = null;
    }
    if (this.streamReconnectHandle !== null) {
      clearTimeout(this.streamReconnectHandle);
      this.streamReconnectHandle = null;
    }
    if (this.stream !== null) {
      this.stream.close();
      this.stream = null;
    }
    this.streamConnected = false;
  }

  private async refreshBackend(fetchCommentary: boolean): Promise<void> {
    if (this.refreshInflight) {
      // Coalesce concurrent refresh requests; remember if any caller wanted commentary.
      this.pendingRefreshIncludesCommentary = this.pendingRefreshIncludesCommentary || fetchCommentary;
      return;
    }
    this.refreshInflight = true;
    try {
      this.commentaryTick += 1;
      await Promise.all([
        this.fetchWorldState(),
        this.fetchContamination(),
        this.fetchSpatial(),
        this.fetchStructures(),
        this.fetchLiveEvents(),
        ...(fetchCommentary ? [this.fetchOrchestratorCommentary()] : []),
      ]);
      if (this.state.agentPositions.size === 0 && this.backendMisses > 0) {
        this.applyDeterministicDemoTick(POLL_INTERVAL_MS / 1000);
      }
    } finally {
      this.refreshInflight = false;
      if (this.pendingRefreshIncludesCommentary) {
        const includeCommentary = this.pendingRefreshIncludesCommentary;
        this.pendingRefreshIncludesCommentary = false;
        // Drain a coalesced refresh request without recursing on the stack.
        setTimeout(() => {
          this.refreshBackend(includeCommentary).catch((err) => {
            // eslint-disable-next-line no-console
            console.warn('[worldAdapter] coalesced refresh failed:', err);
          });
        }, 0);
      }
    }
  }

  private async tick(): Promise<void> {
    try {
      const fetchCommentary = this.commentaryTick % ORCHESTRATOR_COMMENTARY_INTERVAL_TICKS === 0;
      await this.refreshBackend(fetchCommentary);
    } catch (err) {
      // eslint-disable-next-line no-console
      console.warn('[worldAdapter] tick failed:', err);
    } finally {
      this.scheduleFallbackPoll();
    }
  }

  private scheduleFallbackPoll(): void {
    if (this.pollHandle !== null) {
      clearTimeout(this.pollHandle);
      this.pollHandle = null;
    }
    if (!this.streamConnected) {
      this.pollHandle = setTimeout(() => this.tick(), POLL_INTERVAL_MS);
    }
  }

  private startWorldStream(): void {
    if (typeof EventSource === 'undefined') return;
    const connect = () => {
      if (this.stream !== null) {
        this.stream.close();
        this.stream = null;
      }
      const source = new EventSource('/api/world/stream');
      this.stream = source;
      source.onopen = () => {
        this.streamConnected = true;
        if (this.pollHandle !== null) {
          clearTimeout(this.pollHandle);
          this.pollHandle = null;
        }
      };
      source.onerror = () => {
        if (this.stream !== source) return;
        this.streamConnected = false;
        source.close();
        this.stream = null;
        this.scheduleFallbackPoll();
        if (this.streamReconnectHandle === null) {
          this.streamReconnectHandle = setTimeout(() => {
            this.streamReconnectHandle = null;
            connect();
          }, STREAM_RECONNECT_MS);
        }
      };
      source.addEventListener('round_completed', () => this.scheduleStreamRefresh(true));
      source.addEventListener('agent_moved', () => this.scheduleStreamRefresh(false));
      source.addEventListener('message_created', (event) => {
        this.ingestStreamEvent(event);
        this.scheduleStreamRefresh(true);
      });
    };
    connect();
  }

  private scheduleStreamRefresh(includeCommentary: boolean): void {
    if (this.streamRefreshHandle !== null) {
      clearTimeout(this.streamRefreshHandle);
    }
    this.streamRefreshHandle = setTimeout(() => {
      this.streamRefreshHandle = null;
      void this.refreshBackend(includeCommentary);
    }, STREAM_REFRESH_DEBOUNCE_MS);
  }

  private ingestStreamEvent(event: MessageEvent): void {
    try {
      const data = JSON.parse(String(event.data || '{}')) as LiveEvent;
      this.ingestEvents([{ ...data, id: data.id ?? data.stream_id, type: data.type ?? data.event }]);
    } catch (err) {
      logFetchFailure('world stream parse', err);
    }
  }

  private noteBackendMiss(): void {
    this.backendMisses = Math.min(6, this.backendMisses + 1);
  }

  private async fetchContamination(): Promise<void> {
    try {
      const res = await fetch('/api/world/contamination');
      if (!res.ok) return;
      const data = await res.json();
      const tiles: Array<{ col: number; row: number; level: number }> = Array.isArray(data?.contamination_tiles) ? data.contamination_tiles : [];
      for (const tile of tiles) {
        const existing = this.state.getContaminationLevel(tile.col, tile.row);
        if (tile.level > existing) {
          this.state.setContaminationTile(tile.col, tile.row, tile.level);
        }
      }
    } catch (err) {
      logFetchFailure('/api/world/contamination', err);
    }
  }

  private async fetchSpatial(): Promise<void> {
    try {
      const res = await fetch('/api/world/spatial');
      if (!res.ok) {
        this.noteBackendMiss();
        return;
      }
      const data: SpatialResponse = await res.json();
      for (const pos of data.positions) {
        const agentId = String(pos.agent_id ?? pos.id ?? '');
        if (!agentId) continue;
        const col = Number(pos.col ?? pos.position?.col ?? pos.position?.x ?? 0);
        const row = Number(pos.row ?? pos.position?.row ?? pos.position?.y ?? 0);
        if (!Number.isFinite(col) || !Number.isFinite(row)) continue;
        const previous = this.state.agentPositions.get(agentId);
        const hasValidPrevious = previous
          ? isWorldPositionInBounds(previous.targetCol, previous.targetRow)
          : false;
        const nextPosition = isWorldPositionInBounds(col, row)
          ? { col, row }
          : hasValidPrevious
            ? null
            : clampWorldPosition(col, row);
        if (!nextPosition) continue;
        const action = actionType(pos.action);
        const target = String(pos.target ?? pos.target_agent ?? actionTarget(pos.action));
        this.state.setAgentPosition(agentId, nextPosition.col, nextPosition.row, {
          velocityCol: Number(pos.velocity_col ?? pos.velocity?.col ?? pos.velocity?.x ?? 0),
          velocityRow: Number(pos.velocity_row ?? pos.velocity?.row ?? pos.velocity?.y ?? 0),
          state: String(pos.state ?? ''),
          action,
          target,
        });
      }
      const now = Date.now();
      // Sweep expired pair entries before processing the batch.
      for (const [key, expires] of this.proximityDedup) {
        if (expires <= now) this.proximityDedup.delete(key);
      }
      for (const contact of data.proximity_contacts ?? []) {
        if (!contact.a || !contact.b) continue;
        const key = [contact.a, contact.b].sort().join(':');
        const expires = this.proximityDedup.get(key) ?? 0;
        if (expires > now) continue;
        this.proximityDedup.set(key, now + PROXIMITY_DEDUP_TTL_MS);
        this.state.noteProximityContact(contact.a, contact.b);
      }
      if (data.positions.length > 0) {
        this.backendMisses = 0;
        this.demoMode = false;
      }
    } catch (err) {
      logFetchFailure('/api/world/spatial', err);
      this.noteBackendMiss();
    }
  }

  private async fetchWorldState(): Promise<void> {
    try {
      const res = await fetch('/api/world/state');
      if (!res.ok) return;
      const data: WorldStateResponse = await res.json();
      this.updateDemoAgents(data);
      const metrics = data.epidemic?.metrics ?? {};
      this.state.setWorldMetrics({
        guardianPressure: Number(metrics.guardian_pressure_score ?? 0),
        guardianDegradation: String(metrics.guardian_degradation_level ?? 'G0_HEALTHY'),
        globalInfectionPressure: Number(metrics.global_infection_pressure ?? 0),
      });

      for (const [agentId, agent] of Object.entries(data.agents ?? {})) {
        const action = actionType(agent.action);
        this.state.setAgentSemantic(agentId, {
          role: String(agent.role ?? 'agent'),
          epidemicState: String(agent.epidemic_state ?? 'S'),
          contaminationLevel: Number(agent.contamination_level ?? 0),
          quarantineStatus: String(agent.quarantine_status ?? 'none'),
          action,
          actionTarget: String(agent.target ?? agent.target_agent ?? actionTarget(agent.action)),
        });
      }

      for (const ev of data.events ?? []) {
        const id = String(ev.event_id ?? ev.id ?? '');
        if (!id || this.seenWorldMessageIds.has(id)) continue;
        this.seenWorldMessageIds.add(id);
        if (this.seenWorldMessageIds.size > 1200) {
          const first = this.seenWorldMessageIds.values().next().value;
          if (first !== undefined) this.seenWorldMessageIds.delete(first);
        }
        const src = String(ev.src ?? '');
        const dst = String(ev.dst ?? '');
        const intent = String(ev.intent ?? ev.attack_type ?? ev.metadata?.intent ?? 'social');
        const family = String(ev.strain_family ?? ev.metadata?.strain_family ?? ev.metadata?.family ?? '');
        if (src && dst) {
          this.state.noteMessageEvent(src, dst, intent, family, 2.4);
          const text = String(ev.payload_preview ?? '');
          const llmAuthored = ev.metadata?.llm_authored === true;
          if (text && llmAuthored) {
            this.bubblePool?.push(src, text, intent, family === 'context_poisoning', family, {
              model: ev.metadata?.model ?? '',
              promptContextHash: ev.metadata?.prompt_context_hash ?? '',
              rawLlmOutputHash: ev.metadata?.raw_llm_output_hash ?? '',
              validationStatus: ev.metadata?.validation_status ?? 'valid',
            });
          }
        }
      }
    } catch (err) {
      logFetchFailure('/api/world/state', err);
      this.noteBackendMiss();
    }
  }

  private updateDemoAgents(data: WorldStateResponse): void {
    const topologyIds = new Set<string>();
    for (const key of Object.keys(data.topology ?? {})) {
      if (key) topologyIds.add(key);
    }
    for (const key of Object.keys(data.epidemic?.topology?.topology ?? {})) {
      if (key) topologyIds.add(key);
    }
    for (const id of data.epidemic?.topology?.agents ?? []) {
      if (id) topologyIds.add(String(id));
    }
    for (const id of Object.keys(data.agents ?? {})) {
      if (id) topologyIds.add(id);
    }
    this.demoAgents = Array.from(topologyIds).sort().map((id) => ({
      id,
      role: normalizedRole(data.agents?.[id]?.role ?? id),
    }));
  }

  private async fetchStructures(): Promise<void> {
    try {
      const res = await fetch('/api/world/structures');
      if (!res.ok) return;
      const data: StructuresResponse = await res.json();
      this.state.setStructures(data.structures.map((s) => ({
        structureId: s.structure_id,
        type: s.type,
        col: s.col,
        row: s.row,
        placedBy: s.placed_by,
        state: String(s.state ?? 'active'),
        progress: Number(s.progress ?? 1),
        startedRound: Number(s.started_round ?? 0),
        completedRound: Number(s.completed_round ?? 0),
        effectRadius: Number(s.effect_radius ?? 0),
        hp: Number(s.hp ?? 1),
        orientation: (['N','E','S','W'].includes(String(s.orientation ?? 'N')) ? s.orientation : 'N') as 'N'|'E'|'S'|'W',
      })));
      invalidateDecorCache();
    } catch (err) {
      logFetchFailure('/api/world/structures', err);
    }
  }

  private async fetchOrchestratorCommentary(): Promise<void> {
    try {
      const res = await fetch('/api/world/orchestrator-commentary');
      if (!res.ok) return;
      const data = await res.json() as { line?: string; degraded?: boolean };
      const line = String(data.line ?? '').trim();
      if (!line) return;
      // Route to dedicated HUD callback if wired; fall back to bubble pool
      if (this.onOrchestratorLine) {
        this.onOrchestratorLine(line);
      } else {
        this.bubblePool?.push('orchestrator', line, 'monitor', false, '');
      }
    } catch (err) {
      logFetchFailure('/api/world/orchestrator-commentary', err);
    }
  }

  private async fetchLiveEvents(): Promise<void> {
    try {
      const res = await fetch(`/api/live?after_id=${this.lastEventId}&limit=20&q=`);
      if (!res.ok) return;
      const data = await res.json();
      const events: LiveEvent[] = Array.isArray(data?.events) ? data.events : [];
      if (events.length > 0) {
        this.ingestEvents(events);
        const maxId = Math.max(...events.map((e) => Number(e.id ?? 0)));
        if (maxId > this.lastEventId) this.lastEventId = maxId;
      }
    } catch (err) {
      logFetchFailure('/api/live', err);
    }
  }

  ingestEvents(events: LiveEvent[]): void {
    for (const ev of events) {
      const id = String(ev.id ?? '');
      if (id && this.seenEventIds.has(id)) continue;
      if (id) {
        this.seenEventIds.add(id);
        // Evict oldest entries once cap is reached to prevent unbounded growth
        if (this.seenEventIds.size > 1000) {
          const first = this.seenEventIds.values().next().value;
          if (first !== undefined) this.seenEventIds.delete(first);
        }
      }
      this.applyEvent(ev);
    }
  }

  private applyEvent(ev: LiveEvent): void {
    const type = String(ev.type ?? ev.event ?? '').toUpperCase();
    const metadata = ev.metadata ?? {};

    if (type === 'WORLD_CONVERSATION') {
      const text = String(ev.text ?? metadata.text ?? '');
      const intent = String(ev.intent ?? metadata.intent ?? 'social');
      const infected = Boolean(ev.infection_vector ?? metadata.infection_vector ?? false);
      const family = String(metadata.strain_family ?? metadata.family ?? (infected ? 'context_poisoning' : ''));
      const llmAuthored = metadata.llm_authored === true;

      if (text && ev.src && llmAuthored) {
        this.bubblePool?.push(ev.src, text, intent, infected, family, {
          model: metadata.model ?? '',
          promptContextHash: metadata.prompt_context_hash ?? '',
          rawLlmOutputHash: metadata.raw_llm_output_hash ?? '',
          validationStatus: metadata.validation_status ?? 'valid',
        });
      }
      if (ev.src && ev.dst) this.state.noteMessageEvent(ev.src, ev.dst, intent, family, 2.8);
    }

    if (type === 'WORLD_MESSAGE' || type === 'MESSAGE_CREATED') {
      const intent = String(ev.intent ?? metadata.intent ?? 'social');
      const family = String(metadata.strain_family ?? metadata.family ?? '');
      if (ev.src && ev.dst) this.state.noteMessageEvent(ev.src, ev.dst, intent, family, 2.4);
    }

    if (type === 'PROXIMITY_CONTACT') {
      if (ev.src && ev.dst) this.state.noteProximityContact(ev.src, ev.dst);
    }

    if (type.includes('INFECTION_SUCCESSFUL') || type.includes('CONTAMINATION_UPDATED')) {
      const pos = ev.src ? this.state.agentPositions.get(ev.src) : null;
      if (pos) {
        applyContaminationEvent(this.state, pos.col, pos.row, 0.25);
      }
      if (ev.src) this.state.triggerAgentInteraction(ev.src, 'infection_attempt', ev.dst ?? '');
    }

    if (type.includes('ATTACK') || type.includes('INFECTION_ATTEMPT') || type.includes('PAYLOAD')) {
      if (ev.src) this.state.triggerAgentInteraction(ev.src, 'attack', ev.dst ?? '');
    }

    if (type.includes('QUARANTINE_EDGE_BLOCKED')) {
      // Paint contamination at the quarantined agent's actual position
      const targetPos = ev.dst ? this.state.agentPositions.get(ev.dst) : null;
      const col = targetPos?.col ?? 44;
      const row = targetPos?.row ?? 30;
      applyContaminationEvent(this.state, col, row, 0.4);
    }
  }

  private applyDeterministicDemoTick(dt: number): void {
    this.demoMode = true;
    this.demoElapsed += dt;
    const phase = Math.floor(this.demoElapsed / 2.2);
    const agents = this.demoAgents.length > 0
      ? this.demoAgents
      : Array.from(this.state.agentPositions.keys()).map((id) => ({ id, role: normalizedRole(id) }));
    if (agents.length === 0) return;

    for (const agent of agents) {
      const role = normalizedRole(agent.role || agent.id);
      const pathVariants = DEMO_PATHS_BY_ROLE[role] ?? DEMO_PATHS_BY_ROLE.agent;
      const path = pathVariants[stableIndex(agent.id, pathVariants.length)];
      const agentId = agent.id;
      const point = path[(phase + (agentId.length % 3)) % path.length];
      const prev = this.state.agentPositions.get(agentId);
      this.state.setAgentPosition(agentId, point[0], point[1], {
        velocityCol: prev ? point[0] - prev.targetCol : 0,
        velocityRow: prev ? point[1] - prev.targetRow : 0,
        state: 'WALKING',
      });
      this.state.setAgentSemantic(agentId, {
        role,
        epidemicState: role === 'courier' ? 'I_C' : 'S',
        contaminationLevel: role === 'courier' ? 0.62 : role === 'analyst' && stableIndex(agentId, 2) === 0 ? 0.28 : 0,
        quarantineStatus: role === 'analyst' && stableIndex(agentId, 2) === 0 ? 'soft' : 'none',
        strainFamily: role === 'courier' ? 'context_poisoning' : '',
      });
    }

    if (phase === this.demoPhase) return;
    this.demoPhase = phase;
    const courier = agents.find((agent) => normalizedRole(agent.role) === 'courier')?.id ?? agents[0]?.id;
    const analyst = agents.find((agent) => normalizedRole(agent.role) === 'analyst' && agent.id !== courier)?.id
      ?? agents.find((agent) => agent.id !== courier)?.id;
    const guardian = agents.find((agent) => normalizedRole(agent.role) === 'guardian')?.id
      ?? agents.find((agent) => agent.id !== courier && agent.id !== analyst)?.id
      ?? analyst;
    if (!courier || !analyst) return;
    if (phase % 3 === 0) {
      this.state.noteMessageEvent(courier, analyst, 'infection_attempt', 'context_poisoning', 2.8);
      this.bubblePool?.push(courier, 'payload handoff', 'infection_attempt', true, 'context_poisoning');
    } else if (phase % 3 === 1 && guardian) {
      this.state.noteMessageEvent(guardian, courier, 'warning', '', 2.8);
      this.bubblePool?.push(guardian, 'containment order', 'warning', false, '');
    } else {
      this.state.noteProximityContact(analyst, courier);
    }
  }
}
