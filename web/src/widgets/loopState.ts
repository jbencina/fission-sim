/**
 * One-line description of the primary loop for the schematic's title:
 * the reactor's criticality and whether the loop is heating up, cooling or
 * steady. Pure, so it is unit tested directly.
 */

import type { Frame } from '../types/telemetry'

/** Fraction by which core power may differ from SG heat and still count as steady. */
const STEADY_BAND = 0.02

/** Word for the sign of the displayed (one-decimal) reactivity in pcm. */
export function criticalityWord(pcm: number): string {
  if (Math.abs(pcm) < 0.05) return 'critical'
  return pcm > 0 ? 'supercritical' : 'subcritical'
}

/** e.g. "subcritical, cooling"; "waiting for telemetry" before the first frame. */
export function describeLoop(frame: Frame | null): string {
  if (frame === null) return 'waiting for telemetry'
  const made = frame.power_thermal
  const removed = frame.Q_sg
  const scale = Math.max(Math.abs(made), Math.abs(removed), 1)
  const diff = (made - removed) / scale
  const trend = diff > STEADY_BAND ? 'heating up' : diff < -STEADY_BAND ? 'cooling' : 'steady'
  return `${criticalityWord(frame.rho_total * 1e5)}, ${trend}`
}
