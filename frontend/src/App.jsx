import React, { useEffect, useMemo, useRef, useState } from "react";
import { fetchJson } from "./api";
import { FooterBar, Header, SubHeader } from "./components/chrome";
import { CourierChatTab } from "./components/courierChat";
import { LiveTab } from "./components/live";
import { SearchTab } from "./components/search";
import WorldView from "./components/world/WorldView.jsx";
import { TranscriptView } from "./components/transcript";
import { TrustGraphView } from "./components/trust";
import { usePixelLabController } from "./pixel/hooks/usePixelLabController";
import {
  TAB_LABELS,
  buildFieldPivotsFromApi,
  buildIntelligenceCards,
  buildPatternCards,
  buildSimulationMetrics,
  buildStatsCards,
  buildTimelineData,
  computeLiveMetrics,
  deriveAgentCards,
  matchLiveFilter,
  normalizeLiveEvent,
  normalizeSearchEvent,
} from "./data";

async function fetchControlPlaneState() {
  try {
    return await fetchJson("/api/world/state");
  } catch (error) {
    const message = String(error?.message || error || "");
    if (message.includes("503") || message.includes("Persistent world engine is disabled")) {
      return fetchJson("/dashboard/state");
    }
    throw error;
  }
}

const WORLD_TRANSCRIPT_LIMIT = 240;

function normalizeWorldTranscriptEntry(event) {
  const fallbackId = [
    event.ts || "",
    event.round_id || 0,
    event.src || "",
    event.dst || "",
    event.payload_text || event.payload_preview || "",
  ].join(":");
  return {
    key: String(event.event_id || event.id || fallbackId),
    id: event.event_id || event.id || fallbackId,
    round: Number(event.round_id || 0),
    sender: event.src || "?",
    receiver: event.dst || "?",
    strainFamily: event.strain_family || "none",
    timestamp: event.ts || "",
    message: event.payload_text || event.payload_preview || "",
    intent: event.intent || event.attack_type || "social",
    trustEffect: Number(event.trust_delta || event.effect_on_trust?.trust_delta || 0),
    guardianPressureDelta: Number(event.guardian_pressure_delta || event.effect_on_guardian_pressure?.pressure_delta || 0),
    parentId: event.derived_from_message_id || null,
  };
}

function mergeWorldTranscript(previous, events) {
  if (!Array.isArray(events) || events.length === 0) return previous;
  const seen = new Set(previous.map((entry) => entry.key));
  const merged = [...previous];

  events.forEach((event) => {
    if (event?.event !== "WORLD_MESSAGE") return;
    const normalized = normalizeWorldTranscriptEntry(event);
    if (seen.has(normalized.key)) return;
    seen.add(normalized.key);
    merged.push(normalized);
  });

  merged.sort((left, right) => {
    const roundDelta = left.round - right.round;
    if (roundDelta !== 0) return roundDelta;
    return String(left.timestamp).localeCompare(String(right.timestamp));
  });
  return merged.slice(-WORLD_TRANSCRIPT_LIMIT);
}

function App() {
  const [activeTab, setActiveTab] = useState("world");
  const [difficulty, setDifficulty] = useState("medium");
  const [simRunning, setSimRunning] = useState(false);
  const [controlStatus, setControlStatus] = useState("system idle :: control plane nominal");
  const [controlState, setControlState] = useState(null);
  const [healthState, setHealthState] = useState(null);
  const [clock, setClock] = useState(new Date());
  const [searchMode, setSearchMode] = useState("structured");
  const [timeRange, setTimeRange] = useState("last_1h");
  const [searchQuery, setSearchQuery] = useState("event=INFECTION_SUCCESSFUL");
  const [activeSearchRun, setActiveSearchRun] = useState("active_infections");
  const [activeSearchFilter, setActiveSearchFilter] = useState("all");
  const [searchTab, setSearchTab] = useState("events");
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchPayload, setSearchPayload] = useState(null);
  const [statsPayload, setStatsPayload] = useState(null);
  const [fieldsPayload, setFieldsPayload] = useState(null);
  const [hintsPayload, setHintsPayload] = useState(null);
  const [queryHelp, setQueryHelp] = useState(null);
  const [selectedEventId, setSelectedEventId] = useState("");
  const [livePaused, setLivePaused] = useState(false);
  const [liveFilter, setLiveFilter] = useState("all");
  const [liveEvents, setLiveEvents] = useState([]);
  const [liveLatestId, setLiveLatestId] = useState(0);
  const [liveMetricsPayload, setLiveMetricsPayload] = useState(null);
  const [liveConnected, setLiveConnected] = useState(true);
  const [worldTranscriptState, setWorldTranscriptState] = useState([]);
  const [selectedInjectionTarget, setSelectedInjectionTarget] = useState("auto");
  const [selectedQuarantineTarget, setSelectedQuarantineTarget] = useState("auto");
  const liveFeedRef = useRef(null);
  const liveAutoScrollRef = useRef(true);
  const liveLatestIdRef = useRef(0);
  const worldRoundIdRef = useRef(0);
  const searchRequestRef = useRef(0);
  const controlRefreshInFlightRef = useRef(false);
  const liveRefreshInFlightRef = useRef(false);
  const simPulseInFlightRef = useRef(false);
  const searchBootstrappedRef = useRef(false);
  const liveBootstrappedRef = useRef(false);
  const [worldSubTab, setWorldSubTab] = useState("map");
  const [sessionId] = useState(() => `SIM_${Math.floor(11 + Math.random() * 999999).toString(16).padStart(6, "0")}`);
  const labController = usePixelLabController(controlState);
  useEffect(() => {
    const timer = window.setInterval(() => setClock(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    refreshControlState();
    const timer = window.setInterval(refreshControlState, 6000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (liveBootstrappedRef.current) return;
    liveBootstrappedRef.current = true;
    refreshLive(true);
  }, []);

  useEffect(() => {
    if (activeTab !== "search") return;
    fetchQueryHelp();
    if (searchBootstrappedRef.current) return;
    searchBootstrappedRef.current = true;
    runSearch(searchQuery);
  }, [activeTab, searchQuery]);

  const topologyView = useMemo(() => controlState?.epidemic?.topology || { topology: controlState?.topology || {}, agents: [] }, [controlState]);
  const injectionTargets = useMemo(() => {
    const targets = topologyView?.injection_targets;
    if (Array.isArray(targets) && targets.length) return targets;
    return Object.entries(topologyView?.topology || {})
      .filter(([, node]) => Boolean(node?.can_receive_injection))
      .map(([agentId]) => agentId);
  }, [topologyView]);
  const quarantineTargets = useMemo(
    () => Object.keys(controlState?.agents || {}),
    [controlState]
  );

  useEffect(() => {
    if (activeTab === "world" && worldSubTab === "map" && !simRunning) {
      setSimRunning(true);
      runSimulationPulse();
    }
  }, [activeTab, worldSubTab]);

  useEffect(() => {
    if (!simRunning) return undefined;
    // Server-side WORLD_AUTO_ADVANCE drives the world on its own; the client
    // pulse is a safety net. Keep interval longer than a typical LLM round
    // (~20-25s) and gate against overlap via simPulseInFlightRef.
    const interval = window.setInterval(runSimulationPulse, 30000);
    return () => window.clearInterval(interval);
  }, [simRunning, difficulty, selectedInjectionTarget, injectionTargets]);

  useEffect(() => {
    if (livePaused) return undefined;
    const interval = window.setInterval(() => {
      refreshLive();
    }, 1500);
    return () => window.clearInterval(interval);
  }, [livePaused]);

  useEffect(() => {
    liveLatestIdRef.current = liveLatestId;
  }, [liveLatestId]);

  useEffect(() => {
    const node = liveFeedRef.current;
    if (!node || !liveAutoScrollRef.current) return;
    node.scrollTop = node.scrollHeight;
  }, [liveEvents, activeTab]);

  const searchEvents = useMemo(() => {
    const events = (searchPayload?.events || []).map(normalizeSearchEvent);

    if (activeSearchFilter === "all") return events;

    return events.filter((event) => {
      const eventType = event.event_type.toLowerCase();
      return eventType.includes(activeSearchFilter) || event.severity.toLowerCase() === activeSearchFilter;
    });
  }, [activeSearchFilter, searchPayload]);

  const selectedEvent = useMemo(
    () => searchEvents.find((event) => event.id === selectedEventId) || searchEvents[0] || null,
    [searchEvents, selectedEventId]
  );

  useEffect(() => {
    if (!searchEvents.length) {
      setSelectedEventId("");
      return;
    }

    const hasSelectedEvent = searchEvents.some((event) => event.id === selectedEventId);
    if (!hasSelectedEvent) {
      setSelectedEventId(searchEvents[0].id);
    }
  }, [searchEvents, selectedEventId]);

  const agents = useMemo(() => deriveAgentCards(controlState), [controlState]);
  const simMetrics = useMemo(() => buildSimulationMetrics(controlState, healthState, simRunning), [controlState, healthState, simRunning]);
  const breadcrumb = `epi / siem / ${TAB_LABELS[activeTab]}`;
  const infectedCount = useMemo(() => agents.filter((agent) => agent.isEpidemicInfected).length, [agents]);
  const alertCount = useMemo(() => {
    const backendActiveAlerts = Number(controlState?.alerts?.active_count);
    const infectionStateAlerts = Number.isFinite(backendActiveAlerts) ? backendActiveAlerts : infectedCount;
    const criticalSearch = searchEvents.filter((event) => event.severity === "CRITICAL").length;
    const criticalLive = liveEvents.filter((event) => event.severity === "CRITICAL").length;
    return Math.max(infectionStateAlerts, criticalSearch + criticalLive);
  }, [controlState, infectedCount, liveEvents, searchEvents]);
  const liveMetrics = useMemo(() => computeLiveMetrics(liveEvents, liveMetricsPayload), [liveEvents, liveMetricsPayload]);
  const worldTranscript = useMemo(
    () => [...worldTranscriptState].reverse(),
    [worldTranscriptState]
  );
  const worldTrustAgents = useMemo(
    () =>
      Object.entries(controlState?.agents ?? {})
        .filter(([, a]) => Boolean(a))
        .map(([id, a]) => ({
          id,
          role: a.role || "agent",
          trustScore: Number(a.global_trust ?? 0),
          credibilityScore: Number(a.influence_weight ?? 0),
        })),
    [controlState]
  );
  const visibleLiveEvents = useMemo(() => {
    if (liveFilter === "all") return liveEvents;
    return liveEvents.filter((event) => matchLiveFilter(event.type, liveFilter));
  }, [liveEvents, liveFilter]);
  const sidebarPivots = useMemo(() => buildFieldPivotsFromApi(fieldsPayload), [fieldsPayload]);
  const timelineBars = useMemo(() => buildTimelineData(searchPayload?.timeline), [searchPayload]);
  const statisticsCards = useMemo(() => buildStatsCards(statsPayload), [statsPayload]);
  const patternCards = useMemo(() => buildPatternCards(searchPayload, statsPayload), [searchPayload, statsPayload]);
  const intelligenceCards = useMemo(() => buildIntelligenceCards(searchPayload, statsPayload, hintsPayload), [searchPayload, statsPayload, hintsPayload]);

  useEffect(() => {
    if (selectedInjectionTarget === "auto" || selectedInjectionTarget === "all") return;
    if (!injectionTargets.includes(selectedInjectionTarget)) {
      setSelectedInjectionTarget("auto");
    }
  }, [injectionTargets, selectedInjectionTarget]);

  useEffect(() => {
    if (selectedQuarantineTarget === "auto") return;
    if (!quarantineTargets.includes(selectedQuarantineTarget)) {
      setSelectedQuarantineTarget("auto");
    }
  }, [quarantineTargets, selectedQuarantineTarget]);

  async function refreshControlState() {
    if (controlRefreshInFlightRef.current) return;
    controlRefreshInFlightRef.current = true;
    try {
      const [control, health] = await Promise.all([fetchControlPlaneState(), fetchJson("/api/health")]);
      const worldRoundId = Number(control?.epidemic?.metrics?.world_round_id ?? 0);
      const nextTranscript = control?.events || [];
      const previousRoundId = worldRoundIdRef.current;
      const roundReset = worldRoundId < previousRoundId;
      if (roundReset) {
        setWorldTranscriptState(mergeWorldTranscript([], nextTranscript));
        setControlStatus(`world reset detected :: round ${previousRoundId} → ${worldRoundId} :: transcript cleared`);
      } else {
        setWorldTranscriptState((previous) => mergeWorldTranscript(previous, nextTranscript));
      }
      worldRoundIdRef.current = worldRoundId;
      setControlState(control);
      setHealthState(health);
      setLiveConnected(true);
    } catch (error) {
      setLiveConnected(false);
      setControlStatus(`telemetry degraded :: ${error.message}`);
    } finally {
      controlRefreshInFlightRef.current = false;
    }
  }

  async function fetchQueryHelp() {
    try {
      setQueryHelp(await fetchJson("/api/query-help"));
    } catch {
      setQueryHelp(null);
    }
  }

  async function refreshLive(forceFull = false) {
    if (liveRefreshInFlightRef.current) return;
    liveRefreshInFlightRef.current = true;
    try {
      const params = new URLSearchParams();
      params.set("limit", "100");
      if (!forceFull && liveLatestIdRef.current > 0) {
        params.set("after_id", String(liveLatestIdRef.current));
      }
      const payload = await fetchJson(`/api/live?${params.toString()}`);
      const epidemicMetrics = controlState?.epidemic?.metrics || {};
      const c2Metrics = controlState?.c2?.metrics || {};
      const normalizedEvents = (payload.events || []).map(normalizeLiveEvent);

      setLiveConnected(true);
      setLiveMetricsPayload({ ...(payload.metrics || {}), epidemicMetrics, c2Metrics });
      setLiveLatestId(Number(payload.latest_id || liveLatestIdRef.current || 0));
      setLiveEvents((previous) => {
        if (forceFull || !liveLatestIdRef.current) {
          return normalizedEvents.slice(-100);
        }
        const seen = new Set(previous.map((event) => event.id));
        const merged = [...previous];
        normalizedEvents.forEach((event) => {
          if (!seen.has(event.id)) {
            merged.push(event);
          }
        });
        return merged.slice(-100);
      });
    } catch (error) {
      setLiveConnected(false);
      setControlStatus(`live stream degraded :: ${error.message}`);
    } finally {
      liveRefreshInFlightRef.current = false;
    }
  }

  async function runSearch(queryOverride = searchQuery) {
    const requestId = searchRequestRef.current + 1;
    searchRequestRef.current = requestId;
    setSearchBusy(true);

    try {
      const params = new URLSearchParams({ q: queryOverride, mode: searchMode, time_range: timeRange }).toString();
      const [search, stats, fields, hints] = await Promise.all([
        fetchJson(`/api/search?${params}&limit=24`),
        fetchJson(`/api/stats?${params}`),
        fetchJson(`/api/fields?${params}`),
        fetchJson(`/api/hints?${params}`)
      ]);

      if (requestId !== searchRequestRef.current) return;

      setSearchPayload(search);
      setStatsPayload(stats);
      setFieldsPayload(fields);
      setHintsPayload(hints);
      setControlStatus(`query executed :: ${queryOverride || "all events"} :: ${search.total ?? search.events?.length ?? 0} rows`);
    } catch (error) {
      if (requestId !== searchRequestRef.current) return;

      setSearchPayload(null);
      setStatsPayload(null);
      setFieldsPayload(null);
      setHintsPayload(null);
      setControlStatus(`query failure :: ${error.message}`);
    } finally {
      if (requestId === searchRequestRef.current) {
        setSearchBusy(false);
      }
    }
  }

  async function postControl(endpoint, body) {
    const payload = await fetchJson(endpoint, {
      method: "POST",
      body: JSON.stringify(body ?? {})
    });
    setControlStatus(`${endpoint} :: ${JSON.stringify(payload)}`);
    await refreshControlState();
    return payload;
  }

  function resolveInjectionTargets() {
    if (!injectionTargets.length) return [];
    if (selectedInjectionTarget === "all") return injectionTargets;
    if (selectedInjectionTarget !== "auto") return [selectedInjectionTarget];
    return [injectionTargets[0]];
  }

  function resolveQuarantineTarget() {
    if (!quarantineTargets.length) return "";
    if (selectedQuarantineTarget !== "auto") return selectedQuarantineTarget;
    const priorityTarget = agents.find((agent) => agent.isEpidemicInfected)?.id;
    return priorityTarget || quarantineTargets[0];
  }

  async function runSimulationPulse() {
    if (simPulseInFlightRef.current) return;
    simPulseInFlightRef.current = true;
    setControlStatus("advancing world :: waiting for LLM decision...");
    try {
      const response = await fetchJson("/api/world/advance", {
        method: "POST",
        body: JSON.stringify({ difficulty })
      });
      setControlStatus(`world round ${response.round_id} :: ${response.reason} :: actor=${response.selected_agent || "none"}`);
      await refreshControlState();
      await refreshLive(true);
    } catch (error) {
      setControlStatus(`simulation pulse failed :: ${error.message}`);
    } finally {
      simPulseInFlightRef.current = false;
    }
  }

  async function handleControlAction(action) {
    if (action === "advance") {
      await runSimulationPulse();
      return;
    }

    if (action === "run") {
      setSimRunning(true);
      await runSimulationPulse();
      return;
    }

    if (action === "pause") {
      setSimRunning(false);
      setControlStatus("simulation paused :: auto-injection halted");
      return;
    }

    if (action === "vaccine") {
      await postControl("/api/world/vaccine");
      await refreshLive(true);
      setControlStatus("vaccine deployed :: temporary defense boost active");
      return;
    }

    if (action === "quarantine") {
      const target = resolveQuarantineTarget();
      if (!target) {
        setControlStatus("quarantine skipped :: no agent available");
        return;
      }
      await postControl(`/api/world/quarantine/${target}`);
      await refreshLive(true);
      return;
    }

    if (action === "reset") {
      setSimRunning(false);
      await postControl("/api/world/reset");
      await refreshLive(true);
    }
  }

  function handleLiveScroll(event) {
    const node = event.currentTarget;
    liveAutoScrollRef.current = node.scrollTop + node.clientHeight >= node.scrollHeight - 24;
  }

  async function fetchEventDetail(eventId, includePayload = false) {
    const params = includePayload ? "?include_full_payload=true" : "";
    return fetchJson(`/api/event/${eventId}${params}`);
  }

  function applyQuery(query) {
    setSearchQuery(query);
    runSearch(query);
  }

  function handleSaveSearch(run) {
    setActiveSearchRun(run.id);
    applyQuery(run.query);
  }

  function applyScopeShortcut(scope) {
    if (scope === "current_reset" && liveMetrics.currentResetId)
      applyQuery(`reset_id=${liveMetrics.currentResetId}`);
    if (scope === "current_run" && liveMetrics.currentResetId && liveMetrics.currentEpoch !== undefined)
      applyQuery(`reset_id=${liveMetrics.currentResetId} AND epoch=${liveMetrics.currentEpoch}`);
  }

  function exportLiveFeed() {
    const blob = new Blob([JSON.stringify(visibleLiveEvents, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `epidemic-live-${Date.now()}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="min-h-screen bg-terminal-base text-slate-200 terminal-grid">
      <div className="crt-overlay" />
      <div className="mx-auto flex min-h-screen max-w-[1600px] flex-col px-4 pb-4 pt-3">
        <Header activeTab={activeTab} setActiveTab={setActiveTab} alertCount={alertCount} clock={clock} />
        <SubHeader breadcrumb={breadcrumb} activeAgents={simMetrics.agentsOnline.value} infectedCount={infectedCount} threatLevel={simMetrics.infectionRate.subLabel} />
        <main className="flex-1">
          <div key={activeTab} className="tab-enter">
            {{
              search: (
                <SearchTab
                  activeSearchRun={activeSearchRun}
                  onSaveSearch={handleSaveSearch}
                  searchQuery={searchQuery}
                  setSearchQuery={setSearchQuery}
                  searchMode={searchMode}
                  setSearchMode={setSearchMode}
                  timeRange={timeRange}
                  setTimeRange={setTimeRange}
                  activeSearchFilter={activeSearchFilter}
                  setActiveSearchFilter={setActiveSearchFilter}
                  searchTab={searchTab}
                  setSearchTab={setSearchTab}
                  searchBusy={searchBusy}
                  onRunSearch={runSearch}
                  searchEvents={searchEvents}
                  selectedEvent={selectedEvent}
                  setSelectedEventId={setSelectedEventId}
                  timelineBars={timelineBars}
                  sidebarPivots={sidebarPivots}
                  statisticsCards={statisticsCards}
                  patternCards={patternCards}
                  intelligenceCards={intelligenceCards}
                  fieldsPayload={fieldsPayload}
                  queryHelp={queryHelp}
                  hints={hintsPayload?.hints || []}
                  liveContext={liveMetrics}
                  onApplyScopeShortcut={applyScopeShortcut}
                  onFetchEventDetail={fetchEventDetail}
                />
              ),
              live: (
                <LiveTab
                  liveMetrics={liveMetrics}
                  livePaused={livePaused}
                  setLivePaused={setLivePaused}
                  liveFilter={liveFilter}
                  setLiveFilter={setLiveFilter}
                  visibleLiveEvents={visibleLiveEvents}
                  onClear={() => setLiveEvents([])}
                  onExport={exportLiveFeed}
                  liveFeedRef={liveFeedRef}
                  onScroll={handleLiveScroll}
                  sessionId={sessionId}
                  liveConnected={liveConnected}
                  onRefresh={() => refreshLive(true)}
                />
              ),
              world: (
                <div className="flex flex-col">
                  <div className="flex gap-1 border-b border-white/5 px-3 pt-1 pb-0">
                    {["map", "transcript", "trust"].map((t) => (
                      <button
                        key={t}
                        type="button"
                        onClick={() => setWorldSubTab(t)}
                        className={`px-3 py-2 text-[10px] font-mono uppercase tracking-widest border-b-2 transition ${
                          worldSubTab === t
                            ? "border-terminal-cyan text-terminal-cyan"
                            : "border-transparent text-slate-500 hover:text-terminal-cyan"
                        }`}
                      >
                        {t}
                      </button>
                    ))}
                  </div>
                  {worldSubTab === "map" ? (
                    <div style={{ height: "calc(100vh - 200px)", position: "relative" }}>
                      <WorldView
                        controlsOverlayProps={{
                          difficulty,
                          setDifficulty,
                          controlStatus,
                          onControlAction: handleControlAction,
                          simRunning,
                          injectionTargets,
                          selectedInjectionTarget,
                          setSelectedInjectionTarget,
                          quarantineTargets,
                          selectedQuarantineTarget,
                          setSelectedQuarantineTarget,
                          labController,
                        }}
                      />
                    </div>
                  ) : worldSubTab === "transcript" ? (
                    <TranscriptView
                      transcript={worldTranscript}
                      onFetchLineage={() => Promise.resolve([])}
                    />
                  ) : (
                    <TrustGraphView agents={worldTrustAgents} transcript={worldTranscript} />
                  )}
                </div>
              ),
              courier: (
                <CourierChatTab onStatus={setControlStatus} />
              ),
            }[activeTab]}
          </div>
        </main>
        <FooterBar />
      </div>
    </div>
  );
}

export default App;
