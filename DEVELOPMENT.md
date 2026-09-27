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

The example scripts, with what each one demonstrates, are listed in one
place: [README.md → Run From The CLI](README.md#run-from-the-cli). All of them
run with `uv run python examples/<name>.py`.

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

`tests/test_docs.py` extracts the engine tutorial below from this file and
runs it, so a change to the plant wiring that breaks the tutorial fails the
test suite.

## End-To-End Smoke Test

The Playwright smoke test runs two checks in a real browser: the educational
help for a control and for a status readout can be opened with the keyboard
alone, and a SCRAM (after a reset to a known running state) produces a large
power drop.

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

Bidirectional. Connect once; the client may send command messages at any
time. On connect the server immediately sends the current state, also while
the simulation is paused or halted at a model limit. While the simulation
runs, the server pushes one telemetry frame per engine step: 10 steps per
wall-clock second, each advancing simulated time by 0.1 s × `speed`.

#### Telemetry Frame

Each frame is one JSON object. All numeric fields use SI units internally;
`P_primary_MPa` is a convenience conversion provided for display. The example
is a real frame from the design steady state:

```json
{
  "t": 42.7,
  "power_thermal": 3000000000.0,
  "T_hot": 597.742,
  "T_cold": 568.258,
  "T_avg": 583.0,
  "T_fuel": 1100.0,
  "rod_position": 0.5,
  "P_primary_Pa": 15499345.2,
  "P_primary_MPa": 15.4993,
  "Q_sg": 3000000000.0,
  "rho_rod": 0.0,
  "rho_doppler": 0.0,
  "rho_moderator": 0.0,
  "rho_total": 0.0,
  "running": true,
  "speed": 1.0,
  "scrammed": false,
  "rod_command": 0.5,
  "model_limit": null
}
```

The design pressure reads about 0.65 kPa below 15.5 MPa because the initial
pressurizer inventory is derived with one CoolProp backend (IAPWS-IF97) and
converted back to a pressure with another (Helmholtz EOS); see
[README.md → Pressurizer](README.md#pressurizer-srcfission_simphysicspressurizerpy).

| Key | Type | Units | Description |
|---|---|---|---|
| `t` | float | s | Simulation time |
| `power_thermal` | float | W | Modeled fission power, `n · P_design`. Fission-product decay heat is not modeled. |
| `T_hot` | float | K | Hot-leg coolant temperature |
| `T_cold` | float | K | Cold-leg coolant temperature |
| `T_avg` | float | K | Average primary coolant temperature, `(T_hot + T_cold) / 2` |
| `T_fuel` | float | K | Lumped (average) fuel temperature, not the centerline |
| `rod_position` | float | dimensionless | Actual control-bank position (0 = inserted, 1 = withdrawn). The shutdown bank is not in the frame. |
| `P_primary_Pa` | float | Pa | Primary system pressure from pressurizer |
| `P_primary_MPa` | float | MPa | Same pressure, converted for display |
| `Q_sg` | float | W | Heat removed by the steam generator |
| `rho_rod` | float | dimensionless | Rod reactivity, control bank + shutdown bank |
| `rho_doppler` | float | dimensionless | Doppler fuel-temperature reactivity feedback |
| `rho_moderator` | float | dimensionless | Moderator coolant-temperature reactivity feedback |
| `rho_total` | float | dimensionless | Total reactivity |
| `running` | bool | dimensionless | Whether simulated time is advancing (false while paused or halted at a model limit) |
| `speed` | float | dimensionless | Simulation speed multiplier (1.0 = real time) |
| `scrammed` | bool | dimensionless | Whether the SCRAM latch is set |
| `rod_command` | float | dimensionless | Operator's requested control-bank position (fraction withdrawn) |
| `model_limit` | string or null | — | Why the simulation halted at the edge of the model, or `null`. A halt caused by an unexpected step failure instead starts with `Simulation error: `. |

#### Command Messages

Commands are JSON objects with a `"type"` discriminator. The server returns an
acknowledgement frame such as `{"type": "ack", "command": "set_speed"}` on
success, or an error frame `{"type": "error", "detail": "..."}` on failure.
Text that is not valid JSON, and binary WebSocket frames, are also answered
with an error frame. Errors do not disconnect the WebSocket.

While the simulation is paused or halted, a command that changes what the
frame reports (rod command, SCRAM latch, speed, pause state) is published as
one new frame with `t` unchanged, so every client sees it. A command that
changes nothing visible publishes nothing.

**`set_rod_command`** - move the control bank toward a target position.

```json
{"type": "set_rod_command", "value": 0.55}
```

`value`: float in `[0, 1]`, the fraction withdrawn. 0 = fully inserted,
1 = fully withdrawn; the design full-power position is 0.5. The rod
controller drives the control bank toward this position at 1 %/s (100 s for
the full stroke, 50 s from the design position to either end). Each 1 % of
travel is worth 12 pcm, so the whole range is ±600 pcm about the design
position. While a SCRAM is latched the command is stored but has no effect.

**`scram`** - emergency shutdown; drops the control bank and the shutdown
bank into the core.

```json
{"type": "scram"}
```

No extra fields. Sets `scrammed = true`. SCRAM immediately commands both banks
to full insertion; they then fall at a finite speed (0.5 of full travel per
second), so a bank starting fully withdrawn is 99 % inserted after 1.98 s,
and the control bank from its design position after 0.98 s. Together the two
banks insert −7,000 pcm relative to the design state. The core is subcritical
from the moment the rods start to fall, but power does not vanish: delayed-neutron
precursors keep decaying and emitting neutrons, which sustain a shrinking
level of fission for tens of seconds to minutes. Fission-product decay heat
is not modeled.

**`reset_scram`** - clear the SCRAM latch and return the control bank to the
operator.

```json
{"type": "reset_scram"}
```

No extra fields. Only the control bank comes back: it moves toward
`rod_command` at normal drive speed. The shutdown bank stays fully inserted,
so the reactor stays subcritical whatever the rod command: total reactivity
stays below about −4,300 pcm even with the control bank fully withdrawn
(+600 pcm) and the plant cooled to the secondary temperature (feedback up to
about +1,480 pcm), against the shutdown bank's −6,400 pcm. Returning to power
takes a `reset`; the procedure-driven reactor startup that would withdraw the
shutdown banks in a real plant is not modeled. In the simulator clearing the
latch is unconditional (no interlock logic is modeled).

**`pause`** - stop advancing simulated time. The background loop keeps
running.

```json
{"type": "pause"}
```

No extra fields. The runtime publishes one frame with `running = false`.
While paused, a frame is published only when an accepted command changes the
command state (rod command, SCRAM, speed), with `t` unchanged, or when a
`reset` publishes its t = 0 frame; otherwise no frames are emitted. Resume
with `resume`.

**`resume`** - resume stepping after a `pause`.

```json
{"type": "resume"}
```

No extra fields. Refused with an error frame while a model limit is active
(`model_limit` is not `null`); only `reset` clears a model-limit halt.

**`reset`** - rebuild the plant at t = 0.

```json
{"type": "reset"}
```

No extra fields. The physical state (neutron population, temperatures,
pressurizer inventory, both rod banks) returns to the full-power design
state, `rod_command` returns to 0.5, and the SCRAM latch is cleared. A
model-limit halt is cleared and the simulation runs again. `P_setpoint` and
`speed` are kept, and so is a pause the operator chose. One frame at t = 0 is
published. Calling `SimRuntime.reset()` directly does exactly the same.

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
setpoint. The setpoint is not a frame field, so this command publishes no
frame while paused. A very low setpoint makes the controller spray
continuously; the pressurizer can then fill with water, which ends the
simulation at a model limit.

#### Model-Limit Halt

After every step the runtime checks the new state against the model's
supported domain (`fission_sim.physics.domain.check_snapshot`; the limits are
explained in [README.md → Model Limits](README.md#model-limits)). If a step
leaves the domain, or fails outright, the runtime:

1. puts the engine back at the state before that step (the last valid one),
2. sets `running = false` and fills `model_limit` with a plain-language
   explanation of which assumption failed,
3. publishes one frame of the last valid state carrying that explanation.

`resume` is then refused until `reset`. Only accepted steps are checked: the
BDF solver may try states outside the domain while it searches for a step,
and those are not errors.

## Architecture

The simulator follows a strict layered stack with one-way downward
dependencies. The web layer is a top-level package (`fission_sim.api`) that
sits above the engine, physics, and control layers:

```text
Browser (React / TypeScript)
  HTTP + WebSocket via Vite dev server
    -> fission_sim.api
       FastAPI + uvicorn + SimRuntime
         -> fission_sim.plant
            build_standard_plant(): the standard wiring
              -> fission_sim.engine
                 SimEngine owns state, wiring, and BDF stepping
              -> fission_sim.physics
              -> fission_sim.control
```

Layer rules:

- Physics never imports from control or API. The engine has zero domain
  knowledge; it only knows components, ports, and ODEs.
- `fission_sim.plant` is the one place that knows which components make up
  the standard plant and how they connect. It sits outside the API layer so
  the command-line examples can use it without importing FastAPI.
- `fission_sim.api` is the only package that knows about asyncio, HTTP, or
  WebSocket. `runtime.py` is HTTP-agnostic; `app.py` is physics-agnostic.
- The Vite frontend is a separate process. During development, the Vite proxy
  (`/api`, `/ws` to `127.0.0.1:8000`) removes the need for browser CORS
  preflights.

## Frontend Tech Stack

The browser dashboard is a single-page app in `web/`:

| Technology | Version | Role |
|---|---|---|
| Vite | 5.x | Build tool and dev server with backend proxy |
| React | 18.x | UI component tree |
| TypeScript | 5.x strict | Type-safe frontend language |
| Tailwind CSS | 3.x | Utility-first styling, mapped onto the console's CSS variables |
| uPlot | 1.6.x | Canvas time-series charts |
| Zustand | 5.x | Lightweight global state store for telemetry |
| ESLint + Prettier | 8.x / 3.x | Lint and format |
| Vitest | 4.x | Unit tests for store logic and utilities |

During development, Vite forwards `/api/*` and `/ws/*` to
`http://127.0.0.1:8000` and `ws://127.0.0.1:8000`, respectively.
Authentication, persistence, multi-user support, and replay are not
implemented.

A frame's path through the frontend: `wsClient.ts` receives it, the Zustand
store in `telemetryStore.ts` keeps it as `latest` and appends it to a history
of up to 600 frames, `chartData.ts` turns the history into chart columns
using the series listed in `chartSpecs.ts`, and the charts and status
readouts render it.

- Charts show a fixed window of the most recent 60 s of simulated time, at
  every speed, with every frame in the window drawn.
- The charts redraw on every display refresh, not only when a frame
  arrives. One `requestAnimationFrame` loop (`ticker.ts`) drives all six;
  their right edge follows `displayClock.ts`, which advances continuously
  one frame period behind the newest frame, so traces scroll smoothly
  instead of stepping ten times a second. Each y axis is sticky and eases
  between ranges (`autoRange.ts`). Data, scales and legend values go to
  uPlot and the DOM directly, so React does not re-render per frame.
- Colours are CSS variables in `index.css`: one palette, a black ground with
  white ink and hairlines, amber for caution and red for alarm. There is no
  light theme. Text is IBM Plex Sans and every number IBM Plex Mono,
  self-hosted from `@fontsource`.
- `widgets/PlantMimic.tsx` draws the loop schematic from the latest frame;
  `widgets/loopState.ts` words its title. `state/events.ts` derives plant
  events from consecutive frames and the store keeps the newest 100 for
  `widgets/EventLog.tsx`.
- Backend error frames and connection errors go through the store's
  `reportError` and appear as a dismissible notice (`clearError` hides it).
  A `model_limit` in the latest frame appears as a separate, persistent
  notice that stays until a reset clears it.
- Each status readout's explanation (and each chart's, and each toolbar
  badge's) opens on hover, on keyboard focus of its info button, or on a
  tap of that button. Control help opens on hover and
  on keyboard focus of the control.

## Component Contract

Every component is a Python class that owns its parameters and equations but
not its time-evolving state. All time-evolving state for the whole plant lives
in one flat numpy vector owned by `SimEngine`; each component declares how
many entries it needs, and the engine hands it that slice.

Class attributes:

| Attribute | Meaning |
|---|---|
| `state_size` | Number of state entries the component owns (0 for an algebraic component such as `SteamGenerator`) |
| `state_labels` | Names of those entries in order, e.g. `("rod_position", "shutdown_position")` |
| `input_ports` | Names of the values the component reads; every one must be wired before `finalize()` |
| `output_ports` | Names of the values it offers to other components; these become signal names, so they must be unique among the modules whose outputs are wired |
| `outputs_require_inputs` | Optional `True` / `False`: how the engine evaluates `outputs()` (see below) |

Methods:

    __init__(params)                          # takes a frozen Params dataclass
    initial_state() -> np.ndarray             # shape (state_size,)
    derivatives(state, inputs) -> np.ndarray  # d(state)/dt, shape (state_size,)
    outputs(state, inputs=...) -> dict        # one entry per output port
    telemetry(state, inputs=None) -> dict     # superset of outputs, for display

`derivatives()` and `outputs()` must be pure functions of their arguments:
the BDF solver calls them many times per step with trial states that it later
discards, so they must not keep per-step state on `self` or do I/O.

### State-Derived And Computed Outputs

The `outputs()` signature is not the same for every component, because the
engine evaluates `outputs()` in one of two ways, decided once in `finalize()`:

- **State-derived:** called as `outputs(state)`, without inputs, before any
  computed module. Every output must depend only on the component's own state
  and fixed parameters. Examples: the loop's `T_avg = (T_hot + T_cold) / 2`,
  the rod controller's `rho_rod` from the two bank positions, the
  pressurizer's pressure `P` from its mass and internal energy, and the
  secondary sink's constant `T_secondary`.
- **Computed:** called as `outputs(state, inputs=...)` after the modules that
  produce its inputs, in dependency order. Examples: the steam generator's
  `Q_sg = UA · (T_avg − T_secondary)`, the core's
  `Q_fuel_to_coolant = hA_fc · (T_fuel − T_cool)` (it needs the loop's
  `T_cool`), and the pressurizer controller's heater and spray demands (they
  need `P` and the setpoint).

How the engine decides:

1. If the component class declares `outputs_require_inputs = True`, the module
   is computed; `False` makes it state-derived. The declaration is trusted and
   no probe calls are made. `PointKineticsCore`, `SteamGenerator`, and
   `PressurizerController` declare `True`.
2. Without a declaration the engine infers the kind. It calls
   `outputs(state)` on the initial state: success means state-derived. A
   `TypeError` means computed, for example from an `outputs()` that raises it
   when `inputs` is `None`, or one that takes `inputs` as a required keyword
   (`outputs(state, *, inputs)`), so Python raises it. The engine confirms
   with one more call whose `inputs` mapping raises as soon as it is read. If
   that call raises `TypeError` again without reading any input, the
   first error came from a bug inside `outputs()`, and `finalize()` raises
   `EngineWiringError` instead of silently treating the module as computed.

The rule to keep when writing a component: `outputs(state)` may succeed only
if every output really depends on state and parameters alone. An `outputs()`
that returns a harmless default when `inputs` is omitted is classified as
state-derived, and the engine then never gives it inputs, so its outputs
silently ignore their real input dependencies. Prefer declaring
`outputs_require_inputs` in a new component over relying on the probe.

**Telemetry-only quantities.** A value that is useful to display but that no
other component needs goes only in `telemetry()`. The engine passes
`telemetry()` the module's inputs when it builds a snapshot, but it must also
accept `inputs=None` and then report `None` for input-dependent keys.
Examples: the core's reactivity breakdown (`rho_doppler`, `rho_moderator`,
`rho_total`) and `startup_rate_dpm`, the loop's `Q_flow`, and the
pressurizer's `m_dot_surge` and `subcooling_margin`. The pressurizer is
state-derived so that its pressure is available early; `m_dot_surge` needs
inputs, so it cannot be one of its output ports. The loop and the pressurizer
each compute the surge flow themselves with the shared
`surge.compute_m_dot_surge` helper.

### Why Derivative Dependencies Do Not Create Cycles

The plant is full of feedback loops: the core heats the loop, and the loop's
temperature feeds back into the core's reactivity. Those loops close through
the state vector, not through `outputs()`. In every evaluation of the ODE
right-hand side the engine first resolves all outputs (state-derived modules,
then computed modules in dependency order) and only then calls every
`derivatives()`. A derivative reads the current outputs and returns a rate of
change; its effect on anyone's inputs appears only later, through the
integrated state.

For example, the loop's `T_cool` is state-derived, the core's
`Q_fuel_to_coolant` is computed from it, and the loop reads
`Q_fuel_to_coolant` only in `derivatives()`. The evaluation order is loop
outputs → core outputs → all derivatives, with no cycle. In the same way the
pressurizer's `P` (state-derived) feeds the controller's computed demands,
which the pressurizer reads only in `derivatives()`. `finalize()` reports a
cycle only when computed outputs need each other at the same instant,
including a computed module wired to its own output.

## Simulation Engine

`SimEngine` (in `src/fission_sim/engine/engine.py`) is the graph runner that
owns global state, wires components, and steps time. It has zero physics
imports; all it knows is components, ports, and ODEs.

### API

For everyday use, get the standard plant from one call:

```python
from fission_sim.plant import build_standard_plant

engine = build_standard_plant()  # finalized, at the design steady state
```

Keyword arguments replace one component's parameters, for example
`build_standard_plant(core_params=CoreParams(alpha_m=-2e-4))`, or set the
defaults of the `rod_command` and `P_setpoint` externals. The module names
(the snapshot keys) are `rod`, `core`, `loop`, `sg`, `sink`, `pzr`, and
`pzr_ctrl`.

The web runtime and the `report_primary.py`, `power_maneuver.py`,
`console.py`, and `dump_state.py` examples use it. The tutorial below builds
the same plant by hand so every step of the engine API is visible;
`examples/run_primary.py` is the one example that does the same.
`tests/test_docs.py` and `tests/test_examples.py` check that both copies
match the factory's wiring.

<!-- engine-tutorial: tests/test_docs.py runs this block -->
```python
from fission_sim.control.pressurizer_controller import (
    PressurizerController,
    PressurizerControllerParams,
)
from fission_sim.engine import SimEngine
from fission_sim.physics.core import CoreParams, PointKineticsCore
from fission_sim.physics.domain import check_snapshot
from fission_sim.physics.pressurizer import Pressurizer, PressurizerParams
from fission_sim.physics.primary_loop import LoopParams, PrimaryLoop
from fission_sim.physics.rod_controller import RodController, RodParams
from fission_sim.physics.secondary_sink import SecondarySink, SinkParams
from fission_sim.physics.steam_generator import SGParams, SteamGenerator

engine = SimEngine()

# 1. Register components. The name is the module's key in snapshots; it
#    defaults to the snake_case class name ("point_kinetics_core").
loop_params = LoopParams()
rod = engine.module(RodController(RodParams()), name="rod")
core = engine.module(PointKineticsCore(CoreParams()), name="core")
loop = engine.module(PrimaryLoop(loop_params), name="loop")
sg = engine.module(SteamGenerator(SGParams()), name="sg")
sink = engine.module(SecondarySink(SinkParams()), name="sink")
# The pressurizer computes surge flow from the loop's thermal expansion, so
# it gets the same LoopParams as the loop.
pzr = engine.module(Pressurizer(PressurizerParams(loop_params=loop_params)), name="pzr")
pzr_ctrl = engine.module(PressurizerController(PressurizerControllerParams()), name="pzr_ctrl")

# 2. Declare external operator inputs with their defaults.
rod_cmd = engine.input("rod_command", default=0.5)  # control bank, fraction withdrawn
scram = engine.input("scram", default=False)
P_set = engine.input("P_setpoint", default=15.5e6)  # [Pa]
heater_manual = engine.input("heater_manual", default=None)  # None = automatic
spray_manual = engine.input("spray_manual", default=None)

# 3. Wire by calling. Every output port is also an attribute (loop.T_avg,
#    core.Q_fuel_to_coolant); a module with exactly one output port returns
#    it from the call (Q_sg = sg(...)). Wiring order does not matter.
rho_rod = rod(rod_command=rod_cmd, scram=scram)
T_sec = sink()
Q_sg = sg(T_avg=loop.T_avg, T_secondary=T_sec)
core(rho_rod=rho_rod, T_cool=loop.T_cool)
pzr(
    Q_fuel_to_coolant=core.Q_fuel_to_coolant,
    Q_sg=Q_sg,
    T_hotleg=loop.T_hot,
    T_coldleg=loop.T_cold,
    Q_heater=pzr_ctrl.Q_heater,
    m_dot_spray=pzr_ctrl.m_dot_spray,
)
pzr_ctrl(P=pzr.P, P_setpoint=P_set, heater_manual=heater_manual, spray_manual=spray_manual)
loop(
    Q_fuel_to_coolant=core.Q_fuel_to_coolant,  # heat leaving the fuel, not fission power
    Q_sg=Q_sg,
    m_dot_spray=pzr_ctrl.m_dot_spray,
    P_primary=pzr.P,
)

# 4. Finalize validates the graph, classifies each module's outputs as
#    state-derived or computed, and allocates the state vector.
engine.finalize()  # optional; auto-called on first step()/run()

# 5a. Step-at-a-time, as the web runtime does. A keyword overrides an
#     external for this step only. 0.6 asks for +120 pcm of control-bank
#     withdrawal (12 pcm per 1 % of travel); at 1 %/s the bank needs about
#     10 s to get there.
snap = engine.step(dt=1.0, rod_command=0.6)
print(snap["t"], snap["rod"]["rod_position"], snap["core"]["power_thermal"])

# 5b. Or run a whole scenario: a function of time that returns externals.
def scenario(t):
    return {"rod_command": 0.6, "scram": t >= 60.0}

final = engine.run(t_end=120.0, scenario_fn=scenario)
check_snapshot(final)  # raises ModelDomainError outside the model's domain
print(final["t"], final["core"]["power_thermal"], final["core"]["rho_total"])
```

Fission power is read from the core's telemetry, `snap["core"]["power_thermal"]`.
No module consumes it (the loop is heated by `Q_fuel_to_coolant`), so it is
not a wired signal and does not appear in `snap["signals"]`.

To undo a step, checkpoint `t0, y0 = engine.t, engine.state.copy()` before
it and call `engine.restore(t0, y0)` afterwards. Only time and the state
vector are restored (externals are per-call). The web runtime does this when
a step fails or ends outside the model's domain, so it holds the last valid
state.

### Snapshot Dict Shape

Returned by `step()`, `run()`, and `engine.snapshot()`. This is the plant
above after `step(dt=5.0)` at the design steady state, values rounded:

```python
{
    "t": 5.0,
    "signals": {
        "rod_command": 0.5, "scram": False, "P_setpoint": 15500000.0,
        "heater_manual": None, "spray_manual": None,
        "rho_rod": 0.0, "T_hot": 597.742, "T_cold": 568.258,
        "T_avg": 583.0, "T_cool": 583.0, "T_secondary": 558.0,
        "P": 15499345.2, "Q_fuel_to_coolant": 3.0e9,
        "Q_heater": 0.0, "m_dot_spray": 0.0, "Q_sg": 3.0e9,
    },
    "rod": {
        "rod_position": 0.5, "shutdown_position": 1.0,
        "rho_rod": 0.0, "rho_control": 0.0, "rho_shutdown": 0.0,
        "rod_command": 0.5, "scram": False, "rod_command_effective": 0.5,
    },
    "core": {
        "power_thermal": 3.0e9, "T_fuel": 1100.0, "Q_fuel_to_coolant": 3.0e9,
        "n": 1.0, "C1": 433.47, "C2": 1167.21, "C3": 286.94,
        "C4": 213.29, "C5": 16.40, "C6": 2.27,
        "rho_total": 0.0, "rho_rod": 0.0, "rho_doppler": 0.0,
        "rho_moderator": 0.0, "startup_rate_dpm": 0.0,
    },
    "loop": {
        "T_hot": 597.742, "T_cold": 568.258, "T_avg": 583.0, "T_cool": 583.0,
        "delta_T": 29.484, "Q_flow": 3.0e9, "Tref": 583.0, "M_loop": 123392.6,
        "Q_fuel_to_coolant": 3.0e9, "Q_sg": 3.0e9,
    },
    "sg": {"Q_sg": 3.0e9, "T_avg": 583.0, "T_secondary": 558.0, "delta_T": 25.0},
    "sink": {"T_secondary": 558.0},
    "pzr": {
        "P": 15499345.2, "level": 0.49999, "T_sat": 617.938,
        "x": 0.14638, "M_l": 15156.3, "M_v": 2598.9,
        "M_pzr": 17755.2, "U_pzr": 3.06595e10,
        "m_dot_surge": 0.0, "subcooling_margin": 20.196,
        "heater_on": False, "spray_open": False, "Q_heater": 0.0, "m_dot_spray": 0.0,
    },
    "pzr_ctrl": {
        "Q_heater": 0.0, "m_dot_spray": 0.0, "P": 15499345.2,
        "P_setpoint": 15500000.0, "heater_manual": None, "spray_manual": None,
    },
}
```

`signals` contains every wired signal: the externals plus module outputs that
at least one module consumes. Each is keyed by its canonical name, which is
the producing port's name: the pressurizer's `P` appears as `"P"` even though
the loop's input port for it is called `P_primary`. Each `<module_name>` key
holds that module's `telemetry()` dict, computed with the same inputs the
module's derivatives see.

### Wiring Rules

- Globally unique signal names. Two modules whose outputs are wired cannot
  expose an output port with the same name, and a wired external cannot share
  a name with a wired module output.
- Every output port is accessible as an attribute (`loop.T_avg`,
  `pzr_ctrl.m_dot_spray`), even before the module itself is called. Calling a
  module records its inputs; if it has exactly one output port the call also
  returns that `Signal`, otherwise it returns `None`.
- Each input port can be wired once. To rewire, construct a new engine.
- Externals not provided in `step()` or `scenario_fn(t)` fall back to the
  declared default.
- The module names `t` and `signals` are reserved: they are the snapshot's
  own keys.

### Wiring Errors And `finalize()`

`EngineWiringError` is raised in two places.

At wiring time, immediately: `engine.module(...)` with a reserved or
duplicate module name; `engine.input(...)` declaring the same external twice;
a module call with an unknown input port, a value that is not a `Signal`, or
an input port that is already wired; and any `module()` or `input()` call
after `finalize()`.

In `finalize()`: a signal created by a different `SimEngine`, signal name
collisions (between modules, or between an external and a module output),
dangling inputs, unused externals, an `initial_state()` of the wrong shape,
an `outputs()` that raises `TypeError` for a reason other than missing
inputs, an `outputs_require_inputs` that is not a bool, and cycles among
computed-output modules (including a computed module wired to its own
output).

### `run(dense=True)`

```python
import numpy as np

from fission_sim.plant import build_standard_plant

def scenario(t):  # same scenario as the tutorial above
    return {"rod_command": 0.6, "scram": t >= 60.0}

engine = build_standard_plant()
final, dense = engine.run(t_end=300.0, scenario_fn=scenario, dense=True)
mid = dense.at(150.0)
n_traj = dense.signal("n", np.linspace(0, 300, 1500))
```

`dense.at(t)` returns a snapshot at the given time or times. `dense.signal(name,
t_array)` returns a 1D array of values, falling back to module telemetry if the
name is not a wired signal (as here: `n` is core telemetry).

## Multi-Component Runners

The plant examples (`report_primary.py`, `power_maneuver.py`, `console.py`,
`dump_state.py`) and the web runtime get their plant from
`build_standard_plant()`. `run_primary.py` wires the same plant by hand, as
described above. They differ in scenario and output: matplotlib plots, ASCII
text reports, an interactive console, or a full state dump. The runners check
each sampled state with `check_snapshot`, and stop with the model-limit
explanation if the scenario leaves the model's domain. `run_core.py` and
`report_core.py` drive the core alone, without the engine.

The coupled-plant tests (`tests/test_primary_plant.py`,
`tests/test_pressurizer_plant.py`) wire their own plants rather than calling
the factory, so they remain independent checks of it.
