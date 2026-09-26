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
dip (~170 kPa) goes past the controller's 150 kPa deadband, so the heaters
fire for about a minute and a half. On withdrawal the primary reheats and
drives an insurge that brings pressure back up; it stays below setpoint,
so spray never opens. P stays within 0.2 MPa of the 15.5 MPa setpoint
and level within 0.45-0.51 throughout.

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
    print("  Pressurizer response:")
    print("    * t = 30..150: outsurge as primary cools (T_avg drops ~3.5 K) → P falls")
    print("      by up to ~170 kPa (low point ≈ 15.33 MPa near t = 150 s), past the")
    print("      controller's 150 kPa deadband. The heaters run at their 1.8 MW maximum")
    print("      from about t = 95 s to t = 165 s, then taper to ~0 by about t = 190 s.")
    print("    * t = 150..360: new equilibrium ~150 kPa below setpoint, level ≈ 0.45")
    print("      (down from 0.50). The offset sits at the deadband edge, so the")
    print("      controller is essentially idle.")
    print("    * t = 360..480: insurge as primary reheats; P recovers to ≈ 15.42 MPa,")
    print("      still below setpoint, so spray never opens. Proportional control with a")
    print("      deadband has no integral action, so this small offset remains.")
    print("    * Throughout: |P − 15.5 MPa| stays under 0.2 MPa (inside the 0.5 MPa bound).")
    print()


if __name__ == "__main__":
    main()
