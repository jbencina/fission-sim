"""SimRuntime halts coherently at the edge of the model's physical domain.

Reachable path (accepted operator commands only): withdraw the control bank
fully (rod command 1.0) and lower the pressure setpoint to the 10 MPa bottom
of the accepted range together from the default full-power state. Rod
withdrawal heats the loop, whose expanding water surges into the pressurizer,
while the controller sprays continuously to chase the low setpoint. Both fill
the pressurizer; after about 236.5 s of simulated time it goes water-solid
(steam quality reaches 0), which the saturated-pressurizer closure cannot
describe. Before the domain check, the simulation kept running there with a
negative quality and a pressure that climbed for no physical reason.

The test runs at speed 200 (the allowed speeds are widened for this test
only; the operator can choose 1–10x), so the roughly 4-minute transient takes
a few seconds of wall time. That changes only how far each step advances, not
which commands were accepted.
"""

from __future__ import annotations

import asyncio

import pytest

import fission_sim.api.runtime as runtime_module
from fission_sim.api.runtime import SIM_ERROR_PREFIX, SimRuntime


async def _wait_for_halt(q: asyncio.Queue, timeout: float) -> dict:
    """Return the first frame with a model limit, failing after ``timeout`` s."""

    async def _next_halt() -> dict:
        while True:
            frame = await q.get()
            if frame["model_limit"] is not None:
                return frame

    try:
        return await asyncio.wait_for(_next_halt(), timeout=timeout)
    except asyncio.TimeoutError:
        pytest.fail(f"no model-limit frame within {timeout} s")


async def test_accepted_commands_reach_model_limit_and_halt_coherently(monkeypatch):
    rt = SimRuntime()
    for msg in (
        {"type": "set_rod_command", "value": 1.0},
        {"type": "set_pressure_setpoint", "value": 10e6},
    ):
        assert (await rt.handle_command(msg))["type"] == "ack"
    monkeypatch.setattr(runtime_module, "_ALLOWED_SPEEDS", (*runtime_module._ALLOWED_SPEEDS, 200.0))
    rt.set_speed(200)

    q = rt.subscribe()
    await rt.start()
    try:
        halt = await _wait_for_halt(q, timeout=60.0)

        # Stopped, with an explanation that names the broken assumption.
        assert halt["running"] is False
        assert "pressurizer has filled solid" in halt["model_limit"]
        assert "Reset" in halt["model_limit"]
        assert rt.snapshot() == halt

        # The published state is the last valid one: time did not advance
        # past it, and the engine was rolled back to that same state.
        assert halt["t"] == pytest.approx(rt._engine.t)
        pzr = rt._engine.snapshot()["pzr"]
        assert 0.0 < pzr["x"] < 1.0
        assert pzr["P"] == pytest.approx(halt["P_primary_Pa"])

        # Resume is refused with an explanation; the halt stays in place.
        reply = await rt.handle_command({"type": "resume"})
        assert reply["type"] == "error"
        assert "Reset" in reply["detail"]
        await asyncio.sleep(0.3)
        assert rt.snapshot()["running"] is False
        assert rt.snapshot()["t"] == halt["t"]

        # Reset clears the limit and the simulation runs again from t = 0.
        assert (await rt.handle_command({"type": "reset"}))["type"] == "ack"
        after = rt.snapshot()
        assert after["model_limit"] is None
        assert after["running"] is True
        assert after["t"] == pytest.approx(0.0)
        while not q.empty():
            q.get_nowait()
        stepped = await asyncio.wait_for(q.get(), timeout=5.0)
        assert stepped["t"] > 0.0
        assert stepped["model_limit"] is None
    finally:
        rt.unsubscribe(q)
        await rt.stop()


async def test_unexpected_step_failure_halts_as_simulation_error():
    """A non-domain failure (a bug) halts the same way but is labelled as a
    simulator fault, so the UI does not present it as a physics limit."""
    rt = SimRuntime()

    def broken_step(*args, **kwargs):
        raise RuntimeError("solver blew up")

    rt._engine.step = broken_step
    q = rt.subscribe()
    await rt.start()
    try:
        halt = await _wait_for_halt(q, timeout=5.0)
        assert halt["running"] is False
        assert halt["t"] == pytest.approx(0.0)
        assert halt["model_limit"].startswith(SIM_ERROR_PREFIX)
        assert "RuntimeError: solver blew up" in halt["model_limit"]
        assert (await rt.handle_command({"type": "resume"}))["type"] == "error"

        # A browser that loads or reconnects now is seeded with the halt,
        # so it sees the explanation too.
        late = rt.subscribe()
        try:
            assert late.get_nowait() == halt
        finally:
            rt.unsubscribe(late)
    finally:
        rt.unsubscribe(q)
        await rt.stop()
