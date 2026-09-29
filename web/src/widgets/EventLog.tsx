/**
 * EventLog — the retained plant-event history, newest first, under a "Now"
 * row with the current clock. Events come from the telemetry store
 * (state/events.ts).
 */

import type { FC } from 'react'
import type { EventLevel } from '../state/events'
import { useTelemetryStore } from '../state/telemetryStore'
import { formatClock } from '../ui/format'
import { eventsForLog } from './EventLog.helpers'

const LEVEL_CLASS: Record<EventLevel, string> = {
  info: 'text-ink-2',
  warn: 'text-warn-ink',
  alarm: 'text-danger-ink',
}

const EventLog: FC = () => {
  const events = useTelemetryStore((s) => s.events)
  const t = useTelemetryStore((s) => s.latest?.t ?? null)
  const shown = eventsForLog(events)

  return (
    <section aria-label="Events" className="px-4 pb-3 pt-2.5 sm:px-5">
      <h2 className="eyebrow mb-1.5">Events</h2>
      <ol className="scroll-column max-h-[12rem] overflow-y-auto pr-1 text-[12px]">
        <li className="grid grid-cols-[62px_1fr] gap-2.5 py-1 text-ink">
          <span className="font-mono text-[11.5px] text-ink-3">{formatClock(t)}</span>
          <span>Now</span>
        </li>
        {shown.map((e, i) => (
          <li key={`${e.t}-${i}`} className={`grid grid-cols-[62px_1fr] gap-2.5 py-1 ${LEVEL_CLASS[e.level]}`}>
            <span className={`font-mono text-[11.5px] ${e.level === 'info' ? 'text-ink-3' : ''}`}>
              {formatClock(e.t)}
            </span>
            <span>{e.text}</span>
          </li>
        ))}
        {shown.length === 0 && <li className="py-1 text-ink-3">No events yet.</li>}
      </ol>
    </section>
  )
}

export default EventLog
