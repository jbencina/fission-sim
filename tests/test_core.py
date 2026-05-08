"""Tests for src/fission_sim/physics/core.py.

Three layers (per spec §5):
  Layer 1 — pure derivative tests (no integration)
  Layer 2 — short-integration behavior tests
  Layer 3 — inhour-equation analytical test
"""

from dataclasses import replace

import numpy as np
import pytest
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from fission_sim.physics.core import CoreParams, PointKineticsCore


# ---------------------------------------------------------------------------
# Shared fixture: canonical L1 parameter set used by every test.
# Tests that need altered parameters use dataclasses.replace() to override.
# ---------------------------------------------------------------------------
def default_params() -> CoreParams:
    """Return the project-wide default L1 parameter set."""
    return CoreParams()


# ---------------------------------------------------------------------------
# CoreParams construction and self-consistency
# ---------------------------------------------------------------------------
def test_core_params_defaults_are_consistent():
    p = default_params()
    # Six delayed groups, total beta ~0.0065 for U-235 thermal
    assert p.beta_i.shape == (6,)
    assert p.lambda_i.shape == (6,)
    assert abs(p.beta_i.sum() - 0.0065) < 1e-3
    # Derived hA_fc closes steady-state energy balance
    expected_hA = p.P_design / (p.T_fuel_ref - p.T_cool_ref)
    assert p.hA_fc == pytest.approx(expected_hA)
    # Feedback coefficients are negative (stable PWR)
    assert p.alpha_f < 0
    assert p.alpha_m < 0


# ---------------------------------------------------------------------------
# Layer 1: pure derivative tests (no integration)
# ---------------------------------------------------------------------------
def test_state_layout_indices():
    core = PointKineticsCore(default_params())
    assert core.state_size == 8
    assert core.state_labels == (
        "n",
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
        "T_fuel",
    )


def test_initial_state_is_design_steady_state():
    p = default_params()
    core = PointKineticsCore(p)
    s = core.initial_state()

    assert s.shape == (8,)
    # n = 1 (normalized to design power)
    assert s[0] == pytest.approx(1.0)
    # C_i steady state: C_i = beta_i / (Lambda * lambda_i) at n=1
    expected_C = p.beta_i / (p.Lambda * p.lambda_i)
    assert s[1:7] == pytest.approx(expected_C)
    # T_fuel at reference
    assert s[7] == pytest.approx(p.T_fuel_ref)


def _design_inputs(p: CoreParams) -> dict:
    """Inputs that, with initial_state, yield zero derivatives."""
    return {"rho_rod": 0.0, "T_cool": p.T_cool_ref}


def test_design_steady_state_balances():
    p = default_params()
    core = PointKineticsCore(p)
    dstate = core.derivatives(core.initial_state(), _design_inputs(p))
    # At design steady state every derivative should be ~0
    assert np.allclose(dstate, 0.0, atol=1e-9)


def test_positive_reactivity_grows_n():
    p = default_params()
    core = PointKineticsCore(p)
    inputs = _design_inputs(p) | {"rho_rod": 100e-5}  # +100 pcm
    dstate = core.derivatives(core.initial_state(), inputs)
    assert dstate[0] > 0  # dn/dt > 0


def test_negative_reactivity_shrinks_n():
    p = default_params()
    core = PointKineticsCore(p)
    inputs = _design_inputs(p) | {"rho_rod": -100e-5}  # -100 pcm
    dstate = core.derivatives(core.initial_state(), inputs)
    assert dstate[0] < 0  # dn/dt < 0


def test_doppler_is_negative_feedback():
    p = default_params()
    core = PointKineticsCore(p)
    s = core.initial_state()
    s[7] = p.T_fuel_ref + 50.0  # raise fuel temperature 50 K
    inputs = _design_inputs(p)
    dstate = core.derivatives(s, inputs)
    # Higher fuel temp -> negative Doppler reactivity -> dn/dt should be
    # negative (assuming no other inputs change). With C_i still at the old
    # steady state, the reactivity drop dominates the precursor source.
    assert dstate[0] < 0


def test_outputs_returns_power_and_T_fuel():
    p = default_params()
    core = PointKineticsCore(p)
    s = core.initial_state()
    out = core.outputs(s)
    assert out["power_thermal"] == pytest.approx(p.P_design)  # n=1 at design
    assert out["T_fuel"] == pytest.approx(p.T_fuel_ref)


def test_outputs_scales_power_with_n():
    p = default_params()
    core = PointKineticsCore(p)
    s = core.initial_state()
    s[0] = 0.5  # half power
    s[7] = p.T_fuel_ref + 100.0  # also vary T_fuel away from reference
    out = core.outputs(s)
    assert out["power_thermal"] == pytest.approx(0.5 * p.P_design)
    assert out["T_fuel"] == pytest.approx(p.T_fuel_ref + 100.0)


def test_telemetry_with_inputs_decomposes_reactivity():
    p = default_params()
    core = PointKineticsCore(p)
    s = core.initial_state()
    s[7] = p.T_fuel_ref + 100.0  # raise T_fuel by 100 K
    inputs = {"rho_rod": 200e-5, "T_cool": p.T_cool_ref + 5.0}
    tele = core.telemetry(s, inputs)
    # All keys present
    expected_keys = {
        "power_thermal",
        "T_fuel",
        "n",
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
        "rho_total",
        "rho_rod",
        "rho_doppler",
        "rho_moderator",
        "startup_rate_dpm",
    }
    assert set(tele.keys()) == expected_keys
    # Decomposition
    assert tele["rho_rod"] == pytest.approx(200e-5)
    assert tele["rho_doppler"] == pytest.approx(p.alpha_f * 100.0)
    assert tele["rho_moderator"] == pytest.approx(p.alpha_m * 5.0)
    assert tele["rho_total"] == pytest.approx(tele["rho_rod"] + tele["rho_doppler"] + tele["rho_moderator"])


def test_telemetry_without_inputs_reports_none_for_input_dependent_keys():
    p = default_params()
    core = PointKineticsCore(p)
    s = core.initial_state()
    tele = core.telemetry(s)
    # State-only keys still present
    assert tele["power_thermal"] == pytest.approx(p.P_design)
    assert tele["T_fuel"] == pytest.approx(p.T_fuel_ref)
    # Doppler is computable from state alone
    assert tele["rho_doppler"] == pytest.approx(0.0)
    # The input-dependent ones are None
    assert tele["rho_rod"] is None
    assert tele["rho_moderator"] is None
    assert tele["rho_total"] is None
    # startup_rate also requires inputs (via dn/dt)
    assert tele["startup_rate_dpm"] is None


def test_startup_rate_zero_at_steady_state():
    """At design steady state, dn/dt ≈ 0 → startup rate ≈ 0 DPM."""
    p = default_params()
    core = PointKineticsCore(p)
    s = core.initial_state()
    inputs = {"rho_rod": 0.0, "T_cool": p.T_cool_ref}
    tele = core.telemetry(s, inputs)
    assert tele["startup_rate_dpm"] == pytest.approx(0.0, abs=1e-9)


def test_startup_rate_sign_matches_reactivity():
    """SUR > 0 when supercritical, SUR < 0 when subcritical.

    Magnitude depends on the regime — immediately after a step insertion
    (precursors not yet equilibrated) the prompt-jump value dominates and
    can be hundreds of DPM; asymptotic SUR for the delayed-neutron-driven
    period would be far smaller. We test sign here, not magnitude.
    """
    p = default_params()
    core = PointKineticsCore(p)
    s = core.initial_state()
    # +50 pcm: supercritical
    tele_pos = core.telemetry(s, {"rho_rod": +50e-5, "T_cool": p.T_cool_ref})
    assert tele_pos["startup_rate_dpm"] > 0.0
    # -50 pcm: subcritical
    tele_neg = core.telemetry(s, {"rho_rod": -50e-5, "T_cool": p.T_cool_ref})
    assert tele_neg["startup_rate_dpm"] < 0.0


def test_startup_rate_matches_explicit_formula():
    """Numerical sanity: SUR_dpm = (60 / ln(10)) · (1/n) · dn/dt."""
    p = default_params()
    core = PointKineticsCore(p)
    s = core.initial_state()
    inputs = {"rho_rod": 100e-5, "T_cool": p.T_cool_ref + 5.0}
    tele = core.telemetry(s, inputs)
    # Recompute dn/dt from derivatives() and the SUR formula by hand.
    dstate = core.derivatives(s, inputs)
    dn_dt = dstate[0]
    n = s[0]
    expected = (60.0 / np.log(10.0)) * (dn_dt / n)
    assert tele["startup_rate_dpm"] == pytest.approx(expected, rel=1e-9)


# ---------------------------------------------------------------------------
# Layer 2: short-integration behavior tests
# ---------------------------------------------------------------------------
def _integrate(core, rod_fn, T_cool_fn, t_end, t_start=0.0, max_step=0.5):
    """Integrate the core from initial_state under input functions of t.

    Parameters
    ----------
    core : PointKineticsCore
    rod_fn : Callable[[float], float]
        Returns rho_rod at time t.
    T_cool_fn : Callable[[float], float]
        Returns T_cool [K] at time t.
    t_end : float
        Final simulated time [s].
    """

    def f(t, y):
        return core.derivatives(
            y,
            {
                "rho_rod": rod_fn(t),
                "T_cool": T_cool_fn(t),
            },
        )

    return solve_ivp(
        f,
        (t_start, t_end),
        core.initial_state(),
        method="BDF",
        dense_output=True,
        rtol=1e-6,
        atol=1e-9,
        max_step=max_step,
    )


def test_steady_state_holds_for_60s():
    p = default_params()
    core = PointKineticsCore(p)
    sol = _integrate(
        core,
        rod_fn=lambda t: 0.0,
        T_cool_fn=lambda t: p.T_cool_ref,
        t_end=60.0,
    )
    assert sol.success
    n_final = sol.y[0, -1]
    assert n_final == pytest.approx(1.0, abs=1e-3)


def test_doppler_levels_off_power():
    """+200 pcm step with constant T_cool — Doppler should plateau power."""
    p = default_params()
    core = PointKineticsCore(p)
    sol = _integrate(
        core,
        rod_fn=lambda t: 200e-5,  # +200 pcm from t=0
        T_cool_fn=lambda t: p.T_cool_ref,
        t_end=100.0,
    )
    assert sol.success
    # Sample late in the run; power should be plateauing
    t_late = np.linspace(80.0, 100.0, 50)
    n_late = sol.sol(t_late)[0]
    assert n_late.min() > 1.0  # rose above unity
    assert n_late.max() < 100.0  # but did not run away

    # Plateau check: relative change over the last 20 s is small
    rel_change = abs(n_late[-1] - n_late[0]) / n_late[0]
    assert rel_change < 0.05


def test_scram_drops_power_then_decays():
    """Scram at t=10 — prompt drop, then slow delayed-neutron tail."""
    p = default_params()
    core = PointKineticsCore(p)

    def rod_fn(t):
        return -7000e-5 if t >= 10.0 else 0.0

    sol = _integrate(
        core,
        rod_fn=rod_fn,
        T_cool_fn=lambda t: p.T_cool_ref,
        t_end=300.0,
    )
    assert sol.success
    # Prompt drop: n at t=11 should be well below initial
    assert sol.sol(11.0)[0] < 0.1
    # Delayed-neutron tail: still nonzero at t=300 (long-lived precursors)
    assert sol.sol(300.0)[0] > 1e-4


def test_no_runaway_on_small_step():
    """Small +50 pcm step should give a tame, bounded response."""
    p = default_params()
    core = PointKineticsCore(p)
    sol = _integrate(
        core,
        rod_fn=lambda t: 50e-5,
        T_cool_fn=lambda t: p.T_cool_ref,
        t_end=60.0,
    )
    assert sol.success
    n_final = sol.y[0, -1]
    assert np.isfinite(n_final)
    assert n_final < 1000.0


# ---------------------------------------------------------------------------
# Layer 3: inhour-equation analytical test
# ---------------------------------------------------------------------------
def _inhour_period(rho: float, params: CoreParams) -> float:
    """Solve the inhour equation for the asymptotic reactor period.

    The point kinetics characteristic equation is:

        rho = omega * Lambda + sum_i [(omega * beta_i) / (omega + lambda_i)]

    For a positive reactivity step rho > 0 (and rho < beta), the largest
    positive root omega_1 of this equation determines the asymptotic
    exponential growth rate of the neutron population:

        n(t) ~ exp(omega_1 * t)   (for large t, after the prompt jump)

    The "asymptotic period" is T = 1 / omega_1 — the e-folding time.

    Returns
    -------
    float
        Asymptotic period [s]. Positive for positive reactivity.

    References
    ----------
    Lamarsh §7.4 (eq. 7.36-7.39); Duderstadt eq. 6.55.
    """

    def inhour_residual(omega: float) -> float:
        return omega * params.Lambda + np.sum((omega * params.beta_i) / (omega + params.lambda_i)) - rho

    # For rho > 0, the largest positive root sits between 0 and the
    # smallest lambda_i (about 0.0124 1/s). brentq needs a sign change.
    # Bracket on a tiny positive number and just below the smallest decay
    # constant.
    omega_1 = brentq(inhour_residual, 1e-8, params.lambda_i.min() - 1e-6)
    return 1.0 / omega_1


def test_inhour_asymptotic_period_50pcm():
    """Match the inhour equation for +50 pcm with feedback off, within 1%."""
    # Feedback off via parameter choice (no flag in production code)
    p = replace(default_params(), alpha_f=0.0, alpha_m=0.0)
    core = PointKineticsCore(p)
    rho = 50e-5  # +50 pcm — small enough to stay well below prompt critical

    def f(t, y):
        return core.derivatives(y, {"rho_rod": rho, "T_cool": p.T_cool_ref})

    sol = solve_ivp(
        f,
        (0.0, 300.0),
        core.initial_state(),
        method="BDF",
        dense_output=True,
        rtol=1e-9,
        atol=1e-12,
        max_step=0.5,
    )
    assert sol.success

    # Sample the asymptotic region — well past the transient (~first 100 s).
    # For +50 pcm the asymptotic period is ~137 s, so all transient modes
    # (faster decaying terms) have died out by t=100 s.
    t_grid = np.linspace(100.0, 300.0, 200)
    n_grid = sol.sol(t_grid)[0]

    # log(n) should be linear in t with slope = omega_1
    slope, _intercept = np.polyfit(t_grid, np.log(n_grid), 1)
    measured_period = 1.0 / slope

    expected_period = _inhour_period(rho, p)
    rel_err = abs(measured_period - expected_period) / expected_period
    assert rel_err < 0.01, (
        f"Measured period {measured_period:.4f} s vs inhour prediction "
        f"{expected_period:.4f} s (rel error {rel_err:.4%})"
    )
