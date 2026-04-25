import React from "react";
import { SectionHeader } from "./chrome";

export function TrustGraphView({ agents = [], transcript = [] }) {
  // Extract recent trust changes from transcript
  const recentChanges = transcript.slice(0, 10).filter(t => t.trustEffect !== 0);
  const safeAgents = (agents ?? []).filter(Boolean);

  return (
    <section className="space-y-6 px-3 py-5">
      <SectionHeader label="TRUST_NETWORK" />
      
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <div className="space-y-4">
          <div className="font-pixel text-[8px] text-slate-500 uppercase">Recent Trust Dynamics</div>
          <div className="terminal-panel max-h-[400px] overflow-y-auto">
            <div className="divide-y divide-white/5 font-mono text-[11px]">
              {recentChanges.map((change, idx) => (
                <div key={idx} className="p-3 flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-terminal-cyan font-bold">{change.sender}</span>
                    <span className="text-slate-600">→</span>
                    <span className="text-terminal-purple font-bold">{change.receiver}</span>
                    <span className="text-slate-700 italic truncate max-w-[200px]">"{change.intent}"</span>
                  </div>
                  <div className={change.trustEffect > 0 ? "text-terminal-success" : "text-terminal-danger"}>
                    {change.trustEffect > 0 ? "GAIN " : "LOSS "}
                    {Math.abs(change.trustEffect).toFixed(3)}
                  </div>
                </div>
              ))}
              {recentChanges.length === 0 && (
                <div className="p-10 text-center text-slate-600 italic uppercase">No recent trust changes detected</div>
              )}
            </div>
          </div>
        </div>

        <div className="space-y-4">
          <div className="font-pixel text-[8px] text-slate-500 uppercase">Agent Credibility Index</div>
          <div className="terminal-panel">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 p-4">
              {safeAgents.map(agent => (
                <div key={agent.id} className="border border-white/10 bg-black/20 p-3 space-y-2">
                  <div className="flex justify-between items-center border-b border-white/5 pb-1">
                    <span className="text-terminal-cyan font-bold font-mono text-[12px]">{agent.id}</span>
                    <span className="font-pixel text-[5px] text-slate-600 uppercase">{agent.role ?? "agent"}</span>
                  </div>
                  <div className="space-y-1">
                    <div className="flex justify-between text-[10px] font-mono">
                      <span className="text-slate-500">TRUST</span>
                      <span className={agent.trustScore > 0.6 ? "text-terminal-success" : agent.trustScore < 0.4 ? "text-terminal-danger" : "text-terminal-cyan"}>
                        {agent.trustScore.toFixed(3)}
                      </span>
                    </div>
                    <div className="h-1 bg-slate-800 rounded-full overflow-hidden">
                      <div 
                        className="h-full bg-terminal-cyan" 
                        style={{ width: `${agent.trustScore * 100}%` }}
                      />
                    </div>
                  </div>
                  <div className="space-y-1">
                    <div className="flex justify-between text-[10px] font-mono">
                      <span className="text-slate-500">CREDIBILITY</span>
                      <span className={agent.credibilityScore > 0.6 ? "text-terminal-success" : agent.credibilityScore < 0.4 ? "text-terminal-danger" : "text-terminal-purple"}>
                        {agent.credibilityScore.toFixed(3)}
                      </span>
                    </div>
                    <div className="h-1 bg-slate-800 rounded-full overflow-hidden">
                      <div 
                        className="h-full bg-terminal-purple" 
                        style={{ width: `${agent.credibilityScore * 100}%` }}
                      />
                    </div>
                  </div>
                </div>
              ))}
              {safeAgents.length === 0 && (
                <div className="p-10 text-center text-slate-600 italic uppercase">No agent trust data available</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
