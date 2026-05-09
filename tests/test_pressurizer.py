"""Tests for src/fission_sim/physics/pressurizer.py.

Three layers (mirroring the rest of the physics package):
  Layer 1 — pure derivative + outputs/telemetry tests (no integration)
  Layer 2 — short-integration behavior tests
  Layer 3 — handled in tests/test_pressurizer_plant.py (full plant)
"""

import numpy as np
import pytest
from scipy.integrate import solve_ivp

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
    assert pzr.output_ports == ("P", "level", "T_sat")


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



# ---------------------------------------------------------------------------
# Layer 1: derivatives — pure (no integration)
# ---------------------------------------------------------------------------
def _design_inputs(p: PressurizerParams) -> dict:
    """Inputs at the coupled-plant design point: Q_core = Q_sg = Q_design,
    T_hot/T_cold at loop refs, no heater, no spray, no surge."""
    lp = p.loop_params
    return {
        "power_thermal": lp.Q_design,
        "Q_sg": lp.Q_design,
        "T_hotleg": lp.T_hot_ref,
        "T_coldleg": lp.T_cold_ref,
        "Q_heater": 0.0,
        "m_dot_spray": 0.0,
    }


def test_design_steady_state_balances():
    """At design conditions with Q_core = Q_sg, dT_avg/dt = 0, so
    ṁ_surge = 0; with no spray, dM/dt and dU/dt should both be zero."""
    p = default_params()
    pzr = Pressurizer(p)
    dstate = pzr.derivatives(pzr.initial_state(), _design_inputs(p))
    assert np.allclose(dstate, 0.0, atol=1e-3)


def test_heater_only_raises_internal_energy():
    """With Q_heater > 0 and everything else zero, dU/dt = Q_heater."""
    p = default_params()
    pzr = Pressurizer(p)
    inputs = _design_inputs(p) | {"Q_heater": 1.0e6}
    dstate = pzr.derivatives(pzr.initial_state(), inputs)
    assert dstate[0] == pytest.approx(0.0, abs=1e-3)
    assert dstate[1] == pytest.approx(1.0e6, rel=1e-6)


def test_spray_raises_mass_and_lowers_internal_energy_relative_to_pure_insurge():
    """Spray adds cooler-than-saturation water → dM/dt > 0 and the energy
    addition rate is at h_coldleg per kg (well below saturation)."""
    p = default_params()
    pzr = Pressurizer(p)
    m_spray = 5.0
    inputs = _design_inputs(p) | {"m_dot_spray": m_spray}
    dstate = pzr.derivatives(pzr.initial_state(), inputs)
    assert dstate[0] == pytest.approx(m_spray, rel=1e-6)
    h_cold = coolprop.enthalpy_PT(P=p.P_design, T=p.loop_params.T_cold_ref)
    assert dstate[1] == pytest.approx(m_spray * h_cold, rel=1e-6)


def test_insurge_uses_hotleg_density():
    """Force a positive surge_volume_rate via raising power_thermal above
    Q_sg. The resulting m_dot_surge should equal ρ_hotleg · surge_vol_rate."""
    p = default_params()
    pzr = Pressurizer(p)
    lp = p.loop_params
    inputs = _design_inputs(p) | {"power_thermal": 1.01 * lp.Q_design}
    state0 = pzr.initial_state()
    dstate = pzr.derivatives(state0, inputs)
    dT_avg_dt = (1.01 * lp.Q_design - lp.Q_design) / ((lp.M_hot + lp.M_cold) * lp.c_p)
    surge_vol_rate = lp.beta_T_primary * lp.V_loop * dT_avg_dt
    rho_hotleg = coolprop.density_PT(P=p.P_design, T=lp.T_hot_ref)
    expected_m_dot_surge = rho_hotleg * surge_vol_rate
    assert dstate[0] == pytest.approx(expected_m_dot_surge, rel=5e-3)


def test_outsurge_uses_saturated_liquid_density():
    """Force negative surge_volume_rate via lowering power_thermal below
    Q_sg. The resulting m_dot_surge should equal ρ_l_sat · surge_vol_rate."""
    p = default_params()
    pzr = Pressurizer(p)
    lp = p.loop_params
    inputs = _design_inputs(p) | {"power_thermal": 0.99 * lp.Q_design}
    state0 = pzr.initial_state()
    dstate = pzr.derivatives(state0, inputs)
    dT_avg_dt = (0.99 * lp.Q_design - lp.Q_design) / ((lp.M_hot + lp.M_cold) * lp.c_p)
    surge_vol_rate = lp.beta_T_primary * lp.V_loop * dT_avg_dt
    rho_l_sat = coolprop.sat_liquid_density(P=p.P_design)
    expected_m_dot_surge = rho_l_sat * surge_vol_rate
    assert dstate[0] == pytest.approx(expected_m_dot_surge, rel=5e-3)
    rho_hotleg = coolprop.density_PT(P=p.P_design, T=lp.T_hot_ref)
    wrong_m_dot_surge = rho_hotleg * surge_vol_rate
    assert dstate[0] != pytest.approx(wrong_m_dot_surge, rel=1e-3)


# ---------------------------------------------------------------------------
# Layer 1: outputs() and telemetry()
# ---------------------------------------------------------------------------
def test_outputs_at_design_returns_design_pressure_and_level():
    """outputs() returns only the three state-derived ports: P, level, T_sat.

    m_dot_surge and subcooling_margin are no longer output ports — they
    require inputs unavailable in the state-derived engine pass and are
    now telemetry-only.
    """
    p = default_params()
    pzr = Pressurizer(p)
    out = pzr.outputs(pzr.initial_state())
    assert set(out.keys()) == {"P", "level", "T_sat"}
    assert out["P"] == pytest.approx(p.P_design, rel=1e-3)
    assert out["level"] == pytest.approx(p.level_design, abs=1e-3)


def test_telemetry_subcooling_margin_is_T_sat_minus_T_hotleg():
    """subcooling_margin is available in telemetry() when inputs are provided."""
    p = default_params()
    pzr = Pressurizer(p)
    tele = pzr.telemetry(pzr.initial_state(), inputs=_design_inputs(p))
    T_sat = tele["T_sat"]
    expected = T_sat - p.loop_params.T_hot_ref
    assert tele["subcooling_margin"] == pytest.approx(expected, rel=1e-9)
    assert tele["subcooling_margin"] > 0


def test_telemetry_m_dot_surge_zero_at_design():
    """m_dot_surge is available in telemetry() and is zero at the design point
    (Q_core = Q_sg → dT_avg/dt = 0 → no volumetric expansion)."""
    p = default_params()
    pzr = Pressurizer(p)
    tele = pzr.telemetry(pzr.initial_state(), inputs=_design_inputs(p))
    assert tele["m_dot_surge"] == pytest.approx(0.0, abs=1e-3)


def test_outputs_state_derived_classification():
    """Pressurizer is a "state-derived" module — outputs(state) without inputs
    must succeed so the engine can break the algebraic loop between
    the pressurizer (needs controller outputs for *derivatives*) and the
    controller (needs pressurizer P for its outputs).

    outputs() returns only the three state-derived ports: P, level, T_sat.
    m_dot_surge and subcooling_margin are telemetry-only (require inputs).
    """
    pzr = Pressurizer(default_params())
    out = pzr.outputs(pzr.initial_state())
    assert "P" in out
    assert "level" in out
    assert "T_sat" in out
    assert set(out.keys()) == {"P", "level", "T_sat"}


def test_telemetry_includes_heater_on_and_spray_open():
    p = default_params()
    pzr = Pressurizer(p)
    inputs = _design_inputs(p) | {"Q_heater": 0.6 * 1.8e6, "m_dot_spray": 5.0}
    tele = pzr.telemetry(pzr.initial_state(), inputs=inputs)
    assert "heater_on" in tele
    assert "spray_open" in tele
    assert tele["heater_on"] is True
    assert tele["spray_open"] is True


def test_telemetry_heater_on_false_below_threshold():
    p = default_params()
    pzr = Pressurizer(p)
    inputs = _design_inputs(p) | {"Q_heater": 0.4 * 1.8e6, "m_dot_spray": 0.0}
    tele = pzr.telemetry(pzr.initial_state(), inputs=inputs)
    assert tele["heater_on"] is False
    assert tele["spray_open"] is False


def test_telemetry_without_inputs_returns_state_only_keys():
    p = default_params()
    pzr = Pressurizer(p)
    tele = pzr.telemetry(pzr.initial_state())
    assert "P" in tele
    assert "level" in tele
    assert "T_sat" in tele
    assert tele.get("m_dot_surge") is None
    assert tele.get("subcooling_margin") is None
    assert tele.get("heater_on") is None
    assert tele.get("spray_open") is None


# ---------------------------------------------------------------------------
# Layer 2: short-integration behavior tests
#
# These integrate the pressurizer alone with synthesized inputs that mimic
# the surrounding plant. Useful for confirming sign and order-of-magnitude
# behavior in isolation before plugging into the full plant.
# ---------------------------------------------------------------------------
def _integrate_pressurizer(pzr, inputs_fn, t_end, t_start=0.0, max_step=0.5):
    """Drive Pressurizer.derivatives under a time-varying inputs function."""
    def f(t, y):
        return pzr.derivatives(y, inputs_fn(t))
    return solve_ivp(
        f,
        (t_start, t_end),
        pzr.initial_state(),
        method="BDF",
        dense_output=True,
        rtol=1e-7,
        atol=1e-3,
        max_step=max_step,
    )


def test_steady_insurge_ramp_raises_pressure():
    """A constant +1% power excess for 30 s drives steady insurge;
    pressure should rise monotonically."""
    p = default_params()
    pzr = Pressurizer(p)
    lp = p.loop_params
    inputs_const = {
        "power_thermal": 1.01 * lp.Q_design,
        "Q_sg": lp.Q_design,
        "T_hotleg": lp.T_hot_ref,
        "T_coldleg": lp.T_cold_ref,
        "Q_heater": 0.0,
        "m_dot_spray": 0.0,
    }
    sol = _integrate_pressurizer(pzr, lambda t: inputs_const, t_end=30.0)
    assert sol.success
    P0 = pzr.outputs(sol.y[:, 0], inputs=inputs_const)["P"]
    P_end = pzr.outputs(sol.y[:, -1], inputs=inputs_const)["P"]
    assert P_end > P0


def test_steady_outsurge_ramp_lowers_pressure():
    """A constant −1% power deficit for 30 s drives steady outsurge;
    pressure should fall monotonically."""
    p = default_params()
    pzr = Pressurizer(p)
    lp = p.loop_params
    inputs_const = {
        "power_thermal": 0.99 * lp.Q_design,
        "Q_sg": lp.Q_design,
        "T_hotleg": lp.T_hot_ref,
        "T_coldleg": lp.T_cold_ref,
        "Q_heater": 0.0,
        "m_dot_spray": 0.0,
    }
    sol = _integrate_pressurizer(pzr, lambda t: inputs_const, t_end=30.0)
    assert sol.success
    P0 = pzr.outputs(sol.y[:, 0], inputs=inputs_const)["P"]
    P_end = pzr.outputs(sol.y[:, -1], inputs=inputs_const)["P"]
    assert P_end < P0


def test_heater_step_raises_pressure():
    """Holding Q_heater at 1.8 MW for 30 s with no surge or spray
    should raise pressure measurably."""
    p = default_params()
    pzr = Pressurizer(p)
    lp = p.loop_params
    inputs_const = {
        "power_thermal": lp.Q_design,
        "Q_sg": lp.Q_design,
        "T_hotleg": lp.T_hot_ref,
        "T_coldleg": lp.T_cold_ref,
        "Q_heater": 1.8e6,
        "m_dot_spray": 0.0,
    }
    sol = _integrate_pressurizer(pzr, lambda t: inputs_const, t_end=30.0)
    assert sol.success
    P0 = pzr.outputs(sol.y[:, 0], inputs=inputs_const)["P"]
    P_end = pzr.outputs(sol.y[:, -1], inputs=inputs_const)["P"]
    assert P_end > P0
    assert (P_end - P0) > 1.0e3
    assert (P_end - P0) < 5.0e5


def test_spray_step_lowers_pressure():
    """Holding m_dot_spray at 25 kg/s for 30 s with no surge or heaters
    should lower pressure (cold spray condenses steam)."""
    p = default_params()
    pzr = Pressurizer(p)
    lp = p.loop_params
    inputs_const = {
        "power_thermal": lp.Q_design,
        "Q_sg": lp.Q_design,
        "T_hotleg": lp.T_hot_ref,
        "T_coldleg": lp.T_cold_ref,
        "Q_heater": 0.0,
        "m_dot_spray": 25.0,
    }
    sol = _integrate_pressurizer(pzr, lambda t: inputs_const, t_end=30.0)
    assert sol.success
    P0 = pzr.outputs(sol.y[:, 0], inputs=inputs_const)["P"]
    P_end = pzr.outputs(sol.y[:, -1], inputs=inputs_const)["P"]
    assert P_end < P0
