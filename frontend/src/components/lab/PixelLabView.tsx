import React, { memo, useEffect, useMemo, useRef, useState } from 'react';

import { getAgentVisualProfile } from '../../agents/agentIdentity';
import { SectionHeader } from '../chrome';
import { RoomMetrics } from './RoomMetrics';
import { renderPixelLabOverlay } from '../../pixel/render/beaconLanes.js';
import { OfficeCanvas } from '../../pixel/office/components/OfficeCanvas.js';

function PixelLabViewInner({ agents, controlAgents, controller, controlStatus }) {
  const containerRef = useRef(null);
  const overlayRef = useRef(null);
  const [, setRenderTick] = useState(0);
  const visualState = controller.adapter.getVisualState();
  const selectedOverlayTarget = controller.selectedAgentKey || controller.editorState.selectedFurnitureUid || 'none';
  const branchCount = controller.officeState.getCharacters().filter((character) => character.isSubagent).length;

  useEffect(() => {
    const timer = window.setInterval(() => setRenderTick((value) => value + 1), 240);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    const canvas = overlayRef.current;
    const container = containerRef.current;
    if (!canvas || !container || !controller.ready) return undefined;

    const ctx = canvas.getContext('2d');
    if (!ctx) return undefined;

    const resize = () => {
      const rect = container.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.round(rect.width * dpr);
      canvas.height = Math.round(rect.height * dpr);
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = `${rect.height}px`;
    };

    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(container);

    let frame = 0;
    const draw = () => {
      renderPixelLabOverlay(
        ctx,
        controller.officeState,
        controller.adapter.getVisualState(),
        controller.editor.zoom,
        controller.editor.panRef.current.x,
        controller.editor.panRef.current.y,
      );
      frame = requestAnimationFrame(draw);
    };

    frame = requestAnimationFrame(draw);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [controller, controller.ready, controller.editor.zoom]);

  const selectedAgent = useMemo(
    () => agents.find((agent) => agent.id === controller.selectedAgentKey) || null,
    [agents, controller.selectedAgentKey],
  );
  const rawSelectedAgent = controller.selectedAgentKey ? controlAgents?.[controller.selectedAgentKey] : null;
  const profile = controller.selectedAgentKey ? getAgentVisualProfile(controller.selectedAgentKey) : null;
  const guardianLocked = visualState.agents.guardian.promptLocked;

  if (controller.error) {
    return (
      <section className="space-y-4 px-1 py-4 sm:px-3">
        <SectionHeader label="PIXEL_LAB" />
        <div className="terminal-panel p-4 font-mono text-[12px] text-terminal-danger">
          pixel lab bootstrap failed :: {controller.error}
        </div>
      </section>
    );
  }

  if (!controller.ready) {
    return (
      <section className="space-y-4 px-1 py-4 sm:px-3">
        <SectionHeader label="PIXEL_LAB" />
        <div className="terminal-panel p-4 font-mono text-[12px] text-slate-400">loading shared office runtime...</div>
      </section>
    );
  }

  return (
    <section className="space-y-4 px-1 py-4 sm:px-3">
      <SectionHeader label="PIXEL_LAB" />
      <div className="flex flex-wrap items-center gap-3 font-mono text-[11px] text-slate-500">
        <span>shared office topology :: 5 agents co-located</span>
        <span className={guardianLocked ? 'text-terminal-danger' : 'text-terminal-success'}>
          guardian prompt {guardianLocked ? 'LOCKED' : 'stable'}
        </span>
      </div>

      <div
        ref={containerRef}
        className="relative h-[620px] overflow-hidden rounded-2xl border border-white/10 bg-[#05070b] shadow-glass"
      >
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(34,211,238,0.08),transparent_38%),radial-gradient(circle_at_bottom_right,rgba(248,113,113,0.08),transparent_30%)]" />
        <OfficeCanvas
          officeState={controller.officeState}
          onClick={() => {}}
          isEditMode={controller.editor.isEditMode}
          editorState={controller.editorState}
          onEditorTileAction={controller.editor.handleEditorTileAction}
          onEditorEraseAction={controller.editor.handleEditorEraseAction}
          onEditorSelectionChange={controller.editor.handleEditorSelectionChange}
          onDeleteSelected={controller.editor.handleDeleteSelected}
          onRotateSelected={controller.editor.handleRotateSelected}
          onDragMove={controller.editor.handleDragMove}
          editorTick={controller.editor.editorTick}
          zoom={controller.editor.zoom}
          onZoomChange={controller.editor.handleZoomChange}
          panRef={controller.editor.panRef}
        />
        <canvas ref={overlayRef} className="pointer-events-none absolute inset-0 z-[3]" />

        {profile && selectedAgent ? (
          <RoomMetrics
            profile={profile}
            agentId={controller.selectedAgentKey}
            agentCard={selectedAgent}
            rawAgent={rawSelectedAgent}
          />
        ) : null}

        <div className="absolute right-3 top-3 z-[4] w-[280px] rounded-2xl border border-white/10 bg-black/45 p-3 backdrop-blur">
          <div className="flex items-center justify-between gap-3">
            <div className="font-pixel text-[6px] uppercase tracking-widest text-slate-500">Office Telemetry</div>
            <span
              className={`rounded border px-2 py-1 font-pixel text-[6px] uppercase ${
                controller.editor.isEditMode
                  ? 'border-terminal-cyan/40 bg-terminal-cyan/10 text-terminal-cyan'
                  : 'border-white/10 text-slate-400'
              }`}
            >
              {controller.editor.isEditMode ? 'Edit mode' : 'Live mode'}
            </span>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-2 font-mono text-[10px] text-slate-400">
            <div className="rounded border border-white/10 px-2 py-2">
              <div className="text-[9px] uppercase tracking-wide text-slate-500">Prompt Shield</div>
              <div className={guardianLocked ? 'mt-1 text-terminal-danger' : 'mt-1 text-terminal-success'}>
                {guardianLocked ? 'locked' : 'stable'}
              </div>
            </div>
            <div className="rounded border border-white/10 px-2 py-2">
              <div className="text-[9px] uppercase tracking-wide text-slate-500">Layout State</div>
              <div className={controller.editor.isDirty ? 'mt-1 text-terminal-warn' : 'mt-1 text-terminal-success'}>
                {controller.editor.isDirty ? 'unsaved' : 'synced'}
              </div>
            </div>
            <div className="rounded border border-white/10 px-2 py-2">
              <div className="text-[9px] uppercase tracking-wide text-slate-500">Focus</div>
              <div className="mt-1 truncate text-slate-200">{selectedOverlayTarget}</div>
            </div>
            <div className="rounded border border-white/10 px-2 py-2">
              <div className="text-[9px] uppercase tracking-wide text-slate-500">Zoom</div>
              <div className="mt-1 text-slate-200">{Math.round(controller.editor.zoom * 100)}%</div>
            </div>
            <div className="rounded border border-white/10 px-2 py-2">
              <div className="text-[9px] uppercase tracking-wide text-slate-500">Strain Branches</div>
              <div className="mt-1 text-slate-200">{branchCount}</div>
            </div>
            <div className="rounded border border-white/10 px-2 py-2">
              <div className="text-[9px] uppercase tracking-wide text-slate-500">Overlay Mode</div>
              <div className="mt-1 text-slate-200">{controller.editor.isEditMode ? 'edit assist' : 'live assist'}</div>
            </div>
          </div>

          <div className="mt-3 font-mono text-[11px] leading-snug text-slate-500">
            {controller.editor.isEditMode
              ? 'layout tools moved to the control plane overlay. use the bottom-right studio to paint floors, move furniture, and persist the office.'
              : 'click an agent to inspect it. drag to pan the office, ctrl+scroll to zoom, and open layout studio from the control plane when you want to reconfigure the lab.'}
          </div>
        </div>
      </div>

      <div className="font-mono text-[11px] text-slate-500">{controlStatus}</div>
    </section>
  );
}

export const PixelLabView = memo(PixelLabViewInner);
