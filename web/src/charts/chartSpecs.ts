/**
 * The six live trend charts: what each plots, in which colour, and how its
 * y axis is ranged.
 *
 * Colours are CSS variable names (index.css) so they follow the theme, and
 * they are shared between related quantities: rods are purple, fuel and its
 * Doppler feedback orange, coolant and its moderator feedback teal. Dashed
 * lines are references for the solid trace (heat removed vs. heat made,
 * rod command vs. rod position).
 */

import type { Frame } from '../types/telemetry'
import type { RangeSpec } from './autoRange'
import { toMW, toPcm, toPercent } from './chartData'

export interface SeriesSpec {
  label: string
  /** CSS variable holding the line colour, e.g. '--series-blue'. */
  color: string
  value: (frame: Frame) => number
  /** Line width [CSS px]; default 1.5. */
  width?: number
  /** Dash pattern [CSS px] for reference lines. */
  dash?: number[]
  /** Soft gradient fill under the line. */
  fill?: boolean
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
      { label: 'Core', color: '--series-blue', value: (f) => toMW(f.power_thermal), width: 2, fill: true },
      { label: 'SG removal', color: '--series-gray', value: (f) => toMW(f.Q_sg), dash: [4, 3] },
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
      { label: 'Rods', color: '--series-purple', value: (f) => toPcm(f.rho_rod) },
      { label: 'Doppler', color: '--series-orange', value: (f) => toPcm(f.rho_doppler) },
      { label: 'Moderator', color: '--series-teal', value: (f) => toPcm(f.rho_moderator) },
      { label: 'Net', color: '--series-ink', value: (f) => toPcm(f.rho_total), width: 2 },
    ],
  },
  {
    id: 'coolant',
    title: 'Coolant temperature',
    unit: 'K',
    description:
      'Primary coolant leaving the core (hot leg), returning to it (cold leg), ' +
      'and their average, which drives moderator feedback. Design: 597.7 K ' +
      'hot, 583.0 K average, 568.3 K cold.',
    decimals: 1,
    range: { minSpan: 10 },
    series: [
      { label: 'Hot leg', color: '--series-red', value: (f) => f.T_hot },
      { label: 'Average', color: '--series-teal', value: (f) => f.T_avg, width: 2 },
      { label: 'Cold leg', color: '--series-blue', value: (f) => f.T_cold },
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
    series: [{ label: 'Fuel', color: '--series-orange', value: (f) => f.T_fuel, width: 2, fill: true }],
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
      { label: 'Pressure', color: '--series-indigo', value: (f) => f.P_primary_MPa, width: 2, fill: true },
    ],
  },
  {
    id: 'rods',
    title: 'Control rods',
    unit: '% withdrawn',
    description:
      'Control-bank position (solid) and the operator command it moves toward ' +
      '(dashed), in % of travel withdrawn. The bank moves at 1 % per second; ' +
      'each 1 % is worth 12 pcm. Design: 50 %.',
    decimals: 1,
    range: { minSpan: 10, floor: 0, ceil: 100 },
    series: [
      { label: 'Position', color: '--series-purple', value: (f) => toPercent(f.rod_position), width: 2, fill: true },
      { label: 'Command', color: '--series-gray', value: (f) => toPercent(f.rod_command), dash: [4, 3] },
    ],
  },
]
