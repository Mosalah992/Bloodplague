import { useEffect, useRef } from 'react';
import { WORLD_COLS, WORLD_ROWS, WORLD_ZONES } from '../../pixel/constants.js';
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

    for (const [id, pos] of state.agentPositions) {
      ctx.fillStyle = id === 'guardian' ? '#a78bfa' : id.startsWith('courier') ? '#fb923c' : '#4ade80';
      ctx.beginPath();
      ctx.arc(pos.col * scaleX, pos.row * scaleY, 2.5, 0, Math.PI * 2);
      ctx.fill();
    }

    const tileSize = 16;
    const vpX = (camera.x / tileSize) * scaleX;
    const vpY = (camera.y / tileSize) * scaleY;
    const vpW = (camera.viewportW / camera.zoom / tileSize) * scaleX;
    const vpH = (camera.viewportH / camera.zoom / tileSize) * scaleY;
    ctx.strokeStyle = '#ffffff44';
    ctx.lineWidth = 1;
    ctx.strokeRect(vpX, vpY, vpW, vpH);
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
