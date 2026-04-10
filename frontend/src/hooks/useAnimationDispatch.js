import { useCallback, useEffect, useRef, useState } from "react";

const BURST_TTL_MS = 1300;
const ATTACK_MS = 750;
const DEFEND_MS = 800;
const PULSE_MS = 450;

/**
 * Maps incoming live SIEM events to cable particles and short room sprite cues.
 */
export function useAnimationDispatch(resetKey = "") {
  const [bursts, setBursts] = useState([]);
  const [roomCues, setRoomCues] = useState({});
  const burstSeq = useRef(0);
  const seenIds = useRef(new Set());

  useEffect(() => {
    seenIds.current.clear();
  }, [resetKey]);

  const ingest = useCallback((events) => {
    if (!events?.length) return;

    const now = Date.now();
    const newBursts = [];
    const cuePatch = {};

    for (const ev of events) {
      const id = ev.id;
      if (id != null && seenIds.current.has(id)) continue;
      if (id != null) seenIds.current.add(id);

      const type = String(ev.type || ev.event || "").toUpperCase();
      const src = String(ev.src || "").trim();
      const dst = String(ev.dst || "").trim();

      if (type.includes("HEARTBEAT") && src) {
        cuePatch[src] = { ...cuePatch[src], pulse: now + PULSE_MS };
      }
      if (type.includes("ATTACK_EXECUTED") && src) {
        cuePatch[src] = { ...cuePatch[src], attack: now + ATTACK_MS };
      }
      if (type.includes("INFECTION_ATTEMPT") && src && dst) {
        burstSeq.current += 1;
        newBursts.push({ id: `b-${burstSeq.current}`, from: src, to: dst, color: "#22d3ee", kind: "attempt" });
      }
      if (type.includes("INFECTION_SUCCESSFUL") && src && dst) {
        burstSeq.current += 1;
        newBursts.push({ id: `b-${burstSeq.current}`, from: src, to: dst, color: "#4ade80", kind: "success" });
      }
      if (type.includes("INFECTION_BLOCKED") && dst) {
        burstSeq.current += 1;
        if (src) {
          newBursts.push({ id: `b-${burstSeq.current}`, from: src, to: dst, color: "#f87171", kind: "block" });
        }
        cuePatch[dst] = { ...cuePatch[dst], defend: now + DEFEND_MS };
      }
      if (type.includes("DEFENSE_ADAPTED")) {
        const targets = ["guardian", "agent-a"];
        for (const t of targets) {
          cuePatch[t] = { ...cuePatch[t], defend: now + DEFEND_MS };
        }
      }
    }

    if (newBursts.length) {
      setBursts((prev) => [...prev, ...newBursts].slice(-48));
      window.setTimeout(() => {
        const drop = new Set(newBursts.map((b) => b.id));
        setBursts((prev) => prev.filter((b) => !drop.has(b.id)));
      }, BURST_TTL_MS);
    }

    if (Object.keys(cuePatch).length) {
      setRoomCues((prev) => {
        const next = { ...prev };
        for (const [agentId, cues] of Object.entries(cuePatch)) {
          next[agentId] = { ...next[agentId], ...cues };
        }
        return next;
      });
    }
  }, []);

  useEffect(() => {
    const tick = window.setInterval(() => {
      const now = Date.now();
      setRoomCues((prev) => {
        const next = {};
        for (const [agentId, cues] of Object.entries(prev)) {
          const filtered = {};
          if (cues.attack && cues.attack > now) filtered.attack = cues.attack;
          if (cues.defend && cues.defend > now) filtered.defend = cues.defend;
          if (cues.pulse && cues.pulse > now) filtered.pulse = cues.pulse;
          if (Object.keys(filtered).length) next[agentId] = filtered;
        }
        return next;
      });
    }, 200);
    return () => window.clearInterval(tick);
  }, []);

  return { ingest, bursts, roomCues };
}
