"""Text-only diagnostic for the coupled primary plant.

SSH-friendly sibling of ``run_primary.py``. Same scenario; output is a
printed table at key time points plus ASCII charts of n, T_avg, and
Q_core/Q_sg over time. No matplotlib.

Run:
    uv run python examples/report_primary.py

Note on intentional duplication: this script holds its own copy of the plant
wiring, identical in shape to those in ``run_primary.py`` and
``tests/test_primary_plant.py``. See the spec at
``docs/superpowers/specs/2026-05-04-primary-loop-and-secondary-design.md`` §10.
"""

from __future__ import annotations

import numpy as np
from scipy.integrate import solve_ivp

from fission_sim.physics.core import CoreParams, PointKineticsCore
from fission_sim.physics.primary_loop import LoopParams, PrimaryLoop
from fission_sim.physics.secondary_sink import SecondarySink, SinkParams
from fission_sim.physics.steam_generator import SGParams, SteamGenerator


def rod_reactivity_fn(t: float) -> float:
    if t < 10.0:
        return 0.0
    if t < 60.0:
        return 200e-5
    return -7000e-5


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
    # --- assemble plant ---
    core = PointKineticsCore(CoreParams())
    loop = PrimaryLoop(LoopParams())
    sg = SteamGenerator(SGParams())
    sink = SecondarySink(SinkParams())
    y0 = np.concatenate([core.initial_state(), loop.initial_state()])

    def f(t, y):
        s_core = y[0:8]
        s_loop = y[8:10]
        out_sink = sink.outputs(np.empty(0))
        out_loop = loop.outputs(s_loop)
        out_sg = sg.outputs(
            np.empty(0),
            inputs={
                "T_primary": out_loop["T_avg"],
                "T_secondary": out_sink["T_secondary"],
            },
        )
        out_core = core.outputs(s_core)
        dy = np.empty_like(y)
        dy[0:8] = core.derivatives(
            s_core,
            inputs={
                "rod_reactivity": rod_reactivity_fn(t),
                "T_cool": out_loop["T_cool"],
            },
        )
        dy[8:10] = loop.derivatives(
            s_loop,
            inputs={
                "Q_core": out_core["power_thermal"],
                "Q_sg": out_sg["Q_sg"],
            },
        )
        return dy

    sol = solve_ivp(
        f,
        (0.0, 300.0),
        y0,
        method="BDF",
        dense_output=True,
        rtol=1e-6,
        atol=1e-9,
        max_step=0.5,
    )
    if not sol.success:
        raise RuntimeError(f"solve_ivp failed: {sol.message}")

    print()
    print("=" * 80)
    print("  Coupled Primary Plant  —  default scenario  (text report)")
    print("=" * 80)
    print()
    print("  Scenario:")
    print("    t = 0..10 s   steady state at design power")
    print("    t = 10 s      rod step  +200 pcm")
    print("    t = 10..60 s  Doppler AND moderator feedback level power off")
    print("    t = 60 s      scram  -7000 pcm")
    print("    t = 60..300 s delayed-neutron tail; loop water cools")
    print()

    # --- table at key time points ---
    sample_t = np.array([0, 5, 10, 10.5, 12, 30, 60, 60.5, 80, 150, 300])
    Y = sol.sol(sample_t)
    n = Y[0]
    T_fuel = Y[7]
    T_hot = Y[8]
    T_cold = Y[9]
    T_avg = (T_hot + T_cold) / 2

    print("  Time-series at key points:")
    header = "    ------------------------------------------------------------------------------"
    print(header)
    print("       t[s]      n       T_fuel    T_hot    T_cold   T_avg    Q_core   Q_sg")
    print("                            [K]      [K]      [K]     [K]    [GW]   [GW]")
    print(header)
    p_core = core.params
    UA = sg.params.UA
    T_sec = sink.params.T_secondary
    for ti, ni, Tfi, Thi, Tci, Tavi in zip(sample_t, n, T_fuel, T_hot, T_cold, T_avg):
        Q_core_v = ni * p_core.P_design
        Q_sg_v = UA * (Tavi - T_sec)
        print(
            f"    {ti:6.1f}  {ni:8.3e}  {Tfi:7.2f}  {Thi:7.2f}  {Tci:7.2f}"
            f"  {Tavi:6.2f}  {Q_core_v / 1e9:6.3f}  {Q_sg_v / 1e9:6.3f}"
        )
    print(header)
    print()

    # --- charts ---
    chart_t = np.array([0, 2, 5, 10, 10.5, 13, 30, 60, 60.5, 80, 150, 300])
    chart_Y = sol.sol(chart_t)
    chart_n = chart_Y[0]
    chart_Tavg = (chart_Y[8] + chart_Y[9]) / 2

    print("  Neutron population n  (log scale, n=1 at design power):")
    print()
    ascii_log_chart(chart_t, chart_n, width=52, vmin=1e-4, vmax=1e2, label="n")
    print()

    print("  Loop average temperature T_avg [K]:")
    print()
    ascii_linear_chart(chart_t, chart_Tavg, width=52, label="T_avg", unit="K")
    print()

    print("  Energy balance check (Q_core vs Q_sg at key times, both in GW):")
    print()
    print("                  Q_core       Q_sg      ΔQ        rel")
    for ti in [0.0, 30.0, 100.0, 300.0]:
        Y_t = sol.sol(np.array([ti]))
        n_t = Y_t[0, 0]
        Tav_t = (Y_t[8, 0] + Y_t[9, 0]) / 2
        Qc = n_t * p_core.P_design
        Qs = UA * (Tav_t - T_sec)
        rel = abs(Qc - Qs) / max(abs(Qc), 1.0)
        print(f"    t = {ti:5.1f} s  {Qc / 1e9:6.3f}     {Qs / 1e9:6.3f}     {(Qc - Qs) / 1e9:7.4f}   {rel:8.2%}")
    print()

    print("  What this shows:")
    print("    * Steady state holds at n=1 with Q_core == Q_sg by construction.")
    print("    * After +200 pcm rod step: power rises, fuel and loop water both heat.")
    print("      Doppler AND moderator feedback both push back; new equilibrium is")
    print("      reached at slightly higher power than at start.")
    print("    * After scram (-7000 pcm): power drops fast; loop water cools more")
    print("      slowly because of its larger thermal mass (~30000 kg of water at")
    print("      c_p=5500 J/kg/K is more inertial than ~100000 kg fuel at 300 J/kg/K).")
    print("    * Energy balance gap (Q_core − Q_sg) is the rate at which the loop")
    print("      water is gaining or losing thermal energy — closes to zero at steady.")
    print()


if __name__ == "__main__":
    main()
