import { describe, expect, it } from 'vitest';
import { getBand } from './thresholds';

describe('secondary alert bands', () => {
  it('bands steam pressure at the dump-open and dump-full thresholds', () => {
    expect(getBand('P_steam_MPa', 6.9)).toBe('green');
    expect(getBand('P_steam_MPa', 7.6)).toBe('green');
    expect(getBand('P_steam_MPa', 7.61)).toBe('amber');
    expect(getBand('P_steam_MPa', 8.2)).toBe('amber');
    expect(getBand('P_steam_MPa', 8.21)).toBe('red');
    expect(getBand('P_steam_MPa', 3.5)).toBe('green');
    expect(getBand('P_steam_MPa', 3.49)).toBe('red');
  });

  it('bands SG collapsed liquid fraction around the operating and validity bands', () => {
    expect(getBand('level_sg', 0.5)).toBe('green');
    expect(getBand('level_sg', 0.4)).toBe('green');
    expect(getBand('level_sg', 0.399)).toBe('amber');
    expect(getBand('level_sg', 0.35)).toBe('amber');
    expect(getBand('level_sg', 0.349)).toBe('red');
    expect(getBand('level_sg', 0.6)).toBe('green');
    expect(getBand('level_sg', 0.601)).toBe('amber');
    expect(getBand('level_sg', 0.9)).toBe('amber');
    expect(getBand('level_sg', 0.901)).toBe('red');
  });
});
