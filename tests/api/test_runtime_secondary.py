"""Secondary-side telemetry and command coverage for the web runtime."""

from __future__ import annotations

import asyncio
import json
import math
from typing import Any

import pytest
from fastapi.testclient import TestClient

import fission_sim.api.runtime as runtime_module
from fission_sim.api.app import app
from fission_sim.api.runtime import SimRuntime

from .ws_helpers import receive_reply, receive_telemetry, send_command

NUMERIC_FRAME_KEYS = {
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
    "speed",
    "rod_command",
    "P_steam_Pa",
    "P_steam_MPa",
    "T_secondary",
    "level_sg",
    "m_steam",
    "m_dump",
    "P_electric",
    "turbine_load",
    "turbine_load_demand_effective",
    "T_ref",
    "m_fw",
    "m_fw_max",
    "m_fw_demand",
    "rod_demand",
    "turbine_load_demand",
    "level_setpoint",
}

BOOLEAN_FRAME_KEYS = {
    "running",
    "scrammed",
    "turbine_trip_active",
    "fw_saturated",
    "rod_auto_acting",
    "turbine_trip",
    "rod_auto",
}

NULLABLE_NUMERIC_FRAME_KEYS = {
    "time_to_level_floor_s",
    "feedwater_manual",
    "feedwater_manual_effective",
}

ALL_SECONDARY_FRAME_KEYS = NUMERIC_FRAME_KEYS | BOOLEAN_FRAME_KEYS | NULLABLE_NUMERIC_FRAME_KEYS | {"model_limit"}


def _command_state(rt: SimRuntime) -> tuple[Any, ...]:
    """Return the runtime command state fields that validation errors must not touch."""
    cmd = rt._cmd
    return (
        cmd.rod_command,
        cmd.scrammed,
        cmd.P_setpoint,
        cmd.speed,
        cmd.running,
        cmd.model_limit,
        cmd.turbine_load_demand,
        cmd.turbine_trip,
        cmd.rod_auto,
        cmd.level_setpoint,
        cmd.feedwater_manual,
    )


def _assert_plain_json_frame(frame: dict[str, Any]) -> None:
    """Assert that a frame is strict-JSON serialisable and contains plain scalar values."""
    json.dumps(frame, allow_nan=False)
    assert set(frame) == ALL_SECONDARY_FRAME_KEYS

    for key, value in frame.items():
        if key == "model_limit":
            assert value is None or type(value) is str, f"{key} is {type(value).__name__}, not str or None"
        else:
            assert type(value) in (float, bool, type(None)), (
                f"{key} is {type(value).__name__}, not a plain JSON scalar type"
            )
    for key in NUMERIC_FRAME_KEYS:
        assert type(frame[key]) is float, f"{key} is {type(frame[key]).__name__}, not plain float"
        assert math.isfinite(frame[key]), f"{key} is not finite: {frame[key]!r}"
    for key in BOOLEAN_FRAME_KEYS:
        assert type(frame[key]) is bool, f"{key} is {type(frame[key]).__name__}, not plain bool"
    for key in NULLABLE_NUMERIC_FRAME_KEYS:
        value = frame[key]
        assert value is None or type(value) is float, f"{key} is {type(value).__name__}, not float or None"
        if value is not None:
            assert math.isfinite(value), f"{key} is not finite: {value!r}"
    assert frame["model_limit"] is None or type(frame["model_limit"]) is str


async def _next_frame(q: asyncio.Queue, predicate, *, timeout: float = 5.0) -> dict[str, Any]:
    """Return the next frame matching ``predicate`` within ``timeout`` seconds."""

    async def _wait() -> dict[str, Any]:
        while True:
            frame = await q.get()
            if predicate(frame):
                return frame

    return await asyncio.wait_for(_wait(), timeout=timeout)


def _step_runtime_once(rt: SimRuntime, dt: float) -> None:
    """Advance a stopped runtime once with the same externals the step loop uses."""
    cmd = rt._cmd
    snap = rt._engine.step(
        dt,
        rod_command=cmd.rod_command,
        scram=cmd.scrammed,
        P_setpoint=cmd.P_setpoint,
        heater_manual=None,
        spray_manual=None,
        turbine_load=cmd.turbine_load_demand,
        turbine_trip=cmd.turbine_trip,
        rod_auto=cmd.rod_auto,
        level_setpoint=cmd.level_setpoint,
        feedwater_manual=cmd.feedwater_manual,
    )
    rt._publish(runtime_module._build_telemetry_frame(snap, cmd))


def test_design_frame_has_secondary_keys_plain_types_and_strict_json() -> None:
    """The design frame is the TypeScript contract source: keys, types and JSON must be exact."""
    rt = SimRuntime()

    _assert_plain_json_frame(rt.snapshot())


async def test_frame_after_turbine_trip_is_strict_json_and_pressure_rises() -> None:
    """A tripped turbine publishes effective trip status and steam pressure rises within a few seconds."""
    rt = SimRuntime()
    assert (await rt.handle_command({"type": "set_speed", "value": 10}))["type"] == "ack"
    q = rt.subscribe()
    await rt.start()
    try:
        p_before = rt.snapshot()["P_steam_Pa"]
        assert (await rt.handle_command({"type": "turbine_trip"})) == {
            "type": "ack",
            "command": "turbine_trip",
        }

        tripped = await _next_frame(q, lambda f: f["turbine_trip_active"] is True and f["turbine_trip"] is True)
        later = await _next_frame(q, lambda f: f["t"] >= tripped["t"] + 3.0)

        _assert_plain_json_frame(later)
        assert later["P_steam_Pa"] > p_before
    finally:
        rt.unsubscribe(q)
        await rt.stop()


async def test_scram_alone_effectively_trips_turbine_without_operator_trip_latch() -> None:
    """The P-4 interlock makes SCRAM an effective turbine trip without setting the operator-trip latch."""
    rt = SimRuntime()
    assert (await rt.handle_command({"type": "set_speed", "value": 10}))["type"] == "ack"
    q = rt.subscribe()
    await rt.start()
    try:
        assert (await rt.handle_command({"type": "scram"})) == {"type": "ack", "command": "scram"}
        frame = await _next_frame(
            q,
            lambda f: f["scrammed"] is True and f["turbine_trip_active"] is True,
        )

        assert frame["turbine_trip"] is False
    finally:
        rt.unsubscribe(q)
        await rt.stop()


async def test_secondary_commands_ack_and_update_command_state() -> None:
    """Each secondary-side command uses the existing ack shape and changes its frame field."""
    rt = SimRuntime()

    assert (await rt.handle_command({"type": "set_turbine_load", "value": 0.4})) == {
        "type": "ack",
        "command": "set_turbine_load",
    }
    assert rt.snapshot()["turbine_load_demand"] == 0.4

    assert (await rt.handle_command({"type": "turbine_trip"})) == {"type": "ack", "command": "turbine_trip"}
    assert rt.snapshot()["turbine_trip"] is True

    assert (await rt.handle_command({"type": "reset_turbine_trip"})) == {
        "type": "ack",
        "command": "reset_turbine_trip",
    }
    assert rt.snapshot()["turbine_trip"] is False
    assert rt.snapshot()["turbine_load_demand"] == 0.0

    assert (await rt.handle_command({"type": "set_rod_auto", "value": True})) == {
        "type": "ack",
        "command": "set_rod_auto",
    }
    assert rt.snapshot()["rod_auto"] is True

    assert (await rt.handle_command({"type": "set_level_setpoint", "value": 0.35}))["type"] == "ack"
    assert rt.snapshot()["level_setpoint"] == 0.35
    assert (await rt.handle_command({"type": "set_level_setpoint", "value": 0.90}))["type"] == "ack"
    assert rt.snapshot()["level_setpoint"] == 0.90

    assert (await rt.handle_command({"type": "set_feedwater_manual", "value": 0.25})) == {
        "type": "ack",
        "command": "set_feedwater_manual",
    }
    assert rt.snapshot()["feedwater_manual"] == 0.25
    assert (await rt.handle_command({"type": "set_feedwater_manual", "value": None}))["type"] == "ack"
    assert rt.snapshot()["feedwater_manual"] is None

    assert (await rt.handle_command({"type": "set_turbine_load", "value": 0.8}))["type"] == "ack"
    assert (await rt.handle_command({"type": "scram"}))["type"] == "ack"
    assert (await rt.handle_command({"type": "reset_scram"})) == {
        "type": "ack",
        "command": "reset_scram",
    }
    assert rt.snapshot()["scrammed"] is False
    assert rt.snapshot()["turbine_load_demand"] == 0.0


@pytest.mark.parametrize(
    ("msg", "detail"),
    [
        ({"type": "set_turbine_load", "value": "NaN"}, "finite numeric"),
        ({"type": "set_turbine_load", "value": math.nan}, "finite numeric"),
        ({"type": "set_turbine_load", "value": math.inf}, "finite numeric"),
        ({"type": "set_turbine_load", "value": -math.inf}, "finite numeric"),
        ({"type": "set_turbine_load", "value": -0.1}, "out of range"),
        ({"type": "set_turbine_load", "value": 1.5}, "out of range"),
        ({"type": "set_turbine_load", "value": True}, "finite numeric"),
        ({"type": "set_rod_auto", "value": 1}, "JSON boolean"),
        ({"type": "set_rod_auto", "value": "true"}, "JSON boolean"),
        ({"type": "set_rod_auto", "value": None}, "JSON boolean"),
        ({"type": "set_level_setpoint", "value": 0.34}, "out of range"),
        ({"type": "set_level_setpoint", "value": 0.91}, "out of range"),
        ({"type": "set_level_setpoint", "value": math.nan}, "finite numeric"),
        ({"type": "set_feedwater_manual", "value": -0.1}, "out of range"),
        ({"type": "set_feedwater_manual", "value": 1.1}, "out of range"),
        ({"type": "set_feedwater_manual", "value": math.inf}, "finite numeric"),
        ({"type": "set_feedwater_manual", "value": False}, "finite numeric"),
    ],
)
async def test_secondary_command_validation_errors_leave_state_untouched(msg: dict[str, Any], detail: str) -> None:
    """Invalid secondary commands report an error and do not alter command state."""
    rt = SimRuntime()
    before = (dict(rt.snapshot()), _command_state(rt))

    reply = await rt.handle_command(msg)

    assert reply["type"] == "error"
    assert detail in reply["detail"]
    assert (rt.snapshot(), _command_state(rt)) == before


def test_raw_websocket_nan_literal_is_rejected_and_session_continues() -> None:
    """Python json.loads accepts NaN literals, so the runtime must reject them after parsing."""
    with TestClient(app) as client:
        with client.websocket_connect("/ws/telemetry") as ws:
            initial = receive_telemetry(ws)

            ws.send_text('{"type":"set_turbine_load","value":NaN}')
            error = receive_reply(ws)
            assert error["type"] == "error"
            assert "finite numeric" in error["detail"]

            frame = receive_telemetry(ws, lambda f: f["turbine_load_demand"] == initial["turbine_load_demand"])
            assert frame["turbine_load_demand"] == 1.0
            assert send_command(ws, {"type": "set_turbine_load", "value": 0.9}) == {
                "type": "ack",
                "command": "set_turbine_load",
            }


async def test_rod_auto_to_manual_syncs_command_to_actual_bank_position() -> None:
    """Auto-to-manual transfer is bumpless: the retained manual command becomes the actual bank position."""
    rt = SimRuntime()
    assert (await rt.handle_command({"type": "set_rod_auto", "value": True}))["type"] == "ack"
    assert (await rt.handle_command({"type": "set_turbine_load", "value": 0.0}))["type"] == "ack"

    for _ in range(12):
        _step_runtime_once(rt, 10.0)
        if abs(rt.snapshot()["rod_position"] - 0.5) > 0.005:
            break
    moved_position = rt.snapshot()["rod_position"]
    assert abs(moved_position - 0.5) > 0.005, "automatic control did not move the bank enough for the test"

    assert (await rt.handle_command({"type": "set_rod_auto", "value": False})) == {
        "type": "ack",
        "command": "set_rod_auto",
    }

    frame = rt.snapshot()
    assert frame["rod_auto"] is False
    assert frame["rod_command"] == pytest.approx(moved_position)


async def test_rod_auto_to_manual_during_reset_syncs_to_rebuilt_bank_position() -> None:
    """AUTO→MANUAL during reset uses the new t=0 bank position, not the stale pre-reset frame."""
    rt = SimRuntime()
    assert (await rt.handle_command({"type": "set_rod_auto", "value": True}))["type"] == "ack"
    assert (await rt.handle_command({"type": "set_turbine_load", "value": 0.0}))["type"] == "ack"

    for _ in range(12):
        _step_runtime_once(rt, 10.0)
        if abs(rt.snapshot()["rod_position"] - 0.5) > 0.005:
            break
    moved_position = rt.snapshot()["rod_position"]
    assert abs(moved_position - 0.5) > 0.005, "automatic control did not move the bank enough for the test"

    await rt.start()
    q: asyncio.Queue | None = None
    try:
        rt.pause()

        real_stop_task = rt._stop_task

        async def yielding_stop_task() -> None:
            await asyncio.sleep(0)
            await real_stop_task()

        rt._stop_task = yielding_stop_task
        reset_task = asyncio.create_task(rt.reset())
        await asyncio.sleep(0)
        assert rt._reset_in_progress is True

        assert (await rt.handle_command({"type": "set_rod_auto", "value": False})) == {
            "type": "ack",
            "command": "set_rod_auto",
        }
        await reset_task

        frame = rt.snapshot()
        assert frame["t"] == 0.0
        assert frame["rod_auto"] is False
        assert frame["rod_position"] == pytest.approx(0.5)
        assert frame["rod_command"] == pytest.approx(0.5)

        q = rt.subscribe()
        q.get_nowait()
        rt.resume()
        resumed = await _next_frame(q, lambda f: f["t"] > 0.0, timeout=2.0)
        assert resumed["rod_position"] == pytest.approx(0.5)
        assert resumed["rod_command"] == pytest.approx(0.5)
    finally:
        rt._stop_task = real_stop_task
        if q is not None:
            rt.unsubscribe(q)
        await rt.stop()


async def test_reset_keeps_and_clears_secondary_command_state() -> None:
    """reset() preserves the planned settings and clears trip/manual one-shot states."""
    rt = SimRuntime()
    assert (await rt.handle_command({"type": "set_speed", "value": 5}))["type"] == "ack"
    assert (await rt.handle_command({"type": "set_pressure_setpoint", "value": 15e6}))["type"] == "ack"
    assert (await rt.handle_command({"type": "set_rod_command", "value": 0.7}))["type"] == "ack"
    assert (await rt.handle_command({"type": "set_turbine_load", "value": 0.4}))["type"] == "ack"
    assert (await rt.handle_command({"type": "set_rod_auto", "value": True}))["type"] == "ack"
    assert (await rt.handle_command({"type": "set_level_setpoint", "value": 0.6}))["type"] == "ack"
    assert (await rt.handle_command({"type": "set_feedwater_manual", "value": 0.3}))["type"] == "ack"
    assert (await rt.handle_command({"type": "turbine_trip"}))["type"] == "ack"
    assert (await rt.handle_command({"type": "scram"}))["type"] == "ack"
    rt.pause()

    await rt.reset()

    frame = rt.snapshot()
    assert frame["t"] == 0.0
    assert frame["running"] is False
    assert frame["speed"] == 5.0
    assert rt._cmd.P_setpoint == 15e6
    assert frame["rod_command"] == 0.5
    assert frame["scrammed"] is False
    assert frame["turbine_load_demand"] == 0.4
    assert frame["turbine_trip"] is False
    assert frame["rod_auto"] is True
    assert frame["level_setpoint"] == 0.6
    assert frame["feedwater_manual"] is None


async def test_paused_new_command_fields_publish_without_advancing_time(runtime: SimRuntime) -> None:
    """Secondary command fields use the same paused-publication path as existing commands."""
    await asyncio.sleep(0.3)
    runtime.pause()
    await asyncio.sleep(0.2)
    t_paused = runtime.snapshot()["t"]
    q = runtime.subscribe()
    try:
        q.get_nowait()

        assert (await runtime.handle_command({"type": "set_turbine_load", "value": 0.7}))["type"] == "ack"
        load_frame = await asyncio.wait_for(q.get(), timeout=0.5)
        assert (load_frame["t"], load_frame["turbine_load_demand"]) == (t_paused, 0.7)

        assert (await runtime.handle_command({"type": "turbine_trip"}))["type"] == "ack"
        trip_frame = await asyncio.wait_for(q.get(), timeout=0.5)
        assert (trip_frame["t"], trip_frame["turbine_trip"]) == (t_paused, True)

        assert (await runtime.handle_command({"type": "set_rod_auto", "value": True}))["type"] == "ack"
        auto_frame = await asyncio.wait_for(q.get(), timeout=0.5)
        assert (auto_frame["t"], auto_frame["rod_auto"]) == (t_paused, True)

        assert (await runtime.handle_command({"type": "set_level_setpoint", "value": 0.6}))["type"] == "ack"
        level_frame = await asyncio.wait_for(q.get(), timeout=0.5)
        assert (level_frame["t"], level_frame["level_setpoint"]) == (t_paused, 0.6)

        assert (await runtime.handle_command({"type": "set_feedwater_manual", "value": 0.2}))["type"] == "ack"
        fw_frame = await asyncio.wait_for(q.get(), timeout=0.5)
        assert (fw_frame["t"], fw_frame["feedwater_manual"]) == (t_paused, 0.2)

        assert (await runtime.handle_command({"type": "set_feedwater_manual", "value": None}))["type"] == "ack"
        fw_auto_frame = await asyncio.wait_for(q.get(), timeout=0.5)
        assert (fw_auto_frame["t"], fw_auto_frame["feedwater_manual"]) == (t_paused, None)

        await asyncio.sleep(0.3)
        assert q.empty()
    finally:
        runtime.unsubscribe(q)


async def test_paused_selected_feedwater_and_admission_differ_from_last_stepped_effective_state() -> None:
    """Paused commands update selected fields immediately; effective fields wait for the next accepted step."""
    rt = SimRuntime()
    initial = rt.snapshot()
    assert initial["turbine_load_demand"] == 1.0
    assert initial["turbine_load_demand_effective"] == 1.0
    assert initial["feedwater_manual"] is None
    assert initial["feedwater_manual_effective"] is None

    rt.pause()

    assert (await rt.handle_command({"type": "set_turbine_load", "value": 0.4}))["type"] == "ack"
    assert (await rt.handle_command({"type": "set_feedwater_manual", "value": 0.25}))["type"] == "ack"

    paused = rt.snapshot()
    assert paused["running"] is False
    assert paused["t"] == initial["t"]
    assert paused["turbine_load_demand"] == 0.4
    assert paused["turbine_load_demand_effective"] == 1.0
    assert paused["feedwater_manual"] == 0.25
    assert paused["feedwater_manual_effective"] is None

    _step_runtime_once(rt, 0.1)

    stepped = rt.snapshot()
    assert stepped["t"] > paused["t"]
    assert stepped["running"] is False
    assert stepped["turbine_load_demand"] == 0.4
    assert stepped["turbine_load_demand_effective"] == 0.4
    assert stepped["feedwater_manual"] == 0.25
    assert stepped["feedwater_manual_effective"] == 0.25
