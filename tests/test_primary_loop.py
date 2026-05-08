"""Tests for src/fission_sim/physics/primary_loop.py.

Three layers (mirroring the core's test discipline):
  Layer 1 — pure derivative tests (no integration)
  Layer 2 — short-integration behavior tests
  Layer 3 — analytical comparison (energy balance closure at steady state)
"""

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from fission_sim.physics.primary_loop import LoopParams, PrimaryLoop


def default_params() -> LoopParams:
    """Return the project-wide default L1 loop parameter set."""
    return LoopParams()


def test_loop_params_defaults_are_consistent():
    p = default_params()
    # Reference temperatures derived to satisfy steady-state energy balance:
    # ΔT = Q_design / (m_dot * c_p), centered on T_avg_ref.
    expected_delta = p.Q_design / (p.m_dot * p.c_p)
    assert p.T_hot_ref - p.T_cold_ref == pytest.approx(expected_delta)
    assert (p.T_hot_ref + p.T_cold_ref) / 2 == pytest.approx(p.T_avg_ref)


def test_state_layout_indices():
    loop = PrimaryLoop(default_params())
    assert loop.state_size == 2
    assert loop.state_labels == ("T_hot", "T_cold")


def test_initial_state_is_design_steady_state():
    p = default_params()
    loop = PrimaryLoop(p)
    s = loop.initial_state()
    assert s.shape == (2,)
    assert s[0] == pytest.approx(p.T_hot_ref)
    assert s[1] == pytest.approx(p.T_cold_ref)


# ---------------------------------------------------------------------------
# Layer 1: pure derivative tests (no integration)
# ---------------------------------------------------------------------------
def _design_inputs(p: LoopParams) -> dict:
    """Inputs that, with initial_state, yield zero derivatives."""
    return {"power_thermal": p.Q_design, "Q_sg": p.Q_design}


def test_design_steady_state_balances():
    p = default_params()
    loop = PrimaryLoop(p)
    dstate = loop.derivatives(loop.initial_state(), _design_inputs(p))
    # Both leg derivatives should be ~0 at the design point.
    assert np.allclose(dstate, 0.0, atol=1e-6)


def test_more_q_core_heats_hot_leg():
    """Q_core > Q_flow at design state should produce dT_hot/dt > 0."""
    p = default_params()
    loop = PrimaryLoop(p)
    inputs = _design_inputs(p) | {"power_thermal": 1.1 * p.Q_design}
    dstate = loop.derivatives(loop.initial_state(), inputs)
    assert dstate[0] > 0  # dT_hot/dt > 0


def test_more_q_sg_cools_cold_leg():
    """Q_sg > Q_flow at design state should produce dT_cold/dt < 0."""
    p = default_params()
    loop = PrimaryLoop(p)
    inputs = _design_inputs(p) | {"Q_sg": 1.1 * p.Q_design}
    dstate = loop.derivatives(loop.initial_state(), inputs)
    assert dstate[1] < 0  # dT_cold/dt < 0


# ---------------------------------------------------------------------------
# Layer 2+: outputs and telemetry
# ---------------------------------------------------------------------------
def test_outputs_at_design_state():
    p = default_params()
    loop = PrimaryLoop(p)
    out = loop.outputs(loop.initial_state())
    assert out["T_hot"] == pytest.approx(p.T_hot_ref)
    assert out["T_cold"] == pytest.approx(p.T_cold_ref)
    assert out["T_avg"] == pytest.approx(p.T_avg_ref)
    assert out["T_cool"] == pytest.approx(p.T_avg_ref)  # T_cool == T_avg at L1


def test_outputs_t_avg_and_t_cool_track_state():
    """T_avg and T_cool should follow the actual state, not just defaults."""
    p = default_params()
    loop = PrimaryLoop(p)
    s = np.array([600.0, 570.0])
    out = loop.outputs(s)
    assert out["T_hot"] == pytest.approx(600.0)
    assert out["T_cold"] == pytest.approx(570.0)
    assert out["T_avg"] == pytest.approx(585.0)
    assert out["T_cool"] == pytest.approx(585.0)


def test_telemetry_includes_delta_t_and_q_flow():
    p = default_params()
    loop = PrimaryLoop(p)
    s = np.array([600.0, 570.0])
    inputs = {"power_thermal": 2.5e9, "Q_sg": 2.5e9}
    tele = loop.telemetry(s, inputs)
    expected_keys = {
        "T_hot",
        "T_cold",
        "T_avg",
        "T_cool",
        "delta_T",
        "Tref",
        "power_thermal",
        "Q_sg",
        "Q_flow",
    }
    assert set(tele.keys()) == expected_keys
    assert tele["Tref"] == pytest.approx(p.T_avg_ref)
    assert tele["delta_T"] == pytest.approx(30.0)
    assert tele["Q_flow"] == pytest.approx(p.m_dot * p.c_p * 30.0)
    assert tele["power_thermal"] == pytest.approx(2.5e9)
    assert tele["Q_sg"] == pytest.approx(2.5e9)


def test_telemetry_without_inputs_reports_none_for_input_keys():
    p = default_params()
    loop = PrimaryLoop(p)
    tele = loop.telemetry(loop.initial_state())
    # State-derived keys still present
    assert tele["T_hot"] == pytest.approx(p.T_hot_ref)
    assert tele["delta_T"] == pytest.approx(p.T_hot_ref - p.T_cold_ref)
    # Q_flow is computable from state alone
    assert tele["Q_flow"] is not None
    # Input-dependent keys are None
    assert tele["power_thermal"] is None
    assert tele["Q_sg"] is None


# ---------------------------------------------------------------------------
# Layer 2: short-integration behavior tests
# ---------------------------------------------------------------------------
def _integrate(loop, q_core_fn, q_sg_fn, t_end, t_start=0.0, max_step=0.5):
    """Integrate the loop from initial_state under input functions of t."""

    def f(t, y):
        return loop.derivatives(
            y,
            {
                "power_thermal": q_core_fn(t),
                "Q_sg": q_sg_fn(t),
            },
        )

    return solve_ivp(
        f,
        (t_start, t_end),
        loop.initial_state(),
        method="BDF",
        dense_output=True,
        rtol=1e-6,
        atol=1e-9,
        max_step=max_step,
    )


def test_loop_steady_holds_60s():
    """Constant Q_core = Q_sg = Q_design should hold both temps at reference."""
    p = default_params()
    loop = PrimaryLoop(p)
    sol = _integrate(
        loop,
        q_core_fn=lambda t: p.Q_design,
        q_sg_fn=lambda t: p.Q_design,
        t_end=60.0,
    )
    assert sol.success
    assert sol.y[0, -1] == pytest.approx(p.T_hot_ref, abs=0.01)
    assert sol.y[1, -1] == pytest.approx(p.T_cold_ref, abs=0.01)


def test_loop_responds_to_q_core_step():
    """+10% Q_core with Q_sg held at design has NO total-energy equilibrium —
    heat accumulates indefinitely so T_avg grows linearly with time. However,
    the temperature DIFFERENCE ΔT = T_hot − T_cold does settle to an
    analytically predictable steady value, derived from setting d(ΔT)/dt = 0:

        ΔT_asymptotic = (Q_core + Q_sg) / (2 · ṁ · c_p)

    This test verifies both behaviors: temps rise (heat accumulating), and the
    asymptotic ΔT matches the analytical prediction within 1%. Catches sign
    errors in either leg's energy balance that the design-state test misses.
    """
    p = default_params()
    loop = PrimaryLoop(p)
    Q_high = 1.1 * p.Q_design
    sol = _integrate(
        loop,
        q_core_fn=lambda t: Q_high,
        q_sg_fn=lambda t: p.Q_design,
        t_end=600.0,  # long enough for the ΔT mode to settle
    )
    assert sol.success
    T_hot_final = sol.y[0, -1]
    T_cold_final = sol.y[1, -1]
    # Both temps rise above reference (heat accumulating, no total equilibrium)
    assert T_hot_final > p.T_hot_ref
    assert T_cold_final > p.T_cold_ref
    # Both finite (didn't run away to infinity)
    assert np.isfinite(T_hot_final)
    assert np.isfinite(T_cold_final)
    # ΔT mode HAS settled to the analytical prediction
    measured_delta_T = T_hot_final - T_cold_final
    expected_delta_T = (Q_high + p.Q_design) / (2 * p.m_dot * p.c_p)
    rel_err = abs(measured_delta_T - expected_delta_T) / expected_delta_T
    assert rel_err < 0.01, (
        f"Asymptotic ΔT {measured_delta_T:.4f} K vs analytical {expected_delta_T:.4f} K (rel error {rel_err:.4%})"
    )


# ---------------------------------------------------------------------------
# Layer 3: analytical comparison — energy balance closure at steady state
# ---------------------------------------------------------------------------
def test_loop_energy_balance_at_steady_70pct():
    """At any steady state with Q_core == Q_sg, the achieved ΔT must equal
    Q / (m_dot * c_p) within numerical tolerance.

    This is the analytical-comparison test for the loop: the closed-form
    expression ΔT = Q / (ṁ · c_p) follows directly from setting both
    derivatives to zero. Drive the loop with Q at 70 % of design, integrate
    to steady state, verify the achieved ΔT matches the formula within 1 %.
    """
    p = default_params()
    loop = PrimaryLoop(p)
    Q = 0.70 * p.Q_design
    sol = _integrate(
        loop,
        q_core_fn=lambda t: Q,
        q_sg_fn=lambda t: Q,
        t_end=2000.0,  # large thermal mass, slow approach to equilibrium
        max_step=5.0,  # smooth integration; no discontinuities
    )
    assert sol.success
    # Verify steady state: derivatives near zero at the end
    final_state = sol.y[:, -1]
    final_inputs = {"power_thermal": Q, "Q_sg": Q}
    final_dstate = loop.derivatives(final_state, final_inputs)
    assert np.allclose(final_dstate, 0.0, atol=1e-3)
    # Now check the analytical prediction
    measured_delta_T = sol.y[0, -1] - sol.y[1, -1]
    expected_delta_T = Q / (p.m_dot * p.c_p)
    rel_err = abs(measured_delta_T - expected_delta_T) / expected_delta_T
    assert rel_err < 0.01, (
        f"Measured ΔT {measured_delta_T:.4f} K vs analytical {expected_delta_T:.4f} K (rel error {rel_err:.4%})"
    )
