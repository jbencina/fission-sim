"""Tests for src/fission_sim/physics/pressurizer.py.

Three layers (mirroring the rest of the physics package):
  Layer 1 — pure derivative + outputs/telemetry tests (no integration)
  Layer 2 — short-integration behavior tests
  Layer 3 — handled in tests/test_pressurizer_plant.py (full plant)
"""

import pytest

from fission_sim.physics import coolprop
from fission_sim.physics.pressurizer import Pressurizer, PressurizerParams  # noqa: F401
from fission_sim.physics.primary_loop import LoopParams


def default_params() -> PressurizerParams:
    """Return the project-wide default L1 pressurizer parameter set."""
    return PressurizerParams()


# ---------------------------------------------------------------------------
# PressurizerParams: defaults and derived initial state
# ---------------------------------------------------------------------------
def test_pzr_params_defaults_have_loop_params():
    """PressurizerParams composes a LoopParams default for surge math."""
    p = default_params()
    assert isinstance(p.loop_params, LoopParams)


def test_pzr_params_derived_initial_state_matches_design():
    """M_pzr_initial and U_pzr_initial are derived from
    (P_design, level_design, V_pzr) via the saturation closure."""
    p = default_params()
    rho_l = coolprop.sat_liquid_density(P=p.P_design)
    rho_v = coolprop.sat_vapor_density(P=p.P_design)
    u_l = coolprop.sat_liquid_internal_energy(P=p.P_design)
    u_v = coolprop.sat_vapor_internal_energy(P=p.P_design)
    V_l = p.level_design * p.V_pzr
    V_v = p.V_pzr - V_l
    M_l = V_l * rho_l
    M_v = V_v * rho_v
    expected_M = M_l + M_v
    expected_U = M_l * u_l + M_v * u_v
    assert p.M_pzr_initial == pytest.approx(expected_M, rel=1e-9)
    assert p.U_pzr_initial == pytest.approx(expected_U, rel=1e-9)


def test_pzr_params_explicit_initial_state_overrides_derived():
    """Passing M_pzr_initial / U_pzr_initial bypasses the derivation."""
    p = PressurizerParams(M_pzr_initial=10000.0, U_pzr_initial=2.0e10)
    assert p.M_pzr_initial == 10000.0
    assert p.U_pzr_initial == 2.0e10
