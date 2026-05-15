"""Standalone driver for the PointKineticsCore.

Throwaway script. Drives the core's real public API while faking the
two upstream input sources (rod controller and primary loop) with plain
Python functions of time.

Default scenario:
    t = 0..10   : steady state at design power
    t = 10      : +200 pcm rod step
    t = 10..60  : Doppler feedback levels power off
    t = 60      : scram (-7000 pcm)
    t = 60..300 : delayed-neutron tail

Run:
    uv run python examples/run_core.py

Produces a four-panel matplotlib figure.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from scipy.integrate import solve_ivp

from fission_sim.disclaimer import print_disclaimer
from fission_sim.physics.core import CoreParams, PointKineticsCore


# ---------------------------------------------------------------------------
# Faked upstream input sources. In the real plant these come from the rod
# controller and primary loop components. Here they are hand-coded.
# ---------------------------------------------------------------------------
def rod_reactivity_fn(t: float) -> float:
    """Piecewise rod reactivity schedule [dimensionless]."""
    if t < 10.0:
        return 0.0
    if t < 60.0:
        return 200e-5  # +200 pcm step
    return -7000e-5  # scram


def T_cool_fn(t: float, T_ref: float = 580.0) -> float:
    """Constant coolant temperature [K].

    Swap this for a toy first-order lag if you want to see coupled
    moderator feedback (when the primary loop component arrives, this
    function disappears entirely).
    """
    return T_ref


def main() -> None:
    print_disclaimer()
    params = CoreParams()
    core = PointKineticsCore(params)
    y0 = core.initial_state()

    def f(t, y):
        return core.derivatives(
            y,
            {
                "rho_rod": rod_reactivity_fn(t),
                "T_cool": T_cool_fn(t),
            },
        )

    # Integrate over the full scenario. max_step keeps the BDF solver from
    # sailing past the rod step at t=10 and the scram at t=60.
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

    # Sample on a uniform grid for plotting
    t = np.linspace(0.0, 300.0, 1500)
    Y = sol.sol(t)
    n = Y[0]
    Cs = Y[1:7]
    T_fuel = Y[7]

    # Reactivity components (vectorized over t)
    rho_rod = np.array([rod_reactivity_fn(ti) for ti in t])
    rho_doppler = params.alpha_f * (T_fuel - params.T_fuel_ref)
    T_cool = np.array([T_cool_fn(ti) for ti in t])
    rho_mod = params.alpha_m * (T_cool - params.T_cool_ref)
    rho_total = rho_rod + rho_doppler + rho_mod

    # Four-panel diagnostic plot
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))

    axes[0, 0].semilogy(t, n)
    axes[0, 0].set_title("Neutron population (relative to design)")
    axes[0, 0].set_xlabel("t [s]")
    axes[0, 0].set_ylabel("n")
    axes[0, 0].grid(True, which="both", alpha=0.3)

    axes[0, 1].plot(t, T_fuel)
    axes[0, 1].set_title("Fuel temperature")
    axes[0, 1].set_xlabel("t [s]")
    axes[0, 1].set_ylabel("T_fuel [K]")
    axes[0, 1].grid(True, alpha=0.3)

    PCM = 1e5
    axes[1, 0].plot(t, rho_rod * PCM, label="rod")
    axes[1, 0].plot(t, rho_doppler * PCM, label="Doppler")
    axes[1, 0].plot(t, rho_mod * PCM, label="moderator")
    axes[1, 0].plot(t, rho_total * PCM, label="total", linewidth=2, color="k")
    axes[1, 0].set_title("Reactivity components [pcm]")
    axes[1, 0].set_xlabel("t [s]")
    axes[1, 0].set_ylabel("ρ [pcm]")
    axes[1, 0].legend()
    axes[1, 0].grid(True, alpha=0.3)

    for i, label in enumerate(["C1", "C2", "C3", "C4", "C5", "C6"]):
        axes[1, 1].semilogy(t, Cs[i], label=label)
    axes[1, 1].set_title("Delayed neutron precursors")
    axes[1, 1].set_xlabel("t [s]")
    axes[1, 1].set_ylabel("Cᵢ (relative)")
    axes[1, 1].legend(ncol=2, fontsize=8)
    axes[1, 1].grid(True, which="both", alpha=0.3)

    fig.suptitle("PointKineticsCore — default scenario")
    fig.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
