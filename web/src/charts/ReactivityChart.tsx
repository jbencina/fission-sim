/**
 * ReactivityChart — real-time line chart of reactivity components.
 *
 * Shows four series converted from dimensionless to pcm (× 1e5):
 *   - rho_rod       (amber-400) — control rod worth
 *   - rho_doppler   (red-400)   — Doppler (fuel temperature) feedback
 *   - rho_moderator (sky-400)   — moderator temperature feedback
 *   - rho_total     (slate-100, stroke-2) — net reactivity
 *
 * A reactor is exactly critical when rho_total = 0 pcm.
 * Negative values mean net shutdown reactivity is being added (power falling).
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

interface ReactivityPoint {
  /** Relative time in seconds; 0 = newest. */
  t_rel: number
  /** Rod reactivity worth [pcm] */
  rho_rod_pcm: number
  /** Doppler feedback reactivity [pcm] */
  rho_doppler_pcm: number
  /** Moderator temperature feedback reactivity [pcm] */
  rho_moderator_pcm: number
  /** Total (net) reactivity [pcm] */
  rho_total_pcm: number
}

// ---------------------------------------------------------------------------
// ReactivityChart component
// ---------------------------------------------------------------------------

/**
 * ReactivityChart
 *
 * Displays rod, Doppler, moderator, and total reactivity over the last 60 s.
 * Values are in pcm (percent milli-rho = dimensionless × 1e5).
 */
const ReactivityChart: FC = () => {
  const history = useTelemetryStore((s) => s.history)

  const data = useMemo<ReactivityPoint[]>(() => {
    if (history.length === 0) return []
    const latest = history[history.length - 1].t
    return history
      .filter((_, i) => i % 2 === 0 || i === history.length - 1)
      .map((frame) => ({
        t_rel: +(frame.t - latest).toFixed(2),
        // Convert dimensionless reactivity to pcm (× 1e5)
        rho_rod_pcm: +(frame.rho_rod * 1e5).toFixed(2),
        rho_doppler_pcm: +(frame.rho_doppler * 1e5).toFixed(2),
        rho_moderator_pcm: +(frame.rho_moderator * 1e5).toFixed(2),
        rho_total_pcm: +(frame.rho_total * 1e5).toFixed(2),
      }))
  }, [history.length]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="bg-slate-900/60 rounded-lg border border-slate-800 p-4 h-64 md:h-72 flex flex-col gap-2">
      <div>
        <h3 className="text-sm font-medium text-slate-200">Reactivity components</h3>
        <p className="text-xs text-slate-400">
          Rod, Doppler feedback, moderator feedback, and net — in pcm. Negative = inserting negative reactivity (power decreasing).
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
                value: 'pcm',
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
              dataKey="rho_rod_pcm"
              name="ρ_rod (pcm)"
              stroke="#fbbf24" /* amber-400 */
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="rho_doppler_pcm"
              name="ρ_Doppler (pcm)"
              stroke="#f87171" /* red-400 */
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="rho_moderator_pcm"
              name="ρ_mod (pcm)"
              stroke="#38bdf8" /* sky-400 */
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="rho_total_pcm"
              name="ρ_total (pcm)"
              stroke="#f1f5f9" /* slate-100 */
              strokeWidth={2}
              dot={false}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}

export default ReactivityChart
