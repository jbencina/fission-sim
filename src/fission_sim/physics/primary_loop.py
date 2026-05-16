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

Public references:

- Claire Yu Yan, *Introduction to Engineering Thermodynamics*, §5.2,
  mass and energy conservation equations for a control volume:
  https://pressbooks.bccampus.ca/thermo1/chapter/5-2-steady-flow-and-transient-flow/
- DOE Fundamentals Handbook, *Thermodynamics, Heat Transfer, and Fluid
  Flow*, Vol. 2, heat transfer terminology and overall heat-transfer
  coefficient:
  https://www.steamtablesonline.com/pdf/Thermodynamics-Volume2.pdf
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from fission_sim.physics import coolprop


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
        Lumped water-equivalent thermal inertia on the hot-leg side [kg].
    M_cold : float
        Lumped water-equivalent thermal inertia on the cold-leg side [kg].
    Q_design : float
        Design heat flow through the loop [W] (= core's P_design).
    T_avg_ref : float
        Design average primary temperature [K]. Should match the core's
        ``T_cool_ref`` so that the moderator-feedback term is zero at the
        coupled design point.
    P_ref : float
        Reference primary pressure [Pa]. Used only to derive the initial
        physical loop inventory from ``V_loop`` and CoolProp density.
    T_hot_ref : float, optional
        Hot-leg reference temperature [K]. If None, derived in __post_init__
        as ``T_avg_ref + ΔT_design / 2`` where
        ``ΔT_design = Q_design / (m_dot * c_p)``.
    T_cold_ref : float, optional
        Cold-leg reference temperature [K]. If None, derived as
        ``T_avg_ref - ΔT_design / 2``.
    V_loop : float
        Total primary loop liquid volume excluding the pressurizer [m³].
        Used by the pressurizer to compute surge mass flow from volumetric
        thermal expansion.
    beta_T_primary : float
        Volumetric thermal expansion coefficient of primary water at the
        design point [1/K]. Frozen at 583 K, 15.5 MPa (3.3e-3 /K,
        verified via CoolProp — Task A1).
    M_loop_initial : float, optional
        Initial liquid mass in the loop (excluding pressurizer) [kg]. If
        None, derived in __post_init__ as ``V_loop * rho(P_ref, T_avg_ref)``.

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

    # Lumped water-equivalent thermal inertia on each leg. These are not the
    # physical liquid inventory; M_loop_initial below tracks that separately.
    # SIMPLIFICATION: pipe metal, vessel metal, and coolant thermal inertia are
    # collapsed into water-equivalent masses for the two energy balances.
    M_hot: float = 1.5e4  # [kg]
    M_cold: float = 1.5e4  # [kg]

    # Design heat flow. Match the core's P_design.
    Q_design: float = 3.0e9  # [W]

    # Design average temperature. Match the core's T_cool_ref so moderator
    # feedback is zero at the coupled design point. Westinghouse 4-loop full
    # power T_avg is typically 583-588 K (310-315 °C); 583 K is mid-range.
    T_avg_ref: float = 583.0  # [K] (~310 °C)

    # Reference pressure for deriving the initial physical loop liquid mass
    # from CoolProp density. Nominal Westinghouse 4-loop primary pressure.
    P_ref: float = 1.55e7  # [Pa]

    # Reference leg temperatures. None means "derive from energy balance".
    T_hot_ref: float | None = None  # [K]
    T_cold_ref: float | None = None  # [K]

    # --- M2 additions: loop volume and thermal expansion for surge ---

    # Total primary loop water volume EXCLUDING pressurizer. Used to
    # compute volumetric expansion under temperature change. The
    # pressurizer reads this (via composed LoopParams) for its own
    # surge calculation.
    #
    # SIMPLIFICATION: this is a flat constant; the real value would
    # come from CAD of the loop-piping + RPV downcomer + plenum
    # volumes. Westinghouse 4-loop primary inventory is ~250–270 m³
    # total, of which ~50 m³ is the pressurizer and ~30 m³ is each of
    # the four SG primary sides. Subtracting gives ~80–100 m³ for
    # piping + RPV. We use 175 m³ here as a conservative L1 estimate;
    # implementer should verify against the W Tech Systems Manual
    # §3.1 before publishing benchmark results.
    V_loop: float = 175.0  # [m³]

    # Volumetric thermal expansion coefficient β_T = (1/V)·(∂V/∂T)_P.
    # Frozen at the design point: 583 K, 15.5 MPa. Verified via CoolProp
    # in Task A1: actual value 3.256e-3 /K, rounded to 3.3e-3.
    #
    # SIMPLIFICATION: real β_T varies ~50 % across the 568–598 K
    # operating range (~2.0e-3 to ~3.0e-3 /K, sometimes higher near
    # 583 K). Frozen-at-design under-predicts surge magnitude during
    # cooldowns (where T is below T_design and β is smaller) and
    # over-predicts during heatups. L2 reads β from CoolProp every step.
    beta_T_primary: float = 3.3e-3  # [1/K] — verified via CoolProp at design

    # Initial liquid mass tracked for mass conservation across the sealed
    # primary system (loop + pressurizer). If None, derive from physical loop
    # volume and CoolProp density at reference primary conditions.
    M_loop_initial: float | None = None  # [kg]

    def __post_init__(self) -> None:
        """Derive ``T_hot_ref``, ``T_cold_ref``, and ``M_loop_initial``.

        Temperatures: at the design point both temperature derivatives
        are zero, which means ``Q_core = ṁ · c_p · (T_hot − T_cold)``.
        Solving for ΔT and centering on ``T_avg_ref``:

            ΔT_design  = Q_design / (m_dot * c_p)
            T_hot_ref  = T_avg_ref + ΔT_design / 2
            T_cold_ref = T_avg_ref − ΔT_design / 2

        Mass: at the design point with no surge or spray, the loop
        liquid inventory equals ``V_loop * rho(P_ref, T_avg_ref)``.
        """
        if self.T_hot_ref is None or self.T_cold_ref is None:
            delta_T = self.Q_design / (self.m_dot * self.c_p)
            T_hot = self.T_avg_ref + delta_T / 2
            T_cold = self.T_avg_ref - delta_T / 2
            # Frozen dataclass; bypass the freeze to set the derived defaults.
            object.__setattr__(self, "T_hot_ref", T_hot)
            object.__setattr__(self, "T_cold_ref", T_cold)
        if self.M_loop_initial is None:
            rho_ref = coolprop.density_PT(P=self.P_ref, T=self.T_avg_ref)
            object.__setattr__(self, "M_loop_initial", self.V_loop * rho_ref)


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
        m_dot_spray : float [kg/s]
            Mass flow rate of cold-leg water sprayed into the pressurizer.
            Positive means water leaving the loop (from controller).
        P_primary : float [Pa]
            Primary system pressure (= pressurizer pressure, a state-derived
            output available before any computed module runs). Used by the loop
            to compute m_dot_surge internally via the shared surge helper,
            replacing the old wired ``m_dot_surge`` port that always carried
            0.0 due to the pressurizer's state-derived classification.

    Ports out (returned by ``outputs()``):
        T_hot : float [K]
            Hot-leg temperature (water leaving the core).
        T_cold : float [K]
            Cold-leg temperature (water returning to the core).
        T_avg : float [K]
            Average primary temperature, ``(T_hot + T_cold) / 2``.
        T_cool : float [K]
            What the core sees as coolant temperature (= ``T_avg`` at L1).

    State vector (length ``state_size`` = 3, names in ``state_labels``):
        index 0 : T_hot   — hot-leg temperature [K]
        index 1 : T_cold  — cold-leg temperature [K]
        index 2 : M_loop  — liquid mass in the loop (excluding pressurizer) [kg]

    Notes
    -----
    The hot/cold split tracks the temperature difference (~32 K at design)
    that, multiplied by mass flow and specific heat, equals the heat being
    moved through the loop: ``Q = ṁ · c_p · (T_hot − T_cold)``. This is the
    energy-balance closure that becomes M1 success criterion #4 once the loop
    is coupled to the core and SG.
    """

    state_size: int = 3
    state_labels: tuple[str, ...] = ("T_hot", "T_cold", "M_loop")
    input_ports: tuple[str, ...] = ("power_thermal", "Q_sg", "m_dot_spray", "P_primary")
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

        At design, both temperature derivatives are zero by construction
        and the loop's liquid inventory equals ``M_hot + M_cold``. The
        third state ``M_loop`` is the dynamic inventory that drains
        when surge or spray pushes water into the pressurizer.

        Returns
        -------
        np.ndarray, shape (3,)
            ``[T_hot_ref, T_cold_ref, M_loop_initial]``.
        """
        p = self.params
        return np.array([p.T_hot_ref, p.T_cold_ref, p.M_loop_initial])

    def derivatives(self, state: np.ndarray, inputs: dict) -> np.ndarray:
        """Two-leg energy balance + liquid inventory conservation.

        State and energy-balance equations unchanged from M1. The third
        equation closes the conservation loop with the pressurizer:

            dM_loop/dt = − ṁ_surge − ṁ_spray

        The negative signs reflect that mass leaving the loop into the
        pressurizer reduces the loop's inventory.

        ``ṁ_surge`` is computed *internally* by this method using the
        shared helper ``surge.compute_m_dot_surge``, identical to the
        computation in ``Pressurizer.derivatives``. This is the key to
        mass conservation: both modules apply the same surge flow to their
        respective state derivatives, so ``d/dt(M_loop + M_pzr) = 0`` to
        solver tolerance. The old wired ``m_dot_surge`` port was replaced
        with ``P_primary`` (the pressurizer pressure, a state-derived
        output available early in the engine's eval pass) which is the only
        additional input the surge helper needs beyond quantities already
        available (power_thermal, Q_sg, T_hot from state).

        ``ṁ_spray`` is still an input wired directly from the controller.

        SIMPLIFICATION: ``M_hot`` and ``M_cold`` parameters in the
        energy balance represent **lumped pipe-metal-plus-water
        effective thermal inertia** in water-equivalent units, NOT the
        instantaneous water mass. They stay constant. The few-hundred-kg
        liquid-inventory shifts during a transient do not move them
        appreciably — pipe metal dominates the thermal time constant.
        Promoting them to a single coupled state would be a clean L2
        step.

        Parameters
        ----------
        state : np.ndarray, shape (3,)
            ``[T_hot, T_cold, M_loop]``.
        inputs : dict
            See ``input_ports`` for required keys: ``power_thermal``,
            ``Q_sg``, ``m_dot_spray``, ``P_primary``.

        Returns
        -------
        np.ndarray, shape (3,)
            ``[dT_hot/dt, dT_cold/dt, dM_loop/dt]``.

        Notes
        -----
        Equations (.docs/design.md §5.2, Todreas eq 6.18 for energy,
        and public control-volume balances from Yan §5.2):

            M_hot  · c_p · dT_hot/dt  = Q_core − ṁ · c_p · (T_hot − T_cold)
            M_cold · c_p · dT_cold/dt = ṁ · c_p · (T_hot − T_cold) − Q_sg
            dM_loop/dt                = − ṁ_surge − ṁ_spray

        where ṁ_surge is derived from (P_primary, power_thermal, Q_sg,
        T_hot) via ``surge.compute_m_dot_surge``.
        """
        # Local import to avoid circular import: surge.py imports LoopParams
        # from this module. The import is cached by Python after the first call.
        from fission_sim.physics import coolprop
        from fission_sim.physics.surge import compute_m_dot_surge

        p = self.params

        # --- decode the state slice into named locals ---
        T_hot = state[0]
        T_cold = state[1]
        # M_loop = state[2]  # not used in energy equations; ṁ_surge + ṁ_spray determine d/dt directly

        # --- decode inputs ---
        power_thermal = inputs["power_thermal"]  # heat from core [W]
        Q_sg = inputs["Q_sg"]
        m_dot_spray = inputs["m_dot_spray"]  # cold-leg spray to pressurizer [kg/s]
        P_primary = inputs["P_primary"]  # pressurizer pressure (state-derived) [Pa]

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

        # --- compute surge mass flow using the shared helper ---
        # The pressurizer's derivatives() calls the same function, ensuring
        # d/dt(M_loop + M_pzr) = -ṁ_surge - ṁ_spray + ṁ_surge + ṁ_spray = 0
        # i.e. the sealed-system invariant holds to solver tolerance.
        rho_l_sat = coolprop.sat_liquid_density(P=P_primary)
        m_dot_surge = compute_m_dot_surge(
            power_thermal=power_thermal,
            Q_sg=Q_sg,
            T_hotleg=T_hot,
            P_primary=P_primary,
            rho_l_sat=rho_l_sat,
            loop_params=p,
        )

        # --- mass conservation across the sealed primary system ---
        # Spec §3.3. Positive ṁ_surge means mass flowing INTO the pressurizer
        # (OUT of the loop), so dM_loop/dt is negative for positive surge.
        dM_loop_dt = -m_dot_surge - m_dot_spray

        # --- assemble derivative vector matching state layout ---
        dstate = np.empty(self.state_size)
        dstate[0] = dT_hot_dt
        dstate[1] = dT_cold_dt
        dstate[2] = dM_loop_dt
        return dstate

    def outputs(self, state: np.ndarray, inputs: dict | None = None) -> dict:
        """Return the values consumed by downstream components.

        Parameters
        ----------
        state : np.ndarray, shape (3,)
            ``[T_hot, T_cold, M_loop]`` in K and kg.
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
        state : np.ndarray, shape (3,)
        inputs : dict, optional
            If provided (with the same keys as ``derivatives``),
            ``power_thermal`` and ``Q_sg`` are echoed. If omitted, those keys
            are reported as None; ``Q_flow`` and ``M_loop`` are always
            computable from state alone.

        Returns
        -------
        dict
            Keys: ``T_hot``, ``T_cold``, ``T_avg``, ``T_cool``, ``delta_T``,
            ``Tref``, ``power_thermal``, ``Q_sg``, ``Q_flow``, ``M_loop``.
            ``Tref`` is the T_avg setpoint for the current load — at L1/M1
            (no turbine) it is constant ``T_avg_ref``; M3 will make it a
            function of turbine demand. Real-plant operators watch
            ``T_avg − Tref`` as the primary control signal. ``M_loop`` is the
            current liquid inventory (loop only, excluding pressurizer) in kg.
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
        # M_loop: current liquid mass in the loop (third state, always present).
        out["M_loop"] = state[2]

        if inputs is not None:
            out["power_thermal"] = inputs.get("power_thermal")
            out["Q_sg"] = inputs.get("Q_sg")
        else:
            out["power_thermal"] = None
            out["Q_sg"] = None
        return out
