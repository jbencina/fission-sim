"""Tests for the model's supported physical domain (physics/domain.py).

Each limit is checked just inside and at/past its boundary. The
end-to-end halt through the runtime is in
tests/api/test_runtime_model_limit.py.
"""

import pytest

from fission_sim.physics import coolprop
from fission_sim.physics.domain import (
    P_MAX,
    P_MIN,
    P_STEAM_MAX,
    P_STEAM_MIN,
    ModelDomainError,
    check_primary_domain,
    check_secondary_domain,
    check_snapshot,
)
from fission_sim.physics.sg_secondary import SGSecondaryParams
from fission_sim.plant import build_standard_plant

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


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"P_steam": P_STEAM_MIN},
        {"P_steam": P_STEAM_MAX},
        {"x_sg": 1e-6},
        {"x_sg": 1.0 - 1e-6},
        {"level_sg": 0.30},
        {"level_sg": 0.95},
    ],
    ids=["design", "P_min", "P_max", "nearly_solid", "nearly_dry", "low_level_edge", "high_level_edge"],
)
def test_secondary_states_inside_domain_pass(overrides):
    p = SGSecondaryParams()
    check_secondary_domain(**{**{"P_steam": p.P_ref, "x_sg": 0.05}, **overrides})


@pytest.mark.parametrize(
    ("overrides", "limit", "message"),
    [
        ({"P_steam": float("nan")}, "non_finite", "non-numeric value for P_steam"),
        ({"P_steam": P_STEAM_MIN - 1.0}, "steam_pressure", "configured feedwater would flash near"),
        ({"P_steam": P_STEAM_MAX + 1.0}, "steam_pressure", "above the model's 12 MPa ceiling"),
        ({"x_sg": 0.0}, "sg_solid", "filled solid"),
        ({"x_sg": 1.0}, "sg_dry", "boiled dry"),
        ({"level_sg": 0.29}, "sg_tubes_uncovered", "top of the tube bundle"),
        ({"level_sg": 0.96}, "sg_overfill", "carry over into the steam lines"),
    ],
    ids=["non_finite", "below_P_min", "above_P_max", "solid", "dry", "tubes_uncovered", "overfill"],
)
def test_secondary_states_outside_domain_raise_named_limit(overrides, limit, message):
    p = SGSecondaryParams()
    with pytest.raises(ModelDomainError, match=message) as exc_info:
        check_secondary_domain(**{**{"P_steam": p.P_ref, "x_sg": 0.05, "P_fw_flash": p.P_fw_flash}, **overrides})
    assert exc_info.value.limit == limit


def test_steam_pressure_floor_keeps_feedwater_liquid():
    assert P_STEAM_MIN > coolprop.P_sat(T=SGSecondaryParams().T_fw)
    assert SGSecondaryParams().P_fw_flash == pytest.approx(coolprop.P_sat(T=SGSecondaryParams().T_fw))


def test_snapshot_uses_configured_feedwater_flash_pressure():
    sg_params = SGSecondaryParams(T_fw=540.0)
    snap = build_standard_plant(sg_sec_params=sg_params).snapshot()
    assert snap["sg_sec"]["P_fw_flash"] > P_STEAM_MIN
    snap["sg_sec"]["P_steam"] = 4.46e6
    expected_flash = rf"configured feedwater would flash near {sg_params.P_fw_flash / 1e6:.2f} MPa"
    with pytest.raises(ModelDomainError, match=expected_flash) as exc_info:
        check_snapshot(snap)
    assert exc_info.value.limit == "steam_pressure"


def test_standard_plant_snapshot_is_inside_domain():
    check_snapshot(build_standard_plant().snapshot())


def test_snapshot_with_secondary_dry_raises_sg_dry():
    snap = build_standard_plant().snapshot()
    snap["sg_sec"]["x"] = 1.0
    with pytest.raises(ModelDomainError) as exc_info:
        check_snapshot(snap)
    assert exc_info.value.limit == "sg_dry"


def test_snapshot_with_low_sg_level_raises_tube_uncovering():
    snap = build_standard_plant().snapshot()
    snap["sg_sec"]["level_sg"] = 0.29
    with pytest.raises(ModelDomainError) as exc_info:
        check_snapshot(snap)
    assert exc_info.value.limit == "sg_tubes_uncovered"


def test_snapshot_without_secondary_still_checks_primary_domain():
    check_snapshot(
        {
            "loop": {"T_hot": DESIGN["T_hot"], "M_loop": DESIGN["M_loop"]},
            "pzr": {"P": DESIGN["P"], "T_sat": DESIGN["T_sat"], "x": DESIGN["x_pzr"]},
        }
    )
