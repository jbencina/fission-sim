"""Power-maneuver demo — slow rod insertion + withdrawal at hot full power.

Demonstrates the operator's startup-rate meter (DPM) over a controlled
maneuver, and the pressurizer pressure-control response to the thermal
transient.

Starts at design steady state, slowly inserts rod to drop power by ~14%,
holds, then re-withdraws to design. The SUR indicator transitions through
subcritical → critical → supercritical → stable across the maneuver — the
same shape an operator sees during load-follow or any controlled rod-driven
power change at power.

The pressurizer story runs in parallel: insertion cools the primary, which
drives an outsurge (water contracts → level drops → P falls). The pressure
dip is about 0.52 MPa in the coupled-secondary M3 plant, so the heaters stay
at their 1.8 MW maximum for several minutes. On withdrawal the primary
reheats and drives an insurge that brings pressure back up; it stays below
setpoint, so spray never opens. Level falls to about 0.359 at the low-power
plateau and recovers slightly above 0.5 by the end of the return to power.

This is **NOT** a cold-startup approach-to-criticality. A real cold
startup begins at deep-subcritical conditions where neutron count rate
is supported by an external neutron source (Pu-Be / Sb-Be), with primary
loop temperatures cold or at hot-zero-power, and the operator slowly
withdraws rods over many minutes/hours watching SUR converge toward zero
as the system approaches critical. This simulator models none of that:
    - No external neutron source — n decays to zero at deep subcritical.
    - No cold / HZP loop initial conditions — loop initializes at design.
    - No two-phase state with primary at saturation pressure.

A cold-startup scenario would need that source term and consistent
low-power thermal initial conditions, which are not modeled.

Scenario:
    t = 0..30 s     hold at design (rod_command = 0.5, n = 1.0)
    t = 30..150 s   ramp rod_command 0.5 → 0.325 (slow insertion, −210 pcm)
    t = 150..360 s  hold; power settles around 86% of design (Doppler + moderator
                    feedback offset most of the rod insertion)
    t = 360..480 s  ramp rod_command 0.325 → 0.5 (slow withdrawal back)
    t = 480..900 s  hold; power returns to design

Run:
    uv run python examples/power_maneuver.py
"""

from __future__ import annotations

import numpy as np

from fission_sim.disclaimer import print_disclaimer
from fission_sim.physics.domain import check_snapshot
from fission_sim.plant import build_standard_plant

PCM = 1e5


def scenario(t: float) -> dict:
    """Operator's rod-command profile over the full maneuver."""
    # −210 pcm = 0.175 of control-bank travel (1,200 pcm full travel).
    if t < 30.0:
        rod_command = 0.5
    elif t < 150.0:
        # Insert: 0.5 → 0.325 over 120 s. Rate ≈ 1.46e-3/s (1.75 pcm/s), well
        # below v_normal.
        rod_command = 0.5 - 0.175 * (t - 30.0) / 120.0
    elif t < 360.0:
        rod_command = 0.325
    else:
        rod_command = 0.325 + 0.175 * min(t - 360.0, 120.0) / 120.0
    return {"rod_command": rod_command, "scram": False}


def load_follow_scenario(t: float) -> dict:
    """100 % → 90 % turbine-load ramp with rods in automatic."""
    if t <= 10.0:
        load = 1.0
    else:
        load = max(0.9, 1.0 - 8.33e-4 * (t - 10.0))
    return {"turbine_load": load, "rod_auto": True, "scram": False}


def main() -> None:
    print_disclaimer()
    # Standard plant at design defaults: n = 1, temperatures at their
    # references, rod at 0.5, P = 15.5 MPa, pressurizer level 0.5.
    engine = build_standard_plant()
    _final, dense = engine.run(t_end=900.0, scenario_fn=scenario, dense=True, max_step=0.5)

    print()
    print("=" * 100)
    print("  Power Maneuver Demo  —  controlled rod insertion + withdrawal at hot full power")
    print("=" * 100)
    print()
    print("  Scenario:")
    print("    t =   0..30 s    hold at design (rod_command = 0.5, n = 1.0)")
    print("    t =  30..150 s   ramp rod 0.500 → 0.325 (slow insertion, −210 pcm)")
    print("    t = 150..360 s   hold at 0.325; power settles toward new equilibrium")
    print("    t = 360..480 s   ramp rod 0.325 → 0.500 (slow withdrawal back to design)")
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
        # Stop with an explanation if outside the model's domain (checks the
        # printed samples only).
        check_snapshot(snap)
        n = snap["core"]["n"]
        Q_core = snap["core"]["power_thermal"] / 1e9
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
    print("    * t = 150..360: rod held at 0.325. Power settles around 86% of design")
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
    print("  Pressurizer and coupled-secondary response:")
    print("    * t = 30..150: rod insertion lowers power and secondary pressure/temperature")
    print("      follow it (P_steam ≈ 6.41 MPa, T_secondary ≈ 553.1 K at t = 150 s).")
    print("      The primary cools, outsurges, and pressure falls to ≈ 14.98 MPa.")
    print("      That is well past the 150 kPa heater deadband, so heaters are at their")
    print("      1.8 MW maximum.")
    print("    * t = 150..360: with rods held at 0.325, the plant sits near n ≈ 0.897,")
    print("      T_avg ≈ 572.83 K, P ≈ 15.28 MPa, and pressurizer level ≈ 0.359.")
    print("      The controller still calls for maximum heaters at t = 360 s; it is not")
    print("      an idle-pressure plateau.")
    print("    * t = 360..480: rod withdrawal reheats the loop and drives insurge. Pressure")
    print("      recovers to ≈ 15.41 MPa by t = 480 s while level rises to ≈ 0.475; spray")
    print("      never opens because pressure remains below setpoint.")
    print("    * By t = 900 s, the plant is essentially back at full power with P ≈")
    print("      15.48 MPa and level ≈ 0.519. The M3 secondary is dynamic, so these")
    print("      numbers differ from the old fixed-secondary M2 maneuver.")
    print()

    print("=" * 100)
    print("  Turbine Load-Follow Demo  —  100% → 90% admission ramp with rods automatic")
    print("=" * 100)
    print()
    print("  Scenario:")
    print("    t =   0..10 s    hold at full turbine admission, rods in automatic")
    print("    t =  10..130 s   ramp turbine_load 1.000 → 0.900 at 5 %/min")
    print("    t = 130..1800 s   hold 90 % admission; Tavg controller tracks T_ref")
    print()

    load_engine = build_standard_plant(rod_auto=True)
    _load_final, load_dense = load_engine.run(
        t_end=1800.0,
        scenario_fn=load_follow_scenario,
        dense=True,
        max_step=0.5,
    )
    load_sample_t = np.array([0.0, 10.0, 60.0, 130.0, 300.0, 900.0, 1500.0, 1800.0])

    print("  Time-series at key points:")
    header = "    " + "-" * 95
    print(header)
    print(
        f"    {'t[s]':>6}  {'load':>6}  {'n':>9}  {'T_avg':>7}  {'T_ref':>7}"
        f"  {'rod_pos':>7}  {'P_stm':>7}  {'P_e':>7}  {'T_err':>7}"
    )
    print(
        f"    {'':>6}  {'':>6}  {'':>9}  {'[K]':>7}  {'[K]':>7}"
        f"  {'':>7}  {'[MPa]':>7}  {'[MW]':>7}  {'[K]':>7}"
    )
    print(header)
    for ti in load_sample_t:
        snap = load_dense.at(float(ti))
        check_snapshot(snap)
        print(
            f"    {ti:6.1f}  {snap['turbine']['load']:6.3f}  {snap['core']['n']:9.3e}"
            f"  {snap['loop']['T_avg']:7.2f}  {snap['turbine']['T_ref']:7.2f}"
            f"  {snap['rod']['rod_position']:7.4f}  {snap['sg_sec']['P_steam'] / 1e6:7.3f}"
            f"  {snap['turbine']['P_electric'] / 1e6:7.1f}"
            f"  {snap['tavg_ctrl']['T_err']:7.3f}"
        )
    print(header)
    print()
    print("  What this shows:")
    print("    * The turbine T_ref program drops from 583 K to 581.2 K as admission reaches 90%.")
    print("    * With rods automatic, the control bank inserts enough to pull T_avg back")
    print("      toward that lower reference instead of letting moderator feedback alone")
    print("      settle the plant warm.")
    print()


if __name__ == "__main__":
    main()
