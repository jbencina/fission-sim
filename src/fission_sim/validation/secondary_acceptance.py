"""Shared M3 secondary-side acceptance helpers and threshold constants.

The pytest acceptance suite and ``scripts/validate_secondary.py`` both import
this module so the scenario definitions and numerical limits cannot drift.
It intentionally contains no pytest or plotting code.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import numpy as np

from fission_sim.physics.domain import check_snapshot

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
STEADY_HEAT_RATE_MISMATCH_FRAC: float = 5.0e-3
LOAD_HEAT_RATE_MISMATCH_FRAC: float = 1.0e-2
# The accumulation check normalizes the largest trapezoid-vs-state error to
# the largest observed |ΔU_sec|. With DT = 1 s, the manual-load scenario's
# measured numerical quadrature error is roughly 3e-5 of ΔU, so 1e-3 leaves
# room for solver/library roundoff while still detecting a wrong first-law term.
TRANSIENT_ENERGY_ACCUMULATION_FRAC: float = 1.0e-3
# Legacy names retained for scripts written before M3.9.2; the quantities are
# equilibrium heat-rate mismatches, not transient energy balances.
ENERGY_BALANCE_FRAC: float = STEADY_HEAT_RATE_MISMATCH_FRAC
TRANSIENT_ENERGY_BALANCE_FRAC: float = LOAD_HEAT_RATE_MISMATCH_FRAC
MASS_DRIFT_LIMIT: float = 1.0  # [kg]
MASS_ACCUMULATION_FRAC: float = 1.0e-3
AUTO_TAVG_TREF_TOL: float = 1.0  # [K]
STEAM_PRESSURE_MAX_ON_TRIP: float = 8.5e6  # [Pa]
SCRAM_N_MAX: float = 1.0e-2
HUGE_SHELL_TAVG_TOL: float = 0.5  # [K]
M4_LEVEL_HOLD_TOL: float = 1.0e-3
M4_FLOW_MATCH_FRAC: float = 5.0e-3
M4_LOAD_LEVEL_EXCURSION: float = 0.05
M4_LOAD_LEVEL_RESIDUAL: float = 0.005
M4_SETPOINT_RESIDUAL: float = 0.01
M4_SETPOINT_OVERSHOOT_MAX: float = 0.57
M4_LOFW_HALT_BAND: tuple[float, float] = (30.0, 600.0)
M4_OVERFILL_HALT_BAND: tuple[float, float] = (200.0, 2000.0)
M4_TRIP_SCRAM_LEVEL_RESIDUAL: float = 0.02


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
    criterion = _renamed_criterion(criterion)
    if isinstance(measured, str):
        measured_text = measured
    else:
        measured_text = f"{measured:.6g}"
    return CriterionResult(criterion=criterion, measured=measured_text, limit=limit, passed=bool(passed))


def _renamed_criterion(criterion: str) -> str:
    """Return current names for criterion labels printed by older callers.

    Parameters
    ----------
    criterion : str
        Candidate criterion label.

    Returns
    -------
    str
        Updated criterion label.
    """
    renames = {
        "energy balance: secondary energy residual": "equilibrium: heat-rate mismatch",
        "load manual: secondary energy residual": "load manual: equilibrium heat-rate mismatch",
    }
    return renames.get(criterion, criterion)


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


def _secondary_shell_energy_rate(snap: dict[str, Any]) -> float:
    """Return the shell's net internal-energy accumulation rate.

    Parameters
    ----------
    snap : dict
        Engine snapshot with ``sg_sec`` and ``turbine`` telemetry.

    Returns
    -------
    float
        ``Q_sg + m_fw*h_fw - (m_steam + m_dump)*h_g`` [W].
    """
    sg_sec = snap["sg_sec"]
    turbine = snap["turbine"]
    Q_sg = sg_sec["Q_sg"]
    h_g = sg_sec["h_g"]
    h_fw = sg_sec["h_fw"]
    m_fw = sg_sec["m_fw"]
    m_out = turbine["m_steam"] + turbine["m_dump"]
    return Q_sg + m_fw * h_fw - m_out * h_g


def equilibrium_heat_rate_mismatch_fraction(snap: dict[str, Any]) -> float:
    """Return the final-equilibrium shell heat-rate mismatch fraction.

    Parameters
    ----------
    snap : dict
        Engine snapshot with ``sg_sec`` telemetry keys ``Q_sg`` [W],
        ``h_g`` [J/kg], ``h_fw`` [J/kg], and ``m_fw`` [kg/s], plus turbine
        telemetry keys ``m_steam`` [kg/s] and ``m_dump`` [kg/s].

    Returns
    -------
    float
        ``abs(Q_sg + m_fw*h_fw - (m_steam + m_dump)*h_g) / abs(Q_sg)`` [-].

    Notes
    -----
    This is an equilibrium heat-rate mismatch, not a transient conservation
    check. During real transients the same numerator is ``dU_sec/dt`` and need
    not be zero.
    """
    Q_sg = snap["sg_sec"]["Q_sg"]
    return abs(_secondary_shell_energy_rate(snap)) / max(abs(Q_sg), 1.0)


def secondary_energy_accumulation_fraction(snaps: list[dict[str, Any]]) -> float:
    """Compare integrated shell energy rate with stored internal-energy change.

    Parameters
    ----------
    snaps : list of dict
        Uniformly sampled engine snapshots from one transient run. Each
        snapshot must include ``t`` [s], ``sg_sec.U_sec`` [J], ``sg_sec.Q_sg``
        [W], ``sg_sec.h_g`` [J/kg], ``sg_sec.h_fw`` [J/kg],
        ``sg_sec.m_fw`` [kg/s], and turbine steam/dump flows [kg/s].

    Returns
    -------
    float
        ``max(|ΔU_sec - ∫dU_sec/dt dt|) / max(|ΔU_sec|)`` [-], using the
        trapezoid rule over the supplied samples. Returns 0 for fewer than two
        samples.

    Notes
    -----
    The integrand is the rigid control-volume first law:

    ``dU_sec/dt = Q_sg + m_fw*h_fw - (m_steam + m_dump)*h_g``

    All terms are taken from the same run's telemetry so custom feedwater
    temperature or non-matching feedwater flow remains covered.
    """
    if len(snaps) < 2:
        return 0.0

    t = np.array([snap["t"] for snap in snaps], dtype=float)
    U = np.array([snap["sg_sec"]["U_sec"] for snap in snaps], dtype=float)
    rates = np.array([_secondary_shell_energy_rate(snap) for snap in snaps], dtype=float)
    dt = np.diff(t)
    integral = np.zeros_like(rates)
    integral[1:] = np.cumsum(0.5 * (rates[:-1] + rates[1:]) * dt)
    dU = U - U[0]
    scale = max(float(np.max(np.abs(dU))), 1.0)
    return float(np.max(np.abs(dU - integral)) / scale)


def secondary_mass_accumulation_fraction(snaps: list[dict[str, Any]]) -> float:
    """Compare integrated shell net mass flow with stored mass change.

    Parameters
    ----------
    snaps : list of dict
        Uniformly sampled engine snapshots from one transient run. Each
        snapshot must include ``t`` [s], ``sg_sec.M_sec`` [kg],
        ``sg_sec.m_fw`` [kg/s], and turbine steam/dump flows [kg/s].

    Returns
    -------
    float
        ``max(|ΔM_sec - ∫(m_fw − m_steam − m_dump)dt|) / M_sec(0)`` [-],
        using the trapezoid rule over the supplied samples. Returns 0 for
        fewer than two samples.

    Notes
    -----
    The integrand is the rigid control-volume mass balance:

    ``dM_sec/dt = m_fw − m_steam − m_dump``

    M4 uses a dynamic feedwater actuator, so this is the mass-conservation
    check with a real inventory change that replaces the M3 exact-mass
    constancy assertion.
    """
    if len(snaps) < 2:
        return 0.0

    t = np.array([snap["t"] for snap in snaps], dtype=float)
    M = np.array([snap["sg_sec"]["M_sec"] for snap in snaps], dtype=float)
    net = np.array(
        [
            snap["sg_sec"]["m_fw"] - snap["turbine"]["m_steam"] - snap["turbine"]["m_dump"]
            for snap in snaps
        ],
        dtype=float,
    )
    integral = np.zeros_like(net)
    integral[1:] = np.cumsum(0.5 * (net[:-1] + net[1:]) * np.diff(t))
    dM = M - M[0]
    return float(np.max(np.abs(dM - integral)) / max(abs(M[0]), 1.0))


def secondary_energy_fraction(snap: dict[str, Any]) -> float:
    """Legacy alias for :func:`equilibrium_heat_rate_mismatch_fraction`.

    Parameters
    ----------
    snap : dict
        Engine snapshot.

    Returns
    -------
    float
        Equilibrium heat-rate mismatch fraction [-].
    """
    return equilibrium_heat_rate_mismatch_fraction(snap)


__all__ = [
    "AUTO_TAVG_TREF_TOL",
    "AUTO_N_BAND",
    "CriterionResult",
    "DT",
    "LOAD_HEAT_RATE_MISMATCH_FRAC",
    "ENERGY_BALANCE_FRAC",
    "HUGE_SHELL_TAVG_TOL",
    "MANUAL_N_BAND",
    "MANUAL_P_STEAM_BAND",
    "MANUAL_TAVG_BAND",
    "MASS_DRIFT_LIMIT",
    "MASS_ACCUMULATION_FRAC",
    "M4_FLOW_MATCH_FRAC",
    "M4_LEVEL_HOLD_TOL",
    "M4_LOAD_LEVEL_EXCURSION",
    "M4_LOAD_LEVEL_RESIDUAL",
    "M4_LOFW_HALT_BAND",
    "M4_OVERFILL_HALT_BAND",
    "M4_SETPOINT_OVERSHOOT_MAX",
    "M4_SETPOINT_RESIDUAL",
    "M4_TRIP_SCRAM_LEVEL_RESIDUAL",
    "SCRAM_N_MAX",
    "STEADY_LEVEL_TOL",
    "STEADY_LOAD_TOL",
    "STEADY_N_TOL",
    "STEADY_P_STEAM_TOL",
    "STEADY_TAVG_TOL",
    "STEADY_HEAT_RATE_MISMATCH_FRAC",
    "STEAM_PRESSURE_MAX_ON_TRIP",
    "TRANSIENT_ENERGY_ACCUMULATION_FRAC",
    "TRANSIENT_ENERGY_BALANCE_FRAC",
    "TRIP_N_BAND",
    "TRIP_P_STEAM_BAND",
    "TRIP_TAVG_BAND",
    "equilibrium_heat_rate_mismatch_fraction",
    "ramp_to",
    "result",
    "run_dense",
    "secondary_energy_accumulation_fraction",
    "secondary_energy_fraction",
    "secondary_mass_accumulation_fraction",
    "series",
]
