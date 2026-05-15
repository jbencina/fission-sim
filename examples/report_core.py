"""Text-only diagnostic for the PointKineticsCore.

Throwaway sibling of `run_core.py` for use over SSH or in any terminal
without a display attached. Same default scenario; output is a printed
table at key time points plus an ASCII log-scale chart of neutron
population over time. No matplotlib.

Run:
    uv run python examples/report_core.py
"""

from __future__ import annotations

import numpy as np
from scipy.integrate import solve_ivp

from fission_sim.disclaimer import print_disclaimer
from fission_sim.physics.core import CoreParams, PointKineticsCore


# ---------------------------------------------------------------------------
# Faked upstream input sources (same scenario as run_core.py).
# ---------------------------------------------------------------------------
def rod_reactivity_fn(t: float) -> float:
    if t < 10.0:
        return 0.0
    if t < 60.0:
        return 200e-5  # +200 pcm step
    return -7000e-5  # scram


def T_cool_fn(t: float) -> float:
    return 580.0  # constant; primary loop component will replace this


# ---------------------------------------------------------------------------
# Tiny ASCII log-axis chart. One line per time sample, * marks position.
# ---------------------------------------------------------------------------
def ascii_log_chart(times, values, width=50, vmin=None, vmax=None, label="value"):
    """Print a horizontal log-scale chart of `values` vs `times`.

    Parameters
    ----------
    times, values : 1-D arrays of equal length
    width : int
        Width of the plot region in characters.
    vmin, vmax : float, optional
        Log-axis limits. Auto-derived from data if omitted.
    label : str
        Quantity label for the column header.
    """
    v = np.asarray(values, dtype=float)
    # Clip non-positive (log undefined). With our scenario n stays > 0.
    v = np.where(v > 0, v, np.nan)
    log_v = np.log10(v)
    lo = float(np.nanmin(log_v)) if vmin is None else np.log10(vmin)
    hi = float(np.nanmax(log_v)) if vmax is None else np.log10(vmax)
    # Pad slightly so endpoints aren't exactly on the border.
    pad = 0.05 * (hi - lo) if hi > lo else 0.5
    lo -= pad
    hi += pad

    # Header: log decades inside the plot region.
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


def main() -> None:
    print_disclaimer()
    params = CoreParams()
    core = PointKineticsCore(params)
    y0 = core.initial_state()

    def f(t, y):
        return core.derivatives(
            y,
            {
                "rho_rod": rod_reactivity_fn(t),
                "T_cool": T_cool_fn(t),
            },
        )

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
    print("=" * 76)
    print("  PointKineticsCore  —  default scenario  (text report)")
    print("=" * 76)
    print()
    print("  Scenario:")
    print("    t = 0..10 s   steady state at design power")
    print("    t = 10 s      rod step  +200 pcm")
    print("    t = 10..60 s  Doppler feedback levels power off")
    print("    t = 60 s      scram  -7000 pcm")
    print("    t = 60..300 s delayed-neutron tail")
    print()

    # --- table of key time points ---
    sample_t = np.array([0, 5, 10, 10.5, 12, 20, 40, 60, 60.2, 62, 80, 150, 300])
    Y = sol.sol(sample_t)
    n = Y[0]
    T_fuel = Y[7]
    PCM = 1e5

    print("  Time-series at key points (reactivity in pcm = 1e-5):")
    print("    -----------------------------------------------------------------------")
    print("       t[s]     n         T_fuel[K]   rho_rod  rho_doppler  rho_mod  total")
    print("    -----------------------------------------------------------------------")
    for ti, ni, Ti in zip(sample_t, n, T_fuel):
        rho_rod = rod_reactivity_fn(float(ti))
        rho_dop = params.alpha_f * (Ti - params.T_fuel_ref)
        rho_mod = params.alpha_m * (T_cool_fn(float(ti)) - params.T_cool_ref)
        rho_tot = rho_rod + rho_dop + rho_mod
        print(
            f"    {ti:6.1f}  {ni:9.3e}  {Ti:8.2f}    "
            f"{rho_rod * PCM:7.1f}    {rho_dop * PCM:8.1f}   {rho_mod * PCM:6.1f}  "
            f"{rho_tot * PCM:7.1f}"
        )
    print("    -----------------------------------------------------------------------")
    print()

    # --- ASCII chart of n on log scale ---
    print("  Neutron population n  (log scale, n=1 at design power):")
    print()
    chart_t = np.array([0, 2, 5, 8, 10, 10.5, 11, 13, 18, 30, 50, 60, 60.5, 65, 80, 120, 200, 300])
    chart_n = sol.sol(chart_t)[0]
    ascii_log_chart(chart_t, chart_n, width=52, vmin=1e-4, vmax=1e2, label="n")
    print()

    # --- ASCII chart of T_fuel (linear-axis, but reusing log helper requires
    # values above 1; offset by min so chart is meaningful) ---
    chart_T = sol.sol(chart_t)[7]
    print("  Fuel temperature  T_fuel [K]:")
    print()
    Tlo, Thi = float(chart_T.min()), float(chart_T.max())
    span = max(Thi - Tlo, 1.0)
    width = 52
    print(f"   t [s]     T_fuel        |{Tlo:6.1f}{' ' * (width - 14)}{Thi:6.1f}|")
    for ti, Ti in zip(chart_t, chart_T):
        col = int(round((Ti - Tlo) / span * (width - 1)))
        col = max(0, min(width - 1, col))
        row = [" "] * width
        row[col] = "*"
        print(f"   {ti:6.1f}    {Ti:8.2f}      " + "".join(row))
    print()

    # --- summary ---
    print("  What this shows:")
    print("    * Steady state holds at n = 1.0 with derivatives = 0 by construction.")
    print("    * After +200 pcm rod step: prompt jump (~0.5 s), then exponential rise,")
    print("      then Doppler feedback (negative rho as fuel heats) levels power off.")
    print("    * After scram (-7000 pcm): power drops by ~3 orders of magnitude in ~1 s,")
    print("      then a slow tail dominated by long-lived precursors (C1, ~55 s half-life).")
    print()


if __name__ == "__main__":
    main()
