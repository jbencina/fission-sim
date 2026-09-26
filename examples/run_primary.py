"""Matplotlib driver for the coupled primary plant — the expanded wiring example.

This is the one example that assembles the plant by hand: every component,
every operator input, and every wire between them is spelled out in
``build_plant()`` below, so you can read how the engine graph is put
together. The other operational examples and the web runtime get the same
plant from ``fission_sim.plant.build_standard_plant()``;
``tests/test_examples.py`` checks the two wirings stay identical.

Default scenario:
    t = 0..10   : steady state at design power (rod_command = 0.5)
    t = 10      : rod_command raised 0.5 → 0.675 (+210 pcm; ~17.5 s of rod
                  motion at 1 %/s)
    t = 10..60  : Doppler AND moderator feedback level power off
    t = 60      : scram (control and shutdown banks drop in ~2 s, −7,000 pcm)
    t = 60..300 : delayed-neutron tail; loop water cools

Run:
    uv run python examples/run_primary.py

Produces a four-panel matplotlib figure.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np

from fission_sim.control.pressurizer_controller import (
    PressurizerController,
    PressurizerControllerParams,
)
from fission_sim.disclaimer import print_disclaimer
from fission_sim.engine import SimEngine
from fission_sim.physics.core import CoreParams, PointKineticsCore
from fission_sim.physics.domain import check_snapshot
from fission_sim.physics.pressurizer import Pressurizer, PressurizerParams
from fission_sim.physics.primary_loop import LoopParams, PrimaryLoop
from fission_sim.physics.rod_controller import RodController, RodParams
from fission_sim.physics.secondary_sink import SecondarySink, SinkParams
from fission_sim.physics.steam_generator import SGParams, SteamGenerator


def scenario(t: float) -> dict:
    """Operator inputs over time."""
    return {
        # +210 pcm: 0.175 of travel × 1,200 pcm control-bank worth.
        "rod_command": 0.5 if t < 10.0 else 0.675,
        "scram": t >= 60.0,
    }


def build_plant(core_params: CoreParams) -> SimEngine:
    """Wire the standard primary plant by hand and finalize it.

    Same topology as ``fission_sim.plant.build_standard_plant()``.
    """
    loop_params = LoopParams()
    # The pressurizer computes surge flow from the loop's thermal expansion,
    # so it shares the loop's parameter object.
    pzr_params = PressurizerParams(loop_params=loop_params)
    ctrl_params = PressurizerControllerParams()

    # 1. Register the components. The names become the snapshot keys.
    engine = SimEngine()
    rod = engine.module(RodController(RodParams()), name="rod")
    core = engine.module(PointKineticsCore(core_params), name="core")
    loop = engine.module(PrimaryLoop(loop_params), name="loop")
    sg = engine.module(SteamGenerator(SGParams()), name="sg")
    sink = engine.module(SecondarySink(SinkParams()), name="sink")
    pzr = engine.module(Pressurizer(pzr_params), name="pzr")
    pzr_ctrl = engine.module(PressurizerController(ctrl_params), name="pzr_ctrl")

    # 2. Declare the operator's inputs (engine externals) with defaults.
    #    None for the manual overrides means "automatic control".
    rod_cmd = engine.input("rod_command", default=0.5)
    scram = engine.input("scram", default=False)
    P_setpoint = engine.input("P_setpoint", default=ctrl_params.P_setpoint_default)
    heater_manual = engine.input("heater_manual", default=None)
    spray_manual = engine.input("spray_manual", default=None)

    # 3. Wire outputs to inputs. Calling a module connects its input ports;
    #    ``module.<port>`` is a handle to one of its outputs. The order of
    #    these calls does not matter: finalize() sorts the evaluation order.
    rho_rod = rod(rod_command=rod_cmd, scram=scram)
    T_sec = sink()
    Q_sg_sig = sg(T_avg=loop.T_avg, T_secondary=T_sec)
    core(rho_rod=rho_rod, T_cool=loop.T_cool)
    pzr(
        Q_fuel_to_coolant=core.Q_fuel_to_coolant,
        Q_sg=Q_sg_sig,
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
        Q_sg=Q_sg_sig,
        m_dot_spray=pzr_ctrl.m_dot_spray,
        P_primary=pzr.P,
    )

    # 4. Validate the graph (every input connected, no cycles) and allocate
    #    the state vector.
    engine.finalize()
    return engine


def main() -> None:
    print_disclaimer()
    core_params = CoreParams()
    engine = build_plant(core_params)

    # --- integrate ---
    _final_snap, dense = engine.run(t_end=300.0, scenario_fn=scenario, dense=True)

    # --- sample on a uniform grid for plotting ---
    t = np.linspace(0.0, 300.0, 1500)

    # Pull arrays for each plotted quantity.
    Q_core = dense.signal("power_thermal", t)
    n = Q_core / core_params.P_design
    Q_sg = dense.signal("Q_sg", t)

    # Things not directly in the wiring graph (T_hot, T_cold, T_fuel,
    # rod_position): pull them from per-time snapshots. dense.at() with
    # an array argument returns a list of snapshots.
    snaps = dense.at(t)
    # Stop with an explanation, as the web runtime does, rather than plot
    # a state outside the model's liquid-loop / saturated-pressurizer domain.
    for snap in snaps:
        check_snapshot(snap)
    T_hot = np.array([s["loop"]["T_hot"] for s in snaps])
    T_cold = np.array([s["loop"]["T_cold"] for s in snaps])
    T_avg_arr = (T_hot + T_cold) / 2
    T_fuel = np.array([s["core"]["T_fuel"] for s in snaps])
    rod_position = np.array([s["rod"]["rod_position"] for s in snaps])

    # --- reactivity components ---
    rho_rod_arr = dense.signal("rho_rod", t)
    rho_doppler = core_params.alpha_f * (T_fuel - core_params.T_fuel_ref)
    rho_mod = core_params.alpha_m * (T_avg_arr - core_params.T_cool_ref)
    rho_total = rho_rod_arr + rho_doppler + rho_mod

    # --- four-panel plot ---
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))

    # Panel 1: power
    ax = axes[0, 0]
    ax.semilogy(t, n, "b-")
    ax.set_title("Neutron population n (relative to design)")
    ax.set_xlabel("t [s]")
    ax.set_ylabel("n")
    ax.grid(True, which="both", alpha=0.3)

    # Panel 2: primary leg temperatures + rod position (right axis)
    ax = axes[0, 1]
    ax.plot(t, T_hot, "r-", label="T_hot")
    ax.plot(t, T_cold, "b-", label="T_cold")
    ax.plot(t, T_avg_arr, "k--", label="T_avg", linewidth=1)
    ax.plot(t, T_fuel, "orange", label="T_fuel")
    ax.set_title("Temperatures + rod position")
    ax.set_xlabel("t [s]")
    ax.set_ylabel("T [K]")
    ax.legend(loc="center left", fontsize=8)
    ax.grid(True, alpha=0.3)
    ax2 = ax.twinx()
    ax2.plot(t, rod_position, "g-", linewidth=1.5, label="rod_position")
    ax2.set_ylabel("rod position", color="g")
    ax2.set_ylim(-0.05, 1.05)
    ax2.tick_params(axis="y", labelcolor="g")

    # Panel 3: reactivity components in pcm
    ax = axes[1, 0]
    PCM = 1e5
    ax.plot(t, rho_rod_arr * PCM, label="rod")
    ax.plot(t, rho_doppler * PCM, label="Doppler")
    ax.plot(t, rho_mod * PCM, label="moderator")
    ax.plot(t, rho_total * PCM, "k", linewidth=2, label="total")
    ax.set_title("Reactivity components [pcm]")
    ax.set_xlabel("t [s]")
    ax.set_ylabel("ρ [pcm]")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

    # Panel 4: heat flows (energy balance check)
    ax = axes[1, 1]
    ax.plot(t, Q_core / 1e9, "r-", label="Q_core")
    ax.plot(t, Q_sg / 1e9, "b-", label="Q_sg")
    ax.set_title("Heat flows [GW] — gap shows loop thermal storage")
    ax.set_xlabel("t [s]")
    ax.set_ylabel("Q [GW]")
    ax.legend()
    ax.grid(True, alpha=0.3)

    fig.suptitle("Coupled primary plant + rod controller — engine-driven")
    fig.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
