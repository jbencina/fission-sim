/**
 * Shared test fixture: a valid telemetry Frame at simulation time `t`.
 *
 * Values sit near the design full-power state and change with `t`, so frames
 * built for different times produce different chart points. Pass `overrides`
 * to set individual fields.
 */

import type { Frame } from '../types/telemetry';

export function makeFrame(t = 1, overrides: Partial<Frame> = {}): Frame {
  return {
    t,
    power_thermal: 3_000_000_000 + t * 1_000_000,
    T_hot: 600 + t,
    T_cold: 568 + t,
    T_avg: 584 + t,
    T_fuel: 1100 + t,
    rod_position: 0.5,
    P_primary_Pa: 15_500_000 + t * 1_000,
    P_primary_MPa: 15.5 + t * 0.001,
    Q_sg: 3_000_000_000,
    P_steam_Pa: 6_899_000,
    P_steam_MPa: 6.899,
    T_secondary: 558,
    level_sg: 0.5,
    time_to_level_floor_s: null,
    m_steam: 1_669.01,
    m_dump: 0,
    P_electric: 990_000_000,
    turbine_load: 1,
    T_ref: 583,
    turbine_load_demand_effective: 1,
    turbine_trip_active: false,
    m_fw: 1_669.01,
    m_fw_max: 2_002.81,
    m_fw_demand: 1_669.01,
    fw_saturated: false,
    feedwater_manual_effective: null,
    rod_demand: 0.5,
    rod_auto_acting: false,
    turbine_load_demand: 1,
    turbine_trip: false,
    rod_auto: false,
    level_setpoint: 0.5,
    feedwater_manual: null,
    rho_rod: t * 1e-6,
    rho_doppler: -t * 1e-6,
    rho_moderator: -t * 2e-6,
    rho_total: -t * 2e-6,
    running: true,
    speed: 1,
    scrammed: false,
    rod_command: 0.5,
    model_limit: null,
    ...overrides,
  };
}
