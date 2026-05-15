"""Tests for fission_sim.api.runtime — SimRuntime background task.

These tests verify the async runtime without the HTTP layer. Tests are
intentionally generous with wall-clock tolerances to avoid CI flakiness
on slow machines: a 1× real-time simulator may run faster or slower than
wall time depending on load, so we assert only conservative lower bounds.
"""

from __future__ import annotations

import asyncio

import pytest

from fission_sim.api.runtime import SimRuntime

# Required keys in every telemetry frame.
REQUIRED_FRAME_KEYS = {
    "t",
    "power_thermal",
    "T_hot",
    "T_cold",
    "T_avg",
    "T_fuel",
    "rod_position",
    "P_primary_Pa",
    "P_primary_MPa",
    "Q_sg",
    "rho_rod",
    "rho_doppler",
    "rho_moderator",
    "rho_total",
    "running",
    "speed",
    "scrammed",
    "rod_command",
}


@pytest.fixture
async def runtime():
    """Construct a SimRuntime, start it, yield it, then stop it."""
    rt = SimRuntime()
    await rt.start()
    yield rt
    await rt.stop()


@pytest.mark.asyncio
async def test_runtime_advances_time(runtime: SimRuntime):
    """Simulator time must advance while the runtime is running.

    Wall-clock budget: ~2 s. We allow up to 4 s wall time to keep the
    test green on slow CI while still being useful.
    """
    t_before = runtime.snapshot()["t"]
    await asyncio.sleep(2.0)
    t_after = runtime.snapshot()["t"]
    # At 1× speed, 2 s wall time should advance sim time by at least 0.5 s.
    assert t_after - t_before >= 0.5, (
        f"Simulator time did not advance sufficiently: t_before={t_before:.3f}, t_after={t_after:.3f}"
    )


@pytest.mark.asyncio
async def test_pause_halts_time(runtime: SimRuntime):
    """After pause(), simulator time must stop advancing."""
    # Let the runtime run briefly so t > 0.
    await asyncio.sleep(0.5)
    runtime.pause()
    # Give the current step loop iteration a moment to finish.
    await asyncio.sleep(0.2)
    t_paused = runtime.snapshot()["t"]
    # Wait and confirm t does not change.
    await asyncio.sleep(1.0)
    t_later = runtime.snapshot()["t"]
    assert t_later - t_paused < 0.1, (
        f"Time advanced after pause: t_paused={t_paused:.3f}, t_later={t_later:.3f}"
    )


@pytest.mark.asyncio
async def test_resume_after_pause(runtime: SimRuntime):
    """After resume(), simulator time must advance again."""
    await asyncio.sleep(0.3)
    runtime.pause()
    await asyncio.sleep(0.2)
    t_paused = runtime.snapshot()["t"]
    runtime.resume()
    await asyncio.sleep(1.5)
    t_after = runtime.snapshot()["t"]
    assert t_after > t_paused + 0.3, (
        f"Time did not advance after resume: t_paused={t_paused:.3f}, t_after={t_after:.3f}"
    )


@pytest.mark.asyncio
async def test_reset_returns_t_near_zero(runtime: SimRuntime):
    """After reset(), snapshot t must be close to 0."""
    await asyncio.sleep(0.5)
    await runtime.reset()
    t = runtime.snapshot()["t"]
    assert t < 1.0, f"After reset, t={t:.3f} is not near 0"


@pytest.mark.asyncio
async def test_subscription_delivers_frames(runtime: SimRuntime):
    """A subscriber queue must receive at least one frame within 0.5 s."""
    q = runtime.subscribe()
    try:
        frame = await asyncio.wait_for(q.get(), timeout=0.5)
        assert isinstance(frame, dict), "Frame must be a dict"
    except asyncio.TimeoutError:
        pytest.fail("No telemetry frame received within 0.5 s")
    finally:
        runtime.unsubscribe(q)


@pytest.mark.asyncio
async def test_all_required_keys_present(runtime: SimRuntime):
    """Every telemetry frame must contain all required keys."""
    q = runtime.subscribe()
    try:
        frame = await asyncio.wait_for(q.get(), timeout=0.5)
    except asyncio.TimeoutError:
        pytest.fail("No telemetry frame received within 0.5 s")
    finally:
        runtime.unsubscribe(q)

    missing = REQUIRED_FRAME_KEYS - set(frame.keys())
    assert not missing, f"Frame missing required keys: {sorted(missing)}"
