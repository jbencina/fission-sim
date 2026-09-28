import math

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from fission_sim.control.feedwater_controller import FeedwaterController, FeedwaterControllerParams
from fission_sim.physics.domain import check_snapshot
from fission_sim.plant import build_standard_plant

TOY_RHO_L = 741.5  # [kg/m^3], saturated-liquid density from the independent review reproducer
TOY_V_SEC = 600.0  # [m^3], default SGSecondary shell volume
TOY_TAU_FW = 5.0  # [s], M4 feedwater actuator lag used by the reproducer


def inputs(**over):
    base = {
        "level_sg": 0.5,
        "level_setpoint": 0.5,
        "m_steam": 1669.0,
        "m_dump": 0.0,
        "feedwater_manual": None,
    }
    base.update(over)
    return base


def _raw_automatic_demand(c: FeedwaterController, state: np.ndarray, controller_inputs: dict) -> float:
    p = c.params
    e = controller_inputs["level_setpoint"] - controller_inputs["level_sg"]
    integral_authority = p.integral_authority_frac * p.sg_params.m_steam_design
    integral_flow = float(np.clip(p.K_i * state[0], -integral_authority, integral_authority))
    return controller_inputs["m_steam"] + controller_inputs["m_dump"] + p.K_p * e + integral_flow


def _unbounded_automatic_demand(c: FeedwaterController, state: np.ndarray, controller_inputs: dict) -> float:
    p = c.params
    e = controller_inputs["level_setpoint"] - controller_inputs["level_sg"]
    return controller_inputs["m_steam"] + controller_inputs["m_dump"] + p.K_p * e + p.K_i * state[0]


def _expected_back_calculation_derivative(
    c: FeedwaterController,
    state: np.ndarray,
    controller_inputs: dict,
) -> float:
    p = c.params
    raw = _raw_automatic_demand(c, state, controller_inputs)
    clipped = c.outputs(state, inputs=controller_inputs)["m_fw_demand"]
    e = controller_inputs["level_setpoint"] - controller_inputs["level_sg"]
    integral_authority = p.integral_authority_frac * p.sg_params.m_steam_design
    integral_flow_raw = p.K_i * state[0]
    integral_flow = float(np.clip(integral_flow_raw, -integral_authority, integral_authority))
    authority_tracking = (integral_flow - integral_flow_raw) / (p.K_i * p.antiwindup_tracking_time)
    return e + (clipped - raw) / (p.K_i * p.antiwindup_tracking_time) + authority_tracking


def _solve_toy_level_loop(level_setpoint: float, m_steam: float):
    c = FeedwaterController(FeedwaterControllerParams())

    def rhs(_t: float, y: np.ndarray) -> list[float]:
        level_sg, m_fw, integral = y
        controller_state = np.array([integral])
        controller_inputs = inputs(level_sg=level_sg, level_setpoint=level_setpoint, m_steam=m_steam)
        m_fw_demand = c.outputs(controller_state, inputs=controller_inputs)["m_fw_demand"]
        d_integral_dt = c.derivatives(controller_state, controller_inputs)[0]
        d_level_dt = (m_fw - m_steam) / (TOY_RHO_L * TOY_V_SEC)
        d_m_fw_dt = (m_fw_demand - m_fw) / TOY_TAU_FW
        return [d_level_dt, d_m_fw_dt, d_integral_dt]

    return solve_ivp(
        rhs,
        (0.0, 600.0),
        [0.5, m_steam, 0.0],
        method="BDF",
        rtol=1.0e-6,
        atol=1.0e-9,
        max_step=0.5,
    )


def test_layout_and_derived_gains():
    c = FeedwaterController(FeedwaterControllerParams())
    p = c.params
    assert c.state_size == 1
    assert c.state_labels == ("level_error_integral",)
    assert c.input_ports == ("level_sg", "level_setpoint", "m_steam", "m_dump", "feedwater_manual")
    assert c.output_ports == ("m_fw_demand",)
    assert c.outputs_require_inputs is True
    assert p.K_i == pytest.approx(p.K_p / 300.0)
    assert p.antiwindup_tracking_time == pytest.approx(30.0)
    assert p.manual_tracking_time == pytest.approx(1.0)
    assert p.manual_tracking_time < TOY_TAU_FW
    assert p.integral_authority_frac == pytest.approx(0.2)
    assert p.integral_authority_frac * p.sg_params.m_steam_design == pytest.approx(0.2 * p.sg_params.m_steam_design)
    assert c.initial_state()[0] == 0.0


def test_balanced_at_setpoint_demands_total_steam():
    c = FeedwaterController(FeedwaterControllerParams())
    out = c.outputs(np.array([0.0]), inputs=inputs(m_steam=1500.0, m_dump=169.0))
    assert out["m_fw_demand"] == pytest.approx(1669.0)
    assert c.derivatives(np.array([0.0]), inputs())[0] == 0.0


def test_low_level_adds_proportional_flow():
    c = FeedwaterController(FeedwaterControllerParams())
    out = c.outputs(np.array([0.0]), inputs=inputs(level_sg=0.45))
    assert out["m_fw_demand"] == pytest.approx(1669.0 + 0.05 * c.params.K_p)
    assert c.derivatives(np.array([0.0]), inputs(level_sg=0.45))[0] == pytest.approx(0.05)


def test_integral_contributes():
    c = FeedwaterController(FeedwaterControllerParams())
    out = c.outputs(np.array([10.0]), inputs=inputs())
    assert out["m_fw_demand"] == pytest.approx(1669.0 + 10.0 * c.params.K_i)


def test_manual_override_scales_max_flow_and_tracks_integral():
    c = FeedwaterController(FeedwaterControllerParams())
    p = c.params
    m_max = p.m_fw_max_frac * p.sg_params.m_steam_design
    state = np.array([3.0])
    controller_inputs = inputs(feedwater_manual=0.5, level_sg=0.3)

    out = c.outputs(state, inputs=controller_inputs)
    feedforward = controller_inputs["m_steam"] + controller_inputs["m_dump"]
    integral_authority = p.integral_authority_frac * p.sg_params.m_steam_design
    target_integral_flow = float(
        np.clip(0.5 * m_max - feedforward - p.K_p * 0.2, -integral_authority, integral_authority)
    )
    expected = (target_integral_flow / p.K_i - state[0]) / p.manual_tracking_time

    assert out["m_fw_demand"] == pytest.approx(0.5 * m_max)
    assert c.derivatives(state, controller_inputs)[0] == pytest.approx(expected)


def test_manual_tracking_uses_clipped_physical_demand():
    c = FeedwaterController(FeedwaterControllerParams())
    p = c.params
    m_max = p.m_fw_max_frac * p.sg_params.m_steam_design
    state = np.array([2.0])
    integral_authority = p.integral_authority_frac * p.sg_params.m_steam_design

    high_inputs = inputs(feedwater_manual=2.0)
    high_feedforward = high_inputs["m_steam"] + high_inputs["m_dump"]
    high_target = np.clip(m_max - high_feedforward, -integral_authority, integral_authority) / p.K_i
    high_expected = (high_target - state[0]) / p.manual_tracking_time
    assert c.derivatives(state, high_inputs)[0] == pytest.approx(high_expected)

    low_inputs = inputs(feedwater_manual=-1.0)
    low_feedforward = low_inputs["m_steam"] + low_inputs["m_dump"]
    low_target = np.clip(0.0 - low_feedforward, -integral_authority, integral_authority) / p.K_i
    low_expected = (low_target - state[0]) / p.manual_tracking_time
    assert c.derivatives(state, low_inputs)[0] == pytest.approx(low_expected)


def test_manual_tracking_makes_auto_demand_match_manual_after_a_few_seconds():
    c = FeedwaterController(FeedwaterControllerParams())
    p = c.params
    m_max = p.m_fw_max_frac * p.sg_params.m_steam_design
    controller_inputs = inputs(feedwater_manual=0.9, level_sg=0.527)

    def rhs(_t: float, y: np.ndarray) -> list[float]:
        return [c.derivatives(y, controller_inputs)[0]]

    sol = solve_ivp(
        rhs,
        (0.0, 5.0 * p.manual_tracking_time),
        [0.0],
        method="BDF",
        rtol=1.0e-8,
        atol=1.0e-10,
    )

    assert sol.success, sol.message
    final_state = np.array([sol.y[0, -1]])
    raw_auto = _raw_automatic_demand(c, final_state, controller_inputs)
    assert abs(raw_auto - 0.9 * m_max) < 0.01 * m_max


def test_manual_tracking_steady_inputs_converges_to_integral_authority_limit():
    c = FeedwaterController(FeedwaterControllerParams())
    p = c.params
    controller_inputs = inputs(feedwater_manual=0.0)
    integral_authority = p.integral_authority_frac * p.sg_params.m_steam_design

    def rhs(_t: float, y: np.ndarray) -> list[float]:
        return [c.derivatives(y, controller_inputs)[0]]

    sol = solve_ivp(
        rhs,
        (0.0, 5.0),
        [0.0],
        method="BDF",
        rtol=1.0e-8,
        atol=1.0e-10,
    )

    assert sol.success, sol.message
    integral_flow = p.K_i * sol.y[0, -1]
    expected = -integral_authority * (1.0 - math.exp(-5.0 / p.manual_tracking_time))
    assert integral_flow == pytest.approx(expected, rel=5.0e-3)
    assert abs(integral_flow) < integral_authority


def _manual_to_auto_demand_step(feedwater_manual: float, transfer_time: float) -> tuple[float, float, float, float]:
    eng = build_standard_plant()
    eng.run(10.0, max_step=0.5)
    manual_snap = eng.run(
        transfer_time,
        scenario_fn=lambda _t: {"feedwater_manual": feedwater_manual},
        max_step=0.5,
    )
    manual_demand = manual_snap["fw_ctrl"]["m_fw_demand"]
    auto_demand = eng.snapshot()["fw_ctrl"]["m_fw_demand"]
    integral_flow = FeedwaterControllerParams().K_i * manual_snap["fw_ctrl"]["level_error_integral"]
    return auto_demand - manual_demand, manual_demand, auto_demand, integral_flow


def test_manual_zero_then_auto_recovers_without_model_limit():
    """Large manual/AUTO mismatch steps back toward feed-forward and preserves inventory."""
    params = FeedwaterControllerParams()
    integral_authority = params.integral_authority_frac * params.sg_params.m_steam_design
    eng = build_standard_plant()
    snap = eng.snapshot()
    min_level = snap["sg_sec"]["level_sg"]
    for _ in range(5):
        snap = eng.step(1.0, feedwater_manual=0.0)
        check_snapshot(snap)
        min_level = min(min_level, snap["sg_sec"]["level_sg"])

    manual_demand = snap["fw_ctrl"]["m_fw_demand"]
    auto_transfer_snap = eng.snapshot()
    transfer_step = auto_transfer_snap["fw_ctrl"]["m_fw_demand"] - manual_demand
    auto_snap = eng.step(1.0)
    check_snapshot(auto_snap)
    min_level = min(min_level, auto_snap["sg_sec"]["level_sg"])

    while eng.t < 600.0:
        snap = eng.step(min(1.0, 600.0 - eng.t))
        check_snapshot(snap)
        min_level = min(min_level, snap["sg_sec"]["level_sg"])

    assert manual_demand == 0.0
    assert transfer_step > 0.5 * params.sg_params.m_steam_design
    assert transfer_step < params.sg_params.m_steam_design
    assert min_level > 0.35
    assert abs(params.K_i * auto_snap["fw_ctrl"]["level_error_integral"]) <= integral_authority + 2.0


def test_standard_plant_manual_to_auto_feedwater_transfer_is_bumpless_when_near_auto_demand():
    """Moving plant inputs leave only a small residual step when manual demand is near AUTO."""
    eng = build_standard_plant()
    manual_snap = eng.run(
        100.0,
        scenario_fn=lambda t: {"feedwater_manual": 0.9 if t >= 10.0 else None},
        max_step=0.5,
    )

    manual_demand = manual_snap["fw_ctrl"]["m_fw_demand"]
    auto_snap = eng.snapshot()
    auto_demand = auto_snap["fw_ctrl"]["m_fw_demand"]

    assert abs(auto_demand - manual_demand) < 10.0


def test_integral_authority_stays_bounded_in_manual_and_auto():
    params = FeedwaterControllerParams()
    integral_authority = params.integral_authority_frac * params.sg_params.m_steam_design
    eng = build_standard_plant()
    max_abs_integral_flow = 0.0

    for _ in range(5):
        snap = eng.step(1.0, feedwater_manual=0.0)
        max_abs_integral_flow = max(max_abs_integral_flow, abs(params.K_i * snap["fw_ctrl"]["level_error_integral"]))

    for _ in range(60):
        snap = eng.step(1.0)
        max_abs_integral_flow = max(max_abs_integral_flow, abs(params.K_i * snap["fw_ctrl"]["level_error_integral"]))
        check_snapshot(snap)

    assert max_abs_integral_flow <= integral_authority + 2.0


def test_manual_override_clips_fraction_to_physical_range():
    c = FeedwaterController(FeedwaterControllerParams())
    p = c.params
    m_max = p.m_fw_max_frac * p.sg_params.m_steam_design
    assert c.outputs(np.array([0.0]), inputs=inputs(feedwater_manual=2.0))["m_fw_demand"] == pytest.approx(m_max)
    assert c.outputs(np.array([0.0]), inputs=inputs(feedwater_manual=-1.0))["m_fw_demand"] == 0.0


def test_unsaturated_automatic_integral_derivative_is_exact_level_error():
    c = FeedwaterController(FeedwaterControllerParams())
    controller_inputs = inputs(level_sg=0.45)
    m_fw_max = c.params.m_fw_max_frac * c.params.sg_params.m_steam_design
    assert _raw_automatic_demand(c, np.array([0.0]), controller_inputs) < m_fw_max
    assert c.derivatives(np.array([0.0]), controller_inputs)[0] == pytest.approx(0.05)


def test_back_calculation_pulls_integral_down_at_upper_saturation():
    c = FeedwaterController(FeedwaterControllerParams())
    p = c.params
    state = np.array([10.0])
    high_flow = p.m_fw_max_frac * p.sg_params.m_steam_design
    controller_inputs = inputs(m_steam=high_flow, level_sg=0.49)
    assert c.outputs(state, inputs=controller_inputs)["m_fw_demand"] == pytest.approx(high_flow)

    expected = _expected_back_calculation_derivative(c, state, controller_inputs)
    assert expected < 0.0
    assert c.derivatives(state, controller_inputs)[0] == pytest.approx(expected)


def test_back_calculation_pulls_integral_up_at_lower_saturation():
    c = FeedwaterController(FeedwaterControllerParams())
    state = np.array([-10.0])
    controller_inputs = inputs(m_steam=0.0, level_sg=0.51)
    assert c.outputs(state, inputs=controller_inputs)["m_fw_demand"] == 0.0

    expected = _expected_back_calculation_derivative(c, state, controller_inputs)
    assert expected > 0.0
    assert c.derivatives(state, controller_inputs)[0] == pytest.approx(expected)


def test_back_calculation_unwinds_from_both_limits():
    c = FeedwaterController(FeedwaterControllerParams())
    p = c.params
    high_flow = p.m_fw_max_frac * p.sg_params.m_steam_design

    lower_inputs = inputs(m_steam=0.0, level_sg=0.49)
    assert c.outputs(np.array([-10.0]), inputs=lower_inputs)["m_fw_demand"] == 0.0
    assert c.derivatives(np.array([-10.0]), lower_inputs)[0] > 0.0

    upper_inputs = inputs(m_steam=high_flow, level_sg=0.51)
    assert c.outputs(np.array([10.0]), inputs=upper_inputs)["m_fw_demand"] == pytest.approx(high_flow)
    assert c.derivatives(np.array([10.0]), upper_inputs)[0] < 0.0


@pytest.mark.parametrize(
    ("level_setpoint", "m_steam"),
    [
        (0.60, FeedwaterControllerParams().sg_params.m_steam_design),
        (0.40, 0.2 * FeedwaterControllerParams().sg_params.m_steam_design),
    ],
)
def test_bdf_closed_loop_regression_for_saturated_step(level_setpoint, m_steam):
    sol = _solve_toy_level_loop(level_setpoint=level_setpoint, m_steam=m_steam)
    assert sol.success, sol.message

    final_level = sol.y[0, -1]
    final_m_fw = sol.y[1, -1]
    final_level_rate = (final_m_fw - m_steam) / (TOY_RHO_L * TOY_V_SEC)

    assert abs(final_level - level_setpoint) < 0.02
    assert abs(final_level - level_setpoint) < abs(0.5 - level_setpoint)
    assert (level_setpoint - final_level) * final_level_rate > 0.0


@pytest.mark.parametrize("key", ["level_sg", "level_setpoint", "m_steam", "m_dump"])
def test_nonfinite_level_or_flow_inputs_raise_value_error(key):
    c = FeedwaterController(FeedwaterControllerParams())
    with pytest.raises(ValueError, match=key):
        c.outputs(np.array([0.0]), inputs=inputs(**{key: math.nan}))


def test_nonfinite_manual_input_raises_value_error():
    c = FeedwaterController(FeedwaterControllerParams())
    with pytest.raises(ValueError, match="feedwater_manual"):
        c.outputs(np.array([0.0]), inputs=inputs(feedwater_manual=math.inf))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"K_p": math.nan},
        {"K_p": 0.0},
        {"K_i": math.inf},
        {"K_i": 0.0},
        {"level_setpoint_default": 0.0},
        {"level_setpoint_default": 1.0},
        {"m_fw_max_frac": 0.0},
        {"antiwindup_tracking_time": math.nan},
        {"antiwindup_tracking_time": 0.0},
        {"manual_tracking_time": math.nan},
        {"manual_tracking_time": 0.0},
        {"integral_authority_frac": math.nan},
        {"integral_authority_frac": 0.0},
    ],
)
def test_invalid_params_raise_value_error(kwargs):
    with pytest.raises(ValueError):
        FeedwaterControllerParams(**kwargs)


def test_telemetry_without_inputs():
    c = FeedwaterController(FeedwaterControllerParams())
    tele = c.telemetry(np.array([7.0]))
    assert tele == {
        "m_fw_demand": None,
        "level_error": None,
        "level_error_integral": 7.0,
        "feedwater_manual": None,
        "mode": None,
        "saturated": None,
    }


def test_telemetry_with_inputs_reports_mode_and_saturation():
    c = FeedwaterController(FeedwaterControllerParams())
    tele = c.telemetry(np.array([0.0]), inputs=inputs(level_sg=0.45))
    assert tele["m_fw_demand"] == pytest.approx(1669.0 + 0.05 * c.params.K_p)
    assert tele["level_error"] == pytest.approx(0.05)
    assert tele["level_error_integral"] == 0.0
    assert tele["feedwater_manual"] is None
    assert tele["mode"] == "auto"
    assert tele["saturated"] is False

    manual = c.telemetry(np.array([0.0]), inputs=inputs(feedwater_manual=2.0))
    assert manual["feedwater_manual"] == 1.0
    assert manual["mode"] == "manual"
    assert manual["saturated"] is True
