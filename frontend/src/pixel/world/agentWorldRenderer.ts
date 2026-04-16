import { WORLD_TILE_SIZE } from '../constants.js';
import type { WorldState } from './worldState.js';

const ROLE_COLORS: Record<string, { body: string; glow: string; label: string }> = {
  'courier-1': { body: '#fb923c', glow: '#f9731680', label: 'C1' },
  'courier-2': { body: '#f97316', glow: '#f9731680', label: 'C2' },
  'analyst-1': { body: '#4ade80', glow: '#22c55e80', label: 'A1' },
  'analyst-2': { body: '#22c55e', glow: '#16a34a80', label: 'A2' },
  'guardian':  { body: '#a78bfa', glow: '#8b5cf680', label: 'G' },
};

const INFECTION_STATE_TINTS: Record<string, string> = {
  'I_R': '#fbbf24',
  'I_C': '#ef4444',
  'I_X': '#dc2626',
  'Q':   '#6366f1',
  'P':   '#f43f5e',
};

export function renderAgentLayer(
  ctx: CanvasRenderingContext2D,
  state: WorldState,
  elapsed: number,
): void {
  const s = WORLD_TILE_SIZE;

  for (const [agentId, pos] of state.agentPositions) {
    const colors = ROLE_COLORS[agentId] ?? { body: '#888', glow: '#88888880', label: '?' };
    const px = pos.col * s + s / 2;
    const py = pos.row * s + s / 2;

    const glowRadius = (s * 0.75) + Math.sin(elapsed * 2 + pos.col) * 2;
    const gradient = ctx.createRadialGradient(px, py, 0, px, py, glowRadius);
    gradient.addColorStop(0, colors.glow);
    gradient.addColorStop(1, 'transparent');
    ctx.fillStyle = gradient;
    ctx.beginPath();
    ctx.arc(px, py, glowRadius, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = colors.body;
    ctx.beginPath();
    ctx.arc(px, py, s * 0.4, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = '#fff';
    ctx.font = `bold ${s * 0.35}px monospace`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(colors.label, px, py);

    const epidemicState = (state as any).visualState?.agents?.[agentId]?.epidemicState ?? 'S';
    const tint = INFECTION_STATE_TINTS[epidemicState];
    if (tint) {
      ctx.fillStyle = tint + '88';
      ctx.beginPath();
      ctx.arc(px, py, s * 0.45, 0, Math.PI * 2);
      ctx.fill();
    }
  }
}
