"""Dump every state value and full telemetry at key time points.

Comprehensive snapshot of the coupled primary plant + rod controller —
shows the entire 11-element state vector (which the integrator advances)
plus the full telemetry dict from every component (the rich diagnostic
view).

Useful when you want to see exactly what the simulation knows at each
moment.

Run:
    uv run python examples/dump_state.py

Note on intentional duplication: this script holds its own copy of the
plant wiring, identical in shape to ``tests/test_primary_plant.py``,
``examples/run_primary.py``, and ``examples/report_primary.py``. The
duplication accumulates the signal that the engine should be extracted
in slice 4.
"""

from __future__ import annotations

import numpy as np
from scipy.integrate import solve_ivp

from fission_sim.physics.core import CoreParams, PointKineticsCore
from fission_sim.physics.primary_loop import LoopParams, PrimaryLoop
from fission_sim.physics.rod_controller import RodController, RodParams
from fission_sim.physics.secondary_sink import SecondarySink, SinkParams
from fission_sim.physics.steam_generator import SGParams, SteamGenerator


def rod_command_fn(t: float) -> float:
    """Same default scenario as run_primary.py / report_primary.py."""
    if t < 10.0:
        return 0.5
    return 0.515


def scram_fn(t: float) -> bool:
    return t >= 60.0


def main() -> None:
    core = PointKineticsCore(CoreParams())
    loop = PrimaryLoop(LoopParams())
    sg = SteamGenerator(SGParams())
    sink = SecondarySink(SinkParams())
    rod = RodController(RodParams())
    y0 = np.concatenate([core.initial_state(), loop.initial_state(), rod.initial_state()])

    def f(t, y):
        s_core = y[0:8]
        s_loop = y[8:10]
        s_rod = y[10:11]
        out_sink = sink.outputs(np.empty(0))
        out_loop = loop.outputs(s_loop)
        out_sg = sg.outputs(
            np.empty(0),
            inputs={"T_primary": out_loop["T_avg"], "T_secondary": out_sink["T_secondary"]},
        )
        out_core = core.outputs(s_core)
        out_rod = rod.outputs(s_rod)
        dy = np.empty_like(y)
        dy[0:8] = core.derivatives(s_core, inputs={"rho_rod": out_rod["rho_rod"], "T_cool": out_loop["T_cool"]})
        dy[8:10] = loop.derivatives(s_loop, inputs={"power_thermal": out_core["power_thermal"], "Q_sg": out_sg["Q_sg"]})
        dy[10:11] = rod.derivatives(s_rod, inputs={"rod_command": rod_command_fn(t), "scram": scram_fn(t)})
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

    sample_t = [0.0, 10.0, 11.0, 30.0, 60.0, 60.5, 100.0, 300.0]

    for t in sample_t:
        y = sol.sol(np.array([t])).flatten()
        s_core = y[0:8]
        s_loop = y[8:10]
        s_rod = y[10:11]
        rod_cmd = rod_command_fn(t)
        scr = scram_fn(t)

        out_sink = sink.outputs(np.empty(0))
        out_loop = loop.outputs(s_loop)
        out_sg = sg.outputs(
            np.empty(0),
            inputs={"T_primary": out_loop["T_avg"], "T_secondary": out_sink["T_secondary"]},
        )
        out_rod = rod.outputs(s_rod)

        core_tele = core.telemetry(s_core, inputs={"rho_rod": out_rod["rho_rod"], "T_cool": out_loop["T_cool"]})
        loop_tele = loop.telemetry(s_loop, inputs={"power_thermal": core_tele["power_thermal"], "Q_sg": out_sg["Q_sg"]})
        sg_tele = sg.telemetry(
            np.empty(0),
            inputs={"T_primary": out_loop["T_avg"], "T_secondary": out_sink["T_secondary"]},
        )
        sink_tele = sink.telemetry(np.empty(0))
        rod_tele = rod.telemetry(s_rod, inputs={"rod_command": rod_cmd, "scram": scr})

        print()
        print("=" * 78)
        print(f"  t = {t:7.2f} s")
        print("=" * 78)

        print("  RAW STATE VECTOR (11 values; the integrator advances exactly these)")
        print(f"    y[0]  n            = {s_core[0]:.6e}    (neutron population, dimensionless)")
        for i in range(6):
            print(f"    y[{i + 1}]  C{i + 1}           = {s_core[i + 1]:.6e}    (precursor group {i + 1})")
        print(f"    y[7]  T_fuel       = {s_core[7]:9.4f} K     (lumped fuel temperature)")
        print(f"    y[8]  T_hot        = {s_loop[0]:9.4f} K     (primary hot leg)")
        print(f"    y[9]  T_cold       = {s_loop[1]:9.4f} K     (primary cold leg)")
        print(f"    y[10] rod_position = {s_rod[0]:.6f}     (0=fully in, 1=fully out)")

        print()
        print("  PointKineticsCore.telemetry:")
        print(f"    power_thermal  = {core_tele['power_thermal']:.4e} W   (= n * P_design)")
        print(f"    T_fuel         = {core_tele['T_fuel']:9.4f} K")
        print(f"    n              = {core_tele['n']:.6e}")
        for i in range(6):
            label = f"C{i + 1}"
            print(f"    {label:14s} = {core_tele[label]:.6e}")
        print(f"    rho_rod        = {core_tele['rho_rod'] * 1e5:+9.2f} pcm")
        print(f"    rho_doppler    = {core_tele['rho_doppler'] * 1e5:+9.2f} pcm")
        print(f"    rho_moderator  = {core_tele['rho_moderator'] * 1e5:+9.2f} pcm")
        print(f"    rho_total      = {core_tele['rho_total'] * 1e5:+9.2f} pcm")

        print()
        print("  PrimaryLoop.telemetry:")
        print(f"    T_hot          = {loop_tele['T_hot']:9.4f} K")
        print(f"    T_cold         = {loop_tele['T_cold']:9.4f} K")
        print(f"    T_avg          = {loop_tele['T_avg']:9.4f} K")
        print(f"    T_cool         = {loop_tele['T_cool']:9.4f} K")
        print(f"    delta_T        = {loop_tele['delta_T']:9.4f} K")
        print(f"    power_thermal  = {loop_tele['power_thermal'] / 1e9:9.4f} GW")
        print(f"    Q_sg           = {loop_tele['Q_sg'] / 1e9:9.4f} GW")
        print(f"    Q_flow         = {loop_tele['Q_flow'] / 1e9:9.4f} GW")

        print()
        print("  SteamGenerator.telemetry:")
        print(f"    T_primary      = {sg_tele['T_primary']:9.4f} K")
        print(f"    T_secondary    = {sg_tele['T_secondary']:9.4f} K")
        print(f"    delta_T        = {sg_tele['delta_T']:9.4f} K")
        print(f"    Q_sg           = {sg_tele['Q_sg'] / 1e9:9.4f} GW")

        print()
        print("  SecondarySink.telemetry:")
        print(f"    T_secondary    = {sink_tele['T_secondary']:9.4f} K     (constant)")

        print()
        print("  RodController.telemetry:")
        print(f"    rod_position           = {rod_tele['rod_position']:.6f}")
        print(f"    rho_rod                = {rod_tele['rho_rod'] * 1e5:+9.2f} pcm")
        print(f"    rod_command            = {rod_tele['rod_command']:.6f}")
        print(f"    scram                  = {rod_tele['scram']}")
        print(f"    rod_command_effective  = {rod_tele['rod_command_effective']:.6f}")


if __name__ == "__main__":
    main()
