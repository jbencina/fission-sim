import { useEffect } from 'react'
import { useTelemetryStore } from './state/telemetryStore'
import { connectTelemetry } from './state/wsClient'

// Tailwind colour classes for each connection status
const STATUS_DOT: Record<string, string> = {
  connecting: 'bg-amber-400',
  connected: 'bg-green-400',
  disconnected: 'bg-red-500',
}

const STATUS_LABEL: Record<string, string> = {
  connecting: 'Connecting…',
  connected: 'Connected',
  disconnected: 'Disconnected',
}

function App() {
  const pushFrame = useTelemetryStore((s) => s.pushFrame)
  const setStatus = useTelemetryStore((s) => s.setStatus)
  const setError = useTelemetryStore((s) => s.setError)
  const setSend = useTelemetryStore((s) => s.setSend)
  const status = useTelemetryStore((s) => s.status)
  const latest = useTelemetryStore((s) => s.latest)

  useEffect(() => {
    // Open the WebSocket connection and wire callbacks to store actions.
    const client = connectTelemetry(pushFrame, setStatus, setError)
    // Register the send function so sendCommand() can delegate to it.
    setSend(client.send)

    // Clean up when the component unmounts.
    return () => {
      client.close()
    }
  }, [pushFrame, setStatus, setError, setSend])

  const dotClass = STATUS_DOT[status] ?? 'bg-slate-400'
  const label = STATUS_LABEL[status] ?? status

  return (
    <div className="bg-slate-950 text-slate-100 min-h-screen flex items-center justify-center relative">

      {/* Connection status chip — top-right corner */}
      <div className="absolute top-4 right-4 flex items-center gap-2 rounded-full bg-slate-800 px-3 py-1.5 text-sm font-medium shadow-md">
        <span className={`inline-block h-2.5 w-2.5 rounded-full ${dotClass}`} />
        <span>{label}</span>
      </div>

      {/* Main heading */}
      <div className="flex flex-col items-center gap-4">
        <h1 className="text-4xl font-bold tracking-tight text-amber-400">
          fission-sim
        </h1>

        {/* Sim-time readout — stopgap verifier that telemetry is flowing;
            feat-008 will replace this section with a proper dashboard layout */}
        <p className="text-slate-400 text-sm">
          sim time:{' '}
          <span className="font-mono text-slate-200">
            {latest != null ? `${latest.t.toFixed(2)} s` : '—'}
          </span>
        </p>
      </div>
    </div>
  )
}

export default App
