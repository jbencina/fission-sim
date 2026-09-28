"""Diagnostic state dump for the standard primary plant.

Runs the same rod-step-then-scram scenario as ``run_primary.py`` and prints
the full snapshot at a few sample times: every wired signal, then every
module's telemetry (core, loop, rod, SG, secondary shell, turbine,
feedwater/Tavg controls, pressurizer and pressurizer controller).
SSH-friendly. No matplotlib.

Run:
    uv run python examples/dump_state.py
"""

from __future__ import annotations

import numpy as np

from fission_sim.disclaimer import print_disclaimer
from fission_sim.physics.domain import check_snapshot
from fission_sim.plant import build_standard_plant


def scenario(t: float) -> dict:
    """Operator inputs over time (same as run_primary.py)."""
    return {
        "rod_command": 0.5 if t < 10.0 else 0.675,
        "scram": t >= 60.0,
    }


def _fmt(v) -> str:
    """Format a value for the dump."""
    if isinstance(v, (np.floating, float, int)) and not isinstance(v, bool):
        return f"{float(v):+.6e}"
    return repr(v)


def print_snapshot(snap: dict) -> None:
    """Print one snapshot: resolved signals, then each module's telemetry.

    Iterates over whatever modules the snapshot holds, so a module added to
    the plant shows up here without editing this function.
    """
    print()
    print(f"  t = {snap['t']:6.2f} s")
    print("    signals:")
    for k, v in sorted(snap["signals"].items()):
        print(f"      {k:18s} = {_fmt(v)}")
    for module_name, tele in snap.items():
        if module_name in ("t", "signals") or not tele:
            continue
        print(f"    {module_name}:")
        for k, v in sorted(tele.items()):
            print(f"      {k:18s} = {_fmt(v)}")


def main() -> None:
    print_disclaimer()
    engine = build_standard_plant()
    _final, dense = engine.run(t_end=300.0, scenario_fn=scenario, dense=True)

    print()
    print("=" * 80)
    print("  Standard primary plant — full state dump at sample times")
    print("=" * 80)
    for ti in (0.0, 5.0, 10.0, 30.0, 60.5, 100.0, 300.0):
        snap = dense.at(ti)
        # Stop with an explanation if the state has left the model's domain
        # (checks the printed samples only).
        check_snapshot(snap)
        print_snapshot(snap)


if __name__ == "__main__":
    main()
