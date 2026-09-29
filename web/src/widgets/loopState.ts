/**
 * One-line description of the primary loop for the schematic's title:
 * the reactor's criticality and whether the loop is heating up, cooling or
 * steady. Secondary-side helpers add the turbine trip, steam dump and SG
 * level words without changing the primary sentence. Pure, so it is unit
 * tested directly.
 */

import {
  PENDING_DETAIL,
  deriveDumpStatus,
  deriveLevelStatus,
  deriveTurbineTripStatus,
} from '../state/plantStatus'
import type { Frame } from '../types/telemetry'

/** Fraction by which core power may differ from SG heat and still count as steady. */
const STEADY_BAND = 0.02

/** User-facing pending text when a paused trip command has not affected the plant yet. */
export const TRIP_PENDING = `trip ${PENDING_DETAIL}`

/** User-facing pending text when a paused trip reset has not affected the plant yet. */
export const TRIP_RESET_PENDING = `trip reset ${PENDING_DETAIL}`

/** Turbine trip state shown by the schematic. */
export interface TurbineTripStatus {
  /** Whether the label is an effective trip, paused pending state, or running transient. */
  kind: 'active' | 'pending-trip' | 'pending-reset' | 'trip-transient'
  /** Short user-facing label for the cause or pending action. */
  label: string
}

/** Word for the sign of the displayed (one-decimal) reactivity in pcm. */
export function criticalityWord(pcm: number): string {
  if (Math.abs(pcm) < 0.05) return 'critical'
  return pcm > 0 ? 'supercritical' : 'subcritical'
}

/** e.g. "subcritical, cooling"; "waiting for telemetry" before the first frame. */
export function describeLoop(frame: Frame | null): string {
  if (frame === null) return 'waiting for telemetry'
  const made = frame.power_thermal
  const removed = frame.Q_sg
  const scale = Math.max(Math.abs(made), Math.abs(removed), 1)
  const diff = (made - removed) / scale
  const trend = diff > STEADY_BAND ? 'heating up' : diff < -STEADY_BAND ? 'cooling' : 'steady'
  return `${criticalityWord(frame.rho_total * 1e5)}, ${trend}`
}

/**
 * Turbine trip status, including paused command/effective-state disagreement.
 *
 * The runtime can publish a command latch that disagrees with the last
 * effective turbine state while paused. The wording mirrors the Phase D P1
 * rule: show pending while paused, then operator trip, SCRAM (P-4), or trip
 * clearing when the effective trip is active.
 */
export function turbineTripStatus(frame: Frame | null): TurbineTripStatus | null {
  if (frame === null) return null
  const status = deriveTurbineTripStatus(frame)
  if (status.kind === 'trip-pending') {
    return status.pending
      ? { kind: 'pending-trip', label: TRIP_PENDING }
      : { kind: 'trip-transient', label: `trip ${status.cause}` }
  }
  if (status.kind === 'reset-pending') return { kind: 'pending-reset', label: TRIP_RESET_PENDING }
  if (!status.active) return null
  return {
    kind: 'active',
    label: status.kind === 'valves-closing' ? 'trip clearing' : status.cause,
  }
}

/** Human wording for an effective turbine trip cause, excluding pending states. */
export function turbineTripCause(frame: Frame | null): string | null {
  const status = turbineTripStatus(frame)
  return status?.kind === 'active' ? status.label : null
}

/**
 * Secondary-side phrases appended to the schematic title.
 *
 * SG level uses the illustrative 0.40-0.60 normal band, not a trip setpoint.
 */
export function describeSecondaryState(frame: Frame | null): string[] {
  if (frame === null) return []

  const phrases: string[] = []
  const trip = turbineTripStatus(frame)
  if (trip?.kind === 'active') phrases.push('turbine tripped')
  if (trip?.kind === 'pending-trip' || trip?.kind === 'pending-reset' || trip?.kind === 'trip-transient') {
    phrases.push(trip.label)
  }
  if (deriveDumpStatus(frame).open) phrases.push('steam dump open')

  const level = deriveLevelStatus(frame)
  if (level.band !== 'green' && level.level < 0.5) {
    phrases.push('SG level low')
  } else if (level.band !== 'green' && level.level > 0.5) {
    phrases.push('SG level high')
  }
  return phrases
}

/**
 * Full schematic title sentence: primary loop state plus secondary-side state.
 */
export function describeSchematicState(frame: Frame | null): string {
  const primary = describeLoop(frame)
  const secondary = describeSecondaryState(frame)
  return secondary.length === 0 ? primary : `${primary} · ${secondary.join(' · ')}`
}
