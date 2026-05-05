"""Standalone matplotlib driver for the coupled primary plant.

Throwaway script. Drives core + loop + SG + sink through their real public APIs
while faking the rod controller (will arrive as a real component in slice 3).

Default scenario:
    t = 0..10   : steady state at design power
    t = 10      : +200 pcm rod step
    t = 10..60  : Doppler AND moderator feedback level power off
    t = 60      : scram (-7000 pcm)
    t = 60..300 : delayed-neutron tail; loop water cools

Run:
    uv run python examples/run_primary.py

Produces a four-panel matplotlib figure.

Note on intentional duplication: this script holds its own ~30 lines of plant
wiring, identical in shape to ``tests/test_primary_plant.py::_assemble_plant``
and ``examples/report_primary.py``. The duplication is the signal that the
engine should be extracted in slice 4 — see the spec at
``docs/superpowers/specs/2026-05-04-primary-loop-and-secondary-design.md`` §10.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from scipy.integrate import solve_ivp

from fission_sim.physics.core import CoreParams, PointKineticsCore
from fission_sim.physics.primary_loop import LoopParams, PrimaryLoop
from fission_sim.physics.secondary_sink import SecondarySink, SinkParams
from fission_sim.physics.steam_generator import SGParams, SteamGenerator


# ---------------------------------------------------------------------------
# Faked upstream input source (rod controller arrives in slice 3).
# ---------------------------------------------------------------------------
def rod_reactivity_fn(t: float) -> float:
    """Piecewise rod reactivity schedule [dimensionless]."""
    if t < 10.0:
        return 0.0
    if t < 60.0:
        return 200e-5  # +200 pcm step
    return -7000e-5  # scram


def main() -> None:
    # --- construct components ---
    core = PointKineticsCore(CoreParams())
    loop = PrimaryLoop(LoopParams())
    sg = SteamGenerator(SGParams())
    sink = SecondarySink(SinkParams())

    # --- assemble global initial state: 8 core + 2 loop ---
    y0 = np.concatenate([core.initial_state(), loop.initial_state()])

    # --- f(t, y) glue — see the design spec §2.3 for shape ---
    def f(t, y):
        s_core = y[0:8]
        s_loop = y[8:10]

        # Compute outputs in dependency order
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

        # Compute derivatives, threading outputs through inputs
        dy = np.empty_like(y)
        dy[0:8] = core.derivatives(
            s_core,
            inputs={
                "rod_reactivity": rod_reactivity_fn(t),
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

    # --- reactivity components vectorized over t ---
    p_core = core.params
    rho_rod = np.array([rod_reactivity_fn(ti) for ti in t])
    rho_doppler = p_core.alpha_f * (T_fuel - p_core.T_fuel_ref)
    rho_mod = p_core.alpha_m * (T_avg - p_core.T_cool_ref)
    rho_total = rho_rod + rho_doppler + rho_mod

    # --- heat flows over t ---
    Q_core = n * p_core.P_design
    Q_sg = sg.params.UA * (T_avg - sink.params.T_secondary)

    # --- four-panel diagnostic plot ---
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))

    # Panel 1: power and primary temperatures
    ax = axes[0, 0]
    ax.semilogy(t, n, "b-", label="n")
    ax.set_title("Neutron population n (relative to design)")
    ax.set_xlabel("t [s]")
    ax.set_ylabel("n")
    ax.grid(True, which="both", alpha=0.3)

    # Panel 2: primary leg temperatures
    ax = axes[0, 1]
    ax.plot(t, T_hot, "r-", label="T_hot")
    ax.plot(t, T_cold, "b-", label="T_cold")
    ax.plot(t, T_avg, "k--", label="T_avg", linewidth=1)
    ax.plot(t, T_fuel, "orange", label="T_fuel")
    ax.set_title("Temperatures")
    ax.set_xlabel("t [s]")
    ax.set_ylabel("T [K]")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)

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

    fig.suptitle("Coupled primary plant — default scenario")
    fig.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
