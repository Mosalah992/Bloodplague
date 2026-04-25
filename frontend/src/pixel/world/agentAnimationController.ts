export const AGENT_ANIMATION_STATES = {
  IDLE: 'IDLE',
  WALKING: 'WALKING',
  STANDING: 'STANDING',
  ATTACKING: 'ATTACKING',
} as const;

export type AgentAnimationState = typeof AGENT_ANIMATION_STATES[keyof typeof AGENT_ANIMATION_STATES];

export type AgentAnimationDirection =
  | 'north'
  | 'north-east'
  | 'east'
  | 'south-east'
  | 'south'
  | 'south-west'
  | 'west'
  | 'north-west';

export type AgentInteractionKind = 'message' | 'attack' | 'infection_attempt' | 'proximity';

export interface AgentAnimationFrame {
  offsetX: number;
  offsetY: number;
  scaleX: number;
  scaleY: number;
  lunge: number;
  shadowScale: number;
  flash: number;
}

interface AgentAnimationDefinition {
  fps: number;
  loop: boolean;
  frames: AgentAnimationFrame[];
}

export interface AgentAnimationInput {
  dt: number;
  velocityCol: number;
  velocityRow: number;
  targetDistance: number;
  backendState?: string;
  backendAction?: string;
  targetId?: string;
}

export interface AgentAnimationPose {
  state: AgentAnimationState;
  previousState: AgentAnimationState;
  direction: AgentAnimationDirection;
  frame: AgentAnimationFrame;
  frameIndex: number;
  stateAge: number;
  transitionAlpha: number;
  interactionKind: AgentInteractionKind | '';
  targetId: string;
  proximityPulse: number;
}

const ZERO_FRAME: AgentAnimationFrame = {
  offsetX: 0,
  offsetY: 0,
  scaleX: 1,
  scaleY: 1,
  lunge: 0,
  shadowScale: 1,
  flash: 0,
};

const ANIMATIONS: Record<AgentAnimationState, AgentAnimationDefinition> = {
  IDLE: {
    fps: 2.2,
    loop: true,
    frames: [
      { ...ZERO_FRAME, offsetY: 0, scaleY: 1 },
      { ...ZERO_FRAME, offsetY: -0.7, scaleY: 1.012, shadowScale: 0.98 },
      { ...ZERO_FRAME, offsetY: -1.1, scaleY: 1.018, shadowScale: 0.97 },
      { ...ZERO_FRAME, offsetY: -0.4, scaleY: 1.008, shadowScale: 0.99 },
    ],
  },
  WALKING: {
    fps: 8.5,
    loop: true,
    frames: [
      { ...ZERO_FRAME, offsetX: -1.2, offsetY: -1.5, scaleY: 1.01, shadowScale: 1.04 },
      { ...ZERO_FRAME, offsetX: -0.6, offsetY: -3.2, scaleY: 1.025, shadowScale: 0.98 },
      { ...ZERO_FRAME, offsetX: 0.2, offsetY: -1.4, scaleY: 1.005, shadowScale: 1.03 },
      { ...ZERO_FRAME, offsetX: 0.9, offsetY: -0.4, scaleY: 0.995, shadowScale: 1.08 },
      { ...ZERO_FRAME, offsetX: 1.2, offsetY: -1.6, scaleY: 1.01, shadowScale: 1.04 },
      { ...ZERO_FRAME, offsetX: 0.6, offsetY: -3.3, scaleY: 1.025, shadowScale: 0.98 },
      { ...ZERO_FRAME, offsetX: -0.2, offsetY: -1.4, scaleY: 1.005, shadowScale: 1.03 },
      { ...ZERO_FRAME, offsetX: -0.9, offsetY: -0.4, scaleY: 0.995, shadowScale: 1.08 },
    ],
  },
  STANDING: {
    fps: 9,
    loop: false,
    frames: [
      { ...ZERO_FRAME, offsetY: -1.6, scaleY: 1.01, shadowScale: 0.98 },
      { ...ZERO_FRAME, offsetY: -0.8, scaleY: 1.005, shadowScale: 1.0 },
      { ...ZERO_FRAME, offsetY: -0.2, scaleY: 0.998, shadowScale: 1.03 },
      ZERO_FRAME,
    ],
  },
  ATTACKING: {
    fps: 12,
    loop: false,
    frames: [
      { ...ZERO_FRAME, offsetY: -0.6, scaleX: 0.98, scaleY: 1.03, lunge: -2, shadowScale: 0.98, flash: 0.1 },
      { ...ZERO_FRAME, offsetY: -2.0, scaleX: 1.03, scaleY: 1.0, lunge: 3, shadowScale: 1.02, flash: 0.4 },
      { ...ZERO_FRAME, offsetY: -3.4, scaleX: 1.08, scaleY: 0.96, lunge: 8, shadowScale: 1.12, flash: 1.0 },
      { ...ZERO_FRAME, offsetY: -1.6, scaleX: 1.04, scaleY: 0.98, lunge: 5, shadowScale: 1.08, flash: 0.72 },
      { ...ZERO_FRAME, offsetY: -0.5, scaleX: 0.99, scaleY: 1.01, lunge: 1, shadowScale: 1.02, flash: 0.32 },
      ZERO_FRAME,
    ],
  },
};

const WALK_ENTER_DELAY = 0.08;
const IDLE_ENTER_DELAY = 0.12;
const STANDING_SECONDS = 0.32;
const TRANSITION_SECONDS = 0.12;
const MOVING_SPEED_EPSILON = 0.035;
const TARGET_DISTANCE_EPSILON = 0.075;

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

export function directionFromVector(
  dc: number,
  dr: number,
  fallback: AgentAnimationDirection = 'south',
): AgentAnimationDirection {
  const speed = Math.hypot(dc, dr);
  if (speed < 0.001) return fallback;

  const angle = Math.atan2(dr, dc);
  const octant = Math.round(angle / (Math.PI / 4));
  switch ((octant + 8) % 8) {
    case 0: return 'east';
    case 1: return 'south-east';
    case 2: return 'south';
    case 3: return 'south-west';
    case 4: return 'west';
    case 5: return 'north-west';
    case 6: return 'north';
    case 7: return 'north-east';
    default: return fallback;
  }
}

export function directionToTileVector(direction: AgentAnimationDirection): { col: number; row: number } {
  switch (direction) {
    case 'north': return { col: 0, row: -1 };
    case 'north-east': return { col: 1, row: -1 };
    case 'east': return { col: 1, row: 0 };
    case 'south-east': return { col: 1, row: 1 };
    case 'south': return { col: 0, row: 1 };
    case 'south-west': return { col: -1, row: 1 };
    case 'west': return { col: -1, row: 0 };
    case 'north-west': return { col: -1, row: -1 };
    default: return { col: 0, row: 1 };
  }
}

function normalizeState(value?: string): AgentAnimationState | null {
  const normalized = String(value ?? '').trim().toUpperCase();
  if (normalized in AGENT_ANIMATION_STATES) {
    return normalized as AgentAnimationState;
  }
  return null;
}

export function interactionKindFromAction(action?: string): AgentInteractionKind | null {
  const normalized = String(action ?? '').trim().toLowerCase();
  if (!normalized) return null;
  if (normalized.includes('quarantine')) return null;
  if (normalized.includes('infect') || normalized.includes('contamination') || normalized.includes('poison')) {
    return 'infection_attempt';
  }
  if (normalized.includes('attack') || normalized.includes('exploit') || normalized.includes('payload')) {
    return 'attack';
  }
  if (normalized.includes('message') || normalized.includes('conversation') || normalized.includes('send')) {
    return 'message';
  }
  return null;
}

export class AgentAnimationController {
  readonly agentId: string;

  private state: AgentAnimationState = 'IDLE';
  private previousState: AgentAnimationState = 'IDLE';
  private direction: AgentAnimationDirection = 'south';
  private frameIndex = 0;
  private frameAge = 0;
  private stateAge = 0;
  private transitionAge = TRANSITION_SECONDS;
  private movingAge = 0;
  private stillAge = 0;
  private interactionKind: AgentInteractionKind | '' = '';
  private interactionTarget = '';
  private proximityPulseAge = 999;
  private lastBackendActionKey = '';

  constructor(agentId: string) {
    this.agentId = agentId;
  }

  triggerInteraction(kind: AgentInteractionKind, targetId = ''): void {
    if (kind === 'proximity') {
      this.proximityPulseAge = 0;
      if (this.state !== 'ATTACKING') this.enter('STANDING');
      return;
    }
    this.interactionKind = kind;
    this.interactionTarget = targetId;
    this.enter('ATTACKING');
  }

  update(input: AgentAnimationInput): void {
    const dt = Math.max(0, input.dt || 0);
    const backendState = normalizeState(input.backendState);
    const backendInteraction = interactionKindFromAction(input.backendAction);
    const backendActionKey = input.backendAction ? `${input.backendAction}:${input.targetId ?? ''}` : '';
    if (backendInteraction && backendActionKey && backendActionKey !== this.lastBackendActionKey) {
      this.triggerInteraction(backendInteraction, input.targetId ?? '');
    }
    this.lastBackendActionKey = backendActionKey;

    const speed = Math.hypot(input.velocityCol, input.velocityRow);
    const moving = speed > MOVING_SPEED_EPSILON || input.targetDistance > TARGET_DISTANCE_EPSILON;
    if (moving) {
      this.direction = directionFromVector(input.velocityCol, input.velocityRow, this.direction);
    }

    this.stateAge += dt;
    this.transitionAge += dt;
    this.proximityPulseAge += dt;

    if (this.state === 'ATTACKING') {
      this.advanceFrame(dt);
      if (this.isCurrentAnimationDone()) {
        this.interactionKind = '';
        this.interactionTarget = '';
        this.enter(moving ? 'WALKING' : 'STANDING');
      }
      return;
    }

    if (backendState === 'ATTACKING') {
      this.enter('ATTACKING');
      this.advanceFrame(dt);
      return;
    }

    if (moving) {
      this.movingAge += dt;
      this.stillAge = 0;
      if (this.state !== 'WALKING' && this.movingAge >= WALK_ENTER_DELAY) {
        this.enter('WALKING');
      }
    } else {
      this.stillAge += dt;
      this.movingAge = 0;
      if (this.state === 'WALKING') {
        this.enter('STANDING');
      } else if (this.state === 'STANDING' && this.stateAge >= STANDING_SECONDS) {
        this.enter('IDLE');
      } else if (this.state !== 'IDLE' && this.state !== 'STANDING' && this.stillAge >= IDLE_ENTER_DELAY) {
        this.enter('IDLE');
      }
    }

    if (backendState === 'WALKING' && moving && this.state !== 'WALKING') {
      this.enter('WALKING');
    } else if (backendState === 'STANDING' && !moving && this.state !== 'STANDING') {
      this.enter('STANDING');
    } else if (backendState === 'IDLE' && !moving && this.state !== 'IDLE' && this.stillAge >= IDLE_ENTER_DELAY) {
      this.enter('IDLE');
    }

    this.advanceFrame(dt);
  }

  getPose(): AgentAnimationPose {
    const definition = ANIMATIONS[this.state];
    const frame = definition.frames[this.frameIndex] ?? ZERO_FRAME;
    return {
      state: this.state,
      previousState: this.previousState,
      direction: this.direction,
      frame,
      frameIndex: this.frameIndex,
      stateAge: this.stateAge,
      transitionAlpha: clamp01(this.transitionAge / TRANSITION_SECONDS),
      interactionKind: this.interactionKind,
      targetId: this.interactionTarget,
      proximityPulse: clamp01(1 - this.proximityPulseAge / 1.1),
    };
  }

  private enter(next: AgentAnimationState): void {
    if (this.state === next) return;
    this.previousState = this.state;
    this.state = next;
    this.frameIndex = 0;
    this.frameAge = 0;
    this.stateAge = 0;
    this.transitionAge = 0;
  }

  private advanceFrame(dt: number): void {
    const definition = ANIMATIONS[this.state];
    const frames = definition.frames;
    if (!frames.length || dt <= 0) return;
    const frameSeconds = 1 / Math.max(1, definition.fps);
    this.frameAge += dt;
    while (this.frameAge >= frameSeconds) {
      this.frameAge -= frameSeconds;
      if (definition.loop) {
        this.frameIndex = (this.frameIndex + 1) % frames.length;
      } else {
        this.frameIndex = Math.min(frames.length - 1, this.frameIndex + 1);
      }
    }
  }

  private isCurrentAnimationDone(): boolean {
    const definition = ANIMATIONS[this.state];
    return !definition.loop && this.frameIndex >= definition.frames.length - 1;
  }
}
