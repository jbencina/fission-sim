"""Text-only diagnostic for the coupled primary plant + rod controller — engine-driven.

SSH-friendly sibling of ``run_primary.py``. Same scenario; output is a
printed table at key time points plus ASCII charts of n, T_avg, and
Q_core/Q_sg over time. No matplotlib.

Run:
    uv run python examples/report_primary.py
"""

from __future__ import annotations

import numpy as np

from fission_sim.engine import SimEngine
from fission_sim.physics.core import CoreParams, PointKineticsCore
from fission_sim.physics.primary_loop import LoopParams, PrimaryLoop
from fission_sim.physics.rod_controller import RodController, RodParams
from fission_sim.physics.secondary_sink import SecondarySink, SinkParams
from fission_sim.physics.steam_generator import SGParams, SteamGenerator


def ascii_log_chart(times, values, width=50, vmin=None, vmax=None, label="value"):
    """Print a horizontal log-scale chart of `values` vs `times`."""
    v = np.asarray(values, dtype=float)
    v = np.where(v > 0, v, np.nan)
    log_v = np.log10(v)
    lo = float(np.nanmin(log_v)) if vmin is None else np.log10(vmin)
    hi = float(np.nanmax(log_v)) if vmax is None else np.log10(vmax)
    pad = 0.05 * (hi - lo) if hi > lo else 0.5
    lo -= pad
    hi += pad

    decade_lo = int(np.floor(lo))
    decade_hi = int(np.ceil(hi))
    axis = [" "] * width
    for d in range(decade_lo, decade_hi + 1):
        col = int(round((d - lo) / (hi - lo) * (width - 1)))
        if 0 <= col < width:
            axis[col] = "|"
    print(f"   t [s]     {label:<13}  " + "".join(axis))
    labels = [" "] * width
    for d in range(decade_lo, decade_hi + 1):
        col = int(round((d - lo) / (hi - lo) * (width - 1)))
        if 0 <= col < width - 4:
            tag = f"1e{d:+d}"
            for k, ch in enumerate(tag):
                if col + k < width:
                    labels[col + k] = ch
    print(f"   {' ' * 22}" + "".join(labels))

    for t, val, lv in zip(times, values, log_v):
        row = ["·" if axis[i] == "|" else " " for i in range(width)]
        if not np.isnan(lv):
            col = int(round((lv - lo) / (hi - lo) * (width - 1)))
            col = max(0, min(width - 1, col))
            row[col] = "*"
        print(f"   {t:6.1f}    {val:11.3e}    " + "".join(row))


def ascii_linear_chart(times, values, width=50, label="value", unit=""):
    """Print a horizontal linear-scale chart of `values` vs `times`."""
    v = np.asarray(values, dtype=float)
    lo, hi = float(v.min()), float(v.max())
    span = max(hi - lo, 1e-9)
    print(f"   t [s]     {label:<13}  |{lo:7.2f}{' ' * (width - 16)}{hi:7.2f}|")
    for t, val in zip(times, v):
        col = int(round((val - lo) / span * (width - 1)))
        col = max(0, min(width - 1, col))
        row = [" "] * width
        row[col] = "*"
        print(f"   {t:6.1f}    {val:9.3f} {unit:<3}  " + "".join(row))


def main() -> None:
    core_params = CoreParams()
    loop_params = LoopParams()
    sg_params = SGParams()
    sink_params = SinkParams()
    rod_params = RodParams()

    engine = SimEngine()
    rod = engine.module(RodController(rod_params), name="rod")
    core = engine.module(PointKineticsCore(core_params), name="core")
    loop = engine.module(PrimaryLoop(loop_params), name="loop")
    sg = engine.module(SteamGenerator(sg_params), name="sg")
    sink = engine.module(SecondarySink(sink_params), name="sink")

    rod_cmd = engine.input("rod_command", default=0.5)
    scram = engine.input("scram", default=False)

    rho_rod = rod(rod_command=rod_cmd, scram=scram)
    T_sec = sink()
    Q_sg_sig = sg(T_avg=loop.T_avg, T_secondary=T_sec)
    core(rho_rod=rho_rod, T_cool=loop.T_cool)
    loop(power_thermal=core.power_thermal, Q_sg=Q_sg_sig)

    def scenario(t: float) -> dict:
        return {
            "rod_command": 0.5 if t < 10.0 else 0.515,
            "scram": t >= 60.0,
        }

    _final, dense = engine.run(t_end=300.0, scenario_fn=scenario, dense=True)

    print()
    print("=" * 84)
    print("  Coupled Primary Plant + Rod Controller  —  default scenario  (text report)")
    print("=" * 84)
    print()
    print("  Scenario:")
    print("    t = 0..10 s   steady state at design (rod_command = 0.5)")
    print("    t = 10 s      rod_command raised by +0.015 (gradual withdraw ~1.5 s)")
    print("    t = 10..60 s  Doppler AND moderator feedback level power off")
    print("    t = 60 s      scram (rod_command_effective → 0)")
    print("    t = 60..300 s delayed-neutron tail; loop water cools")
    print()

    sample_t = np.array([0, 5, 10, 11, 12, 30, 60, 60.5, 62, 80, 150, 300])
    snaps = [dense.at(float(ti)) for ti in sample_t]

    print("  Time-series at key points:")
    # Column widths matched to the data row below (6, 9, 7, 6, 7, 7, 6, 6) with
    # 2-space separators and a 4-space indent. rod_pos column is 7 wide so the
    # "rod_pos" header label fits without overflow.
    header = "    " + "-" * 76
    print(header)
    print(
        f"    {'t[s]':>6}  {'n':>9}  {'T_fuel':>7}  {'T_avg':>6}  {'rod_pos':>7}"
        f"  {'rho_rod':>7}  {'Q_core':>6}  {'Q_sg':>6}"
    )
    print(f"    {'':>6}  {'':>9}  {'[K]':>7}  {'[K]':>6}  {'':>7}  {'[pcm]':>7}  {'[GW]':>6}  {'[GW]':>6}")
    print(header)
    PCM = 1e5
    for ti, snap in zip(sample_t, snaps):
        ni = snap["core"]["n"]
        Tfi = snap["core"]["T_fuel"]
        Tavi = (snap["loop"]["T_hot"] + snap["loop"]["T_cold"]) / 2.0
        posi = snap["rod"]["rod_position"]
        rho_rod_v = snap["signals"]["rho_rod"] * PCM
        Q_core_v = snap["signals"]["power_thermal"]
        Q_sg_v = snap["signals"]["Q_sg"]
        print(
            f"    {ti:6.1f}  {ni:9.3e}  {Tfi:7.2f}  {Tavi:6.2f}  {posi:7.4f}"
            f"  {rho_rod_v:+7.1f}  {Q_core_v / 1e9:6.3f}  {Q_sg_v / 1e9:6.3f}"
        )
    print(header)
    print()

    chart_t = np.array([0, 2, 5, 10, 11, 13, 30, 60, 60.5, 65, 80, 150, 300])
    chart_n = dense.signal("power_thermal", chart_t) / core_params.P_design
    chart_Tavg = np.array(
        [(dense.at(float(ti))["loop"]["T_hot"] + dense.at(float(ti))["loop"]["T_cold"]) / 2 for ti in chart_t]
    )
    chart_rod = np.array([dense.at(float(ti))["rod"]["rod_position"] for ti in chart_t])

    print("  Neutron population n  (log scale, n=1 at design power):")
    print()
    ascii_log_chart(chart_t, chart_n, width=52, vmin=1e-4, vmax=1e2, label="n")
    print()

    print("  Loop average temperature T_avg [K]:")
    print()
    ascii_linear_chart(chart_t, chart_Tavg, width=52, label="T_avg", unit="K")
    print()

    print("  Rod position (0=fully inserted, 1=fully withdrawn):")
    print()
    ascii_linear_chart(chart_t, chart_rod, width=52, label="rod_pos", unit="")
    print()

    print("  Energy balance check (Q_core vs Q_sg at key times, both in GW):")
    print()
    # Header columns right-align with the data values below.
    print(f"{'':>17}{'Q_core':>6}     {'Q_sg':>6}     {'ΔQ':>7}   {'rel':>8}")
    for ti in [0.0, 30.0, 100.0, 300.0]:
        snap_t = dense.at(float(ti))
        Qc = snap_t["signals"]["power_thermal"]
        Qs = snap_t["signals"]["Q_sg"]
        rel = abs(Qc - Qs) / max(abs(Qc), 1.0)
        print(f"    t = {ti:5.1f} s  {Qc / 1e9:6.3f}     {Qs / 1e9:6.3f}     {(Qc - Qs) / 1e9:7.4f}   {rel:8.2%}")
    print()

    print("  What this shows:")
    print("    * Steady state holds at n=1 with rod at design (0.5).")
    print("    * After +0.015 rod_command step: rod moves at v_normal=0.01/s for ~1.5 s")
    print("      (rate clip binds), then exponential settling over ~3 s. Total +210 pcm")
    print("      reactivity ramps in over ~3 s (not instantaneously). Doppler+moderator")
    print("      level it off.")
    print("    * After scram: rod_command_effective → 0. Rod drops at v_scram=0.5/s for")
    print("      ~1 s (delivers ~80% of scram worth), then exponential settling over a")
    print("      few more seconds for the last bit. Power drops two orders of magnitude")
    print("      within ~2 s, then delayed-neutron tail (group-1 precursor, ~55 s τ).")
    print()


if __name__ == "__main__":
    main()
