"""Simulation engine — graph runner for ODE-based component models.

The engine owns global state, calls each component's derivative function,
wires outputs to inputs, and steps time. It has zero domain knowledge:
no physics imports, no awareness of what its components do. It only knows
components, ports, and ODEs.

DEVELOPMENT.md documents the engine for users: "Component Contract" (the
methods and class attributes a component provides) and "Simulation Engine"
(the API, the snapshot dict shape, wiring rules, and finalize-time
validation).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy.integrate import solve_ivp

# A snapshot is a plain dict — we use a TypeAlias for documentation.
Snapshot = dict[str, Any]


class EngineWiringError(Exception):
    """Raised by SimEngine.finalize() (or eagerly during wiring) when the graph
    is invalid.

    Each error names the offending module/port so the fix is obvious from the
    message alone. All wiring problems are detected at setup time, never
    silently at integration time.
    """


@dataclass(frozen=True)
class Signal:
    """Opaque handle to a value in the wiring graph.

    Produced by ``engine.input(name, default)`` (externals), by calling a
    module that has exactly one output port (``Q_sg = sg(...)``), or by
    attribute access on any module (``loop.T_avg``).

    Users pass ``Signal`` objects between modules; they do NOT read values
    off them. Snapshot dicts (returned by ``step()``, ``run()``,
    ``snapshot()``) are the readout path.

    Attributes
    ----------
    name : str
        The canonical signal name. Used as the key in
        ``snapshot["signals"][name]``.
    is_external : bool
        True if produced by ``engine.input(...)``, False if produced by a
        module's output port.
    """

    name: str
    is_external: bool = False
    # Engine-internal pointers (not part of public API). Producer module
    # name and the port on it; both None for externals.
    producer_module: str | None = None
    producer_port: str | None = None
    # The engine that created this handle. finalize() uses it to reject a
    # signal borrowed from a different engine, whose name could otherwise
    # silently alias a local signal. Excluded from equality and hashing so
    # a Signal still compares by what it names, not by the engine object.
    owner: SimEngine | None = field(default=None, repr=False, compare=False)


# Snapshot keys the engine itself writes. A module with one of these names
# would overwrite them (its telemetry dict would replace the time or the
# signals dict), so module() rejects them.
_RESERVED_MODULE_NAMES = frozenset({"t", "signals"})


class _InputsRequested(BaseException):
    """Raised by ``_ProbeInputs`` when a component tries to read an input.

    Derives from ``BaseException`` (like ``KeyboardInterrupt``) so that a
    component's own broad ``except Exception`` cannot swallow or re-wrap it
    and hide the fact that an input was read.
    """


class _ProbeInputs(Mapping):
    """Stand-in ``inputs`` mapping used once per module at finalize time.

    Any attempt to read it (``inputs["x"]``, ``inputs.get("x")``, iteration,
    ``len``) raises ``_InputsRequested``. If a component whose
    ``outputs(state)`` raised ``TypeError`` then reaches for an input here,
    the ``TypeError`` really meant "I need inputs". If it raises
    ``TypeError`` again without touching the mapping, the error came from
    somewhere else inside ``outputs()`` — a bug the engine should report,
    not a reason to reclassify the module.
    """

    def __getitem__(self, key: str) -> Any:
        raise _InputsRequested(key)

    def __iter__(self) -> Iterator[str]:
        raise _InputsRequested("<iteration>")

    def __len__(self) -> int:
        raise _InputsRequested("<len>")


def _find_cycle(remaining: dict[str, set[str]]) -> list[str]:
    """Recover a concrete cycle from a topological-sort residual.

    After Kahn's algorithm leaves nodes in ``remaining`` (each still has at
    least one unsatisfied dependency), walk the dep edges to surface a
    closed cycle for the user. Used to format an actionable error message.

    Parameters
    ----------
    remaining : dict[str, set[str]]
        Map of node names to their unresolved dependency sets, post-Kahn.

    Returns
    -------
    list[str]
        Names of nodes forming the cycle, with the start name repeated at
        the end (e.g. ``["m1", "m2", "m1"]`` for an m1→m2→m1 cycle).
    """
    # Pick any starting node and walk one of its remaining deps repeatedly
    # until we revisit a node — that closing arc is the cycle. Determinism:
    # iterate `sorted(remaining)` and `sorted(remaining[node])` so the same
    # graph always produces the same reported cycle.
    start = sorted(remaining)[0]
    path: list[str] = [start]
    seen = {start}
    while True:
        deps = remaining[path[-1]]
        nxt = sorted(deps)[0]
        if nxt in seen:
            i = path.index(nxt)
            return path[i:] + [nxt]
        path.append(nxt)
        seen.add(nxt)


def _snake_case(camel: str) -> str:
    """Convert a CamelCase class name to snake_case.

    Examples
    --------
    >>> _snake_case("RodController")
    'rod_controller'
    >>> _snake_case("PointKineticsCore")
    'point_kinetics_core'
    >>> _snake_case("_ScalarIntegrator")
    '_scalar_integrator'
    """
    # Insert underscore before each capital that follows a lowercase or digit,
    # then before each capital that precedes a lowercase (handles ABCDef).
    s1 = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", camel)
    s2 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s1)
    return s2.lower()


class SimModule:
    """Wrapper around a physics component that records wiring with the engine.

    Construction is internal; use ``engine.module(component, name=...)`` to
    obtain a SimModule. Users interact through ``__call__`` (records inputs)
    and attribute access (returns Signal handles for output ports).
    """

    def __init__(self, engine: SimEngine, component: Any, name: str) -> None:
        # Use object.__setattr__ to bypass our custom __getattr__ during init.
        object.__setattr__(self, "_engine", engine)
        object.__setattr__(self, "_component", component)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "_state_offset", None)
        object.__setattr__(self, "_state_size", int(getattr(component, "state_size")))
        object.__setattr__(self, "_inputs", {})
        object.__setattr__(self, "_was_called", False)
        object.__setattr__(self, "_output_ports", tuple(getattr(component, "output_ports")))
        object.__setattr__(self, "_input_ports", tuple(getattr(component, "input_ports")))

    # ----- Wiring API -----

    def __call__(self, **inputs: Signal) -> Signal | None:
        """Record this module's input wiring.

        Each kwarg's name must be a port in the underlying component's
        ``input_ports``; each kwarg's value must be a ``Signal`` (produced by
        ``engine.input()``, by another module's call return, or by another
        module's attribute access).

        Each input port can be wired at most once. Calling with a port that's
        already wired raises ``EngineWiringError`` — matches the engine's
        convention for module() and input() (raise on duplicate). To rewire,
        construct a new engine.

        Returns the output ``Signal`` if the component has exactly one output
        port; otherwise returns None and outputs are read via attribute access.
        Calling a module is also legal as a pure side effect.
        """
        for port_name, sig in inputs.items():
            if port_name not in self._input_ports:
                raise EngineWiringError(
                    f"unknown input port '{port_name}' on module '{self.name}'; valid ports: {self._input_ports!r}"
                )
            if not isinstance(sig, Signal):
                raise EngineWiringError(
                    f"module '{self.name}' input '{port_name}' must be a Signal "
                    f"(got {type(sig).__name__}); pass an engine.input(...) handle "
                    f"or another module's output signal"
                )
            if port_name in self._inputs:
                raise EngineWiringError(
                    f"module '{self.name}' input '{port_name}' is already wired "
                    f"(previously to signal '{self._inputs[port_name].name}'); "
                    f"each input port can only be connected once. To rewire, "
                    f"construct a new engine."
                )
            self._inputs[port_name] = sig
        object.__setattr__(self, "_was_called", True)

        if len(self._output_ports) == 1:
            return self._signal_for_output(self._output_ports[0])
        return None

    def __getattr__(self, name: str) -> Signal:
        """Return a Signal handle for the named output port.

        Triggered for attribute names that are not real instance attributes
        (those go through normal lookup). Used to expose state-derived output
        ports as Signal handles before the module is even called — e.g.
        ``loop.T_avg`` works during graph construction.
        """
        # __getattr__ is only called when normal attribute lookup fails (i.e.
        # the name isn't in self.__dict__). The _-prefix early-return is the
        # primary defense against dunder probing during copy/deepcopy/pickle/
        # repr/hasattr — without it, those operations would try to look up
        # __copy__, __getstate__, etc. as output ports and either recurse or
        # raise misleading errors. The init-incomplete fallback is secondary.
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            output_ports = object.__getattribute__(self, "_output_ports")
        except AttributeError as e:
            raise AttributeError(name) from e
        if name not in output_ports:
            module_name = object.__getattribute__(self, "name")
            raise AttributeError(f"module '{module_name}' has no output port '{name}'; output_ports: {output_ports!r}")
        return self._signal_for_output(name)

    # ----- Internal helpers -----

    def _signal_for_output(self, port: str) -> Signal:
        return Signal(
            name=port,
            is_external=False,
            producer_module=self.name,
            producer_port=port,
            owner=self._engine,
        )


class SimEngine:
    """ODE graph runner. Owns global state; orchestrates component execution.

    See module docstring for usage. Lifecycle: construction → wiring (via
    ``module()``, ``input()``, and module ``__call__``) → ``finalize()`` →
    execution (``step()`` or ``run()``).
    """

    def __init__(self) -> None:
        # Module registry, in registration order.
        self._modules: list[SimModule] = []
        self._modules_by_name: dict[str, SimModule] = {}
        # External-input registry: name → default value.
        self._externals: dict[str, Any] = {}
        # Global state vector, allocated at finalize time.
        self._state: np.ndarray | None = None
        self._t: float = 0.0
        self._finalized: bool = False
        # Frozen at finalize: list of (kind, name) tuples describing the
        # eval order each f(t, y) replays. kind is one of "external",
        # "state_derived" (call outputs(state)) or "computed" (call
        # outputs(state, inputs=...)). Set by finalize().
        self._eval_order: list[tuple[str, str]] = []
        # Frozen at finalize: which signals are actually consumed by the
        # graph. Used by snapshot/step/run to filter the signals dict to
        # wired entries only. O(1) lookup vs. linear scan.
        self._consumed_externals: frozenset[str] = frozenset()
        self._consumed_module_outputs: frozenset[tuple[str, str]] = frozenset()

    # ----- Construction -----

    def module(self, component: Any, name: str | None = None) -> SimModule:
        """Register a component with the engine and return its SimModule wrapper.

        Parameters
        ----------
        component : object
            Any object that satisfies the 5-method component API and declares
            ``state_size``, ``state_labels``, ``input_ports``, ``output_ports``
            class attributes.
        name : str, optional
            Module name used as the snapshot dict key. If None, derived from
            the component's class name via snake_case (e.g.
            ``RodController`` → ``"rod_controller"``). ``"t"`` and
            ``"signals"`` are reserved for the snapshot's own keys.

        Returns
        -------
        SimModule
            The wrapper. Use it for wiring (``module(...)``, ``module.<port>``).
        """
        if self._finalized:
            raise EngineWiringError("cannot register modules after finalize(); construct a new engine")
        if name is None:
            name = _snake_case(type(component).__name__)
        if name in _RESERVED_MODULE_NAMES:
            raise EngineWiringError(
                f"module name '{name}' is reserved: snapshots use the keys "
                f"{sorted(_RESERVED_MODULE_NAMES)!r} for time and resolved signals; "
                f"pass a different name=... to engine.module()"
            )
        if name in self._modules_by_name:
            raise EngineWiringError(f"duplicate module name '{name}'")
        m = SimModule(self, component, name)
        self._modules.append(m)
        self._modules_by_name[name] = m
        return m

    def input(self, name: str, default: Any) -> Signal:
        """Declare an external input signal with a default value.

        Externals are signals whose producer is the outside world (operator
        commands, setpoints, etc.) rather than another module. The default
        is used when ``step()``'s kwargs and ``run()``'s ``scenario_fn``
        don't provide a value.
        """
        if self._finalized:
            raise EngineWiringError("cannot declare externals after finalize(); construct a new engine")
        if name in self._externals:
            raise EngineWiringError(f"external '{name}' declared more than once")
        self._externals[name] = default
        return Signal(name=name, is_external=True, owner=self)

    def finalize(self) -> None:
        """Validate the wiring graph and allocate the state vector.

        Validations performed:
        - Every wired Signal was created by this engine (not borrowed from
          another engine, where its name could alias a different value).
        - Every consumer port (kwarg in a module's __call__) has either a
          producer module's output Signal feeding it, or it's an external.
        - Every external declared via input() is consumed at least once.
        - No two modules name the same canonical output signal (i.e., no
          two modules produce a port with the same name AND that signal is
          consumed somewhere), and no consumed module output shares its
          name with a consumed external.
        - Every module's required input_ports are wired (call dict covers
          all entries in component.input_ports).
        - Each module is classified as state-derived or computed (see step
          6); a ``TypeError`` inside a state-derived ``outputs()`` is
          reported here rather than mistaken for "needs inputs".
        - Computed outputs have no algebraic cycle, including a module
          whose computed output feeds its own input.
        """
        if self._finalized:
            return  # idempotent

        # 0. Reject signals created by another engine. A foreign handle's name
        # may not exist here at all (a KeyError at the first snapshot) or,
        # worse, may coincide with an unrelated local signal.
        for m in self._modules:
            for port_name, sig in m._inputs.items():
                if sig.owner is self:
                    continue
                if sig.owner is None:
                    origin = "which was not created by any SimEngine"
                elif sig.is_external:
                    origin = f"from engine.input('{sig.name}', ...) of a different SimEngine"
                else:
                    origin = f"from module '{sig.producer_module}' of a different SimEngine"
                raise EngineWiringError(
                    f"module '{m.name}' input '{port_name}' is wired to signal "
                    f"'{sig.name}' {origin}; obtain signals from this engine's "
                    f"engine.input(...) or one of its modules before wiring them"
                )

        # 1. Build set of all consumed signals across all modules.
        consumed_signals: set[Signal] = set()
        for m in self._modules:
            for sig in m._inputs.values():
                consumed_signals.add(sig)

        # 1b. Precompute which externals and module-output ports are consumed.
        # snapshot/step/run use these for O(1) "is this signal wired?" tests.
        self._consumed_externals = frozenset(sig.name for sig in consumed_signals if sig.is_external)
        self._consumed_module_outputs = frozenset(
            (sig.producer_module, sig.producer_port) for sig in consumed_signals if not sig.is_external
        )

        # 2. Detect two-producers conflict: a signal name that has been
        # consumed and is published by more than one module. Iterate over
        # modules in registration order (rather than over the consumed_signals
        # set) so that when multiple collisions exist, the same one wins
        # deterministically across runs.
        producer_signals: dict[str, set[str]] = {}  # signal name → producer module names
        for m in self._modules:
            for sig in m._inputs.values():
                if sig.is_external:
                    continue
                producer_signals.setdefault(sig.name, set()).add(sig.producer_module)

        for sig_name, producers in producer_signals.items():
            if len(producers) > 1:
                raise EngineWiringError(
                    f"signal '{sig_name}' has more than one producer: "
                    f"modules {sorted(producers)!r} all expose an output "
                    f"port named '{sig_name}'. Rename one in its component's "
                    f"output_ports declaration."
                )
            # snapshot["signals"] is keyed by bare name, so a consumed external
            # and a consumed module output with the same name would overwrite
            # each other there even though consumers see different values.
            if sig_name in self._consumed_externals:
                (producer,) = producers
                raise EngineWiringError(
                    f"signal name '{sig_name}' is used by both external "
                    f"engine.input('{sig_name}', ...) and module '{producer}' "
                    f"output port '{sig_name}'; snapshot['signals'] is keyed by "
                    f"name, so one would hide the other. Rename the external."
                )

        # 3. Check each module's input_ports are all wired.
        for m in self._modules:
            for required_port in m._input_ports:
                if required_port not in m._inputs:
                    raise EngineWiringError(
                        f"module '{m.name}' input '{required_port}' was not "
                        f"connected; either wire it via "
                        f"{m.name}({required_port}=signal) or declare it as an "
                        f"external via engine.input('{required_port}', default=...)"
                    )

        # 4. Check every declared external is consumed.
        consumed_external_names = {sig.name for sig in consumed_signals if sig.is_external}
        for ext_name in self._externals:
            if ext_name not in consumed_external_names:
                raise EngineWiringError(
                    f"external '{ext_name}' declared but never consumed; "
                    f"either wire it into some module's input or remove the "
                    f"engine.input('{ext_name}', ...) call"
                )

        # 5. Allocate state vector and record per-module offsets.
        offset = 0
        chunks: list[np.ndarray] = []
        for m in self._modules:
            object.__setattr__(m, "_state_offset", offset)
            init = np.asarray(m._component.initial_state(), dtype=float)
            if init.shape != (m._state_size,):
                raise EngineWiringError(
                    f"module '{m.name}' initial_state() has shape {init.shape}; expected ({m._state_size},)"
                )
            chunks.append(init)
            offset += m._state_size

        if chunks:
            self._state = np.concatenate(chunks).astype(float, copy=True)
        else:
            self._state = np.empty(0, dtype=float)

        # 6. Classify each module's outputs() as "state-derived" (depends only
        # on state and parameters, evaluated with outputs(state) before any
        # computed module) or "computed" (reads inputs, evaluated with
        # outputs(state, inputs=...) in dependency order). The kind is frozen
        # into _eval_order, so evaluation never re-probes. See _output_kind().
        state_derived: list[SimModule] = []
        computed: list[SimModule] = []
        for m in self._modules:
            if self._output_kind(m) == "computed":
                computed.append(m)
            else:
                state_derived.append(m)

        # 7. Topological sort over the computed modules: each computed module
        # depends on its inputs' producer modules (state-derived dependencies
        # are trivially satisfied because they precede all computed evals).
        # A computed module wired to its own output is the smallest possible
        # algebraic loop: its outputs would need themselves as input.
        computed_names = {m.name for m in computed}
        deps: dict[str, set[str]] = {m.name: set() for m in computed}
        for m in computed:
            for port_name, sig in m._inputs.items():
                if sig.is_external:
                    continue
                producer = sig.producer_module
                if producer == m.name:
                    raise EngineWiringError(
                        f"module '{m.name}' input '{port_name}' is wired to its own "
                        f"output '{sig.name}', but '{m.name}' computes its outputs "
                        f"from its inputs, so the value would depend on itself. "
                        f"Feed '{port_name}' from another module, or route the loop "
                        f"through a module with state."
                    )
                if producer in computed_names:
                    deps[m.name].add(producer)

        # Kahn's algorithm — sorted ready set for deterministic ordering.
        ordered_computed: list[str] = []
        remaining = {name: set(d) for name, d in deps.items()}
        ready = sorted(name for name, d in remaining.items() if not d)
        while ready:
            name = ready.pop(0)
            ordered_computed.append(name)
            del remaining[name]
            newly_ready: list[str] = []
            for other_name, other_deps in remaining.items():
                if name in other_deps:
                    other_deps.discard(name)
                    if not other_deps:
                        newly_ready.append(other_name)
            ready.extend(newly_ready)
            ready.sort()
        if remaining:
            cycle = _find_cycle(remaining)
            raise EngineWiringError(f"cycle detected: {' → '.join(cycle)}")

        # 8. Build the frozen eval_order:
        #    - ('external', name) for each external (declaration order)
        #    - ('state_derived', module_name) for each state-derived module (registration order)
        #    - ('computed', module_name) for each computed module (topological order)
        eval_order: list[tuple[str, str]] = []
        for ext_name in self._externals:
            eval_order.append(("external", ext_name))
        for m in state_derived:
            eval_order.append(("state_derived", m.name))
        for name in ordered_computed:
            eval_order.append(("computed", name))
        self._eval_order = eval_order

        self._finalized = True

    @staticmethod
    def _output_kind(m: SimModule) -> str:
        """Return ``"state_derived"`` or ``"computed"`` for one module.

        A component class may declare its kind with the class attribute
        ``outputs_require_inputs = True`` (computed) or ``False``
        (state-derived); the engine then trusts the declaration and makes
        no probe calls. Without one, the engine infers the kind once, here:

        1. Call ``outputs(state)`` on the initial state. Success means
           state-derived.
        2. On ``TypeError`` (for example an ``outputs()`` that raises it
           when ``inputs`` is None, or one whose ``inputs`` is a required
           keyword), call ``outputs(state, inputs=probe)``
           where ``probe`` raises as soon as it is read. Reading it confirms
           the module is computed. A second ``TypeError`` without reading any
           input means the first error was a bug inside ``outputs()``, which
           is reported rather than silently reclassified.

        Components must keep ``outputs()`` side-effect-free and cheap (no
        I/O, no logging): the probe calls happen once per module here.
        """
        component = m._component
        # Read from the class, as documented: an instance attribute (or a
        # test double such as MagicMock that invents attributes) is ignored.
        declared = getattr(type(component), "outputs_require_inputs", None)
        if declared is not None:
            if not isinstance(declared, bool):
                raise EngineWiringError(
                    f"module '{m.name}': outputs_require_inputs must be True or "
                    f"False, got {declared!r}"
                )
            return "computed" if declared else "state_derived"

        state = component.initial_state()
        try:
            component.outputs(state)
            return "state_derived"
        except TypeError as error:
            first_error = error

        # outputs(state) refused to run. Check that the refusal was about
        # missing inputs by offering a probe mapping that raises when read.
        try:
            component.outputs(state, inputs=_ProbeInputs())
        except TypeError as second_error:
            raise EngineWiringError(
                f"module '{m.name}': outputs(state) raised TypeError "
                f"({first_error}), and so did outputs(state, inputs=...) "
                f"before reading any input ({second_error}). The engine "
                f"treats a TypeError from outputs(state) as 'this module "
                f"needs inputs', so this looks like a bug inside outputs(). "
                f"If the outputs depend only on state, fix the error; if "
                f"they need inputs, set outputs_require_inputs = True on "
                f"{type(component).__name__}."
            ) from first_error
        except (_InputsRequested, Exception):
            # It read an input, or failed some other way after getting past
            # the inputs=None rejection; a genuine bug of that kind surfaces
            # at the first evaluation with real inputs.
            pass
        return "computed"

    # ----- Properties -----

    @property
    def t(self) -> float:
        """Current simulation time."""
        return self._t

    @property
    def state(self) -> np.ndarray:
        """The full global state vector. For debugging only — prefer snapshot()."""
        if self._state is None:
            raise EngineWiringError("engine.state is unavailable until finalize()")
        return self._state

    def restore(self, t: float, state: np.ndarray) -> None:
        """Put the engine back at time ``t`` with global state vector ``state``.

        A checkpoint pair is ``(engine.t, engine.state.copy())`` taken
        before a ``step()``. Restoring it undoes that step, for example when
        the caller finds the step's end state unacceptable. Only time and
        the state vector are restored; external inputs are per-call and have
        nothing to restore.

        Parameters
        ----------
        t : float
            Simulation time to return to [s].
        state : np.ndarray
            Global state vector, same shape as ``engine.state``. It is
            copied, so the caller may keep reusing its array.
        """
        if not self._finalized:
            raise EngineWiringError("engine.restore() requires finalize()")
        y = np.array(state, dtype=float)
        if y.shape != self._state.shape:
            raise ValueError(f"restore() needs a state of shape {self._state.shape}, got {y.shape}")
        self._state = y
        self._t = float(t)

    def snapshot(self) -> Snapshot:
        """Return a snapshot dict reflecting the current state and signals.

        Does not advance time. Replays the wiring graph using the current
        external values (defaults if no overrides are active) and the current
        state vector. The returned dict has the shape described under
        "Snapshot Dict Shape" in DEVELOPMENT.md:
        ``{"t": float, "signals": {...}, "<module>": {...}}``.
        """
        if not self._finalized:
            raise EngineWiringError("engine.snapshot() requires finalize()")
        externals = self._current_external_values()
        signal_values = self._resolve_signal_values(self._state, externals)
        return self._build_snapshot(self._t, self._state, signal_values)

    # ----- Private helpers used by snapshot/step/run -----

    def _current_external_values(self) -> dict[str, Any]:
        """Active external values for the next f(t, y) evaluation.

        For ``snapshot()``, these are the declared defaults. ``step()`` and
        ``run()`` (with ``scenario_fn``) override on a per-call basis via
        their own merged dicts.
        """
        return dict(self._externals)

    def _resolve_signal_values(self, y: np.ndarray, externals: dict[str, Any]) -> dict[str, Any]:
        """Replay the eval_order to compute every consumed signal's value.

        Returns a dict ``{signal_name: value}`` containing only signals that
        appear in the wiring graph (consumed externals + consumed module
        outputs). Unwired outputs aren't tracked.

        This is the single graph-evaluation path: snapshots and the
        ``f(t, y)`` closure handed to ``solve_ivp`` both call it, so what the
        integrator sees and what a snapshot reports cannot diverge.
        """
        signal_values: dict[str, Any] = {}

        for kind, name in self._eval_order:
            if kind == "external":
                if self._is_external_consumed(name):
                    signal_values[name] = externals.get(name, self._externals[name])
                continue
            m = self._modules_by_name[name]
            state_slice = y[m._state_offset : m._state_offset + m._state_size]
            if kind == "state_derived":
                out = m._component.outputs(state_slice)
            elif kind == "computed":
                # Every producer this module reads precedes it in eval_order,
                # so its inputs are already in signal_values.
                inputs = self._inputs_for_module(m, signal_values, externals)
                out = m._component.outputs(state_slice, inputs=inputs)
            else:
                raise AssertionError(f"unknown eval_order kind: {kind!r}")
            # Publish each consumed output port as a signal.
            for port_name, value in out.items():
                if self._is_module_output_consumed(m.name, port_name):
                    signal_values[port_name] = value

        return signal_values

    def _inputs_for_module(
        self,
        m: SimModule,
        signal_values: dict[str, Any],
        externals: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the inputs dict for ``derivatives()`` / ``outputs(inputs=...)``."""
        inputs: dict[str, Any] = {}
        for port_name, sig in m._inputs.items():
            if sig.is_external:
                inputs[port_name] = externals.get(sig.name, self._externals[sig.name])
            else:
                inputs[port_name] = signal_values[sig.name]
        return inputs

    def _is_external_consumed(self, name: str) -> bool:
        return name in self._consumed_externals

    def _is_module_output_consumed(self, module_name: str, port_name: str) -> bool:
        return (module_name, port_name) in self._consumed_module_outputs

    def _build_snapshot(
        self,
        t: float,
        y: np.ndarray,
        signal_values: dict[str, Any],
        externals: dict[str, Any] | None = None,
    ) -> Snapshot:
        """Assemble the full snapshot dict from the resolved signal values.

        ``t`` becomes the ``"t"`` field; it is passed in rather than read
        from ``self._t`` so ``DenseSolution`` can build snapshots at
        intermediate times without touching the engine. Each module's
        telemetry is computed by calling ``component.telemetry(
        state_slice, inputs=...)`` with the same input dict that derivatives
        would see — passing the kwargs-merged externals (if provided),
        otherwise the declared defaults.

        Parameters
        ----------
        t : float
            Simulation time the snapshot describes [s].
        y : np.ndarray
            Global state vector to read state slices from.
        signal_values : dict[str, Any]
            Pre-resolved signal values for the wiring graph.
        externals : dict[str, Any] | None
            Active external values for this snapshot. If None, declared
            defaults (``self._externals``) are used. step() and run() pass
            their merged dicts so telemetry sees the same external values
            that drove the integration; ``snapshot()`` (no override context)
            passes None and gets defaults.
        """
        if externals is None:
            externals = self._current_external_values()
        snap: Snapshot = {"t": float(t), "signals": dict(signal_values)}
        for m in self._modules:
            state_slice = y[m._state_offset : m._state_offset + m._state_size]
            inputs = self._inputs_for_module(m, signal_values, externals)
            tele = m._component.telemetry(state_slice, inputs=inputs)
            snap[m.name] = dict(tele) if tele is not None else {}
        return snap

    # ----- Execution -----

    def step(self, dt: float, **externals: Any) -> Snapshot:
        """Advance the simulation by ``dt`` seconds and return a snapshot.

        Parameters
        ----------
        dt : float
            How far to advance. Must be > 0.
        **externals
            Per-step overrides for declared external inputs. Any keyword not
            in ``self._externals`` raises ``TypeError``. Only affects this
            single step; subsequent ``step()`` calls revert to the declared
            defaults unless re-provided.

        Returns
        -------
        Snapshot
            Engine state after the step (uses the new t and y).
        """
        if not self._finalized:
            self.finalize()

        if not (dt > 0):
            raise ValueError(f"step() requires dt > 0, got {dt!r}")

        for k in externals:
            if k not in self._externals:
                raise TypeError(f"engine has no external named '{k}'")

        # Merge defaults + per-step overrides.
        current_externals = dict(self._externals)
        current_externals.update(externals)

        f = self._build_f(current_externals_provider=lambda t: current_externals)

        sol = solve_ivp(
            f,
            (self._t, self._t + dt),
            self._state,
            method="BDF",
            rtol=1e-6,
            atol=1e-9,
            max_step=0.5,
        )
        if not sol.success:
            raise RuntimeError(f"solve_ivp failed in step(): {sol.message}")

        self._state = sol.y[:, -1].astype(float, copy=True)
        self._t = float(sol.t[-1])

        signal_values = self._resolve_signal_values(self._state, current_externals)
        return self._build_snapshot(self._t, self._state, signal_values, current_externals)

    def _build_f(
        self, current_externals_provider: Callable[[float], dict[str, Any]]
    ) -> Callable[[float, np.ndarray], np.ndarray]:
        """Build the ``f(t, y)`` closure passed to ``solve_ivp``.

        The closure resolves every wired signal with
        ``_resolve_signal_values`` (the same path snapshots use), then asks
        each stateful module for its derivatives.
        ``current_externals_provider(t)`` returns the active external dict at
        simulation time t — for ``step()`` it ignores t (constant per call);
        for ``run()`` it merges ``scenario_fn(t)`` onto defaults.
        """
        modules = self._modules

        def f(t: float, y: np.ndarray) -> np.ndarray:
            externals = current_externals_provider(t)
            signal_values = self._resolve_signal_values(y, externals)

            # Compute derivatives for each module.
            dy = np.empty_like(y)
            for m in modules:
                if m._state_size == 0:
                    continue
                state_slice = y[m._state_offset : m._state_offset + m._state_size]
                inputs = self._inputs_for_module(m, signal_values, externals)
                d = m._component.derivatives(state_slice, inputs=inputs)
                dy[m._state_offset : m._state_offset + m._state_size] = d
            return dy

        return f

    def run(
        self,
        t_end: float,
        scenario_fn: Callable[[float], dict[str, Any]] | None = None,
        *,
        max_step: float = 0.5,
        dense: bool = False,
    ) -> "Snapshot | tuple[Snapshot, DenseSolution]":
        """Integrate from current time to ``t_end`` with one ``solve_ivp`` call.

        Parameters
        ----------
        t_end : float
            Target simulation time. Must be > ``self.t``.
        scenario_fn : callable, optional
            ``scenario_fn(t) -> dict`` returns a partial mapping of external
            names to values. Missing keys fall back to declared defaults.
            If None, externals stay at their defaults for the whole run.
        max_step : float, default 0.5
            Forwarded to ``solve_ivp``'s BDF integrator.
        dense : bool, default False
            If True, also return a :class:`DenseSolution` wrapper for
            evaluating the trajectory at intermediate times.

        Returns
        -------
        Snapshot or tuple[Snapshot, DenseSolution]
            The post-integration snapshot. If ``dense=True``, also a
            :class:`DenseSolution` for sampling the trajectory.
        """
        if not self._finalized:
            self.finalize()
        if not (t_end > self._t):
            raise ValueError(f"run() requires t_end > current t ({self._t}); got t_end={t_end!r}")

        defaults = self._externals

        def make_externals(t: float) -> dict[str, Any]:
            current = dict(defaults)
            if scenario_fn is not None:
                provided = scenario_fn(t)
                for k in provided:
                    if k not in defaults:
                        raise TypeError(f"scenario_fn returned unknown external '{k}'")
                current.update(provided)
            return current

        f = self._build_f(current_externals_provider=make_externals)

        sol = solve_ivp(
            f,
            (self._t, t_end),
            self._state,
            method="BDF",
            rtol=1e-6,
            atol=1e-9,
            max_step=max_step,
            dense_output=dense,
        )
        if not sol.success:
            raise RuntimeError(f"solve_ivp failed in run(): {sol.message}")

        self._state = sol.y[:, -1].astype(float, copy=True)
        self._t = float(sol.t[-1])

        externals = make_externals(self._t)
        signal_values = self._resolve_signal_values(self._state, externals)
        snap = self._build_snapshot(self._t, self._state, signal_values, externals)

        if dense:
            return snap, DenseSolution(
                ode_solution=sol.sol,
                engine=self,
                make_externals=make_externals,
            )
        return snap


class DenseSolution:
    """Adapter from scipy's :class:`OdeSolution` to the engine's snapshot vocabulary.

    Returned by :meth:`SimEngine.run` when called with ``dense=True``. Lets
    callers query the integrated trajectory at arbitrary intermediate times
    (within the run's interval) without re-integrating.
    """

    def __init__(
        self,
        ode_solution,
        engine: SimEngine,
        make_externals: Callable[[float], dict[str, Any]],
    ) -> None:
        self._sol = ode_solution
        self._engine = engine
        self._make_externals = make_externals

    def at(self, t: "float | np.ndarray") -> "Snapshot | list[Snapshot]":
        """Return a snapshot (or list of snapshots) at the given time(s).

        Parameters
        ----------
        t : float or 1D array of floats
            Target evaluation time(s). Must lie within the run's interval.

        Returns
        -------
        Snapshot or list[Snapshot]
            Single snapshot if t is a scalar; list of snapshots if t is an
            array.
        """
        scalar = np.isscalar(t)
        ts = np.atleast_1d(np.asarray(t, dtype=float))
        snaps: list[Snapshot] = []
        for ti in ts:
            y = self._sol(float(ti))
            externals = self._make_externals(float(ti))
            signal_values = self._engine._resolve_signal_values(y, externals)
            snaps.append(self._engine._build_snapshot(float(ti), y, signal_values, externals))
        return snaps[0] if scalar else snaps

    def signal(self, name: str, t: np.ndarray) -> np.ndarray:
        """Return a 1D array of values for a named quantity at the given times.

        Resolution order:

        1. Wired signals from the graph (entries in ``snapshot["signals"]``):
           externals plus module outputs that have at least one consumer.
           This is the strict wiring-graph case.
        2. Per-module telemetry keys (entries in
           ``snapshot["<module>"]``). Useful for sampling unwired outputs
           or internal-state quantities (e.g. a state variable exposed
           via ``telemetry()``) for plotting / inspection.

        If multiple modules expose the same telemetry key, lookup raises
        ``KeyError`` with the candidate modules listed — to avoid silent
        ambiguity. Wire the signal explicitly into a consumer (or query
        with the module-qualified form ``snap['<module>']['<name>']``)
        if you need a specific one.

        Parameters
        ----------
        name : str
            Signal or telemetry key.
        t : 1D array of floats
            Evaluation times. Must lie within the run's interval.

        Returns
        -------
        np.ndarray, shape (len(t),)
            Float array of values.

        Raises
        ------
        KeyError
            If the name is not found in any signal or telemetry, or if it
            appears in multiple modules' telemetry (ambiguous).
        """
        ts = np.atleast_1d(np.asarray(t, dtype=float))
        result = np.empty(ts.shape, dtype=float)
        for i, ti in enumerate(ts):
            y = self._sol(float(ti))
            externals = self._make_externals(float(ti))
            signal_values = self._engine._resolve_signal_values(y, externals)

            if name in signal_values:
                result[i] = float(signal_values[name])
                continue

            # Fallback: per-module telemetry. Detect ambiguity (same key in
            # multiple modules) and raise rather than silently picking one.
            snap = self._engine._build_snapshot(float(ti), y, signal_values, externals)
            module_names = self._engine._modules_by_name
            candidates = [module_name for module_name in module_names if name in snap[module_name]]
            if not candidates:
                all_tele_keys = sorted({k for module_name in module_names for k in snap[module_name]})
                raise KeyError(
                    f"signal '{name}' not found at t={float(ti)}; "
                    f"available signals: {sorted(signal_values)!r}; "
                    f"available module telemetry keys: {all_tele_keys!r}"
                )
            if len(candidates) > 1:
                raise KeyError(
                    f"signal '{name}' is ambiguous at t={float(ti)} — "
                    f"appears in modules {candidates!r}. Use snap['<module>']['{name}'] "
                    f"to disambiguate, or wire one as a graph signal."
                )
            result[i] = float(snap[candidates[0]][name])
        return result


__all__ = [
    "DenseSolution",
    "EngineWiringError",
    "Signal",
    "SimEngine",
    "SimModule",
    "Snapshot",
]
