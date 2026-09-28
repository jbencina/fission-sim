"""M3 acceptance tests: secondary side, turbine and automatic rod control."""

from __future__ import annotations

import numpy as np
import pytest

from fission_sim.physics.domain import ModelDomainError, check_secondary_domain, check_snapshot
from fission_sim.physics.sg_secondary import SGSecondaryParams
from fission_sim.plant import build_standard_plant
from fission_sim.validation.secondary_acceptance import (
    AUTO_TAVG_TREF_TOL,
    ENERGY_BALANCE_FRAC,
    HUGE_SHELL_TAVG_TOL,
    MANUAL_N_BAND,
    MANUAL_P_STEAM_BAND,
    MANUAL_TAVG_BAND,
    MASS_DRIFT_LIMIT,
    SCRAM_N_MAX,
    STEADY_LEVEL_TOL,
    STEADY_LOAD_TOL,
    STEADY_N_TOL,
    STEADY_P_STEAM_TOL,
    STEADY_TAVG_TOL,
    STEAM_PRESSURE_MAX_ON_TRIP,
    TRANSIENT_ENERGY_BALANCE_FRAC,
    TRIP_N_BAND,
    TRIP_P_STEAM_BAND,
    TRIP_TAVG_BAND,
    ramp_to,
    run_dense,
    secondary_energy_fraction,
    series,
)
from fission_sim.validation.secondary_acceptance import (
    DT as _DT,
)

DT = _DT


def run(engine, t_end, scenario, check=True):
    """Step with a scenario dict-of-externals function; return sampled snapshots."""
    return run_dense(engine, t_end, scenario, check=check)


def _assert_between(value: float, band: tuple[float, float]) -> None:
    assert band[0] < value < band[1]


def test_design_steady_state_holds_600s():
    eng = build_standard_plant()
    snaps = run(eng, 600.0, lambda t: {})
    assert abs(series(snaps, "core", "n")[-1] - 1.0) < STEADY_N_TOL
    assert abs(series(snaps, "loop", "T_avg")[-1] - 583.0) < STEADY_TAVG_TOL
    assert abs(series(snaps, "sg_sec", "P_steam")[-1] - SGSecondaryParams().P_ref) < STEADY_P_STEAM_TOL
    assert abs(series(snaps, "sg_sec", "level_sg")[-1] - 0.5) < STEADY_LEVEL_TOL
    assert abs(series(snaps, "turbine", "load")[-1] - 1.0) < STEADY_LOAD_TOL


def test_secondary_energy_balance_closes_at_steady_state():
    eng = build_standard_plant()
    snap = run(eng, 60.0, lambda t: {})[-1]
    assert secondary_energy_fraction(snap) < ENERGY_BALANCE_FRAC


def test_shell_mass_is_conserved_when_feedwater_matches_steam():
    eng = build_standard_plant()
    snaps = run(eng, 300.0, lambda t: {"turbine_load": 0.8 if t > 10 else 1.0})
    M = series(snaps, "sg_sec", "M_sec")
    assert np.max(np.abs(M - M[0])) < MASS_DRIFT_LIMIT


def test_load_reduction_rods_manual_reactor_follows_turbine():
    """A 10 % admission cut settles near measured A6 values.

    ``turbine_load`` is valve admission, not fixed MW demand: when admission
    falls, steam pressure rises, so the actual steam flow and core power fall
    by only a few percent in this L1 model.
    """
    eng = build_standard_plant()
    snaps = run(eng, 1500.0, ramp_to(0.9))
    n = series(snaps, "core", "n")
    T_avg = series(snaps, "loop", "T_avg")
    P_steam = series(snaps, "sg_sec", "P_steam")
    _assert_between(n[-1], MANUAL_N_BAND)
    _assert_between(T_avg[-1], MANUAL_TAVG_BAND)
    _assert_between(P_steam[-1], MANUAL_P_STEAM_BAND)
    assert T_avg[-1] > 583.5
    assert P_steam[-1] > P_steam[0] + 1e5
    assert secondary_energy_fraction(snaps[-1]) < TRANSIENT_ENERGY_BALANCE_FRAC


def test_load_reduction_rods_auto_returns_to_program():
    eng = build_standard_plant(rod_auto=True)
    base = ramp_to(0.9)
    snaps = run(eng, 1800.0, lambda t: {**base(t), "rod_auto": True})
    T_avg = series(snaps, "loop", "T_avg")
    T_ref = series(snaps, "turbine", "T_ref")
    rod = series(snaps, "rod", "rod_position")
    assert abs(T_ref[-1] - (565.0 + 18.0 * 0.9)) < 1e-6
    assert abs(T_avg[-1] - T_ref[-1]) <= AUTO_TAVG_TREF_TOL
    assert rod[-1] < 0.5
    assert 0.85 < series(snaps, "core", "n")[-1] < 0.95


def test_turbine_trip_without_scram_stays_in_domain():
    """The dump limits pressure while power settles to the dump steam flow."""
    eng = build_standard_plant()
    snaps = run(eng, 600.0, lambda t: {"turbine_trip": t >= 10.0})
    P_steam = series(snaps, "sg_sec", "P_steam")
    m_dump = series(snaps, "turbine", "m_dump")
    assert P_steam.max() < STEAM_PRESSURE_MAX_ON_TRIP
    assert m_dump.max() > 0.0
    assert series(snaps, "turbine", "load")[-1] < 1e-3
    _assert_between(series(snaps, "core", "n")[-1], TRIP_N_BAND)
    _assert_between(series(snaps, "loop", "T_avg")[-1], TRIP_TAVG_BAND)
    _assert_between(P_steam[-1], TRIP_P_STEAM_BAND)


def test_scram_alone_trips_turbine_via_p4_and_stays_in_domain():
    eng = build_standard_plant()
    snaps = run(eng, 600.0, lambda t: {"scram": t >= 10.0})
    assert series(snaps, "turbine", "load")[-1] < 1e-3
    assert series(snaps, "sg_sec", "P_steam").max() < STEAM_PRESSURE_MAX_ON_TRIP
    assert series(snaps, "core", "n")[-1] < SCRAM_N_MAX


def test_turbine_trip_with_scram_cooldown_in_domain():
    eng = build_standard_plant()
    snaps = run(eng, 900.0, lambda t: {"turbine_trip": t >= 10.0, "scram": t >= 10.0})
    assert series(snaps, "core", "n")[-1] < SCRAM_N_MAX
    T_hot = series(snaps, "loop", "T_hot")
    T_sat = series(snaps, "pzr", "T_sat")
    assert np.all(T_sat - T_hot > 0.0)


def test_huge_shell_volume_reproduces_fixed_secondary():
    """With V_sec 1e5 times larger, steam pressure cannot move: the M2 plant."""
    from .test_pressurizer_plant import build_m2_plant

    def scenario(t):
        return {"scram": t >= 10.0}

    m2 = build_m2_plant()
    m3 = build_standard_plant(sg_sec_params=SGSecondaryParams(V_sec=6.0e7))
    a = run(m2, 300.0, scenario, check=False)
    b = run(m3, 300.0, scenario, check=False)
    dT = series(a, "loop", "T_avg") - series(b, "loop", "T_avg")
    assert np.max(np.abs(dT)) < HUGE_SHELL_TAVG_TOL


def test_steam_pressure_limit_fires_before_property_failure():
    """Review Focus 3: a shell whose pressure collapsed reports a model limit."""
    with pytest.raises(ModelDomainError) as err:
        check_secondary_domain(P_steam=0.4e6, x_sg=0.05)
    assert err.value.limit == "steam_pressure"
    with pytest.raises(ModelDomainError) as err:
        check_secondary_domain(P_steam=7.0e6, x_sg=1.0)
    assert err.value.limit == "sg_dry"
    with pytest.raises(ModelDomainError) as err:
        check_secondary_domain(P_steam=7.0e6, x_sg=0.0)
    assert err.value.limit == "sg_solid"


def test_build_standard_plant_rejects_nan_and_clips_high_default_load():
    with pytest.raises(ValueError, match="turbine_load must be finite"):
        build_standard_plant(turbine_load=float("nan"))
    assert build_standard_plant(turbine_load=1.5).snapshot()["signals"]["turbine_load"] == pytest.approx(1.0)


def test_snapshot_without_secondary_still_checks():
    """M2-style plants do not carry ``sg_sec`` and should still be checkable."""
    from .test_pressurizer_plant import build_m2_plant

    check_snapshot(build_m2_plant().snapshot())
