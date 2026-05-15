"""Tests for SimRuntime pause/resume transition telemetry publishing.

Validates that when the runtime transitions between running and paused states,
it publishes exactly one telemetry frame reflecting the new state so subscribers
(and the web UI) immediately see the correct ``running`` flag.

DEF-01 root cause: ``_step_loop`` only published frames inside the
``if is_running:`` branch, so no frame with ``running=False`` was ever pushed
when the simulation was paused.

These tests verify the fix:
  - Pause causes one frame with ``running == False`` to be pushed within 0.5 s.
  - After the pause frame, no additional frames arrive (the loop is quiet).
  - Resume causes one frame with ``running == True`` within 0.5 s, followed by
    a steady stream of frames (the loop is active again).
"""

from __future__ import annotations

import asyncio

import pytest

from fission_sim.api.runtime import SimRuntime


@pytest.fixture
async def runtime():
    """Construct a SimRuntime, start it, yield it, then stop it."""
    rt = SimRuntime()
    await rt.start()
    yield rt
    await rt.stop()


@pytest.mark.asyncio
async def test_pause_publishes_running_false(runtime: SimRuntime):
    """After pause(), a frame with running=False must arrive within 0.5 s.

    Also verifies that NO additional frames arrive for at least 1 s after
    the pause transition frame — the loop must be quiet while paused.
    """
    q = runtime.subscribe()
    try:
        # Drain any already-queued running frames so the queue is empty.
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


@pytest.mark.asyncio
async def test_resume_publishes_running_true(runtime: SimRuntime):
    """After resume(), a frame with running=True must arrive within 0.5 s.

    Also verifies that subsequent frames continue to arrive (the loop is
    actively advancing simulation time again).
    """
    q = runtime.subscribe()
    try:
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

        # Now resume; this should trigger a single transition frame with running=True.
        runtime.resume()

        try:
            resume_frame = await asyncio.wait_for(q.get(), timeout=0.5)
        except asyncio.TimeoutError:
            pytest.fail("No telemetry frame with running=True received within 0.5 s after resume()")

        assert resume_frame.get("running") is True, (
            f"Expected running=True in resume transition frame, got running={resume_frame.get('running')!r}"
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
