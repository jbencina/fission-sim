"""Tests for fission_sim.api.runtime — SimRuntime background task.

These tests verify the async runtime without the HTTP layer. Tests are
intentionally generous with wall-clock tolerances to avoid CI flakiness
on slow machines: a 1× real-time simulator may run faster or slower than
wall time depending on load, so we assert only conservative lower bounds.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

import pytest

import fission_sim.api.runtime as runtime_module
from fission_sim.api.runtime import SIM_ERROR_PREFIX, SimRuntime

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
    "P_steam_Pa",
    "P_steam_MPa",
    "T_secondary",
    "level_sg",
    "time_to_level_floor_s",
    "m_steam",
    "m_dump",
    "P_electric",
    "turbine_load",
    "T_ref",
    "turbine_trip_active",
    "m_fw",
    "m_fw_max",
    "m_fw_demand",
    "fw_saturated",
    "rod_demand",
    "rod_auto_acting",
    "running",
    "speed",
    "scrammed",
    "rod_command",
    "turbine_load_demand",
    "turbine_trip",
    "rod_auto",
    "level_setpoint",
    "feedwater_manual",
    "model_limit",
}


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


async def test_reset_returns_to_t_zero_and_initial_rod_commands(runtime: SimRuntime):
    """reset() restarts the plant at t = 0 with the rod commands at their
    initial state (rod command 0.5, SCRAM latch clear) and keeps speed.

    The runtime first runs past t = 0.3 s, so a reset that did nothing would
    leave t there.
    """
    runtime.set_speed(2)
    runtime.set_rod_command(0.7)
    runtime.scram()
    while runtime.snapshot()["t"] < 0.3:
        await asyncio.sleep(0.05)

    await runtime.reset()

    frame = runtime.snapshot()
    assert frame["t"] == 0.0
    assert frame["rod_command"] == 0.5
    assert frame["scrammed"] is False
    assert frame["speed"] == 2.0
    # ...and the simulation carries on from there.
    await asyncio.sleep(0.3)
    assert runtime.snapshot()["t"] > 0.0


def _live_step_loops() -> list[asyncio.Task]:
    return [t for t in asyncio.all_tasks() if t.get_name() == "sim-step-loop" and not t.done()]


async def test_concurrent_resets_leave_one_step_loop_and_stop_ends_it(caplog):
    """Two resets dispatched in the same event-loop turn (two clients) must
    leave exactly one integration task, and stop() must end it, also when
    it overlaps a reset."""
    rt = SimRuntime()
    await rt.start()
    try:
        replies = await asyncio.gather(
            rt.handle_command({"type": "reset"}),
            rt.handle_command({"type": "reset"}),
        )
        assert [r["type"] for r in replies] == ["ack", "ack"]
        assert len(_live_step_loops()) == 1

        await asyncio.gather(rt.reset(), rt.stop())
        assert _live_step_loops() == []
        # Cancelling the loop is a normal stop, not a simulator fault: no
        # halt, and nothing logged as an error (including by asyncio).
        assert rt.snapshot()["model_limit"] is None
        assert [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR] == []
    finally:
        await rt.stop()
    assert _live_step_loops() == []


async def test_command_sent_during_reset_is_kept():
    """A rod command acknowledged while a reset waits for the old loop to end
    applies after the reset; the reset does not overwrite it with 0.5."""
    rt = SimRuntime()
    await rt.start()
    try:
        reset = asyncio.create_task(rt.reset())
        await asyncio.sleep(0)  # the reset is now waiting for the old loop
        assert (await rt.handle_command({"type": "set_rod_command", "value": 0.7}))["type"] == "ack"
        await reset
        assert rt.snapshot()["rod_command"] == 0.7
    finally:
        await rt.stop()


async def test_step_loop_failure_outside_engine_step_halts_visibly(monkeypatch):
    """If the loop dies outside its guarded engine step (here: building a
    frame), clients get a halt frame explaining it instead of silence, and
    reset() starts a working loop again."""
    rt = SimRuntime()
    q = rt.subscribe()
    q.get_nowait()  # the seeded initial frame

    def broken_frame(snap, cmd):
        raise RuntimeError("frame builder broke")

    real_build = runtime_module._build_telemetry_frame
    monkeypatch.setattr(runtime_module, "_build_telemetry_frame", broken_frame)
    await rt.start()
    try:
        halt = await asyncio.wait_for(q.get(), timeout=2.0)
        assert halt["running"] is False
        assert halt["model_limit"].startswith(SIM_ERROR_PREFIX)
        assert "RuntimeError: frame builder broke" in halt["model_limit"]
        assert rt.snapshot() == halt

        monkeypatch.setattr(runtime_module, "_build_telemetry_frame", real_build)
        await rt.reset()
        stepped = await asyncio.wait_for(_next_frame_after_t0(q), timeout=2.0)
        assert stepped["model_limit"] is None
    finally:
        rt.unsubscribe(q)
        await rt.stop()


def test_web_ui_uses_the_same_sim_error_prefix():
    """The web UI tells a simulator fault from a model limit by this prefix,
    so its copy in the TypeScript types must match the backend's exactly."""
    telemetry_ts = Path(__file__).resolve().parents[2] / "web" / "src" / "types" / "telemetry.ts"
    match = re.search(r"export const SIM_ERROR_PREFIX = '([^']*)';", telemetry_ts.read_text(encoding="utf-8"))
    assert match is not None, "SIM_ERROR_PREFIX not found in web/src/types/telemetry.ts"
    assert match.group(1) == SIM_ERROR_PREFIX


async def _next_frame_after_t0(q: asyncio.Queue) -> dict:
    while (frame := await q.get())["t"] == 0.0:
        pass
    return frame


@pytest.mark.parametrize(
    ("msg", "detail"),
    [
        ([], "JSON object"),
        ({"value": 1}, "string field 'type'"),
        ({"type": "launch"}, "unknown command type"),
        ({"type": "set_rod_command", "value": "high"}, "numeric"),
        # JSON true/false are not numbers (Python would read True as 1).
        ({"type": "set_rod_command", "value": True}, "numeric"),
        ({"type": "set_speed", "value": True}, "numeric"),
        ({"type": "set_pressure_setpoint", "value": False}, "numeric"),
        ({"type": "set_rod_command", "value": 1.5}, "out of range"),
        ({"type": "set_rod_command", "value": -0.1}, "out of range"),
        ({"type": "set_speed", "value": 3}, "must be one of"),
        ({"type": "set_speed"}, "numeric"),
        ({"type": "set_pressure_setpoint", "value": 5e6}, "out of range"),
        ({"type": "set_pressure_setpoint", "value": 25e6}, "out of range"),
    ],
)
async def test_handle_command_rejects_invalid_messages(msg, detail):
    """Each invalid command gets an error reply and changes nothing."""
    rt = SimRuntime()
    # The pressure setpoint is not a frame field, so compare it separately.
    before = (dict(rt.snapshot()), rt._cmd.P_setpoint)
    reply = await rt.handle_command(msg)
    assert reply["type"] == "error"
    assert detail in reply["detail"]
    assert (rt.snapshot(), rt._cmd.P_setpoint) == before


async def test_handle_command_accepts_valid_messages():
    """Valid commands are acknowledged and reach the command state."""
    rt = SimRuntime()
    for msg in (
        {"type": "set_rod_command", "value": 0.6},
        {"type": "set_speed", "value": 5},
        {"type": "set_pressure_setpoint", "value": 15e6},
        {"type": "scram"},
    ):
        assert await rt.handle_command(msg) == {"type": "ack", "command": msg["type"]}
    frame = rt.snapshot()
    assert (frame["rod_command"], frame["speed"], frame["scrammed"]) == (0.6, 5.0, True)
    assert rt._cmd.P_setpoint == 15e6  # not a frame field


async def test_all_required_keys_present(runtime: SimRuntime):
    """Every telemetry frame must contain all required keys."""
    q = runtime.subscribe()
    try:
        await asyncio.wait_for(q.get(), timeout=0.5)  # the seeded frame
        frame = await asyncio.wait_for(q.get(), timeout=0.5)  # a stepped frame
    except asyncio.TimeoutError:
        pytest.fail("No telemetry frame received within 0.5 s")
    finally:
        runtime.unsubscribe(q)

    missing = REQUIRED_FRAME_KEYS - set(frame.keys())
    assert not missing, f"Frame missing required keys: {sorted(missing)}"
