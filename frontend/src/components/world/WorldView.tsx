import { useEffect, useMemo, useRef, useCallback, useState } from 'react';
import { WorldState } from '../../pixel/world/worldState.js';
import { createCamera, updateCamera, panCamera, zoomCamera, resizeCamera, screenToWorld, tileToIso, isoToTile, type CameraState } from '../../pixel/world/worldCamera.js';
import { renderWorld } from '../../pixel/world/worldRenderer.js';
import { tickContaminationDecay } from '../../pixel/world/infectionOverlay.js';
import { SpeechBubblePool, renderSpeechBubbles } from '../../pixel/world/speechBubble.js';
import { WorldAdapter } from '../../pixel/worldAdapter.js';
import { startGameLoop } from '../../pixel/office/engine/gameLoop.js';
import { WORLD_COLS, WORLD_ROWS, WORLD_TILE_SIZE } from '../../pixel/constants.js';
import { EditTool, TileType } from '../../pixel/office/types.js';
import type { CatalogEntry } from '../../pixel/shared/assets/types.js';
import WorldHUD from './WorldHUD';
import AgentInspector from './AgentInspector';
import ZoneMinimap from './ZoneMinimap';
import { ControlsOverlay } from '../controls/ControlsOverlay';
import {
  BUNDLED_WORLD_LAYOUT,
  WORLD_ASSET_GROUPS,
  WORLD_LAYOUT_STORAGE_KEY,
  WORLD_TILE_OPTIONS,
  cleanWorldLayoutImage,
  cloneStoredWorldLayout,
  computeLayoutBlockedTiles,
  findWorldAssetAt,
  normalizeHalfTurn,
  readStoredWorldLayout,
  renderWorldLayoutAssets,
  sourceGroupForAsset,
  worldOptionLabel,
  type PlacedWorldAsset,
  type WorldLayoutAsset,
  type WorldLayoutRenderable,
} from './worldLayoutStudio';

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

interface Props {
  onAgentClick?: (agentId: string) => void;
  controlsOverlayProps?: Record<string, unknown>;
}

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

export default function WorldView({ onAgentClick, controlsOverlayProps }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const stateRef  = useRef<WorldState | null>(null);
  const camRef    = useRef<CameraState | null>(null);
  const dragRef   = useRef<{ x: number; y: number } | null>(null);
  const initialFocusDoneRef = useRef(false);
  const placedAssetsRef = useRef<PlacedWorldAsset[]>([]);
  const tileOverridesRef = useRef<Map<string, number>>(new Map());
  const worldImagesRef = useRef<Map<string, WorldLayoutRenderable>>(new Map());
  const worldCatalogRef = useRef<Map<string, WorldLayoutAsset>>(new Map());
  const hoverTileRef = useRef<{ col: number; row: number } | null>(null);
  const editModeRef = useRef(false);
  const activeToolRef = useRef<string>(EditTool.SELECT);
  const selectedTileTypeRef = useRef<number>(TileType.FLOOR_1);
  const selectedAssetRef = useRef('');
  const selectedUidRef = useRef<string | null>(null);
  const renderErrorRef = useRef('');
  const [hudData, setHudData] = useState<HudData>(DEFAULT_HUD);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [debugMode, setDebugMode] = useState(false);
  const [gameReady, setGameReady] = useState(false);
  const [renderError, setRenderError] = useState('');
  const [worldAssets, setWorldAssets] = useState<WorldLayoutAsset[]>([]);
  const [worldAssetLoadError, setWorldAssetLoadError] = useState('');
  const [worldEditMode, setWorldEditMode] = useState(false);
  const [worldActiveTool, setWorldActiveTool] = useState<string>(EditTool.SELECT);
  const [worldSelectedTileType, setWorldSelectedTileType] = useState<number>(TileType.FLOOR_1);
  const [worldSelectedAssetId, setWorldSelectedAssetId] = useState('');
  const [selectedWorldUid, setSelectedWorldUid] = useState<string | null>(null);
  const [, setWorldLayoutVersion] = useState(0);
  const [, setWorldCameraVersion] = useState(0);

  const worldAssetCatalog = useMemo(
    () => new Map(worldAssets.map((asset) => [asset.id, asset])),
    [worldAssets],
  );

  useEffect(() => {
    worldCatalogRef.current = worldAssetCatalog;
    if (worldAssetCatalog.size === 0) return;
    // Once the catalog is non-empty we can confidently identify orphans
    // (assets whose IDs no longer exist in the catalog). Warn so operators
    // can clean up legacy layouts; collision is still computed from whatever
    // catalog entries do exist.
    const orphanIds = placedAssetsRef.current
      .map((item) => item.assetId)
      .filter((id) => !worldAssetCatalog.has(id));
    if (orphanIds.length > 0) {
      // eslint-disable-next-line no-console
      console.warn(
        `[WorldView] ${orphanIds.length} placed asset(s) reference unknown catalog ids:`,
        Array.from(new Set(orphanIds)),
      );
    }
    stateRef.current?.setLayoutBlockedTiles(
      computeLayoutBlockedTiles(placedAssetsRef.current, worldAssetCatalog),
    );
  }, [worldAssetCatalog]);

  const persistWorldLayout = useCallback(() => {
    window.localStorage.setItem(
      WORLD_LAYOUT_STORAGE_KEY,
      JSON.stringify({
        assets: placedAssetsRef.current,
        tileOverrides: Array.from(tileOverridesRef.current.entries()).map(([key, type]) => {
          const [col, row] = key.split(',').map(Number);
          return { col, row, type };
        }),
      }),
    );
  }, []);

  const commitWorldLayout = useCallback(() => {
    persistWorldLayout();
    stateRef.current?.setLayoutBlockedTiles(
      computeLayoutBlockedTiles(placedAssetsRef.current, worldCatalogRef.current),
    );
    setWorldLayoutVersion((version) => version + 1);
  }, [persistWorldLayout]);

  useEffect(() => {
    if (stateRef.current) {
      stateRef.current.debugMode = debugMode;
    }
  }, [debugMode]);

  useEffect(() => {
    if (stateRef.current) {
      stateRef.current.selectedWorldAgentId = selectedAgentId;
      if (!selectedAgentId) {
        stateRef.current.nearbyAgents.clear();
        stateRef.current.reachableAgents.clear();
      } else if (!debugMode) {
        // Fetch local context to populate perception sets for fog-of-war
        fetch(`/api/world/agent/${selectedAgentId}/context`)
          .then(res => res.json())
          .then(data => {
            if (stateRef.current && stateRef.current.selectedWorldAgentId === selectedAgentId) {
              stateRef.current.nearbyAgents = new Set(data.nearby_agents || []);
              stateRef.current.reachableAgents = new Set(data.reachable_agents || []);
            }
          })
          .catch(() => {});
      }
    }
  }, [selectedAgentId, debugMode]);
  useEffect(() => {
    editModeRef.current = worldEditMode;
  }, [worldEditMode]);

  useEffect(() => {
    activeToolRef.current = worldActiveTool;
  }, [worldActiveTool]);

  useEffect(() => {
    selectedTileTypeRef.current = worldSelectedTileType;
  }, [worldSelectedTileType]);

  useEffect(() => {
    selectedAssetRef.current = worldSelectedAssetId;
  }, [worldSelectedAssetId]);

  useEffect(() => {
    selectedUidRef.current = selectedWorldUid;
  }, [selectedWorldUid]);

  useEffect(() => {
    let cancelled = false;

    async function loadWorldAssets() {
      try {
        const response = await fetch('/pixel-assets/furniture-catalog.json');
        if (!response.ok) throw new Error(`catalog ${response.status}`);
        const catalog = (await response.json()) as CatalogEntry[];
        const layoutAssets = catalog
          .filter((asset) => asset.id.startsWith('layout-studio-'))
          .map((asset) => {
            const sourceGroup = sourceGroupForAsset(asset.id);
            return {
              ...asset,
              sourceGroupId: sourceGroup.id,
              sourceGroupLabel: sourceGroup.label,
            };
          });

        for (const asset of layoutAssets) {
          if (worldImagesRef.current.has(asset.id)) continue;
          const image = new Image();
          image.onload = () => {
            worldImagesRef.current.set(asset.id, cleanWorldLayoutImage(image));
            setWorldLayoutVersion((version) => version + 1);
          };
          image.onerror = () => {
            worldImagesRef.current.delete(asset.id);
          };
          image.src = `/pixel-assets/${asset.furniturePath}`;
        }

        if (cancelled) return;
        setWorldAssets(layoutAssets);
        setWorldAssetLoadError('');
        setWorldSelectedAssetId((current) => current || layoutAssets[0]?.id || '');
      } catch (error) {
        if (!cancelled) {
          setWorldAssetLoadError(error instanceof Error ? error.message : String(error));
        }
      }
    }

    void loadWorldAssets();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    // Wait until the world asset catalog has loaded (or has confirmed an
    // empty/error state) before booting the adapter and game loop. Otherwise
    // the renderer paints structures with a missing catalog on the first
    // frame, causing visible pop-in and stale collision data.
    if (worldAssets.length === 0 && !worldAssetLoadError) return;

    const ws = new WorldState();
    const cam = createCamera(canvas.clientWidth || 800, canvas.clientHeight || 600);
    stateRef.current = ws;
    camRef.current = cam;
    const storedLayout = readStoredWorldLayout();
    placedAssetsRef.current = storedLayout.assets ?? [];
    tileOverridesRef.current = new Map(
      (storedLayout.tileOverrides ?? []).map((override) => [`${override.col},${override.row}`, override.type]),
    );
    ws.setTileOverrides(
      (storedLayout.tileOverrides ?? []).map((override) => ({
        col: override.col,
        row: override.row,
        type: override.type as (typeof TileType)[keyof typeof TileType],
      })),
    );

    canvas.width  = canvas.clientWidth || 800;
    canvas.height = canvas.clientHeight || 600;
    cam.viewportW = canvas.width;
    cam.viewportH = canvas.height;

    const bubblePool = new SpeechBubblePool();
    const adapter = new WorldAdapter(ws);
    adapter.setBubblePool(bubblePool);
    adapter.setOrchestratorLineCallback((line) => {
      setHudData((prev) => ({ ...prev, orchestratorLine: line }));
    });
    adapter.start();

    const stop = startGameLoop(canvas, {
      update: (dt) => {
        ws.update(dt);

        // Soft-follow agent centroid so agents stay visible
        const followPositions = Array.from(ws.agentPositions.values()).filter(
          (pos) => pos.col >= 0 && pos.col < WORLD_COLS && pos.row >= 0 && pos.row < WORLD_ROWS,
        );
        if (followPositions.length > 0 && !dragRef.current) {
          let sumX = 0, sumY = 0;
          for (const pos of followPositions) {
            const [ix, iy] = tileToIso(pos.col, pos.row);
            sumX += ix; sumY += iy;
          }
          const cx = sumX / followPositions.length;
          const cy = sumY / followPositions.length;
          const targetX = cx - cam.viewportW / (2 * cam.targetZoom);
          const targetY = cy - cam.viewportH / (2 * cam.targetZoom);
          if (!initialFocusDoneRef.current) {
            // Snap camera to agents on first data load
            cam.targetX = targetX;
            cam.targetY = targetY;
            cam.x = targetX;
            cam.y = targetY;
            initialFocusDoneRef.current = true;
          } else {
            // Gentle follow: 4%/sec drift, doesn't fight manual panning
            cam.targetX += (targetX - cam.targetX) * 0.04 * dt;
            cam.targetY += (targetY - cam.targetY) * 0.04 * dt;
          }
        }

        updateCamera(cam, dt);
        tickContaminationDecay(ws, dt);
        bubblePool.update(dt);
      },
      render: (ctx) => {
        try {
          ctx.clearRect(0, 0, canvas.width, canvas.height);
          ctx.fillStyle = '#06060e';
          ctx.fillRect(0, 0, canvas.width, canvas.height);
          const layoutEditorState = {
            isEditMode: editModeRef.current,
            selectedUid: selectedUidRef.current,
            activeTool: activeToolRef.current,
            selectedAssetId: selectedAssetRef.current,
            hoverTile: hoverTileRef.current,
          };
          renderWorld(ctx, ws, cam, (worldCtx) => {
            renderWorldLayoutAssets(
              worldCtx,
              cam,
              placedAssetsRef.current,
              worldImagesRef.current,
              worldCatalogRef.current,
              layoutEditorState,
              false,
            );
          });

          const posMap = new Map(
            Array.from(ws.agentPositions.entries()).map(([id, p]) => [id, { col: p.col, row: p.row }])
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
    // Re-run once the asset catalog resolves (loaded or errored) so the
    // renderer never boots without it.
  }, [worldAssets.length === 0 && !worldAssetLoadError]);

  useEffect(() => {
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

    const fetchHud = async () => {
      try {
        const [stateRes, spatialRes] = await Promise.all([
          fetch('/api/world/state').catch(() => fetch('/dashboard/state')),
          fetch('/api/world/spatial').catch(() => null),
        ]);

        if (!stateRes.ok) return;
        const data = await stateRes.json();
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
            zoneAgents[z].count += 1;
          }
        }

        const zoneOrder = ['courier_zone', 'analyst_bay', 'quarantine_block', 'guardian_fortress', 'hub'];
        const zoneStatuses = zoneOrder
          .filter((z) => zoneAgents[z])
          .map((z) => ({
            id: z,
            label: ZONE_LABELS[z] ?? z.toUpperCase(),
            infectionLevel: zoneAgents[z].count > 0 ? zoneAgents[z].contamSum / zoneAgents[z].count : 0,
            agentCount: zoneAgents[z].count,
            color: ZONE_COLORS[z] ?? '#94a3b8',
          }));

        setHudData((prev) => ({
          ...prev,
          zoneStatuses,
          guardianDegradation: metrics.guardian_degradation_level ?? 'G0_HEALTHY',
          globalPressure: metrics.guardian_pressure_score ?? 0,
          roundId: metrics.world_round_id ?? 0,
          alerts: Number(metrics.guardian_pressure_score ?? 0) > 0.35
            ? [`guardian pressure ${Math.round(Number(metrics.guardian_pressure_score ?? 0) * 100)}%`]
            : [],
        }));
      } catch {}
    };
    fetchHud();
    const interval = setInterval(fetchHud, 3000);
    return () => clearInterval(interval);
  }, []);

  const eventToTile = useCallback((e: React.MouseEvent) => {
    if (!camRef.current || !canvasRef.current) return null;
    const rect = canvasRef.current.getBoundingClientRect();
    const [wx, wy] = screenToWorld(camRef.current, e.clientX - rect.left, e.clientY - rect.top);
    const [colF, rowF] = isoToTile(wx, wy);
    const col = Math.floor(colF);
    const row = Math.floor(rowF);
    if (col < 0 || col >= WORLD_COLS || row < 0 || row >= WORLD_ROWS) return null;
    return { col, row };
  }, []);

  const handleWorldEditClick = useCallback((e: React.MouseEvent) => {
    const tile = eventToTile(e);
    const ws = stateRef.current;
    if (!tile || !ws) return;

    if (activeToolRef.current === EditTool.FURNITURE_PLACE) {
      const assetId = selectedAssetRef.current;
      if (!assetId) return;
      placedAssetsRef.current = [
        ...placedAssetsRef.current,
        {
          uid: `world-layout-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          assetId,
          col: tile.col,
          row: tile.row,
          rotationDeg: 0,
        },
      ];
      commitWorldLayout();
      return;
    }

    if (activeToolRef.current === EditTool.TILE_PAINT || activeToolRef.current === EditTool.WALL_PAINT) {
      const type = activeToolRef.current === EditTool.WALL_PAINT ? TileType.WALL : selectedTileTypeRef.current;
      tileOverridesRef.current.set(`${tile.col},${tile.row}`, type);
      ws.setTileOverride(tile.col, tile.row, type as (typeof TileType)[keyof typeof TileType]);
      commitWorldLayout();
      return;
    }

    const hit = findWorldAssetAt(placedAssetsRef.current, worldAssetCatalog, tile.col, tile.row);

    if (activeToolRef.current === EditTool.ERASE) {
      if (hit) {
        placedAssetsRef.current = placedAssetsRef.current.filter((item) => item.uid !== hit.uid);
        if (selectedUidRef.current === hit.uid) setSelectedWorldUid(null);
      } else {
        tileOverridesRef.current.delete(`${tile.col},${tile.row}`);
        ws.setTileOverride(tile.col, tile.row, null);
      }
      commitWorldLayout();
      return;
    }

    if (activeToolRef.current === EditTool.SELECT) {
      if (hit) {
        setSelectedWorldUid(hit.uid);
        return;
      }
      if (selectedUidRef.current) {
        placedAssetsRef.current = placedAssetsRef.current.map((item) =>
          item.uid === selectedUidRef.current ? { ...item, col: tile.col, row: tile.row } : item,
        );
        commitWorldLayout();
      } else {
        setSelectedWorldUid(null);
      }
    }
  }, [commitWorldLayout, eventToTile, worldAssetCatalog]);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    if (editModeRef.current) return;
    dragRef.current = { x: e.clientX, y: e.clientY };
  }, []);

  const onMouseMove = useCallback((e: React.MouseEvent) => {
    if (editModeRef.current) {
      hoverTileRef.current = eventToTile(e);
      return;
    }
    if (!dragRef.current || !camRef.current) return;
    const dx = e.clientX - dragRef.current.x;
    const dy = e.clientY - dragRef.current.y;
    panCamera(camRef.current, -dx, -dy);
    dragRef.current = { x: e.clientX, y: e.clientY };
  }, [eventToTile]);

  const onMouseUp = useCallback(() => { dragRef.current = null; }, []);
  const onMouseLeave = useCallback(() => {
    dragRef.current = null;
    hoverTileRef.current = null;
  }, []);

  const onWheel = useCallback((e: React.WheelEvent) => {
    if (!camRef.current) return;
    e.preventDefault();
    const rect = canvasRef.current!.getBoundingClientRect();
    zoomCamera(camRef.current, e.deltaY < 0 ? 1 : -1, e.clientX - rect.left, e.clientY - rect.top);
    setWorldCameraVersion((version) => version + 1);
  }, []);

  const onCanvasClick = useCallback((e: React.MouseEvent) => {
    if (editModeRef.current) {
      handleWorldEditClick(e);
      return;
    }
    if (!camRef.current || !stateRef.current) return;
    const rect = canvasRef.current!.getBoundingClientRect();
    const [wx, wy] = screenToWorld(camRef.current, e.clientX - rect.left, e.clientY - rect.top);
    const [colF, rowF] = isoToTile(wx, wy);
    const clickCol = Math.floor(colF);
    const clickRow = Math.floor(rowF);

    for (const [id, pos] of stateRef.current.agentPositions) {
      if (Math.abs(pos.col - clickCol) <= 1 && Math.abs(pos.row - clickRow) <= 1) {
        setSelectedAgentId(id);
        onAgentClick?.(id);
        return;
      }
    }
    setSelectedAgentId(null);
  }, [handleWorldEditClick, onAgentClick]);

  const worldAssetGroups = useMemo(() => (
    WORLD_ASSET_GROUPS.map((group) => ({
      ...group,
      options: worldAssets
        .filter((asset) => asset.sourceGroupId === group.id)
        .map((asset) => ({
          label: worldOptionLabel(asset),
          value: asset.id,
        })),
    })).filter((group) => group.options.length > 0)
  ), [worldAssets]);

  const selectedWorldAsset = worldAssets.find((asset) => asset.id === worldSelectedAssetId) ?? null;
  const selectedWorldObject = selectedWorldUid
    ? placedAssetsRef.current.find((item) => item.uid === selectedWorldUid) ?? null
    : null;

  const worldEditor = useMemo(() => ({
    ready: gameReady,
    error: worldAssetLoadError,
    assetGroups: worldAssetGroups,
    tileOptions: WORLD_TILE_OPTIONS,
	    selectedLabel: selectedWorldObject
	      ? worldOptionLabel(worldAssetCatalog.get(selectedWorldObject.assetId) ?? selectedWorldAsset ?? {
	        ...selectedWorldObject,
	        id: selectedWorldObject.assetId,
	        label: selectedWorldObject.assetId,
	      } as unknown as WorldLayoutAsset)
      : '',
    editorState: {
      activeTool: worldActiveTool,
      selectedTileType: worldSelectedTileType,
      selectedFurnitureType: worldSelectedAssetId,
      selectedFurnitureUid: selectedWorldUid,
      undoStack: [],
      redoStack: [],
    },
    selectedItem: selectedWorldObject,
    editor: {
      isEditMode: worldEditMode,
      isDirty: false,
      zoom: camRef.current?.targetZoom ?? camRef.current?.zoom ?? 1,
      handleToggleEditMode: () => setWorldEditMode((value) => !value),
      handleZoomChange: (value: number) => {
        const cam = camRef.current;
        if (!cam) return;
        cam.targetZoom = Math.max(0.5, Math.min(4, value));
        cam.zoom = cam.targetZoom;
        setWorldCameraVersion((version) => version + 1);
      },
      handleToolChange: (tool: string) => setWorldActiveTool(tool),
      handleTileTypeChange: (type: number) => setWorldSelectedTileType(type),
      handleFurnitureTypeChange: (type: string) => {
        setWorldSelectedAssetId(type);
        if (type) setWorldActiveTool(EditTool.FURNITURE_PLACE);
      },
      handleRotateSelected: () => {
        const uid = selectedUidRef.current;
        if (!uid) return;
        placedAssetsRef.current = placedAssetsRef.current.map((item) =>
          item.uid === uid
            ? { ...item, rotationDeg: normalizeHalfTurn((item.rotationDeg ?? 0) + 180) }
            : item,
        );
        commitWorldLayout();
      },
      handleDeleteSelected: () => {
        const uid = selectedUidRef.current;
        if (!uid) return;
        placedAssetsRef.current = placedAssetsRef.current.filter((item) => item.uid !== uid);
        setSelectedWorldUid(null);
        commitWorldLayout();
      },
      handleUndo: () => {},
      handleRedo: () => {},
      handleSave: () => commitWorldLayout(),
      handleReset: () => {
        const defaultLayout = cloneStoredWorldLayout(BUNDLED_WORLD_LAYOUT);
        placedAssetsRef.current = defaultLayout.assets ?? [];
        tileOverridesRef.current = new Map(
          (defaultLayout.tileOverrides ?? []).map((override) => [`${override.col},${override.row}`, override.type]),
        );
        stateRef.current?.setTileOverrides(
          (defaultLayout.tileOverrides ?? []).map((override) => ({
            col: override.col,
            row: override.row,
            type: override.type as (typeof TileType)[keyof typeof TileType],
          })),
        );
        stateRef.current?.setLayoutBlockedTiles(
          computeLayoutBlockedTiles(placedAssetsRef.current, worldCatalogRef.current),
        );
        setSelectedWorldUid(null);
        window.localStorage.removeItem(WORLD_LAYOUT_STORAGE_KEY);
        setWorldLayoutVersion((version) => version + 1);
      },
    },
    resetLayoutToDefault: () => {
      const defaultLayout = cloneStoredWorldLayout(BUNDLED_WORLD_LAYOUT);
      placedAssetsRef.current = defaultLayout.assets ?? [];
      tileOverridesRef.current = new Map(
        (defaultLayout.tileOverrides ?? []).map((override) => [`${override.col},${override.row}`, override.type]),
      );
      stateRef.current?.setTileOverrides(
        (defaultLayout.tileOverrides ?? []).map((override) => ({
          col: override.col,
          row: override.row,
          type: override.type as (typeof TileType)[keyof typeof TileType],
        })),
      );
      stateRef.current?.setLayoutBlockedTiles(
        computeLayoutBlockedTiles(placedAssetsRef.current, worldCatalogRef.current),
      );
      setSelectedWorldUid(null);
      window.localStorage.removeItem(WORLD_LAYOUT_STORAGE_KEY);
      setWorldLayoutVersion((version) => version + 1);
    },
  }), [
    commitWorldLayout,
    gameReady,
    selectedWorldObject,
    selectedWorldUid,
    selectedWorldAsset,
    worldActiveTool,
    worldAssetCatalog,
    worldAssetGroups,
    worldAssetLoadError,
    worldEditMode,
    worldSelectedAssetId,
    worldSelectedTileType,
  ]);

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative', background: '#06060e' }}>
      <canvas
        ref={canvasRef}
        style={{ width: '100%', height: '100%', display: 'block', cursor: worldEditMode ? 'crosshair' : 'grab' }}
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
      {renderError ? (
        <div
          style={{
            position: 'absolute',
            left: 12,
            bottom: 12,
            maxWidth: 520,
            border: '1px solid rgba(239,68,68,0.7)',
            background: 'rgba(15, 23, 42, 0.92)',
            color: '#fecaca',
            borderRadius: 6,
            padding: '8px 10px',
            fontFamily: 'monospace',
            fontSize: 12,
            pointerEvents: 'none',
          }}
        >
          render degraded :: {renderError.slice(0, 160)}
        </div>
      ) : null}
	      {controlsOverlayProps ? (
	        <ControlsOverlay {...(controlsOverlayProps as any)} worldEditor={worldEditor} />
	      ) : null}
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
