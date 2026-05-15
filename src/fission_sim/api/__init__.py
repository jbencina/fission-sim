"""fission_sim.api — HTTP/WebSocket interface layer for the PWR simulator.

This package sits at the top of the four-layer stack defined in CLAUDE.md:

    Visualization  ←  (browser / React UI)
         │
    fission_sim.api   ← YOU ARE HERE (HTTP + WebSocket gateway)
         │
    fission_sim.control
         │
    fission_sim.physics
         │
    fission_sim.engine

Architectural constraints
-------------------------
- This package may import from ``fission_sim.engine``, ``fission_sim.physics``,
  and ``fission_sim.control``, but NEVER the reverse.
- No physics logic lives here.  Domain objects (temperatures, pressures, power)
  are passed through as plain data; their meaning is computed by the layers below.
- All HTTP routes are defined in ``app.py`` and exported via the ``app`` object.

Notes
-----
Run the server with::

    uv run python -m fission_sim.api

which starts uvicorn on ``127.0.0.1:8000``.
"""
