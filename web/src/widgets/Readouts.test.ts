import { describe, expect, it } from 'vitest'
import { EMPTY_VALUE } from '../ui/format'
import { formatLevelFloorEstimate } from './readoutFormat'

describe('formatLevelFloorEstimate', () => {
  it('shows an empty value when the SG is not draining toward the floor', () => {
    expect(formatLevelFloorEstimate(null)).toEqual({ value: EMPTY_VALUE, showUnits: true })
  })

  it('keeps seconds for estimates up to one hour', () => {
    expect(formatLevelFloorEstimate(3599.6)).toEqual({ value: '3,600', showUnits: true })
  })

  it('coarsens estimates over one hour as near balance', () => {
    expect(formatLevelFloorEstimate(3600.1)).toEqual({ value: '> 1 h (near balance)', showUnits: false })
  })
})
