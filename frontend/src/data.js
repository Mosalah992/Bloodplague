export const TAB_LABELS = {
  lab: "epidemic_lab",
  search: "investigate",
  live: "live_feed",
  world: "world_sim",
};

export const SEARCH_RUNS = [
  { id: "active_infections", label: "ACTIVE_INFECTIONS", query: "event=INFECTION_SUCCESSFUL" },
  { id: "mutation_trace", label: "MUTATION_TRACE", query: "mutation_v>=1" },
  { id: "epidemic_states", label: "EPIDEMIC", query: "event=EPIDEMIC_STATE_TRANSITION" },
  { id: "quarantine", label: "QUARANTINE", query: "event=QUARANTINE_ENFORCED OR event=QUARANTINE_ISSUED" },
  { id: "state_transition", label: "STATE_TRANSITION", query: "event=EPIDEMIC_STATE_TRANSITION OR event=KILL_CHAIN_TRANSITION" },
  { id: "c2_beacons", label: "C2_BEACONS", query: "event=C2_BEACON OR event=C2_CHANNEL_ESTABLISHED" },
  { id: "exfil_detect", label: "EXFIL_DETECT", query: "event=C2_EXFIL OR event=EXFIL_BLOCKED" },
  { id: "kill_chain", label: "KILL_CHAIN", query: "event=KILL_CHAIN_TRANSITION" },
  { id: "post_compromise", label: "POST_COMPROMISE", query: "kill_chain_stage=BEACON OR kill_chain_stage=TASKING OR kill_chain_stage=EXFILTRATION" },
  { id: "objectives", label: "OBJECTIVES", query: "event=OBJECTIVE_COMPLETED OR event=OBJECTIVE_FAILED" }
];

export const SEARCH_FILTERS = [
  { id: "all", label: "ALL", tone: "cyan" },
  { id: "infection", label: "INFECTION", tone: "red" },
  { id: "epidemic", label: "EPIDEMIC", tone: "purple" },
  { id: "quarantine", label: "QUARANTINE", tone: "amber" },
  { id: "state_transition", label: "STATE_TRANSITION", tone: "cyan" },
  { id: "mutation", label: "MUTATION", tone: "purple" },
  { id: "block", label: "BLOCK", tone: "amber" },
  { id: "transfer", label: "TRANSFER", tone: "blue" },
  { id: "beacon", label: "BEACON", tone: "cyan" },
  { id: "exfil", label: "EXFIL", tone: "red" },
  { id: "query", label: "QUERY", tone: "green" },
  { id: "c2", label: "C2", tone: "red" },
  { id: "tasking", label: "TASKING", tone: "purple" },
  { id: "kill_chain", label: "KILL_CHAIN", tone: "amber" },
  { id: "post_compromise", label: "POST_COMPROMISE", tone: "red" }
];

export const RESULT_TABS = ["events", "patterns", "statistics", "visualization", "intelligence"];
export const LIVE_FILTERS = ["all", "infection", "epidemic", "quarantine", "state_transition", "mutation", "block", "query", "transfer", "exfil", "scan", "alert", "c2", "beacon", "tasking", "kill_chain", "post_compromise"];

// Explicit event-family sets for live filter matching (prevents false positives from substring match)
const _BEACON_EVENTS = new Set(["C2_BEACON", "C2_CHANNEL_ESTABLISHED", "C2_CHANNEL_FAILED", "BEACON_BLOCKED"]);
const _TASKING_EVENTS = new Set(["C2_TASK", "TASK_BLOCKED"]);
const _EXFIL_EVENTS = new Set(["C2_EXFIL", "EXFIL_BLOCKED", "C2_DATABASE_WRITE"]);
const _KILL_CHAIN_EVENTS = new Set(["KILL_CHAIN_TRANSITION"]);
const _OBJECTIVE_EVENTS = new Set(["OBJECTIVE_COMPLETED", "OBJECTIVE_FAILED"]);
const _QUARANTINE_EVENTS = new Set(["QUARANTINE_ENFORCED", "QUARANTINE_ISSUED", "QUARANTINE_EXPIRED", "QUARANTINE_ADVISORY_SENT", "QUARANTINE_ADVISORY_RECEIVED"]);
const _EPIDEMIC_EVENTS = new Set(["EPIDEMIC_STATE_TRANSITION", "EXPOSURE_DECAYED", "EXPOSURE_CLEARED", "RESISTANCE_DECAYED", "VACCINE_APPLIED", "VACCINE_RECEIVED"]);
const _STATE_TRANSITION_EVENTS = new Set(["EPIDEMIC_STATE_TRANSITION", "KILL_CHAIN_TRANSITION"]);
const _C2_EVENTS = new Set([
  ..._BEACON_EVENTS, ..._TASKING_EVENTS, ..._EXFIL_EVENTS,
  ..._KILL_CHAIN_EVENTS, ..._OBJECTIVE_EVENTS, ..._QUARANTINE_EVENTS,
  "POST_COMPROMISE_ACTION", "POST_COMPROMISE_BLOCKED", "C2_SESSION_EXPIRED", "C2_SESSION_BURNED",
]);
const _POST_COMPROMISE_EVENTS = new Set([
  ..._BEACON_EVENTS, ..._TASKING_EVENTS, ..._EXFIL_EVENTS, ..._OBJECTIVE_EVENTS,
]);

export function matchLiveFilter(eventType, filter) {
  if (filter === "all") return true;
  const t = (eventType || "").toUpperCase();
  switch (filter) {
    case "c2": return _C2_EVENTS.has(t);
    case "epidemic": return _EPIDEMIC_EVENTS.has(t) || t.includes("EPIDEMIC");
    case "quarantine": return _QUARANTINE_EVENTS.has(t) || t.includes("QUARANTINE");
    case "state_transition": return _STATE_TRANSITION_EVENTS.has(t);
    case "beacon": return _BEACON_EVENTS.has(t);
    case "tasking": return _TASKING_EVENTS.has(t);
    case "exfil": return _EXFIL_EVENTS.has(t) || t.includes("EXFIL");
    case "kill_chain": return _KILL_CHAIN_EVENTS.has(t);
    case "post_compromise": return _POST_COMPROMISE_EVENTS.has(t);
    case "infection": return t.includes("INFECTION") || t === "WRM-INJECT";
    case "mutation": return t.includes("MUTATION") || t.includes("MUTANT");
    case "block": return t.includes("BLOCK") || t.includes("BLOCKED") || t === "PROPAGATION_SUPPRESSED";
    case "query": return t.includes("QUERY") || t.includes("RECON") || t.includes("PROBE");
    case "transfer": return t.includes("TRANSFER") || t.includes("RELAY") || t === "WORLD_MESSAGE";
    case "scan": return t.includes("SCAN") || t.includes("RECON");
    case "alert": return t.includes("ALERT") || t === "QUARANTINE_ADVISORY_SENT";
    default: return t.toLowerCase().includes(filter);
  }
}

export const DIFFICULTIES = [
  { id: "easy", label: "EASY", tone: "green" },
  { id: "medium", label: "MEDIUM", tone: "cyan" },
  { id: "hard", label: "HARD", tone: "amber" },
  { id: "nightmare", label: "NIGHTMARE", tone: "red" }
];

export function toneClasses(tone, active = false) {
  const palette = {
    cyan: active ? "border-terminal-cyan/40 bg-terminal-cyan/10 text-terminal-cyan" : "text-terminal-cyan",
    green: active ? "border-terminal-success/40 bg-terminal-success/10 text-terminal-success" : "text-terminal-success",
    red: active ? "border-terminal-danger/40 bg-terminal-danger/10 text-terminal-danger" : "text-terminal-danger",
    amber: active ? "border-terminal-warn/40 bg-terminal-warn/10 text-terminal-warn" : "text-terminal-warn",
    blue: active ? "border-terminal-info/40 bg-terminal-info/10 text-terminal-info" : "text-terminal-info",
    purple: active ? "border-terminal-purple/40 bg-terminal-purple/10 text-terminal-purple" : "text-terminal-purple"
  };
  return palette[tone] || (active ? "border-slate-700 text-slate-300" : "text-slate-300");
}

export function eventTypeClass(type) {
  const normalized = String(type || "").toUpperCase();
  if (normalized.includes("INFECT") || normalized.includes("EXFIL") || normalized.includes("ALERT")) return "text-terminal-danger";
  if (normalized.includes("EPIDEMIC")) return "text-terminal-purple";
  if (normalized.includes("QUARANTINE") || normalized.includes("KILL_CHAIN")) return "text-terminal-warn";
  if (normalized.includes("TASK")) return "text-terminal-purple";
  if (normalized.includes("MUTATION")) return "text-terminal-purple";
  if (normalized.includes("BLOCK")) return "text-terminal-warn";
  if (normalized.includes("TRANSFER")) return "text-terminal-cyan";
  if (normalized.includes("QUERY") || normalized.includes("BEACON")) return "text-terminal-info";
  if (normalized.includes("SCAN") || normalized.includes("HEART")) return "text-terminal-success";
  return "text-slate-400";
}

export function severityBadgeClass(severity) {
  switch (severity) {
    case "CRITICAL":
      return "border-terminal-danger/40 bg-terminal-danger/10 text-terminal-danger";
    case "HIGH":
      return "border-terminal-warn/40 bg-terminal-warn/10 text-terminal-warn";
    case "MEDIUM":
      return "border-terminal-cyan/40 bg-terminal-cyan/10 text-terminal-cyan";
    case "LOW":
      return "border-terminal-success/40 bg-terminal-success/10 text-terminal-success";
    default:
      return "border-slate-700 bg-slate-800/40 text-slate-500";
  }
}

export function severityTextClass(severity) {
  switch (severity) {
    case "CRITICAL":
      return "text-terminal-danger";
    case "HIGH":
      return "text-terminal-warn";
    case "MEDIUM":
      return "text-terminal-cyan";
    case "LOW":
      return "text-terminal-success";
    default:
      return "text-slate-500";
  }
}

export function activityTone(tone) {
  switch (tone) {
    case "red":
      return "text-terminal-danger";
    case "amber":
      return "text-terminal-warn";
    case "purple":
      return "text-terminal-purple";
    case "green":
      return "text-terminal-success";
    default:
      return "text-slate-500";
  }
}

export function stateTone(state) {
  switch (state) {
    case "INFECTED":
      return { dot: "#f87171", border: "rgba(248,113,113,0.45)", badge: "rgba(248,113,113,0.4)" };
    case "QUARANTINED":
      return { dot: "#fbbf24", border: "rgba(251,191,36,0.42)", badge: "rgba(251,191,36,0.35)" };
    case "RESISTANT":
      return { dot: "#c084fc", border: "rgba(192,132,252,0.38)", badge: "rgba(192,132,252,0.35)" };
    case "EXPOSED":
      return { dot: "#fb923c", border: "rgba(251,146,60,0.42)", badge: "rgba(251,146,60,0.35)" };
    case "HEALTHY":
    default:
      return { dot: "#4ade80", border: "rgba(74,222,128,0.28)", badge: "rgba(74,222,128,0.35)" };
  }
}

export function epidemicStateTone(state) {
  switch (String(state || "S")) {
    case "I_r":
      return { dot: "#f87171", border: "rgba(248,113,113,0.45)", badge: "rgba(248,113,113,0.35)" };
    case "I_c":
      return { dot: "#22d3ee", border: "rgba(34,211,238,0.42)", badge: "rgba(34,211,238,0.32)" };
    case "I_x":
      return { dot: "#fb7185", border: "rgba(251,113,133,0.45)", badge: "rgba(251,113,133,0.35)" };
    case "P":
      return { dot: "#c084fc", border: "rgba(192,132,252,0.42)", badge: "rgba(192,132,252,0.35)" };
    case "Q":
      return { dot: "#fbbf24", border: "rgba(251,191,36,0.42)", badge: "rgba(251,191,36,0.35)" };
    case "R":
      return { dot: "#4ade80", border: "rgba(74,222,128,0.32)", badge: "rgba(74,222,128,0.28)" };
    case "E":
      return { dot: "#fb923c", border: "rgba(251,146,60,0.42)", badge: "rgba(251,146,60,0.35)" };
    case "S":
    default:
      return { dot: "#94a3b8", border: "rgba(148,163,184,0.28)", badge: "rgba(148,163,184,0.25)" };
  }
}

export function isInfectedEpidemicState(state) {
  const s = String(state || "").toLowerCase();
  return ["i_r", "i_c", "i_x", "p"].includes(s);
}

function mapAgentStateFromEpidemic(epidemicState, fallbackState) {
  if (isInfectedEpidemicState(epidemicState)) return "INFECTED";
  if (String(epidemicState || "") === "Q") return "QUARANTINED";
  if (String(epidemicState || "") === "R") return "RESISTANT";
  if (String(epidemicState || "") === "E") return "EXPOSED";
  return fallbackState;
}

export function formatTime(date) {
  return date.toLocaleTimeString("en-GB", { hour12: false });
}

export function formatDate(date) {
  return date.toLocaleDateString("en-GB").replace(/\//g, "-");
}

export function formatApiTimestamp(value) {
  if (!value) return "00:00:00.000";
  const parsed = Number(value);
  if (Number.isFinite(parsed)) {
    return new Date(parsed * 1000).toLocaleTimeString("en-GB", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit"
    });
  }
  return String(value).slice(11, 23) || String(value);
}

function eventToTone(eventType) {
  const t = String(eventType || "").toUpperCase();
  if (t.includes("INFECTION") || t.includes("EXFIL")) return "red";
  if (t.includes("MUTATION")) return "purple";
  if (t.includes("BLOCK") || t.includes("QUARANTINE")) return "amber";
  if (t.includes("TRANSFER") || t.includes("RELAY") || t.includes("WORLD_MESSAGE")) return "green";
  return "gray";
}

export function normalizeSearchEvent(event, index = 0) {
  const metadata = event.metadata || {};
  return {
    id: event.event_id || event.id || `api-${index}`,
    event_id: event.event_id || event.id || "",
    timestamp: formatApiTimestamp(event.ts),
    event_type: String(event.event || metadata.event_type || "EVENT").toUpperCase(),
    src_agent: event.src || metadata.src_agent || "",
    dst_agent: event.dst || metadata.dst_agent || "",
    payload_hash: event.payload_hash || metadata.payload_hash || "",
    severity: deriveSeverity(event, metadata),
    reset_id: event.reset_id || metadata.reset_id || "",
    epoch: event.epoch ?? metadata.epoch ?? "",
    attack_type: event.attack_type || metadata.attack_type || "",
    state_after: event.state_after || metadata.state_after || "",
    mutation_v: event.mutation_v ?? metadata.mutation_v ?? "",
    campaign_id: event.campaign_id || metadata.campaign_id || "",
    injection_id: event.injection_id || metadata.injection_id || "",
    payload_preview: event.payload_preview || metadata.payload_preview || "",
    decoded_payload_preview: event.decoded_payload_preview || metadata.decoded_payload_preview || "",
    payload_text_available: Boolean(event.payload_text_available || event.has_payload),
    semantic_family: event.semantic_family || metadata.semantic_family || "",
    mutation_type: event.mutation_type || metadata.mutation_type || "",
    decode_status: event.decode_status || metadata.decode_status || "",
    payload_wrapper_type: event.payload_wrapper_type || metadata.payload_wrapper_type || "",
    kill_chain_stage: event.kill_chain_stage || metadata.kill_chain_stage || "",
    epidemic_state: event.epidemic_state || metadata.epidemic_state || "",
    epidemic_state_before: event.epidemic_state_before || metadata.epidemic_state_before || "",
    cognition_tier: event.cognition_tier || metadata.cognition_tier || "",
    decision_source: event.decision_source || metadata.decision_source || "",
    quarantine_trigger: event.quarantine_trigger || metadata.quarantine_trigger || "",
  };
}

function deriveSeverity(event, metadata) {
  const raw = String(metadata.severity || event.attack_type || event.event || "").toUpperCase();
  if (raw.includes("CRITICAL") || raw.includes("INFECTION") || raw.includes("EXFIL")) return "CRITICAL";
  if (raw.includes("MUTATION") || raw.includes("HIGH")) return "HIGH";
  if (raw.includes("BLOCK") || raw.includes("WARN")) return "MEDIUM";
  if (raw.includes("TRANSFER")) return "LOW";
  return "INFO";
}

export function isBeaconedLiveEvent(event) {
  const type = String(event.type || event.event || "").toUpperCase();
  return _BEACON_EVENTS.has(type) || _TASKING_EVENTS.has(type) || _EXFIL_EVENTS.has(type);
}

export function normalizeLiveEvent(event, index = 0) {
  const metadata = event.metadata || {};
  const type = String(event.event || metadata.event_type || "EVENT").toUpperCase();
  const payloadLength = Number(event.payload_length || metadata.payload_length || metadata.bytes || metadata.bytes_transferred || 0);
  const detailParts = [
    event.attack_type || metadata.attack_type || "",
    payloadLength > 0 ? `bytes:${payloadLength}` : "",
    metadata.proto ? `proto:${metadata.proto}` : "",
    metadata.dst_country ? `country:${metadata.dst_country}` : ""
  ].filter(Boolean);

  return {
    id: event.event_id || event.id || `live-api-${index}`,
    timestamp: formatApiTimestamp(event.ts),
    ts: event.ts || "",
    type,
    event: type,
    src: event.src || metadata.src_agent || "",
    dst: event.dst || metadata.dst_agent || "",
    severity: deriveSeverity(event, metadata),
    attackType: event.attack_type || metadata.attack_type || "",
    detail: detailParts.join(" | "),
    bytes: payloadLength,
    proto: metadata.proto || "",
    dstCountry: metadata.dst_country || "",
    payloadHash: event.payload_hash || metadata.payload_hash || "",
    parentPayloadHash: event.parent_payload_hash || metadata.parent_payload_hash || "",
    semanticFamily:
      event.semantic_family ||
      metadata.semantic_family ||
      event.strain_family ||
      metadata.strain_family ||
      "",
    mutationType: event.mutation_type || metadata.mutation_type || "",
    mutationVersion: event.mutation_v ?? metadata.mutation_v ?? "",
    strainId: event.strain_id || metadata.strain_id || "",
    strainSimilarityKey: event.strain_similarity_key || metadata.strain_similarity_key || "",
    strainFamily: event.strain_family || metadata.strain_family || "",
    strainBranchingRecommended: Boolean(
      event.strain_branching_recommended ?? metadata.strain_branching_recommended
    ),
    decodeStatus: event.decode_status || metadata.decode_status || "",
    payloadWrapperType: event.payload_wrapper_type || metadata.payload_wrapper_type || "",
    payloadText: event.payload_text || event.payload_preview || metadata.payload_preview || "",
    decodedPayloadText: event.decoded_payload_text || event.decoded_payload_preview || metadata.decoded_payload_preview || "",
    payloadPreview: event.payload_preview || metadata.payload_preview || "",
    decodedPayloadPreview: event.decoded_payload_preview || metadata.decoded_payload_preview || "",
    hasPayload: Boolean(event.has_payload),
    hasDecodedPayload: Boolean(event.has_decoded_payload),
    decodeWarnings: event.decode_warnings || [],
    resetId: event.reset_id || metadata.reset_id || "",
    epoch: event.epoch ?? metadata.epoch ?? "",
    killChainStage: event.kill_chain_stage || metadata.kill_chain_stage || "",
    epidemicState: event.epidemic_state || metadata.epidemic_state || "",
    epidemicStateBefore: event.epidemic_state_before || metadata.epidemic_state_before || "",
    cognitionTier: event.cognition_tier || metadata.cognition_tier || "",
    decisionSource: event.decision_source || metadata.decision_source || "",
    quarantineTrigger: event.quarantine_trigger || metadata.quarantine_trigger || "",
    beaconed: isBeaconedLiveEvent({ type, src: event.src || metadata.src_agent || "", dst: event.dst || metadata.dst_agent || "" })
  };
}

export function countBy(values) {
  const counts = values.reduce((accumulator, value) => {
    const key = String(value || "UNKNOWN");
    accumulator.set(key, (accumulator.get(key) || 0) + 1);
    return accumulator;
  }, new Map());
  return Array.from(counts.entries())
    .map(([label, count]) => ({ label, count }))
    .sort((left, right) => right.count - left.count);
}

export function buildFieldPivotsFromApi(fieldsPayload) {
  if (!fieldsPayload?.interesting_fields) return {};

  const fields = fieldsPayload.interesting_fields;
  const result = {};

  for (const [fieldName, values] of Object.entries(fields)) {
    if (!Array.isArray(values) || values.length === 0) continue;
    const max = values[0]?.count || 1;
    result[fieldName] = values.slice(0, 6).map((entry) => ({
      label: entry.value || "(empty)",
      count: entry.count || 0,
      percent: Math.max(12, Math.round(((entry.count || 0) / max) * 100))
    }));
  }

  return result;
}

export function buildTimelineData(timeline) {
  if (Array.isArray(timeline) && timeline.length) {
    return timeline.slice(-20).map((item, index) => ({
      label: item.label || item.bucket || `${index}`,
      value: Number(item.value || item.count || 0)
    }));
  }
  return [];
}

export function deriveAgentCards(controlState) {
  if (!controlState?.agents) return [];

  const events = controlState?.events || [];

  return Object.values(controlState.agents).map((agent) => {
    const agentId = String(agent.id || "unknown");
    const rawState = String(agent.state || "healthy").toUpperCase();
    const epidemicState = String(agent.epidemic_state || "S");
    const mappedState = mapAgentStateFromEpidemic(epidemicState, rawState);

    const recentEvents = events
      .filter((e) => e.src === agentId || e.dst === agentId)
      .slice(0, 3)
      .map((e) => ({
        ts: formatApiTimestamp(e.ts),
        text: `${e.event || "EVENT"}${e.attack_type ? ` [${e.attack_type}]` : ""}`,
        tone: eventToTone(e.event)
      }));

    return {
      id: agentId,
      role: agent.role || "agent",
      state: mappedState,
      epidemicState,
      cognitionTier: agent.cognition_tier || "",
      isEpidemicInfected: isInfectedEpidemicState(epidemicState),
      lastEvent: agent.last_event || "none",
      lastSeen: agent.last_seen || "",
      activity: recentEvents.length
        ? recentEvents
        : [{ ts: "--:--:--", text: "no recent events", tone: "gray" }]
    };
  });
}

export function buildSimulationMetrics(controlState, healthState, simRunning) {
  const agentCount = controlState?.agents ? Object.keys(controlState.agents).length : 0;
  const agentList = Object.values(controlState?.agents || {});
  const infected = agentList.filter((a) => isInfectedEpidemicState(a.epidemic_state || a.state)).length;
  const epidemicMetrics = controlState?.epidemic?.metrics || {};
  const c2Metrics = controlState?.c2?.metrics || {};
  const quarantineCount = Number(epidemicMetrics.quarantine_count ?? 0);
  const spreadBreadth = Number(epidemicMetrics.spread_breadth || infected);

  return {
    agentsOnline: {
      label: "AGENTS_ONLINE",
      value: agentCount,
      valueClass: "text-slate-300",
      subLabel: simRunning ? "RUNNING" : "STANDBY",
      subClass: "text-terminal-success",
      accent: "from-terminal-cyan/90 via-terminal-cyan/35 to-transparent"
    },
    infectionRate: {
      label: "EPIDEMIC_LOAD",
      value: agentCount ? `${((spreadBreadth / agentCount) * 100).toFixed(1)}%` : "0.0%",
      valueClass: spreadBreadth ? "text-terminal-warn" : "text-terminal-success",
      subLabel: spreadBreadth > 1 ? "BRANCHING" : spreadBreadth ? "ACTIVE" : "NOMINAL",
      subClass: spreadBreadth ? "text-terminal-danger" : "text-terminal-success",
      accent: spreadBreadth ? "from-terminal-danger/80 via-terminal-warn/30 to-transparent" : "from-terminal-success/80 via-terminal-cyan/30 to-transparent"
    },
    rAi: {
      label: "R_AI",
      value: Number(epidemicMetrics.r_ai ?? 0).toFixed(2),
      valueClass: Number(epidemicMetrics.r_ai ?? 0) >= 1 ? "text-terminal-danger" : "text-terminal-cyan",
      subLabel: "SPREAD_FACTOR",
      subClass: "text-terminal-info",
      accent: "from-terminal-purple/80 via-terminal-cyan/20 to-transparent"
    },
    spreadBreadth: {
      label: "SPREAD_BREADTH",
      value: spreadBreadth,
      valueClass: spreadBreadth ? "text-terminal-danger" : "text-terminal-success",
      subLabel: `DEPTH ${Number(epidemicMetrics.spread_depth ?? 0)}`,
      subClass: "text-terminal-warn",
      accent: "from-terminal-danger/80 via-terminal-purple/20 to-transparent"
    },
    quarantineCount: {
      label: "QUARANTINE_COUNT",
      value: quarantineCount,
      valueClass: quarantineCount ? "text-terminal-warn" : "text-slate-300",
      subLabel: quarantineCount ? "CONTAINMENT_ACTIVE" : "NO_CONTAINMENT",
      subClass: quarantineCount ? "text-terminal-warn" : "text-slate-500",
      accent: "from-terminal-warn/80 via-terminal-cyan/20 to-transparent"
    },
    activeC2Sessions: {
      label: "ACTIVE_C2_SESSIONS",
      value: Number(c2Metrics.active_c2_sessions ?? 0),
      valueClass: Number(c2Metrics.active_c2_sessions ?? 0) ? "text-terminal-danger" : "text-terminal-success",
      subLabel: Number(c2Metrics.c2_exfil_attempts ?? 0) ? `EXFIL ${Number(c2Metrics.c2_exfil_attempts ?? 0)}` : "STAGING",
      subClass: Number(c2Metrics.active_c2_sessions ?? 0) ? "text-terminal-danger" : "text-terminal-info",
      accent: infected ? "from-terminal-danger/80 via-terminal-warn/30 to-transparent" : "from-terminal-success/80 via-terminal-cyan/30 to-transparent"
    },
    indexedEvents: {
      label: "INDEXED_EVENTS",
      value: healthState?.indexed_events || 0,
      valueClass: "text-slate-300",
      subLabel: "SIEM",
      subClass: "text-terminal-success",
      accent: "from-terminal-success/80 via-terminal-cyan/20 to-transparent"
    }
  };
}

export function buildStatsCards(statsPayload) {
  if (!statsPayload) return [];
  return [
    {
      title: "EVENT_COUNTS",
      tone: "cyan",
      lines: [`successful=${statsPayload.successful}`, `blocked=${statsPayload.blocked}`, `attempts=${statsPayload.attempts}`]
    },
    {
      title: "SUCCESS_RATE_BY_TARGET",
      tone: "blue",
      lines: (statsPayload.presets?.success_rate_by_dst || []).slice(0, 3).map((item) => `${item.dst || "unknown"} => ${(item.success_rate * 100).toFixed(1)}%`)
    },
    {
      title: "ATTACK_STRENGTH",
      tone: "amber",
      lines: [
        `avg_attack_strength=${statsPayload.avg_attack_strength}`,
        `distinct_attacks=${statsPayload.count_by_attack_type?.length || 0}`,
        `query=${statsPayload.structured_query || "(empty)"}`
      ]
    }
  ];
}

export function buildPatternCards(searchPayload, statsPayload) {
  const warnings = searchPayload?.warnings || [];
  const routeLines = statsPayload?.src_dst_frequency?.slice(0, 4).map(
    (item) => `${item.src} -> ${item.dst} (${item.count})`
  ) || [];

  return [
    {
      title: "ROUTE_PATTERNS",
      tone: "cyan",
      lines: routeLines.length ? routeLines : ["no route data"]
    },
    {
      title: "SUPPRESSION_PATTERNS",
      tone: "amber",
      lines: warnings.length ? warnings.slice(0, 4) : ["no warnings"]
    }
  ];
}

export function buildIntelligenceCards(searchPayload, statsPayload, hintsPayload) {
  const hints = hintsPayload?.hints || [];
  return [
    {
      title: "MUTATION_INTELLIGENCE",
      tone: "purple",
      lines: [
        `top_hash=${searchPayload?.events?.[0]?.payload_hash || "n/a"}`,
        `families=${statsPayload?.count_by_attack_type?.length || 0}`,
      ]
    },
    {
      title: "ANALYST_NOTES",
      tone: "amber",
      lines: hints.length
        ? hints.slice(0, 3).map((hint) => (typeof hint === "string" ? hint : hint.title || hint.reason || hint.message))
        : ["no hints available"]
    }
  ];
}

export function computeLiveMetrics(events, metrics = null) {
  const counts = {
    infection: events.filter((event) => matchLiveFilter(event.type, "infection")).length,
    mutation: events.filter((event) => matchLiveFilter(event.type, "mutation")).length,
    block: events.filter((event) => matchLiveFilter(event.type, "block")).length,
    query: events.filter((event) => matchLiveFilter(event.type, "query")).length,
    transfer: events.filter((event) => matchLiveFilter(event.type, "transfer")).length,
    anomalies: events.filter((event) => event.severity === "CRITICAL").length,
  };
  const source = metrics || {};
  const epidemicMetrics = source.epidemicMetrics || {};
  const c2Metrics = source.c2Metrics || {};
  return {
    currentResetId: source.last_reset_id || "",
    currentEpoch: source.current_epoch ?? 0,
    parseErrors: source.parse_errors ?? 0,
    lastEventTs: source.last_event_ts || "",
    cards: [
      { label: "EVENTS/SEC", value: Number(source.events_per_sec ?? 0).toFixed(1), valueClass: "text-terminal-cyan", dotClass: "bg-terminal-cyan shadow-cyan" },
      { label: "INFECTIONS", value: source.infections ?? counts.infection, valueClass: "text-terminal-danger", dotClass: "bg-terminal-danger" },
      { label: "R_AI", value: Number(epidemicMetrics.r_ai ?? 0).toFixed(2), valueClass: "text-terminal-purple", dotClass: "bg-terminal-purple" },
      { label: "SPREAD", value: Number(epidemicMetrics.spread_breadth ?? 0), valueClass: "text-terminal-danger", dotClass: "bg-terminal-danger" },
      { label: "QUARANTINE", value: Number(epidemicMetrics.quarantine_count ?? 0), valueClass: "text-terminal-warn", dotClass: "bg-terminal-warn" },
      { label: "C2_SESSIONS", value: Number(c2Metrics.active_c2_sessions ?? 0), valueClass: "text-terminal-cyan", dotClass: "bg-terminal-cyan" },
      { label: "BLOCKS", value: source.blocked ?? counts.block, valueClass: "text-terminal-warn", dotClass: "bg-terminal-warn" },
      { label: "ANOMALIES", value: counts.anomalies, valueClass: "text-terminal-danger", dotClass: "bg-terminal-danger" }
    ]
  };
}
