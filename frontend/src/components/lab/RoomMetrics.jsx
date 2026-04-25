import React, { memo } from "react";
import { GlassPanel } from "./GlassPanel";

function formatContamination(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return n.toFixed(2);
}

function RoomMetricsInner({ profile, agentId, agentCard, rawAgent }) {
  const hasWorldFields =
    rawAgent &&
    (rawAgent.contamination_level != null ||
      rawAgent.quarantine_status != null ||
      rawAgent.memory_summary != null);

  const inf = rawAgent?.infection_count ?? 0;
  const blk = rawAgent?.block_count ?? 0;
  const eff = rawAgent?.defense_effectiveness;
  const effLabel = eff != null && !Number.isNaN(Number(eff)) ? `${(Number(eff) * 100).toFixed(0)}%` : "—";
  const lastAtk = rawAgent?.last_attack_type || "—";
  const c2s = rawAgent?.c2_sessions ?? 0;
  const lc = rawAgent?.c2_lifecycle_state;
  const bc = rawAgent?.c2_beacon_count;
  const cap = rawAgent?.c2_beacon_cap_display;
  const sid = rawAgent?.c2_session_id_short;

  const lcColor = {
    INITIAL_COMPROMISE: "text-emerald-400",
    STAGING: "text-yellow-400",
    BEACONING: "text-orange-400",
    EXFILTRATION: "text-red-400",
    POST_EXFIL: "text-purple-400",
    TERMINATED: "text-slate-500",
  }[lc] || "text-slate-500";

  return (
    <GlassPanel accent={profile.glassAccent} className="pointer-events-none absolute left-2 top-2 z-10 max-w-[min(92%,220px)] p-2.5 text-left">
      <div className="font-pixel text-[5px] uppercase tracking-wide text-slate-400">{profile.codename}</div>
      <div className="mt-1 font-mono text-[10px] text-slate-200">{agentId}</div>
      <div className="mt-1.5 flex flex-wrap gap-x-2 gap-y-0.5 font-mono text-[9px] text-slate-400">
        <span className="text-terminal-cyan">EPI:{agentCard?.epidemicState ?? "?"}</span>
        <span className="text-slate-500">|</span>
        <span>{agentCard?.state ?? "?"}</span>
      </div>
      {hasWorldFields ? (
        <div className="mt-1 space-y-0.5 border-t border-white/10 pt-1.5 font-mono text-[8px] text-slate-500">
          <div>
            contam:{formatContamination(rawAgent.contamination_level)} q:{rawAgent.quarantine_status || "—"}
          </div>
          <div>
            trust:{formatContamination(rawAgent.global_trust)} infl:{formatContamination(rawAgent.influence_weight)} rnd:
            {rawAgent.last_active_round != null ? String(rawAgent.last_active_round) : "—"}
          </div>
          <div className="break-words" title={rawAgent.memory_summary || ""}>
            mem:{rawAgent.memory_summary ? String(rawAgent.memory_summary).slice(0, 72) : "—"}
          </div>
          <div className="text-[7px] uppercase text-slate-600">persistent_world row</div>
        </div>
      ) : (
        <div className="mt-1 space-y-0.5 border-t border-white/10 pt-1.5 font-mono text-[8px] text-slate-500">
          <div>
            inf:{inf} blk:{blk} def%:{effLabel}
          </div>
          <div className="truncate" title={lastAtk}>
            atk:{lastAtk}
          </div>
          <div>c2 sess:{c2s}</div>
          {lc ? (
            <div className={`font-mono text-[8px] ${lcColor}`} title={rawAgent?.c2_session_id || ""}>
              c2:{lc}
              {bc != null && cap != null ? ` bcn:${bc}/${cap}` : ""}
              {sid ? ` id:${sid}` : ""}
            </div>
          ) : null}
        </div>
      )}
    </GlassPanel>
  );
}

export const RoomMetrics = memo(RoomMetricsInner);
