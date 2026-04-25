import { AGENT_PROFILES } from '../../agents/agentIdentity.js';

const AGENT_CODENAMES: Record<string, string> = {
  'courier-1': 'SHADOW',
  'courier-2': 'PHANTOM',
  'analyst-1': 'ORACLE',
  'analyst-2': 'CIPHER',
  'guardian':  'SENTINEL',
};

const STATE_TO_ANIM: Record<string, string> = {
  'I_R': 'infected',
  'I_C': 'infected',
  'I_X': 'infected',
  'Q':   'defend',
  'P':   'infected',
};

type SpriteFrame = Array<Array<string | null>>;
type AnimSet = Record<string, SpriteFrame[]>;

export const SPRITE_SCALE = 3;
export const SPRITE_W = 16 * SPRITE_SCALE;
export const SPRITE_H = 18 * SPRITE_SCALE;

// Per-agent cache: mode → OffscreenCanvas[]
const spriteCache = new Map<string, Map<string, OffscreenCanvas[]>>();

function frameToOffscreen(frame: SpriteFrame): OffscreenCanvas {
  const srcH = frame.length;
  const srcW = frame[0]?.length ?? 0;
  const dstW = srcW * SPRITE_SCALE;
  const dstH = srcH * SPRITE_SCALE;
  const canvas = new OffscreenCanvas(dstW, dstH);
  const ctx = canvas.getContext('2d')!;
  const imgData = new ImageData(dstW, dstH);
  const data = imgData.data;

  for (let r = 0; r < srcH; r++) {
    for (let c = 0; c < srcW; c++) {
      const hex = frame[r]?.[c];
      if (!hex || typeof hex !== 'string') continue;
      const ri = parseInt(hex.slice(1, 3), 16);
      const gi = parseInt(hex.slice(3, 5), 16);
      const bi = parseInt(hex.slice(5, 7), 16);
      for (let sy = 0; sy < SPRITE_SCALE; sy++) {
        for (let sx = 0; sx < SPRITE_SCALE; sx++) {
          const idx = ((r * SPRITE_SCALE + sy) * dstW + (c * SPRITE_SCALE + sx)) * 4;
          data[idx]     = ri;
          data[idx + 1] = gi;
          data[idx + 2] = bi;
          data[idx + 3] = 255;
        }
      }
    }
  }

  ctx.putImageData(imgData, 0, 0);
  return canvas;
}

function buildCacheForAgent(agentId: string): Map<string, OffscreenCanvas[]> {
  const codename = AGENT_CODENAMES[agentId];
  if (!codename) return new Map();
  const profile = (AGENT_PROFILES as Record<string, { spriteSet?: AnimSet }>)[codename];
  if (!profile?.spriteSet) return new Map();
  const cache = new Map<string, OffscreenCanvas[]>();
  for (const [mode, frames] of Object.entries(profile.spriteSet)) {
    cache.set(mode, (frames as SpriteFrame[]).map(frameToOffscreen));
  }
  return cache;
}

function getCache(agentId: string): Map<string, OffscreenCanvas[]> {
  if (!spriteCache.has(agentId)) {
    spriteCache.set(agentId, buildCacheForAgent(agentId));
  }
  return spriteCache.get(agentId)!;
}

export function getAgentSprite(
  agentId: string,
  epidemicState: string,
  elapsed: number,
): OffscreenCanvas | null {
  const cache = getCache(agentId);
  if (!cache.size) return null;
  const mode = STATE_TO_ANIM[epidemicState] ?? 'idle';
  const frames = cache.get(mode) ?? cache.get('idle');
  if (!frames?.length) return null;
  const fps = mode === 'idle' ? 1.5 : 3;
  const idx = Math.floor(elapsed * fps) % frames.length;
  return frames[idx];
}
