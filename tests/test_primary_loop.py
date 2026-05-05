"""Tests for src/fission_sim/physics/primary_loop.py.

Three layers (mirroring the core's test discipline):
  Layer 1 — pure derivative tests (no integration)
  Layer 2 — short-integration behavior tests
  Layer 3 — analytical comparison (energy balance closure at steady state)
"""

import numpy as np
import pytest

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
    return {"Q_core": p.Q_design, "Q_sg": p.Q_design}


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
    inputs = _design_inputs(p) | {"Q_core": 1.1 * p.Q_design}
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
    inputs = {"Q_core": 2.5e9, "Q_sg": 2.5e9}
    tele = loop.telemetry(s, inputs)
    expected_keys = {
        "T_hot",
        "T_cold",
        "T_avg",
        "T_cool",
        "delta_T",
        "Q_core",
        "Q_sg",
        "Q_flow",
    }
    assert set(tele.keys()) == expected_keys
    assert tele["delta_T"] == pytest.approx(30.0)
    assert tele["Q_flow"] == pytest.approx(p.m_dot * p.c_p * 30.0)
    assert tele["Q_core"] == pytest.approx(2.5e9)
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
    assert tele["Q_core"] is None
    assert tele["Q_sg"] is None
