/**
 * One requestAnimationFrame loop shared by every chart.
 *
 * Each chart registers a callback; on every display refresh the loop
 * advances the shared DisplayClock and hands each callback the simulated
 * time for the charts' right edge, so all charts scroll in lockstep. The
 * clock is fed from the telemetry store as frames arrive. The loop runs only
 * while at least one chart is mounted, and the browser pauses it in
 * background tabs.
 *
 * The clock and its store subscription outlive the loop: a theme change
 * remounts every chart, and restarting the clock from scratch then would
 * jump the charts back by up to one frame period.
 */

import { useTelemetryStore } from '../state/telemetryStore'
import { DisplayClock } from './displayClock'

/** Called once per display refresh with the right-edge time (null before data). */
export type TickCallback = (now: number | null, wallMs: number) => void

const clock = new DisplayClock()
const callbacks = new Set<TickCallback>()
let rafId: number | null = null
let feeding = false

function feedClock(): void {
  if (feeding) return
  feeding = true
  const seed = useTelemetryStore.getState().latest
  if (seed) clock.observe(seed.t, seed.running, seed.speed, performance.now())
  useTelemetryStore.subscribe((state, prev) => {
    const frame = state.latest
    if (frame && frame !== prev.latest) {
      clock.observe(frame.t, frame.running, frame.speed, performance.now())
    }
  })
}

function loop(wallMs: number): void {
  const now = clock.tick(wallMs)
  callbacks.forEach((cb) => cb(now, wallMs))
  rafId = requestAnimationFrame(loop)
}

function start(): void {
  feedClock()
  rafId = requestAnimationFrame(loop)
}

function stop(): void {
  if (rafId !== null) cancelAnimationFrame(rafId)
  rafId = null
}

/** Register a per-refresh callback; returns the function that removes it. */
export function subscribeTick(cb: TickCallback): () => void {
  callbacks.add(cb)
  if (callbacks.size === 1) start()
  return () => {
    callbacks.delete(cb)
    if (callbacks.size === 0) stop()
  }
}
