# Development

This file collects the developer workflow, Web API details, architecture notes,
and code-level conventions for `fission-sim`. For the project overview,
quickstart, and educational model guide, see [README.md](README.md).

## Prerequisites

- Python 3.11+
- Node.js 20+ (or 22+)
- `uv` installed (see [astral.sh/uv](https://astral.sh/uv))

## Setup

Install both Python and frontend dependencies:

    make install

This runs `uv sync && npm install --prefix web`. Run it once after cloning or
whenever `pyproject.toml` or `web/package.json` changes.

For Python-only work:

    uv sync

## Run The Dashboard

Start the FastAPI backend and Vite frontend together:

    make dev

This starts the backend on port 8000 and the Vite dev server on port 5173 with
colour-prefixed output. Press **Ctrl-C** to stop both processes.

Open [http://localhost:5173](http://localhost:5173) in a browser once both
processes are ready. During development, Vite proxies `/api` and `/ws` to the
backend.

Both servers bind `0.0.0.0`, so the dashboard is reachable from any host on
your network at `http://<your-machine-ip>:5173`. There is no authentication;
only expose this on a trusted network.

The `make dev` launcher is Unix-only. On Windows, run the two processes in
separate terminals:

    uv run python -m fission_sim.api   # backend, port 8000
    npm run dev --prefix web           # frontend, port 5173

## Run From The CLI

| Command | What it shows |
|---|---|
| `uv run python examples/console.py` | Interactive terminal dashboard with live commands |
| `uv run python examples/console.py --speed 60` | Same console, 60 simulated seconds per wall second |
| `uv run python examples/report_primary.py` | Text-only primary-plant report, good over SSH |
| `uv run python examples/power_maneuver.py` | Text report for a controlled rod-driven power maneuver |
| `uv run python examples/run_primary.py` | Matplotlib plots for the coupled primary plant |
| `uv run python examples/run_core.py` | Matplotlib plots for point kinetics only |

## Useful Make Targets

| Target | What it does |
|---|---|
| `make install` | Install Python + Node dependencies |
| `make dev` | Start backend + frontend together |
| `make api` | Backend only (`uvicorn` on port 8000) |
| `make web` | Frontend only (Vite dev server on port 5173) |
| `make install-e2e` | Install Chromium for the Playwright smoke test |
| `make e2e` | Run Playwright smoke test against an already-running stack |
| `make test` | Full test suite: `uv run pytest` + `npm run test -- --run` |
| `make lint` | Python (`ruff check`) + TypeScript (`eslint`) linting |

## Tests

Run the Python test suite directly:

    uv run pytest

Run the full repository test suite:

    make test

Run linting:

    make lint

## End-To-End Smoke Test

The Playwright smoke test verifies that the browser can connect, reset to a
known running state, SCRAM, and observe a large power drop.

Install the browser once:

    make install-e2e

Start the stack in one terminal:

    make dev

Run the smoke test in another:

    make e2e

## Web API Reference

The backend exposes one HTTP endpoint and one WebSocket endpoint. The Vite dev
server proxies `/api` and `/ws` paths to the backend, so the browser always
talks to port 5173 during development.

### `GET /api/health`

Liveness probe. Returns HTTP 200 with body:

```json
{"status": "ok"}
```

No simulation state is checked; this is a shallow ping.

### `WebSocket /ws/telemetry`

Bidirectional. Connect once; the server pushes telemetry frames at 10 Hz. The
client may send command messages at any time.

#### Telemetry Frame

The server pushes one JSON object per step. All numeric fields use SI units
internally; `P_primary_MPa` is a convenience conversion provided for display.

```json
{
  "t": 42.7,
  "power_thermal": 3000000000.0,
  "T_hot": 597.7,
  "T_cold": 568.3,
  "T_avg": 583.0,
  "T_fuel": 1100.0,
  "rod_position": 0.5,
  "P_primary_Pa": 15500000.0,
  "P_primary_MPa": 15.5,
  "Q_sg": 3000000000.0,
  "rho_rod": 0.0,
  "rho_doppler": 0.0,
  "rho_moderator": 0.0,
  "rho_total": 0.0,
  "running": true,
  "speed": 1.0,
  "scrammed": false,
  "rod_command": 0.5
}
```

| Key | Type | Units | Description |
|---|---|---|---|
| `t` | float | s | Simulation time |
| `power_thermal` | float | W | Fission thermal power |
| `T_hot` | float | K | Hot-leg coolant temperature |
| `T_cold` | float | K | Cold-leg coolant temperature |
| `T_avg` | float | K | Average primary coolant temperature |
| `T_fuel` | float | K | Lumped fuel temperature |
| `rod_position` | float | dimensionless | Actual rod position (0 = inserted, 1 = withdrawn) |
| `P_primary_Pa` | float | Pa | Primary system pressure from pressurizer |
| `P_primary_MPa` | float | MPa | Same pressure, converted for display |
| `Q_sg` | float | W | Heat removed by the steam generator |
| `rho_rod` | float | dimensionless | Rod reactivity contribution |
| `rho_doppler` | float | dimensionless | Doppler fuel-temperature reactivity feedback |
| `rho_moderator` | float | dimensionless | Moderator coolant-temperature reactivity feedback |
| `rho_total` | float | dimensionless | Total reactivity |
| `running` | bool | dimensionless | Whether the simulator is currently stepping |
| `speed` | float | dimensionless | Simulation speed multiplier (1.0 = real time) |
| `scrammed` | bool | dimensionless | Whether a SCRAM is active |
| `rod_command` | float | dimensionless | Operator's requested rod position |

#### Command Messages

Commands are JSON objects with a `"type"` discriminator. The server returns an
acknowledgement frame such as `{"type": "ack", "command": "set_speed"}` on
success, or an error frame `{"type": "error", "detail": "..."}` on failure.
Errors do not disconnect the WebSocket.

**`set_rod_command`** - move the control rod bank toward a target position.

```json
{"type": "set_rod_command", "value": 0.55}
```

`value`: float in `[0, 1]`. 0 = fully inserted (shutdown), 1 = fully withdrawn
(maximum reactivity). The rod controller drives toward this position at a
finite speed, about 1%/s for normal motion.

**`scram`** - emergency shutdown; forces rods to full insertion at scram speed.

```json
{"type": "scram"}
```

No extra fields. Sets `scrammed = true` in the runtime. The reactor does not go
subcritical instantly; delayed-neutron precursors sustain a tail of fission
heat for tens of seconds.

**`reset_scram`** - clear the SCRAM latch and restore operator rod control.

```json
{"type": "reset_scram"}
```

No extra fields. In the simulator this is unconditional; a real plant requires
independent safety system confirmation.

**`pause`** - suspend engine stepping. The background loop keeps running.

```json
{"type": "pause"}
```

No extra fields. The runtime publishes one transition frame with
`running = false`; while paused, no additional telemetry frames are emitted.
Resume with `resume`.

**`resume`** - resume engine stepping after a `pause`.

```json
{"type": "resume"}
```

No extra fields.

**`reset`** - rebuild the engine from t = 0.

```json
{"type": "reset"}
```

No extra fields. All state returns to initial conditions. `P_setpoint` and
`speed` are preserved; the SCRAM latch is cleared and `rod_command` resets to
0.5.

**`set_speed`** - change the simulation speed multiplier.

```json
{"type": "set_speed", "value": 5}
```

`value`: one of `{1, 2, 5, 10}`. Values outside this set are rejected with an
error frame.

**`set_pressure_setpoint`** - adjust the pressurizer pressure setpoint.

```json
{"type": "set_pressure_setpoint", "value": 15500000.0}
```

`value`: float in `[10e6, 20e6]` Pa (10-20 MPa). Nominal design is 15.5 MPa =
1.55e7 Pa. The pressurizer controller will heat or spray to reach this
setpoint.

## Architecture

The simulator follows a strict four-layer stack with one-way downward
dependencies. The web layer is a top-level package (`fission_sim.api`) that
sits above the engine, physics, and control layers:

```text
Browser (React / TypeScript)
  HTTP + WebSocket via Vite dev server
    -> fission_sim.api
       FastAPI + uvicorn + SimRuntime
         -> fission_sim.engine
            SimEngine owns state, wiring, and BDF stepping
              -> fission_sim.physics
              -> fission_sim.control
```

Layer rules:

- Physics never imports from control or API. The engine has zero domain
  knowledge; it only knows components, ports, and ODEs.
- `fission_sim.api` is the only package that knows about asyncio, HTTP, or
  WebSocket. `runtime.py` is HTTP-agnostic; `app.py` is physics-agnostic.
- The Vite frontend is a separate process. During development, the Vite proxy
  (`/api`, `/ws` to `127.0.0.1:8000`) removes the need for browser CORS
  preflights.

See `.docs/design.md` sections 2-3 for the original four-layer design spec.

## Frontend Tech Stack

The browser dashboard is a single-page app in `web/`:

| Technology | Version | Role |
|---|---|---|
| Vite | 5.x | Build tool and dev server with backend proxy |
| React | 18.x | UI component tree |
| TypeScript | 5.x strict | Type-safe frontend language |
| Tailwind CSS | 3.x | Utility-first styling |
| Recharts | 2.x | Time-series charts |
| Zustand | 5.x | Lightweight global state store for telemetry |
| ESLint + Prettier | 8.x / 3.x | Lint and format |
| Vitest | 4.x | Unit tests for store logic and utilities |

During development, Vite forwards `/api/*` and `/ws/*` to
`http://127.0.0.1:8000` and `ws://127.0.0.1:8000`, respectively. Deferred work
such as authentication, persistence, multi-user support, and replay is tracked
in `.docs/design.md`.

## Design Conventions

Every component is a Python class that owns its parameters and equations but
not its time-evolving state. State lives in a numpy vector owned by the caller.
Each component exposes the same surface:

    __init__(params)                            # takes a frozen Params dataclass
    initial_state() -> np.ndarray
    derivatives(state, inputs) -> np.ndarray
    outputs(state, inputs=None) -> dict
    telemetry(state, inputs=None) -> dict

Components also expose class attributes `state_size` and `state_labels`. The
three state-evaluation methods all take the same `(state, inputs)` shape.
Components that do not need inputs accept the kwarg and ignore it. Algebraic
components, such as `SteamGenerator`, use it.

All time-evolving state for the whole plant lives in one flat numpy vector.
Each component declares the slot it owns.

## Simulation Engine

`SimEngine` (in `src/fission_sim/engine/engine.py`) is the graph runner that
owns global state, wires components, and steps time. It has zero physics
imports; all it knows is components, ports, and ODEs.

### API

```python
from fission_sim.engine import SimEngine

engine = SimEngine()

# 1. Register components; name defaults to snake_case of class name.
rod = engine.module(RodController(RodParams()), name="rod")
core = engine.module(PointKineticsCore(CoreParams()), name="core")
loop = engine.module(PrimaryLoop(LoopParams()), name="loop")
sg = engine.module(SteamGenerator(SGParams()), name="sg")
sink = engine.module(SecondarySink(SinkParams()), name="sink")

# 2. Declare external operator inputs.
rod_cmd = engine.input("rod_command", default=0.5)
scram = engine.input("scram", default=False)

# 3. Wire by calling; the engine traces these calls to build the DAG.
rho_rod = rod(rod_command=rod_cmd, scram=scram)
T_sec = sink()
Q_sg = sg(T_avg=loop.T_avg, T_secondary=T_sec)
core(rho_rod=rho_rod, T_cool=loop.T_cool)
loop(power_thermal=core.power_thermal, Q_sg=Q_sg)

# 4. Finalize validates the graph and allocates state.
engine.finalize()  # optional; auto-called on first step()/run()

# 5a. Step-at-a-time for live or interactive use.
snap = engine.step(dt=0.5, rod_command=0.515)
print(snap["core"]["n"], snap["signals"]["power_thermal"])

# 5b. Or run a whole scenario.
def scenario(t):
    return {"rod_command": 0.5 if t < 10 else 0.515, "scram": t >= 60.0}

final = engine.run(t_end=300.0, scenario_fn=scenario)
```

### Snapshot Dict Shape

Returned by `step()`, `run()`, and `engine.snapshot()`:

```python
{
    "t": 5.0,
    "signals": {
        "rho_rod": 0.0,
        "T_cool": 583.0,
        "power_thermal": 3.0e9,
        "Q_sg": 3.0e9,
        "T_avg": 583.0,
        "T_secondary": 558.0,
        "rod_command": 0.5,
        "scram": False,
    },
    "core": {"n": 1.0, "T_fuel": 1100.0},
    "loop": {"T_hot": 597.7, "T_cold": 568.3},
    "rod": {"rod_position": 0.5, "rho_rod": 0.0},
    "sg": {},
    "sink": {},
}
```

`signals` contains every wired signal by canonical name: externals plus module
outputs that have at least one consumer. Each `<module_name>` key holds that
module's `telemetry()` dict.

### Wiring Rules

- Globally unique signal names. Two modules cannot expose an output port with
  the same name.
- State-derived outputs, such as `loop.T_avg`, are accessible as attributes
  before the module is called. Computed outputs, such as `Q_sg = sg(...)`, come
  from the call return.
- Single-output calls return the `Signal`; multi-output calls return `None`.
  Use attribute access for multi-output components.
- Externals not provided in `step()` or `scenario_fn(t)` fall back to the
  declared default.

### `finalize()`

`EngineWiringError` is raised for dangling inputs, signal name collisions,
unused externals, unknown ports in `module(...)` calls, and cycles among
computed-output modules.

### `run(dense=True)`

```python
final, dense = engine.run(t_end=300.0, scenario_fn=scenario, dense=True)
mid = dense.at(150.0)
n_traj = dense.signal("power_thermal", np.linspace(0, 300, 1500)) / core_params.P_design
```

`dense.at(t)` returns a snapshot at the given time or times. `dense.signal(name,
t_array)` returns a 1D array of values, falling back to module telemetry if the
name is not a wired signal.

## Multi-Component Runners

All runners (`run_primary.py`, `report_primary.py`, `dump_state.py`) and the
coupled-plant tests (`test_primary_plant.py`) use `SimEngine` for wiring. They
differ only in their `scenario_fn` and how they format the output: matplotlib,
ASCII text, or full state dump.
