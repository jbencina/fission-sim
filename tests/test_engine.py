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

    a_pos = engine._eval_order.index(("state_derived", "a"))
    c_pos = engine._eval_order.index(("computed", "c"))
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


class _Sink:
    """Toy: stateless module that only consumes one input (makes a signal 'wired')."""

    state_size = 0
    state_labels: tuple = ()
    input_ports = ("inp",)
    output_ports = ()

    def initial_state(self):
        return np.empty(0)

    def derivatives(self, state, inputs=None):
        return np.empty(0)

    def outputs(self, state, inputs=None):
        return {}

    def telemetry(self, state, inputs=None):
        return {}


class _Doubler:
    """Toy computed module: output 'value' = 2 * input 'upstream'.

    Declares no ``outputs_require_inputs``, so the engine infers the kind from
    its probe: outputs(state) without inputs raises TypeError. Counts those
    input-less calls so tests can check the engine probes only once, at
    finalize.
    """

    state_size = 0
    state_labels: tuple = ()
    input_ports = ("upstream",)
    output_ports = ("value",)

    def __init__(self) -> None:
        self.calls_without_inputs = 0

    def initial_state(self):
        return np.empty(0)

    def derivatives(self, state, inputs=None):
        return np.empty(0)

    def outputs(self, state, inputs=None):
        if inputs is None:
            self.calls_without_inputs += 1
            raise TypeError("_Doubler.outputs requires inputs")
        return {"value": 2.0 * float(inputs["upstream"])}

    def telemetry(self, state, inputs=None):
        return {}


def test_computed_outputs_not_reprobed_after_finalize() -> None:
    """The computed/state-derived split is decided once at finalize, not per evaluation."""
    engine = SimEngine()
    src = engine.module(_ScalarIntegrator(x0=4.0), name="src")
    doubler = _Doubler()
    d = engine.module(doubler, name="d")
    engine.module(_Sink(), name="snk")(inp=d(upstream=src.x))
    src(rate=engine.input("rate", default=1.0))
    engine.finalize()
    assert doubler.calls_without_inputs == 1

    engine.step(dt=1.0)
    snap = engine.snapshot()
    assert snap["signals"]["value"] == pytest.approx(10.0)
    assert doubler.calls_without_inputs == 1


def test_state_derived_typeerror_is_reported_at_finalize() -> None:
    """An unrelated TypeError inside a state-derived outputs() is a bug, not 'needs inputs'."""

    class _Buggy(_ScalarIntegrator):
        def outputs(self, state, inputs=None):
            return {"x": state[0] + None}

    engine = SimEngine()
    b = engine.module(_Buggy(), name="b")
    b(rate=engine.input("rate", default=0.0))
    with pytest.raises(EngineWiringError, match=r"module 'b': outputs\(state\) raised TypeError"):
        engine.finalize()


def test_outputs_require_inputs_declaration_is_honored() -> None:
    """A declared-computed module gets its inputs even if outputs(state) would succeed.

    Without the declaration, the default-returning branch would make the
    module look state-derived and 'value' would silently stay 0.0.
    """

    class _DeclaredDoubler(_Doubler):
        outputs_require_inputs = True

        def outputs(self, state, inputs=None):
            if inputs is None:
                return {"value": 0.0}
            return {"value": 2.0 * float(inputs["upstream"])}

    engine = SimEngine()
    src = engine.module(_ScalarIntegrator(x0=3.0), name="src")
    d = engine.module(_DeclaredDoubler(), name="d")
    engine.module(_Sink(), name="snk")(inp=d(upstream=src.x))
    src(rate=engine.input("rate", default=0.0))
    engine.finalize()
    assert engine.snapshot()["signals"]["value"] == pytest.approx(6.0)


def test_signal_from_another_engine_raises() -> None:
    """A Signal created by a different engine cannot be wired in."""
    foreign = SimEngine().input("rate", default=9.0)
    engine = SimEngine()
    engine.module(_ScalarIntegrator(), name="m")(rate=foreign)
    with pytest.raises(EngineWiringError, match="input 'rate' .* different SimEngine"):
        engine.finalize()


def test_computed_self_dependency_raises() -> None:
    """A computed module whose output feeds its own input is an algebraic loop."""
    engine = SimEngine()
    d = engine.module(_Doubler(), name="d")
    d(upstream=d.value)
    with pytest.raises(EngineWiringError, match="module 'd' input 'upstream' is wired to its own output"):
        engine.finalize()


def test_external_and_module_output_with_same_name_raises() -> None:
    """snapshot['signals'] is keyed by name, so an external and a wired output cannot share one."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(), name="m")  # output port 'x'
    m(rate=engine.input("x", default=5.0))
    engine.module(_Sink(), name="snk")(inp=m.x)
    with pytest.raises(EngineWiringError, match="'x' is used by both external .* module 'm'"):
        engine.finalize()


class T(_ScalarIntegrator):
    """Toy whose snake_case class name is the reserved module name 't'."""


@pytest.mark.parametrize(
    ("component", "name", "reserved"),
    [
        (_ScalarIntegrator(), "t", "t"),
        (_ScalarIntegrator(), "signals", "signals"),
        (T(), None, "t"),  # name derived from the class name
    ],
)
def test_reserved_module_name_raises(component: object, name: str | None, reserved: str) -> None:
    """'t' and 'signals' are snapshot keys; a module with that name would overwrite them."""
    engine = SimEngine()
    with pytest.raises(EngineWiringError, match=f"module name '{reserved}' is reserved"):
        engine.module(component, name=name)


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


def test_step_advances_time_by_dt() -> None:
    """One step(dt=...) advances engine.t by exactly dt."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(x0=0.0), name="m")
    rate = engine.input("rate", default=1.0)
    m(rate=rate)
    engine.finalize()
    snap = engine.step(dt=0.5)
    assert snap["t"] == pytest.approx(0.5)
    assert engine.t == pytest.approx(0.5)


def test_step_integrates_state() -> None:
    """An integrator with rate=2.0 and dt=3.0 advances state by 6.0."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(x0=0.0), name="m")
    rate = engine.input("rate", default=2.0)
    m(rate=rate)
    engine.finalize()
    snap = engine.step(dt=3.0)
    assert snap["m"]["x"] == pytest.approx(6.0, rel=1e-5)


def test_step_external_default_used_when_missing() -> None:
    """If step() doesn't provide a kwarg, the declared default is used."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(x0=0.0), name="m")
    rate = engine.input("rate", default=4.0)
    m(rate=rate)
    engine.finalize()
    snap = engine.step(dt=1.0)
    assert snap["m"]["x"] == pytest.approx(4.0, rel=1e-5)


def test_restore_undoes_a_step() -> None:
    """restore() with a pre-step checkpoint returns t and state to it, so the
    next step reproduces the undone one (the runtime's model-limit rollback)."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(x0=1.0), name="m")
    rate = engine.input("rate", default=2.0)
    m(rate=rate)
    engine.finalize()
    engine.step(dt=0.5)
    t0, y0 = engine.t, engine.state.copy()
    first = engine.step(dt=0.5)

    engine.restore(t0, y0)
    assert engine.t == t0
    assert engine.snapshot()["m"]["x"] == pytest.approx(2.0, rel=1e-5)
    assert engine.step(dt=0.5)["m"]["x"] == pytest.approx(first["m"]["x"], rel=1e-9)

    with pytest.raises(ValueError, match="shape"):
        engine.restore(t0, np.zeros(2))


def test_step_kwarg_overrides_default() -> None:
    """If step() provides a kwarg, that value is used instead of the default."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(x0=0.0), name="m")
    rate = engine.input("rate", default=4.0)
    m(rate=rate)
    engine.finalize()
    snap = engine.step(dt=1.0, rate=10.0)
    assert snap["m"]["x"] == pytest.approx(10.0, rel=1e-5)


def test_step_unknown_external_kwarg_raises_typeerror() -> None:
    """step(foo=...) with unknown external → TypeError."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(), name="m")
    rate = engine.input("rate", default=0.0)
    m(rate=rate)
    engine.finalize()
    with pytest.raises(TypeError, match="no external named 'foo'"):
        engine.step(dt=0.1, foo=1.0)


def test_step_kwarg_only_affects_one_step() -> None:
    """A kwarg passed to step() does NOT persist; the next step uses the default."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(x0=0.0), name="m")
    rate = engine.input("rate", default=1.0)
    m(rate=rate)
    engine.finalize()
    engine.step(dt=1.0, rate=10.0)  # x advances by ~10
    snap = engine.step(dt=1.0)  # next step uses default rate=1.0
    # Total advancement: 10 + 1 = 11.
    assert snap["m"]["x"] == pytest.approx(11.0, rel=1e-5)


def test_step_telemetry_sees_overridden_external() -> None:
    """telemetry() during step(rate=X) should see rate=X, not the default.

    Regression guard: snapshots returned by step() must thread the
    kwargs-merged externals through to per-module telemetry, so a component
    whose telemetry echoes its inputs sees the values that actually drove
    the integration.
    """

    class _RateEcho:
        """Stateless: telemetry echoes the rate input."""

        state_size = 0
        state_labels: tuple = ()
        input_ports = ("rate",)
        output_ports = ()

        def initial_state(self):
            return np.empty(0)

        def derivatives(self, state, inputs=None):
            return np.empty(0)

        def outputs(self, state, inputs=None):
            return {}

        def telemetry(self, state, inputs=None):
            return {"rate_seen": float(inputs["rate"]) if inputs else None}

    engine = SimEngine()
    echo = engine.module(_RateEcho(), name="echo")
    rate = engine.input("rate", default=1.0)
    echo(rate=rate)
    engine.finalize()
    snap = engine.step(dt=0.1, rate=42.0)
    assert snap["echo"]["rate_seen"] == pytest.approx(42.0)


def test_step_zero_dt_raises() -> None:
    """step(dt=0) raises ValueError."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(), name="m")
    rate = engine.input("rate", default=0.0)
    m(rate=rate)
    engine.finalize()
    with pytest.raises(ValueError, match="dt > 0"):
        engine.step(dt=0.0)


def test_step_negative_dt_raises() -> None:
    """step(dt<0) raises ValueError."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(), name="m")
    rate = engine.input("rate", default=0.0)
    m(rate=rate)
    engine.finalize()
    with pytest.raises(ValueError, match="dt > 0"):
        engine.step(dt=-0.5)


def test_run_advances_to_t_end() -> None:
    """run(t_end) advances engine.t to exactly t_end."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(x0=0.0), name="m")
    rate = engine.input("rate", default=1.0)
    m(rate=rate)
    engine.finalize()
    snap = engine.run(t_end=5.0)
    assert snap["t"] == pytest.approx(5.0)
    assert engine.t == pytest.approx(5.0)


def test_run_integrates_with_default_externals() -> None:
    """run() with default externals produces the expected integrated state."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(x0=0.0), name="m")
    rate = engine.input("rate", default=2.0)
    m(rate=rate)
    engine.finalize()
    snap = engine.run(t_end=5.0)
    assert snap["m"]["x"] == pytest.approx(10.0, rel=1e-5)


def test_run_with_scenario_fn() -> None:
    """scenario_fn(t) → dict overrides externals during integration."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(x0=0.0), name="m")
    rate = engine.input("rate", default=0.0)
    m(rate=rate)
    engine.finalize()

    # rate = 1.0 for t < 5, 3.0 for t >= 5. Total over [0,10]:
    # 5 * 1.0 + 5 * 3.0 = 20.0.
    def scenario(t: float) -> dict:
        return {"rate": 1.0 if t < 5.0 else 3.0}

    snap = engine.run(t_end=10.0, scenario_fn=scenario)
    assert snap["m"]["x"] == pytest.approx(20.0, rel=1e-3)


def test_run_dense_returns_dense_solution() -> None:
    """run(dense=True) returns (snapshot, DenseSolution)."""
    from fission_sim.engine import DenseSolution

    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(x0=0.0), name="m")
    rate = engine.input("rate", default=1.0)
    m(rate=rate)
    engine.finalize()
    result = engine.run(t_end=5.0, dense=True)
    assert isinstance(result, tuple)
    snap, dense = result
    assert isinstance(snap, dict)
    assert isinstance(dense, DenseSolution)


def test_dense_at_returns_snapshot() -> None:
    """DenseSolution.at(t) returns a snapshot evaluated at intermediate time t."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(x0=0.0), name="m")
    rate = engine.input("rate", default=1.0)
    m(rate=rate)
    engine.finalize()
    _, dense = engine.run(t_end=10.0, dense=True)
    mid = dense.at(5.0)
    assert mid["t"] == pytest.approx(5.0)
    assert mid["m"]["x"] == pytest.approx(5.0, rel=1e-3)


def test_dense_signal_returns_array() -> None:
    """DenseSolution.signal(name, t_array) returns a 1D array of values."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(x0=0.0), name="m")
    rate = engine.input("rate", default=2.0)
    m(rate=rate)
    engine.finalize()
    _, dense = engine.run(t_end=10.0, dense=True)
    ts = np.array([0.0, 5.0, 10.0])
    xs = dense.signal("x", ts)
    np.testing.assert_allclose(xs, np.array([0.0, 10.0, 20.0]), rtol=1e-3, atol=1e-5)


def test_run_unknown_external_in_scenario_raises() -> None:
    """If scenario_fn returns a dict with an undeclared external, raise TypeError."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(), name="m")
    rate = engine.input("rate", default=0.0)
    m(rate=rate)
    engine.finalize()

    def bad_scenario(t):
        return {"rate": 1.0, "ghost": 99.0}

    with pytest.raises(TypeError, match="unknown external 'ghost'"):
        engine.run(t_end=1.0, scenario_fn=bad_scenario)


def test_dense_signal_unwired_output_via_telemetry() -> None:
    """signal() falls back to module telemetry when a name isn't in the wiring graph.

    Documented escape hatch for plotting unwired outputs / internal-state
    quantities. The telemetry must contain exactly one match — ambiguous
    keys raise.
    """
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(x0=0.0), name="m")
    rate = engine.input("rate", default=2.0)
    m(rate=rate)
    engine.finalize()
    _, dense = engine.run(t_end=4.0, dense=True)
    # 'x' is _ScalarIntegrator's output (unwired here) AND its only
    # telemetry key. The fallback resolves it.
    xs = dense.signal("x", np.array([0.0, 2.0, 4.0]))
    np.testing.assert_allclose(xs, np.array([0.0, 4.0, 8.0]), rtol=1e-3, atol=1e-5)


def test_dense_signal_ambiguous_telemetry_raises() -> None:
    """Two modules with the same telemetry key → signal() raises KeyError."""
    engine = SimEngine()
    a = engine.module(_ScalarIntegrator(x0=1.0), name="a")
    b = engine.module(_ScalarIntegrator(x0=2.0), name="b")
    rate = engine.input("rate", default=0.0)
    a(rate=rate)
    b(rate=rate)
    engine.finalize()
    _, dense = engine.run(t_end=1.0, dense=True)
    # Both 'a' and 'b' expose telemetry key 'x'; neither is wired.
    with pytest.raises(KeyError, match="ambiguous"):
        dense.signal("x", np.array([0.5]))


def test_dense_signal_unknown_name_raises() -> None:
    """signal() with a name nowhere in signals or telemetry → KeyError."""
    engine = SimEngine()
    m = engine.module(_ScalarIntegrator(), name="m")
    rate = engine.input("rate", default=0.0)
    m(rate=rate)
    engine.finalize()
    _, dense = engine.run(t_end=1.0, dense=True)
    with pytest.raises(KeyError, match="not found"):
        dense.signal("zzz_nonexistent", np.array([0.5]))


# ---------------------------------------------------------------------------
# Layer 2 — integration with real physics components (the full plant)
# ---------------------------------------------------------------------------

from fission_sim.control.pressurizer_controller import (  # noqa: E402
    PressurizerController,
    PressurizerControllerParams,
)
from fission_sim.physics.core import CoreParams, PointKineticsCore  # noqa: E402
from fission_sim.physics.pressurizer import Pressurizer, PressurizerParams  # noqa: E402
from fission_sim.physics.primary_loop import LoopParams, PrimaryLoop  # noqa: E402
from fission_sim.physics.rod_controller import RodController, RodParams  # noqa: E402
from fission_sim.physics.secondary_sink import SecondarySink, SinkParams  # noqa: E402
from fission_sim.physics.steam_generator import SGParams, SteamGenerator  # noqa: E402


def _assemble_full_plant() -> tuple[SimEngine, dict]:
    """Build the full plant via the engine: rod, core, loop, sg, sink, pzr, pzr_ctrl."""
    engine = SimEngine()
    loop_params = LoopParams()
    pzr_params = PressurizerParams(loop_params=loop_params)
    ctrl_params = PressurizerControllerParams()

    rod = engine.module(RodController(RodParams()), name="rod")
    core = engine.module(PointKineticsCore(CoreParams()), name="core")
    loop = engine.module(PrimaryLoop(loop_params), name="loop")
    sg = engine.module(SteamGenerator(SGParams()), name="sg")
    sink = engine.module(SecondarySink(SinkParams()), name="sink")
    pzr = engine.module(Pressurizer(pzr_params), name="pzr")
    pzr_ctrl = engine.module(PressurizerController(ctrl_params), name="pzr_ctrl")

    rod_cmd = engine.input("rod_command", default=0.5)
    scram = engine.input("scram", default=False)
    P_setpoint = engine.input("P_setpoint", default=ctrl_params.P_setpoint_default)
    heater_manual = engine.input("heater_manual", default=None)
    spray_manual = engine.input("spray_manual", default=None)

    rod(rod_command=rod_cmd, scram=scram)
    T_sec = sink()
    Q_sg = sg(T_avg=loop.T_avg, T_secondary=T_sec)
    core(rho_rod=rod.rho_rod, T_cool=loop.T_cool)
    pzr(
        Q_fuel_to_coolant=core.Q_fuel_to_coolant,
        Q_sg=Q_sg,
        T_hotleg=loop.T_hot,
        T_coldleg=loop.T_cold,
        Q_heater=pzr_ctrl.Q_heater,
        m_dot_spray=pzr_ctrl.m_dot_spray,
    )
    pzr_ctrl(
        P=pzr.P,
        P_setpoint=P_setpoint,
        heater_manual=heater_manual,
        spray_manual=spray_manual,
    )
    loop(
        Q_fuel_to_coolant=core.Q_fuel_to_coolant,
        Q_sg=Q_sg,
        m_dot_spray=pzr_ctrl.m_dot_spray,
        P_primary=pzr.P,
    )
    engine.finalize()
    return engine, {
        "rod": rod,
        "core": core,
        "loop": loop,
        "sg": sg,
        "sink": sink,
        "pzr": pzr,
        "pzr_ctrl": pzr_ctrl,
    }


def test_engine_assembles_full_plant() -> None:
    """The full plant assembles via the engine; every module's state is laid out."""
    engine, _modules = _assemble_full_plant()
    plant_classes = (
        RodController,
        PointKineticsCore,
        PrimaryLoop,
        SteamGenerator,
        SecondarySink,
        Pressurizer,
        PressurizerController,
    )
    assert engine.state.shape == (sum(cls.state_size for cls in plant_classes),)


def test_engine_steady_state_holds() -> None:
    """At default operator inputs, the plant holds steady for 30 s."""
    engine, _modules = _assemble_full_plant()
    snap = engine.run(t_end=30.0)
    # n stays within 0.1% of 1.0; T_avg within 0.5 K of design.
    assert snap["core"]["n"] == pytest.approx(1.0, rel=1e-3)
    T_avg_design = (snap["loop"]["T_hot"] + snap["loop"]["T_cold"]) / 2.0
    # Loop's design T_avg is around 580 K — loose bound to allow for
    # slight design-point drift.
    assert 575.0 < T_avg_design < 585.0


def test_engine_step_then_run_match_for_full_plant() -> None:
    """run(t_end=10) equals the result of 100 step(dt=0.1) calls (within tol)."""
    engine_a, _ = _assemble_full_plant()
    snap_a = engine_a.run(t_end=10.0)

    engine_b, _ = _assemble_full_plant()
    for _ in range(100):
        engine_b.step(dt=0.1)
    snap_b = engine_b.snapshot()

    # Compare the consequential signals.
    assert snap_a["core"]["n"] == pytest.approx(snap_b["core"]["n"], rel=1e-3)
    assert snap_a["loop"]["T_hot"] == pytest.approx(snap_b["loop"]["T_hot"], rel=1e-4)
    assert snap_a["loop"]["T_cold"] == pytest.approx(snap_b["loop"]["T_cold"], rel=1e-4)


# ---------------------------------------------------------------------------
# Layer 3 — independent oracle: engine trajectory vs. a closed-form solution
# ---------------------------------------------------------------------------


def test_engine_run_matches_analytic_closed_loop() -> None:
    """A mass under a PD controller, wired through the engine, matches expm(A t).

    The graph has the same shape as the plant: a stateful module with
    state-derived outputs (position x, velocity v) and a stateless computed
    module (the controller) whose output feeds the stateful module's
    derivatives. The closed loop is linear,

        x'' = -(k/m) (x - x_ref) - (c/m) x',

    so with z = [x - x_ref, v] the exact solution is z(t) = expm(A t) z(0),
    A = [[0, 1], [-k/m, -c/m]]. That oracle shares no code with the engine.
    """
    from scipy.linalg import expm

    mass, k, c, x_ref = 2.0, 8.0, 1.6, 1.0  # ω0 = 2 rad/s, ζ = 0.2 (underdamped)

    class _Mass:
        state_size = 2
        state_labels = ("x", "v")
        input_ports = ("force",)
        output_ports = ("x", "v")

        def initial_state(self):
            return np.array([0.0, 0.0])

        def derivatives(self, state, inputs):
            return np.array([state[1], inputs["force"] / mass])

        def outputs(self, state, inputs=None):
            return {"x": float(state[0]), "v": float(state[1])}

        def telemetry(self, state, inputs=None):
            return {"x": float(state[0]), "v": float(state[1])}

    class _PDController:
        state_size = 0
        state_labels: tuple = ()
        input_ports = ("x", "v", "x_ref")
        output_ports = ("force",)

        def initial_state(self):
            return np.empty(0)

        def derivatives(self, state, inputs):
            return np.empty(0)

        def outputs(self, state, inputs=None):
            if inputs is None:
                raise TypeError("_PDController.outputs requires inputs")
            return {"force": -k * (inputs["x"] - inputs["x_ref"]) - c * inputs["v"]}

        def telemetry(self, state, inputs=None):
            return {}

    engine = SimEngine()
    plant = engine.module(_Mass(), name="plant")
    ctrl = engine.module(_PDController(), name="ctrl")
    force = ctrl(x=plant.x, v=plant.v, x_ref=engine.input("x_ref", default=x_ref))
    plant(force=force)
    _, dense = engine.run(t_end=10.0, dense=True)

    A = np.array([[0.0, 1.0], [-k / mass, -c / mass]])
    z0 = np.array([0.0 - x_ref, 0.0])
    ts = np.array([0.5, 1.7, 3.0, 6.0, 10.0])
    exact = np.array([expm(A * t) @ z0 for t in ts])
    exact_x, exact_v = exact[:, 0] + x_ref, exact[:, 1]

    # Solver tolerances are rtol=1e-6, atol=1e-9 per step; 1e-4 absolute on
    # O(1) quantities leaves room for accumulated global error.
    for t, x, v in zip(ts, exact_x, exact_v):
        snap = dense.at(float(t))
        assert snap["plant"]["x"] == pytest.approx(x, abs=1e-4)
        assert snap["plant"]["v"] == pytest.approx(v, abs=1e-4)
    # The computed signal seen by the integrator is also what dense output reports.
    np.testing.assert_allclose(dense.signal("force", ts), -k * (exact_x - x_ref) - c * exact_v, atol=1e-3)
