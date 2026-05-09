"""Pressurizer pressure controller (proportional + deadband, L1 fidelity).

Reads the measured pressurizer pressure and a setpoint; outputs heater
electrical power and spray mass flow demands. Manual overrides per
actuator allow the operator (or a fault scenario) to bypass the
controller and drive an actuator directly.

At L1 we model:
- Pure proportional control (no integral, no derivative).
- Symmetric deadband around the setpoint to suppress chatter.
- Hard saturation at Q_heater_max and m_dot_spray_max.
- Manual override per actuator (``None`` → automatic).

Physics specification: see
``docs/superpowers/specs/2026-05-08-pressurizer-design.md`` §3.2.

References
----------
Tong, L. S. and Weisman, J. *Thermal Analysis of Pressurized Water
Reactors*, 3rd ed., American Nuclear Society, 1996. (Pressure control,
§6.4 / §7.3 — including the variable/backup heater bank scheme that
we collapse to one continuous duty.)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PressurizerControllerParams:
    """Parameters for the L1 pressurizer pressure controller.

    Defaults sized for a Westinghouse 4-loop centroid (1.8 MW total
    heater capacity, 25 kg/s spray, ±150 kPa deadband matching the real
    plant's variable-heater band).

    Parameters
    ----------
    Q_heater_max : float
        Maximum heater electrical power [W]. Default 1.8e6 = 1800 kW.
        Source: Tong & Weisman §7.3 — typical W4-loop installed heater
        capacity is 1400–1800 kW.
    m_dot_spray_max : float
        Maximum spray mass flow [kg/s]. Default 25.0. W4-loop spray
        valves are sized for 18–24 kg/s (two valves at ~150 gpm each).
    deadband : float
        Symmetric deadband around the setpoint [Pa]. Default 1.5e5 = 150
        kPa = ±22 psi, matching real W4-loop variable-heater control.
        Tighter values cause visible heater chatter that an operator
        would not see in a real plant.
    K_p_heater : float
        Proportional gain on heater duty [1/Pa]. Default 2.0e-4: with
        the deadband at 150 kPa, the heater saturates at 5 kPa beyond
        deadband — effectively bang-bang outside deadband, matching the
        real backup-heater on/off behavior.
    K_p_spray : float
        Proportional gain on spray duty [1/Pa]. Default 2.0e-4 (same as
        heater for symmetry).
    P_setpoint_default : float
        Default pressure setpoint [Pa] when the engine input is omitted.
        Default 1.55e7 = 15.5 MPa (= primary design pressure).
    """

    # SIMPLIFICATION: no heater bank discreteness. Real plants have base
    # load + variable + backup banks. We model one continuous duty.
    Q_heater_max: float = 1.8e6  # [W] — Tong & Weisman §7.3

    # SIMPLIFICATION: no spray-bypass valve, no aux spray. Single
    # continuous flow.
    m_dot_spray_max: float = 25.0  # [kg/s] — typical W4-loop spray sizing

    # ±150 kPa around setpoint — matches W4-loop variable-band reality.
    deadband: float = 1.5e5  # [Pa]

    # Proportional gains — nearly bang-bang outside deadband.
    K_p_heater: float = 2.0e-4  # [1/Pa] — saturates at ~5 kPa beyond deadband
    K_p_spray: float = 2.0e-4   # [1/Pa]

    P_setpoint_default: float = 1.55e7  # [Pa] = primary design pressure


class PressurizerController:
    """Proportional-with-deadband pressure controller (L1).

    Stateless. ``derivatives()`` returns an empty array; all logic
    lives in ``outputs()``.

    Ports in (passed to ``outputs()`` via ``inputs`` dict):
        P : float [Pa]
            Measured pressurizer pressure.
        P_setpoint : float [Pa]
            Pressure setpoint (pass via ``engine.input("P_setpoint", ...)``).
        heater_manual : float | None [dimensionless, 0..1]
            If float, forces heater duty fraction; if None, controller
            drives. Used for fault scenarios (heater stuck off etc.).
        spray_manual : float | None [dimensionless, 0..1]
            If float, forces spray duty fraction; if None, controller
            drives.

    Ports out (returned by ``outputs()``):
        Q_heater : float [W]
            Heater electrical power demand (in [0, Q_heater_max]).
        m_dot_spray : float [kg/s]
            Spray mass-flow demand (in [0, m_dot_spray_max]).

    State vector (length 0): empty.
    """

    state_size: int = 0
    state_labels: tuple[str, ...] = ()
    input_ports: tuple[str, ...] = (
        "P",
        "P_setpoint",
        "heater_manual",
        "spray_manual",
    )
    output_ports: tuple[str, ...] = ("Q_heater", "m_dot_spray")

    def __init__(self, params: PressurizerControllerParams) -> None:
        self.params = params

    def initial_state(self) -> np.ndarray:
        """Return ``np.zeros(0)`` — no state."""
        return np.zeros(0)

    def derivatives(self, state: np.ndarray, inputs: dict) -> np.ndarray:
        """Return ``np.zeros(0)`` — stateless controller has no derivatives."""
        return np.zeros(0)
