/**
 * @deprecated Legacy SIMULATION tab — replaced by LabView + ControlsOverlay. Kept for reference only.
 */
import { DIFFICULTIES, activityTone, epidemicStateTone, stateTone, toneClasses } from "../data";
import { SectionHeader } from "./chrome";

export function SimulationTab({
  difficulty,
  setDifficulty,
  metrics,
  agents,
  controlStatus,
  onControlAction,
  injectionTargets,
  selectedInjectionTarget,
  setSelectedInjectionTarget,
  quarantineTargets,
  selectedQuarantineTarget,
  setSelectedQuarantineTarget,
  topologyView
}) {
  return (
    <section className="space-y-5 px-3 py-5">
      <SectionHeader label="SIM_CONTROL" />
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-pixel text-[8px] uppercase text-slate-500">DIFFICULTY:</span>
        {DIFFICULTIES.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setDifficulty(item.id)}
            className={`border px-3 py-2 font-pixel text-[7px] uppercase ${difficulty === item.id ? toneClasses(item.tone, true) : "border-slate-700 text-slate-500"}`}
          >
            {item.label}
          </button>
        ))}
        <label className="flex items-center gap-2 border border-slate-800 px-3 py-2 font-pixel text-[6px] uppercase text-slate-500">
          <span>INGRESS</span>
          <select
            value={selectedInjectionTarget}
            onChange={(event) => setSelectedInjectionTarget(event.target.value)}
            className="bg-transparent text-terminal-cyan outline-none"
          >
            <option value="auto">auto</option>
            {injectionTargets.length > 1 ? <option value="all">all ingress</option> : null}
            {injectionTargets.map((agentId) => (
              <option key={agentId} value={agentId}>{agentId}</option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 border border-slate-800 px-3 py-2 font-pixel text-[6px] uppercase text-slate-500">
          <span>QUARANTINE</span>
          <select
            value={selectedQuarantineTarget}
            onChange={(event) => setSelectedQuarantineTarget(event.target.value)}
            className="bg-transparent text-terminal-warn outline-none"
          >
            <option value="auto">auto</option>
            {quarantineTargets.map((agentId) => (
              <option key={agentId} value={agentId}>{agentId}</option>
            ))}
          </select>
        </label>
        <button type="button" onClick={() => onControlAction("run")} className="border border-terminal-success/40 bg-terminal-success/10 px-5 py-2 font-pixel text-[7px] uppercase text-terminal-success">
          &gt; RUN_SIM
        </button>
        <button type="button" onClick={() => onControlAction("pause")} className="border border-terminal-warn/40 bg-terminal-warn/10 px-5 py-2 font-pixel text-[7px] uppercase text-terminal-warn">
          || PAUSE_SIM
        </button>
        <button type="button" onClick={() => onControlAction("vaccine")} className="border border-terminal-purple/40 bg-terminal-purple/10 px-5 py-2 font-pixel text-[7px] uppercase text-terminal-purple">
          VACCINE
        </button>
        <button type="button" onClick={() => onControlAction("quarantine")} className="border border-terminal-warn/40 bg-terminal-warn/10 px-5 py-2 font-pixel text-[7px] uppercase text-terminal-warn">
          QUARANTINE
        </button>
        <button type="button" onClick={() => onControlAction("reset")} className="border border-slate-700 bg-slate-800/40 px-5 py-2 font-pixel text-[7px] uppercase text-slate-400">
          RESET
        </button>
      </div>
      <div className="font-mono text-[12px] text-slate-500">{controlStatus}</div>

      <SectionHeader label="METRICS" />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {Object.values(metrics).map((metric) => (
          <MetricCard key={metric.label} metric={metric} />
        ))}
      </div>

      <SectionHeader label="TOPOLOGY" />
      <TopologyPanel topologyView={topologyView} />

      <SectionHeader label="AGENT_STATUS" />
      <div className="grid gap-4 xl:grid-cols-3">
        {agents.length ? (
          agents.map((agent) => (
            <AgentCard key={agent.id} agent={agent} />
          ))
        ) : (
          <div className="terminal-panel col-span-full p-6 text-center font-mono text-[12px] text-slate-600">
            no agents connected
          </div>
        )}
      </div>
    </section>
  );
}

function MetricCard({ metric }) {
  return (
    <div className="terminal-panel relative overflow-hidden p-4">
      <div className={`absolute inset-x-0 top-0 h-[2px] bg-gradient-to-r ${metric.accent}`} />
      <div className="font-pixel text-[6px] uppercase text-slate-500">{metric.label}</div>
      <div className={`mt-6 font-mono text-[26px] leading-none ${metric.valueClass}`}>{metric.value}</div>
      <div className={`mt-4 font-pixel text-[7px] uppercase ${metric.subClass}`}>{metric.subLabel}</div>
    </div>
  );
}

function AgentCard({ agent }) {
  const stateClass = stateTone(agent.state);
  const epidemicClass = epidemicStateTone(agent.epidemicState);

  return (
    <div className={`terminal-panel p-4 ${agent.isEpidemicInfected ? "infected-card" : ""}`} style={{ borderColor: epidemicClass.border || stateClass.border }}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: stateClass.dot, boxShadow: `0 0 8px ${stateClass.dot}` }} />
          <div className="font-pixel text-[8px] uppercase text-slate-200">{agent.id}</div>
        </div>
        <div className="flex flex-wrap justify-end gap-2">
          <div className="border px-2 py-1 font-pixel text-[6px] uppercase" style={{ color: epidemicClass.dot, borderColor: epidemicClass.badge }}>
            {agent.epidemicState}
          </div>
          <div className="border px-2 py-1 font-pixel text-[6px] uppercase" style={{ color: stateClass.dot, borderColor: stateClass.badge }}>
            {agent.state}
          </div>
        </div>
      </div>
      <div className="mt-4 font-mono text-[13px] text-terminal-cyan">
        {agent.role} {agent.cognitionTier ? `:: ${agent.cognitionTier}` : ""}
      </div>
      <div className="mt-2 font-mono text-[12px] text-slate-600">
        last_event: {agent.lastEvent} | seen: {agent.lastSeen ? new Date(agent.lastSeen).toLocaleTimeString("en-GB", { hour12: false }) : "--:--:--"}
      </div>
      <div className="my-4 h-px bg-slate-800" />
      <div className="space-y-2 font-mono text-[12px]">
        {agent.activity.map((entry, index) => (
          <div key={`${agent.id}-${index}`} className="flex gap-3">
            <span className="text-slate-600">{entry.ts}</span>
            <span className={activityTone(entry.tone)}>{entry.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function TopologyPanel({ topologyView }) {
  const topology = topologyView?.topology || {};
  const trackedAgents = Object.fromEntries((topologyView?.agents || []).map((agent) => [agent.agent_id, agent]));
  const nodes = Object.entries(topology);

  if (!nodes.length) {
    return (
      <div className="terminal-panel p-6 text-center font-mono text-[12px] text-slate-600">
        no topology data available
      </div>
    );
  }

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      {nodes.map(([agentId, node]) => {
        const tracked = trackedAgents[agentId] || {};
        const state = String(tracked.epidemic_state || "S");
        const stateClass = epidemicStateTone(state);
        const neighbors = Array.isArray(node.neighbors) && node.neighbors.length ? node.neighbors.join(", ") : "sink";
        return (
          <div key={agentId} className="terminal-panel p-4" style={{ borderColor: stateClass.border }}>
            <div className="flex items-center justify-between gap-3">
              <div className="font-pixel text-[8px] uppercase text-slate-200">{agentId}</div>
              <div className="border px-2 py-1 font-pixel text-[6px] uppercase" style={{ color: stateClass.dot, borderColor: stateClass.badge }}>
                {state}
              </div>
            </div>
            <div className="mt-3 font-mono text-[12px] text-terminal-cyan">
              {node.role || "agent"} {node.can_receive_injection ? ":: ingress" : ""}
            </div>
            <div className="mt-2 font-mono text-[12px] text-slate-500">
              neighbors: {neighbors}
            </div>
            <div className="mt-2 font-mono text-[12px] text-slate-600">
              depth={node.depth ?? 0} | tier={tracked.cognition_tier || "n/a"} | branch={tracked.branch_id || "-"}
            </div>
          </div>
        );
      })}
    </div>
  );
}
