"""Two-phase pressurizer with heaters and spray (L1 fidelity).

The pressurizer is a vertical vessel attached to the primary loop hot
leg via a surge line. It contains a saturated mixture of liquid water
and steam: the liquid pool sits at the bottom with electrical heaters
submerged in it; spray nozzles at the top inject cooler water from
the cold leg to condense steam during overpressure.

It is the *primary system's* pressure controller — by adjusting how
much water is liquid vs. vapor, it sets the saturation pressure of the
whole primary loop. As primary water expands and contracts (with
temperature changes), volume surges into and out of the pressurizer
through the surge line.

At L1 we model:
- Two states (M_pzr, U_pzr) — total mass and internal energy of the
  saturated mixture in the vessel.
- Saturation closure via CoolProp's (D, U) → P inversion.
- Surge mass flow with direction-branched density (subcooled-liquid
  ρ on insurge, saturated-liquid ρ on outsurge).
- Heater = continuous Q_heater [W] input, no actuator dynamics.
- Spray = continuous m_dot_spray [kg/s] input, no valve dynamics.
- Sealed primary system (no PORV venting, no CVCS at M2).

Physics specification: see ``docs/superpowers/specs/2026-05-08-pressurizer-design.md``.

References
----------
Todreas, N. E. and Kazimi, M. S. *Nuclear Systems Vol. 1*, 2nd ed.,
CRC Press, 2012. (Open-system first law for fixed-volume control
volumes, §6.2 Eq. 6-13.)

Tong, L. S. and Weisman, J. *Thermal Analysis of Pressurized Water
Reactors*, 3rd ed., American Nuclear Society, 1996. (Pressurizer
design and pressure control, §6.4 / §7.3.)

Moran, M. J. and Shapiro, H. N. *Fundamentals of Engineering
Thermodynamics*. (Two-phase mixtures, lever rule on specific volume,
§3.6 Eq. 3.7.)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from fission_sim.physics import coolprop
from fission_sim.physics.primary_loop import LoopParams


@dataclass(frozen=True)
class PressurizerParams:
    """Parameters for the L1 two-phase pressurizer.

    Defaults represent a Westinghouse 4-loop centroid (~1800 ft³ vessel
    at 15.5 MPa primary pressure with half water level at design).

    Parameters
    ----------
    V_pzr : float
        Total internal vessel volume [m³]. Default 51.0 ≈ 1800 ft³ —
        Westinghouse 4-loop FSAR family typical.
    P_design : float
        Primary design pressure [Pa]. Default 1.55e7 = 15.5 MPa.
    level_design : float
        Fractional water level at design (V_l / V_pzr). Default 0.5
        gives equal margin for insurge expansion and outsurge contraction.
    loop_params : LoopParams
        Reference to the primary loop's params, needed by the pressurizer
        to compute surge mass flow from the loop's energy imbalance. Pass
        the same instance the loop uses; default ``LoopParams()`` covers
        the all-defaults plant.
    M_pzr_initial : float, optional
        Initial total mass [kg]. If None, derived in ``__post_init__`` so
        the design state has level=level_design and pressure=P_design.
    U_pzr_initial : float, optional
        Initial total internal energy [J]. If None, derived alongside
        M_pzr_initial.

    Notes
    -----
    Frozen dataclass; ``__post_init__`` uses ``object.__setattr__`` to
    fill in derived defaults — standard pattern for frozen + derived.
    """

    # Total internal volume. Source: NRC Westinghouse Standard Plant FSAR
    # §5.4.10 lists pressurizer vessel volumes in the 1700–1850 ft³ range
    # for 4-loop plants. 51 m³ ≈ 1800 ft³ is mid-family.
    V_pzr: float = 51.0  # [m³]

    # Design pressure — primary system setpoint. Westinghouse 4-loop
    # nominal is 2235–2250 psia ≈ 15.4–15.5 MPa.
    P_design: float = 1.55e7  # [Pa]

    # Design water level. Half-full gives equal capacity in either
    # direction; real plants run closer to 60 % at full power.
    level_design: float = 0.5  # [dimensionless, 0..1]

    # Composed loop params for surge computation. The pressurizer needs
    # M_hot, M_cold, c_p, V_loop, beta_T_primary to compute dT_avg/dt and
    # hence surge_volume_rate from (Q_core, Q_sg). The cleanest way to
    # share these between the two modules is composition.
    loop_params: LoopParams = field(default_factory=LoopParams)

    # Derived in __post_init__ from (P_design, level_design, V_pzr).
    M_pzr_initial: float | None = None  # [kg]
    U_pzr_initial: float | None = None  # [J]

    def __post_init__(self) -> None:
        """Derive ``M_pzr_initial`` and ``U_pzr_initial`` so the initial
        pressurizer state corresponds exactly to (P_design, level_design).

        Saturation closure inversion: at the design pressure, query
        CoolProp for the saturated-liquid and saturated-vapor densities
        and internal energies. Split the vessel into water and steam
        sub-volumes by ``level_design``. Sum masses and internal energies
        to get the totals.

        This makes the design point a true equilibrium when paired with
        the loop and controller in their corresponding design states.
        """
        if self.M_pzr_initial is None or self.U_pzr_initial is None:
            P = self.P_design
            rho_l = coolprop.sat_liquid_density(P=P)
            rho_v = coolprop.sat_vapor_density(P=P)
            u_l = coolprop.sat_liquid_internal_energy(P=P)
            u_v = coolprop.sat_vapor_internal_energy(P=P)
            V_l = self.level_design * self.V_pzr
            V_v = self.V_pzr - V_l
            M_l = V_l * rho_l
            M_v = V_v * rho_v
            object.__setattr__(self, "M_pzr_initial", M_l + M_v)
            object.__setattr__(self, "U_pzr_initial", M_l * u_l + M_v * u_v)


@dataclass(frozen=True)
class SaturationState:
    """Snapshot of the saturated mixture's intensive + decomposed state.

    Returned by ``saturation_state()``. Field meanings:

    Attributes
    ----------
    P : float
        Pressure [Pa].
    T_sat : float
        Saturation temperature [K].
    rho_l : float
        Saturated-liquid density [kg/m³].
    rho_v : float
        Saturated-vapor density [kg/m³].
    h_l : float
        Saturated-liquid specific enthalpy [J/kg].
    h_v : float
        Saturated-vapor specific enthalpy [J/kg].
    x : float
        Quality (vapor mass fraction) [dimensionless, 0..1].
    level : float
        Fractional water level (V_l / V_pzr) [dimensionless].
    M_l : float
        Liquid mass [kg].
    M_v : float
        Vapor mass [kg].
    """

    P: float
    T_sat: float
    rho_l: float
    rho_v: float
    h_l: float
    h_v: float
    x: float
    level: float
    M_l: float
    M_v: float


def saturation_state(M: float, U: float, V: float) -> SaturationState:
    """Compute the saturated mixture's intensive + decomposed state.

    Inverts CoolProp's saturation surface using the (D, U) pair to find
    pressure, then evaluates all saturation properties at that pressure.
    Decomposes the total mass into liquid and vapor sub-amounts via the
    lever rule on specific volume.

    Parameters
    ----------
    M : float
        Total mass in the vessel (water + steam) [kg].
    U : float
        Total internal energy in the vessel [J].
    V : float
        Vessel internal volume [m³] (constant for a rigid tank).

    Returns
    -------
    SaturationState
        Frozen dataclass of all derived quantities.

    Notes
    -----
    Equations:
        ρ_avg = M / V                                              # average density
        u_avg = U / M                                              # specific internal energy
        P     = CoolProp(D=ρ_avg, U=u_avg)                         # saturation P from (D,U)
        T_sat, ρ_l, ρ_v, h_l, h_v from CoolProp at (P, Q=0|1)      # saturation curve

    Lever rule on specific volume v = 1/ρ (Moran & Shapiro §3.6 Eq. 3.7;
    algebraically equivalent to the standard form on quality):
        v_avg = (1 − x) · v_l + x · v_v
        x = (v_avg − v_l) / (v_v − v_l)

    Then:
        M_l = (1 − x) · M
        M_v = x · M
        V_l = M_l / ρ_l
        level = V_l / V
    """
    rho_avg = M / V
    u_avg = U / M

    # Invert saturation surface: pressure such that the mixture at this
    # density and specific internal energy lies on the saturation dome.
    P = coolprop.P_from_DU(D=rho_avg, U=u_avg)

    T_sat = coolprop.T_sat(P=P)
    rho_l = coolprop.sat_liquid_density(P=P)
    rho_v = coolprop.sat_vapor_density(P=P)
    h_l = coolprop.sat_liquid_enthalpy(P=P)
    h_v = coolprop.sat_vapor_enthalpy(P=P)

    # Lever rule on specific volume v = 1/ρ. Algebraically identical to the
    # standard quality decomposition; this form falls out cleanly because
    # we already have densities. Moran & Shapiro §3.6 Eq. 3.7.
    x = (1.0 / rho_avg - 1.0 / rho_l) / (1.0 / rho_v - 1.0 / rho_l)

    M_l = (1.0 - x) * M
    M_v = x * M
    V_l = M_l / rho_l

    return SaturationState(
        P=P,
        T_sat=T_sat,
        rho_l=rho_l,
        rho_v=rho_v,
        h_l=h_l,
        h_v=h_v,
        x=x,
        level=V_l / V,
        M_l=M_l,
        M_v=M_v,
    )


class Pressurizer:
    """Two-phase pressurizer (L1 fidelity).

    The class owns its parameters and equations. State (the total
    pressurizer mass and internal energy) lives in a numpy array passed
    in by the caller. Every method that needs current-state numbers takes
    them as an argument.

    Ports in (passed to ``derivatives()`` / ``outputs(inputs=)``):
        power_thermal : float [W]
            Heat from the core (used to compute dT_avg/dt and hence
            surge_volume_rate inside the pressurizer).
        Q_sg : float [W]
            Heat removed by the steam generator (also for dT_avg/dt).
        T_hotleg : float [K]
            Hot-leg temperature — sets ρ and h of insurge water.
        T_coldleg : float [K]
            Cold-leg temperature — sets h of spray water.
        Q_heater : float [W]
            Heater electrical power demand (≥ 0).
        m_dot_spray : float [kg/s]
            Spray mass-flow demand (≥ 0).

    Ports out (returned by ``outputs(state, inputs=)``):
        P : float [Pa]
            Pressurizer pressure (= primary system pressure).
        level : float [dimensionless]
            Fractional water level, V_l / V_pzr.
        T_sat : float [K]
            Saturation temperature at current P.
        m_dot_surge : float [kg/s]
            Mass surge rate (positive = insurge into pressurizer).
        subcooling_margin : float [K]
            T_sat − T_hotleg. Operator-facing primary indicator.

    State vector (length ``state_size`` = 2, names in ``state_labels``):
        index 0 : M_pzr — total mass in vessel [kg]
        index 1 : U_pzr — total internal energy in vessel [J]
    """

    state_size: int = 2
    state_labels: tuple[str, ...] = ("M_pzr", "U_pzr")
    input_ports: tuple[str, ...] = (
        "power_thermal",
        "Q_sg",
        "T_hotleg",
        "T_coldleg",
        "Q_heater",
        "m_dot_spray",
    )
    output_ports: tuple[str, ...] = (
        "P",
        "level",
        "T_sat",
        "m_dot_surge",
        "subcooling_margin",
    )

    def __init__(self, params: PressurizerParams) -> None:
        self.params = params

    def initial_state(self) -> np.ndarray:
        """Return ``[M_pzr_initial, U_pzr_initial]``.

        Both values are derived from (P_design, level_design, V_pzr) in
        ``PressurizerParams.__post_init__``; this method just packages
        them into a numpy array of the right shape.
        """
        p = self.params
        return np.array([p.M_pzr_initial, p.U_pzr_initial])
