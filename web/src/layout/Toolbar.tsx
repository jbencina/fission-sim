/**
 * Toolbar — the dashboard's top bar.
 *
 * Left: the wordmark, the connection indicator and the simulation's state
 * (clock, speed, running/paused/halted, SCRAM). Right: the learning-use
 * badge, the theme switch and a link to the project README. The state
 * badges are buttons that explain themselves on hover, focus or tap.
 */

import type { FC } from 'react'
import { useTelemetryStore } from '../state/telemetryStore'
import type { ConnectionStatus } from '../types/telemetry'
import { type ThemePreference, useThemeStore } from '../theme/themeStore'
import { InfoTip } from '../ui/InfoTip'
import { formatClock } from '../ui/format'
import { BookIcon, BrandMark, MonitorIcon, MoonIcon, PauseIcon, SunIcon } from '../ui/icons'
import { TOOLTIPS } from '../widgets/tooltips'

const README_URL = 'https://github.com/jbencina/fission-sim#readme'

const badge =
  'inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-[12px] font-semibold transition-colors'
const neutralBadge = `${badge} bg-surface-2 text-ink-2 hover:bg-surface-3`
const dangerBadge = `${badge} bg-danger-soft text-danger-ink`

// ---------------------------------------------------------------------------
// Connection
// ---------------------------------------------------------------------------

const CONNECTION: Record<ConnectionStatus, { label: string; dot: string; halo: string }> = {
  connecting: { label: 'Connecting…', dot: 'bg-warn animate-pulse', halo: 'var(--warn-soft)' },
  connected: { label: 'Connected', dot: 'bg-live', halo: 'color-mix(in srgb, var(--live) 22%, transparent)' },
  disconnected: { label: 'Disconnected', dot: 'bg-danger', halo: 'var(--danger-soft)' },
}

const ConnectionIndicator: FC = () => {
  const status = useTelemetryStore((s) => s.status)
  const { label, dot, halo } = CONNECTION[status]
  return (
    <span role="status" className="inline-flex items-center gap-2 text-[13px] font-medium text-ink-2">
      <span className={`h-[7px] w-[7px] rounded-full ${dot}`} style={{ boxShadow: `0 0 0 3px ${halo}` }} />
      {label}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Simulation state
// ---------------------------------------------------------------------------

const SimClock: FC = () => {
  const t = useTelemetryStore((s) => s.latest?.t ?? null)
  return (
    <InfoTip
      title={TOOLTIPS.sim_time.title}
      body={TOOLTIPS.sim_time.body}
      label={`Simulation time ${formatClock(t)}`}
      className="rounded-md px-1 text-[13px] font-medium tabular-nums text-ink transition-colors hover:bg-surface-2"
    >
      <span className="text-ink-3">T+</span> {formatClock(t)}
    </InfoTip>
  )
}

const SimState: FC = () => {
  const speed = useTelemetryStore((s) => s.latest?.speed ?? null)
  const running = useTelemetryStore((s) => s.latest?.running ?? null)
  const scrammed = useTelemetryStore((s) => s.latest?.scrammed === true)
  const halted = useTelemetryStore((s) => s.latest != null && s.latest.model_limit !== null)

  if (running === null) return null

  return (
    <>
      <InfoTip
        title={TOOLTIPS.speed.title}
        body={TOOLTIPS.speed.body}
        label={`Simulation speed ${speed}×`}
        className={`${neutralBadge} tabular-nums`}
      >
        {speed}×
      </InfoTip>
      <InfoTip
        title={TOOLTIPS.running.title}
        body={TOOLTIPS.running.body}
        label={`Run state: ${halted ? 'halted' : running ? 'running' : 'paused'}`}
        className={halted ? dangerBadge : neutralBadge}
      >
        {halted ? (
          'Halted'
        ) : running ? (
          <>
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-live" />
            Running
          </>
        ) : (
          <>
            <PauseIcon size={11} strokeWidth={2.6} />
            Paused
          </>
        )}
      </InfoTip>
      {scrammed && (
        <InfoTip
          title={TOOLTIPS.scrammed.title}
          body={TOOLTIPS.scrammed.body}
          label="Reactor scrammed"
          className={dangerBadge}
        >
          <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-danger" />
          Scrammed
        </InfoTip>
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// Right-hand tools
// ---------------------------------------------------------------------------

const THEME_OPTIONS: { value: ThemePreference; label: string; Icon: FC<{ size?: number }> }[] = [
  { value: 'system', label: 'Match system appearance', Icon: MonitorIcon },
  { value: 'light', label: 'Light appearance', Icon: SunIcon },
  { value: 'dark', label: 'Dark appearance', Icon: MoonIcon },
]

const ThemeSwitch: FC = () => {
  const preference = useThemeStore((s) => s.preference)
  const setPreference = useThemeStore((s) => s.setPreference)
  return (
    <div role="group" aria-label="Appearance" className="inline-flex gap-0.5 rounded-[9px] bg-surface-2 p-0.5">
      {THEME_OPTIONS.map(({ value, label, Icon }) => {
        const active = preference === value
        return (
          <button
            key={value}
            type="button"
            aria-label={label}
            aria-pressed={active}
            title={label}
            onClick={() => setPreference(value)}
            className={[
              'grid h-7 w-7 place-items-center rounded-[7px] transition-colors duration-150',
              active ? 'bg-seg-on text-ink shadow-[0_1px_2px_rgba(0,0,0,0.14)]' : 'text-ink-2 hover:text-ink',
            ].join(' ')}
          >
            <Icon size={15} />
          </button>
        )
      })}
    </div>
  )
}

const LearningBadge: FC = () => (
  <InfoTip
    title="Learning use only"
    body="Built as a side project for learning, from public sources, by an author with no nuclear engineering training. Model behavior, values, and explanations may be incorrect, incomplete, and oversimplified. Do not rely on it for anything real."
    align="end"
    className={`${badge} hidden bg-warn-soft text-warn-ink hover:brightness-110 md:inline-flex`}
  >
    Learning use only
  </InfoTip>
)

// ---------------------------------------------------------------------------
// Toolbar
// ---------------------------------------------------------------------------

const Toolbar: FC = () => (
  <header className="glass sticky top-0 z-30 border-b border-line">
    <div className="mx-auto flex max-w-[1720px] flex-wrap items-center gap-x-3 gap-y-2 px-4 py-2.5 sm:px-6">
      <div className="flex items-center gap-2">
        <BrandMark size={22} className="text-accent" />
        <h1 className="text-[15px] font-semibold tracking-[-0.01em] text-ink">fission-sim</h1>
        <span className="hidden text-[13px] text-ink-3 lg:inline">PWR simulator</span>
      </div>

      <span aria-hidden="true" className="mx-1 hidden h-5 w-px bg-line sm:block" />

      {/* On phones the state drops to its own row below the brand and tools. */}
      <div className="order-last flex basis-full flex-wrap items-center gap-x-2.5 gap-y-1.5 sm:order-none sm:basis-auto">
        <ConnectionIndicator />
        <SimClock />
        <SimState />
      </div>

      <div className="ml-auto flex items-center gap-2">
        <LearningBadge />
        <ThemeSwitch />
        <a
          href={README_URL}
          target="_blank"
          rel="noopener noreferrer"
          aria-label="Project README on GitHub"
          title="README"
          className="grid h-8 w-8 place-items-center rounded-[9px] text-ink-2 transition-colors hover:bg-surface-2 hover:text-ink"
        >
          <BookIcon size={17} />
        </a>
      </div>
    </div>
  </header>
)

export default Toolbar
