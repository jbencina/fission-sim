"""Tests for src/fission_sim/physics/core.py.

Three layers (per spec §5):
  Layer 1 — pure derivative tests (no integration)
  Layer 2 — short-integration behavior tests
  Layer 3 — inhour-equation analytical test
"""

import numpy as np
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


def _design_inputs(p: CoreParams) -> dict:
    """Inputs that, with initial_state, yield zero derivatives."""
    return {"rod_reactivity": 0.0, "T_cool": p.T_cool_ref}


def test_design_steady_state_balances():
    p = default_params()
    core = PointKineticsCore(p)
    dstate = core.derivatives(core.initial_state(), _design_inputs(p))
    # At design steady state every derivative should be ~0
    assert np.allclose(dstate, 0.0, atol=1e-9)


def test_positive_reactivity_grows_n():
    p = default_params()
    core = PointKineticsCore(p)
    inputs = _design_inputs(p) | {"rod_reactivity": 100e-5}  # +100 pcm
    dstate = core.derivatives(core.initial_state(), inputs)
    assert dstate[0] > 0  # dn/dt > 0


def test_negative_reactivity_shrinks_n():
    p = default_params()
    core = PointKineticsCore(p)
    inputs = _design_inputs(p) | {"rod_reactivity": -100e-5}  # -100 pcm
    dstate = core.derivatives(core.initial_state(), inputs)
    assert dstate[0] < 0  # dn/dt < 0


def test_doppler_is_negative_feedback():
    p = default_params()
    core = PointKineticsCore(p)
    s = core.initial_state()
    s[7] = p.T_fuel_ref + 50.0  # raise fuel temperature 50 K
    inputs = _design_inputs(p)
    dstate = core.derivatives(s, inputs)
    # Higher fuel temp -> negative Doppler reactivity -> dn/dt should be
    # negative (assuming no other inputs change). With C_i still at the old
    # steady state, the reactivity drop dominates the precursor source.
    assert dstate[0] < 0


def test_outputs_returns_power_and_T_fuel():
    p = default_params()
    core = PointKineticsCore(p)
    s = core.initial_state()
    out = core.outputs(s)
    assert out["power_thermal"] == pytest.approx(p.P_design)  # n=1 at design
    assert out["T_fuel"] == pytest.approx(p.T_fuel_ref)


def test_outputs_scales_power_with_n():
    p = default_params()
    core = PointKineticsCore(p)
    s = core.initial_state()
    s[0] = 0.5  # half power
    s[7] = p.T_fuel_ref + 100.0  # also vary T_fuel away from reference
    out = core.outputs(s)
    assert out["power_thermal"] == pytest.approx(0.5 * p.P_design)
    assert out["T_fuel"] == pytest.approx(p.T_fuel_ref + 100.0)


def test_telemetry_with_inputs_decomposes_reactivity():
    p = default_params()
    core = PointKineticsCore(p)
    s = core.initial_state()
    s[7] = p.T_fuel_ref + 100.0  # raise T_fuel by 100 K
    inputs = {"rod_reactivity": 200e-5, "T_cool": p.T_cool_ref + 5.0}
    tele = core.telemetry(s, inputs)
    # All keys present
    expected_keys = {
        "power_thermal",
        "T_fuel",
        "n",
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
        "rho_total",
        "rho_rod",
        "rho_doppler",
        "rho_moderator",
    }
    assert set(tele.keys()) == expected_keys
    # Decomposition
    assert tele["rho_rod"] == pytest.approx(200e-5)
    assert tele["rho_doppler"] == pytest.approx(p.alpha_f * 100.0)
    assert tele["rho_moderator"] == pytest.approx(p.alpha_m * 5.0)
    assert tele["rho_total"] == pytest.approx(tele["rho_rod"] + tele["rho_doppler"] + tele["rho_moderator"])


def test_telemetry_without_inputs_reports_none_for_input_dependent_keys():
    p = default_params()
    core = PointKineticsCore(p)
    s = core.initial_state()
    tele = core.telemetry(s)
    # State-only keys still present
    assert tele["power_thermal"] == pytest.approx(p.P_design)
    assert tele["T_fuel"] == pytest.approx(p.T_fuel_ref)
    # Doppler is computable from state alone
    assert tele["rho_doppler"] == pytest.approx(0.0)
    # The input-dependent ones are None
    assert tele["rho_rod"] is None
    assert tele["rho_moderator"] is None
    assert tele["rho_total"] is None
