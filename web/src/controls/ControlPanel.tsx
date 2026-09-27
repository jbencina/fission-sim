/**
 * ControlPanel — operator controls for the fission-sim web UI.
 *
 * Four groups:
 *   1. Control rods — a ring gauge showing the bank's position (dot) and the
 *                     command (amber tick), with a slider beneath it for the
 *                     command in % of travel withdrawn (sent to the backend
 *                     as a fraction 0–1). The slider's track carries an amber
 *                     marker at the actual position, so the lag between
 *                     command and position is visible at a glance.
 *   2. Safety       — SCRAM with a confirmation dialog; Reset Scram while
 *                     scrammed.
 *   3. Run          — Pause/Resume and Reset Simulation (with confirmation).
 *   4. Speed        — segmented 1× / 2× / 5× / 10× real-time multiplier.
 *
 * All controls dispatch through the telemetry store's `sendCommand`. While
 * the WebSocket is not connected every control is disabled.
 *
 * Each control explains itself on hover and on keyboard focus; the
 * explanation is linked to the control with aria-describedby so screen
 * readers read it as the control's description.
 *
 * @module ControlPanel
 */

import { type FC, useCallback, useEffect, useRef, useState } from 'react'
import { useTelemetryStore } from '../state/telemetryStore'
import { SPEEDS, type Speed } from '../types/telemetry'
import { HelpTip } from '../ui/InfoTip'
import { formatNumber } from '../ui/format'
import { PauseIcon, PlayIcon, ResetIcon } from '../ui/icons'
import ConfirmDialog from './ConfirmDialog'
import RodGauge from './RodGauge'

// ---------------------------------------------------------------------------
// Small building blocks
// ---------------------------------------------------------------------------

const Readout: FC<{ label: string; value: string }> = ({ label, value }) => (
  <div>
    <div className="text-[11.5px] tracking-[0.04em] text-ink-2">{label}</div>
    <div className="font-mono text-[22px] font-light leading-tight tabular-nums text-ink">
      {value}
      <span className="ml-1 font-sans text-[11px] text-ink-2">%</span>
    </div>
  </div>
)

// ---------------------------------------------------------------------------
// ControlPanel
// ---------------------------------------------------------------------------

const ControlPanel: FC = () => {
  const status = useTelemetryStore((s) => s.status)
  const latest = useTelemetryStore((s) => s.latest)
  const sendCommand = useTelemetryStore((s) => s.sendCommand)
  const clearHistory = useTelemetryStore((s) => s.clearHistory)

  const connected = status === 'connected'
  const scrammed = latest?.scrammed === true
  const running = latest?.running === true
  // Halted at a model limit: the backend refuses resume until a reset.
  const halted = latest?.model_limit != null
  const speed = latest?.speed ?? 1
  // null until the first frame arrives; the readout then shows "—".
  const rodPosition = latest?.rod_position ?? null

  // ── Slider value ───────────────────────────────────────────────────────────
  //
  // The slider is controlled by local state so dragging it doesn't spam the
  // WebSocket. The value is sent on the input's native `change` event, which
  // fires once when a drag is released (wherever the pointer is) and once
  // per arrow-key step. While the user is not dragging, the slider follows
  // the backend's rod_command.
  const [localRodCmd, setLocalRodCmd] = useState<number>(latest?.rod_command ?? 0.5)
  const draggingRef = useRef(false)
  const sliderRef = useRef<HTMLInputElement>(null)
  const backendRodCmdRef = useRef<number | undefined>(latest?.rod_command)
  backendRodCmdRef.current = latest?.rod_command

  useEffect(() => {
    if (!draggingRef.current && latest?.rod_command !== undefined) {
      setLocalRodCmd(latest.rod_command)
    }
  }, [latest?.rod_command])

  useEffect(() => {
    const el = sliderRef.current
    if (!el) return
    const commit = () => {
      draggingRef.current = false
      sendCommand({ type: 'set_rod_command', value: parseFloat(el.value) })
    }
    // A drag released where it started fires no `change`. Check once any
    // `change` has had its turn; if none came, stop dragging and show the
    // backend's command again, or the slider would stop following it.
    let pending: number | undefined
    const release = () => {
      window.clearTimeout(pending)
      pending = window.setTimeout(() => {
        if (!draggingRef.current) return
        draggingRef.current = false
        const backend = backendRodCmdRef.current
        if (backend !== undefined) setLocalRodCmd(backend)
      }, 0)
    }
    el.addEventListener('change', commit)
    el.addEventListener('pointerup', release)
    el.addEventListener('pointercancel', release)
    el.addEventListener('blur', release)
    return () => {
      window.clearTimeout(pending)
      el.removeEventListener('change', commit)
      el.removeEventListener('pointerup', release)
      el.removeEventListener('pointercancel', release)
      el.removeEventListener('blur', release)
    }
  }, [sendCommand])

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

  const positionPct = Math.min(1, Math.max(0, rodPosition ?? 0)) * 100

  return (
    <>
      <ConfirmDialog
        open={scramDialogOpen}
        title="Initiate SCRAM?"
        message="SCRAM immediately drops the control bank and the shutdown bank; both are fully inserted within about 2 s (about −7,000 pcm) and fission power falls within seconds. Reset Scram returns only the control bank to your command. The shutdown bank stays in, so getting back to power takes Reset Simulation."
        confirmLabel="SCRAM"
        danger
        onConfirm={handleScramConfirm}
        onCancel={() => setScramDialogOpen(false)}
      />
      <ConfirmDialog
        open={resetDialogOpen}
        title="Reset simulation?"
        message="This restarts the simulator at t = 0 from the full-power design state: both rod banks at their design positions, rod command 50 %, design temperatures and pressure. Speed and pressure setpoint are kept. All current chart data will be lost."
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
            <div className="flex items-start gap-4">
              <RodGauge position={rodPosition} command={localRodCmd} />
              <div className="flex min-h-[124px] min-w-0 flex-1 flex-col justify-between">
                <Readout label="Command" value={formatNumber(localRodCmd * 100, 0)} />
                <Readout
                  label="Position"
                  value={formatNumber(rodPosition === null ? null : rodPosition * 100, 0)}
                />
                <p className="text-[11.5px] leading-snug text-ink-2">
                  {scrammed
                    ? 'Shutdown bank is in. Reset the SCRAM to give the control bank back to your command.'
                    : 'The bank moves at 1 % per second toward the command.'}
                </p>
              </div>
            </div>

            <HelpTip tip="Control-bank command, % of travel withdrawn (0 % fully inserted, 100 % fully withdrawn; design 50 %). The bank moves toward it at 1 % per second: 100 s for a full stroke, 50 s from design to either end. Each 1 % of travel is worth 12 pcm, so the bank can add or remove at most 600 pcm from design.">
              {(tipId) => (
                <div className="relative mt-3">
                  {/* Visible 1 px track, inset by the knob radius so the marker and knob line up. The white marker is the bank's actual position, as on the gauge. */}
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
                    ref={sliderRef}
                    aria-describedby={tipId}
                    type="range"
                    className="rod-range relative"
                    min={0}
                    max={1}
                    step={0.01}
                    value={localRodCmd}
                    disabled={!connected}
                    aria-label="Rod command"
                    aria-valuetext={`${(localRodCmd * 100).toFixed(0)} % withdrawn`}
                    onChange={(e) => {
                      draggingRef.current = true
                      setLocalRodCmd(parseFloat(e.target.value))
                    }}
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
          {/* While scrammed, Reset Scram takes half of the row instead of adding one. */}
          <section aria-label="Safety" className={scrammed ? 'grid grid-cols-2 gap-2' : ''}>
            <HelpTip tip="Emergency shutdown. Immediately commands the control and shutdown banks to drop; both are fully inserted within about 2 s, adding about −7,000 pcm. Fission power falls to a few percent within seconds, then fades as delayed-neutron precursors decay.">
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
                tip="Clears the SCRAM latch and returns the control bank to your rod command. The shutdown bank stays fully inserted, so the reactor stays subcritical: total reactivity stays below about −4,300 pcm even with the control bank fully withdrawn and the plant cooled down. To return to power, use Reset Simulation."
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
            <HelpTip tip="Pauses simulator time advancement. Values are frozen; the display still updates when you change a control (SCRAM, speed, rods).">
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
              tip="Restarts from the full-power design state (shutdown bank withdrawn, control bank at 50 %, design temperatures and pressure). The only way back to power after a SCRAM; the procedure-driven startup of a real plant is not modeled."
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
