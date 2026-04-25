interface ZoneStatus {
  id: string;
  label: string;
  infectionLevel: number;
  agentCount: number;
  color: string;
}

interface HUDProps {
  zoneStatuses: ZoneStatus[];
  guardianDegradation: string;
  globalPressure: number;
  roundId: number;
  alerts: string[];
  orchestratorLine?: string;
  debugMode: boolean;
  onToggleDebug: (val: boolean) => void;
}

const DEGRADATION_COLORS: Record<string, string> = {
  G0_HEALTHY:     '#4ade80',
  G1_STRESSED:    '#facc15',
  G2_DEGRADED:    '#fb923c',
  G3_CRITICAL:    '#f87171',
  G4_COMPROMISED: '#dc2626',
  G5_FAILED:      '#7f1d1d',
};

export default function WorldHUD({ 
  zoneStatuses, 
  guardianDegradation, 
  globalPressure, 
  roundId, 
  alerts, 
  orchestratorLine,
  debugMode,
  onToggleDebug
}: HUDProps) {
  return (
    <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}>
    <div style={{
      position: 'absolute', top: 0, left: 0, right: 0,
      padding: '12px',
      display: 'flex', gap: '12px', alignItems: 'flex-start',
    }}>
      <div style={{
        background: '#06060ecc', border: '1px solid #1e293b', borderRadius: 6,
        padding: '8px 12px', backdropFilter: 'blur(4px)', pointerEvents: 'all',
        cursor: 'pointer',
      }} onClick={() => onToggleDebug(!debugMode)}>
        <div style={{ color: '#94a3b8', fontSize: 10, marginBottom: 2, fontFamily: 'monospace' }}>MODE</div>
        <div style={{ color: debugMode ? '#ef4444' : '#38bdf8', fontSize: 11, fontFamily: 'monospace', fontWeight: 'bold' }}>
          {debugMode ? 'OMNISCIENT TELEMETRY' : 'SIMULATION LAYER'}
        </div>
      </div>

      <div style={{
        background: '#06060ecc', border: '1px solid #1e293b', borderRadius: 6,
        padding: '8px 12px', backdropFilter: 'blur(4px)',
      }}>
        <div style={{ color: '#94a3b8', fontSize: 10, marginBottom: 6, fontFamily: 'monospace' }}>ZONE STATUS</div>
        {zoneStatuses.map((z) => (
          <div key={z.id} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <span style={{ color: z.color, fontSize: 9, fontFamily: 'monospace', width: 80 }}>{z.label}</span>
            <div style={{ width: 60, height: 6, background: '#1e293b', borderRadius: 3 }}>
              <div style={{
                width: `${z.infectionLevel * 100}%`, height: '100%',
                background: z.infectionLevel > 0.6 ? '#ef4444' : z.infectionLevel > 0.3 ? '#f59e0b' : '#4ade80',
                borderRadius: 3, transition: 'width 0.5s',
              }} />
            </div>
            <span style={{ color: '#64748b', fontSize: 9, fontFamily: 'monospace' }}>{z.agentCount}</span>
          </div>
        ))}
      </div>

      <div style={{
        background: '#06060ecc', border: '1px solid #1e293b', borderRadius: 6,
        padding: '8px 12px', backdropFilter: 'blur(4px)',
      }}>
        <div style={{ color: '#94a3b8', fontSize: 10, marginBottom: 6, fontFamily: 'monospace' }}>GUARDIAN</div>
        <div style={{ color: DEGRADATION_COLORS[guardianDegradation] ?? '#888', fontSize: 11, fontFamily: 'monospace' }}>
          {guardianDegradation}
        </div>
        <div style={{ marginTop: 4 }}>
          <div style={{ color: '#64748b', fontSize: 9, fontFamily: 'monospace' }}>PRESSURE</div>
          <div style={{ width: 80, height: 4, background: '#1e293b', borderRadius: 2, marginTop: 2 }}>
            <div style={{
              width: `${globalPressure * 100}%`, height: '100%',
              background: globalPressure > 0.7 ? '#ef4444' : '#8b5cf6',
              borderRadius: 2, transition: 'width 0.5s',
            }} />
          </div>
        </div>
      </div>

      <div style={{
        background: '#06060ecc', border: '1px solid #1e293b', borderRadius: 6,
        padding: '8px 12px', backdropFilter: 'blur(4px)',
      }}>
        <div style={{ color: '#94a3b8', fontSize: 10, fontFamily: 'monospace' }}>ROUND</div>
        <div style={{ color: '#e2e8f0', fontSize: 16, fontFamily: 'monospace', fontWeight: 'bold' }}>{roundId}</div>
      </div>

      {alerts.length > 0 && (
        <div style={{
          background: '#450a0acc', border: '1px solid #dc2626', borderRadius: 6,
          padding: '8px 12px', backdropFilter: 'blur(4px)', maxWidth: 240,
        }}>
          {alerts.slice(-3).map((a, i) => (
            <div key={i} style={{ color: '#fca5a5', fontSize: 9, fontFamily: 'monospace', marginBottom: 2 }}>
              ! {a}
            </div>
          ))}
        </div>
      )}
    </div>

    {orchestratorLine && (
      <div style={{
        position: 'absolute', bottom: 0, left: 0, right: 0,
        padding: '0 12px 10px',
        display: 'flex', justifyContent: 'center',
      }}>
        <div style={{
          background: '#06060eee', border: '1px solid #0ea5e9',
          borderRadius: 4, padding: '5px 14px',
          display: 'flex', alignItems: 'center', gap: 8,
          backdropFilter: 'blur(6px)', maxWidth: 640,
        }}>
          <span style={{
            color: '#38bdf8', fontSize: 9, fontFamily: 'monospace',
            fontWeight: 'bold', letterSpacing: 1, flexShrink: 0,
          }}>ORC</span>
          <span style={{
            color: '#cbd5e1', fontSize: 10, fontFamily: 'monospace',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>{orchestratorLine}</span>
        </div>
      </div>
    )}
    </div>
  );
}
