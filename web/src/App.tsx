/**
 * App — root component for fission-sim web UI.
 *
 * Responsibilities:
 *   1. Open the WebSocket connection to the backend on mount.
 *   2. Wire the telemetry store callbacks to the WS client.
 *   3. Render AppShell (the full-page layout scaffold).
 *
 * Side effects (WebSocket lifecycle) live here at the root so they outlive
 * any individual layout or content component and are set up exactly once.
 */

import { useEffect } from 'react'
import { useTelemetryStore } from './state/telemetryStore'
import { connectTelemetry } from './state/wsClient'
import AppShell from './layout/AppShell'

function App() {
  const pushFrame = useTelemetryStore((s) => s.pushFrame)
  const setStatus = useTelemetryStore((s) => s.setStatus)
  const reportError = useTelemetryStore((s) => s.reportError)
  const setSend = useTelemetryStore((s) => s.setSend)

  useEffect(() => {
    // Open the WebSocket connection and wire callbacks to store actions.
    const client = connectTelemetry(pushFrame, setStatus, reportError)
    // Register the send function so sendCommand() can delegate to it.
    setSend(client.send)

    // Clean up when the component unmounts.
    return () => {
      client.close()
    }
  }, [pushFrame, setStatus, reportError, setSend])

  // Render the full-page layout shell. All visual chrome and layout regions
  // live inside AppShell; this component only owns the connection side effect.
  return <AppShell />
}

export default App
