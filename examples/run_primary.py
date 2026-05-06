"""Standalone matplotlib driver for the coupled primary plant.

Throwaway script. Drives core + loop + SG + sink + rod controller through
their real public APIs. Now that the rod controller is a real component,
the only "fake" inputs in this runner are operator decisions
(rod_command_fn, scram_fn) — which is exactly what they should be.

Default scenario:
    t = 0..10   : steady state at design power (rod_command = 0.5)
    t = 10      : rod_command raised by +0.015 (gradual withdraw, ~1.5 s)
    t = 10..60  : Doppler AND moderator feedback level power off
    t = 60      : scram (rod_command_effective forced to 0)
    t = 60..300 : delayed-neutron tail; loop water cools

Run:
    uv run python examples/run_primary.py

Produces a four-panel matplotlib figure.

Note on intentional duplication: this script holds its own ~35 lines of
plant wiring, identical in shape to ``tests/test_primary_plant.py::_assemble_plant``,
``examples/report_primary.py``, and ``examples/dump_state.py``. The
duplication is the signal that the engine should be extracted in slice 4 —
see the spec at
``docs/superpowers/specs/2026-05-04-rod-controller-design.md`` §9.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from scipy.integrate import solve_ivp

from fission_sim.physics.core import CoreParams, PointKineticsCore
from fission_sim.physics.primary_loop import LoopParams, PrimaryLoop
from fission_sim.physics.rod_controller import RodController, RodParams
from fission_sim.physics.secondary_sink import SecondarySink, SinkParams
from fission_sim.physics.steam_generator import SGParams, SteamGenerator


# ---------------------------------------------------------------------------
# Faked operator inputs (these are correctly fake; we don't model humans).
# ---------------------------------------------------------------------------
def rod_command_fn(t: float) -> float:
    """Operator's rod-position setpoint over time [dimensionless, 0–1]."""
    if t < 10.0:
        return 0.5  # design position
    return 0.515  # +0.015 step at t=10 (≈ +210 pcm via 0.14 worth slope)


def scram_fn(t: float) -> bool:
    """Operator's scram button [bool]."""
    return t >= 60.0


def main() -> None:
    # --- construct components ---
    core = PointKineticsCore(CoreParams())
    loop = PrimaryLoop(LoopParams())
    sg = SteamGenerator(SGParams())
    sink = SecondarySink(SinkParams())
    rod = RodController(RodParams())

    # --- assemble global initial state: 8 core + 2 loop + 1 rod ---
    y0 = np.concatenate([core.initial_state(), loop.initial_state(), rod.initial_state()])

    # --- f(t, y) glue ---
    def f(t, y):
        s_core = y[0:8]
        s_loop = y[8:10]
        s_rod = y[10:11]

        out_sink = sink.outputs(np.empty(0))
        out_loop = loop.outputs(s_loop)
        out_sg = sg.outputs(
            np.empty(0),
            inputs={
                "T_primary": out_loop["T_avg"],
                "T_secondary": out_sink["T_secondary"],
            },
        )
        out_core = core.outputs(s_core)
        out_rod = rod.outputs(s_rod)

        dy = np.empty_like(y)
        dy[0:8] = core.derivatives(
            s_core,
            inputs={
                "rod_reactivity": out_rod["rod_reactivity"],
                "T_cool": out_loop["T_cool"],
            },
        )
        dy[8:10] = loop.derivatives(
            s_loop,
            inputs={
                "Q_core": out_core["power_thermal"],
                "Q_sg": out_sg["Q_sg"],
            },
        )
        dy[10:11] = rod.derivatives(
            s_rod,
            inputs={
                "rod_command": rod_command_fn(t),
                "scram": scram_fn(t),
            },
        )
        return dy

    # --- integrate ---
    sol = solve_ivp(
        f,
        (0.0, 300.0),
        y0,
        method="BDF",
        dense_output=True,
        rtol=1e-6,
        atol=1e-9,
        max_step=0.5,
    )
    if not sol.success:
        raise RuntimeError(f"solve_ivp failed: {sol.message}")

    # --- sample on a uniform grid for plotting ---
    t = np.linspace(0.0, 300.0, 1500)
    Y = sol.sol(t)
    n = Y[0]
    T_fuel = Y[7]
    T_hot = Y[8]
    T_cold = Y[9]
    T_avg = (T_hot + T_cold) / 2
    rod_position = Y[10]

    # --- reactivity components vectorized over t ---
    p_core = core.params
    p_rod = rod.params
    rho_rod = p_rod.rho_total_worth * (rod_position - p_rod.rod_position_critical)
    rho_doppler = p_core.alpha_f * (T_fuel - p_core.T_fuel_ref)
    rho_mod = p_core.alpha_m * (T_avg - p_core.T_cool_ref)
    rho_total = rho_rod + rho_doppler + rho_mod

    # --- heat flows over t ---
    Q_core = n * p_core.P_design
    Q_sg = sg.params.UA * (T_avg - sink.params.T_secondary)

    # --- four-panel diagnostic plot ---
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
    ax.plot(t, T_avg, "k--", label="T_avg", linewidth=1)
    ax.plot(t, T_fuel, "orange", label="T_fuel")
    ax.set_title("Temperatures + rod position")
    ax.set_xlabel("t [s]")
    ax.set_ylabel("T [K]")
    ax.legend(loc="center left", fontsize=8)
    ax.grid(True, alpha=0.3)
    # Right axis for rod position
    ax2 = ax.twinx()
    ax2.plot(t, rod_position, "g-", linewidth=1.5, label="rod_position")
    ax2.set_ylabel("rod position", color="g")
    ax2.set_ylim(-0.05, 1.05)
    ax2.tick_params(axis="y", labelcolor="g")

    # Panel 3: reactivity components in pcm
    ax = axes[1, 0]
    PCM = 1e5
    ax.plot(t, rho_rod * PCM, label="rod")
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

    fig.suptitle("Coupled primary plant + rod controller — default scenario")
    fig.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
