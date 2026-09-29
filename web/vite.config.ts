import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

const apiPort = process.env.FISSION_SIM_API_PORT ?? '8000'
const apiHttpTarget = `http://127.0.0.1:${apiPort}`
const apiWsTarget = `ws://127.0.0.1:${apiPort}`

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // Bind all interfaces so the dev server is reachable on the LAN.
    // Vite prints both Local: and Network: URLs when host is true.
    host: true,
    proxy: {
      // Proxy targets stay on loopback — the proxy runs on the same host
      // as the backend, so going through 127.0.0.1 avoids an extra hop.
      '/api': {
        target: apiHttpTarget,
        changeOrigin: true,
      },
      '/ws': {
        target: apiWsTarget,
        ws: true,
        changeOrigin: true,
      },
    },
  },
  test: {
    // Use the node environment for store-only tests (no DOM needed for Zustand).
    environment: 'node',
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
  },
})
