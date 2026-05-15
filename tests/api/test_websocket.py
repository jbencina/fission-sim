"""Tests for the /ws/telemetry WebSocket endpoint.

Verifies A-03: clients receive telemetry frames at the configured cadence,
frames contain the required keys, multiple simultaneous subscribers work,
and unknown commands do not disconnect the client.

Uses FastAPI's synchronous ``TestClient.websocket_connect()`` — no
pytest-asyncio needed for these tests.

Note on TestClient usage
------------------------
``TestClient(app)`` must be used as a context manager (``with TestClient(app) as client:``)
to trigger the FastAPI ``lifespan`` handler which starts the ``SimRuntime``.
Using the client outside a ``with`` block means the lifespan never fires and
``app.state.runtime`` is not set.
"""

from __future__ import annotations

import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from fission_sim.api.app import app

# Required keys in every telemetry frame per A-03.
# Either P_primary_Pa or P_primary_MPa is acceptable.
_REQUIRED_KEYS = {
    "t",
    "power_thermal",
    "T_hot",
    "T_cold",
    "T_fuel",
    "rod_position",
    "Q_sg",
    "running",
    "speed",
}

# One of these pressure keys must appear.
_PRESSURE_KEYS = {"P_primary_Pa", "P_primary_MPa"}


def _has_required_keys(frame: dict) -> bool:
    """Return True if *frame* contains all A-03 required keys."""
    if not _REQUIRED_KEYS.issubset(frame.keys()):
        return False
    # At least one pressure key must be present.
    if not _PRESSURE_KEYS.intersection(frame.keys()):
        return False
    return True


def test_websocket_receives_at_least_5_frames():
    """A-03: at least 5 telemetry frames must arrive within 1.5 s wall clock.

    Each frame must be a JSON object containing the A-03 required keys.
    """
    with TestClient(app) as client:
        frames: list[dict] = []
        deadline = time.monotonic() + 1.5

        with client.websocket_connect("/ws/telemetry") as ws:
            while time.monotonic() < deadline and len(frames) < 5:
                try:
                    # receive_text blocks until data arrives or the socket closes.
                    raw = ws.receive_text()
                    frame = json.loads(raw)
                    frames.append(frame)
                except Exception:
                    # Socket closed unexpectedly — stop collecting.
                    break

    assert len(frames) >= 5, (
        f"Expected at least 5 frames within 1.5 s, got {len(frames)}"
    )
    for i, frame in enumerate(frames[:5]):
        assert isinstance(frame, dict), f"Frame {i} is not a dict: {frame!r}"
        missing = _REQUIRED_KEYS - frame.keys()
        assert not missing, f"Frame {i} missing required keys: {sorted(missing)}"
        assert _PRESSURE_KEYS.intersection(frame.keys()), (
            f"Frame {i} contains neither P_primary_Pa nor P_primary_MPa"
        )


def test_unknown_command_does_not_disconnect():
    """Sending an unknown command must not cause a disconnect or exception.

    In feat-003 the server may reply with an error frame or silently accept
    the message — both are acceptable. We only assert the connection stays open.
    """
    with TestClient(app) as client:
        with client.websocket_connect("/ws/telemetry") as ws:
            # Receive one frame so we know the connection is live.
            ws.receive_text()

            # Send an unknown command.
            ws.send_json({"type": "set_rod_command", "value": 0.6})

            # Receive another frame — if the server disconnected, this would raise.
            try:
                ws.receive_text()
            except Exception as exc:
                pytest.fail(f"Connection broke after unknown command: {exc}")


def test_two_simultaneous_websockets_both_receive_frames():
    """Multiple simultaneous WebSocket clients must each receive frames.

    Opens two connections in parallel threads and asserts both collect at
    least 3 frames each.
    """
    results: dict[str, list] = {"a": [], "b": []}
    errors: list[str] = []

    # Share a single TestClient (and thus a single lifespan/runtime) across
    # both threads. TestClient's WebSocket sessions are thread-safe to open
    # concurrently as long as they share the same portal/loop.
    with TestClient(app) as client:

        def collect(key: str) -> None:
            try:
                deadline = time.monotonic() + 1.5
                with client.websocket_connect("/ws/telemetry") as ws:
                    while time.monotonic() < deadline and len(results[key]) < 3:
                        try:
                            raw = ws.receive_text()
                            results[key].append(json.loads(raw))
                        except Exception:
                            break
            except Exception as exc:
                errors.append(f"{key}: {exc}")

        t1 = threading.Thread(target=collect, args=("a",))
        t2 = threading.Thread(target=collect, args=("b",))
        t1.start()
        t2.start()
        t1.join(timeout=3.0)
        t2.join(timeout=3.0)

    assert not errors, f"Thread errors: {errors}"
    assert len(results["a"]) >= 3, f"Client A got only {len(results['a'])} frames"
    assert len(results["b"]) >= 3, f"Client B got only {len(results['b'])} frames"
