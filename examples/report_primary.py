"""Text-only diagnostic for the coupled primary plant + rod controller — engine-driven.

SSH-friendly sibling of ``run_primary.py``. Same scenario; output is a
printed table at key time points plus ASCII charts of n, T_avg, and
Q_core/Q_sg over time. No matplotlib.

Run:
    uv run python examples/report_primary.py
"""

from __future__ import annotations

import numpy as np

from fission_sim.disclaimer import print_disclaimer
from fission_sim.physics.core import CoreParams
from fission_sim.physics.domain import check_snapshot
from fission_sim.plant import build_standard_plant


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
    print_disclaimer()
    core_params = CoreParams()
    engine = build_standard_plant(core_params=core_params)

    def scenario(t: float) -> dict:
        return {
            # +210 pcm: 0.175 of travel × 1,200 pcm control-bank worth.
            "rod_command": 0.5 if t < 10.0 else 0.675,
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
    print("    t = 10 s      rod_command raised 0.5 → 0.675 (+210 pcm, ~17.5 s of rod motion)")
    print("    t = 10..60 s  Doppler AND moderator feedback level power off")
    print("    t = 60 s      scram (control + shutdown banks drop, −7,000 pcm total)")
    print("    t = 60..300 s delayed-neutron tail; loop water cools")
    print()

    sample_t = np.array([0, 5, 10, 11, 12, 30, 60, 60.5, 62, 80, 150, 300])
    snaps = [dense.at(float(ti)) for ti in sample_t]
    # Stop with an explanation, as the web runtime does, rather than report
    # a state outside the model's liquid-loop / saturated-pressurizer domain
    # (checks the tabulated samples only).
    for snap in snaps:
        check_snapshot(snap)

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
        Q_core_v = snap["core"]["power_thermal"]
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
        Qc = snap_t["core"]["power_thermal"]
        Qs = snap_t["signals"]["Q_sg"]
        rel = abs(Qc - Qs) / max(abs(Qc), 1.0)
        print(f"    t = {ti:5.1f} s  {Qc / 1e9:6.3f}     {Qs / 1e9:6.3f}     {(Qc - Qs) / 1e9:7.4f}   {rel:8.2%}")
    print()

    print()
    print("  PRESSURIZER")
    print("  -----------")
    print(f"    {'t[s]':>6}  {'P[MPa]':>7}  {'level':>5}  {'T_sat[K]':>8}  {'Q_htr[MW]':>9}  {'m_spr[kg/s]':>11}")
    for ti in sample_t:
        snap = dense.at(float(ti))
        P_MPa = snap["pzr"]["P"] / 1e6
        level = snap["pzr"]["level"]
        T_sat = snap["pzr"]["T_sat"]
        Q_htr = snap["signals"]["Q_heater"] / 1e6
        m_spr = snap["signals"]["m_dot_spray"]
        print(
            f"    {ti:6.1f}  {P_MPa:7.3f}  {level:5.3f}  {T_sat:8.2f}  {Q_htr:9.3f}  {m_spr:11.3f}"
        )
    print()

    print("  What this shows:")
    print("    * Steady state holds at n=1 with rod at design (0.5).")
    print("    * After the 0.5 → 0.675 rod_command step: the control bank (1,200 pcm over")
    print("      full travel) moves at v_normal=0.01/s = 12 pcm/s for ~17.5 s, so the")
    print("      +210 pcm ramps in rather than stepping. Doppler+moderator level it off.")
    print("    * After scram: both banks drop at v_scram=0.5/s. The control bank is in")
    print("      within ~1.3 s and the fully withdrawn shutdown bank within ~2 s,")
    print("      −7,000 pcm in total. Power falls below 10% of design within ~2 s,")
    print("      then follows the delayed-neutron tail set by the longest-lived precursor")
    print("      group (C1: ~55 s half-life, ~80 s mean life).")
    print("    * Late-tail T_avg → T_secondary (558 K) is a model simplification:")
    print("      fission-product decay heat is not modeled and the secondary side is held")
    print("      at a fixed 558 K, so once the neutron tail dies nothing heats the loop and")
    print("      it equilibrates to the sink. In a real plant decay heat would still be")
    print("      roughly 1-3% of full power a few minutes after shutdown (order of")
    print("      magnitude from the ANS-5.1 decay-heat standard), keeping the primary")
    print("      warmer than the sink.")
    print("    * Q_core (fission power) and Q_sg differ whenever the fuel and loop are")
    print("      storing or releasing heat (M·c_p·dT/dt). After the scram the SG keeps")
    print("      removing heat that was stored in the fuel and water, so Q_sg exceeds")
    print("      fission power by a large factor during the cooldown. P ≈ Q_sg holds")
    print("      only at settled plateaus; the full balance including storage is checked")
    print("      in tests/test_primary_plant.py.")
    print()


if __name__ == "__main__":
    main()
