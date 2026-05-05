"""Tests for src/fission_sim/physics/core.py.

Three layers (per spec §5):
  Layer 1 — pure derivative tests (no integration)
  Layer 2 — short-integration behavior tests
  Layer 3 — inhour-equation analytical test
"""

import pytest

from fission_sim.physics.core import CoreParams, PointKineticsCore


# ---------------------------------------------------------------------------
# Shared fixture: canonical L1 parameter set used by every test.
# Tests that need altered parameters use dataclasses.replace() to override.
# ---------------------------------------------------------------------------
def default_params() -> CoreParams:
    """Return the project-wide default L1 parameter set."""
    return CoreParams()


# ---------------------------------------------------------------------------
# CoreParams construction and self-consistency
# ---------------------------------------------------------------------------
def test_core_params_defaults_are_consistent():
    p = default_params()
    # Six delayed groups, total beta ~0.0065 for U-235 thermal
    assert p.beta_i.shape == (6,)
    assert p.lambda_i.shape == (6,)
    assert abs(p.beta_i.sum() - 0.0065) < 1e-3
    # Derived hA_fc closes steady-state energy balance
    expected_hA = p.P_design / (p.T_fuel_ref - p.T_cool_ref)
    assert p.hA_fc == pytest.approx(expected_hA)
    # Feedback coefficients are negative (stable PWR)
    assert p.alpha_f < 0
    assert p.alpha_m < 0


# ---------------------------------------------------------------------------
# Layer 1: pure derivative tests (no integration)
# ---------------------------------------------------------------------------
def test_state_layout_indices():
    core = PointKineticsCore(default_params())
    assert core.state_size == 8
    assert core.state_labels == (
        "n",
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
        "T_fuel",
    )


def test_initial_state_is_design_steady_state():
    p = default_params()
    core = PointKineticsCore(p)
    s = core.initial_state()

    assert s.shape == (8,)
    # n = 1 (normalized to design power)
    assert s[0] == pytest.approx(1.0)
    # C_i steady state: C_i = beta_i / (Lambda * lambda_i) at n=1
    expected_C = p.beta_i / (p.Lambda * p.lambda_i)
    assert s[1:7] == pytest.approx(expected_C)
    # T_fuel at reference
    assert s[7] == pytest.approx(p.T_fuel_ref)
