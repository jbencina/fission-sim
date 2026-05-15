/**
 * TemperatureChart — real-time line chart of primary loop temperatures.
 *
 * Shows four series:
 *   - T_hot   (red-400)  — hot-leg coolant, core outlet
 *   - T_cold  (sky-400)  — cold-leg coolant, core inlet
 *   - T_avg   (slate-300) — average primary temperature (control reference)
 *   - T_fuel  (orange-400) — bulk fuel temperature
 *
 * All values are in Kelvin (K) as received from the backend.
 */

import { useMemo, type FC } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts'
import { useTelemetryStore } from '../state/telemetryStore'
import { toTemperaturePoints } from './chartData'
import {
  GRID_STROKE,
  TICK_FILL,
  AXIS_LABEL_FILL,
  TOOLTIP_WRAPPER_STYLE,
  X_AXIS_PROPS,
} from './chartTheme'

// ---------------------------------------------------------------------------
// TemperatureChart component
// ---------------------------------------------------------------------------

/**
 * TemperatureChart
 *
 * Plots hot-leg, cold-leg, average, and fuel temperatures for the last 60 s.
 */
const TemperatureChart: FC = () => {
  const history = useTelemetryStore((s) => s.history)

  const data = useMemo(() => toTemperaturePoints(history), [history])

  return (
    <div className="bg-slate-900/60 rounded-lg border border-slate-800 p-4 h-64 md:h-72 flex flex-col gap-2">
      <div>
        <h3 className="text-sm font-medium text-slate-200">Primary loop temperatures</h3>
        <p className="text-xs text-slate-400">
          Hot leg (core outlet), cold leg (core inlet), average (control reference), and bulk fuel temperature.
        </p>
      </div>

      {data.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-slate-500 text-sm">
          Waiting for telemetry…
        </div>
      ) : (
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 8, bottom: 20, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={GRID_STROKE} />
            <XAxis {...X_AXIS_PROPS} />
            <YAxis
              tick={{ fill: TICK_FILL, fontSize: 11 }}
              stroke={TICK_FILL}
              label={{
                value: 'K',
                angle: -90,
                position: 'insideLeft',
                fill: AXIS_LABEL_FILL,
                fontSize: 11,
              }}
              width={55}
            />
            <Tooltip wrapperStyle={TOOLTIP_WRAPPER_STYLE} />
            <Legend wrapperStyle={{ fontSize: 11, color: TICK_FILL }} />
            <Line
              type="monotone"
              dataKey="T_hot"
              name="T_hot (K)"
              stroke="#f87171" /* red-400 */
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="T_cold"
              name="T_cold (K)"
              stroke="#38bdf8" /* sky-400 */
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="T_avg"
              name="T_avg (K)"
              stroke="#cbd5e1" /* slate-300 */
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="T_fuel"
              name="T_fuel (K)"
              stroke="#fb923c" /* orange-400 */
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

export default TemperatureChart
