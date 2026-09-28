"""Average-temperature rod controller for load-following PWR operation (L1).

This control-layer component models the simplified automatic rod control
function used in many Westinghouse-style pressurized-water reactors: compare
the measured (in real plants, auctioneered highest-loop) average primary
temperature ``T_avg`` with the turbine-load reference temperature ``T_ref``,
then move the control bank inward or outward using a deadband and speed
program. The default program uses an approximately 1.5 °F deadband and ramps
from 8 to 72 steps/min for a 228-step bank. At L1, one state variable is the
automatic rod-demand position; the physical rod actuator is still the separate
``RodController``.

The controller is intentionally not wired into the standard plant yet. M3.6
adds the turbine/secondary-side signals that supply ``T_ref`` and connect
``rod_demand`` to the rod controller.

References
----------
Todreas, N. E. and Kazimi, M. S. *Nuclear Systems Volume I: Thermal
Hydraulic Fundamentals*, 2nd ed., CRC Press, 2011, Ch. 7. (PWR load-following
temperature program context.)

Public reference:

- U.S. NRC Technical Training Center, *Reactor Concepts Manual:
  Pressurized Water Reactor Systems*, describes PWR reactor control by
  control rods and the primary/secondary power balance that motivates a
  programmed average-temperature reference:
  https://ww2.nrc.gov/sites/default/files/doc_library/cdn/legacy/reading-rm/basic-ref/students/for-educators/04.pdf
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TavgControllerParams:
    """Parameters for the average-temperature rod controller.

    Parameters
    ----------
    deadband : float
        Symmetric temperature-error deadband [K]. Default 0.8 K ≈ 1.44 °F,
        representing the Westinghouse-style 1.5 °F rod-control deadband.
    err_max : float
        Absolute temperature error [K] where the speed program reaches
        ``v_max``. Default 2.8 K ≈ 5.0 °F.
    v_min : float
        Minimum rod-demand speed outside the deadband [1/s]. Default
        5.8e-4 is 8 steps/min of a 228-step bank.
    v_max : float
        Maximum rod-demand speed at and beyond ``err_max`` [1/s]. Default
        5.3e-3 is 72 steps/min of a 228-step bank.
    tau_track : float
        Tracking time constant [s] used when automatic action is not active
        (manual mode, SCRAM, or turbine trip). A short value keeps mode
        transfers bumpless without making the controller stiff.
    """

    # Deadband: 0.8 K × 9/5 = 1.44 °F, the public Westinghouse rod-control
    # deadband is usually described as about 1.5 °F. [K]
    deadband: float = 0.8

    # Full-speed point: 2.8 K × 9/5 = 5.04 °F, matching the 5 °F speed-program
    # span described for Westinghouse Tavg control. [K]
    err_max: float = 2.8

    # 8 steps/min over a 228-step bank:
    #     8 step/min ÷ 228 step ÷ 60 s/min = 5.85e-4 1/s.
    v_min: float = 5.8e-4  # [1/s]

    # 72 steps/min over a 228-step bank:
    #     72 step/min ÷ 228 step ÷ 60 s/min = 5.26e-3 1/s.
    # RodParams.v_normal = 0.01 1/s is faster than this demand, so the
    # physical bank can follow automatic demand without becoming the limiter.
    v_max: float = 5.3e-3  # [1/s]

    # Numerical tracking lag for bumpless transfers. One second is much
    # shorter than operator-visible load-following transients but nonzero, so
    # the ODE remains continuous when action is suspended. [s]
    tau_track: float = 1.0


class TavgController:
    """Automatic rod-demand controller on ``T_avg − T_ref``.

    The state is a rod demand (fraction withdrawn) used only in automatic
    mode. In manual mode the controller passes the operator's ``rod_command``
    through, while its state tracks the actual ``rod_position``. The same
    tracking occurs while SCRAM or turbine trip suspends automatic rod action.

    Parameters
    ----------
    params : TavgControllerParams
        Controller constants: deadband [K], full-speed error [K], speed
        program limits [1/s], and tracking time constant [s].
    rod_position_initial : float, default 0.5
        Initial control-bank position [dimensionless, 0–1]. Must match the
        rod controller's initial physical position for a bumpless start.

    Ports in (passed to ``outputs()`` and ``derivatives()`` via ``inputs``):
        T_avg : float [K]
            Average primary coolant temperature.
        T_ref : float [K]
            Turbine-load reference temperature.
        rod_position : float [dimensionless, 0–1]
            Actual control-bank position from ``RodController``.
        rod_command : float [dimensionless, 0–1]
            Operator manual command, passed through when ``rod_auto`` is false.
        rod_auto : bool
            True selects automatic rod demand; false selects manual command.
        scram : bool
            True suspends automatic action and lets the rod system trip.
        turbine_trip : bool
            True suspends automatic action so the controller does not withdraw
            rods when post-trip ``T_avg`` falls below ``T_ref``.

    Ports out (returned by ``outputs()``):
        rod_demand : float [dimensionless, 0–1 nominal]
            Command sent to the rod actuator. In automatic mode this is the
            clipped controller state. In manual mode this is the operator's
            ``rod_command``.

    State vector (length ``state_size`` = 1, names in ``state_labels``):
        index 0 : rod_demand_auto — automatic rod demand [0–1 withdrawn]
    """

    state_size: int = 1
    state_labels: tuple[str, ...] = ("rod_demand_auto",)
    input_ports: tuple[str, ...] = (
        "T_avg",
        "T_ref",
        "rod_position",
        "rod_command",
        "rod_auto",
        "scram",
        "turbine_trip",
    )
    output_ports: tuple[str, ...] = ("rod_demand",)
    outputs_require_inputs: bool = True

    def __init__(self, params: TavgControllerParams, rod_position_initial: float = 0.5) -> None:
        """Construct the average-temperature rod controller.

        Parameters
        ----------
        params : TavgControllerParams
            Frozen parameter set. Held as ``self.params`` for the lifetime of
            the object.
        rod_position_initial : float, default 0.5
            Initial control-bank position [dimensionless, 0–1]. This must
            equal the rod controller's initial physical position for a
            bumpless start. M3.6 passes the resolved ``RodParams`` initial
            position (``rod_position_initial`` if supplied, otherwise
            ``rod_position_design``).
        """
        self.params = params
        self._s0 = rod_position_initial

    def initial_state(self) -> np.ndarray:
        """Return the initial automatic rod demand.

        Returns
        -------
        np.ndarray, shape (1,)
            ``[rod_demand_auto]`` [dimensionless, 0–1 nominal].
        """
        return np.array([self._s0])

    def speed(self, abs_err: float) -> float:
        """Return the programmed rod-demand speed for an absolute error.

        The speed program is the L1 approximation of the Westinghouse
        rod-control schedule:

        ``0`` inside the deadband, a linear ramp from ``v_min`` to ``v_max``
        between ``deadband`` and ``err_max``, and ``v_max`` beyond
        ``err_max``.

        Parameters
        ----------
        abs_err : float
            Absolute temperature error ``|T_avg − T_ref|`` [K].

        Returns
        -------
        float
            Rod-demand speed [1/s, fraction of bank travel per second].
        """
        p = self.params
        if abs_err <= p.deadband:
            return 0.0
        if abs_err >= p.err_max:
            return p.v_max

        # Westinghouse speed-program approximation (NRC Reactor Concepts
        # Manual for rod-control context; Todreas & Kazimi Ch. 7 for PWR
        # temperature/load programs):
        #     v = v_min + (v_max − v_min) · (|err| − deadband) / (err_max − deadband)
        return p.v_min + (p.v_max - p.v_min) * (abs_err - p.deadband) / (p.err_max - p.deadband)

    def _acting(self, inputs: dict) -> bool:
        """Return True when automatic rod action is allowed."""
        return bool(inputs["rod_auto"]) and not inputs["scram"] and not inputs["turbine_trip"]

    def derivatives(self, state: np.ndarray, inputs: dict) -> np.ndarray:
        """Compute the automatic rod-demand derivative.

        Parameters
        ----------
        state : np.ndarray, shape (1,)
            ``[rod_demand_auto]`` [dimensionless, 0–1 nominal].
        inputs : dict
            Required keys: ``T_avg`` [K], ``T_ref`` [K], ``rod_position``
            [dimensionless], ``rod_command`` [dimensionless], ``rod_auto``
            [bool], ``scram`` [bool], and ``turbine_trip`` [bool].

        Returns
        -------
        np.ndarray, shape (1,)
            ``[d rod_demand_auto/dt]`` [1/s].

        Notes
        -----
        Manual or suspended tracking equation:

        ``demand_dot = (rod_position − rod_demand_auto) / tau_track``

        Automatic action equation:

        ``err = T_avg − T_ref``

        ``demand_dot = −sign(err) · speed(|err|)``

        Hotter-than-reference coolant inserts rods (negative rate). Colder
        coolant withdraws rods (positive rate), except while SCRAM or turbine
        trip suspends action.
        """
        p = self.params
        demand = state[0]

        if not self._acting(inputs):
            # Tracking equation for bumpless mode transfer. In auto-but-
            # suspended mode outputs() still publishes clip(state); if the rod
            # position is following that output, this derivative is zero, so
            # suspension is neutral rather than a new rod-drive request.
            # SIMPLIFICATION: one first-order tracking state stands in for the
            # operator/control-system alignment logic used during mode changes.
            return np.array([(inputs["rod_position"] - demand) / p.tau_track])

        # Temperature error used by Westinghouse Tavg rod control:
        #     err = T_avg − T_ref
        # Positive error means the primary side is hot for the current load,
        # so rods insert; negative error withdraws rods.
        err = inputs["T_avg"] - inputs["T_ref"]

        # Automatic speed-program equation (see speed()). The sign convention
        # is "hot inserts" (negative demand rate) and "cold withdraws".
        rate = -np.sign(err) * self.speed(abs(err))

        # Hard travel-limit guard: do not integrate farther out of bounds.
        # If a numerical overshoot put demand just outside [0, 1], an inward
        # rate is still allowed so the state can return.
        if (demand <= 0.0 and rate < 0.0) or (demand >= 1.0 and rate > 0.0):
            rate = 0.0
        return np.array([float(rate)])

    def outputs(self, state: np.ndarray, *, inputs: dict) -> dict:
        """Compute the rod-demand output.

        Parameters
        ----------
        state : np.ndarray, shape (1,)
            ``[rod_demand_auto]`` [dimensionless].
        inputs : dict
            Required key ``rod_auto`` [bool]. In manual mode also uses
            ``rod_command`` [dimensionless].

        Returns
        -------
        dict
            ``{"rod_demand": float [dimensionless]}``.
        """
        if inputs["rod_auto"]:
            # Auto mode publishes the controller state. SCRAM/turbine-trip
            # suspension affects only the derivative (tracking rod_position);
            # the output remains the tracked state so mode transfer has no
            # discontinuity.
            return {"rod_demand": float(np.clip(state[0], 0.0, 1.0))}
        return {"rod_demand": float(inputs["rod_command"])}

    def telemetry(self, state: np.ndarray, inputs: dict | None = None) -> dict:
        """Return operator-facing diagnostics for the controller.

        Parameters
        ----------
        state : np.ndarray, shape (1,)
            ``[rod_demand_auto]`` [dimensionless].
        inputs : dict or None
            Same mapping as ``outputs()`` and ``derivatives()``. When None,
            input-dependent values are reported as None.

        Returns
        -------
        dict
            Keys include ``rod_demand_auto`` [dimensionless],
            ``rod_demand`` [dimensionless or None], ``T_err`` [K or None],
            ``rod_auto`` [bool or None], and ``acting`` [bool or None].
        """
        tele = {
            "rod_demand_auto": float(state[0]),
            "rod_demand": None,
            "T_err": None,
            "rod_auto": None,
            "acting": None,
            "T_avg": None,
            "T_ref": None,
            "rod_position": None,
            "rod_command": None,
            "scram": None,
            "turbine_trip": None,
        }
        if inputs is None:
            return tele

        tele.update(
            self.outputs(state, inputs=inputs),
            T_err=inputs["T_avg"] - inputs["T_ref"],
            rod_auto=bool(inputs["rod_auto"]),
            acting=self._acting(inputs),
            T_avg=inputs["T_avg"],
            T_ref=inputs["T_ref"],
            rod_position=inputs["rod_position"],
            rod_command=inputs["rod_command"],
            scram=inputs["scram"],
            turbine_trip=inputs["turbine_trip"],
        )
        return tele
