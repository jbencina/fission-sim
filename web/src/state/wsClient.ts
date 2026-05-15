/**
 * WebSocket client for the fission-sim telemetry stream.
 *
 * Connects to `ws://<host>/ws/telemetry` (the Vite dev proxy forwards this
 * to the FastAPI backend at localhost:8000 during development; in production
 * the same origin serves both). Receives JSON telemetry frames and pushes
 * them to the store via the provided callbacks.
 *
 * Reconnect strategy
 * ------------------
 * Uses exponential backoff starting at 500 ms and doubling up to 5000 ms.
 * The backoff resets to 500 ms on each successful connection open. Calling
 * the returned `close()` function disables reconnection and closes cleanly.
 */

import { isFrame } from '../types/telemetry';
import type { Command, ConnectionStatus, Frame } from '../types/telemetry';

/** Minimum reconnect delay [ms]. */
const BACKOFF_MIN_MS = 500;

/** Maximum reconnect delay [ms]. */
const BACKOFF_MAX_MS = 5_000;

/** WebSocket path — Vite proxy forwards to the FastAPI backend. */
const WS_PATH = '/ws/telemetry';

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export interface TelemetryClient {
  /**
   * Send a command to the backend.
   * No-op if the socket is not currently OPEN (rather than queuing the
   * command, we drop it — the UI should gate controls on the connected status).
   */
  send: (cmd: Command) => void;

  /**
   * Permanently close the WebSocket and disable reconnection.
   * Call this in the React component's cleanup effect.
   */
  close: () => void;
}

/**
 * Open a persistent WebSocket connection to the telemetry endpoint.
 *
 * @param onFrame   - Called with each valid Frame received from the server.
 * @param onStatus  - Called whenever the connection state changes.
 * @param onError   - Called with an error description string on error events
 *                    or when the server sends `{"type": "error", ...}`.
 * @returns         TelemetryClient with `send` and `close` methods.
 */
export function connectTelemetry(
  onFrame: (f: Frame) => void,
  onStatus: (s: ConnectionStatus) => void,
  onError: (e: string) => void,
): TelemetryClient {
  // Whether the caller has requested a permanent close (no more reconnects).
  let destroyed = false;

  // Current backoff delay [ms] — doubles after each failed attempt.
  let backoffMs = BACKOFF_MIN_MS;

  // Active socket (may be null between reconnect attempts).
  let socket: WebSocket | null = null;

  // Reconnect timer handle — cleared on successful open or permanent close.
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  // -------------------------------------------------------------------------
  // Internal: build the WebSocket URL from the current page origin.
  // In production `location.host` is the API host. In dev, Vite proxies /ws/*.
  // -------------------------------------------------------------------------
  function buildUrl(): string {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${location.host}${WS_PATH}`;
  }

  // -------------------------------------------------------------------------
  // Internal: open one WebSocket attempt.
  // -------------------------------------------------------------------------
  function connect(): void {
    if (destroyed) return;

    onStatus('connecting');
    const ws = new WebSocket(buildUrl());
    socket = ws;

    ws.onopen = () => {
      if (destroyed) {
        ws.close();
        return;
      }
      // Reset backoff — connection succeeded.
      backoffMs = BACKOFF_MIN_MS;
      onStatus('connected');
    };

    ws.onmessage = (event: MessageEvent) => {
      // Parse JSON; validate with the type guard before calling onFrame.
      let parsed: unknown;
      try {
        parsed = JSON.parse(event.data as string) as unknown;
      } catch {
        // Malformed JSON — log and ignore; do not disconnect.
        console.warn('[wsClient] Received non-JSON message; ignoring.');
        return;
      }

      // Check if the server sent an error envelope.
      if (
        typeof parsed === 'object' &&
        parsed !== null &&
        (parsed as Record<string, unknown>)['type'] === 'error'
      ) {
        const detail = (parsed as Record<string, unknown>)['detail'];
        onError(typeof detail === 'string' ? detail : 'Unknown server error');
        return;
      }

      // Successful command acknowledgements are control-plane messages, not
      // telemetry samples. They intentionally do not update chart/history state.
      if (
        typeof parsed === 'object' &&
        parsed !== null &&
        (parsed as Record<string, unknown>)['type'] === 'ack'
      ) {
        return;
      }

      // Validate that the message is a full telemetry Frame.
      if (isFrame(parsed)) {
        onFrame(parsed);
      } else {
        console.warn('[wsClient] Received message missing required Frame keys; ignoring.', parsed);
      }
    };

    ws.onerror = () => {
      // onerror fires before onclose; actual reconnect is scheduled in onclose.
      onError('WebSocket error — will reconnect');
    };

    ws.onclose = () => {
      socket = null;
      if (destroyed) return;

      onStatus('disconnected');

      // Schedule reconnect with exponential backoff.
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        // Double the backoff for the next potential failure.
        backoffMs = Math.min(backoffMs * 2, BACKOFF_MAX_MS);
        connect();
      }, backoffMs);
    };
  }

  // Start the first connection attempt immediately.
  connect();

  // -------------------------------------------------------------------------
  // Public send — delegates to the active socket if it is OPEN.
  // -------------------------------------------------------------------------
  function send(cmd: Command): void {
    if (socket !== null && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(cmd));
    }
    // Silently drop when not connected — the UI should be gating controls
    // on `status === 'connected'` from the Zustand store.
  }

  // -------------------------------------------------------------------------
  // Public close — disable reconnect and shut down cleanly.
  // -------------------------------------------------------------------------
  function close(): void {
    destroyed = true;

    // Cancel any pending reconnect timer.
    if (reconnectTimer !== null) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }

    // Close the active socket if present.
    if (socket !== null) {
      socket.close();
      socket = null;
    }
  }

  return { send, close };
}
