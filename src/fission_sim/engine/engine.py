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
        self._engine = engine
        self._component = component
        self.name = name
        # State-vector slice indices, populated by engine.finalize().
        self._state_offset: int | None = None
        self._state_size: int = int(getattr(component, "state_size"))
        # Recorded input wiring (port_name → Signal). Populated by __call__.
        self._inputs: dict[str, Signal] = {}
        # Set in __call__: was the call form used at all? (Some modules may
        # be wired purely via attribute access; we track this for diagnostics.)
        self._was_called: bool = False


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

        After this call, the engine is ready to ``step()`` or ``run()``. The
        topology is locked.
        """
        if self._finalized:
            return  # idempotent

        # Allocate state vector and record per-module offsets.
        offset = 0
        chunks: list[np.ndarray] = []
        for m in self._modules:
            m._state_offset = offset
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
