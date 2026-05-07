"""Tests for src/fission_sim/physics/steam_generator.py.

The L1 SG is purely algebraic: Q_sg = UA * (T_avg - T_secondary). Layers 2
(short-integration) and 3 (textbook formula comparison) do not apply — the
implementation IS the formula, and there is no time evolution to integrate.
"""

import numpy as np
import pytest

from fission_sim.physics.steam_generator import SGParams, SteamGenerator


def default_params() -> SGParams:
    """Return the project-wide default SG parameter set."""
    return SGParams()


def _design_inputs(p: SGParams) -> dict:
    """Inputs that, with default params, yield Q_sg == Q_design."""
    return {"T_avg": p.T_primary_ref, "T_secondary": p.T_secondary_ref}


def test_state_layout_indices():
    sg = SteamGenerator(default_params())
    assert sg.state_size == 0
    assert sg.state_labels == ()


def test_initial_state_is_empty():
    sg = SteamGenerator(default_params())
    assert sg.initial_state().shape == (0,)


def test_derivatives_returns_empty():
    sg = SteamGenerator(default_params())
    d = sg.derivatives(np.empty(0), inputs=_design_inputs(default_params()))
    assert d.shape == (0,)


def test_design_q_matches():
    """At reference T_avg and T_secondary, Q_sg should equal Q_design."""
    p = default_params()
    sg = SteamGenerator(p)
    out = sg.outputs(np.empty(0), inputs=_design_inputs(p))
    assert out["Q_sg"] == pytest.approx(p.Q_design, rel=1e-9)


def test_q_scales_with_delta_t():
    """Doubling (T_avg - T_secondary) should exactly double Q_sg."""
    p = default_params()
    sg = SteamGenerator(p)
    delta_T_design = p.T_primary_ref - p.T_secondary_ref
    out_1 = sg.outputs(
        np.empty(0),
        inputs={
            "T_avg": p.T_secondary_ref + delta_T_design,
            "T_secondary": p.T_secondary_ref,
        },
    )
    out_2 = sg.outputs(
        np.empty(0),
        inputs={
            "T_avg": p.T_secondary_ref + 2 * delta_T_design,
            "T_secondary": p.T_secondary_ref,
        },
    )
    assert out_2["Q_sg"] == pytest.approx(2 * out_1["Q_sg"])


def test_zero_delta_t_zero_q():
    """T_avg == T_secondary should give Q_sg == 0."""
    p = default_params()
    sg = SteamGenerator(p)
    out = sg.outputs(
        np.empty(0),
        inputs={
            "T_avg": 600.0,
            "T_secondary": 600.0,
        },
    )
    assert out["Q_sg"] == pytest.approx(0.0)
