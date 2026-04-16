import { WORLD_TILE_SIZE } from '../constants.js';

interface StructureRenderSpec {
  fillColor: string;
  strokeColor: string;
  symbol: string;
  pulse?: boolean;
}

const SPECS: Record<string, StructureRenderSpec> = {
  barrier:         { fillColor: '#ef444455', strokeColor: '#ef4444', symbol: '█' },
  checkpoint:      { fillColor: '#f59e0b55', strokeColor: '#f59e0b', symbol: '⬡' },
  gate:            { fillColor: '#3b82f655', strokeColor: '#3b82f6', symbol: '◧' },
  watch_post:      { fillColor: '#8b5cf655', strokeColor: '#8b5cf6', symbol: '◈', pulse: true },
  quarantine_wall: { fillColor: '#dc262699', strokeColor: '#dc2626', symbol: '▓' },
};

export function renderStructureLayer(
  ctx: CanvasRenderingContext2D,
  structures: Array<{ type: string; col: number; row: number }>,
  zoom: number,
  elapsed: number,
): void {
  const s = WORLD_TILE_SIZE;
  for (const struct of structures) {
    const spec = SPECS[struct.type] ?? SPECS['barrier'];
    const px = struct.col * s;
    const py = struct.row * s;

    const alpha = spec.pulse ? 0.7 + 0.3 * Math.sin(elapsed * 3) : 1.0;
    ctx.globalAlpha = alpha;

    ctx.fillStyle = spec.fillColor;
    ctx.fillRect(px, py, s, s);
    ctx.strokeStyle = spec.strokeColor;
    ctx.lineWidth = 1.5 / zoom;
    ctx.strokeRect(px + 0.5, py + 0.5, s - 1, s - 1);

    ctx.fillStyle = spec.strokeColor;
    ctx.font = `${Math.max(8, s * 0.6)}px monospace`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(spec.symbol, px + s / 2, py + s / 2);

    ctx.globalAlpha = 1.0;
  }
}
