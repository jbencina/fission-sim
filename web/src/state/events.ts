/**
 * Plant events derived from telemetry frames plus explicit event-tracker state.
 *
 * The event log records plant-visible transitions: SCRAM, effective turbine
 * trip, steam dump, run state, commands, model-limit halts and illustrative
 * alert-band crossings. Most transitions come from `(prev, next)`, while
 * hysteresis/debounce state is carried by `EventTracker` so the logic stays
 * pure and testable.
 */

import type { Frame } from '../types/telemetry'
import { formatNumber } from '../ui/format'
import { type Band, THRESHOLDS, getBand } from '../widgets/thresholds'
import {
  DUMP_FLOW_CLOSE_KG_S,
  DUMP_FLOW_OPEN_KG_S,
  PENDING_DETAIL,
  deriveDumpStatus,
  deriveFeedwaterModeStatus,
  deriveRodModeStatus,
  deriveTurbineTripStatus,
  feedwaterSaturation,
  type FeedwaterSaturation,
} from './plantStatus'

export type EventLevel = 'info' | 'warn' | 'alarm'

export interface PlantEvent {
  /** Simulation time of the frame that revealed the event [s]. */
  t: number
  text: string
  level: EventLevel
}

/** Explicit state carried by the store between pure event detections. */
export interface EventTracker {
  /** Whether the steam dump was last considered open after hysteresis. */
  dumpOpen: boolean
  /** Last effective rod AUTO activity state from accepted telemetry. */
  rodAutoActing: boolean
  /** Stable feedwater saturation state after debounce. */
  feedwaterSaturation: FeedwaterSaturation
  /** Candidate saturation state waiting to satisfy the dwell time. */
  feedwaterSaturationCandidate: FeedwaterSaturation
  /** Simulation time when the candidate saturation state first appeared [s]. */
  feedwaterSaturationCandidateSince: number | null
}

/** Result of pure event detection: new events plus the next tracker. */
export interface EventDetection {
  events: PlantEvent[]
  tracker: EventTracker
}

/** Most events the store keeps. */
export const EVENTS_CAP = 100

/** Rod position at or below which the banks count as fully inserted. */
const FULLY_IN = 0.005

/** Dwell required before feedwater saturation enter/leave events are logged [s]. */
export const FEEDWATER_SATURATION_DWELL_S = 0.3

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

/**
 * Build event-tracker state from a single frame.
 *
 * Parameters
 * ----------
 * frame:
 *   Telemetry frame to seed from, or null before the first frame arrives.
 *
 * Returns
 * -------
 * EventTracker
 *   Tracker matching the provided frame without emitting any events.
 */
export function initialEventTracker(frame: Frame | null = null): EventTracker {
  return {
    dumpOpen: frame === null ? false : deriveDumpStatus(frame).open,
    rodAutoActing: frame?.rod_auto_acting ?? false,
    feedwaterSaturation: frame === null ? null : feedwaterSaturation(frame),
    feedwaterSaturationCandidate: null,
    feedwaterSaturationCandidateSince: null,
  }
}

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

function feedwaterSaturationText(kind: Exclude<FeedwaterSaturation, null>): string {
  if (kind === 'zero') return 'Feedwater demand saturated at zero'
  if (kind === 'maximum') return 'Feedwater demand saturated at maximum'
  return 'Feedwater demand saturated'
}

function pendingSuffix(pending: boolean): string {
  return pending ? ` (${PENDING_DETAIL})` : ''
}

function turbineAdmissionPending(frame: Frame): boolean {
  return !frame.running && Math.abs(frame.turbine_load_demand - frame.turbine_load_demand_effective) > 1e-6
}

function updateFeedwaterSaturationTracker(
  tracker: EventTracker,
  observed: FeedwaterSaturation,
  t: number,
  out: PlantEvent[],
  at: (text: string, level: EventLevel) => PlantEvent,
): EventTracker {
  if (observed === tracker.feedwaterSaturation) {
    return {
      ...tracker,
      feedwaterSaturationCandidate: null,
      feedwaterSaturationCandidateSince: null,
    }
  }

  if (observed !== tracker.feedwaterSaturationCandidate || tracker.feedwaterSaturationCandidateSince === null) {
    return {
      ...tracker,
      feedwaterSaturationCandidate: observed,
      feedwaterSaturationCandidateSince: t,
    }
  }

  const since = tracker.feedwaterSaturationCandidateSince ?? t
  if (t - since < FEEDWATER_SATURATION_DWELL_S) return tracker

  if (observed === null) out.push(at('Feedwater demand saturation cleared', 'info'))
  else out.push(at(feedwaterSaturationText(observed), 'warn'))

  return {
    ...tracker,
    feedwaterSaturation: observed,
    feedwaterSaturationCandidate: null,
    feedwaterSaturationCandidateSince: null,
  }
}

/**
 * Events revealed by `next` following `prev`, plus updated hysteresis state.
 *
 * Parameters
 * ----------
 * prev:
 *   Previous telemetry frame, or null for the first frame after connect.
 * next:
 *   Current telemetry frame.
 * tracker:
 *   Explicit state retained by the caller for hysteresis/debounce. When
 *   omitted, it is seeded from `prev`, which is convenient for unit tests
 *   that examine one transition.
 *
 * Returns
 * -------
 * EventDetection
 *   New events and the tracker to carry to the next call.
 */
export function detectEvents(
  prev: Frame | null,
  next: Frame,
  tracker: EventTracker = initialEventTracker(prev),
): EventDetection {
  const at = (text: string, level: EventLevel): PlantEvent => ({ t: next.t, text, level })

  if (prev === null) return { events: [at('Telemetry link established', 'info')], tracker: initialEventTracker(next) }
  if (next.t < prev.t) return { events: [at('Simulation reset to the design state', 'info')], tracker: initialEventTracker(next) }

  const out: PlantEvent[] = []
  let nextTracker: EventTracker = { ...tracker }
  const tripStatus = deriveTurbineTripStatus(next)
  const rodStatus = deriveRodModeStatus(next)
  const feedwaterStatus = deriveFeedwaterModeStatus(next)

  if (!prev.scrammed && next.scrammed) out.push(at('SCRAM latched, both banks dropping', 'alarm'))
  if (next.scrammed && prev.rod_position > FULLY_IN && next.rod_position <= FULLY_IN) {
    out.push(at('Both banks fully inserted, about −7,000 pcm', 'alarm'))
  }
  if (prev.scrammed && !next.scrammed) out.push(at('SCRAM reset, control bank back to command', 'info'))

  if (!prev.turbine_trip_active && next.turbine_trip_active && !tripStatus.pending) {
    out.push(at(`Turbine trip active: ${tripStatus.cause}`, 'alarm'))
  }
  if (prev.turbine_trip_active && !next.turbine_trip_active) {
    out.push(at('Turbine trip cleared', 'info'))
  }
  if (!prev.turbine_trip && next.turbine_trip && !next.turbine_trip_active) {
    out.push(at(`Turbine trip selected${pendingSuffix(tripStatus.pending)}`, 'warn'))
  }
  if (prev.turbine_trip && !next.turbine_trip) {
    const demand = formatNumber(next.turbine_load_demand * 100, 0)
    out.push(
      at(
        `Turbine trip latch reset; admission demand set to ${demand} %${pendingSuffix(tripStatus.pending)}`,
        'info',
      ),
    )
  }

  const dumpStatus = deriveDumpStatus(next, {
    wasOpen: nextTracker.dumpOpen,
    openKgS: DUMP_FLOW_OPEN_KG_S,
    closeKgS: DUMP_FLOW_CLOSE_KG_S,
  })
  if (!nextTracker.dumpOpen && dumpStatus.open) out.push(at('Steam dump opened', 'warn'))
  if (nextTracker.dumpOpen && !dumpStatus.open) out.push(at('Steam dump closed', 'info'))
  nextTracker.dumpOpen = dumpStatus.open

  if (prev.running && !next.running) out.push(at('Paused', 'info'))
  if (!prev.running && next.running) out.push(at('Resumed', 'info'))
  if (prev.speed !== next.speed) out.push(at(`Speed set to ${next.speed}×`, 'info'))
  if (prev.rod_command !== next.rod_command) {
    out.push(at(`Rod command set to ${formatNumber(next.rod_command * 100, 0)} %`, 'info'))
  }
  if (prev.turbine_load_demand !== next.turbine_load_demand) {
    out.push(
      at(
        `Turbine admission demand set to ${formatNumber(next.turbine_load_demand * 100, 0)} %${pendingSuffix(
          turbineAdmissionPending(next),
        )}`,
        'info',
      ),
    )
  }
  if (prev.level_setpoint !== next.level_setpoint) {
    out.push(at(`SG level setpoint set to ${formatNumber(next.level_setpoint * 100, 0)} %`, 'info'))
  }
  if (!prev.rod_auto && next.rod_auto) {
    out.push(at(`Rod control set to AUTO${pendingSuffix(rodStatus.pending)}`, 'info'))
  }
  if (prev.rod_auto && !next.rod_auto) {
    out.push(at(`Rod control set to MANUAL${pendingSuffix(rodStatus.pending)}`, 'info'))
  }

  if (
    nextTracker.rodAutoActing &&
    !next.rod_auto_acting &&
    prev.rod_auto &&
    next.rod_auto &&
    rodStatus.kind === 'auto-suspended'
  ) {
    out.push(at('Automatic rod control suspended', 'warn'))
  }
  if (!nextTracker.rodAutoActing && next.rod_auto_acting && prev.rod_auto && next.rod_auto) {
    out.push(at('Automatic rod control resumed', 'info'))
  }
  nextTracker.rodAutoActing = next.rod_auto_acting

  if (prev.feedwater_manual === null && next.feedwater_manual !== null) {
    out.push(
      at(
        `Feedwater set to MANUAL (${formatNumber(next.feedwater_manual * 100, 0)} % max)${pendingSuffix(
          feedwaterStatus.pending,
        )}`,
        'info',
      ),
    )
  }
  if (prev.feedwater_manual !== null && next.feedwater_manual === null) {
    out.push(at(`Feedwater set to AUTO${pendingSuffix(feedwaterStatus.pending)}`, 'info'))
  }

  nextTracker = updateFeedwaterSaturationTracker(
    nextTracker,
    feedwaterSaturation(next),
    next.t,
    out,
    at,
  )

  if (prev.model_limit === null && next.model_limit !== null) {
    out.push(at(`Halted: ${next.model_limit}`, 'alarm'))
  }

  for (const field of BANDED) {
    const before = getBand(field.key, field.value(prev))
    const after = getBand(field.key, field.value(next))
    if (before !== after) out.push(at(crossingText(field, field.value(next), after), BAND_LEVEL[after]))
  }

  return { events: out, tracker: nextTracker }
}
