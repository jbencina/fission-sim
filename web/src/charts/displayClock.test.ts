import { describe, expect, it } from 'vitest';
import { DisplayClock, FRAME_PERIOD_S } from './displayClock';

/** Feed frames every 100 ms of wall time and tick at 60 Hz in between. */
function run(clock: DisplayClock, opts: { frames: number; speed?: number; startT?: number; jitterMs?: (i: number) => number }) {
  const speed = opts.speed ?? 1;
  const shown: number[] = [];
  let frame = 0;
  let t = opts.startT ?? 0;
  for (let wall = 0; frame < opts.frames; wall += 1000 / 60) {
    const due = frame * 100 + (opts.jitterMs?.(frame) ?? 0);
    if (wall >= due) {
      clock.observe(t, true, speed, wall);
      t = +(t + FRAME_PERIOD_S * speed).toFixed(6);
      frame++;
    }
    const v = clock.tick(wall);
    if (v !== null) shown.push(v);
  }
  return shown;
}

describe('DisplayClock', () => {
  it('returns null before the first frame', () => {
    expect(new DisplayClock().tick(0)).toBeNull();
  });

  it('advances smoothly between frames and never runs backward', () => {
    const shown = run(new DisplayClock(), { frames: 50 });
    for (let i = 1; i < shown.length; i++) {
      expect(shown[i]).toBeGreaterThanOrEqual(shown[i - 1]);
    }
    // Per-refresh steps stay close to 1/60 s of simulated time at 1x:
    // no pauses-then-jumps as frames arrive.
    const steps = shown.slice(30).map((v, i, a) => (i ? v - a[i - 1] : 1 / 60)).slice(1);
    for (const step of steps) {
      expect(step).toBeGreaterThan(0.005);
      expect(step).toBeLessThan(0.03);
    }
  });

  it('stays smooth with a few milliseconds of frame-timing jitter', () => {
    const shown = run(new DisplayClock(), { frames: 60, jitterMs: (i) => ((i * 37) % 11) - 5 });
    const steps = shown.slice(40).map((v, i, a) => (i ? v - a[i - 1] : 1 / 60)).slice(1);
    for (const step of steps) {
      expect(step).toBeGreaterThanOrEqual(0);
      expect(step).toBeLessThan(0.04);
    }
  });

  it('never shows time beyond the newest frame', () => {
    const clock = new DisplayClock();
    clock.observe(10, true, 1, 0);
    // No further frames arrive (a stall): the clock stops at the data.
    let v = 0;
    for (let wall = 0; wall < 2000; wall += 16) v = clock.tick(wall) as number;
    expect(v).toBeLessThanOrEqual(10);
    expect(v).toBeGreaterThan(9.9);
  });

  it('settles exactly on the newest frame while paused', () => {
    const clock = new DisplayClock();
    clock.observe(10, true, 1, 0);
    clock.observe(10, false, 1, 0);
    let v = 0;
    for (let wall = 0; wall < 3000; wall += 16) v = clock.tick(wall) as number;
    expect(v).toBeCloseTo(10, 6);
  });

  it('scales with speed', () => {
    const shown = run(new DisplayClock(), { frames: 40, speed: 10 });
    const last = shown.length - 1;
    const rate = (shown[last] - shown[last - 60]) / 1; // 60 refreshes = 1 s
    expect(rate).toBeGreaterThan(9);
    expect(rate).toBeLessThan(11);
  });

  it('snaps back when simulated time moves backward (a reset)', () => {
    const clock = new DisplayClock();
    run(clock, { frames: 20, startT: 100 });
    clock.observe(0, true, 1, 5000);
    expect(clock.tick(5016)).toBeLessThan(1);
  });
});
