"""Coupled primary-plant tests — wired through SimEngine.

Replaces the pre-slice-4 _assemble_plant helper that built the f(t, y) function
manually. The engine version is declarative; these tests assert that the
coupled plant satisfies the four properties the M1 spec calls out:

1. Steady-state holds at design.
2. Rod withdrawal raises power, then Doppler+moderator level it off.
3. Scram with rod motion drops power gradually.
4. Energy balance closes (Q_core ≈ Q_sg).
"""

from __future__ import annotations

import numpy as np
import pytest

from fission_sim.control.pressurizer_controller import (
    PressurizerController,
    PressurizerControllerParams,
)
from fission_sim.engine import SimEngine
from fission_sim.physics.core import CoreParams, PointKineticsCore
from fission_sim.physics.pressurizer import Pressurizer, PressurizerParams
from fission_sim.physics.primary_loop import LoopParams, PrimaryLoop
from fission_sim.physics.rod_controller import RodController, RodParams
from fission_sim.physics.secondary_sink import SecondarySink, SinkParams
from fission_sim.physics.steam_generator import SGParams, SteamGenerator


def _assemble_plant():
    """Build the M2 plant via the engine and return (engine, modules) ready
    for run() with a scenario_fn.

    Module registration order is rod, core, loop, sg, sink, pzr, pzr_ctrl —
    matching tests/test_engine.py::_assemble_full_plant for cross-test
    consistency. Includes M2 pressurizer and controller so the loop's new
    inputs (m_dot_spray, m_dot_surge) are satisfied.
    """
    engine = SimEngine()
    loop_params = LoopParams()
    pzr_params = PressurizerParams(loop_params=loop_params)
    ctrl_params = PressurizerControllerParams()

    rod = engine.module(RodController(RodParams()), name="rod")
    core = engine.module(PointKineticsCore(CoreParams()), name="core")
    loop = engine.module(PrimaryLoop(loop_params), name="loop")
    sg = engine.module(SteamGenerator(SGParams()), name="sg")
    sink = engine.module(SecondarySink(SinkParams()), name="sink")
    pzr = engine.module(Pressurizer(pzr_params), name="pzr")
    pzr_ctrl = engine.module(PressurizerController(ctrl_params), name="pzr_ctrl")

    rod_cmd = engine.input("rod_command", default=0.5)
    scram = engine.input("scram", default=False)
    P_setpoint = engine.input("P_setpoint", default=ctrl_params.P_setpoint_default)
    heater_manual = engine.input("heater_manual", default=None)
    spray_manual = engine.input("spray_manual", default=None)

    rho_rod = rod(rod_command=rod_cmd, scram=scram)
    T_sec = sink()
    Q_sg = sg(T_avg=loop.T_avg, T_secondary=T_sec)
    core(rho_rod=rho_rod, T_cool=loop.T_cool)
    pzr(
        power_thermal=core.power_thermal,
        Q_sg=Q_sg,
        T_hotleg=loop.T_hot,
        T_coldleg=loop.T_cold,
        Q_heater=pzr_ctrl.Q_heater,
        m_dot_spray=pzr_ctrl.m_dot_spray,
    )
    pzr_ctrl(
        P=pzr.P,
        P_setpoint=P_setpoint,
        heater_manual=heater_manual,
        spray_manual=spray_manual,
    )
    loop(
        power_thermal=core.power_thermal,
        Q_sg=Q_sg,
        m_dot_spray=pzr_ctrl.m_dot_spray,
        P_primary=pzr.P,
    )
    engine.finalize()
    return engine, {
        "rod": rod,
        "core": core,
        "loop": loop,
        "sg": sg,
        "sink": sink,
        "pzr": pzr,
        "pzr_ctrl": pzr_ctrl,
    }


def test_coupled_steady_state_holds() -> None:
    """All five components at design conditions: state should not drift over 60s."""
    engine, modules = _assemble_plant()
    snap = engine.run(t_end=60.0)
    # n stays at 1
    assert snap["core"]["n"] == pytest.approx(1.0, abs=1e-3)
    # Loop temps stay at reference
    p_loop = modules["loop"]._component.params
    assert snap["loop"]["T_hot"] == pytest.approx(p_loop.T_hot_ref, abs=0.05)
    assert snap["loop"]["T_cold"] == pytest.approx(p_loop.T_cold_ref, abs=0.05)
    # Rod stays at design position
    p_rod = modules["rod"]._component.params
    assert snap["rod"]["rod_position"] == pytest.approx(p_rod.rod_position_design, abs=1e-4)


def test_coupled_doppler_plus_moderator_levels_off() -> None:
    """Withdraw rod by 0.015 (=+210 pcm step) at t=10 s. Power should plateau,
    loop should heat up, both Doppler and moderator feedback should be active."""
    p_rod = RodParams()
    engine, modules = _assemble_plant()

    def scenario(t: float) -> dict:
        return {
            "rod_command": p_rod.rod_position_design + (0.015 if t >= 10.0 else 0.0),
            "scram": False,
        }

    # +5 s relative to slice 2 to allow the ~1.5 s rod-motion delay before Doppler kicks in
    snap, dense = engine.run(t_end=205.0, scenario_fn=scenario, dense=True)
    # Sample late: power has plateaued
    t_late = np.linspace(155.0, 205.0, 50)
    n_late = dense.signal("n", t_late)
    rel_change = abs(n_late[-1] - n_late[0]) / n_late[0]
    assert rel_change < 0.05, "power not plateaued"
    # Loop's T_avg has risen
    p_loop = modules["loop"]._component.params
    T_avg_final = (snap["loop"]["T_hot"] + snap["loop"]["T_cold"]) / 2
    assert T_avg_final > p_loop.T_avg_ref, "loop did not heat up"
    # Power is bounded
    assert n_late.max() < 100.0


def test_coupled_energy_balance_closes_at_steady() -> None:
    """At steady state with no rod movement, Q_core ≈ Q_sg within 0.1%.

    This is M1 success criterion #4 from .docs/design.md §4.
    """
    engine, _ = _assemble_plant()
    snap = engine.run(t_end=120.0, max_step=0.5)
    Q_core = snap["signals"]["power_thermal"]
    Q_sg = snap["signals"]["Q_sg"]
    rel_err = abs(Q_core - Q_sg) / Q_core
    assert rel_err < 1e-3, (
        f"Energy balance not closed: Q_core={Q_core:.4e} W, Q_sg={Q_sg:.4e} W (rel err {rel_err:.4%})"
    )


def test_coupled_energy_balance_closes_during_transient() -> None:
    """At a stable plateau after a rod-step transient, Q_core ≈ Q_sg
    within 1%.

    Stronger than the steady-state version: the plateau is reached via a
    real transient where the loop's storage term (M·c_p·dT/dt) was
    actively non-zero. If the storage term has a sign error or
    miscoefficient, the plateau won't close even though the steady-state
    test does (which is trivially true at exact equilibrium).
    """
    engine, _ = _assemble_plant()

    def scenario(t: float) -> dict:
        return {"rod_command": 0.5 + (0.015 if t >= 10.0 else 0.0), "scram": False}

    snap = engine.run(t_end=200.0, scenario_fn=scenario)
    Q_core = snap["signals"]["power_thermal"]
    Q_sg = snap["signals"]["Q_sg"]
    rel_err = abs(Q_core - Q_sg) / Q_core
    assert rel_err < 1e-2, (
        f"Energy balance not closed during transient: Q_core={Q_core:.4e} W, Q_sg={Q_sg:.4e} W (rel err {rel_err:.4%})"
    )


def test_coupled_scram_drops_power_with_rod_motion() -> None:
    """Hold steady to t=10, then scram. Power should drop dramatically as rods
    insert (rod motion takes ~1 s), then continue to fall via the delayed-neutron
    tail. Verifies the genuine scram-via-rod-motion coupling end to end."""
    engine, _ = _assemble_plant()

    def scenario(t: float) -> dict:
        return {"rod_command": 0.5, "scram": t >= 10.0}

    snap, dense = engine.run(t_end=60.0, scenario_fn=scenario, dense=True, max_step=0.1)
    # Pre-scram: holding steady at n=1
    n_pre = dense.signal("n", np.array([9.0]))[0]
    assert n_pre == pytest.approx(1.0, abs=1e-3)
    # Early post-scram (1.5 s after trigger): rods are mostly inserted,
    # prompt drop has happened, n is at ~8% of design. This catches a
    # regression where the prompt jump is too small or the rod moved too
    # slowly. Real PWR plants land around 6% by 1.5 s post-scram.
    n_early = dense.signal("n", np.array([11.5]))[0]
    assert n_early < 0.10, f"prompt drop too small: n(11.5) = {n_early:.4f}"
    # Post-scram + rod insertion + prompt drop: by t=15s (5 s after scram),
    # rods have fully inserted and the prompt drop is well under way.
    # Real plants are at ~3-5% at 5 s post-scram (delayed-neutron tail).
    n_post = dense.signal("n", np.array([15.0]))[0]
    assert n_post < 0.05, f"power didn't drop enough: n(15) = {n_post:.4f}"
    # Late: delayed-neutron tail still nonzero
    n_late = dense.signal("n", np.array([60.0]))[0]
    assert n_late > 1e-4, f"delayed-neutron tail vanished too fast: n(60) = {n_late:.4e}"
    # Verify rod actually moved (not just power dropped from feedback)
    rod_pos_final = snap["rod"]["rod_position"]
    assert rod_pos_final < 0.05, f"rod did not fully insert: rod_position(60) = {rod_pos_final:.4f}"
