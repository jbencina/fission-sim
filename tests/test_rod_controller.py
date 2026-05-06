"""Tests for src/fission_sim/physics/rod_controller.py.

Three layers (mirroring the rest of the physics package):
  Layer 1 — pure derivative + output tests (no integration)
  Layer 2 — short-integration behavior tests
  Layer 3 — analytical comparison (first-order lag in the small-step regime)
"""

import numpy as np
import pytest

from fission_sim.physics.rod_controller import RodController, RodParams


def default_params() -> RodParams:
    """Return the project-wide default L1 rod-controller parameter set."""
    return RodParams()


def test_state_layout_indices():
    rod = RodController(default_params())
    assert rod.state_size == 1
    assert rod.state_labels == ("rod_position",)


def test_initial_state_is_design_position():
    p = default_params()
    rod = RodController(p)
    s = rod.initial_state()
    assert s.shape == (1,)
    assert s[0] == pytest.approx(p.rod_position_design)


# ---------------------------------------------------------------------------
# Layer 1: pure derivative tests (no integration)
# ---------------------------------------------------------------------------
def _design_inputs(p: RodParams) -> dict:
    """Inputs that, with initial_state, yield zero derivative."""
    return {"rod_command": p.rod_position_design, "scram": False}


def test_design_steady_state_balances():
    p = default_params()
    rod = RodController(p)
    dstate = rod.derivatives(rod.initial_state(), _design_inputs(p))
    assert np.allclose(dstate, 0.0, atol=1e-12)


def test_command_increase_withdraws_rod():
    """rod_command > current position → drod/dt > 0 (rods withdrawn)."""
    p = default_params()
    rod = RodController(p)
    inputs = _design_inputs(p) | {"rod_command": p.rod_position_design + 0.05}
    dstate = rod.derivatives(rod.initial_state(), inputs)
    assert dstate[0] > 0


def test_command_decrease_inserts_rod():
    """rod_command < current position → drod/dt < 0 (rods inserted)."""
    p = default_params()
    rod = RodController(p)
    inputs = _design_inputs(p) | {"rod_command": p.rod_position_design - 0.05}
    dstate = rod.derivatives(rod.initial_state(), inputs)
    assert dstate[0] < 0


def test_scram_overrides_command():
    """scram=True drives drod/dt < 0 even when rod_command says fully out."""
    p = default_params()
    rod = RodController(p)
    inputs = {"rod_command": 1.0, "scram": True}
    dstate = rod.derivatives(rod.initial_state(), inputs)
    assert dstate[0] < 0


def test_scram_at_max_velocity():
    """When scram=True from fully-withdrawn, the rate clip binds at -v_scram."""
    # Use tau=1 so raw rate = -1/1 = -1.0, which exceeds v_scram=0.5 and clips.
    p = RodParams(tau=1.0)
    rod = RodController(p)
    state = np.array([1.0])  # fully withdrawn
    inputs = {"rod_command": 1.0, "scram": True}
    dstate = rod.derivatives(state, inputs)
    # error = 0 - 1 = -1, raw rate = -1/tau = -1.0, clipped to -v_scram = -0.5
    assert dstate[0] == pytest.approx(-p.v_scram)


def test_normal_motion_at_max_velocity():
    """When command is far above current position, the rate clip binds at +v_normal."""
    p = default_params()
    rod = RodController(p)
    state = np.array([0.0])  # fully inserted
    inputs = {"rod_command": 1.0, "scram": False}
    dstate = rod.derivatives(state, inputs)
    # error = 1 - 0 = 1, raw rate = 1/tau = 0.1, clipped to +v_normal = 0.01
    assert dstate[0] == pytest.approx(p.v_normal)


def test_small_motion_in_lag_region():
    """Small error → rate is error/tau (clip not binding, pure first-order lag)."""
    p = default_params()
    rod = RodController(p)
    # Small error of 0.005: raw rate = 0.005 / 10 = 5e-4 (well below v_normal=0.01)
    state = np.array([p.rod_position_design])
    inputs = {"rod_command": p.rod_position_design + 0.005, "scram": False}
    dstate = rod.derivatives(state, inputs)
    expected = 0.005 / p.tau
    assert dstate[0] == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Layer 1: outputs() and telemetry() tests
# ---------------------------------------------------------------------------
def test_rod_reactivity_at_critical():
    """At rod_position == rod_position_critical, rod_reactivity == 0."""
    p = default_params()
    rod = RodController(p)
    state = np.array([p.rod_position_critical])
    out = rod.outputs(state)
    assert out["rod_reactivity"] == pytest.approx(0.0)


def test_rod_reactivity_negative_below_critical():
    """rod_position below critical → negative reactivity (rods more inserted)."""
    p = default_params()
    rod = RodController(p)
    state = np.array([p.rod_position_critical - 0.1])
    out = rod.outputs(state)
    expected = p.rho_total_worth * (-0.1)
    assert out["rod_reactivity"] == pytest.approx(expected)
    assert out["rod_reactivity"] < 0


def test_rod_reactivity_positive_above_critical():
    """rod_position above critical → positive reactivity (rods more withdrawn)."""
    p = default_params()
    rod = RodController(p)
    state = np.array([p.rod_position_critical + 0.1])
    out = rod.outputs(state)
    expected = p.rho_total_worth * 0.1
    assert out["rod_reactivity"] == pytest.approx(expected)
    assert out["rod_reactivity"] > 0


def test_telemetry_with_inputs():
    p = default_params()
    rod = RodController(p)
    state = np.array([0.4])
    inputs = {"rod_command": 0.6, "scram": False}
    tele = rod.telemetry(state, inputs)
    expected_keys = {
        "rod_position",
        "rod_reactivity",
        "rod_command",
        "scram",
        "rod_command_effective",
    }
    assert set(tele.keys()) == expected_keys
    assert tele["rod_position"] == pytest.approx(0.4)
    assert tele["rod_command"] == pytest.approx(0.6)
    assert tele["scram"] is False
    assert tele["rod_command_effective"] == pytest.approx(0.6)


def test_telemetry_with_scram_zeroes_effective_command():
    """rod_command_effective should be 0 when scram is asserted."""
    p = default_params()
    rod = RodController(p)
    state = np.array([0.4])
    inputs = {"rod_command": 0.8, "scram": True}
    tele = rod.telemetry(state, inputs)
    assert tele["rod_command_effective"] == pytest.approx(0.0)
    assert tele["scram"] is True


def test_telemetry_without_inputs_reports_none():
    p = default_params()
    rod = RodController(p)
    tele = rod.telemetry(rod.initial_state())
    # State-derived keys still present
    assert tele["rod_position"] == pytest.approx(p.rod_position_design)
    assert tele["rod_reactivity"] == pytest.approx(0.0)
    # Input-dependent keys are None
    assert tele["rod_command"] is None
    assert tele["scram"] is None
    assert tele["rod_command_effective"] is None
