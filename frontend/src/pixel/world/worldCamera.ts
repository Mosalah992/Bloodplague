import { WORLD_COLS, WORLD_ROWS, WORLD_TILE_SIZE } from '../constants.js';

const ZOOM_MIN = 1.0;
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

export function createCamera(viewportW: number, viewportH: number): CameraState {
  const worldW = WORLD_COLS * WORLD_TILE_SIZE;
  const worldH = WORLD_ROWS * WORLD_TILE_SIZE;
  return {
    x: worldW / 2 - viewportW / 2,
    y: worldH / 2 - viewportH / 2,
    zoom: 2.0,
    targetX: worldW / 2 - viewportW / 2,
    targetY: worldH / 2 - viewportH / 2,
    targetZoom: 2.0,
    viewportW,
    viewportH,
  };
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
  const worldW = WORLD_COLS * WORLD_TILE_SIZE;
  const worldH = WORLD_ROWS * WORLD_TILE_SIZE;
  const visW = cam.viewportW / cam.zoom;
  const visH = cam.viewportH / cam.zoom;
  cam.targetX = Math.max(0, Math.min(worldW - visW, cam.targetX));
  cam.targetY = Math.max(0, Math.min(worldH - visH, cam.targetY));
  cam.x = Math.max(0, Math.min(worldW - visW, cam.x));
  cam.y = Math.max(0, Math.min(worldH - visH, cam.y));
}

export function worldToScreen(cam: CameraState, wx: number, wy: number): [number, number] {
  return [(wx - cam.x) * cam.zoom, (wy - cam.y) * cam.zoom];
}

export function screenToWorld(cam: CameraState, sx: number, sy: number): [number, number] {
  return [sx / cam.zoom + cam.x, sy / cam.zoom + cam.y];
}

export function resizeCamera(cam: CameraState, w: number, h: number): void {
  cam.viewportW = w;
  cam.viewportH = h;
  clampCamera(cam);
}
