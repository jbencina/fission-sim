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
  /** Optional qualifier shown on a second line below the label. */
  secondary?: string
  band?: Band
  /** Whether to append tooltip.units after the value. */
  showUnits?: boolean
  /** Stack the value below the label for long readouts that need full width. */
  stackValue?: boolean
  /** Popover alignment; 'end' opens leftward from the right edge. */
  align?: 'start' | 'end'
  'data-testid'?: string
}

export const InfoRow: FC<ReadoutProps> = ({
  tooltip,
  value,
  secondary,
  band = 'green',
  showUnits = true,
  stackValue = false,
  align = 'start',
  'data-testid': testId,
}) => {
  const ref = useRef<HTMLDivElement>(null)
  const valueBlock = (
    <div className="flex shrink-0 items-baseline justify-end gap-2 whitespace-nowrap tabular-nums">
      <span className={`font-mono text-[13px] ${ROW_BAND[band]}`}>
        <span data-testid={testId ? `${testId}-value` : undefined}>{value}</span>
        {showUnits && tooltip.units && value !== EMPTY_VALUE && (
          <span className="ml-1 font-sans text-[11px] text-ink-2">{tooltip.units}</span>
        )}
      </span>
    </div>
  )

  return (
    <div
      ref={ref}
      data-testid={testId}
      className={
        stackValue
          ? 'grid min-h-[50px] grid-cols-1 gap-1 border-t border-line py-1.5 first:border-t-0'
          : 'grid min-h-[40px] grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-t border-line py-1.5 first:border-t-0'
      }
    >
      <div className="min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="whitespace-nowrap text-[12.5px] leading-snug text-ink-2">{tooltip.title}</span>
          <InfoTip title={tooltip.title} body={tooltip.body} area={ref} align={align} />
        </div>
        {secondary && <div className="mt-0.5 text-[10.5px] leading-tight text-ink-3">{secondary}</div>}
      </div>
      {valueBlock}
    </div>
  )
}
