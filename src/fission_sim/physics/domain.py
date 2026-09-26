"""The physical domain the lumped primary-plant equations are valid in.

Every model is built on assumptions. This one assumes two things that the
equations cannot check for themselves:

1. **The primary loop is liquid water.** ``PrimaryLoop`` and the surge
   helper use single-phase liquid energy balances and liquid densities.
   Once the hottest water (the hot leg) reaches the saturation temperature
   at primary pressure it would start to boil, and steam voids, two-phase
   flow and boiling heat transfer are not modeled.
2. **The pressurizer is a saturated steam bubble over water.** The
   pressurizer's closure (``pressurizer.saturation_state``) splits its mass
   into saturated liquid and saturated steam with the lever rule. That only
   means something while both phases are present, i.e. while the steam
   quality (vapor mass fraction) x is strictly between 0 and 1. At x = 0
   the vessel has filled "solid" with water; at x = 1 it has boiled dry.

Outside these limits the code does not fail on its own. The property
library happily returns a steam density for water that is past saturation,
and the lever rule returns a negative "quality" for a water-solid vessel,
so the simulation would keep running and plot numbers that describe no real
plant. :func:`check_primary_domain` turns those silent failures into a
:class:`ModelDomainError` that names the broken assumption, so a front end
can stop and explain instead.

When to check
-------------
Check **accepted** states only, i.e. the state at the end of each
``SimEngine.step``. The stiff (BDF) integrator probes trial states while it
searches for a step, and some of those may land briefly outside the domain
even though the step it finally accepts is inside. Rejecting trial states
would stop simulations that are actually fine. The one exception is a
property-library failure on a trial state: the integrator cannot recover
from an exception raised inside the right-hand side, so ``coolprop.py``
reports it as a ``ModelDomainError`` too (the step genuinely cannot
complete).

This module adds no physics: no boiling model, no clamping, no automatic
reactor protection. It only makes the edge of the model visible.

Public references:

- CoolProp high-level API, "Vapor-liquid and saturation states" (why
  (P, T) inputs cannot identify a state on the saturation line):
  https://coolprop.org/coolprop/HighLevelAPI.html#vapor-liquid-and-saturation-states
- IAPWS, Revised Release on the Industrial Formulation 1997 (IF97), §2
  gives the critical point of water, 22.064 MPa / 647.096 K:
  https://iapws.org/documents/release/IF97-Rev
"""

from __future__ import annotations

import math

# ---------------------------------------------------------------------------
# Limits
# ---------------------------------------------------------------------------

# Critical pressure of water [Pa] (IAPWS-IF97 §2). Above it liquid and steam are
# no longer distinct phases, so a pressurizer "level" has no meaning.
P_CRITICAL: float = 22.064e6

# Highest primary pressure the model accepts [Pa]. 1 MPa below the critical
# point, because saturation properties change steeply as the dome closes.
# (Real plants open relief valves near 17 MPa; that is plant protection,
# not modeled here, and not a limit of the equations.)
P_MAX: float = 21.0e6

# Lowest primary pressure the model accepts [Pa]. In practice the hot-leg
# subcooling limit below trips long before this (at the design hot-leg
# temperature of ~598 K, water boils below about 12 MPa), so this bound
# only catches a pressurizer closure that has produced a non-physical
# pressure.
P_MIN: float = 1.0e6

# Minimum hot-leg subcooling T_sat(P) − T_hot [K]. Zero: any subcooled
# liquid is inside the domain, and the saturation line is the boundary.
MIN_SUBCOOLING: float = 0.0


class ModelDomainError(ValueError):
    """The simulated state has left the region the model's equations describe.

    Raised by :func:`check_primary_domain` for an accepted state, and by
    ``coolprop.py`` when the property library cannot evaluate a state at
    all. The message is written for a learner: it names the broken
    assumption and the values that broke it.

    Subclasses ``ValueError`` so callers that already handled property
    lookup failures (CoolProp raises ``ValueError``) keep working.

    Parameters
    ----------
    message : str
        Plain-language explanation.
    limit : str
        Short machine-readable name of the violated limit: one of
        ``"non_finite"``, ``"loop_inventory"``, ``"pressure"``,
        ``"pressurizer_solid"``, ``"pressurizer_dry"``,
        ``"hot_leg_subcooling"``, ``"property_lookup"``.
    """

    def __init__(self, message: str, *, limit: str) -> None:
        super().__init__(message)
        self.limit = limit


def check_primary_domain(
    *,
    P: float,
    T_sat: float,
    T_hot: float,
    M_loop: float,
    x_pzr: float,
) -> None:
    """Raise ``ModelDomainError`` if an accepted state is outside the model.

    All inputs are already in the engine snapshot (loop and pressurizer
    telemetry), so the check costs a few comparisons and no property calls.
    :func:`check_snapshot` pulls them out of a snapshot for you.

    Parameters
    ----------
    P : float
        Primary (pressurizer) pressure [Pa].
    T_sat : float
        Saturation temperature at ``P`` [K].
    T_hot : float
        Hot-leg temperature [K], the hottest water in the loop.
    M_loop : float
        Liquid mass in the loop, excluding the pressurizer [kg].
    x_pzr : float
        Pressurizer steam quality (vapor mass fraction) [-].

    Raises
    ------
    ModelDomainError
        With a learner-readable message for the first violated limit,
        checked in this order: finite numbers, loop inventory, pressure,
        pressurizer quality, hot-leg subcooling.
    """
    values = {"P": P, "T_sat": T_sat, "T_hot": T_hot, "M_loop": M_loop, "x_pzr": x_pzr}
    bad = [name for name, value in values.items() if not math.isfinite(value)]
    if bad:
        raise ModelDomainError(
            f"The simulation produced a non-numeric value for {', '.join(bad)}. "
            "The equations have been pushed somewhere they cannot be evaluated.",
            limit="non_finite",
        )
    P_MPa = P / 1e6
    if M_loop <= 0.0:
        raise ModelDomainError(
            f"The primary loop has run out of water (inventory {M_loop:.0f} kg). "
            "The loop equations need a positive mass of liquid to carry heat.",
            limit="loop_inventory",
        )
    if P < P_MIN:
        raise ModelDomainError(
            f"Primary pressure fell to {P_MPa:.2f} MPa, below the model's "
            f"{P_MIN / 1e6:.0f} MPa floor and far below any pressurized-water "
            "reactor operating pressure. The model's fixed design-point water "
            "properties do not describe the plant there.",
            limit="pressure",
        )
    if P > P_MAX:
        raise ModelDomainError(
            f"Primary pressure rose to {P_MPa:.2f} MPa, above the model's "
            f"{P_MAX / 1e6:.0f} MPa ceiling and close to water's critical point "
            f"({P_CRITICAL / 1e6:.1f} MPa), where liquid and steam stop being "
            "distinct. The pressurizer's steam-over-water picture no longer "
            "applies.",
            limit="pressure",
        )
    if x_pzr <= 0.0:
        raise ModelDomainError(
            "The pressurizer has filled solid with water: no steam is left "
            "(steam quality at or below zero) and the water reaches the top of "
            "the vessel. The model's pressurizer is a steam bubble over water, "
            "and its pressure comes from that bubble. With no steam left, "
            "pressure would be set by squeezing liquid water, which the model "
            "does not include.",
            limit="pressurizer_solid",
        )
    if x_pzr >= 1.0:
        raise ModelDomainError(
            "The pressurizer has boiled dry: no liquid water is left (steam "
            "quality at or above one). The model's pressurizer needs liquid "
            "water under its steam bubble.",
            limit="pressurizer_dry",
        )
    subcooling = T_sat - T_hot
    if subcooling <= MIN_SUBCOOLING:
        raise ModelDomainError(
            f"Hot-leg water reached its boiling point: T_hot = {T_hot:.1f} K, "
            f"saturation temperature {T_sat:.1f} K at {P_MPa:.2f} MPa "
            f"(subcooling {subcooling:.2f} K). The model treats the primary "
            "loop as liquid water only; boiling and steam voids are not modeled.",
            limit="hot_leg_subcooling",
        )


def check_snapshot(snap: dict) -> None:
    """Run :func:`check_primary_domain` on a ``SimEngine`` snapshot.

    Call it after every ``engine.step`` (the accepted state), not inside the
    solver. Expects the module names of the standard wiring,
    ``fission_sim.plant.build_standard_plant()``: a ``PrimaryLoop``
    registered as ``"loop"`` and a ``Pressurizer`` as ``"pzr"``. Plants without a
    pressurizer have no pressure state and cannot be checked this way.

    Parameters
    ----------
    snap : dict
        Snapshot returned by ``SimEngine.step`` or ``SimEngine.snapshot``.

    Raises
    ------
    ModelDomainError
        See :func:`check_primary_domain`.
    """
    loop = snap["loop"]
    pzr = snap["pzr"]
    check_primary_domain(
        P=pzr["P"],
        T_sat=pzr["T_sat"],
        T_hot=loop["T_hot"],
        M_loop=loop["M_loop"],
        x_pzr=pzr["x"],
    )


__all__ = [
    "MIN_SUBCOOLING",
    "P_CRITICAL",
    "P_MAX",
    "P_MIN",
    "ModelDomainError",
    "check_primary_domain",
    "check_snapshot",
]
