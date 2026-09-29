/**
 * Turbine-admission status helpers for operator controls.
 *
 * The runtime publishes both the selected turbine admission demand and the
 * last-stepped effective demand. While paused, those can differ, so the UI
 * must show a pending command rather than imply valve motion. The same helper
 * also classifies actual admission against the runtime's reset tolerance.
 *
 * @module admissionStatus
 */

import type { Frame } from '../types/telemetry'
import { deriveTurbineTripStatus, type StatusTone } from './plantStatus'

/** Actual turbine admission at or below this fraction is treated as closed. */
export const TURBINE_ADMISSION_CLOSED_FRACTION = 0.005

/** Demand differences smaller than this fraction are display noise. */
const DEMAND_PENDING_TOLERANCE = 1e-6

type AdmissionStatusFrame = Pick<
  Frame,
  | 'running'
  | 'turbine_load'
  | 'turbine_load_demand'
  | 'turbine_load_demand_effective'
  | 'turbine_trip_active'
  | 'turbine_trip'
  | 'scrammed'
>

/** Effective turbine-admission travel state for the current frame. */
export type AdmissionTripState = 'available' | 'trip-active-closing' | 'trip-active-closed' | 'reset-pending'

/** Derived turbine-admission state used by controls and tests. */
export interface AdmissionStatus {
  /** Operator-selected admission demand [fraction]. */
  selectedDemand: number
  /** Last-stepped effective admission demand [fraction]. */
  effectiveDemand: number
  /** Actual turbine admission valve opening [fraction]. */
  actualAdmission: number
  /** True when selected and effective demand differ while the plant is frozen. */
  demandPending: boolean
  /** True when actual admission is within the closed-valve tolerance. */
  admissionClosed: boolean
  /** True when Reset Turbine Trip must stay disabled because valves are still open. */
  resetBlocked: boolean
  /** Motion/closed/pending classification for the trip indication. */
  tripState: AdmissionTripState
}

/** Compact turbine-trip status display used by the persistent toolbar. */
export interface ToolbarTurbineTripDisplay {
  /** Human-readable toolbar text. */
  label: string
  /** Tooltip/explainer text for the toolbar item. */
  cause: string
  /** Whether an effective turbine trip is active. */
  active: boolean
  /** Whether a paused selected command is waiting for the plant to step. */
  pending: boolean
  /** True when actual turbine admission is within the closed-valve tolerance. */
  closed: boolean
  /** Severity tone inherited from the shared trip classifier. */
  tone: StatusTone
}

/**
 * Clamp a turbine-admission fraction to the UI command range.
 *
 * Parameters
 * ----------
 * value:
 *   Turbine admission fraction [dimensionless].
 *
 * Returns
 * -------
 * number
 *   Fraction limited to [0, 1]; non-finite inputs become 0.
 */
function clampAdmission(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.min(1, Math.max(0, value))
}

/**
 * Return true when actual turbine admission is at the closed-valve tolerance.
 *
 * Parameters
 * ----------
 * actualAdmission:
 *   Actual turbine admission valve opening [fraction].
 *
 * Returns
 * -------
 * boolean
 *   True when `actualAdmission` is less than or equal to 0.5 % open.
 */
export function isTurbineAdmissionClosed(actualAdmission: number): boolean {
  return clampAdmission(actualAdmission) <= TURBINE_ADMISSION_CLOSED_FRACTION
}

/**
 * Derive pending demand and trip-closure status from one telemetry frame.
 *
 * Parameters
 * ----------
 * frame:
 *   Telemetry fields for selected/effective turbine demand, actual admission,
 *   trip latch, SCRAM latch and run state.
 *
 * Returns
 * -------
 * AdmissionStatus
 *   Demand-pending state, closed-valve classification and reset guard flags.
 */
export function deriveAdmissionStatus(frame: AdmissionStatusFrame): AdmissionStatus {
  const selectedDemand = clampAdmission(frame.turbine_load_demand)
  const effectiveDemand = clampAdmission(frame.turbine_load_demand_effective)
  const actualAdmission = clampAdmission(frame.turbine_load)
  const admissionClosed = isTurbineAdmissionClosed(actualAdmission)
  const demandPending = !frame.running && Math.abs(selectedDemand - effectiveDemand) > DEMAND_PENDING_TOLERANCE
  const selectedTrip = frame.turbine_trip || frame.scrammed
  const resetPending = !frame.running && frame.turbine_trip_active && !selectedTrip
  const tripState: AdmissionTripState = resetPending
    ? 'reset-pending'
    : frame.turbine_trip_active
      ? admissionClosed
        ? 'trip-active-closed'
        : 'trip-active-closing'
      : 'available'

  return {
    selectedDemand,
    effectiveDemand,
    actualAdmission,
    demandPending,
    admissionClosed,
    resetBlocked: !admissionClosed,
    tripState,
  }
}

/**
 * Derive the persistent toolbar's compact turbine-trip display.
 *
 * Parameters
 * ----------
 * frame:
 *   Telemetry fields for selected/effective turbine trip, SCRAM, admission
 *   demand, actual admission and run state.
 *
 * Returns
 * -------
 * ToolbarTurbineTripDisplay
 *   Text, closed flag and severity for the toolbar status chip.
 */
export function deriveToolbarTurbineTripDisplay(frame: AdmissionStatusFrame): ToolbarTurbineTripDisplay {
  const tripStatus = deriveTurbineTripStatus(frame)
  const admissionStatus = deriveAdmissionStatus(frame)
  const cause =
    admissionStatus.tripState === 'trip-active-closed'
      ? `${tripStatus.cause}; admission closed at ≤ ${TURBINE_ADMISSION_CLOSED_FRACTION * 100} %`
      : tripStatus.cause

  let label: string
  if (tripStatus.pending) {
    label = tripStatus.kind === 'reset-pending' ? 'Turbine PENDING · reset' : 'Turbine PENDING · trip'
  } else if (admissionStatus.tripState === 'available') {
    label = 'Turbine OK'
  } else if (admissionStatus.tripState === 'trip-active-closed') {
    label = tripStatus.kind === 'scram-trip' ? 'Turbine TRIPPED · P-4' : 'Turbine TRIPPED · operator'
  } else if (tripStatus.kind === 'operator-trip') {
    label = 'Turbine TRIPPED · operator'
  } else if (tripStatus.kind === 'scram-trip') {
    label = 'Turbine TRIPPED · P-4'
  } else {
    label = 'Turbine CLOSING'
  }

  return {
    label,
    cause,
    active: tripStatus.active,
    pending: tripStatus.pending,
    closed: admissionStatus.admissionClosed,
    tone: tripStatus.tone,
  }
}
