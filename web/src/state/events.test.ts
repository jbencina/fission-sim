import { describe, expect, it } from 'vitest'
import type { Frame } from '../types/telemetry'
import { makeFrame } from '../test/makeFrame'
import { type EventTracker, detectEvents, initialEventTracker } from './events'

function detectionTexts(prev: Frame | null, next: Frame, tracker?: EventTracker): string[] {
  return detectEvents(prev, next, tracker).events.map((e) => `${e.level}:${e.text}`)
}

function runFrames(frames: Frame[]): { texts: string[]; tracker: EventTracker } {
  let prev: Frame | null = null
  let tracker = initialEventTracker()
  const texts: string[] = []
  for (const frame of frames) {
    const result = detectEvents(prev, frame, tracker)
    texts.push(...result.events.map((event) => `${event.level}:${event.text}`))
    tracker = result.tracker
    prev = frame
  }
  return { texts, tracker }
}

describe('detectEvents', () => {
  it('reports the first frame as a connection', () => {
    expect(detectionTexts(null, makeFrame(3))).toEqual(['info:Telemetry link established'])
  })

  it('reports nothing for an unchanged frame', () => {
    expect(detectionTexts(makeFrame(1), makeFrame(2))).toEqual([])
  })

  it('reports a reset when time moves backward, and nothing else', () => {
    const prev = makeFrame(50, { scrammed: true, rod_position: 0 })
    const next = makeFrame(0.1, { scrammed: false, rod_position: 0.5 })
    expect(detectionTexts(prev, next)).toEqual(['info:Simulation reset to the design state'])
  })

  it('reports the SCRAM latch and the banks reaching full insertion once', () => {
    const a = makeFrame(1)
    const b = makeFrame(2, { scrammed: true, rod_position: 0.4 })
    const c = makeFrame(3, { scrammed: true, rod_position: 0.004 })
    const d = makeFrame(4, { scrammed: true, rod_position: 0 })
    expect(detectionTexts(a, b)).toEqual(['alarm:SCRAM latched, both banks dropping'])
    expect(detectionTexts(b, c)).toEqual(['alarm:Both banks fully inserted, about −7,000 pcm'])
    expect(detectionTexts(c, d)).toEqual([])
  })

  it('does not repeat full insertion when the page joins after a SCRAM', () => {
    const a = makeFrame(1, { scrammed: true, rod_position: 0 })
    const b = makeFrame(2, { scrammed: true, rod_position: 0 })
    expect(detectionTexts(null, a)).toEqual(['info:Telemetry link established'])
    expect(detectionTexts(a, b)).toEqual([])
  })

  it('reports a SCRAM reset', () => {
    const a = makeFrame(1, { scrammed: true, rod_position: 0 })
    const b = makeFrame(2, { scrammed: false, rod_position: 0 })
    expect(detectionTexts(a, b)).toEqual(['info:SCRAM reset, control bank back to command'])
  })

  it('reports effective turbine trips with operator, SCRAM/P-4 and valves-closing causes', () => {
    expect(detectionTexts(makeFrame(1), makeFrame(2, { turbine_trip: true, turbine_trip_active: true }))).toEqual([
      'alarm:Turbine trip active: operator trip',
    ])

    expect(detectionTexts(makeFrame(1, { scrammed: true }), makeFrame(2, { scrammed: true, turbine_trip_active: true }))).toEqual([
      'alarm:Turbine trip active: SCRAM (P-4)',
    ])

    expect(detectionTexts(makeFrame(1), makeFrame(2, { turbine_trip_active: true }))).toEqual([
      'alarm:Turbine trip active: valves closing after trip reset',
    ])
  })

  it('reports an effective turbine trip clearing separately from the latch reset', () => {
    const before = makeFrame(1, {
      turbine_trip: true,
      turbine_trip_active: true,
      turbine_load_demand: 0.55,
      turbine_load_demand_effective: 0.55,
    })
    const after = makeFrame(2, {
      turbine_trip: false,
      turbine_trip_active: false,
      turbine_load_demand: 0,
      turbine_load_demand_effective: 0,
    })
    expect(detectionTexts(before, after)).toEqual([
      'info:Turbine trip cleared',
      'info:Turbine trip latch reset; admission demand set to 0 %',
      'info:Turbine admission demand set to 0 %',
    ])
  })

  it('labels paused turbine trip and reset commands as pending instead of claiming an effective cause', () => {
    expect(
      detectionTexts(
        makeFrame(1, { running: false, turbine_trip: false, turbine_trip_active: false }),
        makeFrame(2, { running: false, turbine_trip: true, turbine_trip_active: false }),
      ),
    ).toEqual(['warn:Turbine trip selected (pending — applies when the simulation runs)'])

    expect(
      detectionTexts(
        makeFrame(1, {
          running: false,
          turbine_trip: true,
          turbine_trip_active: true,
          turbine_load_demand: 0.5,
          turbine_load_demand_effective: 0.5,
        }),
        makeFrame(2, {
          running: false,
          turbine_trip: false,
          turbine_trip_active: true,
          turbine_load_demand: 0,
          turbine_load_demand_effective: 0.5,
        }),
      ),
    ).toEqual([
      'info:Turbine trip latch reset; admission demand set to 0 % (pending — applies when the simulation runs)',
      'info:Turbine admission demand set to 0 % (pending — applies when the simulation runs)',
    ])
  })

  it('labels paused SCRAM reset turbine effects as pending without an operator-trip cause', () => {
    expect(
      detectionTexts(
        makeFrame(1, {
          running: false,
          scrammed: true,
          turbine_trip: false,
          turbine_trip_active: true,
          turbine_load_demand: 0.6,
          turbine_load_demand_effective: 0.6,
        }),
        makeFrame(2, {
          running: false,
          scrammed: false,
          turbine_trip: false,
          turbine_trip_active: true,
          turbine_load_demand: 0,
          turbine_load_demand_effective: 0.6,
        }),
      ),
    ).toEqual([
      'info:SCRAM reset, control bank back to command',
      'info:Turbine admission demand set to 0 % (pending — applies when the simulation runs)',
    ])
  })

  it('reports steam dump opening and closing with hysteresis', () => {
    const frames = [
      makeFrame(0, { m_dump: 0.99 }),
      makeFrame(0.1, { m_dump: 1.01 }),
      makeFrame(0.2, { m_dump: 0.99 }),
      makeFrame(0.3, { m_dump: 1.01 }),
      makeFrame(0.4, { m_dump: 0.49 }),
    ]
    expect(runFrames(frames).texts).toEqual([
      'info:Telemetry link established',
      'warn:Steam dump opened',
      'info:Steam dump closed',
    ])
  })

  it('reports pause, resume, speed and rod command changes', () => {
    expect(detectionTexts(makeFrame(1), makeFrame(2, { running: false }))).toEqual(['info:Paused'])
    expect(detectionTexts(makeFrame(1, { running: false }), makeFrame(2))).toEqual(['info:Resumed'])
    expect(detectionTexts(makeFrame(1), makeFrame(2, { speed: 5 }))).toEqual(['info:Speed set to 5×'])
    expect(detectionTexts(makeFrame(1), makeFrame(2, { rod_command: 0.7 }))).toEqual(['info:Rod command set to 70 %'])
  })

  it('reports turbine admission demand and SG level setpoint changes', () => {
    expect(
      detectionTexts(
        makeFrame(1, { turbine_load_demand: 1, turbine_load_demand_effective: 1 }),
        makeFrame(2, { turbine_load_demand: 0.75, turbine_load_demand_effective: 0.75 }),
      ),
    ).toEqual(['info:Turbine admission demand set to 75 %'])
    expect(
      detectionTexts(
        makeFrame(1, { running: false, turbine_load_demand: 1, turbine_load_demand_effective: 1 }),
        makeFrame(2, { running: false, turbine_load_demand: 0.75, turbine_load_demand_effective: 1 }),
      ),
    ).toEqual(['info:Turbine admission demand set to 75 % (pending — applies when the simulation runs)'])
    expect(detectionTexts(makeFrame(1), makeFrame(2, { level_setpoint: 0.55 }))).toEqual([
      'info:SG level setpoint set to 55 %',
    ])
  })

  it('reports rod AUTO/MANUAL changes and effective automatic suspension/resume', () => {
    expect(detectionTexts(makeFrame(1, { rod_auto: false }), makeFrame(2, { rod_auto: true, rod_auto_acting: true }))).toEqual([
      'info:Rod control set to AUTO',
    ])
    expect(detectionTexts(makeFrame(1, { rod_auto: true }), makeFrame(2, { rod_auto: false }))).toEqual([
      'info:Rod control set to MANUAL',
    ])
    expect(
      detectionTexts(
        makeFrame(1, { rod_auto: true, rod_auto_acting: true }),
        makeFrame(2, { rod_auto: true, rod_auto_acting: false, turbine_trip_active: true }),
      ),
    ).toEqual(['alarm:Turbine trip active: valves closing after trip reset', 'warn:Automatic rod control suspended'])
    expect(
      detectionTexts(
        makeFrame(1, { rod_auto: true, rod_auto_acting: false }),
        makeFrame(2, { rod_auto: true, rod_auto_acting: true }),
      ),
    ).toEqual(['info:Automatic rod control resumed'])
  })

  it('labels paused rod AUTO and MANUAL changes as pending when selected disagrees with effective state', () => {
    expect(
      detectionTexts(
        makeFrame(1, { running: false, rod_auto: false, rod_auto_acting: false }),
        makeFrame(2, { running: false, rod_auto: true, rod_auto_acting: false }),
      ),
    ).toEqual(['info:Rod control set to AUTO (pending — applies when the simulation runs)'])

    expect(
      detectionTexts(
        makeFrame(1, { running: false, rod_auto: true, rod_auto_acting: true }),
        makeFrame(2, { running: false, rod_auto: false, rod_auto_acting: true }),
      ),
    ).toEqual(['info:Rod control set to MANUAL (pending — applies when the simulation runs)'])
  })

  it('does not mark paused AUTO during SCRAM as pending and does not duplicate suspension on resume', () => {
    expect(
      detectionTexts(
        makeFrame(1, {
          running: false,
          rod_auto: false,
          rod_auto_acting: false,
          scrammed: true,
          turbine_trip_active: true,
        }),
        makeFrame(2, {
          running: false,
          rod_auto: true,
          rod_auto_acting: false,
          scrammed: true,
          turbine_trip_active: true,
        }),
      ),
    ).toEqual(['info:Rod control set to AUTO'])

    const frames = [
      makeFrame(1, { rod_auto: true, rod_auto_acting: false, turbine_trip_active: true }),
      makeFrame(2, { running: false, rod_auto: true, rod_auto_acting: false, turbine_trip_active: true }),
      makeFrame(3, { running: true, rod_auto: true, rod_auto_acting: false, turbine_trip_active: true }),
    ]
    expect(runFrames(frames).texts).toEqual([
      'info:Telemetry link established',
      'info:Paused',
      'info:Resumed',
    ])
  })

  it('tracks suspension state while paused so clearing a trip resumes once when running', () => {
    const frames = [
      makeFrame(1, { rod_auto: true, rod_auto_acting: false, turbine_trip: true, turbine_trip_active: true }),
      makeFrame(2, {
        running: false,
        rod_auto: true,
        rod_auto_acting: false,
        turbine_trip: false,
        turbine_trip_active: true,
        turbine_load_demand: 0,
        turbine_load_demand_effective: 1,
      }),
      makeFrame(3, {
        running: true,
        rod_auto: true,
        rod_auto_acting: true,
        turbine_trip: false,
        turbine_trip_active: false,
        turbine_load_demand: 0,
        turbine_load_demand_effective: 0,
      }),
    ]
    expect(runFrames(frames).texts).toEqual([
      'info:Telemetry link established',
      'info:Turbine trip latch reset; admission demand set to 0 % (pending — applies when the simulation runs)',
      'info:Paused',
      'info:Turbine admission demand set to 0 % (pending — applies when the simulation runs)',
      'info:Turbine trip cleared',
      'info:Resumed',
      'info:Automatic rod control resumed',
    ])
  })

  it('reports feedwater mode changes with pending annotations', () => {
    expect(
      detectionTexts(
        makeFrame(1, { feedwater_manual: null, feedwater_manual_effective: null }),
        makeFrame(2, { feedwater_manual: 0.4, feedwater_manual_effective: 0.4 }),
      ),
    ).toEqual(['info:Feedwater set to MANUAL (40 % max)'])
    expect(
      detectionTexts(
        makeFrame(1, { feedwater_manual: 0.4, feedwater_manual_effective: 0.4 }),
        makeFrame(2, { feedwater_manual: null, feedwater_manual_effective: null }),
      ),
    ).toEqual(['info:Feedwater set to AUTO'])
    expect(
      detectionTexts(
        makeFrame(1, { running: false, feedwater_manual: null, feedwater_manual_effective: null }),
        makeFrame(2, { running: false, feedwater_manual: 0.4, feedwater_manual_effective: null }),
      ),
    ).toEqual(['info:Feedwater set to MANUAL (40 % max) (pending — applies when the simulation runs)'])
    expect(
      detectionTexts(
        makeFrame(1, { running: false, feedwater_manual: 0.4, feedwater_manual_effective: 0.4 }),
        makeFrame(2, { running: false, feedwater_manual: null, feedwater_manual_effective: 0.4 }),
      ),
    ).toEqual(['info:Feedwater set to AUTO (pending — applies when the simulation runs)'])
  })

  it('debounces feedwater saturation alternation at 10 Hz and logs sustained transitions', () => {
    const alternating: Frame[] = [makeFrame(0, { fw_saturated: false, m_fw_demand: 100 })]
    for (let i = 1; i <= 10; i += 1) {
      alternating.push(
        makeFrame(i / 10, {
          fw_saturated: i % 2 === 1,
          m_fw_demand: i % 2 === 1 ? 2_002.81 : 100,
          m_fw_max: 2_002.81,
        }),
      )
    }
    expect(runFrames(alternating).texts).toEqual(['info:Telemetry link established'])

    const sustained = [
      makeFrame(0, { fw_saturated: false, m_fw_demand: 100, m_fw_max: 2_002.81 }),
      makeFrame(0.1, { fw_saturated: true, m_fw_demand: 2_002.81, m_fw_max: 2_002.81 }),
      makeFrame(0.2, { fw_saturated: true, m_fw_demand: 2_002.81, m_fw_max: 2_002.81 }),
      makeFrame(0.3, { fw_saturated: true, m_fw_demand: 2_002.81, m_fw_max: 2_002.81 }),
      makeFrame(0.4, { fw_saturated: true, m_fw_demand: 2_002.81, m_fw_max: 2_002.81 }),
      makeFrame(0.5, { fw_saturated: false, m_fw_demand: 100, m_fw_max: 2_002.81 }),
      makeFrame(0.6, { fw_saturated: false, m_fw_demand: 100, m_fw_max: 2_002.81 }),
      makeFrame(0.7, { fw_saturated: false, m_fw_demand: 100, m_fw_max: 2_002.81 }),
      makeFrame(0.8, { fw_saturated: false, m_fw_demand: 100, m_fw_max: 2_002.81 }),
    ]
    expect(runFrames(sustained).texts).toEqual([
      'info:Telemetry link established',
      'warn:Feedwater demand saturated at maximum',
      'info:Feedwater demand saturation cleared',
    ])
  })

  it('reports a model-limit halt as an alarm', () => {
    expect(detectionTexts(makeFrame(1), makeFrame(2, { model_limit: 'hot-leg water reached boiling' }))).toEqual([
      'alarm:Halted: hot-leg water reached boiling',
    ])
  })

  it('reports a pressure band crossing and the return to normal, never twice in a row', () => {
    const ok = makeFrame(1, { P_primary_MPa: 15.5 })
    const low = makeFrame(2, { P_primary_MPa: 13.9 })
    const lower = makeFrame(3, { P_primary_MPa: 13.5 })
    const back = makeFrame(4, { P_primary_MPa: 14.2 })
    expect(detectionTexts(ok, low)).toEqual(['warn:Primary pressure below 14.0 MPa'])
    expect(detectionTexts(low, lower)).toEqual([])
    expect(detectionTexts(lower, back)).toEqual(['info:Primary pressure back in its normal band'])
    expect(detectionTexts(ok, makeFrame(2, { P_primary_MPa: 11.5 }))).toEqual(['alarm:Primary pressure below 12.0 MPa'])
    expect(detectionTexts(ok, makeFrame(2, { P_primary_MPa: 17.5 }))).toEqual(['warn:Primary pressure above 17.0 MPa'])
  })

  it('reports fuel temperature and reactivity band crossings', () => {
    expect(detectionTexts(makeFrame(1), makeFrame(2, { T_fuel: 1450 }))).toEqual(['warn:Fuel temperature above 1,400 K'])
    expect(detectionTexts(makeFrame(1), makeFrame(2, { rho_total: 2.5e-3 }))).toEqual([
      'alarm:Total reactivity above 200 pcm',
    ])
  })

  it('reports steam-pressure and SG-level band crossings', () => {
    const normal = makeFrame(1, { P_steam_MPa: 6.9, level_sg: 0.5 })
    expect(detectionTexts(normal, makeFrame(2, { P_steam_MPa: 7.7 }))).toEqual([
      'warn:Steam pressure above 7.6 MPa',
    ])
    expect(detectionTexts(normal, makeFrame(2, { P_steam_MPa: 8.3 }))).toEqual([
      'alarm:Steam pressure above 8.2 MPa',
    ])
    expect(detectionTexts(normal, makeFrame(2, { P_steam_MPa: 3.4 }))).toEqual([
      'alarm:Steam pressure below 3.5 MPa',
    ])
    expect(detectionTexts(makeFrame(1, { P_steam_MPa: 7.7 }), normal)).toEqual([
      'info:Steam pressure back in its normal band',
    ])

    expect(detectionTexts(normal, makeFrame(2, { level_sg: 0.39 }))).toEqual([
      'warn:SG collapsed liquid fraction below 40 %',
    ])
    expect(detectionTexts(normal, makeFrame(2, { level_sg: 0.91 }))).toEqual([
      'alarm:SG collapsed liquid fraction above 90 %',
    ])
    expect(detectionTexts(makeFrame(1, { level_sg: 0.61 }), normal)).toEqual([
      'info:SG collapsed liquid fraction back in its normal band',
    ])
  })
})
