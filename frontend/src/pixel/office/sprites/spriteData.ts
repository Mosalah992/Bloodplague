import { Direction, type SpriteData } from '../types.js';

export interface DirectionalFrames {
  [Direction.DOWN]: SpriteData[];
  [Direction.LEFT]: SpriteData[];
  [Direction.RIGHT]: SpriteData[];
  [Direction.UP]: SpriteData[];
}

export interface CharacterSprites {
  walk: DirectionalFrames;
  typing: DirectionalFrames;
  reading: DirectionalFrames;
}

interface CharacterDirectionSprites {
  down: SpriteData[];
  up: SpriteData[];
  right: SpriteData[];
}

const TRANSPARENT = '';

export const BUBBLE_WAITING_SPRITE: SpriteData = [
  ['', '#FFFFFF', '#FFFFFF', '#FFFFFF', '#FFFFFF', '#FFFFFF', ''],
  ['#FFFFFF', '#111827', '#111827', '#111827', '#111827', '#111827', '#FFFFFF'],
  ['#FFFFFF', '#111827', '#FFFFFF', '#111827', '#FFFFFF', '#111827', '#FFFFFF'],
  ['#FFFFFF', '#111827', '#111827', '#111827', '#111827', '#111827', '#FFFFFF'],
  ['', '#FFFFFF', '#FFFFFF', '#FFFFFF', '#FFFFFF', '#FFFFFF', ''],
  ['', '', '#FFFFFF', '', '', '', ''],
];

export const BUBBLE_PERMISSION_SPRITE: SpriteData = [
  ['', '#FEF3C7', '#FEF3C7', '#FEF3C7', '#FEF3C7', '#FEF3C7', ''],
  ['#FEF3C7', '#451A03', '#451A03', '#F59E0B', '#451A03', '#451A03', '#FEF3C7'],
  ['#FEF3C7', '#451A03', '#FDE68A', '#FDE68A', '#FDE68A', '#451A03', '#FEF3C7'],
  ['#FEF3C7', '#451A03', '#451A03', '#F59E0B', '#451A03', '#451A03', '#FEF3C7'],
  ['', '#FEF3C7', '#FEF3C7', '#FEF3C7', '#FEF3C7', '#FEF3C7', ''],
  ['', '', '#FEF3C7', '', '', '', ''],
];

let characterTemplates: CharacterDirectionSprites[] = createFallbackTemplates();

export function setCharacterTemplates(templates: CharacterDirectionSprites[]): void {
  if (!templates.length) return;
  characterTemplates = templates;
}

export function getLoadedCharacterCount(): number {
  return Math.max(1, characterTemplates.length);
}

export function getCharacterSprites(palette: number, _hueShift = 0): CharacterSprites {
  const template = characterTemplates[Math.abs(palette) % characterTemplates.length];
  return {
    walk: toDirectionalFrames(template, 4),
    typing: toDirectionalFrames(template, 2, 3),
    reading: toDirectionalFrames(template, 2, 5),
  };
}

function toDirectionalFrames(
  template: CharacterDirectionSprites,
  count: number,
  start = 0,
): DirectionalFrames {
  const down = cycle(template.down, count, start);
  const up = cycle(template.up, count, start);
  const right = cycle(template.right, count, start);
  return {
    [Direction.DOWN]: down,
    [Direction.LEFT]: right.map(mirrorSprite),
    [Direction.RIGHT]: right,
    [Direction.UP]: up,
  };
}

function cycle(frames: SpriteData[], count: number, start = 0): SpriteData[] {
  const source = frames.length ? frames : [emptySprite()];
  return Array.from({ length: count }, (_, index) => source[(start + index) % source.length]);
}

function mirrorSprite(sprite: SpriteData): SpriteData {
  return sprite.map((row) => [...row].reverse());
}

function emptySprite(): SpriteData {
  return Array.from({ length: 16 }, () => Array(12).fill(TRANSPARENT));
}

function createFallbackTemplates(): CharacterDirectionSprites[] {
  const palettes = [
    ['#22C55E', '#14532D', '#86EFAC'],
    ['#EC4899', '#831843', '#F9A8D4'],
    ['#22D3EE', '#164E63', '#A5F3FC'],
    ['#A855F7', '#581C87', '#D8B4FE'],
    ['#F59E0B', '#78350F', '#FDE68A'],
  ];
  return palettes.map(([primary, suit, accent]) => ({
    down: buildOfficeFrames(primary, suit, accent),
    up: buildOfficeFrames(primary, suit, accent, 'up'),
    right: buildOfficeFrames(primary, suit, accent, 'right'),
  }));
}

function buildOfficeFrames(
  primary: string,
  suit: string,
  accent: string,
  facing: 'down' | 'up' | 'right' = 'down',
): SpriteData[] {
  const palette: Record<string, string> = {
    K: '#05070A',
    B: primary,
    C: suit,
    A: accent,
    H: facing === 'up' ? suit : '#F1C27D',
    W: '#FFFFFF',
    S: '#334155',
    '.': TRANSPARENT,
  };
  const rows = [
    [
      '....KKKK....',
      '...KBBBBK...',
      '..KBBHHBBK..',
      '..KBBBBBBK..',
      '...KBBBBK...',
      '....KHHK....',
      '..KKCCCCKK..',
      '.KCCACACCK.',
      '.KCCCCCCCCK.',
      '..KCCCCCCK..',
      '...KCCCCK...',
      '...KSSSSK...',
      '..KSS..SSK..',
      '.KSS....SSK.',
      '.KK......KK.',
      '............',
    ],
    [
      '....KKKK....',
      '...KBBBBK...',
      '..KBBHHBBK..',
      '..KBBBBBBK..',
      '...KBBBBK...',
      '....KHHK....',
      '..KKCCCCKK..',
      '.KCCACACCK.',
      '.KCCCCCCCCK.',
      '..KCCCCCCK..',
      '...KCCCCK...',
      '...KSSSSK...',
      '.KSS....SSK.',
      '.KK......KK.',
      '............',
      '............',
    ],
    [
      '....KKKK....',
      '...KBBBBK...',
      '..KBBHHBBK..',
      '..KBBBBBBK..',
      '...KBBBBK...',
      '....KHHK....',
      '..KKCCCCK...',
      '.KCCACACKK..',
      '.KCCCCCCK...',
      '..KCCCCK....',
      '...KCCK.....',
      '...KSSSSK...',
      '..KSS..SSK..',
      '.KSS....SSK.',
      '.KK......KK.',
      '............',
    ],
    [
      '....KKKK....',
      '...KBBBBK...',
      '..KBBHHBBK..',
      '..KBBBBBBK..',
      '...KBBBBK...',
      '....KHHK....',
      '...KCCCCKK..',
      '..KKCACACCK.',
      '...KCCCCCCK.',
      '....KCCCCK..',
      '.....KCCK...',
      '...KSSSSK...',
      '..KSS..SSK..',
      '.KSS....SSK.',
      '.KK......KK.',
      '............',
    ],
  ];
  return rows.map((frame) => frame.map((row) => row.split('').map((key) => palette[key] || TRANSPARENT)));
}
