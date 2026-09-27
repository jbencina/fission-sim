import { describe, expect, it } from 'vitest'
import { makeFrame } from '../test/makeFrame'
import { criticalityWord, describeLoop } from './loopState'

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
