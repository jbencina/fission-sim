"""Steam-generator shell side: saturated water and steam in one L1 volume.

This module represents the *secondary* (shell) side of the plant's four
steam generators as one lumped, rigid volume ``V_sec`` containing boiling
water under its own saturated steam. Heat ``Q_sg`` arrives from the primary
tubes, feedwater enters as warm compressed liquid, and steam leaves through
the turbine and steam-dump paths. The thermodynamic closure is intentionally
the same saturated-mixture-in-a-tank picture used by the pressurizer; only the
boundary flows differ.

Fidelity level
--------------
L1. This is a control-volume bookkeeping model for mass, internal energy,
saturation pressure, saturation temperature, and collapsed liquid level.

# SIMPLIFICATION: no tube-metal heat capacity is modeled; heat deposited by
``SteamGenerator`` appears instantly in the shell water.
# SIMPLIFICATION: no recirculation ratio, riser/downcomer split, separator
carryover, or void swell is modeled. ``level_sg`` is the collapsed liquid
volume fraction ``V_l / V_sec`` rather than a real narrow-range indicated
level.
# SIMPLIFICATION: feedwater enters at one constant temperature ``T_fw`` and
the tube bundle's heat transfer coefficient is provided by the separate
constant-``UA`` ``SteamGenerator`` component.

References
----------
Yan, J. *Introduction to Engineering Thermodynamics*, §5.2.2 "Mass
Conservation Equations in a Control Volume" and §5.2.3 "Energy Conservation
Equations in a Control Volume". Transient open-system balance forms:
https://pressbooks.bccampus.ca/thermo1/chapter/5-2-steady-flow-and-transient-flow/

DOE Fundamentals Handbook, *Thermodynamics, Heat Transfer, and Fluid Flow*,
Vol. 1, DOE-HDBK-1012/1-92. Saturation properties, quality, and two-phase
mixture relationships, including HT-01 p. 34 Eq. (1-20) for quality and
p. 54 for accumulation:
https://www.steamtablesonline.com/pdf/Thermodynamics-Volume1.pdf

Public PWR system reference:

- U.S. NRC Technical Training Center, *Westinghouse Technology Systems
  Manual*, §7.1 "Main and Auxiliary Steam Systems", §7.1.3.3 p. 7.1-5 and
  §7.1.3.4 p. 7.1-6 (PDF pp. 7-8), Rev. 0101, for representative steam-line
  relief paths:
  https://www.nrc.gov/docs/ML1122/ML11223A244.pdf
- U.S. NRC Technical Training Center, *Westinghouse Technology Systems
  Manual*, §11.1 "Steam Generator Water Level Control System", pp. 11.1-2-3
  (PDF pp. 4-5) and Fig. 11.1-2, Rev. 0706, for the real narrow-range
  level/shrink-swell context that this collapsed-level model omits:
  https://www.nrc.gov/docs/ML1122/ML11223A293.pdf
- CoolProp / IAPWS references for water and steam property evaluations:
  https://coolprop.org/fluid_properties/IF97.html
  https://iapws.org/documents/release/IF97-Rev
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import brentq

from fission_sim.physics import coolprop
from fission_sim.physics.domain import LEVEL_SG_MIN
from fission_sim.physics.pressurizer import saturation_state

# Numerical flow deadband for display-only time estimates. 1e-6 kg/s is far
# below any modeled SG transient flow and prevents division by a near-zero
# "drain rate" from being presented as a meaningful forecast.
_FLOW_EPS: float = 1.0e-6  # [kg/s]


def _root_bracket_contains_zero(f_lower: float, f_upper: float) -> bool:
    """Return whether a scalar root is bracketed by two residual values.

    Parameters
    ----------
    f_lower : float
        Residual at the lower internal-energy trial value [Pa].
    f_upper : float
        Residual at the upper internal-energy trial value [Pa].

    Returns
    -------
    bool
        True when the residuals have opposite signs or either endpoint is
        already a root.
    """
    return f_lower == 0.0 or f_upper == 0.0 or (f_lower < 0.0 < f_upper) or (f_upper < 0.0 < f_lower)


def _solve_u_for_pressure(M_sec: float, U_closed_form: float, V_sec: float, P_ref: float) -> float:
    """Solve the shell internal energy that inverts to the requested pressure.

    Parameters
    ----------
    M_sec : float
        Total shell-side water mass [kg].
    U_closed_form : float
        IF97 closed-form mixture internal energy [J], used as the center of
        the bracket.
    V_sec : float
        Shell-side control volume [m³].
    P_ref : float
        Target saturation pressure [Pa].

    Returns
    -------
    float
        Total internal energy [J] such that
        ``saturation_state(M_sec, U, V_sec).P`` is ``P_ref`` to well below
        the pressure tolerances used by the design-point tests.

    Raises
    ------
    ValueError
        If a root cannot be bracketed around ``U_closed_form``.

    Notes
    -----
    The residual is:

        f(U) = P_from_DU(M_sec / V_sec, U / M_sec) − P_ref

    ``P_from_DU`` uses CoolProp's Helmholtz backend ("HEOS") because IF97
    does not implement the ``(D, U)`` input pair. The saturated densities and
    internal energies used for the closed-form state use IF97. The two
    backends are both accurate steam-water property models, but their
    numerical surfaces are not bit-identical; solving this one scalar closes
    the initial-pressure mismatch without changing the physically meaningful
    mass/level design point.

    The root reconciles pressure only. It does not make the stored HEOS
    ``U_sec`` exactly equal to the IF97 phase-split internal energy; the
    default difference is about 50.23 MJ, or 0.016 % of the stored shell
    energy, which is acceptable for this L1 educational model.
    """

    def pressure_residual(U_sec: float) -> float:
        """Return current pressure minus target pressure [Pa]."""
        return saturation_state(M=M_sec, U=U_sec, V=V_sec).P - P_ref

    f_guess = pressure_residual(U_closed_form)
    if abs(f_guess) < 0.01:
        return U_closed_form

    # Numerical bracket, not a physics constant. The default shell root sits
    # at +1.64e-4 relative to the IF97 closed-form U; expand generously so
    # unusual shell volumes and levels still have room to bracket.
    for relative_half_width in (
        1.0e-6,
        3.0e-6,
        1.0e-5,
        3.0e-5,
        1.0e-4,
        3.0e-4,
        1.0e-3,
        3.0e-3,
        1.0e-2,
        3.0e-2,
        1.0e-1,
    ):
        lower = U_closed_form * (1.0 - relative_half_width)
        upper = U_closed_form * (1.0 + relative_half_width)
        f_lower = pressure_residual(lower)
        f_upper = pressure_residual(upper)
        if _root_bracket_contains_zero(f_lower, f_upper):
            if f_lower == 0.0:
                return lower
            if f_upper == 0.0:
                return upper
            return brentq(pressure_residual, lower, upper, xtol=1.0e-3, rtol=1.0e-14, maxiter=100)

    raise ValueError(
        "Could not bracket SGSecondary U_sec_initial so saturation_state pressure matches P_ref. "
        f"P_ref={P_ref:.6g} Pa, M_sec={M_sec:.6g} kg, V_sec={V_sec:.6g} m^3, "
        f"U_closed_form={U_closed_form:.6g} J."
    )


def feedwater_enthalpy(P: float, T_fw: float) -> float:
    """Return feedwater specific enthalpy at shell pressure and temperature.

    Parameters
    ----------
    P : float
        Shell/steam pressure [Pa].
    T_fw : float
        Feedwater temperature at the shell inlet [K].

    Returns
    -------
    float
        Specific enthalpy of feedwater at ``P`` and ``T_fw`` [J/kg].

    Notes
    -----
    Equation:

        h_fw(P, T_fw) = h(P, T_fw)

    CoolProp evaluates the compressed-liquid enthalpy. The plant domain
    check keeps ``P`` high enough that hot feedwater is liquid rather than
    flashing to steam, so this helper stays a property lookup rather than a
    separate two-phase model.
    """
    return coolprop.enthalpy_PT(P=P, T=T_fw)


@dataclass(frozen=True)
class SGSecondaryParams:
    """Parameters for the saturated steam-generator shell side.

    Parameters
    ----------
    V_sec : float
        Lumped shell-side volume of all modeled steam generators [m³].
    T_sec_ref : float
        Design saturation temperature [K]. The default matches
        ``SGParams.T_secondary_ref``.
    level_ref : float
        Design collapsed liquid level, ``V_l / V_sec`` [-].
    T_fw : float
        Feedwater temperature at the shell inlet [K].
    Q_design : float
        Design heat flow from the primary side into the shell [W].
    P_ref : float or None, optional
        Design shell pressure [Pa]. If None, derived as
        ``coolprop.P_sat(T_sec_ref)``.
    P_fw_flash : float or None, optional
        Feedwater saturation pressure at ``T_fw`` [Pa]. If None, derived as
        ``coolprop.P_sat(T_fw)`` once during parameter construction so domain
        checks need no property calls.
    m_steam_design : float or None, optional
        Design steam flow [kg/s]. If None, derived from
        ``Q_design / (h_g(P_ref) - h_fw(P_ref, T_fw))``.
    M_sec_initial : float or None, optional
        Initial shell mass [kg]. If either initial mass or initial internal
        energy is None, both are derived from ``P_ref``, ``level_ref``, and
        ``V_sec``.
    U_sec_initial : float or None, optional
        Initial shell internal energy [J]. If either initial state field is
        None, both are derived together; if both are supplied explicitly,
        they are left untouched.

    Notes
    -----
    Frozen dataclass; ``__post_init__`` uses ``object.__setattr__`` to fill
    derived defaults. The mass is kept at the closed-form IF97 saturated
    value so the collapsed level is exact; only internal energy is nudged by
    a one-dimensional pressure root solve to reconcile IF97 saturation tables
    with the Helmholtz ``(D, U)`` inversion used by
    :func:`fission_sim.physics.pressurizer.saturation_state`.
    """

    # Total secondary-side water/steam volume. Provenance: generic L1
    # educational assumption of plausible four-SG scale; at level_ref = 0.5
    # the default IF97 phase split contains about 222 t of liquid. This is
    # not a plant drawing value or calibrated level elevation.
    V_sec: float = 600.0  # [m³]

    # Design secondary saturation temperature. Provenance: matches the
    # existing L1 SteamGenerator/SecondarySink reference temperature (558 K),
    # which is about 285 °C and corresponds to ~6.9 MPa steam.
    T_sec_ref: float = 558.0  # [K]

    # Design collapsed water level. Provenance: generic L1 educational anchor;
    # half-full leaves symmetric margin for boiloff and overfill in this
    # simplified shell model, not a narrow-range level setpoint.
    level_ref: float = 0.5  # [-]

    # Feedwater temperature. Provenance: 500 K = 227 °C, a typical final
    # feedwater temperature after high-pressure feedwater heaters in a large
    # PWR secondary plant.
    T_fw: float = 500.0  # [K]

    # Thermal design power. Provenance: same 3.0 GWth nominal four-loop PWR
    # heat rate used by PointKineticsCore and SteamGenerator defaults.
    Q_design: float = 3.0e9  # [W]

    P_ref: float | None = None  # [Pa], derived from P_sat(T_sec_ref)
    P_fw_flash: float | None = None  # [Pa], derived from P_sat(T_fw)
    m_steam_design: float | None = None  # [kg/s], derived from Q/(h_g - h_fw)
    M_sec_initial: float | None = None  # [kg], derived from saturated liquid/vapor volumes
    U_sec_initial: float | None = None  # [J], derived from pressure-matched saturated state

    def __post_init__(self) -> None:
        """Derive default design-point quantities.

        Parameters
        ----------
        None
            All inputs are dataclass fields.

        Returns
        -------
        None
            Derived values are written to the frozen dataclass using
            ``object.__setattr__``.

        Notes
        -----
        Governing design equations (DOE-HDBK-1012/1-92 HT-01 p. 34
        saturated-mixture relations):

            P_ref = P_sat(T_sec_ref)
            V_l = level_ref · V_sec
            V_v = V_sec − V_l
            M_sec = ρ_l(P_ref) · V_l + ρ_v(P_ref) · V_v
            U_closed = M_l · u_l(P_ref) + M_v · u_v(P_ref)
            m_steam,design = Q_design / (h_g(P_ref) − h_fw(P_ref, T_fw))

        The final ``U_sec_initial`` is the scalar root near ``U_closed`` that
        makes the shared ``saturation_state`` inversion return ``P_ref``. It
        reconciles the initial pressure only; the HEOS stored energy and the
        IF97 phase-split energy still differ by about 0.016 % at the default
        state.
        """
        P_ref = self.P_ref
        if P_ref is None:
            P_ref = coolprop.P_sat(T=self.T_sec_ref)
            object.__setattr__(self, "P_ref", P_ref)
        if self.P_fw_flash is None:
            object.__setattr__(self, "P_fw_flash", coolprop.P_sat(T=self.T_fw))

        if self.M_sec_initial is None or self.U_sec_initial is None:
            # Saturated liquid/vapor properties at the design pressure.
            rho_l = coolprop.sat_liquid_density(P=P_ref)
            rho_v = coolprop.sat_vapor_density(P=P_ref)
            u_l = coolprop.sat_liquid_internal_energy(P=P_ref)
            u_v = coolprop.sat_vapor_internal_energy(P=P_ref)

            # M_l = ρ_l · V_l and M_v = ρ_v · V_v, standard saturated-mixture
            # volume split (DOE-HDBK-1012/1-92, quality/phase relations).
            V_l = self.level_ref * self.V_sec
            V_v = self.V_sec - V_l
            M_l = V_l * rho_l
            M_v = V_v * rho_v
            M_sec_initial = M_l + M_v

            # U = M_l · u_l + M_v · u_v, the extensive internal energy of the
            # two saturated phases before the pressure-only IF97/HEOS root.
            U_closed_form = M_l * u_l + M_v * u_v

            # Keep the closed-form mass: level depends on mass and IF97
            # saturated densities once the pressure is exact. Adjust only U.
            U_sec_initial = _solve_u_for_pressure(
                M_sec=M_sec_initial,
                U_closed_form=U_closed_form,
                V_sec=self.V_sec,
                P_ref=P_ref,
            )

            object.__setattr__(self, "M_sec_initial", M_sec_initial)
            object.__setattr__(self, "U_sec_initial", U_sec_initial)

        if self.m_steam_design is None:
            h_g = coolprop.sat_vapor_enthalpy(P=P_ref)
            h_fw = feedwater_enthalpy(P=P_ref, T_fw=self.T_fw)
            object.__setattr__(self, "m_steam_design", self.Q_design / (h_g - h_fw))


class SGSecondary:
    """Saturated shell-side steam generator control volume.

    Ports in
    --------
    Q_sg : float
        Heat transferred from the primary loop into the shell [W].
    m_steam : float
        Steam mass flow leaving for the turbine [kg/s].
    m_dump : float
        Steam mass flow leaving through dump/relief paths [kg/s].
    m_fw : float
        Feedwater mass flow entering the shell [kg/s].

    Ports out
    ---------
    P_steam : float
        Saturated steam pressure in the shell [Pa].
    T_secondary : float
        Saturation temperature at ``P_steam`` [K].
    level_sg : float
        Collapsed liquid level, ``V_l / V_sec`` [-].

    State variables
    ---------------
    M_sec : float
        Total shell-side water mass (liquid plus vapor) [kg].
    U_sec : float
        Total shell-side internal energy [J].

    Notes
    -----
    The component is state-derived: pressure, saturation temperature, and
    level follow from ``(M_sec, U_sec)`` alone, so
    ``outputs_require_inputs = False`` and the engine can publish
    ``P_steam`` before computed modules such as the turbine are evaluated.
    """

    state_size: int = 2
    state_labels: tuple[str, ...] = ("M_sec", "U_sec")
    input_ports: tuple[str, ...] = ("Q_sg", "m_steam", "m_dump", "m_fw")
    output_ports: tuple[str, ...] = ("P_steam", "T_secondary", "level_sg")
    outputs_require_inputs: bool = False

    def __init__(self, params: SGSecondaryParams) -> None:
        """Construct a shell-side steam generator model.

        Parameters
        ----------
        params : SGSecondaryParams
            Frozen parameter set with derived design-point values [SI units].
        """
        self.params = params

    def initial_state(self) -> np.ndarray:
        """Return the initial shell state vector.

        Returns
        -------
        np.ndarray, shape (2,)
            ``[M_sec_initial, U_sec_initial]`` in ``[kg, J]``.
        """
        p = self.params
        return np.array([p.M_sec_initial, p.U_sec_initial], dtype=float)

    def h_fw(self, P: float) -> float:
        """Return feedwater specific enthalpy at shell pressure.

        Parameters
        ----------
        P : float
            Shell/steam pressure [Pa].

        Returns
        -------
        float
            Specific enthalpy of feedwater at ``P`` and constant
            ``params.T_fw`` [J/kg].

        Notes
        -----
        Equation:

            h_fw(P) = h(P, T_fw)

        CoolProp evaluates the compressed-liquid enthalpy. A later plant
        domain check keeps ``P`` high enough that 500 K feedwater is liquid
        instead of flashing to steam.
        """
        return feedwater_enthalpy(P=P, T_fw=self.params.T_fw)

    def derivatives(self, state: np.ndarray, inputs: dict[str, float]) -> np.ndarray:
        """Return mass and internal-energy rates for the shell.

        Parameters
        ----------
        state : np.ndarray, shape (2,)
            ``[M_sec, U_sec]`` in ``[kg, J]``.
        inputs : dict
            Required keys are ``Q_sg`` [W], ``m_steam`` [kg/s],
            ``m_dump`` [kg/s], and ``m_fw`` [kg/s].

        Returns
        -------
        np.ndarray, shape (2,)
            ``[dM_sec/dt, dU_sec/dt]`` in ``[kg/s, W]``.

        Notes
        -----
        Governing equations (Yan §5.2.2 mass conservation and §5.2.3 energy
        conservation for a transient control volume):

            dM_sec/dt = ṁ_fw − ṁ_steam − ṁ_dump
            dU_sec/dt = Q_sg + ṁ_fw · h_fw(P_steam)
                        − (ṁ_steam + ṁ_dump) · h_g(P_steam)

        ``h_g`` is the saturated-vapor specific enthalpy. In plant language,
        it is the energy carried away by one kilogram of dry steam leaving the
        steam dome.
        """
        p = self.params
        M_sec, U_sec = state[0], state[1]
        sat = saturation_state(M=M_sec, U=U_sec, V=p.V_sec)

        m_steam = inputs["m_steam"]
        m_dump = inputs["m_dump"]
        m_fw = inputs["m_fw"]
        m_out = m_steam + m_dump

        # Mass balance: feedwater entering minus all steam leaving (Yan
        # §5.2.2, transient control-volume mass conservation).
        dM_dt = m_fw - m_out

        # Energy balance for a rigid control volume. Flow work is already
        # included in the stream enthalpies h_fw and h_g (Yan §5.2.3).
        dU_dt = inputs["Q_sg"] + m_fw * self.h_fw(sat.P) - m_out * sat.h_v

        return np.array([dM_dt, dU_dt], dtype=float)

    def outputs(self, state: np.ndarray, inputs: dict[str, float] | None = None) -> dict[str, float]:
        """Return the state-derived output ports.

        Parameters
        ----------
        state : np.ndarray, shape (2,)
            ``[M_sec, U_sec]`` in ``[kg, J]``.
        inputs : dict or None, optional
            Accepted for component API uniformity; ignored because the output
            ports are functions of state and fixed parameters only.

        Returns
        -------
        dict
            Keys are ``P_steam`` [Pa], ``T_secondary`` [K], and
            ``level_sg`` [-].

        Notes
        -----
        Equation:

            (P_steam, T_secondary, level_sg) = saturation_state(M_sec, U_sec, V_sec)

        ``saturation_state`` applies the same two-phase lever-rule closure
        used by the pressurizer.
        """
        p = self.params
        sat = saturation_state(M=state[0], U=state[1], V=p.V_sec)
        return {
            "P_steam": sat.P,
            "T_secondary": sat.T_sat,
            "level_sg": sat.level,
        }

    def telemetry(self, state: np.ndarray, inputs: dict[str, float] | None = None) -> dict[str, Any]:
        """Return rich shell-side diagnostics for logs and visualization.

        Parameters
        ----------
        state : np.ndarray, shape (2,)
            ``[M_sec, U_sec]`` in ``[kg, J]``.
        inputs : dict or None, optional
            Required input-port values when available. If None,
            input-dependent telemetry keys are still present but set to None.

        Returns
        -------
        dict
            Always contains ``P_steam``, ``T_secondary``, ``level_sg``, ``x``,
            ``level_margin_low``, ``M_l``, ``M_v``, ``M_sec``, ``U_sec``,
            ``h_g``, ``h_fw``, and ``P_fw_flash``.
            Also contains ``Q_sg``, ``m_steam``, ``m_dump``, ``m_fw``, and
            ``Q_steam_net``; those are numeric when ``inputs`` is provided.
            ``boil_off_time_s`` is also numeric when ``inputs`` is provided.
            ``time_to_level_floor_s`` is numeric only when the shell is
            presently draining toward the lower validity floor. Input-
            dependent keys are None otherwise.

        Notes
        -----
        ``x`` is quality, the vapor mass fraction. A value of 0.05 means five
        percent of the shell mass is steam by mass, even though steam occupies
        much more volume than water.

        ``boil_off_time_s`` divides total current liquid mass by present
        steam outflow. It is a total-liquid turnover cue, not time to the
        lower model limit or to a plant trip.

        ``time_to_level_floor_s`` is a separate display estimate of time to
        the L1 surrogate floor. It freezes the current saturated-liquid
        density and present net flow imbalance, so it is only a trend
        diagnostic; it does not integrate pressure, density, controller, or
        actuator changes.
        """
        p = self.params
        M_sec, U_sec = state[0], state[1]
        sat = saturation_state(M=M_sec, U=U_sec, V=p.V_sec)
        h_fw = self.h_fw(sat.P)

        out: dict[str, Any] = {
            "P_steam": sat.P,
            "T_secondary": sat.T_sat,
            "level_sg": sat.level,
            # Margin to tube uncovering: positive means the simplified
            # constant-UA heat-transfer picture is still inside its level band.
            "level_margin_low": sat.level - LEVEL_SG_MIN,
            "x": sat.x,
            "M_l": sat.M_l,
            "M_v": sat.M_v,
            "M_sec": M_sec,
            "U_sec": U_sec,
            "h_g": sat.h_v,
            "h_fw": h_fw,
            "P_fw_flash": p.P_fw_flash,
        }

        if inputs is None:
            out["Q_sg"] = None
            out["m_steam"] = None
            out["m_dump"] = None
            out["m_fw"] = None
            out["Q_steam_net"] = None
            out["boil_off_time_s"] = None
            out["time_to_level_floor_s"] = None
        else:
            m_out = inputs["m_steam"] + inputs["m_dump"]
            net_outflow = m_out - inputs["m_fw"]
            # Net heat exported by outgoing steam after subtracting the
            # enthalpy brought back by replacement feedwater.
            Q_steam_net = m_out * sat.h_v - inputs["m_fw"] * h_fw
            # Total liquid inventory divided by present steam outflow. This
            # is not time to LEVEL_SG_MIN because it counts liquid below the
            # surrogate validity floor and ignores future property/flow
            # changes.
            boil_off_time_s = sat.M_l / max(m_out, _FLOW_EPS)
            # SIMPLIFICATION: approximate time to the lower collapsed-level
            # validity floor using frozen saturated-liquid density and the
            # present net outflow. Vapor replacing the drained volume, future
            # pressure changes, actuator motion, and controller response are
            # intentionally omitted because this is telemetry only.
            liquid_mass_above_floor = sat.rho_l * p.V_sec * max(sat.level - LEVEL_SG_MIN, 0.0)
            time_to_level_floor_s = (
                liquid_mass_above_floor / net_outflow if net_outflow > _FLOW_EPS else None
            )
            out["Q_sg"] = inputs["Q_sg"]
            out["m_steam"] = inputs["m_steam"]
            out["m_dump"] = inputs["m_dump"]
            out["m_fw"] = inputs["m_fw"]
            out["Q_steam_net"] = Q_steam_net
            out["boil_off_time_s"] = boil_off_time_s
            out["time_to_level_floor_s"] = time_to_level_floor_s

        return out
