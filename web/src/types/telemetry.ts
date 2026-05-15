/**
 * Telemetry types for fission-sim web UI.
 *
 * These interfaces mirror the telemetry frame keys produced by
 * `src/fission_sim/api/runtime.py::_build_telemetry_frame()` exactly.
 * Any change to the backend frame dict must be reflected here.
 */

// ---------------------------------------------------------------------------
// Frame — one telemetry snapshot emitted by the backend at ~10 Hz
// ---------------------------------------------------------------------------

/**
 * A single telemetry frame as broadcast over the /ws/telemetry WebSocket.
 *
 * All temperatures are in Kelvin (K), pressures in Pa or MPa as noted,
 * powers in Watts (W), reactivities are dimensionless, times in seconds (s).
 */
export interface Frame {
  /** Simulation time [s] */
  t: number;

  /** Total thermal power produced by the reactor core [W] */
  power_thermal: number;

  /** Hot-leg coolant temperature (core outlet) [K] */
  T_hot: number;

  /** Cold-leg coolant temperature (core inlet) [K] */
  T_cold: number;

  /** Average primary coolant temperature: (T_hot + T_cold) / 2 [K] */
  T_avg: number;

  /** Fuel centerline temperature [K] */
  T_fuel: number;

  /**
   * Physical rod position as fraction of fully withdrawn [0..1].
   * 0 = fully inserted (maximum shutdown reactivity worth),
   * 1 = fully withdrawn (maximum reactivity addition).
   */
  rod_position: number;

  /** Primary system pressure from the pressurizer [Pa] */
  P_primary_Pa: number;

  /** Primary system pressure from the pressurizer [MPa] (convenience derived) */
  P_primary_MPa: number;

  /** Heat transferred from primary to secondary side via the steam generator [W] */
  Q_sg: number;

  /**
   * Reactivity worth of the control rods [dimensionless].
   * Negative when rods are inserted (add negative reactivity = shutdown margin).
   */
  rho_rod: number;

  /**
   * Doppler (fuel temperature) feedback reactivity [dimensionless].
   * Negative for hotter fuel — provides inherent prompt stability.
   */
  rho_doppler: number;

  /**
   * Moderator temperature feedback reactivity [dimensionless].
   * Negative in a well-designed PWR when coolant heats up.
   */
  rho_moderator: number;

  /**
   * Total reactivity = rho_rod + rho_doppler + rho_moderator [dimensionless].
   * Reactor is exactly critical when rho_total = 0.
   */
  rho_total: number;

  /** Whether the simulation step loop is actively advancing time (false = paused) */
  running: boolean;

  /**
   * Simulation speed multiplier.
   * 1.0 = real time, 2.0 = 2× faster, etc.
   */
  speed: number;

  /**
   * Whether a SCRAM has been initiated.
   * A SCRAM forces full rod insertion regardless of rod_command.
   */
  scrammed: boolean;

  /**
   * Operator rod command [0..1].
   * The rod controller drives the physical rod toward this value.
   */
  rod_command: number;
}

// ---------------------------------------------------------------------------
// Command — outbound messages from UI to backend
// ---------------------------------------------------------------------------

/** Move the control rods toward the specified position [0..1]. */
export interface SetRodCommand {
  type: 'set_rod_command';
  /** Target rod position [0..1]. 0 = full shutdown, 1 = full power. */
  value: number;
}

/** Initiate a SCRAM — forces full rod insertion immediately. */
export interface ScramCommand {
  type: 'scram';
}

/** Clear the SCRAM latch and restore operator rod control. */
export interface ResetScramCommand {
  type: 'reset_scram';
}

/** Pause simulation time advancement (step loop keeps running). */
export interface PauseCommand {
  type: 'pause';
}

/** Resume simulation time after a pause. */
export interface ResumeCommand {
  type: 'resume';
}

/** Rebuild the engine from t = 0, preserving P_setpoint and speed. */
export interface ResetCommand {
  type: 'reset';
}

/** Set the simulation speed multiplier. */
export interface SetSpeedCommand {
  type: 'set_speed';
  /** Speed factor — must be one of 1, 2, 5, or 10. */
  value: 1 | 2 | 5 | 10;
}

/** Set the primary pressure setpoint for the pressurizer controller [Pa]. */
export interface SetPressureSetpointCommand {
  type: 'set_pressure_setpoint';
  /** Pressure setpoint [Pa]. Nominal is 15.5 MPa = 1.55e7 Pa. */
  value: number;
}

/**
 * Discriminated union of all commands the UI can send to the backend.
 * The `type` field determines which command is being sent.
 */
export type Command =
  | SetRodCommand
  | ScramCommand
  | ResetScramCommand
  | PauseCommand
  | ResumeCommand
  | ResetCommand
  | SetSpeedCommand
  | SetPressureSetpointCommand;

// ---------------------------------------------------------------------------
// ConnectionStatus
// ---------------------------------------------------------------------------

/**
 * WebSocket connection lifecycle states.
 * - 'connecting' — initial connect or reconnect attempt in progress
 * - 'connected'  — socket is open and receiving telemetry
 * - 'disconnected' — socket is closed; reconnect will be scheduled
 */
export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected';

// ---------------------------------------------------------------------------
// Type guard — validates that a parsed JSON object has required Frame keys
// ---------------------------------------------------------------------------

/** Required numeric keys that every valid Frame must contain. */
const REQUIRED_FRAME_KEYS: ReadonlyArray<keyof Frame> = [
  't',
  'power_thermal',
  'T_hot',
  'T_cold',
  'T_avg',
  'T_fuel',
  'rod_position',
  'P_primary_Pa',
  'P_primary_MPa',
  'Q_sg',
  'rho_rod',
  'rho_doppler',
  'rho_moderator',
  'rho_total',
  'running',
  'speed',
  'scrammed',
  'rod_command',
];

/**
 * Type guard: returns true if `value` is a valid Frame.
 *
 * Only checks that required keys are present — does not validate numeric
 * ranges. Safe to call on the result of `JSON.parse()`.
 */
export function isFrame(value: unknown): value is Frame {
  if (typeof value !== 'object' || value === null) return false;
  const obj = value as Record<string, unknown>;
  return REQUIRED_FRAME_KEYS.every((k) => k in obj);
}
