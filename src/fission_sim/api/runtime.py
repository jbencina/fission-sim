"""SimRuntime — asyncio background task wrapping SimEngine for the web UI.

This module is the bridge between the PWR simulation engine and the HTTP/WS
API layer. It owns:

- A ``SimEngine`` built by ``fission_sim.plant.build_standard_plant`` (the
  same plant ``examples/run_primary.py`` wires out step by step)
- An asyncio background task that steps the engine at a fixed cadence
- A command-state struct (rod position, scram, pressure setpoint, speed)
- A pub/sub mechanism that pushes telemetry frames to subscriber queues

Fidelity
--------
Wraps the same lumped physics components as the run_primary example.

Architecture
------------
This module sits at the TOP of the four-layer stack and is the only layer
that knows about asyncio. It does NOT import from ``fission_sim.api.app``
or any HTTP framework.  Imports are restricted to:

    fission_sim.engine
    fission_sim.plant
    fission_sim.physics.*
    fission_sim.control.*

Layer rule: nothing below the API layer knows this module exists.

Usage
-----
Construct a ``SimRuntime``, call ``await runtime.start()``, read telemetry
with ``runtime.snapshot()`` or subscribe via ``runtime.subscribe()``.

    runtime = SimRuntime()
    await runtime.start()

    frame = await runtime.subscribe().get()   # first telemetry dict
    runtime.pause()
    await runtime.reset()
    await runtime.stop()

References
----------
Python asyncio documentation: https://docs.python.org/3/library/asyncio.html
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from typing import Any

from fission_sim.control.feedwater_controller import FeedwaterControllerParams
from fission_sim.control.pressurizer_controller import PressurizerControllerParams
from fission_sim.engine import SimEngine
from fission_sim.physics.domain import ModelDomainError, check_snapshot
from fission_sim.physics.rod_controller import RodParams
from fission_sim.physics.turbine import TurbineParams
from fission_sim.plant import build_standard_plant

logger = logging.getLogger(__name__)

# Maximum number of frames buffered per subscriber queue before oldest is
# dropped. 16 frames at 10 Hz = 1.6 s of buffer — small to avoid memory
# growth if a consumer falls behind.
_QUEUE_MAXSIZE = 16

# Step cadence in Hz — how many times per second the engine is stepped.
# This is *wall-clock* rate; sim time advances by (dt * speed) each step,
# where dt = 1 / cadence_hz. At speed=1.0 and cadence=10 Hz each step
# advances 0.1 s of simulation time.
_DEFAULT_CADENCE_HZ = 10

# Speed multipliers the operator may choose; the web UI offers exactly
# these. Higher speeds hand the stiff BDF integrator a longer stretch of
# simulated time per cadence step, which can take longer to compute than
# the cadence period itself.
_ALLOWED_SPEEDS = (1.0, 2.0, 5.0, 10.0)

# Range accepted for the operator's primary pressure setpoint. The design
# setpoint is 15.5 MPa; outside this band the pressurizer model is far from
# the conditions it was built for.
_P_MIN_PA = 10e6  # 10 MPa — minimum plausible primary pressure [Pa]
_P_MAX_PA = 20e6  # 20 MPa — maximum plausible primary pressure [Pa]

# Control-bank command at start-up and after reset: the design full-power
# position, where the rods add no reactivity (fraction withdrawn, 0..1).
_DESIGN_ROD_COMMAND = RodParams().rod_position_design

# Prefix of ``model_limit`` when the halt came from an unexpected step
# failure (a bug or numerical breakdown) rather than a model-domain limit.
# The web UI keys its notice heading on it (web/src/widgets/ErrorNotice.tsx).
SIM_ERROR_PREFIX = "Simulation error: "

# Appended to every halt explanation and to the refused-resume reply:
# reset keeps the settings that may have caused the halt.
_RESET_KEEPS_SETTINGS = (
    "Reset keeps your pressure setpoint, speed, turbine admission demand, "
    "rod-control mode, SG level setpoint, and pause state; it clears SCRAM, "
    "the turbine trip latch, and manual feedwater, and the rod command returns "
    f"to {_DESIGN_ROD_COMMAND * 100:.0f} %. Change the setting that caused this, "
    "or the same thing will happen again."
)


def _is_number(value: Any) -> bool:
    """True for a finite JSON number.

    ``bool`` is excluded: Python treats ``True`` as the int 1, but a JSON
    ``true`` is not a valid numeric command value. ``json.loads`` accepts the
    non-standard literals ``NaN`` and ``Infinity`` as floats, so the finite
    check is part of the command boundary rather than the JSON parser.
    """
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _plain_float(value: Any) -> float | None:
    """Return ``value`` as a plain Python ``float``, preserving ``None``."""
    if value is None:
        return None
    return float(value)


def _plain_bool(value: Any) -> bool | None:
    """Return ``value`` as a plain Python ``bool``, preserving ``None``."""
    if value is None:
        return None
    return bool(value)


def _command_number(msg: dict[str, Any], cmd_type: str) -> tuple[float | None, dict[str, str] | None]:
    """Extract a finite numeric command value or an error reply."""
    value = msg.get("value")
    if not _is_number(value):
        return None, {"type": "error", "detail": f"{cmd_type} requires a finite numeric 'value'"}
    return float(value), None


def _build_telemetry_frame(snap: dict[str, Any], cmd: "_CommandState") -> dict[str, Any]:
    """Convert a raw engine snapshot + command state into a UI telemetry frame.

    Extracts the quantities the web UI needs from each module's telemetry
    dict, computes derived reactivity components (Doppler and moderator
    feedback from current temperatures vs. reference), and tags the frame
    with the runtime's current command state.

    Parameters
    ----------
    snap : dict
        Full engine snapshot (from ``SimEngine.step()``).
    cmd : _CommandState
        Current runtime command state (rod_command, scram, speed, running).

    Returns
    -------
    dict
        Telemetry frame with keys documented in the module docstring.
    """
    # Per-module telemetry sub-dicts from the engine snapshot.
    core_tele = snap.get("core", {})
    loop_tele = snap.get("loop", {})
    rod_tele = snap.get("rod", {})
    pzr_tele = snap.get("pzr", {})
    sg_tele = snap.get("sg", {})
    sg_sec_tele = snap.get("sg_sec", {})
    turbine_tele = snap.get("turbine", {})
    feedwater_tele = snap.get("feedwater", {})
    fw_ctrl_tele = snap.get("fw_ctrl", {})
    tavg_ctrl_tele = snap.get("tavg_ctrl", {})

    # Raw temperatures needed for reactivity decomposition.
    T_fuel = _plain_float(core_tele.get("T_fuel"))
    T_hot = _plain_float(loop_tele.get("T_hot"))
    T_cold = _plain_float(loop_tele.get("T_cold"))
    # T_avg = (T_hot + T_cold) / 2  [K]; the loop module also provides this
    # but we compute it locally to be explicit about what the UI gets.
    T_avg = (
        (T_hot + T_cold) / 2
        if (T_hot is not None and T_cold is not None)
        else _plain_float(loop_tele.get("T_avg"))
    )

    # Rod reactivity [dimensionless] — produced by the rod controller output.
    rho_rod = _plain_float(rod_tele.get("rho_rod"))

    # Doppler feedback: α_f * (T_fuel − T_fuel_ref), read from the core's
    # telemetry. Negative for hotter fuel (more resonance absorption).
    rho_doppler = _plain_float(core_tele.get("rho_doppler"))

    # Moderator feedback: α_m * (T_cool − T_cool_ref), also from the core.
    # Negative when the coolant is hotter than its reference.
    rho_moderator = _plain_float(core_tele.get("rho_moderator"))

    # Total reactivity = rod + Doppler + moderator.
    # A reactor is critical when rho_total = 0.
    rho_total = _plain_float(core_tele.get("rho_total"))

    # Primary-side pressure from the pressurizer output [Pa].
    P_pa = _plain_float(pzr_tele.get("P"))
    # Convert to MPa for dashboard convenience (1 Pa = 1e-6 MPa).
    P_mpa = P_pa / 1e6 if P_pa is not None else None

    # Secondary-side pressure from the steam-generator shell [Pa].
    P_steam_pa = _plain_float(sg_sec_tele.get("P_steam"))
    P_steam_mpa = P_steam_pa / 1e6 if P_steam_pa is not None else None

    return {
        "t": _plain_float(snap.get("t")),
        "power_thermal": _plain_float(core_tele.get("power_thermal")),
        "T_hot": T_hot,
        "T_cold": T_cold,
        "T_avg": T_avg,
        "T_fuel": T_fuel,
        "rod_position": _plain_float(rod_tele.get("rod_position")),
        "P_primary_Pa": P_pa,
        "P_primary_MPa": P_mpa,
        "Q_sg": _plain_float(sg_tele.get("Q_sg")),
        "rho_rod": rho_rod,
        "rho_doppler": rho_doppler,
        "rho_moderator": rho_moderator,
        "rho_total": rho_total,
        "P_steam_Pa": P_steam_pa,
        "P_steam_MPa": P_steam_mpa,
        "T_secondary": _plain_float(sg_sec_tele.get("T_secondary")),
        "level_sg": _plain_float(sg_sec_tele.get("level_sg")),
        "time_to_level_floor_s": _plain_float(sg_sec_tele.get("time_to_level_floor_s")),
        "m_steam": _plain_float(turbine_tele.get("m_steam")),
        "m_dump": _plain_float(turbine_tele.get("m_dump")),
        "P_electric": _plain_float(turbine_tele.get("P_electric")),
        "turbine_load": _plain_float(turbine_tele.get("load")),
        "T_ref": _plain_float(turbine_tele.get("T_ref")),
        "turbine_load_demand_effective": _plain_float(turbine_tele.get("load_demand")),
        "turbine_trip_active": _plain_bool(turbine_tele.get("trip_active")),
        "m_fw": _plain_float(feedwater_tele.get("m_fw")),
        "m_fw_max": _plain_float(feedwater_tele.get("m_fw_max")),
        "m_fw_demand": _plain_float(fw_ctrl_tele.get("m_fw_demand")),
        "fw_saturated": _plain_bool(fw_ctrl_tele.get("saturated")),
        "feedwater_manual_effective": _plain_float(fw_ctrl_tele.get("feedwater_manual")),
        "rod_demand": _plain_float(tavg_ctrl_tele.get("rod_demand")),
        "rod_auto_acting": _plain_bool(tavg_ctrl_tele.get("acting")),
        **_command_fields(cmd),
    }


def _command_fields(cmd: "_CommandState") -> dict[str, Any]:
    """The part of a telemetry frame that reports the runtime's command state.

    Lets the UI reflect what was commanded. Kept separate so a command that
    changes only these fields (while simulation time stands still) can
    update the latest frame without rebuilding its physics values.
    """
    return {
        "running": bool(cmd.running),
        "speed": float(cmd.speed),
        "scrammed": bool(cmd.scrammed),
        "rod_command": float(cmd.rod_command),
        "turbine_load_demand": float(cmd.turbine_load_demand),
        "turbine_trip": bool(cmd.turbine_trip),
        "rod_auto": bool(cmd.rod_auto),
        "level_setpoint": float(cmd.level_setpoint),
        "feedwater_manual": _plain_float(cmd.feedwater_manual),
        # Why the simulation halted at the edge of the model, or None.
        "model_limit": None if cmd.model_limit is None else str(cmd.model_limit),
    }


class _CommandState:
    """Mutable command state for the runtime.

    Grouped in one place so ``reset()`` and the telemetry frame read the
    whole command state together. There is no lock: every access happens on
    the one asyncio event loop, and no reader awaits between reading these
    fields and using them (see ``SimRuntime``).

    Attributes
    ----------
    rod_command : float
        Control-bank command, fraction of travel withdrawn [0..1].
        0 = fully inserted, 1 = fully withdrawn. Default 0.5 = the design
        full-power position.
    scrammed : bool
        True when a SCRAM has been commanded. The rod controller then drives
        both the control bank and the shutdown bank to full insertion.
    P_setpoint : float
        Primary pressure setpoint [Pa] for the pressurizer controller.
    speed : float
        Simulation speed multiplier. 1.0 = real time, 2.0 = double speed.
    running : bool
        Whether the step loop is actively advancing simulation time.
        False while paused or stopped.
    model_limit : str or None
        Plain-language reason the simulation halted because it reached the
        edge of what the model can describe, or None. A halt caused by an
        unexpected step failure instead starts with ``SIM_ERROR_PREFIX``.
        While set, the engine holds the last valid state, ``resume`` is
        refused, and only ``reset()`` clears it.
    turbine_load_demand : float
        Operator turbine-admission demand [0..1]. The turbine governor ramps
        actual admission toward it at 5 %/min unless a trip is active.
    turbine_trip : bool
        Operator turbine-trip latch. The effective trip reported in telemetry
        also includes the reactor-trip P-4 interlock (`scram`).
    rod_auto : bool
        True when the load-dependent Tavg controller drives the control bank;
        False when `rod_command` is passed through manually.
    level_setpoint : float
        Steam-generator collapsed liquid level setpoint [0..1].
    feedwater_manual : float or None
        Manual feedwater demand as a fraction of maximum actuator flow [0..1],
        or None for automatic three-element level control.
    """

    def __init__(
        self,
        P_setpoint_default: float,
        turbine_load_default: float,
        level_setpoint_default: float,
    ) -> None:
        self.rod_command: float = _DESIGN_ROD_COMMAND
        self.scrammed: bool = False
        self.P_setpoint: float = P_setpoint_default
        self.speed: float = 1.0
        self.running: bool = True  # True = not paused
        self.model_limit: str | None = None
        self.turbine_load_demand: float = turbine_load_default
        self.turbine_trip: bool = False
        self.rod_auto: bool = False
        self.level_setpoint: float = level_setpoint_default
        self.feedwater_manual: float | None = None


class SimRuntime:
    """Background asyncio task that runs the PWR simulator continuously.

    This is the primary integration point between the simulation engine and
    the web API. It:

    1. Owns a ``SimEngine`` from ``build_standard_plant()`` (the standard plant).
    2. Runs a step loop at ``cadence_hz`` Hz — each step advances simulation
       time by ``dt * speed`` where ``dt = 1 / cadence_hz``.
    3. Publishes telemetry frames to all subscribed asyncio queues.
    4. Accepts command changes (rod position, scram, pressure setpoint,
       speed, turbine admission/trip, rod auto/manual mode, SG level
       setpoint and feedwater mode) through plain setter methods or
       ``handle_command``.

    Lifecycle
    ---------
    Construction is synchronous and cheap (no engine step yet). Call
    ``await start()`` to launch the background task::

        rt = SimRuntime()
        await rt.start()           # background task begins
        frame = await q.get()      # subscribe for frames
        rt.pause()
        rt.resume()
        await rt.reset()           # rebuilds engine from t=0
        await rt.stop()            # cancels background task

    Concurrency
    -----------
    Everything runs on one asyncio event loop, and code between two
    ``await`` points cannot be interleaved with anything else. The step
    loop reads the command state, steps the engine, and publishes the frame
    with no ``await`` in between, so every frame is tagged with the command
    values its step actually used, and command state needs no lock.
    ``start()``, ``stop()`` and ``reset()`` *do* await (stopping waits for
    the step task to finish), so they share one lifecycle lock: overlapping
    resets run one after the other and leave exactly one step task.

    Publication
    -----------
    A new subscriber's queue starts with the latest frame, so a client that
    connects while the simulation is paused or halted sees its state at
    once. While the simulation runs, the step loop publishes one frame per
    step. While it does not (paused, halted, or never started), a frame is
    published only when something visible changes: an accepted command, a
    pause, a reset, or a halt. When nothing changes, nothing is sent.

    Architecture
    ------------
    This module only imports from ``fission_sim.engine``, ``fission_sim.plant``,
    ``fission_sim.physics``, and ``fission_sim.control``. It is completely
    HTTP-agnostic.

    Parameters
    ----------
    cadence_hz : float, optional
        Step rate [Hz]. Default 10. Each wall-clock cycle advances simulation
        time by ``(1 / cadence_hz) * speed`` seconds.

    Notes
    -----
    Telemetry frame keys: ``t``, ``power_thermal``, ``T_hot``, ``T_cold``,
    ``T_avg``, ``T_fuel``, ``rod_position``, ``P_primary_Pa``,
    ``P_primary_MPa``, ``Q_sg``, ``rho_rod``, ``rho_doppler``,
    ``rho_moderator``, ``rho_total``, ``P_steam_Pa``, ``P_steam_MPa``,
    ``T_secondary``, ``level_sg``, ``time_to_level_floor_s``, ``m_steam``,
    ``m_dump``, ``P_electric``, ``turbine_load``, ``T_ref``,
    ``turbine_trip_active``, ``m_fw``, ``m_fw_max``, ``m_fw_demand``,
    ``fw_saturated``, ``feedwater_manual_effective``, ``rod_demand``,
    ``rod_auto_acting``, ``running``, ``speed``, ``scrammed``,
    ``rod_command``, ``turbine_load_demand``,
    ``turbine_load_demand_effective``, ``turbine_trip``, ``rod_auto``,
    ``level_setpoint``, ``feedwater_manual`` and ``model_limit``.

    Model limit
    -----------
    After every step the runtime checks the new state against the model's
    supported domain (``fission_sim.physics.domain``): liquid hot leg,
    steam-and-water pressurizer, sane pressure and inventory. If a step
    leaves that domain, or fails outright, the runtime puts the engine back
    at the last valid state, stops advancing, and publishes a frame whose
    ``model_limit`` explains why. ``resume`` is refused until ``reset()``.
    """

    def __init__(self, cadence_hz: float = _DEFAULT_CADENCE_HZ) -> None:
        self._cadence_hz = cadence_hz
        self._dt = 1.0 / cadence_hz  # wall-clock seconds between steps [s]

        # Mutable command state (no lock needed; see "Concurrency" above).
        self._cmd = _CommandState(
            P_setpoint_default=PressurizerControllerParams().P_setpoint_default,
            turbine_load_default=TurbineParams().load_initial,
            level_setpoint_default=FeedwaterControllerParams().level_setpoint_default,
        )

        # Serialises start/stop/reset, the only operations that await.
        self._lifecycle_lock = asyncio.Lock()

        # Build the initial engine (synchronous; cheap until the first step).
        self._engine = self._new_engine()

        # Latest telemetry frame — updated after every engine step and
        # every visible command change. Initialized from the engine's
        # initial snapshot so callers can call snapshot() before the first
        # step completes.
        self._latest_frame: dict[str, Any] = _build_telemetry_frame(
            self._engine.snapshot(), self._cmd
        )

        # Pub/sub: a set of asyncio.Queue objects registered by subscribers.
        self._subscribers: set[asyncio.Queue] = set()

        # The one step-loop task. None until start() and again after stop();
        # only the lifecycle methods (holding _lifecycle_lock) change it.
        self._task: asyncio.Task | None = None

        # True while reset() is between preparing reset command state and
        # publishing the rebuilt engine's t = 0 frame. Synchronous setters can
        # run during reset's awaits; AUTO→MANUAL rod transfer uses this flag
        # to sync against the engine that will run after reset, not the stale
        # pre-reset frame.
        self._reset_in_progress = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _new_engine(self) -> SimEngine:
        """Build a fresh design-default plant with the current commands.

        Called once at construction and again by ``reset()`` to rebuild
        the engine from t = 0. The operator's rod command, pressure setpoint,
        turbine-admission demand and rod-control mode carry over as externals'
        defaults; level setpoint and feedwater mode are still passed on every
        step.

        Returns
        -------
        SimEngine
            Finalized engine at t = 0.
        """
        return build_standard_plant(
            rod_command=self._cmd.rod_command,
            P_setpoint=self._cmd.P_setpoint,
            turbine_load=self._cmd.turbine_load_demand,
            rod_auto=self._cmd.rod_auto,
        )

    async def _step_loop(self) -> None:
        """Main background loop — steps the engine at ``cadence_hz`` Hz.

        Sleeps between steps so wall-clock time advances approximately at
        the cadence rate. The sleep time is adjusted to account for the
        time spent in ``engine.step()`` itself (which can be significant for
        stiff ODE solvers).

        Publishes a telemetry frame to all subscribers after each step.
        While ``running`` is False (paused or halted) it only sleeps; the
        pause itself, and any command given while paused, publish their own
        frame (see ``_command_state_changed``).

        Model-limit halt
        ----------------
        Each accepted step's end state is checked with
        ``physics.domain.check_snapshot``. Only the end state is checked: the BDF
        solver may probe trial states outside the domain while it searches
        for a step that ends inside it, and those are not errors. A
        property-library failure inside the solver *does* end the step, and
        ``coolprop.py`` reports it as ``ModelDomainError`` too. On any step
        failure the engine is restored to the pre-step state, ``running``
        is cleared, ``model_limit`` is set, and one frame carrying the
        explanation is published.
        """
        # Snapshot of the last accepted, in-domain state (None until the
        # first step), used to rebuild the frame if a step has to be undone.
        last_snap: dict[str, Any] | None = None

        while True:
            t0_wall = time.monotonic()

            # From here to the sleep at the bottom there is no await, so no
            # command can change self._cmd part-way through: the frame
            # published below carries the command values this step used.
            cmd = self._cmd
            if cmd.running:
                # Advance simulation time by dt * speed (may be > 1× if speed > 1).
                # The engine's BDF integrator handles the stiff ODE internally.
                sim_dt = self._dt * cmd.speed
                # Last accepted state, kept so a failed step can be undone.
                # A copy of a ~20-element vector: negligible per step.
                t_before = self._engine.t
                y_before = self._engine.state.copy()
                try:
                    snap = self._engine.step(
                        sim_dt,
                        rod_command=cmd.rod_command,
                        scram=cmd.scrammed,
                        P_setpoint=cmd.P_setpoint,
                        # heater_manual and spray_manual left at engine defaults (None).
                        heater_manual=None,
                        spray_manual=None,
                        turbine_load=cmd.turbine_load_demand,
                        turbine_trip=cmd.turbine_trip,
                        rod_auto=cmd.rod_auto,
                        level_setpoint=cmd.level_setpoint,
                        feedwater_manual=cmd.feedwater_manual,
                    )
                    check_snapshot(snap)
                except Exception as err:
                    if isinstance(err, ModelDomainError):
                        # Traceback kept in the log: a property-lookup
                        # failure's CoolProp cause is only visible there.
                        logger.warning(
                            "Model limit reached at t=%.2f s: %s", t_before, err, exc_info=True
                        )
                        explanation = str(err)
                    else:
                        logger.exception("Engine step failed; simulation halted")
                        explanation = (
                            f"{SIM_ERROR_PREFIX}a simulation step failed unexpectedly "
                            f"({type(err).__name__}: {err}). This is a fault in the "
                            "simulator, not a physics limit."
                        )
                    # SimEngine.step commits its end state before the domain
                    # check runs, so undo the step explicitly.
                    self._engine.restore(t_before, y_before)
                    explanation += (
                        f" The simulation stopped at t = {t_before:.1f} s, the last "
                        "valid state, and shows that state. Reset the simulation to "
                        f"start again. {_RESET_KEEPS_SETTINGS}"
                    )
                    cmd.running = False
                    cmd.model_limit = explanation
                    # Re-publish the last valid state flagged as halted, with
                    # the current command state.
                    valid_snap = last_snap if last_snap is not None else self._engine.snapshot()
                    self._publish(_build_telemetry_frame(valid_snap, cmd))
                else:
                    last_snap = snap
                    self._publish(_build_telemetry_frame(snap, cmd))

            # Sleep for the remainder of the wall-clock cycle.
            elapsed = time.monotonic() - t0_wall
            sleep_time = max(0.0, self._dt - elapsed)
            await asyncio.sleep(sleep_time)

    def _publish(self, frame: dict[str, Any]) -> None:
        """Record ``frame`` as the latest state and push it to every subscriber.

        If a queue is full (maxsize reached), the oldest frame is discarded
        to make room for the new one. This keeps slow consumers from blocking
        the step loop, at the cost of dropping stale data (acceptable for
        a live dashboard). This method never awaits, so nothing can refill
        a queue between the drop and the put: the put always succeeds.

        Parameters
        ----------
        frame : dict
            Telemetry frame to publish.
        """
        self._latest_frame = frame
        for q in self._subscribers:
            if q.full():
                q.get_nowait()
                logger.warning("Subscriber queue full; dropped oldest telemetry frame")
            q.put_nowait(frame)

    def _step_loop_publishing(self) -> bool:
        """True when the step loop will publish a fresh frame within one cycle."""
        return self._cmd.running and self._task is not None and not self._task.done()

    def _command_state_changed(self) -> None:
        """Bring the latest frame's command fields up to date after a change.

        Called by every setter, so ``snapshot()`` always reports the current
        command state. The updated frame is also published unless the step
        loop is about to publish one anyway (while running it publishes
        every cycle). That way a paused or halted client sees an accepted
        command, with simulation time unchanged. A call that changes nothing
        publishes nothing, which keeps a paused simulator quiet.
        """
        frame = {**self._latest_frame, **_command_fields(self._cmd)}
        if frame == self._latest_frame:
            return
        if self._step_loop_publishing():
            self._latest_frame = frame
        else:
            self._publish(frame)

    def _on_step_task_done(self, task: asyncio.Task) -> None:
        """Halt visibly if the step loop dies outside its guarded engine step.

        A failed engine step is caught inside the loop and becomes a
        model-limit halt. Anything else that raises (for example while
        building a telemetry frame) ends the task; without this callback
        that would happen silently, leaving clients connected with no
        frames. This logs the error and publishes a halt in the same form,
        so the UI explains what happened and ``reset()`` starts a new loop.
        """
        if task.cancelled():
            return  # stop() or reset() cancelled it: the normal way to end
        err = task.exception()
        if err is None:
            return
        logger.error("Simulation step loop stopped unexpectedly", exc_info=err)
        self._cmd.running = False
        self._cmd.model_limit = (
            f"{SIM_ERROR_PREFIX}the simulation loop stopped unexpectedly "
            f"({type(err).__name__}: {err}). This is a fault in the simulator, "
            "not a physics limit. Reset the simulation to start again."
        )
        self._command_state_changed()

    # ------------------------------------------------------------------
    # Lifecycle methods (serialised by _lifecycle_lock)
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background step loop.

        Idempotent — calling ``start()`` again while the loop is running is
        a no-op with a debug log. Call ``stop()`` first to restart.

        Notes
        -----
        The background task is scheduled on the running event loop. The
        caller must therefore ``await start()`` from an async context.
        """
        async with self._lifecycle_lock:
            self._start_task()

    async def stop(self) -> None:
        """Cancel the background step loop and wait for it to finish.

        Safe to call multiple times. After stop(), the engine state is
        preserved — call ``reset()`` to return to t = 0.
        """
        async with self._lifecycle_lock:
            await self._stop_task()

    async def reset(self) -> None:
        """Rebuild the plant at t = 0 and reset transient command latches.

        The physical state (temperatures, neutron population, pressurizer
        inventory, SG inventory, turbine admission, rod positions) is rebuilt
        at t = 0 using the kept admission demand and rod-control mode.
        ``rod_command`` goes back to its initial 0.5;
        SCRAM, the operator turbine-trip latch and manual feedwater are
        cleared. ``P_setpoint``, ``speed``, ``turbine_load_demand``,
        ``rod_auto`` and ``level_setpoint`` are kept, and so is a pause the
        operator chose. A model-limit halt is cleared and the simulation runs
        again, since the halt was the only reason it stopped. The WebSocket
        ``reset`` command calls this method, so both behave the same way.

        One frame at t = 0 is published, so every client sees the rollback
        even while paused.

        Notes
        -----
        This rebuilds the entire ``SimEngine`` object, which is the only
        reliable way to reset the global ODE state vector to ``initial_state()``.
        The lifecycle lock is held throughout, so two overlapping resets
        run one after the other and leave exactly one step task.
        """
        async with self._lifecycle_lock:
            self._reset_in_progress = True
            try:
                # Restart a loop that was started and not stopped, including
                # one that died with an error (its task is kept until stop()).
                restart = self._task is not None
                # Reset the rod commands before the first await below, so a
                # command another client sends while the old loop winds down is
                # applied after the reset instead of being overwritten by it.
                self._cmd.rod_command = _DESIGN_ROD_COMMAND
                self._cmd.scrammed = False
                self._cmd.turbine_trip = False
                self._cmd.feedwater_manual = None
                await self._stop_task()

                if self._cmd.model_limit is not None:
                    self._cmd.model_limit = None
                    self._cmd.running = True
                # Built after the command reset: the engine's rod_command default
                # comes from self._cmd.
                self._engine = self._new_engine()
                self._publish(_build_telemetry_frame(self._engine.snapshot(), self._cmd))

                if restart:
                    self._start_task()
            finally:
                self._reset_in_progress = False

    def _start_task(self) -> None:
        """Create the step task unless one is running. Caller holds the lifecycle lock."""
        if self._task is not None and not self._task.done():
            logger.debug("SimRuntime.start() called while already running — no-op")
            return
        task = asyncio.create_task(self._step_loop(), name="sim-step-loop")
        task.add_done_callback(self._on_step_task_done)
        self._task = task

    async def _stop_task(self) -> None:
        """Cancel the step task and wait for it to end. Caller holds the lifecycle lock.

        Works on a local reference, so it waits for exactly the task it
        cancelled, and clears ``_task`` only if that is still the current
        task. ``asyncio.wait`` neither re-raises the task's own error (the
        done-callback has logged it) nor hides a cancellation of the caller.
        """
        task = self._task
        if task is None:
            return
        task.cancel()
        await asyncio.wait({task})
        if self._task is task:
            self._task = None

    # ------------------------------------------------------------------
    # Pause / resume (synchronous — safe to call from sync or async code)
    # ------------------------------------------------------------------

    def pause(self) -> None:
        """Pause the simulation — the step loop keeps running but skips engine.step().

        Publishes one frame with ``running`` False; after that the loop
        sleeps quietly, consuming negligible CPU. Resume with ``resume()``.
        Safe to call multiple times.
        """
        self._cmd.running = False
        self._command_state_changed()

    def resume(self) -> None:
        """Resume the simulation after a ``pause()``.

        Safe to call when already running. Does nothing while a model limit
        is active: stepping on from the edge of the model would only fail
        again, so ``reset()`` is required (``handle_command`` tells the
        client so).
        """
        if self._cmd.model_limit is not None:
            logger.info("resume() ignored: model limit active; reset required")
            return
        self._cmd.running = True
        self._command_state_changed()

    # ------------------------------------------------------------------
    # Command setters
    # ------------------------------------------------------------------

    def set_rod_command(self, v: float) -> None:
        """Set the control-bank command.

        Parameters
        ----------
        v : float
            Control-bank command, fraction of travel withdrawn [0..1].
            0 = fully inserted, 1 = fully withdrawn, 0.5 = design. The rod
            controller moves the bank toward it at ``RodParams.v_normal``
            (0.01 per second, so 100 s for the full stroke).
        """
        self._cmd.rod_command = float(v)
        self._command_state_changed()

    def scram(self) -> None:
        """Initiate a SCRAM — drop both rod banks into the core.

        A SCRAM (Safety Control Rod Axe Man, also Subcritical Reactivity
        Attenuation Mechanism) inserts all rods by gravity. The rod
        controller drops the operator's control bank and the shutdown
        bank together, overriding ``rod_command``: both are in within
        about 2 s, for −7,000 pcm relative to the design state.

        The core is subcritical as soon as the rods are in, but power does
        not vanish: delayed-neutron precursors keep decaying and emitting
        neutrons, which sustain a shrinking level of fission that falls
        off over tens of seconds to minutes on the precursor half-lives.
        (Fission-product decay heat is not modeled.)
        """
        self._cmd.scrammed = True
        self._command_state_changed()

    def reset_scram(self) -> None:
        """Clear the SCRAM latch and require explicit turbine re-admission.

        Only the control bank comes back: it moves toward ``rod_command``
        at normal drive speed. The shutdown bank stays inserted, so the
        core stays subcritical whatever the rod command: total reactivity
        stays below about −4,300 pcm even with the control bank fully
        withdrawn (+600 pcm) and the plant cooled to the secondary
        temperature (feedback up to about +1,480 pcm), against the shutdown
        bank's −6,400 pcm (see ``RodParams.rho_shutdown_worth``).
        Returning to power requires a full simulation reset (``reset()``);
        the procedure-driven reactor startup that would withdraw the
        shutdown banks in a real plant is not modeled. In the simulator
        clearing the latch is unconditional (no interlock logic is
        modeled).

        Clearing SCRAM also sets ``turbine_load_demand`` to zero. A SCRAM
        trips the turbine through the P-4 interlock, and resetting that trip
        must not silently re-open the admission valves to an old demand;
        re-admission is an explicit operator action.
        """
        self._cmd.scrammed = False
        self._cmd.turbine_load_demand = 0.0
        self._command_state_changed()

    def set_speed(self, x: float) -> None:
        """Set the simulation speed multiplier.

        The one place speed is validated; ``handle_command`` relays its
        error to the client.

        Parameters
        ----------
        x : float
            Speed factor, one of ``_ALLOWED_SPEEDS`` (1, 2, 5 or 10; the web
            UI offers exactly these). 1.0 = real time, 2.0 = 2× faster.

        Raises
        ------
        ValueError
            If ``x`` is not one of the allowed speeds.
        """
        x = float(x)
        if x not in _ALLOWED_SPEEDS:
            raise ValueError(f"set_speed value {x!r} must be one of {list(_ALLOWED_SPEEDS)}")
        self._cmd.speed = x
        self._command_state_changed()

    def set_pressure_setpoint(self, p: float) -> None:
        """Set the primary pressure setpoint for the pressurizer controller.

        Parameters
        ----------
        p : float
            Pressure setpoint [Pa]. Nominal design value is 15.5 MPa = 1.55e7 Pa.
            The pressurizer controller will heat or spray to maintain this pressure.
            A setpoint far below the actual pressure keeps the spray on
            continuously; the pressurizer can then fill with water, which
            halts the simulation at a model limit.
        """
        self._cmd.P_setpoint = float(p)
        # The setpoint is not a frame field, so this publishes nothing; the
        # call keeps every setter on the same path.
        self._command_state_changed()

    def set_turbine_load(self, v: float) -> None:
        """Set turbine admission demand.

        Parameters
        ----------
        v : float
            Turbine stop/governor-valve admission demand [0..1]. The turbine
            component ramps actual admission toward this demand at 5 %/min.
        """
        self._cmd.turbine_load_demand = float(v)
        self._command_state_changed()

    def trip_turbine(self) -> None:
        """Set the operator turbine-trip latch.

        The turbine component closes admission whenever this latch is true
        or SCRAM is active through the P-4 reactor-trip interlock. The
        command latch records the operator trip cause; the telemetry key
        ``turbine_trip_active`` reports the effective trip status.
        """
        self._cmd.turbine_trip = True
        self._command_state_changed()

    def reset_turbine_trip(self) -> None:
        """Clear the operator turbine-trip latch and zero admission demand.

        Resetting the trip does not restore the previous admission demand:
        ``turbine_load_demand`` is set to 0 so re-admission is an explicit
        operator action, matching the M3 operator-review requirement.
        """
        self._cmd.turbine_trip = False
        self._cmd.turbine_load_demand = 0.0
        self._command_state_changed()

    def set_rod_auto(self, enabled: bool) -> None:
        """Switch between automatic Tavg rod control and manual rod command.

        Parameters
        ----------
        enabled : bool
            True enables the automatic Tavg controller. False returns control
            to the manual ``rod_command``.

        Notes
        -----
        On an AUTO→MANUAL transfer, ``rod_command`` is synchronized to the
        actual control-bank position from the latest accepted frame. During a
        concurrent reset it synchronizes to the rebuilt engine's initial bank
        position instead, because that is the engine that will run next.
        Without this bumpless transfer, a stale manual command would
        immediately drive the bank after automatic control had moved it.
        """
        enabled = bool(enabled)
        if self._cmd.rod_auto and not enabled:
            self._cmd.rod_command = (
                _DESIGN_ROD_COMMAND if self._reset_in_progress else float(self._latest_frame["rod_position"])
            )
        self._cmd.rod_auto = enabled
        self._command_state_changed()

    def set_level_setpoint(self, v: float) -> None:
        """Set the steam-generator collapsed-level setpoint.

        Parameters
        ----------
        v : float
            Desired SG collapsed liquid fraction [0.35..0.90]. This operator
            band stays inside the model validity limits at 0.30 and 0.95.
        """
        self._cmd.level_setpoint = float(v)
        self._command_state_changed()

    def set_feedwater_manual(self, v: float | None) -> None:
        """Set or clear manual feedwater demand.

        Parameters
        ----------
        v : float or None
            Manual feedwater demand as a fraction of maximum feedwater flow
            [0..1], or ``None`` to return to automatic level control.
        """
        self._cmd.feedwater_manual = None if v is None else float(v)
        self._command_state_changed()

    # ------------------------------------------------------------------
    # Snapshot and pub/sub
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Return the most recent telemetry frame (non-blocking).

        Returns
        -------
        dict
            The latest telemetry frame as produced by ``_build_telemetry_frame()``.
            Keys are documented in the module and class docstrings. Its
            physics values are from the last step (or the initial state if
            no step has completed yet); its command fields are always current.
        """
        return self._latest_frame

    def subscribe(self) -> asyncio.Queue:
        """Register a new subscriber and return its queue.

        The queue starts with the latest frame, so a subscriber has the
        current state at once even when nothing else is being published
        (paused, or halted at a model limit). It has a bounded capacity
        (``_QUEUE_MAXSIZE`` frames). If the consumer is slow and the queue
        fills, the oldest frame is silently dropped on the next publish call
        — acceptable for a live dashboard.

        Returns
        -------
        asyncio.Queue
            Call ``await q.get()`` to receive the next telemetry frame.
            Call ``runtime.unsubscribe(q)`` when done.
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        q.put_nowait(self._latest_frame)
        self._subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Remove a subscriber queue registered with ``subscribe()``.

        Parameters
        ----------
        q : asyncio.Queue
            The queue to remove. No-op if already removed.
        """
        self._subscribers.discard(q)

    # ------------------------------------------------------------------
    # Command dispatch (the WebSocket command API)
    # ------------------------------------------------------------------

    async def handle_command(self, msg: Any) -> dict[str, Any]:
        """Validate and dispatch an operator command message.

        This is the single entry-point for all commands arriving over the
        WebSocket API. It validates the ``type`` field, applies range checks,
        and calls the appropriate setter or lifecycle method.

        Supported ``msg['type']`` values
        ---------------------------------
        set_rod_command
            ``value: float`` in ``[0, 1]``.  Drives the rod controller toward
            the requested position.
        scram
            No extra fields.  Drops both rod banks (see ``scram()``).
        reset_scram
            No extra fields.  Clears the scram latch, returns the control
            bank to the operator, and sets turbine admission demand to 0
            (see ``reset_scram()``).
        pause
            No extra fields.  Suspends engine stepping (wall-clock loop keeps running).
        resume
            No extra fields.  Resumes engine stepping after a pause.
            Refused with an error while a model limit is active (see
            ``model_limit`` in the frame); a ``reset`` is required.
        reset
            No extra fields.  Calls ``reset()``: rebuilds the plant at
            t = 0, returns ``rod_command`` to 0.5, clears the SCRAM and
            turbine-trip latches and manual feedwater, and keeps
            ``P_setpoint``, ``speed``, ``turbine_load_demand``,
            ``rod_auto`` and ``level_setpoint``.
        set_speed
            ``value: float`` — must be one of ``{1, 2, 5, 10}``.
        set_pressure_setpoint
            ``value: float`` [Pa] — must be in ``[10e6, 20e6]``.
        set_turbine_load
            ``value: float`` in ``[0, 1]``. Sets turbine admission demand.
        turbine_trip
            No extra fields. Sets the operator turbine-trip latch.
        reset_turbine_trip
            No extra fields. Clears the latch and sets turbine admission
            demand to 0, so re-admission is explicit.
        set_rod_auto
            ``value: bool``. Enables/disables automatic Tavg rod control;
            AUTO→MANUAL synchronizes ``rod_command`` to actual bank position.
        set_level_setpoint
            ``value: float`` in ``[0.35, 0.90]``.
        set_feedwater_manual
            ``value: float`` in ``[0, 1]`` or ``null`` for automatic control.

        Parameters
        ----------
        msg : dict
            Parsed JSON message from the WebSocket client.  Must contain at
            least ``"type": str``.

        Returns
        -------
        dict
            Returns ``{"type": "ack", "command": "<command type>"}`` on
            success.  Returns an error dict of the form ``{"type": "error",
            "detail": "<reason>"}`` for unknown command types or out-of-range
            values.  This method does **not** raise on bad input — the caller
            (recv loop in ``app.py``) decides how to relay the response to the
            client.
        """
        if not isinstance(msg, dict):
            return {"type": "error", "detail": "command message must be a JSON object"}

        cmd_type = msg.get("type")
        if not isinstance(cmd_type, str):
            return {"type": "error", "detail": "command message requires string field 'type'"}

        if cmd_type == "set_rod_command":
            # Validate: rod command must be a number in [0, 1].
            value, error = _command_number(msg, cmd_type)
            if error is not None:
                return error
            if not (0.0 <= value <= 1.0):
                return {
                    "type": "error",
                    "detail": f"set_rod_command value {value!r} is out of range [0, 1]",
                }
            self.set_rod_command(value)
            return {"type": "ack", "command": cmd_type}

        elif cmd_type == "scram":
            self.scram()
            return {"type": "ack", "command": cmd_type}

        elif cmd_type == "reset_scram":
            self.reset_scram()
            return {"type": "ack", "command": cmd_type}

        elif cmd_type == "set_turbine_load":
            value, error = _command_number(msg, cmd_type)
            if error is not None:
                return error
            if not (0.0 <= value <= 1.0):
                return {
                    "type": "error",
                    "detail": f"set_turbine_load value {value!r} is out of range [0, 1]",
                }
            self.set_turbine_load(value)
            return {"type": "ack", "command": cmd_type}

        elif cmd_type == "turbine_trip":
            self.trip_turbine()
            return {"type": "ack", "command": cmd_type}

        elif cmd_type == "reset_turbine_trip":
            self.reset_turbine_trip()
            return {"type": "ack", "command": cmd_type}

        elif cmd_type == "set_rod_auto":
            value = msg.get("value")
            if not isinstance(value, bool):
                return {"type": "error", "detail": "set_rod_auto requires a JSON boolean 'value'"}
            self.set_rod_auto(value)
            return {"type": "ack", "command": cmd_type}

        elif cmd_type == "set_level_setpoint":
            value, error = _command_number(msg, cmd_type)
            if error is not None:
                return error
            if not (0.35 <= value <= 0.90):
                return {
                    "type": "error",
                    "detail": f"set_level_setpoint value {value!r} is out of range [0.35, 0.90]",
                }
            self.set_level_setpoint(value)
            return {"type": "ack", "command": cmd_type}

        elif cmd_type == "set_feedwater_manual":
            if "value" not in msg:
                return {"type": "error", "detail": "set_feedwater_manual requires 'value' (number or null)"}
            value = msg["value"]
            if value is None:
                self.set_feedwater_manual(None)
                return {"type": "ack", "command": cmd_type}
            if not _is_number(value):
                return {"type": "error", "detail": "set_feedwater_manual requires a finite numeric 'value' or null"}
            value = float(value)
            if not (0.0 <= value <= 1.0):
                return {
                    "type": "error",
                    "detail": f"set_feedwater_manual value {value!r} is out of range [0, 1]",
                }
            self.set_feedwater_manual(value)
            return {"type": "ack", "command": cmd_type}

        elif cmd_type == "pause":
            self.pause()
            return {"type": "ack", "command": cmd_type}

        elif cmd_type == "resume":
            if self._cmd.model_limit is not None:
                return {
                    "type": "error",
                    "detail": (
                        "Cannot resume: the simulation stopped at the edge of what "
                        "the model can simulate, and continuing from there would give "
                        "meaningless results. Reset the simulation to start again. "
                        f"{_RESET_KEEPS_SETTINGS}"
                    ),
                }
            self.resume()
            return {"type": "ack", "command": cmd_type}

        elif cmd_type == "reset":
            await self.reset()
            return {"type": "ack", "command": cmd_type}

        elif cmd_type == "set_speed":
            value, error = _command_number(msg, cmd_type)
            if error is not None:
                return error
            try:
                self.set_speed(value)
            except ValueError as err:
                return {"type": "error", "detail": str(err)}
            return {"type": "ack", "command": cmd_type}

        elif cmd_type == "set_pressure_setpoint":
            # Validate: must be within [10 MPa, 20 MPa] = [10e6, 20e6] Pa.
            value, error = _command_number(msg, cmd_type)
            if error is not None:
                return error
            if not (_P_MIN_PA <= value <= _P_MAX_PA):
                return {
                    "type": "error",
                    "detail": (
                        f"set_pressure_setpoint value {value:.3e} Pa is out of range "
                        f"[{_P_MIN_PA:.3e}, {_P_MAX_PA:.3e}] Pa"
                    ),
                }
            self.set_pressure_setpoint(value)
            return {"type": "ack", "command": cmd_type}

        else:
            # Unknown command type — return an error frame; do not disconnect.
            return {
                "type": "error",
                "detail": f"unknown command type: {cmd_type!r}",
            }


__all__ = ["SimRuntime"]
