"""Smoke checks for the runnable scripts in ``examples/``.

The examples are part of the learning path, and they have broken before
when component ports changed. These checks keep them runnable without
re-testing the physics: the hand-wired tutorial plant must match the shared
factory, the state dump must run and cover every module, and the standalone
core drivers must start in equilibrium.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

from fission_sim.physics.core import CoreParams, PointKineticsCore
from fission_sim.plant import build_standard_plant

from .topology import plant_topology

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


def _load_example(name: str) -> ModuleType:
    """Import ``examples/<name>.py`` as a module without running ``main()``."""
    spec = importlib.util.spec_from_file_location(f"example_{name}", EXAMPLES_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
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
    for module_name in ("rod", "core", "loop", "sg", "sink", "pzr", "pzr_ctrl"):
        assert f"    {module_name}:\n" in out


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
