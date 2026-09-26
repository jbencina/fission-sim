"""Tests for the model's supported physical domain (physics/domain.py).

Each limit is checked just inside and at/past its boundary. The
end-to-end halt through the runtime is in
tests/api/test_runtime_model_limit.py.
"""

import pytest

from fission_sim.physics.domain import P_MAX, P_MIN, ModelDomainError, check_primary_domain

# Design-point values, as the engine snapshot reports them.
DESIGN = dict(P=15.5e6, T_sat=617.9, T_hot=597.7, M_loop=123_400.0, x_pzr=0.146)


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"P": P_MIN},
        {"P": P_MAX},
        {"x_pzr": 1e-6},
        {"x_pzr": 1.0 - 1e-6},
        {"T_hot": 617.9 - 0.01},
    ],
    ids=["design", "P_min", "P_max", "nearly_solid", "nearly_dry", "barely_subcooled"],
)
def test_states_inside_domain_pass(overrides):
    check_primary_domain(**{**DESIGN, **overrides})


@pytest.mark.parametrize(
    ("overrides", "limit", "message"),
    [
        ({"T_hot": float("nan")}, "non_finite", "non-numeric value for T_hot"),
        ({"M_loop": 0.0}, "loop_inventory", "run out of water"),
        ({"P": P_MIN - 1.0}, "pressure", "below the model's 1 MPa floor"),
        ({"P": P_MAX + 1.0}, "pressure", "critical point"),
        ({"x_pzr": 0.0}, "pressurizer_solid", "no steam is left"),
        ({"x_pzr": 1.0}, "pressurizer_dry", "no liquid water is left"),
        ({"T_hot": 617.9}, "hot_leg_subcooling", "boiling point"),
    ],
    ids=["non_finite", "no_inventory", "below_P_min", "above_P_max", "solid", "dry", "at_saturation"],
)
def test_states_outside_domain_raise_named_limit(overrides, limit, message):
    with pytest.raises(ModelDomainError, match=message) as exc_info:
        check_primary_domain(**{**DESIGN, **overrides})
    assert exc_info.value.limit == limit


def test_subcooling_message_reports_values_for_a_learner():
    with pytest.raises(ModelDomainError, match=r"T_hot = 620\.0 K.*617\.9 K at 15\.50 MPa"):
        check_primary_domain(**{**DESIGN, "T_hot": 620.0})
