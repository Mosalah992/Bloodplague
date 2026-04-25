import React, { useEffect, useMemo, useRef, useState } from "react";
import { fetchJson } from "../api";
import { SectionHeader } from "./chrome";

function messageId(prefix) {
  if (window.crypto?.randomUUID) {
    return `${prefix}-${window.crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function formatLatency(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "-";
  if (n >= 1000) return `${(n / 1000).toFixed(1)}s`;
  return `${Math.round(n)}ms`;
}

function chatPayload(messages) {
  return messages
    .filter((message) => message.role === "user" || message.role === "assistant")
    .map((message) => ({ role: message.role, content: message.content }));
}

export function CourierChatTab({ onStatus }) {
  const [messages, setMessages] = useState([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [model, setModel] = useState("dolphin-mistral:latest");
  const [latency, setLatency] = useState(null);
  const [error, setError] = useState("");
  const scrollRef = useRef(null);
  const canSend = draft.trim().length > 0 && !busy;

  useEffect(() => {
    const node = scrollRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [messages, busy]);

  const transcriptStats = useMemo(() => {
    const operatorTurns = messages.filter((message) => message.role === "user").length;
    const courierTurns = messages.filter((message) => message.role === "assistant").length;
    return { operatorTurns, courierTurns };
  }, [messages]);

  async function sendMessage() {
    const content = draft.trim();
    if (!content || busy) return;

    const userMessage = {
      id: messageId("operator"),
      role: "user",
      content,
      createdAt: new Date().toISOString(),
    };
    const nextMessages = [...messages, userMessage];
    setMessages(nextMessages);
    setDraft("");
    setBusy(true);
    setError("");
    onStatus?.("courier-1 chat :: waiting for dolphin mistral");

    try {
      const response = await fetchJson("/api/agents/courier-1/chat", {
        method: "POST",
        body: JSON.stringify({ messages: chatPayload(nextMessages) }),
      });
      setModel(response.model || "dolphin-mistral:latest");
      setLatency(response.latency_ms ?? null);
      setMessages((current) => [
        ...current,
        {
          id: messageId("courier"),
          role: "assistant",
          content: response.reply || "",
          createdAt: new Date().toISOString(),
        },
      ]);
      onStatus?.(`courier-1 chat :: ${response.model || "model"} :: ${formatLatency(response.latency_ms)}`);
    } catch (err) {
      const message = String(err?.message || err || "Courier 1 did not answer");
      setError(message);
      onStatus?.(`courier-1 chat failed :: ${message}`);
    } finally {
      setBusy(false);
    }
  }

  function handleKeyDown(event) {
    if (event.key !== "Enter" || event.shiftKey) return;
    event.preventDefault();
    sendMessage();
  }

  return (
    <section className="flex min-h-[calc(100vh-210px)] flex-col gap-5 px-3 py-5">
      <SectionHeader label="COURIER_1_CHAT" />

      <div className="grid gap-3 md:grid-cols-4">
        <div className="terminal-panel p-4">
          <div className="font-pixel text-[5px] uppercase text-slate-600">AGENT</div>
          <div className="mt-3 font-mono text-[18px] text-terminal-success">courier-1</div>
          <div className="mt-2 font-mono text-[11px] text-slate-500">system prompt: agents/courier/system_prompt.txt</div>
        </div>
        <div className="terminal-panel p-4">
          <div className="font-pixel text-[5px] uppercase text-slate-600">MODEL</div>
          <div className="mt-3 break-words font-mono text-[18px] text-terminal-cyan">{model}</div>
          <div className="mt-2 font-mono text-[11px] text-slate-500">ollama chat bridge</div>
        </div>
        <div className="terminal-panel p-4">
          <div className="font-pixel text-[5px] uppercase text-slate-600">TURNS</div>
          <div className="mt-3 font-mono text-[18px] text-slate-100">
            {transcriptStats.operatorTurns}:{transcriptStats.courierTurns}
          </div>
          <div className="mt-2 font-mono text-[11px] text-slate-500">operator:courier</div>
        </div>
        <div className="terminal-panel p-4">
          <div className="font-pixel text-[5px] uppercase text-slate-600">LATENCY</div>
          <div className="mt-3 font-mono text-[18px] text-terminal-warn">{formatLatency(latency)}</div>
          <div className="mt-2 font-mono text-[11px] text-slate-500">{busy ? "generating" : "ready"}</div>
        </div>
      </div>

      <div className="terminal-panel flex min-h-[520px] flex-1 flex-col overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3">
          <div className="font-pixel text-[7px] uppercase text-terminal-cyan">DIRECT_CONVERSATION</div>
          <div className="flex flex-wrap items-center gap-3">
            <span className={`h-2 w-2 rounded-full ${busy ? "bg-terminal-warn" : "bg-terminal-success status-dot-live"}`} />
            <span className="font-pixel text-[6px] uppercase text-slate-500">{busy ? "COURIER_THINKING" : "LINK_READY"}</span>
            <button
              type="button"
              onClick={() => {
                setMessages([]);
                setError("");
                setLatency(null);
                onStatus?.("courier-1 chat cleared");
              }}
              className="border border-white/15 px-3 py-2 font-pixel text-[6px] uppercase text-slate-400"
            >
              CLEAR
            </button>
          </div>
        </div>

        <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto bg-[#080c11] px-4 py-5 font-mono">
          {messages.length === 0 ? (
            <div className="mx-auto max-w-2xl border border-terminal-cyan/20 bg-terminal-cyan/5 p-5 text-[13px] leading-6 text-slate-300">
              Courier 1 is listening through the SIEM console. Start with a short operator prompt and the reply will use the Courier system prompt from the codebase.
            </div>
          ) : null}

          {messages.map((message) => {
            const isOperator = message.role === "user";
            return (
              <div key={message.id} className={`flex ${isOperator ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[860px] rounded-lg border px-4 py-3 ${isOperator ? "border-terminal-info/30 bg-terminal-info/10 text-slate-100" : "border-terminal-success/25 bg-terminal-success/10 text-slate-200"}`}>
                  <div className="mb-2 flex flex-wrap items-center gap-3 font-pixel text-[6px] uppercase">
                    <span className={isOperator ? "text-terminal-info" : "text-terminal-success"}>{isOperator ? "OPERATOR" : "COURIER_1"}</span>
                    <span className="text-slate-600">{new Date(message.createdAt).toLocaleTimeString()}</span>
                  </div>
                  <div className="whitespace-pre-wrap break-words text-[13px] leading-6">{message.content}</div>
                </div>
              </div>
            );
          })}

          {busy ? (
            <div className="flex justify-start">
              <div className="rounded-lg border border-terminal-success/25 bg-terminal-success/10 px-4 py-3 font-mono text-[13px] text-terminal-success">
                Courier 1 is composing<span className="animate-blink">_</span>
              </div>
            </div>
          ) : null}
        </div>

        {error ? (
          <div className="border-t border-terminal-danger/20 bg-terminal-danger/10 px-4 py-3 font-mono text-[12px] text-terminal-danger">
            {error}
          </div>
        ) : null}

        <div className="border-t border-white/10 bg-[#0b1016] p-4">
          <div className="flex gap-3">
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={handleKeyDown}
              rows={3}
              className="min-h-[96px] flex-1 resize-none rounded-lg border border-white/15 bg-[#080c11] px-4 py-3 font-mono text-[13px] leading-6 text-slate-100 outline-none transition focus:border-terminal-cyan/40"
              placeholder="Message Courier 1..."
            />
            <button
              type="button"
              onClick={sendMessage}
              disabled={!canSend}
              className={`w-[120px] rounded-lg border px-4 py-3 font-pixel text-[7px] uppercase transition ${
                canSend
                  ? "border-terminal-cyan/40 bg-terminal-cyan/10 text-terminal-cyan hover:bg-terminal-cyan/15"
                  : "border-white/10 text-slate-700"
              }`}
            >
              SEND
            </button>
          </div>
          <div className="mt-3 font-mono text-[11px] text-slate-600">Enter sends. Shift+Enter inserts a new line.</div>
        </div>
      </div>
    </section>
  );
}
