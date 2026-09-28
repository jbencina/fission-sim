"""M4 acceptance tests: SG level dynamics and three-element feedwater control."""

from __future__ import annotations

import numpy as np
import pytest

from fission_sim.control.feedwater_controller import FeedwaterControllerParams
from fission_sim.physics.domain import ModelDomainError, check_snapshot
from fission_sim.physics.feedwater import FeedwaterParams
from fission_sim.physics.sg_secondary import SGSecondaryParams
from fission_sim.plant import build_standard_plant
from fission_sim.validation.secondary_acceptance import (
    TRANSIENT_ENERGY_ACCUMULATION_FRAC,
    secondary_energy_accumulation_fraction,
)
from tests.test_secondary_plant import ramp_to, run, series


def _integrated_net_mass(snaps: list[dict]) -> np.ndarray:
    """Return ``∫(m_fw − m_steam − m_dump)dt`` over sampled snapshots."""
    m_fw = series(snaps, "feedwater", "m_fw")
    m_out = series(snaps, "turbine", "m_steam") + series(snaps, "turbine", "m_dump")
    t = np.array([snap["t"] for snap in snaps], dtype=float)
    net = np.zeros_like(m_fw)
    net[1:] = np.cumsum(0.5 * ((m_fw - m_out)[1:] + (m_fw - m_out)[:-1]) * np.diff(t))
    return net


def test_level_holds_at_setpoint():
    snaps = run(build_standard_plant(), 600.0, lambda t: {})
    level = series(snaps, "sg_sec", "level_sg")
    assert np.max(np.abs(level - 0.5)) < 1e-3
    m_fw = series(snaps, "feedwater", "m_fw")
    m_out = series(snaps, "turbine", "m_steam") + series(snaps, "turbine", "m_dump")
    assert abs(m_fw[-1] - m_out[-1]) < 0.005 * m_out[-1]


def test_shell_mass_matches_integrated_flows():
    snaps = run(build_standard_plant(), 600.0, ramp_to(0.8))
    M = series(snaps, "sg_sec", "M_sec")
    net = _integrated_net_mass(snaps)
    assert np.max(np.abs((M - M[0]) - net)) < 1e-3 * M[0]
    assert abs(M[-1] - M[0]) > 100.0
    assert secondary_energy_accumulation_fraction(snaps) < TRANSIENT_ENERGY_ACCUMULATION_FRAC


def test_load_ramp_level_excursion_and_recovery():
    base = ramp_to(0.9)
    snaps = run(build_standard_plant(rod_auto=True), 1800.0, lambda t: {**base(t), "rod_auto": True})
    level = series(snaps, "sg_sec", "level_sg")
    assert np.max(np.abs(level - 0.5)) < 0.05
    assert abs(level[-1] - 0.5) < 0.005


def test_level_setpoint_step():
    snaps = run(build_standard_plant(), 1200.0, lambda t: {"level_setpoint": 0.55 if t >= 10.0 else 0.5})
    level = series(snaps, "sg_sec", "level_sg")
    assert abs(level[-1] - 0.55) < 0.01
    assert level.max() < 0.57


def test_loss_of_feedwater_halts_at_tube_uncovering():
    """Review Focus 4: loss of feedwater stops at the tube-uncovering limit."""
    eng = build_standard_plant()
    t_halt = None
    t = 0.0
    while t < 600.0:
        snap = eng.step(1.0, feedwater_manual=0.0 if t >= 10.0 else None)
        t = snap["t"]
        try:
            check_snapshot(snap)
        except ModelDomainError as err:
            assert err.limit == "sg_tubes_uncovered"
            t_halt = t
            break
    assert t_halt is not None and 30.0 < t_halt < 600.0


def test_feedwater_overfill_halts():
    """Review Focus 5: maximum manual feedwater stops at the overfill limit."""
    eng = build_standard_plant()
    t_halt = None
    t = 0.0
    while t < 2000.0:
        snap = eng.step(1.0, feedwater_manual=1.0 if t >= 10.0 else None)
        t = snap["t"]
        try:
            check_snapshot(snap)
        except ModelDomainError as err:
            assert err.limit == "sg_overfill"
            t_halt = t
            break
    assert t_halt is not None and 200.0 < t_halt < 2000.0


def test_turbine_trip_and_scram_level_recovers():
    snaps = run(build_standard_plant(), 1200.0, lambda t: {"turbine_trip": t >= 10.0, "scram": t >= 10.0})
    level = series(snaps, "sg_sec", "level_sg")
    assert level.min() > 0.30
    assert abs(level[-1] - 0.5) < 0.02


def test_factory_derives_feedwater_defaults_from_nondefault_shell_params():
    shell = SGSecondaryParams(V_sec=6.0e7)
    snap = build_standard_plant(sg_sec_params=shell).snapshot()
    assert snap["sg_sec"]["M_sec"] == pytest.approx(shell.M_sec_initial)
    assert snap["feedwater"]["m_fw_max"] == pytest.approx(1.2 * shell.m_steam_design)
    assert snap["signals"]["level_setpoint"] == pytest.approx(0.5)


def test_factory_derives_controller_ceiling_from_reduced_actuator_capacity():
    feedwater_params = FeedwaterParams(m_fw_max_frac=1.0)
    eng = build_standard_plant(feedwater_params=feedwater_params)
    snap = eng.step(60.0, level_setpoint=0.55)
    assert snap["feedwater"]["m_fw_max"] == pytest.approx(feedwater_params.m_fw_max)
    assert snap["fw_ctrl"]["m_fw_demand"] == pytest.approx(feedwater_params.m_fw_max)
    assert snap["fw_ctrl"]["saturated"] is True


def test_factory_derives_controller_ceiling_from_increased_actuator_capacity():
    feedwater_params = FeedwaterParams(m_fw_max_frac=1.5)
    snap = build_standard_plant(feedwater_params=feedwater_params).step(1.0, feedwater_manual=1.0)
    assert snap["feedwater"]["m_fw_max"] == pytest.approx(feedwater_params.m_fw_max)
    assert snap["fw_ctrl"]["m_fw_demand"] == pytest.approx(feedwater_params.m_fw_max)


def test_factory_rejects_inconsistent_explicit_feedwater_params():
    shell = SGSecondaryParams(V_sec=6.0e7)
    with pytest.raises(ValueError, match="fw_params.sg_params"):
        build_standard_plant(sg_sec_params=shell, fw_params=FeedwaterControllerParams())
    with pytest.raises(ValueError, match="feedwater_params.sg_params"):
        build_standard_plant(sg_sec_params=shell, feedwater_params=FeedwaterParams())
    with pytest.raises(ValueError, match="flow ceiling"):
        build_standard_plant(
            fw_params=FeedwaterControllerParams(m_fw_max_frac=1.2),
            feedwater_params=FeedwaterParams(m_fw_max_frac=1.0),
        )
