"""Focused review probes for baseline 5dc6e64; these are not acceptance tests.

Run from the repository root after installing its locked Python dependencies:
    .venv/bin/python reviews/reproduce.py
    .venv/bin/python reviews/reproduce.py --transients

The runtime probes intentionally inspect private state to diagnose lifecycle
bugs. Production code should not depend on those private attributes.
"""

from __future__ import annotations

import argparse
import asyncio

from scipy.integrate import solve_ivp

from fission_sim.api.runtime import SimRuntime
from fission_sim.physics import coolprop
from fission_sim.physics.core import CoreParams, PointKineticsCore
from fission_sim.physics.primary_loop import LoopParams, PrimaryLoop
from fission_sim.physics.rod_controller import RodController, RodParams


def energy_balance() -> None:
    """Isolate the fuel/loop heat-interface mismatch at one physical state."""
    p, lp = CoreParams(), LoopParams()
    core, loop = PointKineticsCore(p), PrimaryLoop(lp)
    state = core.initial_state()
    state[0] = 0.1  # Fission falls before stored fuel heat has dissipated.
    power = core.outputs(state)["power_thermal"]
    fuel_d = core.derivatives(state, {"rho_rod": -0.07, "T_cool": lp.T_avg_ref})
    loop_d = loop.derivatives(loop.initial_state(), {
        "power_thermal": power, "Q_sg": p.P_design,
        "m_dot_spray": 0.0, "P_primary": lp.P_ref,
    })
    stored = p.M_fuel * p.c_p_fuel * fuel_d[7]
    stored += lp.c_p * (lp.M_hot * loop_d[0] + lp.M_cold * loop_d[1])
    expected = power - p.P_design
    print("A1: combined fuel/loop storage =", stored / 1e6, "MW;")
    print("    external fission minus SG =", expected / 1e6, "MW;")
    print("    residual =", (stored - expected) / 1e6, "MW")


def parameters_and_rods() -> None:
    lp = LoopParams()
    print("A3: effective thermal mass / actual coolant mass [kg] =",
          lp.M_hot + lp.M_cold, lp.M_loop_initial)
    for temperature in (568, 583, 598):
        print("A6: beta_T at", temperature, "K =",
              coolprop.beta_T(lp.P_ref, temperature), "/K")
    for position in (0.5, 1.0):
        rod = RodController(RodParams(rod_position_initial=position))
        sol = solve_ivp(
            lambda t, y: rod.derivatives(y, {"rod_command": position, "scram": True}),
            (0, 5), rod.initial_state(), method="BDF", dense_output=True,
            rtol=1e-9, atol=1e-12,
        )
        print("A4: SCRAM from", position, "position at 2s / 4s =",
              sol.sol(2)[0], sol.sol(4)[0])
    asymmetric = PrimaryLoop(LoopParams(M_hot=10000, M_cold=20000))
    state = asymmetric.initial_state()
    state[0] += 1
    d = asymmetric.derivatives(state, {
        "power_thermal": 3e9, "Q_sg": 3e9,
        "m_dot_spray": 0.0, "P_primary": 15.5e6,
    })
    print("A7: unequal masses: dT_avg/dt =", (d[0] + d[1]) / 2,
          "K/s, reported surge =", -d[2], "kg/s")


async def runtime_lifecycle() -> None:
    runtime = SimRuntime()
    await runtime.start()
    queue = runtime.subscribe()
    try:
        await asyncio.wait_for(queue.get(), timeout=2)
        runtime.pause()
        while (await asyncio.wait_for(queue.get(), timeout=2))["running"]:
            pass
        print("C2: paused SCRAM response =",
              await runtime.handle_command({"type": "scram"}))
        print("    command / displayed scrammed =", runtime._cmd.scrammed,
              runtime.snapshot()["scrammed"])
        new_queue = runtime.subscribe()
        print("    new subscriber has initial frame =", not new_queue.empty())
        runtime.unsubscribe(new_queue)
        runtime.resume()
        await asyncio.gather(
            runtime.handle_command({"type": "reset"}),
            runtime.handle_command({"type": "reset"}),
        )
        loops = [task for task in asyncio.all_tasks()
                 if task.get_name() == "sim-step-loop" and not task.done()]
        print("C1: live loops after two resets =", len(loops))
        await runtime.stop()
        loops = [task for task in loops if not task.done()]
        print("    loops remaining after stop =", len(loops))
    finally:
        runtime.unsubscribe(queue)
        await runtime.stop()
        # This standalone process owns every sim-step-loop; clean up the leak.
        leftovers = [task for task in asyncio.all_tasks()
                     if task.get_name() == "sim-step-loop" and not task.done()]
        for task in leftovers:
            task.cancel()
        await asyncio.gather(*leftovers, return_exceptions=True)


def transients() -> None:
    engine = SimRuntime()._engine
    _, dense = engine.run(12, scenario_fn=lambda t: {"scram": t >= 2},
                          dense=True, max_step=0.1)
    p = CoreParams()
    print("A1: ordinary SCRAM trajectory [s, fission MW, heat leaving fuel MW]")
    for t in (2.1, 2.5, 3, 4, 7, 12):
        snap = dense.at(t)
        heat = p.hA_fc * (snap["core"]["T_fuel"] - snap["loop"]["T_avg"])
        print(t, snap["core"]["power_thermal"] / 1e6, heat / 1e6)
    engine = SimRuntime()._engine
    for _ in range(400):
        try:
            engine.step(0.1, rod_command=0.6)
        except ValueError as error:
            print("A2: accepted rod command 0.6 fails after t =", engine.t)
            print(error)
            break
    else:
        print("A2: command 0.6 completed 40 seconds without an error")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transients", action="store_true")
    args = parser.parse_args()
    energy_balance()
    parameters_and_rods()
    asyncio.run(runtime_lifecycle())
    if args.transients:
        transients()
