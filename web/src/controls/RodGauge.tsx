/**
 * RodGauge — a ring gauge for the control bank: 41 ticks over a 270° arc,
 * a white dot at the bank's position, an amber tick at the active command or
 * automatic demand, and a grey tick at the design position (50 %). Display
 * only; the range input in ControlPanel is the manual control.
 */

import type { FC } from 'react'
import { formatNumber } from '../ui/format'

const CX = 62
const CY = 62
const R = 52
const START = -225
const SWEEP = 270

/**
 * Convert a gauge angle and radius to SVG coordinates.
 *
 * Parameters
 * ----------
 * deg:
 *   Gauge angle [degrees].
 * r:
 *   Radius from the gauge center [SVG px].
 *
 * Returns
 * -------
 * [number, number]
 *   The x/y coordinates [SVG px].
 */
function point(deg: number, r: number): [number, number] {
  const a = (deg * Math.PI) / 180
  return [CX + r * Math.cos(a), CY + r * Math.sin(a)]
}

/**
 * Ring gauge showing actual bank position and active command/demand.
 *
 * Parameters
 * ----------
 * position:
 *   Actual control-bank position [fraction withdrawn], or null before the
 *   first frame arrives.
 * command:
 *   Active command/demand tick [fraction withdrawn].
 */
const RodGauge: FC<{ position: number | null; command: number }> = ({ position, command }) => {
  const pos = position === null ? null : Math.min(1, Math.max(0, position))
  const cmd = Math.min(1, Math.max(0, command))
  const [dx1, dy1] = point(START + SWEEP * 0.5, R + 6)
  const [dx2, dy2] = point(START + SWEEP * 0.5, R + 1)
  const [cx1, cy1] = point(START + SWEEP * cmd, R + 2)
  const [cx2, cy2] = point(START + SWEEP * cmd, R - 13)
  const dot = pos === null ? null : point(START + SWEEP * pos, R - 19)

  return (
    <div className="relative h-[124px] w-[124px] shrink-0">
      <svg viewBox="0 0 124 124" aria-hidden="true" className="block h-full w-full">
        {Array.from({ length: 41 }, (_, i) => {
          const d = START + (SWEEP * i) / 40
          const big = i % 10 === 0
          const [x1, y1] = point(d, R)
          const [x2, y2] = point(d, R - (big ? 8 : 3.5))
          return (
            <line
              key={i}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke={big ? 'var(--ink)' : 'var(--ink-3)'}
              strokeWidth="1"
            />
          )
        })}
        <line x1={dx1} y1={dy1} x2={dx2} y2={dy2} stroke="var(--ink-2)" strokeWidth="1.5" />
        <line x1={cx1} y1={cy1} x2={cx2} y2={cy2} stroke="var(--warn)" strokeWidth="2" />
        {dot && <circle cx={dot[0]} cy={dot[1]} r="3" fill="var(--ink)" />}
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">
        <div>
          <div className="font-mono text-[18px] font-light leading-none text-ink">
            {formatNumber(pos === null ? null : pos * 100, 0)}
          </div>
          <div className="mt-1 text-[8.5px] uppercase tracking-[0.1em] text-ink-2">% withdrawn</div>
        </div>
      </div>
    </div>
  )
}

export default RodGauge
