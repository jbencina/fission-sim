/**
 * thresholds — colour-band limits for status tiles.
 *
 * Each entry defines optional amber and red alert thresholds for a telemetry
 * field. Only obvious, safety-relevant bounds are defined here to avoid
 * false alarms. Green is the default (no threshold exceeded).
 *
 * Thresholds are one-sided: `aboveAmber` triggers amber if the value exceeds
 * the threshold; `belowAmber` triggers amber if the value falls below it.
 */

/** Colour band thresholds for a single tile. */
export interface Thresholds {
  /** Value above which the tile turns amber (warning). */
  aboveAmber?: number;
  /** Value above which the tile turns red (alarm). */
  aboveRed?: number;
  /** Value below which the tile turns amber (warning). */
  belowAmber?: number;
  /** Value below which the tile turns red (alarm). */
  belowRed?: number;
}

/**
 * Per-tile threshold map.
 *
 * Conservative — only obvious safety-relevant bands are listed.
 * Add new entries only when the engineering basis is clear.
 */
export const THRESHOLDS: Record<string, Thresholds> = {
  // Fuel temperature: > 1500 K approaches safety limits
  T_fuel: {
    aboveAmber: 1400,
    aboveRed: 1500,
  },

  // Primary pressure: low pressure risks coolant boiling; very high risks over-pressure
  P_primary_MPa: {
    belowAmber: 14.0,
    belowRed: 12.0,
    aboveAmber: 17.0,
    aboveRed: 18.0,
  },

  // Reactivity: large positive reactivity is a power excursion concern
  rho_total: {
    aboveAmber: 50,   // 50 pcm — perceptible power rise
    aboveRed: 200,    // 200 pcm — prompt criticality concern
  },
};

/**
 * Derive the colour band ('green' | 'amber' | 'red') for a tile value.
 *
 * @param tileId - The tile ID matching a key in THRESHOLDS.
 * @param value  - Current numeric value of the tile.
 * @returns      'red' | 'amber' | 'green'
 */
export function getBand(tileId: string, value: number): 'green' | 'amber' | 'red' {
  const t = THRESHOLDS[tileId];
  if (!t) return 'green';

  if (
    (t.aboveRed !== undefined && value > t.aboveRed) ||
    (t.belowRed !== undefined && value < t.belowRed)
  ) {
    return 'red';
  }

  if (
    (t.aboveAmber !== undefined && value > t.aboveAmber) ||
    (t.belowAmber !== undefined && value < t.belowAmber)
  ) {
    return 'amber';
  }

  return 'green';
}
