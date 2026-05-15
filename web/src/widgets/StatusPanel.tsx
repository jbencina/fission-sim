/**
 * StatusPanel — sidebar grid of live telemetry status tiles.
 *
 * Reads `latest` from the Zustand telemetry store and renders a 2-column
 * grid of StatusTile components. Each tile shows a formatted value and an
 * educational tooltip explaining the quantity in plain language.
 *
 * When `latest` is null (no data yet received), every tile shows "—".
 *
 * Tiles rendered (13 total, all with tooltips ≥40 chars):
 *   power_thermal, T_hot, T_cold, T_avg, T_fuel, P_primary_MPa,
 *   rod_position, rod_command, Q_sg, rho_total, sim_time, speed,
 *   scrammed, running.
 *
 * @module StatusPanel
 */

import type { FC } from 'react'
import { useTelemetryStore } from '../state/telemetryStore'
import type { Frame } from '../types/telemetry'
import StatusTile from './StatusTile'
import { TOOLTIPS } from './tooltips'
import { getBand } from './thresholds'

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

/**
 * Format a Kelvin temperature as "NNN.N K" and return the °C secondary line.
 *
 * @param k - Temperature in Kelvin, or null if no data.
 * @returns  `{ primary: string; secondary: string }` — formatted strings.
 */
function formatKelvin(k: number | null): { primary: string; secondary: string } {
  if (k === null) return { primary: '—', secondary: '' }
  const celsius = k - 273.15
  return {
    primary: k.toFixed(1),
    secondary: `(${celsius.toFixed(1)} °C)`,
  }
}

/**
 * Format thermal power in Watts as "NNNN.N MW".
 *
 * @param w - Power in Watts, or null.
 */
function formatMW(w: number | null): string {
  if (w === null) return '—'
  return (w / 1e6).toFixed(1)
}

/**
 * Format simulation time in seconds as "mm:ss.t".
 *
 * Examples:
 *   0       → "00:00.0"
 *   90.7    → "01:30.7"
 *   3661.2  → "61:01.2"
 *
 * @param t - Time in seconds, or null.
 */
function formatSimTime(t: number | null): string {
  if (t === null) return '—'
  const total = Math.max(0, t)
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  const mm = String(minutes).padStart(2, '0')
  const ss = String(Math.floor(seconds)).padStart(2, '0')
  const tenths = Math.floor((seconds % 1) * 10)
  return `${mm}:${ss}.${tenths}`
}

/**
 * Format a rod position fraction (0–1) as a percentage with one decimal.
 *
 * @param frac - Rod position [0..1], or null.
 */
function formatPercent(frac: number | null): string {
  if (frac === null) return '—'
  return (frac * 100).toFixed(1)
}

/**
 * Format reactivity in pcm (per cent mille = ×10⁻⁵) to one decimal place.
 *
 * @param rho - Dimensionless reactivity, or null.
 */
function formatPcm(rho: number | null): string {
  if (rho === null) return '—'
  // Convert dimensionless → pcm: multiply by 1e5
  return (rho * 1e5).toFixed(1)
}

// ---------------------------------------------------------------------------
// StatusPanel component
// ---------------------------------------------------------------------------

/**
 * StatusPanel
 *
 * Sidebar widget panel. Renders a heading and a responsive 2-column grid
 * of live telemetry tiles. Subscribes to the global Zustand telemetry store.
 */
const StatusPanel: FC = () => {
  // Single subscription to `latest`; component re-renders at every telemetry
  // frame (~10 Hz). This is acceptable for a small grid of tiles.
  const latest: Frame | null = useTelemetryStore((s) => s.latest)

  // Extract raw values (null when no data)
  const powerW = latest?.power_thermal ?? null
  const tHot = latest?.T_hot ?? null
  const tCold = latest?.T_cold ?? null
  const tAvg = latest?.T_avg ?? null
  const tFuel = latest?.T_fuel ?? null
  const pMPa = latest?.P_primary_MPa ?? null
  const rodPos = latest?.rod_position ?? null
  const rodCmd = latest?.rod_command ?? null
  const qSgW = latest?.Q_sg ?? null
  const rhoTotal = latest?.rho_total ?? null
  const simT = latest?.t ?? null
  const speed = latest?.speed ?? null
  const scrammed = latest?.scrammed ?? null
  const running = latest?.running ?? null

  // Pre-format temperature pairs
  const tHotFmt = formatKelvin(tHot)
  const tColdFmt = formatKelvin(tCold)
  const tAvgFmt = formatKelvin(tAvg)
  const tFuelFmt = formatKelvin(tFuel)

  return (
    <section aria-label="Plant status" className="flex flex-col gap-3">
      {/* Section heading */}
      <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-widest px-0.5">
        Plant status
      </h2>

      {/*
       * 2-column grid of tiles.
       * gap-3 provides breathing room between tiles.
       * Each tile manages its own hover-tooltip via CSS `group` + group-hover.
       */}
      <div className="grid grid-cols-2 gap-3">

        {/* ── Thermal power ────────────────────────────────────────────────── */}
        <StatusTile
          tooltip={TOOLTIPS.power_thermal}
          value={formatMW(powerW)}
        />

        {/* ── Primary pressure ─────────────────────────────────────────────── */}
        <StatusTile
          tooltip={TOOLTIPS.P_primary_MPa}
          value={pMPa !== null ? pMPa.toFixed(2) : '—'}
          band={pMPa !== null ? getBand('P_primary_MPa', pMPa) : 'green'}
        />

        {/* ── Hot-leg temperature ──────────────────────────────────────────── */}
        <StatusTile
          tooltip={TOOLTIPS.T_hot}
          value={tHotFmt.primary}
          secondary={tHotFmt.secondary}
        />

        {/* ── Cold-leg temperature ─────────────────────────────────────────── */}
        <StatusTile
          tooltip={TOOLTIPS.T_cold}
          value={tColdFmt.primary}
          secondary={tColdFmt.secondary}
        />

        {/* ── Average coolant temperature ──────────────────────────────────── */}
        <StatusTile
          tooltip={TOOLTIPS.T_avg}
          value={tAvgFmt.primary}
          secondary={tAvgFmt.secondary}
        />

        {/* ── Fuel temperature ─────────────────────────────────────────────── */}
        <StatusTile
          tooltip={TOOLTIPS.T_fuel}
          value={tFuelFmt.primary}
          secondary={tFuelFmt.secondary}
          band={tFuel !== null ? getBand('T_fuel', tFuel) : 'green'}
        />

        {/* ── Rod position ─────────────────────────────────────────────────── */}
        <StatusTile
          tooltip={TOOLTIPS.rod_position}
          value={formatPercent(rodPos)}
        />

        {/* ── Rod command ──────────────────────────────────────────────────── */}
        <StatusTile
          tooltip={TOOLTIPS.rod_command}
          value={formatPercent(rodCmd)}
        />

        {/* ── SG heat transfer ─────────────────────────────────────────────── */}
        <StatusTile
          tooltip={TOOLTIPS.Q_sg}
          value={formatMW(qSgW)}
        />

        {/* ── Total reactivity ─────────────────────────────────────────────── */}
        <StatusTile
          tooltip={{ ...TOOLTIPS.rho_total, units: 'pcm' }}
          value={formatPcm(rhoTotal)}
          band={rhoTotal !== null ? getBand('rho_total', rhoTotal * 1e5) : 'green'}
        />

        {/* ── Simulation time ──────────────────────────────────────────────── */}
        <StatusTile
          tooltip={{ ...TOOLTIPS.sim_time, units: 's' }}
          value={formatSimTime(simT)}
        />

        {/* ── Speed multiplier ─────────────────────────────────────────────── */}
        <StatusTile
          tooltip={TOOLTIPS.speed}
          value={speed !== null ? `${speed}` : '—'}
        />

        {/* ── SCRAM status ─────────────────────────────────────────────────── */}
        <StatusTile
          tooltip={TOOLTIPS.scrammed}
          value={scrammed === null ? '—' : scrammed ? 'YES' : 'NO'}
          band={scrammed === true ? 'red' : 'green'}
        />

        {/* ── Running status ───────────────────────────────────────────────── */}
        <StatusTile
          tooltip={TOOLTIPS.running}
          value={running === null ? '—' : running ? 'YES' : 'NO'}
        />

      </div>
    </section>
  )
}

export default StatusPanel
