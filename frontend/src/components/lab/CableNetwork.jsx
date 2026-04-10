import { motion } from "framer-motion";
import React, { memo, useLayoutEffect, useState } from "react";

function undirectedEdges(topology) {
  if (!topology || typeof topology !== "object") return [];
  const seen = new Set();
  const out = [];
  for (const [src, neighbors] of Object.entries(topology)) {
    for (const dst of neighbors || []) {
      const key = [String(src), String(dst)].sort().join("|");
      if (seen.has(key)) continue;
      seen.add(key);
      out.push([String(src), String(dst)]);
    }
  }
  return out;
}

function BurstParticle({ from, to, color }) {
  return (
    <motion.circle
      r="3"
      fill={color}
      initial={{ cx: from.x, cy: from.y, opacity: 0.95 }}
      animate={{ cx: to.x, cy: to.y, opacity: 0.15 }}
      transition={{ duration: 1.05, ease: "easeInOut" }}
    />
  );
}

function CableNetworkInner({ containerRef, roomElementsRef, topology, bursts }) {
  const [geom, setGeom] = useState({ w: 1, h: 1, centers: {}, paths: [] });

  useLayoutEffect(() => {
    const root = containerRef?.current;
    if (!root) return undefined;

    const measure = () => {
      const rect = root.getBoundingClientRect();
      const map = roomElementsRef?.current || {};
      const centers = {};
      for (const [id, el] of Object.entries(map)) {
        if (!el || typeof el.getBoundingClientRect !== "function") continue;
        const r = el.getBoundingClientRect();
        centers[id] = {
          x: r.left - rect.left + r.width / 2,
          y: r.top - rect.top + r.height / 2
        };
      }
      const paths = [];
      for (const [a, b] of undirectedEdges(topology)) {
        const ca = centers[a];
        const cb = centers[b];
        if (!ca || !cb) continue;
        const mx = (ca.x + cb.x) / 2;
        const my = (ca.y + cb.y) / 2 - 24;
        paths.push({ key: `${a}-${b}`, d: `M ${ca.x} ${ca.y} Q ${mx} ${my} ${cb.x} ${cb.y}` });
      }
      setGeom({ w: Math.max(1, rect.width), h: Math.max(1, rect.height), centers, paths });
    };

    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(root);
    window.addEventListener("resize", measure);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [containerRef, roomElementsRef, topology, bursts]);

  return (
    <svg
      className="pointer-events-none absolute left-0 top-0 z-[2]"
      width={geom.w}
      height={geom.h}
      viewBox={`0 0 ${geom.w} ${geom.h}`}
      preserveAspectRatio="none"
    >
      <defs>
        <filter id="cable-glow" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="1.2" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>
      {geom.paths.map((p) => (
        <path
          key={p.key}
          d={p.d}
          fill="none"
          stroke="rgba(148, 163, 184, 0.28)"
          strokeWidth="2"
          filter="url(#cable-glow)"
        />
      ))}
      {bursts.map((b) => {
        const ca = geom.centers[b.from];
        const cb = geom.centers[b.to];
        if (!ca || !cb) return null;
        return <BurstParticle key={b.id} from={ca} to={cb} color={b.color} />;
      })}
    </svg>
  );
}

export const CableNetwork = memo(CableNetworkInner);
