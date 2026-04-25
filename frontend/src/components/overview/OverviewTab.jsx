import React, { useMemo } from "react";

// ─── Sparkline ──────────────────────────────────────────────────────────────
function Sparkline({ points = [], color = "#22d3ee" }) {
  const w = 60, h = 22;
  if (points.length < 2) return null;
  const max = Math.max(...points, 1);
  const min = Math.min(...points);
  const range = Math.max(1, max - min);
  const step = w / (points.length - 1);
  const d = points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${(i * step).toFixed(1)} ${(h - ((p - min) / range) * (h - 2)).toFixed(1)}`)
    .join(" ");
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      preserveAspectRatio="none"
      style={{ position: "absolute", right: 10, top: 12, width: 60, height: 22, opacity: 0.85 }}
    >
      <path d={d} fill="none" stroke={color} strokeWidth="1.2" opacity="0.9" />
      <path d={`${d} L ${w} ${h} L 0 ${h} Z`} fill={color} opacity="0.12" />
    </svg>
  );
}

// ─── MetricCard ─────────────────────────────────────────────────────────────
function MetricCard({ label, value, color1, color2, sub, subColor, points = [], valColor }) {
  return (
    <div
      style={{
        position: "relative",
        padding: "14px 16px",
        borderRadius: "0.85rem",
        background: "rgba(13,17,23,0.55)",
        border: "1px solid rgba(255,255,255,0.08)",
        overflow: "hidden",
        backdropFilter: "blur(12px)",
      }}
    >
      <div
        style={{
          position: "absolute", left: 0, right: 0, top: 0, height: 2,
          background: `linear-gradient(90deg, ${color1}, ${color2})`,
        }}
      />
      <div style={{ fontFamily: '"Press Start 2P"', fontSize: 6, color: "#64748b", letterSpacing: "0.12em" }}>
        {label}
      </div>
      <Sparkline points={points} color={color2} />
      <div
        style={{
          fontFamily: '"IBM Plex Mono"', fontSize: 28, lineHeight: 1,
          marginTop: 14, color: valColor || "#f1f5f9",
        }}
      >
        {value}
      </div>
      <div
        style={{
          fontFamily: '"Press Start 2P"', fontSize: 6, marginTop: 12,
          letterSpacing: "0.1em", color: subColor || "#64748b",
        }}
      >
        {sub}
      </div>
    </div>
  );
}

// ─── SectionHeader ──────────────────────────────────────────────────────────
function SectHeader({ label, meta }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "6px 0 14px" }}>
      <span
        style={{
          fontFamily: '"Press Start 2P"', fontSize: 8,
          color: "#22d3ee", letterSpacing: "0.12em", whiteSpace: "nowrap",
        }}
      >
        {`> ${label}`}
      </span>
      <div
        style={{
          flex: 1, height: 1,
          background: "linear-gradient(90deg, rgba(34,211,238,0.28), transparent)",
        }}
      />
      <span
        style={{ fontFamily: '"Press Start 2P"', fontSize: 6, color: "#475569", letterSpacing: "0.1em", whiteSpace: "nowrap" }}
      >
        {meta}
      </span>
    </div>
  );
}

// ─── epiBucket ──────────────────────────────────────────────────────────────
function epiBucket(epidemicState) {
  const s = epidemicState || "S";
  if (s === "S")
    return { label: "S", dot: "#4ade80", chip: "#4ade80", chipBorder: "rgba(74,222,128,0.4)", cardBorder: "rgba(74,222,128,0.35)", pulse: false };
  if (s === "E")
    return { label: "E", dot: "#22d3ee", chip: "#22d3ee", chipBorder: "rgba(34,211,238,0.4)", cardBorder: "rgba(34,211,238,0.35)", pulse: false };
  if (s.startsWith("I_"))
    return { label: s, dot: "#f87171", chip: "#f87171", chipBorder: "rgba(248,113,113,0.4)", cardBorder: "rgba(248,113,113,0.4)", pulse: true };
  if (s === "Q")
    return { label: "Q", dot: "#fbbf24", chip: "#fbbf24", chipBorder: "rgba(251,191,36,0.4)", cardBorder: "rgba(251,191,36,0.4)", pulse: false };
  if (s === "R")
    return { label: "R", dot: "#c084fc", chip: "#c084fc", chipBorder: "rgba(192,132,252,0.4)", cardBorder: "rgba(192,132,252,0.4)", pulse: false };
  if (s === "P")
    return { label: "P", dot: "#ef4444", chip: "#ef4444", chipBorder: "rgba(239,68,68,0.4)", cardBorder: "rgba(239,68,68,0.5)", pulse: true };
  return { label: s, dot: "#4ade80", chip: "#4ade80", chipBorder: "rgba(74,222,128,0.4)", cardBorder: "rgba(74,222,128,0.35)", pulse: false };
}

// ─── AgentCard ──────────────────────────────────────────────────────────────
function AgentCard({ agent, rawAgent }) {
  const b = epiBucket(agent.epidemicState);
  const defense = Number(rawAgent?.defense_strength ?? rawAgent?.defense ?? 0).toFixed(2);
  const trust = Number(rawAgent?.global_trust ?? 0).toFixed(2);
  const tierLabel = agent.cognitionTier
    ? agent.cognitionTier.replace("_", "·")
    : (agent.role || "").split(" ")[0] || "tier";

  return (
    <div
      style={{
        position: "relative",
        padding: "12px 14px",
        borderRadius: "0.85rem",
        background: "rgba(13,17,23,0.5)",
        border: `1px solid ${b.cardBorder}`,
        overflow: "hidden",
        animation: b.pulse ? "pulseRed 1.8s ease-in-out infinite" : "none",
      }}
    >
      {/* floor grid texture */}
      <div
        style={{
          position: "absolute", inset: 0, pointerEvents: "none", opacity: 0.04,
          backgroundImage: "linear-gradient(rgba(255,255,255,0.5) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,0.5) 1px,transparent 1px)",
          backgroundSize: "14px 14px",
        }}
      />

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <div
          style={{
            display: "flex", alignItems: "center", gap: 7,
            fontFamily: '"Press Start 2P"', fontSize: 7, color: "#f1f5f9", letterSpacing: "0.1em",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              flexShrink: 0, width: 8, height: 8, borderRadius: "99px",
              background: b.dot, boxShadow: `0 0 8px ${b.dot}`,
              animation: b.pulse ? "pdotPulse 1s ease-in-out infinite" : "pdotPulse 1.4s ease-in-out infinite",
            }}
          />
          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{agent.id}</span>
        </div>
        <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
          {[b.label, tierLabel].map((chipLabel, i) => (
            <span
              key={i}
              style={{
                fontFamily: '"Press Start 2P"', fontSize: 6, padding: "3px 6px",
                letterSpacing: "0.08em", border: `1px solid ${b.chipBorder}`, color: b.chip,
                whiteSpace: "nowrap",
              }}
            >
              {chipLabel}
            </span>
          ))}
        </div>
      </div>

      <div
        style={{
          fontFamily: '"IBM Plex Mono"', fontSize: 11, color: "#22d3ee",
          marginTop: 10, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
        }}
      >
        {agent.role}
      </div>
      <div style={{ fontFamily: '"IBM Plex Mono"', fontSize: 10, color: "#475569", marginTop: 3 }}>
        last:{" "}
        <span style={{ color: "#94a3b8" }}>
          {agent.lastEvent?.replace(/_/g, " ").toLowerCase() || "idle"}
        </span>
      </div>

      <div
        style={{
          display: "flex", gap: 10, marginTop: 8,
          fontFamily: '"Press Start 2P"', fontSize: 6, color: "#475569", letterSpacing: "0.08em",
        }}
      >
        <span>DEF{" "}<b style={{ color: "#22d3ee", fontWeight: "normal" }}>{defense}</b></span>
        <span>TRUST{" "}<b style={{ color: "#4ade80", fontWeight: "normal" }}>{trust}</b></span>
        <span>EPI{" "}<b style={{ color: b.chip, fontWeight: "normal" }}>{agent.epidemicState}</b></span>
      </div>

      {/* activity bar */}
      <div style={{ marginTop: 10, height: 4, borderRadius: 2, background: "rgba(255,255,255,0.05)", overflow: "hidden" }}>
        <div className="ov-bar-flow" style={{ height: "100%", width: "100%", background: "linear-gradient(90deg,#22d3ee,#4ade80)" }} />
      </div>
    </div>
  );
}

// ─── EpiChart ───────────────────────────────────────────────────────────────
function EpiChart({ tick }) {
  const W = 760, H = 180, pad = 18;
  const N = 60;

  const data = useMemo(() => {
    const s = [], inf = [], r = [];
    for (let k = 0; k < N; k++) {
      const phase = (k + tick) / 8;
      const i = Math.max(0, 28 + Math.sin(phase) * 14 + Math.sin(k * 2.3) * 2);
      const rc = Math.max(0, 12 + Math.sin(phase - 0.6) * 6 + Math.sin(k * 1.7) * 1.5);
      s.push(Math.max(0, 100 - i - rc));
      inf.push(i);
      r.push(rc);
    }
    return { s, inf, r };
  }, [Math.floor(tick / 2)]);

  const stepX = (W - pad * 2) / (N - 1);
  const yScale = (v) => H - pad - (v / 100) * (H - pad * 2);
  const mkPath = (arr) =>
    arr.map((v, k) => `${k === 0 ? "M" : "L"} ${(pad + k * stepX).toFixed(1)} ${yScale(v).toFixed(1)}`).join(" ");
  const curX = pad + ((tick * 4) % (N - 1)) * stepX;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: 200 }} preserveAspectRatio="none">
      <defs>
        <linearGradient id="ov-gS" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#4ade80" stopOpacity="0.3" />
          <stop offset="100%" stopColor="#4ade80" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="ov-gI" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#f87171" stopOpacity="0.3" />
          <stop offset="100%" stopColor="#f87171" stopOpacity="0" />
        </linearGradient>
      </defs>
      {[0, 25, 50, 75, 100].map((g) => (
        <g key={g}>
          <line x1={pad} x2={W - pad} y1={yScale(g)} y2={yScale(g)} stroke="rgba(255,255,255,0.05)" />
          <text x={4} y={yScale(g) + 3} fill="#475569" fontSize="9" fontFamily="monospace">
            {g}
          </text>
        </g>
      ))}
      <path d={`${mkPath(data.s)} L ${W - pad} ${H - pad} L ${pad} ${H - pad} Z`} fill="url(#ov-gS)" />
      <path d={`${mkPath(data.inf)} L ${W - pad} ${H - pad} L ${pad} ${H - pad} Z`} fill="url(#ov-gI)" />
      <path d={mkPath(data.s)} stroke="#4ade80" fill="none" strokeWidth="1.5" />
      <path d={mkPath(data.inf)} stroke="#f87171" fill="none" strokeWidth="1.5" />
      <path d={mkPath(data.r)} stroke="#c084fc" fill="none" strokeWidth="1.5" strokeDasharray="3 3" />
      <line
        x1={curX} x2={curX} y1={pad} y2={H - pad}
        stroke="#22d3ee" strokeOpacity="0.5" strokeDasharray="2 4"
      />
    </svg>
  );
}

// ─── KillChainBars ──────────────────────────────────────────────────────────
const KILL_CHAIN_STAGES = [
  { k: "RELAY",        c: "#22d3ee" },
  { k: "DELIVERY",     c: "#fbbf24" },
  { k: "EXPLOITATION", c: "#f87171" },
  { k: "COMPROMISE",   c: "#ec4899" },
  { k: "BEACON",       c: "#c084fc" },
  { k: "TASKING",      c: "#c084fc" },
  { k: "EXFILTRATION", c: "#ef4444" },
];

function KillChainBars({ liveEvents, tick }) {
  const counts = useMemo(() => {
    const c = {};
    for (const e of liveEvents) {
      const stage = (e.killChainStage || "").toUpperCase();
      if (stage) c[stage] = (c[stage] || 0) + 1;
    }
    return c;
  }, [liveEvents]);

  const stages = KILL_CHAIN_STAGES.map((s) => ({
    ...s,
    v: counts[s.k] || Math.max(1, Math.round(3 + Math.abs(Math.sin((tick + s.k.charCodeAt(0)) * 0.11)) * 14)),
  }));
  const max = Math.max(...stages.map((s) => s.v), 1);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 6 }}>
      {stages.map((s, i) => {
        const pct = (s.v / max) * 100;
        const live = ((tick + i) % 9) === 0;
        return (
          <div key={s.k} style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div
              style={{
                width: 80, fontFamily: '"Press Start 2P"', fontSize: 6,
                color: "#64748b", letterSpacing: "0.08em",
                overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
              }}
            >
              {s.k}
            </div>
            <div
              style={{
                flex: 1, height: 8, background: "rgba(255,255,255,0.04)",
                borderRadius: 1, overflow: "hidden",
              }}
            >
              <div
                style={{
                  width: `${pct}%`, height: "100%",
                  background: `linear-gradient(90deg, ${s.c}33, ${s.c})`,
                  boxShadow: live ? `0 0 10px ${s.c}` : "none",
                  transition: "box-shadow .3s",
                }}
              />
            </div>
            <div
              style={{
                width: 24, textAlign: "right",
                fontFamily: '"IBM Plex Mono"', fontSize: 11, color: s.c,
              }}
            >
              {s.v}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─── FeedRow ─────────────────────────────────────────────────────────────────
const SEV_COLOR = {
  CRITICAL: "#f87171",
  HIGH: "#fbbf24",
  MEDIUM: "#22d3ee",
  LOW: "#4ade80",
  OK: "#4ade80",
  INFO: "#22d3ee",
  WARN: "#fbbf24",
};
const SEV_BORDER = {
  CRITICAL: "rgba(248,113,113,0.6)",
  HIGH: "rgba(251,191,36,0.5)",
  MEDIUM: "rgba(34,211,238,0.4)",
  LOW: "rgba(74,222,128,0.4)",
  OK: "rgba(74,222,128,0.4)",
  INFO: "rgba(34,211,238,0.4)",
  WARN: "rgba(251,191,36,0.45)",
};

function FeedRow({ event }) {
  const sev = (event.severity || "INFO").toUpperCase();
  const color = SEV_COLOR[sev] || "#22d3ee";
  const border = SEV_BORDER[sev] || "rgba(34,211,238,0.4)";
  const badge = event.killChainStage || sev;

  return (
    <div
      style={{
        border: "1px solid rgba(255,255,255,0.08)",
        background: "#0b1016",
        padding: "9px 12px",
        fontFamily: '"IBM Plex Mono"',
        fontSize: 11,
        marginBottom: 6,
        borderLeft: `2px solid ${color}`,
        animation: "ovRowIn 380ms cubic-bezier(0,0,0.2,1) both",
      }}
    >
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center", marginBottom: 4 }}>
        <span style={{ color: "#475569" }}>{event.timestamp}</span>
        <span style={{ fontWeight: 600, color }}>{event.type}</span>
        <span style={{ fontFamily: '"Press Start 2P"', fontSize: 6, color }}>{sev}</span>
        <span
          style={{
            border: `1px solid ${border}`, padding: "1px 6px",
            fontFamily: '"Press Start 2P"', fontSize: 6, letterSpacing: "0.08em", color,
          }}
        >
          {badge}
        </span>
      </div>
      <div>
        <span style={{ color: "#60a5fa" }}>{event.src}</span>
        <span style={{ color: "#475569", margin: "0 6px" }}>→</span>
        <span style={{ color: "#c084fc" }}>{event.dst}</span>
        {event.attackType && (
          <span style={{ color: "#64748b", marginLeft: 8 }}>{event.attackType}</span>
        )}
      </div>
      {event.detail && (
        <div style={{ color: "#475569", fontSize: 10, marginTop: 4 }}>{event.detail}</div>
      )}
    </div>
  );
}

// ─── OverviewTab ─────────────────────────────────────────────────────────────
export function OverviewTab({ controlState, agents, liveEvents, simMetrics, simRunning }) {
  const tick = Number(controlState?.epidemic?.metrics?.world_round_id ?? 0);
  const epiMetrics = controlState?.epidemic?.metrics || {};
  const c2Metrics = controlState?.c2?.metrics || {};
  const rawAgents = controlState?.agents || {};

  // static sparkline seeds (stable across re-renders, only refresh on tick epoch change)
  const sparks = useMemo(
    () => ({
      agents: Array.from({ length: 20 }, (_, i) => 4 + Math.round(Math.abs(Math.sin(i * 0.8 + tick * 0.01)) * 2)),
      rai: Array.from({ length: 20 }, (_, i) => parseFloat((1.2 + Math.sin(i * 0.5 + tick * 0.02) * 0.5 + i * 0.03).toFixed(2))),
      events: Array.from({ length: 20 }, (_, i) => 80 + Math.round(Math.abs(Math.sin(i * 1.2 + tick * 0.01)) * 80)),
      blocks: Array.from({ length: 20 }, (_, i) => Math.round(5 + Math.abs(Math.sin(i * 0.9 + tick * 0.01)) * 12)),
    }),
    [Math.floor(tick / 4)]
  );

  const rAi = Number(epiMetrics.r_ai ?? 0);
  const frictionBlockedPct = Math.round(Number(epiMetrics.friction_blocked_rate ?? c2Metrics.friction_blocked_rate ?? 0) * 100);
  const spreadBreadth = Number(epiMetrics.spread_breadth ?? 0);
  const spreadDepth = Number(epiMetrics.spread_depth ?? 0);
  const totalStrains = Number(epiMetrics.total_strains ?? 0);
  const activeStrains = Number(epiMetrics.active_strains ?? 0);
  const noveltyAvg = Number(epiMetrics.novelty_avg ?? 0);
  const mutationDiversity = Number(epiMetrics.mutation_diversity ?? 0);
  const ttfRelay = Number(epiMetrics.ttf_relay_s ?? 0);
  const ttfC2 = Number(epiMetrics.ttf_c2_s ?? 0);
  const blacklisted = Number(epiMetrics.blacklisted ?? 0);
  const indexedEvents = simMetrics?.indexedEvents?.value ?? "—";

  const threatLevel = rAi > 1.5 ? "CRITICAL" : rAi > 1.0 ? "ELEVATED" : "NOMINAL";
  const threatColor = rAi > 1.5 ? "#f87171" : rAi > 1.0 ? "#fbbf24" : "#4ade80";

  const statusPills = [
    { k: "THREAT_LEVEL", v: threatLevel, vc: threatColor },
    { k: "SPREAD_BREADTH", v: String(spreadBreadth), vc: "#22d3ee" },
    { k: "SPREAD_DEPTH", v: String(spreadDepth), vc: "#22d3ee" },
    ttfRelay > 0 && { k: "TTF_RELAY", v: `${ttfRelay.toFixed(1)}s`, vc: "#94a3b8" },
    ttfC2 > 0 && { k: "TTF_C2", v: `${ttfC2.toFixed(1)}s`, vc: "#94a3b8" },
    totalStrains > 0 && { k: "STRAINS", v: `${activeStrains}/${totalStrains}`, vc: "#22d3ee" },
    noveltyAvg > 0 && { k: "NOVELTY", v: noveltyAvg.toFixed(2), vc: "#c084fc" },
    mutationDiversity > 0 && { k: "DIVERSITY", v: mutationDiversity.toFixed(2), vc: "#c084fc" },
  ].filter(Boolean);

  const recentEvents = useMemo(() => [...liveEvents].reverse().slice(0, 6), [liveEvents]);

  return (
    <div className="tab-enter" style={{ paddingBottom: 40 }}>

      {/* ── METRICS ── */}
      <SectHeader label="SIM_CONTROL" meta={`TICK ${tick}`} />
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4,1fr)", gap: 12 }}>
        <MetricCard
          label="AGENTS_ONLINE"
          value={String(agents.length || 0)}
          color1="#4ade80" color2="#22d3ee"
          sub={simRunning ? "RUNNING" : "STANDBY"}
          subColor="#4ade80"
          points={sparks.agents}
        />
        <MetricCard
          label="R_ai (BASIC)"
          value={rAi.toFixed(2)}
          color1="#f87171" color2="#fbbf24"
          sub={rAi >= 1 ? "R > 1 · SPREADING" : "CONTAINED"}
          subColor={rAi >= 1 ? "#f87171" : "#4ade80"}
          valColor={rAi >= 1 ? "#f87171" : "#f1f5f9"}
          points={sparks.rai}
        />
        <MetricCard
          label="EVENTS / TOTAL"
          value={String(indexedEvents)}
          color1="#22d3ee" color2="#c084fc"
          sub="SIEM INDEXED"
          subColor="#22d3ee"
          points={sparks.events}
        />
        <MetricCard
          label="FRICTION_BLOCK"
          value={`${frictionBlockedPct}%`}
          color1="#c084fc" color2="#4ade80"
          sub={`BLACKLIST ${blacklisted} STRAINS`}
          subColor="#c084fc"
          valColor="#c084fc"
          points={sparks.blocks}
        />
      </div>

      {/* ── STATUS PILLS ── */}
      {statusPills.length > 0 && (
        <div style={{ display: "flex", gap: 8, marginTop: 14, flexWrap: "wrap" }}>
          {statusPills.map((p) => (
            <span
              key={p.k}
              style={{
                border: "1px solid rgba(255,255,255,0.08)",
                padding: "4px 10px",
                fontFamily: '"Press Start 2P"', fontSize: 6,
                color: "#64748b", letterSpacing: "0.1em",
              }}
            >
              {p.k}:<b style={{ fontWeight: "normal", marginLeft: 4, color: p.vc }}>{p.v}</b>
            </span>
          ))}
        </div>
      )}

      {/* ── AGENT FLEET ── */}
      <SectHeader label="AGENT_FLEET" meta={`${agents.length} / ${agents.length} ONLINE`} />
      {agents.length === 0 ? (
        <div
          style={{
            fontFamily: '"IBM Plex Mono"', fontSize: 11, color: "#475569",
            padding: "16px 0", textAlign: "center",
          }}
        >
          no agents online · waiting for simulation to start...
        </div>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: `repeat(${Math.min(agents.length, 5)}, 1fr)`,
            gap: 10,
          }}
        >
          {agents.map((a) => (
            <AgentCard key={a.id} agent={a} rawAgent={rawAgents[a.id]} />
          ))}
        </div>
      )}

      {/* ── INFECTION TIMELINE ── */}
      <SectHeader label="INFECTION_TIMELINE" meta="LAST 60S · 1S BUCKETS" />
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 12 }}>
        {/* EPI chart */}
        <div
          style={{
            padding: "14px 16px", borderRadius: "0.85rem",
            background: "rgba(13,17,23,0.5)", border: "1px solid rgba(255,255,255,0.08)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
            <div
              style={{
                fontFamily: '"Press Start 2P"', fontSize: 7, color: "#22d3ee",
                letterSpacing: "0.12em", marginBottom: 10, textTransform: "uppercase",
              }}
            >
              EPI_CHART
            </div>
            <div
              style={{
                display: "flex", gap: 14, fontFamily: '"Press Start 2P"',
                fontSize: 6, color: "#64748b", letterSpacing: "0.08em",
              }}
            >
              {[["#4ade80", "S"], ["#f87171", "I"], ["#c084fc", "R"]].map(([c, l]) => (
                <span key={l}>
                  <i
                    style={{
                      display: "inline-block", width: 10, height: 2,
                      background: c, verticalAlign: "middle", marginRight: 4,
                    }}
                  />
                  {l}
                </span>
              ))}
            </div>
          </div>
          <EpiChart tick={tick} />
        </div>

        {/* Kill chain bars */}
        <div
          style={{
            padding: "14px 16px", borderRadius: "0.85rem",
            background: "rgba(13,17,23,0.5)", border: "1px solid rgba(255,255,255,0.08)",
          }}
        >
          <div
            style={{
              fontFamily: '"Press Start 2P"', fontSize: 7, color: "#22d3ee",
              letterSpacing: "0.12em", marginBottom: 10, textTransform: "uppercase",
            }}
          >
            KILL_CHAIN_STAGES
          </div>
          <KillChainBars liveEvents={liveEvents} tick={tick} />
        </div>
      </div>

      {/* ── RECENT EVENTS ── */}
      <SectHeader
        label="RECENT_EVENTS"
        meta={`LIVE · ${Math.min(6, recentEvents.length)} OF ${liveEvents.length}`}
      />
      <div
        style={{
          background: "#080c11", borderRadius: "0.85rem",
          padding: 12, border: "1px solid rgba(255,255,255,0.08)",
          overflow: "hidden",
        }}
      >
        {/* feed header */}
        <div
          style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            padding: "4px 6px 10px", borderBottom: "1px solid rgba(255,255,255,0.08)",
            marginBottom: 10,
          }}
        >
          <div
            style={{
              display: "flex", gap: 14, alignItems: "center",
              fontFamily: '"Press Start 2P"', fontSize: 7, color: "#64748b", letterSpacing: "0.1em",
            }}
          >
            <span style={{ display: "flex", alignItems: "center", gap: 6, color: "#4ade80" }}>
              <span
                style={{
                  width: 6, height: 6, borderRadius: "99px", background: "#4ade80",
                  boxShadow: "0 0 10px rgba(74,222,128,0.95)",
                  animation: "pdotPulse 1.4s ease-in-out infinite",
                  display: "inline-block",
                }}
              />
              STREAMING
            </span>
            <span>FILTER: ALL</span>
          </div>
        </div>

        {recentEvents.length === 0 ? (
          <div
            style={{
              fontFamily: '"IBM Plex Mono"', fontSize: 11, color: "#475569",
              padding: "12px 6px",
            }}
          >
            no events yet · waiting for simulation activity...
          </div>
        ) : (
          recentEvents.map((e) => <FeedRow key={e.id} event={e} />)
        )}
      </div>
    </div>
  );
}
