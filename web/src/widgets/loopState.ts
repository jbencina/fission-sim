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
 * Human wording for an effective turbine trip cause.
 *
 * The runtime can publish a command latch that disagrees with the last
 * effective turbine state while paused or clearing. The wording mirrors the
 * Phase D P1 rule: operator trip wins, then SCRAM (P-4), then trip clearing.
 */
export function turbineTripCause(frame: Frame | null): string | null {
  if (frame === null || !frame.turbine_trip_active) return null
  if (frame.turbine_trip) return 'operator trip'
  if (frame.scrammed) return 'SCRAM (P-4)'
  return 'trip clearing'
}

/**
 * Secondary-side phrases appended to the schematic title.
 *
 * SG level uses the illustrative 0.40-0.60 normal band, not a trip setpoint.
 */
export function describeSecondaryState(frame: Frame | null): string[] {
  if (frame === null) return []

  const phrases: string[] = []
  if (frame.turbine_trip_active) phrases.push('turbine tripped')
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
