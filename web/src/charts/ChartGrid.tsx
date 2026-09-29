/**
 * ChartGrid — the selectable live trend charts (chartSpecs.ts).
 *
 * Two columns from `md` up; one column on phones. Rows keep the old chart
 * minimum height instead of squeezing five rows into the viewport, so the
 * chart column scrolls on wide screens. Every chart carries its own readable
 * time axis because a bottom-row-only axis would scroll off-screen.
 */

import { type FC, useState } from 'react'
import { HelpTip } from '../ui/InfoTip'
import {
  CHART_WINDOW_OPTIONS,
  DEFAULT_CHART_WINDOW_S,
  type ChartWindowOption,
} from './chartData'
import TimeSeriesChart from './TimeSeriesChart'
import { CHART_VIEWS, DEFAULT_CHART_VIEW, chartSpecsForView, type ChartViewId } from './chartSpecs'

const ChartGrid: FC = () => {
  const [view, setView] = useState<ChartViewId>(DEFAULT_CHART_VIEW)
  const [windowSeconds, setWindowSeconds] = useState<number>(DEFAULT_CHART_WINDOW_S)
  const specs = chartSpecsForView(view)

  return (
    <div className="min-w-0">
      <div className="sticky top-0 z-10 flex flex-col gap-3 border-b border-line-strong bg-canvas px-4 py-3 md:flex-row md:items-center md:justify-between">
        <div className="min-w-0">
          <h2 className="eyebrow !text-ink">Trends</h2>
          <p className="mt-1 text-[12px] text-ink-2">
            {specs.length} charts · {CHART_WINDOW_OPTIONS.find((option) => option.seconds === windowSeconds)?.label}
            {' '}simulated-time window
          </p>
        </div>

        <div className="flex flex-wrap gap-3">
          <HelpTip
            title="Chart view"
            tip="Choose which trends share the chart column. Reactor keeps core, reactivity, coolant, pressure, and rod plots together; Secondary keeps power, Tavg/Tref, steam pressure, SG level, flows, and electrical output together."
          >
            {(tipId) => (
              <div role="group" aria-label="Chart view" aria-describedby={tipId} className="seg">
                {CHART_VIEWS.map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    aria-pressed={view === option.id}
                    onClick={() => setView(option.id)}
                    className={`h-8 px-3 text-[12px] ${view === option.id ? 'seg-on' : 'hover:bg-surface-2'}`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            )}
          </HelpTip>

          <HelpTip
            title="Chart window"
            tip="Choose how much simulated time each chart shows. The page keeps enough time-based history for the 15-minute window at any speed; changing speed does not change what one minute means on the x axis."
            align="end"
          >
            {(tipId) => (
              <div role="group" aria-label="Chart time window" aria-describedby={tipId} className="seg">
                {CHART_WINDOW_OPTIONS.map((option: ChartWindowOption) => (
                  <button
                    key={option.seconds}
                    type="button"
                    aria-pressed={windowSeconds === option.seconds}
                    onClick={() => setWindowSeconds(option.seconds)}
                    className={`h-8 px-3 text-[12px] ${
                      windowSeconds === option.seconds ? 'seg-on' : 'hover:bg-surface-2'
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            )}
          </HelpTip>
        </div>
      </div>

      <div className="grid auto-rows-[15.5rem] grid-cols-1 gap-px bg-line md:grid-cols-2">
        {specs.map((spec) => (
          <TimeSeriesChart key={`${spec.id}-${windowSeconds}`} spec={spec} timeAxis windowSeconds={windowSeconds} />
        ))}
      </div>
    </div>
  )
}

export default ChartGrid
