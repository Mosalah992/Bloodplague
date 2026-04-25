const BASE = '/pixel-assets/kenney-dungeon';
const cache = new Map<string, HTMLImageElement | null>();
const loading = new Set<string>();

export function getIsoSprite(name: string): HTMLImageElement | null {
  const cached = cache.get(name);
  if (cached !== undefined) return cached;
  if (loading.has(name)) return null;
  loading.add(name);
  const img = new Image();
  img.onload = () => { cache.set(name, img); loading.delete(name); };
  img.onerror = () => { cache.set(name, null); loading.delete(name); };
  img.src = `${BASE}/${name}.png`;
  return null;
}

export function preloadIsoSprites(names: string[]): void {
  for (const n of names) getIsoSprite(n);
}
