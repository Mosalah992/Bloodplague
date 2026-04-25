#!/usr/bin/env node
/**
 * generate_pixel_furniture.mjs
 *
 * Generates PNG assets for Pixel Lab animated furniture frames and new
 * cyber-ops furniture items. Uses ONLY built-in Node.js (zlib + fs).
 *
 * Run: node scripts/generate_pixel_furniture.mjs
 *
 * Outputs:
 *   frontend/public/pixel-assets/furniture/  ← animated frames + new items
 *   frontend/public/pixel-assets/floors/     ← cyber-ops tile sheet
 */

import { deflateSync } from 'zlib';
import { writeFileSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT     = join(__dirname, '..');
const FURN_OUT = join(ROOT, 'frontend', 'public', 'pixel-assets', 'furniture');
const FLOOR_OUT = join(ROOT, 'frontend', 'public', 'pixel-assets', 'floors');

mkdirSync(FURN_OUT,  { recursive: true });
mkdirSync(FLOOR_OUT, { recursive: true });

// ─── CRC32 (needed for PNG chunks) ─────────────────────────────────
const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = (c & 1) ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c;
  }
  return t;
})();
function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

// ─── Minimal PNG encoder ────────────────────────────────────────────
function encodePNG(width, height, rgba) {
  const sig  = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width,  0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8; ihdr[9] = 6; // 8-bit RGBA

  const stride = width * 4;
  const raw    = Buffer.alloc(height * (stride + 1));
  for (let y = 0; y < height; y++) {
    raw[y * (stride + 1)] = 0;
    rgba.copy(raw, y * (stride + 1) + 1, y * stride, (y + 1) * stride);
  }
  const idat = deflateSync(raw, { level: 9 });

  function chunk(type, data) {
    const t   = Buffer.from(type, 'ascii');
    const out = Buffer.alloc(4 + 4 + data.length + 4);
    out.writeUInt32BE(data.length, 0);
    t.copy(out, 4);
    data.copy(out, 8);
    out.writeUInt32BE(crc32(Buffer.concat([t, data])), 8 + data.length);
    return out;
  }
  return Buffer.concat([sig, chunk('IHDR', ihdr), chunk('IDAT', idat), chunk('IEND', Buffer.alloc(0))]);
}

// ─── Canvas helpers ─────────────────────────────────────────────────
function makeCanvas(w, h) {
  return { w, h, buf: Buffer.alloc(w * h * 4) };
}
function px(c, x, y, r, g, b, a = 255) {
  if (x < 0 || x >= c.w || y < 0 || y >= c.h) return;
  const i = (y * c.w + x) * 4;
  c.buf[i] = r; c.buf[i+1] = g; c.buf[i+2] = b; c.buf[i+3] = a;
}
function fillRect(c, x, y, w, h, r, g, b, a = 255) {
  for (let dy = 0; dy < h; dy++) for (let dx = 0; dx < w; dx++) px(c, x+dx, y+dy, r,g,b,a);
}
function hline(c, y, x0, x1, r, g, b, a = 255) {
  for (let x = x0; x <= x1; x++) px(c, x, y, r,g,b,a);
}
function vline(c, x, y0, y1, r, g, b, a = 255) {
  for (let y = y0; y <= y1; y++) px(c, x, y, r,g,b,a);
}
function outline(c, x, y, w, h, r, g, b, a = 255) {
  hline(c, y,       x, x+w-1, r,g,b,a);
  hline(c, y+h-1,   x, x+w-1, r,g,b,a);
  vline(c, x,       y, y+h-1, r,g,b,a);
  vline(c, x+w-1,   y, y+h-1, r,g,b,a);
}

// ─── Color helpers ──────────────────────────────────────────────────
function hex(h) {
  const s = h.replace('#', '');
  return [parseInt(s.slice(0,2),16), parseInt(s.slice(2,4),16), parseInt(s.slice(4,6),16)];
}
// Convenient spread-ready color accessor
const C = {
  VOID:  hex('#0a0a0f'),  // outline
  DARK:  hex('#1a1a2e'),  // dark body
  MID:   hex('#16213e'),  // mid dark
  NAVY:  hex('#0f3460'),  // navy
  CYAN:  hex('#00d4ff'),  // cyan active
  TEAL:  hex('#00b4d8'),  // teal
  GREEN: hex('#22c55e'),  // green LED
  AMBER: hex('#f59e0b'),  // amber LED
  RED:   hex('#ef4444'),  // red alert
  WHITE: hex('#f1f5f9'),  // bright
  LGRAY: hex('#94a3b8'),  // light gray
  GRAY:  hex('#374151'),  // dark gray metal
  DGRAY: hex('#1e293b'),  // deep gray
  SEAT:  hex('#1e1b4b'),  // dark indigo seat
  IND:   hex('#3730a3'),  // indigo
  PURP:  hex('#4c1d95'),  // dark purple
  VPURP: hex('#7c3aed'),  // vivid purple
  YELLOW:hex('#fef08a'),  // yellow sticky
  MINT:  hex('#bbf7d0'),  // light green sticky
  MESH:  hex('#1e3a5f'),  // blue mesh back
  CBLU:  hex('#0369a1'),  // bright blue screen
  ERED:  hex('#dc2626'),  // bright red
  CORK:  hex('#c2976b'),  // corkboard beige
  Dcork: hex('#a37a4c'),  // dark cork
  PINE:  hex('#2d4a1e'),  // dark pin head
  STRING:hex('#c9413e'),  // red string
  NCARD: hex('#e2e8f0'),  // note card white
  MCARD: hex('#cbd5e1'),  // card shadow
  RPIN:  hex('#dc2626'),  // red push pin
  BPIN:  hex('#1d4ed8'),  // blue push pin
  GPAT:  hex('#1e3a5f'),  // metal grate
  HAZB:  hex('#1c1917'),  // hazard stripe black
  HAZY:  hex('#ca8a04'),  // hazard stripe yellow
  CIRC:  hex('#1e40af'),  // circuit blue
  CIRK:  hex('#0a0a1e'),  // circuit trace dark
  CONC:  hex('#374151'),  // concrete gray
  CONL:  hex('#4b5563'),  // concrete light
  GRID:  hex('#1e40af'),  // grid line cyan-blue
  OBS:   hex('#0f172a'),  // obsidian
  OREF:  hex('#1e3a5f'),  // obsidian reflection
};

function save(filename, canvas, outDir = FURN_OUT) {
  writeFileSync(join(outDir, filename), encodePNG(canvas.w, canvas.h, canvas.buf));
  console.log(`  ✓  ${filename}  (${canvas.w}×${canvas.h})`);
}

// ═══════════════════════════════════════════════════════════════════
// SECTION 1 — SERVER RACK ANIMATION FRAMES (32×32)
// ═══════════════════════════════════════════════════════════════════

function makeServerRack(frameIndex) {
  const g = makeCanvas(32, 32);
  // Body
  fillRect(g, 0, 0, 32, 32, ...C.DARK);
  // Side trim
  fillRect(g, 0,  0, 2, 32, ...C.GRAY);
  fillRect(g, 30, 0, 2, 32, ...C.GRAY);
  // Outline
  outline(g, 0, 0, 32, 32, ...C.VOID);

  // Draw 7 rack units (each 4px tall)
  for (let unit = 0; unit < 7; unit++) {
    const y0 = 1 + unit * 4;

    // Rack unit separator line
    if (unit > 0) hline(g, y0 - 1, 2, 29, ...C.GRAY);

    // Drive bay slots (small dark rects)
    fillRect(g, 3, y0, 16, 3, ...C.MID);
    outline(g, 3, y0, 16, 3, ...C.DGRAY);

    // Power button (tiny)
    fillRect(g, 21, y0, 2, 2, ...C.DGRAY);

    // LED cluster (3 small LEDs at right)
    const ledColors = getLedColors(frameIndex, unit);
    for (let li = 0; li < 3; li++) {
      px(g, 25 + li, y0 + 1, ...ledColors[li]);
    }
  }

  // Bottom row: power LED + label area
  hline(g, 29, 2, 29, ...C.GRAY);
  px(g, 4, 30, ...C.GREEN);
  fillRect(g, 7, 30, 18, 1, ...C.MID);

  return g;
}

function getLedColors(frame, unit) {
  if (frame === 0) {
    // All green/healthy
    const patterns = [
      [C.GREEN, C.GREEN, C.GREEN],
      [C.GREEN, C.GREEN, C.AMBER],
      [C.GREEN, C.GREEN, C.GREEN],
      [C.AMBER, C.GREEN, C.GREEN],
      [C.GREEN, C.GREEN, C.GREEN],
      [C.GREEN, C.AMBER, C.GREEN],
      [C.GREEN, C.GREEN, C.GREEN],
    ];
    return patterns[unit];
  } else if (frame === 1) {
    // Warning: red alert on some units
    const patterns = [
      [C.GREEN, C.RED,   C.GREEN],
      [C.RED,   C.GREEN, C.AMBER],
      [C.GREEN, C.RED,   C.GREEN],
      [C.RED,   C.AMBER, C.GREEN],
      [C.GREEN, C.GREEN, C.RED  ],
      [C.RED,   C.GREEN, C.RED  ],
      [C.GREEN, C.RED,   C.AMBER],
    ];
    return patterns[unit];
  } else {
    // Frame 2: cycling/dim — mostly off, few blue
    const patterns = [
      [C.DGRAY, C.CYAN,  C.DGRAY],
      [C.DGRAY, C.DGRAY, C.CYAN ],
      [C.CYAN,  C.DGRAY, C.DGRAY],
      [C.DGRAY, C.CYAN,  C.DGRAY],
      [C.DGRAY, C.DGRAY, C.CYAN ],
      [C.CYAN,  C.DGRAY, C.DGRAY],
      [C.DGRAY, C.CYAN,  C.DGRAY],
    ];
    return patterns[unit];
  }
}

console.log('\n── Server Rack frames ──');
save('server-rack-on-f0.png', makeServerRack(0));
save('server-rack-on-f1.png', makeServerRack(1));
save('server-rack-on-f2.png', makeServerRack(2));

// ═══════════════════════════════════════════════════════════════════
// SECTION 2 — ANALYST PC ANIMATION FRAMES (48×48)
// ═══════════════════════════════════════════════════════════════════

function makeAnalystPC(frameIndex) {
  const g = makeCanvas(48, 48);

  // Desk surface
  fillRect(g, 0, 0, 48, 48, ...C.MID);
  outline(g, 0, 0, 48, 48, ...C.VOID);

  // Desk edge highlight
  hline(g, 1, 1, 46, ...C.NAVY);

  // Left monitor (20×20 at position 2, 8)
  drawMonitor(g, 2, 8, 20, 20, frameIndex, 0);

  // Right monitor (20×20 at position 26, 8)
  drawMonitor(g, 26, 8, 20, 20, frameIndex, 1);

  // Keyboard (between monitors bottom area)
  fillRect(g, 6, 36, 36, 6, ...C.GRAY);
  outline(g, 6, 36, 36, 6, ...C.VOID);
  // Key rows
  for (let row = 0; row < 3; row++) {
    hline(g, 37 + row, 7, 41, ...C.DGRAY);
  }

  // Mouse (small)
  fillRect(g, 42, 38, 4, 5, ...C.GRAY);
  outline(g, 42, 38, 4, 5, ...C.VOID);
  hline(g, 40, 43, 45, ...C.VOID);

  return g;
}

function drawMonitor(g, x, y, w, h, frameIndex, monitorIdx) {
  // Bezel
  fillRect(g, x, y, w, h, ...C.VOID);
  // Screen (2px inset)
  const sx = x + 2, sy = y + 2, sw = w - 4, sh = h - 4;
  fillRect(g, sx, sy, sw, sh, ...C.DARK);

  if (frameIndex === 0) {
    // Frame 0: terminal with green text lines
    const lineColor = monitorIdx === 0 ? C.GREEN : C.CYAN;
    for (let row = 0; row < 5; row++) {
      const lineLen = (row % 2 === 0) ? sw - 3 : sw - 7;
      hline(g, sy + 2 + row * 2, sx + 1, sx + lineLen, ...lineColor);
    }
    // Cursor blink
    fillRect(g, sx + 1, sy + 12, 2, 1, ...C.WHITE);
  } else if (frameIndex === 1) {
    // Frame 1: alert panel — red border + warning text
    outline(g, sx, sy, sw, sh, ...C.RED);
    fillRect(g, sx + 1, sy + 1, sw - 2, 3, ...C.ERED);
    for (let row = 0; row < 4; row++) {
      const lineColor = row % 2 === 0 ? C.RED : C.AMBER;
      hline(g, sy + 6 + row * 2, sx + 2, sx + sw - 3, ...lineColor);
    }
  } else {
    // Frame 2: graph/chart
    const barColor = monitorIdx === 0 ? C.CYAN : C.GREEN;
    // Bar chart
    const bars = [6, 10, 4, 8, 12, 7, 9];
    for (let b = 0; b < bars.length; b++) {
      const barH = Math.min(bars[b], sh - 3);
      const bx   = sx + 1 + b * 2;
      fillRect(g, bx, sy + sh - 2 - barH, 1, barH, ...barColor);
    }
    // Baseline
    hline(g, sy + sh - 2, sx + 1, sx + sw - 2, ...C.LGRAY);
  }
}

console.log('\n── Analyst PC frames ──');
save('analyst-pc-on-f0.png', makeAnalystPC(0));
save('analyst-pc-on-f1.png', makeAnalystPC(1));
save('analyst-pc-on-f2.png', makeAnalystPC(2));

// ═══════════════════════════════════════════════════════════════════
// SECTION 3 — GUARDIAN PC ANIMATION FRAMES (80×64)
// ═══════════════════════════════════════════════════════════════════

function makeGuardianPC(frameIndex) {
  const g = makeCanvas(80, 64);

  // Large workstation desk surface
  fillRect(g, 0, 0, 80, 64, ...C.MID);
  outline(g, 0, 0, 80, 64, ...C.VOID);
  hline(g, 1, 1, 78, ...C.NAVY);

  // Three wide monitors across the top
  // Left monitor (24×22 at x=2, y=4)
  drawGuardianMonitor(g, 2,  4, 24, 22, frameIndex, 0);
  // Center monitor (26×26 at x=28, y=2) — main display, bigger
  drawGuardianMonitor(g, 28, 2, 26, 26, frameIndex, 1);
  // Right monitor (24×22 at x=56, y=4)
  drawGuardianMonitor(g, 56, 4, 24, 22, frameIndex, 2);

  // Control panel strip below monitors
  fillRect(g, 2, 32, 76, 12, ...C.DGRAY);
  outline(g, 2, 32, 76, 12, ...C.VOID);

  // Control panel: status indicators
  for (let i = 0; i < 12; i++) {
    const ledX = 4 + i * 6;
    const col = frameIndex === 1 && i % 3 === 0 ? C.RED :
                frameIndex === 2 ? (i % 2 === 0 ? C.CYAN : C.TEAL) : C.GREEN;
    fillRect(g, ledX, 34, 4, 4, ...col);
    outline(g, ledX, 34, 4, 4, ...C.VOID);
  }

  // Slider / knob row
  hline(g, 40, 4, 75, ...C.GRAY);
  for (let k = 0; k < 6; k++) {
    const kx = 8 + k * 12;
    fillRect(g, kx, 38, 6, 4, ...C.GRAY);
    outline(g, kx, 38, 6, 4, ...C.VOID);
    // Knob position varies by frame
    px(g, kx + (frameIndex % 3) + 1, 39, ...C.CYAN);
  }

  // Wide keyboard at bottom
  fillRect(g, 4, 48, 72, 10, ...C.GRAY);
  outline(g, 4, 48, 72, 10, ...C.VOID);
  for (let row = 0; row < 4; row++) {
    hline(g, 49 + row * 2, 5, 75, ...C.DGRAY);
  }

  return g;
}

function drawGuardianMonitor(g, x, y, w, h, frameIndex, idx) {
  fillRect(g, x, y, w, h, ...C.VOID);
  const sx = x + 2, sy = y + 2, sw = w - 4, sh = h - 4;
  fillRect(g, sx, sy, sw, sh, ...C.DARK);

  if (frameIndex === 0) {
    // Topology graph / network map
    const nodeColor = C.CYAN;
    const edgeColor = C.NAVY;
    if (idx === 1) {
      // Center: full topology
      const nodes = [[sw/2|0, 2], [2, sh-4], [sw-3, sh-4], [2, sh/2|0], [sw-3, 3]];
      for (const [nx, ny] of nodes) {
        fillRect(g, sx+nx-1, sy+ny-1, 2, 2, ...nodeColor);
      }
      for (let i = 0; i < nodes.length - 1; i++) {
        // Simple dot connection (not real line, pixel art)
        const [x1,y1] = nodes[i], [x2,y2] = nodes[i+1];
        px(g, sx + ((x1+x2)/2|0), sy + ((y1+y2)/2|0), ...edgeColor);
      }
    } else {
      // Side monitors: scan lines
      for (let row = 0; row < sh - 1; row += 2) {
        hline(g, sy + row, sx, sx + sw - 1, ...C.NAVY);
      }
      hline(g, sy + 1, sx, sx + sw/2|0, ...C.CYAN);
    }
  } else if (frameIndex === 1) {
    // Alert mode — red screen
    if (idx === 1) {
      // Center: full red alert
      outline(g, sx, sy, sw, sh, ...C.RED);
      fillRect(g, sx+1, sy+1, sw-2, 3, ...C.ERED);
      for (let row = 0; row < 4; row++) {
        hline(g, sy + 6 + row * 2, sx + 1, sx + sw - 2, row % 2 === 0 ? C.RED : C.AMBER);
      }
    } else {
      // Sides: flashing indicators
      fillRect(g, sx, sy, sw, sh, ...C.DARK);
      fillRect(g, sx+1, sy+1, sw-2, 2, ...C.RED);
      for (let row = 0; row < sh/3|0; row++) {
        hline(g, sy+4+row*2, sx+1, sx+sw-2, ...C.AMBER);
      }
    }
  } else {
    // Frame 2: data streams / traffic
    if (idx === 1) {
      // Center: bar chart
      const bars = [sh-5, sh-3, sh-7, sh-4, sh-6, sh-2, sh-8];
      for (let b = 0; b < bars.length; b++) {
        const bx = sx + 1 + b * ((sw-2)/7|0);
        fillRect(g, bx, sy + sh - 1 - bars[b] + (sh-9), 2, bars[b]-(sh-9), ...C.CYAN);
      }
      hline(g, sy + sh - 2, sx, sx + sw - 1, ...C.LGRAY);
    } else {
      // Sides: scrolling text
      for (let row = 0; row < (sh/2)|0; row++) {
        const len = 3 + ((idx + row) % (sw - 4));
        hline(g, sy + row * 2, sx + 1, sx + 1 + len, ...C.TEAL);
      }
    }
  }
}

console.log('\n── Guardian PC frames ──');
save('guardian-pc-on-f0.png', makeGuardianPC(0));
save('guardian-pc-on-f1.png', makeGuardianPC(1));
save('guardian-pc-on-f2.png', makeGuardianPC(2));

// ═══════════════════════════════════════════════════════════════════
// SECTION 4 — DIGITAL CLOCK ANIMATION FRAMES (48×16)
// Seven-segment digit rendering
// ═══════════════════════════════════════════════════════════════════

// Segments: top, top-left, top-right, middle, bot-left, bot-right, bottom
//  _
// | |  →  0=top, 1=top-left, 2=top-right, 3=middle, 4=bot-left, 5=bot-right, 6=bottom
// |_|
//
//  a
// f b
//  g
// e c
//  d
// Index order: [a=top, b=top-right, c=bot-right, d=bottom, e=bot-left, f=top-left, g=middle]
const SEG_DIGITS = {
  //  a      b      c      d      e      f      g(mid)
  0: [true,  true,  true,  true,  true,  true,  false],  // all except middle
  1: [false, true,  true,  false, false, false, false],  // right side only
  2: [true,  true,  false, true,  true,  false, true ],  // top+top-r+mid+bot-l+bot
  3: [true,  true,  true,  true,  false, false, true ],  // all except bot-l and top-l
  4: [false, true,  true,  false, false, true,  true ],  // top-r+bot-r+top-l+mid
  5: [true,  false, true,  true,  false, true,  true ],  // top+bot-r+bot+top-l+mid
  6: [true,  false, true,  true,  true,  true,  true ],  // all except top-right
  7: [true,  true,  true,  false, false, false, false],  // top+top-r+bot-r
  8: [true,  true,  true,  true,  true,  true,  true ],  // all on
  9: [true,  true,  true,  true,  false, true,  true ],  // all except bot-left
};

function drawDigit(g, x, y, digit, color, bgColor) {
  // Draw a 5×9 seven-segment digit
  const [a,b,c,d,e,f,segG] = SEG_DIGITS[digit] || SEG_DIGITS[0];
  const off = C.DARK;
  // top segment
  hline(g, y,     x+1, x+3, ...(a ? color : off));
  // top-left (f)
  vline(g, x,     y+1, y+4, ...(f ? color : off));
  // top-right (b)
  vline(g, x+4,   y+1, y+4, ...(b ? color : off));
  // middle (g)
  hline(g, y+4,   x+1, x+3, ...(segG ? color : off));
  // bot-left (e)
  vline(g, x,     y+5, y+8, ...(e ? color : off));
  // bot-right (c)
  vline(g, x+4,   y+5, y+8, ...(c ? color : off));
  // bottom (d)
  hline(g, y+8,   x+1, x+3, ...(d ? color : off));
}

function makeDigitalClock(timeLabel) {
  // timeLabel e.g. "12:00"
  const g = makeCanvas(48, 16);

  // Panel body
  fillRect(g, 0, 0, 48, 16, ...C.DARK);
  outline(g, 0, 0, 48, 16, ...C.VOID);

  // Inner recessed screen
  fillRect(g, 2, 2, 44, 12, ...C.DGRAY);
  outline(g, 2, 2, 44, 12, ...C.VOID);

  // Brand dots (left)
  for (let i = 0; i < 3; i++) px(g, 1, 6 + i, ...C.CYAN);

  const digits = timeLabel.replace(':', '');
  const [h1, h2, m1, m2] = digits.split('').map(Number);
  const seg = C.CYAN;

  // Digit positions (5px wide each, 1px gap, colon in middle)
  // x offsets: 4, 11, colon at 18-19, 22, 29
  drawDigit(g, 4,  3, h1, seg, C.DGRAY);
  drawDigit(g, 11, 3, h2, seg, C.DGRAY);

  // Colon
  px(g, 19, 6,  ...seg);
  px(g, 19, 9,  ...seg);

  drawDigit(g, 22, 3, m1, seg, C.DGRAY);
  drawDigit(g, 29, 3, m2, seg, C.DGRAY);

  // AM/PM indicator
  fillRect(g, 36, 4, 8, 4, ...C.MID);
  hline(g, 5, 37, 43, ...C.TEAL);
  hline(g, 6, 37, 43, ...C.NAVY);

  return g;
}

console.log('\n── Digital Clock frames ──');
save('digital-clock-on-f0.png', makeDigitalClock('12:00'));
save('digital-clock-on-f1.png', makeDigitalClock('12:15'));
save('digital-clock-on-f2.png', makeDigitalClock('12:30'));
save('digital-clock-on-f3.png', makeDigitalClock('12:45'));

// ═══════════════════════════════════════════════════════════════════
// SECTION 5 — CHAIRS (16×16)
// ═══════════════════════════════════════════════════════════════════

function makeOpsChairFront() {
  const g = makeCanvas(16, 16);
  // Back of chair (top)
  fillRect(g, 2, 1,  12, 5, ...C.MESH);
  outline(g,  2, 1,  12, 5, ...C.VOID);
  // Mesh detail lines on back
  vline(g, 6,  2, 5, ...C.NAVY);
  vline(g, 9,  2, 5, ...C.NAVY);
  vline(g, 12, 2, 5, ...C.NAVY);
  // Armrests
  fillRect(g, 0, 5, 2, 4, ...C.GRAY);
  fillRect(g, 14,5, 2, 4, ...C.GRAY);
  outline(g, 0, 5, 2, 4, ...C.VOID);
  outline(g,14, 5, 2, 4, ...C.VOID);
  // Seat
  fillRect(g, 2, 6, 12, 6, ...C.SEAT);
  outline(g, 2, 6, 12, 6, ...C.VOID);
  // Seat highlight
  hline(g, 7, 3, 13, ...C.IND);
  // Cylinder base
  fillRect(g, 6, 12, 4, 2, ...C.LGRAY);
  outline(g, 6, 12, 4, 2, ...C.VOID);
  // Caster dots
  px(g, 3,  15, ...C.GRAY);
  px(g, 12, 15, ...C.GRAY);
  px(g, 7,  15, ...C.LGRAY);
  px(g, 9,  15, ...C.LGRAY);
  return g;
}

function makeOpsChairSide() {
  const g = makeCanvas(16, 16);
  // Back of chair (left side when viewed from right)
  fillRect(g, 2, 1, 5, 8, ...C.MESH);
  outline(g, 2, 1, 5, 8, ...C.VOID);
  hline(g, 4, 3, 6, ...C.NAVY);
  hline(g, 6, 3, 6, ...C.NAVY);
  // Seat
  fillRect(g, 4, 7, 8, 4, ...C.SEAT);
  outline(g, 4, 7, 8, 4, ...C.VOID);
  hline(g, 8, 5, 11, ...C.IND);
  // Base + casters
  fillRect(g, 6, 11, 3, 2, ...C.LGRAY);
  outline(g, 6, 11, 3, 2, ...C.VOID);
  px(g, 5, 13, ...C.GRAY);
  px(g, 10,13, ...C.GRAY);
  return g;
}

function makeExecChairFront() {
  const g = makeCanvas(16, 16);
  // High back (taller, with head rest)
  fillRect(g, 3, 0, 10, 2, ...C.PURP);   // headrest
  outline(g, 3, 0, 10, 2, ...C.VOID);
  fillRect(g, 2, 2, 12, 4, ...C.PURP);   // back
  outline(g, 2, 2, 12, 4, ...C.VOID);
  // Accent line
  hline(g, 3, 3, 13, ...C.VPURP);
  // Gold armrests
  fillRect(g, 0, 5, 2, 4, ...C.AMBER);
  fillRect(g,14, 5, 2, 4, ...C.AMBER);
  outline(g, 0, 5, 2, 4, ...C.VOID);
  outline(g,14, 5, 2, 4, ...C.VOID);
  // Seat (dark leather)
  fillRect(g, 2, 6, 12, 6, ...C.PURP);
  outline(g, 2, 6, 12, 6, ...C.VOID);
  hline(g, 8, 3, 13, ...C.VPURP);
  // Base
  fillRect(g, 6, 12, 4, 2, ...C.LGRAY);
  outline(g, 6, 12, 4, 2, ...C.VOID);
  px(g, 3,  15, ...C.GRAY);
  px(g, 12, 15, ...C.GRAY);
  return g;
}

function makeExecChairSide() {
  const g = makeCanvas(16, 16);
  // Tall back
  fillRect(g, 2, 0, 5, 10, ...C.PURP);
  outline(g, 2, 0, 5, 10, ...C.VOID);
  vline(g, 4, 1, 8, ...C.VPURP);
  // Seat
  fillRect(g, 4, 7, 8, 4, ...C.PURP);
  outline(g, 4, 7, 8, 4, ...C.VOID);
  // Gold armrest
  fillRect(g, 7, 6, 3, 2, ...C.AMBER);
  outline(g, 7, 6, 3, 2, ...C.VOID);
  // Base
  fillRect(g, 6, 11, 3, 2, ...C.LGRAY);
  outline(g, 6, 11, 3, 2, ...C.VOID);
  px(g, 5, 13, ...C.GRAY);
  px(g, 10,13, ...C.GRAY);
  return g;
}

console.log('\n── Chairs ──');
save('ops-chair-front.png',  makeOpsChairFront());
save('ops-chair-side.png',   makeOpsChairSide());
save('exec-chair-front.png', makeExecChairFront());
save('exec-chair-side.png',  makeExecChairSide());

// ═══════════════════════════════════════════════════════════════════
// SECTION 6 — CABLE BUNDLES
// ═══════════════════════════════════════════════════════════════════

function makeCableBundleH() {
  // 32×16 — horizontal bundle
  const g = makeCanvas(32, 16);
  // Floor transparency — fully transparent outer area
  const y0 = 5, ht = 5;
  fillRect(g, 0, y0, 32, ht, ...C.DARK);
  outline(g, 0, y0, 32, ht, ...C.VOID);
  // Cable lines inside
  hline(g, y0+1, 1, 30, ...C.CYAN);
  hline(g, y0+2, 1, 30, ...C.RED);
  hline(g, y0+3, 1, 30, ...C.TEAL);
  // Cable ties (every 8px)
  for (let x = 4; x < 32; x += 8) {
    vline(g, x, y0, y0+ht-1, ...C.GRAY);
    px(g, x, y0+2, ...C.LGRAY);
  }
  return g;
}

function makeCableBundleV() {
  // 16×32 — vertical bundle
  const g = makeCanvas(16, 32);
  const x0 = 5, wt = 5;
  fillRect(g, x0, 0, wt, 32, ...C.DARK);
  outline(g, x0, 0, wt, 32, ...C.VOID);
  // Cable lines
  vline(g, x0+1, 1, 30, ...C.CYAN);
  vline(g, x0+2, 1, 30, ...C.RED);
  vline(g, x0+3, 1, 30, ...C.TEAL);
  // Cable ties
  for (let y = 4; y < 32; y += 8) {
    hline(g, y, x0, x0+wt-1, ...C.GRAY);
    px(g, x0+2, y, ...C.LGRAY);
  }
  return g;
}

console.log('\n── Cable bundles ──');
save('cable-bundle-h.png', makeCableBundleH());
save('cable-bundle-v.png', makeCableBundleV());

// ═══════════════════════════════════════════════════════════════════
// SECTION 7 — PATCH PANEL (48×16)
// ═══════════════════════════════════════════════════════════════════

function makePatchPanel() {
  const g = makeCanvas(48, 16);
  fillRect(g, 0, 0, 48, 16, ...C.GRAY);
  outline(g, 0, 0, 48, 16, ...C.VOID);

  // Label area (top strip)
  fillRect(g, 1, 1, 46, 3, ...C.DGRAY);
  hline(g, 2, 2, 45, ...C.LGRAY);

  // 12 patch ports in two rows of 6
  const portColors = [C.CYAN, C.GREEN, C.AMBER, C.RED, C.CYAN, C.TEAL,
                      C.GREEN, C.CYAN, C.TEAL,  C.GREEN, C.AMBER, C.CYAN];
  for (let i = 0; i < 12; i++) {
    const col = i % 6;
    const row = Math.floor(i / 6);
    const px0 = 2 + col * 8, py0 = 5 + row * 5;
    // Port housing
    fillRect(g, px0, py0, 6, 4, ...C.DARK);
    outline(g, px0, py0, 6, 4, ...C.VOID);
    // Port hole
    fillRect(g, px0+1, py0+1, 4, 2, ...C.DGRAY);
    // Cable color indicator
    px(g, px0+2, py0+1, ...portColors[i]);
    px(g, px0+3, py0+1, ...portColors[i]);
  }

  return g;
}

console.log('\n── Patch panel ──');
save('patch-panel.png', makePatchPanel());

// ═══════════════════════════════════════════════════════════════════
// SECTION 8 — EVIDENCE BOARD (48×32)
// ═══════════════════════════════════════════════════════════════════

function makeEvidenceBoard() {
  const g = makeCanvas(48, 32);

  // Dark wooden frame
  fillRect(g, 0, 0, 48, 32, ...C.VOID);
  // Cork surface
  fillRect(g, 2, 2, 44, 28, ...C.CORK);
  // Cork texture (darker patches)
  for (let y = 3; y < 30; y += 4) {
    for (let x = 3; x < 46; x += 5) {
      px(g, x, y, ...C.DORK);
    }
  }

  // Note cards (white rectangles with pinned corners)
  // Card 1 (left)
  fillRect(g, 4,  4,  12, 9, ...C.NCARD);
  outline(g, 4,  4,  12, 9, ...C.VOID);
  hline(g, 6,  5, 14, ...C.MCARD);
  hline(g, 8,  5, 14, ...C.MCARD);
  hline(g, 10, 5, 14, ...C.MCARD);
  px(g, 5, 4, ...C.RPIN);   // red pin

  // Card 2 (right)
  fillRect(g, 30, 4,  12, 9, ...C.NCARD);
  outline(g, 30, 4,  12, 9, ...C.VOID);
  hline(g, 6,  31, 41, ...C.MCARD);
  hline(g, 8,  31, 41, ...C.MCARD);
  hline(g, 10, 31, 41, ...C.MCARD);
  px(g, 40, 4, ...C.BPIN);  // blue pin

  // Card 3 (center bottom)
  fillRect(g, 17, 18, 14, 9, ...C.YELLOW);
  outline(g, 17, 18, 14, 9, ...C.VOID);
  hline(g, 20, 18, 30, ...C.AMBER);
  hline(g, 22, 18, 30, ...C.AMBER);
  hline(g, 24, 18, 30, ...C.AMBER);
  px(g, 23, 18, ...C.RPIN);

  // Red string connecting pins
  // From card1 pin (5,4) to card3 pin (23,18)
  for (let t = 0; t <= 8; t++) {
    const sx = 5  + Math.round(t * (23-5)/8);
    const sy = 4  + Math.round(t * (18-4)/8);
    px(g, sx, sy, ...C.STRING);
  }
  // From card2 pin (40,4) to card3 pin (23,18)
  for (let t = 0; t <= 8; t++) {
    const sx = 40 + Math.round(t * (23-40)/8);
    const sy = 4  + Math.round(t * (18-4)/8);
    px(g, sx, sy, ...C.STRING);
  }

  // A few loose pins
  px(g, 12, 18, ...C.BPIN);
  px(g, 36, 20, ...C.RPIN);
  px(g, 22, 9,  ...C.RPIN);

  // Biohazard network diagram (faint pencil lines)
  hline(g, 14, 5, 43, ...C.DORK);
  vline(g, 24, 4, 17, ...C.DORK);

  return g;
}

// Fix: DORK is not in C, use DORK as DORK color
const C_DORK = hex('#8b6448');

function makeEvidenceBoardFix() {
  const g = makeCanvas(48, 32);

  fillRect(g, 0, 0, 48, 32, ...C.VOID);
  fillRect(g, 2, 2, 44, 28, ...C.CORK);

  // Cork texture
  for (let y = 3; y < 30; y += 4) {
    for (let x = 3; x < 46; x += 5) {
      px(g, x, y, ...C_DORK);
    }
  }

  // Card 1
  fillRect(g, 4,  4,  12, 9, ...C.NCARD);
  outline(g, 4,  4,  12, 9, ...C.VOID);
  for (let r = 0; r < 3; r++) hline(g, 6+r*2, 5, 14, ...C.MCARD);
  px(g, 5, 4, ...C.RPIN);

  // Card 2
  fillRect(g, 30, 4,  12, 9, ...C.NCARD);
  outline(g, 30, 4,  12, 9, ...C.VOID);
  for (let r = 0; r < 3; r++) hline(g, 6+r*2, 31, 41, ...C.MCARD);
  px(g, 40, 4, ...C.BPIN);

  // Sticky note card 3
  fillRect(g, 17, 18, 14, 9, ...C.YELLOW);
  outline(g, 17, 18, 14, 9, ...C.VOID);
  for (let r = 0; r < 3; r++) hline(g, 20+r*2, 18, 30, ...C.AMBER);
  px(g, 23, 18, ...C.RPIN);

  // Red strings
  for (let t = 0; t <= 8; t++) {
    px(g, 5  + Math.round(t*(23-5)/8), 4  + Math.round(t*(18-4)/8), ...C.STRING);
    px(g, 40 + Math.round(t*(23-40)/8), 4 + Math.round(t*(18-4)/8), ...C.STRING);
  }

  // Loose pins
  px(g, 12, 18, ...C.BPIN);
  px(g, 36, 20, ...C.RPIN);

  // Faint diagram lines
  for (let x = 5; x < 43; x++) px(g, x, 14, ...C_DORK);
  for (let y = 4; y < 17; y++) px(g, 24, y, ...C_DORK);

  return g;
}

console.log('\n── Evidence board ──');
save('evidence-board.png', makeEvidenceBoardFix());

// ═══════════════════════════════════════════════════════════════════
// SECTION 9 — STICKY NOTES (16×16)
// ═══════════════════════════════════════════════════════════════════

function makeStickyNotes() {
  const g = makeCanvas(16, 16);

  // Bottom note (slightly offset/shadow)
  fillRect(g, 2, 2, 11, 9, ...C.MINT);
  outline(g, 2, 2, 11, 9, ...C.VOID);

  // Top note (yellow)
  fillRect(g, 4, 4, 11, 9, ...C.YELLOW);
  outline(g, 4, 4, 11, 9, ...C.VOID);
  // Note lines
  hline(g, 6,  5, 14, ...C.AMBER);
  hline(g, 8,  5, 14, ...C.AMBER);
  hline(g, 10, 5, 14, ...C.AMBER);

  // Small pin dot
  px(g, 9, 4, ...C.RPIN);

  return g;
}

console.log('\n── Sticky notes ──');
save('sticky-notes.png', makeStickyNotes());

// ═══════════════════════════════════════════════════════════════════
// SECTION 10 — FLOOR TILES (4 × 16×16 grayscale patterns)
//
// The floor tile system (floorTiles.ts) expects individual 16×16
// grayscale PNGs. The colorize pass maps luminance → room HSL color,
// so these tiles must encode structure as light/dark, not as color.
//
// Luminance guide:
//   0x10-0x20 = very dark (near-black floor base)
//   0x40-0x60 = dark (medium shadow)
//   0x80-0xA0 = mid (main surface)
//   0xC0-0xE0 = light (highlight / accent line)
//   0xF0-0xFF = bright (intersection dot / node)
// ═══════════════════════════════════════════════════════════════════

function gray(v) { return [v, v, v]; }   // grayscale RGB helper

// Tile 1: Concrete Grid — dark base, lighter grid lines, bright intersections
function makeFloorConcreteGrid() {
  const g = makeCanvas(16, 16);
  fillRect(g, 0, 0, 16, 16, ...gray(0x38));   // dark concrete base
  // Grid lines every 4px
  for (let i = 0; i < 16; i += 4) {
    hline(g, i, 0, 15, ...gray(0x60));
    vline(g, i, 0, 15, ...gray(0x60));
  }
  // Intersection highlight dots
  for (let y = 0; y < 16; y += 4) for (let x = 0; x < 16; x += 4) {
    px(g, x, y, ...gray(0xd0));
  }
  return g;
}

// Tile 2: Metal Grate — very dark base, regular 3×3 cell pattern
function makeFloorMetalGrate() {
  const g = makeCanvas(16, 16);
  fillRect(g, 0, 0, 16, 16, ...gray(0x18));   // near-black base
  // 3×3 cell grid (raised surface, lighter)
  for (let y = 0; y < 16; y += 3) {
    for (let x = 0; x < 16; x += 3) {
      fillRect(g, x, y, 2, 2, ...gray(0x55));  // cell surface
      px(g, x+1, y+1, ...gray(0x80));          // cell highlight centre
    }
  }
  // Rivet/bolt dots at corners of 6×6 super-cells
  for (let y = 0; y < 16; y += 6) for (let x = 0; x < 16; x += 6) {
    px(g, x, y, ...gray(0xc0));
  }
  return g;
}

// Tile 3: Hazard Stripe — alternating dark and medium-light diagonal bands
function makeFloorHazardStripe() {
  const g = makeCanvas(16, 16);
  fillRect(g, 0, 0, 16, 16, ...gray(0x18));   // dark base (becomes room shadow)
  // Diagonal stripes every 4px — medium value (becomes room highlight color)
  for (let d = -16; d < 32; d += 4) {
    for (let i = 0; i < 2; i++) {
      const dd = d + i;
      for (let y = 0; y < 16; y++) {
        const x = dd + y;
        if (x >= 0 && x < 16) px(g, x, y, ...gray(0x90));
      }
    }
  }
  return g;
}

// Tile 4: Obsidian Circuit — very dark base, bright orthogonal trace lines + node dots
function makeFloorObsidianCircuit() {
  const g = makeCanvas(16, 16);
  fillRect(g, 0, 0, 16, 16, ...gray(0x0e));   // near-black obsidian
  // Circuit trace lines (bright)
  hline(g, 4,  1, 14, ...gray(0xb0));
  hline(g, 11, 1, 14, ...gray(0xb0));
  vline(g, 4,  1, 14, ...gray(0xb0));
  vline(g, 11, 1, 14, ...gray(0xb0));
  // Node/via pads at trace intersections (very bright)
  for (const [nx, ny] of [[4,4],[11,4],[4,11],[11,11]]) {
    fillRect(g, nx-1, ny-1, 3, 3, ...gray(0xd0));
    px(g, nx, ny, ...gray(0xff));             // via centre
  }
  // Subtle mid-line reflections
  for (let i = 0; i < 16; i += 5) px(g, i, (i+3)%16, ...gray(0x30));
  return g;
}

console.log('\n── Floor tiles (grayscale 16×16) ──');
save('floor_concrete_grid.png',    makeFloorConcreteGrid(),    FLOOR_OUT);
save('floor_metal_grate.png',      makeFloorMetalGrate(),      FLOOR_OUT);
save('floor_hazard_stripe.png',    makeFloorHazardStripe(),    FLOOR_OUT);
save('floor_obsidian_circuit.png', makeFloorObsidianCircuit(), FLOOR_OUT);

// ═══════════════════════════════════════════════════════════════════
// SECTION 11 — CYBERPUNK OPERATION CENTER PACK
// Original pixel-art recreations inspired by the supplied references.
// ═══════════════════════════════════════════════════════════════════

function drawGlassRect(g, x, y, w, h, glow = C.CYAN) {
  fillRect(g, x, y, w, h, ...C.MID, 210);
  outline(g, x, y, w, h, ...C.VOID);
  hline(g, y + 1, x + 2, x + w - 3, ...glow);
  vline(g, x + 1, y + 2, y + h - 3, ...C.NAVY);
  hline(g, y + h - 2, x + 2, x + w - 3, ...C.DGRAY);
}

function makeOpsCommandDisplay() {
  const g = makeCanvas(96, 32);
  drawGlassRect(g, 0, 0, 96, 32);
  fillRect(g, 5, 5, 86, 20, ...hex('#111436'));
  outline(g, 5, 5, 86, 20, ...C.CYAN);
  for (let x = 10; x < 88; x += 6) px(g, x, 27, ...C.CYAN);
  for (let x = 12; x < 82; x += 10) hline(g, 11 + (x % 3) * 3, x, x + 6, ...C.TEAL);
  return g;
}

function makeGlassMonitorWall() {
  const g = makeCanvas(64, 32);
  for (let i = 0; i < 3; i++) {
    drawGlassRect(g, 2 + i * 20, 4, 18, 20, i % 2 ? C.GREEN : C.CYAN);
    hline(g, 10, 5 + i * 20, 16 + i * 20, ...C.TEAL);
    hline(g, 15, 5 + i * 20, 14 + i * 20, ...C.GREEN);
    hline(g, 20, 5 + i * 20, 17 + i * 20, ...C.CYAN);
  }
  return g;
}

function makeNeonRackTall() {
  const g = makeCanvas(32, 48);
  fillRect(g, 4, 0, 24, 48, ...C.DARK);
  outline(g, 4, 0, 24, 48, ...C.VOID);
  for (let y = 4; y < 44; y += 6) {
    hline(g, y, 7, 24, ...C.GRAY);
    px(g, 9, y + 2, ...C.CYAN);
    px(g, 14, y + 2, ...(y % 12 ? C.GREEN : C.RED));
    px(g, 20, y + 2, ...C.TEAL);
  }
  vline(g, 5, 2, 45, ...C.NAVY);
  vline(g, 26, 2, 45, ...C.CYAN);
  return g;
}

function makeCableSprawl(colorA, colorB) {
  const g = makeCanvas(48, 16);
  for (let x = 0; x < 48; x++) {
    const y1 = 8 + Math.round(Math.sin(x / 5) * 4);
    const y2 = 5 + Math.round(Math.cos(x / 6) * 3);
    px(g, x, y1, ...colorA);
    if (x % 2 === 0) px(g, x, y1 + 1, ...colorA);
    px(g, x, y2, ...colorB);
  }
  for (let x = 5; x < 44; x += 13) fillRect(g, x, 6, 3, 3, ...C.DGRAY);
  return g;
}

function makeVerticalCablePillar() {
  const g = makeCanvas(16, 48);
  fillRect(g, 5, 0, 6, 48, ...C.DGRAY);
  outline(g, 5, 0, 6, 48, ...C.VOID);
  vline(g, 3, 4, 44, ...C.CYAN);
  vline(g, 8, 2, 45, ...C.RED);
  vline(g, 12, 5, 43, ...C.GREEN);
  for (let y = 5; y < 46; y += 10) hline(g, y, 2, 13, ...C.GRAY);
  return g;
}

function makeGlassPanelBlue() {
  const g = makeCanvas(32, 32);
  drawGlassRect(g, 1, 1, 30, 30);
  for (let y = 7; y < 28; y += 6) hline(g, y, 5, 25, ...C.NAVY);
  for (let x = 7; x < 28; x += 7) vline(g, x, 5, 25, ...C.TEAL);
  return g;
}

function makeGadgetConsole() {
  const g = makeCanvas(48, 32);
  drawGlassRect(g, 1, 5, 46, 24);
  fillRect(g, 5, 9, 16, 13, ...hex('#12305c'));
  outline(g, 5, 9, 16, 13, ...C.CYAN);
  fillRect(g, 26, 9, 16, 13, ...hex('#2b1245'));
  outline(g, 26, 9, 16, 13, ...C.RED);
  for (let i = 0; i < 5; i++) px(g, 8 + i * 3, 25, ...(i % 2 ? C.GREEN : C.CYAN));
  return g;
}

function makeStatusLightStrip() {
  const g = makeCanvas(48, 16);
  fillRect(g, 0, 4, 48, 8, ...C.DARK);
  outline(g, 0, 4, 48, 8, ...C.VOID);
  for (let x = 5; x < 45; x += 7) fillRect(g, x, 7, 3, 2, ...(x % 3 ? C.CYAN : C.RED));
  return g;
}

function makeCyberCornerTrim() {
  const g = makeCanvas(32, 32);
  hline(g, 2, 2, 29, ...C.NAVY);
  hline(g, 5, 5, 25, ...C.CYAN);
  vline(g, 2, 2, 29, ...C.NAVY);
  vline(g, 5, 5, 25, ...C.CYAN);
  fillRect(g, 1, 1, 6, 6, ...C.DARK);
  outline(g, 1, 1, 6, 6, ...C.VOID);
  return g;
}

function makeQuarantineGlassDoor() {
  const g = makeCanvas(32, 48);
  drawGlassRect(g, 3, 0, 26, 48, C.YELLOW);
  fillRect(g, 7, 5, 18, 30, ...hex('#13213d'), 210);
  for (let y = 8; y < 35; y += 6) hline(g, y, 8, 24, ...C.YELLOW);
  hline(g, 40, 7, 24, ...C.RED);
  return g;
}

function makeFloorCableNode() {
  const g = makeCanvas(32, 16);
  fillRect(g, 13, 5, 6, 6, ...C.DGRAY);
  outline(g, 13, 5, 6, 6, ...C.VOID);
  hline(g, 8, 0, 31, ...C.RED);
  hline(g, 10, 2, 29, ...C.CYAN);
  for (const [x, y] of [[8,8],[23,10],[16,6]]) fillRect(g, x, y, 2, 2, ...C.GREEN);
  return g;
}

function makeHoloMapTable() {
  const g = makeCanvas(48, 32);
  fillRect(g, 4, 16, 40, 10, ...C.DGRAY);
  outline(g, 4, 16, 40, 10, ...C.VOID);
  fillRect(g, 10, 6, 28, 12, ...hex('#0a3340'), 210);
  outline(g, 10, 6, 28, 12, ...C.CYAN);
  for (let x = 14; x < 35; x++) px(g, x, 12 + Math.round(Math.sin(x / 3) * 3), ...C.GREEN);
  return g;
}

function makePatchPanelWide() {
  const g = makeCanvas(64, 16);
  fillRect(g, 0, 1, 64, 14, ...C.DARK);
  outline(g, 0, 1, 64, 14, ...C.VOID);
  for (let x = 5; x < 60; x += 6) {
    fillRect(g, x, 5, 3, 3, ...C.MID);
    px(g, x + 1, 10, ...(x % 4 ? C.CYAN : C.RED));
  }
  return g;
}

console.log('\n── Cyberpunk operation center pack ──');
save('ops-command-display.png', makeOpsCommandDisplay());
save('glass-monitor-wall.png', makeGlassMonitorWall());
save('neon-rack-tall.png', makeNeonRackTall());
save('cable-sprawl-red.png', makeCableSprawl(C.RED, C.GREEN));
save('cable-sprawl-cyan.png', makeCableSprawl(C.CYAN, C.TEAL));
save('vertical-cable-pillar.png', makeVerticalCablePillar());
save('glass-panel-blue.png', makeGlassPanelBlue());
save('gadget-console.png', makeGadgetConsole());
save('status-light-strip.png', makeStatusLightStrip());
save('cyber-corner-trim.png', makeCyberCornerTrim());
save('quarantine-glass-door.png', makeQuarantineGlassDoor());
save('floor-cable-node.png', makeFloorCableNode());
save('holo-map-table.png', makeHoloMapTable());
save('patch-panel-wide.png', makePatchPanelWide());

console.log('\n✅  All assets generated.\n');
