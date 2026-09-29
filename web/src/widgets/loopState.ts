/**
 * One-line description of the primary loop for the schematic's title:
 * the reactor's criticality and whether the loop is heating up, cooling or
 * steady. Secondary-side helpers add the turbine trip, steam dump and SG
 * level words without changing the primary sentence. Pure, so it is unit
 * tested directly.
 */

import type { Frame } from '../types/telemetry'

/** Fraction by which core power may differ from SG heat and still count as steady. */
const STEADY_BAND = 0.02

/** Steam dump is called open above this visible-flow threshold [kg/s]. */
const DUMP_OPEN_KG_PER_S = 1

/** Illustrative lower edge of the normal SG collapsed-liquid-fraction band [fraction]. */
const SG_LEVEL_LOW = 0.4

/** Illustrative upper edge of the normal SG collapsed-liquid-fraction band [fraction]. */
const SG_LEVEL_HIGH = 0.6

/** User-facing pending text when a paused trip command has not affected the plant yet. */
export const TRIP_PENDING = 'trip pending — applies when the simulation runs'

/** User-facing pending text when a paused trip reset has not affected the plant yet. */
export const TRIP_RESET_PENDING = 'trip reset pending — applies when the simulation runs'

/** Turbine trip state shown by the schematic. */
export interface TurbineTripStatus {
  /** Whether the label is an effective trip or a paused command waiting to apply. */
  kind: 'active' | 'pending-trip' | 'pending-reset'
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
  const selectedTrip = frame.turbine_trip || frame.scrammed
  if (!frame.running && selectedTrip !== frame.turbine_trip_active) {
    return selectedTrip
      ? { kind: 'pending-trip', label: TRIP_PENDING }
      : { kind: 'pending-reset', label: TRIP_RESET_PENDING }
  }
  if (!frame.turbine_trip_active) return null
  if (frame.turbine_trip) return { kind: 'active', label: 'operator trip' }
  if (frame.scrammed) return { kind: 'active', label: 'SCRAM (P-4)' }
  return { kind: 'active', label: 'trip clearing' }
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
  if (trip?.kind === 'pending-trip' || trip?.kind === 'pending-reset') phrases.push(trip.label)
  if (frame.m_dump > DUMP_OPEN_KG_PER_S) phrases.push('steam dump open')
  if (frame.level_sg < SG_LEVEL_LOW) {
    phrases.push('SG level low')
  } else if (frame.level_sg > SG_LEVEL_HIGH) {
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
