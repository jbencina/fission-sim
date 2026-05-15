/**
 * StatusTile — a single telemetry readout card with an educational tooltip.
 *
 * Renders a dark, rounded card showing:
 *   - A small label row (top-left: field name, top-right: info icon)
 *   - A large primary value with unit suffix
 *   - An optional secondary value line (e.g., Celsius alongside Kelvin)
 *   - A CSS-only tooltip (no runtime dep) triggered on group-hover
 *
 * The tooltip is positioned below the tile and uses z-50 so it overlays
 * charts and neighbouring tiles.
 *
 * @module StatusTile
 */

import type { FC } from 'react'
import type { TooltipEntry } from './tooltips'

// ---------------------------------------------------------------------------
// Colour-band accent classes
// ---------------------------------------------------------------------------

/** Tailwind border-colour and value-colour for each alarm band. */
const BAND_CLASSES: Record<'green' | 'amber' | 'red', { border: string; value: string }> = {
  green: { border: 'border-slate-800', value: 'text-slate-100' },
  amber: { border: 'border-amber-500/60', value: 'text-amber-300' },
  red: { border: 'border-red-500/70', value: 'text-red-300' },
}

// ---------------------------------------------------------------------------
// Info icon — inline SVG circle-i
// ---------------------------------------------------------------------------

/**
 * Small inline "ⓘ" SVG icon. Rendered at 14×14 px.
 * Aria-hidden because the tooltip text is the accessible description.
 */
const InfoIcon: FC = () => (
  <svg
    aria-hidden="true"
    width="14"
    height="14"
    viewBox="0 0 14 14"
    fill="none"
    xmlns="http://www.w3.org/2000/svg"
    className="shrink-0"
  >
    <circle cx="7" cy="7" r="6.25" stroke="currentColor" strokeWidth="1.25" />
    {/* dot above the "i" stem */}
    <circle cx="7" cy="4.5" r="0.9" fill="currentColor" />
    {/* stem */}
    <rect x="6.25" y="6.25" width="1.5" height="3.5" rx="0.6" fill="currentColor" />
  </svg>
)

// ---------------------------------------------------------------------------
// StatusTile props
// ---------------------------------------------------------------------------

export interface StatusTileProps {
  /** Tooltip / title info for this tile. */
  tooltip: TooltipEntry
  /** Formatted primary value string, e.g. "3000.0" or "--". */
  value: string
  /** Optional secondary line, e.g. "(327 °C)". */
  secondary?: string
  /** Alarm band — controls border and value text colour. */
  band?: 'green' | 'amber' | 'red'
}

// ---------------------------------------------------------------------------
// StatusTile component
// ---------------------------------------------------------------------------

/**
 * StatusTile
 *
 * A single readout card with CSS-only hover tooltip.
 *
 * Props:
 *   tooltip   — `{ title, body, units }` from tooltips.ts
 *   value     — formatted primary value string
 *   secondary — optional secondary annotation string
 *   band      — 'green' | 'amber' | 'red' colour band (default: 'green')
 */
const StatusTile: FC<StatusTileProps> = ({ tooltip, value, secondary, band = 'green' }) => {
  const { border, value: valueClass } = BAND_CLASSES[band]

  return (
    /*
     * `group` enables CSS sibling/child selectors driven by hover state.
     * The tooltip child uses `group-hover:opacity-100` to appear on tile hover.
     * `relative` establishes the positioning context for the tooltip.
     */
    <div
      className={`group relative rounded-2xl bg-slate-900 border ${border} p-4 flex flex-col gap-1 cursor-default transition-colors`}
    >
      {/* ── Top row: label + info icon ─────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-1">
        <span className="text-xs text-slate-400 uppercase tracking-wide font-medium leading-none">
          {tooltip.title}
        </span>
        {/* Info icon — colour transitions to indicate interactivity */}
        <span className="text-slate-500 group-hover:text-slate-300 transition-colors shrink-0">
          <InfoIcon />
        </span>
      </div>

      {/* ── Primary value + unit ───────────────────────────────────────────── */}
      <div className="flex items-baseline gap-1">
        <span className={`text-3xl font-mono tabular-nums leading-none ${valueClass}`}>
          {value}
        </span>
        {tooltip.units && (
          <span className="text-base text-slate-400 leading-none">{tooltip.units}</span>
        )}
      </div>

      {/* ── Optional secondary line (e.g. °C alongside K) ─────────────────── */}
      {secondary && (
        <span className="text-xs text-slate-500 font-mono leading-none">{secondary}</span>
      )}

      {/* ── CSS-only tooltip ───────────────────────────────────────────────── */}
      {/*
       * Positioned absolutely below the tile.
       * opacity-0 by default; transitions to opacity-100 on `group-hover`.
       * pointer-events-none so it never intercepts clicks.
       * z-50 ensures it floats above charts and neighbouring tiles.
       * min-w-[16rem] / max-w-xs keeps copy readable without overflow.
       *
       * To avoid clipping at the right panel edge, the tooltip is left-aligned
       * to the tile and constrained by max-w-xs (20rem). This keeps it visible
       * even for the rightmost tiles in a 2-column grid.
       */}
      <div
        className={[
          'absolute left-0 top-[calc(100%+6px)]',
          'z-50 min-w-[16rem] max-w-xs',
          'bg-slate-950 border border-slate-700 rounded-lg p-3',
          'text-xs text-slate-200 shadow-lg',
          'opacity-0 group-hover:opacity-100',
          'transition-opacity duration-150',
          'pointer-events-none',
        ].join(' ')}
        role="tooltip"
      >
        {/* Tooltip title */}
        <p className="font-semibold text-slate-100 mb-1">{tooltip.title}</p>
        {/* Tooltip body — plain-language explanation */}
        <p className="text-slate-300 leading-relaxed">{tooltip.body}</p>
      </div>
    </div>
  )
}

export default StatusTile
