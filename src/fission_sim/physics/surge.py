"""Shared helper for computing primary→pressurizer surge mass flow.

It lives in its own module so both ``primary_loop.py`` and
``pressurizer.py`` can compute m_dot_surge identically without
creating a circular import (pressurizer.py already imports LoopParams
from primary_loop.py). Each module applies it to its own derivatives,
which keeps the system mass-conservation invariant
``M_loop + M_pzr = const`` to solver tolerance.

Conservation rationale
----------------------
The pressurizer's outputs are state-derived: the engine evaluates
``Pressurizer.outputs(state)`` without inputs, so its pressure P is
available to the controller early. The surge flow depends on inputs
(the heat flows and the hot-leg temperature), so it cannot be one of
those outputs, and a wired surge port would not carry the real value.
Instead the loop and the pressurizer each call this pure function inside
``derivatives()``, with the same inputs (the loop gets ``P_primary``
from ``pzr.P``) at the same instant, so the surge leaving one is exactly
the surge entering the other.

Public references:

- U.S. NRC Technical Training Center, *Reactor Concepts Manual:
  Pressurized Water Reactor Systems*, describes pressurizer surge caused
  by primary-coolant thermal expansion/contraction:
  https://ww2.nrc.gov/sites/default/files/doc_library/cdn/legacy/reading-rm/basic-ref/students/for-educators/04.pdf
- Claire Yu Yan, *Introduction to Engineering Thermodynamics*, §5.2,
  gives the public control-volume mass/energy balance and volumetric to
  mass flow relation used by this helper:
  https://pressbooks.bccampus.ca/thermo1/chapter/5-2-steady-flow-and-transient-flow/
"""

from __future__ import annotations

from fission_sim.physics import coolprop
from fission_sim.physics.primary_loop import LoopParams


def compute_m_dot_surge(
    *,
    Q_fuel_to_coolant: float,
    Q_sg: float,
    T_hotleg: float,
    P_primary: float,
    rho_l_sat: float,
    loop_params: LoopParams,
) -> float:
    """Mass surge flow into the pressurizer [kg/s].

    Direction-branched: insurge uses subcooled-liquid ρ_hotleg(P, T_hot);
    outsurge uses saturated-liquid ρ_l from the pressurizer's saturation
    closure.

    Parameters
    ----------
    Q_fuel_to_coolant : float
        Heat entering the coolant from the fuel [W] (the core's
        ``Q_fuel_to_coolant`` output, not its fission power).
    Q_sg : float
        Heat removed by the steam generator [W].
    T_hotleg : float
        Hot-leg temperature [K] — sets ρ for insurge.
    P_primary : float
        Current pressurizer pressure [Pa] — sets ρ for both branches.
    rho_l_sat : float
        Saturated-liquid density at P_primary [kg/m³] — used for
        outsurge. Passed in so the pressurizer can use its already-
        computed value from ``saturation_state``; the loop computes
        it via ``coolprop.sat_liquid_density(P=P_primary)``.
    loop_params : LoopParams
        Source of M_hot, M_cold, c_p, V_loop, beta_T_primary.

    Returns
    -------
    float
        Signed mass flow [kg/s]. Positive = insurge (mass into pzr);
        negative = outsurge (mass out of pzr, into loop).

    Notes
    -----
    Algorithm:

    1. Compute the rate of change of the loop's **mass-weighted** mean
       temperature from its net energy imbalance:

           T_mean    = (M_hot · T_hot + M_cold · T_cold) / (M_hot + M_cold)
           dT_mean/dt = (Q_core − Q_sg) / ((M_hot + M_cold) · c_p)

       Adding the loop's two leg energy balances gives this exactly, for
       any masses: the inter-leg flow term ṁ·c_p·(T_hot − T_cold) cancels.
       It is the energy-consistent driver of net thermal expansion,
       because it only changes when heat is added to or removed from the
       whole inventory.

       Note: this is NOT always the derivative of the loop's published
       ``T_avg = (T_hot + T_cold) / 2`` (an arithmetic mean, used for SG
       heat transfer and moderator feedback). The two agree only when
       M_hot = M_cold, which is the default. With unequal masses the
       arithmetic T_avg can move while the stored energy, and so the net
       expansion, does not (e.g. pure redistribution between the legs);
       this helper then correctly reports zero surge.

    2. Volumetric expansion of primary water into/out of pressurizer:

           surge_volume_rate = β_T · V_loop · dT_mean/dt

       ``M_hot + M_cold`` is the water inventory of the same ``V_loop``
       (by default ``V_loop · ρ_ref``; see ``LoopParams``), so this
       reduces to β_T · (Q_core − Q_sg) / (ρ_ref · c_p): the surge volume
       for a given heat imbalance does not depend on the size of the
       loop. If a user overrides the thermal masses so they no longer
       equal the inventory of ``V_loop``, the two parameters describe
       different water and the surge prediction inherits that
       inconsistency.

       Volume expanding *out of* the loop pipes goes *into* the
       pressurizer (same sign convention: positive = insurge).

    3. Convert volumetric to mass flow with direction-branched ρ:

       - Insurge (surge_volume_rate ≥ 0): hot-leg subcooled liquid
         enters → ρ_hotleg(P, T_hot) from CoolProp.
       - Outsurge (surge_volume_rate < 0): saturated liquid leaves the
         bottom of the pressurizer → ρ_l_sat.

       The asymmetry is real: at design (15.5 MPa, T_hot = 597.7 K)
       CoolProp gives ρ_hotleg ≈ 668 kg/m³ vs. ρ_l_sat ≈ 594 kg/m³, an
       ~11 % gap. Using a single value would misstate the mass carried by
       a given surge volume by about that much in one direction.

    References
    ----------
    Todreas & Kazimi Vol. 1, §6.2 Eq. 6-13 (energy balance form on a
    rigid control volume); §6.4 (volumetric expansion under heating).
    Public cross-check: NRC PWR Systems manual for surge behavior, and
    Yan §5.2 for ``m_dot = rho * volume_flow`` and control-volume balances.
    """
    lp = loop_params

    # Mass-weighted mean temperature rate of the whole loop inventory
    # (sum of the two leg energy balances; see Notes step 1). Exact for
    # any M_hot, M_cold. Equals d(T_avg)/dt of the published arithmetic
    # T_avg only when M_hot = M_cold (the default).
    M_total = lp.M_hot + lp.M_cold
    dT_mean_dt = (Q_fuel_to_coolant - Q_sg) / (M_total * lp.c_p)

    # Volumetric expansion of primary water into the pressurizer.
    # SIMPLIFICATION: β_T_primary frozen at design (3.3e-3 /K; CoolProp
    # gives 3.26e-3 at 583 K, 15.5 MPa). The real value rises from
    # 2.67e-3 /K at 568 K to 4.27e-3 /K at 598 K, so the frozen value
    # over-predicts surge magnitude when the loop is colder than 583 K and
    # under-predicts it when hotter (see LoopParams.beta_T_primary).
    surge_volume_rate = lp.beta_T_primary * lp.V_loop * dT_mean_dt

    # Direction-branched density.
    if surge_volume_rate >= 0.0:
        # Insurge: hot-leg subcooled liquid enters at primary P, T_hot.
        rho_surge = coolprop.density_PT(P=P_primary, T=T_hotleg)
    else:
        # Outsurge: saturated liquid leaves at the pressurizer's
        # current saturation density.
        rho_surge = rho_l_sat

    return rho_surge * surge_volume_rate
