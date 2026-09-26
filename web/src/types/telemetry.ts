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

  /**
   * Modeled fission power in the core [W]: n · P_design, the rate at which
   * fission releases energy. Fission-product decay heat is not modeled.
   */
  power_thermal: number;

  /** Hot-leg coolant temperature (core outlet) [K] */
  T_hot: number;

  /** Cold-leg coolant temperature (core inlet) [K] */
  T_cold: number;

  /** Average primary coolant temperature: (T_hot + T_cold) / 2 [K] */
  T_avg: number;

  /** Lumped average fuel temperature (one value for the whole core) [K] */
  T_fuel: number;

  /**
   * Control-bank position as a fraction of travel withdrawn [0..1].
   * 0 = fully inserted, 1 = fully withdrawn; design 0.5. The shutdown bank
   * (dropped only by SCRAM) is not in the frame; its worth is in rho_rod.
   */
  rod_position: number;

  /** Primary system pressure from the pressurizer [Pa] */
  P_primary_Pa: number;

  /** Primary system pressure from the pressurizer [MPa] (convenience derived) */
  P_primary_MPa: number;

  /** Heat transferred from primary to secondary side via the steam generator [W] */
  Q_sg: number;

  /**
   * Rod reactivity, control bank + shutdown bank [dimensionless].
   * Zero at design; positive when the control bank is withdrawn past 0.5,
   * negative when either bank is inserted further.
   */
  rho_rod: number;

  /**
   * Doppler (fuel temperature) feedback reactivity [dimensionless].
   * Negative when the fuel is hotter than its 1100 K reference: hotter fuel
   * broadens U-238 absorption resonances and captures more neutrons.
   */
  rho_doppler: number;

  /**
   * Moderator temperature feedback reactivity [dimensionless].
   * Negative when the coolant (T_avg) is hotter than its 583 K reference;
   * this model uses one constant negative coefficient.
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
   * Whether the SCRAM latch is set. While set, both rod banks are driven
   * to full insertion (within about 2 s) regardless of rod_command.
   */
  scrammed: boolean;

  /**
   * Operator's control-bank command, fraction of travel withdrawn [0..1].
   * The rod controller moves the bank toward it at 0.01 per second.
   */
  rod_command: number;

  /**
   * Why the simulation halted at the edge of what the model can describe,
   * or null during normal operation. Set when a step would take the plant
   * outside the model's supported domain (hot-leg water boiling, a
   * pressurizer that is water-solid or dry, pressure out of range). While
   * set, the backend holds the last valid state and refuses `resume`; a
   * `reset` clears it. A halt caused by an unexpected step failure (a
   * simulator fault rather than a physics limit) starts with
   * `SIM_ERROR_PREFIX`.
   */
  model_limit: string | null;
}

/**
 * Prefix of `Frame.model_limit` for a halt caused by an unexpected step
 * failure. Mirrors `SIM_ERROR_PREFIX` in `src/fission_sim/api/runtime.py`.
 */
export const SIM_ERROR_PREFIX = 'Simulation error: ';

// ---------------------------------------------------------------------------
// Command — outbound messages from UI to backend
// ---------------------------------------------------------------------------

/** Move the control bank toward the specified position [0..1]. */
export interface SetRodCommand {
  type: 'set_rod_command';
  /**
   * Target control-bank position, fraction of travel withdrawn [0..1].
   * 0 = fully inserted, 1 = fully withdrawn; 0.5 is the design full-power
   * position. Each 0.01 of travel is worth 12 pcm.
   */
  value: number;
}

/**
 * Initiate a SCRAM: immediately commands both rod banks to drop; they are
 * fully inserted within about 2 s.
 */
export interface ScramCommand {
  type: 'scram';
}

/**
 * Clear the SCRAM latch and return the control bank to rod_command. The
 * shutdown bank stays inserted (the core stays subcritical) until `reset`.
 */
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

/**
 * Rebuild the engine at the design full-power state from t = 0: SCRAM
 * cleared, both banks back at their design positions, rod_command 0.5.
 * P_setpoint and speed are preserved. Also clears a model-limit halt.
 */
export interface ResetCommand {
  type: 'reset';
}

/**
 * Speed multipliers the backend accepts. Mirrors `_ALLOWED_SPEEDS` in
 * `src/fission_sim/api/runtime.py`.
 */
export const SPEEDS = [1, 2, 5, 10] as const;

/** One of the allowed speed multipliers. */
export type Speed = (typeof SPEEDS)[number];

/** Set the simulation speed multiplier. */
export interface SetSpeedCommand {
  type: 'set_speed';
  /** Speed factor — must be one of `SPEEDS`. */
  value: Speed;
}

/** Set the primary pressure setpoint for the pressurizer controller [Pa]. */
export interface SetPressureSetpointCommand {
  type: 'set_pressure_setpoint';
  /**
   * Pressure setpoint [Pa]. Nominal is 15.5 MPa = 1.55e7 Pa. A setpoint far
   * below the actual pressure keeps the spray running; the pressurizer can
   * then fill with water, which halts the simulation at a model limit.
   */
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

/**
 * Where a user-visible message came from.
 *
 * - 'server'     — an explanation sent by the backend, e.g. why a command was
 *                  rejected. It stays until the user dismisses it or the
 *                  backend sends a newer one.
 * - 'connection' — the browser lost (or could not open) the WebSocket. It is
 *                  cleared automatically once the socket reconnects.
 */
export type AppErrorSource = 'server' | 'connection';

// ---------------------------------------------------------------------------
// Type guard — validates that a parsed JSON object has required Frame keys
// ---------------------------------------------------------------------------

/** Required numeric keys that every valid Frame must contain. */
const NUMERIC_FRAME_KEYS: ReadonlyArray<keyof Frame> = [
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
  'speed',
  'rod_command',
];

/** Required boolean keys that every valid Frame must contain. */
const BOOLEAN_FRAME_KEYS: ReadonlyArray<keyof Frame> = ['running', 'scrammed'];

/** Required keys that every valid Frame must contain. */
const REQUIRED_FRAME_KEYS: ReadonlyArray<keyof Frame> = [
  ...NUMERIC_FRAME_KEYS,
  ...BOOLEAN_FRAME_KEYS,
];

/**
 * Type guard: returns true if `value` is a valid Frame.
 *
 * Checks required keys, primitive types, and finite numeric values. It does
 * not validate domain-specific operating ranges.
 */
export function isFrame(value: unknown): value is Frame {
  if (typeof value !== 'object' || value === null) return false;
  const obj = value as Record<string, unknown>;
  if (!REQUIRED_FRAME_KEYS.every((k) => k in obj)) return false;
  if (!NUMERIC_FRAME_KEYS.every((k) => typeof obj[k] === 'number' && Number.isFinite(obj[k]))) {
    return false;
  }
  if (!BOOLEAN_FRAME_KEYS.every((k) => typeof obj[k] === 'boolean')) return false;
  // model_limit must be present: null normally, a message while halted.
  return 'model_limit' in obj && (obj.model_limit === null || typeof obj.model_limit === 'string');
}
