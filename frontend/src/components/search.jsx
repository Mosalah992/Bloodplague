import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  RESULT_TABS,
  SEARCH_FILTERS,
  SEARCH_RUNS,
  eventTypeClass,
  severityBadgeClass,
  severityTextClass,
  toneClasses
} from "../data";
import { SectionHeader } from "./chrome";

export function SearchTab({
  activeSearchRun,
  onSaveSearch,
  searchQuery,
  setSearchQuery,
  searchMode,
  setSearchMode,
  timeRange,
  setTimeRange,
  activeSearchFilter,
  setActiveSearchFilter,
  searchTab,
  setSearchTab,
  searchBusy,
  onRunSearch,
  searchEvents,
  selectedEvent,
  setSelectedEventId,
  timelineBars,
  sidebarPivots,
  statisticsCards,
  patternCards,
  intelligenceCards,
  fieldsPayload,
  queryHelp,
  hints,
  liveContext,
  onApplyScopeShortcut,
  onFetchEventDetail
}) {
  return (
    <section className="space-y-5 px-3 py-5">
      <SectionHeader label="SAVED_SEARCHES" />
      <div className="flex flex-wrap gap-3">
        {SEARCH_RUNS.map((run) => (
          <button
            key={run.id}
            type="button"
            onClick={() => onSaveSearch(run)}
            className={`border px-4 py-3 font-mono text-[12px] ${activeSearchRun === run.id ? "border-terminal-cyan bg-terminal-cyan/10 text-terminal-cyan" : "border-slate-700 text-slate-500"}`}
          >
            [{run.label}]
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button type="button" onClick={() => onApplyScopeShortcut("current_reset")} className="border border-terminal-purple/30 px-4 py-2 font-mono text-[12px] text-terminal-purple">
          [CURRENT_RESET]
        </button>
        <button type="button" onClick={() => onApplyScopeShortcut("current_run")} className="border border-terminal-info/30 px-4 py-2 font-mono text-[12px] text-terminal-info">
          [CURRENT_RUN]
        </button>
        <div className="font-mono text-[11px] text-slate-500">
          reset={liveContext?.currentResetId || "-"} | epoch={liveContext?.currentEpoch ?? "-"}
        </div>
      </div>

      <div className="terminal-panel border-terminal-cyan/30 p-4 shadow-cyan">
        <div className="flex flex-wrap items-center gap-3">
          <select value={searchMode} onChange={(event) => setSearchMode(event.target.value)} className="border border-slate-700 bg-transparent px-3 py-2 font-pixel text-[7px] uppercase text-slate-400">
            <option value="structured">field search</option>
            <option value="natural">natural</option>
          </select>
          <select value={timeRange} onChange={(event) => setTimeRange(event.target.value)} className="border border-slate-700 bg-transparent px-3 py-2 font-pixel text-[7px] uppercase text-slate-400">
            <option value="all">all time</option>
            <option value="last_15m">last 15m</option>
            <option value="last_1h">last 1h</option>
            <option value="last_24h">last 24h</option>
            <option value="last_7d">last 7d</option>
          </select>
          <div className="flex min-w-[460px] flex-1 items-center border border-terminal-cyan/20 bg-[#0c1219] px-4 py-3 font-mono text-[12px] text-terminal-cyan">
            <span className="mr-2 shrink-0">epi:search $</span>
            <input value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} className="w-full bg-transparent text-slate-200 outline-none" />
          </div>
          <button type="button" onClick={() => onRunSearch()} className="border border-terminal-success/40 bg-terminal-success/10 px-6 py-3 font-pixel text-[7px] uppercase text-terminal-success">
            &gt; RUN
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          {SEARCH_FILTERS.map((filter) => (
            <button
              key={filter.id}
              type="button"
              onClick={() => setActiveSearchFilter(filter.id)}
              className={`border px-3 py-2 font-pixel text-[6px] uppercase ${activeSearchFilter === filter.id ? toneClasses(filter.tone, true) : "border-slate-700 text-slate-500"}`}
            >
              {filter.label}
            </button>
          ))}
        </div>
        <div className="font-mono text-[12px] text-slate-500">
          {searchEvents.length} results {searchBusy ? ":: scanning..." : ""}
        </div>
      </div>

      {timelineBars.length > 0 && (
        <div className="terminal-panel p-4">
          <div className="mb-2 flex items-center justify-between font-pixel text-[6px] uppercase">
            <span className="text-slate-500">EVENT_TIMELINE</span>
            <span className="text-terminal-danger">| events over time</span>
          </div>
          <div className="h-[88px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={timelineBars}>
                <CartesianGrid stroke="rgba(55,65,81,0.18)" vertical={false} />
                <XAxis dataKey="label" tick={{ fill: "#6b7280", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis hide />
                <Tooltip contentStyle={{ backgroundColor: "#080c11", border: "1px solid rgba(248,113,113,0.25)", color: "#d1d5db", fontFamily: "IBM Plex Mono", fontSize: 11 }} />
                <Bar dataKey="value" fill="#f87171" radius={[1, 1, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-1 border-b border-white/10">
        {RESULT_TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setSearchTab(tab)}
            className={`border border-b-0 px-4 py-3 font-pixel text-[6px] uppercase ${searchTab === tab ? "border-terminal-cyan/30 bg-terminal-panel text-terminal-cyan" : "border-white/10 text-slate-600"}`}
          >
            {tab.toUpperCase()}
          </button>
        ))}
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_280px]">
        <div className="space-y-4">
          <EventsTable events={searchEvents} selectedEvent={selectedEvent} setSelectedEventId={setSelectedEventId} />
          {selectedEvent ? (
            <EventDetail
              selectedEvent={selectedEvent}
              onFetchEventDetail={onFetchEventDetail}
              onRunSearch={onRunSearch}
              setSearchQuery={setSearchQuery}
            />
          ) : null}
          <ResultPanel tab={searchTab} patternCards={patternCards} statisticsCards={statisticsCards} intelligenceCards={intelligenceCards} timelineBars={timelineBars} />
        </div>
        <SearchSidebar sidebarPivots={sidebarPivots} hints={hints} queryHelp={queryHelp} />
      </div>
    </section>
  );
}

function EventsTable({ events, selectedEvent, setSelectedEventId }) {
  if (!events.length) {
    return (
      <div className="terminal-panel p-8 text-center">
        <div className="font-pixel text-[8px] uppercase text-slate-600">NO_RESULTS</div>
        <div className="mt-3 font-mono text-[12px] text-slate-500">
          query returned 0 events — adjust filters or time range
        </div>
      </div>
    );
  }

  return (
    <div className="terminal-panel overflow-hidden">
      <table className="w-full border-collapse">
        <thead className="border-b border-white/10 bg-[#0c1118]">
          <tr className="font-pixel text-[6px] uppercase text-terminal-cyan">
            {["TIME", "EVENT_TYPE", "SOURCE", "DESTINATION", "PAYLOAD_HASH", "SEVERITY"].map((label) => (
              <th key={label} className="px-3 py-3 text-left">
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="font-mono text-[13px]">
          {events.slice(0, 12).map((event, index) => (
            <tr
              key={event.id}
              onClick={() => setSelectedEventId(event.id)}
              className={`cursor-pointer border-b border-white/10 ${index % 2 === 0 ? "bg-[#0b1016]" : "bg-[#0d1117]"} ${selectedEvent?.id === event.id ? "bg-terminal-cyan/10" : ""}`}
            >
              <td className="px-3 py-4 text-slate-500">{event.timestamp}</td>
              <td className={`px-3 py-4 ${eventTypeClass(event.event_type)}`}>{event.event_type}</td>
              <td className="px-3 py-4 text-terminal-info">{event.src_agent || "-"}</td>
              <td className="px-3 py-4 text-terminal-purple">{event.dst_agent || "-"}</td>
              <td className="px-3 py-4 text-terminal-purple/80">{event.payload_hash || "-"}</td>
              <td className="px-3 py-4">
                <span className={`border px-2 py-1 font-pixel text-[5px] uppercase ${severityBadgeClass(event.severity)}`}>{event.severity}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EventDetail({ selectedEvent, onFetchEventDetail, onRunSearch, setSearchQuery }) {
  const [revealedPayload, setRevealedPayload] = useState(null);
  const [revealLoading, setRevealLoading] = useState(false);

  useEffect(() => { setRevealedPayload(null); }, [selectedEvent.event_id]);

  async function handleRevealPayload() {
    if (!selectedEvent.event_id || !onFetchEventDetail) return;
    setRevealLoading(true);
    try {
      const detail = await onFetchEventDetail(selectedEvent.event_id, true);
      setRevealedPayload(detail?.event || null);
    } catch {
      setRevealedPayload(null);
    } finally {
      setRevealLoading(false);
    }
  }

  function pivot(query) {
    setSearchQuery(query);
    onRunSearch(query);
  }

  const coreFields = [
    ["event_id", selectedEvent.event_id || selectedEvent.id, "text-slate-300"],
    ["timestamp", selectedEvent.timestamp, "text-slate-300"],
    ["event_type", selectedEvent.event_type, eventTypeClass(selectedEvent.event_type)],
    ["src_agent", selectedEvent.src_agent, "text-terminal-info"],
    ["dst_agent", selectedEvent.dst_agent, "text-terminal-purple"],
    ["severity", selectedEvent.severity, severityTextClass(selectedEvent.severity)],
    ["payload_hash", selectedEvent.payload_hash, "text-terminal-purple"],
    ["reset_id", selectedEvent.reset_id || "-", "text-slate-400"],
    ["epoch", String(selectedEvent.epoch ?? "-"), "text-terminal-cyan"],
  ];

  const metadataFields = [
    selectedEvent.attack_type && ["attack_type", selectedEvent.attack_type, "text-terminal-warn"],
    selectedEvent.state_after && ["state_after", selectedEvent.state_after, "text-slate-400"],
    selectedEvent.kill_chain_stage && ["kill_chain_stage", selectedEvent.kill_chain_stage, "text-terminal-warn"],
    selectedEvent.epidemic_state && ["epidemic_state", selectedEvent.epidemic_state, "text-terminal-purple"],
    selectedEvent.epidemic_state_before && ["epidemic_state_before", selectedEvent.epidemic_state_before, "text-slate-400"],
    selectedEvent.cognition_tier && ["cognition_tier", selectedEvent.cognition_tier, "text-terminal-info"],
    selectedEvent.decision_source && ["decision_source", selectedEvent.decision_source, "text-terminal-cyan"],
    selectedEvent.quarantine_trigger && ["quarantine_trigger", selectedEvent.quarantine_trigger, "text-terminal-warn"],
    selectedEvent.semantic_family && ["semantic_family", selectedEvent.semantic_family, "text-terminal-info"],
    selectedEvent.mutation_type && ["mutation_type", selectedEvent.mutation_type, "text-terminal-purple"],
    selectedEvent.decode_status && ["decode_status", selectedEvent.decode_status, "text-slate-400"],
    selectedEvent.payload_wrapper_type && ["wrapper_type", selectedEvent.payload_wrapper_type, "text-slate-400"],
    selectedEvent.campaign_id && ["campaign_id", selectedEvent.campaign_id, "text-terminal-cyan"],
    (selectedEvent.mutation_v !== "" && selectedEvent.mutation_v != null) && ["mutation_v", String(selectedEvent.mutation_v), "text-terminal-purple"],
  ].filter(Boolean);

  const allFields = [...coreFields, ...metadataFields];

  return (
    <div className="terminal-panel p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="font-pixel text-[7px] uppercase text-terminal-cyan">EVENT_DETAIL</div>
        <div className="flex flex-wrap gap-2">
          {selectedEvent.src_agent && (
            <button type="button" onClick={() => pivot(`src=${selectedEvent.src_agent}`)} className="border border-terminal-cyan/20 px-3 py-2 font-pixel text-[6px] uppercase text-terminal-cyan">
              PIVOT_SRC
            </button>
          )}
          {selectedEvent.injection_id && (
            <button type="button" onClick={() => pivot(`injection_id=${selectedEvent.injection_id}`)} className="border border-terminal-cyan/20 px-3 py-2 font-pixel text-[6px] uppercase text-terminal-cyan">
              TRACE
            </button>
          )}
          {selectedEvent.payload_hash && (
            <button type="button" onClick={() => pivot(`payload_hash=${selectedEvent.payload_hash}`)} className="border border-terminal-cyan/20 px-3 py-2 font-pixel text-[6px] uppercase text-terminal-purple">
              LINEAGE
            </button>
          )}
          {selectedEvent.payload_text_available && !revealedPayload && (
            <button
              type="button"
              onClick={handleRevealPayload}
              disabled={revealLoading}
              className="border border-terminal-warn/30 px-3 py-2 font-pixel text-[6px] uppercase text-terminal-warn"
            >
              {revealLoading ? "LOADING..." : "REVEAL_PAYLOAD"}
            </button>
          )}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {allFields.map(([field, value, valueClass]) => (
          <div key={field} className="border border-white/10 bg-[#0b1016] p-3">
            <div className="font-pixel text-[6px] uppercase text-terminal-cyan/70">{field}</div>
            <div className={`mt-2 font-mono text-[13px] break-all ${valueClass}`}>{value || "-"}</div>
          </div>
        ))}
      </div>

      {(selectedEvent.payload_preview || selectedEvent.decoded_payload_preview) && (
        <div className="mt-4 space-y-3">
          {selectedEvent.payload_preview && (
            <div className="border border-white/10 bg-[#0b1016] p-3">
              <div className="font-pixel text-[6px] uppercase text-terminal-warn/70">payload_preview</div>
              <div className="mt-2 font-mono text-[12px] text-slate-400 break-all whitespace-pre-wrap">{selectedEvent.payload_preview}</div>
            </div>
          )}
          {selectedEvent.decoded_payload_preview && (
            <div className="border border-white/10 bg-[#0b1016] p-3">
              <div className="font-pixel text-[6px] uppercase text-terminal-info/70">decoded_payload_preview</div>
              <div className="mt-2 font-mono text-[12px] text-slate-400 break-all whitespace-pre-wrap">{selectedEvent.decoded_payload_preview}</div>
            </div>
          )}
        </div>
      )}

      {revealedPayload && (
        <div className="mt-4 space-y-3">
          {revealedPayload.payload_text && (
            <div className="border border-terminal-warn/20 bg-[#0b1016] p-3">
              <div className="font-pixel text-[6px] uppercase text-terminal-warn">FULL_PAYLOAD</div>
              <pre className="mt-2 max-h-[200px] overflow-auto font-mono text-[11px] text-slate-400 whitespace-pre-wrap break-all">{revealedPayload.payload_text}</pre>
            </div>
          )}
          {revealedPayload.decoded_payload_text && (
            <div className="border border-terminal-info/20 bg-[#0b1016] p-3">
              <div className="font-pixel text-[6px] uppercase text-terminal-info">DECODED_PAYLOAD</div>
              <pre className="mt-2 max-h-[200px] overflow-auto font-mono text-[11px] text-slate-400 whitespace-pre-wrap break-all">{revealedPayload.decoded_payload_text}</pre>
            </div>
          )}
          {!revealedPayload.payload_text && !revealedPayload.decoded_payload_text && (
            <div className="border border-white/10 bg-[#0b1016] p-3 font-mono text-[12px] text-slate-600">
              no payload data available for this event
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ResultPanel({ tab, patternCards, statisticsCards, intelligenceCards, timelineBars }) {
  if (tab === "events") return null;

  if (tab === "visualization") {
    if (!timelineBars.length) {
      return (
        <div className="terminal-panel p-6 text-center font-mono text-[12px] text-slate-600">
          no visualization data available
        </div>
      );
    }
    return (
      <div className="terminal-panel p-4">
        <div className="mb-3 font-pixel text-[7px] uppercase text-terminal-cyan">VISUALIZATION_OVERVIEW</div>
        <div className="border border-white/10 p-3">
          <div className="mb-2 font-mono text-[12px] text-slate-500">Event distribution</div>
          <div className="h-[120px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={timelineBars}>
                <CartesianGrid stroke="rgba(55,65,81,0.18)" vertical={false} />
                <XAxis dataKey="label" tick={{ fill: "#6b7280", fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis hide />
                <Bar dataKey="value" fill="#22d3ee" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    );
  }

  const cards = { patterns: patternCards, statistics: statisticsCards, intelligence: intelligenceCards }[tab] ?? [];

  if (!cards.length) {
    return (
      <div className="terminal-panel p-6 text-center font-mono text-[12px] text-slate-600">
        no {tab} data available
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {cards.map((card) => (
        <div key={card.title} className="terminal-panel p-4">
          <div className={`mb-3 font-pixel text-[7px] uppercase ${toneClasses(card.tone)}`}>{card.title}</div>
          <div className="space-y-2 font-mono text-[12px] text-slate-500">
            {card.lines.map((line, index) => (
              <div key={`${card.title}-${index}`}>{line}</div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function SearchSidebar({ sidebarPivots, hints, queryHelp }) {
  const pivotFields = Object.keys(sidebarPivots);

  return (
    <div className="space-y-4">
      <div className="terminal-panel p-4">
        <div className="mb-4 font-pixel text-[7px] uppercase text-terminal-cyan">FIELD_PIVOT</div>
        {pivotFields.length === 0 && (
          <div className="font-mono text-[12px] text-slate-600">no field data</div>
        )}
        {pivotFields.map((group) => (
          <div key={group} className="mb-5">
            <div className="mb-2 font-mono text-[12px] text-terminal-cyan/80">{group}</div>
            <div className="space-y-2">
              {(sidebarPivots[group] || []).map((entry) => (
                <div key={`${group}-${entry.label}`} className="grid grid-cols-[1fr_auto] items-center gap-3">
                  <div>
                    <div className="mb-1 font-mono text-[12px] text-slate-500">{entry.label}</div>
                    <div className="h-3 bg-[#0a0f15]">
                      <div className="h-3 bg-gradient-to-r from-terminal-cyan/40 to-terminal-cyan/10" style={{ width: `${entry.percent}%` }} />
                    </div>
                  </div>
                  <div className="font-mono text-[12px] text-slate-500">{entry.count}</div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {hints.length > 0 && (
        <div className="terminal-panel p-4">
          <div className="mb-3 font-pixel text-[7px] uppercase text-terminal-warn">ANALYTIC_HINTS</div>
          <div className="space-y-3 font-mono text-[12px] text-slate-500">
            {hints.slice(0, 4).map((hint, index) => (
              <div key={`${index}-${typeof hint === "string" ? hint : hint.title}`}>
                <span className="mr-2 text-terminal-warn">&gt;</span>
                {typeof hint === "string" ? hint : hint.title || hint.reason || hint.message}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="terminal-panel p-4">
        <div className="mb-3 font-pixel text-[7px] uppercase text-terminal-cyan">QUERY_GUIDE</div>
        <div className="space-y-2 font-mono text-[11px] text-slate-500">
          {(queryHelp?.operators || []).slice(0, 4).map((item) => (
            <div key={item.syntax}>
              <span className="text-terminal-cyan">{item.syntax}</span> :: {item.description}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
