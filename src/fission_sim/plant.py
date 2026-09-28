"""The standard primary plant, assembled in one call.

``build_standard_plant()`` wires the seven components of the simulated
pressurized-water-reactor primary plant into a finalized ``SimEngine``:

    rod ──rho_rod──▶ core ──Q_fuel_to_coolant──▶ loop, pzr
    loop ──T_cool──▶ core          (coolant temperature the core sees)
    loop ──T_avg──▶ sg ──Q_sg──▶ loop, pzr
    sink ──T_secondary──▶ sg       (fixed secondary-side temperature)
    loop ──T_hot, T_cold──▶ pzr    (temperature of water surging in or out)
    pzr ──P──▶ pzr_ctrl ──Q_heater, m_dot_spray──▶ pzr
    pzr ──P──▶ loop,  pzr_ctrl ──m_dot_spray──▶ loop

Operator commands enter as five engine externals: ``rod_command``,
``scram``, ``P_setpoint``, ``heater_manual`` and ``spray_manual`` (the last
two ``None`` = automatic control).

The web runtime and the operational examples use this factory so they all
simulate the same plant. To see every ``engine.module``/``engine.input``
call and each wire spelled out, read ``examples/run_primary.py`` or the
engine tutorial in DEVELOPMENT.md. They are the two deliberately expanded
copies of this wiring, kept in step with this module by
``tests/test_examples.py`` and ``tests/test_docs.py``.

This module sits beside the engine and physics packages, not in the API
layer, so command-line examples can import it without pulling in FastAPI.
"""

from __future__ import annotations

from fission_sim.control.pressurizer_controller import (
    PressurizerController,
    PressurizerControllerParams,
)
from fission_sim.engine import SimEngine
from fission_sim.physics.core import CoreParams, PointKineticsCore
from fission_sim.physics.pressurizer import Pressurizer, PressurizerParams
from fission_sim.physics.primary_loop import LoopParams, PrimaryLoop
from fission_sim.physics.rod_controller import RodController, RodParams
from fission_sim.physics.secondary_sink import SecondarySink, SinkParams
from fission_sim.physics.steam_generator import SGParams, SteamGenerator


def build_standard_plant(
    *,
    core_params: CoreParams | None = None,
    loop_params: LoopParams | None = None,
    sg_params: SGParams | None = None,
    sink_params: SinkParams | None = None,
    rod_params: RodParams | None = None,
    pzr_params: PressurizerParams | None = None,
    ctrl_params: PressurizerControllerParams | None = None,
    rod_command: float | None = None,
    P_setpoint: float | None = None,
) -> SimEngine:
    """Build and finalize the standard primary plant.

    Every parameter object defaults to its design-point values, so
    ``build_standard_plant()`` starts at steady full power. Pass an object
    to change one component, e.g. ``core_params=CoreParams(alpha_m=...)``.

    Module names (the snapshot keys) are ``rod``, ``core``, ``loop``,
    ``sg``, ``sink``, ``pzr`` and ``pzr_ctrl``. These are the names
    ``physics.domain.check_snapshot`` expects.

    Parameters
    ----------
    core_params, loop_params, sg_params, sink_params, rod_params : optional
        Component parameters; ``None`` uses the defaults.
    pzr_params : PressurizerParams, optional
        ``None`` builds ``PressurizerParams(loop_params=loop_params)``. The
        pressurizer computes surge flow from the loop's thermal expansion,
        so a supplied object must carry the same loop parameters as the loop
        (if only ``pzr_params`` is given, the loop uses its ``loop_params``).
    ctrl_params : PressurizerControllerParams, optional
        Pressurizer pressure controller parameters.
    rod_command : float, optional
        Default rod command external, fraction withdrawn [0..1]; ``None``
        uses the rod's initial position (``rod_params.rod_position_initial``,
        else the design full-power position 0.5), so the rods start at rest.
    P_setpoint : float, optional
        Default pressure setpoint external [Pa]; ``None`` uses
        ``ctrl_params.P_setpoint_default`` (15.5 MPa).

    Returns
    -------
    SimEngine
        Finalized engine at t = 0, ready for ``step()`` or ``run()``.

    Raises
    ------
    ValueError
        If ``pzr_params.loop_params`` differs from ``loop_params``.
    """
    if core_params is None:
        core_params = CoreParams()
    if loop_params is None:
        loop_params = LoopParams() if pzr_params is None else pzr_params.loop_params
    if sg_params is None:
        sg_params = SGParams()
    if sink_params is None:
        sink_params = SinkParams()
    if rod_params is None:
        rod_params = RodParams()
    if pzr_params is None:
        pzr_params = PressurizerParams(loop_params=loop_params)
    if ctrl_params is None:
        ctrl_params = PressurizerControllerParams()
    if pzr_params.loop_params != loop_params:
        raise ValueError(
            "pzr_params.loop_params must match loop_params: the pressurizer's "
            "surge flow is computed from the loop's thermal expansion"
        )
    if rod_command is None:
        rod_command = (
            rod_params.rod_position_design
            if rod_params.rod_position_initial is None
            else rod_params.rod_position_initial
        )
    if P_setpoint is None:
        P_setpoint = ctrl_params.P_setpoint_default

    engine = SimEngine()
    rod = engine.module(RodController(rod_params), name="rod")
    core = engine.module(PointKineticsCore(core_params), name="core")
    loop = engine.module(PrimaryLoop(loop_params), name="loop")
    sg = engine.module(SteamGenerator(sg_params), name="sg")
    sink = engine.module(SecondarySink(sink_params), name="sink")
    pzr = engine.module(Pressurizer(pzr_params), name="pzr")
    pzr_ctrl = engine.module(PressurizerController(ctrl_params), name="pzr_ctrl")

    # Operator commands; step()/run() override these defaults per call.
    rod_cmd = engine.input("rod_command", default=rod_command)
    scram = engine.input("scram", default=False)
    P_set = engine.input("P_setpoint", default=P_setpoint)
    heater_manual = engine.input("heater_manual", default=None)
    spray_manual = engine.input("spray_manual", default=None)

    # Wiring order does not matter: finalize() sorts the evaluation order.
    rod(rod_command=rod_cmd, scram=scram)
    T_sec = sink()
    Q_sg = sg(T_avg=loop.T_avg, T_secondary=T_sec)
    core(rho_rod=rod.rho_rod, T_cool=loop.T_cool)
    pzr(
        Q_fuel_to_coolant=core.Q_fuel_to_coolant,
        Q_sg=Q_sg,
        T_hotleg=loop.T_hot,
        T_coldleg=loop.T_cold,
        Q_heater=pzr_ctrl.Q_heater,
        m_dot_spray=pzr_ctrl.m_dot_spray,
    )
    pzr_ctrl(P=pzr.P, P_setpoint=P_set, heater_manual=heater_manual, spray_manual=spray_manual)
    loop(
        Q_fuel_to_coolant=core.Q_fuel_to_coolant,
        Q_sg=Q_sg,
        m_dot_spray=pzr_ctrl.m_dot_spray,
        P_primary=pzr.P,
    )

    engine.finalize()
    return engine


__all__ = ["build_standard_plant"]
