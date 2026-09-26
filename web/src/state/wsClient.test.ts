/**
 * Unit tests for the WebSocket client's error reporting.
 *
 * Uses a minimal fake WebSocket (no browser needed) to check that error
 * events are reported only for the socket the client is still using.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { connectTelemetry } from './wsClient';

/** Records every socket the client opens so tests can fire events on it. */
class FakeWebSocket {
  static readonly OPEN = 1;
  static instances: FakeWebSocket[] = [];

  readyState = 0; // CONNECTING
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  close(): void {
    this.readyState = 3; // CLOSED
  }
}

beforeEach(() => {
  FakeWebSocket.instances = [];
  vi.stubGlobal('WebSocket', FakeWebSocket);
  vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:5173' });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('connectTelemetry error reporting', () => {
  it('ignores the error event from a socket the app closed itself', () => {
    // React StrictMode in development: mount, immediately unmount (close),
    // then the browser fires `error` on the abandoned connecting socket.
    const onError = vi.fn();
    const client = connectTelemetry(vi.fn(), vi.fn(), onError);
    const abandoned = FakeWebSocket.instances[0];

    client.close();
    abandoned.onerror?.();

    expect(onError).not.toHaveBeenCalled();
  });

  it('reports live socket errors and server explanations with their source', () => {
    const onError = vi.fn();
    const client = connectTelemetry(vi.fn(), vi.fn(), onError);
    const ws = FakeWebSocket.instances[0];

    ws.onmessage?.({ data: JSON.stringify({ type: 'error', detail: 'rod command out of range' }) });
    ws.onerror?.();

    expect(onError.mock.calls).toEqual([
      ['server', 'rod command out of range'],
      ['connection', expect.stringMatching(/retrying/i)],
    ]);
    client.close();
  });
});
