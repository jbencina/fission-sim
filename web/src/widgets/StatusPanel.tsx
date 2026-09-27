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
import { useTelemetryStore } from '../state/telemetryStore'
import { formatNumber, kelvinToCelsius } from '../ui/format'
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
