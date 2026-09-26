/**
 * ControlPanel — operator controls for the fission-sim web UI.
 *
 * Provides four control sections:
 *   1. Rod control  — range slider for the control-bank command, shown in % of
 *                     travel withdrawn (sent to the backend as a fraction 0–1).
 *   2. Safety       — SCRAM button with confirmation modal; Reset Scram when active.
 *   3. Run          — Pause/Resume toggle and Reset Simulation (with confirmation).
 *   4. Speed        — Segmented 1× / 2× / 5× / 10× real-time multiplier.
 *
 * All controls dispatch via `useTelemetryStore.getState().sendCommand(cmd)`.
 * When the WebSocket status is not 'connected', every control is visually
 * disabled and a notice is shown at the top of the panel.
 *
 * Each control has a CSS tooltip (no tooltip library dependency) that appears
 * on hover and on keyboard focus, and is linked to the control with
 * aria-describedby so screen readers read it as the control's description.
 *
 * @module ControlPanel
 */

import { type FC, useState, useCallback, useRef, useEffect, useId } from 'react'
import { useTelemetryStore } from '../state/telemetryStore'
import { SPEEDS, type Speed } from '../types/telemetry'
import ConfirmDialog from './ConfirmDialog'

// ---------------------------------------------------------------------------
// Inline slider styles
// ---------------------------------------------------------------------------

/*
 * Tailwind does not ship utilities for styling the <input type="range"> thumb
 * and track cross-browser, so we inject a small <style> block once.
 *
 * Track:       slate-700 background
 * Fill-before: amber-400 (achieved via accent-color on Webkit / custom on FF)
 * Thumb:       sky-400 circle
 */
const SLIDER_STYLES = `
  .rod-slider {
    -webkit-appearance: none;
    appearance: none;
    width: 100%;
    height: 6px;
    border-radius: 3px;
    background: #334155; /* slate-700 */
    outline: none;
    cursor: pointer;
    accent-color: #f59e0b; /* amber-400 — used by Chromium for the filled portion */
  }
  .rod-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: #38bdf8; /* sky-400 */
    cursor: pointer;
    transition: box-shadow 0.15s;
  }
  .rod-slider::-webkit-slider-thumb:hover {
    box-shadow: 0 0 0 4px rgba(56,189,248,0.25);
  }
  .rod-slider::-moz-range-thumb {
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: #38bdf8; /* sky-400 */
    cursor: pointer;
    border: none;
    transition: box-shadow 0.15s;
  }
  .rod-slider::-moz-range-thumb:hover {
    box-shadow: 0 0 0 4px rgba(56,189,248,0.25);
  }
  .rod-slider:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
`

// ---------------------------------------------------------------------------
// Small tooltip wrapper
// ---------------------------------------------------------------------------

/**
 * CSS tooltip container.
 *
 * Children are wrapped in a `group` div; the tooltip is a hidden sibling that
 * appears on `group-hover`, and also when a control inside has keyboard focus
 * (`group-has-[:focus-visible]`) so keyboard users get the same explanation.
 *
 * `children` is a function that receives the tooltip's id. Pass it as
 * `aria-describedby` on each focusable control the tip explains, so assistive
 * technology announces the tip when that control is focused.
 */
const Tip: FC<{
  tip: string
  children: (tipId: string) => React.ReactNode
  className?: string
}> = ({ tip, children, className = '' }) => {
  const tipId = useId()
  return (
    <div className={`group relative ${className}`}>
      {children(tipId)}
      <div
        id={tipId}
        className={[
          'absolute bottom-[calc(100%+6px)] left-0',
          'z-50 w-64',
          'bg-slate-950 border border-slate-700 rounded-lg p-3',
          'text-xs text-slate-200 shadow-lg leading-relaxed',
          'opacity-0 group-hover:opacity-100 group-has-[:focus-visible]:opacity-100',
          'transition-opacity duration-150',
          'pointer-events-none',
        ].join(' ')}
        role="tooltip"
      >
        {tip}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Section heading helper
// ---------------------------------------------------------------------------

const SectionHeading: FC<{ children: React.ReactNode }> = ({ children }) => (
  <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-widest mb-3">
    {children}
  </h3>
)

// ---------------------------------------------------------------------------
// ControlPanel
// ---------------------------------------------------------------------------

/**
 * ControlPanel
 *
 * Operator control panel. Reads the latest telemetry frame from the global
 * Zustand store and sends commands back via `sendCommand`.
 *
 * Sections:
 *   Rod control — slider for rod_command; progress bar showing rod_position lag.
 *   Safety      — SCRAM and Reset Scram buttons.
 *   Run         — Pause/Resume and Reset Simulation.
 *   Speed       — segmented speed selector.
 */
const ControlPanel: FC = () => {
  // ── Store subscriptions ────────────────────────────────────────────────────
  const status = useTelemetryStore((s) => s.status)
  const latest = useTelemetryStore((s) => s.latest)
  const sendCommand = useTelemetryStore((s) => s.sendCommand)
  const clearHistory = useTelemetryStore((s) => s.clearHistory)

  // Convenience booleans derived from latest frame.
  const connected = status === 'connected'
  const scrammed = latest?.scrammed === true
  const running = latest?.running === true
  // Halted at a model limit: the backend refuses resume until a reset.
  const halted = latest?.model_limit != null
  const speed = latest?.speed ?? 1
  // null until the first frame arrives; the readout then shows "—".
  const rodPosition = latest?.rod_position ?? null

  // ── Local state: slider value ──────────────────────────────────────────────
  //
  // The slider is controlled by local state so dragging it doesn't spam the WS.
  // We commit the value to the backend on mouseup/touchend/keyup only.
  //
  // We track a "committed" value separately; when the backend echoes a new
  // rod_command we only sync the slider if the user is not actively dragging.
  const [localRodCmd, setLocalRodCmd] = useState<number>(latest?.rod_command ?? 0.5)
  const draggingRef = useRef(false)

  // Keep slider in sync with backend value when not dragging.
  useEffect(() => {
    if (!draggingRef.current && latest?.rod_command !== undefined) {
      setLocalRodCmd(latest.rod_command)
    }
  }, [latest?.rod_command])

  // ── Commit rod command to backend ─────────────────────────────────────────
  const commitRodCmd = useCallback(
    (value: number) => {
      draggingRef.current = false
      sendCommand({ type: 'set_rod_command', value })
    },
    [sendCommand],
  )

  // ── Modal state: which dialog is open ─────────────────────────────────────
  const [scramDialogOpen, setScramDialogOpen] = useState(false)
  const [resetDialogOpen, setResetDialogOpen] = useState(false)

  // ── Handlers ──────────────────────────────────────────────────────────────
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

  // ── Disabled overlay class when disconnected ───────────────────────────────
  //
  // When not connected we want an overlay that signals "inactive" without
  // hiding the control shapes — opacity-50 and pointer-events-none achieves
  // this. Individual <button> elements also carry `disabled` for a11y.
  const disabledClass = connected ? '' : 'opacity-50 pointer-events-none'

  return (
    <>
      {/* Inject slider custom CSS once */}
      <style>{SLIDER_STYLES}</style>

      {/* Modals — rendered outside the disabled overlay */}
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

      {/* ── Panel card ──────────────────────────────────────────────────────── */}
      <section
        aria-label="Operator controls"
        className="bg-slate-900 border border-slate-800 rounded-2xl p-4 flex flex-col gap-5"
      >
        {/* ── Disconnected notice ─────────────────────────────────────────────── */}
        {!connected && (
          <div className="rounded-lg bg-slate-800 border border-slate-700 px-3 py-2 text-xs text-slate-400 text-center">
            Disconnected — controls inactive
          </div>
        )}

        {/* Wrap all controls in a div that goes dim + no-pointer when offline */}
        <div className={`flex flex-col gap-5 ${disabledClass}`}>

          {/* ════════════════════════════════════════════════════════════════════
              1. ROD CONTROL
          ═══════════════════════════════════════════════════════════════════ */}
          <section aria-label="Rod control">
            <SectionHeading>Rod control</SectionHeading>

            {/* Numeric readout: command vs actual control-bank position, in % withdrawn */}
            <div className="flex justify-between text-xs text-slate-400 font-mono mb-2">
              <span>
                Command:{' '}
                <span className="text-amber-300">{(localRodCmd * 100).toFixed(1)} %</span>
              </span>
              <span>
                Position:{' '}
                <span className="text-sky-300">
                  {rodPosition === null ? '—' : `${(rodPosition * 100).toFixed(1)} %`}
                </span>
              </span>
            </div>

            {/* Rod command slider with tooltip */}
            <Tip tip="Control-bank command, % of travel withdrawn (0 % fully inserted, 100 % fully withdrawn; design 50 %). The bank moves toward it at 1 % per second: 100 s for a full stroke, 50 s from design to either end. Each 1 % of travel is worth 12 pcm, so the bank can add or remove at most 600 pcm from design.">
              {(tipId) => (
                <input
                  aria-describedby={tipId}
                  type="range"
                  className="rod-slider"
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
                  onMouseUp={(e) =>
                    commitRodCmd(parseFloat((e.target as HTMLInputElement).value))
                  }
                  onTouchEnd={(e) =>
                    commitRodCmd(parseFloat((e.target as HTMLInputElement).value))
                  }
                  onKeyUp={(e) =>
                    commitRodCmd(parseFloat((e.target as HTMLInputElement).value))
                  }
                />
              )}
            </Tip>

            {/* Actual control-bank position bar — shows lag between command and position */}
            <div className="mt-2">
              <div className="text-[10px] text-slate-500 mb-1">Actual control-bank position</div>
              <div className="h-1.5 w-full rounded bg-slate-700 overflow-hidden">
                <div
                  className="h-full bg-sky-500 rounded transition-all duration-300"
                  style={{ width: `${Math.min(1, Math.max(0, rodPosition ?? 0)) * 100}%` }}
                />
              </div>
            </div>
          </section>

          {/* ════════════════════════════════════════════════════════════════════
              2. SAFETY
          ═══════════════════════════════════════════════════════════════════ */}
          <section aria-label="Safety">
            <SectionHeading>Safety</SectionHeading>

            {/* SCRAM button */}
            <Tip tip="Emergency shutdown. Immediately commands the control and shutdown banks to drop; both are fully inserted within about 2 s, adding about −7,000 pcm. Fission power falls to a few percent within seconds, then fades as delayed-neutron precursors decay.">
              {(tipId) => (
                <button
                  aria-describedby={tipId}
                  type="button"
                  disabled={!connected || scrammed}
                  onClick={() => setScramDialogOpen(true)}
                  className={[
                    'w-full py-4 px-6 rounded-lg text-lg font-bold uppercase tracking-wide',
                    'bg-red-600 text-white',
                    'hover:bg-red-500 hover:ring-2 hover:ring-red-400/50',
                    'focus:outline-none focus:ring-2 focus:ring-red-400',
                    'disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:ring-0',
                    'transition-all duration-150',
                  ].join(' ')}
                  title={scrammed ? 'Reactor is already scrammed' : undefined}
                >
                  SCRAM
                </button>
              )}
            </Tip>

            {/* Reset Scram — only shown when reactor is in scrammed state */}
            {scrammed && (
              <div className="mt-2">
                <Tip tip="Clears the SCRAM latch and returns the control bank to your rod command. The shutdown bank stays fully inserted, so the reactor stays subcritical: total reactivity stays below about −4,300 pcm even with the control bank fully withdrawn and the plant cooled down. To return to power, use Reset Simulation.">
                  {(tipId) => (
                    <button
                      aria-describedby={tipId}
                      type="button"
                      disabled={!connected}
                      onClick={handleResetScram}
                      className={[
                        'w-full py-2 px-4 rounded-lg text-sm font-medium',
                        'bg-slate-700 hover:bg-slate-600 text-slate-200',
                        'focus:outline-none focus:ring-2 focus:ring-slate-500',
                        'disabled:opacity-50 disabled:cursor-not-allowed',
                        'transition-colors duration-150',
                      ].join(' ')}
                    >
                      Reset Scram
                    </button>
                  )}
                </Tip>
              </div>
            )}
          </section>

          {/* ════════════════════════════════════════════════════════════════════
              3. RUN CONTROL
          ═══════════════════════════════════════════════════════════════════ */}
          <section aria-label="Run control">
            <SectionHeading>Run</SectionHeading>

            <div className="flex flex-col gap-2">
              {/* Pause / Resume toggle */}
              <Tip tip="Pauses simulator time advancement. Values are frozen; the display still updates when you change a control (SCRAM, speed, rods).">
                {(tipId) => (
                  <button
                    aria-describedby={tipId}
                    type="button"
                    disabled={!connected || halted}
                    onClick={handlePauseResume}
                    className={[
                      'w-full py-2.5 px-4 rounded-lg text-sm font-semibold',
                      running
                        ? 'bg-amber-600 hover:bg-amber-500 text-white'
                        : 'bg-green-700 hover:bg-green-600 text-white',
                      'focus:outline-none focus:ring-2 focus:ring-slate-500',
                      'disabled:opacity-50 disabled:cursor-not-allowed',
                      'transition-colors duration-150',
                    ].join(' ')}
                  >
                    {running ? 'Pause' : 'Resume'}
                  </button>
                )}
              </Tip>

              {/* Reset Simulation */}
              <Tip tip="Restarts from the full-power design state (shutdown bank withdrawn, control bank at 50 %, design temperatures and pressure). The only way back to power after a SCRAM; the procedure-driven startup of a real plant is not modeled.">
                {(tipId) => (
                  <button
                    aria-describedby={tipId}
                    type="button"
                    disabled={!connected}
                    onClick={() => setResetDialogOpen(true)}
                    className={[
                      'w-full py-2.5 px-4 rounded-lg text-sm font-medium',
                      'bg-slate-700 hover:bg-slate-600 text-slate-300',
                      'focus:outline-none focus:ring-2 focus:ring-slate-500',
                      'disabled:opacity-50 disabled:cursor-not-allowed',
                      'transition-colors duration-150',
                    ].join(' ')}
                  >
                    Reset Simulation
                  </button>
                )}
              </Tip>
            </div>
          </section>

          {/* ════════════════════════════════════════════════════════════════════
              4. SPEED
          ═══════════════════════════════════════════════════════════════════ */}
          <section aria-label="Speed control">
            <SectionHeading>Speed</SectionHeading>

            {/* Segmented speed selector */}
            <Tip tip="Real-time multiplier. Useful for observing long transients quickly.">
              {(tipId) => (
                <div
                  className="grid grid-cols-4 gap-1 rounded-lg bg-slate-800 p-1"
                  role="group"
                  aria-label="Simulation speed multiplier"
                >
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
                          'py-1.5 rounded-md text-sm font-semibold transition-colors duration-150',
                          'focus:outline-none focus:ring-2 focus:ring-sky-500',
                          active
                            ? 'bg-sky-600 text-white shadow'
                            : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700',
                          'disabled:opacity-50 disabled:cursor-not-allowed',
                        ].join(' ')}
                      >
                        {opt}×
                      </button>
                    )
                  })}
                </div>
              )}
            </Tip>
          </section>

        </div>
      </section>
    </>
  )
}

export default ControlPanel
