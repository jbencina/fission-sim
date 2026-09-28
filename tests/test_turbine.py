import numpy as np
import pytest

from fission_sim.physics.sg_secondary import SGSecondaryParams
from fission_sim.physics.turbine import Turbine, TurbineParams


def make():
    sg = SGSecondaryParams()
    return Turbine(TurbineParams(sg_params=sg)), sg


def inputs(sg: SGSecondaryParams, **overrides):
    base = {
        "P_steam": sg.P_ref,
        "load_demand": 1.0,
        "turbine_trip": False,
        "scram": False,
    }
    base.update(overrides)
    return base


def test_state_layout():
    t, _ = make()
    assert t.state_size == 1 and t.state_labels == ("load",)
    assert t.input_ports == ("P_steam", "load_demand", "turbine_trip", "scram")
    assert t.output_ports == ("m_steam", "m_dump", "P_electric", "T_ref")
    assert t.outputs_require_inputs is True


def test_design_point_flows():
    t, sg = make()
    out = t.outputs(t.initial_state(), inputs=inputs(sg))
    assert out["m_steam"] == pytest.approx(sg.m_steam_design)
    assert out["m_dump"] == 0.0
    assert 9.5e8 < out["P_electric"] < 1.05e9  # ~990 MWe at eta 0.33
    assert out["T_ref"] == pytest.approx(583.0)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"P_dump_full": 7.0e6}, "P_dump_full must be greater than P_dump_set"),
        ({"P_dump_full": 7.6e6}, "P_dump_full must be greater than P_dump_set"),
        ({"P_dump_set": np.nan}, "P_dump_set must be finite"),
        ({"P_dump_full": np.inf}, "P_dump_full must be finite"),
        ({"tau_gov": 0.0}, "tau_gov must be finite and > 0"),
        ({"tau_trip": -0.5}, "tau_trip must be finite and > 0"),
        ({"ramp_rate": np.nan}, "ramp_rate must be finite and > 0"),
        ({"ramp_rate": -1.0e-3}, "ramp_rate must be finite and > 0"),
        ({"eta": 0.0}, "eta must be finite and in"),
        ({"eta": 1.2}, "eta must be finite and in"),
        ({"load_initial": -0.1}, "load_initial must be finite and in"),
        ({"load_initial": 1.1}, "load_initial must be finite and in"),
        ({"k_valve": -1.0}, "k_valve must be finite and > 0"),
    ],
)
def test_invalid_turbine_params_raise_learner_readable_value_error(kwargs, message):
    with pytest.raises(ValueError, match=message):
        TurbineParams(**kwargs)


def test_steam_flow_scales_with_load_and_pressure():
    t, sg = make()
    half = np.array([0.5])
    out = t.outputs(half, inputs=inputs(sg, P_steam=1.1 * sg.P_ref, load_demand=0.5))
    assert out["m_steam"] == pytest.approx(0.5 * 1.1 * sg.m_steam_design)


def test_negative_solver_trial_load_does_not_make_negative_flow():
    t, sg = make()
    out = t.outputs(np.array([-1.0e-12]), inputs=inputs(sg))
    assert out["m_steam"] == pytest.approx(0.0)
    assert out["P_electric"] == pytest.approx(0.0)


def test_T_ref_program_is_linear_in_load():
    t, _ = make()
    assert t.T_ref_for(0.0) == pytest.approx(565.0)
    assert t.T_ref_for(0.5) == pytest.approx(574.0)
    assert t.T_ref_for(1.0) == pytest.approx(583.0)


def test_load_ramps_at_governor_rate():
    t, sg = make()
    d = t.derivatives(np.array([1.0]), inputs(sg, load_demand=0.5))
    assert d[0] == pytest.approx(-t.params.ramp_rate)
    d = t.derivatives(np.array([0.9995]), inputs(sg, load_demand=1.0))
    assert 0.0 < d[0] < t.params.ramp_rate  # inside the lag, below the rate limit


def test_trip_closes_fast_regardless_of_demand():
    t, sg = make()
    d = t.derivatives(np.array([1.0]), inputs(sg, turbine_trip=True))
    assert d[0] == pytest.approx(-1.0 / t.params.tau_trip)


def test_scram_alone_closes_turbine_and_telemetry_reports_p4_interlock():
    t, sg = make()
    state = np.array([1.0])
    trip_inputs = inputs(sg, scram=True)
    d = t.derivatives(state, trip_inputs)
    tele = t.telemetry(state, trip_inputs)
    assert d[0] == pytest.approx(-1.0 / t.params.tau_trip)
    assert tele["scram"] is True
    assert tele["turbine_trip"] is False
    assert tele["trip_active"] is True


def test_dump_opens_proportionally_above_setpoint():
    t, sg = make()
    p = t.params
    zero = np.array([0.0])
    assert t.outputs(zero, inputs=inputs(sg, load_demand=0.0, turbine_trip=True, P_steam=p.P_dump_set))["m_dump"] == 0.0
    mid = t.outputs(
        zero,
        inputs=inputs(sg, load_demand=0.0, turbine_trip=True, P_steam=0.5 * (p.P_dump_set + p.P_dump_full)),
    )["m_dump"]
    assert mid == pytest.approx(0.5 * sg.m_steam_design)
    full = t.outputs(
        zero,
        inputs=inputs(sg, load_demand=0.0, turbine_trip=True, P_steam=p.P_dump_full + 1e6),
    )["m_dump"]
    assert full == pytest.approx(sg.m_steam_design)


def test_load_demand_is_clipped_to_unit_interval():
    t, sg = make()
    d_hi = t.derivatives(np.array([1.0]), inputs(sg, load_demand=7.0))
    assert d_hi[0] == pytest.approx(0.0)
    d_lo = t.derivatives(np.array([0.0]), inputs(sg, load_demand=-3.0))
    assert d_lo[0] == pytest.approx(0.0)


def test_nonfinite_load_demand_is_rejected():
    t, sg = make()
    with pytest.raises(ValueError, match="load_demand must be finite"):
        t.derivatives(np.array([1.0]), inputs(sg, load_demand=np.nan))


def test_telemetry_without_inputs():
    t, _ = make()
    tele = t.telemetry(t.initial_state())
    assert tele["load"] == 1.0 and tele["T_ref"] == pytest.approx(583.0)
    assert tele["m_steam"] is None and tele["m_dump"] is None and tele["P_electric"] is None
    assert tele["scram"] is None and tele["trip_active"] is None
