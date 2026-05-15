/**
 * chartTheme — shared Recharts axis/grid/tooltip styling constants.
 *
 * All colours use Tailwind slate palette values to keep charts visually
 * consistent with the dark-themed AppShell.
 */

/** Stroke for CartesianGrid lines — slate-800. */
export const GRID_STROKE = 'rgb(30 41 59)';

/** Tick text fill — slate-400. */
export const TICK_FILL = 'rgb(148 163 184)';

/** Axis label fill — slate-400. */
export const AXIS_LABEL_FILL = 'rgb(148 163 184)';

/** Tooltip wrapper class applied via `wrapperStyle`. */
export const TOOLTIP_WRAPPER_STYLE: React.CSSProperties = {
  backgroundColor: 'rgb(30 41 59)', // slate-800
  border: '1px solid rgb(51 65 85)', // slate-700
  borderRadius: '0.5rem',
  color: 'rgb(241 245 249)', // slate-100
  fontSize: '0.75rem',
  padding: '6px 10px',
};

/**
 * Common X-axis props for all charts.
 * Displays relative time in seconds; newest data is at 0, oldest at -60.
 */
export const X_AXIS_PROPS = {
  type: 'number' as const,
  dataKey: 't_rel',
  domain: [-60, 0] as [number, number],
  tickCount: 7,
  tickFormatter: (v: number) => `${v}`,
  label: {
    value: 't [s]  (now = 0)',
    position: 'insideBottom' as const,
    offset: -2,
    fill: AXIS_LABEL_FILL,
    fontSize: 11,
  },
  tick: { fill: TICK_FILL, fontSize: 11 },
  stroke: TICK_FILL,
};
