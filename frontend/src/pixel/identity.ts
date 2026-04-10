export type PixelAgentKey =
  | 'courier-1'
  | 'courier-2'
  | 'analyst-1'
  | 'analyst-2'
  | 'guardian';

export interface PixelAgentSpec {
  key: PixelAgentKey;
  numericId: number;
  palette: number;
  codename: 'SHADOW' | 'PHANTOM' | 'ORACLE' | 'CIPHER' | 'SENTINEL';
  role: 'Courier' | 'Analyst' | 'Guardian';
  seatId: string;
  quarantineSeatId: string;
  accent: string;
  infectionTint: string;
}

export const PIXEL_AGENT_SPECS: Record<PixelAgentKey, PixelAgentSpec> = {
  'courier-1': {
    key: 'courier-1',
    numericId: 101,
    palette: 0,
    codename: 'SHADOW',
    role: 'Courier',
    seatId: 'chair-shadow',
    quarantineSeatId: 'quarantine-a',
    accent: '#4ade80',
    infectionTint: 'rgba(74, 222, 128, 0.28)',
  },
  'courier-2': {
    key: 'courier-2',
    numericId: 102,
    palette: 1,
    codename: 'PHANTOM',
    role: 'Courier',
    seatId: 'chair-phantom',
    quarantineSeatId: 'quarantine-b',
    accent: '#ec4899',
    infectionTint: 'rgba(236, 72, 153, 0.28)',
  },
  'analyst-1': {
    key: 'analyst-1',
    numericId: 103,
    palette: 2,
    codename: 'ORACLE',
    role: 'Analyst',
    seatId: 'chair-oracle',
    quarantineSeatId: 'quarantine-a',
    accent: '#22d3ee',
    infectionTint: 'rgba(34, 211, 238, 0.28)',
  },
  'analyst-2': {
    key: 'analyst-2',
    numericId: 104,
    palette: 3,
    codename: 'CIPHER',
    role: 'Analyst',
    seatId: 'chair-cipher',
    quarantineSeatId: 'quarantine-b',
    accent: '#c084fc',
    infectionTint: 'rgba(192, 132, 252, 0.28)',
  },
  guardian: {
    key: 'guardian',
    numericId: 105,
    palette: 4,
    codename: 'SENTINEL',
    role: 'Guardian',
    seatId: 'chair-sentinel',
    quarantineSeatId: 'quarantine-a',
    accent: '#fbbf24',
    infectionTint: 'rgba(251, 191, 36, 0.22)',
  },
};

const AGENT_ALIASES: Record<string, PixelAgentKey> = {
  'agent-a': 'guardian',
  'agent-b': 'analyst-1',
  'agent-c': 'courier-1',
  shadow: 'courier-1',
  phantom: 'courier-2',
  oracle: 'analyst-1',
  cipher: 'analyst-2',
  sentinel: 'guardian',
};

const NUMERIC_TO_KEY = new Map(
  Object.values(PIXEL_AGENT_SPECS).map((spec) => [spec.numericId, spec.key]),
);

export const PIXEL_AGENT_ORDER: PixelAgentKey[] = [
  'courier-1',
  'courier-2',
  'analyst-1',
  'analyst-2',
  'guardian',
];

export const PIXEL_LAYOUT_IDS = {
  c2FurnitureUid: 'pc-c2',
  exfilFurnitureUid: 'exfil-console',
  exfilTile: { col: 28, row: 8 },
};

export function resolvePixelAgentKey(value: string | null | undefined): PixelAgentKey | null {
  const raw = String(value || '').trim().toLowerCase();
  if (!raw) return null;
  if (raw in PIXEL_AGENT_SPECS) {
    return raw as PixelAgentKey;
  }
  return AGENT_ALIASES[raw] || null;
}

export function getPixelAgentSpec(value: string | null | undefined): PixelAgentSpec | null {
  const key = resolvePixelAgentKey(value);
  return key ? PIXEL_AGENT_SPECS[key] : null;
}

export function getPixelAgentSpecByNumericId(id: number | null | undefined): PixelAgentSpec | null {
  if (id == null) return null;
  const key = NUMERIC_TO_KEY.get(id);
  return key ? PIXEL_AGENT_SPECS[key] : null;
}
