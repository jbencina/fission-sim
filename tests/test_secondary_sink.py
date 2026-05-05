"""Tests for src/fission_sim/physics/secondary_sink.py.

Layers 2 and 3 do not apply to this component (no time evolution, no analytical
formula to compare against — the implementation IS the trivial constant).
"""

import numpy as np
import pytest

from fission_sim.physics.secondary_sink import SecondarySink, SinkParams


def default_params() -> SinkParams:
    """Return the project-wide default sink parameter set."""
    return SinkParams()


def test_state_layout_indices():
    sink = SecondarySink(default_params())
    assert sink.state_size == 0
    assert sink.state_labels == ()


def test_initial_state_is_empty():
    sink = SecondarySink(default_params())
    s = sink.initial_state()
    assert s.shape == (0,)


def test_derivatives_returns_empty():
    sink = SecondarySink(default_params())
    d = sink.derivatives(np.empty(0))
    assert d.shape == (0,)


def test_outputs_constant_T_secondary():
    p = default_params()
    sink = SecondarySink(p)
    out = sink.outputs(np.empty(0))
    assert out == {"T_secondary": pytest.approx(p.T_secondary)}


def test_outputs_ignores_inputs():
    """Sink takes no inputs; passing any value should not change behavior."""
    p = default_params()
    sink = SecondarySink(p)
    out_with = sink.outputs(np.empty(0), inputs={"Q_sg": 1.0e9})
    out_without = sink.outputs(np.empty(0))
    assert out_with == out_without
