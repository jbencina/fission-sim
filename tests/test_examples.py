"""Smoke checks for the runnable scripts in ``examples/``.

The examples are part of the learning path, and they have broken before
when component ports changed. These checks keep them runnable without
re-testing the physics: the hand-wired tutorial plant must match the shared
factory, the state dump must run and cover every module, and the standalone
core drivers must start in equilibrium.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from fission_sim.physics.core import CoreParams, PointKineticsCore
from fission_sim.plant import build_standard_plant

from .topology import plant_topology

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"


def _load_example(name: str) -> ModuleType:
    """Import ``examples/<name>.py`` as a module without running ``main()``."""
    spec = importlib.util.spec_from_file_location(f"example_{name}", EXAMPLES_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_script(name: str) -> ModuleType:
    """Import ``scripts/<name>.py`` as a module without running ``main()``."""
    spec = importlib.util.spec_from_file_location(f"script_{name}", SCRIPTS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


# Globbed so a newly added example is covered automatically; the build
# paths themselves are exercised by the tests below and by the factory users.
@pytest.mark.parametrize(
    "name",
    sorted(p.stem for p in EXAMPLES_DIR.glob("*.py")),
)
def test_example_imports(name):
    """Every example imports cleanly (catches imports broken by refactors)."""
    _load_example(name)


def test_run_primary_wiring_matches_standard_plant():
    """``run_primary.py`` spells out the plant the factory builds.

    The two must stay identical, or the tutorial teaches a plant the web UI
    and the other examples do not run.
    """
    run_primary = _load_example("run_primary")
    tutorial = run_primary.build_plant(CoreParams())
    factory = build_standard_plant()

    assert plant_topology(tutorial) == plant_topology(factory)


def test_dump_state_runs_and_dumps_every_module(capsys):
    """The state dump runs its full scenario and prints every module,
    including the pressurizer and its controller."""
    _load_example("dump_state").main()

    out = capsys.readouterr().out
    for module_name in (
        "rod",
        "core",
        "loop",
        "sg",
        "sg_sec",
        "turbine",
        "feedwater",
        "fw_ctrl",
        "tavg_ctrl",
        "pzr",
        "pzr_ctrl",
    ):
        assert f"    {module_name}:\n" in out


def test_validate_secondary_script_imports():
    """The M3 validation CLI imports without running scenarios."""
    module = _load_script("validate_secondary")
    assert module.parse_args is not None


def test_console_status_reports_p4_turbine_trip():
    """Console status distinguishes SCRAM's effective P-4 turbine trip."""
    console = _load_example("console")
    engine = build_standard_plant(rod_auto=True)
    snap = engine.step(1.0, scram=True, rod_auto=True)
    state = {
        "sim_t": engine.t,
        "rod_command": 0.5,
        "scram": True,
        "msg": "",
        "last_snap": snap,
        "heater_manual": None,
        "spray_manual": None,
        "P_setpoint": 15.5e6,
        "turbine_load": 1.0,
        "turbine_trip": False,
        "rod_auto": True,
        "level_setpoint": 0.5,
        "feedwater_manual": None,
    }

    text = "\n".join(console.status_lines(state))

    assert "rod control = AUTO SUSPENDED" in text
    assert "retained manual cmd = 0.5000" in text
    assert "turbine trip = ON (SCRAM via P-4)" in text
    assert "turbine admission demand/actual" in text
    assert "feedwater AUTO" in text


def test_console_trip_releases_require_explicit_readmission():
    """SCRAM release and turbine untrip leave admission demand at zero."""
    console = _load_example("console")

    state = {"scram": True, "turbine_trip": True, "turbine_load": 0.9, "msg": ""}
    assert console.process_command(state, "r")
    assert state["scram"] is False
    assert state["turbine_load"] == 0.0
    assert "idealized signal release" in state["msg"]
    assert "not a plant restart" in state["msg"]

    state = {"scram": False, "turbine_trip": True, "turbine_load": 0.9, "msg": ""}
    assert console.process_command(state, "untrip")
    assert state["turbine_trip"] is False
    assert state["turbine_load"] == 0.0
    assert "idealized signal release" in state["msg"]
    assert "not a plant restart" in state["msg"]


def _console_m4_state() -> dict:
    """Return the minimal console state needed for M4 command/status tests."""
    snap = build_standard_plant().snapshot()
    return {
        "sim_t": 0.0,
        "rod_command": 0.5,
        "scram": False,
        "msg": "",
        "last_snap": snap,
        "heater_manual": None,
        "spray_manual": None,
        "P_setpoint": 15.5e6,
        "turbine_load": 1.0,
        "turbine_trip": False,
        "rod_auto": False,
        "level_setpoint": 0.5,
        "feedwater_manual": None,
    }


def test_console_level_and_feedwater_commands():
    """Console exposes M4 SG level setpoint and feedwater manual override."""
    console = _load_example("console")
    state = _console_m4_state()

    assert console.process_command(state, "level 0.55")
    assert state["level_setpoint"] == pytest.approx(0.55)
    assert "collapsed liquid-fraction setpoint" in state["msg"]

    assert console.process_command(state, "feedwater 0.25")
    assert state["feedwater_manual"] == pytest.approx(0.25)
    assert "Manual feedwater demand" in state["msg"]
    assert "fraction of maximum feedwater flow (max = 120 % design)" in state["msg"]
    assert "500.7 kg/s" in state["msg"]
    assert "30.0 % design" in state["msg"]

    assert console.process_command(state, "feedwater auto")
    assert state["feedwater_manual"] is None
    assert "Feedwater AUTO selected" in state["msg"]


def test_console_rejects_bare_feedwater_command():
    """A bare ``feedwater`` command reports help instead of silently selecting AUTO."""
    console = _load_example("console")
    state = _console_m4_state()
    state["feedwater_manual"] = 0.25

    assert console.process_command(state, "feedwater")

    assert state["feedwater_manual"] == pytest.approx(0.25)
    assert "requires 'feedwater auto' or a fraction" in state["msg"]


def test_console_rejects_level_targets_outside_ordinary_band():
    """Ordinary SG level commands stay inside the 0.35-0.90 operating band."""
    console = _load_example("console")
    state = _console_m4_state()

    assert console.process_command(state, "level 0.2")

    assert state["level_setpoint"] == pytest.approx(0.5)
    assert "0.35" in state["msg"]
    assert "0.90" in state["msg"]
    assert "validity limits are 0.30 and 0.95" in state["msg"]


def test_console_status_reports_feedwater_controller_saturation():
    """Console status shows AUTO saturation as a control-authority limit."""
    console = _load_example("console")
    state = _console_m4_state()
    state["last_snap"]["fw_ctrl"]["saturated"] = True

    text = "\n".join(console.status_lines(state))

    assert "feedwater AUTO (saturated)" in text


@pytest.mark.parametrize("name", ["run_core", "report_core"])
def test_standalone_core_examples_start_in_equilibrium(name):
    """The core drivers advertise t = 0..10 s as steady state, so their
    fixed inputs must leave every derivative of the design state at zero."""
    example = _load_example(name)
    params = CoreParams()
    core = PointKineticsCore(params)

    inputs = {"rho_rod": example.rod_reactivity_fn(0.0), "T_cool": example.T_cool_fn(0.0, params)}
    derivatives = core.derivatives(core.initial_state(), inputs)

    np.testing.assert_allclose(derivatives, 0.0, atol=1e-9)
