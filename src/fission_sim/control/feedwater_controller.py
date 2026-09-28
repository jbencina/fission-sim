"""M3 stand-in feedwater controller for the steam-generator secondary side.

This L1 control component is the Milestone 3 stand-in for the feedwater
system: feedwater exactly matches the steam that leaves, so shell mass
inventory is constant. Collapsed level can still drift slightly with pressure
because saturated liquid water becomes less dense as it gets hotter. M4
replaces this ideal mass-inventory match with a three-element level controller
and a feedwater actuator.

Real pressurized-water reactors control steam-generator water level because
the feedwater system must maintain tube coverage while the turbine removes
steam at a changing rate. Here, the controller is deliberately ideal: it
measures the turbine steam flow and dump/relief flow and commands the same
total feedwater flow back into the shell.

References
----------
Tong, L. S. and Weisman, J. *Thermal Analysis of Pressurized Water Reactors*,
3rd ed., American Nuclear Society, 1996. (Steam-generator secondary-side mass
and energy balances; feedwater is the controlled inlet flow to the shell.)

Yan, J. *Introduction to Engineering Thermodynamics*, §5.2.2 "Mass
Conservation Equations in a Control Volume", for the inlet-minus-outlet mass
balance used by this placeholder:
https://pressbooks.bccampus.ca/thermo1/chapter/5-2-steady-flow-and-transient-flow/

U.S. NRC Technical Training Center, *Westinghouse Technology Systems Manual*,
§11.1 "Steam Generator Water Level Control System", pp. 11.1-2-3 (PDF
pp. 4-5) and Fig. 11.1-2, Rev. 0706, describes measured level, steam-flow,
and feedwater-flow signals in the real control system that this L1 mass match
defers:
https://www.nrc.gov/docs/ML1122/ML11223A293.pdf
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class FeedwaterControllerParams:
    """Parameters for the M3 flow-matching feedwater controller.

    The M3 stand-in has no tunable parameters. The frozen dataclass is kept so
    the plant factory can keep a stable ``FeedwaterControllerParams`` argument
    when M4 replaces this ideal flow match with three-element level control.

    Notes
    -----
    No numeric controller gains are present in M3; the only equation is the
    exact flow match ``m_fw = m_steam + m_dump`` [kg/s].
    """


class FeedwaterController:
    """Ideal flow-matching feedwater controller.

    Stateless. ``derivatives()`` returns an empty array; all logic lives in
    ``outputs()``.

    Ports in (passed to ``outputs()`` via ``inputs`` dict):
        m_steam : float [kg/s]
            Main steam mass flow leaving the steam-generator shell for the
            turbine.
        m_dump : float [kg/s]
            Steam dump, relief, or safety-valve mass flow leaving the shell.

    Ports out (returned by ``outputs()``):
        m_fw : float [kg/s]
            Feedwater mass-flow demand entering the steam-generator shell.

    State vector (length 0): empty.

    Notes
    -----
    This is not a real feedwater control system. It is a Milestone 3 closure
    relation that keeps the secondary mass inventory constant while the steam
    header and secondary-shell models are introduced.
    """

    state_size: int = 0
    state_labels: tuple[str, ...] = ()
    input_ports: tuple[str, ...] = ("m_steam", "m_dump")
    output_ports: tuple[str, ...] = ("m_fw",)
    outputs_require_inputs: bool = True

    def __init__(self, params: FeedwaterControllerParams) -> None:
        """Initialize the controller with immutable parameters.

        Parameters
        ----------
        params : FeedwaterControllerParams
            No-tunable parameter object for the M3 ideal flow match.
        """
        self.params = params

    def initial_state(self) -> np.ndarray:
        """Return the controller's empty initial state.

        Returns
        -------
        np.ndarray
            Length-0 state vector because the M3 feedwater controller is
            stateless.
        """
        return np.empty(0)

    def derivatives(self, state: np.ndarray, inputs: dict) -> np.ndarray:
        """Return no state derivatives.

        Parameters
        ----------
        state : np.ndarray
            Length-0 state vector.
        inputs : dict
            Must contain ``m_steam`` [kg/s] and ``m_dump`` [kg/s]. They are not
            used by ``derivatives()`` because this controller is stateless.

        Returns
        -------
        np.ndarray
            Length-0 derivative vector.
        """
        return np.empty(0)

    def outputs(self, state: np.ndarray, *, inputs: dict) -> dict:
        """Compute the feedwater mass-flow demand.

        Parameters
        ----------
        state : np.ndarray
            Length-0 state vector.
        inputs : dict
            Must contain ``m_steam`` [kg/s] and ``m_dump`` [kg/s].

        Returns
        -------
        dict
            ``m_fw`` [kg/s], the feedwater demand entering the steam-generator
            shell.
        """
        # Governing M3 mass-closure equation (Yan §5.2.2 mass balance; NRC
        # WTSM §11.1 for the real measured flows this placeholder defers):
        #
        #     m_fw = m_steam + m_dump
        #
        # SIMPLIFICATION: ideal mass-inventory matching, not level control.
        # Real PWRs compare level, steam flow, and feedwater flow; this
        # stand-in exactly replaces the steam mass leaving, so shell mass stays
        # fixed. Collapsed level can still drift slightly when pressure changes
        # because hotter saturated liquid water is less dense.
        return {"m_fw": inputs["m_steam"] + inputs["m_dump"]}

    def telemetry(self, state: np.ndarray, inputs: dict | None = None) -> dict:
        """Echo the feedwater demand and measured steam outflows.

        Parameters
        ----------
        state : np.ndarray
            Length-0 state vector.
        inputs : dict or None
            Same dict as ``outputs()``. When None (for example before the first
            integration step), all input-dependent values are returned as
            ``None``.

        Returns
        -------
        dict
            Keys: ``m_fw`` [kg/s], ``m_steam`` [kg/s], and ``m_dump`` [kg/s].
        """
        if inputs is None:
            return {"m_fw": None, "m_steam": None, "m_dump": None}
        return {
            **self.outputs(state, inputs=inputs),
            "m_steam": inputs["m_steam"],
            "m_dump": inputs["m_dump"],
        }
