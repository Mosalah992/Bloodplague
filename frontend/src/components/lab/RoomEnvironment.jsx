import { motion } from "framer-motion";
import React, { memo, useMemo } from "react";

function AmbientLayer({ ambient, accent }) {
  const nodes = useMemo(() => {
    const out = [];
    if (ambient === "code") {
      for (let i = 0; i < 12; i += 1) {
        out.push({
          key: `c-${i}`,
          className: "absolute font-mono text-[8px] opacity-20",
          style: { left: `${(i * 17) % 90}%`, top: `${(i * 23) % 85}%`, color: accent?.primary || "#4ade80" },
          text: ["01", "0x", "{};", "=>", "if", "xor"][i % 6]
        });
      }
    } else if (ambient === "led") {
      for (let i = 0; i < 16; i += 1) {
        out.push({
          key: `l-${i}`,
          className: "absolute h-1 w-1 rounded-full",
          style: {
            left: `${8 + (i % 8) * 11}%`,
            top: `${12 + Math.floor(i / 8) * 28}%`,
            backgroundColor: i % 3 === 0 ? accent?.primary || "#ec4899" : "#4b5563",
            boxShadow: i % 3 === 0 ? `0 0 6px ${accent?.primary || "#ec4899"}` : "none"
          }
        });
      }
    } else if (ambient === "holo") {
      for (let i = 0; i < 8; i += 1) {
        out.push({
          key: `h-${i}`,
          className: "absolute h-px w-8 opacity-30",
          style: {
            left: `${10 + i * 11}%`,
            top: `${20 + (i % 4) * 18}%`,
            background: `linear-gradient(90deg, transparent, ${accent?.primary || "#22d3ee"}, transparent)`
          }
        });
      }
    } else if (ambient === "glyph") {
      for (let i = 0; i < 10; i += 1) {
        out.push({
          key: `g-${i}`,
          className: "absolute font-pixel text-[6px] opacity-25",
          style: { left: `${(i * 19) % 88}%`, top: `${(i * 31) % 80}%`, color: accent?.primary || "#c084fc" },
          text: ["*", "?", "0", "1", "k", "λ"][i % 6]
        });
      }
    } else {
      for (let i = 0; i < 10; i += 1) {
        out.push({
          key: `s-${i}`,
          className: "absolute h-0.5 w-0.5 rounded-full",
          style: {
            left: `${(i * 37) % 92}%`,
            top: `${(i * 29) % 88}%`,
            backgroundColor: accent?.primary || "#fbbf24",
            boxShadow: `0 0 4px ${accent?.primary || "#fbbf24"}`
          }
        });
      }
    }
    return out;
  }, [ambient, accent]);

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      {nodes.map((n) =>
        n.text != null ? (
          <motion.span
            key={n.key}
            className={n.className}
            style={n.style}
            animate={{ opacity: [0.15, 0.35, 0.15], y: [0, -4, 0] }}
            transition={{ duration: 3 + (n.key.length % 3), repeat: Infinity, ease: "easeInOut" }}
          >
            {n.text}
          </motion.span>
        ) : (
          <motion.div
            key={n.key}
            className={n.className}
            style={n.style}
            animate={ambient === "led" ? { opacity: [0.4, 1, 0.4] } : { opacity: [0.2, 0.5, 0.2] }}
            transition={{ duration: 1.2 + (n.key.charCodeAt(2) % 5) * 0.1, repeat: Infinity }}
          />
        )
      )}
    </div>
  );
}

function RoomEnvironmentInner({ profile, variant = "normal" }) {
  const { gradientFrom, gradientVia, gradientTo, ambient } = profile;
  const accent = {
    primary: profile.glassAccent === "green" ? "#4ade80" : profile.glassAccent === "pink" ? "#ec4899" : profile.glassAccent === "cyan" ? "#22d3ee" : profile.glassAccent === "purple" ? "#c084fc" : "#fbbf24"
  };

  const overlay =
    variant === "infected"
      ? "rgba(248,113,113,0.18)"
      : variant === "quarantine"
        ? "rgba(59,130,246,0.22)"
        : "transparent";

  return (
    <div className="absolute inset-0 overflow-hidden rounded-xl">
      <div
        className="absolute inset-0"
        style={{
          background: `linear-gradient(152deg, ${gradientFrom} 0%, ${gradientVia} 45%, ${gradientTo} 100%)`
        }}
      />
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_30%_20%,rgba(255,255,255,0.06),transparent_55%)]" />
      <div className="absolute inset-0" style={{ backgroundColor: overlay }} />
      <AmbientLayer ambient={ambient} accent={accent} />
      {/* Floor grid */}
      <div
        className="absolute inset-0 opacity-[0.07]"
        style={{
          backgroundImage: `linear-gradient(rgba(255,255,255,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.5) 1px, transparent 1px)`,
          backgroundSize: "14px 14px"
        }}
      />
    </div>
  );
}

export const RoomEnvironment = memo(RoomEnvironmentInner);
