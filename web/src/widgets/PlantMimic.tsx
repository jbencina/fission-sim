/**
 * PlantMimic — a wireframe schematic of the primary loop with live values.
 *
 * Reactor vessel (control bank drawn to its inserted depth), hot leg up to the
 * steam generator, cold leg back through the pump, and the pressurizer on
 * a surge line from the hot leg. Labels show core power, fuel temperature,
 * rod insertion, steam-generator heat, pressure (in its band colour) and
 * the three coolant temperatures. Before the first frame every value is
 * "—" and the rods sit at their design position.
 */

import { type FC, useRef } from 'react'
import { useTelemetryStore } from '../state/telemetryStore'
import { InfoTip } from '../ui/InfoTip'
import { formatNumber } from '../ui/format'
import { describeLoop } from './loopState'
import { type Band, getBand } from './thresholds'

const LABEL = { fontSize: 9.5, letterSpacing: 1, fill: 'var(--ink-2)' } as const
const VALUE = { fontSize: 14, fontWeight: 300, fill: 'var(--ink)' } as const
const UNIT = { fontSize: 10, fontWeight: 400, fill: 'var(--ink-2)' } as const
const BAND_FILL: Record<Band, string> = {
  green: 'var(--ink)',
  amber: 'var(--warn-ink)',
  red: 'var(--danger-ink)',
}

const SCHEMATIC_HELP =
  'The primary loop: water heated in the reactor core flows through the hot leg to the steam ' +
  'generator, gives up heat to make steam, and returns through the cold leg and the reactor ' +
  'coolant pump (RCP). The pressurizer, on a surge line from the hot leg, sets the pressure. ' +
  'The bars in the core are the control bank, drawn to its inserted depth; the shutdown bank, ' +
  'dropped only by a SCRAM, is not drawn.'

/** Rod bar height for a bank position; the design position before any data. */
function insertedFraction(rodPosition: number | undefined): number {
  if (rodPosition === undefined) return 0.5
  return 1 - Math.min(1, Math.max(0, rodPosition))
}

const PlantMimic: FC = () => {
  const latest = useTelemetryStore((s) => s.latest)
  const titleRef = useRef<HTMLDivElement>(null)

  const inserted = insertedFraction(latest?.rod_position)
  const powerMW = latest ? latest.power_thermal / 1e6 : null
  const sgMW = latest ? latest.Q_sg / 1e6 : null
  const pMPa = latest?.P_primary_MPa ?? null
  const band: Band = pMPa === null ? 'green' : getBand('P_primary_MPa', pMPa)
  const pressureNote =
    pMPa === null || band === 'green' ? 'design 15.5' : `${pMPa < 15.5 ? 'low' : 'high'}, design 15.5`
  const tFuel = formatNumber(latest?.T_fuel ?? null, 0)
  const tHot = formatNumber(latest?.T_hot ?? null, 1)
  const tCold = formatNumber(latest?.T_cold ?? null, 1)
  const tAvg = formatNumber(latest?.T_avg ?? null, 1)

  const summary =
    `Core ${formatNumber(powerMW, 0)} MW, fuel ${tFuel} K, control bank ${formatNumber(inserted * 100, 0)} % inserted; ` +
    `steam generator ${formatNumber(sgMW, 0)} MW; pressure ${formatNumber(pMPa, 2)} MPa; ` +
    `hot leg ${tHot} K, cold leg ${tCold} K, average ${tAvg} K.`

  return (
    <section aria-label="Primary loop schematic" className="flex min-h-0 flex-col lg:h-full">
      <div ref={titleRef} className="flex items-center gap-2 px-4 pb-1 pt-3.5 sm:px-5">
        <h2 className="eyebrow">
          Primary loop{' '}
          <span className="normal-case tracking-normal text-ink">· {describeLoop(latest)}</span>
        </h2>
        <InfoTip title="Primary loop" body={SCHEMATIC_HELP} area={titleRef} />
      </div>
      <div className="min-h-0 flex-1 px-3 pb-2">
        <svg
          viewBox="0 0 300 470"
          role="img"
          aria-label={summary}
          className="mx-auto block h-full max-h-[420px] w-full lg:max-h-none"
          fontFamily="'IBM Plex Mono', ui-monospace, monospace"
        >
          {/* cold leg: steam generator bottom, pump, core inlet */}
          <path
            d="M228 262 V372 H112 V352"
            fill="none"
            stroke="var(--line-strong)"
            strokeWidth="3"
            strokeLinejoin="round"
          />
          {/* hot leg: core outlet to steam generator top */}
          <path
            d="M112 232 V212 H228 V80"
            fill="none"
            stroke="var(--line-strong)"
            strokeWidth="3"
            strokeLinejoin="round"
          />

          {/* reactor vessel and core */}
          <rect x="60" y="232" width="104" height="120" fill="var(--canvas)" stroke="var(--line-strong)" strokeWidth="1.5" />
          <rect x="72" y="248" width="80" height="90" fill="none" stroke="var(--line)" strokeWidth="1" />
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <rect key={i} x={78 + i * 13} y="248" width="5" height={90 * inserted} fill="var(--series-rod)" />
          ))}
          <text x="112" y="366" textAnchor="middle" {...LABEL}>
            CORE
          </text>
          <text x="112" y="386" textAnchor="middle" {...VALUE}>
            {formatNumber(powerMW, 0)} <tspan {...UNIT}>MW</tspan>
          </text>
          <text x="112" y="400" textAnchor="middle" {...UNIT}>
            fuel {tFuel} K, control bank {formatNumber(inserted * 100, 0)} % in
          </text>

          {/* steam generator */}
          <rect x="204" y="60" width="48" height="200" fill="var(--canvas)" stroke="var(--line-strong)" strokeWidth="1.5" />
          <path
            d="M214 90 q7 10 0 20 q-7 10 0 20 q7 10 0 20 q-7 10 0 20 q7 10 0 20 q-7 10 0 20 M228 90 q7 10 0 20 q-7 10 0 20 q7 10 0 20 q-7 10 0 20 q7 10 0 20 q-7 10 0 20 M242 90 q7 10 0 20 q-7 10 0 20 q7 10 0 20 q-7 10 0 20 q7 10 0 20 q-7 10 0 20"
            fill="none"
            stroke="var(--line)"
            strokeWidth="1"
          />
          <text x="228" y="46" textAnchor="middle" {...LABEL}>
            STEAM GEN
          </text>
          <text x="228" y="32" textAnchor="middle" {...VALUE}>
            {formatNumber(sgMW, 0)} <tspan {...UNIT}>MW out</tspan>
          </text>

          {/* pressurizer on its surge line */}
          <path d="M160 212 V156" fill="none" stroke="var(--line-strong)" strokeWidth="1" />
          <rect x="140" y="92" width="40" height="64" fill="var(--canvas)" stroke={BAND_FILL[band]} strokeWidth="1.5" />
          <rect x="141" y="128" width="38" height="27" fill="var(--line)" />
          <text x="160" y="82" textAnchor="middle" {...LABEL}>
            PRESSURIZER
          </text>
          <text x="160" y="176" textAnchor="middle" {...VALUE} fill={BAND_FILL[band]}>
            {formatNumber(pMPa, 2)} <tspan fontSize="10">MPa</tspan>
          </text>
          <text
            x="160"
            y="189"
            textAnchor="middle"
            {...UNIT}
            fill={band === 'green' ? 'var(--ink-2)' : BAND_FILL[band]}
          >
            {pressureNote}
          </text>

          {/* pump on the cold leg */}
          <circle cx="228" cy="318" r="14" fill="var(--canvas)" stroke="var(--line-strong)" strokeWidth="1.5" />
          <path d="M222 312 l12 6 -12 6z" fill="var(--series-blue)" />
          <text x="252" y="322" {...LABEL}>
            RCP
          </text>

          {/* leg temperatures */}
          <text x="14" y="218" {...LABEL}>
            HOT LEG
          </text>
          <text x="14" y="204" {...VALUE}>
            {tHot} <tspan {...UNIT}>K</tspan>
          </text>
          <text x="60" y="430" {...LABEL} fill="var(--series-blue)">
            COLD LEG
          </text>
          <text x="60" y="450" {...VALUE}>
            {tCold} <tspan {...UNIT}>K</tspan>
          </text>
          <text x="238" y="430" textAnchor="end" {...LABEL}>
            AVERAGE
          </text>
          <text x="238" y="450" textAnchor="end" {...VALUE}>
            {tAvg} <tspan {...UNIT}>K</tspan>
          </text>
        </svg>
      </div>
    </section>
  )
}

export default PlantMimic
