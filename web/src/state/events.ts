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
  type FeedwaterSaturation,
} from './plantStatus'

export type EventLevel = 'info' | 'warn' | 'alarm'

/**
 * Event category exported for the event-log UI's filter controls.
 *
 * `command` marks routine operator commands such as slider/setpoint changes;
 * `plant` marks plant-visible state transitions; `alarm` marks protective,
 * trip, halt, or red-band conditions that should stay visible by default.
 */
export const EVENT_CATEGORIES = ['plant', 'command', 'alarm'] as const

/** Category used to filter events without parsing their text. */
export type EventCategory = (typeof EVENT_CATEGORIES)[number]

export interface PlantEvent {
  /** Simulation time of the frame that revealed the event [s]. */
  t: number
  /** Browser receipt time for coalescing operator-command bursts [ms]. */
  receivedAtMs: number
  text: string
  level: EventLevel
  category: EventCategory
  /** Same-key command events replace the previous one when consecutive. */
  coalesceKey?: CommandCoalesceKey
}

export type CommandCoalesceKey =
  | 'rod-command'
  | 'turbine-admission-demand'
  | 'level-setpoint'
  | 'feedwater-manual-demand'

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

/** Wall-clock receipt-time window for merging one operator interaction [ms]. */
export const COMMAND_COALESCE_WINDOW_MS = 1_000

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
    feedwaterSaturation: frame === null ? null : deriveFeedwaterModeStatus(frame).saturation,
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

function feedwaterManualDemandValueText(fraction: number, maxKgS: number): string {
  return `${formatNumber(fraction * 100, 0)} % max (${formatNumber(fraction * maxKgS, 0)} kg/s)`
}

function feedwaterManualDemandText(fraction: number, maxKgS: number): string {
  return `manual demand ${feedwaterManualDemandValueText(fraction, maxKgS)}`
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
 * Append new events, replacing only same-interaction routine commands.
 *
 * Parameters
 * ----------
 * existing:
 *   Retained event history, oldest first.
 * fresh:
 *   Newly detected events for the current frame.
 *
 * Returns
 * -------
 * PlantEvent[]
 *   Event history where consecutive demand changes with the same
 *   `coalesceKey` keep only the final value if their browser receipt times
 *   are within `COMMAND_COALESCE_WINDOW_MS`. Distinct actions, mode transfers,
 *   alarms, commands separated by any other event, and later adjustments are
 *   never merged.
 */
export function mergeCoalescedEvents(existing: PlantEvent[], fresh: PlantEvent[]): PlantEvent[] {
  const merged = [...existing]
  for (const event of fresh) {
    const last = merged[merged.length - 1]
    if (
      event.coalesceKey !== undefined &&
      last?.coalesceKey === event.coalesceKey &&
      event.receivedAtMs >= last.receivedAtMs &&
      event.receivedAtMs - last.receivedAtMs <= COMMAND_COALESCE_WINDOW_MS
    ) {
      merged[merged.length - 1] = event
    } else {
      merged.push(event)
    }
  }
  return merged
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
 * receivedAtMs:
 *   Browser receipt time [ms]. The telemetry store supplies a clock that
 *   advances while paused so command burst coalescing is not tied to
 *   simulation time.
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
  receivedAtMs = 0,
): EventDetection {
  const at = (
    text: string,
    level: EventLevel,
    category: EventCategory = level === 'alarm' ? 'alarm' : 'plant',
    coalesceKey?: CommandCoalesceKey,
  ): PlantEvent => ({
    t: next.t,
    receivedAtMs,
    text,
    level,
    category,
    coalesceKey,
  })

  if (prev === null) return { events: [at('Telemetry link established', 'info')], tracker: initialEventTracker(next) }
  if (next.t < prev.t) return { events: [at('Simulation reset to the design state', 'info')], tracker: initialEventTracker(next) }

  const out: PlantEvent[] = []
  let nextTracker: EventTracker = { ...tracker }
  const tripStatus = deriveTurbineTripStatus(next)
  const rodStatus = deriveRodModeStatus(next)
  const feedwaterStatus = deriveFeedwaterModeStatus(next)

  if (!prev.scrammed && next.scrammed) {
    out.push(
      at(next.running ? 'SCRAM latched, both banks dropping' : 'SCRAM selected; insertion pending on resume', 'alarm'),
    )
  }
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
    out.push(at(`Turbine trip selected${pendingSuffix(tripStatus.pending)}`, 'warn', 'alarm'))
  }
  if (prev.turbine_trip && !next.turbine_trip) {
    const demand = formatNumber(next.turbine_load_demand * 100, 0)
    out.push(
      at(
        `Turbine trip latch reset; admission demand set to ${demand} %${pendingSuffix(tripStatus.pending)}`,
        'info',
        'command',
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

  if (prev.running && !next.running) out.push(at('Paused', 'info', 'command'))
  if (!prev.running && next.running) out.push(at('Resumed', 'info', 'command'))
  if (prev.speed !== next.speed) out.push(at(`Speed set to ${next.speed}×`, 'info', 'command'))
  if (prev.rod_command !== next.rod_command) {
    out.push(at(`Rod command set to ${formatNumber(next.rod_command * 100, 0)} %`, 'info', 'command', 'rod-command'))
  }
  if (prev.turbine_load_demand !== next.turbine_load_demand) {
    out.push(
      at(
        `Turbine admission demand set to ${formatNumber(next.turbine_load_demand * 100, 0)} %${pendingSuffix(
          turbineAdmissionPending(next),
        )}`,
        'info',
        'command',
        'turbine-admission-demand',
      ),
    )
  }
  if (prev.level_setpoint !== next.level_setpoint) {
    out.push(
      at(
        `SG level setpoint set to ${formatNumber(next.level_setpoint * 100, 0)} %`,
        'info',
        'command',
        'level-setpoint',
      ),
    )
  }
  if (!prev.rod_auto && next.rod_auto) {
    out.push(at(`Rod control set to AUTO${pendingSuffix(rodStatus.pending)}`, 'info', 'command'))
  }
  if (prev.rod_auto && !next.rod_auto) {
    out.push(at(`Rod control set to MANUAL${pendingSuffix(rodStatus.pending)}`, 'info', 'command'))
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
        `Feedwater set to MANUAL; ${feedwaterManualDemandText(next.feedwater_manual, next.m_fw_max)}${pendingSuffix(
          feedwaterStatus.pending,
        )}`,
        'info',
        'command',
      ),
    )
  }
  if (prev.feedwater_manual !== null && next.feedwater_manual === null) {
    out.push(at(`Feedwater set to AUTO${pendingSuffix(feedwaterStatus.pending)}`, 'info', 'command'))
  }
  if (
    prev.feedwater_manual !== null &&
    next.feedwater_manual !== null &&
    prev.feedwater_manual !== next.feedwater_manual
  ) {
    out.push(
      at(
        `Feedwater manual demand set to ${feedwaterManualDemandValueText(next.feedwater_manual, next.m_fw_max)}${pendingSuffix(
          feedwaterStatus.pending,
        )}`,
        'info',
        'command',
        'feedwater-manual-demand',
      ),
    )
  }

  nextTracker = updateFeedwaterSaturationTracker(
    nextTracker,
    feedwaterStatus.saturation,
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
