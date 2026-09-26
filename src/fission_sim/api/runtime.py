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
import time
from typing import Any

from fission_sim.control.pressurizer_controller import PressurizerControllerParams
from fission_sim.engine import SimEngine
from fission_sim.physics.domain import ModelDomainError, check_snapshot
from fission_sim.physics.rod_controller import RodParams
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
    "Reset keeps your pressure setpoint and speed (the rod command returns "
    f"to {_DESIGN_ROD_COMMAND * 100:.0f} %), so change the setting that caused this, "
    "or the same thing will happen again."
)


def _is_number(value: Any) -> bool:
    """True for a JSON number. ``bool`` is excluded: Python treats ``True``
    as the int 1, but a JSON ``true`` is not a valid numeric command value."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


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

    # Raw temperatures needed for reactivity decomposition.
    T_fuel = core_tele.get("T_fuel")
    T_hot = loop_tele.get("T_hot")
    T_cold = loop_tele.get("T_cold")
    # T_avg = (T_hot + T_cold) / 2  [K]; the loop module also provides this
    # but we compute it locally to be explicit about what the UI gets.
    T_avg = (T_hot + T_cold) / 2 if (T_hot is not None and T_cold is not None) else loop_tele.get("T_avg")

    # Rod reactivity [dimensionless] — produced by the rod controller output.
    rho_rod = rod_tele.get("rho_rod")

    # Doppler feedback: α_f * (T_fuel − T_fuel_ref), read from the core's
    # telemetry. Negative for hotter fuel (more resonance absorption).
    rho_doppler = core_tele.get("rho_doppler")

    # Moderator feedback: α_m * (T_cool − T_cool_ref), also from the core.
    # Negative when the coolant is hotter than its reference.
    rho_moderator = core_tele.get("rho_moderator")

    # Total reactivity = rod + Doppler + moderator.
    # A reactor is critical when rho_total = 0.
    rho_total = core_tele.get("rho_total")

    # Primary-side pressure from the pressurizer output [Pa].
    P_pa = pzr_tele.get("P")
    # Convert to MPa for dashboard convenience (1 Pa = 1e-6 MPa).
    P_mpa = P_pa / 1e6 if P_pa is not None else None

    return {
        "t": snap.get("t"),
        "power_thermal": core_tele.get("power_thermal"),
        "T_hot": T_hot,
        "T_cold": T_cold,
        "T_avg": T_avg,
        "T_fuel": T_fuel,
        "rod_position": rod_tele.get("rod_position"),
        "P_primary_Pa": P_pa,
        "P_primary_MPa": P_mpa,
        "Q_sg": sg_tele.get("Q_sg"),
        "rho_rod": rho_rod,
        "rho_doppler": rho_doppler,
        "rho_moderator": rho_moderator,
        "rho_total": rho_total,
        **_command_fields(cmd),
    }


def _command_fields(cmd: "_CommandState") -> dict[str, Any]:
    """The part of a telemetry frame that reports the runtime's command state.

    Lets the UI reflect what was commanded. Kept separate so a command that
    changes only these fields (while simulation time stands still) can
    update the latest frame without rebuilding its physics values.
    """
    return {
        "running": cmd.running,
        "speed": cmd.speed,
        "scrammed": cmd.scrammed,
        "rod_command": cmd.rod_command,
        # Why the simulation halted at the edge of the model, or None.
        "model_limit": cmd.model_limit,
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
    """

    def __init__(self, P_setpoint_default: float) -> None:
        self.rod_command: float = _DESIGN_ROD_COMMAND
        self.scrammed: bool = False
        self.P_setpoint: float = P_setpoint_default
        self.speed: float = 1.0
        self.running: bool = True  # True = not paused
        self.model_limit: str | None = None


class SimRuntime:
    """Background asyncio task that runs the PWR simulator continuously.

    This is the primary integration point between the simulation engine and
    the web API. It:

    1. Owns a ``SimEngine`` from ``build_standard_plant()`` (the standard plant).
    2. Runs a step loop at ``cadence_hz`` Hz — each step advances simulation
       time by ``dt * speed`` where ``dt = 1 / cadence_hz``.
    3. Publishes telemetry frames to all subscribed asyncio queues.
    4. Accepts command changes (rod position, scram, pressure setpoint,
       speed) through plain setter methods or ``handle_command``.

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
    ``rho_moderator``, ``rho_total``, ``running``, ``speed``, ``scrammed``,
    ``rod_command``, ``model_limit``.

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
        self._cmd = _CommandState(P_setpoint_default=PressurizerControllerParams().P_setpoint_default)

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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _new_engine(self) -> SimEngine:
        """Build a fresh design-default plant with the current commands.

        Called once at construction and again by ``reset()`` to rebuild
        the engine from t = 0. Only the operator's rod command and pressure
        setpoint carry over, as the externals' defaults.

        Returns
        -------
        SimEngine
            Finalized engine at t = 0.
        """
        return build_standard_plant(rod_command=self._cmd.rod_command, P_setpoint=self._cmd.P_setpoint)

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
        """Rebuild the plant at t = 0 and return the operator's rods to 50 %.

        The physical state (temperatures, neutron population, pressurizer
        inventory, rod positions) returns to its initial conditions, and so
        do the rod commands: ``rod_command`` goes back to its initial 0.5
        and the SCRAM latch is cleared. ``P_setpoint`` and ``speed`` are
        kept, and so is a pause the operator chose. A model-limit halt is
        cleared and the simulation runs again, since the halt was the only
        reason it stopped. The WebSocket ``reset`` command calls this
        method, so both behave the same way.

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
            # Restart a loop that was started and not stopped, including
            # one that died with an error (its task is kept until stop()).
            restart = self._task is not None
            # Reset the rod commands before the first await below, so a
            # command another client sends while the old loop winds down is
            # applied after the reset instead of being overwritten by it.
            self._cmd.rod_command = _DESIGN_ROD_COMMAND
            self._cmd.scrammed = False
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
        """Clear the SCRAM latch — returns the control bank to the operator.

        Only the control bank comes back: it moves toward ``rod_command``
        at normal drive speed. The shutdown bank stays inserted, so the
        core stays subcritical whatever the rod command: total reactivity
        stays below about −4,300 pcm even with the control bank fully
        withdrawn (+600 pcm) and the plant cooled to the secondary
        temperature (feedback up to about +1,480 pcm), against the shutdown
        bank's −6,400 pcm (see ``RodParams.rho_shutdown_worth``). Returning to power requires a full simulation reset
        (``reset()``); the procedure-driven reactor startup that would
        withdraw the shutdown banks in a real plant is not modeled. In the
        simulator clearing the latch is unconditional (no interlock logic
        is modeled).
        """
        self._cmd.scrammed = False
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
            No extra fields.  Clears the scram latch, returning the control
            bank to the operator (see ``reset_scram()``).
        pause
            No extra fields.  Suspends engine stepping (wall-clock loop keeps running).
        resume
            No extra fields.  Resumes engine stepping after a pause.
            Refused with an error while a model limit is active (see
            ``model_limit`` in the frame); a ``reset`` is required.
        reset
            No extra fields.  Calls ``reset()``: rebuilds the plant at
            t = 0, returns ``rod_command`` to 0.5 and clears the scram
            latch, and keeps ``P_setpoint`` and ``speed``.
        set_speed
            ``value: float`` — must be one of ``{1, 2, 5, 10}``.
        set_pressure_setpoint
            ``value: float`` [Pa] — must be in ``[10e6, 20e6]``.

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
            value = msg.get("value")
            if not _is_number(value):
                return {"type": "error", "detail": "set_rod_command requires a numeric 'value'"}
            value = float(value)
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
            value = msg.get("value")
            if not _is_number(value):
                return {"type": "error", "detail": "set_speed requires a numeric 'value'"}
            try:
                self.set_speed(value)
            except ValueError as err:
                return {"type": "error", "detail": str(err)}
            return {"type": "ack", "command": cmd_type}

        elif cmd_type == "set_pressure_setpoint":
            # Validate: must be within [10 MPa, 20 MPa] = [10e6, 20e6] Pa.
            value = msg.get("value")
            if not _is_number(value):
                return {
                    "type": "error",
                    "detail": "set_pressure_setpoint requires a numeric 'value'",
                }
            value = float(value)
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
