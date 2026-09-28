"""Shared M3 secondary-side acceptance helpers and threshold constants.

The pytest acceptance suite and ``scripts/validate_secondary.py`` both import
this module so the scenario definitions and numerical limits cannot drift.
It intentionally contains no pytest or plotting code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from fission_sim.physics import coolprop
from fission_sim.physics.domain import check_snapshot
from fission_sim.physics.sg_secondary import SGSecondaryParams

ScenarioFn = Callable[[float], dict[str, Any]]

# Dense-solution sample spacing [s]. The integrator still adapts internally;
# this is only the acceptance readout cadence.
DT: float = 1.0

# Acceptance bands adjusted to the actual L1 feedback model in A6. Because
# turbine_load is valve admission, steam flow rises with pressure; a 10 %
# admission cut is only a small net power cut once the header pressure rises.
MANUAL_N_BAND: tuple[float, float] = (0.96, 0.98)
MANUAL_TAVG_BAND: tuple[float, float] = (586.0, 590.0)  # [K]
MANUAL_P_STEAM_BAND: tuple[float, float] = (7.35e6, 7.65e6)  # [Pa]

# With a turbine trip and no reactor trip, the core runs back mostly on
# moderator feedback while the single dump path removes about full-load steam.
TRIP_N_BAND: tuple[float, float] = (0.93, 0.96)
TRIP_TAVG_BAND: tuple[float, float] = (591.0, 595.0)  # [K]
TRIP_P_STEAM_BAND: tuple[float, float] = (8.0e6, 8.35e6)  # [Pa]
AUTO_N_BAND: tuple[float, float] = (0.88, 0.95)

STEADY_N_TOL: float = 1.0e-3
STEADY_TAVG_TOL: float = 0.05  # [K]
STEADY_P_STEAM_TOL: float = 5.0e3  # [Pa]
STEADY_LEVEL_TOL: float = 1.0e-3
STEADY_LOAD_TOL: float = 1.0e-9
ENERGY_BALANCE_FRAC: float = 5.0e-3
TRANSIENT_ENERGY_BALANCE_FRAC: float = 1.0e-2
MASS_DRIFT_LIMIT: float = 1.0  # [kg]
AUTO_TAVG_TREF_TOL: float = 1.0  # [K]
STEAM_PRESSURE_MAX_ON_TRIP: float = 8.5e6  # [Pa]
SCRAM_N_MAX: float = 1.0e-2
HUGE_SHELL_TAVG_TOL: float = 0.5  # [K]


@dataclass(frozen=True)
class CriterionResult:
    """One validation-table row.

    Parameters
    ----------
    criterion : str
        Human-readable criterion name.
    measured : str
        Measured value formatted for a markdown table.
    limit : str
        Acceptance limit formatted for a markdown table.
    passed : bool
        True when the criterion passed.
    """

    criterion: str
    measured: str
    limit: str
    passed: bool


def result(criterion: str, measured: float | str, limit: str, passed: bool) -> CriterionResult:
    """Build a formatted criterion result.

    Parameters
    ----------
    criterion : str
        Human-readable criterion name.
    measured : float or str
        Numeric or preformatted measured value.
    limit : str
        Acceptance limit.
    passed : bool
        True if accepted.

    Returns
    -------
    CriterionResult
        Markdown-ready validation row.
    """
    if isinstance(measured, str):
        measured_text = measured
    else:
        measured_text = f"{measured:.6g}"
    return CriterionResult(criterion=criterion, measured=measured_text, limit=limit, passed=bool(passed))


def run_dense(engine, t_end: float, scenario: ScenarioFn, *, check: bool = True) -> list[dict[str, Any]]:
    """Integrate with one dense BDF run and return uniformly sampled snapshots.

    Parameters
    ----------
    engine : SimEngine
        Finalized or finalizable engine.
    t_end : float
        End time [s].
    scenario : callable
        ``scenario(t) -> dict`` external overrides.
    check : bool, default True
        When true, run ``check_snapshot`` on every sampled accepted state.

    Returns
    -------
    list of dict
        Snapshots from the engine's start time to ``t_end`` [s], sampled at
        ``DT`` spacing with the exact endpoint always included.
    """
    t_start = float(engine.t)
    _final, dense = engine.run(t_end, scenario_fn=scenario, dense=True, max_step=0.5)
    times = np.arange(t_start, t_end, DT)
    times = times[times < t_end - 1e-12]
    times = np.append(times, t_end)
    snaps = dense.at(times)
    if check:
        for snap in snaps:
            check_snapshot(snap)
    return snaps


def series(snaps: list[dict[str, Any]], module: str, key: str) -> np.ndarray:
    """Return one telemetry key as a numpy array.

    Parameters
    ----------
    snaps : list of dict
        Snapshots from :func:`run_dense`.
    module : str
        Snapshot module key.
    key : str
        Telemetry key inside that module.

    Returns
    -------
    np.ndarray
        Numeric series in snapshot order.
    """
    return np.array([s[module][key] for s in snaps], dtype=float)


def ramp_to(load_end: float, t0: float = 10.0, rate: float = 8.33e-4) -> ScenarioFn:
    """Return a turbine-load ramp from 1.0 to ``load_end``.

    Parameters
    ----------
    load_end : float
        Final valve-admission demand [-].
    t0 : float, default 10.0
        Time at which the ramp starts [s].
    rate : float, default 8.33e-4
        Demand ramp rate [1/s], 5 %/min by default.

    Returns
    -------
    callable
        Scenario function returning ``{"turbine_load": demand}``.
    """

    def scenario(t: float) -> dict[str, float]:
        if t <= t0:
            return {"turbine_load": 1.0}
        return {"turbine_load": max(load_end, 1.0 - rate * (t - t0))}

    return scenario


def secondary_energy_fraction(snap: dict[str, Any]) -> float:
    """Return the absolute secondary energy-balance residual fraction.

    Parameters
    ----------
    snap : dict
        Engine snapshot with ``sg``, ``sg_sec`` and ``turbine`` modules.

    Returns
    -------
    float
        ``abs(Q_sg - m_out * (h_g - h_fw)) / abs(Q_sg)`` [-].
    """
    Q_sg = snap["sg"]["Q_sg"]
    m_out = snap["turbine"]["m_steam"] + snap["turbine"]["m_dump"]
    P = snap["sg_sec"]["P_steam"]
    h_g = coolprop.sat_vapor_enthalpy(P=P)
    h_fw = coolprop.enthalpy_PT(P=P, T=SGSecondaryParams().T_fw)
    return abs(Q_sg - m_out * (h_g - h_fw)) / abs(Q_sg)


__all__ = [
    "AUTO_TAVG_TREF_TOL",
    "AUTO_N_BAND",
    "CriterionResult",
    "DT",
    "ENERGY_BALANCE_FRAC",
    "HUGE_SHELL_TAVG_TOL",
    "MANUAL_N_BAND",
    "MANUAL_P_STEAM_BAND",
    "MANUAL_TAVG_BAND",
    "MASS_DRIFT_LIMIT",
    "SCRAM_N_MAX",
    "STEADY_LEVEL_TOL",
    "STEADY_LOAD_TOL",
    "STEADY_N_TOL",
    "STEADY_P_STEAM_TOL",
    "STEADY_TAVG_TOL",
    "STEAM_PRESSURE_MAX_ON_TRIP",
    "TRANSIENT_ENERGY_BALANCE_FRAC",
    "TRIP_N_BAND",
    "TRIP_P_STEAM_BAND",
    "TRIP_TAVG_BAND",
    "ramp_to",
    "result",
    "run_dense",
    "secondary_energy_fraction",
    "series",
]
