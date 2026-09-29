/**
 * TimeSeriesChart — one live trend, drawn on canvas by uPlot.
 *
 * Smoothness comes from three things working together:
 *   - The x window [now − 60 s, now] moves on every display refresh, driven
 *     by the shared ticker (ticker.ts / displayClock.ts), not only when a
 *     telemetry frame arrives.
 *   - The y range is sticky and eased (autoRange.ts).
 *   - Nothing here re-renders React per frame: new data, scales and legend
 *     values are pushed to uPlot and the DOM imperatively.
 *
 * Grid lines stay fixed at 10 s intervals relative to "now" while the traces
 * slide under them. Hovering shows a crosshair synchronised across every
 * chart, and the legend switches from the latest values to the values under
 * the cursor. The time axis is labelled only when `timeAxis` is set, so a
 * grid of charts can label its bottom row alone.
 */

import { type FC, useEffect, useId, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { useTelemetryStore } from '../state/telemetryStore'
import { InfoTip } from '../ui/InfoTip'
import { MINUS, formatNumber } from '../ui/format'
import { AutoRange, niceStep, stepDecimals, visibleExtent } from './autoRange'
import { CHART_WINDOW_S, toColumns } from './chartData'
import type { ChartSpec } from './chartSpecs'
import { subscribeTick } from './ticker'

const FONT = '300 10.5px "IBM Plex Mono", ui-monospace, monospace'
const Y_AXIS_SIZE = 48
const X_AXIS_SIZE = 22
const X_AXIS_HIDDEN_SIZE = 6
const SYNC_KEY = 'plant-trends'

function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

/** Axis/cursor label for a time relative to now, e.g. "−30s" or "now". */
function relativeLabel(dt: number, decimals = 0): string {
  const r = +dt.toFixed(decimals)
  if (r === 0) return 'now'
  return `${r < 0 ? MINUS : ''}${Math.abs(r).toFixed(decimals)}s`
}

function setText(el: HTMLElement | null | undefined, text: string): void {
  if (el && el.textContent !== text) el.textContent = text
}

const Swatch: FC<{ color: string; dashed: boolean }> = ({ color, dashed }) => (
  <span
    aria-hidden="true"
    className="inline-block h-px w-3 shrink-0"
    style={
      dashed
        ? {
            backgroundImage: `linear-gradient(90deg, var(${color}) 55%, transparent 0)`,
            backgroundSize: '4px 1px',
          }
        : { background: `var(${color})` }
    }
  />
)

const TimeSeriesChart: FC<{ spec: ChartSpec; timeAxis: boolean }> = ({ spec, timeAxis }) => {
  const empty = useTelemetryStore((s) => s.history.length === 0)
  const titleId = useId()
  const plotRef = useRef<HTMLDivElement>(null)
  const valueRefs = useRef<(HTMLSpanElement | null)[]>([])
  const cursorRef = useRef<HTMLSpanElement>(null)
  // Outlives chart re-creation (the axis toggling), so the range does not jump.
  const rangeRef = useRef<AutoRange | null>(null)
  rangeRef.current ??= new AutoRange(spec.range)

  useEffect(() => {
    const el = plotRef.current
    const range = rangeRef.current
    if (!el || !range) return

    const ink3 = cssVar('--ink-3')
    const line = cssVar('--line')
    const lineStrong = cssVar('--line-strong')
    const canvas = cssVar('--canvas')
    const colors = spec.series.map((s) => cssVar(s.color))
    const extractors = spec.series.map((s) => s.value)

    const store = useTelemetryStore.getState()
    let data = toColumns(store.history, extractors)
    let pending: number[][] | null = null
    let latestFrame = store.latest
    let now: number | null = null
    let yRange: [number, number] | null = null
    let lastWall: number | null = null
    let legendDirty = true

    const writeLegend = (u: uPlot) => {
      const idx = u.cursor.idx
      const hovering = idx != null && (u.cursor.left ?? -1) >= 0 && now !== null
      spec.series.forEach((s, i) => {
        const v = hovering
          ? (u.data[i + 1]?.[idx] as number | undefined)
          : latestFrame
            ? s.value(latestFrame)
            : null
        setText(valueRefs.current[i], formatNumber(v, spec.decimals))
      })
      setText(
        cursorRef.current,
        hovering ? relativeLabel((u.data[0][idx] as number) - (now as number), 1) : '',
      )
      legendDirty = false
    }

    const rect = el.getBoundingClientRect()
    const opts: uPlot.Options = {
      width: Math.max(1, Math.floor(rect.width)),
      height: Math.max(1, Math.floor(rect.height)),
      pxAlign: false,
      padding: [6, 12, 0, 0],
      legend: { show: false },
      select: { show: false, left: 0, top: 0, width: 0, height: 0 },
      cursor: {
        y: false,
        sync: { key: SYNC_KEY },
        drag: { x: false, y: false, setScale: false },
        points: {
          size: 7,
          width: 1,
          fill: () => canvas,
          stroke: (_u, i) => colors[i - 1] ?? ink3,
        },
      },
      scales: {
        x: { time: false, auto: false, range: (_u, min, max) => [min, max] },
        y: { auto: false, range: (_u, min, max) => [min, max] },
      },
      axes: [
        {
          stroke: ink3,
          font: FONT,
          size: timeAxis ? X_AXIS_SIZE : X_AXIS_HIDDEN_SIZE,
          gap: 4,
          grid: { show: false },
          ticks: { show: false },
          splits: (u, _i, _min, max) => {
            const step = u.bbox.width / uPlot.pxRatio < 340 ? 20 : 10
            const out: number[] = []
            for (let r = -CHART_WINDOW_S; r <= 0; r += step) out.push(max + r)
            return out
          },
          values: (u, splits) =>
            timeAxis ? splits.map((v) => relativeLabel(v - (u.scales.x.max ?? v))) : splits.map(() => ''),
        },
        {
          stroke: ink3,
          font: FONT,
          size: Y_AXIS_SIZE,
          gap: 6,
          ticks: { show: false },
          grid: { stroke: line, width: 1 },
          splits: (u, _i, min, max) => {
            const rows = Math.round(u.bbox.height / uPlot.pxRatio / 38)
            const step = niceStep(max - min, Math.min(6, Math.max(3, rows)))
            const out: number[] = []
            for (let v = Math.ceil(min / step - 1e-9) * step; v <= max + step * 1e-9; v += step) {
              out.push(+v.toFixed(stepDecimals(step) + 2))
            }
            return out
          },
          // The bottom grid line keeps its label only if it clears the time axis.
          values: (u, splits) => {
            const step = splits.length > 1 ? splits[1] - splits[0] : 1
            const bottom = u.bbox.top + u.bbox.height
            return splits.map((v) =>
              bottom - u.valToPos(v, 'y', true) < 9 * uPlot.pxRatio
                ? null
                : formatNumber(v, stepDecimals(step)),
            )
          },
        },
      ],
      series: [
        {},
        ...spec.series.map((s, i) => ({
          label: s.label,
          stroke: colors[i],
          width: s.width ?? 1.1,
          dash: s.dash,
          points: { show: false },
        })),
      ],
      hooks: {
        drawAxes: spec.zeroLine
          ? [
              (u: uPlot) => {
                const y = u.valToPos(0, 'y', true)
                const { left, top, width, height } = u.bbox
                if (y < top || y > top + height) return
                const ctx = u.ctx
                ctx.save()
                ctx.strokeStyle = lineStrong
                ctx.lineWidth = uPlot.pxRatio
                ctx.beginPath()
                ctx.moveTo(left, y)
                ctx.lineTo(left + width, y)
                ctx.stroke()
                ctx.restore()
              },
            ]
          : [],
        setCursor: [(u: uPlot) => writeLegend(u)],
      },
    }

    const u = new uPlot(opts, data as uPlot.AlignedData, el)
    writeLegend(u)

    const unsubscribeStore = useTelemetryStore.subscribe((s, prev) => {
      if (s.history !== prev.history) pending = toColumns(s.history, extractors)
      if (s.latest !== prev.latest) {
        latestFrame = s.latest
        legendDirty = true
      }
    })

    const resize = new ResizeObserver(() => {
      const r = el.getBoundingClientRect()
      u.setSize({ width: Math.max(1, Math.floor(r.width)), height: Math.max(1, Math.floor(r.height)) })
    })
    resize.observe(el)

    const unsubscribeTick = subscribeTick((t, wallMs) => {
      const dt = lastWall === null ? 0 : (wallMs - lastWall) / 1000
      lastWall = wallMs
      if (t === null) return

      const columns = pending ?? data
      const next = range.update(visibleExtent(columns, t - CHART_WINDOW_S), dt)
      const moved =
        t !== now ||
        next?.[0] !== yRange?.[0] ||
        next?.[1] !== yRange?.[1]

      if (pending !== null || moved) {
        now = t
        yRange = next
        u.batch(() => {
          if (pending !== null) {
            u.setData(pending as uPlot.AlignedData, false)
            data = pending
            pending = null
          }
          u.setScale('x', { min: t - CHART_WINDOW_S, max: t })
          if (next) u.setScale('y', { min: next[0], max: next[1] })
        })
      }
      if (legendDirty) writeLegend(u)
    })

    return () => {
      unsubscribeTick()
      unsubscribeStore()
      resize.disconnect()
      u.destroy()
    }
  }, [spec, timeAxis])

  const primary = spec.series.find((s) => s.width !== undefined && s.dash === undefined) ?? spec.series[0]
  const primaryIndex = spec.series.indexOf(primary)

  return (
    <section aria-labelledby={titleId} className="flex min-h-0 min-w-0 flex-col bg-canvas px-4 pb-1.5 pt-3">
      <div className="flex items-baseline gap-2">
        <h3 id={titleId} className="eyebrow truncate !text-ink">
          {spec.title}
        </h3>
        <span className="shrink-0 text-[11.5px] text-ink-2">{spec.unit}</span>
        <InfoTip title={spec.title} body={spec.description} className="ml-0.5 self-center" />
        <span ref={cursorRef} aria-hidden="true" className="ml-auto shrink-0 font-mono text-[11px] text-ink-3" />
      </div>

      {/*
        Label and value per series on one row. The row keeps the same height
        on every chart, so plots in a row stay aligned as values change width.
      */}
      <ul className="mt-1.5 flex min-w-0 flex-wrap gap-x-4 gap-y-0.5">
        {spec.series.map((s, i) => (
          <li
            key={s.label}
            className="flex min-w-0 max-w-full flex-wrap items-center gap-x-1.5 gap-y-0 text-[11.5px] leading-tight text-ink-2"
          >
            <Swatch color={s.color} dashed={s.dash !== undefined} />
            <span className="min-w-0 break-words">{s.label}</span>
            <span
              ref={(node) => {
                valueRefs.current[i] = node
              }}
              className={`font-mono tabular-nums ${i === primaryIndex ? 'text-ink' : 'text-ink-2'}`}
            />
          </li>
        ))}
      </ul>

      <div className="relative mt-1 min-h-0 flex-1">
        {/* uPlot owns this node's children; React never renders into it. */}
        <div
          ref={plotRef}
          role="img"
          aria-label={`${spec.title} over the last ${CHART_WINDOW_S} seconds`}
          className="absolute inset-0"
        />
        {empty && (
          <div className="pointer-events-none absolute inset-0 grid place-items-center text-[12px] text-ink-3">
            Waiting for telemetry…
          </div>
        )}
      </div>
    </section>
  )
}

export default TimeSeriesChart
