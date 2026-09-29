/**
 * Toolbar — the console's top bar.
 *
 * Left: the wordmark, the elapsed simulation clock, and the plant state as
 * dot-plus-word items: connection, run state with speed, SCRAM latch,
 * effective turbine trip, and rod-control mode. A compact persistent action
 * strip keeps SCRAM and Pause/Resume reachable while columns scroll. Right:
 * the learning-use note and a link to the README. Each state item explains
 * itself on hover, focus or tap.
 */

import { type FC, useCallback, useState } from 'react'
import ConfirmDialog from '../controls/ConfirmDialog'
import { deriveToolbarTurbineTripDisplay } from '../state/admissionStatus'
import { deriveRodModeStatus, type StatusTone } from '../state/plantStatus'
import { useTelemetryStore } from '../state/telemetryStore'
import type { ConnectionStatus } from '../types/telemetry'
import { HelpTip, InfoTip } from '../ui/InfoTip'
import { formatClock } from '../ui/format'
import { BookIcon, PauseIcon, PlayIcon } from '../ui/icons'
import { TOOLTIPS } from '../widgets/tooltips'

const README_URL = 'https://github.com/jbencina/fission-sim#readme'

const item =
  'inline-flex h-7 items-center gap-2 text-[12.5px] tracking-[0.04em] text-ink-2 transition-colors hover:text-ink'
const dot = 'inline-block h-1.5 w-1.5 rounded-full'
const compactButton =
  'inline-flex h-7 items-center justify-center gap-1.5 border border-line-strong px-2 text-[11.5px] tracking-[0.08em] transition-colors hover:border-ink hover:text-ink disabled:cursor-not-allowed disabled:opacity-45'
const P4_TURBINE_TRIP_COPY =
  "SCRAM also trips the turbine through the simulator's P-4 turbine-trip consequence, so steam transfers to the dump path while fission power falls."

function toneClass(tone: StatusTone): string {
  if (tone === 'danger') return '!text-danger'
  if (tone === 'warn') return '!text-warn'
  return ''
}

// ---------------------------------------------------------------------------
// Connection
// ---------------------------------------------------------------------------

const CONNECTION: Record<ConnectionStatus, { label: string; dot: string }> = {
  connecting: { label: 'Connecting…', dot: 'bg-ink-3 animate-pulse' },
  connected: { label: 'Connected', dot: 'bg-live' },
  disconnected: { label: 'Disconnected', dot: 'bg-danger' },
}

const ConnectionIndicator: FC = () => {
  const status = useTelemetryStore((s) => s.status)
  const { label, dot: dotClass } = CONNECTION[status]
  return (
    <span role="status" className={item}>
      <span className={`${dot} ${dotClass}`} />
      {label}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Simulation clock and state
// ---------------------------------------------------------------------------

const SimClock: FC = () => {
  const t = useTelemetryStore((s) => s.latest?.t ?? null)
  return (
    <InfoTip
      title={TOOLTIPS.sim_time.title}
      body={TOOLTIPS.sim_time.body}
      label={`Simulation time ${formatClock(t)}`}
      className="inline-flex items-baseline gap-2.5 px-1 transition-colors hover:bg-surface-2"
    >
      <span className="eyebrow">Elapsed</span>
      <span className="font-mono text-[24px] font-light leading-none tracking-[0.02em] text-ink sm:text-[26px]">
        {formatClock(t)}
      </span>
    </InfoTip>
  )
}

const SimState: FC = () => {
  const speed = useTelemetryStore((s) => s.latest?.speed ?? null)
  const running = useTelemetryStore((s) => s.latest?.running ?? null)
  const scrammed = useTelemetryStore((s) => s.latest?.scrammed === true)
  const halted = useTelemetryStore((s) => s.latest != null && s.latest.model_limit !== null)

  if (running === null) return null
  const runLabel = halted ? 'Halted' : running ? `Running ${speed}×` : 'Paused'

  return (
    <>
      <InfoTip
        title={TOOLTIPS.running.title}
        body={TOOLTIPS.running.body}
        label={`Run state: ${halted ? 'halted' : running ? 'running' : 'paused'}, speed ${speed}×`}
        className={`${item} ${halted ? '!text-danger' : ''}`}
      >
        <span className={`${dot} ${halted ? 'bg-danger' : running ? 'bg-live' : 'bg-ink-3'}`} />
        <span className="tabular-nums">{runLabel}</span>
      </InfoTip>
      {scrammed && (
        <InfoTip
          title={TOOLTIPS.scrammed.title}
          body={TOOLTIPS.scrammed.body}
          label="Reactor scrammed"
          className={`${item} !text-danger`}
        >
          <span aria-hidden="true" className="inline-block h-2 w-2 bg-danger" />
          SCRAM latched
        </InfoTip>
      )}
    </>
  )
}

const TurbineTripChip: FC = () => {
  const latest = useTelemetryStore((s) => s.latest)
  if (!latest) return null

  const display = deriveToolbarTurbineTripDisplay(latest)

  return (
    <InfoTip
      title="Turbine trip status"
      body={display.cause}
      label={display.label}
      className={`${item} ${toneClass(display.tone)}`}
    >
      <span className={`${dot} ${display.active || display.pending ? 'bg-warn' : 'bg-ink-3'}`} />
      <span className="tabular-nums">{display.label}</span>
      {display.active && display.closed && <span className="text-ink-3">closed</span>}
    </InfoTip>
  )
}

const RodModeChip: FC = () => {
  const latest = useTelemetryStore((s) => s.latest)
  if (!latest) return null

  const rodStatus = deriveRodModeStatus(latest)
  return (
    <InfoTip
      title="Rod-control mode"
      body={rodStatus.detail}
      label={`Rod-control mode: ${rodStatus.label}`}
      className={`${item} ${toneClass(rodStatus.tone)}`}
    >
      <span className={`${dot} ${rodStatus.tone === 'warn' ? 'bg-warn' : 'bg-ink-3'}`} />
      <span className="tabular-nums">Rods {rodStatus.label}</span>
    </InfoTip>
  )
}

const ToolbarActions: FC = () => {
  const status = useTelemetryStore((s) => s.status)
  const latest = useTelemetryStore((s) => s.latest)
  const sendCommand = useTelemetryStore((s) => s.sendCommand)
  const connected = status === 'connected'
  const scrammed = latest?.scrammed === true
  const running = latest?.running === true
  const halted = latest != null && latest.model_limit !== null
  const [scramDialogOpen, setScramDialogOpen] = useState(false)

  const handleScramConfirm = useCallback(() => {
    setScramDialogOpen(false)
    sendCommand({ type: 'scram' })
  }, [sendCommand])

  const handlePauseResume = useCallback(() => {
    sendCommand({ type: running ? 'pause' : 'resume' })
  }, [running, sendCommand])

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
      <div className="order-last flex basis-full flex-wrap items-center gap-2 border-t border-line pt-2 sm:order-none sm:basis-auto sm:border-0 sm:pt-0">
        <HelpTip tip={`Emergency shutdown. Drops both rod banks. ${P4_TURBINE_TRIP_COPY}`}>
          {(tipId) => (
            <button
              aria-describedby={tipId}
              type="button"
              disabled={!connected || scrammed}
              onClick={() => setScramDialogOpen(true)}
              className={`${compactButton} border-danger text-danger hover:border-danger hover:bg-danger-soft hover:text-danger`}
            >
              {scrammed ? 'SCRAM latched' : 'SCRAM'}
            </button>
          )}
        </HelpTip>
        <HelpTip tip="Pauses simulator time advancement. While paused, accepted commands can show as pending until the simulation runs.">
          {(tipId) => (
            <button
              aria-describedby={tipId}
              type="button"
              disabled={!connected || halted || latest == null}
              onClick={handlePauseResume}
              className={`${compactButton} text-ink-2`}
            >
              {running ? <PauseIcon size={12} /> : <PlayIcon size={11} />}
              {running ? 'Pause' : 'Resume'}
            </button>
          )}
        </HelpTip>
      </div>
    </>
  )
}

// ---------------------------------------------------------------------------
// Right-hand items
// ---------------------------------------------------------------------------

const LearningNote: FC = () => (
  <InfoTip
    title="Learning use only"
    body="Built as a side project for learning, from public sources, by an author with no nuclear engineering training. Model behavior, values, and explanations may be incorrect, incomplete, and oversimplified. Do not rely on it for anything real."
    align="end"
    className={`${item} hidden md:inline-flex`}
  >
    Learning use only
  </InfoTip>
)

// ---------------------------------------------------------------------------
// Toolbar
// ---------------------------------------------------------------------------

const Toolbar: FC = () => (
  <header className="sticky top-0 z-30 border-b border-line-strong bg-canvas">
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 px-4 py-2 sm:px-6">
      <div className="flex items-baseline gap-2.5">
        <h1 className="text-[13px] font-light tracking-[0.3em] text-ink">FISSION-SIM</h1>
        <span className="hidden text-[12px] text-ink-2 lg:inline">PWR simulator</span>
      </div>

      <SimClock />

      {/* On phones the state drops to its own row below the brand and clock. */}
      <div className="order-last flex basis-full flex-wrap items-center gap-x-5 gap-y-1 sm:order-none sm:basis-auto">
        <ConnectionIndicator />
        <SimState />
        <TurbineTripChip />
        <RodModeChip />
      </div>

      <ToolbarActions />

      <div className="ml-auto flex items-center gap-4">
        <LearningNote />
        <a
          href={README_URL}
          target="_blank"
          rel="noopener noreferrer"
          aria-label="Project README on GitHub"
          title="README"
          className="grid h-8 w-8 place-items-center border border-line-strong text-ink-2 transition-colors hover:border-ink hover:text-ink"
        >
          <BookIcon size={15} />
        </a>
      </div>
    </div>
  </header>
)

export default Toolbar
