"""Secondary-side stand-in for a Pressurized Water Reactor — fidelity level L1.

A constant-temperature reservoir representing the entire secondary side: turbine,
condenser, and feedwater chain. M3 will replace this entire component with a real
turbine + condenser + feedwater chain.

Physics specification: see ``.docs/design.md`` §5.4.

References
----------
Lamarsh, J. R. and Baratta, A. J. *Introduction to Nuclear Engineering*, 3rd ed.,
Prentice Hall, 2001 (PWR overview).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SinkParams:
    """Parameters for the secondary-side stand-in.

    Parameters
    ----------
    T_secondary : float
        Constant secondary-side temperature [K]. Default 558 K corresponds to the
        saturation temperature of water at ~6.9 MPa, a typical PWR steam pressure
        (the secondary side runs much lower than the primary's 15.5 MPa).
    """

    # SIMPLIFICATION: the entire secondary side (turbine, condenser, feedwater
    # pumps, all of it) collapses to one fixed temperature. M3 will replace this
    # component with an actual chain of components.
    T_secondary: float = 558.0  # [K] saturation temp at ~6.9 MPa (typical PWR steam)


class SecondarySink:
    """Constant-temperature secondary-side stand-in (L1 fidelity).

    At L1 this component has no state and no inputs — it just publishes a fixed
    secondary-side temperature. Conceptually it represents "the steam side is at
    saturation pressure and we're not modeling its dynamics yet."

    The component still implements the full 5-method API even with empty state, so
    the engine wiring code does not need to special-case stateless components.

    Ports in: none.

    Ports out (returned by ``outputs()``):
        T_secondary : float [K]
            Configured constant; identical for all callers.

    State vector: empty (state_size = 0).

    Notes
    -----
    "Sink" in the thermodynamic sense — a reservoir that absorbs heat at a fixed
    temperature. The SG dumps heat into it; we don't model what happens to that
    heat, only that the boundary stays at saturation temperature.
    """

    state_size: int = 0
    state_labels: tuple[str, ...] = ()
    input_ports: tuple[str, ...] = ()
    output_ports: tuple[str, ...] = ("T_secondary",)

    def __init__(self, params: SinkParams) -> None:
        """Construct a sink with the given parameters.

        Parameters
        ----------
        params : SinkParams
            Frozen parameter set. Held as ``self.params`` for the lifetime of the
            object.
        """
        self.params = params

    def initial_state(self) -> np.ndarray:
        """Return an empty state vector (sink has no state).

        Returns
        -------
        np.ndarray, shape (0,)
        """
        return np.empty(0)

    def derivatives(self, state: np.ndarray, inputs: dict | None = None) -> np.ndarray:
        """Return an empty derivatives vector.

        Sink has no evolving state, so dstate/dt is the empty array.

        Parameters
        ----------
        state : np.ndarray
            Ignored (always empty for this component).
        inputs : dict, optional
            Ignored (sink takes no inputs).

        Returns
        -------
        np.ndarray, shape (0,)
        """
        return np.empty(0)

    def outputs(self, state: np.ndarray, inputs: dict | None = None) -> dict:
        """Return the configured constant secondary temperature.

        Parameters
        ----------
        state : np.ndarray
            Ignored — sink has no state.
        inputs : dict, optional
            Ignored — sink takes no inputs.

        Returns
        -------
        dict
            ``{"T_secondary": float [K]}``
        """
        return {"T_secondary": self.params.T_secondary}

    def telemetry(self, state: np.ndarray, inputs: dict | None = None) -> dict:
        """Return the diagnostic dict (same as outputs() for this component)."""
        return {"T_secondary": self.params.T_secondary}
