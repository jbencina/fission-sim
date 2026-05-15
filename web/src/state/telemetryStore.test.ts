/**
 * Unit tests for the telemetry Zustand store.
 *
 * Tests cover:
 * - pushFrame appends to history and updates latest
 * - history caps at HISTORY_CAP (600 frames)
 * - setStatus updates the status field
 * - setError updates the lastError field
 * - reset returns state to defaults
 * - reset/time rollback clears stale chart history
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { HISTORY_CAP, useTelemetryStore } from './telemetryStore';
import type { Frame } from '../types/telemetry';

// ---------------------------------------------------------------------------
// Helper: build a minimal valid Frame for testing
// ---------------------------------------------------------------------------
function makeFrame(t: number): Frame {
  return {
    t,
    power_thermal: 3_000_000_000,
    T_hot: 600,
    T_cold: 560,
    T_avg: 580,
    T_fuel: 900,
    rod_position: 0.5,
    P_primary_Pa: 15_500_000,
    P_primary_MPa: 15.5,
    Q_sg: 2_900_000_000,
    rho_rod: 0.001,
    rho_doppler: -0.0005,
    rho_moderator: -0.0003,
    rho_total: 0.0002,
    running: true,
    speed: 1,
    scrammed: false,
    rod_command: 0.5,
  };
}

// ---------------------------------------------------------------------------
// Reset Zustand store state before each test so tests don't bleed into each
// other — Zustand stores are module-level singletons.
// ---------------------------------------------------------------------------
beforeEach(() => {
  useTelemetryStore.getState().reset();
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
    // After reset(), status should be the initial value.
    expect(useTelemetryStore.getState().status).toBe('connecting');
  });
});

describe('setError', () => {
  it('sets an error message', () => {
    useTelemetryStore.getState().setError('connection refused');
    expect(useTelemetryStore.getState().lastError).toBe('connection refused');
  });

  it('clears error with null', () => {
    useTelemetryStore.getState().setError('some error');
    useTelemetryStore.getState().setError(null);
    expect(useTelemetryStore.getState().lastError).toBeNull();
  });
});

describe('reset', () => {
  it('resets latest and history to defaults', () => {
    useTelemetryStore.getState().pushFrame(makeFrame(5));
    useTelemetryStore.getState().pushFrame(makeFrame(6));
    useTelemetryStore.getState().reset();

    const { latest, history } = useTelemetryStore.getState();
    expect(latest).toBeNull();
    expect(history).toHaveLength(0);
  });

  it('resets status to connecting', () => {
    useTelemetryStore.getState().setStatus('connected');
    useTelemetryStore.getState().reset();
    expect(useTelemetryStore.getState().status).toBe('connecting');
  });

  it('resets lastError to null', () => {
    useTelemetryStore.getState().setError('an error');
    useTelemetryStore.getState().reset();
    expect(useTelemetryStore.getState().lastError).toBeNull();
  });
});

describe('clearHistory', () => {
  it('clears chart history without dropping the latest telemetry or connection state', () => {
    const latest = makeFrame(6);
    useTelemetryStore.getState().pushFrame(makeFrame(5));
    useTelemetryStore.getState().pushFrame(latest);
    useTelemetryStore.getState().setStatus('connected');
    useTelemetryStore.getState().setError('old warning');

    useTelemetryStore.getState().clearHistory();

    const state = useTelemetryStore.getState();
    expect(state.history).toHaveLength(0);
    expect(state.latest).toEqual(latest);
    expect(state.status).toBe('connected');
    expect(state.lastError).toBe('old warning');
  });
});
