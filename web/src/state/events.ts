/**
 * Plant events derived from consecutive telemetry frames.
 *
 * The log records what the plant did, not what the UI sent, so every event
 * comes from a change between two frames: the SCRAM latch, the banks
 * reaching full insertion, run state, speed, rod command, a model-limit
 * halt, and a readout crossing one of the illustrative alert bands in
 * thresholds.ts. Pure, so it is unit tested directly.
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

const BAND_LEVEL: Record<Band, EventLevel> = { green: 'info', amber: 'warn', red: 'alarm' }

interface BandedField {
  /** Key in THRESHOLDS. */
  key: string
  name: string
  unit: string
  decimals: number
  value: (f: Frame) => number
}

const BANDED: BandedField[] = [
  { key: 'P_primary_MPa', name: 'Primary pressure', unit: 'MPa', decimals: 1, value: (f) => f.P_primary_MPa },
  { key: 'T_fuel', name: 'Fuel temperature', unit: 'K', decimals: 0, value: (f) => f.T_fuel },
  { key: 'rho_total', name: 'Total reactivity', unit: 'pcm', decimals: 0, value: (f) => f.rho_total * 1e5 },
]

/** Text for a value that just entered `band`, naming the threshold it crossed. */
function crossingText(field: BandedField, value: number, band: Band): string {
  const { name, unit, decimals } = field
  if (band === 'green') return `${name} back in its normal band`
  const t = THRESHOLDS[field.key]
  const above = band === 'red' ? t.aboveRed : t.aboveAmber
  const below = band === 'red' ? t.belowRed : t.belowAmber
  if (above !== undefined && value > above) return `${name} above ${formatNumber(above, decimals)} ${unit}`
  if (below !== undefined && value < below) return `${name} below ${formatNumber(below, decimals)} ${unit}`
  return `${name} in the ${band} band`
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

  if (prev.running && !next.running) out.push(at('Paused', 'info'))
  if (!prev.running && next.running) out.push(at('Resumed', 'info'))
  if (prev.speed !== next.speed) out.push(at(`Speed set to ${next.speed}×`, 'info'))
  if (prev.rod_command !== next.rod_command) {
    out.push(at(`Rod command set to ${formatNumber(next.rod_command * 100, 0)} %`, 'info'))
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
