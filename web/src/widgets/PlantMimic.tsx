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
import {
  SHUTDOWN_BANK_INSERTED_TEXT,
  deriveFeedwaterModeStatus,
  isShutdownBankInserted,
} from '../state/plantStatus'
import { useTelemetryStore } from '../state/telemetryStore'
import { InfoTip } from '../ui/InfoTip'
import { formatNumber } from '../ui/format'
import { describeSchematicState, turbineTripStatus } from './loopState'
import { type Band, getBand } from './thresholds'

const LABEL = { fontSize: 14.8, letterSpacing: 1.05, fill: 'var(--ink-2)' } as const
const VALUE = { fontSize: 17.5, fontWeight: 300, fill: 'var(--ink)' } as const
const UNIT = { fontSize: 13.6, fontWeight: 400, fill: 'var(--ink-2)' } as const
const STATUS = { fontSize: 13.6, fontWeight: 400, letterSpacing: 1.2 } as const
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

function clampedFraction(value: number | undefined, fallback = 0.5): number {
  if (value === undefined || !Number.isFinite(value)) return fallback
  return Math.min(1, Math.max(0, value))
}

/** Short trip wording that fits inside the turbine body at dashboard scale. */
function turbineTripLines(label: string | undefined): string[] {
  if (label === 'operator trip') return ['OP TRIP']
  if (label === 'SCRAM (P-4)') return ['P-4']
  if (label === 'trip clearing') return ['CLEARING']
  return label ? [label.toUpperCase()] : ['TRIPPED']
}

const PlantMimic: FC = () => {
  const latest = useTelemetryStore((s) => s.latest)
  const titleRef = useRef<HTMLDivElement>(null)

  const inserted = insertedFraction(latest?.rod_position)
  const rodWithdrawnFraction = clampedFraction(latest?.rod_position)
  const powerMW = latest ? latest.power_thermal / 1e6 : null
  const sgMW = latest ? latest.Q_sg / 1e6 : null
  const pMPa = latest?.P_primary_MPa ?? null
  const band: Band = pMPa === null ? 'green' : getBand('P_primary_MPa', pMPa)
  const pzrLevelFraction = clampedFraction(latest?.pzr_level)
  const pzrLevelPercent = latest === null ? null : pzrLevelFraction * 100
  const pzrFillHeight = 68 * pzrLevelFraction
  const pzrFillY = 244 + (68 - pzrFillHeight)
  const tFuel = formatNumber(latest?.T_fuel ?? null, 0)
  const tHot = formatNumber(latest?.T_hot ?? null, 1)
  const tCold = formatNumber(latest?.T_cold ?? null, 1)
  const tAvg = formatNumber(latest?.T_avg ?? null, 1)

  const sgLevel = latest?.level_sg ?? null
  const sgLevelFraction = Math.min(1, Math.max(0, sgLevel ?? 0.5))
  const sgLevelPercent = sgLevel === null ? null : sgLevel * 100
  const sgFillHeight = 264 * sgLevelFraction
  const sgFillY = 162 + (264 - sgFillHeight)
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
  const feedwaterStatus = latest ? deriveFeedwaterModeStatus(latest) : null
  const feedwaterManualEffective = feedwaterStatus?.effectiveMode === 'manual'
  const feedwaterLabel = feedwaterManualEffective ? 'FW MAN' : 'FEED'
  const feedwaterPendingSelection =
    feedwaterStatus?.pending === true ? `${feedwaterStatus.selectedMode.toUpperCase()} PEND` : null
  const trip = turbineTripStatus(latest)
  const tripActive = trip?.kind === 'active'
  const tripPending = trip?.kind === 'pending-trip'
  const tripResetPending = trip?.kind === 'pending-reset'
  const tripTransient = trip?.kind === 'trip-transient'
  const valveClosed = tripActive || tripResetPending
  const turbineStatusSummary = trip
    ? trip.kind === 'active'
      ? `turbine tripped: ${trip.label}`
      : `turbine ${trip.label}`
    : 'turbine not tripped'
  const dumpSummary = dumpOpen ? `steam dump open at ${formatNumber(mDump, 0)} kilograms per second` : 'steam dump closed'
  const feedwaterModeWord = feedwaterManualEffective ? 'manual' : 'automatic'
  const feedwaterPendingSummary =
    feedwaterStatus?.pending === true
      ? `; selected ${feedwaterStatus.selectedMode} feedwater ${feedwaterStatus.detail}`
      : ''
  const feedwaterSummary = `effective ${feedwaterModeWord} feedwater ${formatNumber(
    mFeedwater,
    0,
  )} kilograms per second${feedwaterPendingSummary}`
  const tripDetailLines = turbineTripLines(trip?.label)
  const shutdownInserted = latest ? isShutdownBankInserted(latest) : false

  const summary =
    `Core ${formatNumber(powerMW, 0)} MW, fuel ${tFuel} K, control bank ${formatNumber(
      rodWithdrawnFraction * 100,
      0,
    )} % withdrawn; ${shutdownInserted ? `${SHUTDOWN_BANK_INSERTED_TEXT}; ` : ''}` +
    `primary pressure ${formatNumber(pMPa, 2)} MPa, pressurizer level ${formatNumber(
      pzrLevelPercent,
      0,
    )} percent; hot leg ${tHot} K, cold leg ${tCold} K, average ${tAvg} K. ` +
    `Steam generator heat ${formatNumber(sgMW, 0)} MW; ${sgLevelAria}; steam pressure ${formatNumber(
      pSteamMPa,
      2,
    )} MPa. Turbine admission ${formatNumber(admissionPercent, 0)} %, gross electric ${formatNumber(
      electricMW,
      0,
    )} MW; ${turbineStatusSummary}; ${dumpSummary}; ${feedwaterSummary}.`

  return (
    <section aria-label="Primary and secondary plant schematic" className="flex min-h-0 flex-col lg:h-full">
      <div ref={titleRef} className="px-4 pb-1 pt-3.5 sm:px-5">
        <div className="flex min-w-0 items-center gap-2">
          <h2 className="eyebrow min-w-0 truncate">
            Plant schematic{' '}
            <span className="normal-case tracking-normal text-ink">· {describeSchematicState(latest)}</span>
          </h2>
          <InfoTip title="Plant schematic" body={SCHEMATIC_HELP} area={titleRef} />
        </div>
        <p className="mt-1 text-[10.5px] leading-tight text-ink-3">
          SG collapsed; 4 SGs lumped; no shrink/swell; not narrow-range
        </p>
      </div>
      <div className="min-h-0 flex-1 px-2 pb-2">
        <svg
          viewBox="0 0 360 720"
          role="img"
          aria-label={summary}
          className="mx-auto block h-full w-full"
          fontFamily="'IBM Plex Mono', ui-monospace, monospace"
        >
          {shutdownInserted && (
            <>
              <text x="14" y="22" data-font-role="status" {...STATUS} fill="var(--warn-ink)">
                shutdown bank inserted
              </text>
              <text x="14" y="40" data-font-role="status" {...STATUS} fill="var(--warn-ink)">
                Reset Simulation required
              </text>
            </>
          )}
          {/* hot leg: core outlet to steam generator primary tubes */}
          <path
            d="M168 418 H184 V220 H188"
            fill="none"
            stroke="var(--line-strong)"
            strokeWidth="3"
            strokeLinejoin="round"
          />
          {/* cold leg: steam generator bottom, pump, core inlet */}
          <path
            d="M272 430 H286 V603"
            fill="none"
            stroke="var(--line-strong)"
            strokeWidth="3"
            strokeLinejoin="round"
          />
          <path
            d="M263 618 H24 V472 H58"
            fill="none"
            stroke="var(--line-strong)"
            strokeWidth="3"
            strokeLinejoin="round"
          />

          {/* pressurizer on its surge line */}
          <path d="M156 278 H178 V300 H184" fill="none" stroke="var(--line-strong)" strokeWidth="1" />
          <rect x="112" y="242" width="44" height="72" fill="var(--canvas)" stroke={BAND_FILL[band]} strokeWidth="1.5" />
          <rect x="114" y={pzrFillY} width="40" height={pzrFillHeight} fill="var(--line)" />
          <line x1="114" y1={pzrFillY} x2="154" y2={pzrFillY} stroke="var(--line-strong)" strokeWidth="0.8" />
          <path d="M112 303 H94" fill="none" stroke={BAND_FILL[band]} strokeWidth="1" />
          <text x="66" y="226" textAnchor="middle" data-font-role="label" {...LABEL}>
            PRESSURIZER
          </text>
          <text x="58" y="326" textAnchor="middle" data-font-role="value" {...VALUE} fill={BAND_FILL[band]}>
            {formatNumber(pMPa, 2)} <tspan data-font-role="unit" {...UNIT}>MPa</tspan>
          </text>
          {/* two-sided steam generator: primary tubes inside a secondary shell */}
          <g role="img" aria-label={sgLevelAria}>
            <title>{sgLevelAria}</title>
            <rect x="188" y="160" width="84" height="268" fill="var(--canvas)" stroke="var(--line-strong)" strokeWidth="1.5" />
            <rect x="190" y={sgFillY} width="80" height={sgFillHeight} fill={sgLevelInk} opacity="0.16" />
            <line x1="190" y1={sgFillY} x2="270" y2={sgFillY} stroke={sgLevelInk} strokeWidth="1" />
            <path
              d="M206 192 q7 12 0 24 q-7 12 0 24 q7 12 0 24 q-7 12 0 24 q7 12 0 24 q-7 12 0 24 q7 12 0 24 q-7 12 0 24 M230 192 q7 12 0 24 q-7 12 0 24 q7 12 0 24 q-7 12 0 24 q7 12 0 24 q-7 12 0 24 q7 12 0 24 q-7 12 0 24 M254 192 q7 12 0 24 q-7 12 0 24 q7 12 0 24 q-7 12 0 24 q7 12 0 24 q-7 12 0 24 q7 12 0 24 q-7 12 0 24"
              fill="none"
              stroke="var(--line)"
              strokeWidth="1"
            />
          </g>
          <text x="226" y="112" textAnchor="middle" data-font-role="label" {...LABEL}>
            STEAM GEN
          </text>
          <text x="226" y="138" textAnchor="middle" data-font-role="value" {...VALUE}>
            {formatNumber(pSteamMPa, 2)} <tspan data-font-role="unit" {...UNIT}>MPa</tspan>
          </text>
          <text x="218" y="456" textAnchor="middle" data-font-role="label" {...LABEL}>
            COLLAPSED
          </text>
          <text x="218" y="480" textAnchor="middle" data-font-role="value" {...VALUE} fill={sgLevelInk}>
            {formatNumber(sgLevelPercent, 0)} <tspan data-font-role="unit" {...UNIT}>%</tspan>
          </text>

          {/* steam line, turbine admission and dump branch */}
          <path d="M272 194 H282" fill="none" stroke="var(--line-strong)" strokeWidth="2" />
          <path
            d="M278 194 V82 H354"
            fill="none"
            stroke={dumpOpen ? 'var(--warn-ink)' : 'var(--line)'}
            strokeWidth={dumpOpen ? '2' : '1'}
            strokeLinejoin="round"
          />
          {dumpOpen && (
            <text x="354" y="64" textAnchor="end" data-font-role="unit" {...UNIT} fill="var(--warn-ink)">
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
                <line x1="274" y1="185" x2="282" y2="203" stroke="var(--danger-ink)" strokeWidth="1.5" />
                <line x1="274" y1="203" x2="282" y2="185" stroke="var(--danger-ink)" strokeWidth="1.5" />
              </>
            ) : (
              <path d="M274 186 L282 194 L274 202 Z" fill="none" stroke="var(--ink-2)" strokeWidth="1.2" />
            )}
          </g>
          <rect x="282" y="180" width="74" height="154" fill="var(--canvas)" stroke="var(--line-strong)" strokeWidth="1.5" />
          <text x="319" y="198" textAnchor="middle" data-font-role="label" {...LABEL}>
            TURB
          </text>
          <text x="319" y="224" textAnchor="middle" data-font-role="unit" {...UNIT}>
            ADM
          </text>
          <text x="319" y="252" textAnchor="middle" data-font-role="value" {...VALUE}>
            {formatNumber(admissionPercent, 0)} <tspan data-font-role="unit" {...UNIT}>%</tspan>
          </text>
          <text x="319" y="280" textAnchor="middle" data-font-role="value" {...VALUE}>
            {formatNumber(electricMW, 0)} <tspan data-font-role="unit" {...UNIT}>MW</tspan>
          </text>
          {tripActive && (
            <>
              <text x="319" y="302" textAnchor="middle" data-font-role="status" {...STATUS} fill="var(--danger-ink)">
                TRIPPED
              </text>
              {tripDetailLines.map((line, i) => (
                <text
                  key={line}
                  x="319"
                  y={326 + i * 16}
                  textAnchor="middle"
                  data-font-role="status"
                  fontSize="13.6"
                  fill="var(--danger-ink)"
                  letterSpacing="0.6"
                >
                  {line}
                </text>
              ))}
            </>
          )}
          {tripPending && (
            <>
              <text x="319" y="302" textAnchor="middle" data-font-role="status" {...STATUS} fill="var(--warn-ink)">
                PENDING
              </text>
              <text
                x="319"
                y="326"
                textAnchor="middle"
                data-font-role="status"
                fontSize="13.6"
                fill="var(--warn-ink)"
                letterSpacing="0.4"
              >
                ON RUN
              </text>
            </>
          )}
          {tripResetPending && (
            <>
              <text x="319" y="302" textAnchor="middle" data-font-role="status" {...STATUS} fill="var(--warn-ink)">
                RESET
              </text>
              <text
                x="319"
                y="326"
                textAnchor="middle"
                data-font-role="status"
                fontSize="13.6"
                fill="var(--warn-ink)"
                letterSpacing="0.4"
              >
                ON RUN
              </text>
            </>
          )}
          {tripTransient && (
            <>
              <text x="319" y="302" textAnchor="middle" data-font-role="status" {...STATUS} fill="var(--warn-ink)">
                TRIP CMD
              </text>
              <text
                x="319"
                y="326"
                textAnchor="middle"
                data-font-role="status"
                fontSize="13.6"
                fill="var(--warn-ink)"
                letterSpacing="0.4"
              >
                NEXT STEP
              </text>
            </>
          )}

          {/* feedwater return into the SG shell */}
          <path d="M356 418 H272" fill="none" stroke="var(--series-blue)" strokeWidth="2" />
          <path d="M272 418 l8 -4 v8z" fill="var(--series-blue)" />
          <text x="356" y="362" textAnchor="end" data-font-role="label" {...LABEL} fill="var(--series-blue)">
            {feedwaterLabel}
          </text>
          <text x="356" y="386" textAnchor="end" data-font-role="value" {...VALUE}>
            {formatNumber(mFeedwater, 0)}
          </text>
          <text x="356" y="412" textAnchor="end" data-font-role="unit" {...UNIT}>
            kg/s
          </text>
          {feedwaterPendingSelection && (
            <text x="356" y="438" textAnchor="end" data-font-role="status" {...STATUS} fill="var(--warn-ink)">
              {feedwaterPendingSelection}
            </text>
          )}
          {/* reactor vessel and core */}
          <rect x="58" y="382" width="110" height="128" fill="var(--canvas)" stroke="var(--line-strong)" strokeWidth="1.5" />
          <rect x="72" y="400" width="82" height="78" fill="none" stroke="var(--line)" strokeWidth="1" />
          {[0, 1, 2, 3, 4, 5].map((i) => (
            <rect key={i} x={80 + i * 12} y="400" width="5" height={78 * inserted} fill="var(--series-rod)" />
          ))}
          <text x="113" y="540" textAnchor="middle" data-font-role="label" {...LABEL}>
            CORE
          </text>
          <text x="113" y="564" textAnchor="middle" data-font-role="value" {...VALUE}>
            {formatNumber(powerMW, 0)} <tspan data-font-role="unit" {...UNIT}>MW</tspan>
          </text>
          <text
            x="145"
            y="584"
            textAnchor="middle"
            data-font-role="unit"
            fontSize="13.6"
            fill="var(--ink-2)"
            letterSpacing="0.1"
          >
            control bank {formatNumber(rodWithdrawnFraction * 100, 0)} % withdrawn
          </text>

          {/* pump on the cold leg */}
          <circle cx="278" cy="618" r="15" fill="var(--canvas)" stroke="var(--line-strong)" strokeWidth="1.5" />
          <path d="M272 611 l13 7 -13 7z" fill="var(--series-blue)" />
          <text x="246" y="646" textAnchor="middle" data-font-role="label" {...LABEL}>
            RCP
          </text>

          {/* leg temperatures */}
          <text x="96" y="348" data-font-role="label" {...LABEL}>
            HOT LEG
          </text>
          <text x="96" y="374" data-font-role="value" {...VALUE}>
            {tHot} <tspan data-font-role="unit" {...UNIT}>K</tspan>
          </text>
          <text x="58" y="674" data-font-role="label" {...LABEL} fill="var(--series-blue)">
            COLD LEG
          </text>
          <text x="58" y="700" data-font-role="value" {...VALUE}>
            {tCold} <tspan data-font-role="unit" {...UNIT}>K</tspan>
          </text>
          <text x="312" y="674" textAnchor="end" data-font-role="label" {...LABEL}>
            AVERAGE
          </text>
          <text x="312" y="700" textAnchor="end" data-font-role="value" {...VALUE}>
            {tAvg} <tspan data-font-role="unit" {...UNIT}>K</tspan>
          </text>
        </svg>
      </div>
    </section>
  )
}

export default PlantMimic
