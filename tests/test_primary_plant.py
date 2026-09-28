"""Coupled primary-plant tests — wired through SimEngine.

The plant is wired here by hand, independently of
``fission_sim.plant.build_standard_plant``, as a separate check on the
physics. The tests assert that the coupled plant satisfies these properties:

1. Steady-state holds at design.
2. Rod withdrawal raises power, then Doppler+moderator level it off.
3. Scram with rod motion drops power gradually and keeps the core
   subcritical.
4. Energy balance closes: at steady state (P_fission ≈ Q_sg) and, more
   importantly, while fuel and loop storage are changing
   (dE_fuel/dt + dE_loop/dt = P_fission − Q_sg).
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


def _rod_command_for(pcm: float) -> float:
    """Control-bank command that adds ``pcm`` of rod reactivity relative to
    design, so scenarios are stated in physical reactivity rather than in
    slider fractions (default worth: 1,200 pcm per full travel, 12 pcm per
    1 % of travel)."""
    p = RodParams()
    return p.rod_position_design + pcm * 1e-5 / p.rho_control_worth


def _assemble_plant():
    """Build the full plant via the engine and return (engine, modules) ready
    for run() with a scenario_fn.

    Module registration order is rod, core, loop, sg, sink, pzr, pzr_ctrl —
    matching tests/test_engine.py::_assemble_full_plant for cross-test
    consistency. Includes the pressurizer and controller so the loop's
    inputs (m_dot_spray, P_primary) are satisfied. The loop and pressurizer
    are heated by the core's ``Q_fuel_to_coolant`` (heat leaving the fuel),
    not by fission power.
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

    rod(rod_command=rod_cmd, scram=scram)
    T_sec = sink()
    Q_sg = sg(T_avg=loop.T_avg, T_secondary=T_sec)
    core(rho_rod=rod.rho_rod, T_cool=loop.T_cool)
    pzr(
        Q_fuel_to_coolant=core.Q_fuel_to_coolant,
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
        Q_fuel_to_coolant=core.Q_fuel_to_coolant,
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
    # Rod stays at design position; shutdown bank stays out
    p_rod = modules["rod"]._component.params
    assert snap["rod"]["rod_position"] == pytest.approx(p_rod.rod_position_design, abs=1e-4)
    assert snap["rod"]["shutdown_position"] == pytest.approx(1.0, abs=1e-6)


def test_loop_thermal_time_constant_exceeds_fuel_time_constant() -> None:
    """With thermal masses sized to the represented inventory, the coolant
    must respond more slowly than the fuel (review finding A9):

        tau_fuel = M_fuel · c_p_fuel / hA_fc                ≈ 5.2 s
        tau_loop = (M_hot + M_cold) · c_p / UA              ≈ 5.7 s

    The previous 30 t "effective" mass gave tau_loop ≈ 1.4 s, so the
    coolant tracked fission power almost instantly.

    The margin is thin (~9 %). It flips if the loop's water mass shrinks
    (smaller V_loop, lower c_p) or the SG conductance grows (larger UA,
    e.g. a smaller primary-secondary ΔT at design), or if the fuel's
    time constant grows (more fuel mass or c_p_fuel, or a smaller hA_fc
    from a hotter T_fuel_ref). Adding a cited metal heat capacity to the
    loop would widen it.
    """
    core_p, loop_p, sg_p = CoreParams(), LoopParams(), SGParams()
    tau_fuel = core_p.M_fuel * core_p.c_p_fuel / core_p.hA_fc
    tau_loop = (loop_p.M_hot + loop_p.M_cold) * loop_p.c_p / sg_p.UA
    assert tau_loop > tau_fuel


def test_coupled_doppler_plus_moderator_levels_off() -> None:
    """Command +210 pcm of control-bank withdrawal at t=10 s (17.5 % of
    travel, ~17.5 s of rod motion at 1 %/s). Power should plateau, loop
    should heat up, both Doppler and moderator feedback should be active."""
    p_rod = RodParams()
    engine, modules = _assemble_plant()

    def scenario(t: float) -> dict:
        return {
            "rod_command": _rod_command_for(210.0) if t >= 10.0 else p_rod.rod_position_design,
            "scram": False,
        }

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

    The steady-state half of property 4 in the module docstring.
    """
    engine, _ = _assemble_plant()
    snap = engine.run(t_end=120.0, max_step=0.5)
    Q_core = snap["core"]["power_thermal"]
    Q_sg = snap["signals"]["Q_sg"]
    rel_err = abs(Q_core - Q_sg) / Q_core
    assert rel_err < 1e-3, (
        f"Energy balance not closed: Q_core={Q_core:.4e} W, Q_sg={Q_sg:.4e} W (rel err {rel_err:.4%})"
    )


def test_coupled_energy_balance_closes_on_plateau_after_rod_step() -> None:
    """At the plateau after a +210 pcm rod step, P_fission ≈ Q_sg within 1%.

    This only checks the settled end state, where every storage term is
    back near zero. The balance while storage is changing is checked by
    the SCRAM tests below.
    """
    engine, _ = _assemble_plant()

    def scenario(t: float) -> dict:
        return {"rod_command": _rod_command_for(210.0) if t >= 10.0 else 0.5, "scram": False}

    snap = engine.run(t_end=200.0, scenario_fn=scenario)
    Q_core = snap["core"]["power_thermal"]
    Q_sg = snap["signals"]["Q_sg"]
    rel_err = abs(Q_core - Q_sg) / Q_core
    assert rel_err < 1e-2, (
        f"Energy balance not closed on plateau: Q_core={Q_core:.4e} W, Q_sg={Q_sg:.4e} W (rel err {rel_err:.4%})"
    )


def _stored_heat_rates(snap: dict, modules: dict) -> tuple[float, float]:
    """Return (dE_fuel/dt, dE_loop/dt) [W] implied by the components'
    own derivatives at a snapshot, using the inputs the engine wired to
    them at that instant. The loop's heat input is read from the loop's
    own telemetry echo, not from the core's output, so a miswire of the
    loop alone is caught."""
    core = modules["core"]._component
    loop = modules["loop"]._component
    sig = snap["signals"]
    c, lo = snap["core"], snap["loop"]
    core_state = np.array([c["n"], *(c[f"C{i}"] for i in range(1, 7)), c["T_fuel"]])
    loop_state = np.array([lo["T_hot"], lo["T_cold"], lo["M_loop"]])
    d_core = core.derivatives(core_state, {"rho_rod": sig["rho_rod"], "T_cool": sig["T_cool"]})
    d_loop = loop.derivatives(
        loop_state,
        {
            "Q_fuel_to_coolant": lo["Q_fuel_to_coolant"],
            "Q_sg": lo["Q_sg"],
            "m_dot_spray": sig["m_dot_spray"],
            "P_primary": sig["P"],
        },
    )
    cp, lp = core.params, loop.params
    dE_fuel = cp.M_fuel * cp.c_p_fuel * d_core[7]
    dE_loop = lp.c_p * (lp.M_hot * d_loop[0] + lp.M_cold * d_loop[1])
    return dE_fuel, dE_loop


def test_energy_balance_holds_while_storage_changes_during_scram() -> None:
    """First law for the fuel + loop control volume, evaluated during a
    SCRAM when neither storage term is near zero:

        dE_fuel/dt + dE_loop/dt = P_fission − Q_sg

    The fuel-to-coolant transfer is internal and must cancel. If the loop
    were heated by fission power instead of heat leaving the fuel (review
    finding A1), the residual would be P_fission − Q_fuel_to_coolant, i.e.
    ~2.5 GW one second after the trip.
    """
    engine, modules = _assemble_plant()
    P_design = modules["core"]._component.params.P_design
    _, dense = engine.run(t_end=12.0, scenario_fn=lambda t: {"scram": t >= 2.0}, dense=True, max_step=0.1)
    for t in (2.1, 2.5, 3.0, 4.0, 7.0, 12.0):
        snap = dense.at(t)
        dE_fuel, dE_loop = _stored_heat_rates(snap, modules)
        external = snap["core"]["power_thermal"] - snap["signals"]["Q_sg"]
        assert abs(dE_fuel + dE_loop - external) / P_design < 1e-6, t
        # Genuinely non-equilibrium: the fuel is releasing stored heat.
        if t >= 2.5:
            assert dE_fuel < -0.1 * P_design, t


def test_scram_reset_after_cooldown_stays_subcritical() -> None:
    """SCRAM, let the plant cool for 20 minutes (fuel and coolant fall to
    the secondary temperature, returning up to ~1,480 pcm of feedback),
    then clear the latch and command the control bank fully out. Only the
    control bank returns (+600 pcm at most); the shutdown bank's
    −6,400 pcm stays in, so the core must stay subcritical. If the
    shutdown bank withdrew by itself on reset, this went supercritical
    (ρ ≈ +680 pcm, n ≈ 2.4) even with the control bank fully inserted."""
    engine, _ = _assemble_plant()
    t_reset = 1210.0

    def scenario(t: float) -> dict:
        return {"rod_command": 1.0 if t >= t_reset else 0.5, "scram": 10.0 <= t < t_reset}

    _, dense = engine.run(t_end=t_reset + 600.0, scenario_fn=scenario, dense=True, max_step=1.0)
    t_after = np.linspace(t_reset, t_reset + 600.0, 301)
    snaps = dense.at(t_after)
    rho_total = np.array([s["core"]["rho_total"] for s in snaps])
    assert rho_total.max() < -0.04  # at least ~4,000 pcm subcritical
    assert snaps[-1]["rod"]["rod_position"] == pytest.approx(1.0, abs=1e-3)  # control bank did withdraw
    assert snaps[-1]["rod"]["shutdown_position"] < 0.01  # shutdown bank did not


def test_scram_cooldown_stored_energy_matches_integrated_heat_flows() -> None:
    """Coupled regression over the first 10 s after a SCRAM, from the
    trajectory alone (no component derivatives): the change in energy
    stored in fuel + loop must equal the time integral of fission power
    minus SG heat removal. Also checks that the loop is fed the heat
    actually leaving the fuel, which after the trip is several times the
    collapsing fission power."""
    engine, modules = _assemble_plant()
    cp = modules["core"]._component.params
    lp = modules["loop"]._component.params
    _, dense = engine.run(t_end=12.0, scenario_fn=lambda t: {"scram": t >= 2.0}, dense=True, max_step=0.1)

    def stored_energy(snap: dict) -> float:
        # Relative to 0 K; only differences matter.
        return cp.M_fuel * cp.c_p_fuel * snap["core"]["T_fuel"] + lp.c_p * (
            lp.M_hot * snap["loop"]["T_hot"] + lp.M_cold * snap["loop"]["T_cold"]
        )

    t = np.linspace(2.0, 12.0, 4001)
    snaps = dense.at(t)
    net_heat = np.array([s["core"]["power_thermal"] - s["signals"]["Q_sg"] for s in snaps])
    integrated = np.sum(0.5 * (net_heat[1:] + net_heat[:-1]) * np.diff(t))
    delta_E = stored_energy(snaps[-1]) - stored_energy(snaps[0])
    assert delta_E < -1.0e10  # tens of GJ leave storage in 10 s
    assert delta_E == pytest.approx(integrated, rel=1e-3)

    one_second_after = dense.at(3.0)
    assert one_second_after["signals"]["Q_fuel_to_coolant"] > 5.0 * one_second_after["core"]["power_thermal"]


def test_coupled_scram_drops_power_with_rod_motion() -> None:
    """Hold steady to t=10, then scram. Power should drop dramatically as rods
    insert (both banks are in by ~2 s), then continue to fall via the
    delayed-neutron tail, and the core must stay subcritical for the next
    300 s while the cooling plant returns positive Doppler and moderator
    reactivity. Verifies the genuine scram-via-rod-motion coupling end to
    end."""
    engine, _ = _assemble_plant()

    def scenario(t: float) -> dict:
        return {"rod_command": 0.5, "scram": t >= 10.0}

    snap, dense = engine.run(t_end=310.0, scenario_fn=scenario, dense=True, max_step=0.1)
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
    # Verify both banks actually moved (not just power dropped from feedback):
    # within 1 % of the bottom 2 s after the trip.
    at_2s = dense.at(12.0)["rod"]
    assert at_2s["rod_position"] < 0.01
    assert at_2s["shutdown_position"] < 0.01
    # Subcritical from the moment rods start moving through 300 s later.
    t_post = np.linspace(10.1, 310.0, 600)
    rho_total = np.array([dense.at(float(ti))["core"]["rho_total"] for ti in t_post])
    assert rho_total.max() < 0.0
    # Deeply subcritical once cooled: rods (−7,000 pcm) outweigh feedback.
    assert rho_total[-1] < -0.05
