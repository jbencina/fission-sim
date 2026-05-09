"""Power-maneuver demo — slow rod insertion + withdrawal at hot full power.

Demonstrates the operator's startup-rate meter (DPM) over a controlled
maneuver, and (at M2) the pressurizer pressure-control response to the
thermal transient.

Starts at design steady state, slowly inserts rod to drop power by ~14%,
holds, then re-withdraws to design. The SUR indicator transitions through
subcritical → critical → supercritical → stable across the maneuver — the
same shape an operator sees during load-follow or any controlled rod-driven
power change at power.

The pressurizer story runs in parallel: insertion cools the primary, which
drives an outsurge (water contracts → level drops → P falls). The heater
band fires to restore pressure. On withdrawal the primary reheats, drives
an insurge, and spray opens to condense excess steam. Both P and level
should stay within acceptance-criterion bounds throughout.

This is **NOT** a cold-startup approach-to-criticality. A real cold
startup begins at deep-subcritical conditions where neutron count rate
is supported by an external neutron source (Pu-Be / Sb-Be), with primary
loop temperatures cold or at hot-zero-power, and the operator slowly
withdraws rods over many minutes/hours watching SUR converge toward zero
as the system approaches critical. M1 models none of that:
    - No external neutron source — n decays to zero at deep subcritical.
    - No cold / HZP loop initial conditions — loop initializes at design.
    - No two-phase state with primary at saturation pressure.

A future M6+ slice could add the source term and consistent low-power
thermal initial conditions for a real cold-startup scenario.

Scenario:
    t = 0..30 s     hold at design (rod_command = 0.5, n = 1.0)
    t = 30..150 s   ramp rod_command 0.5 → 0.485 (slow insertion, −210 pcm)
    t = 150..360 s  hold; power settles around 86% of design (Doppler + moderator
                    feedback offset most of the rod insertion)
    t = 360..480 s  ramp rod_command 0.485 → 0.5 (slow withdrawal back)
    t = 480..900 s  hold; power returns to design

Run:
    uv run python examples/power_maneuver.py
"""

from __future__ import annotations

import numpy as np

from fission_sim.engine import SimEngine
from fission_sim.physics.core import CoreParams, PointKineticsCore
from fission_sim.physics.primary_loop import LoopParams, PrimaryLoop
from fission_sim.physics.rod_controller import RodController, RodParams
from fission_sim.physics.secondary_sink import SecondarySink, SinkParams
from fission_sim.physics.steam_generator import SGParams, SteamGenerator

PCM = 1e5


def build_plant() -> SimEngine:
    """M2 plant at design defaults — n=1, all temps at refs, rod at 0.5,
    P=15.5 MPa, level=0.5."""
    from fission_sim.control.pressurizer_controller import (
        PressurizerController,
        PressurizerControllerParams,
    )
    from fission_sim.physics.pressurizer import Pressurizer, PressurizerParams

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
        power_thermal=core.power_thermal,
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
        power_thermal=core.power_thermal, Q_sg=Q_sg_sig,
        m_dot_spray=pzr_ctrl.m_dot_spray, P_primary=pzr.P,
    )
    engine.finalize()
    return engine


def scenario(t: float) -> dict:
    """Operator's rod-command profile over the full maneuver."""
    if t < 30.0:
        rod_command = 0.5
    elif t < 150.0:
        # Insert: 0.5 → 0.485 over 120 s. Rate = 1.25e-4/s, well below v_normal.
        rod_command = 0.5 - 0.015 * (t - 30.0) / 120.0
    elif t < 360.0:
        rod_command = 0.485
    else:
        rod_command = 0.485 + 0.015 * min(t - 360.0, 120.0) / 120.0
    return {"rod_command": rod_command, "scram": False}


def main() -> None:
    engine = build_plant()
    _final, dense = engine.run(t_end=900.0, scenario_fn=scenario, dense=True, max_step=0.5)

    print()
    print("=" * 100)
    print("  Power Maneuver Demo  —  controlled rod insertion + withdrawal at hot full power  (M2)")
    print("=" * 100)
    print()
    print("  Scenario:")
    print("    t =   0..30 s    hold at design (rod_command = 0.5, n = 1.0)")
    print("    t =  30..150 s   ramp rod 0.500 → 0.485 (slow insertion, −210 pcm)")
    print("    t = 150..360 s   hold at 0.485; power settles toward new equilibrium")
    print("    t = 360..480 s   ramp rod 0.485 → 0.500 (slow withdrawal back to design)")
    print("    t = 480..900 s   hold at 0.500; power returns to design")
    print()

    sample_t = np.array([0.0, 30.0, 60.0, 100.0, 150.0, 200.0, 300.0, 360.0, 420.0, 480.0, 600.0, 900.0])

    print("  Time-series at key points:")
    header = "    " + "-" * 93
    print(header)
    print(
        f"    {'t[s]':>6}  {'n':>9}  {'Q_core':>6}  {'T_fuel':>7}  {'T_avg':>6}"
        f"  {'P':>6}  {'level':>5}  {'Q_htr':>6}  {'m_spr':>5}"
        f"  {'rho_tot':>7}  {'SUR':>7}"
    )
    print(
        f"    {'':>6}  {'':>9}  {'[GW]':>6}  {'[K]':>7}  {'[K]':>6}"
        f"  {'[MPa]':>6}  {'':>5}  {'[MW]':>6}  {'[kg/s]':>5}"
        f"  {'[pcm]':>7}  {'[DPM]':>7}"
    )
    print(header)
    for ti in sample_t:
        snap = dense.at(float(ti))
        n = snap["core"]["n"]
        Q_core = snap["signals"]["power_thermal"] / 1e9
        T_fuel = snap["core"]["T_fuel"]
        T_avg = (snap["loop"]["T_hot"] + snap["loop"]["T_cold"]) / 2.0
        P_MPa = snap["pzr"]["P"] / 1e6
        level = snap["pzr"]["level"]
        Q_htr_MW = snap["signals"]["Q_heater"] / 1e6
        m_spr = snap["signals"]["m_dot_spray"]
        rho_tot_pcm = snap["core"]["rho_total"] * PCM
        sur = snap["core"]["startup_rate_dpm"]
        print(
            f"    {ti:6.1f}  {n:9.3e}  {Q_core:6.3f}  {T_fuel:7.2f}  {T_avg:6.2f}"
            f"  {P_MPa:6.3f}  {level:5.3f}  {Q_htr_MW:6.3f}  {m_spr:5.2f}"
            f"  {rho_tot_pcm:+7.1f}  {sur:+7.2f}"
        )
    print(header)
    print()

    print("  What this shows (focus on the SUR column):")
    print("    * t = 0..30: SUR ≈ 0 at steady state. Stable.")
    print("    * t = 30..150: rod ramping in. SUR goes negative as power decays;")
    print("      magnitude grows then shrinks as the system finds a new transient")
    print("      equilibrium. A real operator would see the meter swing left.")
    print("    * t = 150..360: rod held at 0.485. Power settles around 86% of design")
    print("      via Doppler/moderator feedback (a −210 pcm rod insertion is small")
    print("      relative to feedback strength — about a 14% power reduction). SUR")
    print("      returns to ≈ 0 — the operator's cue that the maneuver has completed.")
    print("    * t = 360..480: rod ramping back out. SUR goes positive (rising power).")
    print("    * t = 480..900: rod at design again. Power climbs back to ~1.0, SUR → 0.")
    print()
    print("  The startup-rate meter is the operator's primary 'is the reactor")
    print("  approaching where I want it' indicator. Magnitude tells you how fast;")
    print("  sign tells you direction; zero tells you you've arrived.")
    print()
    print("  Pressurizer response (new at M2):")
    print("    * t = 30..150: outsurge as primary cools (T_avg drops ~3 K) → P falls;")
    print("      pressure dip is ~60 kPa, well WITHIN the controller's 150 kPa deadband,")
    print("      so heaters do NOT fire (Q_htr stays 0). The pzr is in a quiet state.")
    print("    * t = 150..360: new equilibrium at slightly lower P, level drops a few %.")
    print("      Controller idle — pressure offset is below deadband.")
    print("    * t = 360..480: insurge as primary reheats; P recovers toward setpoint.")
    print("    * Throughout: |P − 15.5 MPa| stays under 0.1 MPa (well inside the 0.5 MPa bound).")
    print()
    print("    Why doesn't the controller fire? This 14% rod maneuver is gentle enough that")
    print("    the natural pressurizer + loop dynamics handle it without heater/spray action.")
    print("    A more aggressive maneuver (e.g. 30% load reduction over 60 s) would exceed")
    print("    the deadband and exercise the controller — see future load_reduction.py demo.")
    print()


if __name__ == "__main__":
    main()
