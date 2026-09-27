/**
 * Number formatting shared by the charts, status readouts and toolbar.
 *
 * Values use a typographic minus sign (U+2212, as wide as a plus in tabular
 * figures) and thousands separators, with a fixed number of decimals so
 * readouts do not change width while they update.
 */

export const MINUS = '\u2212'
export const EMPTY_VALUE = '—'

const formatters = new Map<string, Intl.NumberFormat>()

function formatter(decimals: number, grouping: boolean): Intl.NumberFormat {
  const key = `${decimals}:${grouping}`
  let f = formatters.get(key)
  if (!f) {
    f = new Intl.NumberFormat('en-US', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
      useGrouping: grouping,
    })
    formatters.set(key, f)
  }
  return f
}

/**
 * Format `value` with `decimals` places. Null, NaN and infinities give "—".
 * A value that rounds to zero prints without a sign, never as "−0.0".
 */
export function formatNumber(
  value: number | null | undefined,
  decimals: number,
  { grouping = true }: { grouping?: boolean } = {},
): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return EMPTY_VALUE
  const text = formatter(decimals, grouping).format(Math.abs(value))
  const roundsToZero = Number(text.replace(/,/g, '')) === 0
  return value < 0 && !roundsToZero ? `${MINUS}${text}` : text
}

/**
 * Format simulated time [s] as "mm:ss.t". Minutes keep counting past 59.
 *
 *   0 → "00:00.0",  90.7 → "01:30.7",  3661.25 → "61:01.2"
 */
export function formatClock(t: number | null | undefined): string {
  if (t === null || t === undefined || !Number.isFinite(t)) return '--:--.-'
  // Work in whole tenths so a value just under a second (floating-point
  // drift makes these common) never prints as ten tenths.
  const tenthsTotal = Math.floor(Math.max(0, t) * 10 + 1e-6)
  const minutes = Math.floor(tenthsTotal / 600)
  const whole = Math.floor(tenthsTotal / 10) % 60
  const tenths = tenthsTotal % 10
  return `${String(minutes).padStart(2, '0')}:${String(whole).padStart(2, '0')}.${tenths}`
}

/** Kelvin to degrees Celsius. */
export function kelvinToCelsius(k: number): number {
  return k - 273.15
}
