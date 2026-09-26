"""Full-plant acceptance tests for the pressurizer and its controller.

Criteria checked here:

  1. Steady state holds.
  2. Power-maneuver pressure swing < 0.5 MPa.
  3. Conservation invariant M_loop + M_pzr drift < 1 kg.
  4. Sign sanity (insurge raises P, outsurge lowers P, etc.).
  5. Manual override semantics.
  7. Scram-from-full-power transient with conservation.
  8. Heater-failure cooldown stays subcooled.

Criterion 6 (energy-balance closure) is covered in
tests/test_primary_plant.py.
"""

import numpy as np
import pytest

from fission_sim.control.pressurizer_controller import (
    PressurizerController,
    PressurizerControllerParams,
)
from fission_sim.engine.engine import SimEngine
from fission_sim.physics.core import CoreParams, PointKineticsCore
from fission_sim.physics.pressurizer import Pressurizer, PressurizerParams
from fission_sim.physics.primary_loop import LoopParams, PrimaryLoop
from fission_sim.physics.rod_controller import RodController, RodParams
from fission_sim.physics.secondary_sink import SecondarySink, SinkParams
from fission_sim.physics.steam_generator import SGParams, SteamGenerator

# Control-bank travel worth −210 pcm (the maneuver size used below): the
# default bank is worth 1,200 pcm over full travel, so 210 pcm is 17.5 %.
ROD_STEP_210_PCM = 0.0021 / RodParams().rho_control_worth


def build_m2_plant() -> SimEngine:
    """Wire the full plant (with pressurizer and controller) at design defaults."""
    engine = SimEngine()
    loop_params = LoopParams()
    pzr_params = PressurizerParams(loop_params=loop_params)
    ctrl_params = PressurizerControllerParams()

    rod = engine.module(RodController(RodParams()), name="rod")
    core = engine.module(PointKineticsCore(CoreParams()), name="core")
    loop = engine.module(PrimaryLoop(loop_params), name="loop")
    sg = engine.module(SteamGenerator(SGParams()), name="sg")
    sink = engine.module(SecondarySink(SinkParams()), name="sink")
    pzr = engine.module(Pressurizer(pzr_params), name="pzr")
    pzr_ctrl = engine.module(PressurizerController(ctrl_params), name="pzr_ctrl")

    rod_cmd = engine.input("rod_command", default=0.5)
    scram = engine.input("scram", default=False)
    P_setpoint = engine.input("P_setpoint", default=ctrl_params.P_setpoint_default)
    heater_manual = engine.input("heater_manual", default=None)
    spray_manual = engine.input("spray_manual", default=None)

    rho_rod = rod(rod_command=rod_cmd, scram=scram)
    T_sec = sink()
    Q_sg_sig = sg(T_avg=loop.T_avg, T_secondary=T_sec)
    core(rho_rod=rho_rod, T_cool=loop.T_cool)
    pzr(
        Q_fuel_to_coolant=core.Q_fuel_to_coolant,
        Q_sg=Q_sg_sig,
        T_hotleg=loop.T_hot,
        T_coldleg=loop.T_cold,
        Q_heater=pzr_ctrl.Q_heater,
        m_dot_spray=pzr_ctrl.m_dot_spray,
    )
    pzr_ctrl(
        P=pzr.P, P_setpoint=P_setpoint,
        heater_manual=heater_manual, spray_manual=spray_manual,
    )
    loop(
        Q_fuel_to_coolant=core.Q_fuel_to_coolant, Q_sg=Q_sg_sig,
        m_dot_spray=pzr_ctrl.m_dot_spray, P_primary=pzr.P,
    )
    engine.finalize()
    return engine


# ---------------------------------------------------------------------------
# Acceptance criterion 1: steady state holds
# ---------------------------------------------------------------------------
def test_steady_state_holds_for_300s():
    engine = build_m2_plant()
    # run() without dense=True returns a plain Snapshot, not a tuple.
    final = engine.run(t_end=300.0, max_step=1.0)
    P = final["pzr"]["P"]
    level = final["pzr"]["level"]
    assert abs(P - 1.55e7) < 1.0e3      # < 1 kPa drift
    assert abs(level - 0.5) < 1.0e-3    # < 0.001 level drift
    assert final["signals"]["Q_heater"] == pytest.approx(0.0, abs=1.0)
    assert final["signals"]["m_dot_spray"] == pytest.approx(0.0, abs=1e-3)


# ---------------------------------------------------------------------------
# Acceptance criteria 2 + 3: power-maneuver pressure swing + conservation
# (run together because they share the same scenario)
# ---------------------------------------------------------------------------
def _power_maneuver(t: float) -> dict:
    """−210 pcm ramped in over 120 s, held, then ramped back out."""
    low = 0.5 - ROD_STEP_210_PCM
    if t < 30.0:
        rc = 0.5
    elif t < 150.0:
        rc = 0.5 - ROD_STEP_210_PCM * (t - 30.0) / 120.0
    elif t < 360.0:
        rc = low
    elif t < 480.0:
        rc = low + ROD_STEP_210_PCM * min(t - 360.0, 120.0) / 120.0
    else:
        rc = 0.5
    return {"rod_command": rc, "scram": False}


def test_power_maneuver_pressure_swing_within_bound():
    engine = build_m2_plant()
    _, dense = engine.run(t_end=900.0, scenario_fn=_power_maneuver, dense=True, max_step=0.5)
    sample_t = np.linspace(0.0, 900.0, 91)
    P_history = np.array([dense.at(float(t))["pzr"]["P"] for t in sample_t])
    assert np.max(np.abs(P_history - 1.55e7)) < 0.5e6  # < 0.5 MPa


def test_conservation_invariant_holds_across_maneuver():
    """M_loop + M_pzr drift over 900 s power maneuver must be < 1 kg."""
    engine = build_m2_plant()
    _, dense = engine.run(t_end=900.0, scenario_fn=_power_maneuver, dense=True, max_step=0.5)
    snap0 = dense.at(0.0)
    snap_end = dense.at(900.0)
    M_total_0 = snap0["loop"]["M_loop"] + snap0["pzr"]["M_pzr"]
    M_total_end = snap_end["loop"]["M_loop"] + snap_end["pzr"]["M_pzr"]
    assert abs(M_total_end - M_total_0) < 1.0


# ---------------------------------------------------------------------------
# Acceptance criterion 4: sign sanity
# ---------------------------------------------------------------------------
def test_power_down_drives_outsurge_and_lower_pressure():
    """During mid-cooldown, pressure should be below setpoint and the
    surge mass rate (in pzr telemetry) should be negative (outsurge)."""
    engine = build_m2_plant()
    _, dense = engine.run(t_end=180.0, scenario_fn=_power_maneuver, dense=True, max_step=0.5)
    # Sample mid-ramp at t=90 s (deepest into the cooldown).
    snap = dense.at(90.0)
    # Pressure should have fallen below setpoint.
    assert snap["pzr"]["P"] < 1.55e7
    # Telemetry exposes m_dot_surge; outsurge means the rate is negative
    # (mass leaving the pzr back into the loop).
    assert snap["pzr"]["m_dot_surge"] < 0


# ---------------------------------------------------------------------------
# Acceptance criterion 5: manual override
# ---------------------------------------------------------------------------
def test_heater_manual_zero_disables_heater_during_underpressure():
    """Force heater_manual=0 throughout a slow cooldown; heater stays off
    even as pressure falls."""
    engine = build_m2_plant()

    def scenario(t: float) -> dict:
        return {
            "rod_command": 0.5 - ROD_STEP_210_PCM if t > 30.0 else 0.5,
            "scram": False,
            "heater_manual": 0.0,
        }

    _, dense = engine.run(t_end=400.0, scenario_fn=scenario, dense=True, max_step=0.5)
    # Sample late in the run, when pressure is several hundred kPa below
    # setpoint (well past the 150 kPa deadband where heaters would fire).
    snap = dense.at(300.0)
    assert snap["signals"]["Q_heater"] == 0.0


# ---------------------------------------------------------------------------
# Acceptance criterion 7: scram-from-full-power conservation
# ---------------------------------------------------------------------------
def test_scram_from_full_power_conserves_mass():
    """Conservation invariant holds across a fast scram transient — this
    is the test that catches sign errors in the surge-density branch."""
    engine = build_m2_plant()

    def scenario(t: float) -> dict:
        return {"rod_command": 0.5, "scram": t >= 10.0}

    _, dense = engine.run(t_end=600.0, scenario_fn=scenario, dense=True, max_step=0.5)
    snap0 = dense.at(0.0)
    snap_end = dense.at(600.0)
    M_total_0 = snap0["loop"]["M_loop"] + snap0["pzr"]["M_pzr"]
    M_total_end = snap_end["loop"]["M_loop"] + snap_end["pzr"]["M_pzr"]
    assert abs(M_total_end - M_total_0) < 1.0


# ---------------------------------------------------------------------------
# Acceptance criterion 8: heater-failure cooldown stays subcooled
# ---------------------------------------------------------------------------
def test_heater_failure_cooldown_stays_subcooled():
    """Heater fails off; pressure walks down; subcooling margin stays > 0
    over the run (no boiling-induced anomaly in the pressurizer model)."""
    engine = build_m2_plant()

    def scenario(t: float) -> dict:
        rc = 0.5 - ROD_STEP_210_PCM * min(t, 600.0) / 600.0
        return {"rod_command": rc, "scram": False, "heater_manual": 0.0}

    _, dense = engine.run(t_end=600.0, scenario_fn=scenario, dense=True, max_step=1.0)
    # Pressure should walk down monotonically.
    P_50 = dense.at(50.0)["pzr"]["P"]
    P_600 = dense.at(600.0)["pzr"]["P"]
    assert P_600 < P_50
    # Subcooling margin must stay > 0 over the run.
    sample_t = np.linspace(0.0, 600.0, 61)
    margins = [dense.at(float(t))["pzr"]["subcooling_margin"] for t in sample_t]
    assert min(margins) > 0
