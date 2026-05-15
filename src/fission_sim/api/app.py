"""FastAPI application for the fission-sim backend.

This module defines the ASGI ``app`` object used by uvicorn.  It is the single
entry-point for all HTTP (and, in later milestones, WebSocket) traffic.

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
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="fission-sim API",
    description="HTTP gateway for the PWR simulator learning project.",
    version="0.1.0",
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
# Routes
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
