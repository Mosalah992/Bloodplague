import { ISO_HALF_W, ISO_HALF_H } from '../constants.js';
import { tileToIso } from './worldCamera.js';
import type { WorldState } from './worldState.js';
import { getAgentSprite, SPRITE_W, SPRITE_H } from './agentSprites.js';
import { getAgentPngSprite, primeAgentSprites } from './agentPngSprites.js';
import {
  directionToTileVector,
  type AgentAnimationDirection,
  type AgentAnimationFrame,
  type AgentAnimationPose,
} from './agentAnimationController.js';

const AGENT_TARGET_VISUAL_H = 56;
let _primed = false;

const INFECTION_STATE_TINTS: Record<string, string> = {
  'S':          '#94a3b8', // susceptible (slate)
  'E':          '#facc15', // exposed (amber)
  'I_R':        '#fbbf24', // infected, replicating
  'I_C':        '#ef4444', // infected, contagious
  'I_X':        '#dc2626', // infected, exfiltrating
  'Q':          '#6366f1', // quarantined
  'R':          '#34d399', // recovered (default)
  'R_NATURAL':  '#34d399', // recovered naturally
  'R_VACCINE':  '#22d3ee', // recovered via vaccine
  'P':          '#f43f5e', // patient zero / persistent
};

// Fallback colors for when sprite isn't available
const ROLE_COLORS: Record<string, { body: string; label: string }> = {
  'courier-1':    { body: '#fb923c', label: 'C1'  },
  'courier-2':    { body: '#f97316', label: 'C2'  },
  'analyst-1':    { body: '#4ade80', label: 'A1'  },
  'analyst-2':    { body: '#22c55e', label: 'A2'  },
  'guardian':     { body: '#a78bfa', label: 'G'   },
  'orchestrator': { body: '#38bdf8', label: 'ORC' },
};

const ROLE_LABELS: Record<string, string> = {
  'courier-1':    'C1',
  'courier-2':    'C2',
  'analyst-1':    'A1',
  'analyst-2':    'A2',
  'guardian':     'G',
  'orchestrator': 'ORC',
};

const REST_FRAME: AgentAnimationFrame = {
  offsetX: 0,
  offsetY: 0,
  scaleX: 1,
  scaleY: 1,
  lunge: 0,
  shadowScale: 1,
  flash: 0,
};

function lungeOffset(direction: AgentAnimationDirection, amount: number): { x: number; y: number } {
  if (!amount) return { x: 0, y: 0 };
  // Top-down cartesian projection. directionToTileVector returns cell-delta:
  // south → (0, +1), north → (0, -1), east → (+1, 0), west → (-1, 0).
  // Positive y is down on screen, so row delta maps directly.
  const v = directionToTileVector(direction);
  const tx = v.col * 2 * ISO_HALF_W;
  const ty = v.row * 2 * ISO_HALF_H;
  const len = Math.hypot(tx, ty) || 1;
  return { x: (tx / len) * amount, y: (ty / len) * amount };
}

function actionColor(pose: AgentAnimationPose): string {
  if (pose.interactionKind === 'infection_attempt') return '#a855f7';
  if (pose.interactionKind === 'attack') return '#ef4444';
  if (pose.interactionKind === 'message') return '#22d3ee';
  return '#facc15';
}

function drawActionFlash(
  ctx: CanvasRenderingContext2D,
  state: WorldState,
  agentId: string,
  ix: number,
  feetY: number,
  pose: AgentAnimationPose | null,
): void {
  if (!pose || pose.frame.flash <= 0) return;
  const alpha = Math.min(0.9, pose.frame.flash);
  const color = actionColor(pose);
  const target = pose.targetId ? state.agentPositions.get(pose.targetId) : null;

  ctx.save();
  ctx.globalAlpha = alpha;
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = 2;
  ctx.shadowColor = color;
  ctx.shadowBlur = 10;

  if (target) {
    const [tx, ty] = tileToIso(target.col, target.row);
    const mx = ix + (tx - ix) * 0.42;
    const my = feetY + (ty + ISO_HALF_H - feetY) * 0.42;
    ctx.beginPath();
    ctx.moveTo(ix, feetY - 22);
    ctx.quadraticCurveTo(mx, my - 34, tx, ty + ISO_HALF_H - 18);
    ctx.stroke();
    ctx.beginPath();
    ctx.ellipse(tx, ty + ISO_HALF_H - 18, 10 + alpha * 10, 5 + alpha * 5, 0, 0, Math.PI * 2);
    ctx.stroke();
  } else {
    const direction = pose.direction;
    const v = lungeOffset(direction, 22);
    ctx.beginPath();
    ctx.moveTo(ix + v.x * 0.15, feetY - 26 + v.y * 0.15);
    ctx.lineTo(ix + v.x, feetY - 30 + v.y);
    ctx.stroke();
  }

  const selfPulse = 8 + alpha * 14;
  ctx.beginPath();
  ctx.ellipse(ix, feetY - 18, selfPulse, selfPulse * 0.55, 0, 0, Math.PI * 2);
  ctx.stroke();
  ctx.restore();
}

export function renderAgentLayer(
  ctx: CanvasRenderingContext2D,
  state: WorldState,
  elapsed: number,
): void {
  if (!_primed) { primeAgentSprites(); _primed = true; }

  const agents = Array.from(state.agentPositions.entries())
    .sort(([, a], [, b]) => (a.col + a.row) - (b.col + b.row));

  for (const [agentId, pos] of agents) {
    const isSelected = state.selectedWorldAgentId === agentId;
    const isPerceived = !state.selectedWorldAgentId || state.debugMode || isSelected || state.nearbyAgents.has(agentId) || state.reachableAgents.has(agentId);
    
    if (!isPerceived) {
      // Potentially skip or draw very faintly
      ctx.save();
      ctx.globalAlpha = 0.05;
    }

    const [ix, iy] = tileToIso(pos.col, pos.row);
    const semantic = state.agentSemantics.get(agentId);
    const epidemicState = semantic?.epidemicState ?? 'S';
    const contamination = Math.max(0, Math.min(1, semantic?.contaminationLevel ?? 0));
    const quarantineStatus = semantic?.quarantineStatus ?? 'none';
    const strainFamily = semantic?.strainFamily ?? '';
    const pose = state.getAgentAnimationPose(agentId);
    const direction = (pose?.direction ?? state.agentFacings.get(agentId) ?? 'south') as AgentAnimationDirection;
    const frame = pose?.frame ?? REST_FRAME;
    const lunge = lungeOffset(direction, frame.lunge);
    const auraPulse = 0.5 + 0.5 * Math.sin(elapsed * 5 + pos.col);

    const pngSprite = getAgentPngSprite(agentId, direction);
    const feetX = ix + lunge.x * 0.45;
    // Top-down: feet anchored at cell bottom (iy + 2*ISO_HALF_H).
    const feetY = iy + ISO_HALF_H * 2 + lunge.y * 0.2;
    const visibleBounds = pngSprite?.bounds ?? {
      left: 0,
      top: 0,
      right: SPRITE_W,
      bottom: SPRITE_H,
      width: SPRITE_W,
      height: SPRITE_H,
    };
    const visualScale = pngSprite
      ? Math.max(0.92, Math.min(1.26, AGENT_TARGET_VISUAL_H / Math.max(1, visibleBounds.height)))
      : 1;
    const spriteW = pngSprite?.width ?? SPRITE_W;
    const spriteH = pngSprite?.height ?? SPRITE_H;
    const drawW = spriteW * visualScale * frame.scaleX;
    const drawH = spriteH * visualScale * frame.scaleY;
    const scaledBoundsLeft = visibleBounds.left * visualScale * frame.scaleX;
    const scaledBoundsW = visibleBounds.width * visualScale * frame.scaleX;
    const scaledBoundsBottom = visibleBounds.bottom * visualScale * frame.scaleY;
    const bodyMotionY = pose?.state === 'ATTACKING' ? frame.offsetY + lunge.y : 0;
    const pdx = feetX - (scaledBoundsLeft + scaledBoundsW / 2) + frame.offsetX;
    const pdy = feetY - scaledBoundsBottom + bodyMotionY;

    if (isSelected) {
      ctx.save();
      ctx.strokeStyle = '#38bdf8';
      ctx.lineWidth = 2;
      const ringPulse = 1.0 + 0.1 * Math.sin(elapsed * 6);
      ctx.beginPath();
      ctx.ellipse(ix, feetY, 28 * ringPulse, 12 * ringPulse, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    if (contamination > 0.08 || epidemicState.startsWith('I')) {
      const glowR = 24 + contamination * 26 + auraPulse * 6;
      const grad = ctx.createRadialGradient(ix, feetY - 18, 0, ix, feetY - 18, glowR);
      const core = strainFamily === 'context_poisoning' ? '#a855f7' : '#ef4444';
      grad.addColorStop(0, `${core}${Math.round(50 + contamination * 120).toString(16).padStart(2, '0')}`);
      grad.addColorStop(1, 'transparent');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.ellipse(ix, feetY - 16, glowR, glowR * 0.72, 0, 0, Math.PI * 2);
      ctx.fill();
    }

    if (quarantineStatus && quarantineStatus !== 'none') {
      ctx.save();
      ctx.strokeStyle = '#ef4444';
      ctx.lineWidth = 2;
      ctx.globalAlpha = 0.8 + auraPulse * 0.2;
      ctx.beginPath();
      ctx.ellipse(ix, feetY, 24, 10, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = '#ef4444';
      ctx.font = 'bold 7px monospace';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('LOCK', ix, feetY - 24);
      ctx.restore();
    }

    if (pose?.proximityPulse) {
      ctx.save();
      ctx.globalAlpha = pose.proximityPulse * 0.55;
      ctx.strokeStyle = '#facc15';
      ctx.lineWidth = 1.6;
      ctx.setLineDash([3, 3]);
      const pulse = 14 + (1 - pose.proximityPulse) * 30;
      ctx.beginPath();
      ctx.ellipse(feetX, feetY, pulse, pulse * 0.42, 0, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    ctx.save();
    ctx.globalAlpha = 0.23;
    ctx.fillStyle = '#000000';
    ctx.beginPath();
    ctx.ellipse(feetX, feetY + 1, 14 * frame.shadowScale, 4.8 * frame.shadowScale, 0, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();

    drawActionFlash(ctx, state, agentId, feetX, feetY, pose);

    if (pngSprite) {
      // Subtle glow halo
      const colors = ROLE_COLORS[agentId];
      if (colors) {
        const glowR = Math.max(22, visibleBounds.width * visualScale * 0.8);
        const cx = feetX;
        const cy = feetY - Math.max(18, visibleBounds.height * visualScale * 0.45) + frame.offsetY * 0.35;
        const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, glowR);
        grad.addColorStop(0, colors.body + '30');
        grad.addColorStop(1, 'transparent');
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.ellipse(cx, cy, glowR, glowR * 0.55, 0, 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.save();
      ctx.globalAlpha = 0.82 + (pose?.transitionAlpha ?? 1) * 0.18;
      ctx.drawImage(pngSprite.source, pdx, pdy, drawW, drawH);
      ctx.restore();

      // The infection glow above carries state; avoid rectangular tint masks
      // over transparent PNG padding, which makes sprites look pasted on.
    } else {
      // Fallback: legacy pixel-art sprite or glowing circle
      const sprite = getAgentSprite(agentId, epidemicState, elapsed);
      const dx = ix - (SPRITE_W * frame.scaleX) / 2 + frame.offsetX + lunge.x;
      const dy = iy + ISO_HALF_H * 2 - (SPRITE_H * frame.scaleY) + 4 + bodyMotionY;

      if (sprite) {
        ctx.drawImage(sprite, dx, dy, SPRITE_W * frame.scaleX, SPRITE_H * frame.scaleY);
        const tint = INFECTION_STATE_TINTS[epidemicState];
        if (tint) {
          ctx.globalAlpha = Math.min(0.52, 0.22 + contamination * 0.35);
          ctx.fillStyle = tint;
          ctx.fillRect(dx, dy, SPRITE_W * frame.scaleX, SPRITE_H * frame.scaleY);
          ctx.globalAlpha = 1.0;
        }
      } else {
        const colors = ROLE_COLORS[agentId] ?? { body: '#888', label: '?' };
        const RADIUS = 10;
        const px = feetX;
        const py = iy + ISO_HALF_H * 2 - RADIUS + bodyMotionY;
        const glowR = RADIUS * 2 + Math.sin(elapsed * 2 + pos.col) * 2;
        const grad = ctx.createRadialGradient(px, py, 0, px, py, glowR);
        grad.addColorStop(0, colors.body + '80');
        grad.addColorStop(1, 'transparent');
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(px, py, glowR, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = colors.body;
        ctx.beginPath();
        ctx.arc(px, py, RADIUS, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    if (strainFamily === 'role_confusion' || strainFamily === 'context_poisoning') {
      ctx.save();
      ctx.globalAlpha = strainFamily === 'role_confusion' ? 0.45 + auraPulse * 0.35 : 0.62;
      ctx.strokeStyle = strainFamily === 'role_confusion' ? '#f59e0b' : '#84cc16';
      ctx.lineWidth = 1.5;
      ctx.setLineDash(strainFamily === 'role_confusion' ? [3, 3] : [6, 2]);
      ctx.strokeRect(
        pdx + scaledBoundsLeft + Math.sin(elapsed * 18) * 2,
        pdy + visibleBounds.top * visualScale + 2,
        Math.max(12, scaledBoundsW),
        Math.max(16, visibleBounds.height * visualScale - 4),
      );
      if (strainFamily === 'context_poisoning') {
        ctx.strokeStyle = '#a855f7';
        ctx.strokeRect(
          pdx + scaledBoundsLeft - 2,
          pdy + visibleBounds.top * visualScale + 4 + Math.cos(elapsed * 12) * 2,
          Math.max(16, scaledBoundsW + 4),
          Math.max(16, visibleBounds.height * visualScale - 8),
        );
      }
      ctx.restore();
    }

    // Label below sprite
    const label = ROLE_LABELS[agentId] ?? '?';
    const labelY = feetY + 5;
    ctx.font = 'bold 8px monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    ctx.fillStyle = 'rgba(0,0,0,0.6)';
    ctx.fillText(label, ix + 1, labelY + 1);
    ctx.fillStyle = '#ffffff';
    ctx.fillText(label, ix, labelY);

    if (semantic?.action && semantic.action !== 'IDLE' && semantic.action !== 'WALKING') {
      // Small icon or indicator for "working/focused"
      ctx.fillStyle = '#38bdf8';
      ctx.beginPath();
      ctx.arc(ix + 14, labelY + 4, 2, 0, Math.PI * 2);
      ctx.fill();
    }

    if (!isPerceived) {
      ctx.restore();
    }
  }
}
