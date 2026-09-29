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
backend. If port 8000 is already taken on a shared machine, start the backend
on another port and tell Vite which API port to proxy. You can also give
Vite an explicit web port and require it to be free:

    uv run uvicorn fission_sim.api.app:app --host 127.0.0.1 --port 8767
    FISSION_SIM_API_PORT=8767 npm run dev --prefix web -- --port 5187 --strictPort

With `make dev`, both servers bind `0.0.0.0`, so the dashboard is reachable
from any host on your network at `http://<your-machine-ip>:5173`. In the
manual override above, the backend is loopback-only and Vite remains the
network-facing proxy. There is no authentication; only expose this on a
trusted network.

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
| `make install-e2e` | Install Chromium for the Playwright e2e suite |
| `make e2e` | Run Playwright e2e specs against an already-running stack |
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

## End-To-End Tests

The Playwright suite runs browser-level checks against an already-running
stack. `web/e2e/smoke.spec.ts` first drives the persistent backend to a known
design fixture (running at the requested speed, turbine admission demand
100 %, rods MANUAL, SG level setpoint 50 %, feedwater AUTO). It verifies
keyboard-reachable educational help, a SCRAM power drop through the
operator-controls SCRAM button, an unprotected turbine trip that raises steam
pressure and opens the dump path, the Reset Turbine Trip guard that waits for
actual admission to reach the 0.5 % closed-valve tolerance, and the rod
AUTO/MANUAL bumpless transfer from a real control-bank mismatch. The same
`npm run e2e` command also runs `web/e2e/schematic-geometry.spec.ts`, which
drives steady, trip, SCRAM, feedwater-manual and paused-pending states and
checks that the SVG schematic labels clear strokes at desktop and mobile
viewports.

Install the browser once:

    make install-e2e

Start the default stack in one terminal:

    make dev

Run the whole e2e suite in another:

    make e2e

By default Playwright opens `http://127.0.0.1:5173`. Override the browser
target when Vite is using a non-default port. The backend port is selected
when Vite starts via `FISSION_SIM_API_PORT`; Playwright only needs the Vite
URL:

    uv run uvicorn fission_sim.api.app:app --host 127.0.0.1 --port 8767
    FISSION_SIM_API_PORT=8767 npm run dev --prefix web -- --port 5187 --strictPort
    E2E_BASE_URL=http://127.0.0.1:5187 npm run e2e --prefix web

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

Each frame is one JSON object. The runtime casts values at this boundary to
plain Python `float`, `bool`, `None`, or `str` before JSON serialization, so
the browser never has to handle numpy scalar objects. All numeric fields use
SI units internally; `P_primary_MPa` and `P_steam_MPa` are convenience
conversions provided for display. Nullable numeric fields are explicitly
`null` when not applicable. The example is a real frame from the design
steady state:

```json
{
  "t": 0.0,
  "power_thermal": 3000000000.0,
  "T_hot": 597.7420147420147,
  "T_cold": 568.2579852579853,
  "T_avg": 583.0,
  "T_fuel": 1100.0,
  "rod_position": 0.5,
  "shutdown_position": 1.0,
  "P_primary_Pa": 15499345.236082302,
  "P_primary_MPa": 15.499345236082302,
  "pzr_level": 0.49999478981883927,
  "Q_sg": 3000000000.0,
  "rho_rod": 0.0,
  "rho_doppler": -0.0,
  "rho_moderator": -0.0,
  "rho_total": 0.0,
  "P_steam_Pa": 6899179.981585782,
  "P_steam_MPa": 6.899179981585782,
  "T_secondary": 558.0,
  "level_sg": 0.49999999999999856,
  "time_to_level_floor_s": null,
  "m_steam": 1669.012362331777,
  "m_dump": 0.0,
  "P_electric": 989999999.9999962,
  "turbine_load": 1.0,
  "T_ref": 583.0,
  "turbine_load_demand_effective": 1.0,
  "turbine_trip_active": false,
  "m_fw": 1669.0123623317777,
  "m_fw_max": 2002.8148347981332,
  "m_fw_demand": 1669.0123623317818,
  "fw_saturated": false,
  "feedwater_manual_effective": null,
  "rod_demand": 0.5,
  "rod_auto_acting": false,
  "running": true,
  "speed": 1.0,
  "scrammed": false,
  "rod_command": 0.5,
  "turbine_load_demand": 1.0,
  "turbine_trip": false,
  "rod_auto": false,
  "level_setpoint": 0.5,
  "feedwater_manual": null,
  "model_limit": null
}
```

The design primary pressure reads about 0.65 kPa below 15.5 MPa because the
initial pressurizer inventory is derived with one CoolProp backend
(IAPWS-IF97) and converted back to a pressure with another (Helmholtz EOS);
see [README.md → Pressurizer](README.md#pressurizer-srcfission_simphysicspressurizerpy).

| Key | Type | Units | Description |
|---|---|---|---|
| `t` | float | s | Simulation time |
| `power_thermal` | float | W | Modeled fission power, `n · P_design`. Fission-product decay heat is not modeled. |
| `T_hot` | float | K | Hot-leg coolant temperature |
| `T_cold` | float | K | Cold-leg coolant temperature |
| `T_avg` | float | K | Average primary coolant temperature, `(T_hot + T_cold) / 2` |
| `T_fuel` | float | K | Lumped (average) fuel temperature, not the centerline |
| `rod_position` | float | dimensionless | Actual control-bank position (0 = inserted, 1 = withdrawn). |
| `shutdown_position` | float | dimensionless | Shutdown-bank position (1 = withdrawn, 0 = inserted); after Reset Scram this remains near 0 until Reset Simulation. |
| `P_primary_Pa` | float | Pa | Primary system pressure from pressurizer |
| `P_primary_MPa` | float | MPa | Same primary pressure, converted for display |
| `pzr_level` | float | dimensionless | Pressurizer liquid level, fraction of pressurizer volume |
| `Q_sg` | float | W | Heat removed by the steam generator |
| `rho_rod` | float | dimensionless | Rod reactivity, control bank + shutdown bank |
| `rho_doppler` | float | dimensionless | Doppler fuel-temperature reactivity feedback |
| `rho_moderator` | float | dimensionless | Moderator coolant-temperature reactivity feedback |
| `rho_total` | float | dimensionless | Total reactivity |
| `P_steam_Pa` | float | Pa | Steam-generator secondary pressure |
| `P_steam_MPa` | float | MPa | Same steam pressure, converted for display |
| `T_secondary` | float | K | Secondary saturation temperature read by the primary-side SG heat exchanger |
| `level_sg` | float | dimensionless | SG collapsed liquid fraction (4 SGs lumped, no shrink/swell) |
| `time_to_level_floor_s` | float or null | s | Frozen-property estimate of time until the SG collapsed level reaches the model floor; `null` when not draining |
| `m_steam` | float | kg/s | Turbine steam flow |
| `m_dump` | float | kg/s | Steam dump / relief flow |
| `P_electric` | float | W | Gross electric output proxy from the turbine model |
| `turbine_load` | float | dimensionless | Actual turbine admission fraction after governor ramp/trip dynamics |
| `T_ref` | float | K | Load-dependent Tavg reference from the turbine program |
| `turbine_load_demand_effective` | float | dimensionless | Last-stepped turbine admission demand actually used by the turbine component; differs from `turbine_load_demand` while a paused command is pending |
| `turbine_trip_active` | bool | dimensionless | Effective turbine-trip status: operator trip latch or SCRAM/P-4 interlock |
| `m_fw` | float | kg/s | Actual feedwater actuator flow |
| `m_fw_max` | float | kg/s | Maximum feedwater actuator flow (120 % of design steam flow) |
| `m_fw_demand` | float | kg/s | Feedwater-controller demand before actuator lag |
| `fw_saturated` | bool | dimensionless | Whether the feedwater controller demand is clamped at an actuator limit |
| `feedwater_manual_effective` | float or null | dimensionless | Last-stepped manual feedwater fraction actually used by the feedwater controller; `null` = AUTO |
| `rod_demand` | float | dimensionless | Rod demand actually sent to the rod actuator (manual command, automatic demand, or suspended hold) |
| `rod_auto_acting` | bool | dimensionless | Whether automatic Tavg rod control is actively moving rods (not merely selected) |
| `running` | bool | dimensionless | Whether simulated time is advancing (false while paused or halted at a model limit) |
| `speed` | float | dimensionless | Simulation speed multiplier (1.0 = real time) |
| `scrammed` | bool | dimensionless | Whether the SCRAM latch is set |
| `rod_command` | float | dimensionless | Retained manual control-bank command (fraction withdrawn) |
| `turbine_load_demand` | float | dimensionless | Operator turbine-admission demand; actual admission ramps toward it at 5 %/min |
| `turbine_trip` | bool | dimensionless | Operator turbine-trip latch (does not include SCRAM/P-4) |
| `rod_auto` | bool | dimensionless | Operator-selected rod mode: true = automatic Tavg control, false = manual |
| `level_setpoint` | float | dimensionless | Feedwater-controller SG collapsed-level setpoint |
| `feedwater_manual` | float or null | dimensionless | Manual feedwater demand as a fraction of `m_fw_max`; `null` = AUTO |
| `model_limit` | string or null | — | Why the simulation halted at the edge of the model, or `null`. A halt caused by an unexpected step failure instead starts with `Simulation error: `. |

#### Command Messages

Commands are JSON objects with a `"type"` discriminator. The server returns an
acknowledgement frame such as `{"type": "ack", "command": "set_speed"}` on
success, or an error frame `{"type": "error", "detail": "..."}` on failure.
Text that is not valid JSON, and binary WebSocket frames, are also answered
with an error frame. Errors do not disconnect the WebSocket.

Every numeric `value` must be a JSON number (not a string or boolean) and
finite; non-standard JSON literals accepted by Python such as `NaN` and
`Infinity` are rejected. While the simulation is paused or halted, a command
that changes what the frame reports (rod command, SCRAM latch, speed, pause
state, turbine admission demand/trip, rod mode, level setpoint, or feedwater
mode) is published as one new frame with `t` unchanged, so every client sees
it. A command that changes nothing visible publishes nothing. When selected
command fields disagree with last-stepped effective fields while not running,
the frontend labels the state as pending instead of presenting it as already
applied.

| Command | Payload | Effect |
|---|---|---|
| `set_rod_command` | `value` in `[0, 1]` | Stores the manual control-bank command. |
| `set_rod_auto` | JSON boolean `value` | Selects AUTO Tavg rod control or MANUAL; AUTO→MANUAL copies actual rod position into `rod_command`. |
| `scram` | none | Latches SCRAM and drops the control and shutdown banks. |
| `reset_scram` | none | Clears the SCRAM latch, leaves the shutdown bank inserted, latches any accepted P-4 turbine trip as an operator turbine trip, and sets turbine admission demand to 0. |
| `set_turbine_load` | `value` in `[0, 1]` | Sets turbine admission demand; actual admission ramps at 5 percentage-points/min while not tripped. |
| `turbine_trip` | none | Sets the operator turbine-trip latch. |
| `reset_turbine_trip` | none | Clears the operator latch and sets turbine admission demand to 0; refused until actual admission is ≤ 0.5 %. |
| `pause` | none | Stops advancing simulated time. |
| `resume` | none | Resumes simulated time unless a model-limit halt is active. |
| `reset` | none | Rebuilds the plant at design full-power state; preserves selected settings listed below. |
| `set_speed` | one of `1`, `2`, `5`, `10` | Sets the wall-clock-to-simulation speed multiplier. |
| `set_pressure_setpoint` | `value` in `[10e6, 20e6]` Pa | Sets the pressurizer controller pressure target; not shown in the dashboard controls. |
| `set_level_setpoint` | `value` in `[0.35, 0.90]` | Sets the SG collapsed-liquid-fraction target. |
| `set_feedwater_manual` | `value` in `[0, 1]` or `null` | Selects manual feedwater demand as a fraction of `m_fw_max`, or AUTO with `null`. |

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

**`set_rod_auto`** - select automatic Tavg rod control or manual rods.

```json
{"type": "set_rod_auto", "value": true}
```

`value`: JSON boolean. `true` lets the load-dependent Tavg controller drive
`rod_demand`; `false` returns to manual `rod_command`. On an automatic-to-manual
transfer the runtime first copies the actual `rod_position` into `rod_command`,
so the transfer is bumpless: a stale manual command cannot immediately move the
bank after automatic control has repositioned it.

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

**`reset_scram`** - clear the SCRAM latch and require explicit turbine
re-admission.

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
latch is unconditional (no interlock logic is modeled). Clearing SCRAM also sets `turbine_load_demand` to 0 because the SCRAM tripped
the turbine through P-4; re-admission is an explicit operator action. If the
last accepted plant state had an effective P-4 turbine trip and no operator
turbine-trip latch, Reset Scram sets the operator latch before clearing the
SCRAM latch. Resetting the reactor trip is therefore not a shortcut around the
separate turbine-trip reset: the simulated stop valves keep closing until the
operator resets that trip after closure.

**`set_turbine_load`** - set turbine admission demand.

```json
{"type": "set_turbine_load", "value": 0.75}
```

`value`: float in `[0, 1]`, the requested turbine admission fraction. Actual
`turbine_load` ramps toward the demand at 5 %/min while no trip is active.
This is valve admission, not electrical load; gross electric output is
reported separately as `P_electric`.

**`turbine_trip`** - set the operator turbine-trip latch.

```json
{"type": "turbine_trip"}
```

No extra fields. Closes turbine admission through the turbine model. This is
an unprotected exercise in the current simulator: a real plant would normally
trip the reactor on a turbine trip above roughly half power (P-9), but that
interlock is not modeled.

**`reset_turbine_trip`** - clear the operator turbine-trip latch.

```json
{"type": "reset_turbine_trip"}
```

No extra fields. Refused with an error frame while actual turbine admission
(`turbine_load` in the last accepted frame) is above 0.5 %:

```json
{"type": "error", "detail": "turbine valves still closing (6.8 % open); reset the trip once they are closed"}
```

The guard matters because clearing the trip hands the admission valves back to
the ordinary governor ramp, which closes at only 5 percentage-points/min. An
early reset with several percent actual admission would leave steam flowing for
over a minute even though demand is already zero. Once accepted, this command
sets `turbine_load_demand` to 0, so clearing the latch cannot silently re-open
the turbine to an old admission demand. Re-admission is an explicit operator
action through `set_turbine_load`.

**`pause`** - stop advancing simulated time. The background loop keeps
running.

```json
{"type": "pause"}
```

No extra fields. The runtime publishes one frame with `running = false`.
While paused, a frame is published only when an accepted command changes the
command state (for example rod command, SCRAM, speed, turbine admission,
rod mode, level setpoint, or feedwater mode), with `t` unchanged, or when
a `reset` publishes its t = 0 frame; otherwise no frames are emitted. Resume
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
pressurizer and SG inventory, actual turbine admission, and both rod banks) is
rebuilt at the design full-power state at t = 0: actual turbine admission
starts at 100 %. The selected admission demand is kept, so a kept demand below
100 % immediately ramps the actual valve down after reset. `rod_command`
returns to 0.5; the SCRAM latch, operator turbine-trip latch, and manual
feedwater override are cleared. A model-limit halt is cleared and the
simulation runs again. `P_setpoint`, `speed`, `turbine_load_demand`,
`rod_auto`, and `level_setpoint` are kept, and so is a pause the operator
chose. One frame at t = 0 is published. Calling `SimRuntime.reset()` directly
does exactly the same.

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

**`set_level_setpoint`** - adjust the SG level controller target.

```json
{"type": "set_level_setpoint", "value": 0.5}
```

`value`: float in `[0.35, 0.90]`, the SG collapsed liquid fraction target.
This operating band stays inside the model validity limits (0.30 floor and
0.95 overfill ceiling). The displayed level is the SG collapsed liquid
fraction (4 SGs lumped, no shrink/swell).

**`set_feedwater_manual`** - select feedwater manual demand or AUTO.

```json
{"type": "set_feedwater_manual", "value": 0.5}
```

`value`: float in `[0, 1]` or `null`. A number is a manual demand as a
fraction of `m_fw_max`; `null` returns to automatic three-element level
control. The frame reports both actual feedwater flow (`m_fw`) and controller
demand (`m_fw_demand`) in kg/s.

#### Model-Limit Halt

After every step the runtime checks the new state against the model's
supported domain (`fission_sim.physics.domain.check_snapshot`; the limits are
explained in [README.md → Model Limits](README.md#model-limits)): hot-leg
boiling, pressurizer dry/water-solid states, primary or steam pressure outside
the modeled range, and SG collapsed liquid fraction outside 30–95 %. If a
step leaves the domain, or fails outright, the runtime:

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
- The standard M4 plant modules are `rod`, `core`, `loop`, `sg`, `sg_sec`,
  `turbine`, `feedwater`, `fw_ctrl`, `tavg_ctrl`, `pzr`, and `pzr_ctrl`.
  The older `SecondarySink` remains available for M1/M2 regression plants
  but is not in the standard wiring.
- The standard module classes are `RodController`, `PointKineticsCore`,
  `PrimaryLoop`, `SteamGenerator`, `SGSecondary`, `Turbine`,
  `FeedwaterSystem`, `FeedwaterController`, `TavgController`, `Pressurizer`,
  and `PressurizerController`. There is no `sink` module key in a standard
  M4 snapshot.
- `fission_sim.api` is the only package that knows about asyncio, HTTP, or
  WebSocket. `runtime.py` is HTTP-agnostic; `app.py` is physics-agnostic.
- The Vite frontend is a separate process. During development, the Vite proxy
  (`/api`, `/ws` to `127.0.0.1:8000` by default, or `FISSION_SIM_API_PORT`)
  removes the need for browser CORS preflights.

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
`http://127.0.0.1:8000` and `ws://127.0.0.1:8000`, respectively. Set
`FISSION_SIM_API_PORT` before starting Vite to proxy both paths to a different
loopback port when 8000 is occupied.
Authentication, persistence, multi-user support, and replay are not
implemented.

A frame's path through the frontend:

- `wsClient.ts` receives it, and the Zustand store in `telemetryStore.ts`
  keeps it as `latest`. History is trimmed by simulated time to
  `HISTORY_RETENTION_S = 905 s` (the 15-minute chart window plus a 5 s entry
  margin) and then capped at `HISTORY_MAX_FRAMES = 12_000` for unusual paused
  command bursts. If simulation time rolls backward, the store treats that as
  a reset and starts fresh history and events. On disconnect it clears only
  the event baseline/tracker, so reconnects do not invent transitions across
  an unobserved gap.
- The store keeps the newest `EVENTS_CAP = 100` plant events, oldest first in
  state and newest first in `EventLog.tsx`. `events.ts` compares consecutive
  frames plus tracker state, and `EventLog.helpers.ts` turns long model-limit
  halt events into one-line summaries while the full explanation remains in
  the halt notice.
- `plantStatus.ts` derives shared one-frame classifications — turbine-trip
  cause/pending state, rod AUTO ACTIVE/AUTO SUSPENDED/MANUAL, feedwater
  AUTO/MANUAL/saturation, steam-dump open state, SG level band, and the
  shutdown-bank-in indication — so controls, toolbar, schematic, readouts and
  events use the same wording. `admissionStatus.ts` adds turbine-admission
  demand pending state, actual-admission closed status (`<= 0.005`, 0.5 %
  open), and the Reset Turbine Trip guard used by the controls and toolbar.
- Event tracking uses explicit thresholds and dwell times: steam dump opens
  above 1 kg/s and closes below 0.5 kg/s; feedwater saturation enter/leave
  events require `FEEDWATER_SATURATION_DWELL_S = 0.3 s`; routine command
  events carry categories (`plant`, `command`, `alarm`) and same-key slider
  bursts coalesce only when consecutive and received within
  `COMMAND_COALESCE_WINDOW_MS = 1000 ms`.
- `chartData.ts` turns history into chart columns for 60 s, 300 s, and 900 s
  simulated-time windows (`1 min`, `5 min`, `15 min`). Long windows are
  decimated to at most `MAX_DISPLAY_POINTS = 1800` points per chart while
  preserving each bucket's first, last, minimum and maximum samples.
  `chartSpecs.ts` defines ten charts and the operator views:
  **All** (all ten), **Reactor** (power, reactivity, coolant, fuel, primary
  pressure, rods), and **Secondary** (power, coolant/T_ref, steam pressure,
  SG level, steam/feed flow, gross electrical output). `ChartGrid.tsx`
  defaults to **All** and the 1-minute window, keeps rows at 15.5 rem, lets
  the chart column scroll, and gives every chart its own time axis.
- The charts redraw on every display refresh, not only when a frame arrives.
  One `requestAnimationFrame` loop (`ticker.ts`) drives all charts; their
  right edge follows `displayClock.ts`, which advances continuously one frame
  period behind the newest frame, so traces scroll smoothly instead of
  stepping ten times a second. Each y axis is sticky and eases between ranges
  (`autoRange.ts`). Data, scales and legend values go to uPlot and the DOM
  directly, so React does not re-render per frame.
- Colours are CSS variables in `index.css`: one palette, a black ground with
  white ink and hairlines, amber for caution and red for alarm. There is no
  light theme. Text is IBM Plex Sans and every number IBM Plex Mono,
  self-hosted from `@fontsource`.
- `widgets/PlantMimic.tsx` draws the primary/secondary schematic from the
  latest frame, including pressurizer fill from `pzr_level`, SG collapsed
  liquid fraction, turbine/dump/feedwater paths, control-bank `% withdrawn`
  and the shutdown-bank-in cue. `widgets/loopState.ts` words the schematic
  title using the shared status helpers. `widgets/EventLog.tsx` renders the
  full retained event history in a scrollable list under the "Now" row.
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
  pressurizer's pressure `P` from its mass and internal energy, and the SG
  shell's `P_steam` / `T_secondary` / `level_sg` from its mass and internal
  energy. The older M1/M2 secondary sink's constant `T_secondary` follows the
  same state-derived rule in regression plants.
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
defaults of the `rod_command`, `P_setpoint`, `turbine_load`, and `rod_auto`
externals. The module names (the snapshot keys) are `rod`, `core`, `loop`,
`sg`, `sg_sec`, `turbine`, `feedwater`, `fw_ctrl`, `tavg_ctrl`, `pzr`, and
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
from fission_sim.control.feedwater_controller import FeedwaterController, FeedwaterControllerParams
from fission_sim.control.tavg_controller import TavgController, TavgControllerParams
from fission_sim.engine import SimEngine
from fission_sim.physics.core import CoreParams, PointKineticsCore
from fission_sim.physics.domain import check_snapshot
from fission_sim.physics.feedwater import FeedwaterParams, FeedwaterSystem
from fission_sim.physics.pressurizer import Pressurizer, PressurizerParams
from fission_sim.physics.primary_loop import LoopParams, PrimaryLoop
from fission_sim.physics.rod_controller import RodController, RodParams
from fission_sim.physics.sg_secondary import SGSecondary, SGSecondaryParams
from fission_sim.physics.steam_generator import SGParams, SteamGenerator
from fission_sim.physics.turbine import Turbine, TurbineParams

engine = SimEngine()

# 1. Register components. The name is the module's key in snapshots; it
#    defaults to the snake_case class name ("point_kinetics_core").
loop_params = LoopParams()
rod_params = RodParams()
sg_params = SGParams()
sg_sec_params = SGSecondaryParams()
turbine_params = TurbineParams(sg_params=sg_sec_params)
fw_params = FeedwaterControllerParams(sg_params=sg_sec_params)
feedwater_params = FeedwaterParams(sg_params=sg_sec_params)
tavg_params = TavgControllerParams()
rod_position_initial = (
    rod_params.rod_position_design
    if rod_params.rod_position_initial is None
    else rod_params.rod_position_initial
)

rod = engine.module(RodController(rod_params), name="rod")
core = engine.module(PointKineticsCore(CoreParams()), name="core")
loop = engine.module(PrimaryLoop(loop_params), name="loop")
sg = engine.module(SteamGenerator(sg_params), name="sg")
sg_sec = engine.module(SGSecondary(sg_sec_params), name="sg_sec")
turbine = engine.module(Turbine(turbine_params), name="turbine")
feedwater = engine.module(FeedwaterSystem(feedwater_params), name="feedwater")
fw_ctrl = engine.module(FeedwaterController(fw_params), name="fw_ctrl")
tavg_ctrl = engine.module(
    TavgController(tavg_params, rod_position_initial=rod_position_initial),
    name="tavg_ctrl",
)
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
load_demand = engine.input("turbine_load", default=turbine_params.load_initial)
trip = engine.input("turbine_trip", default=False)
auto = engine.input("rod_auto", default=False)
level_set = engine.input("level_setpoint", default=fw_params.level_setpoint_default)
fw_manual = engine.input("feedwater_manual", default=None)

# 3. Wire by calling. Every output port is also an attribute (loop.T_avg,
#    core.Q_fuel_to_coolant); a module with exactly one output port returns
#    it from the call (Q_sg = sg(...)). The rod controller has two outputs,
#    so its rho_rod signal is read as rod.rho_rod. Wiring order does not matter.
rod(rod_command=tavg_ctrl.rod_demand, scram=scram)
Q_sg = sg(T_avg=loop.T_avg, T_secondary=sg_sec.T_secondary)
turbine(P_steam=sg_sec.P_steam, load_demand=load_demand, turbine_trip=trip, scram=scram)
fw_ctrl(
    level_sg=sg_sec.level_sg,
    level_setpoint=level_set,
    m_steam=turbine.m_steam,
    m_dump=turbine.m_dump,
    feedwater_manual=fw_manual,
)
feedwater(m_fw_demand=fw_ctrl.m_fw_demand)
sg_sec(Q_sg=Q_sg, m_steam=turbine.m_steam, m_dump=turbine.m_dump, m_fw=feedwater.m_fw)
tavg_ctrl(
    T_avg=loop.T_avg,
    T_ref=turbine.T_ref,
    rod_position=rod.rod_position,
    rod_command=rod_cmd,
    rod_auto=auto,
    scram=scram,
    turbine_trip=trip,
)
core(rho_rod=rod.rho_rod, T_cool=loop.T_cool)
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
above after `step(dt=5.0)` at the design steady state, values rounded.

There is no `sink` key in this M4 standard-plant shape; `SecondarySink`
appears only in deliberately hand-wired M1/M2 regression plants.

```python
{
    "t": 5.0,
    "signals": {
        "rod_command": 0.5, "scram": False, "P_setpoint": 15500000.0,
        "heater_manual": None, "spray_manual": None,
        "turbine_load": 1.0, "turbine_trip": False, "rod_auto": False,
        "level_setpoint": 0.5, "feedwater_manual": None,
        "rho_rod": 0.0, "rod_position": 0.5,
        "T_hot": 597.742, "T_cold": 568.258, "T_avg": 583.0,
        "T_cool": 583.0, "T_secondary": 558.0,
        "P_steam": 6.899e6, "P": 15499345.2, "Q_fuel_to_coolant": 3.0e9,
        "Q_heater": 0.0, "m_dot_spray": 0.0, "Q_sg": 3.0e9,
        "m_steam": 1669.0, "m_dump": 0.0, "T_ref": 583.0,
        "m_fw_demand": 1669.0, "m_fw": 1669.0, "rod_demand": 0.5,
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
    "sg_sec": {
        "P_steam": 6.899e6, "T_secondary": 558.0, "level_sg": 0.5,
        "level_margin_low": 0.2, "x": 0.0462, "M_l": 222458.1, "M_v": 10781.0,
        "M_sec": 233239.1, "U_sec": 3.06608e11,
        "h_g": 2.77387e6, "h_fw": 9.76402e5, "P_fw_flash": 2.6389e6,
        "Q_sg": 3.0e9,
        "m_steam": 1669.0, "m_dump": 0.0, "m_fw": 1669.0,
        "Q_steam_net": 3.0e9,
        "boil_off_time_s": 133.3,
    },
    "turbine": {
        "load": 1.0, "m_steam": 1669.0, "m_dump": 0.0,
        "P_electric": 9.9e8, "T_ref": 583.0, "P_steam": 6.899e6,
        "load_demand": 1.0, "turbine_trip": False, "scram": False,
        "trip_active": False,
    },
    "feedwater": {"m_fw": 1669.0, "m_fw_demand": 1669.0, "m_fw_max": 2002.8},
    "fw_ctrl": {
        "m_fw_demand": 1669.0, "level_error": 0.0, "level_error_integral": 0.0,
        "feedwater_manual": None, "mode": "auto", "saturated": False,
    },
    "tavg_ctrl": {
        "rod_demand_auto": 0.5, "rod_demand": 0.5,
        "T_err": 0.0, "rod_auto": False, "acting": False,
        "T_avg": 583.0, "T_ref": 583.0, "rod_position": 0.5,
        "rod_command": 0.5, "scram": False, "turbine_trip": False,
    },
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
