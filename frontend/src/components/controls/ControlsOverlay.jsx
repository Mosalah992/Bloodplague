import React from "react";
import { DIFFICULTIES, toneClasses } from "../../data";
import { EditTool, TileType } from "../../pixel/office/types.js";
import { getActiveCategories, getCatalogByCategory } from "../../pixel/office/layout/furnitureCatalog.js";
import { GlassPanel } from "../lab/GlassPanel";

const TOOL_OPTIONS = [
  { label: "Cursor", value: EditTool.SELECT },
  { label: "Floor", value: EditTool.TILE_PAINT },
  { label: "Wall", value: EditTool.WALL_PAINT },
  { label: "Erase", value: EditTool.ERASE },
  { label: "Furniture", value: EditTool.FURNITURE_PLACE },
];

const TILE_OPTIONS = [
  TileType.FLOOR_1,
  TileType.FLOOR_2,
  TileType.FLOOR_4,
  TileType.FLOOR_5,
  TileType.FLOOR_7,
  TileType.FLOOR_9,
];

const LEGACY_FURNITURE_OPTIONS = [
  { label: "Desk", value: "DESK_FRONT" },
  { label: "Chair", value: "WOODEN_CHAIR_BACK" },
  { label: "PC", value: "PC_FRONT_OFF" },
  { label: "Whiteboard", value: "WHITEBOARD" },
  { label: "Plant", value: "PLANT" },
  { label: "Bookshelf", value: "DOUBLE_BOOKSHELF" },
  { label: "Bin", value: "BIN" },
  { label: "Exfil Table", value: "SMALL_TABLE_FRONT" },
];

/**
 * Floating glass panel: inject / quarantine / vaccine / reset (replaces SIM_CONTROL strip).
 */
export function ControlsOverlay({
  difficulty,
  setDifficulty,
  controlStatus,
  onControlAction,
  simRunning,
  injectionTargets,
  selectedInjectionTarget,
  setSelectedInjectionTarget,
  quarantineTargets,
  selectedQuarantineTarget,
  setSelectedQuarantineTarget,
  labController,
  worldEditor
}) {
  const layoutController = worldEditor || labController;
  const editor = layoutController?.editor;
  const editorState = layoutController?.editorState;
  const officeState = worldEditor ? null : labController?.officeState;
  const layout = officeState ? officeState.getLayout() : null;
  const selectedFurniture = worldEditor?.selectedItem || layout?.furniture?.find((item) => item.uid === editorState?.selectedFurnitureUid) || null;
  const selectedTool = TOOL_OPTIONS.find((item) => item.value === editorState?.activeTool)?.label || "Cursor";
  const catalogFurnitureGroups = worldEditor?.assetGroups || getActiveCategories()
      .map((category) => ({
        ...category,
        options: getCatalogByCategory(category.id).map((entry) => ({
          label: entry.label,
          value: entry.type,
        })),
      }))
      .filter((category) => category.options.length > 0);
  const furnitureOptionGroups = catalogFurnitureGroups.length
    ? catalogFurnitureGroups
    : [{ id: "legacy", label: "Legacy", options: LEGACY_FURNITURE_OPTIONS }];
  const furnitureOptions = furnitureOptionGroups.flatMap((category) => category.options);
  const tileOptions = worldEditor?.tileOptions || TILE_OPTIONS.map((value) => ({ value, label: `floor_${value}` }));
  const selectedFurnitureType =
    furnitureOptions.find((item) => item.value === editorState?.selectedFurnitureType)?.label ||
    editorState?.selectedFurnitureType ||
    "none";
  const layoutSelection = worldEditor?.selectedLabel || labController?.selectedAgentKey || selectedFurniture?.uid || "none";
  const zoomPercent = Math.round((editor?.zoom || 1) * 100);
  const canEditLayout = Boolean(layoutController?.ready && editor && editorState);
  const layoutError = layoutController?.error || "";
  const actionButtonClass = "rounded border px-2 py-1.5 font-pixel text-[6px] uppercase";
  const disabledButtonClass = "opacity-40 cursor-not-allowed";

  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 max-w-[min(100vw-2rem,460px)]">
      <GlassPanel accent="cyan" className="pointer-events-auto p-4 shadow-glass">
        <div className="font-pixel text-[6px] uppercase tracking-widest text-slate-500">Control_plane</div>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="font-pixel text-[6px] uppercase text-slate-500">Difficulty</span>
          {DIFFICULTIES.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setDifficulty(item.id)}
              className={`rounded border px-2 py-1.5 font-pixel text-[6px] uppercase ${
                difficulty === item.id ? toneClasses(item.tone, true) : "border-white/10 text-slate-500 hover:border-white/20"
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <label className="flex items-center gap-2 rounded border border-white/10 px-2 py-1.5 font-pixel text-[5px] uppercase text-slate-500">
            <span>Ingress</span>
            <select
              value={selectedInjectionTarget}
              onChange={(e) => setSelectedInjectionTarget(e.target.value)}
              className="max-w-[140px] bg-transparent font-mono text-[10px] text-terminal-cyan outline-none"
            >
              <option value="auto">auto</option>
              {injectionTargets.length > 1 ? <option value="all">all ingress</option> : null}
              {injectionTargets.map((agentId) => (
                <option key={agentId} value={agentId}>
                  {agentId}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 rounded border border-white/10 px-2 py-1.5 font-pixel text-[5px] uppercase text-slate-500">
            <span>Quarantine</span>
            <select
              value={selectedQuarantineTarget}
              onChange={(e) => setSelectedQuarantineTarget(e.target.value)}
              className="max-w-[140px] bg-transparent font-mono text-[10px] text-terminal-warn outline-none"
            >
              <option value="auto">auto</option>
              {quarantineTargets.map((agentId) => (
                <option key={agentId} value={agentId}>
                  {agentId}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="mt-2 flex items-center gap-2 font-mono text-[10px]">
          <span className={`h-1.5 w-1.5 rounded-full ${simRunning ? "bg-terminal-success animate-pulse" : "bg-slate-600"}`} />
          <span className={simRunning ? "text-terminal-success" : "text-slate-500"}>
            {simRunning ? "auto-advance running" : "paused"}
          </span>
        </div>
        <div className="mt-2 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onControlAction("advance")}
            className="rounded border border-terminal-cyan/40 bg-terminal-cyan/15 px-3 py-2 font-pixel text-[6px] uppercase text-terminal-cyan"
          >
            Advance
          </button>
          <button
            type="button"
            onClick={() => onControlAction("run")}
            className={`rounded border px-3 py-2 font-pixel text-[6px] uppercase ${
              simRunning
                ? "border-terminal-success/60 bg-terminal-success/25 text-terminal-success"
                : "border-terminal-success/40 bg-terminal-success/15 text-terminal-success"
            }`}
          >
            {simRunning ? "Running" : "Run"}
          </button>
          <button
            type="button"
            onClick={() => onControlAction("pause")}
            className="rounded border border-terminal-warn/40 bg-terminal-warn/10 px-3 py-2 font-pixel text-[6px] uppercase text-terminal-warn"
          >
            Pause
          </button>
          <button
            type="button"
            onClick={() => onControlAction("vaccine")}
            className="rounded border border-terminal-purple/40 bg-terminal-purple/10 px-3 py-2 font-pixel text-[6px] uppercase text-terminal-purple"
          >
            Vaccine
          </button>
          <button
            type="button"
            onClick={() => onControlAction("quarantine")}
            className="rounded border border-terminal-warn/40 bg-terminal-warn/10 px-3 py-2 font-pixel text-[6px] uppercase text-terminal-warn"
          >
            Quarantine
          </button>
          <button
            type="button"
            onClick={() => onControlAction("reset")}
            className="rounded border border-white/15 bg-white/5 px-3 py-2 font-pixel text-[6px] uppercase text-slate-400"
          >
            Reset
          </button>
        </div>
        <div className="mt-3 max-h-16 overflow-y-auto font-mono text-[10px] leading-snug text-slate-500">{controlStatus}</div>

        <div className="mt-4 border-t border-white/10 pt-4">
          <div className="flex items-center justify-between gap-3">
            <div className="font-pixel text-[6px] uppercase tracking-widest text-slate-500">Layout_studio</div>
            {canEditLayout ? (
              <button
                type="button"
                onClick={editor.handleToggleEditMode}
                className={`rounded border px-2 py-1 font-pixel text-[6px] uppercase ${
                  editor.isEditMode
                    ? "border-terminal-cyan/40 bg-terminal-cyan/10 text-terminal-cyan"
                    : "border-white/10 text-slate-400"
                }`}
              >
                {editor.isEditMode ? "Editing" : "Read Only"}
              </button>
            ) : layoutError ? (
              <span className="font-mono text-[10px] text-terminal-danger">asset error</span>
            ) : (
              <span className="font-mono text-[10px] text-slate-500">bootstrapping</span>
            )}
          </div>

          {canEditLayout ? (
            <>
              {editor.isEditMode ? (
                <>
                  <div className="mt-3 grid grid-cols-2 gap-2 font-mono text-[10px] text-slate-400">
                    <div className="rounded border border-white/10 px-2 py-2">
                      <div className="text-[9px] uppercase tracking-wide text-slate-500">Mode</div>
                      <div className="mt-1 text-slate-200">Layout edit</div>
                    </div>
                    <div className="rounded border border-white/10 px-2 py-2">
                      <div className="text-[9px] uppercase tracking-wide text-slate-500">Save State</div>
                      <div className={`mt-1 ${editor.isDirty ? "text-terminal-warn" : "text-terminal-success"}`}>
                        {editor.isDirty ? "Unsaved changes" : "Persisted"}
                      </div>
                    </div>
                    <div className="rounded border border-white/10 px-2 py-2">
                      <div className="text-[9px] uppercase tracking-wide text-slate-500">Tool</div>
                      <div className="mt-1 text-slate-200">{selectedTool}</div>
                    </div>
                    <div className="rounded border border-white/10 px-2 py-2">
                      <div className="text-[9px] uppercase tracking-wide text-slate-500">Selection</div>
                      <div className="mt-1 truncate text-slate-200">{layoutSelection}</div>
                    </div>
                  </div>

                  <div className="mt-3 flex items-center justify-between gap-3 rounded border border-white/10 px-3 py-2 font-mono text-[10px] text-slate-400">
                    <div>
                      <span className="uppercase tracking-wide text-slate-500">Zoom</span>
                      <span className="ml-2 text-slate-200">{zoomPercent}%</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => editor.handleZoomChange(editor.zoom - 0.1)}
                        className="rounded border border-white/10 px-2 py-1 font-pixel text-[6px] uppercase text-slate-300"
                      >
                        -
                      </button>
                      <button
                        type="button"
                        onClick={() => editor.handleZoomChange(1)}
                        className="rounded border border-white/10 px-2 py-1 font-pixel text-[6px] uppercase text-slate-300"
                      >
                        1x
                      </button>
                      <button
                        type="button"
                        onClick={() => editor.handleZoomChange(editor.zoom + 0.1)}
                        className="rounded border border-white/10 px-2 py-1 font-pixel text-[6px] uppercase text-slate-300"
                      >
                        +
                      </button>
                    </div>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-2">
                    {TOOL_OPTIONS.map((item) => (
                      <button
                        key={item.label}
                        type="button"
                        onClick={() => editor.handleToolChange(item.value)}
                        className={`${actionButtonClass} ${
                          editorState.activeTool === item.value
                            ? "border-terminal-warn/40 bg-terminal-warn/10 text-terminal-warn"
                            : "border-white/10 text-slate-400"
                        }`}
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>

                  <div className="mt-3 grid grid-cols-2 gap-2">
                    <label className="rounded border border-white/10 px-2 py-1.5 font-pixel text-[5px] uppercase text-slate-500">
                      {worldEditor ? "World Tile" : "Floor"}
                      <select
                        value={editorState.selectedTileType}
                        onChange={(event) => editor.handleTileTypeChange(Number(event.target.value))}
                        className="mt-1 w-full bg-transparent font-mono text-[11px] text-terminal-cyan outline-none"
                      >
                        {tileOptions.map((item) => (
                          <option key={item.value} value={item.value}>
                            {item.label}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label className="rounded border border-white/10 px-2 py-1.5 font-pixel text-[5px] uppercase text-slate-500">
                      {worldEditor ? "World Asset" : "Furniture"}
                      <select
                        value={editorState.selectedFurnitureType}
                        onChange={(event) => editor.handleFurnitureTypeChange(event.target.value)}
                        className="mt-1 w-full bg-transparent font-mono text-[11px] text-terminal-warn outline-none"
                      >
                        <option value="">select</option>
                        {furnitureOptionGroups.map((category) => (
                          <optgroup key={category.id} label={category.label}>
                            {category.options.map((item) => (
                              <option key={item.value} value={item.value}>
                                {item.label}
                              </option>
                            ))}
                          </optgroup>
                        ))}
                      </select>
                    </label>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={editor.handleRotateSelected}
                      className={`${actionButtonClass} border-terminal-info/40 bg-terminal-info/10 text-terminal-info ${
                        !selectedFurniture ? disabledButtonClass : ""
                      }`}
                      disabled={!selectedFurniture}
                    >
                      Rotate
                    </button>
                    <button
                      type="button"
                      onClick={editor.handleDeleteSelected}
                      className={`${actionButtonClass} border-terminal-danger/40 bg-terminal-danger/10 text-terminal-danger ${
                        !selectedFurniture ? disabledButtonClass : ""
                      }`}
                      disabled={!selectedFurniture}
                    >
                      Delete
                    </button>
                    <button
                      type="button"
                      onClick={editor.handleUndo}
                      className={`${actionButtonClass} border-white/10 text-slate-300 ${
                        !editorState.undoStack.length ? disabledButtonClass : ""
                      }`}
                      disabled={!editorState.undoStack.length}
                    >
                      Undo
                    </button>
                    <button
                      type="button"
                      onClick={editor.handleRedo}
                      className={`${actionButtonClass} border-white/10 text-slate-300 ${
                        !editorState.redoStack.length ? disabledButtonClass : ""
                      }`}
                      disabled={!editorState.redoStack.length}
                    >
                      Redo
                    </button>
                  </div>

                  <div className="mt-3 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={editor.handleSave}
                      className={`${actionButtonClass} border-terminal-success/40 bg-terminal-success/10 text-terminal-success ${
                        !editor.isDirty ? disabledButtonClass : ""
                      }`}
                      disabled={!editor.isDirty}
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      onClick={editor.handleReset}
                      className={`${actionButtonClass} border-white/10 text-slate-300 ${
                        !editor.isDirty ? disabledButtonClass : ""
                      }`}
                      disabled={!editor.isDirty}
                    >
                      Revert
                    </button>
                    <button
                      type="button"
                      onClick={layoutController.resetLayoutToDefault}
                      className={`${actionButtonClass} border-terminal-danger/40 bg-terminal-danger/10 text-terminal-danger`}
                    >
                      Factory
                    </button>
                  </div>

                  <div className="mt-3 font-mono text-[10px] leading-snug text-slate-500">
                    selected piece :: <span className="text-slate-300">{selectedFurnitureType}</span>
                  </div>
                </>
              ) : (
                <>
                  <div className="mt-3 flex flex-wrap gap-2 font-mono text-[10px] text-slate-400">
                    <span className="rounded border border-white/10 px-2 py-1">
                      mode :: <span className="text-slate-200">observe</span>
                    </span>
                    <span className="rounded border border-white/10 px-2 py-1">
                      save ::{" "}
                      <span className={editor.isDirty ? "text-terminal-warn" : "text-terminal-success"}>
                        {editor.isDirty ? "unsaved" : "persisted"}
                      </span>
                    </span>
                    <span className="rounded border border-white/10 px-2 py-1">
                      zoom :: <span className="text-slate-200">{zoomPercent}%</span>
                    </span>
                  </div>

                  <div className="mt-3 rounded border border-white/10 px-3 py-2 font-mono text-[10px] leading-snug text-slate-500">
                    {worldEditor
                      ? "World editing is live. Enable edit mode to place dungeon, castle, guardian, and plague assets; changes persist in local storage until you reset to the bundled default."
                      : "Layout editing is live for end users. Enable edit mode to move desks, redraw walls, or re-seat the lab; changes persist in local storage until you reset to the bundled default."}
                  </div>
                </>
              )}
            </>
          ) : (
            <div className={`mt-3 rounded border px-3 py-2 font-mono text-[10px] leading-snug ${
              layoutError ? "border-terminal-danger/40 text-terminal-danger" : "border-white/10 text-slate-500"
            }`}>
              {layoutError
                ? `${worldEditor ? "World" : "Pixel office"} assets failed to load :: ${layoutError}`
                : `${worldEditor ? "World" : "Pixel office"} runtime is loading. Simulation controls remain active; layout tooling unlocks after the asset bridge finishes bootstrapping.`}
            </div>
          )}
        </div>
      </GlassPanel>
    </div>
  );
}
