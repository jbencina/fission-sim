"""Tests for feat-004: handle_command dispatch on SimRuntime.

Covers assertions A-04, A-05, and A-06 (lint + full suite).

A-04 — Rod command from a client is reflected in subsequent telemetry.
A-05 — Scram command drives power down sharply; reset_scram clears the latch.

These tests use the FastAPI TestClient's synchronous WebSocket helper so that
no pytest-asyncio configuration is needed.  The simulation is run at a high
speed multiplier (10×) to compress sim time into acceptable wall-clock budgets.

Design notes
------------
- All tests run the sim at 10× speed so that 10 s of sim time takes ~1 s wall.
- The test helper ``_collect_until`` reads frames from a connected WebSocket
  until either a sim-time budget is consumed or a user-supplied predicate is met.
- Wall-clock budget for the full module: well under 30 s total.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from fission_sim.api.app import app

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SPEED = 10  # speed multiplier applied at the start of each test


def _set_speed(ws: WebSocketTestSession, speed: int) -> None:
    """Send a set_speed command; consume and discard any immediate response."""
    ws.send_json({"type": "set_speed", "value": speed})
    # Give the server a moment; TestClient is synchronous so we just continue.


def _recv_frame(ws: WebSocketTestSession) -> dict[str, Any]:
    """Receive one JSON frame from the WebSocket."""
    return json.loads(ws.receive_text())


def _recv_until(
    ws: WebSocketTestSession,
    predicate: Callable[[dict[str, Any]], bool],
    *,
    max_frames: int = 10,
) -> dict[str, Any]:
    """Receive frames until *predicate* matches, or fail after max_frames."""
    for _ in range(max_frames):
        frame = _recv_frame(ws)
        if predicate(frame):
            return frame
    pytest.fail(f"No matching frame received within {max_frames} frames")


def _collect_until(
    ws: WebSocketTestSession,
    *,
    sim_seconds: float,
    predicate: Callable[[dict], bool] | None = None,
) -> list[dict[str, Any]]:
    """Collect telemetry frames until sim_seconds of sim time have elapsed.

    Starts the clock on the first received frame's ``t`` value.

    Parameters
    ----------
    ws : WebSocketTestSession
        Active WebSocket session.
    sim_seconds : float
        Stop after this many seconds of simulation time have elapsed since
        the first frame.
    predicate : callable, optional
        If supplied, also stop early when ``predicate(frame)`` is True for
        a received frame.

    Returns
    -------
    list of dict
        All frames received during the collection window.
    """
    frames: list[dict[str, Any]] = []
    t_start: float | None = None
    # Wall-clock guard: each sim second at 10× speed = 0.1 s wall, so
    # 60 s sim = 6 s wall. Add generous headroom.
    wall_deadline = time.monotonic() + sim_seconds / _SPEED * 4 + 5.0

    while time.monotonic() < wall_deadline:
        try:
            frame = _recv_frame(ws)
        except Exception:
            break

        frames.append(frame)

        t_sim = frame.get("t", 0.0)
        if t_start is None:
            t_start = t_sim

        if t_sim - t_start >= sim_seconds:
            break

        if predicate is not None and predicate(frame):
            break

    return frames


# ---------------------------------------------------------------------------
# A-04: Rod command is reflected in subsequent telemetry
# ---------------------------------------------------------------------------


def test_rod_command_reflected_in_telemetry():
    """A-04 — set_rod_command 0.6 causes rod_position to trend toward 0.6.

    Starting from the default rod_command of 0.5, after commanding 0.6 the
    rod controller will drive the physical rod upward.  We verify that after
    ~2 s of sim time the rod_position has moved above 0.5 (i.e., is trending
    toward 0.6).
    """
    with TestClient(app) as client:
        with client.websocket_connect("/ws/telemetry") as ws:
            # Speed up sim time.
            _set_speed(ws, _SPEED)

            # Consume frames until speed change takes effect (first few frames).
            first = _recv_frame(ws)
            # Ensure rod starts near 0.5 (default) — it may not have moved yet.
            rod_start = first.get("rod_position", 0.5)

            # Command rod to 0.6.
            ws.send_json({"type": "set_rod_command", "value": 0.6})

            # Collect frames for 2 s of sim time.
            frames = _collect_until(ws, sim_seconds=2.0)

    assert frames, "No frames received after rod command"
    last_rod = frames[-1]["rod_position"]
    # After 2 sim-seconds at finite rod speed, position should be heading toward 0.6.
    # The rod controller has a finite speed so we just assert direction of movement,
    # not that it has fully reached 0.6.
    assert last_rod > rod_start or last_rod > 0.5, (
        f"rod_position={last_rod:.4f} did not move toward 0.6 from start={rod_start:.4f}"
    )


# ---------------------------------------------------------------------------
# A-05: Scram drives power down; reset_scram clears the latch
# ---------------------------------------------------------------------------


def test_scram_drops_power_and_reset_scram_clears():
    """A-05 — scram drops power below 20% of pre-scram; reset_scram clears.

    Sequence:
    1. Run at 10× for 5 s sim to reach something close to steady state.
    2. Capture pre-scram power.
    3. Send scram.
    4. Run for 10 s sim and assert power < 20% of pre-scram.
    5. Assert rod_position == 0 and scrammed == True.
    6. Send reset_scram; assert scrammed == False in a subsequent frame.
    """
    with TestClient(app) as client:
        with client.websocket_connect("/ws/telemetry") as ws:
            # Ramp speed up.
            _set_speed(ws, _SPEED)

            # Warm up for ~5 s of sim time to approach steady state.
            warmup_frames = _collect_until(ws, sim_seconds=5.0)
            assert warmup_frames, "No frames during warm-up"

            # Capture pre-scram power from the last warm-up frame.
            pre_scram_frame = warmup_frames[-1]
            pre_scram_power = pre_scram_frame["power_thermal"]
            assert pre_scram_power > 0, "Pre-scram power must be > 0"

            # Issue scram.
            ws.send_json({"type": "scram"})

            # Collect frames for 10 s of sim time after scram.
            post_scram_frames = _collect_until(ws, sim_seconds=10.0)

    assert post_scram_frames, "No frames received after scram"
    last_frame = post_scram_frames[-1]

    # Power must be below 20% of pre-scram value.
    final_power = last_frame["power_thermal"]
    assert final_power < 0.20 * pre_scram_power, (
        f"Power after scram ({final_power:.1f} W) is not below 20% of "
        f"pre-scram power ({pre_scram_power:.1f} W)"
    )

    # Rod must be at zero (fully inserted).
    assert last_frame["rod_position"] == pytest.approx(0.0, abs=0.01), (
        f"rod_position after scram should be ~0, got {last_frame['rod_position']:.4f}"
    )

    # Scrammed flag must be True.
    assert last_frame["scrammed"] is True, "scrammed flag should be True after scram"

    # Now send reset_scram and assert scrammed clears.
    with TestClient(app) as client2:
        with client2.websocket_connect("/ws/telemetry") as ws2:
            _set_speed(ws2, _SPEED)

            # Scram first, then reset.
            ws2.send_json({"type": "scram"})
            # Wait a tick so scram is processed.
            _recv_frame(ws2)
            _recv_frame(ws2)

            # Reset scram.
            ws2.send_json({"type": "reset_scram"})

            # Check that scrammed eventually becomes False.
            reset_frames = _collect_until(ws2, sim_seconds=1.0)

    assert reset_frames, "No frames after reset_scram"
    # The last frame should have scrammed=False.
    assert reset_frames[-1]["scrammed"] is False, (
        "scrammed flag should be False after reset_scram"
    )


# ---------------------------------------------------------------------------
# Invalid command tests
# ---------------------------------------------------------------------------


def test_out_of_range_rod_command_returns_error():
    """set_rod_command with value outside [0,1] must return an error frame.

    The connection must remain open afterward.
    """
    with TestClient(app) as client:
        with client.websocket_connect("/ws/telemetry") as ws:
            # Consume at least one telemetry frame so we know the session is live.
            _recv_frame(ws)

            # Send an out-of-range value.
            ws.send_json({"type": "set_rod_command", "value": 2.0})

            # Expect an error frame next (the server should send it promptly).
            # We read up to 5 frames to avoid being fooled by queued telemetry
            # frames that were published before the command was processed.
            error_found = False
            for _ in range(5):
                frame = _recv_frame(ws)
                if frame.get("type") == "error":
                    error_found = True
                    assert "detail" in frame, "Error frame must have a 'detail' key"
                    break

            assert error_found, "Expected an error frame for out-of-range rod command, got none"

            # Connection must remain open — receive another frame.
            try:
                _recv_frame(ws)
            except Exception as exc:
                pytest.fail(f"Connection closed after error frame: {exc}")


def test_unknown_command_type_returns_error():
    """Unknown command type must return an error frame; connection stays open."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws/telemetry") as ws:
            _recv_frame(ws)

            ws.send_json({"type": "totally_unknown_command"})

            error_found = False
            for _ in range(5):
                frame = _recv_frame(ws)
                if frame.get("type") == "error":
                    error_found = True
                    assert "detail" in frame, "Error frame must have a 'detail' key"
                    break

            assert error_found, "Expected error frame for unknown command type, got none"

            # Connection must stay alive.
            try:
                _recv_frame(ws)
            except Exception as exc:
                pytest.fail(f"Connection closed after unknown command: {exc}")


def test_valid_command_returns_ack_frame():
    """Successful commands should return an acknowledgement frame."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws/telemetry") as ws:
            _recv_frame(ws)

            ws.send_json({"type": "set_speed", "value": 2})

            ack = _recv_until(
                ws,
                lambda frame: frame.get("type") == "ack",
                max_frames=10,
            )
            assert ack["command"] == "set_speed"


def test_non_object_command_returns_validation_error():
    """A JSON array/string command should be a client error, not an internal error."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws/telemetry") as ws:
            _recv_frame(ws)

            ws.send_text("[]")

            error = _recv_until(
                ws,
                lambda frame: frame.get("type") == "error",
                max_frames=10,
            )
            assert "JSON object" in error["detail"]
            assert "internal server error" not in error["detail"]
