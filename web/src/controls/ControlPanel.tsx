/**
 * ControlPanel — primary operator controls for the fission-sim web UI.
 *
 * Groups:
 *   1. Control bank — AUTO/MANUAL rod control, a ring gauge, and the manual
 *                     rod slider. In AUTO, the Tavg controller owns rod
 *                     demand and the slider is disabled.
 *   2. Safety       — SCRAM with a confirmation dialog; Reset Scram while
 *                     scrammed.
 *   3. Run          — Pause/Resume and Reset Simulation (with confirmation).
 *   4. Speed        — segmented 1× / 2× / 5× / 10× real-time multiplier.
 *
 * All controls dispatch through the telemetry store's `sendCommand`. While
 * the WebSocket is not connected every control is disabled by the fieldset.
 *
 * @module ControlPanel
 */

import { type FC, useCallback, useState } from 'react'
import { useTelemetryStore } from '../state/telemetryStore'
import { SPEEDS, type Speed } from '../types/telemetry'
import { HelpTip } from '../ui/InfoTip'
import { formatNumber } from '../ui/format'
import { PauseIcon, PlayIcon, ResetIcon } from '../ui/icons'
import ConfirmDialog from './ConfirmDialog'
import { clampFraction, deriveRodModeStatus, type StatusTone } from '../state/plantStatus'
import RodGauge from './RodGauge'
import { useCommittedRange } from './useCommittedRange'

// ---------------------------------------------------------------------------
// Small building blocks
// ---------------------------------------------------------------------------

function toneClass(tone: StatusTone): string {
  if (tone === 'danger') return 'text-danger'
  if (tone === 'warn') return 'text-warn'
  return 'text-ink'
}

const Readout: FC<{ label: string; value: string; unit?: string }> = ({ label, value, unit = '%' }) => (
  <div>
    <div className="text-[11.5px] tracking-[0.04em] text-ink-2">{label}</div>
    <div className="font-mono text-[22px] font-light leading-tight tabular-nums text-ink">
      {value}
      <span className="ml-1 font-sans text-[11px] text-ink-2">{unit}</span>
    </div>
  </div>
)

const P4_TURBINE_TRIP_COPY =
  "SCRAM also trips the turbine through the simulator's P-4 turbine-trip consequence, so steam transfers to the dump path while fission power falls."

// ---------------------------------------------------------------------------
// ControlPanel
// ---------------------------------------------------------------------------

/** Primary-side operator controls: rods, SCRAM, run/reset and speed. */
const ControlPanel: FC = () => {
  const status = useTelemetryStore((s) => s.status)
  const latest = useTelemetryStore((s) => s.latest)
  const sendCommand = useTelemetryStore((s) => s.sendCommand)
  const clearHistory = useTelemetryStore((s) => s.clearHistory)

  const connected = status === 'connected'
  const scrammed = latest?.scrammed === true
  const running = latest?.running === true
  const halted = latest?.model_limit != null
  const speed = latest?.speed ?? 1
  const rodAuto = latest?.rod_auto === true
  const rodPosition = latest?.rod_position ?? null
  const rodDemand = latest?.rod_demand ?? latest?.rod_command ?? 0.5
  const backendRodCommand = latest?.rod_command ?? 0.5
  const rodSliderBackendValue = rodAuto ? rodDemand : backendRodCommand
  const rodModeStatus = latest
    ? deriveRodModeStatus(latest)
    : {
        kind: 'manual' as const,
        label: 'MANUAL',
        detail: 'Waiting for first telemetry frame.',
        tone: 'normal' as const,
      }

  const handleRodCommit = useCallback(
    (value: number) => {
      if (!rodAuto) sendCommand({ type: 'set_rod_command', value: clampFraction(value) })
    },
    [rodAuto, sendCommand],
  )
  const rodSlider = useCommittedRange(rodSliderBackendValue, handleRodCommit)

  // ── Dialogs ────────────────────────────────────────────────────────────────
  const [scramDialogOpen, setScramDialogOpen] = useState(false)
  const [resetDialogOpen, setResetDialogOpen] = useState(false)

  const handleScramConfirm = useCallback(() => {
    setScramDialogOpen(false)
    sendCommand({ type: 'scram' })
  }, [sendCommand])

  const handleResetScram = useCallback(() => {
    sendCommand({ type: 'reset_scram' })
  }, [sendCommand])

  const handlePauseResume = useCallback(() => {
    sendCommand({ type: running ? 'pause' : 'resume' })
  }, [sendCommand, running])

  const handleResetConfirm = useCallback(() => {
    setResetDialogOpen(false)
    clearHistory()
    sendCommand({ type: 'reset' })
  }, [clearHistory, sendCommand])

  const handleSetSpeed = useCallback(
    (value: Speed) => {
      sendCommand({ type: 'set_speed', value })
    },
    [sendCommand],
  )

  const handleSetRodAuto = useCallback(
    (value: boolean) => {
      sendCommand({ type: 'set_rod_auto', value })
    },
    [sendCommand],
  )

  const positionPct = Math.min(1, Math.max(0, rodPosition ?? 0)) * 100
  const displayedRodTarget = rodAuto ? rodDemand : rodSlider.value
  const rodTargetLabel = rodAuto ? 'Demand (auto)' : 'Command'

  return (
    <>
      <ConfirmDialog
        open={scramDialogOpen}
        title="Initiate SCRAM?"
        message={`SCRAM drops the control bank and shutdown bank; both are fully inserted within about 2 s (about −7,000 pcm). ${P4_TURBINE_TRIP_COPY}`}
        confirmLabel="SCRAM"
        danger
        onConfirm={handleScramConfirm}
        onCancel={() => setScramDialogOpen(false)}
      />
      <ConfirmDialog
        open={resetDialogOpen}
        title="Reset simulation?"
        message="This rebuilds the plant at the full-power design state and clears SCRAM, the turbine trip latch, feedwater manual and any model-limit halt. It keeps speed, pressure setpoint, turbine admission demand, rod mode and SG level setpoint; if admission demand is low, the reset starts with actual admission at 100 % and then ramps down."
        confirmLabel="Reset"
        danger
        onConfirm={handleResetConfirm}
        onCancel={() => setResetDialogOpen(false)}
      />

      <section aria-label="Operator controls" className="panel p-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="eyebrow">Control bank</h2>
          {!connected && <span className="text-[11.5px] text-ink-3">Offline, controls inactive</span>}
        </div>

        <fieldset disabled={!connected} className={connected ? '' : 'opacity-60'}>
          {/* ── 1. Control rods ─────────────────────────────────────────── */}
          <section aria-label="Rod control" className="mt-3">
            <HelpTip
              tip="AUTO lets the Tavg controller move the control bank to hold average coolant temperature near its admission-based reference. MANUAL gives you the rod command; switching to MANUAL is bumpless because the backend first syncs the manual command to the actual bank position."
            >
              {(tipId) => (
                <div className="flex items-center justify-between gap-3">
                  <div aria-describedby={tipId} className="seg" role="group" aria-label="Rod control mode">
                    <button
                      type="button"
                      disabled={!connected}
                      aria-pressed={rodAuto}
                      onClick={() => handleSetRodAuto(true)}
                      className={[
                        'h-8 px-3 text-[12px] tracking-[0.08em] transition-colors',
                        rodAuto ? 'seg-on' : 'text-ink-2 hover:text-ink',
                      ].join(' ')}
                    >
                      AUTO
                    </button>
                    <button
                      type="button"
                      disabled={!connected}
                      aria-pressed={!rodAuto}
                      onClick={() => handleSetRodAuto(false)}
                      className={[
                        'h-8 px-3 text-[12px] tracking-[0.08em] transition-colors',
                        !rodAuto ? 'seg-on' : 'text-ink-2 hover:text-ink',
                      ].join(' ')}
                    >
                      MANUAL
                    </button>
                  </div>
                  <div className="text-right">
                    <div className={`font-mono text-[12px] tabular-nums ${toneClass(rodModeStatus.tone)}`}>
                      {rodModeStatus.label}
                    </div>
                    <div className="text-[10.5px] text-ink-3">{rodModeStatus.detail}</div>
                  </div>
                </div>
              )}
            </HelpTip>

            <div className="mt-3 flex items-start gap-4">
              <RodGauge position={rodPosition} command={displayedRodTarget} />
              <div className="flex min-h-[124px] min-w-0 flex-1 flex-col justify-between">
                <Readout label={rodTargetLabel} value={formatNumber(displayedRodTarget * 100, 0)} />
                <Readout
                  label="Position"
                  value={formatNumber(rodPosition === null ? null : rodPosition * 100, 0)}
                />
                <p className="text-[11.5px] leading-snug text-ink-2">
                  {rodModeStatus.detail}
                </p>
              </div>
            </div>

            <HelpTip
              tip={
                rodAuto
                  ? 'Disabled in AUTO because the Tavg controller, not the operator, is commanding rod demand. Select MANUAL for a bumpless transfer: the backend copies the actual bank position into the manual command before you move it.'
                  : 'Control-bank command, % of travel withdrawn (0 % fully inserted, 100 % fully withdrawn; design 50 %). The bank moves toward it at 1 % per second. Each 1 % of travel is worth 12 pcm, so the bank can add or remove at most 600 pcm from design.'
              }
            >
              {(tipId) => (
                <div className="relative mt-3">
                  <div
                    aria-hidden="true"
                    className="pointer-events-none absolute inset-x-[7px] top-1/2 h-px -translate-y-1/2 bg-line-strong"
                  >
                    <div className="absolute left-1/2 top-1/2 h-2.5 w-px -translate-y-1/2 bg-ink-3" />
                    <div
                      className="absolute top-1/2 h-3 w-0.5 -translate-y-1/2 bg-ink transition-[left] duration-200 ease-linear"
                      style={{ left: `${positionPct}%` }}
                    />
                  </div>
                  <input
                    ref={rodSlider.ref}
                    aria-describedby={tipId}
                    type="range"
                    className="rod-range relative"
                    min={0}
                    max={1}
                    step={0.01}
                    value={rodSlider.value}
                    disabled={!connected || rodAuto}
                    aria-label={rodAuto ? 'Automatic rod demand' : 'Rod command'}
                    aria-valuetext={`${(displayedRodTarget * 100).toFixed(0)} % withdrawn`}
                    onChange={rodSlider.onChange}
                  />
                </div>
              )}
            </HelpTip>
            <div aria-hidden="true" className="mt-0.5 flex justify-between px-0.5 text-[10.5px] text-ink-3">
              <span>Inserted</span>
              <span>Design 50</span>
              <span>Withdrawn</span>
            </div>
          </section>

          <div className="-mx-4 my-4 h-px bg-line" />

          {/* ── 2. Safety ───────────────────────────────────────────────── */}
          <section aria-label="Safety" className={scrammed ? 'grid grid-cols-2 gap-2' : ''}>
            <HelpTip
              tip={`Emergency shutdown. Drops the control and shutdown banks. Fission power falls within seconds, then fades as delayed-neutron precursors decay. ${P4_TURBINE_TRIP_COPY}`}
            >
              {(tipId) => (
                <button
                  aria-describedby={tipId}
                  type="button"
                  disabled={!connected || scrammed}
                  onClick={() => setScramDialogOpen(true)}
                  title={scrammed ? 'Reactor is already scrammed' : undefined}
                  className={`btn btn-danger !h-11 w-full disabled:!opacity-100 ${scrammed ? '!indent-[0.1em] !tracking-[0.1em] text-[12px]' : 'text-[13px]'}`}
                >
                  {scrammed ? 'SCRAM LATCHED' : 'SCRAM'}
                </button>
              )}
            </HelpTip>

            {scrammed && (
              <HelpTip
                align="end"
                tip="Clears the SCRAM latch, returns the control bank to the selected rod-control mode, and sets turbine admission demand to 0 %. A P-4 turbine trip remains latched until Reset Turbine Trip after actual admission is closed. The shutdown bank stays inserted, so the reactor stays subcritical until Reset Simulation."
              >
                {(tipId) => (
                  <button
                    aria-describedby={tipId}
                    type="button"
                    disabled={!connected}
                    onClick={handleResetScram}
                    className="btn !h-11 w-full !border-ink"
                  >
                    Reset Scram
                  </button>
                )}
              </HelpTip>
            )}
          </section>

          {/* ── 3. Run ──────────────────────────────────────────────────── */}
          <section aria-label="Run control" className="mt-2 grid grid-cols-2 gap-2">
            <HelpTip tip="Pauses simulator time advancement. Values are frozen; command fields can update while paused and show as pending until the simulation runs.">
              {(tipId) => (
                <button
                  aria-describedby={tipId}
                  type="button"
                  disabled={!connected || halted}
                  onClick={handlePauseResume}
                  className={`btn w-full ${running ? '' : '!border-ink'}`}
                >
                  {running ? <PauseIcon size={13} /> : <PlayIcon size={12} />}
                  {running ? 'Pause' : 'Resume'}
                </button>
              )}
            </HelpTip>
            <HelpTip
              align="end"
              tip="Rebuilds the plant at full-power design conditions. Keeps speed, pressure setpoint, turbine admission demand, rod AUTO/MANUAL mode and SG level setpoint; clears SCRAM, turbine trip and feedwater manual. If demand is low, actual turbine admission starts at 100 % then ramps down."
            >
              {(tipId) => (
                <button
                  aria-describedby={tipId}
                  type="button"
                  disabled={!connected}
                  onClick={() => setResetDialogOpen(true)}
                  className="btn w-full"
                >
                  <ResetIcon size={13} />
                  Reset Simulation
                </button>
              )}
            </HelpTip>
          </section>

          {/* ── 4. Speed ────────────────────────────────────────────────── */}
          <section aria-label="Speed control" className="mt-3 flex items-center justify-between gap-3">
            <span className="eyebrow">Speed</span>
            <HelpTip align="end" tip="Real-time multiplier. Useful for observing long transients quickly.">
              {(tipId) => (
                <div role="group" aria-label="Simulation speed multiplier" className="seg">
                  {SPEEDS.map((opt) => {
                    const active = speed === opt
                    return (
                      <button
                        key={opt}
                        type="button"
                        disabled={!connected}
                        onClick={() => handleSetSpeed(opt)}
                        aria-pressed={active}
                        aria-describedby={tipId}
                        className={[
                          'h-9 w-11 font-mono text-[12px] tabular-nums transition-colors',
                          active ? 'seg-on' : 'text-ink-2 hover:text-ink',
                          'disabled:cursor-not-allowed',
                        ].join(' ')}
                      >
                        {opt}×
                      </button>
                    )
                  })}
                </div>
              )}
            </HelpTip>
          </section>
        </fieldset>
      </section>
    </>
  )
}

export default ControlPanel
