import { describe, expect, it } from 'vitest'
import { makeFrame } from '../test/makeFrame'
import {
  deriveFeedwaterModeStatus,
  deriveRodModeStatus,
  deriveTurbineTripStatus,
  feedwaterDemandFraction,
  findLastRunningFrame,
} from './controlStatus'

describe('deriveRodModeStatus', () => {
  it('reports manual mode when the operator-selected mode is MANUAL', () => {
    const status = deriveRodModeStatus(makeFrame(1, { rod_auto: false, rod_auto_acting: false }))

    expect(status.kind).toBe('manual')
    expect(status.label).toBe('MANUAL')
  })

  it('reports active AUTO when the automatic controller is acting', () => {
    const status = deriveRodModeStatus(makeFrame(1, { rod_auto: true, rod_auto_acting: true }))

    expect(status.kind).toBe('auto-active')
    expect(status.label).toBe('AUTO ACTIVE')
  })

  it('reports AUTO suspended by SCRAM or turbine trip while those causes are latched', () => {
    expect(
      deriveRodModeStatus(
        makeFrame(1, { rod_auto: true, rod_auto_acting: false, scrammed: true }),
      ),
    ).toMatchObject({
      kind: 'auto-suspended',
      label: 'AUTO SUSPENDED',
      detail: 'Automatic rod motion is suspended by SCRAM.',
    })

    expect(
      deriveRodModeStatus(
        makeFrame(1, { rod_auto: true, rod_auto_acting: false, turbine_trip: true, turbine_trip_active: true }),
      ),
    ).toMatchObject({
      kind: 'auto-suspended',
      detail: 'Automatic rod motion is suspended by turbine trip.',
    })
  })

  it('uses pending wording for paused AUTO selection before the plant steps', () => {
    const status = deriveRodModeStatus(
      makeFrame(1, { running: false, rod_auto: true, rod_auto_acting: false }),
    )

    expect(status.kind).toBe('pending')
    expect(status.detail).toBe('pending — applies when the simulation runs')
  })

  it('uses pending wording for paused MANUAL selection before the plant steps', () => {
    const status = deriveRodModeStatus(
      makeFrame(1, { running: false, rod_auto: false, rod_auto_acting: true }),
    )

    expect(status.kind).toBe('pending')
    expect(status.detail).toBe('pending — applies when the simulation runs')
  })

  it('uses pending wording for paused turbine trip and reset sequences', () => {
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
    })

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
      detail: 'pending — applies when the simulation runs',
    })
  })

  it('uses pending wording for paused SCRAM and reset SCRAM sequences', () => {
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
    })

    expect(
      deriveRodModeStatus(
        makeFrame(1, {
          running: false,
          rod_auto: true,
          rod_auto_acting: false,
          scrammed: false,
          turbine_trip_active: true,
        }),
      ),
    ).toMatchObject({
      kind: 'pending',
      detail: 'pending — applies when the simulation runs',
    })
  })
})

describe('deriveTurbineTripStatus', () => {
  it('reports an operator-trip cause from the effective trip latch', () => {
    const status = deriveTurbineTripStatus(
      makeFrame(1, { turbine_trip_active: true, turbine_trip: true }),
    )

    expect(status).toMatchObject({
      kind: 'operator-trip',
      label: 'TRIPPED',
      cause: 'operator trip',
      active: true,
    })
  })

  it('reports SCRAM/P-4 when SCRAM is the effective turbine-trip cause', () => {
    const status = deriveTurbineTripStatus(
      makeFrame(1, { turbine_trip_active: true, turbine_trip: false, scrammed: true }),
    )

    expect(status).toMatchObject({
      kind: 'scram-trip',
      cause: 'SCRAM (P-4)',
      active: true,
    })
  })

  it('reports trip clearing when no latch still explains an active trip', () => {
    const status = deriveTurbineTripStatus(
      makeFrame(1, { turbine_trip_active: true, turbine_trip: false, scrammed: false }),
    )

    expect(status).toMatchObject({
      kind: 'trip-clearing',
      cause: 'trip clearing',
      active: true,
    })
  })

  it('uses pending wording for a paused operator trip before the plant steps', () => {
    const status = deriveTurbineTripStatus(
      makeFrame(1, { running: false, turbine_trip_active: false, turbine_trip: true }),
    )

    expect(status).toMatchObject({
      kind: 'trip-pending',
      label: 'TRIP PENDING',
      cause: 'pending — applies when the simulation runs',
      active: false,
    })
  })

  it('uses pending wording for a paused trip reset before the plant steps', () => {
    const status = deriveTurbineTripStatus(
      makeFrame(1, {
        running: false,
        turbine_trip_active: true,
        turbine_trip: false,
        scrammed: false,
      }),
    )

    expect(status).toMatchObject({
      kind: 'clear-pending',
      label: 'TRIP CLEARING',
      cause: 'pending — applies when the simulation runs',
      active: true,
    })
  })
})

describe('feedwater status helpers', () => {
  it('converts current demand to a clipped maximum-flow fraction', () => {
    expect(feedwaterDemandFraction(makeFrame(1, { m_fw_demand: 1_001.4, m_fw_max: 2_002.8 }))).toBeCloseTo(0.5)
    expect(feedwaterDemandFraction(makeFrame(1, { m_fw_demand: 3_000, m_fw_max: 2_002.8 }))).toBe(1)
    expect(feedwaterDemandFraction(makeFrame(1, { m_fw_demand: -10, m_fw_max: 2_002.8 }))).toBe(0)
  })

  it('distinguishes AUTO saturation at zero from maximum', () => {
    expect(
      deriveFeedwaterModeStatus(
        makeFrame(1, { feedwater_manual: null, fw_saturated: true, m_fw_demand: 0 }),
      ),
    ).toMatchObject({
      kind: 'auto-saturated-zero',
      label: 'AUTO · saturated at zero',
    })

    expect(
      deriveFeedwaterModeStatus(
        makeFrame(1, { feedwater_manual: null, fw_saturated: true, m_fw_demand: 2_002.8, m_fw_max: 2_002.8 }),
      ),
    ).toMatchObject({
      kind: 'auto-saturated-maximum',
      label: 'AUTO · saturated at maximum',
    })
  })

  it('reports manual feedwater mode separately from AUTO saturation', () => {
    expect(
      deriveFeedwaterModeStatus(
        makeFrame(1, { feedwater_manual: 1, fw_saturated: true, m_fw_demand: 2_002.8 }),
      ),
    ).toMatchObject({
      kind: 'manual',
      label: 'MANUAL',
    })
  })

  it('uses pending wording for paused AUTO to MANUAL feedwater selection', () => {
    const effective = makeFrame(1, {
      running: true,
      feedwater_manual: null,
      m_fw_demand: 1_600,
      m_fw_max: 2_000,
    })
    const selectedManual = makeFrame(2, {
      running: false,
      feedwater_manual: 0.8,
      m_fw_demand: 1_600,
      m_fw_max: 2_000,
    })

    expect(deriveFeedwaterModeStatus(selectedManual, effective)).toMatchObject({
      kind: 'pending',
      label: 'PENDING',
      detail: 'pending — applies when the simulation runs',
      selectedMode: 'manual',
      effectiveMode: 'auto',
      selectedDemandKgS: 1_600,
      effectiveDemandKgS: 1_600,
    })
  })

  it('uses pending wording for paused manual feedwater demand changes', () => {
    const effective = makeFrame(1, {
      running: true,
      feedwater_manual: 0.8,
      m_fw_demand: 1_600,
      m_fw_max: 2_000,
    })
    const changedDemand = makeFrame(2, {
      running: false,
      feedwater_manual: 0.5,
      m_fw_demand: 1_600,
      m_fw_max: 2_000,
    })

    expect(deriveFeedwaterModeStatus(changedDemand, effective)).toMatchObject({
      kind: 'pending',
      selectedMode: 'manual',
      effectiveMode: 'manual',
      selectedDemandKgS: 1_000,
      effectiveDemandKgS: 1_600,
    })
  })

  it('uses pending wording for paused MANUAL to AUTO feedwater selection', () => {
    const effective = makeFrame(1, {
      running: true,
      feedwater_manual: 0.5,
      m_fw_demand: 1_000,
      m_fw_max: 2_000,
    })
    const selectedAuto = makeFrame(2, {
      running: false,
      feedwater_manual: null,
      m_fw_demand: 1_000,
      m_fw_max: 2_000,
    })

    expect(deriveFeedwaterModeStatus(selectedAuto, effective)).toMatchObject({
      kind: 'pending',
      selectedMode: 'auto',
      effectiveMode: 'manual',
      selectedDemandKgS: null,
      effectiveDemandKgS: 1_000,
    })
  })

  it('keeps paused feedwater MANUAL active when command and last-stepped demand match', () => {
    const effective = makeFrame(1, {
      running: true,
      feedwater_manual: 0.5,
      m_fw_demand: 1_000,
      m_fw_max: 2_000,
    })
    const pausedSame = makeFrame(2, {
      running: false,
      feedwater_manual: 0.5,
      m_fw_demand: 1_000,
      m_fw_max: 2_000,
    })

    expect(deriveFeedwaterModeStatus(pausedSame, effective)).toMatchObject({
      kind: 'manual',
      label: 'MANUAL',
    })
  })

  it('finds the newest running frame for paused pending comparisons', () => {
    const runningAuto = makeFrame(1, { running: true, feedwater_manual: null })
    const pausedManual = makeFrame(2, { running: false, feedwater_manual: 0.8 })

    expect(findLastRunningFrame([runningAuto, pausedManual], pausedManual)).toBe(runningAuto)
    expect(findLastRunningFrame([runningAuto], runningAuto)).toBe(runningAuto)
    expect(findLastRunningFrame([], null)).toBeNull()
  })
})
