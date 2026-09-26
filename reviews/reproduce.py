"""Focused review probes for baseline 5dc6e64; these are not acceptance tests.

Run from the repository root after installing its locked Python dependencies:
    .venv/bin/python reviews/reproduce.py
    .venv/bin/python reviews/reproduce.py --transients

Probe labels match the finding identifiers in accuracy.md and craft.md.
The A8/A9 probes and the second A2 branch were added by the second-pass
audit.

The runtime probes intentionally inspect private state to diagnose lifecycle
bugs. Production code should not depend on those private attributes.
"""

from __future__ import annotations

import argparse
import asyncio

from scipy.integrate import solve_ivp

from fission_sim.api.runtime import (
    PressurizerControllerParams,
    PressurizerParams,
    SimRuntime,
    SinkParams,
    _build_engine,
)
from fission_sim.physics import coolprop
from fission_sim.physics.core import CoreParams, PointKineticsCore
from fission_sim.physics.primary_loop import LoopParams, PrimaryLoop
from fission_sim.physics.rod_controller import RodController, RodParams
from fission_sim.physics.steam_generator import SGParams


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
    p, sg = CoreParams(), SGParams()
    bank = RodController(RodParams())
    state = bank.initial_state()
    state[0] = 0.6
    print("A8: rod command 0.6 is worth [pcm] =", bank.outputs(state)["rho_rod"] * 1e5,
          "; one dollar [pcm] =", p.beta_i.sum() * 1e5)
    print("A9: tau_fuel / tau_loop configured / tau_loop inventory [s] =",
          p.M_fuel * p.c_p_fuel / p.hA_fc,
          (lp.M_hot + lp.M_cold) * lp.c_p / sg.UA,
          lp.M_loop_initial * lp.c_p / sg.UA)
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
    # Same command with physically consistent loop thermal mass: no error,
    # but the hot leg boils and density_PT silently returns vapor density.
    half = LoopParams().M_loop_initial / 2
    lp = LoopParams(M_hot=half, M_cold=half)
    engine = _build_engine(
        core_params=CoreParams(), loop_params=lp, sg_params=SGParams(),
        sink_params=SinkParams(), rod_params=RodParams(),
        pzr_params=PressurizerParams(loop_params=lp),
        ctrl_params=PressurizerControllerParams(),
        rod_command_default=0.5, P_setpoint_default=1.55e7,
    )
    crossed = None
    for _ in range(600):
        snap = engine.step(0.1, rod_command=0.6)
        P, T_hot = snap["pzr"]["P"], snap["loop"]["T_hot"]
        if crossed is None and T_hot > coolprop.T_sat(P):
            crossed = engine.t
    print("A2: with M_hot = M_cold =", round(half), "kg the same command raises nothing;")
    print("    T_hot crossed T_sat at t =", crossed, "s; at t = 60 s subcooling =",
          coolprop.T_sat(P) - T_hot, "K, density_PT =", coolprop.density_PT(P=P, T=T_hot), "kg/m3")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transients", action="store_true")
    args = parser.parse_args()
    energy_balance()
    parameters_and_rods()
    asyncio.run(runtime_lifecycle())
    if args.transients:
        transients()
