import type { Config } from 'tailwindcss'

/*
 * Colours are CSS variables defined in src/index.css, so a class such as
 * `bg-canvas` always means the console's one palette.
 */
const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
      colors: {
        canvas: 'var(--canvas)',
        surface: {
          DEFAULT: 'var(--surface)',
          solid: 'var(--surface-solid)',
          2: 'var(--surface-2)',
          3: 'var(--surface-3)',
        },
        raised: 'var(--raised)',
        ink: {
          DEFAULT: 'var(--ink)',
          2: 'var(--ink-2)',
          3: 'var(--ink-3)',
        },
        line: {
          DEFAULT: 'var(--line)',
          strong: 'var(--line-strong)',
        },
        accent: {
          DEFAULT: 'var(--accent)',
          hover: 'var(--accent-hover)',
          soft: 'var(--accent-soft)',
          ink: 'var(--accent-ink)',
        },
        live: 'var(--live)',
        warn: {
          DEFAULT: 'var(--warn)',
          ink: 'var(--warn-ink)',
          soft: 'var(--warn-soft)',
          line: 'var(--warn-line)',
        },
        danger: {
          DEFAULT: 'var(--danger)',
          hover: 'var(--danger-hover)',
          ink: 'var(--danger-ink)',
          soft: 'var(--danger-soft)',
          line: 'var(--danger-line)',
        },
        'seg-on': 'var(--seg-on)',
      },
      boxShadow: {
        card: 'var(--shadow-card)',
        float: 'var(--shadow-float)',
        pop: 'var(--shadow-pop)',
      },
      transitionTimingFunction: {
        smooth: 'cubic-bezier(0.2, 0.7, 0.2, 1)',
      },
      keyframes: {
        'pop-in': {
          from: { opacity: '0', transform: 'translateY(4px) scale(0.98)' },
          to: { opacity: '1', transform: 'translateY(0) scale(1)' },
        },
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
      },
      animation: {
        'pop-in': 'pop-in 0.18s cubic-bezier(0.2, 0.7, 0.2, 1)',
        'fade-in': 'fade-in 0.18s cubic-bezier(0.2, 0.7, 0.2, 1)',
      },
    },
  },
  plugins: [],
}

export default config
