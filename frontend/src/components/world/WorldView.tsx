import { useEffect, useRef, useState, useCallback } from 'react';
import { WorldState } from '../../pixel/world/worldState.js';
import {
  createCamera,
  updateCamera,
  panCamera,
  zoomCamera,
  resizeCamera,
  screenToWorld,
  tileToIso,
  isoToTile,
  type CameraState,
} from '../../pixel/world/worldCamera.js';
import { renderWorld } from '../../pixel/world/worldRenderer.js';
import { tickContaminationDecay } from '../../pixel/world/infectionOverlay.js';
import { SpeechBubblePool, renderSpeechBubbles } from '../../pixel/world/speechBubble.js';
import { WorldAdapter } from '../../pixel/worldAdapter.js';
import { WORLD_COLS, WORLD_ROWS, WORLD_TILE_SIZE, MAX_DELTA_TIME_SEC } from '../../pixel/constants.js';
import WorldHUD from './WorldHUD';
import AgentInspector from './AgentInspector';
import ZoneMinimap from './ZoneMinimap';
import { ControlsOverlay } from '../controls/ControlsOverlay';

// ── Minimal game loop (no office dependency) ─────────────────────────────────
function startLoop(
  canvas: HTMLCanvasElement,
  callbacks: { update: (dt: number) => void; render: (ctx: CanvasRenderingContext2D) => void },
): () => void {
  const ctx = canvas.getContext('2d')!;
  ctx.imageSmoothingEnabled = false;
  let lastTime = 0;
  let rafId = 0;
  let stopped = false;
  const frame = (time: number) => {
    if (stopped) return;
    const dt = lastTime === 0 ? 0 : Math.min((time - lastTime) / 1000, MAX_DELTA_TIME_SEC);
    lastTime = time;
    callbacks.update(dt);
    ctx.imageSmoothingEnabled = false;
    callbacks.render(ctx);
    rafId = requestAnimationFrame(frame);
  };
  rafId = requestAnimationFrame(frame);
  return () => { stopped = true; cancelAnimationFrame(rafId); };
}

// ── Error overlay drawn directly onto the canvas ─────────────────────────────
function drawCanvasError(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  message: string,
): void {
  ctx.save();
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = '#09090f';
  ctx.fillRect(0, 0, width, height);
  ctx.strokeStyle = '#ef4444';
  ctx.lineWidth = 2;
  ctx.strokeRect(16, 16, Math.max(0, width - 32), Math.max(0, height - 32));
  ctx.fillStyle = '#fecaca';
  ctx.font = '14px monospace';
  ctx.fillText('render degraded', 32, 48);
  ctx.fillStyle = '#fca5a5';
  ctx.font = '12px monospace';
  ctx.fillText(message.slice(0, 120), 32, 72);
  ctx.restore();
}

// ── HUD data shape ────────────────────────────────────────────────────────────
interface HudData {
  zoneStatuses: Array<{ id: string; label: string; infectionLevel: number; agentCount: number; color: string }>;
  guardianDegradation: string;
  globalPressure: number;
  roundId: number;
  alerts: string[];
  orchestratorLine: string;
}

const DEFAULT_HUD: HudData = {
  zoneStatuses: [],
  guardianDegradation: 'G0_HEALTHY',
  globalPressure: 0,
  roundId: 0,
  alerts: [],
  orchestratorLine: '',
};

const ZONE_LABELS: Record<string, string> = {
  courier_zone: 'COURIER',
  analyst_bay: 'ANALYST',
  guardian_fortress: 'GUARDIAN',
  quarantine_block: 'QUAR',
  hub: 'HUB',
};
const ZONE_COLORS: Record<string, string> = {
  courier_zone: '#fb923c',
  analyst_bay: '#22c55e',
  guardian_fortress: '#8b5cf6',
  quarantine_block: '#dc2626',
  hub: '#94a3b8',
};

// ── Props ─────────────────────────────────────────────────────────────────────
interface Props {
  onAgentClick?: (agentId: string) => void;
  controlsOverlayProps?: Record<string, unknown>;
}

// ── WorldView ─────────────────────────────────────────────────────────────────
export default function WorldView({ onAgentClick, controlsOverlayProps }: Props) {
  const canvasRef        = useRef<HTMLCanvasElement>(null);
  const stateRef         = useRef<WorldState | null>(null);
  const camRef           = useRef<CameraState | null>(null);
  const dragRef          = useRef<{ x: number; y: number } | null>(null);
  const initialFocusDoneRef = useRef(false);
  const renderErrorRef   = useRef('');

  const [hudData, setHudData]             = useState<HudData>(DEFAULT_HUD);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [debugMode, setDebugMode]         = useState(false);
  const [gameReady, setGameReady]         = useState(false);
  const [renderError, setRenderError]     = useState('');

  // ── Debug mode propagation ──────────────────────────────────────────────────
  useEffect(() => {
    if (stateRef.current) stateRef.current.debugMode = debugMode;
  }, [debugMode]);

  // ── Agent selection + fog-of-war context fetch ──────────────────────────────
  useEffect(() => {
    const ws = stateRef.current;
    if (!ws) return;
    ws.selectedWorldAgentId = selectedAgentId;
    if (!selectedAgentId) {
      ws.nearbyAgents.clear();
      ws.reachableAgents.clear();
      return;
    }
    if (debugMode) return;
    fetch(`/api/world/agent/${selectedAgentId}/context`)
      .then((r) => r.json())
      .then((data) => {
        if (stateRef.current?.selectedWorldAgentId === selectedAgentId) {
          stateRef.current.nearbyAgents   = new Set(data.nearby_agents ?? []);
          stateRef.current.reachableAgents = new Set(data.reachable_agents ?? []);
        }
      })
      .catch(() => {});
  }, [selectedAgentId, debugMode]);

  // ── Boot: WorldState + camera + adapter + render loop ──────────────────────
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ws  = new WorldState();
    const cam = createCamera(canvas.clientWidth || 800, canvas.clientHeight || 600);
    stateRef.current = ws;
    camRef.current   = cam;

    canvas.width  = canvas.clientWidth  || 800;
    canvas.height = canvas.clientHeight || 600;
    cam.viewportW = canvas.width;
    cam.viewportH = canvas.height;

    const bubblePool = new SpeechBubblePool();
    const adapter    = new WorldAdapter(ws);
    adapter.setBubblePool(bubblePool);
    adapter.setOrchestratorLineCallback((line) =>
      setHudData((prev) => ({ ...prev, orchestratorLine: line })),
    );
    adapter.start();

    const stop = startLoop(canvas, {
      update: (dt) => {
        ws.update(dt);
        tickContaminationDecay(ws, dt);
        bubblePool.update(dt);

        // Soft-follow agent centroid
        const positions = Array.from(ws.agentPositions.values()).filter(
          (p) => p.col >= 0 && p.col < WORLD_COLS && p.row >= 0 && p.row < WORLD_ROWS,
        );
        if (positions.length > 0 && !dragRef.current) {
          let sumX = 0, sumY = 0;
          for (const p of positions) {
            const [ix, iy] = tileToIso(p.col, p.row);
            sumX += ix; sumY += iy;
          }
          const cx = sumX / positions.length;
          const cy = sumY / positions.length;
          const tx = cx - cam.viewportW / (2 * cam.targetZoom);
          const ty = cy - cam.viewportH / (2 * cam.targetZoom);
          if (!initialFocusDoneRef.current) {
            cam.targetX = tx; cam.targetY = ty;
            cam.x       = tx; cam.y       = ty;
            initialFocusDoneRef.current = true;
          } else {
            cam.targetX += (tx - cam.targetX) * 0.04 * dt;
            cam.targetY += (ty - cam.targetY) * 0.04 * dt;
          }
        }
        updateCamera(cam, dt);
      },

      render: (ctx) => {
        try {
          ctx.clearRect(0, 0, canvas.width, canvas.height);
          ctx.fillStyle = '#06060e';
          ctx.fillRect(0, 0, canvas.width, canvas.height);

          renderWorld(ctx, ws, cam);

          // Speech bubbles — drawn in world-space after the world pass
          const posMap = new Map(
            Array.from(ws.agentPositions.entries()).map(([id, p]) => [id, { col: p.col, row: p.row }]),
          );
          ctx.save();
          ctx.setTransform(cam.zoom, 0, 0, cam.zoom, -cam.x * cam.zoom, -cam.y * cam.zoom);
          renderSpeechBubbles(ctx, bubblePool.getAll(), posMap, WORLD_TILE_SIZE, tileToIso);
          ctx.restore();

          if (renderErrorRef.current) {
            renderErrorRef.current = '';
            setRenderError('');
          }
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          drawCanvasError(ctx, canvas.width, canvas.height, message);
          if (renderErrorRef.current !== message) {
            renderErrorRef.current = message;
            setRenderError(message);
          }
        }
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

  // ── HUD polling ─────────────────────────────────────────────────────────────
  useEffect(() => {
    const fetchHud = async () => {
      try {
        const [stateRes, spatialRes] = await Promise.all([
          fetch('/api/world/state').catch(() => fetch('/dashboard/state')),
          fetch('/api/world/spatial').catch(() => null),
        ]);
        if (!stateRes.ok) return;
        const data    = await stateRes.json();
        const metrics = data?.epidemic?.metrics ?? {};
        const agentsMap: Record<string, number> = {};
        for (const [id, agent] of Object.entries(data?.agents ?? {})) {
          agentsMap[id] = Number((agent as { contamination_level?: number }).contamination_level ?? 0);
        }

        const zoneAgents: Record<string, { contamSum: number; count: number }> = {};
        if (spatialRes?.ok) {
          const spatial = await spatialRes.json();
          for (const pos of (spatial?.positions ?? []) as Array<{ agent_id: string; zone: string }>) {
            const z = pos.zone ?? 'hub';
            if (!zoneAgents[z]) zoneAgents[z] = { contamSum: 0, count: 0 };
            zoneAgents[z].contamSum += agentsMap[pos.agent_id] ?? 0;
            zoneAgents[z].count     += 1;
          }
        }

        const zoneOrder = ['courier_zone', 'analyst_bay', 'quarantine_block', 'guardian_fortress', 'hub'];
        const zoneStatuses = zoneOrder
          .filter((z) => zoneAgents[z])
          .map((z) => ({
            id:             z,
            label:          ZONE_LABELS[z] ?? z.toUpperCase(),
            infectionLevel: zoneAgents[z].count > 0 ? zoneAgents[z].contamSum / zoneAgents[z].count : 0,
            agentCount:     zoneAgents[z].count,
            color:          ZONE_COLORS[z] ?? '#94a3b8',
          }));

        setHudData((prev) => ({
          ...prev,
          zoneStatuses,
          guardianDegradation: metrics.guardian_degradation_level ?? 'G0_HEALTHY',
          globalPressure:      metrics.guardian_pressure_score ?? 0,
          roundId:             metrics.world_round_id ?? 0,
          alerts:
            Number(metrics.guardian_pressure_score ?? 0) > 0.35
              ? [`guardian pressure ${Math.round(Number(metrics.guardian_pressure_score ?? 0) * 100)}%`]
              : [],
        }));
      } catch {}
    };
    fetchHud();
    const interval = setInterval(fetchHud, 3000);
    return () => clearInterval(interval);
  }, []);

  // ── Mouse / pointer handlers ────────────────────────────────────────────────
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

  const onMouseUp    = useCallback(() => { dragRef.current = null; }, []);
  const onMouseLeave = useCallback(() => { dragRef.current = null; }, []);

  const onWheel = useCallback((e: React.WheelEvent) => {
    if (!camRef.current || !canvasRef.current) return;
    e.preventDefault();
    const rect = canvasRef.current.getBoundingClientRect();
    zoomCamera(camRef.current, e.deltaY < 0 ? 1 : -1, e.clientX - rect.left, e.clientY - rect.top);
  }, []);

  const onCanvasClick = useCallback((e: React.MouseEvent) => {
    if (!camRef.current || !stateRef.current || !canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const [wx, wy]  = screenToWorld(camRef.current, e.clientX - rect.left, e.clientY - rect.top);
    const [colF, rowF] = isoToTile(wx, wy);
    const clickCol  = Math.floor(colF);
    const clickRow  = Math.floor(rowF);

    for (const [id, pos] of stateRef.current.agentPositions) {
      if (Math.abs(pos.col - clickCol) <= 1 && Math.abs(pos.row - clickRow) <= 1) {
        setSelectedAgentId(id);
        onAgentClick?.(id);
        return;
      }
    }
    setSelectedAgentId(null);
  }, [onAgentClick]);

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <div style={{ width: '100%', height: '100%', position: 'relative', background: '#06060e' }}>
      <canvas
        ref={canvasRef}
        style={{ width: '100%', height: '100%', display: 'block', cursor: 'grab' }}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
        onMouseLeave={onMouseLeave}
        onWheel={onWheel}
        onClick={onCanvasClick}
      />
      <WorldHUD
        {...hudData}
        debugMode={debugMode}
        onToggleDebug={setDebugMode}
      />
      {renderError && (
        <div
          style={{
            position: 'absolute', left: 12, bottom: 12, maxWidth: 520,
            border: '1px solid rgba(239,68,68,0.7)',
            background: 'rgba(15,23,42,0.92)',
            color: '#fecaca', borderRadius: 6,
            padding: '8px 10px', fontFamily: 'monospace', fontSize: 12,
            pointerEvents: 'none',
          }}
        >
          render degraded :: {renderError.slice(0, 160)}
        </div>
      )}
      {controlsOverlayProps && (
        <ControlsOverlay {...(controlsOverlayProps as any)} />
      )}
      {gameReady && <ZoneMinimap state={stateRef.current} camera={camRef.current} />}
      {selectedAgentId && (
        <AgentInspector
          key={selectedAgentId}
          agentId={selectedAgentId}
          onClose={() => setSelectedAgentId(null)}
          debugMode={debugMode}
        />
      )}
    </div>
  );
}
