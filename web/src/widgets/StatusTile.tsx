/**
 * StatusTile — a single telemetry readout card with an educational tooltip.
 *
 * Renders a dark, rounded card showing:
 *   - A small label row (top-left: field name, top-right: info button)
 *   - A large primary value with unit suffix
 *   - An optional secondary value line (e.g., Celsius alongside Kelvin)
 *   - An educational tooltip (no runtime dep)
 *
 * The explanation is the point of the tile for a learner, so it is reachable
 * three ways: hovering the tile, focusing the info button with the keyboard,
 * or clicking/tapping the info button (which pins it open until tapped
 * again, Escape, a tap elsewhere, or focus moving off the button). The button is linked to the tooltip
 * with aria-describedby so screen readers read the explanation on focus.
 *
 * The tooltip is positioned below the tile and uses z-50 so it overlays
 * charts and neighbouring tiles.
 *
 * @module StatusTile
 */

import { type FC, useEffect, useId, useRef, useState } from 'react'
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
 * Aria-hidden because it is decorative: the surrounding button carries the
 * accessible name, and the tooltip is linked to it as the description.
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
  /**
   * Which edge of the tile the tooltip anchors to.
   *
   * - 'left'  (default) — tooltip opens rightward from the tile's left edge.
   *   Correct for left-column tiles where there is room to the right.
   * - 'right' — tooltip opens leftward from the tile's right edge.
   *   Use for right-column tiles that sit near the viewport edge, so the
   *   tooltip extends inward instead of overflowing the viewport.
   */
  tooltipSide?: 'left' | 'right'
  /**
   * HTML data-testid attribute for Playwright/testing selectors.
   * Passed through to the root div of the tile.
   */
  'data-testid'?: string
}

// ---------------------------------------------------------------------------
// StatusTile component
// ---------------------------------------------------------------------------

/**
 * StatusTile
 *
 * A single readout card with a hover / focus / tap tooltip.
 *
 * Props:
 *   tooltip     — `{ title, body, units }` from tooltips.ts
 *   value       — formatted primary value string
 *   secondary   — optional secondary annotation string
 *   band        — 'green' | 'amber' | 'red' colour band (default: 'green')
 *   tooltipSide — 'left' | 'right' tooltip anchor edge (default: 'left')
 */
const StatusTile: FC<StatusTileProps> = ({ tooltip, value, secondary, band = 'green', tooltipSide = 'left', 'data-testid': testId }) => {
  const { border, value: valueClass } = BAND_CLASSES[band]

  // Unique id linking the info button to its tooltip (aria-describedby).
  const tooltipId = useId()
  // True while the explanation is pinned open by a click or tap.
  const [pinned, setPinned] = useState(false)
  const tileRef = useRef<HTMLDivElement>(null)

  // A pinned tooltip closes when focus leaves the info button (onBlur below),
  // so Tab-ing onward never leaves a trail of open tooltips. Touch browsers
  // (notably Safari) do not always focus a tapped button, so blur alone is
  // not enough: a tap or click anywhere outside the tile also closes it.
  useEffect(() => {
    if (!pinned) return
    const closeIfOutside = (e: PointerEvent) => {
      if (!tileRef.current?.contains(e.target as Node)) setPinned(false)
    }
    document.addEventListener('pointerdown', closeIfOutside)
    return () => document.removeEventListener('pointerdown', closeIfOutside)
  }, [pinned])

  return (
    /*
     * `group` lets the tooltip react to state on the whole tile: hovering the
     * tile (`group-hover`) or keyboard focus on the info button
     * (`group-has-[:focus-visible]`). `relative` establishes the positioning
     * context for the tooltip.
     */
    <div
      ref={tileRef}
      className={`group relative rounded-2xl bg-slate-900 border ${border} p-4 flex flex-col gap-1 cursor-default transition-colors`}
      data-testid={testId}
    >
      {/* ── Top row: label + info button ───────────────────────────────────── */}
      <div className="flex items-center justify-between gap-1">
        <span className="text-xs text-slate-400 uppercase tracking-wide font-medium leading-none">
          {tooltip.title}
        </span>
        {/*
         * Info button — a real focusable control so keyboard and touch users
         * can reach the explanation. The negative margin enlarges the tap
         * target without moving the icon.
         */}
        <button
          type="button"
          aria-label={`About ${tooltip.title}`}
          aria-describedby={tooltipId}
          onClick={() => setPinned((p) => !p)}
          onBlur={() => setPinned(false)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') setPinned(false)
          }}
          className="-m-1 p-1 rounded-full text-slate-500 group-hover:text-slate-300 focus-visible:text-slate-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 transition-colors shrink-0"
        >
          <InfoIcon />
        </button>
      </div>

      {/* ── Primary value + unit ───────────────────────────────────────────── */}
      <div className="flex items-baseline gap-1">
        <span
          className={`text-3xl font-mono tabular-nums leading-none ${valueClass}`}
          data-testid={testId ? `${testId}-value` : undefined}
        >
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

      {/* ── Tooltip ────────────────────────────────────────────────────────── */}
      {/*
       * Positioned absolutely below the tile.
       * opacity-0 by default; opacity-100 on tile hover, on keyboard focus of
       * the info button, or while pinned by a click/tap. It stays in the
       * accessibility tree when transparent, so aria-describedby always works.
       * pointer-events-none so it never intercepts clicks.
       * z-50 ensures it floats above charts and neighbouring tiles.
       * min-w-[16rem] / max-w-xs keeps copy readable without overflow.
       *
       * Horizontal anchor: controlled by `tooltipSide` prop.
       *   'left'  → left-0  — tooltip extends rightward from the tile's left edge.
       *             For left-column tiles; plenty of space to the right.
       *   'right' → right-0 — tooltip extends leftward from the tile's right edge.
       *             For right-column tiles near the viewport edge; extends inward
       *             so the tooltip never makes the page wider than the window
       *             (which would add a horizontal scrollbar at 1280 px).
       *
       * NOTE: Tailwind purges class names that are only constructed dynamically.
       * These class strings must appear verbatim (not concatenated at runtime)
       * so the Tailwind scanner includes them in the output CSS bundle.
       */}
      <div
        id={tooltipId}
        className={[
          `absolute ${tooltipSide === 'right' ? 'right-0' : 'left-0'} top-[calc(100%+6px)]`,
          'z-50 min-w-[16rem] max-w-xs',
          'bg-slate-950 border border-slate-700 rounded-lg p-3',
          'text-xs text-slate-200 shadow-lg',
          pinned
            ? 'opacity-100'
            : 'opacity-0 group-hover:opacity-100 group-has-[:focus-visible]:opacity-100',
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
