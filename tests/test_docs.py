"""The engine tutorial in DEVELOPMENT.md must build and run the current plant.

The tutorial is the developer guide's main introduction to the wiring API.
It once drifted out of date (the loop gained two required inputs) and failed
in ``finalize()`` before a reader saw any simulation. Running the block
here makes that kind of drift fail the test suite instead, and comparing
its wiring with ``build_standard_plant()`` keeps it teaching the plant the
web UI and the examples run.
"""

from __future__ import annotations

import re
from pathlib import Path

from fission_sim.plant import build_standard_plant

from .topology import plant_topology

DEVELOPMENT_MD = Path(__file__).resolve().parents[1] / "DEVELOPMENT.md"
README_MD = Path(__file__).resolve().parents[1] / "README.md"

# The tutorial is the ```python block right after this marker comment.
_TUTORIAL = re.compile(
    r"<!-- engine-tutorial: tests/test_docs\.py runs this block -->\n```python\n(.*?)\n```",
    re.DOTALL,
)


def test_development_engine_tutorial_runs() -> None:
    match = _TUTORIAL.search(DEVELOPMENT_MD.read_text(encoding="utf-8"))
    assert match is not None, "engine tutorial block (with its marker comment) not found in DEVELOPMENT.md"

    namespace: dict = {}
    exec(compile(match.group(1), "DEVELOPMENT.md engine tutorial", "exec"), namespace)

    # The tutorial ran its scenario to the end, and the rod step it
    # describes reached the core before the SCRAM at t = 60 s.
    assert namespace["final"]["t"] == 120.0
    assert namespace["snap"]["core"]["power_thermal"] > namespace["CoreParams"]().P_design

    # Same modules, parameters, wires and external defaults as the factory.
    # Running the scenario does not change any of these.
    assert plant_topology(namespace["engine"]) == plant_topology(build_standard_plant())


def test_readme_component_guide_covers_every_standard_module() -> None:
    readme = README_MD.read_text(encoding="utf-8")
    guide = readme.split("## Educational Component Guide")[1].split("## Glossary")[0]
    engine = build_standard_plant()
    class_names = {type(module._component).__name__ for module in engine._modules_by_name.values()}
    missing = [class_name for class_name in class_names if f"### {class_name} (" not in guide]
    assert not missing, missing
