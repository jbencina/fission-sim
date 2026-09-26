"""Tests for the /ws/telemetry WebSocket endpoint.

Clients receive telemetry frames at the configured cadence, frames contain
the required keys, multiple simultaneous subscribers work, and a command
does not disconnect the client.

Uses FastAPI's synchronous ``TestClient.websocket_connect()`` with the
bounded receive helpers in ``ws_helpers.py``.

Note on TestClient usage
------------------------
``TestClient(app)`` must be used as a context manager (``with TestClient(app) as client:``)
to trigger the FastAPI ``lifespan`` handler which starts the ``SimRuntime``.
Using the client outside a ``with`` block means the lifespan never fires and
``app.state.runtime`` is not set.
"""

from __future__ import annotations

import logging
import threading
import time

from fastapi.testclient import TestClient

from fission_sim.api.app import app

from .ws_helpers import receive_telemetry, send_command

# Keys every telemetry frame must carry for the dashboard.
_REQUIRED_KEYS = {
    "t",
    "power_thermal",
    "T_hot",
    "T_cold",
    "T_fuel",
    "rod_position",
    "Q_sg",
    "P_primary_Pa",
    "P_primary_MPa",
    "running",
    "speed",
}


def test_websocket_receives_at_least_5_frames():
    """At least 5 telemetry frames arrive within 1.5 s wall clock, each a
    JSON object with the required keys."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws/telemetry") as ws:
            deadline = time.monotonic() + 1.5
            frames = [receive_telemetry(ws, timeout=deadline - time.monotonic()) for _ in range(5)]

    for i, frame in enumerate(frames):
        missing = _REQUIRED_KEYS - frame.keys()
        assert not missing, f"Frame {i} missing required keys: {sorted(missing)}"


def test_command_does_not_disconnect():
    """Sending a command must not disconnect the client or stop telemetry.

    Command-specific acknowledgement/error behavior is covered in
    test_commands.py. Here the acknowledgement is consumed first, so the
    frame that follows is proof that telemetry continues.
    """
    with TestClient(app) as client:
        with client.websocket_connect("/ws/telemetry") as ws:
            t_before = receive_telemetry(ws)["t"]

            # A valid command; its reply is an ack, not telemetry.
            assert send_command(ws, {"type": "set_rod_command", "value": 0.6})["type"] == "ack"

            assert receive_telemetry(ws, lambda f: f["t"] > t_before)


def test_two_simultaneous_websockets_both_receive_frames():
    """Multiple simultaneous WebSocket clients must each receive frames.

    Opens two connections in parallel threads and asserts both collect at
    least 3 frames each. Every receive is bounded, so a thread that gets no
    frames records why instead of blocking forever.
    """
    results: dict[str, list] = {"a": [], "b": []}
    errors: list[str] = []

    # Share a single TestClient (and thus a single lifespan/runtime) across
    # both threads. TestClient's WebSocket sessions are thread-safe to open
    # concurrently as long as they share the same portal/loop.
    with TestClient(app) as client:

        def collect(key: str) -> None:
            try:
                with client.websocket_connect("/ws/telemetry") as ws:
                    for _ in range(3):
                        results[key].append(receive_telemetry(ws, timeout=2.0))
            except BaseException as exc:  # includes pytest.fail's Failed
                errors.append(f"{key}: {type(exc).__name__}: {exc}")

        threads = [threading.Thread(target=collect, args=(key,)) for key in results]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10.0)
        assert not any(thread.is_alive() for thread in threads), "a client thread did not finish"

    assert not errors, f"Thread errors: {errors}"
    assert len(results["a"]) >= 3, f"Client A got only {len(results['a'])} frames"
    assert len(results["b"]) >= 3, f"Client B got only {len(results['b'])} frames"


def test_disconnect_removes_the_subscription(caplog):
    """Closing a session unsubscribes its queue, so the runtime does not keep
    publishing into queues nobody reads, and a clean close is not logged as
    an error."""
    caplog.set_level(logging.DEBUG, logger="fission_sim.api.app")
    with TestClient(app) as client:
        subscribers = client.app.state.runtime._subscribers
        with client.websocket_connect("/ws/telemetry") as ws:
            receive_telemetry(ws)
            assert len(subscribers) == 1
        # Leaving the block closes the socket and waits for the endpoint to end.
        assert len(subscribers) == 0

    warnings = [
        r.getMessage() for r in caplog.records if r.name == "fission_sim.api.app" and r.levelno >= logging.WARNING
    ]
    assert warnings == [], f"clean close was logged as a failure: {warnings}"
