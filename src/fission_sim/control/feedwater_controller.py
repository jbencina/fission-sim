"""Three-element steam-generator level controller.

This module represents the L1 feedwater controller used for steam-generator
secondary-side inventory control. In a pressurized-water reactor (PWR), the
operator cares that the U-tubes stay covered by water while enough steam space
remains above the separators. The controller therefore does not wait for level
to drift far before acting: it uses steam outflow as a feed-forward estimate
of the feedwater needed right now, then trims that flow demand with the measured
water-level error.

Fidelity level
--------------
L1. The controller is a proportional-integral level trim around an ideal
flow-matching feed-forward term. In plain words, the simplified three-element
scheme is:

1. steam-flow feed-forward: replace the steam leaving the shell,
2. feedwater-flow matching: command the feedwater train to match that outflow,
3. level trim: add or subtract flow if the collapsed water level is off target.

Flow matching alone is not enough because any small sensor, valve, or property
bias slowly integrates into inventory drift. Level-only control is also too
slow for a steam generator because level responds after mass and boiling
inventory have already moved. The feed-forward term handles fast load changes;
the level trim removes long-term bias.

The controller also includes back-calculation anti-windup. "Windup" means the
integral term keeps storing a larger and larger correction even though the
feedwater demand is already pinned at a physical limit. Back-calculation fixes
that smoothly by comparing the raw PI demand with the clipped demand and
bleeding the integral back toward a value the feedwater system can actually
deliver.

# SIMPLIFICATION: no shrink/swell compensation is modeled. Real indicated
steam-generator level changes when steam voids expand or collapse after a
power change; this L1 model controls collapsed liquid volume fraction.
# SIMPLIFICATION: steam and dump flows are ideal measurements with no sensor
lag, calibration error, or separate feedwater-flow transmitter dynamics.
# SIMPLIFICATION: the feedwater valve/train dynamics live in the separate
M4 ``FeedwaterSystem`` actuator; this component only computes a demanded mass
flow.

References
----------
Todreas, N. E. and Kazimi, M. S. *Nuclear Systems Vol. 1*, 2nd ed.,
CRC Press, 2012. Ch. 7 describes PWR steam generators and secondary-side
inventory/level control needs.

Yan, J. *Introduction to Engineering Thermodynamics*, §5.2.2 "Mass
Conservation Equations in a Control Volume", for the inlet-minus-outlet mass
balance behind the steam-flow feed-forward term:
https://pressbooks.bccampus.ca/thermo1/chapter/5-2-steady-flow-and-transient-flow/

Åström, K. J. and Murray, R. M. *Feedback Systems*, 2nd ed. §11.4
"Integrator Windup" describes integrator windup and back-calculation/tracking
anti-windup:
https://fbswiki.org/wiki/index.php/PID_Control

Åström, K. J. and Hägglund, T. *Advanced PID Control*, ISA, 2006. §3.5
describes practical PID anti-windup by back-calculation.

Public PWR system reference:

U.S. NRC Technical Training Center, *Westinghouse Technology Systems Manual*,
§11.1 "Steam Generator Water Level Control System", pp. 11.1-2-3 (PDF
pp. 4-5) and Fig. 11.1-2, Rev. 0706. This is the public Westinghouse-system
reference for the real narrow-range level, steam-flow, and feedwater-flow
signals that motivate this L1 three-element controller:
https://www.nrc.gov/docs/ML1122/ML11223A293.pdf
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from fission_sim.physics.sg_secondary import SGSecondaryParams


@dataclass(frozen=True)
class FeedwaterControllerParams:
    """Parameters for the L1 three-element feedwater controller.

    Parameters
    ----------
    sg_params : SGSecondaryParams, optional
        Steam-generator shell parameters that provide design steam flow
        ``m_steam_design`` [kg/s].
    K_p : float, optional
        Proportional level gain [kg/s per unit level]. A unit level is the
        full 0-to-1 collapsed liquid fraction.
    K_i : float or None, optional
        Integral level gain [kg/s per second of accumulated unit-level error].
        If None, derived from ``K_p / 300 s``.
    level_setpoint_default : float, optional
        Nominal steam-generator collapsed-level setpoint [-].
    m_fw_max_frac : float, optional
        Maximum demanded feedwater flow as a fraction of design steam flow [-].
    antiwindup_tracking_time : float or None, optional
        Back-calculation tracking time ``T_t`` [s]. If None, derived as one
        tenth of the PI reset time ``K_p / K_i``.

    Raises
    ------
    ValueError
        If a gain, setpoint, maximum-flow fraction, or derived design flow is
        non-finite or outside its physical range.

    Notes
    -----
    Frozen dataclass; ``__post_init__`` derives ``K_i`` and
    ``antiwindup_tracking_time`` with ``object.__setattr__`` when they are
    omitted.
    """

    # Design shell parameters. Provenance: the controller must use the same
    # SGSecondary design flow as the shell/feedwater hardware it supervises.
    sg_params: SGSecondaryParams = field(default_factory=SGSecondaryParams)

    # 3.34e3 kg/s per unit level. Provenance: M4 L1 tuning choice: a 5 %
    # level error should ask for 10 % of the 1669 kg/s design steam flow,
    # K_p = 0.10 * 1669 kg/s / 0.05 ≈ 3.34e3 kg/s per unit level.
    K_p: float = 3.34e3  # [kg/s per unit level]

    # Integral gain. Provenance: M4 L1 tuning choice: 300 s reset time for an
    # educational, slow SG level trim; in PI form K_i = K_p / T_i = K_p / 300 s.
    K_i: float | None = None  # [kg/s per second of accumulated unit-level error]

    # Nominal narrow-range level setpoint. Provenance: M4 L1 tuning choice:
    # the shell starts half full, leaving margin to both tube-uncovery and
    # overfill limits.
    level_setpoint_default: float = 0.5  # [-]

    # Maximum feedwater demand. Provenance: M4 L1 tuning choice: 120 % of
    # design steam flow so the controller has recovery margin above full-load
    # flow.
    m_fw_max_frac: float = 1.2  # [-]

    # Back-calculation tracking time. Provenance: M4 L1 tuning choice,
    # derived by default as one tenth of the PI reset time,
    # T_t = (K_p / K_i) / 10 = 30 s, so the integral tracks actuator
    # saturation much faster than the 300 s level reset without adding an
    # artificially faster mode than the 5 s feedwater actuator.
    antiwindup_tracking_time: float | None = None  # [s]

    def __post_init__(self) -> None:
        """Validate parameters and derive omitted integral settings.

        Parameters
        ----------
        None
            All inputs are dataclass fields.

        Returns
        -------
        None
            Derived values are written to the frozen dataclass when omitted.

        Raises
        ------
        ValueError
            If controller tuning would make the demanded flow or integral
            derivative undefined.

        Notes
        -----
        Governing tuning relationships (standard PI control notation):

            T_i = K_p / K_i
            T_t = T_i / 10

        ``T_i`` is the reset time: after a sustained error, the integral term
        catches up to the proportional term over about ``T_i`` seconds.
        ``T_t`` is the anti-windup tracking time from Åström & Murray §11.4:
        while the actuator is clipped, the stored integral is pulled toward
        the clipped demand over about ``T_t`` seconds.
        """
        K_p = float(self.K_p)
        if not math.isfinite(K_p) or K_p <= 0.0:
            raise ValueError("K_p must be finite and > 0 [kg/s per unit level].")

        if self.K_i is None:
            K_i = K_p / 300.0
        else:
            K_i = float(self.K_i)
        if not math.isfinite(K_i) or K_i <= 0.0:
            raise ValueError("K_i must be finite and > 0 so the PI reset time is positive.")

        reset_time = K_p / K_i
        if not math.isfinite(reset_time) or reset_time <= 0.0:
            raise ValueError("The feedwater controller reset time K_p / K_i must be finite and > 0 [s].")

        level_setpoint_default = float(self.level_setpoint_default)
        if not math.isfinite(level_setpoint_default) or not (0.0 < level_setpoint_default < 1.0):
            raise ValueError("level_setpoint_default must be finite and inside (0, 1).")

        m_fw_max_frac = float(self.m_fw_max_frac)
        if not math.isfinite(m_fw_max_frac) or m_fw_max_frac <= 0.0:
            raise ValueError("m_fw_max_frac must be finite and > 0.")

        m_steam_design = float(self.sg_params.m_steam_design)
        if not math.isfinite(m_steam_design) or m_steam_design <= 0.0:
            raise ValueError("sg_params.m_steam_design must be finite and > 0 [kg/s].")

        if self.antiwindup_tracking_time is None:
            antiwindup_tracking_time = reset_time / 10.0
        else:
            antiwindup_tracking_time = float(self.antiwindup_tracking_time)
        if not math.isfinite(antiwindup_tracking_time) or antiwindup_tracking_time <= 0.0:
            raise ValueError("antiwindup_tracking_time must be finite and > 0 [s].")

        object.__setattr__(self, "K_p", K_p)
        object.__setattr__(self, "K_i", K_i)
        object.__setattr__(self, "level_setpoint_default", level_setpoint_default)
        object.__setattr__(self, "m_fw_max_frac", m_fw_max_frac)
        object.__setattr__(self, "antiwindup_tracking_time", antiwindup_tracking_time)


@dataclass(frozen=True)
class _DemandTerms:
    demand: float
    raw_demand: float
    level_error: float
    level_error_integral: float
    m_fw_max: float
    feedwater_manual: float | None
    mode: str
    saturated: bool


class FeedwaterController:
    """L1 three-element steam-generator level controller.

    Ports in
    --------
    level_sg : float
        Steam-generator collapsed liquid level, ``V_l / V_sec`` [-].
    level_setpoint : float
        Desired collapsed level setpoint [-].
    m_steam : float
        Steam mass flow leaving through the turbine [kg/s].
    m_dump : float
        Steam mass flow leaving through dump/relief paths [kg/s].
    feedwater_manual : float or None
        Manual feedwater demand fraction [-]. ``None`` selects automatic
        three-element control; numeric values are clipped to ``[0, 1]`` and
        scaled by maximum feedwater flow.

    Ports out
    ---------
    m_fw_demand : float
        Feedwater mass-flow demand sent to the feedwater actuator [kg/s].

    State variables
    ---------------
    level_error_integral : float
        Time integral of ``level_setpoint − level_sg`` [s]. A value of
        ``10`` means a one-unit level error integrated for 10 seconds, or a
        0.01 level error integrated for 1000 seconds.

    Notes
    -----
    The component is computed: output demand depends on measured shell level
    and steam flows, so ``outputs_require_inputs = True`` and :meth:`outputs`
    requires an ``inputs`` keyword.
    """

    state_size: int = 1
    state_labels: tuple[str, ...] = ("level_error_integral",)
    input_ports: tuple[str, ...] = ("level_sg", "level_setpoint", "m_steam", "m_dump", "feedwater_manual")
    output_ports: tuple[str, ...] = ("m_fw_demand",)
    outputs_require_inputs: bool = True

    def __init__(self, params: FeedwaterControllerParams) -> None:
        """Construct a feedwater level controller.

        Parameters
        ----------
        params : FeedwaterControllerParams
            Frozen parameter set with design flow and PI tuning constants
            [SI units].
        """
        self.params = params

    def initial_state(self) -> np.ndarray:
        """Return the initial controller state vector.

        Returns
        -------
        np.ndarray, shape (1,)
            ``[0.0]`` for zero accumulated level error [s].
        """
        return np.array([0.0], dtype=float)

    @staticmethod
    def _finite_input(name: str, value: Any) -> float:
        value_float = float(value)
        if not math.isfinite(value_float):
            raise ValueError(f"{name} must be finite before feedwater demand is evaluated.")
        return value_float

    @staticmethod
    def _manual_fraction(feedwater_manual: Any) -> float:
        manual = float(feedwater_manual)
        if not math.isfinite(manual):
            raise ValueError("feedwater_manual must be finite before clipping to [0, 1].")
        return float(np.clip(manual, 0.0, 1.0))

    def _m_fw_max(self) -> float:
        return self.params.m_fw_max_frac * self.params.sg_params.m_steam_design

    def _demand_terms(self, state: np.ndarray, inputs: dict[str, Any]) -> _DemandTerms:
        p = self.params
        integral = self._finite_input("level_error_integral", state[0])
        level_sg = self._finite_input("level_sg", inputs["level_sg"])
        level_setpoint = self._finite_input("level_setpoint", inputs["level_setpoint"])
        m_steam = self._finite_input("m_steam", inputs["m_steam"])
        m_dump = self._finite_input("m_dump", inputs["m_dump"])
        m_fw_max = self._m_fw_max()
        level_error = level_setpoint - level_sg

        if inputs["feedwater_manual"] is not None:
            manual_fraction = self._manual_fraction(inputs["feedwater_manual"])
            manual_raw = float(inputs["feedwater_manual"]) * m_fw_max
            demand = float(np.clip(manual_raw, 0.0, m_fw_max))
            return _DemandTerms(
                demand=demand,
                raw_demand=manual_raw,
                level_error=level_error,
                level_error_integral=integral,
                m_fw_max=m_fw_max,
                feedwater_manual=manual_fraction,
                mode="manual",
                saturated=manual_raw <= 0.0 or manual_raw >= m_fw_max,
            )

        # Governing automatic three-element demand equation (Todreas &
        # Kazimi Ch. 7; NRC WTSM §11.1 real SG level-control signals):
        #
        #     e = level_setpoint − level_sg
        #     m_fw,demand = m_steam + m_dump + K_p · e + K_i · ∫e dt
        #
        # The first two terms are steam-flow feed-forward; the last two terms
        # are the level PI trim that removes long-term inventory drift.
        raw_demand = m_steam + m_dump + p.K_p * level_error + p.K_i * integral
        demand = float(np.clip(raw_demand, 0.0, m_fw_max))
        return _DemandTerms(
            demand=demand,
            raw_demand=raw_demand,
            level_error=level_error,
            level_error_integral=integral,
            m_fw_max=m_fw_max,
            feedwater_manual=None,
            mode="auto",
            saturated=raw_demand <= 0.0 or raw_demand >= m_fw_max,
        )

    def derivatives(self, state: np.ndarray, inputs: dict[str, Any]) -> np.ndarray:
        """Return the level-error-integral derivative.

        Parameters
        ----------
        state : np.ndarray, shape (1,)
            ``[level_error_integral]`` [s].
        inputs : dict
            Required keys are ``level_sg`` [-], ``level_setpoint`` [-],
            ``m_steam`` [kg/s], ``m_dump`` [kg/s], and ``feedwater_manual``
            [-] or None.

        Returns
        -------
        np.ndarray, shape (1,)
            ``[d(level_error_integral)/dt]`` [-]. In automatic mode this is
            the current level error plus a continuous back-calculation
            anti-windup correction; in manual mode it is zero.

        Raises
        ------
        ValueError
            If a numeric input is non-finite.

        Notes
        -----
        Governing integral equation with back-calculation anti-windup
        (Åström & Murray §11.4; Åström & Hägglund §3.5):

            dI/dt = e + (u_clipped − u_raw) / (K_i · T_t)

        ``u_raw`` is the unconstrained PI demand and ``u_clipped`` is the
        physical demand after the 0-to-maximum feedwater limit. When there is
        no clipping, the second term is exactly zero and the integral is the
        ordinary level-error integral. When the demand saturates, the tracking
        term smoothly pulls the stored integral back toward the value that
        would have produced the clipped demand. This avoids a discontinuous
        on/off derivative at the limit, which is difficult for a stiff BDF
        integrator to step through.
        """
        terms = self._demand_terms(state, inputs)
        if terms.mode == "manual":
            return np.array([0.0], dtype=float)

        e = terms.level_error
        p = self.params

        # Back-calculation anti-windup (Åström & Murray §11.4): compare the
        # realizable clipped demand with the unconstrained PI demand and feed
        # that mismatch back into the integrator through the tracking time.
        # This is continuous at the actuator limit because u_clipped and
        # u_raw are equal as the controller leaves saturation.
        tracking = (terms.demand - terms.raw_demand) / (p.K_i * p.antiwindup_tracking_time)
        return np.array([e + tracking], dtype=float)

    def outputs(self, state: np.ndarray, *, inputs: dict[str, Any]) -> dict[str, float]:
        """Return the feedwater-demand output port.

        Parameters
        ----------
        state : np.ndarray, shape (1,)
            ``[level_error_integral]`` [s].
        inputs : dict
            Required keys are ``level_sg`` [-], ``level_setpoint`` [-],
            ``m_steam`` [kg/s], ``m_dump`` [kg/s], and ``feedwater_manual``
            [-] or None.

        Returns
        -------
        dict
            ``m_fw_demand`` [kg/s], clipped into ``[0, m_fw_max]``.

        Raises
        ------
        ValueError
            If a numeric input is non-finite.
        """
        terms = self._demand_terms(state, inputs)
        return {"m_fw_demand": terms.demand}

    def telemetry(self, state: np.ndarray, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return feedwater-controller diagnostics for logs and displays.

        Parameters
        ----------
        state : np.ndarray, shape (1,)
            ``[level_error_integral]`` [s].
        inputs : dict or None, optional
            Same dict as ``outputs()``. When None, input-dependent telemetry
            keys are present but reported as ``None``.

        Returns
        -------
        dict
            Keys are ``m_fw_demand`` [kg/s], ``level_error`` [-],
            ``level_error_integral`` [s], ``feedwater_manual`` [-] or None,
            ``mode`` (``"auto"`` or ``"manual"``), and ``saturated`` [bool].
        """
        integral = self._finite_input("level_error_integral", state[0])
        if inputs is None:
            return {
                "m_fw_demand": None,
                "level_error": None,
                "level_error_integral": integral,
                "feedwater_manual": None,
                "mode": None,
                "saturated": None,
            }

        terms = self._demand_terms(state, inputs)
        return {
            "m_fw_demand": terms.demand,
            "level_error": terms.level_error,
            "level_error_integral": terms.level_error_integral,
            "feedwater_manual": terms.feedwater_manual,
            "mode": terms.mode,
            "saturated": terms.saturated,
        }
