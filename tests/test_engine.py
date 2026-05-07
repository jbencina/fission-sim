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


def test_topological_order_is_stable() -> None:
    """Building the same graph twice produces the same eval order."""

    def build():
        engine = SimEngine()
        a = engine.module(_ScalarIntegrator(), name="a")
        rate = engine.input("rate", default=0.0)
        a(rate=rate)
        engine.finalize()
        return engine

    e1 = build()
    e2 = build()
    assert e1._eval_order == e2._eval_order


def test_topological_order_state_derived_before_computed() -> None:
    """State-derived outputs come before computed outputs in eval order."""

    class _Computed:
        """Reads an input and produces a computed output."""

        state_size = 0
        state_labels: tuple = ()
        input_ports = ("upstream",)
        output_ports = ("y",)

        def initial_state(self):
            return np.empty(0)

        def derivatives(self, state, inputs):
            return np.empty(0)

        def outputs(self, state, inputs=None):
            if inputs is None:
                raise TypeError("requires inputs")
            return {"y": float(inputs["upstream"])}

        def telemetry(self, state, inputs=None):
            return {}

    engine = SimEngine()
    a = engine.module(_ScalarIntegrator(), name="a")  # state-derived output 'x'
    c = engine.module(_Computed(), name="c")  # computed output 'y'
    rate = engine.input("rate", default=0.0)
    a(rate=rate)
    c(upstream=a.x)
    engine.finalize()

    a_pos = next(i for i, e in enumerate(engine._eval_order) if e == ("output", "a"))
    c_pos = next(i for i, e in enumerate(engine._eval_order) if e == ("output", "c"))
    assert a_pos < c_pos


def test_cycle_in_computed_outputs_raises() -> None:
    """A cycle through computed outputs (stateless modules) → EngineWiringError."""

    class _ComputedAB:
        """Stateless: output 'a' depends on input 'b'."""

        state_size = 0
        state_labels: tuple = ()
        input_ports = ("b",)
        output_ports = ("a",)

        def initial_state(self):
            return np.empty(0)

        def derivatives(self, state, inputs):
            return np.empty(0)

        def outputs(self, state, inputs=None):
            if inputs is None:
                raise TypeError("requires inputs")
            return {"a": float(inputs["b"])}

        def telemetry(self, state, inputs=None):
            return {}

    class _ComputedBA:
        """Stateless: output 'b' depends on input 'a'. Closes the cycle."""

        state_size = 0
        state_labels: tuple = ()
        input_ports = ("a",)
        output_ports = ("b",)

        def initial_state(self):
            return np.empty(0)

        def derivatives(self, state, inputs):
            return np.empty(0)

        def outputs(self, state, inputs=None):
            if inputs is None:
                raise TypeError("requires inputs")
            return {"b": float(inputs["a"])}

        def telemetry(self, state, inputs=None):
            return {}

    engine = SimEngine()
    m1 = engine.module(_ComputedAB(), name="m1")
    m2 = engine.module(_ComputedBA(), name="m2")
    m1(b=m2.b)
    m2(a=m1.a)
    with pytest.raises(EngineWiringError, match="cycle detected"):
        engine.finalize()


def test_cycle_error_message_shows_path() -> None:
    """The cycle error message lists the actual path, not just participants."""

    class _ComputedAB:
        state_size = 0
        state_labels: tuple = ()
        input_ports = ("b",)
        output_ports = ("a",)

        def initial_state(self):
            return np.empty(0)

        def derivatives(self, state, inputs):
            return np.empty(0)

        def outputs(self, state, inputs=None):
            if inputs is None:
                raise TypeError
            return {"a": float(inputs["b"])}

        def telemetry(self, state, inputs=None):
            return {}

    class _ComputedBA:
        state_size = 0
        state_labels: tuple = ()
        input_ports = ("a",)
        output_ports = ("b",)

        def initial_state(self):
            return np.empty(0)

        def derivatives(self, state, inputs):
            return np.empty(0)

        def outputs(self, state, inputs=None):
            if inputs is None:
                raise TypeError
            return {"b": float(inputs["a"])}

        def telemetry(self, state, inputs=None):
            return {}

    engine = SimEngine()
    m1 = engine.module(_ComputedAB(), name="m1")
    m2 = engine.module(_ComputedBA(), name="m2")
    m1(b=m2.b)
    m2(a=m1.a)
    with pytest.raises(EngineWiringError) as exc_info:
        engine.finalize()
    msg = str(exc_info.value)
    # The message should mention both modules and use the → arrow:
    assert "m1" in msg and "m2" in msg and "→" in msg


def test_snapshot_initial_state_after_finalize() -> None:
    """snapshot() returns the initial state values pre-integration."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(x0=7.0), name="m")
    rate = engine.input("rate", default=0.0)
    m(rate=rate)
    engine.finalize()
    snap = engine.snapshot()
    assert snap["t"] == 0.0
    assert "signals" in snap
    assert "m" in snap


def test_snapshot_signals_includes_external_value() -> None:
    """An external used in a wiring shows up in snapshot['signals'] with its default."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(), name="m")
    rate = engine.input("rate", default=2.5)
    m(rate=rate)
    engine.finalize()
    snap = engine.snapshot()
    assert snap["signals"]["rate"] == pytest.approx(2.5)


def test_snapshot_signals_includes_state_derived_output() -> None:
    """A state-derived output a downstream module consumes shows up in signals."""

    class _Consumer:
        state_size = 0
        state_labels: tuple = ()
        input_ports = ("foo",)
        output_ports = ()

        def initial_state(self):
            return np.empty(0)

        def derivatives(self, state, inputs):
            return np.empty(0)

        def outputs(self, state, inputs=None):
            return {}

        def telemetry(self, state, inputs=None):
            return {}

    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(x0=11.0), name="m")
    c = engine.module(_Consumer(), name="c")
    rate = engine.input("rate", default=0.0)
    m(rate=rate)
    c(foo=m.x)
    engine.finalize()
    snap = engine.snapshot()
    assert snap["signals"]["x"] == pytest.approx(11.0)


def test_snapshot_signals_includes_computed_output() -> None:
    """A computed module's output is evaluated using already-resolved inputs."""

    class _Times2:
        state_size = 0
        state_labels: tuple = ()
        input_ports = ("y",)
        output_ports = ("z",)

        def initial_state(self):
            return np.empty(0)

        def derivatives(self, state, inputs):
            return np.empty(0)

        def outputs(self, state, inputs=None):
            if inputs is None:
                raise TypeError
            return {"z": 2.0 * float(inputs["y"])}

        def telemetry(self, state, inputs=None):
            return {}

    class _Sink:
        state_size = 0
        state_labels: tuple = ()
        input_ports = ("zin",)
        output_ports = ()

        def initial_state(self):
            return np.empty(0)

        def derivatives(self, state, inputs):
            return np.empty(0)

        def outputs(self, state, inputs=None):
            return {}

        def telemetry(self, state, inputs=None):
            return {}

    engine = SimEngine()
    src = engine.module(_ScalarIntegrator(x0=4.0), name="src")
    times2 = engine.module(_Times2(), name="t2")
    sink = engine.module(_Sink(), name="snk")
    rate = engine.input("rate", default=0.0)
    src(rate=rate)
    times2(y=src.x)
    sink(zin=times2.z)
    engine.finalize()
    snap = engine.snapshot()
    assert snap["signals"]["x"] == pytest.approx(4.0)
    assert snap["signals"]["z"] == pytest.approx(8.0)


def test_snapshot_includes_module_telemetry() -> None:
    """Each module's telemetry(state) appears under snap[<module_name>]."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(x0=9.0), name="m")
    rate = engine.input("rate", default=0.0)
    m(rate=rate)
    engine.finalize()
    snap = engine.snapshot()
    assert snap["m"] == {"x": 9.0}


def test_snapshot_for_stateless_module_has_empty_telemetry_dict() -> None:
    """A stateless module with empty telemetry shows up as snap['name'] == {}."""

    class _Empty:
        state_size = 0
        state_labels: tuple = ()
        input_ports = ()
        output_ports = ("c",)

        def initial_state(self):
            return np.empty(0)

        def derivatives(self, state, inputs=None):
            return np.empty(0)

        def outputs(self, state, inputs=None):
            return {"c": 1.0}

        def telemetry(self, state, inputs=None):
            return {}

    class _Reader:
        state_size = 0
        state_labels: tuple = ()
        input_ports = ("c",)
        output_ports = ()

        def initial_state(self):
            return np.empty(0)

        def derivatives(self, state, inputs=None):
            return np.empty(0)

        def outputs(self, state, inputs=None):
            return {}

        def telemetry(self, state, inputs=None):
            return {}

    engine = SimEngine()
    e = engine.module(_Empty(), name="e")
    r = engine.module(_Reader(), name="r")
    r(c=e.c)
    engine.finalize()
    snap = engine.snapshot()
    assert snap["e"] == {}
