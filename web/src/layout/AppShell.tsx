/**
 * AppShell — persistent visual chrome for fission-sim web UI.
 *
 * Renders the full-page scaffold:
 *   - Header: wordmark, live sim-clock, connection-status chip, scram indicator
 *   - Main: two-column grid (charts 2/3, sidebar 1/3 at >=lg; single col below)
 *   - Footer: build info + ws status
 *
 * Placeholder sections are rendered with dashed borders so feat-009/010/011
 * workers can see the scaffold clearly. Replace each placeholder with the real
 * component when ready.
 */

import type { FC } from 'react'
import { useTelemetryStore } from '../state/telemetryStore'
import type { ConnectionStatus } from '../types/telemetry'

// ---------------------------------------------------------------------------
// Colour/label maps for connection status chip
// ---------------------------------------------------------------------------

/** Tailwind background-colour class for the status dot. */
const STATUS_DOT_CLASS: Record<ConnectionStatus, string> = {
  connecting: 'bg-amber-400',
  connected: 'bg-green-400',
  disconnected: 'bg-red-500',
}

/** Human-readable label for each connection state. */
const STATUS_LABEL: Record<ConnectionStatus, string> = {
  connecting: 'Connecting…',
  connected: 'Connected',
  disconnected: 'Disconnected',
}

// ---------------------------------------------------------------------------
// Reactor-ring SVG icon (inline — no external asset dependency)
// ---------------------------------------------------------------------------

/** Small inline SVG that suggests a nuclear reactor core / atom ring. */
const ReactorIcon: FC = () => (
  <svg
    aria-hidden="true"
    width="28"
    height="28"
    viewBox="0 0 28 28"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className="shrink-0"
  >
    {/* Outer ring */}
    <circle cx="14" cy="14" r="12" stroke="#f59e0b" strokeWidth="2" />
    {/* Middle ring */}
    <circle cx="14" cy="14" r="7" stroke="#fcd34d" strokeWidth="1.5" strokeDasharray="4 2" />
    {/* Core dot */}
    <circle cx="14" cy="14" r="2.5" fill="#f59e0b" />
  </svg>
)

// ---------------------------------------------------------------------------
// Header sub-component
// ---------------------------------------------------------------------------

interface HeaderProps {
  /** Formatted sim-clock string, e.g. "T+ 01:23.4" */
  simClock: string
  status: ConnectionStatus
  scrammed: boolean
}

const Header: FC<HeaderProps> = ({ simClock, status, scrammed }) => {
  const dotClass = STATUS_DOT_CLASS[status]
  const label = STATUS_LABEL[status]

  return (
    <header className="bg-slate-900 border-b border-slate-800 px-4 py-3 flex items-center gap-4 z-10">
      {/* ── Left: wordmark ─────────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 min-w-0">
        <ReactorIcon />
        <div className="leading-none">
          <span className="text-amber-400 font-bold text-lg tracking-tight">
            fission-sim
          </span>
          <span className="block text-slate-400 text-xs tracking-wide">
            PWR Simulator
          </span>
        </div>
      </div>

      {/* ── Center: live sim-clock ─────────────────────────────────────────── */}
      <div className="flex-1 flex justify-center">
        <span
          className="font-mono tabular-nums text-slate-100 text-base tracking-wide"
          aria-label="Simulation elapsed time"
        >
          {simClock}
        </span>
      </div>

      {/* ── Right: status chips ────────────────────────────────────────────── */}
      <div className="flex items-center gap-2 shrink-0">
        {/* SCRAM indicator — only visible when active */}
        {scrammed && (
          <span className="inline-flex items-center gap-1.5 rounded-full bg-red-600 px-3 py-1 text-xs font-bold text-white tracking-wider uppercase">
            SCRAMMED
          </span>
        )}

        {/* Connection-status chip */}
        <div className="inline-flex items-center gap-2 rounded-full bg-slate-800 border border-slate-700 px-3 py-1.5 text-sm font-medium shadow-sm">
          <span className={`inline-block h-2.5 w-2.5 rounded-full ${dotClass}`} />
          <span className="text-slate-200">{label}</span>
        </div>
      </div>
    </header>
  )
}

// ---------------------------------------------------------------------------
// Footer sub-component
// ---------------------------------------------------------------------------

interface FooterProps {
  status: ConnectionStatus
}

const Footer: FC<FooterProps> = ({ status }) => (
  <footer className="bg-slate-900 border-t border-slate-800 px-4 py-2 text-xs text-slate-500 flex items-center justify-between">
    <span>
      fission-sim web UI &middot; build mode:{' '}
      <span className="font-mono">{import.meta.env.MODE}</span>
      &nbsp;&middot;&nbsp;ws:{' '}
      <span className="font-mono">{status}</span>
    </span>
    {/* Placeholder anchor — will point to hosted docs in a later milestone */}
    <a
      href="/"
      className="text-slate-500 hover:text-slate-300 underline underline-offset-2 transition-colors"
    >
      README
    </a>
  </footer>
)

// ---------------------------------------------------------------------------
// Placeholder section helper
// ---------------------------------------------------------------------------

interface PlaceholderProps {
  id: string
  label: string
  className?: string
}

/**
 * Dashed-border placeholder for a layout region.
 * Subsequent features replace these with real content.
 */
const Placeholder: FC<PlaceholderProps> = ({ id, label, className = '' }) => (
  <section
    id={id}
    className={`flex items-center justify-center rounded border-2 border-dashed border-slate-700 bg-slate-900/40 text-slate-500 text-sm select-none ${className}`}
    aria-label={label}
  >
    <span className="px-4 py-2 text-center">{label}</span>
  </section>
)

// ---------------------------------------------------------------------------
// Sim-clock formatter
// ---------------------------------------------------------------------------

/**
 * Format simulation time in seconds as "T+ mm:ss.t" with one decimal place.
 *
 * Examples:
 *   0        → "T+ 00:00.0"
 *   90.7     → "T+ 01:30.7"
 *   3661.25  → "T+ 61:01.2"
 */
function formatSimClock(t: number | null | undefined): string {
  if (t == null) return 'T+ --:--.--'
  const totalSeconds = Math.max(0, t)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  const mm = String(minutes).padStart(2, '0')
  const ss = String(Math.floor(seconds)).padStart(2, '0')
  const tenths = Math.floor((seconds % 1) * 10)
  return `T+ ${mm}:${ss}.${tenths}`
}

// ---------------------------------------------------------------------------
// AppShell — top-level layout component
// ---------------------------------------------------------------------------

/**
 * AppShell
 *
 * Full-page layout shell. Reads connection status and the latest telemetry
 * frame from the global Zustand store; renders header, main grid, and footer.
 *
 * The main grid uses a 3-column CSS grid:
 *   - Charts column: spans 2 of 3 columns on >=lg screens
 *   - Sidebar: spans 1 of 3 columns on >=lg; stacks below charts on smaller screens
 *
 * Children are NOT accepted — layout regions are hardcoded as placeholders
 * until feat-009/010/011 replace them.
 */
const AppShell: FC = () => {
  const status = useTelemetryStore((s) => s.status)
  const latest = useTelemetryStore((s) => s.latest)

  const simClock = formatSimClock(latest?.t)
  const scrammed = latest?.scrammed === true

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* ── Header ───────────────────────────────────────────────────────── */}
      <Header simClock={simClock} status={status} scrammed={scrammed} />

      {/* ── Main content area ─────────────────────────────────────────────── */}
      <main className="flex-1 max-w-screen-2xl w-full mx-auto px-4 py-4">
        {/*
         * Responsive two-column grid:
         *   <lg  → 1 column (grid-cols-1)
         *   >=lg → 3-column base with charts spanning 2 cols, sidebar 1 col
         */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 h-full">

          {/* ── Charts column (2/3 width on lg+) ─────────────────────────── */}
          <Placeholder
            id="charts"
            label="Charts area — placeholder for feat-009"
            className="lg:col-span-2 min-h-[480px]"
          />

          {/* ── Sidebar (1/3 width on lg+) ───────────────────────────────── */}
          <div className="flex flex-col gap-4">
            <Placeholder
              id="widgets"
              label="Widgets — placeholder for feat-010"
              className="flex-1 min-h-[200px]"
            />
            <Placeholder
              id="controls"
              label="Controls — placeholder for feat-011"
              className="flex-1 min-h-[200px]"
            />
          </div>

        </div>
      </main>

      {/* ── Footer ───────────────────────────────────────────────────────── */}
      <Footer status={status} />
    </div>
  )
}

export default AppShell
