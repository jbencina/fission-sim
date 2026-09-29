/**
 * SecondaryControls — operator controls for the M4 secondary side.
 *
 * The panel covers turbine admission/trip, steam-generator collapsed level,
 * and feedwater AUTO/MANUAL demand. All values are SI in the telemetry frame;
 * labels convert to percent, MW and kg/s for operator readability.
 *
 * @module SecondaryControls
 */

import { type FC, useCallback, useState } from 'react'
import { useTelemetryStore } from '../state/telemetryStore'
import { LEVEL_SETPOINT_MAX, LEVEL_SETPOINT_MIN } from '../types/telemetry'
import { HelpTip } from '../ui/InfoTip'
import { formatNumber } from '../ui/format'
import ConfirmDialog from './ConfirmDialog'
import {
  clampFraction,
  deriveFeedwaterModeStatus,
  deriveTurbineTripStatus,
  feedwaterDemandFraction,
  type StatusTone,
} from '../state/plantStatus'
import { useCommittedRange } from './useCommittedRange'

function toneClass(tone: StatusTone): string {
  if (tone === 'danger') return 'text-danger'
  if (tone === 'warn') return 'text-warn'
  return 'text-ink'
}

function clampRange(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min
  return Math.min(max, Math.max(min, value))
}

function rangePercent(value: number, min: number, max: number): number {
  if (max <= min) return 0
  return clampFraction((value - min) / (max - min)) * 100
}

function formatFeedwaterSelection(
  mode: 'auto' | 'manual',
  demandKgS: number | null,
  mFwMax: number,
): string {
  if (mode === 'auto' || demandKgS === null || mFwMax <= 0) return 'AUTO'
  return `${formatNumber((demandKgS / mFwMax) * 100, 0)} % max (${formatNumber(demandKgS, 0)} kg/s)`
}

const Readout: FC<{ label: string; value: string; unit: string }> = ({ label, value, unit }) => (
  <div>
    <div className="text-[11.5px] tracking-[0.04em] text-ink-2">{label}</div>
    <div className="font-mono text-[18px] font-light leading-tight tabular-nums text-ink">
      {value}
      <span className="ml-1 font-sans text-[11px] text-ink-2">{unit}</span>
    </div>
  </div>
)

const Divider: FC = () => <div className="-mx-4 my-4 h-px bg-line" />

/**
 * Secondary-side operator panel: turbine, SG level and feedwater controls.
 */
const SecondaryControls: FC = () => {
  const status = useTelemetryStore((s) => s.status)
  const latest = useTelemetryStore((s) => s.latest)
  const sendCommand = useTelemetryStore((s) => s.sendCommand)

  const connected = status === 'connected'
  const turbineDemand = latest?.turbine_load_demand ?? 1
  const turbineActual = latest?.turbine_load ?? null
  const grossMw = latest === null ? null : latest.P_electric / 1e6
  const levelSetpoint = latest?.level_setpoint ?? 0.5
  const levelSg = latest?.level_sg ?? null
  const mFwMax = latest?.m_fw_max ?? 0
  const feedwaterManual = latest?.feedwater_manual ?? null
  const feedwaterDemandFrac = latest ? feedwaterDemandFraction(latest) : 0
  const feedwaterSliderBackend = feedwaterManual ?? feedwaterDemandFrac
  const designFeedwater = mFwMax / 1.2

  const tripStatus = latest
    ? deriveTurbineTripStatus(latest)
    : {
        kind: 'not-tripped' as const,
        label: 'NOT TRIPPED',
        cause: 'Waiting for first telemetry frame.',
        active: false,
        tone: 'normal' as const,
      }
  const feedwaterStatus = latest
    ? deriveFeedwaterModeStatus(latest)
    : {
        kind: 'auto' as const,
        label: 'AUTO',
        detail: 'Waiting for first telemetry frame.',
        pending: false,
        tone: 'normal' as const,
        selectedMode: 'auto' as const,
        effectiveMode: 'auto' as const,
        selectedDemandKgS: null,
        effectiveSelectedDemandKgS: null,
        effectiveDemandKgS: 0,
        saturation: null,
      }

  const handleTurbineCommit = useCallback(
    (value: number) => {
      sendCommand({ type: 'set_turbine_load', value: clampFraction(value) })
    },
    [sendCommand],
  )
  const turbineSlider = useCommittedRange(turbineDemand, handleTurbineCommit)

  const handleLevelCommit = useCallback(
    (value: number) => {
      sendCommand({
        type: 'set_level_setpoint',
        value: clampRange(value, LEVEL_SETPOINT_MIN, LEVEL_SETPOINT_MAX),
      })
    },
    [sendCommand],
  )
  const levelSlider = useCommittedRange(levelSetpoint, handleLevelCommit)

  const handleFeedwaterCommit = useCallback(
    (value: number) => {
      if (feedwaterManual !== null) {
        sendCommand({ type: 'set_feedwater_manual', value: clampFraction(value) })
      }
    },
    [feedwaterManual, sendCommand],
  )
  const feedwaterSlider = useCommittedRange(feedwaterSliderBackend, handleFeedwaterCommit)

  const [tripDialogOpen, setTripDialogOpen] = useState(false)

  const handleTripConfirm = useCallback(() => {
    setTripDialogOpen(false)
    sendCommand({ type: 'turbine_trip' })
  }, [sendCommand])

  const handleResetTrip = useCallback(() => {
    sendCommand({ type: 'reset_turbine_trip' })
  }, [sendCommand])

  const handleFeedwaterMode = useCallback(
    (manual: boolean) => {
      if (!manual) {
        sendCommand({ type: 'set_feedwater_manual', value: null })
        return
      }
      const value = latest ? feedwaterDemandFraction(latest) : feedwaterSlider.value
      feedwaterSlider.setValue(value)
      sendCommand({ type: 'set_feedwater_manual', value })
    },
    [feedwaterSlider, latest, sendCommand],
  )

  const actualAdmissionPct = turbineActual === null ? 0 : clampFraction(turbineActual) * 100
  const levelMarkerPct =
    levelSg === null ? 50 : rangePercent(levelSg, LEVEL_SETPOINT_MIN, LEVEL_SETPOINT_MAX)
  const manualFlow = latest === null ? null : feedwaterSlider.value * mFwMax
  const manualDesignPct = designFeedwater > 0 && manualFlow !== null ? (manualFlow / designFeedwater) * 100 : null
  const turbineResetCopy =
    latest?.turbine_trip === true
      ? 'Reset Turbine Trip is accepted once actual admission is closed.'
      : latest?.scrammed === true
        ? 'Reset Scram sets demand to 0 % and keeps the trip until closed.'
        : 'Demand remains retained until the trip clears.'
  const turbineContext =
    tripStatus.active || tripStatus.kind === 'reset-pending'
      ? `Valves closing — demand ${formatNumber(turbineSlider.value * 100, 0)} % retained; ${turbineResetCopy}`
      : tripStatus.kind === 'trip-pending'
        ? `Trip pending — demand ${formatNumber(turbineSlider.value * 100, 0)} % is retained until the simulation runs.`
        : 'Admission demand ramps at 5 %/min; the marker shows actual valve admission.'
  const feedwaterPending = feedwaterStatus.kind === 'pending'
  const feedwaterSelectedText = formatFeedwaterSelection(
    feedwaterStatus.selectedMode,
    feedwaterStatus.selectedDemandKgS,
    mFwMax,
  )

  return (
    <>
      <ConfirmDialog
        open={tripDialogOpen}
        title="Trip turbine?"
        message="This is an unprotected exercise. A real plant also trips the reactor on turbine trip above about 50 % power (P-9); this model does not. The steam dump takes the steam."
        confirmLabel="Trip turbine"
        danger
        onConfirm={handleTripConfirm}
        onCancel={() => setTripDialogOpen(false)}
      />

      <section aria-label="Secondary-side controls" className="panel p-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="eyebrow">Secondary controls</h2>
          {!connected && <span className="text-[11.5px] text-ink-3">Offline, controls inactive</span>}
        </div>

        <fieldset disabled={!connected} className={connected ? '' : 'opacity-60'}>
          {/* ── Turbine admission and trip ──────────────────────────────── */}
          <section aria-label="Turbine controls" className="mt-3">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-[11.5px] tracking-[0.04em] text-ink-2">Effective trip</div>
                <div className={`font-mono text-[13px] tabular-nums ${toneClass(tripStatus.tone)}`}>
                  {tripStatus.label}
                </div>
                <div className="text-[10.5px] text-ink-3">{tripStatus.cause}</div>
              </div>
            </div>

            <div className="mt-3 grid grid-cols-3 gap-3">
              <Readout label="Demand" value={formatNumber(turbineSlider.value * 100, 0)} unit="%" />
              <Readout
                label="Actual"
                value={formatNumber(turbineActual === null ? null : turbineActual * 100, 0)}
                unit="%"
              />
              <Readout label="Gross elec." value={formatNumber(grossMw, 0)} unit="MW" />
            </div>
            <p className={`mt-2 text-[11px] leading-snug ${tripStatus.active ? 'text-warn' : 'text-ink-2'}`}>
              {turbineContext}
            </p>

            <HelpTip tip="Turbine admission demand, not electrical load. The actual admission valve ramps toward this demand at 5 percentage-points per minute and is forced closed by an effective turbine trip. The white marker is actual admission.">
              {(tipId) => (
                <div className="relative mt-3">
                  <div
                    aria-hidden="true"
                    className="pointer-events-none absolute inset-x-[7px] top-1/2 h-px -translate-y-1/2 bg-line-strong"
                  >
                    <div
                      className="absolute top-1/2 h-3 w-0.5 -translate-y-1/2 bg-ink transition-[left] duration-200 ease-linear"
                      style={{ left: `${actualAdmissionPct}%` }}
                    />
                  </div>
                  <input
                    ref={turbineSlider.ref}
                    aria-describedby={tipId}
                    type="range"
                    className="rod-range relative"
                    min={0}
                    max={1}
                    step={0.01}
                    value={turbineSlider.value}
                    disabled={!connected}
                    aria-label="Turbine admission demand"
                    aria-valuetext={`${(turbineSlider.value * 100).toFixed(0)} % admission demand`}
                    onChange={turbineSlider.onChange}
                  />
                </div>
              )}
            </HelpTip>
            <div aria-hidden="true" className="mt-0.5 flex justify-between px-0.5 text-[10.5px] text-ink-3">
              <span>Closed</span>
              <span>Full admission</span>
            </div>

            <div className="mt-3 grid grid-cols-2 gap-2">
              <HelpTip tip="Trips the turbine stop valves. This is unprotected in the simulator: a real plant also trips the reactor above about 50 % power (P-9), but that protection is not modeled here.">
                {(tipId) => (
                  <button
                    type="button"
                    aria-describedby={tipId}
                    disabled={!connected || tripStatus.active || tripStatus.kind === 'trip-pending'}
                    onClick={() => setTripDialogOpen(true)}
                    className="btn btn-danger w-full text-[12px] !tracking-[0.18em]"
                  >
                    TRIP TURBINE
                  </button>
                )}
              </HelpTip>

              {latest?.turbine_trip === true ? (
                <HelpTip
                  align="end"
                  tip="Clears only the operator turbine-trip latch after actual admission is closed. The backend refuses while valves are more than 0.5 % open. Admission demand returns to 0 %, and re-admission is a deliberate later demand change."
                >
                  {(tipId) => (
                    <button
                      type="button"
                      aria-describedby={tipId}
                      disabled={!connected}
                      onClick={handleResetTrip}
                      className="btn w-full !border-ink"
                    >
                      Reset Turbine Trip
                    </button>
                  )}
                </HelpTip>
              ) : (
                <div aria-hidden="true" />
              )}
            </div>
          </section>

          <Divider />

          {/* ── SG level setpoint ───────────────────────────────────────── */}
          <section aria-label="Steam-generator level controls">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h3 className="text-[12px] uppercase tracking-[0.14em] text-ink-2">
                  SG collapsed liquid fraction
                </h3>
                <p className="mt-0.5 text-[11px] text-ink-3">4 SGs lumped, no shrink/swell</p>
              </div>
              <Readout
                label="Current"
                value={formatNumber(levelSg === null ? null : levelSg * 100, 1)}
                unit="%"
              />
            </div>

            <div className="mt-3 grid grid-cols-2 gap-3">
              <Readout label="Setpoint" value={formatNumber(levelSlider.value * 100, 1)} unit="%" />
              <Readout
                label="Band"
                value={`${formatNumber(LEVEL_SETPOINT_MIN * 100, 0)}–${formatNumber(
                  LEVEL_SETPOINT_MAX * 100,
                  0,
                )}`}
                unit="%"
              />
            </div>

            <HelpTip tip="Feedwater level target for SG collapsed liquid fraction. The allowed 35–90 % operating band stays inside the model validity limits; collapsed level is inventory, not a shrink/swell narrow-range indication.">
              {(tipId) => (
                <div className="relative mt-3">
                  <div
                    aria-hidden="true"
                    className="pointer-events-none absolute inset-x-[7px] top-1/2 h-px -translate-y-1/2 bg-line-strong"
                  >
                    <div
                      className="absolute top-1/2 h-3 w-0.5 -translate-y-1/2 bg-ink transition-[left] duration-200 ease-linear"
                      style={{ left: `${levelMarkerPct}%` }}
                    />
                  </div>
                  <input
                    ref={levelSlider.ref}
                    aria-describedby={tipId}
                    type="range"
                    className="rod-range relative"
                    min={LEVEL_SETPOINT_MIN}
                    max={LEVEL_SETPOINT_MAX}
                    step={0.01}
                    value={levelSlider.value}
                    disabled={!connected}
                    aria-label="SG level setpoint"
                    aria-valuetext={`${(levelSlider.value * 100).toFixed(0)} % collapsed liquid fraction setpoint`}
                    onChange={levelSlider.onChange}
                  />
                </div>
              )}
            </HelpTip>
          </section>

          <Divider />

          {/* ── Feedwater mode and manual demand ────────────────────────── */}
          <section aria-label="Feedwater controls">
            <HelpTip tip="AUTO uses the three-element level controller. MANUAL sends a direct feedwater demand; selecting MANUAL is bumpless because the UI sends the current demand fraction. Returning to AUTO sends null.">
              {(tipId) => (
                <div className="flex items-center justify-between gap-3">
                  <div aria-describedby={tipId} className="seg" role="group" aria-label="Feedwater mode">
                    <button
                      type="button"
                      disabled={!connected}
                      aria-pressed={feedwaterManual === null}
                      onClick={() => handleFeedwaterMode(false)}
                      className={[
                        'h-8 px-3 text-[12px] tracking-[0.08em] transition-colors',
                        feedwaterManual === null ? 'seg-on' : 'text-ink-2 hover:text-ink',
                      ].join(' ')}
                    >
                      AUTO
                    </button>
                    <button
                      type="button"
                      disabled={!connected}
                      aria-pressed={feedwaterManual !== null}
                      onClick={() => handleFeedwaterMode(true)}
                      className={[
                        'h-8 px-3 text-[12px] tracking-[0.08em] transition-colors',
                        feedwaterManual !== null ? 'seg-on' : 'text-ink-2 hover:text-ink',
                      ].join(' ')}
                    >
                      MANUAL
                    </button>
                  </div>
                  <div className="text-right">
                    <div className={`font-mono text-[12px] tabular-nums ${toneClass(feedwaterStatus.tone)}`}>
                      {feedwaterStatus.label}
                    </div>
                    <div className="text-[10.5px] text-ink-3">{feedwaterStatus.detail}</div>
                  </div>
                </div>
              )}
            </HelpTip>

            <div className="mt-3 grid grid-cols-3 gap-3">
              <Readout label="Manual" value={formatNumber(feedwaterSlider.value * 100, 0)} unit="% max" />
              <Readout label="Demand" value={formatNumber(manualFlow, 0)} unit="kg/s" />
              <Readout label="Design" value={formatNumber(manualDesignPct, 0)} unit="%" />
            </div>
            {feedwaterPending && (
              <p className="mt-2 text-[11px] leading-snug text-warn">
                Selected {feedwaterSelectedText}; effective demand frozen at{' '}
                {formatNumber(feedwaterStatus.effectiveDemandKgS, 0)} kg/s until the simulation runs.
              </p>
            )}

            <HelpTip tip="Manual feedwater demand is a percent of maximum feedwater flow. Maximum is 120 % of design flow, so 83 % max is about 100 % design. The slider is disabled in AUTO; use MANUAL to take direct control.">
              {(tipId) => (
                <div className="relative mt-3">
                  <div
                    aria-hidden="true"
                    className="pointer-events-none absolute inset-x-[7px] top-1/2 h-px -translate-y-1/2 bg-line-strong"
                  >
                    <div className="absolute left-[83.333%] top-1/2 h-2.5 w-px -translate-y-1/2 bg-ink-3" />
                  </div>
                  <input
                    ref={feedwaterSlider.ref}
                    aria-describedby={tipId}
                    type="range"
                    className="rod-range relative"
                    min={0}
                    max={1}
                    step={0.01}
                    value={feedwaterSlider.value}
                    disabled={!connected || feedwaterManual === null}
                    aria-label="Manual feedwater demand"
                    aria-valuetext={`${(feedwaterSlider.value * 100).toFixed(0)} % of maximum feedwater flow`}
                    onChange={feedwaterSlider.onChange}
                  />
                </div>
              )}
            </HelpTip>
            <div aria-hidden="true" className="mt-0.5 flex justify-between px-0.5 text-[10.5px] text-ink-3">
              <span>0 % max</span>
              <span>100 % design</span>
              <span>120 % design</span>
            </div>
          </section>
        </fieldset>
      </section>
    </>
  )
}

export default SecondaryControls
