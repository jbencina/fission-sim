/**
 * Telemetry history → chart columns.
 *
 * The charts are drawn by uPlot, which takes columns: one array of x values
 * (simulated time [s], ascending) and one array per series. Each chart spec
 * (chartSpecs.ts) lists the series it draws as functions of a Frame; this
 * module applies them to the history.
 *
 * Only frames near the chart window are kept. The window is fixed in
 * simulated time, not in frames: the backend sends frames at a roughly
 * constant wall-clock rate, so at 10x speed consecutive frames are ~1 s of
 * simulated time apart and the store's 600-frame history spans ~600 s.
 * Charts always show only the most recent CHART_WINDOW_S, so the x axis
 * means the same thing at every speed. Every frame in the window is drawn:
 * at most ~600 points per series, which a canvas chart draws in well under a
 * millisecond, so no decimation is needed.
 */

import type { Frame } from '../types/telemetry'

/** Width of the chart time window [s of simulated time]. */
export const CHART_WINDOW_S = 60

/**
 * Extra history kept before the window [s of simulated time]. The charts'
 * right edge trails the newest frame slightly (see displayClock.ts), and the
 * trace must still enter from the left edge at 10x, where frames are 1 s
 * apart; 5 s covers both.
 */
export const WINDOW_MARGIN_S = 5

/** Watts to megawatts. */
export const toMW = (watts: number): number => watts / 1e6

/** Dimensionless reactivity to pcm (per cent mille, 1e-5). */
export const toPcm = (rho: number): number => rho * 1e5

/** Rod fraction of travel withdrawn (0..1) to percent. */
export const toPercent = (fraction: number): number => fraction * 100

/**
 * Build uPlot columns `[xs, ...ys]` from the history for the given series.
 * Frames older than the window (plus WINDOW_MARGIN_S) are dropped.
 */
export function toColumns(
  history: readonly Frame[],
  series: ReadonlyArray<(frame: Frame) => number>,
): number[][] {
  const columns: number[][] = [[], ...series.map(() => [])]
  if (history.length === 0) return columns

  const oldest = history[history.length - 1].t - CHART_WINDOW_S - WINDOW_MARGIN_S
  for (const frame of history) {
    if (frame.t < oldest) continue
    columns[0].push(frame.t)
    for (let s = 0; s < series.length; s++) columns[s + 1].push(series[s](frame))
  }
  return columns
}
