"""Tests for src/fission_sim/physics/primary_loop.py.

Three layers (mirroring the core's test discipline):
  Layer 1 — pure derivative tests (no integration)
  Layer 2 — short-integration behavior tests
  Layer 3 — analytical comparison (energy balance closure at steady state)
"""

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
