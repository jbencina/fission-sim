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
  });

  it('rejects non-numeric values for numeric telemetry fields', () => {
    expect(isFrame(makeFrame({ power_thermal: '3000 MW' }))).toBe(false);
    expect(isFrame(makeFrame({ T_hot: null }))).toBe(false);
  });

  it('rejects non-finite numeric values', () => {
    expect(isFrame(makeFrame({ P_primary_MPa: Number.NaN }))).toBe(false);
    expect(isFrame(makeFrame({ rho_total: Number.POSITIVE_INFINITY }))).toBe(false);
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
  });
});
