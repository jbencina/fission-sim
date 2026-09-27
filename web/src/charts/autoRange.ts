/**
 * Y-axis ranging for the live charts.
 *
 * A plain "fit the data" axis rescales whenever a value crosses a round
 * number, and at steady state it zooms into solver noise; both make a live
 * chart look jittery. The rules here keep the axis calm:
 *
 *   - Each chart sets a minimum span, so a flat trace stays flat.
 *   - The range is padded and rounded outward to round numbers.
 *   - Hysteresis: the range only changes when the data gets close to an edge
 *     or shrinks to a small part of the range, not on every frame.
 *   - When it does change, the displayed range eases toward the new one over
 *     a fraction of a second instead of snapping.
 *
 * Everything here is pure (time is passed in) so it is unit tested directly.
 */

export interface RangeSpec {
  /** Smallest span the axis shows [chart unit]. */
  minSpan: number
  /** Always include zero (the reactivity chart's critical line). */
  includeZero?: boolean
  /** Lowest value the axis may show, e.g. 0 MW. */
  floor?: number
  /** Highest value the axis may show, e.g. 100 %. */
  ceil?: number
}

/** Fraction of the data span added above and below it. */
const PAD_FRACTION = 0.08

/** Shrink once the data fills less than this fraction of the range. */
const SHRINK_BELOW = 0.4

/** Grow once the data comes within this fraction of the range of an edge. */
const EDGE_MARGIN = 0.03

/** Time constant of the eased transition between ranges [s]. */
const EASE_TAU_S = 0.22

/**
 * The round step (1, 2, 2.5 or 5 × 10^n) nearest to `span / targetTicks`,
 * so `span` divides into about `targetTicks` intervals.
 */
export function niceStep(span: number, targetTicks: number): number {
  if (!(span > 0) || !(targetTicks > 0)) return 1
  const raw = span / targetTicks
  const magnitude = 10 ** Math.floor(Math.log10(raw))
  const norm = raw / magnitude
  const nice = norm < 1.5 ? 1 : norm < 2.25 ? 2 : norm < 3.5 ? 2.5 : norm < 7.5 ? 5 : 10
  return nice * magnitude
}

/** Decimal places needed to print multiples of `step` exactly. */
export function stepDecimals(step: number): number {
  if (!(step > 0)) return 0
  const d = -Math.floor(Math.log10(step) + 1e-9)
  // 2.5, 0.25, ... need one digit more than their magnitude suggests.
  const extra = Math.abs(step / 10 ** Math.floor(Math.log10(step)) - 2.5) < 1e-9 ? 1 : 0
  return Math.max(0, d + extra)
}

function roundTo(value: number, step: number): number {
  return +value.toFixed(stepDecimals(step) + 2)
}

/** The padded, rounded range that comfortably holds [dataMin, dataMax]. */
export function targetRange(dataMin: number, dataMax: number, spec: RangeSpec): [number, number] {
  let lo = dataMin
  let hi = dataMax
  if (spec.includeZero) {
    lo = Math.min(lo, 0)
    hi = Math.max(hi, 0)
  }

  const pad = (hi - lo) * PAD_FRACTION
  lo -= pad
  hi += pad

  if (hi - lo < spec.minSpan) {
    const mid = (lo + hi) / 2
    lo = mid - spec.minSpan / 2
    hi = mid + spec.minSpan / 2
  }

  // Keep inside the physical bounds by sliding the window, not squashing it.
  if (spec.floor !== undefined && lo < spec.floor) {
    hi += spec.floor - lo
    lo = spec.floor
  }
  if (spec.ceil !== undefined && hi > spec.ceil) {
    lo -= hi - spec.ceil
    hi = spec.ceil
    if (spec.floor !== undefined) lo = Math.max(lo, spec.floor)
  }

  const step = niceStep(hi - lo, 10)
  lo = roundTo(Math.floor(lo / step + 1e-9) * step, step)
  hi = roundTo(Math.ceil(hi / step - 1e-9) * step, step)
  if (spec.floor !== undefined) lo = Math.max(lo, spec.floor)
  if (spec.ceil !== undefined) hi = Math.min(hi, spec.ceil)
  return [lo, hi]
}

/**
 * Minimum and maximum of the series over the points drawn from `xMin`
 * onward, including the point just before `xMin` that the trace enters
 * from. `columns` is uPlot's layout: [xs, ys1, ys2, ...], xs ascending.
 * Returns null when nothing is in view.
 */
export function visibleExtent(
  columns: ReadonlyArray<ArrayLike<number>>,
  xMin: number,
): [number, number] | null {
  const xs = columns[0]
  if (!xs || xs.length === 0) return null

  // First index with x >= xMin (binary search), then step back one point.
  let a = 0
  let b = xs.length
  while (a < b) {
    const m = (a + b) >> 1
    if (xs[m] < xMin) a = m + 1
    else b = m
  }
  const start = Math.max(0, a - 1)

  let min = Infinity
  let max = -Infinity
  for (let s = 1; s < columns.length; s++) {
    const ys = columns[s]
    for (let i = start; i < xs.length; i++) {
      const v = ys[i]
      if (v < min) min = v
      if (v > max) max = v
    }
  }
  return Number.isFinite(min) && Number.isFinite(max) ? [min, max] : null
}

/** Sticky, eased y range for one chart. */
export class AutoRange {
  private target: [number, number] | null = null
  private shown: [number, number] | null = null

  constructor(private readonly spec: RangeSpec) {}

  /** Range the axis is easing toward, or null before any data. */
  get targetRange(): [number, number] | null {
    return this.target
  }

  /**
   * Update for the data currently in view and `dt` seconds of wall time
   * since the last call; returns the range to draw (null before any data).
   * Pass `extent` null to keep the current range.
   */
  update(extent: [number, number] | null, dt: number): [number, number] | null {
    if (extent !== null) {
      const fresh = targetRange(extent[0], extent[1], this.spec)
      if (this.target === null) {
        this.target = fresh
        this.shown = [...fresh]
      } else {
        const [lo, hi] = this.target
        const { floor, ceil, includeZero } = this.spec
        const dataMin = includeZero ? Math.min(extent[0], 0) : extent[0]
        const dataMax = includeZero ? Math.max(extent[1], 0) : extent[1]
        const margin = (hi - lo) * EDGE_MARGIN
        // Data may sit right on a physical bound (0 MW, 100 % withdrawn).
        const lowOk = dataMin >= lo + margin || (floor !== undefined && lo <= floor && dataMin >= lo)
        const highOk = dataMax <= hi - margin || (ceil !== undefined && hi >= ceil && dataMax <= hi)
        const loose = fresh[1] - fresh[0] < SHRINK_BELOW * (hi - lo)
        if (!lowOk || !highOk || loose) this.target = fresh
      }
    }

    if (this.target === null || this.shown === null) return null

    const k = 1 - Math.exp(-Math.max(0, dt) / EASE_TAU_S)
    const span = this.target[1] - this.target[0]
    for (const i of [0, 1] as const) {
      const next = this.shown[i] + (this.target[i] - this.shown[i]) * k
      this.shown[i] = Math.abs(this.target[i] - next) < span * 1e-4 ? this.target[i] : next
    }
    return [this.shown[0], this.shown[1]]
  }
}
