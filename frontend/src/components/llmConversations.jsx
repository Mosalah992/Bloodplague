import { useState } from "react";

import { SectionHeader } from "./chrome";
import { eventTypeClass, toneClasses } from "../data";

function kindTone(kind) {
  switch (kind) {
    case "message":
      return "cyan";
    case "llm":
      return "purple";
    case "decision":
      return "amber";
    case "defense":
      return "green";
    default:
      return "blue";
  }
}

function formatMetricValue(value) {
  if (value === null || value === undefined || value === "") return "";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  return String(value);
}

function ConversationMeta({ event }) {
  const items = [
    ["msg", event.messageType],
    ["contam", event.contaminationStatus],
    ["trust", event.trustWeight],
    ["tier", event.cognitionTier],
    ["decision", event.decisionSource],
    ["model", event.model],
    ["status", event.modelStatus],
    ["latency", event.latencyMs ? `${event.latencyMs}ms` : ""],
    ["confidence", event.confidence],
    ["retry", event.retryCount],
    ["reject", event.rejectionReason],
    ["campaign", event.campaignId],
  ]
    .map(([label, value]) => [label, formatMetricValue(value)])
    .filter(([, value]) => value);

  if (!items.length && !event.action && !event.taskLabel) return null;

  return (
    <div className="mt-3 flex flex-wrap gap-2 font-mono text-[10px] text-slate-500">
      {event.taskLabel || event.action ? (
        <span className="border border-terminal-info/20 bg-terminal-info/10 px-2 py-1 text-terminal-info">
          task:{event.taskLabel || event.action} {event.destination ? `-> ${event.destination}` : ""} {event.tool ? `via ${event.tool}` : ""}
        </span>
      ) : null}
      {items.map(([label, value]) => (
        <span key={`${label}-${value}`} className="border border-white/10 bg-black/20 px-2 py-1">
          {label}:{value}
        </span>
      ))}
    </div>
  );
}

export function LlmConversationsTab({
  events,
  paused,
  setPaused,
  scrollLock,
  setScrollLock,
  connected,
  onRefresh,
  onClear,
  streamRef,
  sessionId,
}) {
  const [decodedOpen, setDecodedOpen] = useState({});
  const messageCount = events.filter((event) => event.kind === "message").length;
  const llmCount = events.filter((event) => event.kind === "llm").length;
  const decisionCount = events.filter((event) => event.kind === "decision").length;
  const latest = events[events.length - 1];

  return (
    <section className="space-y-5 px-3 py-5">
      <SectionHeader label="LLM_CONVERSATIONS" />

      <div className="grid gap-3 md:grid-cols-4">
        {[
          ["MESSAGES", messageCount, "cyan"],
          ["LLM_OUTPUTS", llmCount, "purple"],
          ["DECISIONS", decisionCount, "amber"],
          ["BUFFER", events.length, "green"],
        ].map(([label, value, tone]) => (
          <div key={label} className="terminal-panel p-4 text-center">
            <div className="font-pixel text-[5px] uppercase text-slate-600">{label}</div>
            <div className={`mt-4 font-mono text-[32px] leading-none ${toneClasses(tone)}`}>{value}</div>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setPaused((value) => !value)}
            className={`border px-4 py-3 font-pixel text-[7px] uppercase ${paused ? "border-terminal-success/40 bg-terminal-success/10 text-terminal-success" : "border-terminal-warn/40 bg-terminal-warn/10 text-terminal-warn"}`}
          >
            {paused ? "> RESUME_LLM_STREAM" : "|| PAUSE_LLM_STREAM"}
          </button>
          <button
            type="button"
            onClick={() => setScrollLock((value) => !value)}
            className={`border px-4 py-3 font-pixel text-[7px] uppercase ${scrollLock ? "border-terminal-cyan/40 bg-terminal-cyan/10 text-terminal-cyan" : "border-white/15 text-slate-500"}`}
          >
            SCROLL_LOCK:{scrollLock ? "ON" : "OFF"}
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button type="button" onClick={onRefresh} className="border border-terminal-success/30 px-4 py-3 font-pixel text-[6px] uppercase text-terminal-success">
            REFRESH
          </button>
          <button type="button" onClick={onClear} className="border border-white/15 px-4 py-3 font-pixel text-[6px] uppercase text-slate-400">
            CLEAR
          </button>
          <div className="flex items-center gap-2 font-pixel text-[7px] uppercase text-terminal-success">
            <span className={`inline-block h-2 w-2 rounded-full ${paused || !connected ? "bg-slate-600" : "bg-terminal-success status-dot-live"}`} />
            {paused ? "STREAM PAUSED" : "LIVE"}
          </div>
        </div>
      </div>

      <div className="terminal-panel">
        <div ref={streamRef} className="h-[520px] overflow-y-auto bg-[#080c11] px-4 py-3 font-mono text-[12px]">
          {events.map((event) => {
            const isDecodedOpen = Boolean(decodedOpen[event.id]);
            const isDecision = event.kind === "decision" || event.action || event.rationale;
            return (
            <div key={event.id} className={`llm-stream-row mb-3 border bg-[#0b1016] p-3 ${isDecision ? "border-terminal-warn/30 shadow-[inset_3px_0_0_rgba(251,191,36,0.55)]" : "border-white/10"}`}>
              <div className="mb-2 flex flex-wrap items-center gap-3">
                <span className="text-slate-600">[{event.timestamp}]</span>
                <span className={`font-semibold ${eventTypeClass(event.type)}`}>{event.type}</span>
                <span className={`border px-2 py-0.5 text-[10px] uppercase ${toneClasses(kindTone(event.kind), true)}`}>{event.kind}</span>
                {event.hasDecodedPayload ? (
                  <button
                    type="button"
                    onClick={() => setDecodedOpen((value) => ({ ...value, [event.id]: !value[event.id] }))}
                    className="border border-terminal-success/30 px-2 py-0.5 text-[10px] uppercase text-terminal-success"
                  >
                    decoded:{isDecodedOpen ? "hide" : "show"}
                  </button>
                ) : null}
              </div>
              <div className="text-slate-300">
                <span className="rounded-sm border border-terminal-info/25 bg-terminal-info/10 px-2 py-0.5 text-terminal-info">{event.src || "unknown"}</span>
                <span className="mx-2 text-slate-700">-&gt;</span>
                <span className="rounded-sm border border-terminal-purple/25 bg-terminal-purple/10 px-2 py-0.5 text-terminal-purple">{event.dst || "unknown"}</span>
                <span className="ml-3 text-slate-600">reset={event.resetId || "-"}</span>
                <span className="ml-3 text-slate-600">epoch={event.epoch ?? "-"}</span>
              </div>
              {event.content ? (
                <div className="mt-3 whitespace-pre-wrap break-words border border-terminal-cyan/10 bg-black/25 p-3 text-slate-300">
                  {event.content}
                </div>
              ) : null}
              {event.hasDecodedPayload && isDecodedOpen ? (
                <div className="mt-3 whitespace-pre-wrap break-words border border-terminal-success/20 bg-terminal-success/5 p-3 text-terminal-success/90">
                  decoded: {event.decodedPayload}
                </div>
              ) : null}
              {event.rationale && event.rationale !== event.content ? (
                <div className="mt-2 whitespace-pre-wrap break-words border-l-2 border-terminal-warn/40 pl-3 text-[11px] text-terminal-warn/85">
                  rationale: {event.rationale}
                </div>
              ) : null}
              {event.rawResponse && event.rawResponse !== event.content ? (
                <div className="mt-2 whitespace-pre-wrap break-words text-[11px] text-terminal-purple/85">
                  raw: {event.rawResponse}
                </div>
              ) : null}
              {(event.validationTags?.length || 0) + (event.persuasionTechniques?.length || 0) > 0 ? (
                <div className="mt-2 text-[11px] text-slate-500">
                  {[...(event.validationTags || []), ...(event.persuasionTechniques || [])].join(" | ")}
                </div>
              ) : null}
              <ConversationMeta event={event} />
            </div>
            );
          })}
          {!events.length ? (
            <div className="py-10 text-center font-mono text-[12px] text-slate-600">
              Waiting for LLM messages, generated payloads, threat analysis, or decision events.
            </div>
          ) : null}
          {!paused ? <div className="pt-1 font-mono text-terminal-cyan animate-blink">|</div> : null}
        </div>
        <div className="border-t border-white/10 px-4 py-3 font-mono text-[10px] text-slate-600">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span>stream:{paused ? "PAUSED" : "LIVE"} | scroll_lock:{scrollLock ? "ON" : "OFF"} | buffer:{events.length}/160</span>
            <span>session_id:{sessionId} | latest:{latest?.timestamp || new Date().toISOString()}</span>
          </div>
        </div>
      </div>
    </section>
  );
}
