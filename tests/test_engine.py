"""Tests for SimEngine — the simulation graph runner.

Toy components are defined inline per-test rather than factored into a fixtures
file, so each test reads as a self-contained statement of expected behavior.
"""

from __future__ import annotations

import numpy as np
import pytest

from fission_sim.engine import EngineWiringError, SimEngine


class _ScalarIntegrator:
    """Toy: state is a scalar that integrates a constant input rate."""

    state_size = 1
    state_labels = ("x",)
    input_ports = ("rate",)
    output_ports = ("x",)

    def __init__(self, x0: float = 0.0) -> None:
        self._x0 = x0

    def initial_state(self) -> np.ndarray:
        return np.array([self._x0])

    def derivatives(self, state: np.ndarray, inputs: dict) -> np.ndarray:
        return np.array([float(inputs["rate"])])

    def outputs(self, state: np.ndarray, inputs: dict | None = None) -> dict:
        return {"x": float(state[0])}

    def telemetry(self, state: np.ndarray, inputs: dict | None = None) -> dict:
        return {"x": float(state[0])}


def test_state_layout_concatenates() -> None:
    """Two modules with state_size 1 → engine.state has shape (2,) after finalize."""
    engine = SimEngine()
    engine.module(_ScalarIntegrator(x0=1.0), name="a")
    engine.module(_ScalarIntegrator(x0=2.0), name="b")
    engine.input("rate", default=0.0)
    # No wiring needed for this layout test — finalize() should still allocate
    # the state vector. Note: this test currently expects unwired inputs to be
    # tolerated; that gets tightened in Task 7.
    engine.finalize()
    assert engine.state.shape == (2,)


def test_initial_state_assembled_from_modules() -> None:
    """engine.state matches concatenated module initial_state() values."""
    engine = SimEngine()
    a = _ScalarIntegrator(x0=3.0)
    b = _ScalarIntegrator(x0=5.0)
    engine.module(a, name="a")
    engine.module(b, name="b")
    engine.input("rate", default=0.0)
    engine.finalize()
    np.testing.assert_array_equal(engine.state, np.array([3.0, 5.0]))


def test_t_starts_at_zero() -> None:
    """engine.t == 0.0 immediately after finalize()."""
    engine = SimEngine()
    engine.module(_ScalarIntegrator(), name="a")
    engine.input("rate", default=0.0)
    engine.finalize()
    assert engine.t == 0.0


def test_module_default_name_is_snake_case() -> None:
    """If no name is given, the module name is derived from the class via snake_case."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator())
    assert m.name == "_scalar_integrator"  # leading underscore preserved


def test_duplicate_module_name_raises() -> None:
    """Two modules with the same name → EngineWiringError immediately."""
    engine = SimEngine()
    engine.module(_ScalarIntegrator(), name="a")
    with pytest.raises(EngineWiringError, match="duplicate module name"):
        engine.module(_ScalarIntegrator(), name="a")
