import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

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
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8000',
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
