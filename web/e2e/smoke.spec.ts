/**
 * Smoke test: SCRAM drops thermal power.
 *
 * Pre-condition: the dev stack must already be running (`make dev`).
 * The test does NOT start the stack itself.
 *
 * A second check confirms that an operator-control explanation and a status
 * explanation can both be revealed with the keyboard alone.
 *
 * SCRAM check:
 *   Navigate to the app, wait for "Connected", reset the sim to ensure
 *   a clean steady-state start, read the initial thermal power, click SCRAM +
 *   confirm the modal, wait 12 s, assert power dropped by ≥50%.
 */

import { test, expect, type Locator, type Page } from '@playwright/test'

/** Parse a readout such as "3,000.0" or "−5,528.9" (typographic minus). */
async function numericText(locator: Locator): Promise<number> {
  const text = (await locator.textContent()) ?? ''
  return parseFloat(text.trim().replace(/,/g, '').replace('\u2212', '-'))
}

async function resumeIfPaused(page: Page): Promise<void> {
  const resume = page.getByRole('button', { name: /^resume$/i })
  if (await resume.isVisible().catch(() => false)) {
    await resume.click()
  }
}

/** Press Tab until `target` has focus, failing if it is never reached. */
async function tabTo(page: Page, target: Locator, maxPresses = 80): Promise<void> {
  for (let i = 0; i < maxPresses; i++) {
    await page.keyboard.press('Tab')
    if (await target.evaluate((el) => el === document.activeElement)) return
  }
  throw new Error(`Tab never reached ${target}`)
}

/** Assert the focused control's explanation is visible and is its accessible description. */
async function expectHelpShownFor(page: Page, control: Locator): Promise<void> {
  const tipId = await control.getAttribute('aria-describedby')
  expect(tipId).toBeTruthy()
  const tip = page.locator(`[id="${tipId}"]`)
  await expect(tip).toHaveCSS('opacity', '1')
  await expect(control).toHaveAccessibleDescription(/\w{3,}/)
}

test('educational help is reachable with the keyboard', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('Connected')).toBeVisible({ timeout: 15_000 })

  // Operator explanation: Reset Simulation is enabled whether or not the
  // reactor is scrammed, so this check does not depend on test order. The
  // controls come before the status readouts in tab order.
  const resetButton = page.getByRole('button', { name: /reset simulation/i })
  await tabTo(page, resetButton)
  await expectHelpShownFor(page, resetButton)

  // Status explanation: the thermal-power tile's info button.
  const powerInfo = page.getByTestId('status-power_thermal').getByRole('button')
  await tabTo(page, powerInfo)
  await expectHelpShownFor(page, powerInfo)

  // Pinning it with Enter must not leave it open once focus moves on.
  const powerTip = page.locator(`[id="${await powerInfo.getAttribute('aria-describedby')}"]`)
  await page.keyboard.press('Enter')
  await page.keyboard.press('Tab')
  await expect(powerTip).toHaveCSS('opacity', '0')
})

test('SCRAM drops thermal power', async ({ page }) => {
  await page.goto('/')

  // Wait for the WebSocket to connect — the toolbar shows "Connected".
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
  // The readout row for power has data-testid="status-power_thermal" on the row
  // and data-testid="status-power_thermal-value" on the inner value <span>.
  // We read the value span to avoid tooltip text (which also contains numbers)
  // from being included in the textContent.
  const powerValueSpan = page.getByTestId('status-power_thermal-value')
  await expect(powerValueSpan).toBeVisible()

  // Poll until the span shows a real numeric value (not the placeholder "—").
  // Power is shown in MW with one decimal and thousands separators: "3,000.0".
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
