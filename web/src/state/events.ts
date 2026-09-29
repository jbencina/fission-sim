/**
 * Plant events derived from consecutive telemetry frames.
 *
 * The log records what the plant did, not what the UI sent, so every event
 * comes from a change between two frames: the SCRAM latch, turbine trip,
 * secondary-side flows and commands, run state, speed, rod command, a
 * model-limit halt, and a readout crossing one of the illustrative alert
 * bands in thresholds.ts. Pure, so it is unit tested directly.
 */

import type { Frame } from '../types/telemetry'
import { formatNumber } from '../ui/format'
import { type Band, THRESHOLDS, getBand } from '../widgets/thresholds'

export type EventLevel = 'info' | 'warn' | 'alarm'

export interface PlantEvent {
  /** Simulation time of the frame that revealed the event [s]. */
  t: number
  text: string
  level: EventLevel
}

/** Most events the store keeps. */
export const EVENTS_CAP = 100

/** Rod position at or below which the banks count as fully inserted. */
const FULLY_IN = 0.005

/** Dump flow [kg/s] above which the event log calls the steam dump open. */
export const DUMP_FLOW_OPEN_KG_S = 1

/** Relative tolerance for classifying feedwater demand as at a saturation limit. */
const FEEDWATER_SATURATION_REL_TOL = 1e-4

const BAND_LEVEL: Record<Band, EventLevel> = { green: 'info', amber: 'warn', red: 'alarm' }

interface BandedField {
  /** Key in THRESHOLDS. */
  key: string
  name: string
  unit: string
  decimals: number
  /** Convert a raw frame/threshold value to displayed units. */
  displayScale?: number
  value: (f: Frame) => number
}

const BANDED: BandedField[] = [
  { key: 'P_primary_MPa', name: 'Primary pressure', unit: 'MPa', decimals: 1, value: (f) => f.P_primary_MPa },
  { key: 'P_steam_MPa', name: 'Steam pressure', unit: 'MPa', decimals: 1, value: (f) => f.P_steam_MPa },
  {
    key: 'level_sg',
    name: 'SG collapsed liquid fraction',
    unit: '%',
    decimals: 0,
    displayScale: 100,
    value: (f) => f.level_sg,
  },
  { key: 'T_fuel', name: 'Fuel temperature', unit: 'K', decimals: 0, value: (f) => f.T_fuel },
  { key: 'rho_total', name: 'Total reactivity', unit: 'pcm', decimals: 0, value: (f) => f.rho_total * 1e5 },
]

/** Text for a value that just entered `band`, naming the threshold it crossed. */
function crossingText(field: BandedField, value: number, band: Band): string {
  const { name, unit, decimals } = field
  const scale = field.displayScale ?? 1
  if (band === 'green') return `${name} back in its normal band`
  const t = THRESHOLDS[field.key]
  const above = band === 'red' ? t.aboveRed : t.aboveAmber
  const below = band === 'red' ? t.belowRed : t.belowAmber
  if (above !== undefined && value > above) return `${name} above ${formatNumber(above * scale, decimals)} ${unit}`
  if (below !== undefined && value < below) return `${name} below ${formatNumber(below * scale, decimals)} ${unit}`
  return `${name} in the ${band} band`
}

/** Cause string for the effective turbine trip status, matching the UI brief. */
export function turbineTripCause(frame: Frame): 'operator trip' | 'SCRAM (P-4)' | 'trip clearing' | null {
  if (!frame.turbine_trip_active) return null
  if (frame.turbine_trip) return 'operator trip'
  if (frame.scrammed) return 'SCRAM (P-4)'
  return 'trip clearing'
}

type FeedwaterSaturation = 'zero' | 'maximum' | 'other' | null

/**
 * Classify feedwater-controller saturation by the demand's active limit.
 *
 * Returns null when the controller is not saturated, "zero" near 0 kg/s,
 * "maximum" near m_fw_max, and "other" for an unexpected saturated frame.
 */
export function feedwaterSaturation(frame: Frame): FeedwaterSaturation {
  if (!frame.fw_saturated) return null
  const tolerance = Math.max(1e-6, Math.abs(frame.m_fw_max) * FEEDWATER_SATURATION_REL_TOL)
  if (frame.m_fw_demand <= tolerance) return 'zero'
  if (frame.m_fw_max - frame.m_fw_demand <= tolerance) return 'maximum'
  return 'other'
}

function feedwaterSaturationText(kind: Exclude<FeedwaterSaturation, null>): string {
  if (kind === 'zero') return 'Feedwater demand saturated at zero'
  if (kind === 'maximum') return 'Feedwater demand saturated at maximum'
  return 'Feedwater demand saturated'
}

function pendingSuffix(pending: boolean): string {
  return pending ? ' (pending — applies when the simulation runs)' : ''
}

/** Events revealed by `next` following `prev` (null for the first frame). */
export function detectEvents(prev: Frame | null, next: Frame): PlantEvent[] {
  const at = (text: string, level: EventLevel): PlantEvent => ({ t: next.t, text, level })

  if (prev === null) return [at('Telemetry link established', 'info')]
  if (next.t < prev.t) return [at('Simulation reset to the design state', 'info')]

  const out: PlantEvent[] = []

  if (!prev.scrammed && next.scrammed) out.push(at('SCRAM latched, both banks dropping', 'alarm'))
  if (next.scrammed && prev.rod_position > FULLY_IN && next.rod_position <= FULLY_IN) {
    out.push(at('Both banks fully inserted, about −7,000 pcm', 'alarm'))
  }
  if (prev.scrammed && !next.scrammed) out.push(at('SCRAM reset, control bank back to command', 'info'))

  if (!prev.turbine_trip_active && next.turbine_trip_active) {
    out.push(at(`Turbine trip active: ${turbineTripCause(next)}`, 'alarm'))
  }
  if (prev.turbine_trip_active && !next.turbine_trip_active) {
    out.push(at('Turbine trip cleared', 'info'))
  }
  if (!prev.turbine_trip && next.turbine_trip && !next.turbine_trip_active && !next.running) {
    out.push(at(`Turbine trip selected${pendingSuffix(true)}`, 'warn'))
  }
  if (prev.turbine_trip && !next.turbine_trip) {
    const pending = !next.running && next.turbine_trip_active
    const demand = formatNumber(next.turbine_load_demand * 100, 0)
    out.push(
      at(
        `Turbine trip latch reset; admission demand set to ${demand} %${pendingSuffix(pending)}`,
        'info',
      ),
    )
  }

  if (prev.m_dump <= DUMP_FLOW_OPEN_KG_S && next.m_dump > DUMP_FLOW_OPEN_KG_S) {
    out.push(at('Steam dump opened', 'warn'))
  }
  if (prev.m_dump > DUMP_FLOW_OPEN_KG_S && next.m_dump <= DUMP_FLOW_OPEN_KG_S) {
    out.push(at('Steam dump closed', 'info'))
  }

  if (prev.running && !next.running) out.push(at('Paused', 'info'))
  if (!prev.running && next.running) out.push(at('Resumed', 'info'))
  if (prev.speed !== next.speed) out.push(at(`Speed set to ${next.speed}×`, 'info'))
  if (prev.rod_command !== next.rod_command) {
    out.push(at(`Rod command set to ${formatNumber(next.rod_command * 100, 0)} %`, 'info'))
  }
  if (prev.turbine_load_demand !== next.turbine_load_demand) {
    out.push(at(`Turbine admission demand set to ${formatNumber(next.turbine_load_demand * 100, 0)} %`, 'info'))
  }
  if (prev.level_setpoint !== next.level_setpoint) {
    out.push(at(`SG level setpoint set to ${formatNumber(next.level_setpoint * 100, 0)} %`, 'info'))
  }
  if (!prev.rod_auto && next.rod_auto) {
    out.push(at(`Rod control set to AUTO${pendingSuffix(!next.running && !next.rod_auto_acting)}`, 'info'))
  }
  if (prev.rod_auto && !next.rod_auto) out.push(at('Rod control set to MANUAL', 'info'))

  const wasAutoSuspended = prev.running && prev.rod_auto && !prev.rod_auto_acting
  const isAutoSuspended = next.running && next.rod_auto && !next.rod_auto_acting
  if (!wasAutoSuspended && isAutoSuspended) out.push(at('Automatic rod control suspended', 'warn'))
  if (wasAutoSuspended && !isAutoSuspended && next.running && next.rod_auto && next.rod_auto_acting) {
    out.push(at('Automatic rod control resumed', 'info'))
  }

  if (prev.feedwater_manual === null && next.feedwater_manual !== null) {
    out.push(at(`Feedwater set to MANUAL (${formatNumber(next.feedwater_manual * 100, 0)} % max)`, 'info'))
  }
  if (prev.feedwater_manual !== null && next.feedwater_manual === null) out.push(at('Feedwater set to AUTO', 'info'))

  const beforeSaturation = feedwaterSaturation(prev)
  const afterSaturation = feedwaterSaturation(next)
  if (beforeSaturation !== afterSaturation) {
    if (afterSaturation === null) out.push(at('Feedwater demand saturation cleared', 'info'))
    else out.push(at(feedwaterSaturationText(afterSaturation), 'warn'))
  }

  if (prev.model_limit === null && next.model_limit !== null) {
    out.push(at(`Halted: ${next.model_limit}`, 'alarm'))
  }

  for (const field of BANDED) {
    const before = getBand(field.key, field.value(prev))
    const after = getBand(field.key, field.value(next))
    if (before !== after) out.push(at(crossingText(field, field.value(next), after), BAND_LEVEL[after]))
  }

  return out
}
