"""Main feedwater pumps and regulating valves as one L1 flow actuator.

This module represents the hardware between the feedwater controller's flow
demand and the steam-generator shell inlet: the main feedwater pumps,
feedwater control valves, and short piping volume are collapsed into one
command-following actuator. In a real PWR secondary plant those devices set
how much warm liquid water returns to the steam generators after steam leaves
through the turbine or dump paths.

Fidelity level
--------------
L1. The actuator has one state, feedwater mass flow ``m_fw``. It follows the
controller's demanded flow with a first-order lag over seconds and is bounded
by a hard maximum flow.

# SIMPLIFICATION: one first-order lag with a hard flow ceiling represents the
main feedwater pumps and regulating valves. No pump curves, valve stroke
limits, cavitation margins, feedwater-heater dynamics, or header pressure
dynamics are modeled.

References
----------
Todreas, N. E. and Kazimi, M. S. *Nuclear Systems Vol. 1*, 2nd ed.,
CRC Press, 2012. Ch. 7 describes PWR steam generators and secondary-side
feedwater/steam systems.

Public PWR system reference:

- U.S. NRC Technical Training Center, *Reactor Concepts Manual: Pressurized
  Water Reactor Systems*, describes the PWR steam generator, main feedwater,
  and steam system context:
  https://ww2.nrc.gov/sites/default/files/doc_library/cdn/legacy/reading-rm/basic-ref/students/for-educators/04.pdf
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from fission_sim.physics.sg_secondary import SGSecondaryParams


@dataclass(frozen=True)
class FeedwaterParams:
    """Parameters for the L1 feedwater flow actuator.

    Parameters
    ----------
    sg_params : SGSecondaryParams, optional
        Steam-generator shell parameters that provide design steam flow
        ``m_steam_design`` [kg/s].
    tau_fw : float, optional
        First-order response time for the pump/valve flow actuator [s].
    m_fw_max_frac : float, optional
        Maximum feedwater flow as a fraction of design steam flow [-].
    m_fw_max : float or None, optional
        Maximum feedwater flow [kg/s]. If None, derived as
        ``m_fw_max_frac * sg_params.m_steam_design``.
    m_fw_initial : float or None, optional
        Initial feedwater flow state [kg/s]. If None, derived as the design
        steam flow so the all-default plant starts at mass balance.

    Notes
    -----
    Frozen dataclass; ``__post_init__`` uses ``object.__setattr__`` to fill
    derived defaults while keeping constructed parameter objects immutable.
    """

    # Design shell parameters. Provenance: reuse the SGSecondary design steam
    # flow so feedwater starts in exact mass balance with the M3 turbine.
    sg_params: SGSecondaryParams = field(default_factory=SGSecondaryParams)

    # 5 s response. Provenance: M4 plan value representing the seconds-scale
    # response of main feedwater pumps plus regulating valves in an
    # educational actuator, not an equipment-specific stroke test.
    tau_fw: float = 5.0  # [s]

    # 120 % of design steam flow. Provenance: M4 plan value giving modest
    # overcapacity for level recovery without modeling detailed pump curves.
    m_fw_max_frac: float = 1.2  # [-]

    m_fw_max: float | None = None  # [kg/s], derived from m_fw_max_frac · design steam flow
    m_fw_initial: float | None = None  # [kg/s], derived from design steam flow

    def __post_init__(self) -> None:
        """Validate actuator parameters and derive omitted flow defaults.

        Parameters
        ----------
        None
            All inputs are dataclass fields.

        Returns
        -------
        None
            Derived values are written to the frozen dataclass using
            ``object.__setattr__``.

        Raises
        ------
        ValueError
            If a time constant, flow limit, or initial flow is non-finite or
            outside its physical range.

        Notes
        -----
        Governing calibration equations (Todreas & Kazimi Ch. 7 secondary
        plant context):

            m_fw,max = m_fw,max,frac · m_steam,design
            m_fw,initial = m_steam,design

        The default initial flow balances the design turbine steam flow.
        """
        tau_fw = float(self.tau_fw)
        if not math.isfinite(tau_fw) or tau_fw <= 0.0:
            raise ValueError("tau_fw must be finite and > 0 so the feedwater actuator derivative is well defined.")

        m_fw_max_frac = float(self.m_fw_max_frac)
        if not math.isfinite(m_fw_max_frac) or m_fw_max_frac <= 0.0:
            raise ValueError("m_fw_max_frac must be finite and > 0 because feedwater capacity is a positive fraction.")

        if self.m_fw_max is None:
            object.__setattr__(self, "m_fw_max", m_fw_max_frac * self.sg_params.m_steam_design)

        m_fw_max = float(self.m_fw_max)
        if not math.isfinite(m_fw_max) or m_fw_max <= 0.0:
            raise ValueError("m_fw_max must be finite and > 0 because feedwater flow cannot have a negative capacity.")

        if self.m_fw_initial is None:
            object.__setattr__(self, "m_fw_initial", self.sg_params.m_steam_design)

        m_fw_initial = float(self.m_fw_initial)
        if not math.isfinite(m_fw_initial) or not (0.0 <= m_fw_initial <= m_fw_max):
            raise ValueError(
                "m_fw_initial must be finite and within [0, m_fw_max] so the actuator starts inside its range."
            )


class FeedwaterSystem:
    """L1 feedwater pump and regulating-valve flow actuator.

    Ports in
    --------
    m_fw_demand : float
        Feedwater mass-flow demand from the level controller [kg/s].

    Ports out
    ---------
    m_fw : float
        Actual feedwater mass flow entering the steam-generator shell [kg/s].

    State variables
    ---------------
    m_fw : float
        Actual feedwater mass flow after actuator lag and limiting [kg/s].

    Notes
    -----
    The component is state-derived: downstream modules only need the current
    ``m_fw`` state, so ``outputs_require_inputs = False`` and the engine can
    publish the feedwater signal before derivative evaluation.
    """

    state_size: int = 1
    state_labels: tuple[str, ...] = ("m_fw",)
    input_ports: tuple[str, ...] = ("m_fw_demand",)
    output_ports: tuple[str, ...] = ("m_fw",)
    outputs_require_inputs: bool = False

    def __init__(self, params: FeedwaterParams) -> None:
        """Construct a feedwater flow actuator.

        Parameters
        ----------
        params : FeedwaterParams
            Frozen parameter set with design flow, time constant, and flow
            limit [SI units].
        """
        self.params = params

    def initial_state(self) -> np.ndarray:
        """Return the initial feedwater state vector.

        Returns
        -------
        np.ndarray, shape (1,)
            ``[m_fw_initial]`` in ``[kg/s]``.
        """
        return np.array([self.params.m_fw_initial], dtype=float)

    @staticmethod
    def _finite_flow_demand(m_fw_demand: Any) -> float:
        """Return a finite feedwater demand as a plain float.

        Parameters
        ----------
        m_fw_demand : Any
            Feedwater flow demand, expected to be numeric [kg/s].

        Returns
        -------
        float
            Finite feedwater flow demand [kg/s].

        Raises
        ------
        ValueError
            If ``m_fw_demand`` is not finite.

        Notes
        -----
        ``solve_ivp`` cannot recover from NaN values in the right-hand side:
        a non-finite operator or controller value can turn the BDF trial
        state into NaN. Rejecting it here gives the caller a local error
        instead of silently poisoning the solver.
        """
        demand = float(m_fw_demand)
        if not math.isfinite(demand):
            raise ValueError("m_fw_demand must be finite before clipping to [0, m_fw_max].")
        return demand

    def derivatives(self, state: np.ndarray, inputs: dict[str, float]) -> np.ndarray:
        """Return the feedwater flow rate of change.

        Parameters
        ----------
        state : np.ndarray, shape (1,)
            ``[m_fw]`` actual feedwater flow [kg/s].
        inputs : dict
            Required key is ``m_fw_demand`` [kg/s].

        Returns
        -------
        np.ndarray, shape (1,)
            ``[dm_fw/dt]`` in ``[kg/s²]``.

        Notes
        -----
        Governing equation (Todreas & Kazimi Ch. 7 feedwater system context):

            dm_fw/dt = (clip(m_fw,demand, 0, m_fw,max) − m_fw) / tau_fw

        The lower clip at zero prevents reverse feedwater flow in this L1
        one-way actuator; the upper clip is the pump/valve capacity ceiling.
        """
        p = self.params
        demand = self._finite_flow_demand(inputs["m_fw_demand"])

        # SIMPLIFICATION: pump curves and valve travel are collapsed to one
        # capacity-limited first-order target (NRC Reactor Concepts Manual PWR
        # feedwater-system context).
        target = float(np.clip(demand, 0.0, p.m_fw_max))
        return np.array([(target - float(state[0])) / p.tau_fw], dtype=float)

    def outputs(self, state: np.ndarray, inputs: dict[str, float] | None = None) -> dict[str, float]:
        """Return the state-derived output ports.

        Parameters
        ----------
        state : np.ndarray, shape (1,)
            ``[m_fw]`` actual feedwater flow [kg/s].
        inputs : dict or None, optional
            Accepted for component API uniformity; ignored because output
            flow depends only on state.

        Returns
        -------
        dict
            Key is ``m_fw`` [kg/s].

        Notes
        -----
        Equation:

            m_fw,out = m_fw,state

        The steam-generator shell reads this delayed actuator state, not the
        controller's instantaneous demand.
        """
        return {"m_fw": float(state[0])}

    def telemetry(self, state: np.ndarray, inputs: dict[str, float] | None = None) -> dict[str, float | None]:
        """Return feedwater diagnostics for logs and visualization.

        Parameters
        ----------
        state : np.ndarray, shape (1,)
            ``[m_fw]`` actual feedwater flow [kg/s].
        inputs : dict or None, optional
            Required input-port values when available. If None,
            input-dependent telemetry keys are still present but set to None.

        Returns
        -------
        dict
            Contains ``m_fw`` [kg/s], ``m_fw_demand`` [kg/s] or None, and
            ``m_fw_max`` [kg/s].
        """
        demand = None if inputs is None else self._finite_flow_demand(inputs["m_fw_demand"])
        return {
            "m_fw": float(state[0]),
            "m_fw_demand": demand,
            "m_fw_max": float(self.params.m_fw_max),
        }
