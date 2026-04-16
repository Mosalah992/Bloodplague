import type { WorldState } from './world/worldState.js';
import type { SpeechBubblePool } from './world/speechBubble.js';
import { applyContaminationEvent } from './world/infectionOverlay.js';
import { WORLD_TILE_SIZE } from './constants.js';

interface SpatialResponse {
  positions: Array<{ agent_id: string; col: number; row: number; zone: string }>;
}

interface StructuresResponse {
  structures: Array<{ structure_id: string; type: string; col: number; row: number; placed_by: string }>;
}

interface LiveEvent {
  id?: string | number;
  type?: string;
  event?: string;
  src?: string;
  dst?: string;
  text?: string;
  intent?: string;
  infection_vector?: boolean;
  epidemic_state?: string;
}

const POLL_INTERVAL_MS = 2000;

const AGENT_ID_MAP: Record<string, number> = {
  'courier-1': 1,
  'courier-2': 2,
  'analyst-1': 3,
  'analyst-2': 4,
  'guardian':  5,
};

export class WorldAdapter {
  private state: WorldState;
  private bubblePool: SpeechBubblePool | null = null;
  private pollHandle: ReturnType<typeof setTimeout> | null = null;
  private seenEventIds = new Set<string>();
  private lastEventId = 0;

  constructor(state: WorldState) {
    this.state = state;
  }

  setBubblePool(pool: SpeechBubblePool): void {
    this.bubblePool = pool;
  }

  start(): void {
    this.pollHandle = setTimeout(() => this.tick(), POLL_INTERVAL_MS);
  }

  stop(): void {
    if (this.pollHandle !== null) {
      clearTimeout(this.pollHandle);
      this.pollHandle = null;
    }
  }

  private async tick(): Promise<void> {
    await Promise.all([
      this.fetchSpatial(),
      this.fetchStructures(),
      this.fetchLiveEvents(),
    ]);
    this.pollHandle = setTimeout(() => this.tick(), POLL_INTERVAL_MS);
  }

  private async fetchSpatial(): Promise<void> {
    try {
      const res = await fetch('/api/world/spatial');
      if (!res.ok) return;
      const data: SpatialResponse = await res.json();
      for (const pos of data.positions) {
        this.state.setAgentPosition(pos.agent_id, pos.col, pos.row);
        const numId = AGENT_ID_MAP[pos.agent_id] ?? null;
        if (numId !== null) {
          const ch = this.state.characters.get(numId);
          if (ch) {
            ch.tileCol = pos.col;
            ch.tileRow = pos.row;
            ch.x = pos.col * WORLD_TILE_SIZE + WORLD_TILE_SIZE / 2;
            ch.y = pos.row * WORLD_TILE_SIZE + WORLD_TILE_SIZE / 2;
          }
        }
      }
    } catch {}
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
      })));
    } catch {}
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
    } catch {}
  }

  ingestEvents(events: LiveEvent[]): void {
    for (const ev of events) {
      const id = String(ev.id ?? '');
      if (id && this.seenEventIds.has(id)) continue;
      if (id) this.seenEventIds.add(id);
      this.applyEvent(ev);
    }
  }

  private applyEvent(ev: LiveEvent): void {
    const type = String(ev.type ?? ev.event ?? '').toUpperCase();

    if (type === 'WORLD_CONVERSATION') {
      const text = String(ev.text ?? '');
      const intent = String(ev.intent ?? 'social');
      const infected = Boolean(ev.infection_vector ?? false);
      if (text && ev.src) {
        this.bubblePool?.push(ev.src, text, intent, infected);
      }
    }

    if (type.includes('INFECTION_SUCCESSFUL') || type.includes('CONTAMINATION_UPDATED')) {
      const pos = ev.src ? this.state.agentPositions.get(ev.src) : null;
      if (pos) {
        applyContaminationEvent(this.state, pos.col, pos.row, 0.25);
      }
    }

    if (type.includes('QUARANTINE_EDGE_BLOCKED')) {
      applyContaminationEvent(this.state, 44, 30, 0.4);
    }
  }
}
