/**
 * Pure rendering helpers for the event log.
 *
 * They are kept outside EventLog.tsx so React Fast Refresh sees the component
 * file as component-only, while unit tests can still cover display ordering
 * and model-limit halt summaries.
 */

import type { EventLevel } from '../state/events'

export interface EventLogItem {
  t: number
  text: string
  level: EventLevel
}

/** Collapse whitespace so long backend explanations stay on one event row. */
function oneLine(text: string): string {
  return text.replace(/\s+/g, ' ').trim()
}

/** First sentence of a backend-provided explanation, preserving punctuation. */
export function firstSentence(text: string): string {
  const cleaned = oneLine(text)
  const match = cleaned.match(/^.*?(?:[.!?](?=\s|$)|$)/)
  return match?.[0] ?? cleaned
}

/**
 * Text displayed in the event log for one retained event.
 *
 * Model-limit halt events can be several sentences long because the full text
 * is shown in the persistent notice. The log keeps just "Halted: <first
 * sentence>" so older initiating events remain visible in the scrollback.
 */
export function eventLogText(text: string): string {
  const prefix = 'Halted: '
  if (!text.startsWith(prefix)) return text
  return `${prefix}${firstSentence(text.slice(prefix.length))}`
}

/** Newest-first events prepared for display. */
export function eventsForLog(events: readonly EventLogItem[]): EventLogItem[] {
  return [...events].reverse().map((event) => ({ ...event, text: eventLogText(event.text) }))
}
