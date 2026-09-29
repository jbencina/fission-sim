import { describe, expect, it } from 'vitest';
import { isFrame } from './telemetry';
import type { Frame } from './telemetry';
import { makeFrame as validFrame } from '../test/makeFrame';

// A frame as parsed JSON: overrides may hold values of the wrong type.
function makeFrame(overrides: Partial<Record<keyof Frame, unknown>> = {}): Record<string, unknown> {
  return { ...validFrame(), ...overrides };
}

describe('isFrame', () => {
  it('accepts a complete telemetry frame with finite numeric values', () => {
    expect(isFrame(makeFrame())).toBe(true);
  });

  it('rejects frames with missing required keys', () => {
    const frame = makeFrame();
    delete frame.power_thermal;
    expect(isFrame(frame)).toBe(false);

    const missingNullable = makeFrame();
    delete missingNullable.feedwater_manual;
    expect(isFrame(missingNullable)).toBe(false);

    const missingEffective = makeFrame();
    delete missingEffective.turbine_load_demand_effective;
    expect(isFrame(missingEffective)).toBe(false);

    const missingShutdownBank = makeFrame();
    delete missingShutdownBank.shutdown_position;
    expect(isFrame(missingShutdownBank)).toBe(false);

    const missingPzrLevel = makeFrame();
    delete missingPzrLevel.pzr_level;
    expect(isFrame(missingPzrLevel)).toBe(false);
  });

  it('rejects non-numeric values for numeric telemetry fields', () => {
    expect(isFrame(makeFrame({ power_thermal: '3000 MW' }))).toBe(false);
    expect(isFrame(makeFrame({ T_hot: null }))).toBe(false);
    expect(isFrame(makeFrame({ m_fw_demand: '1669 kg/s' }))).toBe(false);
    expect(isFrame(makeFrame({ pzr_level: 'half full' }))).toBe(false);
  });

  it('rejects non-finite numeric values', () => {
    expect(isFrame(makeFrame({ P_primary_MPa: Number.NaN }))).toBe(false);
    expect(isFrame(makeFrame({ rho_total: Number.POSITIVE_INFINITY }))).toBe(false);
    expect(isFrame(makeFrame({ P_steam_Pa: Number.NEGATIVE_INFINITY }))).toBe(false);
    expect(isFrame(makeFrame({ turbine_load_demand_effective: Number.NaN }))).toBe(false);
    expect(isFrame(makeFrame({ shutdown_position: Number.NaN }))).toBe(false);
  });

  it('accepts nullable numeric fields only when null or finite numbers', () => {
    expect(
      isFrame(makeFrame({ feedwater_manual: null, feedwater_manual_effective: null, time_to_level_floor_s: null })),
    ).toBe(true);
    expect(
      isFrame(makeFrame({ feedwater_manual: 0.25, feedwater_manual_effective: 0.25, time_to_level_floor_s: 90 })),
    ).toBe(true);
    expect(isFrame(makeFrame({ feedwater_manual: 'AUTO' }))).toBe(false);
    expect(isFrame(makeFrame({ feedwater_manual_effective: 'AUTO' }))).toBe(false);
    expect(isFrame(makeFrame({ time_to_level_floor_s: Number.NaN }))).toBe(false);
    expect(isFrame(makeFrame({ feedwater_manual: Number.POSITIVE_INFINITY }))).toBe(false);
    expect(isFrame(makeFrame({ feedwater_manual_effective: Number.NEGATIVE_INFINITY }))).toBe(false);
  });

  it('accepts a model-limit explanation and requires the field to be string or null', () => {
    expect(isFrame(makeFrame({ model_limit: 'Hot-leg water reached its boiling point.' }))).toBe(true);
    expect(isFrame(makeFrame({ model_limit: 42 }))).toBe(false);
    const frame = makeFrame();
    delete frame.model_limit;
    expect(isFrame(frame)).toBe(false);
  });

  it('rejects non-boolean values for boolean telemetry fields', () => {
    expect(isFrame(makeFrame({ running: 'true' }))).toBe(false);
    expect(isFrame(makeFrame({ scrammed: 0 }))).toBe(false);
    expect(isFrame(makeFrame({ turbine_trip_active: 'false' }))).toBe(false);
    expect(isFrame(makeFrame({ fw_saturated: 0 }))).toBe(false);
  });
});
