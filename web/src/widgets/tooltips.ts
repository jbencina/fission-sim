/**
 * tooltips — centralized educational tooltip copy for status tiles.
 *
 * Each entry describes a telemetry field in plain language suitable for
 * a reader without a nuclear engineering background. The `body` field
 * must be >=40 characters and include: what the value means physically,
 * its units, and a typical operating range.
 *
 * Fidelity note: values are for a generic 3000 MWth PWR (e.g. Westinghouse
 * AP1000 class). Exact numbers vary by plant design.
 */

/** Shape of a single tooltip entry. */
export interface TooltipEntry {
  /** Short title matching the tile label — displayed in bold at the top of the tooltip. */
  title: string;
  /** Plain-language explanation ≥40 characters. Includes units and typical range. */
  body: string;
  /** Primary unit string displayed on the tile, e.g. "MW" or "K". */
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
    title: 'Thermal Power',
    units: 'MW',
    body:
      'Reactor core thermal output — total fission heat released per second. ' +
      'At design conditions this is ~3000 MW. Zero power means the chain ' +
      'reaction has stopped (subcritical or scrammed).',
  },

  T_hot: {
    title: 'Hot-leg Temperature',
    units: 'K',
    body:
      'Coolant temperature leaving the reactor core on its way to the steam ' +
      'generator. Called the "hot leg" because it carries heat away from the ' +
      'core. Normal at full power: ~600 K (~327 °C / 620 °F).',
  },

  T_cold: {
    title: 'Cold-leg Temperature',
    units: 'K',
    body:
      'Coolant temperature returning from the steam generator back to the ' +
      'reactor core. It has given up heat to make steam. Normal at full ' +
      'power: ~565 K (~292 °C / 558 °F).',
  },

  T_avg: {
    title: 'Average Coolant Temp',
    units: 'K',
    body:
      'Arithmetic mean of hot-leg and cold-leg temperatures: (T_hot + T_cold)/2. ' +
      'Used as the control reference for moderator-temperature reactivity ' +
      'feedback. Normal: ~582 K (~309 °C) at full power.',
  },

  T_fuel: {
    title: 'Fuel Temperature',
    units: 'K',
    body:
      'Average temperature of the uranium fuel pellets inside the fuel rods. ' +
      'Higher fuel temperature reduces reactivity through the Doppler effect ' +
      '(neutrons slow more easily), a natural self-limiting safety feature. ' +
      'Typical: ~900–1100 K at full power.',
  },

  P_primary_MPa: {
    title: 'Primary Pressure',
    units: 'MPa',
    body:
      'Pressure of the primary coolant loop, maintained by the pressurizer ' +
      'vessel using electric heaters and spray nozzles. High pressure ' +
      '(~15.5 MPa / 2250 psi) prevents the water from boiling even at ' +
      '~325 °C. Below ~14 MPa indicates an underpressure transient.',
  },

  rod_position: {
    title: 'Rod Position',
    units: '%',
    body:
      'Physical control-rod insertion: 0% = fully inserted (maximum shutdown ' +
      'margin), 100% = fully withdrawn (maximum reactivity). Rods absorb ' +
      'neutrons; withdrawing them allows the chain reaction to grow. ' +
      'Normal operating range: ~40–60%.',
  },

  rod_command: {
    title: 'Rod Command',
    units: '%',
    body:
      'Operator (or automatic controller) setpoint for rod position [0..1]. ' +
      'The rod drive mechanism moves the physical rods toward this target at ' +
      'a finite speed. A difference between command and actual position means ' +
      'the rods are still moving.',
  },

  Q_sg: {
    title: 'SG Heat Transfer',
    units: 'MW',
    body:
      'Heat flowing from the primary coolant to the secondary (steam) side ' +
      'through the steam generator. At steady state this matches core thermal ' +
      'power. A mismatch means thermal energy is accumulating or draining from ' +
      'the primary coolant inventory.',
  },

  sim_time: {
    title: 'Simulation Time',
    units: 's',
    body:
      'Elapsed simulation time in seconds (displayed as mm:ss). This is the ' +
      'model\'s internal clock, independent of real wall-clock time. The speed ' +
      'multiplier controls how fast simulation time advances relative to ' +
      'real time.',
  },

  speed: {
    title: 'Speed Multiplier',
    units: '×',
    body:
      'Real-time multiplier for simulation advancement. At 1×, one simulated ' +
      'second takes one real second. At 10×, one simulated minute passes in ' +
      '6 real seconds. Higher speeds may reduce integration accuracy for very ' +
      'fast transients (µs-scale neutron kinetics).',
  },

  scrammed: {
    title: 'SCRAM Status',
    units: '',
    body:
      'A SCRAM (Safety Control Rod Axe Man — a historic term) is an emergency ' +
      'reactor shutdown: all control rods drop fully in, rapidly making the ' +
      'chain reaction subcritical. The latch stays set until manually reset. ' +
      'Power decays to ~1–7% from decay heat after a scram.',
  },

  running: {
    title: 'Sim Running',
    units: '',
    body:
      'Whether the simulation time-step loop is actively advancing. False ' +
      'means the simulation is paused — telemetry values are frozen at the ' +
      'last computed state. Resume to continue integration.',
  },

  rho_total: {
    title: 'Total Reactivity',
    units: 'pcm',
    body:
      'Net reactivity — sum of rod, Doppler, and moderator contributions. ' +
      'Zero = exactly critical (steady power). Positive = supercritical ' +
      '(power rising). Negative = subcritical (power falling). Displayed in ' +
      'pcm (per cent mille = 1×10⁻⁵), a convenient small unit.',
  },
};
