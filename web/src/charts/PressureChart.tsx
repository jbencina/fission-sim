/**
 * PressureChart — real-time line chart of primary system pressure.
 *
 * Reads `P_primary_MPa` from the telemetry store. The pressurizer maintains
 * primary pressure around its setpoint (~15.5 MPa at nominal conditions).
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

interface PressurePoint {
  /** Relative time in seconds; 0 = newest. */
  t_rel: number
  /** Primary system pressure [MPa] */
  P_MPa: number
}

// ---------------------------------------------------------------------------
// PressureChart component
// ---------------------------------------------------------------------------

/**
 * PressureChart
 *
 * Displays primary loop pressure (in MPa) over the last 60 s.
 * Design setpoint is ~15.5 MPa.
 */
const PressureChart: FC = () => {
  const history = useTelemetryStore((s) => s.history)

  const data = useMemo<PressurePoint[]>(() => {
    if (history.length === 0) return []
    const latest = history[history.length - 1].t
    return history
      .filter((_, i) => i % 2 === 0 || i === history.length - 1)
      .map((frame) => ({
        t_rel: +(frame.t - latest).toFixed(2),
        P_MPa: +frame.P_primary_MPa.toFixed(4),
      }))
  }, [history.length]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="bg-slate-900/60 rounded-lg border border-slate-800 p-4 h-64 md:h-72 flex flex-col gap-2">
      <div>
        <h3 className="text-sm font-medium text-slate-200">Primary pressure</h3>
        <p className="text-xs text-slate-400">
          Pressurizer-set primary system pressure. Design: ~15.5 MPa.
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
                value: 'MPa',
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
              dataKey="P_MPa"
              name="Pressure (MPa)"
              stroke="#38bdf8" /* sky-400 */
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

export default PressureChart
