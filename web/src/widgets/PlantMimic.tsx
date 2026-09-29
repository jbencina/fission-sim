/**
 * PlantMimic — a wireframe schematic of the primary and secondary plant.
 *
 * Reactor vessel (control bank drawn to its inserted depth), hot leg up to the
 * steam generator, cold leg back through the pump, and the pressurizer on a
 * surge line from the hot leg. The steam-generator shell side shows collapsed
 * liquid fraction, steam pressure, the steam line to the turbine, steam dump,
 * and feedwater return. Labels show live values; before the first frame every
 * value is "—" and the rods sit at their design position.
 */

import { type FC, useRef } from 'react'
import { useTelemetryStore } from '../state/telemetryStore'
import { InfoTip } from '../ui/InfoTip'
import { formatNumber } from '../ui/format'
import { describeSchematicState, turbineTripCause } from './loopState'
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
  'The primary loop carries hot pressurized water from the core to the steam generator and back ' +
  'through the reactor coolant pump. On the secondary side, heat boils feedwater into steam, the ' +
  'steam line feeds the turbine, and the dump branch bypasses the turbine when steam pressure is ' +
  'high. Feedwater returns inventory to the steam generator; its level is the SG collapsed liquid ' +
  'fraction (4 SGs lumped, no shrink/swell), not a visible swell level.'

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

  const sgLevel = latest?.level_sg ?? null
  const sgLevelFraction = Math.min(1, Math.max(0, sgLevel ?? 0.5))
  const sgLevelPercent = sgLevel === null ? null : sgLevel * 100
  const sgFillHeight = 196 * sgLevelFraction
  const sgFillY = 62 + (196 - sgFillHeight)
  // thresholds.ts is owned by D.5; this local colour mirrors its illustrative 0.40-0.60 band
  // and 0.35-0.90 operating band for the schematic only. These are not trip setpoints.
  const sgLevelInk =
    sgLevel === null
      ? 'var(--series-blue)'
      : sgLevel < 0.35 || sgLevel > 0.9
        ? 'var(--danger-ink)'
        : sgLevel < 0.4 || sgLevel > 0.6
          ? 'var(--warn-ink)'
          : 'var(--series-blue)'
  const sgLevelAria = `SG level ${formatNumber(sgLevelPercent, 0)} percent, collapsed liquid fraction, 4 SGs lumped, no shrink/swell`

  const pSteamMPa = latest?.P_steam_MPa ?? null
  const admissionPercent = latest ? latest.turbine_load * 100 : null
  const electricMW = latest ? latest.P_electric / 1e6 : null
  const mDump = latest?.m_dump ?? null
  const dumpOpen = (mDump ?? 0) > 1
  const mFeedwater = latest?.m_fw ?? null
  const feedwaterManual = latest ? latest.feedwater_manual !== null : false
  const tripCause = turbineTripCause(latest)
  const turbineTripped = tripCause !== null
  const turbineTripSummary = turbineTripped ? `turbine tripped: ${tripCause}` : 'turbine not tripped'
  const dumpSummary = dumpOpen ? `steam dump open at ${formatNumber(mDump, 0)} kilograms per second` : 'steam dump closed'
  const feedwaterSummary = `${feedwaterManual ? 'manual' : 'automatic'} feedwater ${formatNumber(
    mFeedwater,
    0,
  )} kilograms per second`

  const summary =
    `Core ${formatNumber(powerMW, 0)} MW, fuel ${tFuel} K, control bank ${formatNumber(inserted * 100, 0)} % inserted; ` +
    `primary pressure ${formatNumber(pMPa, 2)} MPa; hot leg ${tHot} K, cold leg ${tCold} K, average ${tAvg} K. ` +
    `Steam generator heat ${formatNumber(sgMW, 0)} MW; ${sgLevelAria}; steam pressure ${formatNumber(
      pSteamMPa,
      2,
    )} MPa. Turbine admission ${formatNumber(admissionPercent, 0)} %, gross electric ${formatNumber(
      electricMW,
      0,
    )} MW; ${turbineTripSummary}; ${dumpSummary}; ${feedwaterSummary}.`

  return (
    <section aria-label="Primary and secondary plant schematic" className="flex min-h-0 flex-col lg:h-full">
      <div ref={titleRef} className="flex items-center gap-2 px-4 pb-1 pt-3.5 sm:px-5">
        <h2 className="eyebrow">
          Plant schematic{' '}
          <span className="normal-case tracking-normal text-ink">· {describeSchematicState(latest)}</span>
        </h2>
        <InfoTip title="Plant schematic" body={SCHEMATIC_HELP} area={titleRef} />
      </div>
      <div className="min-h-0 flex-1 px-3 pb-2">
        <svg
          viewBox="0 0 380 470"
          role="img"
          aria-label={summary}
          className="mx-auto block h-full max-h-[440px] w-full lg:max-h-none"
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
          {/* hot leg: core outlet to steam generator primary tubes */}
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

          {/* two-sided steam generator: primary tubes inside a secondary shell */}
          <g role="img" aria-label={sgLevelAria}>
            <title>{sgLevelAria}</title>
            <rect x="194" y="60" width="70" height="200" fill="var(--canvas)" stroke="var(--line-strong)" strokeWidth="1.5" />
            <rect x="196" y={sgFillY} width="66" height={sgFillHeight} fill={sgLevelInk} opacity="0.16" />
            <line x1="196" y1={sgFillY} x2="262" y2={sgFillY} stroke={sgLevelInk} strokeWidth="1" />
            <path
              d="M210 90 q7 10 0 20 q-7 10 0 20 q7 10 0 20 q-7 10 0 20 q7 10 0 20 q-7 10 0 20 M228 90 q7 10 0 20 q-7 10 0 20 q7 10 0 20 q-7 10 0 20 q7 10 0 20 q-7 10 0 20 M246 90 q7 10 0 20 q-7 10 0 20 q7 10 0 20 q-7 10 0 20 q7 10 0 20 q-7 10 0 20"
              fill="none"
              stroke="var(--line)"
              strokeWidth="1"
            />
          </g>
          <text x="229" y="46" textAnchor="middle" {...LABEL}>
            STEAM GEN
          </text>
          <text x="229" y="31" textAnchor="middle" {...VALUE}>
            {formatNumber(pSteamMPa, 2)} <tspan {...UNIT}>MPa steam</tspan>
          </text>
          <text x="229" y="278" textAnchor="middle" {...VALUE} fill={sgLevelInk}>
            SG level {formatNumber(sgLevelPercent, 0)} <tspan fontSize="10">%</tspan>
          </text>
          <text x="229" y="294" textAnchor="middle" {...UNIT}>
            collapsed liquid, 4 SGs lumped
          </text>
          <text x="229" y="310" textAnchor="middle" {...UNIT}>
            {formatNumber(sgMW, 0)} MW heat transfer
          </text>

          {/* steam line, turbine admission and dump branch */}
          <path d="M264 92 H300" fill="none" stroke="var(--line-strong)" strokeWidth="2" />
          <path
            d="M286 92 V40 H366"
            fill="none"
            stroke={dumpOpen ? 'var(--warn-ink)' : 'var(--line)'}
            strokeWidth={dumpOpen ? '2' : '1'}
            strokeLinejoin="round"
          />
          {dumpOpen && (
            <text x="366" y="35" textAnchor="end" {...UNIT} fill="var(--warn-ink)">
              DUMP {formatNumber(mDump, 0)} kg/s
            </text>
          )}
          <g aria-label={turbineTripped ? `Turbine valve closed, ${tripCause}` : 'Turbine valve open'}>
            {turbineTripped ? (
              <>
                <line x1="289" y1="84" x2="297" y2="100" stroke="var(--danger-ink)" strokeWidth="1.5" />
                <line x1="289" y1="100" x2="297" y2="84" stroke="var(--danger-ink)" strokeWidth="1.5" />
              </>
            ) : (
              <path d="M289 85 L297 92 L289 99 Z" fill="none" stroke="var(--ink-2)" strokeWidth="1.2" />
            )}
          </g>
          <rect x="300" y="54" width="72" height="92" fill="var(--canvas)" stroke="var(--line-strong)" strokeWidth="1.5" />
          <text x="336" y="70" textAnchor="middle" {...LABEL}>
            TURBINE
          </text>
          <text x="336" y="91" textAnchor="middle" {...VALUE}>
            {formatNumber(admissionPercent, 0)} <tspan {...UNIT}>% adm</tspan>
          </text>
          <text x="336" y="109" textAnchor="middle" {...VALUE}>
            {formatNumber(electricMW, 0)} <tspan {...UNIT}>MW</tspan>
          </text>
          {turbineTripped && (
            <>
              <text x="336" y="128" textAnchor="middle" fontSize="11" fill="var(--danger-ink)" letterSpacing="1.2">
                TRIPPED
              </text>
              <text x="336" y="140" textAnchor="middle" fontSize="8.5" fill="var(--danger-ink)">
                {tripCause}
              </text>
            </>
          )}

          {/* feedwater return into the SG shell */}
          <path d="M366 228 H264" fill="none" stroke="var(--series-blue)" strokeWidth="2" />
          <path d="M264 228 l8 -4 v8z" fill="var(--series-blue)" />
          <text x="366" y="214" textAnchor="end" {...LABEL} fill="var(--series-blue)">
            FEEDWATER
          </text>
          <text x="366" y="234" textAnchor="end" {...VALUE}>
            {formatNumber(mFeedwater, 0)} <tspan {...UNIT}>kg/s</tspan>
          </text>
          {feedwaterManual && (
            <text x="366" y="249" textAnchor="end" fontSize="10" fill="var(--warn-ink)" letterSpacing="1.2">
              MAN
            </text>
          )}

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
