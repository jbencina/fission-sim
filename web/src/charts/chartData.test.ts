import { describe, expect, it } from 'vitest';
import { CHART_WINDOW_S, WINDOW_MARGIN_S, toColumns, toMPa, toMW, toPcm, toPercent } from './chartData';
import { CHART_SPECS } from './chartSpecs';
import { makeFrame } from '../test/makeFrame';

describe('toColumns', () => {
  it('lays out one x column and one column per series, aligned by frame', () => {
    const history = [makeFrame(10), makeFrame(11)];
    const columns = toColumns(history, [(f) => f.T_hot, (f) => toMW(f.power_thermal)]);

    expect(columns).toEqual([
      [10, 11],
      [610, 611],
      [3010, 3011],
    ]);
  });

  it('returns empty columns for an empty history', () => {
    expect(toColumns([], [(f) => f.T_hot])).toEqual([[], []]);
  });

  it('keeps only the chart window plus its margin, whatever the speed', () => {
    // At 10x speed the backend still sends ~10 frames per wall-clock second,
    // so consecutive frames are 1 s apart in simulated time and a full
    // 600-frame history spans 599 s. Only the recent window is charted.
    const history = Array.from({ length: 600 }, (_, i) => makeFrame(1000 + i));
    const [xs] = toColumns(history, [(f) => f.T_hot]);

    expect(xs[0]).toBe(1599 - CHART_WINDOW_S - WINDOW_MARGIN_S);
    expect(xs[xs.length - 1]).toBe(1599);
    expect(xs).toHaveLength(CHART_WINDOW_S + WINDOW_MARGIN_S + 1);
  });

  it('draws every frame in the window (no decimation, so nothing flickers)', () => {
    const history = Array.from({ length: 600 }, (_, i) => makeFrame((1000 + i) / 10));
    const [xs] = toColumns(history, [(f) => f.T_hot]);
    expect(xs).toHaveLength(600);
  });
});

describe('unit conversions', () => {
  it('converts common telemetry units to display units', () => {
    expect(toMW(3e9)).toBe(3000);
    expect(toMPa(7.6e6)).toBe(7.6);
    expect(toPcm(-0.0065)).toBeCloseTo(-650);
    expect(toPercent(0.5)).toBe(50);
  });

  it('every chart series reads a finite number from a frame', () => {
    const frame = makeFrame(5);
    for (const spec of CHART_SPECS) {
      for (const series of spec.series) {
        expect(Number.isFinite(series.value(frame)), `${spec.id}/${series.label}`).toBe(true);
      }
    }
  });

  it('chart ids are unique', () => {
    const ids = CHART_SPECS.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('plots T_ref and rod_demand as the charted references', () => {
    const frame = makeFrame(5, { T_ref: 580, rod_command: 0.7, rod_demand: 0.42 });
    const coolant = CHART_SPECS.find((s) => s.id === 'coolant');
    const rods = CHART_SPECS.find((s) => s.id === 'rods');

    expect(coolant?.series.find((s) => s.label === 'T_ref')?.value(frame)).toBe(580);
    expect(rods?.series.find((s) => s.label === 'Demand')?.value(frame)).toBe(42);
  });

  it('defines the ten D.7 dashboard charts', () => {
    expect(CHART_SPECS.map((s) => s.id)).toEqual([
      'power',
      'reactivity',
      'coolant',
      'fuel',
      'pressure',
      'rods',
      'steam-pressure',
      'sg-level',
      'steam-feed-flow',
      'electric-output',
    ]);
  });
});
