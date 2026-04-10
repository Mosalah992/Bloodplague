import { motion } from "framer-motion";
import React, { memo, useEffect, useMemo, useState } from "react";
import { getAgentVisualProfile } from "../../agents/agentIdentity";
import { useSpriteAnimation } from "../../hooks/useSpriteAnimation";
import { PixelCharacter } from "./PixelCharacter";
import { RoomEnvironment } from "./RoomEnvironment";
import { RoomMetrics } from "./RoomMetrics";

function resolveSpriteMode({ agentCard, cues, now }) {
  const state = String(agentCard?.state || "").toLowerCase();
  const epi = String(agentCard?.epidemicState || "S").toUpperCase();
  if (state.includes("quarantine")) return "idle";
  const c = cues || {};
  if (c.attack && c.attack > now) return "attack";
  if (c.defend && c.defend > now) return "defend";
  if (agentCard?.isEpidemicInfected || epi.startsWith("I")) return "infected";
  if (epi === "R") return "defend";
  return "idle";
}

function resolveRoomVariant({ agentCard }) {
  const state = String(agentCard?.state || "").toLowerCase();
  if (state.includes("quarantine")) return "quarantine";
  if (agentCard?.isEpidemicInfected) return "infected";
  return "normal";
}

function AgentRoomInner({ agentId, agentCard, rawAgent, roomCues, title }) {
  const profile = useMemo(() => getAgentVisualProfile(agentId), [agentId]);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 160);
    return () => window.clearInterval(id);
  }, []);
  const cues = roomCues?.[agentId];
  const spriteMode = resolveSpriteMode({ agentCard, cues, now });
  const variant = resolveRoomVariant({ agentCard });
  const frames = profile.spriteSet[spriteMode] || profile.spriteSet.idle;
  const frame = useSpriteAnimation(frames, 280);
  const scale = profile.codename === "SENTINEL" ? 2.4 : 2.8;

  return (
    <motion.div
      layout
      title={title || `${profile.codename} — ${agentId}`}
      className="relative min-h-[200px] overflow-hidden rounded-xl border border-white/10 shadow-glass will-change-transform"
      initial={false}
      animate={
        cues?.pulse && cues.pulse > now
          ? { boxShadow: "0 0 0 1px rgba(34,211,238,0.35), inset 0 0 20px rgba(34,211,238,0.12)" }
          : { boxShadow: "0 8px 32px rgba(0,0,0,0.35), inset 0 1px 0 rgba(255,255,255,0.05)" }
      }
      transition={{ duration: 0.35 }}
    >
      <RoomEnvironment profile={profile} variant={variant} />
      {variant === "quarantine" && (
        <div className="pointer-events-none absolute inset-0 z-[5] animate-lockdown bg-gradient-to-b from-blue-500/10 via-blue-600/20 to-blue-900/30" />
      )}
      <RoomMetrics profile={profile} agentId={agentId} agentCard={agentCard} rawAgent={rawAgent} />
      <div className="relative z-[1] flex h-full min-h-[200px] flex-col items-center justify-end pb-6 pt-16">
        <PixelCharacter frame={frame} cellSize={4} scale={scale} className="drop-shadow-[0_4px_12px_rgba(0,0,0,0.5)]" />
      </div>
    </motion.div>
  );
}

export const AgentRoom = memo(AgentRoomInner);
