/**
 * Unit tests for the telemetry Zustand store.
 *
 * Tests cover:
 * - pushFrame appends to history and updates latest
 * - history caps at HISTORY_CAP (600 frames)
 * - setStatus updates the status field
 * - reportError/clearError manage the error notice without letting a stale
 *   connection message hide or outlive a server explanation
 * - time rollback (backend reset) clears stale chart history
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { HISTORY_CAP, useTelemetryStore } from './telemetryStore';
import { makeFrame } from '../test/makeFrame';

// ---------------------------------------------------------------------------
// Reset Zustand store state before each test so tests don't bleed into each
// other — Zustand stores are module-level singletons.
// ---------------------------------------------------------------------------
beforeEach(() => {
  useTelemetryStore.setState(useTelemetryStore.getInitialState(), true);
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('pushFrame', () => {
  it('appends a frame and sets latest', () => {
    const frame = makeFrame(1.0);
    useTelemetryStore.getState().pushFrame(frame);

    const { latest, history } = useTelemetryStore.getState();
    expect(latest).toEqual(frame);
    expect(history).toHaveLength(1);
    expect(history[0]).toEqual(frame);
  });

  it('appends multiple frames in order', () => {
    useTelemetryStore.getState().pushFrame(makeFrame(1));
    useTelemetryStore.getState().pushFrame(makeFrame(2));
    useTelemetryStore.getState().pushFrame(makeFrame(3));

    const { history, latest } = useTelemetryStore.getState();
    expect(history).toHaveLength(3);
    expect(history[0].t).toBe(1);
    expect(history[2].t).toBe(3);
    expect(latest?.t).toBe(3);
  });

  it(`caps history at ${HISTORY_CAP} frames and drops oldest`, () => {
    // Push one extra frame beyond the cap.
    for (let i = 0; i <= HISTORY_CAP; i++) {
      useTelemetryStore.getState().pushFrame(makeFrame(i));
    }

    const { history } = useTelemetryStore.getState();
    expect(history).toHaveLength(HISTORY_CAP);
    // The very first frame (t=0) should have been dropped.
    expect(history[0].t).toBe(1);
    // The last frame should be the newest.
    expect(history[history.length - 1].t).toBe(HISTORY_CAP);
  });

  it('clears stale history when simulation time moves backward', () => {
    useTelemetryStore.getState().pushFrame(makeFrame(10));
    useTelemetryStore.getState().pushFrame(makeFrame(11));

    const resetFrame = makeFrame(0.1);
    useTelemetryStore.getState().pushFrame(resetFrame);

    const { history, latest } = useTelemetryStore.getState();
    expect(latest).toEqual(resetFrame);
    expect(history).toEqual([resetFrame]);
  });
});

describe('setStatus', () => {
  it('updates status to connected', () => {
    useTelemetryStore.getState().setStatus('connected');
    expect(useTelemetryStore.getState().status).toBe('connected');
  });

  it('updates status to disconnected', () => {
    useTelemetryStore.getState().setStatus('disconnected');
    expect(useTelemetryStore.getState().status).toBe('disconnected');
  });

  it('initial status is connecting', () => {
    // beforeEach restored the store's initial state.
    expect(useTelemetryStore.getState().status).toBe('connecting');
  });
});

describe('error notice', () => {
  it('shows a server explanation until dismissed', () => {
    const store = useTelemetryStore.getState();
    store.reportError('server', 'rod command out of range');
    store.setStatus('connected');
    expect(useTelemetryStore.getState().lastError).toEqual({
      source: 'server',
      message: 'rod command out of range',
    });

    store.clearError();
    expect(useTelemetryStore.getState().lastError).toBeNull();
  });

  it('clears a connection message once the socket reconnects', () => {
    const store = useTelemetryStore.getState();
    store.reportError('connection', 'lost connection');
    store.setStatus('connecting');
    expect(useTelemetryStore.getState().lastError?.source).toBe('connection');

    store.setStatus('connected');
    expect(useTelemetryStore.getState().lastError).toBeNull();
  });

  it('lets a server explanation replace a connection message', () => {
    const store = useTelemetryStore.getState();
    store.reportError('connection', 'cannot reach backend');
    store.reportError('server', 'rod command out of range');
    expect(useTelemetryStore.getState().lastError?.source).toBe('server');
  });

  it('keeps a dismissed connection message hidden until the next connect', () => {
    const store = useTelemetryStore.getState();
    store.reportError('connection', 'cannot reach backend');
    store.clearError();
    store.reportError('connection', 'cannot reach backend'); // next failed retry
    expect(useTelemetryStore.getState().lastError).toBeNull();

    store.setStatus('connected');
    store.reportError('connection', 'cannot reach backend'); // a new outage
    expect(useTelemetryStore.getState().lastError?.source).toBe('connection');
  });

  it('does not let a connection message replace a server explanation', () => {
    const store = useTelemetryStore.getState();
    store.reportError('server', 'speed must be one of 1, 2, 5, 10');
    store.reportError('connection', 'lost connection');
    expect(useTelemetryStore.getState().lastError?.message).toBe(
      'speed must be one of 1, 2, 5, 10',
    );
  });
});

describe('clearHistory', () => {
  it('clears chart history without dropping the latest telemetry or connection state', () => {
    const latest = makeFrame(6);
    useTelemetryStore.getState().pushFrame(makeFrame(5));
    useTelemetryStore.getState().pushFrame(latest);
    useTelemetryStore.getState().setStatus('connected');
    useTelemetryStore.getState().reportError('server', 'old warning');

    useTelemetryStore.getState().clearHistory();

    const state = useTelemetryStore.getState();
    expect(state.history).toHaveLength(0);
    expect(state.latest).toEqual(latest);
    expect(state.status).toBe('connected');
    expect(state.lastError?.message).toBe('old warning');
  });
});
