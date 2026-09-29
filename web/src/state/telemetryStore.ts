/**
 * Zustand store for simulation telemetry.
 *
 * Holds the latest Frame received over the WebSocket plus a rolling,
 * simulated-time history buffer long enough for the 15-minute chart window.
 * Also tracks WebSocket connection status and the message currently shown to
 * the user in the error notice.
 *
 * This store is intentionally side-effect free — selectors are pure reads,
 * and all mutations go through the named action functions. The WebSocket
 * client (`wsClient.ts`) drives mutations by calling these actions.
 */

import { create } from 'zustand';
import type { AppErrorSource, Command, ConnectionStatus, Frame } from '../types/telemetry';
import {
  EVENTS_CAP,
  type EventTracker,
  type PlantEvent,
  detectEvents,
  initialEventTracker,
  mergeCoalescedEvents,
} from './events';

/**
 * Simulated time kept for chart history [s].
 *
 * 905 s covers the 15-minute operator chart window plus the small display
 * margin used to draw the trace entering from the left edge. At 1× and the
 * runtime's 10 Hz publish cadence this is about 9,050 frames; at 10× it is
 * about 905 frames.
 */
export const HISTORY_RETENTION_S = 15 * 60 + 5;

/**
 * Hard frame bound for unusual cases such as many paused command frames with
 * identical simulation time. Ordinary 1× operation stays below this while
 * preserving the full 15-minute simulated-time history.
 */
export const HISTORY_MAX_FRAMES = 12_000;

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
   * Trimmed by simulated time and then by HISTORY_MAX_FRAMES to prevent
   * unbounded memory growth while keeping the 15-minute chart window.
   */
  history: Frame[];

  /** Plant events derived from the frames, oldest first, at most EVENTS_CAP. */
  events: PlantEvent[];

  /** Explicit event hysteresis/debounce state carried between frames. */
  eventTracker: EventTracker;

  /**
   * Previous frame used only for event detection.
   * Cleared on WebSocket disconnect so reconnects seed a fresh tracker
   * instead of logging transitions across an unobserved gap.
   */
  eventBaseline: Frame | null;

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
   * Append a new telemetry frame to history, update `latest`, and append
   * any events the new frame reveals (events.ts). Drops the oldest frame
   * when history exceeds the retained simulated-time span. If simulation
   * time moves backward, treats it as a backend reset and starts a fresh
   * history and event list.
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

/**
 * Return a history buffer with `frame` appended and stale simulated time
 * removed. The input history is oldest first and the output preserves that
 * ordering.
 */
export function trimHistory(history: readonly Frame[], frame: Frame): Frame[] {
  const appended = [...history, frame];
  const oldestKeptT = frame.t - HISTORY_RETENTION_S;
  const timeTrimmed = appended.filter((candidate) => candidate.t >= oldestKeptT);
  return timeTrimmed.length > HISTORY_MAX_FRAMES
    ? timeTrimmed.slice(timeTrimmed.length - HISTORY_MAX_FRAMES)
    : timeTrimmed;
}

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

export const useTelemetryStore = create<TelemetryState>()((set) => ({
  latest: null,
  history: [],
  events: [],
  eventTracker: initialEventTracker(),
  eventBaseline: null,
  status: 'connecting',
  lastError: null,
  connectionNoticeDismissed: false,

  pushFrame: (frame: Frame) =>
    set((state) => {
      // Backend reset is visible as simulation time moving backward. Start a
      // fresh history so charts do not mix pre-reset and post-reset points.
      const timeRolledBack = state.latest !== null && frame.t < state.latest.t;
      const history = timeRolledBack ? [frame] : trimHistory(state.history, frame);
      // Events restart on a reset too; otherwise the newest ones are kept.
      const fresh = detectEvents(state.eventBaseline, frame, state.eventTracker);
      let events = state.events;
      if (timeRolledBack) events = fresh.events;
      else if (fresh.events.length > 0) events = mergeCoalescedEvents(state.events, fresh.events).slice(-EVENTS_CAP);
      return { latest: frame, history, events, eventTracker: fresh.tracker, eventBaseline: frame };
    }),

  setStatus: (status: ConnectionStatus) =>
    set((state) => {
      if (status !== 'connected') {
        return { status, eventBaseline: null, eventTracker: initialEventTracker() };
      }
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
