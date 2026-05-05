"""Steam generator (heat exchanger only) — fidelity level L1.

Models the heat exchanger between the primary and secondary loops as a single
algebraic relation: Q_sg = UA * (T_primary - T_secondary). No state, no thermal
lag, no two-phase modeling. The entire vessel — typically containing thousands
of tubes the size of a small office building — collapses to one equation.

Physics specification: see ``.docs/design.md`` §5.3.

References
----------
Lamarsh, J. R. and Baratta, A. J. *Introduction to Nuclear Engineering*, 3rd ed.,
Prentice Hall, 2001. (PWR steam generator overview, Ch. 4.)

Todreas, N. E. and Kazimi, M. S. *Nuclear Systems Vol. 1: Thermal Hydraulic
Fundamentals*, 2nd ed., CRC Press, 2012. (Heat exchanger sizing.)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SGParams:
    """Parameters for the L1 steam generator.

    Parameters
    ----------
    T_primary_ref : float
        Primary-side reference temperature [K], typically the loop's T_avg_ref.
    T_secondary_ref : float
        Secondary-side reference temperature [K], typically the sink's T_secondary.
    Q_design : float
        Design heat duty [W], typically the core's P_design.
    UA : float, optional
        Lumped heat transfer coefficient times area [W/K]. If None, derived in
        ``__post_init__`` to close the steady-state energy balance:
        ``UA = Q_design / (T_primary_ref - T_secondary_ref)``.

    Notes
    -----
    "UA" is the standard heat exchanger lumped product: U (overall heat transfer
    coefficient, [W/(m²·K)]) times A (heat transfer area, [m²]). At L1 it's a
    single constant; in reality it varies with primary flow, secondary flow,
    fouling buildup over years of operation, and water level on the secondary
    side. Real-world value for a large PWR SG: ~1.4 × 10⁸ W/K, meaning a 22 K
    primary-secondary ΔT moves ~3 GW of heat.

    The class is frozen, but ``__post_init__`` uses ``object.__setattr__`` to
    fill in the derived ``UA`` default. Standard pattern for frozen dataclasses
    with derived fields.
    """

    # Reference temperatures: design point where Q_sg = Q_design exactly. At
    # these temperatures the steady-state energy balance closes by construction.
    T_primary_ref: float = 580.0  # [K] match the primary loop's T_avg_ref
    T_secondary_ref: float = 558.0  # [K] match the sink's T_secondary

    # Design heat duty. ~3000 MWth, large 4-loop PWR.
    Q_design: float = 3.0e9  # [W]

    # Lumped heat transfer. None means "derive from steady-state self-consistency"
    # — see __post_init__.
    UA: float | None = None  # [W/K]

    def __post_init__(self) -> None:
        """Derive ``UA`` if not supplied so steady-state heat removal matches Q_design.

        At the design point we want:

            Q_design = UA * (T_primary_ref − T_secondary_ref)

        Solving for UA gives the value used here. This guarantees that at
        coupled-plant design conditions, the SG removes exactly Q_design and the
        primary loop's energy balance closes.
        """
        if self.UA is None:
            derived = self.Q_design / (self.T_primary_ref - self.T_secondary_ref)
            # Frozen dataclass; bypass the freeze to set the derived default.
            object.__setattr__(self, "UA", derived)


class SteamGenerator:
    """L1 steam generator: pure algebraic heat exchanger.

    Implements ``Q_sg = UA * (T_primary - T_secondary)``. No state, no thermal
    lag, no two-phase secondary side. Heat removal is determined entirely by the
    instantaneous primary-secondary temperature difference and the lumped UA.

    Ports in (passed via the ``inputs`` dict to ``outputs()`` and ``telemetry()``):
        T_primary : float [K]
            Primary-side temperature, typically the loop's T_avg.
        T_secondary : float [K]
            Secondary-side temperature, typically the sink's T_secondary.

    Ports out (returned by ``outputs()``):
        Q_sg : float [W]
            Heat moved from primary to secondary side at this instant.

    State vector: empty (state_size = 0).

    Notes
    -----
    "Algebraic" means the output is a function of inputs at the current instant,
    with no time history. The component has no equations involving derivatives;
    it just evaluates a formula whenever asked.

    SIMPLIFICATIONS (also called out at their use sites):
      * Single average ΔT replaces log mean temperature difference (LMTD), which
        is the more accurate form when ΔT varies along the tube length.
      * No tube metal heat capacity, so no thermal lag between primary and
        secondary temperature changes.
      * No two-phase modeling on the secondary side; "steam generation" doesn't
        actually appear in the equations — heat just disappears into the sink.
      * No water level dynamics on the secondary side (M4 will add these).
      * Constant UA (real value depends on flow, fouling, level).
    """

    state_size: int = 0
    state_labels: tuple[str, ...] = ()

    def __init__(self, params: SGParams) -> None:
        """Construct a steam generator with the given parameters.

        Parameters
        ----------
        params : SGParams
        """
        self.params = params

    def initial_state(self) -> np.ndarray:
        """Return an empty state vector (SG has no state at L1)."""
        return np.empty(0)

    def derivatives(self, state: np.ndarray, inputs: dict | None = None) -> np.ndarray:
        """Return an empty derivatives vector (SG has no evolving state at L1)."""
        return np.empty(0)

    def outputs(self, state: np.ndarray, inputs: dict | None = None) -> dict:
        """Compute Q_sg from the current primary and secondary temperatures.

        Parameters
        ----------
        state : np.ndarray
            Ignored — SG has no state at L1.
        inputs : dict
            Required keys:

            - ``T_primary`` : float [K] — primary-side temperature
            - ``T_secondary`` : float [K] — secondary-side temperature

        Returns
        -------
        dict
            ``{"Q_sg": float [W]}``

        Raises
        ------
        TypeError
            If ``inputs`` is None (SG outputs require inputs).
        KeyError
            If ``inputs`` is missing required keys.
        """
        if inputs is None:
            raise TypeError("SteamGenerator.outputs requires `inputs` with T_primary and T_secondary")
        # SIMPLIFICATION: Q = UA * ΔT (single average ΔT, not log mean).
        # Real heat exchangers use LMTD = (ΔT_in − ΔT_out) / ln(ΔT_in / ΔT_out)
        # which is more accurate when the ΔT varies along the tube length.
        T_primary = inputs["T_primary"]
        T_secondary = inputs["T_secondary"]
        Q_sg = self.params.UA * (T_primary - T_secondary)
        return {"Q_sg": Q_sg}

    def telemetry(self, state: np.ndarray, inputs: dict | None = None) -> dict:
        """Return a diagnostic dict — Q_sg plus the temperature components.

        If ``inputs`` is None, all input-derived keys are reported as None.
        The runner and engine always pass ``inputs``.

        Returns
        -------
        dict
            Keys: ``Q_sg``, ``T_primary``, ``T_secondary``, ``delta_T``.
        """
        if inputs is None:
            return {
                "Q_sg": None,
                "T_primary": None,
                "T_secondary": None,
                "delta_T": None,
            }
        T_primary = inputs["T_primary"]
        T_secondary = inputs["T_secondary"]
        delta_T = T_primary - T_secondary
        return {
            "Q_sg": self.params.UA * delta_T,
            "T_primary": T_primary,
            "T_secondary": T_secondary,
            "delta_T": delta_T,
        }
