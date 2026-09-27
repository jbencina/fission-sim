/**
 * Toolbar — the console's top bar.
 *
 * Left: the wordmark, the elapsed simulation clock, and the plant state as
 * dot-plus-word items: connection, run state with speed, and the SCRAM
 * latch. Right: the learning-use note and a link to the README. Each state
 * item explains itself on hover, focus or tap.
 */

import type { FC } from 'react'
import { useTelemetryStore } from '../state/telemetryStore'
import type { ConnectionStatus } from '../types/telemetry'
import { InfoTip } from '../ui/InfoTip'
import { formatClock } from '../ui/format'
import { BookIcon } from '../ui/icons'
import { TOOLTIPS } from '../widgets/tooltips'

const README_URL = 'https://github.com/jbencina/fission-sim#readme'

const item =
  'inline-flex h-7 items-center gap-2 text-[12.5px] tracking-[0.04em] text-ink-2 transition-colors hover:text-ink'
const dot = 'inline-block h-1.5 w-1.5 rounded-full'

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
      </div>

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
