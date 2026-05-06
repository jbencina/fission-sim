"""Tests for src/fission_sim/physics/rod_controller.py.

Three layers (mirroring the rest of the physics package):
  Layer 1 — pure derivative + output tests (no integration)
  Layer 2 — short-integration behavior tests
  Layer 3 — analytical comparison (first-order lag in the small-step regime)
"""

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
