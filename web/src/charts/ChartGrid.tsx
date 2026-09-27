/**
 * ChartGrid — the six live trend charts (chartSpecs.ts).
 *
 * Two columns on wide screens, filling the height available to them in
 * three equal rows; one column on narrow screens, where each chart has a
 * fixed height and the page scrolls.
 */

import type { FC } from 'react'
import TimeSeriesChart from './TimeSeriesChart'
import { CHART_SPECS } from './chartSpecs'

const ChartGrid: FC = () => (
  <div className="grid auto-rows-[15.5rem] grid-cols-1 gap-3 md:grid-cols-2 lg:h-full lg:grid-rows-[repeat(3,minmax(12.5rem,1fr))]">
    {CHART_SPECS.map((spec) => (
      <TimeSeriesChart key={spec.id} spec={spec} />
    ))}
  </div>
)

export default ChartGrid
