/**
 * Zustand store for simulation telemetry.
 *
 * Holds the latest Frame received over the WebSocket plus a rolling history
 * buffer capped at HISTORY_CAP frames. Also tracks WebSocket connection status
 * and the message currently shown to the user in the error notice.
 *
 * This store is intentionally side-effect free — selectors are pure reads,
 * and all mutations go through the named action functions. The WebSocket
 * client (`wsClient.ts`) drives mutations by calling these actions.
 */

import { create } from 'zustand';
import type { AppErrorSource, Command, ConnectionStatus, Frame } from '../types/telemetry';

/**
 * Maximum number of history frames retained.
 *
 * 600 frames = 60 s of telemetry at the backend's 10 Hz publish rate. At
 * faster simulation speeds the same 600 frames cover more simulated time;
 * the charts still plot only the last CHART_WINDOW_S of it (chartData.ts).
 */
export const HISTORY_CAP = 600;

// ---------------------------------------------------------------------------
// Error messages
// ---------------------------------------------------------------------------

/** A message for the error notice, tagged with its source. */
export interface AppError {
  source: AppErrorSource;
  message: string;
}

// ---------------------------------------------------------------------------
// Store shape
// ---------------------------------------------------------------------------

export interface TelemetryState {
  /** Most recent telemetry frame, or null before the first frame arrives. */
  latest: Frame | null;

  /**
   * Rolling history of frames, newest at the end.
   * Capped at HISTORY_CAP entries; oldest frame is dropped when the cap
   * is exceeded to prevent unbounded memory growth.
   */
  history: Frame[];

  /** Current WebSocket connection state. */
  status: ConnectionStatus;

  /** Message currently shown in the error notice, or null for none. */
  lastError: AppError | null;

  /**
   * True after the user dismisses a connection message, until the socket
   * next connects. While the backend stays unreachable every retry reports
   * the same failure; this keeps the dismissed message from reappearing.
   */
  connectionNoticeDismissed: boolean;

  // Actions -----------------------------------------------------------------

  /**
   * Append a new telemetry frame to history and update `latest`.
   * Drops the oldest frame when history exceeds HISTORY_CAP. If simulation time
   * moves backward, treats it as a backend reset and starts a fresh history.
   */
  pushFrame: (frame: Frame) => void;

  /**
   * Update the WebSocket connection status.
   * Becoming 'connected' clears a connection message, since it is no longer
   * true, and re-arms connection messages after a dismissal; a server
   * explanation is kept until the user dismisses it.
   */
  setStatus: (status: ConnectionStatus) => void;

  /**
   * Record a message for the error notice.
   * A connection message never replaces a server explanation: the status
   * chip already says the socket is down, while the server's explanation
   * (for example, why a command was refused) would otherwise be lost.
   * Connection messages are also ignored after the user dismissed one,
   * until the next successful connect.
   */
  reportError: (source: AppErrorSource, message: string) => void;

  /** Remove the current message (the notice's Dismiss button). */
  clearError: () => void;

  /** Clear rolling chart history while preserving the latest telemetry frame. */
  clearHistory: () => void;

  /**
   * Send a command to the backend via the WebSocket.
   * This delegates to the `send` function registered by `setSend`.
   * If no `send` has been registered yet (socket not yet open), the command
   * is silently dropped — the UI should gate controls on `status === 'connected'`.
   */
  sendCommand: (cmd: Command) => void;

  /**
   * Register the WebSocket client's send function.
   * Called by `App.tsx` once `connectTelemetry` returns, so `sendCommand`
   * has something to delegate to.
   */
  setSend: (fn: (cmd: Command) => void) => void;
}

// Internal: the active send function, wired in by App.tsx after connection.
// Stored outside state so it doesn't trigger re-renders when updated.
let _send: ((cmd: Command) => void) | null = null;

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useTelemetryStore = create<TelemetryState>()((set) => ({
  latest: null,
  history: [],
  status: 'connecting',
  lastError: null,
  connectionNoticeDismissed: false,

  pushFrame: (frame: Frame) =>
    set((state) => {
      // Backend reset is visible as simulation time moving backward. Start a
      // fresh history so charts do not mix pre-reset and post-reset points.
      const timeRolledBack = state.latest !== null && frame.t < state.latest.t;
      const history = timeRolledBack
        ? [frame]
        : state.history.length < HISTORY_CAP
          ? [...state.history, frame]
          : [...state.history.slice(1), frame];
      return { latest: frame, history };
    }),

  setStatus: (status: ConnectionStatus) =>
    set((state) => {
      if (status !== 'connected') return { status };
      return {
        status,
        connectionNoticeDismissed: false,
        lastError: state.lastError?.source === 'connection' ? null : state.lastError,
      };
    }),

  reportError: (source: AppErrorSource, message: string) =>
    set((state) => {
      if (source === 'connection') {
        if (state.lastError?.source === 'server' || state.connectionNoticeDismissed) {
          return {};
        }
      }
      return { lastError: { source, message } };
    }),

  clearError: () =>
    set((state) => ({
      lastError: null,
      // Only a dismissed *connection* message silences later retries.
      connectionNoticeDismissed:
        state.connectionNoticeDismissed || state.lastError?.source === 'connection',
    })),

  clearHistory: () => set({ history: [] }),

  sendCommand: (cmd: Command) => {
    // Delegate to the registered send function; drop silently if not wired yet.
    _send?.(cmd);
  },

  setSend: (fn: (cmd: Command) => void) => {
    // Store the send function outside Zustand state so setting it does not
    // cause the entire tree to re-render.
    _send = fn;
  },
}));
