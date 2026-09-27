/**
 * ChartGrid — the six live trend charts (chartSpecs.ts).
 *
 * Two columns from `md` up, filling the height available to them in three
 * equal rows on wide screens; one column on phones, where each chart has a
 * fixed height and the page scrolls. With two columns only the bottom row
 * carries the time axis, since every chart shares the same window; with
 * one column every chart carries it.
 */

import type { FC } from 'react'
import { useMediaQuery } from '../ui/useMediaQuery'
import TimeSeriesChart from './TimeSeriesChart'
import { CHART_SPECS } from './chartSpecs'

const ChartGrid: FC = () => {
  const twoColumns = useMediaQuery('(min-width: 768px)')
  return (
    <div className="grid auto-rows-[15.5rem] grid-cols-1 gap-px bg-line md:grid-cols-2 lg:h-full lg:grid-rows-[repeat(3,minmax(12.5rem,1fr))]">
      {CHART_SPECS.map((spec, i) => (
        <TimeSeriesChart key={spec.id} spec={spec} timeAxis={!twoColumns || i >= CHART_SPECS.length - 2} />
      ))}
    </div>
  )
}

export default ChartGrid
