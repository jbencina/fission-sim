/**
 * thresholds — colour-band limits for status tiles.
 *
 * Each entry defines optional amber and red alert thresholds for a telemetry
 * field. Green is the default (no threshold exceeded).
 *
 * These are ILLUSTRATIVE alert bands chosen to draw the eye during a
 * transient. They are not plant safety limits, trip setpoints, or
 * Technical Specification values, and this simulator does not act on them.
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
 * Keep the list short, so an amber or red tile still means "look here".
 */
export const THRESHOLDS: Record<string, Thresholds> = {
  // Fuel temperature (design 1100 K). T_fuel is the lumped AVERAGE fuel
  // temperature, so these bands only flag a large departure from design.
  // They do not predict fuel failure: real fuel limits concern local peak
  // temperatures, which a one-temperature fuel model does not compute.
  T_fuel: {
    aboveAmber: 1400,
    aboveRed: 1500,
  },

  // Primary pressure (design 15.5 MPa). Low pressure brings the hot leg
  // closer to boiling (at the 597.7 K design hot leg, water boils below
  // about 12 MPa); high pressure is overpressure.
  P_primary_MPa: {
    belowAmber: 14.0,
    belowRed: 12.0,
    aboveAmber: 17.0,
    aboveRed: 18.0,
  },

  // Total reactivity [pcm]. Positive reactivity makes power rise. This
  // model's prompt-critical threshold is sum(beta_i) = 650.2 pcm (one
  // dollar, $1); these bands sit well below it.
  rho_total: {
    aboveAmber: 50,   // 50 pcm (about $0.08): a noticeable power rise
    aboveRed: 200,    // 200 pcm (about $0.31): a rapid power rise
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
