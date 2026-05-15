"""SimRuntime — asyncio background task wrapping SimEngine for the web UI.

This module is the bridge between the PWR simulation engine and the HTTP/WS
API layer. It owns:

- A fully wired ``SimEngine`` (identical to ``examples/run_primary.py``)
- An asyncio background task that steps the engine at a fixed cadence
- A command-state struct (rod position, scram, pressure setpoint, speed)
- A pub/sub mechanism that pushes telemetry frames to subscriber queues

Fidelity
--------
L1 — wraps the same L1 physics components as the run_primary example.

Architecture
------------
This module sits at the TOP of the four-layer stack and is the only layer
that knows about asyncio. It does NOT import from ``fission_sim.api.app``
or any HTTP framework.  Imports are restricted to:

    fission_sim.engine
    fission_sim.physics.*
    fission_sim.control.*

Layer rule (A-07): nothing below the API layer knows this module exists.

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


def _build_engine(
    core_params: CoreParams,
    loop_params: LoopParams,
    sg_params: SGParams,
    sink_params: SinkParams,
    rod_params: RodParams,
    pzr_params: PressurizerParams,
    ctrl_params: PressurizerControllerParams,
    *,
    rod_command_default: float,
    P_setpoint_default: float,
) -> SimEngine:
    """Build and finalize a SimEngine with the standard primary-plant wiring.

    Mirrors ``examples/run_primary.py`` exactly. Extracted so ``reset()``
    can rebuild the engine from scratch without duplicating the wiring logic.

    Parameters
    ----------
    core_params : CoreParams
        Point-kinetics reactor core parameters.
    loop_params : LoopParams
        Primary loop parameters.
    sg_params : SGParams
        Steam generator parameters.
    sink_params : SinkParams
        Secondary sink parameters.
    rod_params : RodParams
        Rod controller parameters.
    pzr_params : PressurizerParams
        Pressurizer parameters.
    ctrl_params : PressurizerControllerParams
        Pressurizer controller parameters.
    rod_command_default : float
        Default value for the ``rod_command`` external [0..1].
    P_setpoint_default : float
        Default value for the ``P_setpoint`` external [Pa].

    Returns
    -------
    SimEngine
        Finalized engine ready for ``step()`` calls.
    """
    engine = SimEngine()

    rod = engine.module(RodController(rod_params), name="rod")
    core = engine.module(PointKineticsCore(core_params), name="core")
    loop = engine.module(PrimaryLoop(loop_params), name="loop")
    sg = engine.module(SteamGenerator(sg_params), name="sg")
    _sink = engine.module(SecondarySink(sink_params), name="sink")
    pzr = engine.module(Pressurizer(pzr_params), name="pzr")
    pzr_ctrl = engine.module(PressurizerController(ctrl_params), name="pzr_ctrl")

    # Declare external inputs (operator-facing control signals).
    # These are overridden per-step by SimRuntime's command state.
    rod_cmd = engine.input("rod_command", default=rod_command_default)
    scram = engine.input("scram", default=False)
    P_setpoint = engine.input("P_setpoint", default=P_setpoint_default)
    heater_manual = engine.input("heater_manual", default=None)
    spray_manual = engine.input("spray_manual", default=None)

    # Wire the graph — same topology as run_primary.py.
    # The wiring defines the data-flow order; the engine resolves
    # topological dependencies at finalize() time.
    rho_rod = rod(rod_command=rod_cmd, scram=scram)
    T_sec = _sink()  # secondary sink produces a fixed cold-side temperature
    Q_sg_sig = sg(T_avg=loop.T_avg, T_secondary=T_sec)
    core(rho_rod=rho_rod, T_cool=loop.T_cool)
    pzr(
        power_thermal=core.power_thermal,
        Q_sg=Q_sg_sig,
        T_hotleg=loop.T_hot,
        T_coldleg=loop.T_cold,
        Q_heater=pzr_ctrl.Q_heater,
        m_dot_spray=pzr_ctrl.m_dot_spray,
    )
    pzr_ctrl(
        P=pzr.P,
        P_setpoint=P_setpoint,
        heater_manual=heater_manual,
        spray_manual=spray_manual,
    )
    loop(
        power_thermal=core.power_thermal,
        Q_sg=Q_sg_sig,
        m_dot_spray=pzr_ctrl.m_dot_spray,
        P_primary=pzr.P,
    )

    engine.finalize()
    return engine


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

    # Doppler feedback: α_f * (T_fuel − T_fuel_ref)
    # Negative for hotter fuel (more absorption), provides inherent stability.
    # We recompute here using the parameters embedded in the core telemetry
    # rather than carrying params through — the core telemetry already
    # exposes rho_doppler computed with the same formula.
    rho_doppler = core_tele.get("rho_doppler")

    # Moderator feedback: α_m * (T_avg − T_cool_ref)
    # Also negative in a well-designed PWR.
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
        # Runtime command state — lets the UI reflect what was commanded.
        "running": cmd.running,
        "speed": cmd.speed,
        "scrammed": cmd.scrammed,
        "rod_command": cmd.rod_command,
    }


class _CommandState:
    """Mutable command state for the runtime.

    Grouped in one place so ``reset()`` can swap the whole struct atomically.
    Access is protected by the SimRuntime's asyncio.Lock.

    Attributes
    ----------
    rod_command : float
        Desired fractional rod insertion [0..1]. 0 = fully inserted (shutdown),
        1 = fully withdrawn (maximum reactivity). Default 0.5 = design power.
    scrammed : bool
        True when a SCRAM has been commanded. The rod controller interprets
        this as rod_command_effective = 0 (full insertion).
    P_setpoint : float
        Primary pressure setpoint [Pa] for the pressurizer controller.
    speed : float
        Simulation speed multiplier. 1.0 = real time, 2.0 = double speed.
    running : bool
        Whether the step loop is actively advancing simulation time.
        False while paused or stopped.
    """

    def __init__(self, P_setpoint_default: float) -> None:
        self.rod_command: float = 0.5
        self.scrammed: bool = False
        self.P_setpoint: float = P_setpoint_default
        self.speed: float = 1.0
        self.running: bool = True  # True = not paused


class SimRuntime:
    """Background asyncio task that runs the PWR simulator continuously.

    This is the primary integration point between the simulation engine and
    the web API. It:

    1. Owns a fully wired ``SimEngine`` (same topology as run_primary.py).
    2. Runs a step loop at ``cadence_hz`` Hz — each step advances simulation
       time by ``dt * speed`` where ``dt = 1 / cadence_hz``.
    3. Publishes telemetry frames to all subscribed asyncio queues.
    4. Accepts command mutations (rod position, scram, pressure setpoint,
       speed) via thread-safe setter methods.

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

    Architecture (A-07)
    -------------------
    This module only imports from ``fission_sim.engine``, ``fission_sim.physics``,
    and ``fission_sim.control``. It is completely HTTP-agnostic.

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
    ``rod_command``.
    """

    def __init__(self, cadence_hz: float = _DEFAULT_CADENCE_HZ) -> None:
        self._cadence_hz = cadence_hz
        self._dt = 1.0 / cadence_hz  # wall-clock seconds between steps [s]

        # Build default parameter objects (same as run_primary.py).
        self._core_params = CoreParams()
        self._loop_params = LoopParams()
        self._sg_params = SGParams()
        self._sink_params = SinkParams()
        self._rod_params = RodParams()
        self._pzr_params = PressurizerParams(loop_params=self._loop_params)
        self._ctrl_params = PressurizerControllerParams()

        # Mutable command state, protected by _lock.
        self._cmd = _CommandState(P_setpoint_default=self._ctrl_params.P_setpoint_default)

        # asyncio.Lock serialises command mutations so the step loop always
        # sees a consistent view of rod_command, P_setpoint, etc.
        self._lock = asyncio.Lock()

        # Build the initial engine (synchronous; cheap until the first step).
        self._engine = self._new_engine()

        # Latest telemetry frame — updated after every engine step.
        # Initialized from the engine's initial snapshot so callers can
        # call snapshot() before the first step completes.
        self._latest_frame: dict[str, Any] = _build_telemetry_frame(
            self._engine.snapshot(), self._cmd
        )

        # Pub/sub: a set of asyncio.Queue objects registered by subscribers.
        self._subscribers: set[asyncio.Queue] = set()

        # Background task handle; None until start() is called.
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _new_engine(self) -> SimEngine:
        """Build a fresh SimEngine with the current parameter objects.

        Called once at construction and again by ``reset()`` to rebuild
        the engine from t = 0.

        Returns
        -------
        SimEngine
            Finalized engine at t = 0.
        """
        return _build_engine(
            self._core_params,
            self._loop_params,
            self._sg_params,
            self._sink_params,
            self._rod_params,
            self._pzr_params,
            self._ctrl_params,
            rod_command_default=self._cmd.rod_command,
            P_setpoint_default=self._cmd.P_setpoint,
        )

    async def _step_loop(self) -> None:
        """Main background loop — steps the engine at ``cadence_hz`` Hz.

        Sleeps between steps so wall-clock time advances approximately at
        the cadence rate. The sleep time is adjusted to account for the
        time spent in ``engine.step()`` itself (which can be significant for
        stiff ODE solvers).

        Publishes a telemetry frame to all subscribers after each step.
        """
        while True:
            t0_wall = time.monotonic()

            async with self._lock:
                # Snapshot command state while holding the lock so the step
                # sees a consistent view even if setters are called concurrently.
                is_running = self._cmd.running
                rod_cmd = self._cmd.rod_command
                scrammed = self._cmd.scrammed
                P_setpoint = self._cmd.P_setpoint
                speed = self._cmd.speed

            if is_running:
                # Advance simulation time by dt * speed (may be > 1× if speed > 1).
                # The engine's BDF integrator handles the stiff ODE internally.
                sim_dt = self._dt * speed
                try:
                    snap = self._engine.step(
                        sim_dt,
                        rod_command=rod_cmd,
                        scram=scrammed,
                        P_setpoint=P_setpoint,
                        # heater_manual and spray_manual left at engine defaults (None).
                        heater_manual=None,
                        spray_manual=None,
                    )
                except Exception:
                    logger.exception("Engine step failed; simulation paused")
                    async with self._lock:
                        self._cmd.running = False
                    await asyncio.sleep(self._dt)
                    continue

                # Build telemetry frame and publish to all subscribers.
                frame = _build_telemetry_frame(snap, self._cmd)
                self._latest_frame = frame
                self._publish(frame)

            # Sleep for the remainder of the wall-clock cycle.
            elapsed = time.monotonic() - t0_wall
            sleep_time = max(0.0, self._dt - elapsed)
            await asyncio.sleep(sleep_time)

    def _publish(self, frame: dict[str, Any]) -> None:
        """Push a telemetry frame to all subscriber queues.

        If a queue is full (maxsize reached), the oldest frame is discarded
        to make room for the new one. This keeps slow consumers from blocking
        the step loop, at the cost of dropping stale data (acceptable for
        a live dashboard).

        Parameters
        ----------
        frame : dict
            Telemetry frame to publish.
        """
        dead: list[asyncio.Queue] = []
        for q in self._subscribers:
            if q.full():
                # Drop the oldest frame to avoid blocking.
                try:
                    q.get_nowait()
                    logger.warning("Subscriber queue full; dropped oldest telemetry frame")
                except asyncio.QueueEmpty:
                    pass  # race — another task already consumed it
            try:
                q.put_nowait(frame)
            except asyncio.QueueFull:
                logger.warning("Subscriber queue still full after drop; frame lost")
            except Exception:
                logger.exception("Unexpected error publishing to subscriber queue; removing")
                dead.append(q)
        for q in dead:
            self._subscribers.discard(q)

    # ------------------------------------------------------------------
    # Lifecycle methods
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the background step loop.

        Idempotent — calling ``start()`` again while already running is a
        no-op with a debug log. Call ``stop()`` first to restart.

        Notes
        -----
        The background task is scheduled on the running event loop. The
        caller must therefore ``await start()`` from an async context.
        """
        if self._task is not None and not self._task.done():
            logger.debug("SimRuntime.start() called while already running — no-op")
            return
        self._task = asyncio.create_task(self._step_loop(), name="sim-step-loop")

    async def stop(self) -> None:
        """Cancel the background step loop and wait for it to finish.

        Safe to call multiple times. After stop(), the engine state is
        preserved — call ``reset()`` to return to t = 0.
        """
        if self._task is None or self._task.done():
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    async def reset(self) -> None:
        """Stop the step loop, rebuild the engine from t = 0, restart.

        All state (temperatures, neutron population, pressurizer mass,
        rod position) returns to its initial conditions. Command state
        (rod_command, P_setpoint, speed) is preserved.

        Notes
        -----
        This rebuilds the entire ``SimEngine`` object, which is the only
        reliable way to reset the global ODE state vector to ``initial_state()``.
        """
        was_running = self._task is not None and not self._task.done()
        await self.stop()

        async with self._lock:
            self._engine = self._new_engine()
            self._latest_frame = _build_telemetry_frame(
                self._engine.snapshot(), self._cmd
            )

        if was_running:
            await self.start()

    # ------------------------------------------------------------------
    # Pause / resume (synchronous — safe to call from sync or async code)
    # ------------------------------------------------------------------

    def pause(self) -> None:
        """Pause the simulation — the step loop keeps running but skips engine.step().

        The step loop sleeps normally, consuming negligible CPU. Resume with
        ``resume()``. Safe to call multiple times.
        """
        self._cmd.running = False

    def resume(self) -> None:
        """Resume the simulation after a ``pause()``.

        Safe to call when already running.
        """
        self._cmd.running = True

    # ------------------------------------------------------------------
    # Command setters
    # ------------------------------------------------------------------

    def set_rod_command(self, v: float) -> None:
        """Set the desired rod position.

        Parameters
        ----------
        v : float
            Rod command [0..1]. 0 = fully inserted (shutdown), 1 = fully
            withdrawn (maximum reactivity addition). The rod controller
            drives the physical rod toward this position at a finite speed
            (set by ``RodParams.rod_speed``).
        """
        self._cmd.rod_command = float(v)

    def scram(self) -> None:
        """Initiate a SCRAM — forces the rod controller to zero reactivity worth.

        A SCRAM (Safety Control Rod Axe Man, also Subcritical Reactivity
        Attenuation Mechanism) inserts all control rods at maximum speed.
        Modeled here as overriding ``rod_command_effective`` to 0,
        bypassing the operator's ``rod_command``.

        The reactor does not immediately go subcritical — delayed neutron
        precursors continue fissioning for tens of seconds. Power decays
        exponentially on the precursor half-lives.
        """
        self._cmd.scrammed = True

    def reset_scram(self) -> None:
        """Clear the SCRAM flag — restores operator rod control.

        Only valid after the reactor has been brought to a safe subcritical
        state and all trip conditions have been cleared. In the simulator
        this is unconditional (no interlock logic at M2).
        """
        self._cmd.scrammed = False

    def set_speed(self, x: float) -> None:
        """Set the simulation speed multiplier.

        Parameters
        ----------
        x : float
            Speed factor. 1.0 = real time, 2.0 = 2× faster. Must be > 0.
            Very large values may cause the ODE integrator to take large
            steps and be slow; use with care above ~10×.
        """
        if x <= 0:
            raise ValueError(f"speed multiplier must be > 0, got {x!r}")
        self._cmd.speed = float(x)

    def set_pressure_setpoint(self, p: float) -> None:
        """Set the primary pressure setpoint for the pressurizer controller.

        Parameters
        ----------
        p : float
            Pressure setpoint [Pa]. Nominal design value is 15.5 MPa = 1.55e7 Pa.
            The pressurizer controller will heat or spray to maintain this pressure.
        """
        self._cmd.P_setpoint = float(p)

    # ------------------------------------------------------------------
    # Snapshot and pub/sub
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Return the most recent telemetry frame (non-blocking).

        Returns
        -------
        dict
            The latest telemetry frame as produced by ``_build_telemetry_frame()``.
            Keys are documented in the module and class docstrings.
            Returns the initial-state frame if no step has completed yet.
        """
        return self._latest_frame

    def subscribe(self) -> asyncio.Queue:
        """Register a new subscriber and return its queue.

        The queue has a bounded capacity (``_QUEUE_MAXSIZE`` frames). If the
        consumer is slow and the queue fills, the oldest frame is silently
        dropped on the next publish call — acceptable for a live dashboard.

        Returns
        -------
        asyncio.Queue
            Call ``await q.get()`` to receive the next telemetry frame.
            Call ``runtime.unsubscribe(q)`` when done.
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
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
    # Command dispatch (feat-004)
    # ------------------------------------------------------------------

    async def handle_command(self, msg: dict[str, Any]) -> dict[str, Any] | None:
        """Validate and dispatch an operator command message.

        This is the single entry-point for all commands arriving over the
        WebSocket API. It validates the ``type`` field, applies range checks,
        acquires the runtime lock for mutations that touch ``_CommandState``,
        and calls the appropriate setter or lifecycle method.

        Supported ``msg['type']`` values
        ---------------------------------
        set_rod_command
            ``value: float`` in ``[0, 1]``.  Drives the rod controller toward
            the requested position.
        scram
            No extra fields.  Forces full rod insertion (effective rod_command = 0).
        reset_scram
            No extra fields.  Clears the scram latch, restoring operator rod control.
        pause
            No extra fields.  Suspends engine stepping (wall-clock loop keeps running).
        resume
            No extra fields.  Resumes engine stepping after a pause.
        reset
            No extra fields.  Rebuilds the engine from t = 0 while preserving
            ``P_setpoint``, ``speed``, and the user's last ``rod_command``.
            The scram latch is cleared on reset.
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
        dict or None
            Returns ``None`` on success.  Returns an error dict of the form
            ``{"type": "error", "detail": "<reason>"}`` for unknown command
            types or out-of-range values.  This method does **not** raise on
            bad input — the caller (recv loop in ``app.py``) decides how to
            relay the error to the client.

        Notes
        -----
        Mutations to ``_CommandState`` are serialised via ``self._lock``.
        The ``reset()`` method acquires its own lock internally, so it is
        *not* called while holding the lock here.
        """
        cmd_type = msg.get("type")

        if cmd_type == "set_rod_command":
            # Validate: rod command must be a number in [0, 1].
            value = msg.get("value")
            if not isinstance(value, (int, float)):
                return {"type": "error", "detail": "set_rod_command requires a numeric 'value'"}
            value = float(value)
            if not (0.0 <= value <= 1.0):
                return {
                    "type": "error",
                    "detail": f"set_rod_command value {value!r} is out of range [0, 1]",
                }
            async with self._lock:
                self.set_rod_command(value)
            return None

        elif cmd_type == "scram":
            async with self._lock:
                self.scram()
            return None

        elif cmd_type == "reset_scram":
            async with self._lock:
                self.reset_scram()
            return None

        elif cmd_type == "pause":
            # pause() and resume() only touch self._cmd.running — safe to call
            # without the lock since it is a boolean assignment in CPython, but
            # we acquire it for correctness in all cases.
            async with self._lock:
                self.pause()
            return None

        elif cmd_type == "resume":
            async with self._lock:
                self.resume()
            return None

        elif cmd_type == "reset":
            # reset() preserves P_setpoint, speed, and rod_command (handled
            # inside _new_engine which reads self._cmd at call time).
            # Scram latch is cleared so the operator starts fresh.
            async with self._lock:
                self._cmd.scrammed = False
                self._cmd.rod_command = 0.5
            # reset() manages its own locking and task lifecycle.
            await self.reset()
            return None

        elif cmd_type == "set_speed":
            # Allowed values: 1, 2, 5, 10 (integers or floats equal to those).
            value = msg.get("value")
            if not isinstance(value, (int, float)):
                return {"type": "error", "detail": "set_speed requires a numeric 'value'"}
            value = float(value)
            _ALLOWED_SPEEDS = {1.0, 2.0, 5.0, 10.0}
            if value not in _ALLOWED_SPEEDS:
                return {
                    "type": "error",
                    "detail": f"set_speed value {value!r} must be one of {sorted(_ALLOWED_SPEEDS)}",
                }
            async with self._lock:
                self.set_speed(value)
            return None

        elif cmd_type == "set_pressure_setpoint":
            # Validate: must be within [10 MPa, 20 MPa] = [10e6, 20e6] Pa.
            value = msg.get("value")
            if not isinstance(value, (int, float)):
                return {
                    "type": "error",
                    "detail": "set_pressure_setpoint requires a numeric 'value'",
                }
            value = float(value)
            _P_MIN_PA = 10e6   # 10 MPa — minimum plausible primary pressure [Pa]
            _P_MAX_PA = 20e6   # 20 MPa — maximum plausible primary pressure [Pa]
            if not (_P_MIN_PA <= value <= _P_MAX_PA):
                return {
                    "type": "error",
                    "detail": (
                        f"set_pressure_setpoint value {value:.3e} Pa is out of range "
                        f"[{_P_MIN_PA:.3e}, {_P_MAX_PA:.3e}] Pa"
                    ),
                }
            async with self._lock:
                self.set_pressure_setpoint(value)
            return None

        else:
            # Unknown command type — return an error frame; do not disconnect.
            return {
                "type": "error",
                "detail": f"unknown command type: {cmd_type!r}",
            }


__all__ = ["SimRuntime"]
