import { useEffect, useRef } from 'react';
import { WORLD_COLS, WORLD_ROWS, WORLD_ZONES, ISO_ORIGIN_X, ISO_ORIGIN_Y, ISO_HALF_W, ISO_HALF_H } from '../../pixel/constants.js';
import type { WorldState } from '../../pixel/world/worldState.js';
import type { CameraState } from '../../pixel/world/worldCamera.js';

interface Props {
  state: WorldState | null;
  camera: CameraState | null;
  width?: number;
  height?: number;
}

export default function ZoneMinimap({ state, camera, width = 160, height = 120 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !state || !camera) return;
    const ctx = canvas.getContext('2d')!;
    const scaleX = width / WORLD_COLS;
    const scaleY = height / WORLD_ROWS;

    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = '#06060e';
    ctx.fillRect(0, 0, width, height);

    for (const zone of WORLD_ZONES) {
      ctx.fillStyle = zone.floorColor;
      ctx.fillRect(zone.colMin * scaleX, zone.rowMin * scaleY,
        (zone.colMax - zone.colMin + 1) * scaleX, (zone.rowMax - zone.rowMin + 1) * scaleY);
      ctx.strokeStyle = zone.borderColor + 'aa';
      ctx.lineWidth = 0.5;
      ctx.strokeRect(zone.colMin * scaleX, zone.rowMin * scaleY,
        (zone.colMax - zone.colMin + 1) * scaleX, (zone.rowMax - zone.rowMin + 1) * scaleY);
    }

    for (const [key, level] of state.contaminationTiles) {
      const [c, r] = key.split(',').map(Number);
      ctx.fillStyle = `rgba(239,68,68,${level * 0.6})`;
      ctx.fillRect(c * scaleX, r * scaleY, scaleX, scaleY);
    }

    for (const s of state.structures) {
      if (s.state === 'removed') continue;
      ctx.fillStyle = s.type === 'quarantine_barrier'
        ? '#ef4444'
        : s.type === 'scan_relay_post'
          ? '#22d3ee'
          : s.type === 'corruption_beacon'
            ? '#a3e635'
            : '#94a3b8';
      ctx.globalAlpha = s.state === 'constructing' ? 0.45 : 0.9;
      ctx.fillRect(s.col * scaleX - 1, s.row * scaleY - 1, 3, 3);
      ctx.globalAlpha = 1;
    }

    for (const [id, pos] of state.agentPositions) {
      ctx.fillStyle = id === 'guardian' ? '#a78bfa' : id.startsWith('courier') ? '#fb923c' : '#4ade80';
      ctx.beginPath();
      ctx.arc(pos.col * scaleX, pos.row * scaleY, 2.5, 0, Math.PI * 2);
      ctx.fill();
    }

    // Top-down: camera x/y are cartesian world px. Convert to cell coords.
    const camCenterX = camera.x + camera.viewportW / (2 * camera.zoom);
    const camCenterY = camera.y + camera.viewportH / (2 * camera.zoom);
    const centerCol = (camCenterX - ISO_ORIGIN_X) / (2 * ISO_HALF_W);
    const centerRow = (camCenterY - ISO_ORIGIN_Y) / (2 * ISO_HALF_H);
    const cpx = centerCol * scaleX;
    const cpy = centerRow * scaleY;
    ctx.strokeStyle = '#ffffff66';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(cpx - 4, cpy);
    ctx.lineTo(cpx + 4, cpy);
    ctx.moveTo(cpx, cpy - 4);
    ctx.lineTo(cpx, cpy + 4);
    ctx.stroke();
  });

  return (
    <div style={{
      position: 'absolute', bottom: 12, left: 12,
      border: '1px solid #1e293b', borderRadius: 4,
      overflow: 'hidden', pointerEvents: 'none',
    }}>
      <canvas ref={canvasRef} width={width} height={height} style={{ display: 'block' }} />
    </div>
  );
}
