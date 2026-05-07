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
    a = engine.module(_ScalarIntegrator(x0=1.0), name="a")
    b = engine.module(_ScalarIntegrator(x0=2.0), name="b")
    rate = engine.input("rate", default=0.0)
    a(rate=rate)
    b(rate=rate)
    engine.finalize()
    assert engine.state.shape == (2,)


def test_initial_state_assembled_from_modules() -> None:
    """engine.state matches concatenated module initial_state() values."""
    engine = SimEngine()
    a = engine.module(_ScalarIntegrator(x0=3.0), name="a")
    b = engine.module(_ScalarIntegrator(x0=5.0), name="b")
    rate = engine.input("rate", default=0.0)
    a(rate=rate)
    b(rate=rate)
    engine.finalize()
    np.testing.assert_array_equal(engine.state, np.array([3.0, 5.0]))


def test_t_starts_at_zero() -> None:
    """engine.t == 0.0 immediately after finalize()."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(), name="a")
    rate = engine.input("rate", default=0.0)
    m(rate=rate)
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


def test_call_records_input_wiring() -> None:
    """Calling a module with kwargs records each kwarg as an input wire."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(), name="m")
    rate = engine.input("rate", default=0.0)
    m(rate=rate)
    assert m._inputs == {"rate": rate}
    assert m._was_called is True


def test_getattr_returns_signal_for_known_output() -> None:
    """module.<port> returns a Signal naming the producer module/port."""
    from fission_sim.engine import Signal

    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(), name="m")
    sig = m.x
    assert isinstance(sig, Signal)
    assert sig.name == "x"
    assert sig.producer_module == "m"
    assert sig.producer_port == "x"
    assert sig.is_external is False


def test_getattr_unknown_port_raises_attributeerror() -> None:
    """module.<port> for a port not in output_ports raises AttributeError."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(), name="m")
    with pytest.raises(AttributeError, match="has no output port 'foo'"):
        _ = m.foo


def test_call_returns_signal_when_one_output() -> None:
    """A module with exactly one output port: __call__ returns that Signal."""
    from fission_sim.engine import Signal

    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(), name="m")
    rate = engine.input("rate", default=0.0)
    out = m(rate=rate)
    assert isinstance(out, Signal)
    assert out.name == "x"


def test_call_returns_none_when_multiple_outputs() -> None:
    """A module with >1 output: __call__ returns None; use attribute access."""

    class _MultiOut:
        state_size = 1
        state_labels = ("x",)
        input_ports = ("rate",)
        output_ports = ("x", "y")

        def initial_state(self):
            return np.array([0.0])

        def derivatives(self, state, inputs):
            return np.array([0.0])

        def outputs(self, state, inputs=None):
            return {"x": float(state[0]), "y": -float(state[0])}

        def telemetry(self, state, inputs=None):
            return {}

    engine = SimEngine()
    m = engine.module(_MultiOut(), name="m")
    rate = engine.input("rate", default=0.0)
    result = m(rate=rate)
    assert result is None


def test_input_returns_external_signal() -> None:
    """engine.input() returns a Signal marked is_external=True with the given name."""
    from fission_sim.engine import Signal

    engine = SimEngine()
    sig = engine.input("rod_command", default=0.5)
    assert isinstance(sig, Signal)
    assert sig.name == "rod_command"
    assert sig.is_external is True
    assert sig.producer_module is None


def test_call_twice_with_same_port_raises() -> None:
    """Wiring the same input port twice → EngineWiringError."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(), name="m")
    rate1 = engine.input("rate", default=0.0)
    m(rate=rate1)
    with pytest.raises(EngineWiringError, match="already wired"):
        m(rate=rate1)


def test_dangling_input_raises() -> None:
    """A module with an unwired input → EngineWiringError at finalize."""
    engine = SimEngine()
    engine.module(_ScalarIntegrator(), name="m")  # has input 'rate' — never wired
    with pytest.raises(EngineWiringError, match="module 'm' input 'rate' was not connected"):
        engine.finalize()


def test_two_producers_for_same_signal_raises() -> None:
    """Two modules whose output port has the same canonical name → error."""

    class _Consumer:
        state_size = 0
        state_labels: tuple = ()
        input_ports = ("foo",)
        output_ports = ()

        def initial_state(self):
            return np.empty(0)

        def derivatives(self, state, inputs=None):
            return np.empty(0)

        def outputs(self, state, inputs=None):
            return {}

        def telemetry(self, state, inputs=None):
            return {}

    # _ScalarIntegrator's only output is named "x". Wire each module's "x"
    # into a dedicated consumer to make both producers visible.
    engine = SimEngine()
    a = engine.module(_ScalarIntegrator(), name="a")
    b = engine.module(_ScalarIntegrator(), name="b")
    rate_a = engine.input("rate_a", default=0.0)
    rate_b = engine.input("rate_b", default=0.0)
    a(rate=rate_a)
    b(rate=rate_b)
    c1 = engine.module(_Consumer(), name="c1")
    c2 = engine.module(_Consumer(), name="c2")
    c1(foo=a.x)
    c2(foo=b.x)
    with pytest.raises(EngineWiringError, match="signal 'x' has more than one producer"):
        engine.finalize()


def test_unused_external_raises() -> None:
    """An external declared but never consumed → EngineWiringError at finalize."""
    engine = SimEngine()
    engine.input("ghost", default=1.0)  # never used
    # Need at least one wired module to make the rest of finalize valid.
    m = engine.module(_ScalarIntegrator(), name="m")
    rate = engine.input("rate", default=0.0)
    m(rate=rate)
    with pytest.raises(EngineWiringError, match="external 'ghost' declared but never consumed"):
        engine.finalize()


def test_finalize_succeeds_for_minimal_valid_graph() -> None:
    """A trivially valid graph (one module + one external wired in) finalizes cleanly."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(), name="m")
    rate = engine.input("rate", default=0.0)
    m(rate=rate)
    engine.finalize()  # no raise
    assert engine.state.shape == (1,)
