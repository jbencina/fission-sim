"""Tests for src/fission_sim/physics/pressurizer.py.

Three layers (mirroring the rest of the physics package):
  Layer 1 — pure derivative + outputs/telemetry tests (no integration)
  Layer 2 — short-integration behavior tests
  Layer 3 — handled in tests/test_pressurizer_plant.py (full plant)
"""

import pytest

from fission_sim.physics import coolprop
from fission_sim.physics.pressurizer import Pressurizer, PressurizerParams, SaturationState, saturation_state
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


# ---------------------------------------------------------------------------
# Pressurizer: API surface
# ---------------------------------------------------------------------------
def test_state_layout_indices():
    pzr = Pressurizer(default_params())
    assert pzr.state_size == 2
    assert pzr.state_labels == ("M_pzr", "U_pzr")


def test_input_ports():
    pzr = Pressurizer(default_params())
    assert pzr.input_ports == (
        "power_thermal",
        "Q_sg",
        "T_hotleg",
        "T_coldleg",
        "Q_heater",
        "m_dot_spray",
    )


def test_output_ports():
    pzr = Pressurizer(default_params())
    assert pzr.output_ports == (
        "P",
        "level",
        "T_sat",
        "m_dot_surge",
        "subcooling_margin",
    )


def test_initial_state_shape_and_values():
    p = default_params()
    pzr = Pressurizer(p)
    s = pzr.initial_state()
    assert s.shape == (2,)
    assert s[0] == pytest.approx(p.M_pzr_initial)
    assert s[1] == pytest.approx(p.U_pzr_initial)


# ---------------------------------------------------------------------------
# Saturation closure helper
# ---------------------------------------------------------------------------
def test_saturation_state_at_design_round_trip():
    """Build (M, U) at design conditions, invert via saturation_state,
    recover P=P_design and level=0.5 to high precision."""
    p = default_params()
    s = saturation_state(M=p.M_pzr_initial, U=p.U_pzr_initial, V=p.V_pzr)
    assert isinstance(s, SaturationState)
    assert s.P == pytest.approx(p.P_design, rel=1e-3)
    assert s.level == pytest.approx(p.level_design, abs=1e-3)


def test_saturation_state_quality_in_unit_interval():
    """At design (level=0.5), the mass quality x is small — most mass
    is liquid. Sanity check 0 < x < 1.

    At 15.5 MPa the steam density is ~102 kg/m³ (near the critical point
    at 22.1 MPa, steam is dense). With level=0.5 and equal liquid/vapor
    volumes, x ≈ 0.146 — still predominantly liquid by mass (≈85 %).
    The threshold 0.20 gives headroom for parameter variation while
    asserting that the vessel is not steam-dominated.
    """
    p = default_params()
    s = saturation_state(M=p.M_pzr_initial, U=p.U_pzr_initial, V=p.V_pzr)
    assert 0.0 < s.x < 1.0
    assert s.x < 0.20  # mostly liquid by mass (x≈0.146 at design)


def test_saturation_state_M_decomposition_sums_to_M():
    """M_l + M_v = M_total."""
    p = default_params()
    s = saturation_state(M=p.M_pzr_initial, U=p.U_pzr_initial, V=p.V_pzr)
    assert s.M_l + s.M_v == pytest.approx(p.M_pzr_initial, rel=1e-9)


def test_saturation_state_T_sat_matches_P():
    """T_sat returned by closure agrees with CoolProp.T_sat(P)."""
    p = default_params()
    s = saturation_state(M=p.M_pzr_initial, U=p.U_pzr_initial, V=p.V_pzr)
    assert s.T_sat == pytest.approx(coolprop.T_sat(P=s.P), rel=1e-6)
