import { sortAgentIdsForLab } from "../../agents/agentIdentity";

/**
 * @param {string[]} agentIds
 * @returns {{ gridTemplateAreas: string, placement: Record<string, string> }}
 */
export function buildLabLayout(agentIds) {
  const ids = [...new Set((agentIds || []).filter(Boolean))];
  const sorted = sortAgentIdsForLab(ids);

  const isLegacy =
    sorted.includes("agent-c") && sorted.includes("agent-b") && sorted.includes("agent-a") && sorted.length === 3;

  if (isLegacy) {
    return {
      gridTemplateAreas: `"c1 c1" "a1 a1" "gv gv"`,
      placement: { "agent-c": "c1", "agent-b": "a1", "agent-a": "gv" }
    };
  }

  const placement = {};
  if (sorted.includes("courier-1")) placement["courier-1"] = "c1";
  if (sorted.includes("courier-2")) placement["courier-2"] = "c2";
  if (sorted.includes("analyst-1")) placement["analyst-1"] = "a1";
  if (sorted.includes("analyst-2")) placement["analyst-2"] = "a2";
  if (sorted.includes("guardian")) placement.guardian = "gv";

  return {
    gridTemplateAreas: `"c1 c2" "a1 a2" "gv gv"`,
    placement
  };
}
