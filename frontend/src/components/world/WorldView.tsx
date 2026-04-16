import { useEffect, useRef, useCallback, useState } from 'react';
import { WorldState } from '../../pixel/world/worldState.js';
import { createCamera, updateCamera, panCamera, zoomCamera, resizeCamera, screenToWorld, type CameraState } from '../../pixel/world/worldCamera.js';
import { renderWorld } from '../../pixel/world/worldRenderer.js';
import { tickContaminationDecay } from '../../pixel/world/infectionOverlay.js';
import { SpeechBubblePool, renderSpeechBubbles } from '../../pixel/world/speechBubble.js';
import { WorldAdapter } from '../../pixel/worldAdapter.js';
import { startGameLoop } from '../../pixel/office/engine/gameLoop.js';
import { WORLD_TILE_SIZE } from '../../pixel/constants.js';
import WorldHUD from './WorldHUD.jsx';
import AgentInspector from './AgentInspector.jsx';
import ZoneMinimap from './ZoneMinimap.jsx';

interface HudData {
  zoneStatuses: Array<{ id: string; label: string; infectionLevel: number; agentCount: number; color: string }>;
  guardianDegradation: string;
  globalPressure: number;
  roundId: number;
  alerts: string[];
}

const DEFAULT_HUD: HudData = {
  zoneStatuses: [],
  guardianDegradation: 'G0_HEALTHY',
  globalPressure: 0,
  roundId: 0,
  alerts: [],
};

interface Props {
  onAgentClick?: (agentId: string) => void;
}

export default function WorldView({ onAgentClick }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef  = useRef<WorldState | null>(null);
  const camRef    = useRef<CameraState | null>(null);
  const dragRef   = useRef<{ x: number; y: number } | null>(null);
  const [hudData, setHudData] = useState<HudData>(DEFAULT_HUD);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [gameReady, setGameReady] = useState(false);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ws = new WorldState();
    const cam = createCamera(canvas.clientWidth || 800, canvas.clientHeight || 600);
    stateRef.current = ws;
    camRef.current = cam;

    canvas.width  = canvas.clientWidth || 800;
    canvas.height = canvas.clientHeight || 600;
    cam.viewportW = canvas.width;
    cam.viewportH = canvas.height;

    const bubblePool = new SpeechBubblePool();
    const adapter = new WorldAdapter(ws);
    adapter.setBubblePool(bubblePool);
    adapter.start();

    const stop = startGameLoop(canvas, {
      update: (dt) => {
        ws.update(dt);
        updateCamera(cam, dt);
        tickContaminationDecay(ws, dt);
        bubblePool.update(dt);
      },
      render: (ctx) => {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#06060e';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        renderWorld(ctx, ws, cam);

        const posMap = new Map(
          Array.from(ws.agentPositions.entries()).map(([id, p]) => [id, { col: p.col, row: p.row }])
        );
        ctx.save();
        ctx.setTransform(cam.zoom, 0, 0, cam.zoom, -cam.x * cam.zoom, -cam.y * cam.zoom);
        renderSpeechBubbles(ctx, bubblePool.getAll(), posMap, WORLD_TILE_SIZE);
        ctx.restore();
      },
    });

    const onResize = () => {
      canvas.width  = canvas.clientWidth;
      canvas.height = canvas.clientHeight;
      resizeCamera(cam, canvas.clientWidth, canvas.clientHeight);
    };
    window.addEventListener('resize', onResize);
    setGameReady(true);

    return () => {
      stop();
      adapter.stop();
      window.removeEventListener('resize', onResize);
    };
  }, []);

  useEffect(() => {
    const fetchHud = async () => {
      try {
        const res = await fetch('/dashboard/state');
        if (!res.ok) return;
        const data = await res.json();
        const metrics = data?.epidemic?.metrics ?? {};
        setHudData((prev) => ({
          ...prev,
          guardianDegradation: metrics.guardian_degradation_level ?? 'G0_HEALTHY',
          globalPressure: metrics.global_infection_pressure ?? 0,
          roundId: metrics.world_round_id ?? 0,
        }));
      } catch {}
    };
    fetchHud();
    const interval = setInterval(fetchHud, 3000);
    return () => clearInterval(interval);
  }, []);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    dragRef.current = { x: e.clientX, y: e.clientY };
  }, []);

  const onMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragRef.current || !camRef.current) return;
    const dx = e.clientX - dragRef.current.x;
    const dy = e.clientY - dragRef.current.y;
    panCamera(camRef.current, -dx, -dy);
    dragRef.current = { x: e.clientX, y: e.clientY };
  }, []);

  const onMouseUp = useCallback(() => { dragRef.current = null; }, []);

  const onWheel = useCallback((e: React.WheelEvent) => {
    if (!camRef.current) return;
    e.preventDefault();
    const rect = canvasRef.current!.getBoundingClientRect();
    zoomCamera(camRef.current, e.deltaY < 0 ? 1 : -1, e.clientX - rect.left, e.clientY - rect.top);
  }, []);

  const onCanvasClick = useCallback((e: React.MouseEvent) => {
    if (!camRef.current || !stateRef.current) return;
    const rect = canvasRef.current!.getBoundingClientRect();
    const [wx, wy] = screenToWorld(camRef.current, e.clientX - rect.left, e.clientY - rect.top);
    const clickCol = Math.floor(wx / WORLD_TILE_SIZE);
    const clickRow = Math.floor(wy / WORLD_TILE_SIZE);

    for (const [id, pos] of stateRef.current.agentPositions) {
      if (Math.abs(pos.col - clickCol) <= 1 && Math.abs(pos.row - clickRow) <= 1) {
        setSelectedAgentId(id);
        onAgentClick?.(id);
        return;
      }
    }
    setSelectedAgentId(null);
  }, [onAgentClick]);

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative', background: '#06060e' }}>
      <canvas
        ref={canvasRef}
        style={{ width: '100%', height: '100%', display: 'block', cursor: 'grab' }}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseUp}
        onWheel={onWheel}
        onClick={onCanvasClick}
      />
      <WorldHUD {...hudData} />
      {gameReady && <ZoneMinimap state={stateRef.current} camera={camRef.current} />}
      {selectedAgentId && (
        <AgentInspector agentId={selectedAgentId} onClose={() => setSelectedAgentId(null)} />
      )}
    </div>
  );
}
