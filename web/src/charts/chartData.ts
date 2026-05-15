import type { Frame } from '../types/telemetry';

export interface PowerPoint {
  /** Relative time in seconds; 0 = newest, -60 = oldest in window. */
  t_rel: number;
  /** Thermal power in MW (raw Watts / 1e6). */
  power_MW: number;
}

export interface TemperaturePoint {
  /** Relative time in seconds; 0 = newest. */
  t_rel: number;
  /** Hot-leg temperature [K] */
  T_hot: number;
  /** Cold-leg temperature [K] */
  T_cold: number;
  /** Average primary temperature [K] */
  T_avg: number;
  /** Bulk fuel temperature [K] */
  T_fuel: number;
}

export interface PressurePoint {
  /** Relative time in seconds; 0 = newest. */
  t_rel: number;
  /** Primary system pressure [MPa] */
  P_MPa: number;
}

export interface ReactivityPoint {
  /** Relative time in seconds; 0 = newest. */
  t_rel: number;
  /** Rod reactivity worth [pcm] */
  rho_rod_pcm: number;
  /** Doppler feedback reactivity [pcm] */
  rho_doppler_pcm: number;
  /** Moderator temperature feedback reactivity [pcm] */
  rho_moderator_pcm: number;
  /** Total (net) reactivity [pcm] */
  rho_total_pcm: number;
}

function sampledHistory(history: Frame[]): Frame[] {
  return history.filter((_, i) => i % 2 === 0 || i === history.length - 1);
}

function latestTime(history: Frame[]): number {
  return history[history.length - 1].t;
}

export function toPowerPoints(history: Frame[]): PowerPoint[] {
  if (history.length === 0) return [];
  const latest = latestTime(history);
  return sampledHistory(history).map((frame) => ({
    t_rel: +(frame.t - latest).toFixed(2),
    power_MW: +(frame.power_thermal / 1e6).toFixed(3),
  }));
}

export function toTemperaturePoints(history: Frame[]): TemperaturePoint[] {
  if (history.length === 0) return [];
  const latest = latestTime(history);
  return sampledHistory(history).map((frame) => ({
    t_rel: +(frame.t - latest).toFixed(2),
    T_hot: +frame.T_hot.toFixed(2),
    T_cold: +frame.T_cold.toFixed(2),
    T_avg: +frame.T_avg.toFixed(2),
    T_fuel: +frame.T_fuel.toFixed(2),
  }));
}

export function toPressurePoints(history: Frame[]): PressurePoint[] {
  if (history.length === 0) return [];
  const latest = latestTime(history);
  return sampledHistory(history).map((frame) => ({
    t_rel: +(frame.t - latest).toFixed(2),
    P_MPa: +frame.P_primary_MPa.toFixed(4),
  }));
}

export function toReactivityPoints(history: Frame[]): ReactivityPoint[] {
  if (history.length === 0) return [];
  const latest = latestTime(history);
  return sampledHistory(history).map((frame) => ({
    t_rel: +(frame.t - latest).toFixed(2),
    rho_rod_pcm: +(frame.rho_rod * 1e5).toFixed(2),
    rho_doppler_pcm: +(frame.rho_doppler * 1e5).toFixed(2),
    rho_moderator_pcm: +(frame.rho_moderator * 1e5).toFixed(2),
    rho_total_pcm: +(frame.rho_total * 1e5).toFixed(2),
  }));
}
