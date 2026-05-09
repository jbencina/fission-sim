"""Shared helper for computing primary→pressurizer surge mass flow.

Pulled out into its own module so both ``primary_loop.py`` and
``pressurizer.py`` can compute m_dot_surge identically without
creating a circular import (pressurizer.py already imports LoopParams
from primary_loop.py).

The math is the same as before — it was previously inlined inside
``Pressurizer._compute_m_dot_surge`` — but extracting it lets both
modules apply it to their respective derivatives, keeping the system
mass-conservation invariant ``M_loop + M_pzr = const`` to solver
tolerance.

Conservation rationale
----------------------
The engine calls ``Pressurizer.outputs(state)`` *without* inputs in
the state-derived pass (because the pressurizer is classified as
state-derived so its pressure P is available to the controller early).
That means the ``m_dot_surge`` value published by the pressurizer's
outputs port is always 0.0 — the engine has no way to provide the
inputs needed to compute the real surge. When the loop read that 0.0
via wiring, its ``dM_loop/dt = -0.0 - m_dot_spray`` never tracked the
actual surge, while ``Pressurizer.derivatives()`` (which *does* receive
its inputs from the ODE integrator) correctly applied the real surge to
``dM_pzr/dt``. The result was a 1,215 kg mass drift in a 300 s cooldown.

Fix: the loop now computes ``m_dot_surge`` itself using the same helper,
calling it with ``P_primary`` (from ``pzr.P``, a state-derived output
available in the state-derived pass) rather than the old wired port.
Both modules call the same pure function with the same inputs at the
same time step → conservation holds exactly to solver tolerance.
"""

from __future__ import annotations

from fission_sim.physics import coolprop
from fission_sim.physics.primary_loop import LoopParams


def compute_m_dot_surge(
    *,
    power_thermal: float,
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
    power_thermal : float
        Heat from the core [W].
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

    1. Compute dT_avg/dt from the loop's energy imbalance:

           dT_avg/dt = (Q_core − Q_sg) / ((M_hot + M_cold) · c_p)

       SIMPLIFICATION: symmetric thermal-mass approximation
       (M_hot ≈ M_cold). Exact for default L1 parameters where they're
       equal; off by a few percent if the user makes them asymmetric.

    2. Volumetric expansion of primary water into/out of pressurizer:

           surge_volume_rate = β_T · V_loop · dT_avg/dt

       Volume expanding *out of* the loop pipes goes *into* the
       pressurizer (same sign convention: positive = insurge).

    3. Convert volumetric to mass flow with direction-branched ρ:

       - Insurge (surge_volume_rate ≥ 0): hot-leg subcooled liquid
         enters → ρ_hotleg(P, T_hot) from CoolProp.
       - Outsurge (surge_volume_rate < 0): saturated liquid leaves the
         bottom of the pressurizer → ρ_l_sat.

       The asymmetry is real and important: at design ρ_hotleg ≈ 715
       kg/m³ vs. ρ_l_sat ≈ 595 kg/m³ (~17 % gap). Using a single value
       would inflate the conservation-test residual to the size of the
       test tolerance.

    References
    ----------
    Todreas & Kazimi Vol. 1, §6.2 Eq. 6-13 (energy balance form on a
    rigid control volume); §6.4 (volumetric expansion under heating).
    """
    lp = loop_params

    # SIMPLIFICATION: symmetric thermal mass — assumes M_hot ≈ M_cold so
    # dT_avg/dt = (Q_core − Q_sg) / (M_total · c_p). At default L1
    # parameters M_hot = M_cold = 1.5e4 kg, so the approximation is exact.
    # If the user makes them asymmetric, the surge prediction will be off
    # by a few percent.
    M_total = lp.M_hot + lp.M_cold
    dT_avg_dt = (power_thermal - Q_sg) / (M_total * lp.c_p)

    # Volumetric expansion of primary water into the pressurizer.
    # SIMPLIFICATION: β_T_primary frozen at design (~3.3e-3 /K from
    # CoolProp at 583 K, 15.5 MPa, verified Task A1). The real value
    # varies ~50 % across the 568–598 K operating range; frozen-at-
    # design under-predicts surge magnitude during cooldowns and
    # over-predicts during heatups. L2 reads β_T from CoolProp every step.
    surge_volume_rate = lp.beta_T_primary * lp.V_loop * dT_avg_dt

    # Direction-branched density.
    if surge_volume_rate >= 0.0:
        # Insurge: hot-leg subcooled liquid enters at primary P, T_hot.
        rho_surge = coolprop.density_PT(P=P_primary, T=T_hotleg)
    else:
        # Outsurge: saturated liquid leaves at the pressurizer's
        # current saturation density.
        rho_surge = rho_l_sat

    return rho_surge * surge_volume_rate
