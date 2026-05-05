"""Point kinetics reactor core — fidelity level L1.

Models a PWR core as a single point (no spatial detail). Tracks neutron
population, six delayed neutron precursor groups, and a single lumped fuel
temperature. Provides Doppler and moderator temperature feedback.

Physics specification: see ``.docs/design.md`` §5.1.

References
----------
Lamarsh, J. R. and Baratta, A. J. *Introduction to Nuclear Engineering*,
3rd ed., Prentice Hall, 2001. (Point kinetics: Ch. 7. Feedback: Ch. 9.)

Duderstadt, J. J. and Hamilton, L. J. *Nuclear Reactor Analysis*, Wiley,
1976. (Point kinetics derivation: Ch. 6.)

Keepin, G. R. *Physics of Nuclear Kinetics*, Addison-Wesley, 1965.
(Six-group delayed neutron data for U-235 thermal fission.)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class CoreParams:
    """Physical and design parameters for a point-kinetics PWR core.

    All fields have L1 placeholder defaults representative of a generic large
    U-235 PWR (~3000 MWth). Values are illustrative and chosen so that the
    design steady state is self-consistent (see ``__post_init__``).

    Parameters
    ----------
    beta_i : np.ndarray, shape (6,)
        Delayed neutron yield per precursor group [dimensionless].
        Sum is the total delayed neutron fraction beta ≈ 0.0065 for U-235.
    lambda_i : np.ndarray, shape (6,)
        Decay constant per precursor group [1/s].
    Lambda : float
        Prompt neutron generation time [s]. Capital lambda; not the same as
        the decay constants ``lambda_i``.
    P_design : float
        Design thermal power [W].
    alpha_f : float
        Doppler coefficient of reactivity [1/K]. Negative for a stable
        reactor (hotter fuel reduces reactivity).
    alpha_m : float
        Moderator temperature coefficient of reactivity [1/K]. Negative for
        a well-designed PWR.
    T_fuel_ref : float
        Fuel reference temperature [K]. Doppler feedback is zero at this
        temperature by construction.
    T_cool_ref : float
        Coolant reference temperature [K]. Moderator feedback is zero at
        this temperature by construction.
    M_fuel : float
        Total fuel mass, lumped [kg].
    c_p_fuel : float
        Fuel specific heat [J/(kg·K)].
    hA_fc : float, optional
        Lumped fuel-to-coolant heat transfer coefficient [W/K]. If None,
        derived in ``__post_init__`` so the steady-state energy balance
        closes exactly: ``P_design = hA_fc * (T_fuel_ref - T_cool_ref)``.

    Notes
    -----
    The class is frozen, but ``__post_init__`` uses ``object.__setattr__`` to
    fill in the derived ``hA_fc`` default. This is the standard pattern for
    frozen dataclasses with derived fields.
    """

    # SIMPLIFICATION: 6-group delayed neutron approximation.
    # Real fission produces hundreds of distinct precursor isotopes (Br-87,
    # I-137, Cs-141, ...), each with its own half-life and yield. We bin
    # them into 6 effective groups by half-life range, following Keepin
    # (1965). Each beta_i / lambda_i pair represents the lumped behavior of
    # all real precursors in that group's half-life range. This is the
    # standard practice in point kinetics and is accurate to within ~1% for
    # typical reactor dynamics.
    #
    # Values: U-235 thermal fission, Lamarsh Table 7.3 / Keepin 1965.
    beta_i: np.ndarray = field(
        default_factory=lambda: np.array(
            [
                0.000215,  # group 1 (longest-lived, ~55 s half-life)
                0.001424,  # group 2 (~22 s)
                0.001274,  # group 3 (~6 s)
                0.002568,  # group 4 (~2 s)
                0.000748,  # group 5 (~0.5 s)
                0.000273,  # group 6 (shortest-lived, ~0.2 s)
            ]
        )
    )  # delayed neutron yields per group [dimensionless], sum ≈ 0.0065

    lambda_i: np.ndarray = field(
        default_factory=lambda: np.array(
            [
                0.0124,  # group 1 [1/s]
                0.0305,  # group 2
                0.111,  # group 3
                0.301,  # group 4
                1.14,  # group 5
                3.01,  # group 6
            ]
        )
    )  # decay constants per group [1/s]

    # Prompt neutron generation time. Capital Lambda by reactor physics
    # convention; do not confuse with the lambda_i decay constants above.
    # Source: typical thermal reactor value, Lamarsh §7.4. The reactor's
    # response to reactivity bumps is set by the ratio rho/Lambda for the
    # prompt term and by lambda_i for the delayed term.
    Lambda: float = 2.0e-5  # [s]

    # Design thermal power. ~3000 MWth, large 4-loop PWR.
    P_design: float = 3.0e9  # [W]

    # Doppler coefficient — change in reactivity per unit fuel temperature
    # change. Negative because hotter UO2 broadens absorption resonances,
    # capturing more neutrons. This is the primary fast feedback that lets
    # the reactor self-regulate against power excursions on millisecond
    # timescales (hotter fuel happens fast; coolant heating is slower).
    # Representative value, Lamarsh §9.5.
    alpha_f: float = -2.5e-5  # [1/K]

    # Moderator temperature coefficient — change in reactivity per unit
    # coolant temperature change. Negative for a properly-designed PWR
    # because hotter water is less dense and moderates neutrons less
    # effectively, reducing reactivity.
    alpha_m: float = -5.0e-5  # [1/K]

    # Reference temperatures: Doppler and moderator feedback contribute
    # exactly zero reactivity at these temperatures by construction. The
    # design steady state holds T_fuel and T_cool here.
    T_fuel_ref: float = 900.0  # [K] (~627 °C average fuel temperature)
    T_cool_ref: float = 580.0  # [K] (~307 °C; T_avg of primary loop)

    # Fuel thermal mass for the lumped energy balance.
    M_fuel: float = 1.0e5  # [kg] total fuel mass
    c_p_fuel: float = 300.0  # [J/(kg·K)] UO2 specific heat (representative)

    # Lumped fuel-to-coolant heat transfer coefficient. None means "derive
    # so the steady-state energy balance closes exactly" — see
    # __post_init__. Override by passing an explicit value.
    hA_fc: float | None = None  # [W/K]

    def __post_init__(self) -> None:
        """Derive ``hA_fc`` from steady-state self-consistency if not given.

        At the design point, the fuel temperature derivative must be zero:

            P_design = hA_fc * (T_fuel_ref - T_cool_ref)

        Solving for ``hA_fc`` gives the value below. This guarantees the
        ``initial_state()`` produced by ``PointKineticsCore`` is a true
        equilibrium of the equations.
        """
        if self.hA_fc is None:
            derived = self.P_design / (self.T_fuel_ref - self.T_cool_ref)
            # Frozen dataclass; bypass the freeze to set the derived default.
            object.__setattr__(self, "hA_fc", derived)
