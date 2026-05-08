"""Lumped primary loop (L1 fidelity).

The water circuit that carries heat from the reactor core to the steam generator.
Held at high pressure (~155 bar) so it stays liquid at 290–325°C. At L1 the loop
is two well-mixed lumps: a hot leg (water exiting the core) and a cold leg (water
returning to the core). Constant flow, constant pressure, single-phase liquid.

Physics specification: see ``.docs/design.md`` §5.2.

References
----------
Lamarsh, J. R. and Baratta, A. J. *Introduction to Nuclear Engineering*, 3rd ed.,
Prentice Hall, 2001. (PWR primary loop, Ch. 4.)

Todreas, N. E. and Kazimi, M. S. *Nuclear Systems Vol. 1*, 2nd ed., CRC Press,
2012. (Energy balance, Ch. 6.)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class LoopParams:
    """Parameters for the L1 lumped primary loop.

    All defaults represent a generic large 4-loop PWR (~3000 MWth). The
    reference temperatures (``T_hot_ref``, ``T_cold_ref``) are derived from
    steady-state self-consistency unless explicitly supplied.

    Parameters
    ----------
    m_dot : float
        Total mass flow rate [kg/s] (single equivalent loop).
    c_p : float
        Specific heat of primary water at average conditions [J/(kg·K)].
    M_hot : float
        Lumped water mass on the hot-leg side [kg].
    M_cold : float
        Lumped water mass on the cold-leg side [kg].
    Q_design : float
        Design heat flow through the loop [W] (= core's P_design).
    T_avg_ref : float
        Design average primary temperature [K]. Should match the core's
        ``T_cool_ref`` so that the moderator-feedback term is zero at the
        coupled design point.
    T_hot_ref : float, optional
        Hot-leg reference temperature [K]. If None, derived in __post_init__
        as ``T_avg_ref + ΔT_design / 2`` where
        ``ΔT_design = Q_design / (m_dot * c_p)``.
    T_cold_ref : float, optional
        Cold-leg reference temperature [K]. If None, derived as
        ``T_avg_ref - ΔT_design / 2``.

    Notes
    -----
    The class is frozen, but ``__post_init__`` uses ``object.__setattr__`` to
    fill in the derived ``T_hot_ref`` and ``T_cold_ref`` defaults. Standard
    pattern for frozen dataclasses with derived fields.
    """

    # SIMPLIFICATION: single equivalent loop. Real PWRs have 2-4 parallel loops;
    # we model their combined behavior as one lumped circuit.

    # Mass flow rate (combined, single equivalent loop). Westinghouse 4-loop
    # full-power flow is ~140 Mlb/hr ≈ 18000-19000 kg/s total (4 × ~4500-4800
    # kg/s per loop). 18500 is mid-range; gives loop ΔT ≈ 29.5 K at design.
    m_dot: float = 1.85e4  # [kg/s]

    # Specific heat. Source: water at ~300°C and 15.5 MPa, IAPWS-97 (would come
    # from CoolProp at L2). The high value reflects the high-pressure liquid
    # condition.
    c_p: float = 5500.0  # [J/(kg·K)]

    # Lumped water masses on each leg. Order of magnitude estimate for a 4-loop
    # PWR primary inventory (~270 m³ of water at ~720 kg/m³ ≈ 200000 kg total,
    # split roughly evenly between hot side and cold side legs).
    M_hot: float = 1.5e4  # [kg]
    M_cold: float = 1.5e4  # [kg]

    # Design heat flow. Match the core's P_design.
    Q_design: float = 3.0e9  # [W]

    # Design average temperature. Match the core's T_cool_ref so moderator
    # feedback is zero at the coupled design point. Westinghouse 4-loop full
    # power T_avg is typically 583-588 K (310-315 °C); 583 K is mid-range.
    T_avg_ref: float = 583.0  # [K] (~310 °C)

    # Reference leg temperatures. None means "derive from energy balance".
    T_hot_ref: float | None = None  # [K]
    T_cold_ref: float | None = None  # [K]

    def __post_init__(self) -> None:
        """Derive ``T_hot_ref`` and ``T_cold_ref`` from steady-state self-consistency.

        At the design point both temperature derivatives are zero, which means
        ``Q_core = ṁ · c_p · (T_hot − T_cold)``. Solving for ΔT and centering
        on ``T_avg_ref`` gives:

            ΔT_design  = Q_design / (m_dot * c_p)
            T_hot_ref  = T_avg_ref + ΔT_design / 2
            T_cold_ref = T_avg_ref − ΔT_design / 2

        With defaults (Q=3 GW, ṁ=17000 kg/s, c_p=5500 J/(kg·K)), ΔT ≈ 32 K
        giving ``T_hot_ref ≈ 596 K`` (~323 °C) and ``T_cold_ref ≈ 564 K``
        (~291 °C) — the textbook PWR temperatures.
        """
        if self.T_hot_ref is None or self.T_cold_ref is None:
            delta_T = self.Q_design / (self.m_dot * self.c_p)
            T_hot = self.T_avg_ref + delta_T / 2
            T_cold = self.T_avg_ref - delta_T / 2
            # Frozen dataclass; bypass the freeze to set the derived defaults.
            object.__setattr__(self, "T_hot_ref", T_hot)
            object.__setattr__(self, "T_cold_ref", T_cold)


class PrimaryLoop:
    """Lumped primary loop (L1 fidelity).

    The class owns its parameters and equations. It does NOT own time-evolving
    state. State lives in a numpy array passed in by the caller (a driver
    script for now, the simulation engine eventually). Every method that needs
    current-state numbers takes them as an argument.

    Ports in (passed to ``derivatives()`` via the ``inputs`` dict):
        power_thermal : float [W]
            Heat added to the loop by the reactor core (= core's
            ``power_thermal`` output; same name used to enable auto-wiring).
        Q_sg : float [W]
            Heat removed from the loop by the steam generator.

    Ports out (returned by ``outputs()``):
        T_hot : float [K]
            Hot-leg temperature (water leaving the core).
        T_cold : float [K]
            Cold-leg temperature (water returning to the core).
        T_avg : float [K]
            Average primary temperature, ``(T_hot + T_cold) / 2``.
        T_cool : float [K]
            What the core sees as coolant temperature (= ``T_avg`` at L1).

    State vector (length ``state_size`` = 2, names in ``state_labels``):
        index 0 : T_hot  — hot-leg temperature [K]
        index 1 : T_cold — cold-leg temperature [K]

    Notes
    -----
    The hot/cold split tracks the temperature difference (~32 K at design)
    that, multiplied by mass flow and specific heat, equals the heat being
    moved through the loop: ``Q = ṁ · c_p · (T_hot − T_cold)``. This is the
    energy-balance closure that becomes M1 success criterion #4 once the loop
    is coupled to the core and SG.
    """

    state_size: int = 2
    state_labels: tuple[str, ...] = ("T_hot", "T_cold")
    input_ports: tuple[str, ...] = ("power_thermal", "Q_sg")
    output_ports: tuple[str, ...] = ("T_hot", "T_cold", "T_avg", "T_cool")

    def __init__(self, params: LoopParams) -> None:
        """Construct a loop with the given parameters.

        Parameters
        ----------
        params : LoopParams
            Frozen parameter set. Held as ``self.params`` for the lifetime of
            the object.
        """
        self.params = params

    def initial_state(self) -> np.ndarray:
        """Return the design-point steady-state vector.

        At the design point both temperature derivatives are zero by
        construction (``LoopParams.__post_init__`` derives ``T_hot_ref`` and
        ``T_cold_ref`` to make this true).

        Returns
        -------
        np.ndarray, shape (2,)
            ``[T_hot_ref, T_cold_ref]`` in K.
        """
        p = self.params
        return np.array([p.T_hot_ref, p.T_cold_ref])

    def derivatives(self, state: np.ndarray, inputs: dict) -> np.ndarray:
        """Compute dstate/dt for the two-leg primary loop energy balance.

        Pure function of ``state`` and ``inputs`` — no per-step state on
        ``self``. The adaptive ODE solver may call this function speculatively
        many times per step with hypothetical states it later discards.

        Parameters
        ----------
        state : np.ndarray, shape (2,)
            ``[T_hot, T_cold]`` in K.
        inputs : dict
            Required keys:

            - ``power_thermal`` : float [W] — heat from the core (matches the
              core's ``power_thermal`` output port name for auto-wiring).
            - ``Q_sg`` : float [W] — heat removed by the SG.

        Returns
        -------
        np.ndarray, shape (2,)
            ``[dT_hot/dt, dT_cold/dt]`` in K/s.

        Notes
        -----
        Equations (see ``.docs/design.md`` §5.2 and Todreas eq 6.18):

            M_hot  · c_p · dT_hot/dt  = Q_core − ṁ · c_p · (T_hot − T_cold)
            M_cold · c_p · dT_cold/dt = ṁ · c_p · (T_hot − T_cold) − Q_sg

        Physically:

        - The hot leg gains heat from the core (Q_core) and loses heat by
          mixing with cooler return water at rate Q_flow = ṁ · c_p · ΔT.
        - The cold leg gains Q_flow from the hot leg and loses Q_sg to the SG.
        - Mass flow ṁ is constant at L1 (no pump dynamics, no coastdown).
        """
        p = self.params

        # --- decode the state slice into named locals ---
        T_hot = state[0]
        T_cold = state[1]

        # --- decode inputs ---
        power_thermal = inputs["power_thermal"]  # heat from core [W]
        Q_sg = inputs["Q_sg"]

        # --- heat carried from hot leg to cold leg by mass flow ---
        # ṁ · c_p · ΔT, dimensions [W]. This is the rate at which warm water
        # flowing out of the hot leg into the cold leg deposits energy.
        Q_flow = p.m_dot * p.c_p * (T_hot - T_cold)

        # --- hot-leg energy balance ---
        # Equation: M_hot · c_p · dT_hot/dt = Q_core − ṁ · c_p · (T_hot − T_cold)
        # where Q_core is the physics symbol for heat from the reactor core
        # (carried in the port named power_thermal).
        # SIMPLIFICATION: lumped (well-mixed) hot leg. Real piping has plug
        # flow with transport delay (water takes seconds to traverse the legs).
        dT_hot_dt = (power_thermal - Q_flow) / (p.M_hot * p.c_p)

        # --- cold-leg energy balance ---
        dT_cold_dt = (Q_flow - Q_sg) / (p.M_cold * p.c_p)

        # --- assemble derivative vector matching state layout ---
        dstate = np.empty(self.state_size)
        dstate[0] = dT_hot_dt
        dstate[1] = dT_cold_dt
        return dstate

    def outputs(self, state: np.ndarray, inputs: dict | None = None) -> dict:
        """Return the values consumed by downstream components.

        Parameters
        ----------
        state : np.ndarray, shape (2,)
            ``[T_hot, T_cold]`` in K.
        inputs : dict, optional
            Unused for this component (loop outputs depend only on state).
            Accepted for API uniformity.

        Returns
        -------
        dict
            ``{"T_hot": [K], "T_cold": [K], "T_avg": [K], "T_cool": [K]}``.
            ``T_cool`` is what the core sees; equals ``T_avg`` at L1.
        """
        T_hot = state[0]
        T_cold = state[1]
        T_avg = (T_hot + T_cold) / 2
        return {
            "T_hot": T_hot,
            "T_cold": T_cold,
            "T_avg": T_avg,
            # SIMPLIFICATION: T_cool seen by the core equals the loop's T_avg.
            # In reality there's a spatial profile from cold leg → core inlet
            # → core outlet → hot leg; we collapse that to a single number.
            "T_cool": T_avg,
        }

    def telemetry(self, state: np.ndarray, inputs: dict | None = None) -> dict:
        """Return a rich diagnostic dict for logging and visualization.

        Superset of ``outputs()``. Adds ΔT (the temperature difference between
        legs) and Q_flow (the heat carried between legs by mass flow). When
        ``inputs`` is provided, also echoes ``power_thermal`` and ``Q_sg``.

        Parameters
        ----------
        state : np.ndarray, shape (2,)
        inputs : dict, optional
            If provided (with the same keys as ``derivatives``),
            ``power_thermal`` and ``Q_sg`` are echoed. If omitted, those keys
            are reported as None; ``Q_flow`` is always computable from state
            alone.

        Returns
        -------
        dict
            Keys: ``T_hot``, ``T_cold``, ``T_avg``, ``T_cool``, ``delta_T``,
            ``Tref``, ``power_thermal``, ``Q_sg``, ``Q_flow``. ``Tref`` is the
            T_avg setpoint for the current load — at L1/M1 (no turbine) it
            is constant ``T_avg_ref``; M3 will make it a function of turbine
            demand. Real-plant operators watch ``T_avg − Tref`` as the
            primary control signal.
        """
        p = self.params
        T_hot = state[0]
        T_cold = state[1]
        delta_T = T_hot - T_cold

        out = self.outputs(state)
        out["delta_T"] = delta_T
        # Q_flow depends only on state; always computable.
        out["Q_flow"] = p.m_dot * p.c_p * delta_T
        # Tref: design-point T_avg setpoint. Constant at M1 (no turbine
        # load). Exposed now as a placeholder so future UI / control work
        # can already key off it; M3 turbine integration makes it dynamic.
        out["Tref"] = p.T_avg_ref

        if inputs is not None:
            out["power_thermal"] = inputs.get("power_thermal")
            out["Q_sg"] = inputs.get("Q_sg")
        else:
            out["power_thermal"] = None
            out["Q_sg"] = None
        return out
