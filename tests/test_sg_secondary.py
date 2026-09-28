import pytest

from fission_sim.physics import coolprop
from fission_sim.physics.sg_secondary import SGSecondary, SGSecondaryParams


def design_inputs(p: SGSecondaryParams) -> dict:
    """Balanced flows at the design point: no net mass or energy change."""
    return {
        "Q_sg": p.Q_design,
        "m_steam": p.m_steam_design,
        "m_dump": 0.0,
        "m_fw": p.m_steam_design,
    }


def test_params_derive_design_point():
    p = SGSecondaryParams()
    assert abs(p.P_ref - 6.899e6) < 5e3
    assert 1600.0 < p.m_steam_design < 1750.0  # 3.0 GW / (2773.9 - 976.4) kJ/kg
    assert p.M_sec_initial > 2.0e5  # ~222 t water + ~11 t steam


def test_state_layout():
    sgs = SGSecondary(SGSecondaryParams())
    assert sgs.state_size == 2
    assert sgs.state_labels == ("M_sec", "U_sec")
    assert sgs.input_ports == ("Q_sg", "m_steam", "m_dump", "m_fw")
    assert sgs.output_ports == ("P_steam", "T_secondary", "level_sg")
    assert sgs.outputs_require_inputs is False


def test_initial_state_is_design_point():
    p = SGSecondaryParams()
    sgs = SGSecondary(p)
    out = sgs.outputs(sgs.initial_state())
    assert abs(out["P_steam"] - p.P_ref) < 1.0  # Pa
    assert abs(out["T_secondary"] - p.T_sec_ref) < 1e-4
    assert abs(out["level_sg"] - p.level_ref) < 1e-9


def test_design_flows_give_zero_derivatives():
    p = SGSecondaryParams()
    sgs = SGSecondary(p)
    d = sgs.derivatives(sgs.initial_state(), design_inputs(p))
    assert abs(d[0]) < 1e-9  # dM/dt exactly zero
    assert abs(d[1]) < 1e-6 * p.Q_design  # dU/dt within 1 ppm of the heat flow


def test_nondefault_volume_derives_exact_design_point():
    p = SGSecondaryParams(V_sec=6.0e7)
    sgs = SGSecondary(p)
    out = sgs.outputs(sgs.initial_state())
    d = sgs.derivatives(sgs.initial_state(), design_inputs(p))
    assert abs(out["P_steam"] - p.P_ref) < 1.0
    assert abs(out["T_secondary"] - p.T_sec_ref) < 1e-4
    assert abs(out["level_sg"] - p.level_ref) < 1e-9
    assert abs(d[0]) < 1e-9
    assert abs(d[1]) < 1e-6 * p.Q_design


def test_less_steam_out_raises_pressure():
    p = SGSecondaryParams()
    sgs = SGSecondary(p)
    s = sgs.initial_state()
    inputs = design_inputs(p)
    inputs["m_steam"] = 0.5 * p.m_steam_design
    inputs["m_fw"] = inputs["m_steam"]
    d = sgs.derivatives(s, inputs)
    s2 = s + d * 1.0  # one explicit second, only to read the direction
    assert sgs.outputs(s2)["P_steam"] > sgs.outputs(s)["P_steam"]


def test_more_feedwater_than_steam_raises_level():
    p = SGSecondaryParams()
    sgs = SGSecondary(p)
    s = sgs.initial_state()
    inputs = design_inputs(p)
    inputs["m_fw"] = 1.1 * p.m_steam_design
    d = sgs.derivatives(s, inputs)
    assert d[0] > 0.0
    s2 = s + d * 10.0
    assert sgs.outputs(s2)["level_sg"] > sgs.outputs(s)["level_sg"]


def test_energy_bookkeeping_matches_steam_tables():
    p = SGSecondaryParams()
    sgs = SGSecondary(p)
    s = sgs.initial_state()
    inputs = design_inputs(p)
    inputs["Q_sg"] = 0.0
    d = sgs.derivatives(s, inputs)
    h_g = coolprop.sat_vapor_enthalpy(P=p.P_ref)
    h_fw = coolprop.enthalpy_PT(P=p.P_ref, T=p.T_fw)
    expected = p.m_steam_design * (h_fw - h_g)
    assert abs(d[1] - expected) < 1e-6 * abs(expected)


def test_h_fw_uses_public_feedwater_enthalpy_formula():
    p = SGSecondaryParams()
    sgs = SGSecondary(p)
    assert sgs.h_fw(p.P_ref) == pytest.approx(coolprop.enthalpy_PT(P=p.P_ref, T=p.T_fw))


def test_telemetry_without_inputs_reports_none_for_flows():
    sgs = SGSecondary(SGSecondaryParams())
    tele = sgs.telemetry(sgs.initial_state())
    assert tele["m_steam"] is None and tele["Q_sg"] is None
    assert tele["boil_off_time_s"] is None
    assert 0.0 < tele["x"] < 1.0
    assert tele["M_sec"] == pytest.approx(SGSecondaryParams().M_sec_initial)


def test_telemetry_exposes_secondary_diagnostics():
    p = SGSecondaryParams()
    sgs = SGSecondary(p)
    tele = sgs.telemetry(sgs.initial_state(), design_inputs(p))
    assert {
        "P_steam",
        "T_secondary",
        "level_sg",
        "x",
        "M_l",
        "M_v",
        "M_sec",
        "U_sec",
        "h_g",
        "h_fw",
        "P_fw_flash",
        "level_margin_low",
        "Q_sg",
        "m_steam",
        "m_dump",
        "m_fw",
        "Q_steam_net",
        "boil_off_time_s",
    } <= set(tele)
    assert tele["Q_steam_net"] == pytest.approx(p.Q_design)
    assert tele["P_fw_flash"] == pytest.approx(p.P_fw_flash)


def test_telemetry_reports_boil_off_time():
    p = SGSecondaryParams()
    sgs = SGSecondary(p)
    tele = sgs.telemetry(sgs.initial_state(), design_inputs(p))
    assert 100.0 < tele["boil_off_time_s"] < 160.0  # ~222 t / 1,669 kg/s
    assert tele["level_margin_low"] == pytest.approx(0.20)
