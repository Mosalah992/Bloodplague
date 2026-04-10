/**
 * Build a sprite frame from rows of single-character color keys.
 * "." and " " = transparent
 */
export function frameFromKeys(rows, palette) {
  return rows.map((row) =>
    row.split("").map((ch) => {
      if (ch === "." || ch === " ") return null;
      return palette[ch] ?? null;
    })
  );
}

/** Pad each mode so all modes share the same frame count (sprite cycling stays in sync). */
export function normalizeAnimationSet(sets, fallbackFrame) {
  const keys = ["idle", "attack", "defend", "infected"];
  let maxLen = 1;
  for (const k of keys) {
    maxLen = Math.max(maxLen, sets[k]?.length || 0);
  }
  const out = {};
  for (const k of keys) {
    const frames = sets[k]?.length ? [...sets[k]] : [fallbackFrame];
    while (frames.length < maxLen) {
      frames.push(frames[frames.length - 1]);
    }
    out[k] = frames;
  }
  return out;
}
