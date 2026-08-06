import type { ServerMessage } from "./types";

type Handler = (payload: unknown) => void;

/** WebSocket client with auto-reconnect and per-message-type listeners. */
export class WsClient {
  private ws: WebSocket | null = null;
  private handlers = new Map<string, Set<Handler>>();
  private statusHandlers = new Set<(connected: boolean) => void>();
  private closed = false;

  connect(): void {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    this.ws = new WebSocket(`${proto}://${location.host}/ws`);
    this.ws.onopen = () => this.statusHandlers.forEach((h) => h(true));
    this.ws.onclose = () => {
      this.statusHandlers.forEach((h) => h(false));
      if (!this.closed) setTimeout(() => this.connect(), 1000);
    };
    this.ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data) as ServerMessage;
      this.handlers.get(msg.type)?.forEach((h) => h(msg.payload));
    };
  }

  send(type: string, payload: Record<string, unknown>): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type, payload }));
    }
  }

  on(type: string, handler: Handler): () => void {
    if (!this.handlers.has(type)) this.handlers.set(type, new Set());
    this.handlers.get(type)!.add(handler);
    return () => this.handlers.get(type)?.delete(handler);
  }

  onStatus(handler: (connected: boolean) => void): () => void {
    this.statusHandlers.add(handler);
    return () => this.statusHandlers.delete(handler);
  }

  close(): void {
    this.closed = true;
    this.ws?.close();
  }
}

export const ws = new WsClient();
