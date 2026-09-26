"""Bounded receive helpers for ``TestClient`` WebSocket sessions.

``WebSocketTestSession.receive_text()`` blocks until a message arrives, so
a test waiting for telemetry that never comes would hang the suite instead
of failing. These helpers put a real timeout on every receive and sort the
two kinds of server message apart:

- telemetry frames, which have no ``"type"`` key, and
- command replies, ``{"type": "ack", ...}`` or ``{"type": "error", ...}``.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import anyio
import pytest
from starlette.testclient import WebSocketTestSession

# Longest wait for any single expected message [s]. Telemetry arrives every
# 0.1 s and replies within a few milliseconds, so this only matters when
# something is broken.
RECEIVE_TIMEOUT_S = 5.0


def receive_message(ws: WebSocketTestSession, timeout: float = RECEIVE_TIMEOUT_S) -> dict[str, Any]:
    """Receive one JSON message, failing the test if none arrives within ``timeout`` s.

    The wait runs inside the session's event-loop portal under
    ``anyio.fail_after``, which can interrupt it; a wall-clock check around
    the blocking ``receive_text()`` could not. ``_send_rx`` is the session's
    (private) stream of server-to-client messages.
    """

    assert hasattr(ws, "portal") and hasattr(ws, "_send_rx"), (
        "Starlette's WebSocketTestSession no longer has the portal/_send_rx "
        "internals this helper relies on; update receive_message for the new version"
    )

    async def _receive() -> dict[str, Any]:
        with anyio.fail_after(timeout):
            return await ws._send_rx.receive()

    try:
        message = ws.portal.call(_receive)
    except TimeoutError:
        pytest.fail(f"no WebSocket message from the server within {timeout} s")
    if message["type"] == "websocket.close":
        pytest.fail(f"server closed the WebSocket (code {message.get('code')}): {message.get('reason')!r}")
    return json.loads(message["text"])


def is_telemetry(message: dict[str, Any]) -> bool:
    """True for a telemetry frame, False for an ack/error command reply."""
    return "type" not in message


def receive_telemetry(
    ws: WebSocketTestSession,
    predicate: Callable[[dict[str, Any]], bool] = lambda frame: True,
    *,
    timeout: float = RECEIVE_TIMEOUT_S,
) -> dict[str, Any]:
    """Return the next telemetry frame matching ``predicate``, skipping replies."""
    deadline = time.monotonic() + timeout
    while (remaining := deadline - time.monotonic()) > 0:
        message = receive_message(ws, remaining)
        if is_telemetry(message) and predicate(message):
            return message
    pytest.fail(f"no matching telemetry frame within {timeout} s")


def receive_reply(ws: WebSocketTestSession, *, timeout: float = RECEIVE_TIMEOUT_S) -> dict[str, Any]:
    """Return the next ack or error reply, skipping telemetry frames."""
    deadline = time.monotonic() + timeout
    while (remaining := deadline - time.monotonic()) > 0:
        message = receive_message(ws, remaining)
        if not is_telemetry(message):
            return message
    pytest.fail(f"no command reply within {timeout} s")


def send_command(ws: WebSocketTestSession, command: dict[str, Any]) -> dict[str, Any]:
    """Send ``command`` and return its reply (telemetry in between is skipped)."""
    ws.send_json(command)
    return receive_reply(ws)


def collect_telemetry(
    ws: WebSocketTestSession,
    *,
    sim_seconds: float,
    timeout: float,
) -> list[dict[str, Any]]:
    """Collect telemetry frames until ``sim_seconds`` of simulated time have passed.

    The simulated clock starts at the first telemetry frame received. Fails
    if that much simulated time does not pass within ``timeout`` wall seconds.
    """
    deadline = time.monotonic() + timeout
    frames = [receive_telemetry(ws, timeout=timeout)]
    t_start = frames[0]["t"]
    while frames[-1]["t"] - t_start < sim_seconds:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            pytest.fail(
                f"only {frames[-1]['t'] - t_start:.2f} s of the {sim_seconds} s of "
                f"simulated time passed within {timeout} s"
            )
        frames.append(receive_telemetry(ws, timeout=remaining))
    return frames
