"""Tests for src/fission_sim/physics/rod_controller.py.

Three layers (mirroring the rest of the physics package):
  Layer 1 — pure derivative + output tests (no integration)
  Layer 2 — short-integration behavior tests
  Layer 3 — analytical comparison (first-order lag in the small-step regime)
"""

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from fission_sim.physics.rod_controller import RodController, RodParams


def default_params() -> RodParams:
    """Return the project-wide default L1 rod-controller parameter set."""
    return RodParams()


def test_state_layout_indices():
    rod = RodController(default_params())
    assert rod.state_size == 1
    assert rod.state_labels == ("rod_position",)


def test_initial_state_is_design_position():
    p = default_params()
    rod = RodController(p)
    s = rod.initial_state()
    assert s.shape == (1,)
    assert s[0] == pytest.approx(p.rod_position_design)


# ---------------------------------------------------------------------------
# Layer 1: pure derivative tests (no integration)
# ---------------------------------------------------------------------------
def _design_inputs(p: RodParams) -> dict:
    """Inputs that, with initial_state, yield zero derivative."""
    return {"rod_command": p.rod_position_design, "scram": False}


def test_design_steady_state_balances():
    p = default_params()
    rod = RodController(p)
    dstate = rod.derivatives(rod.initial_state(), _design_inputs(p))
    assert np.allclose(dstate, 0.0, atol=1e-12)


def test_command_increase_withdraws_rod():
    """rod_command > current position → drod/dt > 0 (rods withdrawn)."""
    p = default_params()
    rod = RodController(p)
    inputs = _design_inputs(p) | {"rod_command": p.rod_position_design + 0.05}
    dstate = rod.derivatives(rod.initial_state(), inputs)
    assert dstate[0] > 0


def test_command_decrease_inserts_rod():
    """rod_command < current position → drod/dt < 0 (rods inserted)."""
    p = default_params()
    rod = RodController(p)
    inputs = _design_inputs(p) | {"rod_command": p.rod_position_design - 0.05}
    dstate = rod.derivatives(rod.initial_state(), inputs)
    assert dstate[0] < 0


def test_scram_overrides_command():
    """scram=True drives drod/dt < 0 even when rod_command says fully out."""
    p = default_params()
    rod = RodController(p)
    inputs = {"rod_command": 1.0, "scram": True}
    dstate = rod.derivatives(rod.initial_state(), inputs)
    assert dstate[0] < 0


def test_scram_at_max_velocity():
    """When scram=True from fully-withdrawn, the rate clip binds at -v_scram."""
    # Use tau=1 so raw rate = -1/1 = -1.0, which exceeds v_scram=0.5 and clips.
    p = RodParams(tau=1.0)
    rod = RodController(p)
    state = np.array([1.0])  # fully withdrawn
    inputs = {"rod_command": 1.0, "scram": True}
    dstate = rod.derivatives(state, inputs)
    # error = 0 - 1 = -1, raw rate = -1/tau = -1.0, clipped to -v_scram = -0.5
    assert dstate[0] == pytest.approx(-p.v_scram)


def test_normal_motion_at_max_velocity():
    """When command is far above current position, the rate clip binds at +v_normal."""
    p = default_params()
    rod = RodController(p)
    state = np.array([0.0])  # fully inserted
    inputs = {"rod_command": 1.0, "scram": False}
    dstate = rod.derivatives(state, inputs)
    # error = 1 - 0 = 1, raw rate = 1/tau = 0.1, clipped to +v_normal = 0.01
    assert dstate[0] == pytest.approx(p.v_normal)


def test_manual_insertion_without_scram_capped_at_v_normal():
    """Manual insertion (lowering rod_command without scram) is rate-capped
    at v_normal, not v_scram. v_scram applies only during gravity-drop
    scrams; motor-driven motion in either direction uses v_normal.
    """
    p = default_params()
    rod = RodController(p)
    state = np.array([1.0])  # fully withdrawn
    inputs = {"rod_command": 0.0, "scram": False}  # operator commands fully in, NO scram
    dstate = rod.derivatives(state, inputs)
    # error = 0 - 1 = -1, raw rate = -1/tau = -1.0
    # Clipped to -v_normal = -0.01 (NOT -v_scram = -0.5).
    assert dstate[0] == pytest.approx(-p.v_normal)
    assert dstate[0] != pytest.approx(-p.v_scram)  # explicit anti-regression


def test_small_motion_in_lag_region():
    """Small error → rate is error/tau (clip not binding, pure first-order lag)."""
    p = default_params()
    rod = RodController(p)
    # Small error of 0.005: raw rate = 0.005 / 10 = 5e-4 (well below v_normal=0.01)
    state = np.array([p.rod_position_design])
    inputs = {"rod_command": p.rod_position_design + 0.005, "scram": False}
    dstate = rod.derivatives(state, inputs)
    expected = 0.005 / p.tau
    assert dstate[0] == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Layer 1: outputs() and telemetry() tests
# ---------------------------------------------------------------------------
def test_rho_rod_at_critical():
    """At rod_position == rod_position_critical, rho_rod == 0."""
    p = default_params()
    rod = RodController(p)
    state = np.array([p.rod_position_critical])
    out = rod.outputs(state)
    assert out["rho_rod"] == pytest.approx(0.0)


def test_rho_rod_negative_below_critical():
    """rod_position below critical → negative reactivity (rods more inserted)."""
    p = default_params()
    rod = RodController(p)
    state = np.array([p.rod_position_critical - 0.1])
    out = rod.outputs(state)
    expected = p.rho_total_worth * (-0.1)
    assert out["rho_rod"] == pytest.approx(expected)
    assert out["rho_rod"] < 0


def test_rho_rod_positive_above_critical():
    """rod_position above critical → positive reactivity (rods more withdrawn)."""
    p = default_params()
    rod = RodController(p)
    state = np.array([p.rod_position_critical + 0.1])
    out = rod.outputs(state)
    expected = p.rho_total_worth * 0.1
    assert out["rho_rod"] == pytest.approx(expected)
    assert out["rho_rod"] > 0


def test_telemetry_with_inputs():
    p = default_params()
    rod = RodController(p)
    state = np.array([0.4])
    inputs = {"rod_command": 0.6, "scram": False}
    tele = rod.telemetry(state, inputs)
    expected_keys = {
        "rod_position",
        "rho_rod",
        "rod_command",
        "scram",
        "rod_command_effective",
    }
    assert set(tele.keys()) == expected_keys
    assert tele["rod_position"] == pytest.approx(0.4)
    assert tele["rod_command"] == pytest.approx(0.6)
    assert tele["scram"] is False
    assert tele["rod_command_effective"] == pytest.approx(0.6)


def test_telemetry_with_scram_zeroes_effective_command():
    """rod_command_effective should be 0 when scram is asserted."""
    p = default_params()
    rod = RodController(p)
    state = np.array([0.4])
    inputs = {"rod_command": 0.8, "scram": True}
    tele = rod.telemetry(state, inputs)
    assert tele["rod_command_effective"] == pytest.approx(0.0)
    assert tele["scram"] is True


def test_telemetry_without_inputs_reports_none():
    p = default_params()
    rod = RodController(p)
    tele = rod.telemetry(rod.initial_state())
    # State-derived keys still present
    assert tele["rod_position"] == pytest.approx(p.rod_position_design)
    assert tele["rho_rod"] == pytest.approx(0.0)
    # Input-dependent keys are None
    assert tele["rod_command"] is None
    assert tele["scram"] is None
    assert tele["rod_command_effective"] is None


# ---------------------------------------------------------------------------
# Layer 2: short-integration behavior tests
# ---------------------------------------------------------------------------
def _integrate(rod, command_fn, scram_fn, t_end, t_start=0.0, max_step=0.1):
    """Integrate the rod controller from initial_state under input functions."""

    def f(t, y):
        return rod.derivatives(
            y,
            {
                "rod_command": command_fn(t),
                "scram": scram_fn(t),
            },
        )

    return solve_ivp(
        f,
        (t_start, t_end),
        rod.initial_state(),
        method="BDF",
        dense_output=True,
        rtol=1e-7,
        atol=1e-10,
        max_step=max_step,
    )


def test_scram_reaches_zero_in_2s():
    """Start fully withdrawn, apply scram=True, integrate; should be essentially fully inserted by t=2s.

    tau=1.0 is used so the raw rate at full withdrawal is -1.0/s, which exceeds
    v_scram=0.5 and causes the clip to bind, giving constant-velocity full
    insertion in exactly 2 s.  (With tau=10 the clip never binds and scram
    would take ~5τ ≈ 50 s, which is deliberately outside the physical design
    envelope tested here.)
    """
    # tau=1 so raw_rate = (0 - 1) / 1 = -1.0, clipped to -v_scram = -0.5
    p_full_out = RodParams(tau=1.0, rod_position_design=1.0, rod_position_critical=1.0)
    rod = RodController(p_full_out)
    sol = _integrate(
        rod,
        command_fn=lambda t: 1.0,  # operator wants rods out, but scram wins
        scram_fn=lambda t: True,
        t_end=5.0,
    )
    assert sol.success
    # The clip (-v_scram=-0.5/s) binds for the first 2 s (while pos > 0.5*tau=0.5).
    # Once pos < 0.5 the system enters the lag regime and decays exponentially.
    # Analytically: pos(t) ≈ 0.5·exp(-(t-2)/τ) for t > 2 s, so pos(4s) ≈ 0.025.
    # Check at t=4.0 s for a robust threshold of ≤ 0.05.
    pos_at_4 = sol.sol(4.0)[0]
    assert pos_at_4 <= 0.05, f"position at t=4s is {pos_at_4:.4f}, expected ≤ 0.05"


def test_normal_step_tracks_setpoint():
    """Apply a step in rod_command; position should settle to within 1% of it."""
    p = default_params()
    rod = RodController(p)
    new_command = p.rod_position_design + 0.05  # +5% step
    sol = _integrate(
        rod,
        command_fn=lambda t: new_command,
        scram_fn=lambda t: False,
        t_end=120.0,  # plenty of time for the lag to settle
    )
    assert sol.success
    pos_final = sol.y[0, -1]
    assert pos_final == pytest.approx(new_command, rel=0.01)


# ---------------------------------------------------------------------------
# Layer 3: analytical comparison — first-order lag in the small-step regime
# ---------------------------------------------------------------------------
def test_lag_region_matches_first_order():
    """For a small step where the clip never binds, position should follow:

        position(t) = command + (initial - command) · exp(-t/τ)

    within 1%.
    """
    p = default_params()
    rod = RodController(p)
    # Small step: error = 0.005, raw rate = 0.005/10 = 5e-4 (below v_normal=0.01)
    new_command = p.rod_position_design + 0.005
    initial = p.rod_position_design
    sol = _integrate(
        rod,
        command_fn=lambda t: new_command,
        scram_fn=lambda t: False,
        t_end=30.0,  # several time constants
        max_step=0.5,  # smooth integration; no discontinuities
    )
    assert sol.success
    # Compare across multiple sample times to the analytic first-order solution
    t_grid = np.linspace(1.0, 30.0, 30)
    measured = sol.sol(t_grid)[0]
    expected = new_command + (initial - new_command) * np.exp(-t_grid / p.tau)
    rel_err = np.max(np.abs(measured - expected) / np.abs(expected))
    assert rel_err < 0.01, f"first-order lag mismatch: max rel err = {rel_err:.4%}"
