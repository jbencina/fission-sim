/**
 * Readouts — the status panel's building block: a label / value row that
 * carries its explanation (tooltips.ts) and, for some readouts, an alert
 * band (thresholds.ts) that colours the value amber or red.
 */

import { type FC, useRef } from 'react'
import { InfoTip } from '../ui/InfoTip'
import { EMPTY_VALUE } from '../ui/format'
import type { TooltipEntry } from './tooltips'
import type { Band } from './thresholds'

const ROW_BAND: Record<Band, string> = {
  green: 'text-ink',
  amber: 'text-warn-ink',
  red: 'text-danger-ink',
}

export interface ReadoutProps {
  tooltip: TooltipEntry
  /** Formatted value, e.g. "3,000.0" or "—". */
  value: string
  /** Optional annotation shown before the value, e.g. "309.9 °C". */
  secondary?: string
  band?: Band
  /** Popover alignment; 'end' opens leftward from the right edge. */
  align?: 'start' | 'end'
  'data-testid'?: string
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
      className="grid min-h-[36px] grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-t border-line py-1 first:border-t-0"
    >
      <div className="flex min-w-0 items-center gap-1.5 overflow-hidden">
        <span className="truncate text-[12.5px] leading-snug text-ink-2">{tooltip.title}</span>
        <InfoTip title={tooltip.title} body={tooltip.body} area={ref} align={align} />
      </div>
      <div className="flex shrink-0 items-baseline gap-2 whitespace-nowrap tabular-nums">
        {secondary && <span className="text-[10.5px] text-ink-3 lg:hidden xl:inline">{secondary}</span>}
        <span className={`font-mono text-[13px] ${ROW_BAND[band]}`}>
          <span data-testid={testId ? `${testId}-value` : undefined}>{value}</span>
          {tooltip.units && value !== EMPTY_VALUE && (
            <span className="ml-1 font-sans text-[11px] text-ink-2">{tooltip.units}</span>
          )}
        </span>
      </div>
    </div>
  )
}
