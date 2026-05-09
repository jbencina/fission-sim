"""Thin wrapper around CoolProp for IAPWS-97 water/steam properties.

Per ``.docs/design.md`` §3.3, all water/steam property calls go through
this module. Concentrating the dependency here lets us cache results,
swap backends, or substitute simplified correlations without touching
the physics modules.

All inputs are SI (Pa, K). All outputs are SI (kg/m³, J/kg, J/(kg·K),
1/K). Quantity names follow the project convention: ``rho`` for density,
``u`` for specific internal energy, ``h`` for specific enthalpy.

References
----------
IAPWS Industrial Formulation 1997 for the Thermodynamic Properties of
Water and Steam (IAPWS-IF97). Implemented by the CoolProp library.
"""

from __future__ import annotations

import CoolProp.CoolProp as CP

# Fluid name passed to every CoolProp call. Centralized so a future
# substitution (e.g. heavy-water for CANDU-style plants) is one edit.
_FLUID = "Water"


def density_PT(P: float, T: float) -> float:
    """Liquid density of water at given pressure and temperature.

    Parameters
    ----------
    P : float
        Pressure [Pa].
    T : float
        Temperature [K].

    Returns
    -------
    float
        Density [kg/m³]. For primary-loop conditions (15.5 MPa, 568–598 K),
        this is subcooled liquid in the 690–740 kg/m³ range.
    """
    return CP.PropsSI("D", "P", P, "T", T, _FLUID)


def enthalpy_PT(P: float, T: float) -> float:
    """Specific enthalpy of water at given pressure and temperature.

    Parameters
    ----------
    P : float
        Pressure [Pa].
    T : float
        Temperature [K].

    Returns
    -------
    float
        Specific enthalpy [J/kg].
    """
    return CP.PropsSI("H", "P", P, "T", T, _FLUID)


def T_sat(P: float) -> float:
    """Saturation temperature of water at given pressure.

    Parameters
    ----------
    P : float
        Pressure [Pa].

    Returns
    -------
    float
        Saturation temperature [K].
    """
    return CP.PropsSI("T", "P", P, "Q", 0.0, _FLUID)


def sat_liquid_density(P: float) -> float:
    """Saturated-liquid density at given pressure (Q=0)."""
    return CP.PropsSI("D", "P", P, "Q", 0.0, _FLUID)


def sat_vapor_density(P: float) -> float:
    """Saturated-vapor density at given pressure (Q=1)."""
    return CP.PropsSI("D", "P", P, "Q", 1.0, _FLUID)


def sat_liquid_enthalpy(P: float) -> float:
    """Saturated-liquid specific enthalpy at given pressure (Q=0)."""
    return CP.PropsSI("H", "P", P, "Q", 0.0, _FLUID)


def sat_vapor_enthalpy(P: float) -> float:
    """Saturated-vapor specific enthalpy at given pressure (Q=1)."""
    return CP.PropsSI("H", "P", P, "Q", 1.0, _FLUID)


def sat_liquid_internal_energy(P: float) -> float:
    """Saturated-liquid specific internal energy at given pressure."""
    return CP.PropsSI("U", "P", P, "Q", 0.0, _FLUID)


def sat_vapor_internal_energy(P: float) -> float:
    """Saturated-vapor specific internal energy at given pressure."""
    return CP.PropsSI("U", "P", P, "Q", 1.0, _FLUID)


def beta_T(P: float, T: float) -> float:
    """Isobaric volumetric thermal expansion coefficient (1/V)·(∂V/∂T)_P.

    Parameters
    ----------
    P : float
        Pressure [Pa].
    T : float
        Temperature [K].

    Returns
    -------
    float
        β_T in 1/K. At primary design conditions (583 K, 15.5 MPa) this
        is ~3.3e-3 /K (verified via Task A1 with CoolProp 7.2.0).
    """
    return CP.PropsSI("isobaric_expansion_coefficient", "P", P, "T", T, _FLUID)


def P_from_DU(D: float, U: float) -> float:
    """Invert the saturation surface: given specific volume (1/D) and
    specific internal energy U, return pressure.

    Used by the pressurizer's saturation closure: given (M, U, V_pzr) the
    state's average density is D = M/V and specific internal energy is
    U/M; this call returns the pressure of the saturated mixture sitting
    at that density and internal energy.

    Parameters
    ----------
    D : float
        Mass density [kg/m³].
    U : float
        Specific internal energy [J/kg].

    Returns
    -------
    float
        Pressure [Pa].

    Notes
    -----
    For points outside the saturation dome CoolProp may return values
    that don't represent a saturated mixture. The pressurizer model
    assumes the state stays inside the dome at L1; sustained excursions
    would indicate either a parameter problem or the need to extend the
    model to subcooled/superheated regimes.
    """
    return CP.PropsSI("P", "D", D, "U", U, _FLUID)
