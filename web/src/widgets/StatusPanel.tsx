/**
 * StatusPanel — the plant's readouts as label / value rows.
 *
 * Four headline rows (thermal power, average coolant temperature, primary
 * pressure, total reactivity) and grouped rows for the rest. Every readout
 * has an explanation (tooltips.ts) and some carry an illustrative alert
 * band (thresholds.ts). Simulation time, run state and SCRAM status are in
 * the toolbar; the loop schematic shows the same temperatures in place.
 *
 * Before the first telemetry frame every value shows "—".
 *
 * @module StatusPanel
 */

import type { FC, ReactNode } from 'react'
import { feedwaterSaturation } from '../state/events'
import { useTelemetryStore } from '../state/telemetryStore'
import { formatNumber, formatSignedNumber, kelvinToCelsius } from '../ui/format'
import { InfoRow } from './Readouts'
import { criticalityWord } from './loopState'
import { getBand } from './thresholds'
import { TOOLTIPS } from './tooltips'

/** Design thermal power [MW] (core.py `P_design` = 3.0e9 W). */
const DESIGN_POWER_MW = 3000

const celsius = (k: number | null): string | undefined =>
  k === null ? undefined : `${formatNumber(kelvinToCelsius(k), 1)} °C`

const Group: FC<{ title: string; children: ReactNode }> = ({ title, children }) => (
  <div className="mt-3">
    <h3 className="mb-0.5 text-[11.5px] tracking-[0.04em] text-ink-3">{title}</h3>
    <div>{children}</div>
  </div>
)

const StatusPanel: FC = () => {
  const latest = useTelemetryStore((s) => s.latest)

  const powerMW = latest ? latest.power_thermal / 1e6 : null
  const pMPa = latest?.P_primary_MPa ?? null
  const rhoPcm = latest ? latest.rho_total * 1e5 : null
  const tAvg = latest?.T_avg ?? null
  const tFuel = latest?.T_fuel ?? null
  const tHot = latest?.T_hot ?? null
  const tCold = latest?.T_cold ?? null
  const pSteamMPa = latest?.P_steam_MPa ?? null
  const tSecondary = latest?.T_secondary ?? null
  const levelSgPct = latest ? latest.level_sg * 100 : null
  const levelErrorPct = latest ? (latest.level_setpoint - latest.level_sg) * 100 : null
  const tAvgMinusRef = latest ? latest.T_avg - latest.T_ref : null
  const feedSteamMismatch = latest ? latest.m_fw - (latest.m_steam + latest.m_dump) : null
  const fwSaturation = latest ? feedwaterSaturation(latest) : null
  const fwDemandSecondary =
    latest === null
      ? undefined
      : fwSaturation === 'zero'
        ? 'saturated at zero'
        : fwSaturation === 'maximum'
          ? 'saturated at maximum'
          : fwSaturation === 'other'
            ? 'saturated'
            : `${formatNumber((latest.m_fw_demand / latest.m_fw_max) * 100, 0)} % max`

  return (
    <section aria-label="Plant status" className="panel p-4">
      <h2 className="eyebrow mb-1">Readouts</h2>

      <InfoRow
        data-testid="status-power_thermal"
        tooltip={TOOLTIPS.power_thermal}
        value={formatNumber(powerMW, 1)}
        secondary={
          powerMW === null ? undefined : `${formatNumber((powerMW / DESIGN_POWER_MW) * 100, 0)} % of design`
        }
      />
      <InfoRow
        data-testid="status-T_avg"
        tooltip={TOOLTIPS.T_avg}
        value={formatNumber(tAvg, 1)}
        secondary={celsius(tAvg)}
      />
      <InfoRow
        data-testid="status-P_primary_MPa"
        tooltip={TOOLTIPS.P_primary_MPa}
        value={formatNumber(pMPa, 2)}
        band={pMPa === null ? 'green' : getBand('P_primary_MPa', pMPa)}
      />
      <InfoRow
        data-testid="status-rho_total"
        tooltip={TOOLTIPS.rho_total}
        value={formatNumber(rhoPcm, 1)}
        secondary={rhoPcm === null ? undefined : criticalityWord(rhoPcm)}
        band={rhoPcm === null ? 'green' : getBand('rho_total', rhoPcm)}
      />

      <Group title="Core">
        <InfoRow
          data-testid="status-T_fuel"
          tooltip={TOOLTIPS.T_fuel}
          value={formatNumber(tFuel, 1)}
          secondary={celsius(tFuel)}
          band={tFuel === null ? 'green' : getBand('T_fuel', tFuel)}
        />
        <InfoRow
          data-testid="status-Q_sg"
          tooltip={TOOLTIPS.Q_sg}
          value={formatNumber(latest ? latest.Q_sg / 1e6 : null, 1)}
        />
      </Group>

      <Group title="Primary loop">
        <InfoRow
          data-testid="status-T_hot"
          tooltip={TOOLTIPS.T_hot}
          value={formatNumber(tHot, 1)}
          secondary={celsius(tHot)}
        />
        <InfoRow
          data-testid="status-T_cold"
          tooltip={TOOLTIPS.T_cold}
          value={formatNumber(tCold, 1)}
          secondary={celsius(tCold)}
        />
      </Group>

      <Group title="Steam generator">
        <InfoRow
          data-testid="status-P_steam_MPa"
          tooltip={TOOLTIPS.P_steam_MPa}
          value={formatNumber(pSteamMPa, 2)}
          secondary={pSteamMPa === null ? undefined : 'dump 7.6 / full 8.2'}
          band={pSteamMPa === null ? 'green' : getBand('P_steam_MPa', pSteamMPa)}
        />
        <InfoRow
          data-testid="status-T_secondary"
          tooltip={TOOLTIPS.T_secondary}
          value={formatNumber(tSecondary, 1)}
          secondary={celsius(tSecondary)}
        />
        <InfoRow
          data-testid="status-level_sg"
          tooltip={TOOLTIPS.level_sg}
          value={formatNumber(levelSgPct, 1)}
          secondary="valid 30–95 %"
          band={latest === null ? 'green' : getBand('level_sg', latest.level_sg)}
        />
        <InfoRow
          data-testid="status-level_error"
          tooltip={TOOLTIPS.level_error}
          value={formatSignedNumber(levelErrorPct, 1)}
          secondary={latest === null ? undefined : `setpoint ${formatNumber(latest.level_setpoint * 100, 1)} %`}
        />
        <InfoRow
          data-testid="status-T_avg_minus_T_ref"
          tooltip={TOOLTIPS.T_avg_minus_T_ref}
          value={formatSignedNumber(tAvgMinusRef, 1)}
          secondary={latest === null ? undefined : `T_ref ${formatNumber(latest.T_ref, 1)} K`}
        />
        <InfoRow
          data-testid="status-time_to_level_floor_s"
          tooltip={TOOLTIPS.time_to_level_floor_s}
          value={formatNumber(latest?.time_to_level_floor_s, 0)}
          secondary={latest?.time_to_level_floor_s == null ? undefined : 'current-flow estimate'}
        />
      </Group>

      <Group title="Turbine">
        <InfoRow
          data-testid="status-P_electric"
          tooltip={TOOLTIPS.P_electric}
          value={formatNumber(latest ? latest.P_electric / 1e6 : null, 1)}
          secondary="fixed-efficiency proxy"
        />
        <InfoRow
          data-testid="status-turbine_load"
          tooltip={TOOLTIPS.turbine_load}
          value={formatNumber(latest ? latest.turbine_load * 100 : null, 1)}
          secondary={latest === null ? undefined : `demand ${formatNumber(latest.turbine_load_demand * 100, 0)} %`}
        />
        <InfoRow
          data-testid="status-m_steam"
          tooltip={TOOLTIPS.m_steam}
          value={formatNumber(latest?.m_steam, 1)}
        />
        <InfoRow
          data-testid="status-m_dump"
          tooltip={TOOLTIPS.m_dump}
          value={formatNumber(latest?.m_dump, 1)}
        />
      </Group>

      <Group title="Feedwater">
        <InfoRow
          data-testid="status-m_fw"
          tooltip={TOOLTIPS.m_fw}
          value={formatNumber(latest?.m_fw, 1)}
        />
        <InfoRow
          data-testid="status-m_fw_demand"
          tooltip={TOOLTIPS.m_fw_demand}
          value={formatNumber(latest?.m_fw_demand, 1)}
          secondary={fwDemandSecondary}
          band={latest?.fw_saturated ? 'amber' : 'green'}
        />
        <InfoRow
          data-testid="status-feed_steam_mismatch"
          tooltip={TOOLTIPS.feed_steam_mismatch}
          value={formatSignedNumber(feedSteamMismatch, 1)}
        />
      </Group>

      <Group title="Control bank">
        <InfoRow
          data-testid="status-rod_position"
          tooltip={TOOLTIPS.rod_position}
          value={formatNumber(latest ? latest.rod_position * 100 : null, 1)}
        />
        <InfoRow
          data-testid="status-rod_command"
          tooltip={TOOLTIPS.rod_command}
          value={formatNumber(latest ? latest.rod_command * 100 : null, 1)}
        />
      </Group>
    </section>
  )
}

export default StatusPanel
