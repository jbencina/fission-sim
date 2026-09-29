import { describe, expect, it } from 'vitest';
import { AutoRange, niceStep, stepDecimals, targetRange, visibleExtent } from './autoRange';
import { CHART_SPECS } from './chartSpecs';

function chartRange(id: string) {
  const spec = CHART_SPECS.find((s) => s.id === id);
  if (!spec) throw new Error(`missing chart ${id}`);
  return spec.range;
}

describe('niceStep', () => {
  it('picks 1, 2, 2.5 or 5 times a power of ten', () => {
    expect(niceStep(100, 4)).toBe(25);
    expect(niceStep(1000, 5)).toBe(200);
    expect(niceStep(0.3, 3)).toBeCloseTo(0.1);
    expect(niceStep(7, 2)).toBe(5);
  });

  it('rounds to the nearest step, so short plots still get a few grid lines', () => {
    // 4000 / 3 = 1333: 1000 (4 intervals) beats 2000 (2 intervals).
    expect(niceStep(4000, 3)).toBe(1000);
  });

  it('survives a zero span', () => {
    expect(niceStep(0, 4)).toBe(1);
  });
});

describe('stepDecimals', () => {
  it('gives the digits needed to print multiples of a step', () => {
    expect(stepDecimals(100)).toBe(0);
    expect(stepDecimals(25)).toBe(0);
    expect(stepDecimals(2.5)).toBe(1);
    expect(stepDecimals(0.5)).toBe(1);
    expect(stepDecimals(0.25)).toBe(2);
    expect(stepDecimals(0.1)).toBe(1);
    expect(stepDecimals(0.02)).toBe(2);
  });
});

describe('targetRange', () => {
  it('never zooms into steady-state noise: a flat trace gets the minimum span', () => {
    const [lo, hi] = targetRange(3000.0001, 3000.0002, { minSpan: 100 });
    expect(hi - lo).toBeGreaterThanOrEqual(100);
    expect(lo).toBeLessThan(3000);
    expect(hi).toBeGreaterThan(3000);
  });

  it('pads the data and rounds outward', () => {
    const [lo, hi] = targetRange(568.3, 597.7, { minSpan: 10 });
    expect(lo).toBeLessThan(568.3);
    expect(hi).toBeGreaterThan(597.7);
    // Edges land on round numbers (here multiples of 2.5 K), not on raw data.
    expect((lo * 2) % 1).toBe(0);
    expect((hi * 2) % 1).toBe(0);
  });

  it('includes zero when asked (the critical line on the reactivity chart)', () => {
    const [lo, hi] = targetRange(-7000, -6500, { minSpan: 100, includeZero: true });
    expect(lo).toBeLessThanOrEqual(-7000);
    expect(hi).toBeGreaterThanOrEqual(0);
  });

  it('respects floor and ceiling by sliding the window', () => {
    const [lo, hi] = targetRange(0, 3, { minSpan: 10, floor: 0, ceil: 100 });
    expect(lo).toBe(0);
    expect(hi).toBeGreaterThanOrEqual(10);

    const [lo2, hi2] = targetRange(98, 100, { minSpan: 10, floor: 0, ceil: 100 });
    expect(hi2).toBe(100);
    expect(lo2).toBeLessThanOrEqual(90);
  });
});

describe('visibleExtent', () => {
  const columns = [
    [0, 1, 2, 3, 4],
    [10, 20, 30, 40, 50],
    [5, 5, 5, 60, 5],
  ];

  it('spans every series over the visible points', () => {
    expect(visibleExtent(columns, 0)).toEqual([5, 60]);
  });

  it('includes the one point just left of the window, where the trace enters', () => {
    expect(visibleExtent(columns, 3.5)).toEqual([5, 60]);
    expect(visibleExtent(columns, 4)).toEqual([5, 60]);
  });

  it('returns null with no data', () => {
    expect(visibleExtent([[], []], 0)).toBeNull();
  });
});

describe('AutoRange', () => {
  it('snaps to the first range, then holds it while the data wanders inside', () => {
    const r = new AutoRange({ minSpan: 100 });
    const first = r.update([2990, 3010], 0.016);
    expect(first).not.toBeNull();
    for (let i = 0; i < 100; i++) {
      const v = 3000 + 8 * Math.sin(i / 3);
      expect(r.update([v - 1, v + 1], 0.016)).toEqual(first);
    }
  });

  it('eases toward a new range instead of jumping', () => {
    const r = new AutoRange({ minSpan: 100, floor: 0 });
    const [, hi0] = r.update([2990, 3010], 0.016) as [number, number];
    // SCRAM: power collapses toward zero.
    const next = r.update([50, 3010], 0.016) as [number, number];
    const target = r.targetRange as [number, number];
    expect(target[0]).toBe(0);
    // One 16 ms frame moves only part of the way.
    expect(next[0]).toBeGreaterThan(target[0]);
    expect(next[0]).toBeLessThan(2990);
    // ...and it settles exactly on the target after a while.
    let shown = next;
    for (let i = 0; i < 200; i++) shown = r.update([50, 3010], 0.016) as [number, number];
    expect(shown).toEqual(target);
    expect(hi0).toBeGreaterThan(3010);
  });

  it('shrinks once the data fills only a small part of the range', () => {
    const r = new AutoRange({ minSpan: 10, floor: 0 });
    r.update([0, 3000], 0.016);
    for (let i = 0; i < 200; i++) r.update([100, 110], 0.016);
    const [lo, hi] = r.targetRange as [number, number];
    expect(hi - lo).toBeLessThan(100);
  });

  it('keeps the current range when there is nothing in view', () => {
    const r = new AutoRange({ minSpan: 10 });
    expect(r.update(null, 0.016)).toBeNull();
    const shown = r.update([0, 1], 0.016);
    expect(r.update(null, 0.016)).toEqual(shown);
  });
});

describe('D.7 secondary chart ranges', () => {
  it('keeps the steam-pressure axis above the secondary model floor', () => {
    const [lo, hi] = targetRange(6.899, 7.6, chartRange('steam-pressure'));
    expect(lo).toBeGreaterThanOrEqual(3);
    expect(hi - lo).toBeGreaterThanOrEqual(1);
    expect(hi).toBeGreaterThanOrEqual(7.6);
  });

  it('keeps SG level as a bounded percentage with room around the setpoint', () => {
    const [lo, hi] = targetRange(50, 50, chartRange('sg-level'));
    expect(lo).toBeGreaterThanOrEqual(0);
    expect(hi).toBeLessThanOrEqual(100);
    expect(hi - lo).toBeGreaterThanOrEqual(10);
  });

  it('keeps steam/feed-flow and electrical-output axes grounded at zero', () => {
    const [flowLo, flowHi] = targetRange(0, 2003, chartRange('steam-feed-flow'));
    expect(flowLo).toBe(0);
    expect(flowHi).toBeGreaterThan(2003);

    const [mwLo, mwHi] = targetRange(0, 990, chartRange('electric-output'));
    expect(mwLo).toBe(0);
    expect(mwHi).toBeGreaterThan(990);
  });
});
