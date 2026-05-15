import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Slate-based dark palette
        surface: {
          950: '#020617', // slate-950
          900: '#0f172a', // slate-900
          800: '#1e293b', // slate-800
          700: '#334155', // slate-700
        },
        // Amber accent for reactor-status indicators
        accent: {
          DEFAULT: '#f59e0b', // amber-400
          light: '#fcd34d',   // amber-300
          dark: '#d97706',    // amber-600
        },
        // Blue accent for control/informational elements
        info: {
          DEFAULT: '#3b82f6', // blue-500
          light: '#60a5fa',   // blue-400
          dark: '#1d4ed8',    // blue-700
        },
      },
    },
  },
  plugins: [],
}

export default config
