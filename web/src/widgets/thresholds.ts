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

/** Alert band of a readout: normal, warning or alarm. */
export type Band = 'green' | 'amber' | 'red';

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
 * Secondary steam-pressure bands [MPa].
 *
 * The high bands line up with the simplified dump valve: it starts opening
 * above 7.6 MPa and is fully open above 8.2 MPa. The low red band sits above
 * the model's 3.0 MPa feedwater-flashing floor. These are display bands only,
 * not trip setpoints.
 */
export const STEAM_PRESSURE_THRESHOLDS_MPA: Thresholds = {
  aboveAmber: 7.6,
  aboveRed: 8.2,
  belowRed: 3.5,
};

/**
 * SG collapsed-liquid-fraction bands [fraction].
 *
 * The normal teaching band is 40–60 %. Red stays inside the model validity
 * limits (30 % tube-uncovery floor, 95 % overfill ceiling) so the dashboard
 * warns before the backend halts at those assumptions.
 */
export const SG_LEVEL_THRESHOLDS: Thresholds = {
  belowAmber: 0.40,
  aboveAmber: 0.60,
  belowRed: 0.35,
  aboveRed: 0.90,
};

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

  P_steam_MPa: STEAM_PRESSURE_THRESHOLDS_MPA,

  level_sg: SG_LEVEL_THRESHOLDS,

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
export function getBand(tileId: string, value: number): Band {
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
