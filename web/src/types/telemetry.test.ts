import { describe, expect, it } from 'vitest';
import { isFrame } from './telemetry';
import type { Frame } from './telemetry';

function makeFrame(overrides: Partial<Record<keyof Frame, unknown>> = {}): Record<string, unknown> {
  return {
    t: 1,
    power_thermal: 3_000_000_000,
    T_hot: 600,
    T_cold: 568,
    T_avg: 584,
    T_fuel: 1100,
    rod_position: 0.5,
    P_primary_Pa: 15_500_000,
    P_primary_MPa: 15.5,
    Q_sg: 3_000_000_000,
    rho_rod: 0,
    rho_doppler: 0,
    rho_moderator: 0,
    rho_total: 0,
    running: true,
    speed: 1,
    scrammed: false,
    rod_command: 0.5,
    ...overrides,
  };
}

describe('isFrame', () => {
  it('accepts a complete telemetry frame with finite numeric values', () => {
    expect(isFrame(makeFrame())).toBe(true);
  });

  it('rejects frames with missing required keys', () => {
    const frame = makeFrame();
    delete frame.power_thermal;
    expect(isFrame(frame)).toBe(false);
  });

  it('rejects non-numeric values for numeric telemetry fields', () => {
    expect(isFrame(makeFrame({ power_thermal: '3000 MW' }))).toBe(false);
    expect(isFrame(makeFrame({ T_hot: null }))).toBe(false);
  });

  it('rejects non-finite numeric values', () => {
    expect(isFrame(makeFrame({ P_primary_MPa: Number.NaN }))).toBe(false);
    expect(isFrame(makeFrame({ rho_total: Number.POSITIVE_INFINITY }))).toBe(false);
  });

  it('rejects non-boolean values for boolean telemetry fields', () => {
    expect(isFrame(makeFrame({ running: 'true' }))).toBe(false);
    expect(isFrame(makeFrame({ scrammed: 0 }))).toBe(false);
  });
});
