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
import { EVENTS_CAP } from './events';
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

  it('invalidates the event baseline and tracker when the socket disconnects', () => {
    const store = useTelemetryStore.getState();
    store.pushFrame(makeFrame(1, { m_dump: 1.2 }));
    expect(useTelemetryStore.getState().eventBaseline?.t).toBe(1);
    expect(useTelemetryStore.getState().eventTracker.dumpOpen).toBe(true);

    store.setStatus('disconnected');

    expect(useTelemetryStore.getState().eventBaseline).toBeNull();
    expect(useTelemetryStore.getState().eventTracker.dumpOpen).toBe(false);
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

describe('events', () => {
  it('appends derived events and restarts them on a reset', () => {
    const { pushFrame } = useTelemetryStore.getState();
    pushFrame(makeFrame(1));
    pushFrame(makeFrame(2, { scrammed: true, rod_position: 0.3 }));
    expect(useTelemetryStore.getState().events.map((e) => e.text)).toEqual([
      'Telemetry link established',
      'SCRAM latched, both banks dropping',
    ]);
    pushFrame(makeFrame(0.1));
    expect(useTelemetryStore.getState().events.map((e) => e.text)).toEqual([
      'Simulation reset to the design state',
    ]);
  });

  it('keeps at most EVENTS_CAP events', () => {
    const { pushFrame } = useTelemetryStore.getState();
    pushFrame(makeFrame(1));
    for (let i = 2; i < 2 + EVENTS_CAP + 20; i++) pushFrame(makeFrame(i, { speed: i % 2 ? 1 : 2 }));
    expect(useTelemetryStore.getState().events).toHaveLength(EVENTS_CAP);
  });

  it('seeds feedwater saturation tracker from the first frame after reconnect without stale dwell events', () => {
    const { pushFrame, setStatus } = useTelemetryStore.getState();
    pushFrame(makeFrame(1, { fw_saturated: false, m_fw_demand: 100, m_fw_max: 2_000 }));
    pushFrame(makeFrame(1.1, { fw_saturated: true, m_fw_demand: 2_000, m_fw_max: 2_000 }));
    expect(useTelemetryStore.getState().events.map((event) => event.text)).not.toContain(
      'Feedwater demand saturated at maximum',
    );

    setStatus('disconnected');
    pushFrame(makeFrame(10, { fw_saturated: true, m_fw_demand: 2_000, m_fw_max: 2_000 }));

    expect(useTelemetryStore.getState().eventTracker.feedwaterSaturation).toBe('maximum');
    expect(useTelemetryStore.getState().events.map((event) => event.text)).toEqual([
      'Telemetry link established',
      'Telemetry link established',
    ]);
  });

  it('seeds dump hysteresis from the first frame after reconnect instead of retaining stale open state', () => {
    const { pushFrame, setStatus } = useTelemetryStore.getState();
    pushFrame(makeFrame(1, { m_dump: 1.2 }));
    expect(useTelemetryStore.getState().eventTracker.dumpOpen).toBe(true);

    setStatus('disconnected');
    pushFrame(makeFrame(10, { m_dump: 0.75 }));

    expect(useTelemetryStore.getState().eventTracker.dumpOpen).toBe(false);
    expect(useTelemetryStore.getState().events.map((event) => event.text)).toEqual([
      'Telemetry link established',
      'Telemetry link established',
    ]);
  });
});
