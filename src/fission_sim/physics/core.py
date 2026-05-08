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
    # Equals ℓ/k_eff (mean generation time) where ℓ is the prompt neutron
    # lifetime; the two differ by k_eff (≈ 1 here). The reactor's response
    # to reactivity bumps is set by the ratio rho/Lambda for the prompt
    # term and by lambda_i for the delayed term.
    # Source: Bell & Glasstone, "Nuclear Reactor Theory" §9.2 — typical
    # thermal LWR Lambda ~ 30-50 µs; Duderstadt & Hamilton Table 6.1.
    Lambda: float = 4.0e-5  # [s]

    # Design thermal power. ~3000 MWth, large 4-loop PWR.
    P_design: float = 3.0e9  # [W]

    # Doppler coefficient — change in reactivity per unit fuel temperature
    # change. Negative because hotter UO2 broadens absorption resonances,
    # capturing more neutrons (Doppler broadening). This is the primary
    # fast feedback that lets the reactor self-regulate against power
    # excursions on millisecond timescales (hotter fuel happens fast;
    # coolant heating is slower).
    # Source: Duderstadt & Hamilton §6.5 derives the Doppler coefficient;
    # IAEA-TECDOC published range for PWR UO2 fuel is α_f = -2 to -4×10⁻⁵
    # /K depending on fuel temperature and burnup. Lamarsh & Baratta §9.5.
    alpha_f: float = -2.5e-5  # [1/K]

    # Moderator temperature coefficient — change in reactivity per unit
    # coolant temperature change. Negative for a properly-designed PWR at
    # hot full power because hotter water is less dense and moderates
    # neutrons less effectively, reducing reactivity.
    # SIMPLIFICATION: real PWRs can have α_m positive at low boron
    # concentrations or beginning-of-cycle low-power conditions; operators
    # confirm α_m is negative before low-power testing (a Tech Spec
    # requirement). At L1 we model only the hot-full-power negative regime.
    # Source: Duderstadt & Hamilton §6.5; published PWR range -1 to
    # -5×10⁻⁵ /K at hot full power.
    alpha_m: float = -5.0e-5  # [1/K]

    # Reference temperatures: Doppler and moderator feedback contribute
    # exactly zero reactivity at these temperatures by construction. The
    # design steady state holds T_fuel and T_cool here.
    # T_fuel_ref is the volume-averaged fuel temperature; real PWRs have
    # centerline ~1500-2000 K and surface ~700 K with volume-average
    # ~1100 K (Fink 2000, J. Nucl. Mater. 279; Todreas & Kazimi §8.5).
    # SIMPLIFICATION: the *Doppler-effective* fuel temperature (flux-
    # weighted, typically 0.7·T_centerline + 0.3·T_surface ≈ 1200-1400 K)
    # is what physically drives Doppler. At L1 we use the volume-average;
    # L2 multi-region fuel models would split centerline / surface.
    T_fuel_ref: float = 1100.0  # [K] (~827 °C volume-averaged fuel temp)
    T_cool_ref: float = 583.0  # [K] (~310 °C; matches loop's T_avg_ref)

    # Fuel thermal mass for the lumped energy balance.
    M_fuel: float = 1.0e5  # [kg] total fuel mass
    # UO2 specific heat. Fink (2000) "Thermophysical properties of uranium
    # dioxide", J. Nucl. Mater. 279, gives c_p ≈ 235 at 300 K, ~305 at
    # 900 K, ~330 at 1500 K (Bredig peak above 2000 K). 300 J/(kg·K) is
    # representative of the lumped average around T_fuel_ref.
    c_p_fuel: float = 300.0  # [J/(kg·K)]

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


class PointKineticsCore:
    """Point-kinetics PWR core (L1 fidelity).

    Implements the standard point kinetics equations with six delayed
    neutron groups, a single lumped fuel temperature, and Doppler +
    moderator temperature feedback.

    The class owns its parameters and equations. It does NOT own
    time-evolving state. State lives in a numpy array passed in by the
    caller (a driver script for now, the simulation engine eventually).
    Every method that needs current-state numbers takes them as an
    argument.

    Ports in (passed to ``derivatives()`` via the ``inputs`` dict):
        rho_rod : float [dimensionless]
            Reactivity contribution from control rods. In a real plant,
            this comes from the rod controller component.
        T_cool : float [K]
            Coolant temperature seen by the core. In a real plant, this
            comes from the primary loop.

    Ports out (returned by ``outputs()``):
        power_thermal : float [W]
            Core thermal power, ``n * P_design``.
        T_fuel : float [K]
            Average fuel temperature.

    State vector (length ``state_size`` = 8, names in ``state_labels``):
        index 0     : n        — neutron population [dimensionless,
                                  normalized so n=1 at design power]
        index 1..6  : C1..C6   — delayed neutron precursor concentrations
                                  [dimensionless, same scaling as n]
        index 7     : T_fuel   — average fuel temperature [K]

    Notes
    -----
    The "delayed neutron precursors" Ci are not specific isotopes. Real
    fission produces hundreds of distinct precursor isotopes; the standard
    practice (since Keepin 1965) bins them into 6 effective groups by
    half-life range. Each Ci is the lumped concentration of all real
    precursors in group i's range. See ``CoreParams`` for the group
    constants.

    Reactivity convention: stored internally as a dimensionless number
    (rho = (k - 1)/k). Operators read/write it in pcm = 10⁻⁵ for
    convenience, but no conversion happens inside the class.
    """

    state_size: int = 8
    state_labels: tuple[str, ...] = (
        "n",
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
        "T_fuel",
    )

    input_ports: tuple[str, ...] = ("rho_rod", "T_cool")
    output_ports: tuple[str, ...] = ("power_thermal", "T_fuel")

    def __init__(self, params: CoreParams) -> None:
        """Construct a core with the given parameters.

        Parameters
        ----------
        params : CoreParams
            Frozen parameter set. Held as ``self.params`` for the lifetime
            of the object.
        """
        self.params = params

    def initial_state(self) -> np.ndarray:
        """Return the design-point steady-state vector.

        At the design point all derivatives are zero by construction:

        - ``n = 1`` (normalized neutron population at design power)
        - ``C_i = beta_i / (Lambda * lambda_i)`` (precursor steady state
          from setting ``dC_i/dt = 0``)
        - ``T_fuel = T_fuel_ref`` (so Doppler reactivity is zero)

        The coolant temperature seen by the core at this steady state is
        ``T_cool_ref`` (provided by the caller via ``inputs``); the moderator
        and rod reactivities are zero at design conditions.

        Returns
        -------
        np.ndarray, shape (8,)
            State vector laid out as ``state_labels``.
        """
        p = self.params
        s = np.empty(self.state_size)
        s[0] = 1.0
        # Precursor steady state from dC_i/dt = (beta_i/Lambda)*n - lambda_i*C_i = 0
        s[1:7] = p.beta_i / (p.Lambda * p.lambda_i)
        s[7] = p.T_fuel_ref
        return s

    def derivatives(self, state: np.ndarray, inputs: dict) -> np.ndarray:
        """Compute dstate/dt for the point kinetics + fuel thermal model.

        This is a **pure function** of ``state`` and ``inputs`` — it must
        not read or write any per-step state on ``self``. The adaptive ODE
        solver may call this function speculatively many times per step
        with hypothetical states it later discards.

        Parameters
        ----------
        state : np.ndarray, shape (8,)
            Current state vector laid out as ``state_labels``.
        inputs : dict
            Required keys:

            - ``rho_rod`` : float [dimensionless] — reactivity from
              control rods.
            - ``T_cool`` : float [K] — coolant temperature seen by the core.

        Returns
        -------
        np.ndarray, shape (8,)
            ``dstate/dt`` matching the indices of ``state``.

        Notes
        -----
        Equations (see ``.docs/design.md`` §5.1 and Lamarsh §7):

            dn/dt    = ((rho - beta) / Lambda) * n  +  sum_i lambda_i * C_i
            dC_i/dt  = (beta_i / Lambda) * n  -  lambda_i * C_i
            dT_f/dt  = (P_thermal - Q_to_coolant) / (M_fuel * c_p_fuel)

        with total reactivity:

            rho = rho_rod
                + alpha_f * (T_fuel - T_fuel_ref)        [Doppler]
                + alpha_m * (T_cool - T_cool_ref)        [moderator]

        and:

            P_thermal    = n * P_design
            Q_to_coolant = hA_fc * (T_fuel - T_cool)
        """
        p = self.params

        # --- decode the state slice into named locals ---
        n = state[0]
        C = state[1:7]  # view of state, not a copy — do not mutate in-place
        T_fuel = state[7]

        # --- decode inputs ---
        rho_rod = inputs["rho_rod"]
        T_cool = inputs["T_cool"]

        # --- total reactivity (Lamarsh eq 9.39) ---
        # rho is dimensionless. "pcm" (per cent mille = 1e-5) is just a
        # display unit; nothing internal uses it.
        rho_doppler = p.alpha_f * (T_fuel - p.T_fuel_ref)
        rho_moderator = p.alpha_m * (T_cool - p.T_cool_ref)
        rho = rho_rod + rho_doppler + rho_moderator

        # --- point kinetics equations (Lamarsh eq 7.26-7.28) ---
        # dn/dt has two parts:
        #   1) ((rho - beta) / Lambda) * n: net effect of prompt neutrons
        #      (becomes positive only when rho > beta = "prompt critical",
        #      i.e. the runaway threshold; we stay well below it)
        #   2) sum(lambda_i * C_i): delayed neutrons being released by
        #      precursor decay
        beta_total = p.beta_i.sum()
        dn_dt = ((rho - beta_total) / p.Lambda) * n + np.sum(p.lambda_i * C)

        # dC_i/dt: each precursor group is produced from fission at rate
        # (beta_i / Lambda) * n, and decays at its own rate lambda_i.
        dC_dt = (p.beta_i / p.Lambda) * n - p.lambda_i * C

        # --- fuel thermal energy balance (single lumped node) ---
        # SIMPLIFICATION: lumped fuel temperature. Real fuel pellets have a
        # large radial gradient (centerline can be ~1500 K hotter than the
        # surface). One average T_fuel loses that detail; sufficient for
        # bulk dynamics but not for predicting fuel failure.
        P_thermal = n * p.P_design
        Q_to_coolant = p.hA_fc * (T_fuel - T_cool)
        dT_fuel_dt = (P_thermal - Q_to_coolant) / (p.M_fuel * p.c_p_fuel)

        # --- assemble derivative vector matching state layout ---
        dstate = np.empty(self.state_size)
        dstate[0] = dn_dt
        dstate[1:7] = dC_dt
        dstate[7] = dT_fuel_dt
        return dstate

    def outputs(self, state: np.ndarray, inputs: dict | None = None) -> dict:
        """Return the values consumed by downstream components.

        This is the minimal port-out interface — only what the next
        component in the plant needs to read. ``telemetry()`` is the
        richer dict for logging and visualization.

        Parameters
        ----------
        state : np.ndarray, shape (8,)
        inputs : dict, optional
            Unused for this component (the core's outputs depend only on
            state). Accepted for API uniformity with components whose
            outputs depend on inputs (e.g. ``SteamGenerator``).

        Returns
        -------
        dict
            ``{"power_thermal": float [W], "T_fuel": float [K]}``
        """
        return {
            "power_thermal": state[0] * self.params.P_design,
            "T_fuel": state[7],
        }

    def telemetry(self, state: np.ndarray, inputs: dict | None = None) -> dict:
        """Return a rich diagnostic dict for logging and visualization.

        Superset of ``outputs()``. Includes the reactivity decomposition
        (rod, Doppler, moderator, total) and individual precursor
        concentrations.

        Parameters
        ----------
        state : np.ndarray, shape (8,)
        inputs : dict, optional
            If provided (with the same keys as ``derivatives``), the
            input-dependent reactivity components are computed. If
            omitted, ``rho_rod``, ``rho_moderator``, and ``rho_total`` are
            reported as ``None``; ``rho_doppler`` is always computed
            because it depends only on state.

        Returns
        -------
        dict
            Keys: ``power_thermal``, ``T_fuel``, ``n``, ``C1``..``C6``,
            ``rho_total``, ``rho_rod``, ``rho_doppler``, ``rho_moderator``,
            ``startup_rate_dpm``. The startup rate is ``None`` when
            ``inputs`` is omitted (it depends on dn/dt which needs
            ``rho_rod`` and ``T_cool``).
        """
        p = self.params
        n = state[0]
        T_fuel = state[7]
        C = state[1:7]

        # Doppler depends only on state and is always reported.
        rho_doppler = p.alpha_f * (T_fuel - p.T_fuel_ref)

        if inputs is not None:
            rho_rod = inputs["rho_rod"]
            rho_moderator = p.alpha_m * (inputs["T_cool"] - p.T_cool_ref)
            rho_total = rho_rod + rho_doppler + rho_moderator
            # Startup rate in decades-per-minute (DPM) — what an operator
            # watches on the intermediate-range startup-rate meter during
            # cold-startup approach to criticality. SUR = (1/n)·dn/dt
            # converts to "decades per minute" via:
            #   SUR_dpm = (60 / ln(10)) · (1/n) · dn/dt
            # We compute dn/dt here (rather than calling derivatives) so
            # this method stays a pure read of state + inputs.
            beta_total = p.beta_i.sum()
            dn_dt = ((rho_total - beta_total) / p.Lambda) * n + (p.lambda_i * C).sum()
            if n > 1e-30:
                startup_rate_dpm = (60.0 / np.log(10.0)) * (dn_dt / n)
            else:
                startup_rate_dpm = 0.0
        else:
            rho_rod = None
            rho_moderator = None
            rho_total = None
            startup_rate_dpm = None

        return {
            "power_thermal": n * p.P_design,
            "T_fuel": T_fuel,
            "n": n,
            "C1": state[1],
            "C2": state[2],
            "C3": state[3],
            "C4": state[4],
            "C5": state[5],
            "C6": state[6],
            "rho_total": rho_total,
            "rho_rod": rho_rod,
            "rho_doppler": rho_doppler,
            "rho_moderator": rho_moderator,
            "startup_rate_dpm": startup_rate_dpm,
        }
