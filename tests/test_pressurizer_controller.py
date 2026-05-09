"""Tests for src/fission_sim/control/pressurizer_controller.py.

Three layers:
  Layer 1 — pure outputs tests (no integration; controller is stateless)
  Layer 2 — closed-loop with the real pressurizer
  Layer 3 — handled in tests/test_pressurizer_plant.py
"""

import numpy as np
import pytest

from fission_sim.control.pressurizer_controller import (
    PressurizerController,
    PressurizerControllerParams,
)


def default_params() -> PressurizerControllerParams:
    return PressurizerControllerParams()


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------
def test_controller_state_size_is_zero():
    ctrl = PressurizerController(default_params())
    assert ctrl.state_size == 0
    assert ctrl.state_labels == ()


def test_controller_input_ports():
    ctrl = PressurizerController(default_params())
    assert ctrl.input_ports == (
        "P",
        "P_setpoint",
        "heater_manual",
        "spray_manual",
    )


def test_controller_output_ports():
    ctrl = PressurizerController(default_params())
    assert ctrl.output_ports == ("Q_heater", "m_dot_spray")


def test_controller_initial_state_is_empty():
    ctrl = PressurizerController(default_params())
    s = ctrl.initial_state()
    assert s.shape == (0,)


def test_controller_derivatives_returns_empty_array():
    """state_size=0 → derivatives must return shape (0,)."""
    ctrl = PressurizerController(default_params())
    d = ctrl.derivatives(np.zeros(0), {
        "P": 1.55e7, "P_setpoint": 1.55e7,
        "heater_manual": None, "spray_manual": None,
    })
    assert d.shape == (0,)


# ---------------------------------------------------------------------------
# Layer 1: outputs() logic — proportional + deadband + manual override
# ---------------------------------------------------------------------------
def _at_setpoint(p):
    return {
        "P": 1.55e7,
        "P_setpoint": p.P_setpoint_default,
        "heater_manual": None,
        "spray_manual": None,
    }


def test_at_setpoint_both_quiet():
    p = default_params()
    ctrl = PressurizerController(p)
    out = ctrl.outputs(np.zeros(0), inputs=_at_setpoint(p))
    assert out["Q_heater"] == 0.0
    assert out["m_dot_spray"] == 0.0


def test_inside_deadband_below_setpoint_quiet():
    """P below setpoint by less than deadband → both quiet."""
    p = default_params()
    ctrl = PressurizerController(p)
    inputs = _at_setpoint(p) | {"P": 1.55e7 - 0.5 * p.deadband}
    out = ctrl.outputs(np.zeros(0), inputs=inputs)
    assert out["Q_heater"] == 0.0
    assert out["m_dot_spray"] == 0.0


def test_below_deadband_fires_heater():
    """P below setpoint by more than deadband → heater fires."""
    p = default_params()
    ctrl = PressurizerController(p)
    inputs = _at_setpoint(p) | {"P": 1.55e7 - 1.5 * p.deadband}
    out = ctrl.outputs(np.zeros(0), inputs=inputs)
    assert out["Q_heater"] > 0
    assert out["m_dot_spray"] == 0.0


def test_above_deadband_opens_spray():
    """P above setpoint by more than deadband → spray opens."""
    p = default_params()
    ctrl = PressurizerController(p)
    inputs = _at_setpoint(p) | {"P": 1.55e7 + 1.5 * p.deadband}
    out = ctrl.outputs(np.zeros(0), inputs=inputs)
    assert out["m_dot_spray"] > 0
    assert out["Q_heater"] == 0.0


def test_heater_saturates_at_max():
    """Large underpressure → Q_heater clamped at Q_heater_max."""
    p = default_params()
    ctrl = PressurizerController(p)
    inputs = _at_setpoint(p) | {"P": 1.55e7 - 1.0e6}
    out = ctrl.outputs(np.zeros(0), inputs=inputs)
    assert out["Q_heater"] == pytest.approx(p.Q_heater_max)


def test_spray_saturates_at_max():
    """Large overpressure → m_dot_spray clamped at m_dot_spray_max."""
    p = default_params()
    ctrl = PressurizerController(p)
    inputs = _at_setpoint(p) | {"P": 1.55e7 + 1.0e6}
    out = ctrl.outputs(np.zeros(0), inputs=inputs)
    assert out["m_dot_spray"] == pytest.approx(p.m_dot_spray_max)


def test_heater_manual_override_forces_demand():
    """heater_manual=0.3 forces 30% duty regardless of pressure error."""
    p = default_params()
    ctrl = PressurizerController(p)
    inputs = _at_setpoint(p) | {"P": 1.55e7 + 1.0e6, "heater_manual": 0.3}
    out = ctrl.outputs(np.zeros(0), inputs=inputs)
    assert out["Q_heater"] == pytest.approx(0.3 * p.Q_heater_max)
    assert out["m_dot_spray"] > 0


def test_spray_manual_override_forces_demand():
    p = default_params()
    ctrl = PressurizerController(p)
    inputs = _at_setpoint(p) | {"P": 1.55e7 - 1.0e6, "spray_manual": 0.5}
    out = ctrl.outputs(np.zeros(0), inputs=inputs)
    assert out["m_dot_spray"] == pytest.approx(0.5 * p.m_dot_spray_max)
    assert out["Q_heater"] > 0


def test_heater_manual_zero_disables_during_underpressure():
    """heater_manual=0 disables heater even with large underpressure
    (the 'heater stuck off' fault scenario)."""
    p = default_params()
    ctrl = PressurizerController(p)
    inputs = _at_setpoint(p) | {"P": 1.55e7 - 1.0e6, "heater_manual": 0.0}
    out = ctrl.outputs(np.zeros(0), inputs=inputs)
    assert out["Q_heater"] == 0.0


def test_outputs_requires_inputs_kwarg():
    """Controller is a 'computed' module — outputs(state) without
    inputs must raise."""
    ctrl = PressurizerController(default_params())
    with pytest.raises(TypeError):
        ctrl.outputs(np.zeros(0))
