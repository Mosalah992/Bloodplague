import { useEffect, useMemo, useRef, useState } from 'react';

import { loadPixelAssets } from '../assets/loadPixelAssets.js';
import type { DashboardState } from '../epidemicAdapter.js';
import { EpidemicAdapter } from '../epidemicAdapter.js';
import { registerPixelHostHandler } from '../host/pixelHostBridge.js';
import { getPixelAgentSpecByNumericId } from '../identity.js';
import { EditorState } from '../office/editor/editorState.js';
import { OfficeState } from '../office/engine/officeState.js';
import type { OfficeLayout } from '../office/types.js';
import { useEditorActions } from './useEditorActions.js';

const LAYOUT_STORAGE_KEY = 'epidemic.pixel_lab.layout.v2';
const SEATS_STORAGE_KEY = 'epidemic.pixel_lab.seats.v1';

interface StoredSeatAssignment {
  seatId?: string | null;
  palette?: number | null;
}

type StoredSeatAssignments = Record<string, StoredSeatAssignment>;

function isLayoutCandidate(value: unknown): value is OfficeLayout {
  if (!value || typeof value !== 'object') return false;
  const layout = value as Record<string, unknown>;
  return layout.version === 1 && Array.isArray(layout.tiles) && Array.isArray(layout.furniture);
}

function readStoredLayout(): OfficeLayout | null {
  try {
    const raw = window.localStorage.getItem(LAYOUT_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return isLayoutCandidate(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

function isSeatAssignmentsCandidate(value: unknown): value is StoredSeatAssignments {
  if (!value || typeof value !== 'object') return false;
  return Object.values(value as Record<string, unknown>).every((entry) => {
    if (!entry || typeof entry !== 'object') return false;
    const assignment = entry as Record<string, unknown>;
    return (
      assignment.seatId === undefined ||
      assignment.seatId === null ||
      typeof assignment.seatId === 'string'
    );
  });
}

function readStoredSeats(): StoredSeatAssignments | null {
  try {
    const raw = window.localStorage.getItem(SEATS_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return isSeatAssignmentsCandidate(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function usePixelLabController(controlState: unknown) {
  const officeStateRef = useRef<OfficeState | null>(null);
  if (!officeStateRef.current) {
    officeStateRef.current = new OfficeState();
  }

  const editorStateRef = useRef<EditorState | null>(null);
  if (!editorStateRef.current) {
    editorStateRef.current = new EditorState();
  }

  const editor = useEditorActions(() => officeStateRef.current as OfficeState, editorStateRef.current);
  const setLastSavedLayout = editor.setLastSavedLayout;
  const adapterRef = useRef<EpidemicAdapter | null>(null);
  if (!adapterRef.current) {
    adapterRef.current = new EpidemicAdapter(officeStateRef.current);
  }

  const defaultLayoutRef = useRef<OfficeLayout | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedAgentKey, setSelectedAgentKey] = useState<string | null>(null);

  useEffect(() => {
    return registerPixelHostHandler((message) => {
      if (message.type === 'saveLayout' && message.layout) {
        window.localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify(message.layout));
      }
      if (message.type === 'saveAgentSeats' && message.seats) {
        const serialized = JSON.stringify(message.seats);
        window.localStorage.setItem(SEATS_STORAGE_KEY, serialized);
        adapterRef.current?.setSeatAssignments(readStoredSeats());
      }
    });
  }, []);

  useEffect(() => {
    let cancelled = false;

    void loadPixelAssets('/pixel-assets')
      .then(({ layout }) => {
        if (cancelled) return;
        defaultLayoutRef.current = layout;
        const activeLayout = readStoredLayout() || layout;
        const storedSeats = readStoredSeats();
        officeStateRef.current?.rebuildFromLayout(activeLayout);
        adapterRef.current?.setSeatAssignments(storedSeats);
        setLastSavedLayout(activeLayout);
        setReady(true);
      })
      .catch((loadError) => {
        if (cancelled) return;
        setError(loadError instanceof Error ? loadError.message : String(loadError));
      });

    return () => {
      cancelled = true;
      adapterRef.current?.dispose();
    };
  }, [setLastSavedLayout]);

  useEffect(() => {
    if (!ready) return;
    adapterRef.current?.syncSnapshot(controlState as DashboardState | null | undefined);
  }, [controlState, ready]);

  useEffect(() => {
    let frame = 0;
    const tick = () => {
      const selectedId = officeStateRef.current?.selectedAgentId ?? null;
      const next = getPixelAgentSpecByNumericId(selectedId)?.key || null;
      setSelectedAgentKey((current) => (current === next ? current : next));
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, []);

  const controller = useMemo(
    () => ({
      officeState: officeStateRef.current as OfficeState,
      editorState: editorStateRef.current as EditorState,
      editor,
      adapter: adapterRef.current as EpidemicAdapter,
      ready,
      error,
      selectedAgentKey,
      setSelectedAgentKey,
      resetLayoutToDefault: () => {
        const defaultLayout = defaultLayoutRef.current;
        if (!defaultLayout) return;
        window.localStorage.removeItem(LAYOUT_STORAGE_KEY);
        const cloned = structuredClone(defaultLayout);
        officeStateRef.current?.rebuildFromLayout(cloned);
        setLastSavedLayout(cloned);
      },
    }),
    [editor, error, ready, selectedAgentKey, setLastSavedLayout],
  );

  return controller;
}
