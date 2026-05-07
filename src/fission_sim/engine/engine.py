"""Simulation engine — graph runner for ODE-based component models.

The engine owns global state, calls each component's derivative function,
wires outputs to inputs, and steps time. It has zero domain knowledge:
no physics imports, no awareness of what its components do. It only knows
components, ports, and ODEs.

See docs/superpowers/specs/2026-05-07-simulation-engine-design.md for the
design spec, including wiring semantics, snapshot structure, and validation
rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import numpy as np

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
        # eval order each f(t, y) replays. Set by finalize().
        self._eval_order: list[tuple[str, str]] = []

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
            ``RodController`` → ``"rod_controller"``).

        Returns
        -------
        SimModule
            The wrapper. Use it for wiring (``module(...)``, ``module.<port>``).
        """
        if self._finalized:
            raise EngineWiringError("cannot register modules after finalize(); construct a new engine")
        if name is None:
            name = _snake_case(type(component).__name__)
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
        return Signal(name=name, is_external=True)

    def finalize(self) -> None:
        """Validate the wiring graph and allocate the state vector.

        Validations performed:
        - Every consumer port (kwarg in a module's __call__) has either a
          producer module's output Signal feeding it, or it's an external.
        - Every external declared via input() is consumed at least once.
        - No two modules name the same canonical output signal (i.e., no
          two modules produce a port with the same name AND that signal is
          consumed somewhere).
        - Every module's required input_ports are wired (call dict covers
          all entries in component.input_ports).
        """
        if self._finalized:
            return  # idempotent

        # 1. Build set of all consumed signals across all modules.
        consumed_signals: set[Signal] = set()
        for m in self._modules:
            for sig in m._inputs.values():
                consumed_signals.add(sig)

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

        # 6. Classify modules by their outputs() *signature* (not by the math
        # they compute). A module is "state-derived" if outputs(state) — i.e.
        # the call without an inputs kwarg — succeeds; "computed" if it
        # raises TypeError. The eval order treats state-derived modules as
        # having no input dependencies (they're evaluated in registration
        # order before any computed modules).
        #
        # Note: this calls component.outputs() once per module at finalize
        # time. Components must keep outputs(state) side-effect-free and
        # cheap (no I/O, no logging) — the call may also be repeated in the
        # snapshot/step paths.
        state_derived: list[SimModule] = []
        computed: list[SimModule] = []
        for m in self._modules:
            try:
                state_slice = m._component.initial_state()
                m._component.outputs(state_slice)
                state_derived.append(m)
            except TypeError:
                computed.append(m)

        # 7. Topological sort over the computed modules: each computed module
        # depends on its inputs' producer modules (state-derived dependencies
        # are trivially satisfied because they precede all computed evals).
        computed_names = {m.name for m in computed}
        deps: dict[str, set[str]] = {m.name: set() for m in computed}
        for m in computed:
            for sig in m._inputs.values():
                if sig.is_external:
                    continue
                producer = sig.producer_module
                if producer in computed_names and producer != m.name:
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
        #    - ('output', module_name) for each state-derived module (registration order)
        #    - ('output', module_name) for each computed module (topological order)
        eval_order: list[tuple[str, str]] = []
        for ext_name in self._externals:
            eval_order.append(("external", ext_name))
        for m in state_derived:
            eval_order.append(("output", m.name))
        for name in ordered_computed:
            eval_order.append(("output", name))
        self._eval_order = eval_order

        self._finalized = True

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


class DenseSolution:
    """Stub; populated in Task 11."""


__all__ = [
    "DenseSolution",
    "EngineWiringError",
    "Signal",
    "SimEngine",
    "SimModule",
    "Snapshot",
]
