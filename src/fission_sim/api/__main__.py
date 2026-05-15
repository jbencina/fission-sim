"""Entry point: ``python -m fission_sim.api``.

Starts the uvicorn ASGI server bound to ``0.0.0.0:8000`` — listens on
every network interface so a browser on another machine on the same LAN
can connect.  ``reload`` is disabled; the process must be restarted to
pick up code changes.

Usage
-----
::

    uv run python -m fission_sim.api

Notes
-----
There is no authentication. Binding to ``0.0.0.0`` makes the simulator
reachable to anything that can route to this machine — intended for a
trusted dev LAN, not a public network.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "fission_sim.api.app:app",
        host="0.0.0.0",  # noqa: S104 — intentional LAN exposure for dev
        port=8000,
        reload=False,
    )
