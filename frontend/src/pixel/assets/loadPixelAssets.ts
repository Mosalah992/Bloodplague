import { rgbaToHex } from '../shared/assets/colorUtils.js';
import {
  CHAR_FRAME_H,
  CHAR_FRAME_W,
  CHAR_FRAMES_PER_ROW,
  CHARACTER_DIRECTIONS,
  FLOOR_TILE_SIZE,
  WALL_BITMASK_COUNT,
  WALL_GRID_COLS,
  WALL_PIECE_HEIGHT,
  WALL_PIECE_WIDTH,
} from '../shared/assets/constants.js';
import type {
  AssetIndex,
  CatalogEntry,
  CharacterDirectionSprites,
} from '../shared/assets/types.js';
import { setFloorSprites } from '../office/floorTiles.js';
import { buildDynamicCatalog } from '../office/layout/furnitureCatalog.js';
import type { OfficeLayout } from '../office/types.js';
import { setCharacterTemplates } from '../office/sprites/spriteData.js';
import { setWallSprites } from '../office/wallTiles.js';

interface DecodedPng {
  width: number;
  height: number;
  data: Uint8ClampedArray;
}

export interface LoadedPixelAssets {
  layout: OfficeLayout;
}

function joinBase(basePath: string, relPath: string): string {
  return `${basePath.replace(/\/+$/, '')}/${relPath.replace(/^\/+/, '')}`;
}

function getPixel(
  data: Uint8ClampedArray,
  width: number,
  x: number,
  y: number,
): [number, number, number, number] {
  const index = (y * width + x) * 4;
  return [data[index], data[index + 1], data[index + 2], data[index + 3]];
}

function readSprite(
  png: DecodedPng,
  width: number,
  height: number,
  offsetX = 0,
  offsetY = 0,
): string[][] {
  const sprite: string[][] = [];
  for (let y = 0; y < height; y += 1) {
    const row: string[] = [];
    for (let x = 0; x < width; x += 1) {
      const [r, g, b, a] = getPixel(png.data, png.width, offsetX + x, offsetY + y);
      row.push(rgbaToHex(r, g, b, a));
    }
    sprite.push(row);
  }
  return sprite;
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Asset request failed: ${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

async function decodePng(url: string): Promise<DecodedPng> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch PNG asset: ${url}`);
  }
  const blob = await response.blob();
  const bitmap = await createImageBitmap(blob);
  const canvas = document.createElement('canvas');
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  const ctx = canvas.getContext('2d');
  if (!ctx) {
    bitmap.close();
    throw new Error('2D canvas context unavailable while decoding PNG assets');
  }
  ctx.drawImage(bitmap, 0, 0);
  bitmap.close();
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
  return {
    width: canvas.width,
    height: canvas.height,
    data: imageData.data,
  };
}

async function decodeCharacters(
  basePath: string,
  index: AssetIndex,
): Promise<CharacterDirectionSprites[]> {
  const result: CharacterDirectionSprites[] = [];

  for (const relPath of index.characters) {
    const png = await decodePng(joinBase(basePath, `characters/${relPath}`));
    const entry: CharacterDirectionSprites = { down: [], up: [], right: [] };

    for (let directionIndex = 0; directionIndex < CHARACTER_DIRECTIONS.length; directionIndex += 1) {
      const direction = CHARACTER_DIRECTIONS[directionIndex];
      const rowOffset = directionIndex * CHAR_FRAME_H;
      const frames: string[][][] = [];

      for (let frame = 0; frame < CHAR_FRAMES_PER_ROW; frame += 1) {
        frames.push(readSprite(png, CHAR_FRAME_W, CHAR_FRAME_H, frame * CHAR_FRAME_W, rowOffset));
      }

      entry[direction] = frames;
    }

    result.push(entry);
  }

  return result;
}

async function decodeFloors(basePath: string, index: AssetIndex): Promise<string[][][]> {
  const floors: string[][][] = [];
  for (const relPath of index.floors) {
    const png = await decodePng(joinBase(basePath, `floors/${relPath}`));
    floors.push(readSprite(png, FLOOR_TILE_SIZE, FLOOR_TILE_SIZE));
  }
  return floors;
}

async function decodeWalls(basePath: string, index: AssetIndex): Promise<string[][][][]> {
  const wallSets: string[][][][] = [];

  for (const relPath of index.walls) {
    const png = await decodePng(joinBase(basePath, `walls/${relPath}`));
    const set: string[][][] = [];

    for (let mask = 0; mask < WALL_BITMASK_COUNT; mask += 1) {
      const offsetX = (mask % WALL_GRID_COLS) * WALL_PIECE_WIDTH;
      const offsetY = Math.floor(mask / WALL_GRID_COLS) * WALL_PIECE_HEIGHT;
      set.push(readSprite(png, WALL_PIECE_WIDTH, WALL_PIECE_HEIGHT, offsetX, offsetY));
    }

    wallSets.push(set);
  }

  return wallSets;
}

async function decodeFurniture(
  basePath: string,
  catalog: CatalogEntry[],
): Promise<Record<string, string[][]>> {
  const entries = await Promise.all(
    catalog.map(async (entry) => {
      const png = await decodePng(joinBase(basePath, entry.furniturePath));
      return [entry.id, readSprite(png, entry.width, entry.height)] as const;
    }),
  );

  return Object.fromEntries(entries);
}

export async function loadPixelAssets(basePath = '/pixel-assets'): Promise<LoadedPixelAssets> {
  const index = await fetchJson<AssetIndex>(joinBase(basePath, 'asset-index.json'));
  const catalog = await fetchJson<CatalogEntry[]>(joinBase(basePath, 'furniture-catalog.json'));

  const [characters, floors, walls, furnitureSprites, layout] = await Promise.all([
    decodeCharacters(basePath, index),
    decodeFloors(basePath, index),
    decodeWalls(basePath, index),
    decodeFurniture(basePath, catalog),
    fetchJson<OfficeLayout>(joinBase(basePath, index.defaultLayout || 'default-layout.json')),
  ]);

  setCharacterTemplates(characters);
  setFloorSprites(floors);
  setWallSprites(walls);
  buildDynamicCatalog({ catalog, sprites: furnitureSprites });

  return { layout };
}
