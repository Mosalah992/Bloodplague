/**
 * PixelLab asset manifest.
 *
 * Maps each agent codename to the PixelLab character ID and resolved local PNG
 * paths (under /pixel-assets/pixellab/).  southUrl is used for agent-card
 * display; allViews exposes all four directional views for the office renderer.
 *
 * To re-download after new generations complete, run:
 *   PIXELLAB_API_KEY=<key> node scripts/download_pixellab_assets.mjs
 *
 * Tileset:
 *   ID        2660de70-d5c2-4a88-9d56-c68611cf8c82
 *   lower base tile  b8b8e2ea-227f-49f5-968d-5ac04958082f  (clean dark floor)
 *   upper base tile  8684681f-8b23-4535-8aa8-1e776f19d22e  (infected floor)
 */

/** @type {Record<string, { characterId: string, southUrl: string|null, allViews: Record<string, string>|null }>} */
export const PIXELLAB_CHARACTERS = {
  GUARDIAN: {
    characterId: "e1a4eeb0-3d2c-443f-b1a1-8cafd6224153",
    southUrl: "/pixel-assets/pixellab/guardian_south.png",
    allViews: {
      south:      "/pixel-assets/pixellab/guardian_south.png",
      "south-east": "/pixel-assets/pixellab/guardian_south-east.png",
      east:       "/pixel-assets/pixellab/guardian_east.png",
      "north-east": "/pixel-assets/pixellab/guardian_north-east.png",
      north:      "/pixel-assets/pixellab/guardian_north.png",
      "north-west": "/pixel-assets/pixellab/guardian_north-west.png",
      west:       "/pixel-assets/pixellab/guardian_west.png",
      "south-west": "/pixel-assets/pixellab/guardian_south-west.png",
    },
  },
  VECTOR: {
    characterId: "3cbbe6e0-9095-4440-a9c3-3990295c7ef9",
    southUrl: "/pixel-assets/pixellab/vector_south.png",
    allViews: {
      south:      "/pixel-assets/pixellab/vector_south.png",
      "south-east": "/pixel-assets/pixellab/vector_south-east.png",
      east:       "/pixel-assets/pixellab/vector_east.png",
      "north-east": "/pixel-assets/pixellab/vector_north-east.png",
      north:      "/pixel-assets/pixellab/vector_north.png",
      "north-west": "/pixel-assets/pixellab/vector_north-west.png",
      west:       "/pixel-assets/pixellab/vector_west.png",
      "south-west": "/pixel-assets/pixellab/vector_south-west.png",
    },
  },
  SENTINEL: {
    characterId: "fe15f1fc-8c22-4c61-a4f0-80773cb18884",
    southUrl: "/pixel-assets/pixellab/sentinel_south.png",
    allViews: {
      south:      "/pixel-assets/pixellab/sentinel_south.png",
      "south-east": "/pixel-assets/pixellab/sentinel_south-east.png",
      east:       "/pixel-assets/pixellab/sentinel_east.png",
      "north-east": "/pixel-assets/pixellab/sentinel_north-east.png",
      north:      "/pixel-assets/pixellab/sentinel_north.png",
      "north-west": "/pixel-assets/pixellab/sentinel_north-west.png",
      west:       "/pixel-assets/pixellab/sentinel_west.png",
      "south-west": "/pixel-assets/pixellab/sentinel_south-west.png",
    },
  },
  EXPLOIT: {
    characterId: "6125e68d-e6f0-4221-af97-5e5cc0f95058",
    southUrl: "/pixel-assets/pixellab/exploit_south.png",
    allViews: {
      south:      "/pixel-assets/pixellab/exploit_south.png",
      "south-east": "/pixel-assets/pixellab/exploit_south-east.png",
      east:       "/pixel-assets/pixellab/exploit_east.png",
      "north-east": "/pixel-assets/pixellab/exploit_north-east.png",
      north:      "/pixel-assets/pixellab/exploit_north.png",
      "north-west": "/pixel-assets/pixellab/exploit_north-west.png",
      west:       "/pixel-assets/pixellab/exploit_west.png",
      "south-west": "/pixel-assets/pixellab/exploit_south-west.png",
    },
  },
  // Reuses the Analyst 1 generation because /new assets currently has one analyst character.
  PATIENT_ZERO: {
    characterId: "fe15f1fc-8c22-4c61-a4f0-80773cb18884",
    southUrl: "/pixel-assets/pixellab/patient_zero_south.png",
    allViews: {
      south:      "/pixel-assets/pixellab/patient_zero_south.png",
      "south-east": "/pixel-assets/pixellab/patient_zero_south-east.png",
      east:       "/pixel-assets/pixellab/patient_zero_east.png",
      "north-east": "/pixel-assets/pixellab/patient_zero_north-east.png",
      north:      "/pixel-assets/pixellab/patient_zero_north.png",
      "north-west": "/pixel-assets/pixellab/patient_zero_north-west.png",
      west:       "/pixel-assets/pixellab/patient_zero_west.png",
      "south-west": "/pixel-assets/pixellab/patient_zero_south-west.png",
    },
  },
};

export const PIXELLAB_TILESET = {
  tilesetId:       "31287e4d-f40a-42e5-b547-91e40780b29d",
  lowerBaseTileId: "2b43823f-b994-4db6-8b25-d3639b930c89",
  upperBaseTileId: "3189f961-d0b1-4396-9d9a-263acb02b6f1",
  // 64×64 PNG — 4×4 grid of 16 Wang tiles (16×16 each)
  // lower = dark charcoal cyber floor, upper = infected neon-crack floor
  pngUrl: "/pixel-assets/pixellab/cyber_office_floor.png",
};

/**
 * South-facing (front view) PixelLab image URL for a given agent codename,
 * or null if not yet downloaded.
 *
 * @param {string} codename  e.g. "GUARDIAN"
 * @returns {string|null}
 */
export function getPixelLabSouthUrl(codename) {
  return PIXELLAB_CHARACTERS[codename]?.southUrl ?? null;
}

/**
 * All four directional view URLs for a given codename, or null.
 *
 * @param {string} codename
 * @returns {Record<string, string>|null}
 */
export function getPixelLabAllViews(codename) {
  return PIXELLAB_CHARACTERS[codename]?.allViews ?? null;
}
