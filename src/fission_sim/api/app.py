"""FastAPI application for the fission-sim backend.

This module defines the ASGI ``app`` object used by uvicorn.  It is the single
entry-point for all HTTP and WebSocket traffic.

Layer position
--------------
``fission_sim.api`` sits at the **Visualization** tier of the four-layer stack.
It wires the browser to the simulation engine; it contains no physics logic.

CORS policy
-----------
Permissive CORS is enabled only for the Vite dev server origins
(``http://127.0.0.1:5173`` and ``http://localhost:5173``).  Production builds
will serve the bundled React app from the same origin and need no CORS at all.

Routes
------
GET /api/health
    Liveness probe.  Returns ``{"status": "ok"}`` with HTTP 200.

WebSocket /ws/telemetry
    Telemetry stream.  On connect the client is subscribed to the shared
    ``SimRuntime`` and receives telemetry frames as JSON at the runtime's
    configured cadence (default 10 Hz).  The client may also send JSON
    command messages; successful commands are answered with an ack frame and
    invalid command messages are answered with an error frame.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from fission_sim.api.runtime import SimRuntime
from fission_sim.disclaimer import print_disclaimer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifespan — owns the single shared SimRuntime for the process lifetime.
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Construct, start, and stop the shared SimRuntime.

    FastAPI calls this async context manager once at startup and once at
    shutdown.  The runtime is stored on ``app.state.runtime`` so that routes
    can retrieve it via ``websocket.app.state.runtime``.

    Parameters
    ----------
    app : FastAPI
        The application instance (injected by FastAPI).

    Yields
    ------
    None
        Yields control to FastAPI while the server is running.
    """
    print_disclaimer()
    runtime = SimRuntime()
    app.state.runtime = runtime
    await runtime.start()
    logger.info("SimRuntime started (cadence 10 Hz)")
    try:
        yield
    finally:
        await runtime.stop()
        logger.info("SimRuntime stopped")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="fission-sim API",
    description="HTTP gateway for the PWR simulator learning project.",
    version="0.1.0",
    lifespan=_lifespan,
)

# Allow the Vite dev server to reach the backend during local development.
# Only the two localhost origins are whitelisted; this is intentionally
# restrictive — the UI is the only expected caller.
_DEV_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_DEV_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# HTTP Routes
# ---------------------------------------------------------------------------


@app.get("/api/health", summary="Liveness probe")
def health() -> dict[str, str]:
    """Return a simple liveness response.

    Returns
    -------
    dict
        ``{"status": "ok"}`` when the server is running and the Python
        interpreter is healthy.  No simulation state is checked here — this
        endpoint is intentionally a shallow ping.

    Examples
    --------
    >>> from fastapi.testclient import TestClient
    >>> client = TestClient(app)
    >>> client.get("/api/health").json()
    {'status': 'ok'}
    """
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# WebSocket Routes
# ---------------------------------------------------------------------------


@app.websocket("/ws/telemetry")
async def ws_telemetry(websocket: WebSocket) -> None:
    """WebSocket endpoint that streams telemetry frames at the runtime cadence.

    On connect, the client is subscribed to the shared ``SimRuntime``'s
    pub/sub queue.  Two concurrent tasks are launched:

    - **send task**: waits for frames from the queue and forwards them to the
      client as JSON.
    - **recv task**: reads JSON messages from the client and routes them to
      ``runtime.handle_command(msg)``.  If that method does not exist yet
      (it is added in feat-004), an error frame is sent back instead.

    On disconnect (clean or abrupt), the subscription is removed from the
    runtime so no frames accumulate in the abandoned queue.

    Parameters
    ----------
    websocket : WebSocket
        The FastAPI/Starlette WebSocket connection object.
    """
    # Retrieve the shared runtime wired up in the lifespan.
    runtime: SimRuntime = websocket.app.state.runtime

    await websocket.accept()
    # Register this connection as a subscriber — the runtime will push frames
    # into this queue from its background step loop.
    queue: asyncio.Queue[dict[str, Any]] = runtime.subscribe()

    async def _send_task() -> None:
        """Forward telemetry frames from the queue to the WebSocket client.

        Loops forever — cancellation is expected and handled by the caller.
        """
        while True:
            frame = await queue.get()
            await websocket.send_json(frame)

    async def _recv_task() -> None:
        """Read JSON commands from the client and dispatch them to the runtime.

        Calls ``runtime.handle_command(msg)`` for every received message.
        The response dict is forwarded to the client as a JSON frame.  If
        ``handle_command`` raises unexpectedly, a generic error frame is sent
        and the exception is logged.

        Loops until the client disconnects, at which point
        ``WebSocketDisconnect`` propagates up to the parent scope.
        """
        while True:
            msg: Any = await websocket.receive_json()

            try:
                result = await runtime.handle_command(msg)
            except Exception:
                logger.exception("handle_command raised unexpectedly for msg=%r", msg)
                await websocket.send_json(
                    {"type": "error", "detail": "internal server error processing command"}
                )
                continue

            # Forward command acknowledgements and validation errors to the
            # client. Telemetry frames continue to flow through _send_task.
            if isinstance(result, dict):
                await websocket.send_json(result)

    try:
        # Run send and recv concurrently. Either task completing (or raising)
        # cancels the other and causes the with-block to exit.
        async with asyncio.TaskGroup() as tg:
            tg.create_task(_send_task())
            tg.create_task(_recv_task())
    except* WebSocketDisconnect:
        # Client disconnected cleanly — normal end of session.
        logger.debug("WebSocket client disconnected cleanly")
    except* Exception as eg:
        # Unexpected error in one of the tasks — log and close.
        logger.warning("WebSocket session ended with error: %s", eg.exceptions)
    finally:
        # Always clean up the subscriber queue so the runtime does not
        # accumulate dead queues over time.
        runtime.unsubscribe(queue)
