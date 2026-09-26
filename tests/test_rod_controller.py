"""Tests for src/fission_sim/physics/rod_controller.py.

Three layers (mirroring the rest of the physics package):
  Layer 1 — pure derivative + output tests (no integration)
  Layer 2 — short-integration behavior tests
  Layer 3 — analytical comparison (first-order lag in the small-step regime,
            constant-velocity SCRAM drop)

State layout: [rod_position (control bank), shutdown_position].
"""

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from fission_sim.physics.core import CoreParams
from fission_sim.physics.rod_controller import RodController, RodParams
from fission_sim.physics.secondary_sink import SinkParams


def default_params() -> RodParams:
    """Return the project-wide default rod-controller parameter set."""
    return RodParams()


def test_state_layout_indices():
    rod = RodController(default_params())
    assert rod.state_size == 2
    assert rod.state_labels == ("rod_position", "shutdown_position")


def test_initial_state_is_design_position():
    p = default_params()
    rod = RodController(p)
    s = rod.initial_state()
    assert s.shape == (2,)
    assert s[0] == pytest.approx(p.rod_position_design)
    assert s[1] == pytest.approx(1.0)  # shutdown bank fully withdrawn


def test_initial_state_override_via_rod_position_initial():
    """rod_position_initial overrides the default for initial_state()."""
    from dataclasses import replace

    p = replace(default_params(), rod_position_initial=0.1)
    rod = RodController(p)
    s = rod.initial_state()
    assert s[0] == pytest.approx(0.1)


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


def test_shutdown_bank_holds_fully_withdrawn_without_scram():
    """Operator commands move only the control bank."""
    p = default_params()
    rod = RodController(p)
    for cmd in (0.0, 0.5, 1.0):
        dstate = rod.derivatives(rod.initial_state(), {"rod_command": cmd, "scram": False})
        assert dstate[1] == pytest.approx(0.0)
    # Integrator round-off just below 1.0 must not read as a released bank.
    dstate = rod.derivatives(np.array([0.5, 1.0 - 1e-10]), {"rod_command": 0.5, "scram": False})
    assert dstate[1] == 0.0


def test_scram_overrides_command_and_inserts_both_banks():
    """scram=True inserts both banks even when rod_command says fully out."""
    p = default_params()
    rod = RodController(p)
    inputs = {"rod_command": 1.0, "scram": True}
    dstate = rod.derivatives(rod.initial_state(), inputs)
    assert dstate[0] < 0
    assert dstate[1] < 0


def test_scram_at_max_velocity():
    """Far from the bottom, a SCRAM drops each bank at exactly v_scram."""
    p = default_params()
    rod = RodController(p)
    state = np.array([1.0, 1.0])  # both banks fully withdrawn
    dstate = rod.derivatives(state, {"rod_command": 1.0, "scram": True})
    assert dstate == pytest.approx([-p.v_scram, -p.v_scram])


def test_scram_reset_returns_only_the_control_bank():
    """After the SCRAM latch clears, the control bank moves back toward the
    command at the motor-drive cap v_normal, but the shutdown bank stays
    inserted: withdrawing it is a reactor startup the model does not
    simulate, and doing it automatically re-criticalizes a cooled core."""
    p = default_params()
    rod = RodController(p)
    dstate = rod.derivatives(np.array([0.0, 0.0]), {"rod_command": 1.0, "scram": False})
    assert dstate[0] == pytest.approx(p.v_normal)
    assert dstate[1] == pytest.approx(0.0)


def test_released_shutdown_bank_finishes_its_drop_after_latch_clears():
    """A SCRAM cleared mid-drop cannot re-latch a falling shutdown bank."""
    p = default_params()
    rod = RodController(p)
    dstate = rod.derivatives(np.array([0.2, 0.5]), {"rod_command": 0.5, "scram": False})
    assert dstate[1] == pytest.approx(-p.v_scram)


def test_normal_motion_at_max_velocity():
    """When command is far above current position, the rate clip binds at +v_normal."""
    p = default_params()
    rod = RodController(p)
    state = np.array([0.0, 1.0])  # control bank fully inserted
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
    state = np.array([1.0, 1.0])  # control bank fully withdrawn
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
    # Small error of 0.005: raw rate = 0.005 / tau = 5e-3 (below v_normal=0.01)
    state = np.array([p.rod_position_design, 1.0])
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
    state = np.array([p.rod_position_critical, 1.0])
    out = rod.outputs(state)
    assert out["rho_rod"] == pytest.approx(0.0)


def test_rho_rod_negative_below_critical():
    """rod_position below critical → negative reactivity (rods more inserted)."""
    p = default_params()
    rod = RodController(p)
    state = np.array([p.rod_position_critical - 0.1, 1.0])
    out = rod.outputs(state)
    expected = p.rho_control_worth * (-0.1)
    assert out["rho_rod"] == pytest.approx(expected)
    assert out["rho_rod"] < 0


def test_rho_rod_positive_above_critical():
    """rod_position above critical → positive reactivity (rods more withdrawn)."""
    p = default_params()
    rod = RodController(p)
    state = np.array([p.rod_position_critical + 0.1, 1.0])
    out = rod.outputs(state)
    expected = p.rho_control_worth * 0.1
    assert out["rho_rod"] == pytest.approx(expected)
    assert out["rho_rod"] > 0


def test_full_range_operator_command_stays_below_prompt_critical():
    """The most reactivity the operator can add is full control-bank
    withdrawal (position 1.0, shutdown bank already out). It must stay
    below one dollar, sum(beta_i) of the core, or a slider move could make
    the reactor prompt critical (review finding A8)."""
    rod = RodController(default_params())
    beta = CoreParams().beta_i.sum()  # 0.006502 for the Keepin U-235 data
    rho_max = rod.outputs(np.array([1.0, 1.0]))["rho_rod"]
    assert 0.0 < rho_max < beta


def test_scram_worth_holds_core_subcritical_after_full_cooldown():
    """After a SCRAM from design, rod reactivity must outweigh the positive
    reactivity the negative temperature coefficients return as the plant
    cools. The coldest the model can get is the secondary sink temperature,
    so bound the feedback with fuel and coolant both there."""
    rod = RodController(default_params())
    core_p = CoreParams()
    T_floor = SinkParams().T_secondary
    rho_scrammed = rod.outputs(np.array([0.0, 0.0]))["rho_rod"]
    rho_feedback_max = core_p.alpha_f * (T_floor - core_p.T_fuel_ref) + core_p.alpha_m * (T_floor - core_p.T_cool_ref)
    assert rho_feedback_max > 0  # cooling returns positive reactivity
    assert rho_scrammed + rho_feedback_max < -0.05  # > 5,000 pcm shutdown margin


def test_telemetry_with_inputs():
    p = default_params()
    rod = RodController(p)
    state = np.array([0.4, 0.75])
    inputs = {"rod_command": 0.6, "scram": False}
    tele = rod.telemetry(state, inputs)
    expected_keys = {
        "rod_position",
        "shutdown_position",
        "rho_rod",
        "rho_control",
        "rho_shutdown",
        "rod_command",
        "scram",
        "rod_command_effective",
    }
    assert set(tele.keys()) == expected_keys
    assert tele["rod_position"] == pytest.approx(0.4)
    assert tele["shutdown_position"] == pytest.approx(0.75)
    assert tele["rho_control"] == pytest.approx(p.rho_control_worth * (0.4 - p.rod_position_critical))
    assert tele["rho_shutdown"] == pytest.approx(-0.25 * p.rho_shutdown_worth)
    assert tele["rho_rod"] == pytest.approx(tele["rho_control"] + tele["rho_shutdown"])
    assert tele["rod_command"] == pytest.approx(0.6)
    assert tele["scram"] is False
    assert tele["rod_command_effective"] == pytest.approx(0.6)


def test_telemetry_with_scram_zeroes_effective_command():
    """rod_command_effective should be 0 when scram is asserted."""
    p = default_params()
    rod = RodController(p)
    state = np.array([0.4, 1.0])
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


def test_scram_trajectory_inserts_both_banks_within_2s():
    """SCRAM from design: the control bank (0.5) and the fully withdrawn
    shutdown bank (1.0) both drop at constant speed v_scram until the last
    v_scram·tau_scram of travel, then settle exponentially. The documented
    claim is "99 % inserted (position ≤ 0.01) after (pos0 − 0.01)/v_scram",
    i.e. 1.98 s for the shutdown bank.

    Expected trajectory, from integrating d(pos)/dt = −v while pos > v·τ,
    then d(pos)/dt = −pos/τ:

        pos(t) = pos0 − v·t                        for t ≤ t1 = (pos0 − v·τ)/v
        pos(t) = v·τ · exp(−(t − t1)/τ)            for t > t1

    Sampling mid-drop (1.5 s) and at 2 s distinguishes this from the
    previous rate-capped 1 s lag, which from 1.0 would have been at
    0.5·e^(−0.5) ≈ 0.30 and 0.5·e^(−1) ≈ 0.18 at those times.
    """
    p = default_params()
    rod = RodController(p)
    sol = _integrate(
        rod,
        command_fn=lambda t: p.rod_position_design,  # operator input ignored under SCRAM
        scram_fn=lambda t: True,
        t_end=3.0,
        max_step=0.01,
    )
    assert sol.success

    v, tau = 0.5, 0.02  # the documented SCRAM speed [1/s] and bottom lag [s]
    assert (p.v_scram, p.tau_scram) == (v, tau)

    def expected(pos0: float, t: float) -> float:
        t1 = (pos0 - v * tau) / v
        return pos0 - v * t if t <= t1 else v * tau * np.exp(-(t - t1) / tau)

    for t in (0.5, 1.0, 1.5, 1.98, 2.0, 2.5):
        control, shutdown = sol.sol(t)
        assert control == pytest.approx(expected(0.5, t), abs=2e-4), t
        assert shutdown == pytest.approx(expected(1.0, t), abs=2e-4), t
    # Advertised timing: both banks at or below 1 % of travel by 1.98 s,
    # and within 0.004 of the bottom at 2.0 s.
    assert sol.sol(1.98).max() <= 0.01 + 2e-4
    assert sol.sol(2.0).max() < 0.004
    # Mid-drop the shutdown bank is still half-way: not an exponential lag.
    assert sol.sol(1.5)[1] == pytest.approx(0.25, abs=2e-4)


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
    # Small step: error = 0.005, raw rate = 0.005/tau = 5e-3 (below v_normal=0.01)
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
