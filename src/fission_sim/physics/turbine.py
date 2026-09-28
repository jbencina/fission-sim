"""Turbine admission, steam dump, electric power, and Tavg reference program.

This module represents the main turbine, main steam header relief path, and
the Westinghouse-style ``T_ref`` program as one L1 component. The component
does not model turbine stages or a condenser; it turns steam-generator shell
pressure and a governor load demand into steam flow, relief/dump flow,
gross electric power, and the reactor coolant average-temperature reference
used by rod control.

Fidelity level
--------------
L1. The turbine admission state is one normalized load variable. Steam flow
is proportional to admission and steam pressure, electric power is a fixed
fraction of the steam heat rate, and all dump/relief hardware is lumped into
one proportional path.

# SIMPLIFICATION: the turbine governor is represented as a valve-admission
fraction with a rate limit. Real electro-hydraulic turbine controls regulate
megawatts and speed/pressure through several valve groups, not one fixed
valve position.
# SIMPLIFICATION: steam dump, steam-generator power-operated relief valves,
and safety valves are lumped into one proportional relief path. Real plants
use a limited condenser steam dump (often about 40 % load) plus staggered
relief and safety valves near the 7.6–8.3 MPa main-steam range.
# SIMPLIFICATION: no turbine rotor inertia, condenser pressure, moisture
separation/reheat, extraction feedwater heating, or generator losses are
modeled.

References
----------
Todreas, N. E. and Kazimi, M. S. *Nuclear Systems Vol. 1*, 2nd ed.,
CRC Press, 2012. Ch. 7 describes PWR steam generators and secondary plant
heat removal.

Kearton, W. J. *Steam Turbine Theory and Practice*, 7th ed., Pitman, 1958.
Ch. VII describes turbine governing and the approximately pressure-scaled
flow through wide-open turbine valves.

DOE Fundamentals Handbook, *Thermodynamics, Heat Transfer, and Fluid Flow*,
Vol. 1, DOE-HDBK-1012/1-92. Control-volume enthalpy bookkeeping and turbine
work:
https://www.steamtablesonline.com/pdf/Thermodynamics-Volume1.pdf

Public PWR system reference:

- U.S. NRC Technical Training Center, *Reactor Concepts Manual: Pressurized
  Water Reactor Systems*, describes PWR steam generators, turbine-generator
  heat conversion, rod-control temperature program context, and reactor trip
  actions:
  https://ww2.nrc.gov/sites/default/files/doc_library/cdn/legacy/reading-rm/basic-ref/students/for-educators/04.pdf
- CoolProp / IAPWS references for water and steam property evaluations:
  https://coolprop.org/fluid_properties/IF97.html
  https://iapws.org/documents/release/IF97-Rev
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from fission_sim.physics import coolprop
from fission_sim.physics.sg_secondary import SGSecondaryParams, feedwater_enthalpy


@dataclass(frozen=True)
class TurbineParams:
    """Parameters for the L1 turbine and steam-dump component.

    Parameters
    ----------
    sg_params : SGSecondaryParams, optional
        Steam-generator shell parameters that provide design pressure
        ``P_ref`` [Pa], design steam flow ``m_steam_design`` [kg/s], and
        feedwater temperature ``T_fw`` [K].
    ramp_rate : float, optional
        Maximum governor load-change rate [1/s].
    tau_gov : float, optional
        First-order governor lag time constant inside the rate limit [s].
    tau_trip : float, optional
        Turbine stop-valve closure time constant after turbine trip or
        reactor scram [s].
    eta : float, optional
        Gross electrical efficiency, electric power divided by steam heat
        rate [-].
    P_dump_set : float, optional
        Steam pressure where the lumped dump/relief path begins to open [Pa].
    P_dump_full : float, optional
        Steam pressure where the lumped dump/relief path reaches design
        steam-flow capacity [Pa].
    T_ref_noload : float, optional
        Reactor coolant average-temperature reference at no turbine load [K].
    T_ref_full : float, optional
        Reactor coolant average-temperature reference at full turbine load [K].
    load_initial : float, optional
        Initial turbine admission/load state [-].
    k_valve : float or None, optional
        Linear admission-flow coefficient [kg/(s·Pa)]. If None, derived as
        ``m_steam_design / P_ref`` so full load at design pressure removes
        design steam flow.

    Notes
    -----
    Frozen dataclass; ``__post_init__`` derives ``k_valve`` with
    ``object.__setattr__``.
    """

    # Design shell parameters. Provenance: reuse the M3 SGSecondary design
    # point so the all-default plant starts at exact full-load balance.
    sg_params: SGSecondaryParams = field(default_factory=SGSecondaryParams)

    # 8.33e-4 1/s = 0.05 per minute. Provenance: plan value for a 5 %/min
    # educational turbine-governor load ramp.
    ramp_rate: float = 8.33e-4  # [1/s]

    # Governor lag time. Provenance: plan value, a deliberately fast 1 s
    # lag so the rate limiter, not a slow actuator, sets load-ramp behavior.
    tau_gov: float = 1.0  # [s]

    # Stop-valve closure time. Provenance: plan value representing fast main
    # turbine stop-valve closure after a trip.
    tau_trip: float = 0.5  # [s]

    # Thermal-to-electric efficiency. Provenance: typical large PWR gross
    # efficiency of about one-third; 0.33 × 3.0 GWth ≈ 990 MWe.
    eta: float = 0.33  # [-]

    # Dump begins opening near 7.6 MPa. Provenance: plan setpoint; roughly
    # the lower end of main steam dump / relief action in the referenced PWR
    # training material.
    P_dump_set: float = 7.6e6  # [Pa]

    # Full lumped relief capacity near 8.2 MPa. Provenance: plan value inside
    # the 7.6–8.3 MPa range spanning ~40 % condenser dump, SG PORVs, and
    # safety valves in real plants.
    P_dump_full: float = 8.2e6  # [Pa]

    # No-load Tavg reference. Provenance: 565 K is approximately the
    # saturation temperature of 7.6 MPa steam, matching the plan's no-load
    # reference anchor.
    T_ref_noload: float = 565.0  # [K]

    # Full-load Tavg reference. Provenance: same 583 K nominal primary-loop
    # average temperature used by LoopParams.T_avg_ref.
    T_ref_full: float = 583.0  # [K]

    # Initial turbine admission. Provenance: full-load default keeps the
    # all-default plant at its design balance.
    load_initial: float = 1.0  # [-]

    # Admission coefficient. Provenance: derived from the SGSecondary design
    # flow and pressure unless a calibration value is supplied.
    k_valve: float | None = None  # [kg/(s·Pa)]

    def __post_init__(self) -> None:
        """Validate parameters and derive the turbine-admission coefficient.

        Parameters
        ----------
        None
            All inputs are dataclass fields.

        Returns
        -------
        None
            ``k_valve`` is written to the frozen dataclass when omitted.

        Raises
        ------
        ValueError
            If a control or thermodynamic parameter is non-finite or outside
            its physical range.

        Notes
        -----
        Governing calibration equation (Kearton, turbine governing):

            k_valve = m_steam,design / P_ref

        With ``load = 1`` and ``P_steam = P_ref``, the turbine removes the
        design steam flow produced by ``SGSecondaryParams``.
        """
        for name in ("ramp_rate", "tau_gov", "tau_trip"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and > 0 so the turbine load derivative is well defined.")

        if not math.isfinite(float(self.P_dump_set)):
            raise ValueError("P_dump_set must be finite [Pa] so the steam-dump opening pressure is defined.")
        if not math.isfinite(float(self.P_dump_full)):
            raise ValueError("P_dump_full must be finite [Pa] so the steam-dump full-open pressure is defined.")
        if self.P_dump_full <= self.P_dump_set:
            raise ValueError("P_dump_full must be greater than P_dump_set so dump flow increases with pressure.")

        eta = float(self.eta)
        if not math.isfinite(eta) or not (0.0 < eta <= 1.0):
            raise ValueError("eta must be finite and in (0, 1]; it is a gross electrical efficiency.")

        load_initial = float(self.load_initial)
        if not math.isfinite(load_initial) or not (0.0 <= load_initial <= 1.0):
            raise ValueError("load_initial must be finite and in [0, 1] because turbine admission is a fraction.")

        if self.k_valve is None:
            object.__setattr__(self, "k_valve", self.sg_params.m_steam_design / self.sg_params.P_ref)
        else:
            k_valve = float(self.k_valve)
            if not math.isfinite(k_valve) or k_valve <= 0.0:
                raise ValueError("k_valve must be finite and > 0 so turbine steam flow cannot reverse sign.")


class Turbine:
    """L1 turbine admission, steam dump, electric power, and ``T_ref``.

    Ports in
    --------
    P_steam : float
        Saturated steam pressure from the steam-generator shell [Pa].
    load_demand : float
        Operator or load-program demand for turbine admission, clipped to the
        physical interval [0, 1] before use [-].
    turbine_trip : bool
        Main turbine trip signal. When true, the turbine stop valves close.
    scram : bool
        Reactor trip signal. In Westinghouse terminology, a reactor trip
        generates the P-4 interlock: in plain words, once the reactor trips,
        the turbine is also tripped so it stops drawing full steam flow from
        a heat source that has just shut down.

    Ports out
    ---------
    m_steam : float
        Steam mass flow admitted to the turbine [kg/s].
    m_dump : float
        Steam mass flow through the lumped dump/relief path [kg/s].
    P_electric : float
        Gross electric power produced by the turbine-generator [W].
    T_ref : float
        Reactor coolant average-temperature reference for rod control [K].

    State variables
    ---------------
    load : float
        Actual normalized turbine admission after governor lag, rate limits,
        and trip closure [-].

    Notes
    -----
    The component is computed: outputs need ``P_steam`` to determine steam
    flow and enthalpy, so ``outputs_require_inputs = True`` and
    :meth:`outputs` requires an ``inputs`` keyword.
    """

    state_size: int = 1
    state_labels: tuple[str, ...] = ("load",)
    input_ports: tuple[str, ...] = ("P_steam", "load_demand", "turbine_trip", "scram")
    output_ports: tuple[str, ...] = ("m_steam", "m_dump", "P_electric", "T_ref")
    outputs_require_inputs: bool = True

    def __init__(self, params: TurbineParams) -> None:
        """Construct a turbine and steam-dump component.

        Parameters
        ----------
        params : TurbineParams
            Frozen parameter set with design-point and control constants
            [SI units].
        """
        self.params = params

    def initial_state(self) -> np.ndarray:
        """Return the initial turbine state vector.

        Returns
        -------
        np.ndarray, shape (1,)
            ``[load_initial]`` in normalized admission units [-].
        """
        return np.array([self.params.load_initial], dtype=float)

    def T_ref_for(self, load: float) -> float:
        """Return the average-temperature reference for a turbine load.

        Parameters
        ----------
        load : float
            Normalized turbine admission/load [-].

        Returns
        -------
        float
            Programmed reactor coolant average-temperature reference [K].

        Notes
        -----
        Governing equation (NRC Reactor Concepts Manual, PWR rod-control
        temperature-program context):

            T_ref = T_ref,noload + (T_ref,full − T_ref,noload) · load

        This L1 model uses a straight line between no-load and full-load
        anchors.
        """
        p = self.params
        return p.T_ref_noload + (p.T_ref_full - p.T_ref_noload) * load

    @staticmethod
    def _clipped_load_demand(load_demand: Any) -> float:
        """Return finite load demand clipped to the physical interval [0, 1].

        Parameters
        ----------
        load_demand : Any
            External load demand value, expected to be numeric [-].

        Returns
        -------
        float
            Finite load demand clipped into ``[0, 1]`` [-].

        Raises
        ------
        ValueError
            If ``load_demand`` is not finite.

        Notes
        -----
        ``solve_ivp`` cannot recover from NaN values in the right-hand side:
        a non-finite operator input can turn the entire BDF trial state into
        NaN. Rejecting it here gives the runtime a clear, local error instead
        of silently poisoning the solver.
        """
        demand = float(load_demand)
        if not math.isfinite(demand):
            raise ValueError("load_demand must be finite before clipping to [0, 1].")
        return float(np.clip(demand, 0.0, 1.0))

    @staticmethod
    def _trip_active(inputs: dict[str, Any]) -> bool:
        """Return whether turbine stop-valve closure is demanded.

        Parameters
        ----------
        inputs : dict
            Component inputs containing ``turbine_trip`` and ``scram``.

        Returns
        -------
        bool
            True when a turbine trip is present directly or through the
            reactor-trip P-4 interlock.
        """
        return bool(inputs["turbine_trip"] or inputs["scram"])

    def derivatives(self, state: np.ndarray, inputs: dict[str, Any]) -> np.ndarray:
        """Return the turbine admission/load rate of change.

        Parameters
        ----------
        state : np.ndarray, shape (1,)
            ``[load]`` in normalized admission units [-].
        inputs : dict
            Required keys are ``P_steam`` [Pa], ``load_demand`` [-],
            ``turbine_trip`` [bool], and ``scram`` [bool]. ``P_steam`` is an
            input port for output evaluation and is not needed by this state
            derivative.

        Returns
        -------
        np.ndarray, shape (1,)
            ``[dload/dt]`` [1/s].

        Notes
        -----
        Governing equations (Kearton, turbine governing; NRC Reactor Concepts
        Manual for trip action):

            dload/dt = −load / tau_trip                         (trip or scram)
            dload/dt = clip((load_demand − load) / tau_gov,
                            −ramp_rate, +ramp_rate)             (normal)

        A reactor trip closes the turbine stop valves through the P-4
        interlock even when the explicit turbine-trip input is false.
        """
        p = self.params
        load = float(state[0])
        demand = self._clipped_load_demand(inputs["load_demand"])

        if self._trip_active(inputs):
            # Reactor trip → P-4 interlock → turbine trip: close stop valves
            # exponentially toward zero (NRC Reactor Concepts Manual PWR).
            return np.array([-load / p.tau_trip], dtype=float)

        # SIMPLIFICATION: this state is valve admission, not a full
        # megawatt/speed governor. The first-order lag is then clipped to the
        # 5 %/min educational load-program ramp rate (Kearton Ch. VII).
        rate = (demand - load) / p.tau_gov
        return np.array([float(np.clip(rate, -p.ramp_rate, p.ramp_rate))], dtype=float)

    def _flows(self, load: float, P_steam: float) -> dict[str, float]:
        """Return turbine and dump outputs for the current load and pressure.

        Parameters
        ----------
        load : float
            Turbine admission/load state [-].
        P_steam : float
            Saturated steam pressure from the shell [Pa].

        Returns
        -------
        dict
            Output-port values ``m_steam`` [kg/s], ``m_dump`` [kg/s],
            ``P_electric`` [W], and ``T_ref`` [K].
        """
        p = self.params
        sg = p.sg_params

        # BDF can hand back tiny negative trial states such as -1e-12 while
        # estimating a Jacobian. Clamp only for flow computation so those
        # numerical probes do not create unphysical negative steam flow.
        load_clipped = max(float(load), 0.0)

        # SIMPLIFICATION: linear choked/admission-valve law standing in for
        # real multi-valve turbine governing (Kearton Ch. VII):
        #     ṁ_steam = k_v · load · P_steam
        m_steam = p.k_valve * load_clipped * P_steam

        # SIMPLIFICATION: one proportional relief path represents condenser
        # steam dump plus SG PORVs and safety valves. Real plants have
        # multiple paths whose setpoints and capacities are staggered:
        #     ṁ_dump = ṁ_design · clip((P_steam − P_set) / (P_full − P_set), 0, 1)
        dump_fraction = (P_steam - p.P_dump_set) / (p.P_dump_full - p.P_dump_set)
        m_dump = sg.m_steam_design * float(np.clip(dump_fraction, 0.0, 1.0))

        h_g = coolprop.sat_vapor_enthalpy(P=P_steam)
        h_fw = feedwater_enthalpy(P=P_steam, T_fw=sg.T_fw)

        # Gross electrical power from the steam heat rate (DOE-HDBK-1012/1-92):
        #     P_electric = η · ṁ_steam · (h_g(P_steam) − h_fw(P_steam, T_fw))
        P_electric = p.eta * m_steam * (h_g - h_fw)

        # Linear Westinghouse-style average-temperature program (NRC Reactor
        # Concepts Manual PWR rod-control context):
        #     T_ref = T_ref,noload + (T_ref,full − T_ref,noload) · load
        T_ref = self.T_ref_for(load_clipped)

        return {
            "m_steam": m_steam,
            "m_dump": m_dump,
            "P_electric": P_electric,
            "T_ref": T_ref,
        }

    def outputs(self, state: np.ndarray, *, inputs: dict[str, Any]) -> dict[str, float]:
        """Return turbine output ports.

        Parameters
        ----------
        state : np.ndarray, shape (1,)
            ``[load]`` in normalized admission units [-].
        inputs : dict
            Required keys are ``P_steam`` [Pa], ``load_demand`` [-],
            ``turbine_trip`` [bool], and ``scram`` [bool].

        Returns
        -------
        dict
            Keys are ``m_steam`` [kg/s], ``m_dump`` [kg/s],
            ``P_electric`` [W], and ``T_ref`` [K].

        Notes
        -----
        ``load_demand`` does not appear directly in the algebraic outputs,
        but it is still validated here because the engine evaluates computed
        outputs before derivatives in each BDF right-hand-side call.
        """
        self._clipped_load_demand(inputs["load_demand"])
        return self._flows(float(state[0]), float(inputs["P_steam"]))

    def telemetry(self, state: np.ndarray, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return turbine diagnostics for logs and visualization.

        Parameters
        ----------
        state : np.ndarray, shape (1,)
            ``[load]`` in normalized admission units [-].
        inputs : dict or None, optional
            Component inputs when available. If None, input-dependent
            telemetry keys are still present but set to None.

        Returns
        -------
        dict
            Always contains ``load`` and ``T_ref``. When ``inputs`` is
            provided, also reports ``m_steam``, ``m_dump``, ``P_electric``,
            ``P_steam``, clipped ``load_demand``, ``turbine_trip``, ``scram``,
            and ``trip_active``. The last key is true when either a direct
            turbine trip or the reactor-trip P-4 interlock is closing the
            stop valves.
        """
        load = max(float(state[0]), 0.0)
        if inputs is None:
            return {
                "load": load,
                "T_ref": self.T_ref_for(load),
                "m_steam": None,
                "m_dump": None,
                "P_electric": None,
                "P_steam": None,
                "load_demand": None,
                "turbine_trip": None,
                "scram": None,
                "trip_active": None,
            }

        out: dict[str, Any] = self._flows(load, float(inputs["P_steam"]))
        out.update(
            load=load,
            P_steam=float(inputs["P_steam"]),
            load_demand=self._clipped_load_demand(inputs["load_demand"]),
            turbine_trip=bool(inputs["turbine_trip"]),
            scram=bool(inputs["scram"]),
            trip_active=self._trip_active(inputs),
        )
        return out
