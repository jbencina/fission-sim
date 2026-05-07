"""Diagnostic state dump for the coupled primary plant — wired through SimEngine.

Prints the full snapshot dict at sample times. SSH-friendly. No matplotlib.

Run:
    uv run python examples/dump_state.py
"""

from __future__ import annotations

import numpy as np

from fission_sim.engine import SimEngine
from fission_sim.physics.core import CoreParams, PointKineticsCore
from fission_sim.physics.primary_loop import LoopParams, PrimaryLoop
from fission_sim.physics.rod_controller import RodController, RodParams
from fission_sim.physics.secondary_sink import SecondarySink, SinkParams
from fission_sim.physics.steam_generator import SGParams, SteamGenerator


def scenario(t: float) -> dict:
    return {
        "rod_command": 0.5 if t < 10.0 else 0.515,
        "scram": t >= 60.0,
    }


def _fmt(v) -> str:
    """Format a value for the dump."""
    if isinstance(v, (np.floating, float, int)):
        return f"{float(v):+.6e}"
    return repr(v)


def main() -> None:
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

    _final, dense = engine.run(t_end=300.0, scenario_fn=scenario, dense=True)

    sample_t = np.array([0.0, 5.0, 10.0, 30.0, 60.5, 100.0, 300.0])
    print()
    print("=" * 80)
    print("  Coupled primary plant — full state dump at sample times")
    print("=" * 80)
    for ti in sample_t:
        snap = dense.at(float(ti))
        print()
        print(f"  t = {ti:6.2f} s")
        print("    signals:")
        for k, v in sorted(snap["signals"].items()):
            print(f"      {k:18s} = {_fmt(v)}")
        for module_name in ("core", "loop", "rod", "sg", "sink"):
            tele = snap.get(module_name, {})
            if not tele:
                continue
            print(f"    {module_name}:")
            for k, v in sorted(tele.items()):
                print(f"      {k:18s} = {_fmt(v)}")


if __name__ == "__main__":
    main()
