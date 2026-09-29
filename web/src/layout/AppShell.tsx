/**
 * AppShell — the page layout.
 *
 *   - Toolbar (sticky): wordmark, clock, connection and plant state.
 *   - Notices: a model-limit halt and the dismissible backend/connection
 *     message, when present.
 *   - Main, three columns on wide screens, each scrolling on its own: the
 *     loop schematic with the event log beneath it; the six trend charts;
 *     the operator controls above the readouts. On narrow screens the
 *     columns stack (schematic, controls, charts, readouts, events) and the
 *     page scrolls.
 *   - Footer: the learning-use disclaimer.
 */

import type { FC } from 'react'
import ChartGrid from '../charts/ChartGrid'
import ControlPanel from '../controls/ControlPanel'
import SecondaryControls from '../controls/SecondaryControls'
import ErrorNotice, { ModelLimitNotice } from '../widgets/ErrorNotice'
import EventLog from '../widgets/EventLog'
import PlantMimic from '../widgets/PlantMimic'
import StatusPanel from '../widgets/StatusPanel'
import Toolbar from './Toolbar'

const Footer: FC = () => (
  <footer className="border-t border-line-strong">
    <p className="px-4 py-2 text-[11px] leading-relaxed text-ink-3 sm:px-6">
      fission-sim is a personal learning project, not for real-world use. Model behavior, values,
      and explanations may be incorrect, incomplete, and oversimplified.
    </p>
  </footer>
)

const AppShell: FC = () => (
  <div className="flex min-h-dvh flex-col bg-canvas lg:h-dvh">
    <Toolbar />

    <main className="flex flex-1 flex-col lg:min-h-0">
      <div className="flex flex-col gap-2 px-4 pt-3 empty:hidden sm:px-6 lg:px-5">
        <ModelLimitNotice />
        <ErrorNotice />
      </div>

      <div className="flex flex-1 flex-col gap-4 px-4 py-4 sm:px-6 lg:grid lg:min-h-0 lg:grid-cols-[318px_minmax(0,1fr)_312px] lg:gap-0 lg:p-0 xl:grid-cols-[340px_minmax(0,1fr)_340px]">
        {/* Left column: the schematic, with the event log beneath it on wide screens. */}
        <div className="panel order-1 flex flex-col lg:order-none lg:min-h-0 lg:border-0 lg:border-r lg:border-line-strong">
          <div className="lg:flex lg:min-h-0 lg:flex-1 lg:flex-col lg:overflow-hidden">
            <PlantMimic />
          </div>
          <div className="hidden border-t border-line-strong lg:block">
            <EventLog />
          </div>
        </div>

        <section
          id="charts"
          aria-label="Trends"
          className="order-3 lg:scroll-column lg:order-none lg:min-h-0 lg:overflow-y-auto"
        >
          <ChartGrid />
        </section>

        {/*
          On narrow screens `contents` lets the controls and readouts take
          their own place in the single column (controls before the charts,
          readouts after); on wide screens the aside is the right column.
        */}
        <aside
          aria-label="Controls and plant status"
          className="contents lg:scroll-column lg:flex lg:min-h-0 lg:flex-col lg:gap-4 lg:overflow-y-auto lg:border-l lg:border-line-strong lg:p-4"
        >
          <div className="order-2 lg:order-none">
            <ControlPanel />
          </div>
          <div className="order-2 lg:order-none">
            <SecondaryControls />
          </div>
          <div className="order-4 lg:order-none">
            <StatusPanel />
          </div>
        </aside>

        <div className="panel order-5 lg:hidden">
          <EventLog />
        </div>
      </div>
    </main>

    <Footer />
  </div>
)

export default AppShell
