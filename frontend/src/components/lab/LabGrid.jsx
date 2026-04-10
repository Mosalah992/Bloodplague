import React, { memo, useMemo, useRef } from "react";
import { getAgentVisualProfile } from "../../agents/agentIdentity";
import { AgentRoom } from "./AgentRoom";
import { CableNetwork } from "./CableNetwork";
import { buildLabLayout } from "./labLayout";

function LabGridInner({ agents, controlAgents, topology, bursts, roomCues }) {
  const containerRef = useRef(null);
  const roomElementsRef = useRef({});

  const agentIds = useMemo(() => agents.map((a) => a.id), [agents]);
  const { gridTemplateAreas, placement } = useMemo(() => buildLabLayout(agentIds), [agentIds]);

  const rawById = useMemo(() => {
    const m = {};
    if (controlAgents && typeof controlAgents === "object") {
      for (const [k, v] of Object.entries(controlAgents)) {
        m[k] = v;
      }
    }
    return m;
  }, [controlAgents]);

  const setRoomEl = (id) => (el) => {
    if (el) roomElementsRef.current[id] = el;
    else delete roomElementsRef.current[id];
  };

  return (
    <div ref={containerRef} className="relative min-h-[480px] w-full">
      <div
        className="relative z-[1] grid gap-3 sm:gap-4"
        style={{
          gridTemplateAreas: gridTemplateAreas,
          gridTemplateColumns: "minmax(0,1fr) minmax(0,1fr)"
        }}
      >
        {agents.map((agent) => (
          <div key={agent.id} ref={setRoomEl(agent.id)} style={{ gridArea: placement[agent.id] || "auto" }}>
            <AgentRoom
              agentId={agent.id}
              agentCard={agent}
              rawAgent={rawById[agent.id]}
              roomCues={roomCues}
              title={`${getAgentVisualProfile(agent.id).codename} · ${agent.id}`}
            />
          </div>
        ))}
      </div>
      <CableNetwork
        containerRef={containerRef}
        roomElementsRef={roomElementsRef}
        topology={topology}
        bursts={bursts}
      />
    </div>
  );
}

export const LabGrid = memo(LabGridInner);
