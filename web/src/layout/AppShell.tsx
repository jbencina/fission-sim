/**
 * AppShell — the page layout.
 *
 *   - Toolbar (sticky): wordmark, connection and simulation state, tools.
 *   - Notices: a model-limit halt and the dismissible backend/connection
 *     message, when present.
 *   - Main: the six trend charts, and a sidebar with the operator controls
 *     above the plant-status readouts. On wide screens the page fits the
 *     window and each column scrolls on its own if needed; on narrow screens
 *     everything stacks and the page scrolls.
 *   - Footer: the learning-use disclaimer.
 */

import type { FC } from 'react'
import ChartGrid from '../charts/ChartGrid'
import ControlPanel from '../controls/ControlPanel'
import ErrorNotice, { ModelLimitNotice } from '../widgets/ErrorNotice'
import StatusPanel from '../widgets/StatusPanel'
import Toolbar from './Toolbar'

const Footer: FC = () => (
  <footer className="border-t border-line">
    <p className="mx-auto max-w-[1720px] px-4 py-2.5 text-[12px] leading-relaxed text-ink-3 sm:px-6">
      fission-sim is a personal learning project, not for real-world use. Model behavior, values,
      and explanations may be incorrect, incomplete, and oversimplified.
    </p>
  </footer>
)

const AppShell: FC = () => (
  <div className="flex min-h-dvh flex-col lg:h-dvh">
    <Toolbar />

    <main className="mx-auto flex w-full max-w-[1720px] flex-1 flex-col gap-4 px-4 py-4 sm:px-6 lg:min-h-0">
      <div className="flex flex-col gap-2 empty:hidden">
        <ModelLimitNotice />
        <ErrorNotice />
      </div>

      <div className="grid flex-1 gap-4 lg:min-h-0 lg:grid-cols-[minmax(0,1fr)_340px] xl:grid-cols-[minmax(0,1fr)_360px]">
        <section id="charts" aria-label="Trends" className="lg:scroll-column lg:min-h-0 lg:overflow-y-auto">
          <ChartGrid />
        </section>
        <aside
          aria-label="Controls and plant status"
          className="lg:scroll-column grid items-start gap-4 md:grid-cols-2 lg:flex lg:min-h-0 lg:flex-col lg:overflow-y-auto"
        >
          <ControlPanel />
          <StatusPanel />
        </aside>
      </div>
    </main>

    <Footer />
  </div>
)

export default AppShell
