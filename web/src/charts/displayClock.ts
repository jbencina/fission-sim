/**
 * DisplayClock — the simulated time at the right edge of the charts.
 *
 * Telemetry arrives about 10 times a second. Moving the chart window only
 * when a frame arrives makes the traces jump a pixel or two ten times a
 * second, which reads as jitter. Instead the charts redraw on every display
 * refresh and place their right edge at a clock that runs continuously
 * between frames:
 *
 *   - While the simulation runs, the clock advances at `speed` simulated
 *     seconds per wall-clock second, one frame period behind the newest
 *     frame. Each new frame therefore arrives just before the clock reaches
 *     it, so the traces scroll steadily instead of stepping, and the clock
 *     never runs past the data.
 *   - Frame timing wobbles by a few milliseconds. Each redraw nudges the
 *     clock toward where the latest frame says it should be (exponential
 *     correction with time constant TAU_S) instead of jumping there.
 *   - While paused the rate is zero and the clock settles on the newest
 *     frame, so the traces end exactly at the right edge.
 *   - A reset (time moving backward) or a large gap snaps the clock.
 *
 * The class is pure: callers pass wall-clock time in, so it is unit tested
 * without timers.
 */

/** Wall-clock period between telemetry frames [s] (runtime.py `_DEFAULT_CADENCE_HZ`). */
export const FRAME_PERIOD_S = 0.1

/** Time constant of the correction toward the latest frame [s of wall time]. */
const TAU_S = 0.15

export class DisplayClock {
  private latestT: number | null = null
  private latestWallMs = 0
  private rate = 0
  private lag = 0
  private shown: number | null = null
  private lastTickMs: number | null = null

  /** Record a telemetry frame received at `wallMs` (performance.now()). */
  observe(t: number, running: boolean, speed: number, wallMs: number): void {
    const rolledBack = this.latestT !== null && t < this.latestT
    this.latestT = t
    this.latestWallMs = wallMs
    this.rate = running ? speed : 0
    this.lag = running ? FRAME_PERIOD_S * speed : 0
    if (this.shown === null || rolledBack) {
      this.shown = t - this.lag
    }
  }

  /**
   * Advance to wall-clock time `wallMs` and return the simulated time for
   * the charts' right edge, or null before the first frame.
   */
  tick(wallMs: number): number | null {
    if (this.latestT === null || this.shown === null) return null

    const dt = this.lastTickMs === null ? 0 : Math.max(0, (wallMs - this.lastTickMs) / 1000)
    this.lastTickMs = wallMs

    const sinceFrame = Math.max(0, (wallMs - this.latestWallMs) / 1000)
    const target = Math.min(this.latestT, this.latestT - this.lag + sinceFrame * this.rate)

    let shown = this.shown + this.rate * dt
    shown += (target - shown) * (1 - Math.exp(-dt / TAU_S))

    // Far off (a hidden tab resumed, a speed change mid-flight, a long stall):
    // jump rather than visibly racing to catch up.
    const snapDistance = Math.max(1, 3 * FRAME_PERIOD_S * Math.max(this.rate, 1))
    if (Math.abs(target - shown) > snapDistance) shown = target

    this.shown = Math.min(shown, this.latestT)
    return this.shown
  }
}
