"""Tests for what SimRuntime publishes while the simulation is not advancing.

When the step loop is not stepping (paused, or halted at a model limit) it
publishes nothing on its own, so the runtime must publish explicitly
whenever something a client can see changes:

  - A new subscriber is seeded with the current frame at once.
  - Pause publishes one frame with ``running == False``; after that the
    loop is quiet (no frames while nothing changes).
  - Accepted commands given while paused (SCRAM, speed, ...) publish a
    frame carrying the new command state, with simulation time unchanged,
    and ``snapshot()`` agrees.
  - Resume brings back a steady stream of frames with ``running == True``.
"""

from __future__ import annotations

import asyncio

import pytest

from fission_sim.api.runtime import SimRuntime


def _pause(runtime: SimRuntime) -> float:
    """Pause ``runtime`` and return the simulation time it stopped at."""
    runtime.pause()
    return runtime.snapshot()["t"]


async def test_pause_publishes_running_false(runtime: SimRuntime):
    """After pause(), a frame with running=False must arrive within 0.5 s.

    Also verifies that NO additional frames arrive for at least 1 s after
    the pause transition frame — the loop must be quiet while paused.
    """
    q = runtime.subscribe()
    try:
        # Take the seeded frame, then let the loop publish a stepped one.
        q.get_nowait()
        await asyncio.wait_for(q.get(), timeout=0.5)
        # Flush any extra frames that arrived before we paused.
        while not q.empty():
            q.get_nowait()

        # Pause the runtime; this should trigger a single transition frame.
        runtime.pause()

        # Wait for the transition frame (running=False) within 0.5 s.
        try:
            frame = await asyncio.wait_for(q.get(), timeout=0.5)
        except asyncio.TimeoutError:
            pytest.fail("No telemetry frame with running=False received within 0.5 s after pause()")

        assert frame.get("running") is False, (
            f"Expected running=False in transition frame, got running={frame.get('running')!r}"
        )

        # After the single transition frame, the queue must stay empty for 1 s.
        # (No continuous frames while paused.)
        await asyncio.sleep(1.0)
        assert q.empty(), (
            f"Queue was not empty after 1 s of pause — {q.qsize()} extra frame(s) arrived"
        )
    finally:
        runtime.unsubscribe(q)


async def test_resume_publishes_running_true(runtime: SimRuntime):
    """After resume(), a frame with running=True must arrive within 0.5 s.

    Also verifies that subsequent frames continue to arrive (the loop is
    actively advancing simulation time again).
    """
    q = runtime.subscribe()
    try:
        # The seeded frame comes first and shows the runtime running.
        seed = q.get_nowait()
        assert seed["running"] is True

        # Pause the runtime and wait for the pause transition frame.
        runtime.pause()
        try:
            pause_frame = await asyncio.wait_for(q.get(), timeout=0.5)
        except asyncio.TimeoutError:
            pytest.fail("No pause transition frame received within 0.5 s")
        assert pause_frame.get("running") is False, "Expected running=False in pause frame"

        # Flush any stragglers.
        while not q.empty():
            q.get_nowait()

        # Now resume. The live loop publishes the next stepped frame (within
        # one cadence period), which carries running=True.
        runtime.resume()

        try:
            resume_frame = await asyncio.wait_for(q.get(), timeout=0.5)
        except asyncio.TimeoutError:
            pytest.fail("No telemetry frame with running=True received within 0.5 s after resume()")

        assert resume_frame.get("running") is True, (
            f"Expected running=True in the first frame after resume, got running={resume_frame.get('running')!r}"
        )

        # Verify that the loop is active again by confirming additional frames
        # arrive within the next 0.5 s (at 10 Hz we expect several frames).
        try:
            next_frame = await asyncio.wait_for(q.get(), timeout=0.5)
        except asyncio.TimeoutError:
            pytest.fail("No further frames received 0.5 s after resume — loop may not be running")

        assert isinstance(next_frame, dict), "Subsequent frame must be a dict"
    finally:
        runtime.unsubscribe(q)


async def test_subscriber_joining_paused_runtime_gets_current_frame(runtime: SimRuntime):
    """A client that connects while paused sees the paused state at once."""
    await asyncio.sleep(0.3)
    t_paused = _pause(runtime)

    q = runtime.subscribe()
    try:
        frame = q.get_nowait()
        assert frame["running"] is False
        assert frame["t"] == t_paused
        await asyncio.sleep(0.3)
        assert q.empty(), "a paused runtime published without any change"
    finally:
        runtime.unsubscribe(q)


async def test_commands_while_paused_are_published_without_advancing_time(runtime: SimRuntime):
    """SCRAM and a speed change given while paused reach existing subscribers
    and snapshot(), with simulation time standing still."""
    await asyncio.sleep(0.3)
    t_paused = _pause(runtime)
    q = runtime.subscribe()
    try:
        q.get_nowait()  # the seeded paused frame

        assert (await runtime.handle_command({"type": "set_speed", "value": 5}))["type"] == "ack"
        assert (await runtime.handle_command({"type": "scram"}))["type"] == "ack"

        speed_frame = q.get_nowait()
        scram_frame = q.get_nowait()
        assert speed_frame["speed"] == 5.0
        assert (scram_frame["speed"], scram_frame["scrammed"]) == (5.0, True)
        assert scram_frame["t"] == t_paused
        assert scram_frame["running"] is False
        assert runtime.snapshot() == scram_frame

        # Repeating a command that changes nothing stays quiet.
        runtime.scram()
        await asyncio.sleep(0.3)
        assert q.empty()
    finally:
        runtime.unsubscribe(q)
