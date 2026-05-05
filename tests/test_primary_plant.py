"""Coupled-system tests for the assembled primary plant (core + loop + SG + sink).

This file exercises all four components wired together. The wiring helper
``_assemble_plant`` is duplicated (in shape) by the matplotlib runner
``examples/run_primary.py`` and the text runner ``examples/report_primary.py``;
the duplication is intentional and accumulates the signal that the engine
should be extracted in slice 4.
"""

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from fission_sim.physics.core import CoreParams, PointKineticsCore
from fission_sim.physics.primary_loop import LoopParams, PrimaryLoop
from fission_sim.physics.secondary_sink import SecondarySink, SinkParams
from fission_sim.physics.steam_generator import SGParams, SteamGenerator


# ---------------------------------------------------------------------------
# Wiring: assemble all four components, build the global state vector, and
# return the f(t, y) glue function suitable for solve_ivp.
# ---------------------------------------------------------------------------
def _assemble_plant(rod_reactivity_fn):
    """Construct the four-component primary plant.

    Parameters
    ----------
    rod_reactivity_fn : Callable[[float], float]
        Function mapping simulated time t [s] to rod_reactivity [dimensionless].
        Hand-coded stand-in for the rod controller component (slice 3).

    Returns
    -------
    components : dict
        ``{"core", "loop", "sg", "sink"}`` mapping component name to instance.
    y0 : np.ndarray, shape (10,)
        Initial global state vector: core's 8 + loop's 2.
    f : Callable[[float, np.ndarray], np.ndarray]
        The derivative function for solve_ivp.
    """
    core = PointKineticsCore(CoreParams())
    loop = PrimaryLoop(LoopParams())
    sg = SteamGenerator(SGParams())
    sink = SecondarySink(SinkParams())

    y0 = np.concatenate([core.initial_state(), loop.initial_state()])

    def f(t, y):
        # Slice the global state vector
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

    return ({"core": core, "loop": loop, "sg": sg, "sink": sink}, y0, f)


# ---------------------------------------------------------------------------
# Coupled-system tests
# ---------------------------------------------------------------------------
def test_coupled_steady_state_holds():
    """All four components at design conditions: state should not drift over 60s."""
    components, y0, f = _assemble_plant(rod_reactivity_fn=lambda t: 0.0)
    sol = solve_ivp(
        f,
        (0.0, 60.0),
        y0,
        method="BDF",
        dense_output=True,
        rtol=1e-6,
        atol=1e-9,
        max_step=0.5,
    )
    assert sol.success
    # n stays at 1 (within solver tolerance)
    assert sol.y[0, -1] == pytest.approx(1.0, abs=1e-3)
    # Loop temps stay at reference
    p_loop = components["loop"].params
    assert sol.y[8, -1] == pytest.approx(p_loop.T_hot_ref, abs=0.05)
    assert sol.y[9, -1] == pytest.approx(p_loop.T_cold_ref, abs=0.05)


def test_coupled_doppler_plus_moderator_levels_off():
    """+200 pcm rod step: with both Doppler AND moderator feedback active, power
    should plateau lower than a hypothetical core-only run with constant T_cool."""
    components, y0, f = _assemble_plant(rod_reactivity_fn=lambda t: 200e-5)
    sol = solve_ivp(
        f,
        (0.0, 200.0),
        y0,
        method="BDF",
        dense_output=True,
        rtol=1e-6,
        atol=1e-9,
        max_step=0.5,
    )
    assert sol.success
    # Sample late: power has plateaued
    t_late = np.linspace(150.0, 200.0, 50)
    n_late = sol.sol(t_late)[0]
    rel_change = abs(n_late[-1] - n_late[0]) / n_late[0]
    assert rel_change < 0.05, "power not plateaued"

    # Loop's T_avg has risen — proves moderator feedback was active
    p_loop = components["loop"].params
    T_avg_final = (sol.y[8, -1] + sol.y[9, -1]) / 2
    assert T_avg_final > p_loop.T_avg_ref, "loop did not heat up; moderator inactive"

    # Power is bounded — no runaway
    assert n_late.max() < 100.0


def test_coupled_energy_balance_closes_at_steady():
    """At steady state with no rod movement, Q_core ≈ Q_sg within 0.1%.

    This is M1 success criterion #4 from .docs/design.md §4 ("energy balance
    closes: core power equals heat removed by SG to within solver tolerance"),
    made machine-checkable for the first time by this slice.
    """
    components, y0, f = _assemble_plant(rod_reactivity_fn=lambda t: 0.0)
    sol = solve_ivp(
        f,
        (0.0, 120.0),
        y0,
        method="BDF",
        dense_output=True,
        rtol=1e-7,
        atol=1e-10,
        max_step=0.5,
    )
    assert sol.success

    # Read final state
    s_core = sol.y[0:8, -1]
    s_loop = sol.y[8:10, -1]

    # Compute the two heat flows at the final state
    core = components["core"]
    loop = components["loop"]
    sg = components["sg"]
    sink = components["sink"]

    Q_core = core.outputs(s_core)["power_thermal"]
    out_loop = loop.outputs(s_loop)
    out_sink = sink.outputs(np.empty(0))
    Q_sg = sg.outputs(
        np.empty(0),
        inputs={
            "T_primary": out_loop["T_avg"],
            "T_secondary": out_sink["T_secondary"],
        },
    )["Q_sg"]

    rel_err = abs(Q_core - Q_sg) / Q_core
    assert rel_err < 1e-3, (
        f"Energy balance not closed: Q_core={Q_core:.4e} W, Q_sg={Q_sg:.4e} W (rel err {rel_err:.4%})"
    )
