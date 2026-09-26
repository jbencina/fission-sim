import { describe, expect, it } from 'vitest';
import {
  CHART_WINDOW_S,
  toPowerPoints,
  toPressurePoints,
  toReactivityPoints,
  toTemperaturePoints,
} from './chartData';
import type { Frame } from '../types/telemetry';
import { makeFrame } from '../test/makeFrame';

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

  it('shows a fixed simulated-time window even when the simulator runs faster', () => {
    // At 10x speed the backend still sends ~10 frames per wall-clock second,
    // so consecutive frames are 1 s apart in simulated time and a full
    // 600-frame history spans 599 s. Only the last 60 s should be charted.
    const history = Array.from({ length: 600 }, (_, i) => makeFrame(1000 + i));

    const points = toPowerPoints(history);

    expect(points[0].t_rel).toBe(-CHART_WINDOW_S);
    expect(points[points.length - 1].t_rel).toBe(0);
    expect(points).toHaveLength(CHART_WINDOW_S + 1);
  });

  it('keeps the same decimated samples when a full history slides by one frame', () => {
    // 10 Hz frames at 1x: a full 600-frame history, then one more frame
    // arrives and the oldest is dropped (what the store does at capacity).
    // Times are built as i / 10 so they are the exact values JSON would carry.
    const full = Array.from({ length: 600 }, (_, i) => makeFrame((1000 + i) / 10));
    const slid = [...full.slice(1), makeFrame((1000 + 600) / 10)];

    // Recover each point's absolute simulation time in centiseconds.
    const absoluteTimes = (history: Frame[]) => {
      const latest = history[history.length - 1].t;
      return toPowerPoints(history).map((p) => Math.round((p.t_rel + latest) * 100));
    };
    const before = new Set(absoluteTimes(full));
    const after = absoluteTimes(slid);

    // Every interior sample drawn after the slide was also drawn before it.
    // Selecting by buffer index would swap to the complementary half instead.
    const interior = after.slice(1, -1);
    expect(interior.length).toBeGreaterThan(250);
    expect(interior.filter((t) => !before.has(t))).toEqual([]);
  });
});
