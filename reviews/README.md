# Repository review: accuracy, readability, and craft

Date: 2026-09-26. Baseline: `5dc6e641ef7807e323a5b9c90637696a60ad07e4`.
Branch: `review/accuracy-readability-craft`.

## Overall assessment

**The architecture is a good foundation for an educational simulator, but the
coupled thermal model and several teaching explanations need correction before
its transient results can be trusted.** The most significant error is that
heat leaving the modeled fuel never becomes the primary loop's heat input.
The loop instead receives instantaneous fission power, bypassing fuel storage.
Two calibration choices compound it: the operator's rod command carries the
full shutdown-bank worth, and the loop's thermal inertia is smaller than the
fuel's. Together they let a 10 % rod move reach prompt criticality and boil
the hot leg within seconds.

| Perspective | Assessment |
|---|---|
| Accuracy | Standard point kinetics, simple feedback, an algebraic SG, and a lumped pressurizer are reasonable choices. The fuel/loop heat interface is inconsistent, the thermal-inertia interpretation needs reconciliation, the operator's rod command carries shutdown-bank worth, and physical-domain limits are not handled clearly. |
| Readability | Equations, units, state ownership, and frontend boundaries are generally clear. Documentation drift undermines the learning path: the main engine tutorial fails, several references are missing, and some explanations teach the wrong mechanism. |
| Craft | The separation of physics, engine, runtime, and browser is sound. The most actionable defects concern lifecycle ownership, paused telemetry, a test-harness incompatibility that leaves the API suite red, the engine's exception-based output classification, and graph validation. |

This was a three-reviewer effort. The primary reviewer handled physics and
synthesis; separate agents handled readability and craft. The [plan](PLAN.md)
was recorded before delegation. A second pass on 2026-09-26 independently
re-verified every finding against the source; what it changed is recorded in
[Second-pass audit](#second-pass-audit) below. All deliverables are on this
branch. Implementation files remain unchanged so the findings refer to one
baseline.

## Findings to address first

Priorities: **P1** = central result materially wrong; **P2** = concrete behavior
or teaching issue worth fixing soon; **P3** = narrower defect or improvement.
Identifiers refer to the detailed reports below.

| Priority | Finding | Evidence and consequence | Details |
|---|---|---|---|
| P1 | Fuel heat transfer is disconnected from coolant heating | With fission at 300 MW and hot fuel still releasing 3,000 MW, fuel plus loop lose 5,400 MW against an external deficit of 2,700 MW. This distorts cooldown, feedback, surge, and pressure. | Accuracy A1 |
| P2 | Accepted rod commands reach unsupported coolant states | `rod_command=0.6` fails at the saturation boundary in the next step after `t=4.6 s`; the UI receives an unexplained pause. With physically consistent loop mass the same command raises nothing and runs superheated with vapor density in the surge calculation. | Accuracy A2 |
| P2 | Operator rod command carries the full 14,000 pcm bank worth | A 0.5→0.6 command is +1,400 pcm (2.15 $); prompt critical is reached at position 0.546. Root cause of the A2 excursion. | Accuracy A8 |
| P2 | Loop inertia contradicts the stated inventory model | The configured water-plus-metal equivalent is 30,000 kg, versus 123,393 kg of represented water alone. Explain or reconcile the resulting response time. | Accuracy A3 |
| P2 | SCRAM and feedback explanations are misleading | The two-second full-insertion claim disagrees with the actuator; displayed power omits decay heat; Doppler and soluble-boron explanations contain errors. | Accuracy A4–A5; readability R2 |
| P2 | Concurrent resets create duplicate simulation loops | Two simultaneous resets leave two live integration tasks; stopping the runtime leaves one alive. | Craft C1 |
| P2 | Paused clients have stale or absent state | A paused SCRAM is acknowledged but displayed as inactive; a new paused subscriber receives no initial frame. | Craft C2 |
| P2 | API tests fail at `TestClient` teardown on CPython 3.13 and later | Nine tests fail on 3.13 and 3.14 and pass on 3.11 and 3.12; a real server tears down cleanly. A harness incompatibility, not a user-visible defect, but the suite is red in the project's own venv and it hides the only command-validation coverage. | Craft C3 |
| P2 | Educational entry points are broken or misleading | The engine tutorial and `dump_state.py` omit required loop inputs. Standalone core demos drift before their advertised initial event. | Readability R1, R3 |

The detailed reviews also cover inaccessible hover-only help, missing component
protocol rules, the engine's exception-based output classification, graph
self-cycles/foreign signals/name collisions, reserved snapshot names,
malformed-message handling, runtime lock claims that the code does not honor,
orphaned developer-server descendants, ineffective test timeouts, undefined
milestone vocabulary in learner-facing comments, wrong numbers in parameter
comments, and smaller frontend/documentation issues. These have narrower
impact than the heat coupling error; each report gives evidence and a
proportionate recommendation.

## Detailed reviews

- [Accuracy](accuracy.md): equations, component coupling, numerical probes,
  authoritative sources, acceptable simplifications, and unresolved modeling
  limits.
- [Readability](readability.md): educational semantics, runnable examples,
  component contracts, navigation, accessibility, and documentation drift.
- [Craft](craft.md): lifecycle defects, engine/API/frontend contracts, process
  cleanup, DRY opportunities, and test quality.
- [Reproduction script](reproduce.py): isolated balances, rod motion, property
  values, paused telemetry, concurrent resets, and optional full transients.

The same teaching-text and component-contract issues appear from multiple
perspectives. They should be fixed once; report identifiers are not an additive
count of independent defects.

## Verification

Dependencies were installed from the existing lockfiles without changing them.
Environment: macOS arm64, Python 3.14.0, Node 26.9.0, npm 11.19.1;
CoolProp 7.2.0, SciPy 1.17.1, FastAPI 0.136.1, Starlette 1.0.0.

| Check | Result |
|---|---|
| `.venv/bin/pytest -q` | **197 passed, 9 failed, 1 skipped**, 30.27 s |
| `.venv/bin/ruff check src tests` | Passed |
| `npm run test --prefix web -- --run` | **20 passed** across 3 files |
| `npm run lint --prefix web` | Passed |
| `npm run typecheck --prefix web` | Passed |
| `npm run build --prefix web` | Passed |
| Existing Playwright SCRAM smoke test | **1 passed**, 8.1 s, against real local backend and frontend |
| `.venv/bin/ruff check reviews/reproduce.py` | Passed |
| `.venv/bin/python reviews/reproduce.py --transients` | Reproduced the documented balances, timing, phase failure, and lifecycle defects |

The nine Python failures were six tests in `tests/api/test_commands.py` and
three in `tests/api/test_websocket.py`. They raised `CancelledError` during
WebSocket context teardown (including the threaded case). Craft C3 documents
the reproduction: the second pass established that the failure is a
`TestClient` interaction with CPython 3.13's task-group cancellation change,
that it does not occur on 3.11 or 3.12, and that a real uvicorn server on
3.14 tears down cleanly.

The skipped test is `test_engine_run_matches_legacy_solve_ivp`; its handwritten
M1 plant no longer matches the M2 topology. It currently provides no independent
solver comparison. Preserve equivalent independent coverage when retiring or
repairing the stale fixture.

Non-failing tool output included frontend dependency deprecation notices,
Vitest/Vite transform-option warnings, and a 557 kB minified bundle warning.
Those were not treated as proven application defects.

For the smoke check, the pinned Chromium shell was installed in
`/private/tmp/fission-review-browsers`; local review servers were stopped
afterward. The command was:

```sh
PLAYWRIGHT_BROWSERS_PATH=/private/tmp/fission-review-browsers npm run e2e --prefix web
```

Focused probes can be rerun without starting servers:

```sh
.venv/bin/python reviews/reproduce.py
.venv/bin/python reviews/reproduce.py --transients
```

## Recommended implementation sequence

1. **Correct the heat interface, thermal inertia, and rod worth together.**
   Separate fission power from heat transferred to coolant; use the latter
   consistently for loop heating and surge. Decide what coolant inventory the
   temperature states represent and size the thermal masses to it. Give the
   operator's command a control-bank worth rather than the shutdown worth.
   Add an energy-balance check during an actual transient. Fixing A1 alone
   leaves the loop about four times too fast; fixing A3 alone turns the A2
   crash into a silent superheated run.
2. **Make the supported domain visible.** Stop coherently when the liquid-loop
   or saturated-pressurizer assumptions fail, retain the last valid state, and
   publish an explanation. This is required even after step 1, because the
   silent branch of A2 is reachable. Adding more physics is optional.
3. **Repair runtime ownership and publication.** Serialize reset/start/stop,
   seed subscriptions (and adjust the one pause test that assumes no seed),
   publish accepted command-state changes while paused, and move the WebSocket
   endpoint to framework-compatible task-group ownership. Send an error frame
   for malformed messages instead of dropping the socket, and make the lock
   and step-loop failure handling match their docstrings. Use a small number
   of lifecycle regression tests.
4. **Repair the learning path.** Correct the explanations, reference
   temperatures, timing claims, tutorial wiring, and missing links. Make
   educational help reachable with keyboard focus. Document the component
   output-dependency contract explicitly.
5. **Consolidate demonstrated duplication.** Put the standard plant factory
   outside the API layer and reuse it in operational examples/runtime. Keep
   one expanded wiring tutorial and independent test oracles. Consolidate
   duplicated engine output evaluation when touching that code.
6. **Finish bounded craft fixes.** Store the output classification at
   finalize instead of re-probing by exception, reject invalid graph
   references/reserved names/name collisions, retain developer process-group
   IDs, and make test receive timeouts real. Treat chart-window, chart
   decimation, error-display, and focus improvements as smaller work.

## Test scope: improve the assertions before increasing the count

The suite is substantial and mostly useful. The weakness is coverage of
interfaces and lifecycle combinations, plus a few claims the assertions do
not establish. The “transient” energy test checks a settled plateau; the
“two-second” SCRAM test checks four seconds; the runtime reset test asserts
`t < 1.0` after half a second and passes with the reset removed; the
command tests treat the acknowledgement as the first telemetry frame.
Replace weak checks with ones that distinguish correct and incorrect
behavior. Command validation deserves a direct unit test so its coverage
does not depend on the WebSocket harness.

Keep component sign/equilibrium checks, real transient tests, mass conservation,
history/reset behavior, malformed telemetry handling, and the browser smoke
test. Add focused cases for the identified defects. There is no demonstrated
need for broad UI snapshots, exhaustive parameter combinations, a new framework,
or a large generic fixture hierarchy.

## Second-pass audit

On 2026-09-26 a second reviewer re-ran every probe, re-read every cited
location, and dispatched four independent checks (physics, readability,
runtime/API, engine/frontend). Every quoted passage and every number in the
original reports held. The following was changed as a result:

| Change | Where |
|---|---|
| A1 now states the ~5 s fuel time constant over which it acts and that A1 and A3 compound. | Accuracy A1 |
| A2 now documents the silent branch: with physically consistent loop mass the same command boils the hot leg with no error and feeds vapor density to surge. | Accuracy A2 |
| A7 reframed: the surge helper is exact for the mass-weighted mean; the defect is the comment and the mismatch with the published arithmetic `T_avg`. Its recommendation was reversed accordingly. | Accuracy A7 |
| New: rod worth (A8, root cause of A2), inverted fuel/loop time-constant ordering (A9), wrong numbers in parameter comments including the moderator-coefficient range (A10). | Accuracy A8–A10 |
| A4 and A6 gained a second wrong statement each from the same comment blocks. | Accuracy A4, A6 |
| New: undefined milestone vocabulary and stale "not yet" claims in learner-facing comments (R8). Additional rows in R2 (rod stroke time, units, three sets of design temperatures), R3 (a printed "steady by construction" claim), R4, R5, and R7. | Readability |
| C3 reframed from a possible teardown defect to a `TestClient`/CPython 3.13+ harness incompatibility, with the version dependence and real-server behavior established. | Craft C3 |
| C1 now states its one-event-loop-turn trigger window; C2 now notes the existing test that seeding would break; C6 downgraded to P3 by the report's own convention. | Craft C1, C2, C6 |
| New: exception-based output classification re-probed on every evaluation (C8), malformed messages dropping the socket without a close frame (C9), runtime lock and silent step-loop failure (C10). A third C4 case, a chart decimation artifact, dead store code, and a vacuous reset test were added. | Craft |
| Probes for A8, A9, and the second A2 branch were added to `reproduce.py`. | Reproduction script |
| Line references corrected in eight places. | All reports |

Not re-verified in the second pass: the Playwright smoke test and the two
external citations that answer `403` to non-browser clients (the control-volume
text and the NRC page). Everything else in the verification table above was
re-run with matching results.

## Review limits

This is a code and model review supported by direct experiments, not validation
against operating-plant data. Exact plant constants and every inherited textbook
citation were not independently certified. Physical-source access limits are
recorded in the accuracy report. Browser accessibility observations are based
on source; the existing browser test exercises reset/SCRAM, not a full keyboard
or screen-reader audit. Only the environment above was tested.
