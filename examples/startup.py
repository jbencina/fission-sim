"""Power-maneuver demo — slow rod insertion + withdrawal at hot full power.

Demonstrates the operator's startup-rate meter (DPM) over a controlled
load-follow maneuver. Starts at design steady state, slowly inserts rod
to drop power by ~14%, holds, then re-withdraws to design. The SUR
indicator transitions through subcritical → critical → supercritical →
stable across the maneuver — the same shape an operator sees during
load-follow operations.

This is **not** a cold-startup approach to criticality. M1 has no
external neutron source modeled, so it can't simulate the source-driven
deep-subcritical regime where SUR is the *only* power indicator on the
panel. What we demo here is hot-full-power maneuvering, where SUR is
still informative but power level can also be read directly from the
flux instruments. M6+ could add a source term and a true cold-startup
scenario.

Scenario:
    t = 0..30 s     hold at design (rod_command = 0.5, n = 1.0)
    t = 30..150 s   ramp rod_command 0.5 → 0.485 (slow insertion, −210 pcm)
    t = 150..360 s  hold; power settles around 86% of design (Doppler + moderator
                    feedback offset most of the rod insertion)
    t = 360..480 s  ramp rod_command 0.485 → 0.5 (slow withdrawal back)
    t = 480..900 s  hold; power returns to design

Run:
    uv run python examples/startup.py
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
    """M1 plant at design defaults — n=1, all temps at refs, rod at 0.5."""
    engine = SimEngine()
    rod = engine.module(RodController(RodParams()), name="rod")
    core = engine.module(PointKineticsCore(CoreParams()), name="core")
    loop = engine.module(PrimaryLoop(LoopParams()), name="loop")
    sg = engine.module(SteamGenerator(SGParams()), name="sg")
    sink = engine.module(SecondarySink(SinkParams()), name="sink")

    rod_cmd = engine.input("rod_command", default=0.5)
    scram = engine.input("scram", default=False)

    rho_rod = rod(rod_command=rod_cmd, scram=scram)
    T_sec = sink()
    Q_sg_sig = sg(T_avg=loop.T_avg, T_secondary=T_sec)
    core(rho_rod=rho_rod, T_cool=loop.T_cool)
    loop(power_thermal=core.power_thermal, Q_sg=Q_sg_sig)
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
    elif t < 480.0:
        # Withdraw: 0.485 → 0.5 over 120 s.
        rod_command = 0.485 + 0.015 * (t - 360.0) / 120.0
    else:
        rod_command = 0.5
    return {"rod_command": rod_command, "scram": False}


def main() -> None:
    engine = build_plant()
    _final, dense = engine.run(t_end=900.0, scenario_fn=scenario, dense=True, max_step=0.5)

    print()
    print("=" * 96)
    print("  Power Maneuver Demo  —  controlled rod insertion + withdrawal at hot full power")
    print("=" * 96)
    print()
    print("  Scenario:")
    print("    t =   0..30 s    hold at design (rod_command = 0.5, n = 1.0)")
    print("    t =  30..150 s   ramp rod 0.500 → 0.485 (slow insertion, −210 pcm step)")
    print("    t = 150..360 s   hold at 0.485; power settles toward new equilibrium")
    print("    t = 360..480 s   ramp rod 0.485 → 0.500 (slow withdrawal back to design)")
    print("    t = 480..900 s   hold at 0.500; power returns to design")
    print()

    sample_t = np.array([0.0, 30.0, 60.0, 100.0, 150.0, 200.0, 300.0, 360.0, 420.0, 480.0, 600.0, 900.0])

    print("  Time-series at key points:")
    header = "    " + "-" * 87
    print(header)
    print(
        f"    {'t[s]':>6}  {'n':>9}  {'Q_core':>6}  {'T_fuel':>7}  {'T_avg':>6}"
        f"  {'rod_cmd':>7}  {'rho_rod':>7}  {'rho_tot':>7}  {'SUR':>7}"
    )
    print(
        f"    {'':>6}  {'':>9}  {'[GW]':>6}  {'[K]':>7}  {'[K]':>6}  {'':>7}  {'[pcm]':>7}  {'[pcm]':>7}  {'[DPM]':>7}"
    )
    print(header)
    for ti in sample_t:
        snap = dense.at(float(ti))
        rod_cmd = scenario(float(ti))["rod_command"]
        n = snap["core"]["n"]
        Q_core = snap["signals"]["power_thermal"] / 1e9
        T_fuel = snap["core"]["T_fuel"]
        T_avg = (snap["loop"]["T_hot"] + snap["loop"]["T_cold"]) / 2.0
        rho_rod_pcm = snap["signals"]["rho_rod"] * PCM
        rho_tot_pcm = snap["core"]["rho_total"] * PCM
        sur = snap["core"]["startup_rate_dpm"]
        print(
            f"    {ti:6.1f}  {n:9.3e}  {Q_core:6.3f}  {T_fuel:7.2f}  {T_avg:6.2f}"
            f"  {rod_cmd:7.4f}  {rho_rod_pcm:+7.1f}  {rho_tot_pcm:+7.1f}  {sur:+7.2f}"
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


if __name__ == "__main__":
    main()
