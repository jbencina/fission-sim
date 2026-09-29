import { describe, expect, it } from 'vitest'
import type { Frame } from '../types/telemetry'
import { makeFrame } from '../test/makeFrame'
import { detectEvents } from './events'

const texts = (prev: Frame | null, next: Frame) => detectEvents(prev, next).map((e) => `${e.level}:${e.text}`)

describe('detectEvents', () => {
  it('reports the first frame as a connection', () => {
    expect(texts(null, makeFrame(3))).toEqual(['info:Telemetry link established'])
  })

  it('reports nothing for an unchanged frame', () => {
    expect(texts(makeFrame(1), makeFrame(2))).toEqual([])
  })

  it('reports a reset when time moves backward, and nothing else', () => {
    const prev = makeFrame(50, { scrammed: true, rod_position: 0 })
    const next = makeFrame(0.1, { scrammed: false, rod_position: 0.5 })
    expect(texts(prev, next)).toEqual(['info:Simulation reset to the design state'])
  })

  it('reports the SCRAM latch and the banks reaching full insertion once', () => {
    const a = makeFrame(1)
    const b = makeFrame(2, { scrammed: true, rod_position: 0.4 })
    const c = makeFrame(3, { scrammed: true, rod_position: 0.004 })
    const d = makeFrame(4, { scrammed: true, rod_position: 0 })
    expect(texts(a, b)).toEqual(['alarm:SCRAM latched, both banks dropping'])
    expect(texts(b, c)).toEqual(['alarm:Both banks fully inserted, about −7,000 pcm'])
    expect(texts(c, d)).toEqual([])
  })

  it('does not repeat full insertion when the page joins after a SCRAM', () => {
    const a = makeFrame(1, { scrammed: true, rod_position: 0 })
    const b = makeFrame(2, { scrammed: true, rod_position: 0 })
    expect(texts(null, a)).toEqual(['info:Telemetry link established'])
    expect(texts(a, b)).toEqual([])
  })

  it('reports a SCRAM reset', () => {
    const a = makeFrame(1, { scrammed: true, rod_position: 0 })
    const b = makeFrame(2, { scrammed: false, rod_position: 0 })
    expect(texts(a, b)).toEqual(['info:SCRAM reset, control bank back to command'])
  })

  it('reports effective turbine trips with operator, SCRAM/P-4 and clearing causes', () => {
    expect(
      texts(
        makeFrame(1),
        makeFrame(2, { turbine_trip: true, turbine_trip_active: true }),
      ),
    ).toEqual(['alarm:Turbine trip active: operator trip'])

    expect(
      texts(
        makeFrame(1, { scrammed: true }),
        makeFrame(2, { scrammed: true, turbine_trip_active: true }),
      ),
    ).toEqual(['alarm:Turbine trip active: SCRAM (P-4)'])

    expect(texts(makeFrame(1), makeFrame(2, { turbine_trip_active: true }))).toEqual([
      'alarm:Turbine trip active: trip clearing',
    ])
  })

  it('reports an effective turbine trip clearing separately from the latch reset', () => {
    const before = makeFrame(1, {
      turbine_trip: true,
      turbine_trip_active: true,
      turbine_load_demand: 0.55,
    })
    const after = makeFrame(2, {
      turbine_trip: false,
      turbine_trip_active: false,
      turbine_load_demand: 0,
    })
    expect(texts(before, after)).toEqual([
      'info:Turbine trip cleared',
      'info:Turbine trip latch reset; admission demand set to 0 %',
      'info:Turbine admission demand set to 0 %',
    ])
  })

  it('labels paused turbine trip and reset commands as pending instead of claiming an effective cause', () => {
    expect(
      texts(
        makeFrame(1, { running: false, turbine_trip: false, turbine_trip_active: false }),
        makeFrame(2, { running: false, turbine_trip: true, turbine_trip_active: false }),
      ),
    ).toEqual(['warn:Turbine trip selected (pending — applies when the simulation runs)'])

    expect(
      texts(
        makeFrame(1, {
          running: false,
          turbine_trip: true,
          turbine_trip_active: true,
          turbine_load_demand: 0.5,
        }),
        makeFrame(2, {
          running: false,
          turbine_trip: false,
          turbine_trip_active: true,
          turbine_load_demand: 0,
        }),
      ),
    ).toEqual([
      'info:Turbine trip latch reset; admission demand set to 0 % (pending — applies when the simulation runs)',
      'info:Turbine admission demand set to 0 %',
    ])
  })

  it('reports steam dump opening and closing at 1 kg/s', () => {
    expect(texts(makeFrame(1, { m_dump: 1 }), makeFrame(2, { m_dump: 1.01 }))).toEqual([
      'warn:Steam dump opened',
    ])
    expect(texts(makeFrame(1, { m_dump: 2 }), makeFrame(2, { m_dump: 1 }))).toEqual([
      'info:Steam dump closed',
    ])
  })

  it('reports pause, resume, speed and rod command changes', () => {
    expect(texts(makeFrame(1), makeFrame(2, { running: false }))).toEqual(['info:Paused'])
    expect(texts(makeFrame(1, { running: false }), makeFrame(2))).toEqual(['info:Resumed'])
    expect(texts(makeFrame(1), makeFrame(2, { speed: 5 }))).toEqual(['info:Speed set to 5×'])
    expect(texts(makeFrame(1), makeFrame(2, { rod_command: 0.7 }))).toEqual(['info:Rod command set to 70 %'])
  })

  it('reports turbine admission demand and SG level setpoint changes', () => {
    expect(texts(makeFrame(1), makeFrame(2, { turbine_load_demand: 0.75 }))).toEqual([
      'info:Turbine admission demand set to 75 %',
    ])
    expect(texts(makeFrame(1), makeFrame(2, { level_setpoint: 0.55 }))).toEqual([
      'info:SG level setpoint set to 55 %',
    ])
  })

  it('reports rod AUTO/MANUAL changes and running-only automatic suspension', () => {
    expect(texts(makeFrame(1, { rod_auto: false }), makeFrame(2, { rod_auto: true, rod_auto_acting: true }))).toEqual([
      'info:Rod control set to AUTO',
    ])
    expect(texts(makeFrame(1, { rod_auto: true }), makeFrame(2, { rod_auto: false }))).toEqual([
      'info:Rod control set to MANUAL',
    ])
    expect(
      texts(
        makeFrame(1, { rod_auto: true, rod_auto_acting: true }),
        makeFrame(2, { rod_auto: true, rod_auto_acting: false }),
      ),
    ).toEqual(['warn:Automatic rod control suspended'])
    expect(
      texts(
        makeFrame(1, { rod_auto: true, rod_auto_acting: false }),
        makeFrame(2, { rod_auto: true, rod_auto_acting: true }),
      ),
    ).toEqual(['info:Automatic rod control resumed'])
  })

  it('labels paused rod AUTO as pending and does not log automatic suspension while paused', () => {
    expect(
      texts(
        makeFrame(1, { running: false, rod_auto: false, rod_auto_acting: false }),
        makeFrame(2, { running: false, rod_auto: true, rod_auto_acting: false }),
      ),
    ).toEqual(['info:Rod control set to AUTO (pending — applies when the simulation runs)'])

    expect(
      texts(
        makeFrame(1, { running: false, rod_auto: true, rod_auto_acting: true }),
        makeFrame(2, { running: false, rod_auto: true, rod_auto_acting: false }),
      ),
    ).toEqual([])
  })

  it('reports feedwater mode changes and demand saturation states', () => {
    expect(texts(makeFrame(1, { feedwater_manual: null }), makeFrame(2, { feedwater_manual: 0.4 }))).toEqual([
      'info:Feedwater set to MANUAL (40 % max)',
    ])
    expect(texts(makeFrame(1, { feedwater_manual: 0.4 }), makeFrame(2, { feedwater_manual: null }))).toEqual([
      'info:Feedwater set to AUTO',
    ])
    expect(texts(makeFrame(1), makeFrame(2, { fw_saturated: true, m_fw_demand: 0 }))).toEqual([
      'warn:Feedwater demand saturated at zero',
    ])
    expect(
      texts(makeFrame(1), makeFrame(2, { fw_saturated: true, m_fw_demand: 2_002.81 })),
    ).toEqual(['warn:Feedwater demand saturated at maximum'])
    expect(
      texts(
        makeFrame(1, { fw_saturated: true, m_fw_demand: 0 }),
        makeFrame(2, { fw_saturated: false, m_fw_demand: 100 }),
      ),
    ).toEqual(['info:Feedwater demand saturation cleared'])
  })

  it('reports a model-limit halt as an alarm', () => {
    expect(texts(makeFrame(1), makeFrame(2, { model_limit: 'hot-leg water reached boiling' }))).toEqual([
      'alarm:Halted: hot-leg water reached boiling',
    ])
  })

  it('reports a pressure band crossing and the return to normal, never twice in a row', () => {
    const ok = makeFrame(1, { P_primary_MPa: 15.5 })
    const low = makeFrame(2, { P_primary_MPa: 13.9 })
    const lower = makeFrame(3, { P_primary_MPa: 13.5 })
    const back = makeFrame(4, { P_primary_MPa: 14.2 })
    expect(texts(ok, low)).toEqual(['warn:Primary pressure below 14.0 MPa'])
    expect(texts(low, lower)).toEqual([])
    expect(texts(lower, back)).toEqual(['info:Primary pressure back in its normal band'])
    expect(texts(ok, makeFrame(2, { P_primary_MPa: 11.5 }))).toEqual(['alarm:Primary pressure below 12.0 MPa'])
    expect(texts(ok, makeFrame(2, { P_primary_MPa: 17.5 }))).toEqual(['warn:Primary pressure above 17.0 MPa'])
  })

  it('reports fuel temperature and reactivity band crossings', () => {
    expect(texts(makeFrame(1), makeFrame(2, { T_fuel: 1450 }))).toEqual(['warn:Fuel temperature above 1,400 K'])
    expect(texts(makeFrame(1), makeFrame(2, { rho_total: 2.5e-3 }))).toEqual(['alarm:Total reactivity above 200 pcm'])
  })

  it('reports steam-pressure and SG-level band crossings', () => {
    const normal = makeFrame(1, { P_steam_MPa: 6.9, level_sg: 0.5 })
    expect(texts(normal, makeFrame(2, { P_steam_MPa: 7.7 }))).toEqual([
      'warn:Steam pressure above 7.6 MPa',
    ])
    expect(texts(normal, makeFrame(2, { P_steam_MPa: 8.3 }))).toEqual([
      'alarm:Steam pressure above 8.2 MPa',
    ])
    expect(texts(normal, makeFrame(2, { P_steam_MPa: 3.4 }))).toEqual([
      'alarm:Steam pressure below 3.5 MPa',
    ])
    expect(texts(makeFrame(1, { P_steam_MPa: 7.7 }), normal)).toEqual([
      'info:Steam pressure back in its normal band',
    ])

    expect(texts(normal, makeFrame(2, { level_sg: 0.39 }))).toEqual([
      'warn:SG collapsed liquid fraction below 40 %',
    ])
    expect(texts(normal, makeFrame(2, { level_sg: 0.91 }))).toEqual([
      'alarm:SG collapsed liquid fraction above 90 %',
    ])
    expect(texts(makeFrame(1, { level_sg: 0.61 }), normal)).toEqual([
      'info:SG collapsed liquid fraction back in its normal band',
    ])
  })
})
