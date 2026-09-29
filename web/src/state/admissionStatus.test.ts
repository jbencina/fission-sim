import { describe, expect, it } from 'vitest'
import { makeFrame } from '../test/makeFrame'
import {
  TURBINE_ADMISSION_CLOSED_FRACTION,
  deriveAdmissionStatus,
  isTurbineAdmissionClosed,
} from './admissionStatus'

describe('isTurbineAdmissionClosed', () => {
  it('uses the 0.5 % closed-valve tolerance', () => {
    expect(isTurbineAdmissionClosed(TURBINE_ADMISSION_CLOSED_FRACTION)).toBe(true)
    expect(isTurbineAdmissionClosed(TURBINE_ADMISSION_CLOSED_FRACTION + 0.0001)).toBe(false)
  })
})

describe('deriveAdmissionStatus', () => {
  it('marks a paused selected demand as pending until the simulation runs', () => {
    expect(
      deriveAdmissionStatus(
        makeFrame(1, {
          running: false,
          turbine_load_demand: 0,
          turbine_load_demand_effective: 1,
        }),
      ),
    ).toMatchObject({
      selectedDemand: 0,
      effectiveDemand: 1,
      demandPending: true,
    })
  })

  it('does not call a running demand mismatch pending', () => {
    expect(
      deriveAdmissionStatus(
        makeFrame(1, {
          running: true,
          turbine_load_demand: 0,
          turbine_load_demand_effective: 1,
        }),
      ),
    ).toMatchObject({
      demandPending: false,
    })
  })

  it('classifies trip closure and reset availability from actual admission', () => {
    expect(
      deriveAdmissionStatus(
        makeFrame(1, {
          turbine_trip_active: true,
          turbine_trip: true,
          turbine_load: TURBINE_ADMISSION_CLOSED_FRACTION + 0.01,
        }),
      ),
    ).toMatchObject({
      tripState: 'trip-active-closing',
      admissionClosed: false,
      resetBlocked: true,
    })

    expect(
      deriveAdmissionStatus(
        makeFrame(1, {
          turbine_trip_active: true,
          turbine_trip: true,
          turbine_load: TURBINE_ADMISSION_CLOSED_FRACTION,
        }),
      ),
    ).toMatchObject({
      tripState: 'trip-active-closed',
      admissionClosed: true,
      resetBlocked: false,
    })
  })

  it('uses reset-pending state when a paused cleared trip is still effective', () => {
    expect(
      deriveAdmissionStatus(
        makeFrame(1, {
          running: false,
          turbine_trip_active: true,
          turbine_trip: false,
          scrammed: false,
          turbine_load: 0,
        }),
      ),
    ).toMatchObject({
      tripState: 'reset-pending',
      admissionClosed: true,
      resetBlocked: false,
    })
  })
})
