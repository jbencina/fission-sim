# Readability and educational documentation review

Baseline: `5dc6e641ef7807e323a5b9c90637696a60ad07e4`

Review branch: `review/accuracy-readability-craft`

Independently re-verified on 2026-09-26; see the audit section of
[README.md](README.md). R8 and the additional rows in R2, R3, R4, R5, and R7
come from that pass. Line references were corrected where they were off.

## Assessment

The code is generally easy to follow at the equation and component level. The
state/parameter split, explicit units, named local variables, and small physics
modules give this project a good teaching foundation. The frontend also has
recognizable boundaries between transport, state, chart transformations, and
rendering.

The main educational weakness is **documentation drift**. There is plenty of
documentation, but some of it describes previous implementations, unavailable
design documents, or physical behavior that the model does not implement. A
learner currently has to decide which explanation to trust. The first fixes
should make the existing teaching path reliable; a broad rewrite or a much
larger abstraction framework would have less value.

Priorities below use P2 for a concrete issue worth fixing in the next cleanup,
and P3 for a smaller documentation or navigation improvement. None of these
findings asks for higher model fidelity merely for its own sake.

## Prioritized findings

### R1 — P2: The engine tutorial and diagnostic example no longer build a plant

**Locations:** `DEVELOPMENT.md:334`, `DEVELOPMENT.md:355`,
`examples/dump_state.py:52`, `src/fission_sim/physics/primary_loop.py:236`.

The main engine tutorial and `dump_state.py` wire only `power_thermal` and
`Q_sg` into `PrimaryLoop`. Its current required ports also include
`m_dot_spray` and `P_primary`. Both examples therefore fail during
`finalize()`, before the reader sees a simulation. The tutorial also omits
the component imports, but supplying them does not resolve the wiring error.

**Verified:** running `.venv/bin/python examples/dump_state.py` exits with:

```text
EngineWiringError: module 'loop' input 'm_dot_spray' was not connected
```

Executing the API code block from `DEVELOPMENT.md`, with all component imports
supplied, produces the same exception. `P_primary` would be the next missing
input. Other examples, such as `run_primary.py`, already wire both correctly.
Even after rewiring, `dump_state.py:68` iterates only `core`, `loop`, `rod`,
`sg`, and `sink`, so the advertised full-state dump would still omit the
pressurizer and its controller.

**Impact:** the developer guide's main introduction to the graph API is broken,
and the advertised full-state diagnostic is unusable. This is also concrete
evidence that duplicated plant assembly has drifted.

**Recommendation:** update both to the current plant topology, including
complete imports. A clearly labeled fixed-pressure demonstration could instead
wire explicit constant pressure and zero spray. Keep one complete assembly
example visible for teaching; have other runners use a shared standard-plant
builder if the craft review adopts that change. One smoke check that builds
the documented example would catch this regression without repeating physics
tests.

### R2 — P2: Teaching text assigns the wrong meaning to several model outputs

**Locations:** `web/src/types/telemetry.ts:35`,
`web/src/types/telemetry.ts:107`, `web/src/widgets/tooltips.ts:136`,
`web/src/controls/ControlPanel.tsx:228`.

These are concrete contradictions with the implementation, rather than style
preferences:

| Teaching text | Implemented meaning and evidence |
|---|---|
| `Frame.T_fuel` is documented as fuel centerline temperature. | It is a single average fuel temperature; `core.py:399`–`402` explicitly says the model loses the radial gradient. Other frontend text correctly calls it bulk or average temperature. |
| Rod command `1` is documented as full power. | It means fully withdrawn. The design full-power position is `0.5`; `rod_controller.py:132` and the initial plant state establish this. Rod position is an input to reactivity, not a direct normalized power target. |
| SCRAM status tooltip says the power tail comes from decay heat. | `core.py:403` computes power only as `n * P_design`; the precursor terms feed neutron kinetics. Decay heat is still future work in `README.md:1217`. |
| The SCRAM dialog (`ControlPanel.tsx:228`), the SCRAM button tip (`:323`), and the command doc (`telemetry.ts:111`) say rods reach full insertion immediately. | SCRAM changes the target immediately; physical rod position remains an ODE state with finite motion (`rod_controller.py:291`–`313`). |
| The rod slider help says the typical full-stroke time is ~30 s (`ControlPanel.tsx:278`). | `v_normal = 0.01 /s` (`rod_controller.py:106`) gives 100 s; `README.md:909` and `DEVELOPMENT.md:189` say 1 %/s. |
| The rod-command tile is described as a fraction `[0..1]` (`tooltips.ts:100`) but carries `units: '%'` and renders as percent (`StatusPanel.tsx:206`). | Pick one unit for the tile, the slider, and the Python port. |
| Tooltips give "normal" hot/cold/average temperatures of ~600/~565/~582 K and call the plant "AP1000 class" (`tooltips.ts:9`–`10`); `README.md:928` says ~596/~564 K. | Derived references are 597.7/568.3/583.0 K, and every parameter comment calibrates to a Westinghouse 4-loop plant (`primary_loop.py:94`–`96`). |

**Impact:** users learn incorrect distinctions between a model state, a control
command, and a real-plant quantity. In particular, the SCRAM explanation makes
an omitted physical mechanism appear implemented. The lower fidelity itself
is not the problem.

**Recommendation:** use the same model-specific descriptions in the TypeScript
interface, tooltip copy, README, and Python ports. State that `T_fuel` is
lumped average temperature, rod command is fraction withdrawn, and displayed
power is modeled fission power. Say that SCRAM immediately commands rapid
insertion and that decay heat is omitted.

The accuracy reviewer was also notified of two related physical explanations:
the Doppler tooltip says neutrons “slow more easily”
(`web/src/widgets/tooltips.ts:72`), and the SCRAM docstring says precursors
“continue fissioning” and keep the reactor from becoming subcritical
(`src/fission_sim/api/runtime.py:605`). The exact physical corrections and
external-source verification belong in the accuracy review. They should not
be treated as a request for additional physics features.

### R3 — P2: The introductory core examples start with an unadvertised transient

**Locations:** `examples/run_core.py:8`, `examples/run_core.py:43`,
`examples/report_core.py:32`, `examples/report_core.py:125`,
`src/fission_sim/physics/core.py:173`.

Both standalone core drivers claim that the first ten seconds are steady
state at design power. They supply a constant coolant temperature of 580 K,
while the current core reference temperature is 583 K. With the default
initial state this immediately introduces +15 pcm of moderator reactivity and
a nonzero fuel-temperature derivative.

**Verified:** evaluating the default core with these example inputs gives
`dn/dt = 3.75 /s` and `dT_fuel/dt = -0.58027079 K/s` at time zero. A five-second
BDF integration using the same inputs gives `n = 1.01710006`, before the
advertised rod step at ten seconds. `report_core.py:183` then prints
"Steady state holds at n = 1.0 with derivatives = 0 by construction", which
the run it summarizes contradicts.

Both drivers also carry stale scaffolding. `run_core.py:3` calls itself a
"throwaway script" while `README.md:75` lists it as an entry point, and
`run_core.py:46`–`48` and `report_core.py:33` say the constant-coolant
helper disappears "when the primary loop component arrives", which it did
several milestones ago.

**Impact:** the simplest learning example teaches readers to expect a steady
baseline, then shows an unexplained power excursion. A learner could attribute
it to the solver or misunderstand how the reference temperatures work.

**Recommendation:** derive the example's fixed coolant input from
`params.T_cool_ref`. If an initial coolant step is intentional, name it in the
scenario and explain it. The current narrative clearly favors a steady
baseline. An initial-derivative check is enough to verify the correction; a
second long transient test is unnecessary.

### R4 — P2: The component extension contract hides a critical output rule

**Locations:** `DEVELOPMENT.md:308`–`324`,
`src/fission_sim/engine/engine.py:384`–`403`,
`src/fission_sim/engine/engine.py:542`–`560`.

The developer guide presents a uniform `outputs(state, inputs=None)` method
and says algebraic components use inputs. It does not explain the rule that
actually determines graph evaluation: the engine calls `outputs(state)` and
classifies any successful call as state-derived; a `TypeError` means computed.
State-derived outputs are subsequently evaluated without inputs.

This is a significant hidden requirement for a newcomer implementing a new
component. An output method that returns a harmless default when `inputs` is
omitted can appear to satisfy the documented API while causing the engine to
ignore that output's actual input dependencies. The existing steam generator
explicitly raises `TypeError`; the pressure controller makes inputs required.
Their implementation demonstrates the rule, but the extension guide does not.
The guide's claim at `DEVELOPMENT.md:310`–`316` that every component exposes
the same `outputs(state, inputs=None)` surface is also false:
`PressurizerController.outputs` takes a keyword-only required `inputs`
(`pressurizer_controller.py:141`). Because classification is by exception, an
incidental `TypeError` inside a state-derived `outputs()` silently
reclassifies the module as computed and only fails at the first snapshot;
craft C8 covers that mechanism.

**Recommendation:** document the invariant: calling `outputs(state)` must
succeed only when every wired output depends solely on state or fixed
parameters. Add short examples of state-derived, computed, and telemetry-only
quantities, and explain that derivative dependencies do not create an
algebraic cycle. List `input_ports` and `output_ports` with `state_size` and
`state_labels` in the component contract. If craft work replaces exception
probing with explicit metadata, document that final contract instead.

This overlaps the craft review's engine-interface assessment and should be
counted once in the consolidated remediation plan.

### R5 — P2: Central teaching explanations are unavailable through keyboard focus

**Locations:** `web/src/widgets/StatusTile.tsx:111`,
`web/src/widgets/StatusTile.tsx:121`,
`web/src/widgets/StatusTile.tsx:164`–`174`,
`web/src/controls/ControlPanel.tsx:82`–`110`.

Status explanations are only revealed with `group-hover:opacity-100`. The
tile is a non-focusable `div`; its information icon is a `span`. There is no
focus behavior, explicit disclosure control, or `aria-describedby` connection.
The control tooltip wrapper uses the same hover-only pattern, even though its
buttons and slider can receive keyboard focus. The comment at
`StatusTile.tsx:36`–`37` says the icon is aria-hidden "because the tooltip
text is the accessible description", but no `aria-describedby` exists, so
the comment asserts a link that is not there.

**Impact:** a sighted keyboard user can operate the simulator but cannot reveal
the educational explanations by focusing the controls. Touch access is also
dependent on browser hover emulation. Since these explanations carry much of
the teaching content, this is a practical educational-access issue.

**Recommendation:** give the information icon a labeled focusable control,
show help on focus as well as hover, and associate it with the relevant
control or value. A small click/tap disclosure also provides dependable touch
access. Verify one status explanation and one operator explanation using
keyboard-only interaction; no visual redesign is necessary.

**Limit:** this finding is based on the JSX/CSS behavior. No browser or screen
reader interaction was performed during this review, so no claim is made
about a particular screen reader's reading order.

### R6 — P3: The navigation path points readers to missing documents

**Locations:** `README.md:13`, `README.md:143`, `README.md:1200`,
`DEVELOPMENT.md:284`, `src/fission_sim/engine/engine.py:8`,
`src/fission_sim/physics/pressurizer.py:25`,
`web/src/layout/AppShell.tsx:149`–`154`.

The README sends readers to `.docs/design.md` for the original architecture,
physics specification, and roadmap. Multiple modules instead reference
`docs/superpowers/specs/...`. Neither directory nor the cited documents exists
in this checkout or the tracked tree. The dashboard's `README` link points to
`/`, which reloads the dashboard rather than opening documentation.

**Impact:** readers trying to verify rationale or understand milestone and
fidelity terminology encounter dead ends. The physics sections still contain
useful explanations and public references, so this is not a total absence of
documentation.

**Recommendation:** restore the intended public design documents or replace
references with current README/DEVELOPMENT sections. Point the dashboard link
at an actual documentation destination. Avoid references to unavailable
private planning material as if it were required reading.

### R7 — P3: Contradictory comments obscure current behavior and parameter meaning

**Locations and examples:**

| Location | Contradiction | Proportionate correction |
|---|---|---|
| `primary_loop.py:254` | Initial liquid inventory is said to equal `M_hot + M_cold`. The implementation uses `M_loop_initial`, derived separately from volume and density. At defaults these are 30,000 kg and approximately 123,393 kg respectively. | Describe physical inventory separately from effective thermal inertia, consistently with the parameter comments at lines 104–109. |
| `README.md:249`–`250` and `primary_loop.py:6` | The primary loop is introduced as constant pressure, but current `P_primary` is supplied by the dynamic pressurizer and affects surge density. | Say that the thermal balances use fixed flow/heat capacity while the coupled plant obtains pressure from the pressurizer. |
| `runtime.py:714`–`716` and `runtime.py:790` | Command dispatch says reset preserves the last rod command; the reset command immediately assigns `0.5` at line 795. | Distinguish direct `reset()` behavior from the WebSocket `reset` command, or align them if desired. |
| `ControlPanel.tsx:373` | Pause help says telemetry keeps streaming. Current runtime publishes a transition frame and then suppresses frames while paused (`runtime.py:404`–`408`). | Match the chosen runtime contract after the craft review's paused-command findings are resolved. |
| `examples/power_maneuver.py:13`–`17` | The introduction says heaters and spray operate during the default maneuver, while the printed explanation at lines 195–207 says the response stays inside the deadband and the controller is idle. Line 207 also points to a `load_reduction.py` demo that does not exist. | Make the introductory scenario agree with the demonstrated run; do not promise a controller exercise this scenario does not show. |
| `DEVELOPMENT.md:391`–`398` | The snapshot example shows `"sg": {}` and `"sink": {}` and omits `pzr`/`pzr_ctrl`, while the text says each key holds that module's `telemetry()` dict. | Regenerate the example from a real snapshot: `sg` has four keys, `sink` one, `core` fourteen, and both pressurizer modules are present. |
| `README.md:69`–`75`, `DEVELOPMENT.md:51`–`58`, `:432` | The example tables omit `report_core.py` and `dump_state.py`; the "all runners" sentence names the broken `dump_state.py` and omits `power_maneuver.py` and `console.py`. | Keep one authoritative example list and link to it from the other. |
| `src/fission_sim/api/app.py:147`–`149` | Describes a fallback for a `handle_command` method "added in feat-004" that already exists. | Delete the guard and the comment. |

There is also low-impact history left in active API explanations: “the
simulation engine eventually” in several physics classes, placeholder-only
layout descriptions in `AppShell.tsx:196`, and “We recompute” above simple
telemetry reads in `runtime.py:211`. These need a targeted cleanup, not extra
layers of commentary.

### R8 — P3: Learner-facing comments use undefined planning vocabulary and stale "not yet" claims

**Locations (sample):** `README.md:360`, `src/fission_sim/api/runtime.py:23`,
`:689`, `src/fission_sim/api/app.py:149`, `web/src/layout/AppShell.tsx:9`–`11`,
`:196`–`197`, `web/src/charts/ChartGrid.tsx:10`–`11`,
`web/src/widgets/StatusTile.tsx:158`, `src/fission_sim/physics/secondary_sink.py:4`,
`src/fission_sim/physics/primary_loop.py:230`–`231`,
`examples/report_primary.py:240`–`241`.

Comments refer to M1/M2/M3/M5/M6, L1/L2, feat-004/009/010/011, DEF-01/02,
A-07, and "Task A1". None of these is defined in the tracked tree; the only
document that would define them is the missing `.docs/design.md` (R6).
Several also describe work as pending that has landed: `app.py:149` guards
a method "added in feat-004" that exists; `ChartGrid.tsx:10`–`11` says it will
"replace the feat-009 placeholder" that it already replaced;
`secondary_sink.py:4` says "M3 will replace this"; `primary_loop.py:230`–`231`
says a check "becomes M1 success criterion #4 once the loop is coupled",
which it is.

**Impact:** a newcomer cannot tell which comments describe the present code
and which describe an unrecorded plan. Once R6 is addressed this is the
largest remaining barrier to reading the comments in context.

**Recommendation:** either add a short glossary to DEVELOPMENT.md (what an
L1 component is, what each milestone delivered), or purge the labels and
replace "will" statements with what the code does now. Delete the guards and
placeholders for work that has landed.

## What to retain

- **Physics equations are easy to locate and compare with code.**
  `core.py:345`–`411`, `primary_loop.py:317`–`381`, and
  `pressurizer_controller.py:148`–`213` map equations to named terms and attach
  units to inputs. Short symbols such as `rho`, `n`, and `Q_sg` are appropriate
  here because they match established notation and are explained.
- **Ownership is largely clear.** Params objects hold configuration;
  components provide pure evaluations; `SimEngine` owns evolving state. The
  explanation of speculative solver evaluations in `core.py:324` is useful
  and should remain.
- **The physical/code boundary is visible.** The SG and secondary-sink
  documentation explicitly explains their algebraic and fixed-reservoir
  approximations. The pressurizer's output documentation explains why pressure
  can be computed before controller demand (`pressurizer.py:456`).
- **The frontend modules have understandable roles.** `App.tsx` owns the
  connection lifecycle; `wsClient.ts` handles transport; `telemetryStore.ts`
  holds current/history state; `chartData.ts` converts units; charts and tiles
  render. Keeping those boundaries helps a reader trace a value end to end.
- **The examples span useful levels.** A standalone core, a coupled plant,
  text reports, and an interactive console form a sensible learning path once
  the broken and misleading examples are corrected.
- **Many tests read as demonstrations.** The core derivative tests name a
  physical condition and show its expected response. The finite-value frame
  tests and history-reset tests explain frontend boundary behavior clearly.

## Optional organization improvements

These are not additional defects:

1. Add a short reading order near the top of the README: mental model → one
   component and its derivative test → runnable plant assembly → engine
   evaluation → runtime/frame → browser store/chart. Include one current
   wiring diagram showing which arrows carry heat, temperatures, pressure,
   and actuator demands.
2. The 1,218-line README repeats equations in its component guide and later
   equation catalog. Keep a concise entry page and link to a canonical model
   guide, or add navigation within the current document. Either approach is
   reasonable; shortening documentation alone is not a goal.
3. Prefer comments that explain units, assumptions, solver behavior, and
   non-obvious constraints. Repeated constructor prose, heading banners, and
   restatements of straightforward JSX can be shortened when touched. Do not
   remove derivations or the distinction between outputs and telemetry.
4. Keep one clear standard plant assembly outside the API layer if it is
   shared. Requiring CLI examples to import an underscored API helper would
   make the architecture harder to teach. One deliberately expanded wiring
   tutorial can remain even with a reusable builder.
5. Define or purge the milestone vocabulary (R8) before adding any reading
   order; a reading order would otherwise inherit the same undefined terms.

The engine and runtime are long files, but their current sections and method
names are navigable. File length alone does not justify splitting them into
many small modules. Fixing the behavioral contracts would help readers more.

## Scope and verification limits

Reviewed README, DEVELOPMENT, the plan, all physics/control modules, the
engine, API/runtime, all example drivers, frontend types/state/transport,
charts, widgets, controls, and layout. Sampled Python physics/plant/runtime
tests and frontend frame/store/browser tests for their value as executable
documentation. Inspected Makefile and package configuration for the described
workflow.

Targeted executions were limited to the broken state-dump example, the
developer-guide engine snippet with imports supplied, default loop inventory,
and the standalone core's initial derivative/five-second trajectory. The main
reviewer owns the full test/build results and physics-source verification.
No implementation files were changed. Physical claims in inherited agent
documents were not used as authority. Public references listed in the source
were inspected as documentation pointers, but this readability pass did not
independently validate their contents.
