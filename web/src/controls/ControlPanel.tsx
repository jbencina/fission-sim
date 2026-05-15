/**
 * ControlPanel — operator controls for the fission-sim web UI.
 *
 * Provides four control sections:
 *   1. Rod control  — range slider to set the rod-position command (0–1).
 *   2. Safety       — SCRAM button with confirmation modal; Reset Scram when active.
 *   3. Run          — Pause/Resume toggle and Reset Simulation (with confirmation).
 *   4. Speed        — Segmented 1× / 2× / 5× / 10× real-time multiplier.
 *
 * All controls dispatch via `useTelemetryStore.getState().sendCommand(cmd)`.
 * When the WebSocket status is not 'connected', every control is visually
 * disabled and a notice is shown at the top of the panel.
 *
 * CSS-only tooltips are used for all controls (no tooltip library dependency).
 *
 * @module ControlPanel
 */

import { type FC, useState, useCallback, useRef, useEffect } from 'react'
import { useTelemetryStore } from '../state/telemetryStore'
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
 * CSS-only tooltip container.
 * Children are wrapped in a `group` div; the tooltip is a hidden sibling that
 * appears on `group-hover`. Both the trigger and tooltip slot are controlled
 * by the caller via `children` and `tip`.
 */
const Tip: FC<{ tip: string; children: React.ReactNode; className?: string }> = ({
  tip,
  children,
  className = '',
}) => (
  <div className={`group relative ${className}`}>
    {children}
    <div
      className={[
        'absolute bottom-[calc(100%+6px)] left-0',
        'z-50 w-64',
        'bg-slate-950 border border-slate-700 rounded-lg p-3',
        'text-xs text-slate-200 shadow-lg leading-relaxed',
        'opacity-0 group-hover:opacity-100',
        'transition-opacity duration-150',
        'pointer-events-none',
      ].join(' ')}
      role="tooltip"
    >
      {tip}
    </div>
  </div>
)

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

  // Convenience booleans derived from latest frame.
  const connected = status === 'connected'
  const scrammed = latest?.scrammed === true
  const running = latest?.running === true
  const speed = latest?.speed ?? 1
  const rodPosition = latest?.rod_position ?? 0

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
    sendCommand({ type: 'reset' })
  }, [sendCommand])

  const handleSetSpeed = useCallback(
    (value: 1 | 2 | 5 | 10) => {
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

  // Speed options for the segmented control.
  const SPEED_OPTIONS: Array<1 | 2 | 5 | 10> = [1, 2, 5, 10]

  return (
    <>
      {/* Inject slider custom CSS once */}
      <style>{SLIDER_STYLES}</style>

      {/* Modals — rendered outside the disabled overlay */}
      <ConfirmDialog
        open={scramDialogOpen}
        title="Initiate SCRAM?"
        message="This will drive all control rods to full insertion immediately. Reactor power will drop within seconds. This action cannot be undone without a Reset Scram."
        confirmLabel="SCRAM"
        danger
        onConfirm={handleScramConfirm}
        onCancel={() => setScramDialogOpen(false)}
      />
      <ConfirmDialog
        open={resetDialogOpen}
        title="Reset simulation?"
        message="This will return the simulator to its initial steady-state condition at t = 0. All current transient data will be lost."
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

            {/* Numeric readout: command vs actual position */}
            <div className="flex justify-between text-xs text-slate-400 font-mono mb-2">
              <span>
                Command:{' '}
                <span className="text-amber-300">{localRodCmd.toFixed(3)}</span>
              </span>
              <span>
                Position:{' '}
                <span className="text-sky-300">{rodPosition.toFixed(3)}</span>
              </span>
            </div>

            {/* Rod command slider with tooltip */}
            <Tip tip="Set the rod-position command. The simulator drives rod_position toward this value at a finite rate (typical full-stroke time: ~30 s).">
              <input
                type="range"
                className="rod-slider"
                min={0}
                max={1}
                step={0.01}
                value={localRodCmd}
                disabled={!connected}
                aria-label="Rod command"
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
            </Tip>

            {/* Actual rod position progress bar — shows lag between command and position */}
            <div className="mt-2">
              <div className="text-[10px] text-slate-500 mb-1">Actual rod position</div>
              <div className="h-1.5 w-full rounded bg-slate-700 overflow-hidden">
                <div
                  className="h-full bg-sky-500 rounded transition-all duration-300"
                  style={{ width: `${Math.min(1, Math.max(0, rodPosition)) * 100}%` }}
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
            <Tip tip="Emergency shutdown — drives all rods to full insertion immediately. Use only in an emergency or to practice. Reactor power drops within seconds.">
              <button
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
            </Tip>

            {/* Reset Scram — only shown when reactor is in scrammed state */}
            {scrammed && (
              <div className="mt-2">
                <Tip tip="Clear the SCRAM latch and restore operator rod control. Only use once the cause of the SCRAM has been addressed.">
                  <button
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
              <Tip tip="Pauses simulator time advancement. Telemetry still streams; values are frozen.">
                <button
                  type="button"
                  disabled={!connected}
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
              </Tip>

              {/* Reset Simulation */}
              <Tip tip="Returns the simulator to its initial steady-state condition.">
                <button
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
              <div
                className="grid grid-cols-4 gap-1 rounded-lg bg-slate-800 p-1"
                role="group"
                aria-label="Simulation speed multiplier"
              >
                {SPEED_OPTIONS.map((opt) => {
                  const active = speed === opt
                  return (
                    <button
                      key={opt}
                      type="button"
                      disabled={!connected}
                      onClick={() => handleSetSpeed(opt)}
                      aria-pressed={active}
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
            </Tip>
          </section>

        </div>
      </section>
    </>
  )
}

export default ControlPanel
