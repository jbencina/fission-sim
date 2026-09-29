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
 * powers in Watts (W), mass flows in kg/s, reactivities are dimensionless,
 * times in seconds (s).
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

  /** Secondary-side steam pressure in the lumped steam-generator shell [Pa] */
  P_steam_Pa: number;

  /** Secondary-side steam pressure in the lumped steam-generator shell [MPa] */
  P_steam_MPa: number;

  /** Lumped secondary-side saturation temperature in the steam generator [K] */
  T_secondary: number;

  /**
   * SG collapsed liquid fraction (4 SGs lumped, no shrink/swell) [fraction].
   * This is inventory expressed as an equivalent liquid level, not a visible
   * two-phase swell level.
   */
  level_sg: number;

  /**
   * Estimated time until the SG collapsed liquid fraction reaches its lower
   * validity floor while draining [s], or null when the SG is not draining
   * toward that floor.
   */
  time_to_level_floor_s: number | null;

  /** Steam flow admitted through the turbine admission path [kg/s] */
  m_steam: number;

  /** Steam flow diverted through the steam dump instead of the turbine [kg/s] */
  m_dump: number;

  /** Gross electrical power from the turbine/generator fixed-efficiency proxy [W] */
  P_electric: number;

  /**
   * Actual turbine admission valve opening [fraction].
   * Label this as "turbine admission", not load; it ramps toward
   * turbine_load_demand and is forced closed by an effective trip.
   */
  turbine_load: number;

  /** Tavg controller reference temperature scheduled from turbine admission [K] */
  T_ref: number;

  /**
   * Effective turbine trip status [boolean].
   * True when either the commanded operator trip latch is set or SCRAM/P-4 has
   * tripped the turbine; compare with `turbine_trip` for commanded-only state.
   */
  turbine_trip_active: boolean;

  /** Actual feedwater flow into the lumped steam generators [kg/s] */
  m_fw: number;

  /**
   * Maximum feedwater flow available to the controller [kg/s].
   * This maximum is 120 % of design flow and is the denominator for
   * feedwater_manual.
   */
  m_fw_max: number;

  /** Feedwater flow demanded by the level controller before plant response [kg/s] */
  m_fw_demand: number;

  /** Whether the automatic feedwater level controller is saturated [boolean] */
  fw_saturated: boolean;

  /**
   * Active rod demand that actually drives the control bank [fraction].
   * In AUTO it comes from the Tavg controller; in MANUAL it follows
   * rod_command, the retained operator command.
   */
  rod_demand: number;

  /**
   * Whether automatic rod control is actively adjusting rods [boolean].
   * False can mean AUTO is suspended by controller logic or the operator has
   * selected MANUAL; compare with `rod_auto` for the commanded mode.
   */
  rod_auto_acting: boolean;

  /** Commanded turbine admission demand before ramping/trip action [fraction] */
  turbine_load_demand: number;

  /**
   * Commanded operator turbine-trip latch [boolean].
   * This is the operator command only; `turbine_trip_active` is the effective
   * turbine trip after SCRAM/P-4 is also considered.
   */
  turbine_trip: boolean;

  /** Operator-selected automatic rod-control mode [boolean] */
  rod_auto: boolean;

  /** SG collapsed-liquid-fraction setpoint for the feedwater controller [fraction] */
  level_setpoint: number;

  /**
   * Manual feedwater demand [fraction of m_fw_max], or null = AUTO.
   * m_fw_max is 120 % of design flow, so a manual value of 1.0 commands the
   * maximum feedwater flow rather than design flow.
   */
  feedwater_manual: number | null;

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
   * Operator's retained manual control-bank command [fraction withdrawn].
   * This is the manual command shown separately from rod_demand; in AUTO the
   * bank follows rod_demand instead. The rod controller moves the bank toward
   * the active demand at 0.01 per second.
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

/**
 * Minimum SG level setpoint accepted by the runtime. Mirrors
 * `LEVEL_SETPOINT_MIN` in `src/fission_sim/api/runtime.py`.
 */
export const LEVEL_SETPOINT_MIN = 0.35;

/**
 * Maximum SG level setpoint accepted by the runtime. Mirrors
 * `LEVEL_SETPOINT_MAX` in `src/fission_sim/api/runtime.py`.
 */
export const LEVEL_SETPOINT_MAX = 0.90;

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
 * Clear the SCRAM latch, return the control bank to rod_command, and set
 * turbine admission demand to 0. The shutdown bank stays inserted (the core
 * stays subcritical) until `reset`; turbine re-admission is an explicit
 * operator action.
 */
export interface ResetScramCommand {
  type: 'reset_scram';
}

/**
 * Set turbine admission demand [0..1].
 * The turbine admission valve ramps toward this demand at 5 %/min while not
 * effectively tripped; electrical output is reported separately.
 */
export interface SetTurbineLoadCommand {
  type: 'set_turbine_load';
  /** Turbine admission demand as a fraction of full admission [0..1]. */
  value: number;
}

/** Set the operator turbine-trip latch; effective trip may also come from SCRAM/P-4. */
export interface TurbineTripCommand {
  type: 'turbine_trip';
}

/**
 * Clear the operator turbine-trip latch and set turbine admission demand to 0.
 * Re-admission is always an explicit later `set_turbine_load` action.
 */
export interface ResetTurbineTripCommand {
  type: 'reset_turbine_trip';
}

/**
 * Select automatic or manual rod control.
 * `true` lets the Tavg controller drive rod_demand; `false` enters MANUAL and
 * the runtime synchronizes rod_command to the actual rod position for a
 * bumpless transfer.
 */
export interface SetRodAutoCommand {
  type: 'set_rod_auto';
  /** true = automatic rod control, false = manual with rod_command synced. */
  value: boolean;
}

/** Set the SG collapsed-liquid-fraction setpoint for feedwater control [0.35..0.90]. */
export interface SetLevelSetpointCommand {
  type: 'set_level_setpoint';
  /** Target SG collapsed liquid fraction within LEVEL_SETPOINT_MIN/MAX. */
  value: number;
}

/**
 * Set manual feedwater demand or return feedwater to AUTO.
 * Numeric values are fractions of m_fw_max in [0, 1], where m_fw_max is
 * 120 % of design feedwater flow; null selects AUTO. The UI should send the
 * current demand fraction when entering MANUAL for a bumpless transfer, and
 * AUTO resumes within the controller's ±20 % integral authority.
 */
export interface SetFeedwaterManualCommand {
  type: 'set_feedwater_manual';
  /** Manual demand fraction of m_fw_max [0..1], or null = AUTO. */
  value: number | null;
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
 * Rebuild the engine at the design full-power state from t = 0.
 * Preserves P_setpoint, speed, pause state, turbine admission demand,
 * rod_auto mode, and level_setpoint. Clears SCRAM, the turbine trip latch,
 * feedwater_manual (AUTO), and any model-limit halt; both banks return to
 * design positions and rod_command returns to 0.5.
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
  | SetTurbineLoadCommand
  | TurbineTripCommand
  | ResetTurbineTripCommand
  | SetRodAutoCommand
  | SetLevelSetpointCommand
  | SetFeedwaterManualCommand
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
  'P_steam_Pa',
  'P_steam_MPa',
  'T_secondary',
  'level_sg',
  'm_steam',
  'm_dump',
  'P_electric',
  'turbine_load',
  'T_ref',
  'm_fw',
  'm_fw_max',
  'm_fw_demand',
  'rod_demand',
  'turbine_load_demand',
  'level_setpoint',
  'rho_rod',
  'rho_doppler',
  'rho_moderator',
  'rho_total',
  'speed',
  'rod_command',
];

/** Required boolean keys that every valid Frame must contain. */
const BOOLEAN_FRAME_KEYS: ReadonlyArray<keyof Frame> = [
  'turbine_trip_active',
  'fw_saturated',
  'rod_auto_acting',
  'turbine_trip',
  'rod_auto',
  'running',
  'scrammed',
];

/** Required nullable numeric keys that every valid Frame must contain. */
const NULLABLE_NUMERIC_FRAME_KEYS: ReadonlyArray<keyof Frame> = [
  'time_to_level_floor_s',
  'feedwater_manual',
];

/** Required keys that every valid Frame must contain. */
const REQUIRED_FRAME_KEYS: ReadonlyArray<keyof Frame> = [
  ...NUMERIC_FRAME_KEYS,
  ...BOOLEAN_FRAME_KEYS,
  ...NULLABLE_NUMERIC_FRAME_KEYS,
  'model_limit',
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
  if (
    !NULLABLE_NUMERIC_FRAME_KEYS.every(
      (k) => obj[k] === null || (typeof obj[k] === 'number' && Number.isFinite(obj[k])),
    )
  ) {
    return false;
  }
  // model_limit must be present: null normally, a message while halted.
  return obj.model_limit === null || typeof obj.model_limit === 'string';
}
