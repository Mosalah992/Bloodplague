import React, { memo } from "react";
import { SectionHeader } from "../chrome";
import { LabGrid } from "./LabGrid";

function LabViewInner({ agents, controlAgents, topology, bursts, roomCues, controlStatus }) {
  return (
    <section className="space-y-4 px-1 py-4 sm:px-3">
      <SectionHeader label="RETRO_LAB" />
      <p className="font-mono text-[11px] text-slate-500">
        Each agent runs in an isolated ecosystem. Cables follow the active topology; particles reflect live SIEM traffic.
      </p>
      <LabGrid agents={agents} controlAgents={controlAgents} topology={topology} bursts={bursts} roomCues={roomCues} />
      <div className="font-mono text-[11px] text-slate-500">{controlStatus}</div>
    </section>
  );
}

export const LabView = memo(LabViewInner);
