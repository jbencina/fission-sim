/**
 * Pure status derivation for operator controls.
 *
 * The backend publishes both operator-selected command fields and effective
 * plant state. While paused or halted, command fields can update before the
 * frozen plant has stepped, so these helpers centralize the "pending" wording
 * used by the controls.
 */

import type { Frame } from '../types/telemetry'

type RodStatusFrame = Pick<
  Frame,
  'running' | 'rod_auto' | 'rod_auto_acting' | 'scrammed' | 'turbine_trip' | 'turbine_trip_active'
>
type TripStatusFrame = Pick<Frame, 'running' | 'turbine_trip_active' | 'turbine_trip' | 'scrammed'>
type FeedwaterStatusFrame = Pick<Frame, 'running' | 'feedwater_manual' | 'fw_saturated' | 'm_fw_demand' | 'm_fw_max'>

export type StatusTone = 'normal' | 'warn' | 'danger'

export interface RodModeStatus {
  /** Stable identifier for tests and conditional styling. */
  kind: 'manual' | 'auto-active' | 'auto-suspended' | 'pending'
  /** Short status text shown in the control-bank panel. */
  label: string
  /** Learner-readable explanation of why the status is shown. */
  detail: string
  /** Visual severity for the existing dark-console palette. */
  tone: StatusTone
}

export interface TurbineTripStatus {
  /** Stable identifier for tests and conditional styling. */
  kind: 'not-tripped' | 'operator-trip' | 'scram-trip' | 'trip-clearing' | 'trip-pending' | 'clear-pending'
  /** Short status text shown next to the turbine controls. */
  label: string
  /** Cause or pending explanation. */
  cause: string
  /** Whether the effective turbine trip is active in the last-stepped plant state. */
  active: boolean
  /** Visual severity for the existing dark-console palette. */
  tone: StatusTone
}

export interface FeedwaterModeStatus {
  /** Stable identifier for tests and conditional styling. */
  kind: 'auto' | 'manual' | 'pending' | 'auto-saturated-zero' | 'auto-saturated-maximum' | 'auto-saturated'
  /** Short status tag shown in the feedwater section. */
  label: string
  /** Learner-readable explanation for HelpTips or aria labels. */
  detail: string
  /** Visual severity for the existing dark-console palette. */
  tone: StatusTone
  /** Selected command mode from the latest frame. */
  selectedMode: 'auto' | 'manual'
  /** Last-stepped effective command mode when known. */
  effectiveMode: 'auto' | 'manual'
  /** Selected manual demand [kg/s], or null when AUTO is selected. */
  selectedDemandKgS: number | null
  /** Last-stepped effective feedwater demand [kg/s]. */
  effectiveDemandKgS: number
}

const FLOW_EPS = 1e-6
const FEEDWATER_DEMAND_TOL_KG_S = 1e-3

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
 * Find the newest frame that was produced while simulation time was running.
 *
 * Parameters
 * ----------
 * history:
 *   Telemetry history, oldest to newest.
 * latest:
 *   Latest telemetry frame, or null before the first frame arrives.
 *
 * Returns
 * -------
 * Frame | null
 *   `latest` while running; otherwise the newest running frame in `history`,
 *   falling back to `latest` when the UI has only paused frames.
 */
export function findLastRunningFrame(history: readonly Frame[], latest: Frame | null): Frame | null {
  if (latest === null) return null
  if (latest.running) return latest
  for (let i = history.length - 1; i >= 0; i -= 1) {
    if (history[i].running) return history[i]
  }
  return latest
}

/**
 * Derive the control-bank AUTO/MANUAL status line.
 *
 * Parameters
 * ----------
 * frame:
 *   Telemetry fields carrying the selected rod mode and effective action.
 *
 * Returns
 * -------
 * RodModeStatus
 *   The label, explanation and severity for the status line.
 */
export function deriveRodModeStatus(frame: RodStatusFrame): RodModeStatus {
  const expectedActing = frame.rod_auto && !frame.scrammed && !frame.turbine_trip

  if (!frame.running && frame.rod_auto_acting !== expectedActing) {
    return {
      kind: 'pending',
      label: 'PENDING',
      detail: 'pending — applies when the simulation runs',
      tone: 'warn',
    }
  }

  if (!frame.rod_auto) {
    return {
      kind: 'manual',
      label: 'MANUAL',
      detail: 'Operator rod command is the active demand.',
      tone: 'normal',
    }
  }

  if (frame.rod_auto_acting) {
    return {
      kind: 'auto-active',
      label: 'AUTO ACTIVE',
      detail: 'Automatic Tavg control is driving rod demand.',
      tone: 'normal',
    }
  }

  const suspendedBy = frame.scrammed
    ? 'SCRAM'
    : frame.turbine_trip || frame.turbine_trip_active
      ? 'turbine trip'
      : 'controller logic'
  return {
    kind: 'auto-suspended',
    label: 'AUTO SUSPENDED',
    detail: `Automatic rod motion is suspended by ${suspendedBy}.`,
    tone: 'warn',
  }
}

/**
 * Derive the effective turbine-trip status and cause.
 *
 * Parameters
 * ----------
 * frame:
 *   Telemetry fields carrying the operator trip latch, SCRAM latch, and
 *   effective turbine trip state.
 *
 * Returns
 * -------
 * TurbineTripStatus
 *   The label, cause and severity for the turbine-trip indicator.
 */
export function deriveTurbineTripStatus(frame: TripStatusFrame): TurbineTripStatus {
  const commandedActive = frame.turbine_trip || frame.scrammed

  if (!frame.running && frame.turbine_trip_active !== commandedActive) {
    return frame.turbine_trip_active
      ? {
          kind: 'clear-pending',
          label: 'TRIP CLEARING',
          cause: 'pending — applies when the simulation runs',
          active: true,
          tone: 'warn',
        }
      : {
          kind: 'trip-pending',
          label: 'TRIP PENDING',
          cause: 'pending — applies when the simulation runs',
          active: false,
          tone: 'warn',
        }
  }

  if (frame.turbine_trip_active) {
    if (frame.turbine_trip) {
      return {
        kind: 'operator-trip',
        label: 'TRIPPED',
        cause: 'operator trip',
        active: true,
        tone: 'danger',
      }
    }
    if (frame.scrammed) {
      return {
        kind: 'scram-trip',
        label: 'TRIPPED',
        cause: 'SCRAM (P-4)',
        active: true,
        tone: 'danger',
      }
    }
    return {
      kind: 'trip-clearing',
      label: 'TRIP CLEARING',
      cause: 'trip clearing',
      active: true,
      tone: 'warn',
    }
  }

  if (commandedActive) {
    return {
      kind: 'trip-pending',
      label: 'TRIP PENDING',
      cause: 'command accepted; valves update on the next step',
      active: false,
      tone: 'warn',
    }
  }

  return {
    kind: 'not-tripped',
    label: 'NOT TRIPPED',
    cause: 'turbine admission is available',
    active: false,
    tone: 'normal',
  }
}

/**
 * Convert the current feedwater demand to the manual-command fraction.
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

function feedwaterSelectedDemand(frame: FeedwaterStatusFrame): number | null {
  return frame.feedwater_manual === null ? null : clampFraction(frame.feedwater_manual) * frame.m_fw_max
}

function feedwaterMode(frame: FeedwaterStatusFrame): 'auto' | 'manual' {
  return frame.feedwater_manual === null ? 'auto' : 'manual'
}

function demandChanged(a: number | null, b: number | null): boolean {
  if (a === null || b === null) return a !== b
  return Math.abs(a - b) > FEEDWATER_DEMAND_TOL_KG_S
}

/**
 * Derive the feedwater AUTO/MANUAL status tag.
 *
 * Parameters
 * ----------
 * frame:
 *   Telemetry fields carrying selected feedwater mode, demand and saturation.
 *
 * Returns
 * -------
 * FeedwaterModeStatus
 *   The label, explanation and severity for the feedwater mode tag.
 */
export function deriveFeedwaterModeStatus(
  frame: FeedwaterStatusFrame,
  effectiveFrame: FeedwaterStatusFrame = frame,
): FeedwaterModeStatus {
  const selectedMode = feedwaterMode(frame)
  const effectiveMode = feedwaterMode(effectiveFrame)
  const selectedDemandKgS = feedwaterSelectedDemand(frame)
  const effectiveCommandDemandKgS = feedwaterSelectedDemand(effectiveFrame)
  const effectiveDemandKgS = effectiveFrame.m_fw_demand
  const demandMismatch =
    selectedMode === 'manual' &&
    Math.abs((selectedDemandKgS ?? 0) - effectiveDemandKgS) > FEEDWATER_DEMAND_TOL_KG_S
  const commandMismatch =
    selectedMode !== effectiveMode || demandChanged(selectedDemandKgS, effectiveCommandDemandKgS)

  if (!frame.running && (commandMismatch || demandMismatch)) {
    return {
      kind: 'pending',
      label: 'PENDING',
      detail: 'pending — applies when the simulation runs',
      tone: 'warn',
      selectedMode,
      effectiveMode,
      selectedDemandKgS,
      effectiveDemandKgS,
    }
  }

  if (frame.feedwater_manual !== null) {
    return {
      kind: 'manual',
      label: 'MANUAL',
      detail: 'Operator manual feedwater demand is active.',
      tone: 'warn',
      selectedMode,
      effectiveMode,
      selectedDemandKgS,
      effectiveDemandKgS,
    }
  }

  if (!frame.fw_saturated) {
    return {
      kind: 'auto',
      label: 'AUTO',
      detail: 'Automatic SG level control is active.',
      tone: 'normal',
      selectedMode,
      effectiveMode,
      selectedDemandKgS,
      effectiveDemandKgS,
    }
  }

  if (frame.m_fw_demand <= FLOW_EPS) {
    return {
      kind: 'auto-saturated-zero',
      label: 'AUTO · saturated at zero',
      detail: 'Automatic level control wants less than zero feedwater, so demand is clipped at 0 kg/s.',
      tone: 'warn',
      selectedMode,
      effectiveMode,
      selectedDemandKgS,
      effectiveDemandKgS,
    }
  }

  if (frame.m_fw_max > 0 && frame.m_fw_demand >= frame.m_fw_max - FLOW_EPS) {
    return {
      kind: 'auto-saturated-maximum',
      label: 'AUTO · saturated at maximum',
      detail: 'Automatic level control wants more feedwater than the actuator can provide.',
      tone: 'warn',
      selectedMode,
      effectiveMode,
      selectedDemandKgS,
      effectiveDemandKgS,
    }
  }

  return {
    kind: 'auto-saturated',
    label: 'AUTO · saturated',
    detail: 'Automatic level control is clipped at a feedwater-flow limit.',
    tone: 'warn',
    selectedMode,
    effectiveMode,
    selectedDemandKgS,
    effectiveDemandKgS,
  }
}
