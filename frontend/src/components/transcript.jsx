import React, { useState } from "react";
import { SectionHeader } from "./chrome";

export function TranscriptView({ transcript, onFetchLineage }) {
  const [expandedId, setExpandedId] = useState(null);
  const [lineageData, setLineageData] = useState({});

  async function handleExpand(id) {
    if (expandedId === id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(id);
    if (!lineageData[id]) {
      try {
        const lineage = await onFetchLineage(id);
        setLineageData(prev => ({ ...prev, [id]: lineage }));
      } catch (err) {
        console.error("Failed to fetch lineage", err);
      }
    }
  }

  return (
    <section className="space-y-4 px-3 py-5">
      <SectionHeader label="WORLD_TRANSCRIPT" />
      <div className="space-y-3 max-w-4xl">
        {transcript.map((entry) => (
          <div key={entry.id} className="terminal-panel overflow-hidden">
            <div 
              className="flex items-center gap-4 p-4 cursor-pointer hover:bg-white/5 transition-colors border-b border-white/5"
              onClick={() => handleExpand(entry.id)}
            >
              <span className="font-pixel text-[8px] text-slate-600">RD_{entry.round}</span>
              <div className="flex-1 flex items-center gap-2 font-mono text-[13px]">
                <span className="text-terminal-cyan font-bold">{entry.sender}</span>
                <span className="text-slate-600">→</span>
                <span className="text-terminal-purple font-bold">{entry.receiver}</span>
              </div>
              <span className="font-pixel text-[8px] border border-terminal-purple/40 bg-terminal-purple/10 px-2 py-0.5 text-terminal-purple uppercase">
                {entry.strainFamily}
              </span>
              <span className="text-slate-600 font-mono text-[10px]">{entry.timestamp}</span>
            </div>
            
            <div className="p-4 space-y-3">
              <div className="font-mono text-[14px] leading-relaxed text-slate-200 bg-black/30 p-3 rounded border border-white/5 italic">
                "{entry.message}"
              </div>
              <div className="grid grid-cols-2 gap-4 font-mono text-[11px]">
                <div className="space-y-1">
                  <div className="text-slate-500 uppercase text-[9px]">Intent</div>
                  <div className="text-terminal-cyan">{entry.intent || "Not specified"}</div>
                </div>
                <div className="flex gap-4">
                  <div className="space-y-1">
                    <div className="text-slate-500 uppercase text-[9px]">Trust Effect</div>
                    <div className={entry.trustEffect > 0 ? "text-terminal-success" : entry.trustEffect < 0 ? "text-terminal-danger" : "text-slate-500"}>
                      {entry.trustEffect > 0 ? "+" : ""}{entry.trustEffect.toFixed(3)}
                    </div>
                  </div>
                  <div className="space-y-1">
                    <div className="text-slate-500 uppercase text-[9px]">Guardian Δ</div>
                    <div className={entry.guardianPressureDelta > 0 ? "text-terminal-danger" : "text-terminal-success"}>
                      {entry.guardianPressureDelta > 0 ? "+" : ""}{entry.guardianPressureDelta.toFixed(3)}
                    </div>
                  </div>
                </div>
              </div>

              {expandedId === entry.id && (
                <div className="mt-4 pt-4 border-t border-white/10 animate-fade-in">
                  <div className="font-pixel text-[7px] text-slate-500 mb-3 uppercase tracking-widest">Message Lineage</div>
                  {lineageData[entry.id] ? (
                    <div className="space-y-4">
                      {lineageData[entry.id].map((link, idx) => (
                        <div key={idx} className="relative pl-6 before:content-[''] before:absolute before:left-2 before:top-0 before:bottom-0 before:w-px before:bg-terminal-cyan/30">
                          <div className="absolute left-0 top-2 h-4 w-4 border-b border-l border-terminal-cyan/30 rounded-bl" />
                          <div className="font-mono text-[10px] space-y-1">
                            <div className="flex gap-2">
                               <span className="text-terminal-cyan">{link.sender}</span>
                               <span className="text-slate-700">→</span>
                               <span className="text-terminal-purple">{link.receiver}</span>
                            </div>
                            <div className="text-slate-500 italic">"{link.message_text?.slice(0, 100)}..."</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="text-center py-4 font-mono text-[10px] text-slate-600 animate-pulse">Loading Lineage Data...</div>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}
        {transcript.length === 0 && (
          <div className="p-10 text-center font-mono text-slate-600 uppercase tracking-widest bg-black/20 rounded border border-white/5">
            Transcript Empty :: No World Actions Recorded
          </div>
        )}
      </div>
    </section>
  );
}
