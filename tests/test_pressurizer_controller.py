"""Tests for src/fission_sim/control/pressurizer_controller.py.

Three layers:
  Layer 1 — pure outputs tests (no integration; controller is stateless)
  Layer 2 — closed-loop with the real pressurizer
  Layer 3 — handled in tests/test_pressurizer_plant.py
"""

import numpy as np
import pytest  # noqa: F401  - used by Layer-1 logic tests added in E2

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
