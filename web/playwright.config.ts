/**
 * Playwright end-to-end test configuration for fission-sim web UI.
 *
 * Assumptions:
 *   - The dev stack is already running (started via `make dev` or equivalent).
 *   - The frontend is served at http://127.0.0.1:5173 (Vite default).
 *   - The backend WebSocket is served at ws://127.0.0.1:8000.
 *
 * Run: npm run e2e (from web/)
 * Pre-condition: `make dev` must be running in a separate terminal.
 */

import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  // Location of e2e spec files.
  testDir: './e2e',

  // Run specs sequentially — we have one shared backend state.
  fullyParallel: false,
  workers: 1,

  // Fail the build on CI if any spec is skipped via test.only.
  forbidOnly: !!process.env['CI'],

  // No retries — keep failures visible.
  retries: 0,

  // Plain list reporter; no HTML report to keep the test self-contained.
  reporter: [['list']],

  use: {
    // All tests navigate relative to this base URL.
    baseURL: 'http://127.0.0.1:5173',

    // Maximum time for each Playwright action (click, fill, etc.).
    actionTimeout: 15_000,

    // Capture trace on first retry (useful for debugging CI failures).
    trace: 'on-first-retry',
  },

  // Global assertion timeout.
  expect: {
    timeout: 30_000,
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
