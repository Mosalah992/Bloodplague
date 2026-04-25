import { motion } from "framer-motion";
import React, { memo, useMemo } from "react";

// ── PCB circuit-board texture (wall background) ──────────────────────────────
function PcbTexture() {
  return (
    <div
      className="pointer-events-none absolute inset-0"
      style={{
        backgroundImage: `
          repeating-linear-gradient(
            0deg,
            transparent 0px, transparent 23px,
            rgba(34,211,238,0.032) 23px, rgba(34,211,238,0.032) 24px
          ),
          repeating-linear-gradient(
            90deg,
            transparent 0px, transparent 23px,
            rgba(34,211,238,0.022) 23px, rgba(34,211,238,0.022) 24px
          )
        `,
      }}
    />
  );
}

// ── Node dots at circuit trace intersections ─────────────────────────────────
function CircuitNodes() {
  const nodes = useMemo(() => {
    // Scatter along edges and corners — avoid center (office canvas content lives there)
    const positions = [
      { x: 2, y: 12 }, { x: 2, y: 36 }, { x: 2, y: 60 }, { x: 2, y: 84 },
      { x: 97, y: 8 }, { x: 97, y: 32 }, { x: 97, y: 56 }, { x: 97, y: 80 },
      { x: 12, y: 3 }, { x: 35, y: 3 }, { x: 58, y: 3 }, { x: 80, y: 3 },
      { x: 10, y: 96 }, { x: 32, y: 96 }, { x: 55, y: 96 }, { x: 78, y: 96 },
      { x: 94, y: 20 }, { x: 5, y: 48 }, { x: 5, y: 72 }, { x: 93, y: 68 },
    ];
    return positions.map((p, i) => ({
      ...p,
      key: `cn-${i}`,
      bright: i % 5 === 0,
      dur: 1.8 + (i % 4) * 0.5,
    }));
  }, []);

  return (
    <div className="pointer-events-none absolute inset-0">
      {nodes.map((n) => (
        <motion.div
          key={n.key}
          className="absolute rounded-full"
          style={{
            left: `${n.x}%`,
            top: `${n.y}%`,
            width: n.bright ? 4 : 2,
            height: n.bright ? 4 : 2,
            marginLeft: n.bright ? -2 : -1,
            marginTop: n.bright ? -2 : -1,
            backgroundColor: "#22d3ee",
            boxShadow: n.bright ? "0 0 5px rgba(34,211,238,0.7)" : "none",
          }}
          animate={{ opacity: n.bright ? [0.25, 0.65, 0.25] : [0.08, 0.22, 0.08] }}
          transition={{ duration: n.dur, repeat: Infinity, ease: "easeInOut" }}
        />
      ))}
    </div>
  );
}

// ── Instrument rail (left or right wall edge) ────────────────────────────────
function InstrumentRail({ side }) {
  const slots = useMemo(
    () =>
      Array.from({ length: 10 }, (_, i) => ({
        key: `${side}-${i}`,
        isRed: i % 4 === 2,
        delay: `${i * 0.22}s`,
        opacity: i % 3 === 0 ? 1 : 0.55,
      })),
    [side]
  );

  const edge = side === "left" ? { left: 0 } : { right: 0 };
  const ledEdge = side === "left" ? { left: 3 } : { right: 3 };

  return (
    <div className="pointer-events-none absolute top-8 bottom-8" style={{ ...edge, width: 12 }}>
      {/* Vertical trace line */}
      <div
        className="absolute inset-y-0"
        style={{
          ...(side === "left" ? { right: 0 } : { left: 0 }),
          width: 1,
          background:
            "linear-gradient(180deg, transparent 0%, rgba(34,211,238,0.20) 15%, rgba(34,211,238,0.20) 85%, transparent 100%)",
        }}
      />
      {/* Status LEDs */}
      {slots.map((s, i) => (
        <div
          key={s.key}
          className="absolute animate-ledBlink"
          style={{
            top: `${6 + i * 9}%`,
            ...ledEdge,
            width: 3,
            height: 3,
            borderRadius: "50%",
            backgroundColor: s.isRed ? "#f87171" : "#22d3ee",
            boxShadow: s.isRed
              ? "0 0 5px rgba(248,113,113,0.75)"
              : "0 0 4px rgba(34,211,238,0.65)",
            animationDelay: s.delay,
            opacity: s.opacity,
          }}
        />
      ))}
    </div>
  );
}

// ── Red cable traces across the floor (SVG) ──────────────────────────────────
// Uses a wide viewBox so paths stay stable regardless of container width.
function CableTraces() {
  return (
    <svg
      className="pointer-events-none absolute bottom-0 left-0 w-full"
      style={{ height: 90, overflow: "visible" }}
      viewBox="0 0 1000 90"
      preserveAspectRatio="none"
    >
      <defs>
        <style>{`
          @keyframes cableFlow {
            0%   { stroke-dashoffset: 120; }
            100% { stroke-dashoffset: 0; }
          }
          @keyframes cableFlowR {
            0%   { stroke-dashoffset: 0; }
            100% { stroke-dashoffset: 120; }
          }
        `}</style>
      </defs>

      {/* Cable A — left to right, sinuous */}
      <path
        d="M 0,62 C 80,42 160,72 280,54 C 400,36 480,68 620,50 C 740,32 860,58 1000,44"
        stroke="rgba(190,35,35,0.32)"
        strokeWidth="2.5"
        fill="none"
        strokeLinecap="round"
      />
      {/* Flow pulse on cable A */}
      <path
        d="M 0,62 C 80,42 160,72 280,54 C 400,36 480,68 620,50 C 740,32 860,58 1000,44"
        stroke="rgba(248,80,60,0.55)"
        strokeWidth="1.5"
        fill="none"
        strokeLinecap="round"
        strokeDasharray="18 80"
        style={{ animation: "cableFlow 2.4s linear infinite" }}
      />

      {/* Cable B — right to left, lower */}
      <path
        d="M 1000,74 C 880,58 760,80 620,66 C 480,52 360,78 200,64 C 100,55 50,70 0,78"
        stroke="rgba(160,28,28,0.24)"
        strokeWidth="2"
        fill="none"
        strokeLinecap="round"
      />
      {/* Flow pulse on cable B (reverse) */}
      <path
        d="M 1000,74 C 880,58 760,80 620,66 C 480,52 360,78 200,64 C 100,55 50,70 0,78"
        stroke="rgba(220,60,40,0.45)"
        strokeWidth="1"
        fill="none"
        strokeLinecap="round"
        strokeDasharray="12 90"
        style={{ animation: "cableFlowR 3.1s linear infinite" }}
      />

      {/* Cable C — shorter crossing segment */}
      <path
        d="M 0,84 C 120,72 240,86 380,76 C 500,66 600,82 720,72 L 1000,70"
        stroke="rgba(170,30,20,0.18)"
        strokeWidth="1.5"
        fill="none"
        strokeLinecap="round"
      />
    </svg>
  );
}

// ── Corner terminal glows (screen light spilling into room corners) ───────────
function CornerGlows() {
  return (
    <>
      {/* Bottom-left: main terminal cyan glow */}
      <div
        className="pointer-events-none absolute bottom-0 left-0"
        style={{
          width: 160,
          height: 100,
          background:
            "radial-gradient(ellipse at 0% 100%, rgba(34,211,238,0.11) 0%, transparent 65%)",
        }}
      />
      {/* Top-left: secondary screen cyan */}
      <div
        className="pointer-events-none absolute left-0 top-0"
        style={{
          width: 100,
          height: 80,
          background:
            "radial-gradient(ellipse at 0% 0%, rgba(34,211,238,0.08) 0%, transparent 60%)",
        }}
      />
      {/* Bottom-right: infection-red cable terminus */}
      <div
        className="pointer-events-none absolute bottom-0 right-0"
        style={{
          width: 140,
          height: 90,
          background:
            "radial-gradient(ellipse at 100% 100%, rgba(200,38,38,0.12) 0%, transparent 60%)",
        }}
      />
      {/* Top-right: dim red server rack glow */}
      <div
        className="pointer-events-none absolute right-0 top-0"
        style={{
          width: 90,
          height: 70,
          background:
            "radial-gradient(ellipse at 100% 0%, rgba(180,30,30,0.07) 0%, transparent 55%)",
        }}
      />
    </>
  );
}

// ── Top header strip — SYS / EPI / NET readouts ──────────────────────────────
function HeaderStrip() {
  return (
    <div
      className="pointer-events-none absolute left-0 right-0 top-0 flex items-center gap-5 px-4"
      style={{
        height: 20,
        background:
          "linear-gradient(180deg, rgba(2,8,18,0.65) 0%, transparent 100%)",
        borderBottom: "1px solid rgba(34,211,238,0.06)",
      }}
    >
      {[
        { label: "SYS:NOMINAL", color: "rgba(34,211,238,0.45)" },
        { label: "EPI:ACTIVE",  color: "rgba(248,113,113,0.55)" },
        { label: "NET:LIVE",    color: "rgba(34,211,238,0.35)" },
      ].map(({ label, color }) => (
        <span key={label} className="font-mono text-[7px]" style={{ color }}>
          {label}
        </span>
      ))}
    </div>
  );
}

// ── Main export ───────────────────────────────────────────────────────────────
function LabEnvironmentLayerInner() {
  return (
    <div className="pointer-events-none absolute inset-0 z-[2] overflow-hidden rounded-2xl">
      <PcbTexture />
      <CornerGlows />
      <HeaderStrip />
      <InstrumentRail side="left" />
      <InstrumentRail side="right" />
      <CircuitNodes />
      <CableTraces />
    </div>
  );
}

export const LabEnvironmentLayer = memo(LabEnvironmentLayerInner);
