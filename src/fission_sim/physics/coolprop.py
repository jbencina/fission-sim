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

Public references:

- CoolProp IF97 Steam/Water Properties documentation:
  https://coolprop.org/fluid_properties/IF97.html
- IAPWS, Revised Release on the Industrial Formulation 1997 for the
  Thermodynamic Properties of Water and Steam:
  https://iapws.org/documents/release/IF97-Rev
"""

from __future__ import annotations

import CoolProp.CoolProp as CP

# Backend choice — split because IF97 is the speed win but doesn't
# implement every input pair we need.
#
# ``_FLUID_FAST`` selects the IAPWS-IF97 industrial formulation (same
# standard the ASME steam tables use). It uses explicit polynomial fits
# inside each region and is roughly 3× faster per call than the default
# Helmholtz-energy backend. Profiling on report_primary.py traced ~96 %
# of total runtime to PropsSI calls, so the backend swap is the largest
# single cost lever. At primary-system conditions IF97 matches HEOS
# within ~2e-4 relative on every quantity we read, well below the L1
# model's own approximation error.
#
# ``_FLUID_DOME`` keeps the Helmholtz EOS (default ``"Water"``). IF97
# does not implement two pairs we need:
#   1. ``calc_reducing_state`` for ``isobaric_expansion_coefficient``
#      (β_T) — used at module/parameter init only, not in the hot loop.
#   2. ``(D, U)`` → ``P`` inversion — used by the pressurizer's
#      saturation closure on every derivative evaluation. Migrating this
#      to IF97 would require rewriting the closure as a direct fit on
#      one of IF97's region equations, which is a larger refactor.
_FLUID_FAST = "IF97::Water"
_FLUID_DOME = "Water"
# Backwards-compat alias kept so that any existing inspection of
# ``_FLUID`` still finds a sensible default.
_FLUID = _FLUID_FAST


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
    # IF97 refuses (P, T) inputs whose state lies within ~0.003 % of the
    # saturation line (it correctly recognises the state as ambiguous).
    # Some test scenarios drive the loop right up to T_sat, so route this
    # query through HEOS, which extrapolates silently. The runtime cost
    # is small — density_PT was ~1 % of total profile time.
    return CP.PropsSI("D", "P", P, "T", T, _FLUID_DOME)


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
    # Same boundary issue as ``density_PT``: IF97 rejects (P, T) inputs
    # that fall within ~0.003 % of the saturation line. Use HEOS for
    # safety — runtime cost was ~4 % of total profile time.
    return CP.PropsSI("H", "P", P, "T", T, _FLUID_DOME)


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
    return CP.PropsSI("T", "P", P, "Q", 0.0, _FLUID_FAST)


def sat_liquid_density(P: float) -> float:
    """Saturated-liquid density at given pressure (Q=0).

    Parameters
    ----------
    P : float
        Pressure [Pa].

    Returns
    -------
    float
        Density [kg/m³].
    """
    return CP.PropsSI("D", "P", P, "Q", 0.0, _FLUID_FAST)


def sat_vapor_density(P: float) -> float:
    """Saturated-vapor density at given pressure (Q=1).

    Parameters
    ----------
    P : float
        Pressure [Pa].

    Returns
    -------
    float
        Density [kg/m³].
    """
    return CP.PropsSI("D", "P", P, "Q", 1.0, _FLUID_FAST)


def sat_liquid_enthalpy(P: float) -> float:
    """Saturated-liquid specific enthalpy at given pressure (Q=0).

    Parameters
    ----------
    P : float
        Pressure [Pa].

    Returns
    -------
    float
        Specific enthalpy [J/kg].
    """
    return CP.PropsSI("H", "P", P, "Q", 0.0, _FLUID_FAST)


def sat_vapor_enthalpy(P: float) -> float:
    """Saturated-vapor specific enthalpy at given pressure (Q=1).

    Parameters
    ----------
    P : float
        Pressure [Pa].

    Returns
    -------
    float
        Specific enthalpy [J/kg].
    """
    return CP.PropsSI("H", "P", P, "Q", 1.0, _FLUID_FAST)


def sat_liquid_internal_energy(P: float) -> float:
    """Saturated-liquid specific internal energy at given pressure.

    Parameters
    ----------
    P : float
        Pressure [Pa].

    Returns
    -------
    float
        Specific internal energy [J/kg].
    """
    return CP.PropsSI("U", "P", P, "Q", 0.0, _FLUID_FAST)


def sat_vapor_internal_energy(P: float) -> float:
    """Saturated-vapor specific internal energy at given pressure.

    Parameters
    ----------
    P : float
        Pressure [Pa].

    Returns
    -------
    float
        Specific internal energy [J/kg].
    """
    return CP.PropsSI("U", "P", P, "Q", 1.0, _FLUID_FAST)


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
    # IF97 backend does not implement ``calc_reducing_state`` for this
    # query, so fall back to HEOS. This call is only made at module/
    # parameter init (Task A1 verification, frozen constants), not in
    # the integrator's hot loop, so the slower backend is fine here.
    return CP.PropsSI("isobaric_expansion_coefficient", "P", P, "T", T, _FLUID_DOME)


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
    # IF97 backend does not implement the ``(D, U)`` input pair, so fall
    # back to HEOS for this single inversion. Migrating it to IF97 would
    # require rewriting the closure as a direct fit on one of IF97's
    # region equations — a larger refactor deferred for now.
    return CP.PropsSI("P", "D", D, "U", U, _FLUID_DOME)
