/**
 * PowerChart — real-time line chart of reactor thermal power.
 *
 * Reads the rolling history from the telemetry store and plots the last 60 s.
 * Power is converted from raw Watts to MW for a human-readable scale.
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
import {
  GRID_STROKE,
  TICK_FILL,
  AXIS_LABEL_FILL,
  TOOLTIP_WRAPPER_STYLE,
  X_AXIS_PROPS,
} from './chartTheme'

// ---------------------------------------------------------------------------
// Chart data shape
// ---------------------------------------------------------------------------

interface PowerPoint {
  /** Relative time in seconds; 0 = newest, -60 = oldest in window. */
  t_rel: number
  /** Thermal power in MW (raw Watts / 1e6). */
  power_MW: number
}

// ---------------------------------------------------------------------------
// PowerChart component
// ---------------------------------------------------------------------------

/**
 * PowerChart
 *
 * Displays reactor thermal power (in MW) over the last 60 s.
 * Reads `history` from the global telemetry store; transforms with useMemo
 * so re-renders only trigger when new frames arrive.
 */
const PowerChart: FC = () => {
  const history = useTelemetryStore((s) => s.history)

  /** Derive chart-ready points, recalculated only when history length changes. */
  const data = useMemo<PowerPoint[]>(() => {
    if (history.length === 0) return []
    const latest = history[history.length - 1].t
    // Sample every other frame to reduce render load at 10 Hz (still 5 Hz resolution)
    return history
      .filter((_, i) => i % 2 === 0 || i === history.length - 1)
      .map((frame) => ({
        t_rel: +(frame.t - latest).toFixed(2),
        power_MW: +(frame.power_thermal / 1e6).toFixed(3),
      }))
  }, [history.length]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="bg-slate-900/60 rounded-lg border border-slate-800 p-4 h-64 md:h-72 flex flex-col gap-2">
      <div>
        <h3 className="text-sm font-medium text-slate-200">Thermal power</h3>
        <p className="text-xs text-slate-400">
          Reactor core thermal output. Design power is ~3000 MW.
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
                value: 'MW',
                angle: -90,
                position: 'insideLeft',
                fill: AXIS_LABEL_FILL,
                fontSize: 11,
              }}
              width={50}
            />
            <Tooltip wrapperStyle={TOOLTIP_WRAPPER_STYLE} />
            <Legend wrapperStyle={{ fontSize: 11, color: TICK_FILL }} />
            <Line
              type="monotone"
              dataKey="power_MW"
              name="Power (MW)"
              stroke="#fbbf24" /* amber-400 */
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

export default PowerChart
