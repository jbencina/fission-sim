"""Standalone driver for the PointKineticsCore.

Drives the core on its own, through its public API, with the two upstream
inputs (rod reactivity and coolant temperature) supplied by plain Python
functions of time instead of the rod controller and primary loop. The
coolant stays at the core's reference temperature, so only Doppler
feedback acts; ``run_primary.py`` shows the core coupled to the full plant.

Default scenario:
    t = 0..10   : steady state at design power (every derivative is zero)
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
# Hand-coded input sources. In the coupled plant these come from the rod
# controller and the primary loop.
# ---------------------------------------------------------------------------
def rod_reactivity_fn(t: float) -> float:
    """Piecewise rod reactivity schedule [dimensionless]."""
    if t < 10.0:
        return 0.0
    if t < 60.0:
        return 200e-5  # +200 pcm step
    return -7000e-5  # scram


def T_cool_fn(t: float, params: CoreParams) -> float:
    """Constant coolant temperature [K], held at ``params.T_cool_ref``.

    ``T_cool_ref`` is the coolant temperature at which moderator reactivity
    is zero and the design heat balance closes, so holding the coolant there
    keeps the design initial state in equilibrium until the rod moves. Any
    other constant would add moderator reactivity at t = 0. Swap this for a
    first-order lag toward a new temperature to see moderator feedback.
    """
    return params.T_cool_ref


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
                "T_cool": T_cool_fn(t, params),
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
    T_cool = np.array([T_cool_fn(ti, params) for ti in t])
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
