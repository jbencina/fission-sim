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

  it('reports pause, resume, speed and rod command changes', () => {
    expect(texts(makeFrame(1), makeFrame(2, { running: false }))).toEqual(['info:Paused'])
    expect(texts(makeFrame(1, { running: false }), makeFrame(2))).toEqual(['info:Resumed'])
    expect(texts(makeFrame(1), makeFrame(2, { speed: 5 }))).toEqual(['info:Speed set to 5×'])
    expect(texts(makeFrame(1), makeFrame(2, { rod_command: 0.7 }))).toEqual(['info:Rod command set to 70 %'])
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
})
