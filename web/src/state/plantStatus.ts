/**
 * Shared plant-status derivation for controls, readouts and events.
 *
 * The backend publishes both operator-selected fields and last-stepped
 * effective fields. When the simulation is paused, selected fields can change
 * while effective fields remain frozen. These helpers classify one telemetry
 * frame at a time so a newly connected client does not need frame history to
 * understand pending commands.
 *
 * @module plantStatus
 */

import type { Frame } from '../types/telemetry'

/** Visual severity used by the dark-console palette. */
export type StatusTone = 'normal' | 'warn' | 'danger'

/** Level/status band used by readouts and the event log. */
export type PlantBand = 'green' | 'amber' | 'red'

/** Turbine-trip cause when an effective trip is active and attributable. */
export type TurbineTripCause = 'operator trip' | 'SCRAM (P-4)' | 'valves closing'

/** Feedwater-controller saturation limit. */
export type FeedwaterSaturation = 'zero' | 'maximum' | 'other' | null

/** Steam-dump hysteresis input retained by callers such as the event log. */
export interface DumpHysteresisInput {
  /** Whether the dump was previously considered open. */
  wasOpen: boolean
  /** Flow above which a closed dump opens [kg/s]. */
  openKgS?: number
  /** Flow below which an open dump closes [kg/s]. */
  closeKgS?: number
}

/** Effective turbine-trip classification for one telemetry frame. */
export interface TurbineTripStatus {
  /** Stable identifier for tests and conditional styling. */
  kind: 'not-tripped' | 'operator-trip' | 'scram-trip' | 'valves-closing' | 'trip-pending' | 'reset-pending'
  /** Short status text shown in controls or a schematic. */
  label: string
  /** Cause or pending explanation. */
  cause: string
  /** Whether the effective turbine trip is active in the last-stepped plant. */
  active: boolean
  /** True when a paused selected command has not reached the effective plant. */
  pending: boolean
  /** Visual severity for status text. */
  tone: StatusTone
}

/** Automatic rod-control classification for one telemetry frame. */
export interface RodModeStatus {
  /** Stable identifier for tests and conditional styling. */
  kind: 'manual' | 'auto-active' | 'auto-suspended' | 'pending'
  /** Short status text shown in the control-bank panel. */
  label: string
  /** Learner-readable explanation of why the status is shown. */
  detail: string
  /** True when a paused selected mode has not reached the effective plant. */
  pending: boolean
  /** Effective controller activity in the last-stepped plant. */
  effectiveActing: boolean
  /** Visual severity for status text. */
  tone: StatusTone
}

/** Feedwater AUTO/MANUAL and demand classification for one telemetry frame. */
export interface FeedwaterModeStatus {
  /** Stable identifier for tests and conditional styling. */
  kind: 'auto' | 'manual' | 'pending' | 'auto-saturated-zero' | 'auto-saturated-maximum' | 'auto-saturated'
  /** Short status tag shown in the feedwater section. */
  label: string
  /** Learner-readable explanation for HelpTips or aria labels. */
  detail: string
  /** True when a paused selected mode/demand has not reached the effective plant. */
  pending: boolean
  /** Selected command mode from the latest frame. */
  selectedMode: 'auto' | 'manual'
  /** Last-stepped effective command mode. */
  effectiveMode: 'auto' | 'manual'
  /** Selected manual demand [kg/s], or null when AUTO is selected. */
  selectedDemandKgS: number | null
  /** Last-stepped effective manual demand [kg/s], or null when AUTO was effective. */
  effectiveSelectedDemandKgS: number | null
  /** Last-stepped effective feedwater demand [kg/s]. */
  effectiveDemandKgS: number
  /** Active saturation classification, if the effective controller is clipped. */
  saturation: FeedwaterSaturation
  /** Visual severity for status text. */
  tone: StatusTone
}

/** Steam-dump open/closed classification for one telemetry frame. */
export interface DumpStatus {
  /** Whether the dump should be considered open after hysteresis. */
  open: boolean
  /** Flow used for the classification [kg/s]. */
  flowKgS: number
}

/** SG collapsed-level band classification for one telemetry frame. */
export interface LevelStatus {
  /** Display band: green in 40–60 %, amber inside 35–90 %, red outside. */
  band: PlantBand
  /** Collapsed liquid fraction [dimensionless]. */
  level: number
  /** Level error, setpoint minus actual [dimensionless]. */
  error: number
  /** True outside the L1 model validity limits (30–95 %). */
  outsideModelValidity: boolean
}

/** Pending explanation shared across controls, readouts and events. */
export const PENDING_DETAIL = 'pending — applies when the simulation runs'

/** Dump opens above this steam flow [kg/s]. */
export const DUMP_FLOW_OPEN_KG_S = 1

/** Dump closes below this steam flow [kg/s], giving hysteresis around opening. */
export const DUMP_FLOW_CLOSE_KG_S = 0.5

/** Relative tolerance for classifying feedwater demand at a clipped limit. */
export const FEEDWATER_SATURATION_REL_TOL = 1e-4

const FLOW_EPS_KG_S = 1e-6
const DEMAND_TOL_REL = 1e-6
const DEMAND_TOL_ABS_KG_S = 1e-3
const LEVEL_VALID_LOW = 0.30
const LEVEL_VALID_HIGH = 0.95
const LEVEL_RED_LOW = 0.35
const LEVEL_GREEN_LOW = 0.40
const LEVEL_GREEN_HIGH = 0.60
const LEVEL_RED_HIGH = 0.90

type TurbineTripFrame = Pick<Frame, 'running' | 'turbine_trip_active' | 'turbine_trip' | 'scrammed'>
type RodStatusFrame = Pick<Frame, 'running' | 'rod_auto' | 'rod_auto_acting' | 'scrammed'> & TurbineTripFrame
type FeedwaterStatusFrame = Pick<
  Frame,
  | 'running'
  | 'feedwater_manual'
  | 'feedwater_manual_effective'
  | 'fw_saturated'
  | 'm_fw_demand'
  | 'm_fw_max'
>
type DumpStatusFrame = Pick<Frame, 'm_dump'>
type LevelStatusFrame = Pick<Frame, 'level_sg' | 'level_setpoint'>

function demandTolerance(maxKgS: number): number {
  return Math.max(DEMAND_TOL_ABS_KG_S, Math.abs(maxKgS) * DEMAND_TOL_REL)
}

function demandChanged(a: number | null, b: number | null, maxKgS: number): boolean {
  if (a === null || b === null) return a !== b
  return Math.abs(a - b) > demandTolerance(maxKgS)
}

function feedwaterDemandFromFraction(fraction: number | null, maxKgS: number): number | null {
  return fraction === null ? null : clampFraction(fraction) * Math.max(maxKgS, 0)
}

/**
 * Clamp a fractional command to the backend's command range [0, 1].
 *
 * Parameters
 * ----------
 * value:
 *   Fractional command or demand [dimensionless].
 *
 * Returns
 * -------
 * number
 *   `value` limited to the closed interval [0, 1].
 */
export function clampFraction(value: number): number {
  if (!Number.isFinite(value)) return 0
  return Math.min(1, Math.max(0, value))
}

/**
 * Return the attributable turbine-trip cause for one frame.
 *
 * Parameters
 * ----------
 * frame:
 *   Telemetry fields carrying the operator trip latch, SCRAM latch, and
 *   effective turbine trip state.
 *
 * Returns
 * -------
 * TurbineTripCause | null
 *   Operator trip, SCRAM/P-4, valves closing after latch clearing, or null
 *   when no effective turbine trip is active.
 */
export function turbineTripCause(frame: TurbineTripFrame): TurbineTripCause | null {
  if (!frame.turbine_trip_active) return null
  if (frame.turbine_trip) return 'operator trip'
  if (frame.scrammed) return 'SCRAM (P-4)'
  return 'valves closing'
}

/**
 * Derive the effective turbine-trip status and pending state.
 *
 * Parameters
 * ----------
 * frame:
 *   Telemetry fields carrying selected turbine-trip commands and the
 *   last-stepped effective trip state.
 *
 * Returns
 * -------
 * TurbineTripStatus
 *   Label, cause, active flag, pending flag and tone for turbine trip UI.
 */
export function deriveTurbineTripStatus(frame: TurbineTripFrame): TurbineTripStatus {
  const selectedActive = frame.turbine_trip || frame.scrammed

  if (!frame.running && frame.turbine_trip_active !== selectedActive) {
    return frame.turbine_trip_active
      ? {
          kind: 'reset-pending',
          label: 'RESET PENDING',
          cause: PENDING_DETAIL,
          active: true,
          pending: true,
          tone: 'warn',
        }
      : {
          kind: 'trip-pending',
          label: 'TRIP PENDING',
          cause: PENDING_DETAIL,
          active: false,
          pending: true,
          tone: 'warn',
        }
  }

  if (frame.turbine_trip_active) {
    const cause = turbineTripCause(frame)
    if (cause === 'operator trip') {
      return {
        kind: 'operator-trip',
        label: 'TRIPPED',
        cause,
        active: true,
        pending: false,
        tone: 'danger',
      }
    }
    if (cause === 'SCRAM (P-4)') {
      return {
        kind: 'scram-trip',
        label: 'TRIPPED',
        cause,
        active: true,
        pending: false,
        tone: 'danger',
      }
    }
    return {
      kind: 'valves-closing',
      label: 'VALVES CLOSING',
      cause: 'valves closing after trip reset',
      active: true,
      pending: false,
      tone: 'warn',
    }
  }

  if (selectedActive) {
    return {
      kind: 'trip-pending',
      label: 'TRIP PENDING',
      cause: frame.running ? 'command accepted; valves update on the next step' : PENDING_DETAIL,
      active: false,
      pending: !frame.running,
      tone: 'warn',
    }
  }

  return {
    kind: 'not-tripped',
    label: 'NOT TRIPPED',
    cause: 'turbine admission is available',
    active: false,
    pending: false,
    tone: 'normal',
  }
}

/**
 * Derive the control-bank AUTO/MANUAL status for one frame.
 *
 * Parameters
 * ----------
 * frame:
 *   Telemetry fields carrying the selected rod mode, effective controller
 *   action and trip/SCRAM suspension causes.
 *
 * Returns
 * -------
 * RodModeStatus
 *   Label, explanation, pending flag and severity for the control-bank UI.
 */
export function deriveRodModeStatus(frame: RodStatusFrame): RodModeStatus {
  const tripStatus = deriveTurbineTripStatus(frame)

  if (!frame.rod_auto) {
    if (!frame.running && frame.rod_auto_acting) {
      return {
        kind: 'pending',
        label: 'PENDING',
        detail: PENDING_DETAIL,
        pending: true,
        effectiveActing: frame.rod_auto_acting,
        tone: 'warn',
      }
    }
    return {
      kind: 'manual',
      label: 'MANUAL',
      detail: 'Operator rod command is the active demand.',
      pending: false,
      effectiveActing: frame.rod_auto_acting,
      tone: 'normal',
    }
  }

  if (frame.rod_auto_acting) {
    return {
      kind: 'auto-active',
      label: 'AUTO ACTIVE',
      detail: 'Automatic Tavg control is driving rod demand.',
      pending: false,
      effectiveActing: true,
      tone: 'normal',
    }
  }

  if (frame.scrammed) {
    return {
      kind: 'auto-suspended',
      label: 'AUTO SUSPENDED',
      detail: 'Automatic rod motion is suspended by SCRAM.',
      pending: false,
      effectiveActing: false,
      tone: 'warn',
    }
  }

  if (tripStatus.active && !tripStatus.pending) {
    return {
      kind: 'auto-suspended',
      label: 'AUTO SUSPENDED',
      detail: 'Automatic rod motion is suspended by turbine trip.',
      pending: false,
      effectiveActing: false,
      tone: 'warn',
    }
  }

  if (!frame.running) {
    return {
      kind: 'pending',
      label: 'PENDING',
      detail: PENDING_DETAIL,
      pending: true,
      effectiveActing: false,
      tone: 'warn',
    }
  }

  return {
    kind: 'auto-suspended',
    label: 'AUTO SUSPENDED',
    detail: 'Automatic rod motion is suspended by controller logic.',
    pending: false,
    effectiveActing: false,
    tone: 'warn',
  }
}

/**
 * Convert the effective feedwater demand to the manual-command fraction.
 *
 * Parameters
 * ----------
 * frame:
 *   Telemetry fields carrying demand and maximum feedwater flow [kg/s].
 *
 * Returns
 * -------
 * number
 *   Current demand as a fraction of maximum feedwater flow [dimensionless].
 */
export function feedwaterDemandFraction(frame: Pick<Frame, 'm_fw_demand' | 'm_fw_max'>): number {
  if (frame.m_fw_max <= 0) return 0
  return clampFraction(frame.m_fw_demand / frame.m_fw_max)
}

/**
 * Classify feedwater-controller saturation by the active demand limit.
 *
 * Parameters
 * ----------
 * frame:
 *   Telemetry fields carrying saturation flag, demand [kg/s] and max flow
 *   [kg/s].
 *
 * Returns
 * -------
 * FeedwaterSaturation
 *   null when not saturated, otherwise zero, maximum, or other.
 */
export function feedwaterSaturation(
  frame: Pick<Frame, 'fw_saturated' | 'm_fw_demand' | 'm_fw_max'>,
): FeedwaterSaturation {
  if (!frame.fw_saturated) return null
  const tolerance = Math.max(FLOW_EPS_KG_S, Math.abs(frame.m_fw_max) * FEEDWATER_SATURATION_REL_TOL)
  if (frame.m_fw_demand <= tolerance) return 'zero'
  if (frame.m_fw_max - frame.m_fw_demand <= tolerance) return 'maximum'
  return 'other'
}

/**
 * Derive the feedwater AUTO/MANUAL, pending and saturation status.
 *
 * Parameters
 * ----------
 * frame:
 *   Telemetry fields carrying selected and effective feedwater mode/demand.
 *
 * Returns
 * -------
 * FeedwaterModeStatus
 *   Label, explanation, selected/effective demands and saturation state.
 */
export function deriveFeedwaterModeStatus(frame: FeedwaterStatusFrame): FeedwaterModeStatus {
  const selectedMode: 'auto' | 'manual' = frame.feedwater_manual === null ? 'auto' : 'manual'
  const effectiveMode: 'auto' | 'manual' = frame.feedwater_manual_effective === null ? 'auto' : 'manual'
  const selectedDemandKgS = feedwaterDemandFromFraction(frame.feedwater_manual, frame.m_fw_max)
  const effectiveSelectedDemandKgS = feedwaterDemandFromFraction(frame.feedwater_manual_effective, frame.m_fw_max)
  const pending =
    !frame.running &&
    (selectedMode !== effectiveMode || demandChanged(selectedDemandKgS, effectiveSelectedDemandKgS, frame.m_fw_max))
  const activeMode: 'auto' | 'manual' = pending || frame.running ? effectiveMode : selectedMode
  const saturation = activeMode === 'auto' ? feedwaterSaturation(frame) : null
  const common = {
    pending,
    selectedMode,
    effectiveMode,
    selectedDemandKgS,
    effectiveSelectedDemandKgS,
    effectiveDemandKgS: frame.m_fw_demand,
    saturation,
  }

  if (pending) {
    return {
      ...common,
      kind: 'pending',
      label: 'PENDING',
      detail: PENDING_DETAIL,
      tone: 'warn',
    }
  }

  if (activeMode === 'manual') {
    return {
      ...common,
      kind: 'manual',
      label: 'MANUAL',
      detail: 'Operator manual feedwater demand is active.',
      tone: 'warn',
    }
  }

  if (saturation === null) {
    return {
      ...common,
      kind: 'auto',
      label: 'AUTO',
      detail: 'Automatic SG level control is active.',
      tone: 'normal',
    }
  }

  if (saturation === 'zero') {
    return {
      ...common,
      kind: 'auto-saturated-zero',
      label: 'AUTO · saturated at zero',
      detail: 'Automatic level control wants less than zero feedwater, so demand is clipped at 0 kg/s.',
      tone: 'warn',
    }
  }

  if (saturation === 'maximum') {
    return {
      ...common,
      kind: 'auto-saturated-maximum',
      label: 'AUTO · saturated at maximum',
      detail: 'Automatic level control wants more feedwater than the actuator can provide.',
      tone: 'warn',
    }
  }

  return {
    ...common,
    kind: 'auto-saturated',
    label: 'AUTO · saturated',
    detail: 'Automatic level control is clipped at a feedwater-flow limit.',
    tone: 'warn',
  }
}

/**
 * Classify whether the steam dump is open, with optional hysteresis.
 *
 * Parameters
 * ----------
 * frame:
 *   Telemetry fields carrying dump steam flow [kg/s].
 * hysteresis:
 *   Previous open state plus optional open/close thresholds [kg/s]. Omit for
 *   an instantaneous one-frame status.
 *
 * Returns
 * -------
 * DumpStatus
 *   Open flag and flow used for the classification.
 */
export function deriveDumpStatus(frame: DumpStatusFrame, hysteresis?: DumpHysteresisInput): DumpStatus {
  if (hysteresis === undefined) {
    return { open: frame.m_dump > DUMP_FLOW_OPEN_KG_S, flowKgS: frame.m_dump }
  }

  const openThreshold = hysteresis.openKgS ?? DUMP_FLOW_OPEN_KG_S
  const closeThreshold = hysteresis.closeKgS ?? DUMP_FLOW_CLOSE_KG_S
  const open = hysteresis.wasOpen ? frame.m_dump >= closeThreshold : frame.m_dump > openThreshold
  return { open, flowKgS: frame.m_dump }
}

/**
 * Classify SG collapsed liquid fraction into display and validity bands.
 *
 * Parameters
 * ----------
 * frame:
 *   Telemetry fields carrying SG collapsed level and level setpoint
 *   [dimensionless fractions].
 *
 * Returns
 * -------
 * LevelStatus
 *   Level, setpoint error, display band and model-validity flag.
 */
export function deriveLevelStatus(frame: LevelStatusFrame): LevelStatus {
  const level = frame.level_sg
  const band: PlantBand =
    level < LEVEL_RED_LOW || level > LEVEL_RED_HIGH
      ? 'red'
      : level < LEVEL_GREEN_LOW || level > LEVEL_GREEN_HIGH
        ? 'amber'
        : 'green'
  return {
    band,
    level,
    error: frame.level_setpoint - level,
    outsideModelValidity: level < LEVEL_VALID_LOW || level > LEVEL_VALID_HIGH,
  }
}
