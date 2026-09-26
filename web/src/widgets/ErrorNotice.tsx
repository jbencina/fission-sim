/**
 * ErrorNotice — a small dismissible message for backend and connection errors.
 *
 * Shows `lastError` from the telemetry store: either an explanation sent by
 * the simulator (for example, why a command was refused) or a note that the
 * WebSocket connection dropped. The text is rendered as-is, so any
 * plain-language explanation the backend sends appears without frontend
 * changes; long or multi-line messages wrap inside the notice.
 *
 * Renders nothing when there is no message.
 *
 * Also exports `ModelLimitNotice`, the persistent notice shown while the
 * simulation is halted at the edge of what the model can describe.
 *
 * @module ErrorNotice
 */

import type { FC } from 'react'
import { useTelemetryStore } from '../state/telemetryStore'
import { SIM_ERROR_PREFIX, type AppErrorSource } from '../types/telemetry'

/**
 * ModelLimitNotice — why the simulation stopped at the edge of the model.
 *
 * Reads `model_limit` from the latest telemetry frame. The backend sets it
 * when a step would leave the model's supported domain (for example, hot-leg
 * water reaching its boiling point or the pressurizer filling solid with
 * water) and holds the last valid state until a reset. The notice has no
 * Dismiss button on purpose: it describes the current state of the
 * simulation rather than a one-off event, so it stays while the halt lasts
 * and disappears on its own once a reset clears `model_limit`.
 *
 * Renders nothing during normal operation.
 */
export const ModelLimitNotice: FC = () => {
  const modelLimit = useTelemetryStore((s) => s.latest?.model_limit ?? null)

  if (modelLimit === null) return null

  // An unexpected step failure (a simulator fault, not physics) arrives with
  // the backend's SIM_ERROR_PREFIX; label it as such rather than as a limit.
  const isFault = modelLimit.startsWith(SIM_ERROR_PREFIX)
  const heading = isFault ? 'Simulation error, simulation halted' : 'Model limit reached, simulation halted'
  const text = isFault ? modelLimit.slice(SIM_ERROR_PREFIX.length) : modelLimit

  return (
    <div
      role="alert"
      data-testid="model-limit-notice"
      className="rounded-lg border border-red-500/50 bg-slate-900 px-3 py-2 text-sm text-slate-200"
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-red-300">{heading}</p>
      <p className="whitespace-pre-line break-words leading-relaxed first-letter:uppercase">{text}</p>
    </div>
  )
}

/** Short heading for each message source. */
const HEADING: Record<AppErrorSource, string> = {
  server: 'Simulator message',
  connection: 'Connection',
}

const ErrorNotice: FC = () => {
  const lastError = useTelemetryStore((s) => s.lastError)
  const clearError = useTelemetryStore((s) => s.clearError)

  if (lastError === null) return null

  return (
    /*
     * role="alert" asks screen readers to announce the message as soon as it
     * appears, since it usually explains why the last action had no effect.
     */
    <div
      role="alert"
      data-testid="error-notice"
      className="flex items-start gap-3 rounded-lg border border-amber-500/40 bg-slate-900 px-3 py-2 text-sm text-slate-200"
    >
      <div className="min-w-0 flex-1">
        <p className="text-xs font-semibold uppercase tracking-wide text-amber-300">
          {HEADING[lastError.source]}
        </p>
        {/* whitespace-pre-line keeps line breaks the backend puts in its text. */}
        <p className="whitespace-pre-line break-words leading-relaxed">{lastError.message}</p>
      </div>
      <button
        type="button"
        onClick={clearError}
        className="shrink-0 rounded px-2 py-1 text-xs font-medium text-slate-300 hover:bg-slate-800 hover:text-slate-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
      >
        Dismiss
      </button>
    </div>
  )
}

export default ErrorNotice
