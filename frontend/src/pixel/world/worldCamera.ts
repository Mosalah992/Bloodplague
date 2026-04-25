import {
  ISO_HALF_W, ISO_HALF_H, ISO_ORIGIN_X, ISO_ORIGIN_Y,
  ISO_WORLD_W, ISO_WORLD_H,
} from '../constants.js';

const ZOOM_MIN = 0.25;
const ZOOM_MAX = 4.0;
const ZOOM_STEP = 0.2;
const LERP_SPEED = 8.0;

export interface CameraState {
  x: number;
  y: number;
  zoom: number;
  targetX: number;
  targetY: number;
  targetZoom: number;
  viewportW: number;
  viewportH: number;
}

// Top-down (D2-style): anchor is TOP-CENTER of cell so (iy + 2*ISO_HALF_H) is
// the cell bottom (feet line). This preserves existing "iy + ISO_HALF_H*2 = bottom"
// semantics used by agent/structure renderers.
export function tileToIso(col: number, row: number): [number, number] {
  return [
    ISO_ORIGIN_X + col * (2 * ISO_HALF_W) + ISO_HALF_W,
    ISO_ORIGIN_Y + row * (2 * ISO_HALF_H),
  ];
}

// Inverse for cell-pick: caller does Math.floor() to get integer col/row.
export function isoToTile(wx: number, wy: number): [number, number] {
  return [
    (wx - ISO_ORIGIN_X) / (2 * ISO_HALF_W),
    (wy - ISO_ORIGIN_Y) / (2 * ISO_HALF_H),
  ];
}

export function createCamera(viewportW: number, viewportH: number): CameraState {
  // Start at 1.2x zoom centered on the analyst/courier action area (col~22, row~6)
  const zoom = 1.2;
  const [isoX, isoY] = tileToIso(22, 6);
  const x = isoX - viewportW / (2 * zoom);
  const y = isoY - viewportH / (2 * zoom);
  const cam = { x, y, zoom, targetX: x, targetY: y, targetZoom: zoom, viewportW, viewportH };
  clampCamera(cam);
  return cam;
}

export function updateCamera(cam: CameraState, dt: number): void {
  const t = Math.min(1, LERP_SPEED * dt);
  cam.zoom = cam.zoom + (cam.targetZoom - cam.zoom) * t;
  cam.x = cam.x + (cam.targetX - cam.x) * t;
  cam.y = cam.y + (cam.targetY - cam.y) * t;
  clampCamera(cam);
}

export function panCamera(cam: CameraState, dx: number, dy: number): void {
  cam.targetX += dx / cam.zoom;
  cam.targetY += dy / cam.zoom;
  clampCamera(cam);
}

export function zoomCamera(cam: CameraState, delta: number, pivotX: number, pivotY: number): void {
  const prevZoom = cam.targetZoom;
  cam.targetZoom = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, cam.targetZoom + delta * ZOOM_STEP));
  const zoomRatio = cam.targetZoom / prevZoom;
  const worldPivotX = cam.targetX + pivotX / prevZoom;
  const worldPivotY = cam.targetY + pivotY / prevZoom;
  cam.targetX = worldPivotX - pivotX / cam.targetZoom;
  cam.targetY = worldPivotY - pivotY / cam.targetZoom;
  clampCamera(cam);
}

export function focusCamera(cam: CameraState, worldX: number, worldY: number): void {
  cam.targetX = worldX - cam.viewportW / (2 * cam.targetZoom);
  cam.targetY = worldY - cam.viewportH / (2 * cam.targetZoom);
  clampCamera(cam);
}

function clampCamera(cam: CameraState): void {
  const visW = cam.viewportW / cam.zoom;
  const visH = cam.viewportH / cam.zoom;
  const minX = Math.min(0, ISO_WORLD_W - visW) / 2;
  const minY = Math.min(0, ISO_WORLD_H - visH) / 2;
  const maxX = Math.max(0, ISO_WORLD_W - visW);
  const maxY = Math.max(0, ISO_WORLD_H - visH);
  cam.targetX = Math.max(minX, Math.min(maxX, cam.targetX));
  cam.targetY = Math.max(minY, Math.min(maxY, cam.targetY));
  cam.x = Math.max(minX, Math.min(maxX, cam.x));
  cam.y = Math.max(minY, Math.min(maxY, cam.y));
}

function fitZoomForViewport(viewportW: number, viewportH: number): number {
  const fit = Math.min(viewportW / ISO_WORLD_W, viewportH / ISO_WORLD_H) * 0.96;
  return Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, fit));
}

export function worldToScreen(cam: CameraState, wx: number, wy: number): [number, number] {
  return [(wx - cam.x) * cam.zoom, (wy - cam.y) * cam.zoom];
}

export function screenToWorld(cam: CameraState, sx: number, sy: number): [number, number] {
  return [sx / cam.zoom + cam.x, sy / cam.zoom + cam.y];
}

export function resizeCamera(cam: CameraState, w: number, h: number): void {
  const cx = cam.targetX + cam.viewportW / (2 * cam.targetZoom);
  const cy = cam.targetY + cam.viewportH / (2 * cam.targetZoom);
  cam.viewportW = w;
  cam.viewportH = h;
  if (cam.targetZoom <= ZOOM_MIN + 0.01) {
    cam.targetZoom = fitZoomForViewport(w, h);
    cam.zoom = cam.targetZoom;
  }
  cam.targetX = cx - w / (2 * cam.targetZoom);
  cam.targetY = cy - h / (2 * cam.targetZoom);
  clampCamera(cam);
}
