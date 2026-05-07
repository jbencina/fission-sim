"""Simulation engine — graph runner for ODE-based component models.

The engine has no physics imports. It only knows components, ports, and ODEs.
"""

from fission_sim.engine.engine import (
    DenseSolution,
    EngineWiringError,
    Signal,
    SimEngine,
    SimModule,
    Snapshot,
)

__all__ = [
    "DenseSolution",
    "EngineWiringError",
    "Signal",
    "SimEngine",
    "SimModule",
    "Snapshot",
]
