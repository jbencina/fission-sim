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
  /** Original full event text, used as an optional tooltip/title. */
  fullText?: string
}

interface HaltSummaryRule {
  startsWith: string
  summary: string
}

/** Prefix events.ts adds to model-limit halt messages. */
const HALT_PREFIX = 'Halted: '

/** Maximum summary length before the helper adds an ellipsis. */
export const EVENT_SUMMARY_MAX_CHARS = 72

/** Short summaries for known backend model-limit explanations. */
const HALT_SUMMARY_RULES: readonly HaltSummaryRule[] = [
  {
    startsWith: 'Steam-generator collapsed liquid fraction fell below',
    summary: 'Halted: SG tubes uncovered — see the notice above',
  },
  {
    startsWith: 'Steam-generator collapsed liquid fraction rose above',
    summary: 'Halted: SG overfill — see the notice above',
  },
  {
    startsWith: 'Steam pressure fell',
    summary: 'Halted: steam pressure model limit — see the notice above',
  },
  {
    startsWith: 'Steam pressure rose',
    summary: 'Halted: steam pressure model limit — see the notice above',
  },
  {
    startsWith: 'Hot-leg water reached its boiling point',
    summary: 'Halted: primary boiling limit — see the notice above',
  },
  {
    startsWith: 'Simulation error:',
    summary: 'Halted: simulation error — see the notice above',
  },
]

/** Collapse whitespace so long backend explanations stay on one event row. */
function oneLine(text: string): string {
  return text.replace(/\s+/g, ' ').trim()
}

/** Bounded single-line text with a trailing ellipsis when it is too long. */
export function truncateWithEllipsis(text: string, maxChars = EVENT_SUMMARY_MAX_CHARS): string {
  const cleaned = oneLine(text)
  if (cleaned.length <= maxChars) return cleaned
  return `${cleaned.slice(0, Math.max(0, maxChars - 1)).trimEnd()}…`
}

/** One-line halt summary; the full explanation remains in ModelLimitNotice. */
export function haltSummary(explanation: string): string {
  const cleaned = oneLine(explanation)
  const rule = HALT_SUMMARY_RULES.find((candidate) => cleaned.startsWith(candidate.startsWith))
  return truncateWithEllipsis(rule?.summary ?? 'Halted at a model limit — see the notice above')
}

/**
 * Text displayed in the event log for one retained event.
 *
 * Model-limit halt events can be several sentences long because the full text
 * is shown in the persistent notice. The log keeps a bounded one-line summary
 * so older initiating events remain visible in the scrollback.
 */
export function eventLogText(text: string): string {
  if (!text.startsWith(HALT_PREFIX)) return text
  return haltSummary(text.slice(HALT_PREFIX.length))
}

/** Newest-first events prepared for display. */
export function eventsForLog(events: readonly EventLogItem[]): EventLogItem[] {
  return [...events].reverse().map((event) => ({ ...event, fullText: event.text, text: eventLogText(event.text) }))
}
