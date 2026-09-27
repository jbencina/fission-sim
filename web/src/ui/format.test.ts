import { describe, expect, it } from 'vitest';
import { EMPTY_VALUE, MINUS, formatClock, formatNumber } from './format';

describe('formatNumber', () => {
  it('uses fixed decimals and thousands separators', () => {
    expect(formatNumber(3000, 1)).toBe('3,000.0');
    expect(formatNumber(15.5, 2)).toBe('15.50');
    expect(formatNumber(1234.5, 0, { grouping: false })).toBe('1235');
  });

  it('uses a typographic minus, and never prints "−0.0"', () => {
    expect(formatNumber(-7000.04, 1)).toBe(`${MINUS}7,000.0`);
    expect(formatNumber(-0.04, 1)).toBe('0.0');
    expect(formatNumber(-0, 1)).toBe('0.0');
  });

  it('shows a dash for missing values', () => {
    expect(formatNumber(null, 1)).toBe(EMPTY_VALUE);
    expect(formatNumber(undefined, 1)).toBe(EMPTY_VALUE);
    expect(formatNumber(Number.NaN, 1)).toBe(EMPTY_VALUE);
  });
});

describe('formatClock', () => {
  it('formats simulated time as mm:ss.t', () => {
    expect(formatClock(0)).toBe('00:00.0');
    expect(formatClock(90.7)).toBe('01:30.7');
    expect(formatClock(3661.25)).toBe('61:01.2');
  });

  it('does not lose a tenth to floating-point error', () => {
    // 18.2 % 1 is 0.19999999999999929 in binary floating point.
    expect(formatClock(18.2)).toBe('00:18.2');
  });

  it('shows a placeholder before the first frame', () => {
    expect(formatClock(null)).toBe('--:--.-');
  });
});
