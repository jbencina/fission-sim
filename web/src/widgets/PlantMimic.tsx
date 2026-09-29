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
import { describeSchematicState, turbineTripStatus } from './loopState'
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
  const sgFillHeight = 250 * sgLevelFraction
  const sgFillY = 112 + (250 - sgFillHeight)
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
  const trip = turbineTripStatus(latest)
  const tripActive = trip?.kind === 'active'
  const tripPending = trip?.kind === 'pending-trip'
  const tripResetPending = trip?.kind === 'pending-reset'
  const valveClosed = tripActive || tripResetPending
  const turbineStatusSummary = trip
    ? trip.kind === 'active'
      ? `turbine tripped: ${trip.label}`
      : `turbine ${trip.label}`
    : 'turbine not tripped'
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
    )} MW; ${turbineStatusSummary}; ${dumpSummary}; ${feedwaterSummary}.`

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
          viewBox="0 0 360 640"
          role="img"
          aria-label={summary}
          className="mx-auto block h-full w-full"
          fontFamily="'IBM Plex Mono', ui-monospace, monospace"
        >
          {/* hot leg: core outlet to steam generator primary tubes */}
          <path
            d="M112 328 V300 H186 V112"
            fill="none"
            stroke="var(--line-strong)"
            strokeWidth="3"
            strokeLinejoin="round"
          />
          {/* cold leg: steam generator bottom, pump, core inlet */}
          <path
            d="M268 362 H282 V548 H48 V394 H56"
            fill="none"
            stroke="var(--line-strong)"
            strokeWidth="3"
            strokeLinejoin="round"
          />

          {/* reactor vessel and core */}
          <rect x="56" y="328" width="112" height="126" fill="var(--canvas)" stroke="var(--line-strong)" strokeWidth="1.5" />
          <rect x="70" y="346" width="84" height="86" fill="none" stroke="var(--line)" strokeWidth="1" />
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <rect key={i} x={77 + i * 13} y="346" width="5" height={86 * inserted} fill="var(--series-rod)" />
          ))}
          <text x="112" y="476" textAnchor="middle" {...LABEL}>
            CORE
          </text>
          <text x="112" y="498" textAnchor="middle" {...VALUE}>
            {formatNumber(powerMW, 0)} <tspan {...UNIT}>MW</tspan>
          </text>
          <text x="112" y="514" textAnchor="middle" {...UNIT}>
            fuel {tFuel} K, rods {formatNumber(inserted * 100, 0)} % in
          </text>

          {/* two-sided steam generator: primary tubes inside a secondary shell */}
          <g role="img" aria-label={sgLevelAria}>
            <title>{sgLevelAria}</title>
            <rect x="186" y="110" width="82" height="254" fill="var(--canvas)" stroke="var(--line-strong)" strokeWidth="1.5" />
            <rect x="188" y={sgFillY} width="78" height={sgFillHeight} fill={sgLevelInk} opacity="0.16" />
            <line x1="188" y1={sgFillY} x2="266" y2={sgFillY} stroke={sgLevelInk} strokeWidth="1" />
            <path
              d="M202 140 q7 12 0 24 q-7 12 0 24 q7 12 0 24 q-7 12 0 24 q7 12 0 24 q-7 12 0 24 q7 12 0 24 M226 140 q7 12 0 24 q-7 12 0 24 q7 12 0 24 q-7 12 0 24 q7 12 0 24 q-7 12 0 24 q7 12 0 24 M250 140 q7 12 0 24 q-7 12 0 24 q7 12 0 24 q-7 12 0 24 q7 12 0 24 q-7 12 0 24 q7 12 0 24"
              fill="none"
              stroke="var(--line)"
              strokeWidth="1"
            />
          </g>
          <text x="226" y="84" textAnchor="middle" {...LABEL}>
            STEAM GEN
          </text>
          <text x="226" y="102" textAnchor="middle" {...VALUE}>
            {formatNumber(pSteamMPa, 2)} <tspan {...UNIT}>MPa steam</tspan>
          </text>
          <text x="228" y="386" textAnchor="middle" {...VALUE} fill={sgLevelInk}>
            SG level {formatNumber(sgLevelPercent, 0)} <tspan fontSize="10">%</tspan>
          </text>
          <text x="228" y="406" textAnchor="middle" {...UNIT}>
            {formatNumber(sgMW, 0)} MW HX
          </text>

          {/* steam line, turbine admission and dump branch */}
          <path d="M268 144 H278" fill="none" stroke="var(--line-strong)" strokeWidth="2" />
          <path
            d="M278 144 V42 H356"
            fill="none"
            stroke={dumpOpen ? 'var(--warn-ink)' : 'var(--line)'}
            strokeWidth={dumpOpen ? '2' : '1'}
            strokeLinejoin="round"
          />
          {dumpOpen && (
            <text x="356" y="34" textAnchor="end" {...UNIT} fill="var(--warn-ink)">
              DUMP {formatNumber(mDump, 0)} kg/s
            </text>
          )}
          <g
            aria-label={
              valveClosed ? `Turbine valve closed, ${trip?.label ?? 'tripped'}` : 'Turbine valve open'
            }
          >
            {valveClosed ? (
              <>
                <line x1="275" y1="135" x2="283" y2="153" stroke="var(--danger-ink)" strokeWidth="1.5" />
                <line x1="275" y1="153" x2="283" y2="135" stroke="var(--danger-ink)" strokeWidth="1.5" />
              </>
            ) : (
              <path d="M275 136 L283 144 L275 152 Z" fill="none" stroke="var(--ink-2)" strokeWidth="1.2" />
            )}
          </g>
          <rect x="278" y="108" width="78" height="126" fill="var(--canvas)" stroke="var(--line-strong)" strokeWidth="1.5" />
          <text x="317" y="127" textAnchor="middle" {...LABEL}>
            TURBINE
          </text>
          <text x="317" y="151" textAnchor="middle" {...VALUE}>
            <tspan {...UNIT}>adm </tspan>{formatNumber(admissionPercent, 0)} <tspan {...UNIT}>%</tspan>
          </text>
          <text x="317" y="174" textAnchor="middle" {...VALUE}>
            {formatNumber(electricMW, 0)} <tspan {...UNIT}>MW</tspan>
          </text>
          {tripActive && (
            <>
              <text x="317" y="200" textAnchor="middle" fontSize="11" fill="var(--danger-ink)" letterSpacing="1.2">
                TRIPPED
              </text>
              <text x="317" y="216" textAnchor="middle" fontSize="8.5" fill="var(--danger-ink)">
                {trip.label}
              </text>
            </>
          )}
          {tripPending && (
            <>
              <text x="317" y="200" textAnchor="middle" fontSize="10.5" fill="var(--warn-ink)" letterSpacing="0.7">
                PENDING
              </text>
              <text x="317" y="216" textAnchor="middle" fontSize="8" fill="var(--warn-ink)">
                trip on run
              </text>
            </>
          )}
          {tripResetPending && (
            <>
              <text x="317" y="200" textAnchor="middle" fontSize="9.5" fill="var(--warn-ink)" letterSpacing="0.5">
                RESET PEND
              </text>
              <text x="317" y="216" textAnchor="middle" fontSize="8" fill="var(--warn-ink)">
                on run
              </text>
            </>
          )}

          {/* feedwater return into the SG shell */}
          <path d="M356 316 H268" fill="none" stroke="var(--series-blue)" strokeWidth="2" />
          <path d="M268 316 l8 -4 v8z" fill="var(--series-blue)" />
          <text x="356" y="342" textAnchor="end" {...LABEL} fill="var(--series-blue)">
            FEEDWATER
          </text>
          <text x="356" y="362" textAnchor="end" {...VALUE}>
            {formatNumber(mFeedwater, 0)} <tspan {...UNIT}>kg/s</tspan>
          </text>
          {feedwaterManual && (
            <text x="356" y="378" textAnchor="end" fontSize="10" fill="var(--warn-ink)" letterSpacing="1.2">
              MAN
            </text>
          )}

          {/* pressurizer on its surge line */}
          <path d="M162 280 H176 V300" fill="none" stroke="var(--line-strong)" strokeWidth="1" />
          <rect x="118" y="208" width="44" height="70" fill="var(--canvas)" stroke={BAND_FILL[band]} strokeWidth="1.5" />
          <rect x="120" y="248" width="40" height="28" fill="var(--line)" />
          <text x="76" y="214" textAnchor="middle" {...LABEL}>
            PRESSURIZER
          </text>
          <text x="74" y="276" textAnchor="middle" {...VALUE} fill={BAND_FILL[band]}>
            {formatNumber(pMPa, 2)} <tspan fontSize="10">MPa</tspan>
          </text>
          <text
            x="74"
            y="292"
            textAnchor="middle"
            {...UNIT}
            fill={band === 'green' ? 'var(--ink-2)' : BAND_FILL[band]}
          >
            {pressureNote}
          </text>

          {/* pump on the cold leg */}
          <circle cx="282" cy="548" r="15" fill="var(--canvas)" stroke="var(--line-strong)" strokeWidth="1.5" />
          <path d="M276 541 l13 7 -13 7z" fill="var(--series-blue)" />
          <text x="282" y="577" textAnchor="middle" {...LABEL}>
            RCP
          </text>

          {/* leg temperatures */}
          <text x="20" y="322" {...LABEL}>
            HOT LEG
          </text>
          <text x="20" y="306" {...VALUE}>
            {tHot} <tspan {...UNIT}>K</tspan>
          </text>
          <text x="60" y="600" {...LABEL} fill="var(--series-blue)">
            COLD LEG
          </text>
          <text x="60" y="624" {...VALUE}>
            {tCold} <tspan {...UNIT}>K</tspan>
          </text>
          <text x="306" y="600" textAnchor="end" {...LABEL}>
            AVERAGE
          </text>
          <text x="306" y="624" textAnchor="end" {...VALUE}>
            {tAvg} <tspan {...UNIT}>K</tspan>
          </text>
        </svg>
      </div>
    </section>
  )
}

export default PlantMimic
