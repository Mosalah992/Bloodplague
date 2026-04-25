const BUBBLE_DISPLAY_SEC = 5.0;
const BUBBLE_FADE_SEC = 0.6;
const MAX_BUBBLES = 8;

export interface SpeechBubble {
  id: string;
  agentId: string;
  text: string;
  intent: string;
  infected: boolean;
  strainFamily: string;
  age: number;
  alpha: number;
  provenance?: {
    model: string;
    promptContextHash: string;
    rawLlmOutputHash: string;
    validationStatus: string;
  };
}

export class SpeechBubblePool {
  private bubbles: SpeechBubble[] = [];
  private seq = 0;

  push(
    agentId: string,
    text: string,
    intent: string,
    infected: boolean,
    strainFamily = "",
    provenance?: SpeechBubble["provenance"]
  ): void {
    if (this.bubbles.length >= MAX_BUBBLES) {
      this.bubbles.sort((a, b) => b.age - a.age);
      this.bubbles.pop();
    }
    this.bubbles.push({
      id: `bubble-${++this.seq}`,
      agentId,
      text,
      intent,
      infected,
      strainFamily,
      age: 0,
      alpha: 0,
      provenance,
    });
  }

  update(dt: number): void {
    for (const b of this.bubbles) {
      b.age += dt;
      if (b.age < 0.2) {
        b.alpha = b.age / 0.2;
      } else if (b.age >= BUBBLE_DISPLAY_SEC) {
        b.alpha = Math.max(0, 1 - (b.age - BUBBLE_DISPLAY_SEC) / BUBBLE_FADE_SEC);
      } else {
        b.alpha = 1.0;
      }
    }
    this.bubbles = this.bubbles.filter((b) => b.age < BUBBLE_DISPLAY_SEC + BUBBLE_FADE_SEC);
  }

  getAll(): SpeechBubble[] { return this.bubbles; }
}

export function renderSpeechBubbles(
  ctx: CanvasRenderingContext2D,
  bubbles: SpeechBubble[],
  agentPositions: Map<string, { col: number; row: number }>,
  _tileSize: number,
  toWorldPos?: (col: number, row: number) => [number, number],
): void {
  const PAD_X = 6;
  const PAD_Y = 4;
  const FONT_SIZE = 9;
  const MAX_WIDTH = 140;

  ctx.save();
  ctx.font = `${FONT_SIZE}px monospace`;

  for (const b of bubbles) {
    if (b.alpha <= 0) continue;
    const pos = agentPositions.get(b.agentId);
    if (!pos) continue;

    let anchorX: number, anchorY: number;
    if (toWorldPos) {
      const [wx, wy] = toWorldPos(pos.col, pos.row);
      anchorX = wx;
      anchorY = wy - 18; // float above agent circle
    } else {
      anchorX = pos.col * _tileSize + _tileSize / 2;
      anchorY = pos.row * _tileSize - _tileSize;
    }

    const words = b.text.split(' ');
    const lines: string[] = [];
    let current = '';
    for (const word of words) {
      const test = current ? `${current} ${word}` : word;
      if (ctx.measureText(test).width > MAX_WIDTH - PAD_X * 2) {
        if (current) lines.push(current);
        current = word;
      } else {
        current = test;
      }
    }
    if (current) lines.push(current);

    const lineH = FONT_SIZE + 3;
    const boxW = Math.min(MAX_WIDTH, Math.max(...lines.map((l) => ctx.measureText(l).width)) + PAD_X * 2);
    const boxH = lines.length * lineH + PAD_Y * 2;
    const bx = anchorX - boxW / 2;
    const by = anchorY - boxH - 4;

    ctx.globalAlpha = b.alpha * 0.88;

    const intent = b.intent.toLowerCase();
    const isQuestion = intent.includes('question') || intent === '?';
    const isAnswer = intent.includes('answer') || intent.includes('reply');
    const isWarning = intent.includes('warning') || intent.includes('warn') || intent.includes('accusation');
    const isRoleConfusion = b.strainFamily === 'role_confusion';
    const isContextPoisoning = b.strainFamily === 'context_poisoning';

    const icon = isQuestion ? '?' : isAnswer ? '<' : isWarning ? '!' : '*';
    const bgColor = b.infected || isContextPoisoning ? '#21091f' : isWarning ? '#241006' : '#071827';
    const borderColor = b.infected ? '#ef4444' :
      isContextPoisoning ? '#86efac' :
      isWarning ? '#f59e0b' :
      isAnswer ? '#22d3ee' :
      isQuestion ? '#3b82f6' : '#94a3b8';
    const textColor = b.infected || isWarning ? '#fed7aa' :
      isContextPoisoning ? '#d9f99d' :
      isAnswer ? '#cffafe' :
      isQuestion ? '#dbeafe' : '#e2e8f0';

    ctx.fillStyle = bgColor;
    ctx.beginPath();
    if (ctx.roundRect) ctx.roundRect(bx, by, boxW, boxH, 3);
    else ctx.rect(bx, by, boxW, boxH);
    ctx.fill();
    ctx.strokeStyle = borderColor;
    ctx.lineWidth = 1;
    ctx.stroke();

    if (isRoleConfusion || isContextPoisoning) {
      const jitter = isRoleConfusion ? Math.sin(b.age * 32) * 2 : Math.sin(b.age * 7) * 1.2;
      ctx.strokeStyle = isRoleConfusion ? '#f0abfc' : '#a3e635';
      ctx.globalAlpha = b.alpha * 0.55;
      ctx.strokeRect(bx + jitter, by - jitter, boxW, boxH);
      ctx.globalAlpha = b.alpha * 0.88;
    }

    ctx.fillStyle = bgColor;
    ctx.strokeStyle = borderColor;
    ctx.beginPath();
    ctx.moveTo(anchorX - 4, by + boxH);
    ctx.lineTo(anchorX, by + boxH + 5);
    ctx.lineTo(anchorX + 4, by + boxH);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = borderColor;
    ctx.font = `bold ${FONT_SIZE + 1}px monospace`;
    ctx.fillText(icon, bx + PAD_X, by + PAD_Y + lineH - 2);
    ctx.font = `${FONT_SIZE}px monospace`;
    ctx.fillStyle = textColor;
    for (let i = 0; i < lines.length; i++) {
      ctx.fillText(lines[i], bx + PAD_X + 12, by + PAD_Y + (i + 1) * lineH - 2);
    }

    ctx.globalAlpha = 1.0;
  }
  ctx.restore();
}
