"""Rod controller (rod position + manual scram) — fidelity level L1.

Models the operator interface: a commanded rod position is tracked by an
actual rod position via a rate-limited first-order lag. The actual position
is converted to reactivity via a linear (L1) rod-worth function.

This component is the bridge between human decisions (rod_command, scram)
and the physics (rho_rod into the core). After this component lands,
the only "fake" inputs in the simulator are the operator's keystrokes —
which is exactly what they should be (we don't model human decisions).

Physics specification: see ``.docs/design.md`` §5.5.

References
----------
Lamarsh, J. R. and Baratta, A. J. *Introduction to Nuclear Engineering*,
3rd ed., Prentice Hall, 2001. (Control rod theory and rod worth, Ch. 7-8.)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RodParams:
    """Parameters for the L1 rod controller.

    All defaults are illustrative for a generic large PWR. The reference
    position (``rod_position_critical``) is derived from
    ``rod_position_design`` unless explicitly supplied.

    Parameters
    ----------
    tau : float
        First-order lag time constant [s]. Sets the timescale for small
        rod motions in the lag regime.
    v_normal : float
        Maximum normal motion speed [1/s]. Typical PWR rod drive rates
        are ~1%/s, hence the 0.01 default.
    v_scram : float
        Maximum scram speed [1/s]. Default 0.5 corresponds to full
        insertion from fully-withdrawn in ~2 s, matching real PWR scram
        timing.
    rho_total_worth : float
        Reactivity slope per unit rod position [dimensionless]. Positive:
        increasing rod_position (withdrawing rods) raises reactivity.
        With the default value 0.14 and design position 0.5, scram
        (pos → 0) delivers exactly −7000 pcm of reactivity.
    rod_position_design : float
        Position [dimensionless, 0–1] where the bank sits at the
        coupled-plant design steady state. Default 0.5 (halfway) gives
        symmetric room for both withdrawal and insertion.
    rod_position_critical : float, optional
        Position [dimensionless] where the rod produces zero reactivity.
        If None, derived in ``__post_init__`` to equal
        ``rod_position_design`` so that at the coupled-plant design point
        the rod contribution to total reactivity is exactly zero (matching
        the core's Doppler/moderator zero-by-construction).

    Notes
    -----
    The class is frozen, but ``__post_init__`` uses ``object.__setattr__``
    to fill in the derived ``rod_position_critical`` default. Standard
    pattern for frozen dataclasses with derived fields.
    """

    # First-order lag time constant. Small rod motions follow
    # exp(-t/tau) decay toward the commanded position.
    #
    # NOTE on the choice of 1.0 s: tau has no direct physical analog in real
    # rod actuators, which are essentially constant-velocity (stepper motors
    # for normal motion, gravity drop for scram). The lag form
    # `drod/dt = (cmd - pos) / tau` is a numerical smoothing trick that
    # eliminates the discontinuity an ideal velocity tracker would have at
    # the setpoint. tau is the size of the slow-down zone.
    #
    # tau=1.0 was chosen because:
    #   * Slow-down zone is `tau · v_normal = 0.01` (1% of full travel).
    #     Above 1% mismatch, the controller is in the velocity-clipped
    #     regime — matching how real rods actually move.
    #   * For scram from any realistic position (>0.05), the v_scram clip
    #     binds, giving the ~2s full insertion time the spec calls for.
    #   * Numerically benign — BDF integrator handles 1 s time constants
    #     trivially.
    #
    # Smaller tau → cleaner velocity tracking but stiffer ODE.
    # Larger tau → rate caps become vestigial; lag dominates.
    tau: float = 1.0  # [s]

    # Normal motion speed limit. Sources: typical PWR rod drive rate
    # ~1 inch/s on a ~12 ft (3.66 m) core gives ~1%/s in fractional units.
    v_normal: float = 0.01  # [1/s]

    # Scram speed limit (rate cap). Real plants use gravity-drop scrams that
    # fully insert in ~1.5–2.5 s. With v_scram=0.5/s and the default τ=1s,
    # the clip binds for the bulk of any realistic scram (initial error ≈
    # 0.5; raw_rate = 0.5/τ = 0.5, exactly at the cap). Result: full
    # insertion in ~2 s, matching real PWR scram timing.
    v_scram: float = 0.5  # [1/s]

    # Reactivity slope per unit rod position. Positive: withdrawal raises
    # reactivity. The total swing (pos=0 vs pos=1) is rho_total_worth, so
    # 0.14 = ±14000 pcm full swing. With design at 0.5, scram (0.5 → 0)
    # delivers 0.14 * 0.5 = 0.07 = +7000 pcm of negative reactivity (the
    # change in rho_rod is -7000 pcm).
    #
    # SIMPLIFICATION: linear rod worth. Real reactor rods have an S-shaped
    # position-to-reactivity curve because absorbed neutrons are weighted
    # by local flux (cosine-shaped along the core's vertical axis). Top
    # and bottom of the core have low flux, so rod motion there does
    # little; the middle does almost all the work. The L1 linear
    # approximation is wrong in detail but right at the endpoints (zero
    # at critical position, full negative when fully inserted).
    rho_total_worth: float = 0.14  # [dimensionless]

    # Design position. Halfway gives equal scram/withdrawal margin.
    rod_position_design: float = 0.5  # [dimensionless, 0..1]

    # Derived in __post_init__ so design state has zero rod reactivity.
    rod_position_critical: float | None = None  # [dimensionless]

    def __post_init__(self) -> None:
        """Derive ``rod_position_critical`` so design state has zero rod reactivity.

        At the coupled-plant design point, the core requires
        ``rho_rod = 0`` (because Doppler and moderator are also zero by
        their own reference choices). The rod controller's output is
        ``rho_total_worth · (rod_position − rod_position_critical)``. For
        this to be zero at ``rod_position = rod_position_design``, we
        need ``rod_position_critical = rod_position_design``.
        """
        if self.rod_position_critical is None:
            # Frozen dataclass; bypass the freeze to set the derived default.
            object.__setattr__(self, "rod_position_critical", self.rod_position_design)


class RodController:
    """L1 rod controller with rate-limited motion and linear worth.

    The class owns its parameters and equations. It does NOT own
    time-evolving state. State (the actual rod position) lives in a numpy
    array passed in by the caller (a driver script for now, the simulation
    engine eventually).

    This component is the bridge between operator decisions and physics:
    operator commands (``rod_command``, ``scram``) come in as inputs; the
    actual rod position evolves under rate-limited tracking; the position
    is converted to reactivity in ``outputs()``.

    Ports in (passed to ``derivatives()`` via the ``inputs`` dict):
        rod_command : float [dimensionless, 0–1]
            Operator's setpoint for rod position. 0 = fully inserted,
            1 = fully withdrawn.
        scram : bool
            If True, the controller forces the effective command to 0
            (fully inserted) and the rate clip allows scram speed.

    Ports out (returned by ``outputs()``):
        rho_rod : float [dimensionless]
            Reactivity contribution of the rod bank at the current
            position. Zero at design; positive when withdrawn, negative
            when inserted (relative to design).

    State vector (length ``state_size`` = 1, names in ``state_labels``):
        index 0 : rod_position — actual rod position [dimensionless, 0–1]

    Notes
    -----
    The actual rod position can in principle drift outside [0, 1] if the
    integrator overshoots, but with the rate-clip and physically-reasonable
    inputs (rod_command in [0, 1], scram boolean) this does not occur in
    practice. We do not enforce hard bounds on the state vector at L1.
    """

    state_size: int = 1
    state_labels: tuple[str, ...] = ("rod_position",)
    input_ports: tuple[str, ...] = ("rod_command", "scram")
    output_ports: tuple[str, ...] = ("rho_rod",)

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
        """Return the design-point initial state.

        At t=0 the rod position is at the design steady-state position.
        Combined with ``rod_command = rod_position_design`` and
        ``scram = False``, the initial derivative is zero by construction.

        Returns
        -------
        np.ndarray, shape (1,)
            ``[rod_position_design]``
        """
        return np.array([self.params.rod_position_design])

    def derivatives(self, state: np.ndarray, inputs: dict) -> np.ndarray:
        """Compute drod_position/dt with rate-limited first-order tracking.

        Pure function of ``state`` and ``inputs`` — no per-step state on
        ``self``. The adaptive ODE solver may call this function
        speculatively many times per step with hypothetical states it later
        discards.

        Parameters
        ----------
        state : np.ndarray, shape (1,)
            ``[rod_position]`` in dimensionless 0–1.
        inputs : dict
            Required keys:

            - ``rod_command`` : float [dimensionless, 0–1] — operator's
              setpoint for rod position.
            - ``scram`` : bool — if True, forces effective command to 0
              and lets the rate clip allow scram speed.

        Returns
        -------
        np.ndarray, shape (1,)
            ``[drod_position/dt]`` in 1/s.

        Notes
        -----
        Equation (.docs/design.md §5.5):

            rod_command_effective = 0 if scram else rod_command
            drod_position/dt = clip((rod_command_effective − rod_position) / τ,
                                     −v_scram, +v_normal)

        Two regimes:

        - **Lag region** (small |error|): rate is ``error / τ``, smooth
          first-order tracking toward the commanded position.
        - **Saturation region** (large |error|): rate is clipped to
          ``±v_normal`` or ``−v_scram``, constant velocity.

        The crossover happens when ``|error| / τ`` exceeds the velocity
        limit. For default parameters (τ=1s, v_normal=0.01/s), crossover
        is at |error| = 0.01 — i.e. 1% mismatch between command and
        position. Above that, motion is rate-clipped at v_normal (matching
        how a real rod-drive mechanism behaves); below it, motion is the
        smooth first-order lag.
        """
        p = self.params
        rod_position = state[0]
        rod_command = inputs["rod_command"]
        scram = inputs["scram"]

        # Scram forces the effective command to fully-inserted (0).
        # SIMPLIFICATION: scram is binary in the model. Real scrams have
        # small finite ramp times for relay closure, breaker opening, and
        # gravity-drop initiation — typically <100 ms total. We treat as
        # instantaneous.
        rod_command_effective = 0.0 if scram else rod_command

        # First-order lag with rate clipping.
        # SIMPLIFICATION: the clip() introduces a kink in drod/dt at the
        # boundary between lag and saturation regimes. Real actuators have
        # smoother transitions between drive-mode and free-fall (for
        # gravity scrams) but the discontinuity is small in magnitude and
        # BDF handles it fine with max_step=0.5.
        raw_rate = (rod_command_effective - rod_position) / p.tau
        rate = np.clip(raw_rate, -p.v_scram, p.v_normal)

        dstate = np.empty(self.state_size)
        dstate[0] = rate
        return dstate

    def outputs(self, state: np.ndarray, inputs: dict | None = None) -> dict:
        """Return rho_rod from rod position via linear worth.

        Parameters
        ----------
        state : np.ndarray, shape (1,)
            ``[rod_position]``.
        inputs : dict, optional
            Unused for this component (rod reactivity depends only on
            position). Accepted for API uniformity.

        Returns
        -------
        dict
            ``{"rho_rod": float [dimensionless]}``

        Notes
        -----
        SIMPLIFICATION (also called out in the RodParams docstring):
        linear rod worth. Real reactor rods have an S-shaped
        position-to-reactivity curve because absorbed neutrons are weighted
        by local flux (cosine-shaped along the core's vertical axis). Top
        and bottom of the core have low flux, so rod motion there does
        little; the middle does almost all the work. The L1 linear
        approximation is wrong in detail but right at the endpoints.
        """
        p = self.params
        rod_position = state[0]
        rod_reactivity = p.rho_total_worth * (rod_position - p.rod_position_critical)
        return {"rho_rod": rod_reactivity}

    def telemetry(self, state: np.ndarray, inputs: dict | None = None) -> dict:
        """Return a rich diagnostic dict for logging and visualization.

        Superset of ``outputs()``. Adds ``rod_position`` (the raw state
        value) and, when ``inputs`` is provided, echoes the operator
        commands plus the resolved ``rod_command_effective`` (= 0 if
        scram, else rod_command).

        Parameters
        ----------
        state : np.ndarray, shape (1,)
        inputs : dict, optional
            If provided (with the same keys as ``derivatives``), echoes
            ``rod_command``, ``scram``, and the resolved
            ``rod_command_effective``. If omitted, those keys are reported
            as None.

        Returns
        -------
        dict
            Keys: ``rod_position``, ``rho_rod``, ``rod_command``,
            ``scram``, ``rod_command_effective``.
        """
        p = self.params
        rod_position = state[0]
        rod_reactivity = p.rho_total_worth * (rod_position - p.rod_position_critical)

        out = {
            "rod_position": rod_position,
            "rho_rod": rod_reactivity,
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
