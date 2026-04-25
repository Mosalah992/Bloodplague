import type { SpriteData } from '../types.js';

const spriteCache = new Map<string, HTMLCanvasElement>();
const outlineCache = new WeakMap<SpriteData, SpriteData>();

function spriteKey(sprite: SpriteData, zoom: number): string {
  return `${zoom}:${sprite.map((row) => row.join(',')).join('|')}`;
}

function isSolid(pixel: string | undefined): boolean {
  return Boolean(pixel && pixel !== 'transparent');
}

export function getCachedSprite(sprite: SpriteData, zoom: number): HTMLCanvasElement {
  const key = spriteKey(sprite, zoom);
  const cached = spriteCache.get(key);
  if (cached) return cached;

  const height = sprite.length;
  const width = sprite[0]?.length || 0;
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(width * zoom));
  canvas.height = Math.max(1, Math.round(height * zoom));
  const ctx = canvas.getContext('2d');
  if (!ctx) return canvas;

  ctx.imageSmoothingEnabled = false;
  for (let row = 0; row < height; row += 1) {
    for (let col = 0; col < width; col += 1) {
      const pixel = sprite[row]?.[col];
      if (!isSolid(pixel)) continue;
      ctx.fillStyle = pixel;
      ctx.fillRect(
        Math.round(col * zoom),
        Math.round(row * zoom),
        Math.ceil(zoom),
        Math.ceil(zoom),
      );
    }
  }

  spriteCache.set(key, canvas);
  return canvas;
}

export function getOutlineSprite(sprite: SpriteData): SpriteData {
  const cached = outlineCache.get(sprite);
  if (cached) return cached;

  const height = sprite.length;
  const width = sprite[0]?.length || 0;
  const outline: SpriteData = Array.from({ length: height + 2 }, () => Array(width + 2).fill(''));

  for (let row = 0; row < height; row += 1) {
    for (let col = 0; col < width; col += 1) {
      if (!isSolid(sprite[row]?.[col])) continue;
      for (let dy = -1; dy <= 1; dy += 1) {
        for (let dx = -1; dx <= 1; dx += 1) {
          outline[row + dy + 1][col + dx + 1] = '#FFFFFF';
        }
      }
    }
  }

  outlineCache.set(sprite, outline);
  return outline;
}
