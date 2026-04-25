#!/usr/bin/env node
/**
 * download_pixellab_assets.mjs
 *
 * After PixelLab character and tileset generation completes, run this script
 * to download the generated PNGs into the public asset tree. By default the
 * tracked manifest is left unchanged so repeated refreshes do not dirty the
 * git worktree.
 *
 * Usage (requires the @pixellab/mcp SDK or direct REST access):
 *   node scripts/download_pixellab_assets.mjs
 *   node scripts/download_pixellab_assets.mjs --update-manifest
 *
 * What it does:
 *  1. Reads character IDs from src/agents/pixelLabManifest.js
 *  2. Fetches each character from the PixelLab API (GET /characters/:id)
 *  3. Downloads the south-facing PNG into public/pixel-assets/pixellab/
 *  4. Optionally patches pixelLabManifest.js with the resolved local paths
 *  5. Downloads the tileset PNG into public/pixel-assets/pixellab/
 *
 * Character IDs:
 *   GUARDIAN     3126d12d-be8d-4906-affe-9c028e9f810c
 *   VECTOR       97d5c6df-d98e-4406-84aa-0b5895f2152b
 *   SENTINEL     fdf98dd0-8c9b-4d9a-b221-d9acf3a93e46
 *   EXPLOIT      e389150e-4d72-4c9f-b752-e3bd77193099
 *   PATIENT_ZERO d9f17d87-0df9-4842-a9dd-9656d95f3c28
 *
 * Pass --update-manifest only when intentionally changing
 * frontend/src/agents/pixelLabManifest.js.
 *
 * Tileset ID:
 *   2660de70-d5c2-4a88-9d56-c68611cf8c82
 */

import { createWriteStream, mkdirSync } from "fs";
import { readFile, writeFile } from "fs/promises";
import { Readable } from "stream";
import { pipeline } from "stream/promises";
import { fileURLToPath } from "url";
import path from "path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const ASSET_DIR = path.join(ROOT, "frontend", "public", "pixel-assets", "pixellab");
const MANIFEST_PATH = path.join(ROOT, "frontend", "src", "agents", "pixelLabManifest.js");

const PIXELLAB_API = "https://api.pixellab.ai";
// API key — set PIXELLAB_API_KEY in environment or .env
const API_KEY = process.env.PIXELLAB_API_KEY || "";
const UPDATE_MANIFEST = process.argv.includes("--update-manifest");

const CHARACTERS = {
  GUARDIAN:     "3126d12d-be8d-4906-affe-9c028e9f810c",
  VECTOR:       "97d5c6df-d98e-4406-84aa-0b5895f2152b",
  SENTINEL:     "fdf98dd0-8c9b-4d9a-b221-d9acf3a93e46",
  EXPLOIT:      "e389150e-4d72-4c9f-b752-e3bd77193099",
  PATIENT_ZERO: "d9f17d87-0df9-4842-a9dd-9656d95f3c28",
};

const TILESET_ID = "2660de70-d5c2-4a88-9d56-c68611cf8c82";

async function apiFetch(endpoint) {
  const resp = await fetch(`${PIXELLAB_API}${endpoint}`, {
    headers: { Authorization: `Bearer ${API_KEY}` },
  });
  if (!resp.ok) throw new Error(`PixelLab API ${resp.status}: ${endpoint}`);
  return resp.json();
}

async function downloadImage(url, destPath) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`Failed to download ${url}: ${resp.status}`);
  const stream = createWriteStream(destPath);
  await pipeline(Readable.fromWeb(resp.body), stream);
  console.log(`  ✓  ${path.basename(destPath)}`);
}

async function main() {
  if (!API_KEY) {
    console.error("Set PIXELLAB_API_KEY in env before running.");
    process.exit(1);
  }

  mkdirSync(ASSET_DIR, { recursive: true });

  const resolvedUrls = {};

  // ── Characters ────────────────────────────────────────────────────────────
  for (const [codename, charId] of Object.entries(CHARACTERS)) {
    console.log(`\nFetching ${codename} (${charId})…`);
    const data = await apiFetch(`/characters/${charId}`);

    if (data.status !== "completed") {
      console.warn(`  ⚠  Still processing (${data.status}) — skipping`);
      continue;
    }

    // Find the south/front-facing view
    const southView = data.rotations?.find(
      (r) => r.direction === "south" || r.direction === "down"
    ) || data.rotations?.[0];

    if (!southView?.image_url) {
      console.warn(`  ⚠  No south image URL found`);
      continue;
    }

    const filename = `${codename.toLowerCase()}_south.png`;
    await downloadImage(southView.image_url, path.join(ASSET_DIR, filename));
    resolvedUrls[codename] = `/pixel-assets/pixellab/${filename}`;
  }

  // ── Tileset ───────────────────────────────────────────────────────────────
  console.log(`\nFetching tileset (${TILESET_ID})…`);
  const tileData = await apiFetch(`/topdown-tilesets/${TILESET_ID}`);

  let tilesetLocalPath = null;
  if (tileData.status === "completed" && tileData.png_url) {
    const filename = "cyber_office_floor.png";
    await downloadImage(tileData.png_url, path.join(ASSET_DIR, filename));
    tilesetLocalPath = `/pixel-assets/pixellab/${filename}`;
  } else {
    console.warn(`  ⚠  Tileset not yet completed (${tileData.status})`);
  }

  if (!UPDATE_MANIFEST) {
    console.log("\nManifest unchanged. Pass --update-manifest to patch pixelLabManifest.js.");
    console.log("\nDone. Restart the Vite dev server to pick up refreshed assets.");
    return;
  }

  // ── Patch manifest ────────────────────────────────────────────────────────
  console.log("\nPatching pixelLabManifest.js…");
  let src = await readFile(MANIFEST_PATH, "utf8");

  for (const [codename, localUrl] of Object.entries(resolvedUrls)) {
    // Replace:  southUrl: null,   →   southUrl: "/pixel-assets/pixellab/…",
    const re = new RegExp(
      `(${codename}:[^}]+southUrl:\\s*)null`,
      "s"
    );
    src = src.replace(re, `$1"${localUrl}"`);
  }

  if (tilesetLocalPath) {
    src = src.replace(/pngUrl:\s*null/, `pngUrl: "${tilesetLocalPath}"`);
  }

  await writeFile(MANIFEST_PATH, src, "utf8");
  console.log("  ✓  Manifest updated");
  console.log("\nDone. Restart the Vite dev server to pick up new assets.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
