"""Thin wrapper around CoolProp for IAPWS-97 water/steam properties.

By design, all water/steam property calls go through this module.
Concentrating the dependency here lets us cache results, swap backends,
or substitute simplified correlations without touching the physics
modules. The README's "CoolProp wrapper" subsection explains it for learners.

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

from fission_sim.physics.domain import ModelDomainError

# Backend choice — split because IF97 is the speed win but doesn't
# implement every input pair we need.
#
# ``_FLUID_FAST`` selects the IAPWS-IF97 industrial formulation (same
# standard the ASME steam tables use). It uses explicit polynomial fits
# inside each region and is roughly 3× faster per call than the default
# Helmholtz-energy backend. Profiling on report_primary.py traced ~96 %
# of total runtime to PropsSI calls, so the backend swap is the largest
# single cost lever. At primary-system conditions IF97 matches HEOS
# within ~2e-4 relative on every quantity we read, well below the lumped
# model's own approximation error.
#
# ``_FLUID_DOME`` keeps the Helmholtz EOS (default ``"Water"``). IF97
# does not implement two pairs we need:
#   1. ``calc_reducing_state`` for ``isobaric_expansion_coefficient``
#      (β_T) — not called by the simulation at all (see ``beta_T``).
#   2. ``(D, U)`` → ``P`` inversion — used by the pressurizer's
#      saturation closure on every derivative evaluation. Migrating this
#      to IF97 would require rewriting the closure as a direct fit on
#      one of IF97's region equations, which is a larger refactor.
_FLUID_FAST = "IF97::Water"
_FLUID_DOME = "Water"
# Backwards-compat alias kept so that any existing inspection of
# ``_FLUID`` still finds a sensible default.
_FLUID = _FLUID_FAST


# Fragments of CoolProp error messages that mean the *call* is wrong (a
# misspelled property or fluid name, or a query the backend does not
# implement), not that the water state is outside the model. These stay
# plain ValueErrors so a coding mistake is never reported to a learner as
# a physics limit.
_CALL_ERROR_MARKERS = (
    "parsing failed",
    "Input pair variable is invalid",
    "Initialize failed",
    "not implemented",
)


def _props(output: str, name1: str, value1: float, name2: str, value2: float, fluid: str) -> float:
    """Call ``CP.PropsSI`` and report a state-lookup failure as a model-domain error.

    CoolProp raises a bare ``ValueError`` when it cannot evaluate a state,
    for example a (P, T) pair sitting on the saturation line, where
    pressure and temperature alone do not say how much is liquid and how
    much is steam. Inside the ODE right-hand side that exception ends the
    solver step (``solve_ivp`` cannot retry around an exception), so the
    simulation genuinely cannot continue. Re-raising it as
    ``ModelDomainError`` lets the runtime tell a learner *why*, instead of
    showing a library traceback. The original error stays attached as
    ``__cause__``. Errors that mean the call itself is malformed (see
    ``_CALL_ERROR_MARKERS``) are re-raised unchanged.
    """
    try:
        return CP.PropsSI(output, name1, value1, name2, value2, fluid)
    except ValueError as err:
        if any(marker in str(err) for marker in _CALL_ERROR_MARKERS):
            raise
        raise ModelDomainError(
            f"Water properties could not be evaluated for {output} at "
            f"{name1} = {value1:.6g}, {name2} = {value2:.6g} ({fluid}). The state "
            "has reached a region the model does not cover, most likely water "
            "at its boiling point or a pressurizer that is no longer a "
            "steam-water mixture.",
            limit="property_lookup",
        ) from err


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
        this is subcooled liquid in the 690–740 kg/m³ range. Above
        ``T_sat(P)`` it is a steam density; see the comment below.

    Raises
    ------
    ModelDomainError
        If CoolProp cannot evaluate the state (e.g. on the saturation line).
    """
    # IF97 refuses (P, T) inputs whose state lies within ~0.003 % of the
    # saturation line (it correctly recognises the state as ambiguous), so
    # this query goes through HEOS, which accepts states closer to the
    # line. HEOS does NOT extrapolate the liquid, though: for T above
    # T_sat(P) it returns the density of steam (~100 kg/m³ at 15.5 MPa),
    # and exactly on the line it can still refuse. Nothing here enforces
    # "liquid". ``SimRuntime`` runs ``domain.check_snapshot`` on every
    # accepted state and stops when the hot leg reaches saturation; code
    # that steps a ``SimEngine`` directly (tests, examples) is unchecked
    # unless it calls that too. Solver trial states may briefly cross the
    # line inside a step that ends subcooled. The runtime cost is small —
    # density_PT was ~1 % of total profile time.
    return _props("D", "P", P, "T", T, _FLUID_DOME)


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
    # that fall within ~0.003 % of the saturation line, so use HEOS. As
    # there, a state past saturation returns a steam enthalpy rather than
    # an error; the accepted-state domain check is what catches boiling.
    # Runtime cost was ~4 % of total profile time.
    return _props("H", "P", P, "T", T, _FLUID_DOME)


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
    return _props("T", "P", P, "Q", 0.0, _FLUID_FAST)


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
    return _props("D", "P", P, "Q", 0.0, _FLUID_FAST)


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
    return _props("D", "P", P, "Q", 1.0, _FLUID_FAST)


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
    return _props("H", "P", P, "Q", 0.0, _FLUID_FAST)


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
    return _props("H", "P", P, "Q", 1.0, _FLUID_FAST)


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
    return _props("U", "P", P, "Q", 0.0, _FLUID_FAST)


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
    return _props("U", "P", P, "Q", 1.0, _FLUID_FAST)


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
        is ~3.3e-3 /K (3.26e-3 with CoolProp 7.2.0).
    """
    # IF97 backend does not implement ``calc_reducing_state`` for this
    # query, so fall back to HEOS. The simulation never calls this: the
    # loop uses the frozen constant ``LoopParams.beta_T_primary`` (3.3e-3 /K),
    # chosen from this function's design-point value, which
    # tests/test_coolprop.py checks. So the slower backend is fine here.
    return _props("isobaric_expansion_coefficient", "P", P, "T", T, _FLUID_DOME)


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
    For points outside the saturation dome CoolProp returns the pressure
    of a single-phase state (e.g. compressed liquid for a water-solid
    pressurizer), not an error. The pressurizer model assumes the state
    stays inside the dome. ``SimRuntime`` runs ``domain.check_snapshot``
    on every accepted state and stops when the quality leaves (0, 1);
    code that steps a ``SimEngine`` directly is unchecked unless it calls
    that too.
    """
    # IF97 backend does not implement the ``(D, U)`` input pair, so fall
    # back to HEOS for this single inversion. Migrating it to IF97 would
    # require rewriting the closure as a direct fit on one of IF97's
    # region equations — a larger refactor deferred for now.
    return _props("P", "D", D, "U", U, _FLUID_DOME)
