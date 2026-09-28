"""Run M3/M4 secondary-side acceptance scenarios and print a criteria table.

Examples
--------
Run with dense BDF sampling (same mode as the pytest acceptance helper)::

    uv run python scripts/validate_secondary.py --milestone m3 --out-dir artifacts/m3-validate

Run with dashboard-like fixed engine steps at 10 Hz simulated cadence::

    uv run python scripts/validate_secondary.py --milestone m4 --step-dt 0.1
"""

from __future__ import annotations

import argparse
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from fission_sim.physics import coolprop
from fission_sim.physics.domain import P_STEAM_MIN, ModelDomainError, check_secondary_domain, check_snapshot
from fission_sim.physics.sg_secondary import SGSecondaryParams
from fission_sim.plant import build_standard_plant
from fission_sim.validation.secondary_acceptance import (
    AUTO_N_BAND,
    AUTO_TAVG_TREF_TOL,
    DT,
    HUGE_SHELL_TAVG_TOL,
    LOAD_HEAT_RATE_MISMATCH_FRAC,
    M4_FLOW_MATCH_FRAC,
    M4_LEVEL_HOLD_TOL,
    M4_LOAD_LEVEL_EXCURSION,
    M4_LOAD_LEVEL_RESIDUAL,
    M4_LOFW_HALT_BAND,
    M4_OVERFILL_HALT_BAND,
    M4_SETPOINT_OVERSHOOT_MAX,
    M4_SETPOINT_RESIDUAL,
    M4_TRIP_SCRAM_LEVEL_RESIDUAL,
    MANUAL_N_BAND,
    MANUAL_P_STEAM_BAND,
    MANUAL_TAVG_BAND,
    MASS_ACCUMULATION_FRAC,
    SCRAM_N_MAX,
    STEADY_HEAT_RATE_MISMATCH_FRAC,
    STEADY_LEVEL_TOL,
    STEADY_LOAD_TOL,
    STEADY_N_TOL,
    STEADY_P_STEAM_TOL,
    STEADY_TAVG_TOL,
    STEAM_PRESSURE_MAX_ON_TRIP,
    TRANSIENT_ENERGY_ACCUMULATION_FRAC,
    TRIP_N_BAND,
    TRIP_P_STEAM_BAND,
    TRIP_TAVG_BAND,
    CriterionResult,
    equilibrium_heat_rate_mismatch_fraction,
    ramp_to,
    result,
    run_dense,
    secondary_energy_accumulation_fraction,
    secondary_mass_accumulation_fraction,
    series,
)

ScenarioFn = Callable[[float], dict[str, Any]]
UNPROTECTED_TURBINE_TRIP_TITLE = (
    "Unprotected turbine trip: automatic reactor trip on turbine trip omitted; "
    "ideal feedwater and combined dump/relief available"
)


@dataclass(frozen=True)
class Scenario:
    """One validation scenario.

    Parameters
    ----------
    slug : str
        File-name-safe scenario identifier.
    title : str
        Plot title and table prefix.
    t_end : float
        End time [s].
    scenario_fn : callable
        ``scenario_fn(t) -> dict`` external overrides.
    plant_kwargs : dict
        Keyword arguments passed to ``build_standard_plant``.
    caption : str, optional
        Additional plot caption text for scenario-specific interpretation
        limits.
    """

    slug: str
    title: str
    t_end: float
    scenario_fn: ScenarioFn
    plant_kwargs: dict[str, Any] | None = None
    caption: str | None = None


def _step_sample(engine, t_end: float, scenario: ScenarioFn, *, dt: float) -> list[dict[str, Any]]:
    """Drive ``engine.step(dt)`` and return snapshots sampled every ``DT``.

    Parameters
    ----------
    engine : SimEngine
        Engine to advance.
    t_end : float
        End time [s].
    scenario : callable
        Scenario external override function.
    dt : float
        Fixed step size [s].

    Returns
    -------
    list of dict
        Snapshots sampled at approximately ``0, DT, 2*DT, ...`` [s].
    """
    if dt <= 0.0:
        raise ValueError("--step-dt must be > 0")
    snaps = [engine.snapshot()]
    check_snapshot(snaps[0])
    next_sample = DT
    while engine.t < t_end - 1e-9:
        step = min(dt, t_end - engine.t)
        snap = engine.step(step, **scenario(engine.t))
        check_snapshot(snap)
        if snap["t"] >= next_sample - 1e-9 or snap["t"] >= t_end - 1e-9:
            snaps.append(snap)
            next_sample += DT
    return snaps


def _run_scenario(spec: Scenario, *, step_dt: float | None) -> list[dict[str, Any]]:
    """Run one standard-plant scenario in dense or fixed-step mode."""
    engine = build_standard_plant(**(spec.plant_kwargs or {}))
    if step_dt is None:
        return run_dense(engine, spec.t_end, spec.scenario_fn, check=True)
    return _step_sample(engine, spec.t_end, spec.scenario_fn, dt=step_dt)


def _plot_scenario(spec: Scenario, snaps: list[dict[str, Any]], out_dir: Path) -> None:
    """Save a six-panel PNG for one scenario."""
    t = np.array([s["t"] for s in snaps], dtype=float)
    n = series(snaps, "core", "n")
    T_avg = series(snaps, "loop", "T_avg")
    T_ref = series(snaps, "turbine", "T_ref")
    P_steam = series(snaps, "sg_sec", "P_steam") / 1e6
    m_dump = series(snaps, "turbine", "m_dump")
    level = series(snaps, "sg_sec", "level_sg")
    rod = series(snaps, "rod", "rod_position")
    P_electric = series(snaps, "turbine", "P_electric") / 1e6
    admission_actual = series(snaps, "turbine", "load") * 100.0
    admission_demand = series(snaps, "turbine", "load_demand") * 100.0

    fig, axes = plt.subplots(3, 2, figsize=(12, 10), sharex=True)
    ax = axes[0, 0]
    ax.plot(t, n)
    ax.set_ylabel("n [-]")
    ax.grid(alpha=0.3)

    ax = axes[0, 1]
    ax.plot(t, T_avg, label="T_avg")
    ax.plot(t, T_ref, label="T_ref")
    ax.set_ylabel("K")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)

    ax = axes[1, 0]
    ax.plot(t, P_steam, label="Steam pressure P_steam [MPa]")
    ax2 = ax.twinx()
    ax2.plot(t, m_dump, "tab:red", label="Combined dump/relief flow m_dump [kg/s]")
    ax.set_ylabel("MPa")
    ax2.set_ylabel("kg/s")
    handles, labels = ax.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(handles + handles2, labels + labels2, loc="best", fontsize=8)
    ax.grid(alpha=0.3)

    ax = axes[1, 1]
    ax.plot(t, level)
    ax.set_ylabel("SG collapsed liquid\nfraction [-]")
    ax.set_title("4 SGs lumped; no shrink/swell", fontsize=9)
    ax.grid(alpha=0.3)

    ax = axes[2, 0]
    ax.plot(t, rod)
    ax.set_ylabel("rod_position [-]")
    ax.set_xlabel("time [s]")
    ax.grid(alpha=0.3)

    ax = axes[2, 1]
    ax.plot(t, P_electric, label="Gross electrical power P_electric [MW]")
    ax2 = ax.twinx()
    ax2.plot(t, admission_demand, "--", color="tab:green", label="Turbine admission demand [%]")
    ax2.plot(t, admission_actual, color="tab:orange", label="Turbine admission actual [%]")
    ax.set_ylabel("MW")
    ax2.set_ylabel("admission [%]")
    ax.set_xlabel("time [s]")
    handles, labels = ax.get_legend_handles_labels()
    handles2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(handles + handles2, labels + labels2, loc="best", fontsize=8)
    ax.grid(alpha=0.3)

    fig.suptitle(textwrap.fill(spec.title, width=92))
    if spec.caption:
        fig.text(0.5, 0.01, textwrap.fill(spec.caption, width=130), ha="center", fontsize=8)
        fig.tight_layout(rect=(0.0, 0.04, 1.0, 0.96))
    else:
        fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.96))
    fig.savefig(out_dir / f"{spec.slug}.png", dpi=140)
    plt.close(fig)


def _between(value: float, band: tuple[float, float]) -> bool:
    return band[0] < value < band[1]


def _band_text(band: tuple[float, float], unit: str = "") -> str:
    suffix = f" {unit}" if unit else ""
    return f"{band[0]:.6g}..{band[1]:.6g}{suffix}"


def _criteria_for(spec: Scenario, snaps: list[dict[str, Any]]) -> list[CriterionResult]:
    """Evaluate the acceptance criteria for one scenario."""
    rows: list[CriterionResult] = []
    prefix = spec.slug.replace("_", " ")
    if spec.slug == "steady":
        n_err = abs(series(snaps, "core", "n")[-1] - 1.0)
        tavg_err = abs(series(snaps, "loop", "T_avg")[-1] - 583.0)
        p_steam_err = abs(series(snaps, "sg_sec", "P_steam")[-1] - SGSecondaryParams().P_ref)
        level_err = abs(series(snaps, "sg_sec", "level_sg")[-1] - 0.5)
        load_err = abs(series(snaps, "turbine", "load")[-1] - 1.0)
        rows.extend(
            [
                result(f"{prefix}: final n", n_err, f"< {STEADY_N_TOL}", n_err < STEADY_N_TOL),
                result(
                    f"{prefix}: final T_avg error",
                    tavg_err,
                    f"< {STEADY_TAVG_TOL} K",
                    tavg_err < STEADY_TAVG_TOL,
                ),
                result(
                    f"{prefix}: final P_steam error",
                    p_steam_err,
                    f"< {STEADY_P_STEAM_TOL} Pa",
                    p_steam_err < STEADY_P_STEAM_TOL,
                ),
                result(
                    f"{prefix}: final level error",
                    level_err,
                    f"< {STEADY_LEVEL_TOL}",
                    level_err < STEADY_LEVEL_TOL,
                ),
                result(
                    f"{prefix}: final turbine admission error",
                    load_err,
                    f"< {STEADY_LOAD_TOL}",
                    load_err < STEADY_LOAD_TOL,
                ),
            ]
        )
    elif spec.slug == "energy_balance":
        frac = equilibrium_heat_rate_mismatch_fraction(snaps[-1])
        rows.append(
            result(
                "equilibrium: heat-rate mismatch",
                frac,
                f"< {STEADY_HEAT_RATE_MISMATCH_FRAC}",
                frac < STEADY_HEAT_RATE_MISMATCH_FRAC,
            )
        )
    elif spec.slug == "mass_match":
        M = series(snaps, "sg_sec", "M_sec")
        frac = secondary_mass_accumulation_fraction(snaps)
        rows.extend(
            [
                result(
                    f"{prefix}: shell mass accumulation",
                    frac,
                    f"< {MASS_ACCUMULATION_FRAC}",
                    frac < MASS_ACCUMULATION_FRAC,
                ),
                result(f"{prefix}: nonzero ΔM", abs(M[-1] - M[0]), "> 100 kg", abs(M[-1] - M[0]) > 100.0),
            ]
        )
    elif spec.slug == "load_manual":
        n = series(snaps, "core", "n")[-1]
        T_avg = series(snaps, "loop", "T_avg")[-1]
        P = series(snaps, "sg_sec", "P_steam")
        heat_rate_frac = equilibrium_heat_rate_mismatch_fraction(snaps[-1])
        accumulation_frac = secondary_energy_accumulation_fraction(snaps)
        rows.extend(
            [
                result(f"{prefix}: final n", n, _band_text(MANUAL_N_BAND), _between(n, MANUAL_N_BAND)),
                result(
                    f"{prefix}: final T_avg",
                    T_avg,
                    _band_text(MANUAL_TAVG_BAND, "K"),
                    _between(T_avg, MANUAL_TAVG_BAND),
                ),
                result(
                    f"{prefix}: final P_steam",
                    P[-1],
                    _band_text(MANUAL_P_STEAM_BAND, "Pa"),
                    _between(P[-1], MANUAL_P_STEAM_BAND),
                ),
                result(f"{prefix}: T_avg warmed", T_avg, "> 583.5 K", T_avg > 583.5),
                result(f"{prefix}: P_steam rose", P[-1] - P[0], "> 100000 Pa", P[-1] > P[0] + 1e5),
                result(
                    f"{prefix}: equilibrium heat-rate mismatch",
                    heat_rate_frac,
                    f"< {LOAD_HEAT_RATE_MISMATCH_FRAC}",
                    heat_rate_frac < LOAD_HEAT_RATE_MISMATCH_FRAC,
                ),
                result(
                    f"{prefix}: shell energy accumulation",
                    accumulation_frac,
                    f"< {TRANSIENT_ENERGY_ACCUMULATION_FRAC}",
                    accumulation_frac < TRANSIENT_ENERGY_ACCUMULATION_FRAC,
                ),
            ]
        )
    elif spec.slug == "load_auto":
        T_ref = series(snaps, "turbine", "T_ref")[-1]
        T_avg = series(snaps, "loop", "T_avg")[-1]
        rod = series(snaps, "rod", "rod_position")[-1]
        n = series(snaps, "core", "n")[-1]
        tref_err = abs(T_ref - (565.0 + 18.0 * 0.9))
        t_err = abs(T_avg - T_ref)
        rows.extend(
            [
                result(f"{prefix}: final T_ref", tref_err, "< 1e-6 K", tref_err < 1e-6),
                result(
                    f"{prefix}: |T_avg - T_ref|",
                    t_err,
                    f"<= {AUTO_TAVG_TREF_TOL} K",
                    t_err <= AUTO_TAVG_TREF_TOL,
                ),
                result(f"{prefix}: rods inserted", rod, "< 0.5", rod < 0.5),
                result(f"{prefix}: final n", n, _band_text(AUTO_N_BAND), _between(n, AUTO_N_BAND)),
            ]
        )
    elif spec.slug == "turbine_trip":
        P = series(snaps, "sg_sec", "P_steam")
        m_dump = series(snaps, "turbine", "m_dump")
        load = series(snaps, "turbine", "load")[-1]
        n = series(snaps, "core", "n")[-1]
        T_avg = series(snaps, "loop", "T_avg")[-1]
        rows.extend(
            [
                result(
                    f"{prefix}: max P_steam",
                    float(P.max()),
                    f"< {STEAM_PRESSURE_MAX_ON_TRIP} Pa",
                    P.max() < STEAM_PRESSURE_MAX_ON_TRIP,
                ),
                result(f"{prefix}: max m_dump", float(m_dump.max()), "> 0 kg/s", m_dump.max() > 0.0),
                result(f"{prefix}: final load", load, "< 0.001", load < 1e-3),
                result(f"{prefix}: final n", n, _band_text(TRIP_N_BAND), _between(n, TRIP_N_BAND)),
                result(
                    f"{prefix}: final T_avg",
                    T_avg,
                    _band_text(TRIP_TAVG_BAND, "K"),
                    _between(T_avg, TRIP_TAVG_BAND),
                ),
                result(
                    f"{prefix}: final P_steam",
                    P[-1],
                    _band_text(TRIP_P_STEAM_BAND, "Pa"),
                    _between(P[-1], TRIP_P_STEAM_BAND),
                ),
            ]
        )
    elif spec.slug == "scram_alone":
        load = series(snaps, "turbine", "load")[-1]
        P_max = float(series(snaps, "sg_sec", "P_steam").max())
        n = series(snaps, "core", "n")[-1]
        rows.extend(
            [
                result(f"{prefix}: final load", load, "< 0.001", load < 1e-3),
                result(
                    f"{prefix}: max P_steam",
                    P_max,
                    f"< {STEAM_PRESSURE_MAX_ON_TRIP} Pa",
                    P_max < STEAM_PRESSURE_MAX_ON_TRIP,
                ),
                result(f"{prefix}: final n", n, f"< {SCRAM_N_MAX}", n < SCRAM_N_MAX),
            ]
        )
    elif spec.slug == "trip_scram":
        n = series(snaps, "core", "n")[-1]
        margin = series(snaps, "pzr", "T_sat") - series(snaps, "loop", "T_hot")
        rows.extend(
            [
                result(f"{prefix}: final n", n, f"< {SCRAM_N_MAX}", n < SCRAM_N_MAX),
                result(f"{prefix}: min primary subcooling", float(margin.min()), "> 0 K", margin.min() > 0.0),
            ]
        )
    return rows


def _huge_shell_criterion(*, step_dt: float | None) -> CriterionResult:
    """Evaluate the M3-vs-M2 huge-shell regression criterion."""
    def scenario(t: float) -> dict[str, bool]:
        return {"scram": t >= 10.0}

    if step_dt is None:
        a = run_dense(_build_m2_plant(), 300.0, scenario, check=False)
        b = run_dense(
            build_standard_plant(sg_sec_params=SGSecondaryParams(V_sec=6.0e7)),
            300.0,
            scenario,
            check=False,
        )
    else:
        a = _step_sample(_build_m2_plant(), 300.0, scenario, dt=step_dt)
        b = _step_sample(
            build_standard_plant(sg_sec_params=SGSecondaryParams(V_sec=6.0e7)),
            300.0,
            scenario,
            dt=step_dt,
        )
    dT = series(a, "loop", "T_avg") - series(b, "loop", "T_avg")
    measured = float(np.max(np.abs(dT)))
    return result(
        "huge shell: max |T_avg(M2)-T_avg(M3)|",
        measured,
        f"< {HUGE_SHELL_TAVG_TOL} K",
        measured < HUGE_SHELL_TAVG_TOL,
    )


def _build_m2_plant():
    """Build the fixed-secondary M2 plant for the huge-shell comparison."""
    from fission_sim.control.pressurizer_controller import PressurizerController, PressurizerControllerParams
    from fission_sim.engine import SimEngine
    from fission_sim.physics.core import CoreParams, PointKineticsCore
    from fission_sim.physics.pressurizer import Pressurizer, PressurizerParams
    from fission_sim.physics.primary_loop import LoopParams, PrimaryLoop
    from fission_sim.physics.rod_controller import RodController, RodParams
    from fission_sim.physics.secondary_sink import SecondarySink, SinkParams
    from fission_sim.physics.steam_generator import SGParams, SteamGenerator

    engine = SimEngine()
    loop_params = LoopParams()
    pzr_params = PressurizerParams(loop_params=loop_params)
    ctrl_params = PressurizerControllerParams()

    rod = engine.module(RodController(RodParams()), name="rod")
    core = engine.module(PointKineticsCore(CoreParams()), name="core")
    loop = engine.module(PrimaryLoop(loop_params), name="loop")
    sg = engine.module(SteamGenerator(SGParams()), name="sg")
    sink = engine.module(SecondarySink(SinkParams()), name="sink")
    pzr = engine.module(Pressurizer(pzr_params), name="pzr")
    pzr_ctrl = engine.module(PressurizerController(ctrl_params), name="pzr_ctrl")

    rod_cmd = engine.input("rod_command", default=0.5)
    scram = engine.input("scram", default=False)
    P_setpoint = engine.input("P_setpoint", default=ctrl_params.P_setpoint_default)
    heater_manual = engine.input("heater_manual", default=None)
    spray_manual = engine.input("spray_manual", default=None)

    rod(rod_command=rod_cmd, scram=scram)
    T_sec = sink()
    Q_sg = sg(T_avg=loop.T_avg, T_secondary=T_sec)
    core(rho_rod=rod.rho_rod, T_cool=loop.T_cool)
    pzr(
        Q_fuel_to_coolant=core.Q_fuel_to_coolant,
        Q_sg=Q_sg,
        T_hotleg=loop.T_hot,
        T_coldleg=loop.T_cold,
        Q_heater=pzr_ctrl.Q_heater,
        m_dot_spray=pzr_ctrl.m_dot_spray,
    )
    pzr_ctrl(P=pzr.P, P_setpoint=P_setpoint, heater_manual=heater_manual, spray_manual=spray_manual)
    loop(
        Q_fuel_to_coolant=core.Q_fuel_to_coolant,
        Q_sg=Q_sg,
        m_dot_spray=pzr_ctrl.m_dot_spray,
        P_primary=pzr.P,
    )
    engine.finalize()
    return engine


def _domain_criteria() -> list[CriterionResult]:
    """Evaluate static secondary-domain criteria."""
    rows: list[CriterionResult] = []
    p_sat_fw = coolprop.P_sat(T=SGSecondaryParams().T_fw)
    rows.append(
        result(
            "domain: P_STEAM_MIN above P_sat(T_fw)",
            P_STEAM_MIN - p_sat_fw,
            "> 0 Pa",
            P_STEAM_MIN > p_sat_fw,
        )
    )
    for label, kwargs, limit in (
        ("domain: low steam pressure", {"P_steam": 0.4e6, "x_sg": 0.05}, "steam_pressure"),
        ("domain: dry shell", {"P_steam": 7.0e6, "x_sg": 1.0}, "sg_dry"),
        ("domain: solid shell", {"P_steam": 7.0e6, "x_sg": 0.0}, "sg_solid"),
    ):
        try:
            check_secondary_domain(**kwargs)
        except ModelDomainError as err:
            rows.append(result(label, err.limit, limit, err.limit == limit))
        else:
            rows.append(result(label, "no error", limit, False))
    return rows


def _m3_scenarios() -> list[Scenario]:
    """Return the M3 scenario set."""
    return [
        Scenario("steady", "Design steady state, 600 s", 600.0, lambda t: {}),
        Scenario("energy_balance", "Steady secondary energy balance, 60 s", 60.0, lambda t: {}),
        Scenario(
            "mass_match",
            "Secondary shell mass accumulation, 600 s",
            600.0,
            ramp_to(0.8),
        ),
        Scenario("load_manual", "100% to 90% turbine admission, rods manual", 1500.0, ramp_to(0.9)),
        Scenario(
            "load_auto",
            "100% to 90% turbine admission, rods automatic",
            1800.0,
            lambda t: {**ramp_to(0.9)(t), "rod_auto": True},
            {"rod_auto": True},
        ),
        Scenario(
            "turbine_trip",
            UNPROTECTED_TURBINE_TRIP_TITLE,
            600.0,
            lambda t: {"turbine_trip": t >= 10.0},
            caption="P-4 is only the SCRAM-to-turbine-trip direction here; this is not a normal protected trip.",
        ),
        Scenario("scram_alone", "SCRAM alone trips turbine via P-4", 600.0, lambda t: {"scram": t >= 10.0}),
        Scenario(
            "trip_scram",
            "Turbine trip with SCRAM",
            900.0,
            lambda t: {"turbine_trip": t >= 10.0, "scram": t >= 10.0},
        ),
    ]


def run_m3(out_dir: Path, *, step_dt: float | None) -> list[CriterionResult]:
    """Run M3 validation, save plots and return all criteria rows."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[CriterionResult] = []
    for spec in _m3_scenarios():
        snaps = _run_scenario(spec, step_dt=step_dt)
        _plot_scenario(spec, snaps, out_dir)
        rows.extend(_criteria_for(spec, snaps))
    rows.append(_huge_shell_criterion(step_dt=step_dt))
    rows.extend(_domain_criteria())
    return rows


def _run_until_model_limit(
    spec: Scenario,
    *,
    dt: float,
) -> tuple[list[dict[str, Any]], str | None, float | None]:
    """Step one scenario until a model-domain limit is reached.

    Parameters
    ----------
    spec : Scenario
        Scenario to run. ``spec.t_end`` is the maximum simulated time [s].
    dt : float
        Step size [s]. M4 acceptance uses 1 s steps for halting cases.

    Returns
    -------
    tuple
        ``(snapshots, limit, t_halt)``. ``limit`` and ``t_halt`` are None if
        no model limit was reached before ``spec.t_end``.
    """
    engine = build_standard_plant(**(spec.plant_kwargs or {}))
    snaps = [engine.snapshot()]
    check_snapshot(snaps[0])
    while engine.t < spec.t_end - 1e-9:
        snap = engine.step(min(dt, spec.t_end - engine.t), **spec.scenario_fn(engine.t))
        snaps.append(snap)
        try:
            check_snapshot(snap)
        except ModelDomainError as err:
            return snaps, err.limit, snap["t"]
    return snaps, None, None


def _criteria_for_m4_nonhalting(spec: Scenario, snaps: list[dict[str, Any]]) -> list[CriterionResult]:
    """Evaluate M4 non-halting SG-level criteria."""
    rows: list[CriterionResult] = []
    prefix = spec.slug.replace("_", " ")
    level = series(snaps, "sg_sec", "level_sg")

    if spec.slug == "m4_steady":
        m_fw = series(snaps, "feedwater", "m_fw")
        m_out = series(snaps, "turbine", "m_steam") + series(snaps, "turbine", "m_dump")
        level_err = float(np.max(np.abs(level - 0.5)))
        flow_frac = float(abs(m_fw[-1] - m_out[-1]) / max(abs(m_out[-1]), 1.0))
        rows.extend(
            [
                result(
                    f"{prefix}: max level error",
                    level_err,
                    f"< {M4_LEVEL_HOLD_TOL}",
                    level_err < M4_LEVEL_HOLD_TOL,
                ),
                result(
                    f"{prefix}: final feed/steam mismatch",
                    flow_frac,
                    f"< {M4_FLOW_MATCH_FRAC}",
                    flow_frac < M4_FLOW_MATCH_FRAC,
                ),
            ]
        )
    elif spec.slug == "m4_mass_integral":
        M = series(snaps, "sg_sec", "M_sec")
        mass_frac = secondary_mass_accumulation_fraction(snaps)
        energy_frac = secondary_energy_accumulation_fraction(snaps)
        rows.extend(
            [
                result(
                    f"{prefix}: shell mass accumulation",
                    mass_frac,
                    f"< {MASS_ACCUMULATION_FRAC}",
                    mass_frac < MASS_ACCUMULATION_FRAC,
                ),
                result(f"{prefix}: nonzero ΔM", abs(M[-1] - M[0]), "> 100 kg", abs(M[-1] - M[0]) > 100.0),
                result(
                    f"{prefix}: shell energy accumulation",
                    energy_frac,
                    f"< {TRANSIENT_ENERGY_ACCUMULATION_FRAC}",
                    energy_frac < TRANSIENT_ENERGY_ACCUMULATION_FRAC,
                ),
            ]
        )
    elif spec.slug == "m4_load_auto_level":
        excursion = float(np.max(np.abs(level - 0.5)))
        residual = float(abs(level[-1] - 0.5))
        rows.extend(
            [
                result(
                    f"{prefix}: max level excursion",
                    excursion,
                    f"< {M4_LOAD_LEVEL_EXCURSION}",
                    excursion < M4_LOAD_LEVEL_EXCURSION,
                ),
                result(
                    f"{prefix}: final level residual",
                    residual,
                    f"< {M4_LOAD_LEVEL_RESIDUAL}",
                    residual < M4_LOAD_LEVEL_RESIDUAL,
                ),
            ]
        )
    elif spec.slug == "m4_setpoint_step":
        residual = float(abs(level[-1] - 0.55))
        max_level = float(level.max())
        rows.extend(
            [
                result(
                    f"{prefix}: final setpoint residual",
                    residual,
                    f"< {M4_SETPOINT_RESIDUAL}",
                    residual < M4_SETPOINT_RESIDUAL,
                ),
                result(
                    f"{prefix}: overshoot ceiling",
                    max_level,
                    f"< {M4_SETPOINT_OVERSHOOT_MAX}",
                    max_level < M4_SETPOINT_OVERSHOOT_MAX,
                ),
            ]
        )
    elif spec.slug == "m4_trip_scram_level":
        min_level = float(level.min())
        max_level = float(level.max())
        residual = float(abs(level[-1] - 0.5))
        rows.extend(
            [
                result(f"{prefix}: min level", min_level, "> 0.30", min_level > 0.30),
                result(f"{prefix}: max level", max_level, "< 0.95", max_level < 0.95),
                result(
                    f"{prefix}: final level residual",
                    residual,
                    f"< {M4_TRIP_SCRAM_LEVEL_RESIDUAL}",
                    residual < M4_TRIP_SCRAM_LEVEL_RESIDUAL,
                ),
            ]
        )
    return rows


def _m4_scenarios() -> list[Scenario]:
    """Return the M4 SG-level scenario set."""
    return [
        Scenario("m4_steady", "M4 level holds at setpoint for 600 s", 600.0, lambda t: {}),
        Scenario("m4_mass_integral", "M4 shell mass equals integrated net flow", 600.0, ramp_to(0.8)),
        Scenario(
            "m4_load_auto_level",
            "M4 100% to 90% turbine admission, rods automatic",
            1800.0,
            lambda t: {**ramp_to(0.9)(t), "rod_auto": True},
            {"rod_auto": True},
        ),
        Scenario(
            "m4_setpoint_step",
            "M4 SG collapsed-level setpoint step 0.50 to 0.55",
            1200.0,
            lambda t: {"level_setpoint": 0.55 if t >= 10.0 else 0.5},
        ),
        Scenario(
            "m4_loss_of_feedwater",
            "M4 loss of feedwater at power",
            600.0,
            lambda t: {"feedwater_manual": 0.0 if t >= 10.0 else None},
        ),
        Scenario(
            "m4_feedwater_max",
            "M4 manual feedwater held at maximum",
            2000.0,
            lambda t: {"feedwater_manual": 1.0 if t >= 10.0 else None},
        ),
        Scenario(
            "m4_trip_scram_level",
            "M4 turbine trip plus SCRAM under automatic feedwater control",
            1200.0,
            lambda t: {"turbine_trip": t >= 10.0, "scram": t >= 10.0},
            caption="Level is SG collapsed liquid fraction: four SGs lumped; no indicated-level shrink/swell.",
        ),
    ]


def run_m4(out_dir: Path, *, step_dt: float | None) -> list[CriterionResult]:
    """Run M4 validation, save plots and return all criteria rows."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[CriterionResult] = []
    for spec in _m4_scenarios():
        if spec.slug == "m4_loss_of_feedwater":
            snaps, limit, t_halt = _run_until_model_limit(spec, dt=1.0)
            _plot_scenario(spec, snaps, out_dir)
            rows.extend(
                [
                    result(
                        f"{spec.slug}: limit",
                        limit or "no limit",
                        "sg_tubes_uncovered",
                        limit == "sg_tubes_uncovered",
                    ),
                    result(
                        f"{spec.slug}: halt time",
                        t_halt if t_halt is not None else "none",
                        _band_text(M4_LOFW_HALT_BAND, "s"),
                        t_halt is not None and _between(t_halt, M4_LOFW_HALT_BAND),
                    ),
                ]
            )
        elif spec.slug == "m4_feedwater_max":
            snaps, limit, t_halt = _run_until_model_limit(spec, dt=1.0)
            _plot_scenario(spec, snaps, out_dir)
            rows.extend(
                [
                    result(f"{spec.slug}: limit", limit or "no limit", "sg_overfill", limit == "sg_overfill"),
                    result(
                        f"{spec.slug}: halt time",
                        t_halt if t_halt is not None else "none",
                        _band_text(M4_OVERFILL_HALT_BAND, "s"),
                        t_halt is not None and _between(t_halt, M4_OVERFILL_HALT_BAND),
                    ),
                ]
            )
        else:
            snaps = _run_scenario(spec, step_dt=step_dt)
            _plot_scenario(spec, snaps, out_dir)
            rows.extend(_criteria_for_m4_nonhalting(spec, snaps))

    shell = SGSecondaryParams(V_sec=6.0e7)
    try:
        snap = build_standard_plant(sg_sec_params=shell).snapshot()
    except ValueError as err:
        rows.append(result("factory: nondefault shell params", str(err), "constructs", False))
    else:
        ok = abs(snap["feedwater"]["m_fw_max"] - 1.2 * shell.m_steam_design) < 1.0e-9 * shell.m_steam_design
        rows.append(
            result("factory: nondefault shell feedwater defaults", snap["feedwater"]["m_fw_max"], "derived", ok)
        )
    return rows


def print_table(rows: list[CriterionResult]) -> None:
    """Print the markdown criteria table."""
    print("| criterion | measured | limit | pass |")
    print("|---|---:|---:|:---:|")
    for row in rows:
        print(f"| {row.criterion} | {row.measured} | {row.limit} | {'yes' if row.passed else 'NO'} |")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--milestone", choices=("m3", "m4"), required=True)
    parser.add_argument("--out-dir", type=Path, default=Path.cwd(), help="Directory for scenario PNGs")
    parser.add_argument(
        "--step-dt",
        type=float,
        default=None,
        help="Use fixed engine.step(dt) integration instead of dense run() sampling, e.g. 0.1 for 10 Hz",
    )
    return parser.parse_args()


def main() -> int:
    """CLI entry point."""
    args = parse_args()
    if args.milestone == "m4":
        rows = run_m4(args.out_dir, step_dt=args.step_dt)
    else:
        rows = run_m3(args.out_dir, step_dt=args.step_dt)
    print_table(rows)
    return 0 if all(row.passed for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
