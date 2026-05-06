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

    __init__(params)                            # takes a frozen Params dataclass
    initial_state() -> np.ndarray
    derivatives(state, inputs) -> np.ndarray
    outputs(state, inputs=None) -> dict
    telemetry(state, inputs=None) -> dict

plus class attributes ``state_size`` and ``state_labels``. The three
state-evaluation methods all take the same `(state, inputs)` shape; components
that don't need inputs (most do not) accept the kwarg and ignore it.
Algebraic components (e.g. `SteamGenerator`) use it.

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

    outputs(state, inputs=None) -> {
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

### PrimaryLoop (`src/fission_sim/physics/primary_loop.py`)

L1 lumped primary loop: hot leg + cold leg, constant flow, constant pressure,
single-phase liquid. See `.docs/design.md` §5.2 for physics.

**Constructor**

    PrimaryLoop(params: LoopParams)

**State vector** (`state_size = 2`)

    state_labels = ("T_hot", "T_cold")
    units:        K, K

| Index | Name    | Meaning                                           |
|------:|---------|---------------------------------------------------|
| 0     | T_hot   | Coolant temperature exiting the core              |
| 1     | T_cold  | Coolant temperature returning to the core         |

**Methods**

    initial_state() -> np.ndarray
    derivatives(state, inputs) -> np.ndarray
        inputs: {"Q_core": float [W], "Q_sg": float [W]}

    outputs(state, inputs=None) -> {
        "T_hot":  float [K],
        "T_cold": float [K],
        "T_avg":  float [K],
        "T_cool": float [K],   # = T_avg at L1; what the core sees
    }

    telemetry(state, inputs=None) -> outputs() ∪ {
        "delta_T", "Q_flow", "Q_core", "Q_sg",
    }
        delta_T and Q_flow are computable from state alone.
        Q_core and Q_sg are echoed from inputs (None when inputs omitted).

**LoopParams (frozen dataclass)**

| Field         | Units    | Default                                | Source / note                          |
|---------------|----------|----------------------------------------|----------------------------------------|
| `m_dot`       | kg/s     | 1.7e4                                  | Single equivalent loop, 4-loop PWR     |
| `c_p`         | J/(kg·K) | 5500                                   | Water at ~300°C, 15.5 MPa              |
| `M_hot`       | kg       | 1.5e4                                  | Lumped hot-leg water mass              |
| `M_cold`      | kg       | 1.5e4                                  | Lumped cold-leg water mass             |
| `Q_design`    | W        | 3.0e9                                  | Match core's P_design                  |
| `T_avg_ref`   | K        | 580                                    | Match core's T_cool_ref                |
| `T_hot_ref`   | K        | derived: T_avg_ref + ΔT_design/2 ≈ 596 | ΔT = Q_design/(m_dot·c_p) ≈ 32 K       |
| `T_cold_ref`  | K        | derived: T_avg_ref − ΔT_design/2 ≈ 564 | (same)                                 |

### SteamGenerator (`src/fission_sim/physics/steam_generator.py`)

L1 algebraic heat exchanger: `Q_sg = UA · (T_primary − T_secondary)`. No state.
See `.docs/design.md` §5.3 for physics.

**Constructor**

    SteamGenerator(params: SGParams)

**State vector** (`state_size = 0`)

    state_labels = ()

**Methods**

    initial_state() -> np.ndarray         # always np.empty(0)
    derivatives(state, inputs=None) -> np.ndarray   # always np.empty(0)

    outputs(state, inputs) -> {"Q_sg": float [W]}
        inputs: {"T_primary":   float [K],
                 "T_secondary": float [K]}
        Raises TypeError if inputs is None.

    telemetry(state, inputs=None) -> {"Q_sg", "T_primary", "T_secondary", "delta_T"}
        Reports None for input-derived keys when inputs is omitted.

**SGParams (frozen dataclass)**

| Field             | Units | Default                                    | Source / note                  |
|-------------------|-------|--------------------------------------------|--------------------------------|
| `T_primary_ref`   | K     | 580                                        | Match loop's T_avg_ref         |
| `T_secondary_ref` | K     | 558                                        | Match sink's T_secondary       |
| `Q_design`        | W     | 3.0e9                                      | Match core's P_design          |
| `UA`              | W/K   | derived: Q_design / (T_p_ref − T_s_ref)    | ≈ 1.4e8; closes design steady   |

### SecondarySink (`src/fission_sim/physics/secondary_sink.py`)

L1 stand-in for the entire secondary side (turbine + condenser + feedwater).
Constant `T_secondary`; no state, no inputs. See `.docs/design.md` §5.4.

**Constructor**

    SecondarySink(params: SinkParams)

**State vector** (`state_size = 0`)

    state_labels = ()

**Methods**

    initial_state() -> np.ndarray             # always np.empty(0)
    derivatives(state, inputs=None) -> np.ndarray  # always np.empty(0)
    outputs(state, inputs=None) -> {"T_secondary": float [K]}
    telemetry(state, inputs=None) -> {"T_secondary": float [K]}

**SinkParams (frozen dataclass)**

| Field           | Units | Default | Source / note                                    |
|-----------------|-------|---------|--------------------------------------------------|
| `T_secondary`   | K     | 558     | Saturation temp at ~6.9 MPa (typical PWR steam)  |

### RodController (`src/fission_sim/physics/rod_controller.py`)

L1 rod controller: rate-limited first-order tracking of operator commands
plus linear (L1) rod-worth function. Bridges operator decisions
(rod_command, scram) to physics (rod_reactivity into the core). See
`.docs/design.md` §5.5 for physics.

**Constructor**

    RodController(params: RodParams)

**State vector** (`state_size = 1`)

    state_labels = ("rod_position",)
    units:        dimensionless (0=fully inserted, 1=fully withdrawn)

| Index | Name         | Meaning                                                 |
|------:|--------------|---------------------------------------------------------|
| 0     | rod_position | Actual rod position; lags rod_command via rate-limited tracking |

**Methods**

    initial_state() -> np.ndarray
    derivatives(state, inputs) -> np.ndarray
        inputs: {"rod_command": float [0..1, dimensionless],
                 "scram":       bool}

    outputs(state, inputs=None) -> {
        "rod_reactivity": float [dimensionless],
            # = rho_total_worth * (rod_position - rod_position_critical)
    }

    telemetry(state, inputs=None) -> outputs() ∪ {
        "rod_position", "rod_command", "scram", "rod_command_effective",
    }
        rod_position is computable from state alone.
        rod_command, scram, rod_command_effective are echoed/derived from
        inputs (None when inputs omitted).

**RodParams (frozen dataclass)**

| Field                    | Units         | Default                  | Source / note                                       |
|--------------------------|---------------|--------------------------|-----------------------------------------------------|
| `tau`                    | s             | 10.0                     | First-order lag time constant                       |
| `v_normal`               | 1/s           | 0.01                     | Normal motion speed (~1%/s typical PWR drive rate)  |
| `v_scram`                | 1/s           | 0.5                      | Scram speed (full insert in ~2 s)                   |
| `rho_total_worth`        | dimensionless | 0.14                     | Reactivity slope per unit position; scram from design (0.5→0) gives −7000 pcm |
| `rod_position_design`    | dimensionless | 0.5                      | Position at coupled-plant design steady state       |
| `rod_position_critical`  | dimensionless | derived: `= rod_position_design` | Position where rod produces zero reactivity         |

## Multi-component runners

`examples/run_primary.py` (matplotlib), `examples/report_primary.py`
(text/SSH), and `examples/dump_state.py` (full state + telemetry dump)
drive all five components (Core + Loop + SG + Sink + RodController)
coupled together. Each script defines its own ~35-line `f(t, y)` wiring;
the coupled-system test in `tests/test_primary_plant.py` does the same.
After this slice there are four copies of essentially the same wiring;
the engine slice (slice 4) will deduplicate them.

## Roadmap

Tracked in `.docs/design.md` §4. This slice covers the first piece of
Milestone 1 (Drivable Reactor Core).
