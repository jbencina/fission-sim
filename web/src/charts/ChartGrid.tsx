/**
 * ChartGrid — vertical stack of all four real-time telemetry charts.
 *
 * Composed of:
 *   - PowerChart       — thermal power in MW
 *   - TemperatureChart — primary loop temperatures in K
 *   - PressureChart    — primary system pressure in MPa
 *   - ReactivityChart  — reactivity components in pcm
 *
 * Drop this component into AppShell's charts column to replace the
 * feat-009 placeholder.
 */

import type { FC } from 'react'
import PowerChart from './PowerChart'
import TemperatureChart from './TemperatureChart'
import PressureChart from './PressureChart'
import ReactivityChart from './ReactivityChart'

/**
 * ChartGrid
 *
 * Renders the four real-time charts in a vertical stack with consistent
 * gap-4 spacing. Each chart manages its own data subscription and
 * ResponsiveContainer sizing.
 */
const ChartGrid: FC = () => (
  <div className="flex flex-col gap-4 w-full">
    <PowerChart />
    <TemperatureChart />
    <PressureChart />
    <ReactivityChart />
  </div>
)

export default ChartGrid
