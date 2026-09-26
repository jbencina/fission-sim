"""Compare hand-wired plants with ``build_standard_plant()``.

``examples/run_primary.py`` and the DEVELOPMENT.md engine tutorial both
spell out the standard plant's wiring by hand. ``plant_topology`` reduces an
engine to a comparable description so their tests can check that each copy
still matches the factory.
"""

from __future__ import annotations

import dataclasses

import numpy as np


def _plain(value):
    """Turn a parameter dataclass into nested tuples that compare with ``==``
    (numpy array fields such as the delayed-neutron constants become tuples)."""
    if dataclasses.is_dataclass(value):
        return tuple((f.name, _plain(getattr(value, f.name))) for f in dataclasses.fields(value))
    if isinstance(value, np.ndarray):
        return tuple(value.tolist())
    return value


def plant_topology(engine) -> tuple:
    """Describe an engine's plant: each module's name, component class and
    parameters, what feeds each of its input ports, and the external inputs
    with their defaults."""
    # Reads engine internals (_modules, _inputs, _externals) because SimEngine
    # has no public graph-inspection API.
    modules = tuple(
        (
            m.name,
            type(m._component).__name__,
            _plain(m._component.params),
            tuple(
                sorted(
                    (port, sig.name, sig.is_external, sig.producer_module, sig.producer_port)
                    for port, sig in m._inputs.items()
                )
            ),
        )
        for m in engine._modules
    )
    return modules, dict(engine._externals)
