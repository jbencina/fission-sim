"""The standard M4 primary/secondary plant, assembled in one call.

``build_standard_plant()`` wires the coupled pressurized-water-reactor
learning plant into a finalized ``SimEngine``:

    turbine_load, turbine_trip, scram ─▶ turbine ◀── P_steam ─┐
                                    │ m_steam, m_dump        │
                                    ▼                        │
    loop.T_avg ─▶ sg ──Q_sg──▶ sg_sec ──T_secondary──────────┘
                  ▲              ▲  │ level_sg
                  │              │  ▼
                  │              │ fw_ctrl ◀── level_setpoint, feedwater_manual
                  │              │   │ m_fw_demand
                  │              └── feedwater ──m_fw
                  │
    core ──Q_fuel_to_coolant──▶ loop, pzr
      ▲                         │
      │                         └── T_avg ─▶ tavg_ctrl ◀── turbine.T_ref
      │                                         ▲
    rod.rho_rod ◀── rod ◀── tavg_ctrl.rod_demand, scram
                       └── rod_position ────────┘

    loop ──T_hot, T_cold──▶ pzr       pzr ──P──▶ pzr_ctrl ──Q_heater, m_dot_spray──▶ pzr
    pzr ──P──▶ loop                   pzr_ctrl ──m_dot_spray────────────────────────▶ loop

Operator commands enter as ten engine externals: ``rod_command``,
``scram``, ``P_setpoint``, ``heater_manual``, ``spray_manual``,
``turbine_load``, ``turbine_trip``, ``rod_auto``, ``level_setpoint`` and
``feedwater_manual``. ``heater_manual``, ``spray_manual`` and
``feedwater_manual`` use ``None`` for automatic control.

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

import math

from fission_sim.control.feedwater_controller import FeedwaterController, FeedwaterControllerParams
from fission_sim.control.pressurizer_controller import (
    PressurizerController,
    PressurizerControllerParams,
)
from fission_sim.control.tavg_controller import TavgController, TavgControllerParams
from fission_sim.engine import SimEngine
from fission_sim.physics.core import CoreParams, PointKineticsCore
from fission_sim.physics.feedwater import FeedwaterParams, FeedwaterSystem
from fission_sim.physics.pressurizer import Pressurizer, PressurizerParams
from fission_sim.physics.primary_loop import LoopParams, PrimaryLoop
from fission_sim.physics.rod_controller import RodController, RodParams
from fission_sim.physics.sg_secondary import SGSecondary, SGSecondaryParams
from fission_sim.physics.steam_generator import SGParams, SteamGenerator
from fission_sim.physics.turbine import Turbine, TurbineParams


def _finite_clipped_load(value: float) -> float:
    """Return a finite turbine-load default clipped into ``[0, 1]``.

    Parameters
    ----------
    value : float
        Turbine valve-admission default [-].

    Returns
    -------
    float
        Finite load clipped to the physical demand interval [-].

    Raises
    ------
    ValueError
        If ``value`` is not finite.
    """
    load = float(value)
    if not math.isfinite(load):
        raise ValueError("turbine_load must be finite before clipping to [0, 1].")
    return min(1.0, max(0.0, load))


def build_standard_plant(
    *,
    core_params: CoreParams | None = None,
    loop_params: LoopParams | None = None,
    sg_params: SGParams | None = None,
    rod_params: RodParams | None = None,
    pzr_params: PressurizerParams | None = None,
    ctrl_params: PressurizerControllerParams | None = None,
    sg_sec_params: SGSecondaryParams | None = None,
    turbine_params: TurbineParams | None = None,
    fw_params: FeedwaterControllerParams | None = None,
    feedwater_params: FeedwaterParams | None = None,
    tavg_params: TavgControllerParams | None = None,
    rod_command: float | None = None,
    P_setpoint: float | None = None,
    turbine_load: float | None = None,
    rod_auto: bool = False,
) -> SimEngine:
    """Build and finalize the standard M4 plant.

    Every parameter object defaults to its design-point values, so
    ``build_standard_plant()`` starts at steady full power. Pass an object
    to change one component, e.g. ``core_params=CoreParams(alpha_m=...)``.

    Module names (the snapshot keys) are ``rod``, ``core``, ``loop``,
    ``sg``, ``sg_sec``, ``turbine``, ``feedwater``, ``fw_ctrl``,
    ``tavg_ctrl``, ``pzr`` and ``pzr_ctrl``. These are the names
    ``physics.domain.check_snapshot`` expects.

    Externals are ``rod_command`` [0..1], ``scram`` [bool],
    ``P_setpoint`` [Pa], ``heater_manual`` [None or 0..1],
    ``spray_manual`` [None or 0..1], ``turbine_load`` [0..1 valve
    admission], ``turbine_trip`` [bool], ``rod_auto`` [bool],
    ``level_setpoint`` [0..1 collapsed liquid fraction], and
    ``feedwater_manual`` [None or 0..1].

    Parameters
    ----------
    core_params, loop_params, sg_params, rod_params : optional
        Component parameters; ``None`` uses the defaults.
    pzr_params : PressurizerParams, optional
        ``None`` builds ``PressurizerParams(loop_params=loop_params)``. The
        pressurizer computes surge flow from the loop's thermal expansion,
        so a supplied object must carry the same loop parameters as the loop
        (if only ``pzr_params`` is given, the loop uses its ``loop_params``).
    ctrl_params : PressurizerControllerParams, optional
        Pressurizer pressure controller parameters.
    sg_sec_params : SGSecondaryParams, optional
        Saturated steam-generator shell parameters.
    turbine_params : TurbineParams, optional
        Turbine/header parameters. Its ``sg_params`` must equal
        ``sg_sec_params`` because the valve coefficient and design steam
        flow are derived from the shell design point.
    fw_params : FeedwaterControllerParams, optional
        M4 three-element feedwater-controller parameters. ``None`` builds
        ``FeedwaterControllerParams(sg_params=sg_sec_params)``. If only
        ``feedwater_params`` is supplied, this derives the same flow ceiling
        so the controller and actuator agree.
    feedwater_params : FeedwaterParams, optional
        Feedwater actuator parameters. ``None`` builds
        ``FeedwaterParams(sg_params=sg_sec_params)``. If only ``fw_params``
        is supplied, this derives the same flow ceiling. If both are
        supplied, their feedwater ceilings must agree.
    tavg_params : TavgControllerParams, optional
        Automatic Tavg rod-controller parameters.
    rod_command : float, optional
        Default rod command external, fraction withdrawn [0..1]; ``None``
        uses the rod's initial position (``rod_params.rod_position_initial``,
        else the design full-power position 0.5), so the rods start at rest.
    P_setpoint : float, optional
        Default pressure setpoint external [Pa]; ``None`` uses
        ``ctrl_params.P_setpoint_default`` (15.5 MPa).
    turbine_load : float, optional
        Default turbine valve-admission external [-]. ``None`` uses
        ``turbine_params.load_initial``. Finite values outside ``[0, 1]`` are
        clipped for the default; non-finite values raise ``ValueError``.
    rod_auto : bool, default False
        Default rod-control mode external. False passes ``rod_command``
        through; true lets ``TavgController`` drive rods to the turbine
        ``T_ref`` program.

    Returns
    -------
    SimEngine
        Finalized engine at t = 0, ready for ``step()`` or ``run()``.

    Raises
    ------
    ValueError
        If shared design parameters disagree or ``turbine_load`` is
        non-finite.
    """
    if core_params is None:
        core_params = CoreParams()
    if loop_params is None:
        loop_params = LoopParams() if pzr_params is None else pzr_params.loop_params
    if sg_params is None:
        sg_params = SGParams()
    if rod_params is None:
        rod_params = RodParams()
    if pzr_params is None:
        pzr_params = PressurizerParams(loop_params=loop_params)
    if ctrl_params is None:
        ctrl_params = PressurizerControllerParams()
    if sg_sec_params is None:
        sg_sec_params = SGSecondaryParams()
    if turbine_params is None:
        turbine_params = TurbineParams(sg_params=sg_sec_params)
    if tavg_params is None:
        tavg_params = TavgControllerParams()
    if pzr_params.loop_params != loop_params:
        raise ValueError(
            "pzr_params.loop_params must match loop_params: the pressurizer's "
            "surge flow is computed from the loop's thermal expansion"
        )
    if turbine_params.sg_params != sg_sec_params:
        raise ValueError(
            "turbine_params.sg_params must match sg_sec_params: the turbine's "
            "valve constant and design steam flow come from the shell side's design point"
        )
    if fw_params is not None and fw_params.sg_params != sg_sec_params:
        raise ValueError(
            "fw_params.sg_params must match sg_sec_params: the feedwater controller's design flow "
            "comes from the shell side's design point"
        )
    if feedwater_params is not None and feedwater_params.sg_params != sg_sec_params:
        raise ValueError(
            "feedwater_params.sg_params must match sg_sec_params: the feedwater actuator's design flow "
            "comes from the shell side's design point"
        )
    if fw_params is None and feedwater_params is None:
        fw_params = FeedwaterControllerParams(sg_params=sg_sec_params)
        feedwater_params = FeedwaterParams(sg_params=sg_sec_params)
    elif fw_params is None:
        feedwater_ceiling_frac = feedwater_params.m_fw_max / sg_sec_params.m_steam_design
        fw_params = FeedwaterControllerParams(sg_params=sg_sec_params, m_fw_max_frac=feedwater_ceiling_frac)
    elif feedwater_params is None:
        feedwater_params = FeedwaterParams(sg_params=sg_sec_params, m_fw_max_frac=fw_params.m_fw_max_frac)
    else:
        feedwater_ceiling_frac = feedwater_params.m_fw_max / sg_sec_params.m_steam_design
        if abs(fw_params.m_fw_max_frac - feedwater_ceiling_frac) > 1.0e-9:
            raise ValueError(
                "fw_params.m_fw_max_frac must match the feedwater actuator flow ceiling "
                "(feedwater_params.m_fw_max / sg_sec_params.m_steam_design)"
            )
    if abs(sg_params.T_secondary_ref - sg_sec_params.T_sec_ref) > 1e-9:
        raise ValueError(
            "sg_params.T_secondary_ref must equal sg_sec_params.T_sec_ref so the plant starts at steady state"
        )
    if abs(turbine_params.T_ref_full - loop_params.T_avg_ref) > 1e-9:
        raise ValueError("turbine_params.T_ref_full must equal loop_params.T_avg_ref")
    rod_position_initial = (
        rod_params.rod_position_design
        if rod_params.rod_position_initial is None
        else rod_params.rod_position_initial
    )
    if rod_command is None:
        rod_command = rod_position_initial
    if P_setpoint is None:
        P_setpoint = ctrl_params.P_setpoint_default
    if turbine_load is None:
        turbine_load = turbine_params.load_initial
    turbine_load = _finite_clipped_load(turbine_load)

    engine = SimEngine()
    rod = engine.module(RodController(rod_params), name="rod")
    core = engine.module(PointKineticsCore(core_params), name="core")
    loop = engine.module(PrimaryLoop(loop_params), name="loop")
    sg = engine.module(SteamGenerator(sg_params), name="sg")
    sg_sec = engine.module(SGSecondary(sg_sec_params), name="sg_sec")
    turbine = engine.module(Turbine(turbine_params), name="turbine")
    feedwater = engine.module(FeedwaterSystem(feedwater_params), name="feedwater")
    fw_ctrl = engine.module(FeedwaterController(fw_params), name="fw_ctrl")
    tavg_ctrl = engine.module(TavgController(tavg_params, rod_position_initial=rod_position_initial), name="tavg_ctrl")
    pzr = engine.module(Pressurizer(pzr_params), name="pzr")
    pzr_ctrl = engine.module(PressurizerController(ctrl_params), name="pzr_ctrl")

    # Operator commands; step()/run() override these defaults per call.
    rod_cmd = engine.input("rod_command", default=rod_command)
    scram = engine.input("scram", default=False)
    P_set = engine.input("P_setpoint", default=P_setpoint)
    heater_manual = engine.input("heater_manual", default=None)
    spray_manual = engine.input("spray_manual", default=None)
    load_demand = engine.input("turbine_load", default=turbine_load)
    trip = engine.input("turbine_trip", default=False)
    auto = engine.input("rod_auto", default=rod_auto)
    level_set = engine.input("level_setpoint", default=fw_params.level_setpoint_default)
    fw_manual = engine.input("feedwater_manual", default=None)

    # Wiring order does not matter: finalize() sorts the evaluation order.
    rod(rod_command=tavg_ctrl.rod_demand, scram=scram)
    Q_sg = sg(T_avg=loop.T_avg, T_secondary=sg_sec.T_secondary)
    turbine(P_steam=sg_sec.P_steam, load_demand=load_demand, turbine_trip=trip, scram=scram)
    fw_ctrl(
        level_sg=sg_sec.level_sg,
        level_setpoint=level_set,
        m_steam=turbine.m_steam,
        m_dump=turbine.m_dump,
        feedwater_manual=fw_manual,
    )
    feedwater(m_fw_demand=fw_ctrl.m_fw_demand)
    sg_sec(Q_sg=Q_sg, m_steam=turbine.m_steam, m_dump=turbine.m_dump, m_fw=feedwater.m_fw)
    tavg_ctrl(
        T_avg=loop.T_avg,
        T_ref=turbine.T_ref,
        rod_position=rod.rod_position,
        rod_command=rod_cmd,
        rod_auto=auto,
        scram=scram,
        turbine_trip=trip,
    )
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
