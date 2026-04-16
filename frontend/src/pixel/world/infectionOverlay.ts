import type { WorldState } from './worldState.js';

const SPREAD_RADIUS = 2;
const SPREAD_FRACTION = 0.08;
const DECAY_PER_SEC = 0.005;

export function applyContaminationEvent(
  state: WorldState,
  col: number,
  row: number,
  intensity: number,
): void {
  state.setContaminationTile(col, row, state.getContaminationLevel(col, row) + intensity);

  for (let dr = -SPREAD_RADIUS; dr <= SPREAD_RADIUS; dr++) {
    for (let dc = -SPREAD_RADIUS; dc <= SPREAD_RADIUS; dc++) {
      if (dr === 0 && dc === 0) continue;
      const dist = Math.sqrt(dr * dr + dc * dc);
      if (dist > SPREAD_RADIUS) continue;
      const bleed = intensity * SPREAD_FRACTION * (1 - dist / SPREAD_RADIUS);
      const tc = col + dc;
      const tr = row + dr;
      state.setContaminationTile(tc, tr, state.getContaminationLevel(tc, tr) + bleed);
    }
  }
}

export function tickContaminationDecay(state: WorldState, dt: number): void {
  const toUpdate: [string, number][] = [];
  for (const [key, level] of state.contaminationTiles) {
    toUpdate.push([key, level - DECAY_PER_SEC * dt]);
  }
  for (const [key, next] of toUpdate) {
    const [c, r] = key.split(',').map(Number);
    state.setContaminationTile(c, r, next);
  }
}
