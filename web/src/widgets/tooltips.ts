/**
 * tooltips — centralized educational copy for the status readouts and the
 * toolbar's simulation-state badges.
 *
 * Each entry describes a telemetry field in plain language suitable for
 * a reader without a nuclear engineering background. The `body` field
 * must be >=40 characters and include: what the value means physically,
 * its units, and its value at this model's design point.
 *
 * Fidelity note: the model's parameters are calibrated to a generic
 * ~3000 MWth Westinghouse-style 4-loop PWR. Design-point values quoted
 * below are the ones this simulator computes (hot leg 597.7 K, cold leg
 * 568.3 K, average 583.0 K); a particular real plant differs.
 */

/** Shape of a single tooltip entry. */
export interface TooltipEntry {
  /** Short label shown on the readout and in bold at the top of its explanation. */
  title: string;
  /** Plain-language explanation ≥40 characters. Includes units and the design-point value. */
  body: string;
  /** Unit displayed after the value, e.g. "MW" or "K". */
  units: string;
}

/**
 * Tooltip copy keyed by tile ID.
 *
 * Add new entries here when adding new tiles. Keep `body` ≥40 characters
 * and written for a non-specialist audience.
 */
export const TOOLTIPS: Record<string, TooltipEntry> = {
  power_thermal: {
    title: 'Thermal power',
    units: 'MW',
    body:
      'Modeled fission power: the energy released by fission in the core ' +
      'each second (neutron population × 3000 MW design). Design: 3000 MW. ' +
      'After a SCRAM it falls to a few percent within seconds, then fades ' +
      'over minutes: delayed-neutron precursors made before the SCRAM keep ' +
      'decaying and emitting neutrons, which cause a dwindling number of ' +
      'fissions. Decay heat from fission products is not modeled, so a real ' +
      'reactor would still produce more heat than this after shutdown.',
  },

  T_hot: {
    title: 'Hot leg',
    units: 'K',
    body:
      'Coolant temperature leaving the reactor core on its way to the steam ' +
      'generator. Called the "hot leg" because it carries heat away from the ' +
      'core. Design full power in this model: 597.7 K (324.6 °C / 616.3 °F).',
  },

  T_cold: {
    title: 'Cold leg',
    units: 'K',
    body:
      'Coolant temperature returning from the steam generator back to the ' +
      'reactor core. It has given up heat to make steam. Design full power ' +
      'in this model: 568.3 K (295.1 °C / 563.2 °F).',
  },

  T_avg: {
    title: 'Average coolant',
    units: 'K',
    body:
      'Arithmetic mean of hot-leg and cold-leg temperatures: (T_hot + T_cold)/2. ' +
      'The core uses it as the moderator (water) temperature for ' +
      'moderator-temperature reactivity feedback. Design full power: ' +
      '583.0 K (309.9 °C).',
  },

  T_fuel: {
    title: 'Fuel temperature',
    units: 'K',
    body:
      'Lumped average temperature of all the uranium fuel: one number for ' +
      'the whole core, not the hotter pellet centerline. Design full power ' +
      'in this model: 1100 K. Hotter fuel broadens the absorption resonances ' +
      'of U-238, so more neutrons are captured without causing fission ' +
      '(the Doppler effect) and reactivity falls. The fuel heats as soon as ' +
      'power rises, so this natural self-limiting feedback acts first.',
  },

  P_primary_MPa: {
    title: 'Primary pressure',
    units: 'MPa',
    body:
      'Pressure of the primary coolant loop, maintained by the pressurizer ' +
      'vessel using electric heaters and spray. Design: 15.5 MPa (about ' +
      '2250 psi). At that pressure water boils at about 618 K (345 °C), so ' +
      'the 598 K hot leg stays liquid. The tile turns amber below 14 MPa ' +
      '(an illustrative alert band, not a plant limit).',
  },

  rod_position: {
    title: 'Rod position',
    units: '%',
    body:
      'Control-bank position, in % of travel withdrawn: 0 % = fully ' +
      'inserted, 100 % = fully withdrawn. Rods absorb neutrons; withdrawing ' +
      'them adds reactivity. Design full-power position: 50 %. Each 1 % of ' +
      'travel is worth 12 pcm (1,200 pcm over the full stroke). A separate ' +
      'shutdown bank, not shown here, stays fully withdrawn until a SCRAM ' +
      'drops it.',
  },

  rod_command: {
    title: 'Rod command',
    units: '%',
    body:
      'Operator target for the control-bank position, in % of travel ' +
      'withdrawn (sent to the simulator as a fraction, 0 to 1). The rod drive ' +
      'moves the bank toward it at 1 % of travel per second, so a full ' +
      'stroke takes 100 s. A difference between command and position means ' +
      'the bank is still moving. During a SCRAM the command is overridden.',
  },

  Q_sg: {
    title: 'SG heat transfer',
    units: 'MW',
    body:
      'Heat flowing from the primary coolant to the secondary (steam) side ' +
      'through the steam generator. At steady state this matches core thermal ' +
      'power. During a transient the difference is heat being stored in, or ' +
      'drawn from, the fuel and the primary coolant.',
  },

  sim_time: {
    title: 'Simulation time',
    units: 's',
    body:
      'Elapsed simulation time (shown as T+ mm:ss.t). This is the ' +
      'model\'s internal clock, independent of real wall-clock time. The speed ' +
      'multiplier controls how fast simulation time advances relative to ' +
      'real time.',
  },

  speed: {
    title: 'Speed multiplier',
    units: '×',
    body:
      'Real-time multiplier for simulation advancement. At 1×, one simulated ' +
      'second takes one real second. At 10×, one simulated minute passes in ' +
      '6 real seconds. The solver\'s accuracy settings are the same at every ' +
      'speed; at high speed a step may take longer to compute than its ' +
      'real-time slot, and the simulation then runs slower than requested.',
  },

  scrammed: {
    title: 'SCRAM',
    units: '',
    body:
      'A SCRAM is an emergency reactor shutdown. It immediately commands ' +
      'the control bank and the shutdown bank to drop in; both are fully ' +
      'inserted within about 2 s, adding about −7,000 pcm and making the ' +
      'core deeply subcritical. The latch stays set until Reset Scram, ' +
      'which returns only the control bank; the shutdown bank stays in ' +
      'until Reset Simulation.',
  },

  running: {
    title: 'Run state',
    units: '',
    body:
      'Whether simulation time is advancing. Paused and Halted (stopped at ' +
      'a model limit) both freeze values at the last computed state. Resume ' +
      'continues a pause; a model-limit halt needs Reset Simulation.',
  },

  rho_total: {
    title: 'Total reactivity',
    units: 'pcm',
    body:
      'Net reactivity — sum of rod, Doppler, and moderator contributions. ' +
      'Zero = exactly critical (steady power). Positive = supercritical ' +
      '(power rising). Negative = subcritical (power falling). Displayed in ' +
      'pcm (per cent mille = 1×10⁻⁵), a convenient small unit.',
  },
};
