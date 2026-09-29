/**
 * Telemetry history → chart columns.
 *
 * The charts are drawn by uPlot, which takes columns: one array of x values
 * (simulated time [s], ascending) and one array per series. Each chart spec
 * (chartSpecs.ts) lists the series it draws as functions of a Frame; this
 * module applies them to the history.
 *
 * Only frames near the selected chart window are drawn. The window is fixed
 * in simulated time, not in frames: at 1× the 15-minute window contains about
 * 9,000 telemetry frames, while at 10× it contains about 900. Long windows are
 * decimated for display by simulated-time buckets while preserving the first,
 * last, minimum, and maximum point in each series so uPlot stays smooth
 * without hiding excursions.
 */

import type { Frame } from '../types/telemetry'

export interface ChartWindowOption {
  /** Width of the chart time window [s of simulated time]. */
  seconds: number
  /** Short control label. */
  label: string
  /** Plain-language label for help and accessible names. */
  ariaLabel: string
}

/** Operator-selectable chart windows [s of simulated time]. */
export const CHART_WINDOW_OPTIONS = [
  { seconds: 60, label: '1 min', ariaLabel: '1 minute' },
  { seconds: 5 * 60, label: '5 min', ariaLabel: '5 minutes' },
  { seconds: 15 * 60, label: '15 min', ariaLabel: '15 minutes' },
] as const satisfies readonly ChartWindowOption[]

/** Width of the default chart time window [s of simulated time]. */
export const DEFAULT_CHART_WINDOW_S: number = CHART_WINDOW_OPTIONS[0].seconds

/** Widest selectable chart time window [s of simulated time]. */
export const MAX_CHART_WINDOW_S: number = CHART_WINDOW_OPTIONS[CHART_WINDOW_OPTIONS.length - 1].seconds

/**
 * Extra history kept before the window [s of simulated time]. The charts'
 * right edge trails the newest frame slightly (see displayClock.ts), and the
 * trace must still enter from the left edge at 10x, where frames are 1 s
 * apart; 5 s covers both.
 */
export const WINDOW_MARGIN_S = 5

/**
 * Maximum points uPlot receives for one chart series after display decimation.
 * A 15-minute, 1× window has about 9,000 raw frames, so this keeps per-chart
 * redraws bounded while still supplying at least one point every ~0.5 s before
 * bucket extremum preservation.
 */
export const MAX_DISPLAY_POINTS = 1800

/** Watts to megawatts. */
export const toMW = (watts: number): number => watts / 1e6

/** Pascals to megapascals for steam and primary-system pressure charts. */
export const toMPa = (pascals: number): number => pascals / 1e6

/** Dimensionless reactivity to pcm (per cent mille, 1e-5). */
export const toPcm = (rho: number): number => rho * 1e5

/** Rod fraction of travel withdrawn (0..1) to percent. */
export const toPercent = (fraction: number): number => fraction * 100

/** True when `seconds` is one of the operator-selectable chart windows. */
export function isChartWindowSeconds(seconds: number): seconds is (typeof CHART_WINDOW_OPTIONS)[number]['seconds'] {
  return CHART_WINDOW_OPTIONS.some((option) => option.seconds === seconds)
}

/**
 * Human-readable relative time for a tick offset from the chart's right edge.
 * Negative values are in the past; zero labels the newest displayed point.
 */
export function relativeTimeLabel(offsetS: number, decimals = 0): string {
  const rounded = +offsetS.toFixed(decimals)
  if (rounded === 0) return 'now'
  const sign = rounded < 0 ? '−' : ''
  const abs = Math.abs(rounded)
  if (abs >= 60) {
    const minutes = abs / 60
    const minuteDecimals = Number.isInteger(minutes) ? 0 : 1
    return `${sign}${minutes.toFixed(minuteDecimals)}m`
  }
  return `${sign}${abs.toFixed(decimals)}s`
}

/** Tick spacing for the chart x axis [s], chosen to keep labels readable. */
export function timeAxisStep(windowSeconds: number, chartWidthCssPx: number): number {
  if (windowSeconds <= 60) return chartWidthCssPx < 340 ? 20 : 10
  if (windowSeconds <= 5 * 60) return chartWidthCssPx < 340 ? 120 : 60
  return chartWidthCssPx < 340 ? 300 : 180
}

/**
 * Time-axis split positions for uPlot, relative to the right-edge time.
 * The first split marks the left edge and the last split marks "now".
 */
export function timeAxisSplits(rightEdgeS: number, windowSeconds: number, chartWidthCssPx: number): number[] {
  const step = timeAxisStep(windowSeconds, chartWidthCssPx)
  const out: number[] = []
  for (let offset = -windowSeconds; offset < 0; offset += step) out.push(rightEdgeS + offset)
  out.push(rightEdgeS)
  return out
}

/** Select aligned uPlot rows by their shared point indexes. */
function pickIndexes(columns: number[][], indexes: readonly number[]): number[][] {
  return columns.map((column) => indexes.map((index) => column[index]))
}

/**
 * Reduce aligned uPlot columns to at most `maxPoints` by simulated-time buckets.
 *
 * Each bucket keeps its first and last point plus the min/max point from every
 * plotted series. This preserves visible excursions better than taking every
 * Nth point, while keeping the resulting indexes sorted so the traces remain
 * valid time series.
 */
export function decimateColumns(columns: number[][], maxPoints = MAX_DISPLAY_POINTS): number[][] {
  const xs = columns[0]
  if (!xs || xs.length <= maxPoints || maxPoints < 3) return columns

  const seriesCount = Math.max(0, columns.length - 1)
  const perBucketBudget = 2 + 2 * seriesCount
  const bucketCount = Math.max(1, Math.floor((maxPoints - 2) / Math.max(1, perBucketBudget)))
  const bucketSize = Math.ceil((xs.length - 2) / bucketCount)
  const keep = new Set<number>([0, xs.length - 1])

  for (let start = 1; start < xs.length - 1; start += bucketSize) {
    const end = Math.min(xs.length - 1, start + bucketSize)
    keep.add(start)
    keep.add(end - 1)
    for (let series = 1; series < columns.length; series++) {
      const ys = columns[series]
      let minIndex = start
      let maxIndex = start
      for (let i = start + 1; i < end; i++) {
        if (ys[i] < ys[minIndex]) minIndex = i
        if (ys[i] > ys[maxIndex]) maxIndex = i
      }
      keep.add(minIndex)
      keep.add(maxIndex)
    }
  }

  return pickIndexes(columns, [...keep].sort((a, b) => a - b))
}

/**
 * Build uPlot columns `[xs, ...ys]` from the history for the given series.
 * Frames older than the window (plus WINDOW_MARGIN_S) are dropped.
 */
export function toColumns(
  history: readonly Frame[],
  series: ReadonlyArray<(frame: Frame) => number>,
  windowSeconds: number = DEFAULT_CHART_WINDOW_S,
  maxPoints: number = MAX_DISPLAY_POINTS,
): number[][] {
  const columns: number[][] = [[], ...series.map(() => [])]
  if (history.length === 0) return columns

  const oldest = history[history.length - 1].t - windowSeconds - WINDOW_MARGIN_S
  for (const frame of history) {
    if (frame.t < oldest) continue
    columns[0].push(frame.t)
    for (let s = 0; s < series.length; s++) columns[s + 1].push(series[s](frame))
  }
  return decimateColumns(columns, maxPoints)
}
