/**
 * Zustand store for simulation telemetry.
 *
 * Holds the latest Frame received over the WebSocket plus a rolling history
 * buffer capped at HISTORY_CAP frames (600 = 60 s at 10 Hz). Also tracks
 * WebSocket connection status and any last error message.
 *
 * This store is intentionally side-effect free — selectors are pure reads,
 * and all mutations go through the named action functions. The WebSocket
 * client (`wsClient.ts`) drives mutations by calling these actions.
 */

import { create } from 'zustand';
import type { Command, ConnectionStatus, Frame } from '../types/telemetry';

/** Maximum number of history frames retained. 600 = 60 s at 10 Hz. */
export const HISTORY_CAP = 600;

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

  /** Last error message from the backend or connection layer, or null. */
  lastError: string | null;

  // Actions -----------------------------------------------------------------

  /**
   * Append a new telemetry frame to history and update `latest`.
   * Drops the oldest frame when history exceeds HISTORY_CAP. If simulation time
   * moves backward, treats it as a backend reset and starts a fresh history.
   */
  pushFrame: (frame: Frame) => void;

  /** Update the WebSocket connection status. */
  setStatus: (status: ConnectionStatus) => void;

  /** Record an error message (or clear with null). */
  setError: (error: string | null) => void;

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

  /** Reset store to initial state (useful for full simulator reset). */
  reset: () => void;
}

// ---------------------------------------------------------------------------
// Initial state values (extracted so `reset` can return to them)
// ---------------------------------------------------------------------------

const initialState = {
  latest: null as Frame | null,
  history: [] as Frame[],
  status: 'connecting' as ConnectionStatus,
  lastError: null as string | null,
};

// Internal: the active send function, wired in by App.tsx after connection.
// Stored outside state so it doesn't trigger re-renders when updated.
let _send: ((cmd: Command) => void) | null = null;

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useTelemetryStore = create<TelemetryState>()((set) => ({
  ...initialState,

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

  setStatus: (status: ConnectionStatus) => set({ status }),

  setError: (error: string | null) => set({ lastError: error }),

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

  reset: () =>
    set({
      ...initialState,
      // Keep status as 'connecting' so the reconnect chip renders correctly
      // after a full reset — the socket is still open.
    }),
}));
