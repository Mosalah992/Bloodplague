/**
 * Epidemic Lab — pixel-art sprite definitions for all five agent archetypes.
 *
 * Each sprite set has four animation modes: idle, attack, defend, infected.
 * Frames are 16×18 character grids where each character maps to a palette color
 * and "." / " " = transparent.
 *
 * Epidemic Lab character IDs (AI-generated PNGs — see pixelLabManifest.js):
 *   GUARDIAN     3126d12d-be8d-4906-affe-9c028e9f810c
 *   VECTOR       97d5c6df-d98e-4406-84aa-0b5895f2152b
 *   SENTINEL     fdf98dd0-8c9b-4d9a-b221-d9acf3a93e46
 *   EXPLOIT      e389150e-4d72-4c9f-b752-e3bd77193099
 *   PATIENT_ZERO d9f17d87-0df9-4842-a9dd-9656d95f3c28
 *
 * Fallback tileset (cyber-office floor / infected floor):
 *   2660de70-d5c2-4a88-9d56-c68611cf8c82
 */

import { frameFromKeys, normalizeAnimationSet } from "./spriteUtils.js";

// ── Shared helpers ────────────────────────────────────────────────────────────

function build(rows, palette) {
  const maxW = Math.max(...rows.map((r) => r.length));
  const padded = rows.map((r) => r.padEnd(maxW, "."));
  return frameFromKeys(padded, palette);
}

// ── 1. GUARDIAN — Ice-blue crystal knight ────────────────────────────────────
// Palette: #0d47a1 outline, #1a3a5c dark armor, #4fc3f7 mid blue,
//          #b3e5fc highlight, #ffffff specular, #40c4ff cyan shield/glow

const GUARDIAN_PAL = {
  K: "#0d47a1", D: "#1a3a5c", M: "#4fc3f7",
  H: "#b3e5fc", W: "#ffffff", C: "#40c4ff", ".": null,
};

// Idle A — shield at rest, visor glowing
const G_IDLE_A = [
  "................",
  ".....KKKKK......",
  "....KHHHHHK.....",
  "...KHDDDDHK.....",
  "...KHWWWWHK.....",   // visor slit (W=specular white)
  "...KHDDDDHK.....",
  "....KHHHHHK.....",
  ".....KMMK.......",
  "...KKMMMMMKK....",
  "..KMMMDDDMMMK...",
  "..KMMMDDDDMMK...",
  "...KMMMDDMMK....",
  "....KMMMMMK.....",
  "....KCCCCKK.....", // shield glow at base
  "...KCCCCCCK.....",
  "...KCCCCCCK.....",
  "....KMMMMK......",
  "................",
];

// Idle B — shield pulses (cyan brightens slightly, visor dims)
const G_IDLE_B = [
  "................",
  ".....KKKKK......",
  "....KHMMMHK.....",
  "...KHMDDMHK.....",
  "...KHDDDDHK.....", // visor slightly dimmer
  "...KHMDDMHK.....",
  "....KHMMMHK.....",
  ".....KMMK.......",
  "...KKMMMMMKK....",
  "..KMMMCCCMMMK...",  // shield energy charging (C=cyan)
  "..KMMMCCCMMMK...",
  "...KMMMCMMK.....",
  "....KMMMMMK.....",
  "....KCCCCKK.....",
  "...KCCCCCCCK....",
  "...KCCCCCCCK....",
  "....KMMMMK......",
  "................",
];

// Attack — shield thrust forward
const G_ATTACK_A = [
  "................",
  ".....KKKKK......",
  "....KHHHHHK.....",
  "...KHDDDDHK.....",
  "...KHWWWWHK.....",
  "...KHDDDDHK.....",
  "....KHHHHHK.....",
  ".....KMMK.......",
  "..KKMMMMMKK.....",
  ".KMMMMDDMMMMK...",  // shield thrust wider
  ".KMMMCCCCCMMK...",
  "..KMMCCCCCMK....",
  "...KMMMCMMK.....",
  "....KCCCCKK.....",
  "...KCCCCCCK.....",
  "...KCCCCCCK.....",
  "....KMMMMK......",
  "................",
];

// Defend — full shield raise (matches visual: knight braces)
const G_DEFEND_A = [
  "...CCCCCCCC.....",  // cyan aura top
  "..CKKKKKKKKC....",
  ".CKHHHHHHHHHKC..",
  "CKHDDDDDDDDDHKC.",
  "CKHWWWWWWWWWHKC.", // wide visor in defend
  "CKHDDDDDDDDDHKC.",
  ".CKHHHHHHHHHKC..",
  "..CKKMMMMMKKC...",
  "..CMMMMDDDMMMC..",
  "...CMMMDDDMMMC..",
  "...CMMMDDDMMC...",
  "....CMMMMMMC....",
  "....CCCCCCCC....",
  "....KCCCCKK.....",
  "...KCCCCCCK.....",
  "...KCCCCCCK.....",
  "....KMMMMK......",
  "................",
];

// Infected — shield cracked, glow shifts to sickly green
const SICKLY = "#76ff03";
const G_INFECTED_A = [
  "................",
  ".....KKKKK......",
  "....KHHHHHK.....",
  "...KHDDDDHK.....",
  "...KHGGGGHK.....", // visor = sickly green G
  "...KHDDDDHK.....",
  "....KHHHHHK.....",
  ".....KMMK.......",
  "...KKMMMMMKK....",
  "..KMMMDDDMMMK...",
  "..KMGMDDDDMMK...", // green crack
  "...KMMMDGMK.....",
  "....KMMMMMK.....",
  "....KGGGCKK.....", // shield corrupting
  "...KGGGGCCCК....",
  "...KCCCCCCK.....",
  "....KMMMMK......",
  "................",
];
const G_INFECTED_B = [
  "................",
  ".....KKKKK......",
  "....KHHHHHK.....",
  "...KHGDGGHK.....",
  "...KHGGGGGHK....",
  "...KHDDDDHK.....",
  "....KHHHHHK.....",
  ".....KMMK.......",
  "...KKMMMMMKK....",
  "..KMMMDDGMMMK...",
  "..KGMMDGDDMMK...",
  "...KGMMDDMK.....",
  "....KMGMMMK.....",
  "....KGGGCKK.....",
  "...KGGGGGCCK....",
  "...KGGGGCCK.....",
  "....KMMMMK......",
  "................",
];

const GUARDIAN_PAL_INFECTED = { ...GUARDIAN_PAL, G: SICKLY };

function buildGuardian() {
  const p = GUARDIAN_PAL;
  const pi = GUARDIAN_PAL_INFECTED;
  const frames = {
    idle:     [build(G_IDLE_A, p), build(G_IDLE_B, p)],
    attack:   [build(G_ATTACK_A, p), build(G_IDLE_A, p)],
    defend:   [build(G_DEFEND_A, p)],
    infected: [build(G_INFECTED_A, pi), build(G_INFECTED_B, pi)],
  };
  return normalizeAnimationSet(frames, frames.idle[0]);
}

export const guardianSprites = buildGuardian();


// ── 2. VECTOR — Hooded plague doctor ────────────────────────────────────────
// Palette: #1b0033 dark robe, #4a148c mid robe, #7c43bd accent,
//          #ff1744 red eyes, #76ff03 green drip

const VECTOR_PAL = {
  K: "#000000", B: "#1b0033", C: "#4a148c",
  A: "#7c43bd", E: "#ff1744", G: "#76ff03", ".": null,
};

const V_IDLE_A = [
  "................",
  "....KBKKKBK.....",
  "...KBBBBBBBK....",
  "..KBBBBBBBBBK...",
  "...KBBBBBBBK....",
  "...KB..EE..BK...",
  "....KBBBBBBBK...",
  ".....KBBBBBBK...",
  "......KBBBBBK...",
  ".......KBBBBK...",
  "........KBBK....",
  "........KGGK....",   // green drip at beak tip
  "....KKCCCCKK....",
  "...KCCCCCCCK....",
  "...KCCACCCCK....",
  "....KCCCCCK.....",
  "....KCK..KCK....",
  "...KCK....KCK...",
];

const V_IDLE_B = [
  "................",
  "....KBKKKBK.....",
  "...KBBBBBBBK....",
  "..KBBBBBBBBBK...",
  "...KBBBBBBBK....",
  "...KB..EE..BK...",
  "....KBBBBBBBK...",
  ".....KBBBBBBK...",
  "......KBBBBBK...",
  ".......KBBBBK...",
  "........KBBK....",
  ".........KGGK...",  // drip shifted — animation
  "....KKCCCCKK....",
  "...KCCCCCCCK....",
  "...KCCACCCCK....",
  ".....KCCCCCK....",  // cloak sways
  ".....KCK.KCK....",
  "....KCK...KCK...",
];

const V_ATTACK_A = [
  "................",
  "....KBKKKBK.....",
  "...KBBBBBBBK....",
  "..KBBBBBBBBBK...",
  "...KBBBBBBBK....",
  "...KB..EE..BK...",
  "....KBBBBBBBK...",
  "....KBBBBBBBBK..",   // beak extends wider
  ".....KBBBBBBBK..",
  "......KBBBBBBK..",
  ".......KBBBBK...",
  ".......KGGGGK...",   // more drip on attack
  "....KKCCCCKK....",
  "..KCCCCCCCCCK...",   // cloak spreads
  "..KCCACCCCCCK...",
  "...KCCCCCCCK....",
  "....KCK..KCK....",
  "...KCK....KCK...",
];

const V_DEFEND_A = [
  "................",
  "....KBKKKBK.....",
  "...KBBBBBBBK....",
  "..KBBBBBBBBBK...",
  "...KBBBBBBBK....",
  "...KB..EE..BK...",
  "...KBBBBBBBBK...",
  "....KBBBBBBBK...",  // hood pulled low
  ".....KBBBBBBK...",
  "......KBBBBBK...",
  ".......KBBBBK...",
  "........KGGK....",
  "....KKCCCCKK....",
  "..KCCCCCCCCCCK..",  // wide cloak wrap
  "..KCCCACCCCCCK..",
  "...KCCCCCCCCCK..",
  "....KCK..KCK....",
  "...KCK....KCK...",
];

const V_INFECTED_A = [
  "................",
  "....KBKKKBK.....",
  "...KBBGBBBBK....",  // green corruption in hat
  "..KBBBBBBBBBK...",
  "...KBBBGBBBK....",
  "...KB..EE..BK...",
  "....KBGBBBBGK...",  // green spreading in hood
  ".....KBBBBBBK...",
  "......KBBBBBK...",
  ".......KBBBBK...",
  "........KBBK....",
  "........KGGK....",
  "....KKGCCCKK....",  // green corruption in cloak
  "...KGCCGCCCK....",
  "...KCCACCGCK....",
  "....KGCCCCK.....",
  "....KCK..KCK....",
  "...KCK....KCK...",
];

const V_INFECTED_B = [
  "................",
  "....KBKKKBK.....",
  "...KBGBBBGBK....",
  "..KBBGBBBGBBK...",
  "...KBBBGBBBK....",
  "...KB..EE..BK...",
  "....KBBBBBBBK...",
  ".....KGBBBGBK...",
  "......KBBBBBK...",
  ".......KBBBBK...",
  "........KGGK....",
  "........KGGGK...",  // drip stream (infected = stream)
  "....KKGGGCKK....",
  "...KGGGCGCCK....",
  "...KGCACGGGK....",
  "....KGGGGGK.....",
  "....KGK..KGK....",
  "...KGK....KGK...",
];

function buildVector() {
  const p = VECTOR_PAL;
  const frames = {
    idle:     [build(V_IDLE_A, p), build(V_IDLE_B, p)],
    attack:   [build(V_ATTACK_A, p), build(V_IDLE_B, p)],
    defend:   [build(V_DEFEND_A, p)],
    infected: [build(V_INFECTED_A, p), build(V_INFECTED_B, p)],
  };
  return normalizeAnimationSet(frames, frames.idle[0]);
}

export const vectorSprites = buildVector();


// ── 3. SENTINEL — Floating cycloptic drone ───────────────────────────────────
// Palette: #37474f hull dark, #78909c hull light, #ff6d00 orange eye,
//          #ff1744 red laser, #40c4ff jet exhaust

const SENTINEL_PAL = {
  K: "#000000", D: "#37474f", M: "#78909c",
  O: "#ff6d00", R: "#ff1744", J: "#40c4ff", ".": null,
};

const S_IDLE_A = [
  "................",
  "......KMMK......",   // antenna prong
  "......KMMK......",
  ".....KKMMKK.....",   // antenna base
  "....KDDDDDDKK...",
  "...KDDDDDDDDDK..",
  "..KDDDKOOOOKDDDK",  // eye ring
  "..KDDDKOOOOOOKDK",  // big orange eye
  "..KDDDKOOOOKDDrK",  // eye ring + laser pixel R on right
  "...KDDDDDDDDDK..",
  "....KDDDDDDKK...",
  ".....KKDDKK.....",   // jet housing
  "....KJJJJJJK....",
  "...KJJ....JJK...",   // exhaust plume
  "..KJJ......JJK..",
  "................",
  "................",
  "................",
];

const S_IDLE_B = [
  "................",
  "......KMMK......",
  "......KMMK......",
  ".....KKMMKK.....",
  "....KDDDDDDKK...",
  "...KDDDDDDDDDK..",
  "..KRDDkOOOOKDDDK",  // laser on left (R pixel) — sweep
  "..KDDDKOOOOOOKDK",
  "..KDDDKOOOOKDDDK",
  "...KDDDDDDDDDK..",
  "....KDDDDDDKK...",
  ".....KKDDKK.....",
  "....KJJJJJJK....",
  "...KJJ....JJK...",
  "..KJJ......JJK..",
  "................",
  "................",
  "................",
];

const S_ATTACK_A = [
  "................",
  "......KMMK......",
  "......KMMK......",
  ".....KKMMKK.....",
  "....KDDDDDDKK...",
  "...KDDDDDDDDDK..",
  "..KDDDKOOOOKDDDK",
  "..KDDDKOOOOOOKDK",
  "RRRKDDDKOOOOKDDDK",  // laser beam fires left
  "...KDDDDDDDDDK..",
  "....KDDDDDDKK...",
  ".....KKDDKK.....",
  "....KJJJJJJK....",
  "..KJJJ....JJJK..",   // jets flare on attack
  ".KJJ........JJK.",
  "................",
  "................",
  "................",
];

const S_DEFEND_A = [
  "................",
  "......KMMK......",
  "......KMMK......",
  ".....KKMMKK.....",
  "...KDDDDDDDDKK..",   // body hunches/contracts
  "..KDDDDDDDDDDDК.",
  ".KDDDKOOOOOKDDDdk",
  ".KDDDKOOOOOOKDDdk",
  ".KDDDKOOOOOKDDDdk",
  "..KDDDDDDDDDDDК.",
  "...KDDDDDDDDKK..",
  ".....KKDDKK.....",
  "....KJJJJJJK....",
  "...KJJ....JJK...",
  "..KJJ......JJK..",
  "................",
  "................",
  "................",
];

const S_INFECTED_A = [
  "................",
  "......KMMK......",
  "......KMMK......",
  ".....KKMMKK.....",
  "....KGDDDDDKK...",  // green corruption on hull
  "...KGDDDDDDDDDK.",
  "..KDDDKGOOOOKDDK",  // eye flickering with green
  "..KDDDkOGGGGOKDK",
  "..KDDDKOOOOGKDDK",
  "...KGDDDDDDDDK..",
  "....KDDGDDDKK...",
  ".....KKDDKK.....",
  "....KGJJJGJK....",  // jets infected
  "...KJJ....JJK...",
  "..KJJ......JJK..",
  "................",
  "................",
  "................",
];

const S_INFECTED_B = [
  "................",
  "......KMMK......",
  "......KMMK......",
  ".....KKGMKK.....",
  "....KDGDDDGKK...",
  "...KGDDDDDDDDDK.",
  "..KDDDKGGGGKDDDk",
  "..KDDDKGGGGGGKDk",  // eye full green = corrupted
  "..KDDDKGGGGKDdDk",
  "...KGDDGGDDdDk..",
  "....KGDDGDDkk...",
  ".....KKGGKK.....",
  "....KGJJJGJK....",
  "...KGJ....JGK...",
  "..KGJ......JGK..",
  "................",
  "................",
  "................",
];

function buildSentinel() {
  const p = SENTINEL_PAL;
  const frames = {
    idle:     [build(S_IDLE_A, p), build(S_IDLE_B, p)],
    attack:   [build(S_ATTACK_A, p), build(S_IDLE_A, p)],
    defend:   [build(S_DEFEND_A, p)],
    infected: [build(S_INFECTED_A, p), build(S_INFECTED_B, p)],
  };
  return normalizeAnimationSet(frames, frames.idle[0]);
}

export const sentinelDroneSprites = buildSentinel();


// ── 4. EXPLOIT — Skeletal hacker ────────────────────────────────────────────
// Palette: #000000 hoodie black, #212121 hoodie detail, #e0e0e0 bone skull,
//          #ff9100 jaw glow, #00e5ff holographic keyboard

const EXPLOIT_PAL = {
  K: "#0a0a0a", B: "#000000", S: "#212121",
  L: "#e0e0e0", O: "#ff9100", J: "#00e5ff", ".": null,
};

const E_IDLE_A = [
  "................",
  ".....KKKKKKK....",
  "....KBBBBBBBBK..",
  "...KBBBBBBBBBBK.",
  "...KBBLLLLLBBK..",   // skull top
  "..KBBLK..KLBBK..",   // eye sockets
  "..KBBLLLLLLBBK..",   // skull face
  "..KBBLOOOOOLBBK.",   // jaw glow (O=orange)
  "...KBBOOOOOBBK..",
  "....KBBBBBBK....",   // neck/collar
  "....KBBSBBSBBK..",  // binary pattern (S=detail)
  "...KBBSSSSSBBK..",
  "..KJJJJJJJJJK...",  // holographic keyboard (J=cyan)
  ".KJJJJJJJJJJJK..",  // keyboard wide
  "....KBBBBBBK....",
  "....KBB..BBK....",
  "...KBK....KBK...",
  "................",
];

const E_IDLE_B = [
  "................",
  ".....KKKKKKK....",
  "....KBBBBBBBBK..",
  "...KBBBBBBBBBBK.",
  "...KBBLLLLLBBK..",
  "..KBBLK..KLBBK..",
  "..KBBLLLLLLBBK..",
  "..KBBLOOOOOLBBK.",   // jaw glows same
  "...KBBOOOOOBBK..",
  "....KBBBBBBK....",
  "...KBBSSBBSBBK..",  // binary pattern shifts
  "...KBBSSSSSBBK..",
  "...KJJJJJJJJK...",  // keyboard slight offset (typing!)
  "..KJJJJJJJJJJJK.",
  "....KBBBBBBK....",
  "....KBB..BBK....",
  "...KBK....KBK...",
  "................",
];

const E_ATTACK_A = [
  "................",
  ".....KKKKKKK....",
  "....KBBBBBBBBK..",
  "...KBBBBBBBBBBK.",
  "...KBBLLLLLBBK..",
  "..KBBLK..KLBBK..",
  "..KBBLLLLLLBBK..",
  "..KBBLOOOOOLBBK.",
  "...KBBOOOOOBBK..",
  "....KBBBBBBK....",
  "...KBBSBBSBBK...",
  ".JJKBBSSSSSBBK..",  // keyboard thrown (J pixels flying)
  ".JJJJJJJJJJJK...",
  "JJJJJJJJJJJJJK..",  // keyboard explodes outward
  "....KBBBBBBK....",
  "....KBB..BBK....",
  "...KBK....KBK...",
  "................",
];

const E_DEFEND_A = [
  "................",
  ".....KKKKKKK....",
  "....KBBBBBBBBK..",
  "...KBBBBBBBBBBK.",
  "...KBBLLLLLBBK..",
  "..KBBLK..KLBBK..",
  "..KBBLLLLLLBBK..",
  "..KBBLOOOOOOLBK.",
  "...KBOOOOOOOBBK.",
  "....KBBBBBBK....",
  "...KJJJJJJJJK...",  // keyboard held as shield
  "..KJJJJJJJJJJK..",
  "..KJJJJJJJJJJK..",
  "...KJJJJJJJJK...",
  "....KBBBBBBK....",
  "....KBB..BBK....",
  "...KBK....KBK...",
  "................",
];

const E_INFECTED_A = [
  "................",
  ".....KKKKKKK....",
  "....KBBBBBBBBK..",
  "...KBBBBBBBBBBK.",
  "...KBBLLLLLBBK..",
  "..KBBLK..KLBBK..",
  "..KBBLLLLLLBBK..",
  "..KBBLGGGGGLLBK.",   // jaw corruption = green
  "...KBBGGGGGBbK..",
  "....KBBBBBBK....",
  "....KBBSBBSBBK..",
  "...KGGSSSSSBBK..",   // green spreading through hoodie
  "..KGJGJGJGJJK...",  // keyboard glitches
  ".KGGJGJGJGJJJJK.",
  "....KBBBBBBK....",
  "....KGB..GBK....",
  "...KGK....KGK...",
  "................",
];

const EXPLOIT_INF_PAL = { ...EXPLOIT_PAL, G: "#76ff03" };

const E_INFECTED_B = [
  "................",
  ".....KKKKKKK....",
  "....KBBBBBBBBK..",
  "...KGBGBGBGBBBK.",
  "...KBBLLLLLBBK..",
  "..KBBLK..KLBBK..",
  "..KBGLLLLLLBBK..",
  "..KBBLGGGGGLLBK.",
  "...KGGGGGGGBbK..",
  "....KGGGGGGK....",
  "....KBBSBBSBBK..",
  "...KGGSGSSSBGK..",
  "..KGGGGGGGGGGK..",
  ".KGGGGGGGGGGGGK.",
  "....KBBBBBBK....",
  "....KGB..GBK....",
  "...KGK....KGK...",
  "................",
];

function buildExploit() {
  const pi = EXPLOIT_INF_PAL;
  const frames = {
    idle:     [build(E_IDLE_A, EXPLOIT_PAL), build(E_IDLE_B, EXPLOIT_PAL)],
    attack:   [build(E_ATTACK_A, EXPLOIT_PAL), build(E_IDLE_B, EXPLOIT_PAL)],
    defend:   [build(E_DEFEND_A, EXPLOIT_PAL)],
    infected: [build(E_INFECTED_A, pi), build(E_INFECTED_B, pi)],
  };
  return normalizeAnimationSet(frames, frames.idle[0]);
}

export const exploitSprites = buildExploit();


// ── 5. PATIENT_ZERO — Biohazard container on spider legs ─────────────────────
// Palette: #76ff03 bright mist, #1b5e20 dark green, #ffd600 biohazard yellow,
//          #455a64 metal legs, #c8e6c9 glass canister

const PZERO_PAL = {
  K: "#000000", G: "#76ff03", D: "#1b5e20",
  Y: "#ffd600", M: "#455a64", C: "#c8e6c9", ".": null,
};

const P_IDLE_A = [
  "......GGGG......",   // mist rising
  ".....GGGGGG.....",
  "....GGGGGGGG....",
  "....KCCCCCCCK...",   // canister top
  "...KCCGGGGGGCCK.",
  "...KCGG.YYY.GCK.",   // biohazard trefoil top
  "...KCGGY.Y.YGCK.",   // biohazard middle
  "...KCGG.YYY.GCK.",   // biohazard bottom
  "...KCCGGGGGGCCK.",
  "....KCCCCCCCK...",   // canister base
  ".....KKKKKK.....",   // base plate
  ".....KMMMMK.....",   // leg root
  "...KMK....KMK...",   // spider leg joint
  "..KMK......KMK..",   // leg mid
  ".KMK........KMK.",   // leg extended
  "KMK..........KMK",   // foot
  "................",
  "................",
];

const P_IDLE_B = [
  ".......GGG......",   // mist drifts (offset)
  "......GGGGG.....",
  ".....GGGGGGGGG..",
  "....KCCCCCCCK...",
  "...KCCGGGGGGCCK.",
  "...KCGG.YYY.GCK.",
  "...KCGGY.Y.YGCK.",
  "...KCGG.YYY.GCK.",
  "...KCCGGGGGGCCK.",
  "....KCCCCCCCK...",
  ".....KKKKKK.....",
  ".....KMMMMK.....",
  "...KMK....KMK...",
  "..KMK......KMK..",
  "..KMK......KMK..",   // leg twitches
  ".KMK........KMK.",
  "................",
  "................",
];

const P_ATTACK_A = [
  "......GGGG......",
  ".....GGGGGG.....",
  "GGGGGGGGGGGGGGGG",   // mist erupts on attack
  "....KCCCCCCCK...",
  "...KCCGGGGGGCCK.",
  "...KCGG.YYY.GCK.",
  "...KCGGY.Y.YGCK.",
  "...KCGG.YYY.GCK.",
  "...KCCGGGGGGCCK.",
  "....KCCCCCCCK...",
  ".....KKKKKK.....",
  "....KMMMMMMMK...",  // legs spread for lunge
  "..KMK......KMK..",
  ".KMK........KMK.",
  "KMK..........KMK",
  "K............KMK",
  "................",
  "................",
];

const P_DEFEND_A = [
  "................",   // hunker — mist pulled in
  "......GG........",
  ".....GGGG.......",
  "....KCCCCCCCK...",
  "...KCCGGGGGGCCK.",
  "...KCGG.YYY.GCK.",
  "...KCGGY.Y.YGCK.",
  "...KCGG.YYY.GCK.",
  "...KCCGGGGGGCCK.",
  "....KCCCCCCCK...",
  ".....KKKKKK.....",
  "....KMMMMMMK....",
  "....KMK..KMK....",  // legs folded inward
  "...KMK....KMK...",
  "...KMK....KMK...",
  "...KK......KK...",
  "................",
  "................",
];

const P_INFECTED_A = [
  "GGGGGGGGGGGGGGGG",   // mist erupts everywhere
  "GGGGGGGGGGGGGGGG",
  "....GGGGGGGG....",
  "....KGCGCGCK....",   // canister cracking with G corruption
  "...KGGGGGGGGCCK.",
  "...KCGG.GGG.GCK.",
  "...KCGGG.G.GGCK.",
  "...KCGG.GGG.GCK.",
  "...KGGGGGGGGCGK.",
  "....KGCGCGCK....",
  ".....KKKKKK.....",
  ".....KMMMMK.....",
  "...KMK....KMK...",
  "..KMK......KMK..",
  ".KMK........KMK.",
  "KMK..........KMK",
  "................",
  "................",
];

const P_INFECTED_B = [
  "GGGGGGGGGGGGGGGG",
  ".GGGGGGGGGGGGGG.",
  "....GGGGGGGG....",
  "....KGGGGGGGK...",  // canister fully corrupted
  "...KGGGGGGGGGCK.",
  "...KGGG.GGG.GGK.",
  "...KGGGG.G.GGGK.",
  "...KGGG.GGG.GGK.",
  "...KGGGGGGGGGKK.",
  "....KGGGGGGGK...",
  ".....KKKKKK.....",
  ".....KGMGMK.....",
  "...KGK....KGK...",
  "..KGK......KGK..",
  ".KGK........KGK.",
  "KGK..........KGK",
  "................",
  "................",
];

function buildPatientZero() {
  const p = PZERO_PAL;
  const frames = {
    idle:     [build(P_IDLE_A, p), build(P_IDLE_B, p)],
    attack:   [build(P_ATTACK_A, p), build(P_IDLE_A, p)],
    defend:   [build(P_DEFEND_A, p)],
    infected: [build(P_INFECTED_A, p), build(P_INFECTED_B, p)],
  };
  return normalizeAnimationSet(frames, frames.idle[0]);
}

export const patientZeroSprites = buildPatientZero();
