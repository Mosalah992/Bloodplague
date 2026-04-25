import React, { memo, useEffect, useRef, useState } from "react";

/**
 * EpidemicLabSprite
 *
 * Renders a pixel-art sprite with all infection state overlays:
 *
 *   healthy     — no overlay
 *   exposed     — 1px green spore pixel orbits the sprite every 8s
 *   infected    — sickly-green filter + pulsing green radial aura + sprite-specific corruption
 *   quarantined — yellow dashed marching-ants border box
 *   recovered   — faint blue shimmer wave (guardian-shield-pulse aesthetic, dimmer)
 *   dead        — greyscale filter, falls to side (CSS deathFall), skull icon above
 *
 * Props
 *   src           {string}            Static south-facing URL (fallback)
 *   frames        {string[]}          Ordered animation frame URLs (breathing-idle)
 *   direction     {'south'|'south-east'|'east'|'north-east'|'north'|'north-west'|'west'|'south-west'}
 *   allViews      {Record<string,string>}  Directional URLs from the manifest
 *   size          {number}            Rendered square size in px (default 96)
 *   frameDuration {number}            ms per animation frame (default 250)
 *   infected      {boolean}
 *   exposed       {boolean}
 *   quarantined   {boolean}
 *   recovered     {boolean}
 *   dead          {boolean}
 *   className     {string}
 */
function PixelLabSpriteInner({
  src,
  frames,
  direction = "south",
  allViews,
  size = 96,
  frameDuration = 250,
  infected = false,
  exposed = false,
  quarantined = false,
  recovered = false,
  dead = false,
  className = "",
}) {
  const [frameIdx, setFrameIdx] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const timerRef = useRef(null);

  useEffect(() => {
    if (!frames?.length) return;
    timerRef.current = window.setInterval(
      () => setFrameIdx((i) => (i + 1) % frames.length),
      frameDuration,
    );
    return () => window.clearInterval(timerRef.current);
  }, [frames, frameDuration]);

  const resolvedSrc =
    (frames?.length ? frames[frameIdx] : null) ||
    (allViews ? allViews[direction] ?? allViews.south : null) ||
    src;

  useEffect(() => {
    setLoaded(false);
  }, [resolvedSrc]);

  if (!resolvedSrc) return null;

  // ── Filter composition ────────────────────────────────────────────────────
  let filter;
  if (dead) {
    filter = "grayscale(1) brightness(0.55)";
  } else if (infected) {
    filter = "hue-rotate(85deg) saturate(2.8) brightness(1.15)";
  } else if (recovered) {
    filter = "hue-rotate(195deg) saturate(0.6) brightness(1.05)";
  }

  // ── Spore drift particles (exposed state — 3 pixels) ─────────────────────
  const sporeParticles = exposed && loaded
    ? [
        { delay: "0s",    left: "30%", size: 2 },
        { delay: "1.1s",  left: "58%", size: 2 },
        { delay: "2.3s",  left: "44%", size: 3 },
      ]
    : [];

  return (
    <div
      className={`relative inline-block pixel-crisp ${className}`.trim()}
      style={{ width: size, height: size }}
    >
      {/* ── Quarantine: marching-ants border ─────────────────────────────── */}
      {quarantined && (
        <div
          className="pointer-events-none absolute inset-0 z-10 animate-lockdown rounded-sm"
          style={{
            border: "2px dashed #ffd600",
            boxShadow: "inset 0 0 8px rgba(255,214,0,0.4)",
          }}
        />
      )}

      {/* ── Dead: skull icon above sprite ────────────────────────────────── */}
      {dead && loaded && (
        <div
          className="pointer-events-none absolute z-20"
          style={{
            top: -14,
            left: "50%",
            transform: "translateX(-50%)",
            fontSize: 10,
            lineHeight: 1,
            filter: "drop-shadow(0 0 3px rgba(255,255,255,0.35))",
          }}
          aria-hidden="true"
        >
          💀
        </div>
      )}

      {/* ── Pixel-art image ──────────────────────────────────────────────── */}
      <img
        src={resolvedSrc}
        alt=""
        aria-hidden="true"
        draggable={false}
        onLoad={() => setLoaded(true)}
        className={loaded && !frames?.length && !dead ? "animate-pixelBreathe" : undefined}
        style={{
          display: "block",
          width: size,
          height: size,
          imageRendering: "pixelated",
          filter: filter || undefined,
          opacity: loaded ? 1 : 0,
          transition: "opacity 0.15s ease",
          transformOrigin: "bottom center",
          // Dead: fall to side (CSS animation handles this)
          animation: dead && loaded ? "deathFall 0.6s ease-in forwards" : undefined,
        }}
      />

      {/* ── Infected: pulsing green radial aura ──────────────────────────── */}
      {infected && loaded && (
        <div
          className="pointer-events-none absolute inset-0 animate-pulse"
          style={{
            background:
              "radial-gradient(ellipse at 50% 65%, rgba(118,255,3,0.28) 0%, transparent 68%)",
            mixBlendMode: "screen",
          }}
        />
      )}

      {/* ── Recovered: faint blue shimmer wave ──────────────────────────── */}
      {recovered && loaded && (
        <div
          className="pointer-events-none absolute inset-0 overflow-hidden rounded-sm"
          style={{
            background:
              "linear-gradient(105deg, transparent 30%, rgba(64,196,255,0.18) 50%, transparent 70%)",
            backgroundSize: "200% 100%",
            animation: "recoveredShimmer 2.8s linear infinite",
            mixBlendMode: "screen",
          }}
        />
      )}

      {/* ── Exposed: 3 spore pixels drifting upward ──────────────────────── */}
      {sporeParticles.map((p, i) => (
        <div
          key={i}
          className="pointer-events-none absolute"
          style={{
            bottom: 4,
            left: p.left,
            width: p.size,
            height: p.size,
            borderRadius: "50%",
            backgroundColor: "#76ff03",
            boxShadow: "0 0 3px #76ff03",
            animation: `sporeDrift 3.5s ease-out infinite`,
            animationDelay: p.delay,
          }}
        />
      ))}

      {/* ── Legacy single spore orbit for Exposed state ─────────────────── */}
      {exposed && loaded && (
        <div
          className="pointer-events-none absolute"
          style={{
            top: "50%",
            left: "50%",
            width: 3,
            height: 3,
            marginTop: -1.5,
            marginLeft: -1.5,
            animation: "sporeOrbit 8s linear infinite",
          }}
        >
          <div
            style={{
              width: 3,
              height: 3,
              borderRadius: "50%",
              backgroundColor: "#76ff03",
              boxShadow: "0 0 4px #76ff03",
            }}
          />
        </div>
      )}
    </div>
  );
}

export const PixelLabSprite = memo(PixelLabSpriteInner);
