# fission-sim

PWR simulator. Personal learning project. Read `.docs/design.md` for goals
and architecture; this README is the **living API reference** for what
the code currently exposes.

## Quickstart

    uv sync
    uv run python examples/run_core.py
    uv run pytest

## Design conventions

Every component is a Python class that owns its parameters and equations
but **not** its time-evolving state. State lives in a numpy vector owned
by the caller (a driver script for now, the simulation engine later).
Each component exposes the same surface — a constructor and four methods:

    __init__(params)                          # takes a frozen Params dataclass
    initial_state() -> np.ndarray
    derivatives(state, inputs) -> np.ndarray
    outputs(state) -> dict
    telemetry(state, inputs=None) -> dict

plus class attributes ``state_size`` and ``state_labels``.

All time-evolving state for the whole plant lives in one flat numpy
vector. Each component declares the slot it owns.

## Component API reference

### PointKineticsCore (`src/fission_sim/physics/core.py`)

L1 point kinetics with six lumped delayed-neutron groups + Doppler +
moderator temperature feedback. See `.docs/design.md` §5.1 for physics.

**Constructor**

    PointKineticsCore(params: CoreParams)

**State vector** (`state_size = 8`)

    state_labels = ("n", "C1", "C2", "C3", "C4", "C5", "C6", "T_fuel")
    units:        dimensionless × 7,                                 K

| Index | Name   | Meaning                                                       |
|------:|--------|---------------------------------------------------------------|
| 0     | n      | Neutron population (n=1 at design power)                      |
| 1–6   | C1..C6 | Delayed neutron precursor concentrations (Keepin 6-group)     |
| 7     | T_fuel | Average fuel temperature [K]                                  |

**Methods**

    initial_state() -> np.ndarray
        Design-point steady state. n=1, C_i = beta_i / (Lambda * lambda_i),
        T_fuel = T_fuel_ref.

    derivatives(state, inputs) -> np.ndarray
        Pure function. inputs:
            "rod_reactivity": float [dimensionless]
            "T_cool":         float [K]

    outputs(state) -> {
        "power_thermal": float [W],
        "T_fuel":        float [K],
    }

    telemetry(state, inputs=None) -> {
        "power_thermal", "T_fuel", "n",
        "C1", "C2", "C3", "C4", "C5", "C6",
        "rho_total", "rho_rod", "rho_doppler", "rho_moderator",
    }
        rho_doppler is computable from state alone. rho_rod, rho_moderator,
        and rho_total are None when inputs is omitted.

**CoreParams (frozen dataclass)**

| Field         | Units      | Default                                | Source / note                    |
|---------------|------------|----------------------------------------|----------------------------------|
| `beta_i`      | —          | 6 values, Σ ≈ 0.0065                   | Lamarsh Tab 7.3 / Keepin 1965    |
| `lambda_i`    | 1/s        | 6 values, 0.0124 .. 3.01               | Lamarsh Tab 7.3 / Keepin 1965    |
| `Lambda`      | s          | 2.0e-5                                 | Typical thermal reactor          |
| `P_design`    | W          | 3.0e9                                  | ~3000 MWth large PWR             |
| `alpha_f`     | 1/K        | −2.5e-5                                | Doppler, negative                |
| `alpha_m`     | 1/K        | −5.0e-5                                | Moderator, negative              |
| `T_fuel_ref`  | K          | 900                                    | Doppler-zero reference           |
| `T_cool_ref`  | K          | 580                                    | Moderator-zero reference         |
| `M_fuel`      | kg         | 1.0e5                                  | Lumped fuel mass                 |
| `c_p_fuel`    | J/(kg·K)   | 300                                    | UO₂                              |
| `hA_fc`       | W/K        | derived: P_design / (T_f_ref - T_c_ref)| Steady-state energy balance      |

## Roadmap

Tracked in `.docs/design.md` §4. This slice covers the first piece of
Milestone 1 (Drivable Reactor Core).
