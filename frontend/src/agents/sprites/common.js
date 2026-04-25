import { frameFromKeys, normalizeAnimationSet } from "../spriteUtils.js";

const BASE_PALETTE = {
  K: "#05070a",
  O: "#111827",
  S: "#334155",
  L: "#e5e7eb",
  W: "#ffffff",
  R: "#ef4444",
  X: "#f87171",
};

const IDLE_A = [
  "................",
  "......KKKK......",
  ".....KBBBBK.....",
  "....KBBBBBBK....",
  "....KLLBBLLK....",
  "....KBBBBBBK....",
  ".....KBBBBK.....",
  "......KHHK......",
  "....KKCCCCKK....",
  "...KCCACACCK...",
  "...KCCCCCCCCK...",
  "....KCCCCCCK....",
  ".....KCCCCK.....",
  ".....KSSSSK.....",
  "....KSS..SSK....",
  "...KSS....SSK...",
  "...KK......KK...",
  "................",
];

const IDLE_B = [
  "................",
  "......KKKK......",
  ".....KBBBBK.....",
  "....KBBBBBBK....",
  "....KLLBBLLK....",
  "....KBBBBBBK....",
  ".....KBBBBK.....",
  "......KHHK......",
  "....KKCCCCKK....",
  "...KCCACACCK...",
  "...KCCCCCCCCK...",
  "....KCCCCCCK....",
  ".....KCCCCK.....",
  ".....KSSSSK.....",
  "...KSS....SSK...",
  "...KK......KK...",
  "................",
  "................",
];

const ATTACK_A = [
  "................",
  "......KKKK......",
  ".....KBBBBK.....",
  "....KBBLLBBK....",
  "....KBBBBBBK....",
  ".....KBBBBK.....",
  "......KHHK......",
  "....KKCCCCK.....",
  "...KCCACACKK.E..",
  "...KCCCCCCK.EE..",
  "....KCCCCK..E...",
  ".....KCCK.......",
  ".....KSSSSK.....",
  "....KSS..SSK....",
  "...KSS....SSK...",
  "...KK......KK...",
  "................",
  "................",
];

const ATTACK_B = [
  "................",
  "......KKKK......",
  ".....KBBBBK.....",
  "....KBBLLBBK....",
  "....KBBBBBBK....",
  ".....KBBBBK.....",
  "......KHHK......",
  ".....KCCCCKK....",
  "..EE.KCACACCK...",
  "..E..KCCCCCCK...",
  "......KCCCCK....",
  ".......KCCK.....",
  ".....KSSSSK.....",
  "....KSS..SSK....",
  "...KSS....SSK...",
  "...KK......KK...",
  "................",
  "................",
];

const ATTACK_C = [
  "................",
  "......KKKK......",
  ".....KBBBBK.....",
  "....KBBLLBBK....",
  "....KBBBBBBK....",
  ".....KBBBBK.....",
  "...E..KHHK..E...",
  "...EEKKCCCCKKE..",
  "....KCCACACCK...",
  "....KCCCCCCK....",
  ".....KCCCCK.....",
  "......KCCK......",
  ".....KSSSSK.....",
  "....KSS..SSK....",
  "...KSS....SSK...",
  "...KK......KK...",
  "................",
  "................",
];

const DEFEND_A = [
  "................",
  "......KKKK......",
  ".....KBBBBK.....",
  "....KBBBBBBK....",
  "....KLLBBLLK....",
  "....KBBBBBBK....",
  ".....KBBBBK.....",
  "......KHHK......",
  "...KKKCCCCKKK...",
  "..KCCCCACCCCCK..",
  "..KCCCCCCCCCCK..",
  "...KCCCCCCCCK...",
  "....KCCCCCCK....",
  "...E.KSSSSK.E...",
  "..E.KSS..SSK.E..",
  "....KK....KK....",
  "................",
  "................",
];

const DEFEND_B = [
  "................",
  ".....EKKKKE.....",
  "....EKBBBBKE....",
  "...EKBWBBWBKE...",
  "...EKBBBBBBKE...",
  "....EKBBBBKE....",
  ".....EKHHKE.....",
  "...KKKCCCCKKK...",
  "..KCCCCACCCCCK..",
  "..KCCCCCCCCCCK..",
  "...KCCCCCCCCK...",
  "....KCCCCCCK....",
  ".....KSSSSK.....",
  "...E.KSSSSK.E...",
  "..E.KSS..SSK.E..",
  "....KK....KK....",
  "................",
  "................",
];

const INFECTED_A = [
  "................",
  "......KKKK......",
  ".....KBBBBK.....",
  "....KBRBBRBK....",
  "....KBBBBBBK....",
  ".....KBBBBK.....",
  "...R..KHHK..R...",
  "....KKCCCCKK....",
  "...KCRACARCK...",
  "...KCCCCCCCCK...",
  "....KCCRCCK.....",
  ".....KCCCCK.....",
  ".....KSSSSK.R...",
  "....KSS..SSK....",
  "...KSS....SSK...",
  "...KK......KK...",
  "................",
  "................",
];

const INFECTED_B = [
  "................",
  "......KKKK......",
  ".....KBBBBK.....",
  "....KBRBBRBK....",
  "....KBBRRBBK....",
  ".....KBBBBK.....",
  "......KHHK.R....",
  "....KKCCCCKK....",
  "...KCCACACCK...",
  "...KCRCCCCRCK...",
  "....KCCCCCK.R...",
  "...R.KCCCCK.....",
  ".....KSSSSK.....",
  "....KSS..SSK....",
  "...KSS....SSK...",
  "...KK......KK...",
  "................",
  "................",
];

const GUARDIAN_DEFEND_A = [
  ".....GGGGGG.....",
  "...GG.KKKK.GG...",
  "..G..KBBBBK..G..",
  ".G..KBBBBBBK..G.",
  ".G..KLLBBLLK..G.",
  ".G..KBBBBBBK..G.",
  ".G...KBBBBK...G.",
  ".G....KHHK....G.",
  ".G..KKCCCCKK..G.",
  ".G.KCCACACCK.G..",
  ".G.KCCCCCCCCK.G.",
  ".G..KCCCCCCK..G.",
  ".G...KCCCCK...G.",
  ".G...KSSSSK...G.",
  "..G.KSS..SSK.G..",
  "...GKK....KKG...",
  ".....GGGGGG.....",
  "................",
];

const GUARDIAN_DEFEND_B = [
  "....GGGGGGGG....",
  "..GG..KKKK..GG..",
  ".G...KBBBBK...G.",
  "G...KBBWWBBK...G",
  "G...KBBBBBBK...G",
  "G....KBBBBK....G",
  "G.....KHHK.....G",
  "G..KKKCCCCKKK..G",
  "G.KCCCCACCCCCK.G",
  "G.KCCCCCCCCCCK.G",
  "G..KCCCCCCCCK..G",
  "G...KCCCCCCK...G",
  "G....KSSSSK....G",
  ".G...KSSSSK...G.",
  "..G.KSS..SSK.G..",
  "...GKK....KKG...",
  "....GGGGGGGG....",
  "................",
];

function tintPalette(colors) {
  return {
    ...BASE_PALETTE,
    B: colors.primary,
    C: colors.suit,
    A: colors.accent,
    H: colors.skin,
    E: colors.energy,
    G: colors.shield || colors.energy,
  };
}

export function makeAgentSprites(colors) {
  const palette = tintPalette(colors);
  const defendRows = colors.shield
    ? [GUARDIAN_DEFEND_A, GUARDIAN_DEFEND_B]
    : [DEFEND_A, DEFEND_B];
  const fromRows = (rows) => frameFromKeys(normalizeRows(rows), palette);
  const frames = {
    idle: [IDLE_A, IDLE_B].map(fromRows),
    attack: [ATTACK_A, ATTACK_B, ATTACK_C].map(fromRows),
    defend: defendRows.map(fromRows),
    infected: [INFECTED_A, INFECTED_B].map(fromRows),
  };

  return normalizeAnimationSet(frames, frames.idle[0]);
}

function normalizeRows(rows) {
  const width = Math.max(...rows.map((row) => row.length));
  return rows.map((row) => row.padEnd(width, "."));
}
