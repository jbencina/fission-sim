import { describe, expect, it } from 'vitest'
import { makeFrame } from '../test/makeFrame'
import {
  criticalityWord,
  describeLoop,
  describeSchematicState,
  describeSecondaryState,
  turbineTripCause,
  turbineTripStatus,
} from './loopState'

describe('criticalityWord', () => {
  it('names the sign of the displayed reactivity', () => {
    expect(criticalityWord(0.04)).toBe('critical')
    expect(criticalityWord(-0.04)).toBe('critical')
    expect(criticalityWord(12)).toBe('supercritical')
    expect(criticalityWord(-5000)).toBe('subcritical')
  })
})

describe('describeLoop', () => {
  it('waits for telemetry', () => {
    expect(describeLoop(null)).toBe('waiting for telemetry')
  })

  it('is steady when core power and steam generator heat match', () => {
    const f = makeFrame(1, { rho_total: 0, power_thermal: 3e9, Q_sg: 3e9 })
    expect(describeLoop(f)).toBe('critical, steady')
  })

  it('is heating up when the core makes more heat than the steam generator removes', () => {
    const f = makeFrame(1, { rho_total: 1e-4, power_thermal: 3.3e9, Q_sg: 3e9 })
    expect(describeLoop(f)).toBe('supercritical, heating up')
  })

  it('is cooling after a SCRAM', () => {
    const f = makeFrame(1, { rho_total: -0.05, power_thermal: 7e7, Q_sg: 8e8 })
    expect(describeLoop(f)).toBe('subcritical, cooling')
  })

  it('does not divide by zero when no heat is removed', () => {
    const f = makeFrame(1, { rho_total: 0, power_thermal: 1e6, Q_sg: 0 })
    expect(describeLoop(f)).toBe('critical, heating up')
  })
})

describe('turbineTripCause', () => {
  it('uses pending-command wording for an operator turbine trip', () => {
    const f = makeFrame(1, { turbine_trip_active: true, turbine_trip: true, scrammed: false })
    expect(turbineTripCause(f)).toBe('operator trip')
  })

  it('names the SCRAM P-4 interlock when SCRAM, not the operator latch, tripped the turbine', () => {
    const f = makeFrame(1, { turbine_trip_active: true, turbine_trip: false, scrammed: true })
    expect(turbineTripCause(f)).toBe('SCRAM (P-4)')
  })

  it('calls an active trip with no latch a clearing trip', () => {
    const f = makeFrame(1, { turbine_trip_active: true, turbine_trip: false, scrammed: false })
    expect(turbineTripCause(f)).toBe('trip clearing')
  })

  it('is null when the effective turbine trip is clear', () => {
    const f = makeFrame(1, { turbine_trip_active: false, turbine_trip: true, scrammed: true })
    expect(turbineTripCause(f)).toBeNull()
  })
})

describe('turbineTripStatus', () => {
  it('shows an operator trip selected while paused as pending', () => {
    const f = makeFrame(1, {
      running: false,
      turbine_trip_active: false,
      turbine_trip: true,
      scrammed: false,
    })
    expect(turbineTripStatus(f)).toEqual({
      kind: 'pending-trip',
      label: 'trip pending — applies when the simulation runs',
    })
  })

  it('shows SCRAM selected while paused as a pending turbine trip', () => {
    const f = makeFrame(1, {
      running: false,
      turbine_trip_active: false,
      turbine_trip: false,
      scrammed: true,
    })
    expect(turbineTripStatus(f)).toEqual({
      kind: 'pending-trip',
      label: 'trip pending — applies when the simulation runs',
    })
  })

  it('shows an operator trip reset while paused as pending', () => {
    const f = makeFrame(1, {
      running: false,
      turbine_trip_active: true,
      turbine_trip: false,
      scrammed: false,
    })
    expect(turbineTripStatus(f)).toEqual({
      kind: 'pending-reset',
      label: 'trip reset pending — applies when the simulation runs',
    })
  })

  it('shows SCRAM reset while paused as a pending trip reset', () => {
    const f = makeFrame(1, {
      running: false,
      turbine_trip_active: true,
      turbine_trip: false,
      scrammed: false,
    })
    expect(turbineTripStatus(f)).toEqual({
      kind: 'pending-reset',
      label: 'trip reset pending — applies when the simulation runs',
    })
  })

  it('keeps effective trip causes when running', () => {
    const operatorTrip = makeFrame(1, {
      running: true,
      turbine_trip_active: true,
      turbine_trip: true,
      scrammed: false,
    })
    const scramTrip = makeFrame(1, {
      running: true,
      turbine_trip_active: true,
      turbine_trip: false,
      scrammed: true,
    })
    expect(turbineTripStatus(operatorTrip)).toEqual({ kind: 'active', label: 'operator trip' })
    expect(turbineTripStatus(scramTrip)).toEqual({ kind: 'active', label: 'SCRAM (P-4)' })
  })
})

describe('describeSecondaryState', () => {
  it('has no secondary phrases at steady full-power design conditions', () => {
    expect(describeSecondaryState(makeFrame())).toEqual([])
  })

  it('adds turbine trip, steam dump and low SG level phrases', () => {
    const f = makeFrame(1, { turbine_trip_active: true, m_dump: 25, level_sg: 0.39 })
    expect(describeSecondaryState(f)).toEqual(['turbine tripped', 'steam dump open', 'SG level low'])
  })

  it('adds pending turbine trip wording while paused', () => {
    const f = makeFrame(1, {
      running: false,
      turbine_trip_active: false,
      turbine_trip: true,
      scrammed: false,
    })
    expect(describeSecondaryState(f)).toEqual(['trip pending — applies when the simulation runs'])
  })

  it('adds pending reset wording while paused', () => {
    const f = makeFrame(1, {
      running: false,
      turbine_trip_active: true,
      turbine_trip: false,
      scrammed: false,
    })
    expect(describeSecondaryState(f)).toEqual(['trip reset pending — applies when the simulation runs'])
  })

  it('adds a high SG level phrase outside the illustrative 40-60 percent band', () => {
    const f = makeFrame(1, { level_sg: 0.61 })
    expect(describeSecondaryState(f)).toEqual(['SG level high'])
  })

  it('treats the illustrative 40 and 60 percent band edges as normal', () => {
    expect(describeSecondaryState(makeFrame(1, { level_sg: 0.4 }))).toEqual([])
    expect(describeSecondaryState(makeFrame(1, { level_sg: 0.6 }))).toEqual([])
  })
})

describe('describeSchematicState', () => {
  it('keeps the primary-only sentence before telemetry', () => {
    expect(describeSchematicState(null)).toBe('waiting for telemetry')
  })

  it('appends secondary state phrases after the primary loop sentence', () => {
    const f = makeFrame(1, {
      rho_total: 0,
      power_thermal: 3e9,
      Q_sg: 3e9,
      turbine_trip_active: true,
      m_dump: 10,
      level_sg: 0.38,
    })
    expect(describeSchematicState(f)).toBe('critical, steady · turbine tripped · steam dump open · SG level low')
  })
})
