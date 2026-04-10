import { useEffect, useState } from "react";

/**
 * Cycle through sprite frames for a given mode.
 * @param {string[][][]} frames
 * @param {number} intervalMs
 */
export function useSpriteAnimation(frames, intervalMs = 260) {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    setIndex(0);
  }, [frames]);

  useEffect(() => {
    if (!frames?.length) return undefined;
    const id = window.setInterval(() => {
      setIndex((n) => (n + 1) % frames.length);
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [frames, intervalMs]);

  return frames?.[index] || frames?.[0] || [];
}
