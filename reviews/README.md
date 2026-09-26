# Repository review: accuracy, readability, and craft

Date: 2026-09-26. Baseline: `5dc6e641ef7807e323a5b9c90637696a60ad07e4`.
Branch: `review/accuracy-readability-craft`.

## Overall assessment

**The architecture is a good foundation for an educational simulator, but the
coupled thermal model and several teaching explanations need correction before
its transient results can be trusted.** The most significant error is that
heat leaving the modeled fuel never becomes the primary loop's heat input.
The loop instead receives instantaneous fission power, bypassing fuel storage.

| Perspective | Assessment |
|---|---|
| Accuracy | Standard point kinetics, simple feedback, an algebraic SG, and a lumped pressurizer are reasonable choices. The fuel/loop heat interface is inconsistent, the thermal-inertia interpretation needs reconciliation, and physical-domain limits are not handled clearly. |
| Readability | Equations, units, state ownership, and frontend boundaries are generally clear. Documentation drift undermines the learning path: the main engine tutorial fails, several references are missing, and some explanations teach the wrong mechanism. |
| Craft | The separation of physics, engine, runtime, and browser is sound. The most actionable defects concern lifecycle ownership, paused telemetry, WebSocket cleanup, graph validation, and developer process cleanup. |

This was a three-reviewer effort. The primary reviewer handled physics and
synthesis; separate agents handled readability and craft. The [plan](PLAN.md)
was recorded before delegation. All deliverables are on this branch.
Implementation files remain unchanged so the findings refer to one baseline.

## Findings to address first

Priorities: **P1** = central result materially wrong; **P2** = concrete behavior
or teaching issue worth fixing soon; **P3** = narrower defect or improvement.
Identifiers refer to the detailed reports below.

| Priority | Finding | Evidence and consequence | Details |
|---|---|---|---|
| P1 | Fuel heat transfer is disconnected from coolant heating | With fission at 300 MW and hot fuel still releasing 3,000 MW, fuel plus loop lose 5,400 MW against an external deficit of 2,700 MW. This distorts cooldown, feedback, surge, and pressure. | Accuracy A1 |
| P2 | Accepted rod commands reach unsupported coolant states | `rod_command=0.6` fails at the saturation boundary in the next step after `t=4.6 s`. The UI receives an unexplained pause. | Accuracy A2 |
| P2 | Loop inertia contradicts the stated inventory model | The configured water-plus-metal equivalent is 30,000 kg, versus 123,393 kg of represented water alone. Explain or reconcile the resulting response time. | Accuracy A3 |
| P2 | SCRAM and feedback explanations are misleading | The two-second full-insertion claim disagrees with the actuator; displayed power omits decay heat; Doppler and soluble-boron explanations contain errors. | Accuracy A4–A5; readability R2 |
| P2 | Concurrent resets create duplicate simulation loops | Two simultaneous resets leave two live integration tasks; stopping the runtime leaves one alive. | Craft C1 |
| P2 | Paused clients have stale or absent state | A paused SCRAM is acknowledged but displayed as inactive; a new paused subscriber receives no initial frame. | Craft C2 |
| P2 | WebSocket cleanup fails in the tested supported environment | Nine Python tests fail at context exit under Python 3.14. A focused task-group substitution isolated the cancellation interaction. | Craft C3 |
| P2 | Educational entry points are broken or misleading | The engine tutorial and `dump_state.py` omit required loop inputs. Standalone core demos drift before their advertised initial event. | Readability R1, R3 |

The detailed reviews also cover inaccessible hover-only help, missing component
protocol rules, graph self-cycles/foreign signals, reserved snapshot names,
orphaned developer-server descendants, ineffective test timeouts, and smaller
frontend/documentation issues. These have narrower impact than the heat
coupling error; each report gives evidence and a proportionate recommendation.

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
the focused reproduction and limits; the successful real-browser smoke test
does not establish that this test-client cancellation behavior is harmless.

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

1. **Correct the heat interface and thermal interpretation.** Separate
   fission power from heat transferred to coolant; use the latter consistently
   for loop heating and surge. Decide what coolant inventory the temperature
   states represent. Add an energy-balance check during an actual transient.
2. **Make the supported domain visible.** Stop coherently when the liquid-loop
   or saturated-pressurizer assumptions fail, retain the last valid state, and
   publish an explanation. Adding more physics is optional.
3. **Repair runtime ownership and publication.** Serialize reset/start/stop,
   seed subscriptions, publish accepted command-state changes while paused,
   and fix framework-compatible WebSocket cancellation. Use a small number of
   lifecycle regression tests.
4. **Repair the learning path.** Correct the explanations, reference
   temperatures, timing claims, tutorial wiring, and missing links. Make
   educational help reachable with keyboard focus. Document the component
   output-dependency contract explicitly.
5. **Consolidate demonstrated duplication.** Put the standard plant factory
   outside the API layer and reuse it in operational examples/runtime. Keep
   one expanded wiring tutorial and independent test oracles. Consolidate
   duplicated engine output evaluation when touching that code.
6. **Finish bounded craft fixes.** Reject invalid graph references/reserved
   names, retain developer process-group IDs, and make test receive timeouts
   real. Treat chart-window/error-display/focus improvements as smaller work.

## Test scope: improve the assertions before increasing the count

The suite is substantial and mostly useful. The weakness is coverage of
interfaces and lifecycle combinations, plus a few claims the assertions do
not establish. The “transient” energy test checks a settled plateau; the
“two-second” SCRAM test checks four seconds. Replace weak checks with ones
that distinguish correct and incorrect behavior.

Keep component sign/equilibrium checks, real transient tests, mass conservation,
history/reset behavior, malformed telemetry handling, and the browser smoke
test. Add focused cases for the identified defects. There is no demonstrated
need for broad UI snapshots, exhaustive parameter combinations, a new framework,
or a large generic fixture hierarchy.

## Review limits

This is a code and model review supported by direct experiments, not validation
against operating-plant data. Exact plant constants and every inherited textbook
citation were not independently certified. Physical-source access limits are
recorded in the accuracy report. Browser accessibility observations are based
on source; the existing browser test exercises reset/SCRAM, not a full keyboard
or screen-reader audit. Only the environment above was tested.
