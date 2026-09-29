import { describe, expect, it } from 'vitest'
import { makeFrame } from '../test/makeFrame'
import {
  DUMP_FLOW_CLOSE_KG_S,
  DUMP_FLOW_OPEN_KG_S,
  deriveDumpStatus,
  deriveFeedwaterModeStatus,
  deriveLevelStatus,
  deriveRodModeStatus,
  deriveTurbineTripStatus,
  feedwaterDemandFraction,
  feedwaterSaturation,
  isShutdownBankInserted,
  turbineTripCause,
} from './plantStatus'

describe('deriveTurbineTripStatus', () => {
  it('reports an operator-trip cause from one frame', () => {
    expect(deriveTurbineTripStatus(makeFrame(1, { turbine_trip_active: true, turbine_trip: true }))).toMatchObject({
      kind: 'operator-trip',
      label: 'TRIPPED',
      cause: 'operator trip',
      active: true,
      pending: false,
    })
  })

  it('reports SCRAM/P-4 as the turbine trip cause', () => {
    expect(
      deriveTurbineTripStatus(makeFrame(1, { turbine_trip_active: true, turbine_trip: false, scrammed: true })),
    ).toMatchObject({
      kind: 'scram-trip',
      cause: 'SCRAM (P-4)',
      active: true,
      pending: false,
    })
  })

  it('reports a running trip-clearing transient as valves closing', () => {
    expect(
      deriveTurbineTripStatus(
        makeFrame(1, { running: true, turbine_trip_active: true, turbine_trip: false, scrammed: false }),
      ),
    ).toMatchObject({
      kind: 'valves-closing',
      label: 'VALVES CLOSING',
      cause: 'valves closing after trip reset',
      active: true,
      pending: false,
    })
    expect(turbineTripCause(makeFrame(1, { turbine_trip_active: true }))).toBe('valves closing')
  })

  it('uses pending wording for paused trip and reset without frame history', () => {
    expect(
      deriveTurbineTripStatus(makeFrame(1, { running: false, turbine_trip_active: false, turbine_trip: true })),
    ).toMatchObject({
      kind: 'trip-pending',
      label: 'TRIP PENDING',
      cause: 'pending — applies when the simulation runs',
      active: false,
      pending: true,
    })

    expect(
      deriveTurbineTripStatus(
        makeFrame(1, {
          running: false,
          turbine_trip_active: true,
          turbine_trip: false,
          scrammed: false,
        }),
      ),
    ).toMatchObject({
      kind: 'reset-pending',
      label: 'RESET PENDING',
      cause: 'pending — applies when the simulation runs',
      active: true,
      pending: true,
    })
  })

  it('handles SCRAM reset with a paused effective SCRAM/P-4 trip as pending reset', () => {
    expect(
      deriveTurbineTripStatus(
        makeFrame(1, {
          running: false,
          scrammed: false,
          turbine_trip: false,
          turbine_trip_active: true,
        }),
      ),
    ).toMatchObject({
      kind: 'reset-pending',
      pending: true,
    })
  })
})

describe('deriveRodModeStatus', () => {
  it('reports manual, active AUTO and suspended AUTO modes', () => {
    expect(deriveRodModeStatus(makeFrame(1, { rod_auto: false, rod_auto_acting: false }))).toMatchObject({
      kind: 'manual',
      label: 'MANUAL',
    })
    expect(deriveRodModeStatus(makeFrame(1, { rod_auto: true, rod_auto_acting: true }))).toMatchObject({
      kind: 'auto-active',
      label: 'AUTO ACTIVE',
    })
    expect(
      deriveRodModeStatus(makeFrame(1, { rod_auto: true, rod_auto_acting: false, turbine_trip_active: true })),
    ).toMatchObject({
      kind: 'auto-suspended',
      detail: 'Automatic rod motion is suspended by turbine trip.',
    })
  })

  it('uses pending wording for paused MANUAL selection before the plant steps', () => {
    expect(
      deriveRodModeStatus(makeFrame(1, { running: false, rod_auto: false, rod_auto_acting: true })),
    ).toMatchObject({
      kind: 'pending',
      detail: 'MANUAL selected; pending — applies when the simulation runs.',
      pending: true,
    })
  })

  it('uses pending wording for paused AUTO selection without an effective suspension cause', () => {
    expect(
      deriveRodModeStatus(makeFrame(1, { running: false, rod_auto: true, rod_auto_acting: false })),
    ).toMatchObject({
      kind: 'pending',
      detail: 'AUTO selected; pending — applies when the simulation runs.',
      pending: true,
    })
  })

  it('names the queued trip that will inhibit paused AUTO on resume', () => {
    expect(
      deriveRodModeStatus(
        makeFrame(1, {
          running: false,
          rod_auto: true,
          rod_auto_acting: false,
          turbine_trip: true,
          turbine_trip_active: false,
        }),
      ),
    ).toMatchObject({
      kind: 'auto-suspended',
      label: 'AUTO INACTIVE',
      detail: 'AUTO selected; inactive; the queued trip inhibits it on resume.',
      pending: false,
    })
  })

  it('uses pending wording for a paused trip command even when AUTO was acting before the pause', () => {
    expect(
      deriveRodModeStatus(
        makeFrame(1, {
          running: false,
          rod_auto: true,
          rod_auto_acting: true,
          turbine_trip: true,
          turbine_trip_active: false,
        }),
      ),
    ).toMatchObject({
      kind: 'pending',
      detail: 'pending — applies when the simulation runs',
      pending: true,
      effectiveActing: true,
    })
  })

  it('uses pending wording for a paused SCRAM command even when AUTO was acting before the pause', () => {
    expect(
      deriveRodModeStatus(
        makeFrame(1, {
          running: false,
          rod_auto: true,
          rod_auto_acting: true,
          scrammed: true,
          turbine_trip_active: false,
        }),
      ),
    ).toMatchObject({
      kind: 'pending',
      detail: 'pending — applies when the simulation runs',
      pending: true,
      effectiveActing: true,
    })
  })

  it('does not call paused AUTO during SCRAM pending when the effective inactive state matches', () => {
    expect(
      deriveRodModeStatus(
        makeFrame(1, {
          running: false,
          rod_auto: true,
          rod_auto_acting: false,
          scrammed: true,
          turbine_trip_active: true,
        }),
      ),
    ).toMatchObject({
      kind: 'auto-suspended',
      detail: 'Automatic rod motion is suspended by SCRAM.',
      pending: false,
    })
  })

  it('uses pending wording for a paused trip reset that leaves the effective trip frozen', () => {
    expect(
      deriveRodModeStatus(
        makeFrame(1, {
          running: false,
          rod_auto: true,
          rod_auto_acting: false,
          turbine_trip: false,
          turbine_trip_active: true,
        }),
      ),
    ).toMatchObject({
      kind: 'pending',
      pending: true,
    })
  })
})

describe('feedwater status helpers', () => {
  it('converts current demand to a clipped maximum-flow fraction', () => {
    expect(feedwaterDemandFraction(makeFrame(1, { m_fw_demand: 1_001.4, m_fw_max: 2_002.8 }))).toBeCloseTo(0.5)
    expect(feedwaterDemandFraction(makeFrame(1, { m_fw_demand: 3_000, m_fw_max: 2_002.8 }))).toBe(1)
    expect(feedwaterDemandFraction(makeFrame(1, { m_fw_demand: -10, m_fw_max: 2_002.8 }))).toBe(0)
  })

  it('distinguishes AUTO saturation at zero from maximum with tolerance', () => {
    expect(feedwaterSaturation(makeFrame(1, { fw_saturated: true, m_fw_demand: 0 }))).toBe('zero')
    expect(
      feedwaterSaturation(makeFrame(1, { fw_saturated: true, m_fw_demand: 2_002.81, m_fw_max: 2_002.81 })),
    ).toBe('maximum')
    expect(
      feedwaterSaturation(makeFrame(1, { fw_saturated: true, m_fw_demand: 2_002.7, m_fw_max: 2_002.81 })),
    ).toBe('maximum')
  })

  it('reports selected/effective feedwater AUTO and MANUAL modes from one frame', () => {
    expect(
      deriveFeedwaterModeStatus(
        makeFrame(1, {
          feedwater_manual: 0.5,
          feedwater_manual_effective: 0.5,
          m_fw_demand: 1_000,
          m_fw_max: 2_000,
        }),
      ),
    ).toMatchObject({
      kind: 'manual',
      label: 'MANUAL',
      selectedMode: 'manual',
      effectiveMode: 'manual',
      selectedDemandKgS: 1_000,
      effectiveSelectedDemandKgS: 1_000,
      effectiveDemandKgS: 1_000,
    })

    expect(
      deriveFeedwaterModeStatus(
        makeFrame(1, { feedwater_manual: null, feedwater_manual_effective: null, fw_saturated: false }),
      ),
    ).toMatchObject({
      kind: 'auto',
      label: 'AUTO',
    })
  })

  it('uses manual-demand wording instead of saturation while MANUAL is effective', () => {
    expect(
      deriveFeedwaterModeStatus(
        makeFrame(1, {
          feedwater_manual: 0,
          feedwater_manual_effective: 0,
          fw_saturated: true,
          m_fw_demand: 0,
          m_fw_max: 2_000,
        }),
      ),
    ).toMatchObject({
      kind: 'manual',
      label: 'MANUAL · manual demand at zero',
      manualDemandLimit: 'zero',
      saturation: null,
    })

    expect(
      deriveFeedwaterModeStatus(
        makeFrame(1, {
          feedwater_manual: 1,
          feedwater_manual_effective: 1,
          fw_saturated: true,
          m_fw_demand: 2_000,
          m_fw_max: 2_000,
        }),
      ),
    ).toMatchObject({
      label: 'MANUAL · manual demand at maximum',
      manualDemandLimit: 'maximum',
      saturation: null,
    })
  })

  it('uses pending wording for paused AUTO to MANUAL and MANUAL to AUTO changes', () => {
    expect(
      deriveFeedwaterModeStatus(
        makeFrame(1, {
          running: false,
          feedwater_manual: 0.8,
          feedwater_manual_effective: null,
          m_fw_demand: 1_600,
          m_fw_max: 2_000,
        }),
      ),
    ).toMatchObject({
      kind: 'pending',
      pending: true,
      selectedMode: 'manual',
      effectiveMode: 'auto',
      selectedDemandKgS: 1_600,
      effectiveDemandKgS: 1_600,
    })

    expect(
      deriveFeedwaterModeStatus(
        makeFrame(2, {
          running: false,
          feedwater_manual: null,
          feedwater_manual_effective: 0.5,
          m_fw_demand: 1_000,
          m_fw_max: 2_000,
        }),
      ),
    ).toMatchObject({
      kind: 'pending',
      pending: true,
      selectedMode: 'auto',
      effectiveMode: 'manual',
    })
  })

  it('uses pending wording for paused manual feedwater demand changes and converges after one step', () => {
    expect(
      deriveFeedwaterModeStatus(
        makeFrame(1, {
          running: false,
          feedwater_manual: 0.5,
          feedwater_manual_effective: 0.8,
          m_fw_demand: 1_600,
          m_fw_max: 2_000,
        }),
      ),
    ).toMatchObject({
      kind: 'pending',
      selectedDemandKgS: 1_000,
      effectiveSelectedDemandKgS: 1_600,
      effectiveDemandKgS: 1_600,
    })

    expect(
      deriveFeedwaterModeStatus(
        makeFrame(2, {
          running: true,
          feedwater_manual: 0.5,
          feedwater_manual_effective: 0.5,
          m_fw_demand: 1_000,
          m_fw_max: 2_000,
        }),
      ),
    ).toMatchObject({
      kind: 'manual',
      pending: false,
      selectedDemandKgS: 1_000,
      effectiveSelectedDemandKgS: 1_000,
      effectiveDemandKgS: 1_000,
    })
  })
})

describe('deriveDumpStatus', () => {
  it('uses a one-frame open threshold for readouts', () => {
    expect(deriveDumpStatus(makeFrame(1, { m_dump: DUMP_FLOW_OPEN_KG_S }))).toMatchObject({ open: false })
    expect(deriveDumpStatus(makeFrame(1, { m_dump: DUMP_FLOW_OPEN_KG_S + 0.01 }))).toMatchObject({ open: true })
  })

  it('uses explicit open/close hysteresis inputs for events', () => {
    expect(deriveDumpStatus(makeFrame(1, { m_dump: 1.01 }), { wasOpen: false })).toMatchObject({ open: true })
    expect(deriveDumpStatus(makeFrame(2, { m_dump: 0.99 }), { wasOpen: true })).toMatchObject({ open: true })
    expect(deriveDumpStatus(makeFrame(3, { m_dump: DUMP_FLOW_CLOSE_KG_S - 0.01 }), { wasOpen: true })).toMatchObject({
      open: false,
    })
  })
})

describe('deriveLevelStatus', () => {
  it('classifies SG collapsed level bands and level error from one frame', () => {
    const normal = deriveLevelStatus(makeFrame(1, { level_sg: 0.5, level_setpoint: 0.55 }))
    expect(normal).toMatchObject({
      band: 'green',
      outsideModelValidity: false,
    })
    expect(normal.error).toBeCloseTo(0.05)
    expect(deriveLevelStatus(makeFrame(1, { level_sg: 0.39 }))).toMatchObject({ band: 'amber' })
    expect(deriveLevelStatus(makeFrame(1, { level_sg: 0.91 }))).toMatchObject({ band: 'red' })
    expect(deriveLevelStatus(makeFrame(1, { level_sg: 0.29 }))).toMatchObject({
      band: 'red',
      outsideModelValidity: true,
    })
  })

  describe('isShutdownBankInserted', () => {
    it('reports a retained shutdown bank below the withdrawn tolerance', () => {
      expect(isShutdownBankInserted(makeFrame(1, { shutdown_position: 1 }))).toBe(false)
      expect(isShutdownBankInserted(makeFrame(1, { shutdown_position: 0.989 }))).toBe(true)
      expect(isShutdownBankInserted(makeFrame(1, { shutdown_position: 0 }))).toBe(true)
    })
  })
})
