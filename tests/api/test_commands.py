"""WebSocket command tests: commands sent by a client reach the simulation.

Each test opens a real session through FastAPI's ``TestClient`` (which runs
the app's lifespan, so every ``with TestClient(app)`` block gets a fresh
``SimRuntime``) and runs the simulation at 10x speed to compress simulated
time into a short wall-clock budget.

Validation of each command's fields is unit-tested directly against
``SimRuntime.handle_command`` in ``test_runtime.py``; here the concern is
the transport: replies are relayed, the session survives bad input, and
accepted commands show up in the telemetry stream. All receives go through
the bounded helpers in ``ws_helpers.py``.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fission_sim.api.app import app

from .ws_helpers import (
    collect_telemetry,
    receive_reply,
    receive_telemetry,
    send_command,
)

_SPEED = 10  # speed multiplier applied at the start of each test


def _wall_budget(sim_seconds: float) -> float:
    """Wall-clock budget [s] for ``sim_seconds`` of simulated time at ``_SPEED``:
    the nominal duration with 4x headroom plus 5 s for a slow machine."""
    return sim_seconds / _SPEED * 4 + 5.0


def _set_speed(ws, speed: int) -> None:
    """Send a set_speed command and consume its acknowledgement."""
    assert send_command(ws, {"type": "set_speed", "value": speed}) == {
        "type": "ack",
        "command": "set_speed",
    }


# ---------------------------------------------------------------------------
# Accepted commands show up in telemetry
# ---------------------------------------------------------------------------


def test_rod_command_reflected_in_telemetry():
    """set_rod_command 0.6 is echoed in telemetry and moves the rod toward 0.6.

    The control bank starts at 0.5 and moves at ``RodParams.v_normal`` =
    1 %/s, so 2 s of simulated time should move it about 0.02 toward the new
    command. Half of that is required, which a rod that did not move (or
    moved the wrong way) cannot meet.
    """
    with TestClient(app) as client:
        with client.websocket_connect("/ws/telemetry") as ws:
            _set_speed(ws, _SPEED)
            rod_start = receive_telemetry(ws)["rod_position"]

            assert send_command(ws, {"type": "set_rod_command", "value": 0.6})["type"] == "ack"
            # Frames published before the command was handled still carry
            # the old command; start collecting at the first one that doesn't.
            receive_telemetry(ws, lambda f: f["rod_command"] == 0.6)
            frames = collect_telemetry(ws, sim_seconds=2.0, timeout=_wall_budget(2.0))

    last_rod = frames[-1]["rod_position"]
    assert frames[-1]["rod_command"] == 0.6
    assert rod_start + 0.01 <= last_rod <= 0.6, (
        f"rod_position moved from {rod_start:.4f} to {last_rod:.4f}; expected about +0.02 toward 0.6"
    )


def test_scram_drops_power_and_reset_scram_clears():
    """scram drops power below 20 % of its pre-scram value; reset_scram clears the latch.

    Sequence:
    1. Run at 10x for 5 s of simulated time.
    2. Capture pre-scram power.
    3. Send scram; collect 10 s of simulated time.
    4. Assert power < 20 % of pre-scram, control bank inserted, scrammed True.
    5. Send reset_scram; a later frame reports scrammed False.
    """
    with TestClient(app) as client:
        with client.websocket_connect("/ws/telemetry") as ws:
            _set_speed(ws, _SPEED)

            warmup_frames = collect_telemetry(ws, sim_seconds=5.0, timeout=_wall_budget(5.0))
            pre_scram_power = warmup_frames[-1]["power_thermal"]
            assert pre_scram_power > 0, "Pre-scram power must be > 0"

            assert send_command(ws, {"type": "scram"})["type"] == "ack"
            receive_telemetry(ws, lambda f: f["scrammed"] is True)
            post_scram_frames = collect_telemetry(ws, sim_seconds=10.0, timeout=_wall_budget(10.0))

            assert send_command(ws, {"type": "reset_scram"})["type"] == "ack"
            receive_telemetry(ws, lambda f: f["scrammed"] is False)

    last_frame = post_scram_frames[-1]
    final_power = last_frame["power_thermal"]
    assert final_power < 0.20 * pre_scram_power, (
        f"Power after scram ({final_power:.1f} W) is not below 20% of "
        f"pre-scram power ({pre_scram_power:.1f} W)"
    )
    assert last_frame["rod_position"] == pytest.approx(0.0, abs=0.01), (
        f"rod_position after scram should be ~0, got {last_frame['rod_position']:.4f}"
    )
    assert last_frame["scrammed"] is True, "scrammed flag should be True after scram"


# ---------------------------------------------------------------------------
# Replies are relayed and the session survives bad input
# ---------------------------------------------------------------------------


def test_invalid_command_returns_error_and_session_continues():
    """A rejected command is answered with an error frame, and the session
    keeps streaming telemetry and accepting commands afterwards."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws/telemetry") as ws:
            error = send_command(ws, {"type": "set_rod_command", "value": 2.0})
            assert error["type"] == "error"
            assert "out of range" in error["detail"]

            t_error = receive_telemetry(ws)["t"]
            assert receive_telemetry(ws, lambda f: f["t"] > t_error)
            assert send_command(ws, {"type": "pause"})["type"] == "ack"


def test_undecodable_message_returns_error_and_session_continues():
    """Text that is not JSON, and a binary frame, each get an error frame
    instead of ending the session (which previously closed without a close
    frame)."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws/telemetry") as ws:
            ws.send_text("not json {")
            error = receive_reply(ws)
            assert error["type"] == "error"
            assert "not valid JSON" in error["detail"]

            ws.send_bytes(b'{"type": "pause"}')
            error = receive_reply(ws)
            assert error["type"] == "error"
            assert "binary" in error["detail"]

            # Still connected both ways: telemetry flows, commands are handled.
            receive_telemetry(ws)
            assert send_command(ws, {"type": "set_speed", "value": 2})["type"] == "ack"
