/**
 * ChartGrid — the ten live trend charts (chartSpecs.ts).
 *
 * Two columns from `md` up; one column on phones. Rows keep the old chart
 * minimum height instead of squeezing five rows into the viewport, so the
 * chart column scrolls on wide screens. Every chart carries its own readable
 * time axis because a bottom-row-only axis would scroll off-screen.
 */

import type { FC } from 'react'
import TimeSeriesChart from './TimeSeriesChart'
import { CHART_SPECS } from './chartSpecs'

const ChartGrid: FC = () => {
  return (
    <div className="grid auto-rows-[15.5rem] grid-cols-1 gap-px bg-line md:grid-cols-2">
      {CHART_SPECS.map((spec) => (
        <TimeSeriesChart key={spec.id} spec={spec} timeAxis />
      ))}
    </div>
  )
}

export default ChartGrid
