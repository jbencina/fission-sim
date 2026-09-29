/**
 * The ten live trend charts: what each plots, in which colour, and how its
 * y axis is ranged.
 *
 * Colours are CSS variable names (index.css), shared between related
 * quantities: the primary trace of each chart is white, rods are grey, fuel
 * and its Doppler feedback light grey, coolant and its moderator feedback
 * blue. Dashed grey lines are references for the solid trace (heat removed
 * vs. heat made, demand or setpoint vs. actual plant state).
 */

import type { Frame } from '../types/telemetry'
import type { RangeSpec } from './autoRange'
import { toMPa, toMW, toPcm, toPercent } from './chartData'

// Steam dump begins opening at 7.6 MPa and is fully open by 8.2 MPa in the
// turbine model; keep these learner-facing chart references in the same units
// as the y axis.
const STEAM_DUMP_SETPOINT_MPA = 7.6

export interface SeriesSpec {
  label: string
  /** CSS variable holding the line colour, e.g. '--series-blue'. */
  color: string
  value: (frame: Frame) => number
  /** Line width [CSS px]; default 1.1, and 1 for dashed references. */
  width?: number
  /** Dash pattern [CSS px] for reference lines. */
  dash?: number[]
}

export interface ChartSpec {
  id: string
  title: string
  unit: string
  /** Plain-language explanation shown from the chart's info button. */
  description: string
  /** Decimals for legend values. */
  decimals: number
  range: RangeSpec
  series: SeriesSpec[]
  /** Draw a reference line at zero (critical, for reactivity). */
  zeroLine?: boolean
}

export const CHART_SPECS: ChartSpec[] = [
  {
    id: 'power',
    title: 'Thermal power',
    unit: 'MW',
    description:
      'Fission power in the core (solid) and heat removed by the steam ' +
      'generator (dashed). Design: 3000 MW. At steady state the two match; ' +
      'while they differ, the fuel and coolant are heating up or cooling down.',
    decimals: 1,
    range: { minSpan: 100, floor: 0 },
    series: [
      { label: 'Core', color: '--series-ink', value: (f) => toMW(f.power_thermal), width: 1.5 },
      { label: 'SG removal', color: '--series-gray', value: (f) => toMW(f.Q_sg), dash: [4, 3], width: 1 },
    ],
  },
  {
    id: 'reactivity',
    title: 'Reactivity',
    unit: 'pcm',
    description:
      'Net reactivity and its three parts: control rods, Doppler (fuel ' +
      'temperature) feedback and moderator (coolant temperature) feedback. ' +
      'Zero is exactly critical and power holds steady; above zero power ' +
      'rises, below zero it falls.',
    decimals: 1,
    range: { minSpan: 100, includeZero: true },
    zeroLine: true,
    // Net last, so it draws on top of its parts.
    series: [
      { label: 'Rods', color: '--series-rod', value: (f) => toPcm(f.rho_rod) },
      { label: 'Doppler', color: '--series-hot', value: (f) => toPcm(f.rho_doppler) },
      { label: 'Moderator', color: '--series-blue', value: (f) => toPcm(f.rho_moderator) },
      { label: 'Net', color: '--series-ink', value: (f) => toPcm(f.rho_total), width: 1.5 },
    ],
  },
  {
    id: 'coolant',
    title: 'Coolant temperature',
    unit: 'K',
    description:
      'Primary coolant leaving the core (hot leg), returning to it (cold leg), ' +
      'their average, which drives moderator feedback, and T_ref from the ' +
      'turbine-admission program. In AUTO rod control, rods move T_avg toward ' +
      'that reference. Design: 597.7 K hot, 583.0 K average, 568.3 K cold.',
    decimals: 1,
    range: { minSpan: 10 },
    series: [
      { label: 'Hot leg', color: '--series-hot', value: (f) => f.T_hot },
      { label: 'Average', color: '--series-ink', value: (f) => f.T_avg, width: 1.5 },
      { label: 'Cold leg', color: '--series-blue', value: (f) => f.T_cold },
      {
        label: 'T_ref',
        color: '--series-gray',
        value: (f) => f.T_ref,
        dash: [4, 3],
        width: 1,
      },
    ],
  },
  {
    id: 'fuel',
    title: 'Fuel temperature',
    unit: 'K',
    description:
      'Lumped average temperature of all the fuel (one value for the whole ' +
      'core). Design: 1100 K. It responds to power within seconds, and its ' +
      'Doppler feedback is the first thing to push back on a power change.',
    decimals: 1,
    range: { minSpan: 20 },
    series: [{ label: 'Fuel', color: '--series-hot', value: (f) => f.T_fuel, width: 1.5 }],
  },
  {
    id: 'pressure',
    title: 'Primary pressure',
    unit: 'MPa',
    description:
      'Primary system pressure, held by the pressurizer heaters and spray. ' +
      'Design: 15.5 MPa. It follows coolant temperature: warmer water expands ' +
      'into the pressurizer and compresses its steam.',
    decimals: 3,
    range: { minSpan: 0.2 },
    series: [
      { label: 'Pressure', color: '--series-ink', value: (f) => f.P_primary_MPa, width: 1.5 },
    ],
  },
  {
    id: 'rods',
    title: 'Control rods',
    unit: '% withdrawn',
    description:
      'Control-bank position (solid) and active demand (dashed), in % of ' +
      'travel withdrawn. In AUTO, Demand comes from the T_avg controller; in ' +
      'MANUAL, Demand follows the retained operator command after a bumpless ' +
      'transfer. The bank moves at 1 % per second; each 1 % is worth 12 pcm. ' +
      'Design: 50 %. The inactive manual command is not plotted while AUTO is active.',
    decimals: 1,
    range: { minSpan: 10, floor: 0, ceil: 100 },
    series: [
      { label: 'Position', color: '--series-rod', value: (f) => toPercent(f.rod_position), width: 1.5 },
      { label: 'Demand', color: '--series-gray', value: (f) => toPercent(f.rod_demand), dash: [4, 3], width: 1 },
    ],
  },
  {
    id: 'steam-pressure',
    title: 'Steam pressure',
    unit: 'MPa',
    description:
      'Secondary steam pressure in the lumped steam-generator shell. The dashed ' +
      'line is the 7.6 MPa steam-dump opening setpoint; the dump is fully open ' +
      'at 8.2 MPa.',
    decimals: 2,
    range: { minSpan: 1, floor: 3 },
    series: [
      { label: 'Steam', color: '--series-ink', value: (f) => toMPa(f.P_steam_Pa), width: 1.5 },
      {
        label: 'Dump setpoint',
        color: '--series-gray',
        value: () => STEAM_DUMP_SETPOINT_MPA,
        dash: [4, 3],
        width: 1,
      },
    ],
  },
  {
    id: 'sg-level',
    title: 'SG level',
    unit: '% collapsed',
    description:
      'SG collapsed liquid fraction (4 SGs lumped, no shrink/swell). The dashed ' +
      'line is the level controller setpoint. The model validity limits are ' +
      '30 % and 95 %; outside them the simple heat-transfer picture no longer applies.',
    decimals: 1,
    range: { minSpan: 10, floor: 0, ceil: 100 },
    series: [
      { label: 'Level', color: '--series-ink', value: (f) => toPercent(f.level_sg), width: 1.5 },
      { label: 'Setpoint', color: '--series-gray', value: (f) => toPercent(f.level_setpoint), dash: [4, 3], width: 1 },
    ],
  },
  {
    id: 'steam-feed-flow',
    title: 'Steam & feed flow',
    unit: 'kg/s',
    description:
      'Steam to the turbine, steam dump flow, actual feedwater and demanded ' +
      'feedwater. Feedwater above the total steam outflow raises SG level; ' +
      'feedwater below it lowers level.',
    decimals: 0,
    range: { minSpan: 250, floor: 0 },
    series: [
      { label: 'Steam to turbine', color: '--series-ink', value: (f) => f.m_steam, width: 1.5 },
      { label: 'Steam dump', color: '--series-hot', value: (f) => f.m_dump },
      { label: 'Feedwater', color: '--series-blue', value: (f) => f.m_fw },
      { label: 'Feed demand', color: '--series-gray', value: (f) => f.m_fw_demand, dash: [4, 3], width: 1 },
    ],
  },
  {
    id: 'electric-output',
    title: 'Electrical output',
    unit: 'MW gross',
    description:
      'Gross electrical output from a fixed-efficiency proxy based on steam ' +
      'flow. Turbine admission is a valve opening, not an MW demand, so equal ' +
      'admission changes do not imply equal electrical-output changes.',
    decimals: 1,
    range: { minSpan: 100, floor: 0 },
    series: [
      { label: 'Gross', color: '--series-ink', value: (f) => toMW(f.P_electric), width: 1.5 },
    ],
  },
]
