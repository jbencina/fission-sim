"""Rod controller (control bank + shutdown bank + manual scram), simplest model.

Models two lumped rod banks:

- a **control bank** that the operator positions: a commanded position is
  tracked by the actual position via a rate-limited first-order lag;
- a **shutdown bank** that sits fully withdrawn in normal operation and
  drops in only on SCRAM.

On SCRAM both banks fall to the bottom of the core. Each bank's position is
converted to reactivity via a linear rod-worth function, and the two
contributions are summed into ``rho_rod``.

Why two banks: a real PWR operator moves one control bank worth on the order
of a thousand pcm, while the much larger shutdown worth of all the rods
together is reserved for the trip. Giving the operator's slider the full
shutdown worth would make a few-percent slider move a prompt-critical
reactivity step.

This component is the bridge between human decisions (rod_command, scram)
and the physics (rho_rod into the core). With it in the plant, the only
"fake" inputs in the simulator are the operator's keystrokes — which is
exactly what they should be (we don't model human decisions).

The README's "Educational Component Guide" and "Equations" sections explain
this model for learners.

References
----------
Lamarsh, J. R. and Baratta, A. J. *Introduction to Nuclear Engineering*,
3rd ed., Prentice Hall, 2001. (Control rod theory and rod worth, Ch. 7-8.)

Public references:

- U.S. NRC Technical Training Center, *Reactor Concepts Manual:
  Pressurized Water Reactor Systems*, for PWR control-rod and reactor
  system context:
  https://ww2.nrc.gov/sites/default/files/doc_library/cdn/legacy/reading-rm/basic-ref/students/for-educators/04.pdf
- Nuclear-power.com, "SCRAM - Reactor Trip", for public PWR scram timing
  context. The constant-velocity SCRAM drop and the rate-limited first-order
  tracker for normal motion are this simulator's simplified actuator
  approximations:
  https://www.nuclear-power.com/nuclear-power/reactor-physics/reactor-dynamics/scram-reactor-trip/
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RodParams:
    """Parameters for the two-bank rod controller.

    All defaults are illustrative for a generic large PWR. The reference
    position (``rod_position_critical``) is derived from
    ``rod_position_design`` unless explicitly supplied.

    Parameters
    ----------
    tau : float
        First-order lag time constant for normal (motor-driven) motion [s].
        Sets the size of the slow-down zone near the commanded position.
    v_normal : float
        Maximum normal motion speed [1/s, fraction of travel per second].
        Illustrative: real PWR rod drives move roughly 0.5 %/s (approximate
        and unverified; see the field comment); the model uses 1 %/s.
    v_scram : float
        SCRAM drop speed [1/s]. Default 0.5 gives a 2 s full-travel drop.
    tau_scram : float
        Lag time constant used only during SCRAM [s]. Small, so the drop is
        constant-velocity until the last ``v_scram * tau_scram`` = 1 % of
        travel. See the field comment for the resulting timing.
    rho_control_worth : float
        Worth of the operator-positioned control bank over its full travel
        (0 → 1) [dimensionless]. Default 0.012 = 1,200 pcm.
    rho_shutdown_worth : float
        Worth of the shutdown bank over its full travel [dimensionless].
        Default 0.064 = 6,400 pcm.
    rod_position_design : float
        Control-bank position [dimensionless, 0–1] at the coupled-plant
        design steady state. Default 0.5 (halfway) gives symmetric room for
        both withdrawal and insertion.
    rod_position_critical : float, optional
        Control-bank position [dimensionless] where the control bank
        contributes zero reactivity. If None, derived in ``__post_init__``
        to equal ``rod_position_design`` so that at the coupled-plant design
        point the rod contribution to total reactivity is exactly zero
        (matching the core's Doppler/moderator zero-by-construction).
    rod_position_initial : float, optional
        Initial control-bank position. None → ``rod_position_design``.

    Notes
    -----
    The class is frozen, but ``__post_init__`` uses ``object.__setattr__``
    to fill in the derived ``rod_position_critical`` default. Standard
    pattern for frozen dataclasses with derived fields.
    """

    # First-order lag time constant for normal (motor-driven) motion.
    # Small rod motions follow exp(-t/tau) decay toward the commanded
    # position.
    #
    # NOTE on the choice of 1.0 s: tau has no direct physical analog in real
    # rod actuators, which are essentially constant-velocity (stepping
    # mechanisms for normal motion). The lag form
    # `drod/dt = (cmd - pos) / tau` is a numerical smoothing trick that
    # removes the discontinuity an ideal velocity tracker would have at
    # the setpoint. tau sets the size of the slow-down zone:
    #   * Slow-down zone is `tau · v_normal = 0.01` (1 % of full travel).
    #     Above 1 % mismatch, motion is rate-clipped at v_normal — matching
    #     how real rods actually move.
    #   * Numerically benign — BDF handles a 1 s time constant trivially.
    # SCRAM uses its own, much smaller lag constant (tau_scram below).
    tau: float = 1.0  # [s]

    # Normal motion speed limit, as a fraction of full travel per second.
    # Illustrative, not a plant value: 1 %/s is roughly 1.4 in/s over a
    # ~12 ft (3.66 m) stroke. A Westinghouse magnetic-jack drive at its
    # maximum 72 steps/min × 5/8 in per step moves 0.75 in/s, about
    # 0.5 %/s, so this model's rods move about twice as fast as that.
    # (Drive figures quoted from memory, not verified against a
    # Westinghouse or NRC document.)
    # With the control-bank worth below, 1 %/s is 12 pcm/s.
    v_normal: float = 0.01  # [1/s]

    # SCRAM trajectory. On SCRAM each bank moves toward 0 (fully inserted)
    # at
    #     d(pos)/dt = max(-pos / tau_scram, -v_scram)
    # i.e. at constant speed v_scram until the last v_scram · tau_scram =
    # 0.01 (1 % of travel), then exponentially with time constant
    # tau_scram. Defining "inserted" as pos ≤ 0.01 (99 % of travel), a
    # bank starting at pos0 is inserted after
    #     t_insert = (pos0 − 0.01) / v_scram
    # = 1.98 s for the fully withdrawn shutdown bank and 0.98 s for the
    # control bank from its design position 0.5. By t = 2.0 s every bank
    # is within 0.004 of the bottom.
    #
    # Real context: PWR rods fall under gravity once the drive mechanism
    # releases them. The Westinghouse Standard Technical Specifications,
    # NUREG-1431, SR 3.1.4.3, require a rod drop time from the fully
    # withdrawn position of ≤ [2.7] s "from the beginning of decay of
    # stationary gripper coil voltage to dashpot entry"; the brackets mark
    # a plant-specific value, and the final dashpot deceleration comes
    # after that. (Quoted from memory, not verified against the document
    # text.) This model's ~2 s is of that order.
    # SIMPLIFICATION: constant-velocity drop. A real rod starts from rest,
    # accelerates, then is slowed by the coolant and the dashpot, and a
    # ~0.1–0.2 s release delay precedes motion. With linear worth (below)
    # this model inserts negative reactivity somewhat earlier in the drop
    # than a real rod does.
    v_scram: float = 0.5  # [1/s]
    tau_scram: float = 0.02  # [s]

    # Control-bank worth over its full travel. Positive: withdrawal raises
    # reactivity. With design at 0.5 the operator can add at most
    # 0.012 × 0.5 = +600 pcm (full withdrawal) or −600 pcm (full
    # insertion) of ROD reactivity relative to the design critical state.
    # +600 pcm is 0.92 $ — below prompt critical (sum(beta_i) = 650.2 pcm
    # for the core's Keepin U-235 data). That bounds the rod term only:
    # in a core that has cooled below its reference temperatures, the
    # negative temperature coefficients add positive reactivity of their
    # own (up to ~1,480 pcm here), which the control bank's −600 pcm
    # cannot cancel. That is why the shutdown bank stays in after a SCRAM
    # (see rho_shutdown_worth). One 1 % step of travel is 12 pcm.
    # Magnitude: a single PWR control bank is commonly worth on the order
    # of 1,000–1,500 pcm over its travel; 1,200 pcm is an illustrative
    # value in that range, not a plant-specific one. Plant values are in
    # each FSAR's Chapter 4 rod-worth tables.
    #
    # SIMPLIFICATION: linear rod worth. Real reactor rods have an S-shaped
    # position-to-reactivity curve because absorbed neutrons are weighted
    # by local flux (cosine-shaped along the core's vertical axis). Top
    # and bottom of the core have low flux, so rod motion there does
    # little; the middle does almost all the work. The linear
    # approximation is wrong in detail but right at the endpoints (zero
    # at the critical position, full worth when fully inserted). A point
    # model also has no flux redistribution, so rod worth does not change
    # with power level or with the other bank's position.
    rho_control_worth: float = 0.012  # [dimensionless] (1,200 pcm)

    # Shutdown-bank worth over its full travel. The shutdown bank stands
    # for all the rods that are fully withdrawn at power (shutdown banks
    # plus any control banks not being maneuvered). It is only inserted by
    # SCRAM, and once released it stays inserted: clearing the SCRAM latch
    # returns only the control bank to the operator. Withdrawing it again
    # takes a full simulation reset.
    # Why: in a real plant, pulling the shutdown banks after a trip is a
    # deliberate, procedure-driven reactor startup (shutdown-margin
    # checks, bank-by-bank withdrawal, approach to criticality watched on
    # the source- and intermediate-range instruments). This simulator
    # does not model that procedure. Letting the bank withdraw by itself
    # once the latch clears would re-insert 6,400 pcm into a cooled-down
    # core, whose temperature feedback has already returned up to
    # ~1,480 pcm, and the core would go supercritical even with the
    # control bank fully inserted.
    # Total SCRAM worth from the design point:
    #     control 0.012 × 0.5 + shutdown 0.064 = 0.070 = 7,000 pcm.
    # Post-SCRAM margin: as the plant cools, the negative temperature
    # coefficients turn positive reactivity back in. At most the fuel
    # cools from 1,100 K to the 558 K secondary temperature (Doppler
    # +2.5e-5 × 542 = +1,355 pcm) and the coolant from 583 K to 558 K
    # (moderator +5e-5 × 25 = +125 pcm). With the shutdown bank in, rod +
    # feedback therefore stays at or below about −5,500 pcm while the
    # SCRAM is latched, and at or below about −4,300 pcm (−6,400 + 600 +
    # 1,480) after the latch is cleared, whatever the control-bank
    # command. The core stays subcritical until the simulation is reset.
    # SIMPLIFICATION: no stuck-rod allowance, no xenon, no boron. Real
    # shutdown-margin analyses assume the most reactive rod stays out.
    rho_shutdown_worth: float = 0.064  # [dimensionless] (6,400 pcm)

    # Design position. Halfway gives equal insertion/withdrawal margin.
    rod_position_design: float = 0.5  # [dimensionless, 0..1]

    # Derived in __post_init__ so design state has zero rod reactivity.
    rod_position_critical: float | None = None  # [dimensionless]

    # Initial control-bank position used by initial_state(). None → use
    # rod_position_design. Override for cold-startup demos (e.g., 0.1 =
    # control bank nearly fully inserted at session start). The shutdown
    # bank always starts fully withdrawn.
    rod_position_initial: float | None = None  # [dimensionless, 0..1]

    def __post_init__(self) -> None:
        """Derive ``rod_position_critical`` so design state has zero rod reactivity.

        At the coupled-plant design point, the core requires
        ``rho_rod = 0`` (because Doppler and moderator are also zero by
        their own reference choices). With the shutdown bank fully
        withdrawn, the rod controller's output is
        ``rho_control_worth · (rod_position − rod_position_critical)``. For
        this to be zero at ``rod_position = rod_position_design``, we
        need ``rod_position_critical = rod_position_design``.
        """
        if self.rod_position_critical is None:
            # Frozen dataclass; bypass the freeze to set the derived default.
            object.__setattr__(self, "rod_position_critical", self.rod_position_design)


class RodController:
    """Two-bank rod controller with rate-limited motion and linear worth.

    The class owns its parameters and equations. It does NOT own
    time-evolving state. State (the two bank positions) lives in a numpy
    array passed in by the caller (a driver script or the simulation
    engine).

    This component is the bridge between operator decisions and physics:
    operator commands (``rod_command``, ``scram``) come in as inputs; the
    actual bank positions evolve under rate-limited tracking; the positions
    are converted to reactivity in ``outputs()``.

    Ports in (passed to ``derivatives()`` via the ``inputs`` dict):
        rod_command : float [dimensionless, 0–1]
            Operator's setpoint for the control-bank position. 0 = fully
            inserted, 1 = fully withdrawn.
        scram : bool
            If True, both banks are driven to 0 (fully inserted) along the
            SCRAM trajectory, overriding ``rod_command``. When it clears,
            only the control bank returns to ``rod_command``; the released
            shutdown bank completes its drop and stays inserted until the
            simulation is reset (see ``RodParams.rho_shutdown_worth``).

    Ports out (returned by ``outputs()``):
        rho_rod : float [dimensionless]
            Total rod reactivity, control bank + shutdown bank. Zero at
            design; positive when the control bank is withdrawn beyond
            design, negative when either bank is inserted.
        rod_position : float [dimensionless, 0–1]
            Actual control-bank position. Exposed as a signal so automatic
            rod controllers can track the physical bank for bumpless mode
            transfers.

    State vector (length ``state_size`` = 2, names in ``state_labels``):
        index 0 : rod_position      — control-bank position [0–1 withdrawn]
        index 1 : shutdown_position — shutdown-bank position [0–1 withdrawn]

    Notes
    -----
    The actual positions can in principle drift outside [0, 1] if the
    integrator overshoots, but with the rate clip and physically-reasonable
    inputs (rod_command in [0, 1], scram boolean) this does not occur in
    practice. This model does not enforce hard bounds on the state vector.

    SIMPLIFICATION: no startup procedure. After a SCRAM the shutdown bank
    stays inserted even when the latch is cleared; a real operator would
    withdraw the shutdown banks deliberately, one at a time, during a
    reactor startup. Here a restart to power is a full simulation reset.
    """

    state_size: int = 2
    state_labels: tuple[str, ...] = ("rod_position", "shutdown_position")
    input_ports: tuple[str, ...] = ("rod_command", "scram")
    output_ports: tuple[str, ...] = ("rho_rod", "rod_position")

    # A shutdown bank within this distance of fully withdrawn (1.0) counts
    # as never released; see ``derivatives``. [fraction of travel]
    _WITHDRAWN_TOL: float = 1e-6

    def __init__(self, params: RodParams) -> None:
        """Construct a rod controller with the given parameters.

        Parameters
        ----------
        params : RodParams
            Frozen parameter set. Held as ``self.params`` for the lifetime
            of the object.
        """
        self.params = params

    def initial_state(self) -> np.ndarray:
        """Return the initial bank positions.

        The control bank defaults to ``rod_position_design`` (the
        design-point steady state, where combined with
        ``rod_command = rod_position_design`` and ``scram = False`` the
        initial derivative is zero by construction). Override via
        ``RodParams(rod_position_initial=...)`` for non-design starting
        points. The shutdown bank starts fully withdrawn (1.0).

        Returns
        -------
        np.ndarray, shape (2,)
            ``[rod_position, shutdown_position]``
        """
        p = self.params
        pos0 = p.rod_position_design if p.rod_position_initial is None else p.rod_position_initial
        return np.array([pos0, 1.0])

    def derivatives(self, state: np.ndarray, inputs: dict) -> np.ndarray:
        """Compute the bank-position rates.

        Pure function of ``state`` and ``inputs`` — no per-step state on
        ``self``. The adaptive ODE solver may call this function
        speculatively many times per step with hypothetical states it later
        discards.

        Parameters
        ----------
        state : np.ndarray, shape (2,)
            ``[rod_position, shutdown_position]`` in dimensionless 0–1.
        inputs : dict
            Required keys:

            - ``rod_command`` : float [dimensionless, 0–1] — operator's
              setpoint for the control-bank position.
            - ``scram`` : bool — if True, both banks follow the SCRAM
              trajectory to 0.

        Returns
        -------
        np.ndarray, shape (2,)
            ``[d rod_position/dt, d shutdown_position/dt]`` in 1/s.

        Notes
        -----
        Equations (README "Equations" section, rod controller):

        Normal operation (scram=False), motor-driven control bank:

            d rod/dt = clip((rod_command − rod) / τ, −v_normal, +v_normal)

        SCRAM (scram=True), gravity drop of both banks:

            d pos/dt = clip((0 − pos) / τ_scram, −v_scram, +v_normal)

        Shutdown bank: fully withdrawn and stationary (d shutdown/dt = 0)
        until a SCRAM releases it. Once released (scram=True, or
        shutdown < 1 after the latch clears) it follows the drop equation
        above to the bottom and stays there; nothing withdraws it again.

        Two regimes within whichever cap applies:

        - **Saturation region** (large |error|): rate is clipped to the
          velocity cap — constant-velocity motion, like a real rod drive.
          For normal motion that is |error| > τ·v_normal = 0.01; for SCRAM
          it is pos > τ_scram·v_scram = 0.01.
        - **Lag region** (small |error|): rate is ``error / τ``, smooth
          first-order approach to the target, which avoids a discontinuous
          rate at the setpoint.

        SCRAM timing that follows from these equations is derived in the
        ``RodParams.v_scram`` comment: 99 % insertion after
        (pos0 − 0.01) / v_scram, i.e. 1.98 s from fully withdrawn.
        """
        p = self.params
        rod_position = state[0]
        shutdown_position = state[1]
        rod_command = inputs["rod_command"]
        scram = inputs["scram"]

        dstate = np.empty(self.state_size)
        if scram:
            # Gravity drop of both banks toward fully inserted (0).
            # SIMPLIFICATION: scram is binary and acts instantly. Real
            # scrams have small delays for relay/breaker action and
            # gripper release (a fraction of a second) before rods move.
            # The clip() puts a kink in the rate at pos = 0.01; BDF handles
            # it fine with the engine's max_step.
            dstate[0] = np.clip(-rod_position / p.tau_scram, -p.v_scram, p.v_normal)
            dstate[1] = np.clip(-shutdown_position / p.tau_scram, -p.v_scram, p.v_normal)
        else:
            # Motor-driven control bank, capped at v_normal in either
            # direction, follows the operator.
            dstate[0] = np.clip((rod_command - rod_position) / p.tau, -p.v_normal, p.v_normal)
            # "Released" is judged with a small tolerance rather than an
            # exact ``< 1.0``: the integrator may hand back a withdrawn
            # bank as 0.9999999999, and that round-off must not read as a
            # SCRAM that never happened. A real drop moves the bank far
            # past this tolerance within milliseconds.
            if shutdown_position < 1.0 - self._WITHDRAWN_TOL:
                # Released by an earlier SCRAM: a dropped bank finishes its
                # fall and stays in, even though the latch has cleared (see
                # RodParams.rho_shutdown_worth for why it is not withdrawn).
                dstate[1] = np.clip(-shutdown_position / p.tau_scram, -p.v_scram, p.v_normal)
            else:
                # Never released: held where it is, which is fully
                # withdrawn to within the tolerance. The residual offset is
                # worth at most 1e-6 · 6,400 pcm < 0.01 pcm, so nothing
                # needs to pull it back to exactly 1.0.
                dstate[1] = 0.0
        return dstate

    def _bank_reactivities(self, state: np.ndarray) -> tuple[float, float]:
        """Return ``(rho_control, rho_shutdown)`` for the given positions.

        Linear worth for each bank (Lamarsh & Baratta Ch. 7–8 for rod worth;
        the linear shape is a simplification described on
        ``RodParams.rho_control_worth``):

            rho_control  = rho_control_worth  · (rod_position − rod_position_critical)
            rho_shutdown = rho_shutdown_worth · (shutdown_position − 1)

        The shutdown term is zero when that bank is fully withdrawn and
        −rho_shutdown_worth when it is fully inserted.
        """
        p = self.params
        rho_control = p.rho_control_worth * (state[0] - p.rod_position_critical)
        rho_shutdown = p.rho_shutdown_worth * (state[1] - 1.0)
        return rho_control, rho_shutdown

    def outputs(self, state: np.ndarray, inputs: dict | None = None) -> dict:
        """Return rod reactivity and actual control-bank position.

        Parameters
        ----------
        state : np.ndarray, shape (2,)
            ``[rod_position, shutdown_position]``.
        inputs : dict, optional
            Unused for this component (rod reactivity depends only on
            position). Accepted for API uniformity.

        Returns
        -------
        dict
            ``{"rho_rod": float [dimensionless], "rod_position": float [dimensionless]}``.
        """
        rho_control, rho_shutdown = self._bank_reactivities(state)
        return {"rho_rod": rho_control + rho_shutdown, "rod_position": state[0]}

    def telemetry(self, state: np.ndarray, inputs: dict | None = None) -> dict:
        """Return a rich diagnostic dict for logging and visualization.

        Superset of ``outputs()``. Adds both bank positions and their
        separate reactivities and, when ``inputs`` is provided, echoes the
        operator commands plus the resolved ``rod_command_effective``
        (= 0 if scram, else rod_command).

        Parameters
        ----------
        state : np.ndarray, shape (2,)
        inputs : dict, optional
            If provided (with the same keys as ``derivatives``), echoes
            ``rod_command``, ``scram``, and the resolved
            ``rod_command_effective``. If omitted, those keys are reported
            as None.

        Returns
        -------
        dict
            Keys: ``rod_position`` (control bank), ``shutdown_position``,
            ``rho_rod``, ``rho_control``, ``rho_shutdown``,
            ``rod_command``, ``scram``, ``rod_command_effective``.
        """
        rho_control, rho_shutdown = self._bank_reactivities(state)

        out = {
            "rod_position": state[0],
            "shutdown_position": state[1],
            "rho_rod": rho_control + rho_shutdown,
            "rho_control": rho_control,
            "rho_shutdown": rho_shutdown,
        }
        if inputs is not None:
            cmd = inputs.get("rod_command")
            scram = inputs.get("scram")
            out["rod_command"] = cmd
            out["scram"] = scram
            # rod_command_effective = 0 if scram else rod_command
            out["rod_command_effective"] = 0.0 if scram else cmd
        else:
            out["rod_command"] = None
            out["scram"] = None
            out["rod_command_effective"] = None
        return out
