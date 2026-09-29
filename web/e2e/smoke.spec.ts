/**
 * Smoke tests for the operator dashboard.
 *
 * Pre-condition: the dev stack must already be running (`make dev`).
 * The test does NOT start the stack itself.
 *
 * The checks reset the persistent backend before plant transients, then use
 * polling against live readouts or telemetry frames instead of fixed sleeps.
 */

import { test, expect, type Locator, type Page } from '@playwright/test'

type Command = Record<string, boolean | number | null | string>

interface FrameSnapshot {
  feedwater_manual?: number | null
  level_setpoint?: number
  rod_auto?: boolean
  rod_auto_acting?: boolean
  rod_command?: number
  rod_position?: number
  running?: boolean
  scrammed?: boolean
  speed?: number
  t?: number
  turbine_load_demand?: number
  turbine_trip?: boolean
}

test.setTimeout(180_000)

/** Parse a readout such as "3,000.0" or "−5,528.9" (typographic minus). */
async function numericText(locator: Locator): Promise<number> {
  const text = (await locator.textContent()) ?? ''
  return parseFloat(text.trim().replace(/,/g, '').replace('\u2212', '-'))
}

async function waitForConsole(page: Page): Promise<void> {
  await page.goto('/')
  await expect(page.getByText('Connected')).toBeVisible({ timeout: 20_000 })
  await expect(page.getByText(/personal learning project/i)).toBeVisible()
}

async function sendCommand(page: Page, command: Command): Promise<void> {
  await page.evaluate(
    (cmd) =>
      new Promise<void>((resolve, reject) => {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const ws = new WebSocket(`${protocol}//${window.location.host}/ws/telemetry`)
        let finished = false
        const timer = window.setTimeout(() => {
          finished = true
          ws.close()
          reject(new Error(`Timed out waiting for ack for ${cmd.type}`))
        }, 8_000)
        const finish = (error?: Error) => {
          if (finished) return
          finished = true
          window.clearTimeout(timer)
          ws.close()
          if (error) reject(error)
          else resolve()
        }

        ws.onopen = () => ws.send(JSON.stringify(cmd))
        ws.onerror = () => finish(new Error(`WebSocket error sending ${cmd.type}`))
        ws.onmessage = (event) => {
          const data = JSON.parse(event.data) as { command?: string; detail?: string; type?: string }
          if (data.type === 'ack' && data.command === cmd.type) finish()
          else if (data.type === 'error') finish(new Error(data.detail ?? `Command ${cmd.type} failed`))
        }
      }),
    command,
  )
}

async function readLatestFrame(page: Page): Promise<FrameSnapshot> {
  return page.evaluate(
    () =>
      new Promise<FrameSnapshot>((resolve, reject) => {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const ws = new WebSocket(`${protocol}//${window.location.host}/ws/telemetry`)
        let finished = false
        const timer = window.setTimeout(() => {
          finished = true
          ws.close()
          reject(new Error('Timed out waiting for telemetry frame'))
        }, 8_000)
        const finish = (frame: FrameSnapshot) => {
          if (finished) return
          finished = true
          window.clearTimeout(timer)
          ws.close()
          resolve(frame)
        }

        ws.onerror = () => {
          if (finished) return
          finished = true
          window.clearTimeout(timer)
          reject(new Error('WebSocket error reading telemetry frame'))
        }
        ws.onmessage = (event) => {
          const data = JSON.parse(event.data) as FrameSnapshot & { type?: string }
          if (typeof data.t === 'number') finish(data)
        }
      }),
  )
}

async function resetToDesignFixture(page: Page, speed: 1 | 2 | 5 | 10 = 1): Promise<void> {
  await sendCommand(page, { type: 'reset' })
  await sendCommand(page, { type: 'resume' })
  await sendCommand(page, { type: 'set_speed', value: speed })
  await sendCommand(page, { type: 'set_turbine_load', value: 1 })
  await sendCommand(page, { type: 'set_rod_auto', value: false })
  await sendCommand(page, { type: 'set_level_setpoint', value: 0.5 })
  await sendCommand(page, { type: 'set_feedwater_manual', value: null })

  await expect
    .poll(
      async () => {
        const frame = await readLatestFrame(page)
        return (
          frame.running === true &&
          frame.speed === speed &&
          frame.turbine_load_demand === 1 &&
          frame.rod_auto === false &&
          frame.scrammed === false &&
          frame.turbine_trip === false &&
          frame.feedwater_manual === null &&
          Math.abs((frame.level_setpoint ?? 0) - 0.5) < 1e-9
        )
      },
      { timeout: 20_000, intervals: [250, 500, 1_000] },
    )
    .toBe(true)
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
  await waitForConsole(page)

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
  await waitForConsole(page)

  // ── Reset to a clean steady-state before reading initial power ─────────────
  //
  // The dev server is persistent: if a previous test run SCRAMMed the reactor,
  // the power is already near zero. We send a Reset Simulation command up front
  // so this test always starts from the same known state (t=0, n=1, full power).
  //
  // Use backend commands for the fixture so the shared persistent simulator is
  // in a known state before the UI SCRAM action under test.
  await resetToDesignFixture(page, 1)

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

test('turbine trip raises steam pressure and opens the dump', async ({ page }) => {
  await waitForConsole(page)
  await resetToDesignFixture(page, 10)

  const steamPressure = page.getByTestId('status-P_steam_MPa-value')
  await expect(steamPressure).toBeVisible()
  await expect
    .poll(async () => (Number.isFinite(await numericText(steamPressure)) ? await numericText(steamPressure) : null), {
      timeout: 20_000,
      intervals: [250, 500, 1_000],
    })
    .not.toBeNull()
  const initialSteamPressure = await numericText(steamPressure)
  expect(initialSteamPressure).toBeGreaterThan(5)

  const secondaryControls = page.locator('section[aria-label="Secondary-side controls"]')
  await secondaryControls.getByRole('button', { name: /^trip turbine$/i }).click()
  await page.getByRole('dialog').getByRole('button', { name: /^trip turbine$/i }).click()

  await expect
    .poll(async () => numericText(steamPressure), {
      timeout: 60_000,
      intervals: [500, 1_000, 2_000],
    })
    .toBeGreaterThan(initialSteamPressure + 0.6)
  await expect(page.locator('section[aria-label="Events"]').getByText(/Steam dump opened/i).first()).toBeVisible({
    timeout: 60_000,
  })

  await secondaryControls.getByRole('button', { name: /reset turbine trip/i }).click()
  await expect(page.getByTestId('status-turbine_load').getByText(/demand 0 %/i)).toBeVisible({
    timeout: 20_000,
  })
})

test('rod AUTO mode displays status and returns to MANUAL bumplessly', async ({ page }) => {
  await waitForConsole(page)
  await resetToDesignFixture(page, 10)

  const operatorControls = page.locator('section[aria-label="Operator controls"]')
  const rodMode = operatorControls.getByRole('group', { name: /rod control mode/i })
  const rodPositionValue = page.getByTestId('status-rod_position-value')
  const rodCommandValue = page.getByTestId('status-rod_command-value')

  try {
    await rodMode.getByRole('button', { name: /^auto$/i }).click()
    await expect(operatorControls.getByText(/AUTO ACTIVE/i)).toBeVisible({ timeout: 20_000 })
    await sendCommand(page, { type: 'set_turbine_load', value: 0.9 })

    await expect
      .poll(
        async () => {
          const frame = await readLatestFrame(page)
          if (frame.rod_auto !== true || frame.rod_command === undefined || frame.rod_position === undefined) {
            return 0
          }
          return Math.abs(frame.rod_position - 0.5)
        },
        { timeout: 60_000, intervals: [500, 1_000, 2_000] },
      )
      .toBeGreaterThan(0.01)

    await operatorControls.getByRole('button', { name: /^pause$/i }).click()
    await expect(operatorControls.getByRole('button', { name: /^resume$/i })).toBeVisible({ timeout: 20_000 })

    const pausedFrame = await readLatestFrame(page)
    expect(pausedFrame.running).toBe(false)
    let capturedPositionPct = 50
    await expect
      .poll(async () => {
        capturedPositionPct = await numericText(rodPositionValue)
        return Math.abs(capturedPositionPct - 50)
      }, {
        timeout: 20_000,
        intervals: [250, 500, 1_000],
      })
      .toBeGreaterThan(1)

    await rodMode.getByRole('button', { name: /^manual$/i }).click()
    await expect
      .poll(async () => Math.abs((await numericText(rodCommandValue)) - capturedPositionPct), {
        timeout: 20_000,
        intervals: [250, 500, 1_000],
      })
      .toBeLessThan(0.2)

    await operatorControls.getByRole('button', { name: /^resume$/i }).click()
    await expect
      .poll(
        async () => {
          const frame = await readLatestFrame(page)
          return frame.t === undefined || pausedFrame.t === undefined ? 0 : frame.t - pausedFrame.t
        },
        { timeout: 20_000, intervals: [250, 500, 1_000] },
      )
      .toBeGreaterThan(2)

    const resumedPositionPct = await numericText(rodPositionValue)
    expect(Math.abs(resumedPositionPct - capturedPositionPct)).toBeLessThan(0.3)
    expect(Math.abs(50 - resumedPositionPct)).toBeGreaterThanOrEqual(Math.abs(50 - capturedPositionPct) - 0.3)
  } finally {
    await resetToDesignFixture(page, 1).catch(() => undefined)
  }
})
