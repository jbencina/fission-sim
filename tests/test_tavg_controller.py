import numpy as np
import pytest

from fission_sim.control.tavg_controller import TavgController, TavgControllerParams
from fission_sim.physics.rod_controller import RodController, RodParams


def inputs(**over):
    base = {
        "T_avg": 583.0,
        "T_ref": 583.0,
        "rod_position": 0.5,
        "rod_command": 0.5,
        "rod_auto": True,
        "scram": False,
        "turbine_trip": False,
    }
    base.update(over)
    return base


def test_layout():
    c = TavgController(TavgControllerParams())
    assert c.state_labels == ("rod_demand_auto",)
    assert c.output_ports == ("rod_demand",)
    assert c.outputs_require_inputs is True
    assert c.initial_state()[0] == pytest.approx(0.5)


def test_initial_auto_state_can_match_initial_rod_position():
    c = TavgController(TavgControllerParams(), rod_position_initial=0.37)
    assert c.initial_state()[0] == pytest.approx(0.37)


def test_manual_mode_passes_rod_command_through():
    c = TavgController(TavgControllerParams())
    out = c.outputs(np.array([0.7]), inputs=inputs(rod_auto=False, rod_command=0.42))
    assert out["rod_demand"] == 0.42


def test_manual_mode_state_tracks_rod_position():
    c = TavgController(TavgControllerParams())
    d = c.derivatives(np.array([0.7]), inputs(rod_auto=False, rod_position=0.5))
    assert d[0] == pytest.approx((0.5 - 0.7) / c.params.tau_track)


def test_auto_mode_outputs_state():
    c = TavgController(TavgControllerParams())
    assert c.outputs(np.array([0.61]), inputs=inputs())["rod_demand"] == 0.61


def test_auto_mode_output_is_clipped_to_bank_travel():
    c = TavgController(TavgControllerParams())
    assert c.outputs(np.array([-0.1]), inputs=inputs())["rod_demand"] == 0.0
    assert c.outputs(np.array([1.1]), inputs=inputs())["rod_demand"] == 1.0


def test_speed_curve():
    c = TavgController(TavgControllerParams())
    p = c.params
    assert c.speed(0.5) == 0.0
    assert c.speed(p.deadband) == 0.0
    assert c.speed(0.5 * (p.deadband + p.err_max)) == pytest.approx(0.5 * (p.v_min + p.v_max))
    assert c.speed(10.0) == p.v_max


def test_hot_inserts_cold_withdraws():
    c = TavgController(TavgControllerParams())
    d_hot = c.derivatives(np.array([0.5]), inputs(T_avg=586.0))
    d_cold = c.derivatives(np.array([0.5]), inputs(T_avg=580.0))
    assert d_hot[0] == pytest.approx(-c.params.v_max)
    assert d_cold[0] == pytest.approx(+c.params.v_max)


def test_state_stops_at_travel_limits():
    c = TavgController(TavgControllerParams())
    assert c.derivatives(np.array([0.0]), inputs(T_avg=590.0))[0] == 0.0
    assert c.derivatives(np.array([1.0]), inputs(T_avg=570.0))[0] == 0.0


@pytest.mark.parametrize("flag", ["scram", "turbine_trip"])
def test_auto_action_suspended_during_scram_or_turbine_trip(flag):
    """Review Focus 1: after a trip T_avg is far below T_ref; rods must not drive out."""
    c = TavgController(TavgControllerParams())
    d = c.derivatives(np.array([0.5]), inputs(T_avg=560.0, rod_position=0.0, **{flag: True}))
    assert d[0] == pytest.approx((0.0 - 0.5) / c.params.tau_track)


def test_auto_suspended_output_is_neutral_when_tracking_rod_position():
    """In auto-but-suspended mode, tracking the actual bank cannot create a new rod demand."""
    c = TavgController(TavgControllerParams())
    inp = inputs(T_avg=560.0, rod_position=0.42, turbine_trip=True)
    assert c.outputs(np.array([0.42]), inputs=inp)["rod_demand"] == pytest.approx(0.42)
    assert c.derivatives(np.array([0.42]), inp)[0] == pytest.approx(0.0)


def test_auto_suspended_output_holds_actual_rod_position_when_state_differs():
    c = TavgController(TavgControllerParams())
    out = c.outputs(np.array([0.67]), inputs=inputs(rod_position=0.31, turbine_trip=True))
    assert out["rod_demand"] == pytest.approx(0.31)


def test_scram_clear_with_turbine_trip_does_not_withdraw_rods():
    """Coupled controller + rod actuator: clearing SCRAM under turbine trip holds rods in place."""
    ctrl = TavgController(TavgControllerParams(), rod_position_initial=0.7)
    rod = RodController(RodParams())
    ctrl_state = ctrl.initial_state()
    rod_state = rod.initial_state()

    def step(*, scram: bool, turbine_trip: bool, dt: float = 0.005) -> None:
        nonlocal ctrl_state, rod_state
        ctrl_inputs = inputs(
            T_avg=560.0,
            T_ref=583.0,
            rod_position=rod_state[0],
            rod_command=0.7,
            rod_auto=True,
            scram=scram,
            turbine_trip=turbine_trip,
        )
        rod_demand = ctrl.outputs(ctrl_state, inputs=ctrl_inputs)["rod_demand"]
        ctrl_state = ctrl_state + ctrl.derivatives(ctrl_state, ctrl_inputs) * dt
        rod_state = rod_state + rod.derivatives(rod_state, {"rod_command": rod_demand, "scram": scram}) * dt

    for _ in range(round(2.0 / 0.005)):
        step(scram=True, turbine_trip=True)

    position_when_scram_clears = rod_state[0]
    assert ctrl_state[0] > position_when_scram_clears + 0.02

    for _ in range(round(5.0 / 0.005)):
        step(scram=False, turbine_trip=True)

    assert rod_state[0] <= position_when_scram_clears + 1e-12


def test_telemetry_without_inputs():
    c = TavgController(TavgControllerParams())
    tele = c.telemetry(np.array([0.5]))
    assert tele["rod_demand_auto"] == 0.5 and tele["rod_demand"] is None and tele["T_err"] is None
