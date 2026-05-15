/**
 * Smoke test: SCRAM drops thermal power.
 *
 * Pre-condition: the dev stack must already be running (`make dev`).
 * The test does NOT start the stack itself.
 *
 * Assertion A-18:
 *   Navigate to the app, wait for "Connected" chip, reset the sim to ensure
 *   a clean steady-state start, read the initial thermal power, click SCRAM +
 *   confirm the modal, wait 12 s, assert power dropped by ≥50%.
 */

import { test, expect, type Locator, type Page } from '@playwright/test'

async function numericText(locator: Locator): Promise<number> {
  const text = (await locator.textContent()) ?? ''
  return parseFloat(text.trim())
}

async function resumeIfPaused(page: Page): Promise<void> {
  const resume = page.getByRole('button', { name: /^resume$/i })
  if (await resume.isVisible().catch(() => false)) {
    await resume.click()
  }
}

test('SCRAM drops thermal power', async ({ page }) => {
  await page.goto('/')

  // Wait for the WebSocket to connect — the UI shows a "Connected" chip.
  await expect(page.getByText('Connected')).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText(/personal learning project/i)).toBeVisible()

  // ── Reset to a clean steady-state before reading initial power ─────────────
  //
  // The dev server is persistent: if a previous test run SCRAMMed the reactor,
  // the power is already near zero. We send a Reset Simulation command up front
  // so this test always starts from the same known state (t=0, n=1, full power).
  //
  // Reset Simulation button text is "Reset Simulation" — click it, then confirm.
  await resumeIfPaused(page)
  await page.getByRole('button', { name: /reset simulation/i }).click()
  // Confirm modal: the dialog has a confirm button with label "Reset".
  await page.getByRole('dialog').getByRole('button', { name: /reset/i }).click()

  // Reset preserves run/speed state, so force a known running 1× baseline.
  await resumeIfPaused(page)
  await page.getByRole('button', { name: /^1×$/ }).click()

  // Give the simulator a moment to rebuild state and emit a fresh telemetry frame.
  await page.waitForTimeout(2_000)

  // ── Read the initial thermal power ─────────────────────────────────────────
  //
  // The StatusTile for power has data-testid="status-power_thermal" on the card
  // and data-testid="status-power_thermal-value" on the inner value <span>.
  // We read the value span to avoid tooltip text (which also contains numbers)
  // from being included in the textContent.
  const powerValueSpan = page.getByTestId('status-power_thermal-value')
  await expect(powerValueSpan).toBeVisible()

  // Poll until the span shows a real numeric value (not the placeholder "—").
  // formatMW returns (W / 1e6).toFixed(1), so full power is "3000.0".
  await expect.poll(
    async () => {
      const t = (await powerValueSpan.textContent()) ?? ''
      // Reject the placeholder dash; accept any string containing a digit.
      return /\d/.test(t) ? t : null
    },
    { timeout: 15_000 },
  ).not.toBeNull()

  // Read and parse the initial power value in MW.
  const initialMW = await numericText(powerValueSpan)
  // Sanity check: the simulator starts at ~3000 MW (n=1 × 3000 MWth design).
  expect(initialMW).toBeGreaterThan(100)

  // ── Initiate SCRAM ─────────────────────────────────────────────────────────
  //
  // Click the SCRAM button in the Safety section of ControlPanel.
  // The button text is "SCRAM" (all-caps) — getByRole matches case-insensitively.
  await page.getByRole('button', { name: /^scram$/i }).click()

  // Confirm the SCRAM modal. The ConfirmDialog renders a confirm button with
  // confirmLabel="SCRAM" (set by ControlPanel). We target it inside the dialog
  // role to avoid matching the now-disabled main SCRAM button.
  await page.getByRole('dialog').getByRole('button', { name: /^scram$/i }).click()

  // ── Wait for power to drop ─────────────────────────────────────────────────
  //
  // ── Assert power dropped by ≥50% ───────────────────────────────────────────
  // Poll the live readout rather than sleeping a fixed interval; this handles
  // both fast machines and temporarily slow simulator steps.
  await expect.poll(
    async () => numericText(powerValueSpan),
    { timeout: 20_000, intervals: [500] },
  ).toBeLessThan(initialMW * 0.5)
})
