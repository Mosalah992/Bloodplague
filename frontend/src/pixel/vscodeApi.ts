import { emitPixelHostMessage } from './host/pixelHostBridge.js';

export const vscode = {
  postMessage(message: { type: string; [key: string]: unknown }): void {
    emitPixelHostMessage(message);
  },
};
