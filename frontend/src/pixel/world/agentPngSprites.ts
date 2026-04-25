const SPRITE_BASE = '/pixel-assets/agents';

// analyst-2 shares analyst-1 assets; orchestrator has its own
const ASSET_AGENT_ID: Record<string, string> = {
  'courier-1':    'courier-1',
  'courier-2':    'courier-2',
  'analyst-1':    'analyst-1',
  'analyst-2':    'analyst-1',
  'guardian':     'guardian',
  'orchestrator': 'orchestrator',
};

const VALID_DIRECTIONS = [
  'north', 'north-east', 'east', 'south-east',
  'south', 'south-west', 'west', 'north-west',
];

export interface AgentPngSprite {
  source: HTMLCanvasElement | HTMLImageElement;
  width: number;
  height: number;
  bounds: {
    left: number;
    top: number;
    right: number;
    bottom: number;
    width: number;
    height: number;
  };
}

const cache = new Map<string, AgentPngSprite | null>();

function key(agentId: string, direction: string): string {
  return `${agentId}/${direction}`;
}

function cleanAgentImage(img: HTMLImageElement): AgentPngSprite {
  const width = img.naturalWidth || img.width || 1;
  const height = img.naturalHeight || img.height || 1;
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  if (!ctx) {
    return {
      source: img,
      width,
      height,
      bounds: { left: 0, top: 0, right: width, bottom: height, width, height },
    };
  }

  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(img, 0, 0);
  const imageData = ctx.getImageData(0, 0, width, height);
  const { data } = imageData;
  let left = width;
  let top = height;
  let right = 0;
  let bottom = 0;

  const alphaAt = (x: number, y: number) => data[(y * width + x) * 4 + 3] ?? 0;
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const i = (y * width + x) * 4;
      const alpha = data[i + 3];
      if (alpha === 0) continue;
      const edgePixel = x < 2 || y < 2 || x >= width - 2 || y >= height - 2;
      let neighbors = 0;
      for (let oy = -1; oy <= 1; oy += 1) {
        for (let ox = -1; ox <= 1; ox += 1) {
          if (ox === 0 && oy === 0) continue;
          const nx = x + ox;
          const ny = y + oy;
          if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
          if (alphaAt(nx, ny) > 28) neighbors += 1;
        }
      }
      if (alpha < 18 || (alpha < 72 && neighbors <= 1) || (edgePixel && alpha < 96)) {
        data[i + 3] = 0;
        continue;
      }
      left = Math.min(left, x);
      top = Math.min(top, y);
      right = Math.max(right, x + 1);
      bottom = Math.max(bottom, y + 1);
    }
  }
  ctx.putImageData(imageData, 0, 0);

  if (right <= left || bottom <= top) {
    left = 0;
    top = 0;
    right = width;
    bottom = height;
  }

  return {
    source: canvas,
    width,
    height,
    bounds: {
      left,
      top,
      right,
      bottom,
      width: right - left,
      height: bottom - top,
    },
  };
}

function load(agentId: string, direction: string): void {
  const k = key(agentId, direction);
  if (cache.has(k)) return;
  cache.set(k, null);
  const assetId = ASSET_AGENT_ID[agentId];
  if (!assetId) return;
  const img = new Image();
  img.onload = () => cache.set(k, cleanAgentImage(img));
  img.onerror = () => cache.set(k, null);
  img.src = `${SPRITE_BASE}/${assetId}/${direction}.png`;
}

export function primeAgentSprites(): void {
  for (const agentId of Object.keys(ASSET_AGENT_ID)) {
    for (const dir of VALID_DIRECTIONS) {
      load(agentId, dir);
    }
  }
}

export function getAgentPngSprite(
  agentId: string,
  direction: string,
): AgentPngSprite | null {
  const dir = VALID_DIRECTIONS.includes(direction) ? direction : 'south';
  const k = key(agentId, dir);
  if (!cache.has(k)) load(agentId, dir);
  return cache.get(k) ?? null;
}
