export interface PixelHostMessage {
  type: string;
  [key: string]: unknown;
}

type PixelHostHandler = (message: PixelHostMessage) => void;

const handlers = new Set<PixelHostHandler>();

export function emitPixelHostMessage(message: PixelHostMessage): void {
  for (const handler of handlers) {
    handler(message);
  }
}

export function registerPixelHostHandler(handler: PixelHostHandler): () => void {
  handlers.add(handler);
  return () => {
    handlers.delete(handler);
  };
}
