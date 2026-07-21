import "@testing-library/jest-dom/vitest";

// Polyfill for WebSocket in test environment
globalThis.WebSocket = class MockWebSocket {
  url: string;
  onopen: (() => void) | null = null;
  onclose: ((e: { code: number; reason: string }) => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: ((e: unknown) => void) | null = null;
  constructor(url: string) { this.url = url; }
  send() {}
  close() {}
} as unknown as typeof WebSocket;
