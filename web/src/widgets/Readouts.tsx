/**
 * Readouts — the status panel's building blocks.
 *
 * - `StatTile`: a large value in a tinted tile, for the headline quantities.
 * - `InfoRow`: a label / value row, for everything else.
 *
 * Both carry their explanation (tooltips.ts): hover the tile or row, or
 * focus or tap its ⓘ button. An alert band tints the tile or colours the
 * value amber or red (thresholds.ts).
 */

import { type FC, useRef } from 'react'
import { InfoTip } from '../ui/InfoTip'
import type { TooltipEntry } from './tooltips'
import type { Band } from './thresholds'

const TILE_BAND: Record<Band, { tile: string; value: string }> = {
  green: { tile: 'bg-surface-2', value: 'text-ink' },
  amber: { tile: 'bg-warn-soft ring-1 ring-inset ring-warn-line', value: 'text-warn-ink' },
  red: { tile: 'bg-danger-soft ring-1 ring-inset ring-danger-line', value: 'text-danger-ink' },
}

const ROW_BAND: Record<Band, string> = {
  green: 'text-ink',
  amber: 'text-warn-ink',
  red: 'text-danger-ink',
}

interface ReadoutProps {
  tooltip: TooltipEntry
  /** Formatted value, e.g. "3,000.0" or "—". */
  value: string
  /** Optional second line / annotation, e.g. "309.9 °C". */
  secondary?: string
  band?: Band
  /** Popover alignment; 'end' opens leftward from the right edge. */
  align?: 'start' | 'end'
  'data-testid'?: string
}

export const StatTile: FC<ReadoutProps> = ({
  tooltip,
  value,
  secondary,
  band = 'green',
  align = 'start',
  'data-testid': testId,
}) => {
  const ref = useRef<HTMLDivElement>(null)
  const classes = TILE_BAND[band]
  return (
    <div
      ref={ref}
      data-testid={testId}
      className={`min-w-0 rounded-xl px-3 pb-2.5 pt-2.5 transition-colors duration-300 ${classes.tile}`}
    >
      <div className="flex items-center justify-between gap-1">
        <span className="truncate text-[12px] text-ink-2">{tooltip.title}</span>
        <InfoTip title={tooltip.title} body={tooltip.body} area={ref} align={align} />
      </div>
      <div className="mt-1 flex items-baseline gap-1 whitespace-nowrap">
        <span
          data-testid={testId ? `${testId}-value` : undefined}
          className={`text-[22px] font-semibold leading-none tracking-[-0.02em] tabular-nums ${classes.value}`}
        >
          {value}
        </span>
        {tooltip.units && <span className="text-[12px] text-ink-2">{tooltip.units}</span>}
      </div>
      <div className="mt-1 h-4 truncate text-[11.5px] tabular-nums text-ink-3">{secondary}</div>
    </div>
  )
}

export const InfoRow: FC<ReadoutProps> = ({
  tooltip,
  value,
  secondary,
  band = 'green',
  align = 'start',
  'data-testid': testId,
}) => {
  const ref = useRef<HTMLDivElement>(null)
  return (
    <div
      ref={ref}
      data-testid={testId}
      className="flex min-h-[38px] items-center justify-between gap-3 border-t border-line py-1.5 first:border-t-0"
    >
      <div className="flex min-w-0 items-center gap-1.5">
        <span className="truncate text-[13px] text-ink-2">{tooltip.title}</span>
        <InfoTip title={tooltip.title} body={tooltip.body} area={ref} align={align} />
      </div>
      <div className="flex shrink-0 items-baseline gap-2 whitespace-nowrap tabular-nums">
        {secondary && <span className="text-[12px] text-ink-3">{secondary}</span>}
        <span className={`text-[13px] font-medium ${ROW_BAND[band]}`}>
          <span data-testid={testId ? `${testId}-value` : undefined}>{value}</span>
          {tooltip.units && <span className="ml-1 font-normal text-ink-2">{tooltip.units}</span>}
        </span>
      </div>
    </div>
  )
}
