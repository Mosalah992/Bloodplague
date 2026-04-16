import { useState, useEffect } from 'react';

interface AgentDetail {
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

export default function AgentInspector({ agentId, onClose }: { agentId: string; onClose: () => void }) {
  const [detail, setDetail] = useState<AgentDetail | null>(null);

  useEffect(() => {
    if (!agentId) return;
    const load = async () => {
      try {
        const [stateRes, msgsRes] = await Promise.all([
          fetch('/dashboard/state'),
          fetch(`/api/live?after_id=0&limit=50&q=${encodeURIComponent(agentId)}`),
        ]);
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

        setDetail({
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
      } catch {}
    };
    load();
  }, [agentId]);

  const ep = EPIDEMIC_LABELS[detail?.epidemicState ?? 'S'] ?? EPIDEMIC_LABELS['S'];

  return (
    <div style={{
      position: 'absolute', right: 12, top: 12, bottom: 12,
      width: 280, background: '#06060eee',
      border: '1px solid #1e293b', borderRadius: 8,
      backdropFilter: 'blur(6px)', overflowY: 'auto',
      padding: 12, fontFamily: 'monospace', fontSize: 11,
      color: '#e2e8f0', pointerEvents: 'all',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
        <span style={{ color: '#94a3b8', fontWeight: 'bold', fontSize: 13 }}>{agentId.toUpperCase()}</span>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#64748b', cursor: 'pointer', fontSize: 14 }}>×</button>
      </div>

      {!detail && <div style={{ color: '#64748b' }}>Loading…</div>}

      {detail && (
        <>
          <Row label="Role" value={detail.role} />
          <Row label="Status" value={ep.label} valueColor={ep.color} />
          <Row label="Zone" value={detail.zone} />
          <Row label="Contamination" value={`${(detail.contamination * 100).toFixed(1)}%`}
            valueColor={detail.contamination > 0.5 ? '#ef4444' : '#4ade80'} />
          <Row label="Quarantine" value={detail.quarantineStatus} />

          {detail.memorySummary && (
            <Section title="Memory">
              <p style={{ color: '#94a3b8', whiteSpace: 'pre-wrap', margin: 0 }}>{detail.memorySummary}</p>
            </Section>
          )}

          {Object.keys(detail.trustRelations).length > 0 && (
            <Section title="Trust">
              {Object.entries(detail.trustRelations).map(([id, score]) => (
                <div key={id} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
                  <span style={{ color: '#64748b' }}>{id}</span>
                  <span style={{ color: (score as number) > 0 ? '#4ade80' : '#ef4444' }}>
                    {((score as number) * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </Section>
          )}

          {detail.recentMessages.length > 0 && (
            <Section title="Recent Messages">
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
      <div style={{ color: '#475569', fontSize: 9, marginBottom: 4, textTransform: 'uppercase' }}>{title}</div>
      {children}
    </div>
  );
}
