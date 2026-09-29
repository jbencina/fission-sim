/**
 * Geometry regression for the plant schematic.
 *
 * The test drives the simulator through the high-risk schematic states and
 * verifies that every text box clears SVG strokes and other text boxes. It
 * also guards the dashboard-scale font sizes that keep the schematic legible.
 */

import { expect, test, type Browser, type Page } from '@playwright/test'

type Command = Record<string, boolean | number | null | string>

type FontRole = 'label' | 'status' | 'unit' | 'value'

interface FontMeasurement {
  label: string
  px: number
  role: FontRole
}

interface Inspection {
  failures: string[]
  fonts: FontMeasurement[]
  textCount: number
}

interface Scenario {
  name: string
  setup: (page: Page) => Promise<void>
}

interface ViewportCase {
  height: number
  isMobile?: boolean
  width: number
}

const SCHEMATIC_SELECTOR = 'section[aria-label*="schematic" i] svg[role="img"]'
const SCREENSHOT_DIR = process.env.SCHEMATIC_SCREENSHOT_DIR

test.setTimeout(240_000)

async function sendCommand(page: Page, command: Command): Promise<void> {
  await page.evaluate(
    (cmd) =>
      new Promise<void>((resolve, reject) => {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const ws = new WebSocket(`${protocol}//${window.location.host}/ws/telemetry`)
        const timer = window.setTimeout(() => {
          ws.close()
          reject(new Error(`Timed out waiting for ack for ${cmd.type}`))
        }, 8_000)

        ws.onopen = () => ws.send(JSON.stringify(cmd))
        ws.onerror = () => {
          window.clearTimeout(timer)
          reject(new Error(`WebSocket error sending ${cmd.type}`))
        }
        ws.onmessage = (event) => {
          const data = JSON.parse(event.data) as { detail?: string; type?: string }
          if (data.type === 'ack') {
            window.clearTimeout(timer)
            ws.close()
            resolve()
          } else if (data.type === 'error') {
            window.clearTimeout(timer)
            ws.close()
            reject(new Error(data.detail ?? `Command ${cmd.type} failed`))
          }
        }
      }),
    command,
  )
}

async function waitForConsole(page: Page): Promise<void> {
  await page.goto('/')
  await expect(page.getByText('Connected')).toBeVisible({ timeout: 20_000 })
  await expect(page.locator(SCHEMATIC_SELECTOR)).toBeVisible({ timeout: 10_000 })
  await page.waitForTimeout(500)
}

async function waitForBody(page: Page, pattern: RegExp, timeout = 20_000): Promise<void> {
  await expect.poll(async () => page.locator('body').innerText(), { timeout, intervals: [250, 500, 1_000] }).toMatch(pattern)
}

async function waitForSchematic(page: Page, pattern: RegExp, timeout = 20_000): Promise<void> {
  const schematic = page.locator(SCHEMATIC_SELECTOR)
  await expect.poll(async () => (await schematic.textContent()) ?? '', { timeout, intervals: [250, 500, 1_000] }).toMatch(pattern)
}

async function waitForPzrLevelAtLeast(page: Page, level: number, timeout = 60_000): Promise<void> {
  await page.evaluate(
    ({ level, timeout }) =>
      new Promise<void>((resolve, reject) => {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const ws = new WebSocket(`${protocol}//${window.location.host}/ws/telemetry`)
        const timer = window.setTimeout(() => {
          ws.close()
          reject(new Error(`Timed out waiting for pressurizer level >= ${level}`))
        }, timeout)

        ws.onerror = () => {
          window.clearTimeout(timer)
          reject(new Error('WebSocket error waiting for pressurizer level'))
        }
        ws.onmessage = (event) => {
          const data = JSON.parse(event.data) as { pzr_level?: number }
          if (typeof data.pzr_level === 'number' && data.pzr_level >= level) {
            window.clearTimeout(timer)
            ws.close()
            resolve()
          }
        }
      }),
    { level, timeout },
  )
}

async function resetToDesign(page: Page): Promise<void> {
  await sendCommand(page, { type: 'reset' })
  await sendCommand(page, { type: 'resume' })
  await sendCommand(page, { type: 'set_speed', value: 1 })
  await sendCommand(page, { type: 'set_turbine_load', value: 1 })
  await waitForBody(page, /critical, steady/i, 20_000)
  await page.waitForTimeout(500)
}

async function setSteady(page: Page): Promise<void> {
  await resetToDesign(page)
}

async function setTurbineTripWithDump(page: Page): Promise<void> {
  await resetToDesign(page)
  await sendCommand(page, { type: 'set_speed', value: 10 })
  await sendCommand(page, { type: 'turbine_trip' })
  await waitForSchematic(page, /DUMP\s+\d,\d{3}\s+kg\/s/i, 55_000)
  await page.waitForTimeout(500)
}

async function setScram(page: Page): Promise<void> {
  await resetToDesign(page)
  await sendCommand(page, { type: 'set_speed', value: 10 })
  await sendCommand(page, { type: 'scram' })
  await waitForBody(page, /SCRAM \(P-4\)|TRIPPED/i, 20_000)
  await page.waitForTimeout(500)
}

async function setFeedwaterManual(page: Page): Promise<void> {
  await resetToDesign(page)
  await sendCommand(page, { type: 'set_feedwater_manual', value: 0.85 })
  await waitForSchematic(page, /FW MAN[\s\S]*\d,\d{3}/i, 20_000)
  await page.waitForTimeout(500)
}

async function setTripPending(page: Page): Promise<void> {
  await resetToDesign(page)
  await sendCommand(page, { type: 'pause' })
  await sendCommand(page, { type: 'turbine_trip' })
  await waitForBody(page, /trip pending/i, 20_000)
  await page.waitForTimeout(300)
}

async function setTripResetPending(page: Page): Promise<void> {
  await resetToDesign(page)
  await sendCommand(page, { type: 'set_speed', value: 10 })
  await sendCommand(page, { type: 'turbine_trip' })
  await waitForSchematic(page, /TRIPPED/i, 20_000)
  await sendCommand(page, { type: 'pause' })
  await sendCommand(page, { type: 'reset_turbine_trip' })
  await waitForBody(page, /trip reset pending/i, 20_000)
  await page.waitForTimeout(300)
}

async function setScramResetShutdownInserted(page: Page): Promise<void> {
  await resetToDesign(page)
  await sendCommand(page, { type: 'set_speed', value: 10 })
  await sendCommand(page, { type: 'scram' })
  await waitForBody(page, /SCRAM \(P-4\)|shutdown bank inserted/i, 20_000)
  await sendCommand(page, { type: 'reset_scram' })
  await waitForBody(page, /shutdown bank inserted/i, 20_000)
  await page.waitForTimeout(300)
}

async function setPressurizerHighLevel(page: Page): Promise<void> {
  await resetToDesign(page)
  await sendCommand(page, { type: 'set_speed', value: 10 })
  await sendCommand(page, { type: 'set_pressure_setpoint', value: 10_000_000 })
  await waitForPzrLevelAtLeast(page, 0.75)
  await page.waitForTimeout(300)
}

function inspectionSummary(fonts: FontMeasurement[]): string {
  const roles: FontRole[] = ['label', 'unit', 'value', 'status']
  return roles
    .map((role) => {
      const values = fonts.filter((font) => font.role === role).map((font) => font.px)
      if (values.length === 0) return `${role} n/a`
      const min = Math.min(...values)
      return `${role} ${min.toFixed(2)} px`
    })
    .join(', ')
}

function assertFontThresholds(inspection: Inspection, viewport: ViewportCase, label: string): void {
  const minimum = (role: FontRole) => Math.min(...inspection.fonts.filter((font) => font.role === role).map((font) => font.px))

  if (viewport.width === 1440) {
    expect(minimum('label'), `${label} label text`).toBeGreaterThanOrEqual(10)
    expect(minimum('unit'), `${label} unit text`).toBeGreaterThanOrEqual(10)
    expect(minimum('value'), `${label} value text`).toBeGreaterThanOrEqual(13)
    const statusMinimum = minimum('status')
    if (Number.isFinite(statusMinimum)) {
      expect(statusMinimum, `${label} status text`).toBeGreaterThanOrEqual(10)
    }
  }

  if (viewport.width === 390) {
    expect(minimum('label'), `${label} mobile label text`).toBeGreaterThanOrEqual(9)
    expect(minimum('unit'), `${label} mobile unit text`).toBeGreaterThanOrEqual(9)
  }
}

async function inspectSchematic(page: Page): Promise<Inspection> {
  return page.evaluate((selector) => {
    type Box = { bottom: number; left: number; right: number; top: number }
    type Obstacle = Box & { label: string }
    type Point = { x: number; y: number }
    type Role = 'label' | 'status' | 'unit' | 'value'

    const svg = document.querySelector(selector)
    if (!(svg instanceof SVGSVGElement)) {
      return { failures: ['schematic SVG not found'], fonts: [], textCount: 0 }
    }

    const labelOf = (el: Element) => (el.textContent ?? el.getAttribute('aria-label') ?? el.tagName).replace(/\s+/g, ' ').trim()
    const matrixScale = (matrix: DOMMatrix): number =>
      (Math.hypot(matrix.a, matrix.b) + Math.hypot(matrix.c, matrix.d)) / 2
    const screenPoint = (el: SVGGraphicsElement, x: number, y: number): Point => {
      const matrix = el.getScreenCTM()
      if (matrix === null) return { x, y }
      const point = new DOMPoint(x, y).matrixTransform(matrix)
      return { x: point.x, y: point.y }
    }
    const boxOf = (el: SVGGraphicsElement): Box => {
      const bbox = el.getBBox()
      const points = [
        screenPoint(el, bbox.x, bbox.y),
        screenPoint(el, bbox.x + bbox.width, bbox.y),
        screenPoint(el, bbox.x + bbox.width, bbox.y + bbox.height),
        screenPoint(el, bbox.x, bbox.y + bbox.height),
      ]
      return {
        bottom: Math.max(...points.map((point) => point.y)),
        left: Math.min(...points.map((point) => point.x)),
        right: Math.max(...points.map((point) => point.x)),
        top: Math.min(...points.map((point) => point.y)),
      }
    }
    const intersects = (a: Box, b: Box) =>
      a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top
    const strokeWidth = (el: SVGGraphicsElement): number => {
      const width = Number.parseFloat(getComputedStyle(el).strokeWidth)
      return Number.isFinite(width) ? width : 1
    }
    const hasVisibleStroke = (el: SVGGraphicsElement): boolean => {
      const stroke = getComputedStyle(el).stroke
      return stroke !== '' && stroke !== 'none' && stroke !== 'transparent' && !stroke.endsWith(', 0)')
    }

    const obstacles: Obstacle[] = []
    const addObstacle = (el: SVGGraphicsElement, label: string, x: number, y: number) => {
      const matrix = el.getScreenCTM()
      const scale = matrix === null ? 1 : matrixScale(matrix)
      const radius = (strokeWidth(el) * scale) / 2 + 0.35
      const point = screenPoint(el, x, y)
      obstacles.push({
        bottom: point.y + radius,
        label,
        left: point.x - radius,
        right: point.x + radius,
        top: point.y - radius,
      })
    }
    const sampleLine = (el: SVGGraphicsElement, label: string, x1: number, y1: number, x2: number, y2: number) => {
      const length = Math.hypot(x2 - x1, y2 - y1)
      const count = Math.max(1, Math.ceil(length / 1.5))
      for (let i = 0; i <= count; i += 1) {
        const t = i / count
        addObstacle(el, label, x1 + (x2 - x1) * t, y1 + (y2 - y1) * t)
      }
    }

    for (const path of Array.from(svg.querySelectorAll('path'))) {
      if (!hasVisibleStroke(path)) continue
      const length = path.getTotalLength()
      const count = Math.max(1, Math.ceil(length / 1.5))
      const label = `path ${path.getAttribute('d') ?? ''}`
      for (let i = 0; i <= count; i += 1) {
        const point = path.getPointAtLength((length * i) / count)
        addObstacle(path, label, point.x, point.y)
      }
    }

    for (const rect of Array.from(svg.querySelectorAll('rect'))) {
      if (!hasVisibleStroke(rect)) continue
      const x = Number.parseFloat(rect.getAttribute('x') ?? '0')
      const y = Number.parseFloat(rect.getAttribute('y') ?? '0')
      const width = Number.parseFloat(rect.getAttribute('width') ?? '0')
      const height = Number.parseFloat(rect.getAttribute('height') ?? '0')
      const label = `rect(${x},${y},${width},${height})`
      sampleLine(rect, label, x, y, x + width, y)
      sampleLine(rect, label, x + width, y, x + width, y + height)
      sampleLine(rect, label, x + width, y + height, x, y + height)
      sampleLine(rect, label, x, y + height, x, y)
    }

    for (const line of Array.from(svg.querySelectorAll('line'))) {
      if (!hasVisibleStroke(line)) continue
      sampleLine(
        line,
        'line',
        Number.parseFloat(line.getAttribute('x1') ?? '0'),
        Number.parseFloat(line.getAttribute('y1') ?? '0'),
        Number.parseFloat(line.getAttribute('x2') ?? '0'),
        Number.parseFloat(line.getAttribute('y2') ?? '0'),
      )
    }

    for (const circle of Array.from(svg.querySelectorAll('circle'))) {
      if (!hasVisibleStroke(circle)) continue
      const cx = Number.parseFloat(circle.getAttribute('cx') ?? '0')
      const cy = Number.parseFloat(circle.getAttribute('cy') ?? '0')
      const r = Number.parseFloat(circle.getAttribute('r') ?? '0')
      const count = Math.max(24, Math.ceil((2 * Math.PI * r) / 1.5))
      for (let i = 0; i < count; i += 1) {
        const angle = (i / count) * Math.PI * 2
        addObstacle(circle, `circle(${cx},${cy},${r})`, cx + Math.cos(angle) * r, cy + Math.sin(angle) * r)
      }
    }

    const texts = Array.from(svg.querySelectorAll('text')).map((text, index) => ({
      box: boxOf(text),
      index,
      label: labelOf(text),
    }))
    const failures: string[] = []
    const seen = new Set<string>()

    for (let i = 0; i < texts.length; i += 1) {
      for (let j = i + 1; j < texts.length; j += 1) {
        if (intersects(texts[i].box, texts[j].box)) {
          failures.push(`text/text overlap: "${texts[i].label}" vs "${texts[j].label}"`)
        }
      }
    }

    for (const text of texts) {
      for (const obstacle of obstacles) {
        if (!intersects(text.box, obstacle)) continue
        const key = `${text.index}:${obstacle.label}`
        if (seen.has(key)) continue
        seen.add(key)
        failures.push(`text/stroke overlap: "${text.label}" vs ${obstacle.label}`)
      }
    }

    const fonts = Array.from(svg.querySelectorAll('[data-font-role]')).flatMap((node): FontMeasurement[] => {
      if (!(node instanceof SVGGraphicsElement)) return []
      const role = node.getAttribute('data-font-role') as Role | null
      if (role !== 'label' && role !== 'status' && role !== 'unit' && role !== 'value') return []
      const matrix = node.getScreenCTM()
      const size = Number.parseFloat(getComputedStyle(node).fontSize)
      if (matrix === null || !Number.isFinite(size)) return []
      return [{ label: labelOf(node), px: size * matrixScale(matrix), role }]
    })

    return { failures, fonts, textCount: texts.length }
  }, SCHEMATIC_SELECTOR)
}

const scenarios: Scenario[] = [
  { name: 'steady', setup: setSteady },
  { name: 'turbine-trip-dump', setup: setTurbineTripWithDump },
  { name: 'scram', setup: setScram },
  { name: 'feedwater-manual', setup: setFeedwaterManual },
  { name: 'trip-pending', setup: setTripPending },
  { name: 'trip-reset-pending', setup: setTripResetPending },
  { name: 'scram-reset-shutdown-inserted', setup: setScramResetShutdownInserted },
  { name: 'pressurizer-high-level', setup: setPressurizerHighLevel },
]

const viewports: ViewportCase[] = [
  { width: 1440, height: 900 },
  { width: 1024, height: 900 },
  { width: 390, height: 844, isMobile: true },
]

const screenshotNames = new Map<string, string>([
  ['1440:steady', 'd6-v5-steady-1440.png'],
  ['1440:turbine-trip-dump', 'd6-v5-turbine-trip-dump-1440.png'],
  ['1440:scram', 'd6-v5-scram-1440.png'],
  ['1440:feedwater-manual', 'd6-v5-feedwater-manual-1440.png'],
  ['1440:trip-pending', 'd6-v5-trip-pending-1440.png'],
  ['1440:trip-reset-pending', 'd6-v5-trip-reset-pending-1440.png'],
  ['1440:scram-reset-shutdown-inserted', 'd12d-fix-scram-reset-shutdown-inserted-1440.png'],
  ['1440:pressurizer-high-level', 'd12d-fix-pressurizer-high-level-1440.png'],
  ['1024:steady', 'd6-v5-steady-1024.png'],
  ['390:steady', 'd6-v5-steady-390.png'],
])

test('plant schematic text clears strokes and keeps legible font sizes', async ({ browser }: { browser: Browser }) => {
  const measured: string[] = []
  const screenshotPaths: string[] = []

  for (const viewport of viewports) {
    for (const scenario of scenarios) {
      const page = await browser.newPage({
        isMobile: viewport.isMobile ?? false,
        viewport: { width: viewport.width, height: viewport.height },
      })
      const label = `${viewport.width}x${viewport.height} ${scenario.name}`
      try {
        await waitForConsole(page)
        await scenario.setup(page)
        const inspection = await inspectSchematic(page)
        expect(inspection.textCount, `${label} should inspect the schematic SVG, not the heading icon`).toBeGreaterThan(10)
        expect(inspection.failures, label).toEqual([])
        assertFontThresholds(inspection, viewport, label)
        measured.push(`${label}: ${inspectionSummary(inspection.fonts)}`)

        const screenshotName = screenshotNames.get(`${viewport.width}:${scenario.name}`)
        if (SCREENSHOT_DIR && screenshotName) {
          const path = `${SCREENSHOT_DIR.replace(/\/$/, '')}/${screenshotName}`
          await page.screenshot({ fullPage: true, path })
          screenshotPaths.push(path)
        }
      } finally {
        await page.close()
      }
    }
  }

  console.log(`Measured schematic font minima:\n${measured.join('\n')}`)
  if (screenshotPaths.length > 0) console.log(`Schematic screenshots:\n${screenshotPaths.join('\n')}`)
})
