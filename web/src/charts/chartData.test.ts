import { describe, expect, it } from 'vitest';
import {
  toPowerPoints,
  toPressurePoints,
  toReactivityPoints,
  toTemperaturePoints,
} from './chartData';
import type { Frame } from '../types/telemetry';

function makeFrame(t: number, overrides: Partial<Frame> = {}): Frame {
  return {
    t,
    power_thermal: 3_000_000_000 + t * 1_000_000,
    T_hot: 600 + t,
    T_cold: 568 + t,
    T_avg: 584 + t,
    T_fuel: 1100 + t,
    rod_position: 0.5,
    P_primary_Pa: 15_500_000 + t * 1_000,
    P_primary_MPa: 15.5 + t * 0.001,
    Q_sg: 3_000_000_000,
    rho_rod: t * 1e-6,
    rho_doppler: -t * 1e-6,
    rho_moderator: -t * 2e-6,
    rho_total: -t * 2e-6,
    running: true,
    speed: 1,
    scrammed: false,
    rod_command: 0.5,
    ...overrides,
  };
}

describe('chart data transforms', () => {
  it('recomputes chart values for histories with the same length but newer frames', () => {
    const before = [makeFrame(10), makeFrame(11)];
    const after = [makeFrame(11), makeFrame(12)];

    expect(toPowerPoints(before)).not.toEqual(toPowerPoints(after));
    expect(toTemperaturePoints(before)).not.toEqual(toTemperaturePoints(after));
    expect(toPressurePoints(before)).not.toEqual(toPressurePoints(after));
    expect(toReactivityPoints(before)).not.toEqual(toReactivityPoints(after));
  });

  it('anchors relative time to the newest frame', () => {
    expect(toPowerPoints([makeFrame(10), makeFrame(11)])).toEqual([
      { t_rel: -1, power_MW: 3010 },
      { t_rel: 0, power_MW: 3011 },
    ]);
  });
});
