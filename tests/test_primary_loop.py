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
