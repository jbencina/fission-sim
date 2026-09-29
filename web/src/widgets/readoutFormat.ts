/**
 * Pure formatting helpers for status-panel readouts.
 *
 * Keeping them outside React component modules preserves Vite fast-refresh
 * assumptions and makes the wording easy to unit test.
 */

import { EMPTY_VALUE, formatNumber } from '../ui/format'

export interface LevelFloorEstimateReadout {
  /** Display value for the current-flow floor estimate. */
  value: string
  /** Whether the normal seconds unit should be appended. */
  showUnits: boolean
}

/**
 * Format the SG-level floor estimate without overstating long, near-balance times.
 *
 * Parameters
 * ----------
 * seconds:
 *   Current-flow estimate to the SG collapsed-level floor [s], or null when
 *   the SG is not draining toward that floor.
 *
 * Returns
 * -------
 * LevelFloorEstimateReadout
 *   Readout value plus a flag telling InfoRow whether the seconds unit still
 *   applies. Estimates over one hour are intentionally coarse.
 */
export function formatLevelFloorEstimate(seconds: number | null | undefined): LevelFloorEstimateReadout {
  if (seconds == null) return { value: EMPTY_VALUE, showUnits: true }
  if (seconds > 3600) return { value: '> 1 h (near balance)', showUnits: false }
  return { value: formatNumber(seconds, 0), showUnits: true }
}
