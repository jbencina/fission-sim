"""Coupled-system tests for the assembled primary plant.

Exercises all five components wired together: core + loop + SG + sink + rod
controller. The wiring helper ``_assemble_plant`` is duplicated (in shape)
by the matplotlib runner ``examples/run_primary.py``, the text runner
``examples/report_primary.py``, and ``examples/dump_state.py``. The
duplication is intentional and accumulates the signal that the engine
should be extracted in slice 4.
"""

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from fission_sim.physics.core import CoreParams, PointKineticsCore
from fission_sim.physics.primary_loop import LoopParams, PrimaryLoop
from fission_sim.physics.rod_controller import RodController, RodParams
from fission_sim.physics.secondary_sink import SecondarySink, SinkParams
from fission_sim.physics.steam_generator import SGParams, SteamGenerator


# ---------------------------------------------------------------------------
# Wiring: assemble all five components, build the global state vector, and
# return the f(t, y) glue function suitable for solve_ivp.
# ---------------------------------------------------------------------------
def _assemble_plant(rod_command_fn, scram_fn):
    """Construct the five-component primary plant.

    Parameters
    ----------
    rod_command_fn : Callable[[float], float]
        Function mapping simulated time t [s] to operator's rod_command
        setpoint [dimensionless, 0–1].
    scram_fn : Callable[[float], bool]
        Function mapping simulated time t [s] to operator's scram flag.

    Returns
    -------
    components : dict
        Maps name to instance: ``{"core", "loop", "sg", "sink", "rod"}``.
    y0 : np.ndarray, shape (11,)
        Initial global state vector: core's 8 + loop's 2 + rod's 1.
    f : Callable[[float, np.ndarray], np.ndarray]
        The derivative function for solve_ivp.
    """
    core = PointKineticsCore(CoreParams())
    loop = PrimaryLoop(LoopParams())
    sg = SteamGenerator(SGParams())
    sink = SecondarySink(SinkParams())
    rod = RodController(RodParams())

    y0 = np.concatenate([core.initial_state(), loop.initial_state(), rod.initial_state()])

    def f(t, y):
        # Slice the global state vector
        s_core = y[0:8]
        s_loop = y[8:10]
        s_rod = y[10:11]

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
        out_rod = rod.outputs(s_rod)

        # Compute derivatives, threading outputs through inputs
        dy = np.empty_like(y)
        dy[0:8] = core.derivatives(
            s_core,
            inputs={
                "rho_rod": out_rod["rho_rod"],
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

    return ({"core": core, "loop": loop, "sg": sg, "sink": sink, "rod": rod}, y0, f)


# ---------------------------------------------------------------------------
# Coupled-system tests
# ---------------------------------------------------------------------------
def test_coupled_steady_state_holds():
    """All five components at design conditions: state should not drift over 60s."""
    components, y0, f = _assemble_plant(
        rod_command_fn=lambda t: 0.5,  # at design position
        scram_fn=lambda t: False,
    )
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
    # n stays at 1
    assert sol.y[0, -1] == pytest.approx(1.0, abs=1e-3)
    # Loop temps stay at reference
    p_loop = components["loop"].params
    assert sol.y[8, -1] == pytest.approx(p_loop.T_hot_ref, abs=0.05)
    assert sol.y[9, -1] == pytest.approx(p_loop.T_cold_ref, abs=0.05)
    # Rod stays at design position
    p_rod = components["rod"].params
    assert sol.y[10, -1] == pytest.approx(p_rod.rod_position_design, abs=1e-4)


def test_coupled_doppler_plus_moderator_levels_off():
    """Withdraw rod by 0.015 (=+210 pcm step) at t=10 s. Power should plateau,
    loop should heat up, both Doppler and moderator feedback should be active."""
    p_rod = RodParams()
    components, y0, f = _assemble_plant(
        rod_command_fn=lambda t: p_rod.rod_position_design + (0.015 if t >= 10.0 else 0.0),
        scram_fn=lambda t: False,
    )
    # +5 s relative to slice 2 to allow the ~1.5 s rod-motion delay before Doppler kicks in
    sol = solve_ivp(
        f,
        (0.0, 205.0),
        y0,
        method="BDF",
        dense_output=True,
        rtol=1e-6,
        atol=1e-9,
        max_step=0.5,
    )
    assert sol.success
    # Sample late: power has plateaued
    t_late = np.linspace(155.0, 205.0, 50)
    n_late = sol.sol(t_late)[0]
    rel_change = abs(n_late[-1] - n_late[0]) / n_late[0]
    assert rel_change < 0.05, "power not plateaued"
    # Loop's T_avg has risen
    p_loop = components["loop"].params
    T_avg_final = (sol.y[8, -1] + sol.y[9, -1]) / 2
    assert T_avg_final > p_loop.T_avg_ref, "loop did not heat up"
    # Power is bounded
    assert n_late.max() < 100.0


def test_coupled_energy_balance_closes_at_steady():
    """At steady state with no rod movement, Q_core ≈ Q_sg within 0.1%.

    This is M1 success criterion #4 from .docs/design.md §4.
    """
    components, y0, f = _assemble_plant(
        rod_command_fn=lambda t: 0.5,
        scram_fn=lambda t: False,
    )
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

    s_core = sol.y[0:8, -1]
    s_loop = sol.y[8:10, -1]

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


def test_coupled_scram_drops_power_with_rod_motion():
    """Hold steady to t=10, then scram. Power should drop dramatically as rods
    insert (rod motion takes ~1 s), then continue to fall via the delayed-neutron
    tail. Verifies the genuine scram-via-rod-motion coupling end to end."""
    components, y0, f = _assemble_plant(
        rod_command_fn=lambda t: 0.5,
        scram_fn=lambda t: t >= 10.0,
    )
    sol = solve_ivp(
        f,
        (0.0, 60.0),
        y0,
        method="BDF",
        dense_output=True,
        rtol=1e-6,
        atol=1e-9,
        max_step=0.1,  # tighter for the scram transient
    )
    assert sol.success
    # Pre-scram: holding steady at n=1
    n_pre = sol.sol(9.0)[0]
    assert n_pre == pytest.approx(1.0, abs=1e-3)
    # Post-scram + rod insertion + prompt drop: by t=15s (5 s after scram),
    # rods have fully inserted and the prompt drop is well under way.
    n_post = sol.sol(15.0)[0]
    assert n_post < 0.15, f"power didn't drop: n(15) = {n_post:.4f}"
    # Late: delayed-neutron tail still nonzero
    n_late = sol.sol(60.0)[0]
    assert n_late > 1e-4, f"delayed-neutron tail vanished too fast: n(60) = {n_late:.4e}"
    # Verify rod actually moved (not just power dropped from feedback)
    rod_pos_final = sol.y[10, -1]
    assert rod_pos_final < 0.05, f"rod did not fully insert: rod_position(60) = {rod_pos_final:.4f}"
