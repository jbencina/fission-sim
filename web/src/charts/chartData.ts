import type { Frame } from '../types/telemetry';

export interface PowerPoint {
  /** Relative time in seconds; 0 = newest, -CHART_WINDOW_S = oldest in window. */
  t_rel: number;
  /** Thermal power in MW (raw Watts / 1e6). */
  power_MW: number;
}

export interface TemperaturePoint {
  /** Relative time in seconds; 0 = newest. */
  t_rel: number;
  /** Hot-leg temperature [K] */
  T_hot: number;
  /** Cold-leg temperature [K] */
  T_cold: number;
  /** Average primary temperature [K] */
  T_avg: number;
  /** Bulk fuel temperature [K] */
  T_fuel: number;
}

export interface PressurePoint {
  /** Relative time in seconds; 0 = newest. */
  t_rel: number;
  /** Primary system pressure [MPa] */
  P_MPa: number;
}

export interface ReactivityPoint {
  /** Relative time in seconds; 0 = newest. */
  t_rel: number;
  /** Rod reactivity worth [pcm] */
  rho_rod_pcm: number;
  /** Doppler feedback reactivity [pcm] */
  rho_doppler_pcm: number;
  /** Moderator temperature feedback reactivity [pcm] */
  rho_moderator_pcm: number;
  /** Total (net) reactivity [pcm] */
  rho_total_pcm: number;
}

function latestTime(history: Frame[]): number {
  return history[history.length - 1].t;
}

/**
 * Width of the chart time window [s of simulated time].
 *
 * The window is fixed in simulated time, not in frames: the backend sends
 * frames at a roughly constant wall-clock rate, so at 10x speed consecutive
 * frames are ~1 s of simulated time apart and the store's 600-frame history
 * spans ~600 s. Charts always show only the most recent 60 s so the x axis
 * means the same thing at every speed.
 */
export const CHART_WINDOW_S = 60;

/**
 * Width of one decimation bucket [ms of simulated time].
 *
 * 60 s / 200 ms = at most ~300 plotted points per series, which is plenty
 * for a chart a few hundred pixels wide. At 1x (10 Hz, 100 ms per frame)
 * this keeps every other frame; at 2x and above every frame is kept. Those
 * counts assume the runtime's cadence: each frame advances exactly
 * 0.1 s × speed of simulated time (runtime.py `_DEFAULT_CADENCE_HZ`). With
 * a different cadence the bucketing still works, only the thinning changes.
 */
const SAMPLE_BUCKET_MS = 200;

/**
 * Select the frames to plot: those inside the chart window, thinned to at
 * most one frame per SAMPLE_BUCKET_MS of simulated time.
 *
 * Buckets are anchored to absolute simulation time (not to the frame's index
 * in the ring buffer), so a frame that is plotted stays plotted as the
 * history slides. Keeping "every other index" instead would swap to the
 * complementary half of the frames each time the full buffer drops its
 * oldest frame, making noisy series flicker between two point sets.
 *
 * The newest frame is always kept so the line reaches t = 0.
 */
function sampledHistory(history: Frame[]): Frame[] {
  // Work in whole milliseconds so float noise in times such as 100.2 cannot
  // move a frame across a bucket or window boundary.
  const toMs = (t: number) => Math.round(t * 1000);
  const windowStartMs = toMs(latestTime(history)) - CHART_WINDOW_S * 1000;

  const kept: Frame[] = [];
  let lastBucket: number | null = null;
  history.forEach((frame, i) => {
    const tMs = toMs(frame.t);
    if (tMs < windowStartMs) return; // older than the chart window
    const bucket = Math.floor(tMs / SAMPLE_BUCKET_MS);
    if (bucket !== lastBucket || i === history.length - 1) {
      kept.push(frame);
      lastBucket = bucket;
    }
  });
  return kept;
}

export function toPowerPoints(history: Frame[]): PowerPoint[] {
  if (history.length === 0) return [];
  const latest = latestTime(history);
  return sampledHistory(history).map((frame) => ({
    t_rel: +(frame.t - latest).toFixed(2),
    power_MW: +(frame.power_thermal / 1e6).toFixed(3),
  }));
}

export function toTemperaturePoints(history: Frame[]): TemperaturePoint[] {
  if (history.length === 0) return [];
  const latest = latestTime(history);
  return sampledHistory(history).map((frame) => ({
    t_rel: +(frame.t - latest).toFixed(2),
    T_hot: +frame.T_hot.toFixed(2),
    T_cold: +frame.T_cold.toFixed(2),
    T_avg: +frame.T_avg.toFixed(2),
    T_fuel: +frame.T_fuel.toFixed(2),
  }));
}

export function toPressurePoints(history: Frame[]): PressurePoint[] {
  if (history.length === 0) return [];
  const latest = latestTime(history);
  return sampledHistory(history).map((frame) => ({
    t_rel: +(frame.t - latest).toFixed(2),
    P_MPa: +frame.P_primary_MPa.toFixed(4),
  }));
}

export function toReactivityPoints(history: Frame[]): ReactivityPoint[] {
  if (history.length === 0) return [];
  const latest = latestTime(history);
  return sampledHistory(history).map((frame) => ({
    t_rel: +(frame.t - latest).toFixed(2),
    rho_rod_pcm: +(frame.rho_rod * 1e5).toFixed(2),
    rho_doppler_pcm: +(frame.rho_doppler * 1e5).toFixed(2),
    rho_moderator_pcm: +(frame.rho_moderator * 1e5).toFixed(2),
    rho_total_pcm: +(frame.rho_total * 1e5).toFixed(2),
  }));
}
