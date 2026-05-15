"""Entry point: ``python -m fission_sim.api``.

Starts the uvicorn ASGI server bound to ``127.0.0.1:8000``.

Usage
-----
::

    uv run python -m fission_sim.api

Notes
-----
The host is intentionally set to loopback (127.0.0.1) — the API is not
intended to be exposed on a network interface during development.  ``reload``
is disabled; the process must be restarted to pick up code changes.
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "fission_sim.api.app:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
