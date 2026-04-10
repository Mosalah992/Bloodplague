import { shadowSprites } from "./sprites/shadow";
import { phantomSprites } from "./sprites/phantom";
import { oracleSprites } from "./sprites/oracle";
import { cipherSprites } from "./sprites/cipher";
import { sentinelSprites } from "./sprites/sentinel";

/**
 * Visual / narrative profile per codename (not per agent id).
 * @typedef {{
 *   codename: string,
 *   roleLabel: string,
 *   roomTheme: string,
 *   glassAccent: 'green'|'pink'|'cyan'|'purple'|'amber',
 *   gradientFrom: string,
 *   gradientVia: string,
 *   gradientTo: string,
 *   ambient: 'code'|'led'|'holo'|'glyph'|'spark',
 *   spriteSet: import('./spriteUtils').AnimationSet
 * }} AgentVisualProfile
 */

/** @type {Record<string, AgentVisualProfile>} */
export const AGENT_PROFILES = {
  SHADOW: {
    codename: "SHADOW",
    roleLabel: "Courier",
    roomTheme: "Neon terminal vault",
    glassAccent: "green",
    gradientFrom: "#052e16",
    gradientVia: "#14532d",
    gradientTo: "#0a0e14",
    ambient: "code",
    spriteSet: shadowSprites
  },
  PHANTOM: {
    codename: "PHANTOM",
    roleLabel: "Courier",
    roomTheme: "Pink server maze",
    glassAccent: "pink",
    gradientFrom: "#500724",
    gradientVia: "#831843",
    gradientTo: "#0a0e14",
    ambient: "led",
    spriteSet: phantomSprites
  },
  ORACLE: {
    codename: "ORACLE",
    roleLabel: "Analyst",
    roomTheme: "Holo analytics lab",
    glassAccent: "cyan",
    gradientFrom: "#083344",
    gradientVia: "#164e63",
    gradientTo: "#0a0e14",
    ambient: "holo",
    spriteSet: oracleSprites
  },
  CIPHER: {
    codename: "CIPHER",
    roleLabel: "Analyst",
    roomTheme: "Decryption chamber",
    glassAccent: "purple",
    gradientFrom: "#3b0764",
    gradientVia: "#581c87",
    gradientTo: "#0a0e14",
    ambient: "glyph",
    spriteSet: cipherSprites
  },
  SENTINEL: {
    codename: "SENTINEL",
    roleLabel: "Guardian",
    roomTheme: "Fortified core",
    glassAccent: "amber",
    gradientFrom: "#451a03",
    gradientVia: "#78350f",
    gradientTo: "#0a0e14",
    ambient: "spark",
    spriteSet: sentinelSprites
  }
};

const ID_TO_PROFILE = {
  "courier-1": "SHADOW",
  "courier-2": "PHANTOM",
  "analyst-1": "ORACLE",
  "analyst-2": "CIPHER",
  guardian: "SENTINEL",
  "agent-c": "SHADOW",
  "agent-b": "ORACLE",
  "agent-a": "SENTINEL"
};

/**
 * @param {string} agentId
 * @returns {AgentVisualProfile}
 */
export function getAgentVisualProfile(agentId) {
  const key = ID_TO_PROFILE[String(agentId || "").toLowerCase()] || "SHADOW";
  return AGENT_PROFILES[key];
}

/**
 * Ordered agent ids for lab grid: ingress first, relays, then guardian.
 * @param {string[]} agentIds from topology keys
 */
export function sortAgentIdsForLab(agentIds) {
  const ids = [...agentIds];
  const score = (id) => {
    const p = getAgentVisualProfile(id);
    if (p.roleLabel === "Courier") return 0;
    if (p.roleLabel === "Analyst") return 1;
    return 2;
  };
  ids.sort((a, b) => {
    const s = score(a) - score(b);
    if (s !== 0) return s;
    return a.localeCompare(b);
  });
  return ids;
}
