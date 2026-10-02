"""Entry point: ``python -m fission_sim.api``.

Starts the uvicorn ASGI server bound to ``0.0.0.0:8780`` (or the port in
``FISSION_SIM_API_PORT``) — listens on every network interface so a browser
on another machine on the same LAN can connect.  ``reload`` is disabled; the
process must be restarted to pick up code changes.

The default port is deliberately not 8000, which many other local services
use; it matches ``scripts/dev.py`` and the Vite proxy in ``web/vite.config.ts``.

Usage
-----
::

    uv run python -m fission_sim.api
    FISSION_SIM_API_PORT=8781 uv run python -m fission_sim.api

Notes
-----
There is no authentication. Binding to ``0.0.0.0`` makes the simulator
reachable to anything that can route to this machine — intended for a
trusted dev LAN, not a public network.
"""

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "fission_sim.api.app:app",
        host="0.0.0.0",  # noqa: S104 — intentional LAN exposure for dev
        port=int(os.environ.get("FISSION_SIM_API_PORT") or 8780),
        reload=False,
    )
