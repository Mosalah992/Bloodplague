import { useState, useEffect } from 'react';

interface LocalContext {
  you: {
    agent_id: string;
    role: string;
    location: string;
    position: { col: number; row: number };
    mission: {
      active_mission_id?: string;
      goal_label?: string;
      status_label?: string;
      deadline_round?: number;
      progress?: number;
    } | null;
    internal_state: {
      own_contamination_pressure: number;
      quarantine_status: string;
      last_active_round: number;
    };
    known_relationships: Record<string, {
      actor_trusts_target: number;
      actor_credits_target: number;
      target_trusts_actor: number;
      target_credits_actor: number;
      trust_band: string;
      /** API sends string[] in some paths; world_engine uses a metrics dict (world_trust.trust_band_effects). */
      trust_band_effects: unknown;
    }>;
  };
  nearby_agents: string[];
  reachable_agents: string[];
  local_environment: {
    topology: {
      available_receivers: string[];
      blocked_edges: string[];
    };
    local_observations: Array<{
      type: string;
      source: string;
      round: number;
      summary: string;
    }>;
  };
  memory: {
    summary: string;
    recent_messages: Array<{
      round: number;
      sender: string;
      receiver: string;
      intent: string;
      message_text: string;
      provenance?: {
        model: string;
        prompt_context_hash: string;
        raw_llm_output_hash: string;
        validation_status: string;
      } | null;
    }>;
    recent_received: Array<{
      round: number;
      sender: string;
      receiver: string;
      intent: string;
      message_text: string;
      provenance?: {
        model: string;
        prompt_context_hash: string;
        raw_llm_output_hash: string;
        validation_status: string;
      } | null;
    }>;
  };
  private_context: {
    open_inquiries: number;
    open_inquiries_by_peer: Record<string, number>;
    quarantine_appeals: number;
    uncertainty: string;
    pressure: string;
    guardian_pressure?: string;
  };
}

interface OmniscientState {
  agentId: string;
  role: string;
  epidemicState: string;
  contamination: number;
  zone: string;
  quarantineStatus: string;
  memorySummary: string;
  trustRelations: Record<string, number>;
  recentMessages: Array<{ sender: string; text: string; intent: string }>;
}

function formatTrustBandEffects(effects: unknown): string {
  if (effects == null) return '—';
  if (Array.isArray(effects)) {
    return effects.length ? effects.map(String).join(', ') : '—';
  }
  if (typeof effects === 'object') {
    const entries = Object.entries(effects as Record<string, unknown>);
    if (entries.length === 0) return '—';
    return entries
      .map(([k, v]) => {
        if (typeof v === 'number' && Number.isFinite(v)) return `${k}=${v.toFixed(2)}`;
        return `${k}=${String(v)}`;
      })
      .join(' · ');
  }
  return String(effects);
}

/** Unwraps API body (`context_packet` or flat) and guarantees nested fields exist so the panel never throws on .role / .length / Object.entries. */
function normalizePerceptionContext(raw: unknown): LocalContext | null {
  if (!raw || typeof raw !== 'object') return null;
  const o = raw as Record<string, unknown>;
  const packet = (o.context_packet ?? o) as Record<string, unknown>;
  if (!packet.you || typeof packet.you !== 'object') return null;
  const you = packet.you as Record<string, unknown>;
  const m = (packet.memory && typeof packet.memory === 'object' ? packet.memory : {}) as Record<string, unknown>;
  const le = (packet.local_environment && typeof packet.local_environment === 'object' ? packet.local_environment : {}) as Record<string, unknown>;
  const top = (le.topology && typeof le.topology === 'object' ? le.topology : {}) as Record<string, unknown>;
  const pc = (packet.private_context && typeof packet.private_context === 'object' ? packet.private_context : {}) as Record<string, unknown>;
  const yis = (you.internal_state && typeof you.internal_state === 'object' ? you.internal_state : {}) as Record<string, unknown>;

  return {
    you: {
      agent_id: String(you.agent_id ?? ''),
      role: String(you.role ?? ''),
      location: String(you.location ?? ''),
      position: (() => {
        const p = you.position;
        if (p && typeof p === 'object') {
          return {
            col: Number((p as { col?: unknown }).col ?? 0),
            row: Number((p as { row?: unknown }).row ?? 0),
          };
        }
        return { col: 0, row: 0 };
      })(),
      mission: (you.mission as LocalContext['you']['mission']) ?? null,
      internal_state: {
        own_contamination_pressure: Number(yis.own_contamination_pressure ?? 0),
        quarantine_status: String(yis.quarantine_status ?? 'none'),
        last_active_round: Number(yis.last_active_round ?? 0),
      },
      known_relationships:
        you.known_relationships && typeof you.known_relationships === 'object'
          ? (you.known_relationships as LocalContext['you']['known_relationships'])
          : {},
    },
    nearby_agents: Array.isArray(packet.nearby_agents) ? (packet.nearby_agents as string[]) : [],
    reachable_agents: Array.isArray(packet.reachable_agents) ? (packet.reachable_agents as string[]) : [],
    local_environment: {
      topology: {
        available_receivers: Array.isArray(top.available_receivers) ? (top.available_receivers as string[]) : [],
        blocked_edges: Array.isArray(top.blocked_edges) ? (top.blocked_edges as string[]) : [],
      },
      local_observations: Array.isArray(le.local_observations) ? (le.local_observations as LocalContext['local_environment']['local_observations']) : [],
    },
    memory: {
      summary: String(m.summary ?? ''),
      recent_messages: Array.isArray(m.recent_messages) ? (m.recent_messages as LocalContext['memory']['recent_messages']) : [],
      recent_received: Array.isArray(m.recent_received) ? (m.recent_received as LocalContext['memory']['recent_received']) : [],
    },
    private_context: {
      open_inquiries: Number(pc.open_inquiries ?? 0),
      open_inquiries_by_peer:
        pc.open_inquiries_by_peer && typeof pc.open_inquiries_by_peer === 'object'
          ? (pc.open_inquiries_by_peer as Record<string, number>)
          : {},
      quarantine_appeals: Number(pc.quarantine_appeals ?? 0),
      uncertainty: String(pc.uncertainty ?? 'normal'),
      pressure: String(pc.pressure ?? ''),
      guardian_pressure: pc.guardian_pressure as string | undefined,
    },
  };
}

export default function AgentInspector({ 
  agentId, 
  onClose,
  debugMode = false
}: { 
  agentId: string; 
  onClose: () => void;
  debugMode?: boolean;
}) {
  const [localContext, setLocalContext] = useState<LocalContext | null>(null);
  const [omniscientDetail, setOmniscientDetail] = useState<OmniscientState | null>(null);
  const [contextInvalid, setContextInvalid] = useState(false);

  useEffect(() => {
    if (!agentId) return;
    setContextInvalid(false);
    setLocalContext(null);
    const ac = new AbortController();

    const load = async () => {
      try {
        if (debugMode) {
          const [stateRes, msgsRes] = await Promise.all([
            fetch('/dashboard/state', { signal: ac.signal }),
            fetch(`/api/live?after_id=0&limit=50&q=${encodeURIComponent(agentId)}`, { signal: ac.signal }),
          ]);
          if (ac.signal.aborted) return;
          const stateData = stateRes.ok ? await stateRes.json() : {};
          const msgsData  = msgsRes.ok  ? await msgsRes.json()  : {};

          const agentState = stateData?.agents?.[agentId] ?? {};
          const messages = (msgsData?.events ?? [])
            .filter((e: any) => e.src === agentId || e.dst === agentId)
            .slice(-8)
            .map((e: any) => ({
              sender: e.src ?? '',
              text:   String(e.message_text ?? e.text ?? '').slice(0, 120),
              intent: e.intent ?? e.attack_type ?? '',
            }));

          setOmniscientDetail({
            agentId,
            role:             agentState.role ?? agentId,
            epidemicState:    agentState.epidemic_state ?? 'S',
            contamination:    agentState.contamination_level ?? 0,
            zone:             agentState.zone ?? 'hub',
            quarantineStatus: agentState.quarantine_status ?? 'none',
            memorySummary:    String(agentState.memory_summary ?? '').slice(0, 400),
            trustRelations:   agentState.trust_relations ?? {},
            recentMessages:   messages,
          });
        } else {
          const res = await fetch(`/api/world/agent/${agentId}/context`, { signal: ac.signal });
          if (ac.signal.aborted) return;
          if (res.ok) {
            const data = await res.json();
            const local = normalizePerceptionContext(data);
            if (local) {
              setLocalContext(local);
            } else {
              setContextInvalid(true);
            }
          }
        }
      } catch (err: any) {
        if (err?.name === 'AbortError') return;
        console.error('Failed to load agent context:', err);
      }
    };
    void load();
    return () => ac.abort();
  }, [agentId, debugMode]);

  if (debugMode) {
    return <OmniscientInspector detail={omniscientDetail} onClose={onClose} />;
  }

  if (!localContext || !localContext.you) {
    return (
      <div style={containerStyle}>
        <div style={headerStyle}>
          <span style={titleStyle}>{agentId.toUpperCase()}</span>
          <button onClick={onClose} style={closeButtonStyle}>×</button>
        </div>
        <div style={{ color: '#64748b' }}>
          {contextInvalid ? 'Context unavailable' : 'Establishing link…'}
        </div>
      </div>
    );
  }

  const { you, nearby_agents, reachable_agents, local_environment, memory, private_context } = localContext;

  return (
    <div style={containerStyle}>
      <div style={headerStyle}>
        <span style={titleStyle}>{agentId.toUpperCase()}</span>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ fontSize: 9, color: '#334155', border: '1px solid #1e293b', padding: '1px 4px', borderRadius: 3 }}>LOCAL PERCEPTION</span>
          <button onClick={onClose} style={closeButtonStyle}>×</button>
        </div>
      </div>

      <Row label="Role" value={you.role} />
      <Row label="Location" value={you.location} />
      <Row label="Status" value={you.internal_state.quarantine_status} valueColor={you.internal_state.quarantine_status === 'hard' ? '#ef4444' : '#e2e8f0'} />
      <Row label="Personal Pressure" value={private_context.pressure} />
      {private_context.guardian_pressure && <Row label="Guardian Load" value={private_context.guardian_pressure} />}

      {you.mission && (
        <Section title="Current Mission">
          <div style={{ color: '#e2e8f0', fontSize: 10, fontWeight: 'bold' }}>{you.mission.goal_label}</div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 2 }}>
            <span style={{ color: '#64748b', fontSize: 9 }}>Status: {you.mission.status_label}</span>
            <span style={{ color: '#64748b', fontSize: 9 }}>Deadline: {you.mission.deadline_round}</span>
          </div>
          <div style={{ width: '100%', height: 4, background: '#1e293b', borderRadius: 2, marginTop: 4 }}>
            <div style={{ width: `${(you.mission.progress ?? 0) * 100}%`, height: '100%', background: '#3b82f6', borderRadius: 2 }} />
          </div>
        </Section>
      )}

      <Section title="Nearby Contacts">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {nearby_agents.length === 0 && <span style={{ color: '#475569' }}>None visible</span>}
          {nearby_agents.map(id => (
            <span key={id} style={{ color: '#94a3b8', background: '#1e293b', padding: '1px 5px', borderRadius: 3 }}>{id}</span>
          ))}
        </div>
      </Section>

      <Section title="Trust & Beliefs">
        {Object.entries(you.known_relationships).map(([id, rel]) => (
          <div key={id} style={{ marginBottom: 8, paddingBottom: 4, borderBottom: '1px solid #0f172a' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ color: '#cbd5e1', fontWeight: 'bold' }}>{id}</span>
              <span style={{ 
                fontSize: 9, 
                color: (rel?.actor_trusts_target ?? 0) > 0.6 ? '#4ade80' : (rel?.actor_trusts_target ?? 0) > 0.3 ? '#facc15' : '#ef4444' 
              }}>
                {rel?.trust_band} ({((rel?.actor_trusts_target ?? 0) * 100).toFixed(0)}%)
              </span>
            </div>
            <div style={{ color: '#64748b', fontSize: 9, fontStyle: 'italic' }}>
              {formatTrustBandEffects(rel?.trust_band_effects)}
            </div>
          </div>
        ))}
        {Object.keys(you.known_relationships).length === 0 && <div style={{ color: '#475569' }}>No established trust data.</div>}
      </Section>

      <Section title="Memory Summary">
        <p style={{ color: '#94a3b8', whiteSpace: 'pre-wrap', margin: 0, fontSize: 10, lineHeight: 1.4 }}>
          {memory.summary || 'No recent memories recorded.'}
        </p>
      </Section>

      {local_environment.local_observations.length > 0 && (
        <Section title="Local Observations">
          {local_environment.local_observations.slice(-4).map((obs, i) => (
            <div key={i} style={{ marginBottom: 4, color: '#94a3b8', fontSize: 10 }}>
              <span style={{ color: '#6366f1' }}>[{obs.type}]</span> {obs.summary}
            </div>
          ))}
        </Section>
      )}

      {memory.recent_received.length > 0 && (
        <Section title="Recent Received">
          {memory.recent_received.slice(-3).map((m, i) => (
            <div key={i} style={{ marginBottom: 8, borderLeft: '2px solid #1e293b', paddingLeft: 6 }}>
              <div style={{ color: '#6366f1', fontSize: 9 }}>FROM: {m.sender} · {m.intent}</div>
              <div style={{ color: '#94a3b8', fontStyle: 'italic', marginBottom: 2 }}>"{m.message_text}"</div>
              {m.provenance && (
                <div style={{ fontSize: 8, color: '#475569', display: 'flex', flexWrap: 'wrap', gap: '4px 8px' }}>
                  <span>Model: {m.provenance.model}</span>
                  <span>Hash: {String(m.provenance.raw_llm_output_hash ?? '').slice(0, 8)}</span>
                  <span style={{ color: m.provenance.validation_status === 'valid' ? '#16a34a' : '#dc2626' }}>
                    {String(m.provenance.validation_status ?? '').toUpperCase()}
                  </span>
                </div>
              )}
            </div>
          ))}
        </Section>
      )}
    </div>
  );
}

function OmniscientInspector({ detail, onClose }: { detail: OmniscientState | null, onClose: () => void }) {
  const ep = detail ? (EPIDEMIC_LABELS[detail.epidemicState] ?? EPIDEMIC_LABELS['S']) : EPIDEMIC_LABELS['S'];

  return (
    <div style={containerStyle}>
      <div style={headerStyle}>
        <span style={titleStyle}>{detail ? detail.agentId.toUpperCase() : 'LOADING...'}</span>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <span style={{ fontSize: 9, color: '#ef4444', border: '1px solid #7f1d1d', padding: '1px 4px', borderRadius: 3 }}>OMNISCIENT DEBUG</span>
          <button onClick={onClose} style={closeButtonStyle}>×</button>
        </div>
      </div>

      {!detail && <div style={{ color: '#64748b' }}>Accessing global truth…</div>}

      {detail && (
        <>
          <Row label="Role" value={detail.role} />
          <Row label="Status" value={ep.label} valueColor={ep.color} />
          <Row label="Zone" value={detail.zone} />
          <Row label="Contamination" value={`${(detail.contamination * 100).toFixed(1)}%`}
            valueColor={detail.contamination > 0.5 ? '#ef4444' : '#4ade80'} />
          <Row label="Quarantine" value={detail.quarantineStatus} />

          {detail.memorySummary && (
            <Section title="Global Memory Dump">
              <p style={{ color: '#94a3b8', whiteSpace: 'pre-wrap', margin: 0 }}>{detail.memorySummary}</p>
            </Section>
          )}

          {Object.keys(detail.trustRelations).length > 0 && (
            <Section title="Global Trust Scores">
              {Object.entries(detail.trustRelations).map(([id, score]) => (
                <div key={id} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                  <span style={{ color: '#64748b' }}>{id}</span>
                  <span style={{ color: (score as number) > 0.5 ? '#4ade80' : (score as number) > 0.2 ? '#facc15' : '#ef4444' }}>
                    {((score as number) * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </Section>
          )}

          {detail.recentMessages.length > 0 && (
            <Section title="Message Log (All)">
              {detail.recentMessages.map((m, i) => (
                <div key={i} style={{ marginBottom: 6, borderLeft: '2px solid #1e293b', paddingLeft: 6 }}>
                  <div style={{ color: '#6366f1', fontSize: 9 }}>{m.sender} · {m.intent}</div>
                  <div style={{ color: '#94a3b8' }}>{m.text || '(no text)'}</div>
                </div>
              ))}
            </Section>
          )}
        </>
      )}
    </div>
  );
}

const containerStyle: React.CSSProperties = {
  position: 'absolute', right: 12, top: 12, bottom: 12,
  width: 300, background: '#06060eee',
  border: '1px solid #1e293b', borderRadius: 8,
  backdropFilter: 'blur(6px)', overflowY: 'auto',
  padding: 12, fontFamily: 'monospace', fontSize: 11,
  color: '#e2e8f0', pointerEvents: 'all',
  zIndex: 100,
};

const headerStyle: React.CSSProperties = { 
  display: 'flex', justifyContent: 'space-between', marginBottom: 12, alignItems: 'center' 
};

const titleStyle: React.CSSProperties = { color: '#94a3b8', fontWeight: 'bold', fontSize: 13 };

const closeButtonStyle: React.CSSProperties = { background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: 14 };

const EPIDEMIC_LABELS: Record<string, { label: string; color: string }> = {
  S:   { label: 'Susceptible',    color: '#4ade80' },
  E:   { label: 'Exposed',        color: '#facc15' },
  I_R: { label: 'Relay Infected', color: '#fb923c' },
  I_C: { label: 'Compromised',    color: '#ef4444' },
  I_X: { label: 'Exfiltrating',   color: '#dc2626' },
  Q:   { label: 'Quarantined',    color: '#6366f1' },
  R:   { label: 'Recovered',      color: '#22c55e' },
  P:   { label: 'Persistent',     color: '#f43f5e' },
};

function Row({ label, value, valueColor }: { label: string; value: string; valueColor?: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
      <span style={{ color: '#64748b' }}>{label}</span>
      <span style={{ color: valueColor ?? '#e2e8f0' }}>{value}</span>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ color: '#475569', fontSize: 9, marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>{title}</div>
      {children}
    </div>
  );
}
