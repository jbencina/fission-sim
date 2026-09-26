# Software craft review

Baseline: `5dc6e641ef7807e323a5b9c90637696a60ad07e4`.
Branch: `review/accuracy-readability-craft`.
Implementation was preserved during this review. Experiments used inline scripts,
temporary processes, or an in-memory copy of the application.

## Overall assessment

The main decomposition is sound: physics components are independent of HTTP and
React; the engine owns integration; the runtime owns commands and subscriptions;
the browser separates transport, state, chart transforms, and presentation.
There is useful test coverage of equations, graph behavior, commands, and chart
state. A framework rewrite or a much larger test suite would not improve this
project proportionately.

The clearest craft problems are in lifecycle behavior. Concurrent resets create
two integration tasks, paused clients cannot obtain fresh command state, and
WebSocket teardown fails with the locked dependencies on the tested Python
version. These are ordinary interactions that should work before expanding the
simulator. Smaller gaps affect graph diagnostics, developer process cleanup, and
test timeouts.

Severity convention: **P2** = functional defect worth fixing soon; **P3** =
bounded defect or maintenance improvement with a narrower trigger. No P0/P1
craft finding was established.

## Confirmed findings

### C1 — P2: Concurrent resets leave multiple integration tasks running

**Evidence:** `src/fission_sim/api/runtime.py:527-535`, `:549-559`, and
`:789-797`.

`reset()` checks whether a task exists, awaits `stop()`, rebuilds the engine, and
starts it again. The command lock does not cover that lifecycle. Two reset
requests can both wait for the old task. The first reset starts a new task; the
second `stop()` then sets the shared `_task` reference to `None`, losing the new
task, and starts another one. Both loops subsequently step the shared engine.

**Reproduction:** With a running `SimRuntime`, execute:

```python
await asyncio.gather(
    rt.handle_command({"type": "reset"}),
    rt.handle_command({"type": "reset"}),
)
```

There were two live tasks named `sim-step-loop` afterward. At cadence 10 Hz and
speed 1, the new simulation reached `t=0.8` after about 0.3 wall-clock seconds.
After `await rt.stop()`, one integration task remained alive. Two connected
clients can issue these requests concurrently.

**Impact:** Simulation speed depends on request timing, telemetry can be
published twice per cadence, and shutdown no longer stops all simulation work.

**Recommendation:** Serialize the entire reset/start/stop lifecycle with a
dedicated lifecycle lock and internal helpers. Cancel and await a locally held
task reference, and clear `_task` only if it still refers to that task. Preserve
one authoritative owner of the integration loop. Add one concurrency regression
that resets twice, checks there is one integration stream, and verifies complete
shutdown. Test the public lifecycle behavior as much as possible.

### C2 — P2: Paused clients receive no initial state or command updates

**Evidence:** `src/fission_sim/api/runtime.py:404-466`, `:649-676`;
`web/src/state/wsClient.ts:124-131`;
`web/src/controls/ControlPanel.tsx:145-150`, `:342-361`.

The runtime publishes after integration or a change in the `running` flag.
`subscribe()` adds an empty queue without sending the current state. Changes to
speed, rods, and the SCRAM latch do not publish while paused. The browser ignores
acknowledgements and derives controls from telemetry.

**Reproduction:** Start a runtime, subscribe, pause it, and consume the pause
frame. Add another subscriber, then send `set_speed=5` and `scram`. Both commands
returned acknowledgements. After four cadence periods:

```text
existing queued frames: 0
new subscriber queued frames: 0
snapshot: running=False, scrammed=False, speed=1.0
actual command state: scrammed=True, speed=5.0
```

**Impact:** Reloading or opening the page while paused leaves the connected UI
without telemetry until the simulator resumes. An existing paused UI fails to
show its accepted speed or SCRAM state; the Reset Scram control remains hidden.
The runtime's own `snapshot()` also returns stale command state.

**Recommendation:** Seed each subscription with an up-to-date state frame and
publish a state frame whenever an accepted command changes visible command
state, even if simulation time stays fixed. Keep the quiet paused loop; this
does not require continuous duplicate samples. Add focused coverage for joining
a paused runtime and changing its SCRAM/speed state without advancing time.
The existing pause tests should still enforce silence when nothing changes.

### C3 — P2: WebSocket teardown fails on the tested supported environment

**Evidence:** `src/fission_sim/api/app.py:204-215`;
`tests/api/test_websocket.py:66`.

On Python 3.14.0 with the repository lock's installed packages, normal
`TestClient` WebSocket context exit raises
`concurrent.futures.CancelledError`. This is separate from receiving frames or
command responses: a session can exchange valid data and then fail while
disconnecting. The main review's full run reported nine API failures with this
symptom.

**Reproduction:** The focused command

```sh
.venv/bin/python -m pytest tests/api/test_websocket.py::test_websocket_receives_at_least_5_frames -vv
```

failed during `WebSocketTestSession.__exit__`. A second experiment opened five
independent sessions and received three frames from each: all five baseline
sessions failed at exit. In an in-memory copy of `app.py`, replacing only
`asyncio.TaskGroup`/`create_task` with
`anyio.create_task_group`/`start_soon` produced zero failures in five sessions.

**Cause and limits:** This isolates cancellation interaction between the
endpoint's asyncio task group and Starlette TestClient's AnyIO cancellation
scope. The relevant local library paths are
`starlette/testclient.py:108-146` and
`asyncio/taskgroups.py:166-178`: disconnect and outside cancellation can overlap
while the group propagates an exception. This review did not establish that
real network clients suffer the same teardown exception, or that every
supported Python version does.

**Recommendation:** Use task-group/cancellation ownership compatible with the
ASGI framework, and rerun the existing API suite. If adopting AnyIO directly,
declare it as a direct dependency. Keep disconnect cleanup covered; swallowing
`CancelledError` broadly or relaxing the tests would hide lifecycle failures.

### C4 — P3: Graph finalization misses invalid references and a self-cycle

**Evidence:** `src/fission_sim/engine/engine.py:160-179`, `:295-364`,
`:410-416`, `:530-534`.

Finalization checks that required port names are present and local externals are
consumed. It does not establish that every supplied signal resolves to a real
producer in this engine. Its computed-module dependency graph explicitly skips
self-edges.

**Reproductions:**

1. Create `foreign = SimEngine().input("rate", default=9)`, wire it to a scalar
   integrator in a different engine, and finalize the second engine. Finalize
   succeeds; `snapshot()` raises `KeyError('rate')`.
2. For a computed component whose output `value` reads input `upstream`, wire
   `component(upstream=component.value)`. Finalize succeeds; `snapshot()` raises
   `KeyError('value')`. The equivalent two-component cycle is correctly rejected
   by existing tests.

**Impact:** A learner extending or wiring components receives a low-level error
after a supposedly successful validation step. Signals from another graph can
also alias local names rather than identifying the intended producer.

**Recommendation:** Validate each consumed external and producer port during
finalization, and retain self-dependencies for computed components. If foreign
handles must be rejected even when names coincide, give signals an engine
identity. Cover the two concrete cases with small graph tests. No general graph
framework is needed.

### C5 — P3: Valid module names can overwrite snapshot metadata

**Evidence:** `src/fission_sim/engine/engine.py:269-278`, `:591-596`.

The registration API accepts the names `t` and `signals`, although snapshots use
those keys for time and resolved signals. Module telemetry subsequently replaces
the metadata.

**Reproduction:** Register the existing scalar test component as `name="t"`,
wire its input, finalize, and call `snapshot()`:

```text
{'t': {'x': 0.0}, 'signals': {'rate': 1}}
```

Using `name="signals"` returns
`{'t': 0.0, 'signals': {'x': 0.0}}`, losing the actual signal dictionary.

**Impact:** An accepted graph produces a snapshot that violates its advertised
schema. The standard plant uses neither reserved name, so current UI operation
is unaffected.

**Recommendation:** Reject these two reserved names in `module()` with an
actionable `EngineWiringError`. One parameterized test is sufficient.

### C6 — P2: Developer cleanup misses descendants of an exited process leader

**Evidence:** `scripts/dev.py:88-103`, `:242`, `:278-298`.

The launcher correctly starts each server in a new process session and intends
to terminate its whole process group. Cleanup obtains the group ID by calling
`os.getpgid(proc.pid)` at cleanup time. If the immediate process already exited
and was reaped, that call raises `ProcessLookupError`, even when descendants in
the same group are still running. The process-exit polling path specifically
invokes cleanup after detecting this condition.

**Reproduction:** Launch a new-session Python process that starts a sleeping
child, prints that child's PID, and exits. Wait for the leader to exit, put its
`Popen` object in the launcher's `_children`, and call
`_terminate_children(timeout=0.1)`. The descendant was still alive afterward.
The review killed that owned process group after the check.

**Impact:** A wrapper or reloader failure can leave server descendants alive and
ports occupied after the launcher returns. The existing launcher test replaces
the cleanup function itself, so it cannot catch this.

**Recommendation:** Record each process group's identity when spawning it.
Because `start_new_session=True` is already used, the original PID is its group
ID. Signal the recorded group even after its leader exits, and handle
`ProcessLookupError` from the group signal. Add one focused cleanup regression
with an exited leader and a surviving descendant; avoid starting full servers
in the unit test.

### C7 — P3: WebSocket test deadlines do not bound blocking receives

**Evidence:** `tests/api/test_websocket.py:64-75`, `:125-143`;
`tests/api/test_commands.py:95-113`.

The collection helpers check wall-clock deadlines before `receive_text()`, but
that call can block indefinitely. If the simulation stops publishing while the
socket remains open, the next deadline check never runs. The three-second
thread joins in the multi-client test do not cancel blocked worker threads.

**Impact:** A regression in the exact behavior these tests cover can hang the
suite instead of producing a clear failure. This is established from the
blocking call structure; this review did not deliberately leave a hung test
process running.

**Recommendation:** Put a real timeout around receive operations, or use a
bounded async transport helper. A suite-level timeout is an additional last
resort. Keep one shared helper that selects telemetry versus acknowledgement
messages; `test_command_does_not_disconnect` currently accepts the immediate
ACK as proof that telemetry continues (`:99-106`).

## Smaller frontend observations

- **Chart time window changes with speed.** The store retains 600 frames
  (`web/src/state/telemetryStore.ts:104-109`), while chart transforms retain all
  those frames (`web/src/charts/chartData.ts:43-56`). At 10× and 10 Hz, those
  frames span 599 simulated seconds. `chartTheme.ts:34` specifies `[-60, 0]`,
  but the installed Recharts X axis defaults to `allowDataOverflow=false`, so it
  expands to the data. A direct transform plus the installed Recharts domain
  helper returned `[-599, 0]`. This conflicts with the chart comments promising
  the last 60 seconds; choose an explicit simulated-time window or document a
  speed-dependent history. One transform test with accelerated timestamps would
  cover a fixed-window decision. No rendered browser check was performed.
- **Errors are collected but never shown.** `wsClient.ts:119-120` forwards error
  envelopes to the store, but no rendered component subscribes to `lastError`.
  A rejected command has no visible explanation. A small dismissible status
  message would make the existing error pipeline useful; no new notification
  framework is necessary.
- **Modal focus is incomplete.** `ConfirmDialog.tsx:79-103` moves focus inside
  and handles Escape, but does not keep Tab within the modal or restore focus
  afterward. This is source inspection, not a keyboard browser test. The
  readability review separately covers hover-only educational tooltips.

## DRY and maintainability

The highest-value extraction is a shared standard-plant builder. The API has
`_build_engine`, and examples repeatedly assemble the same components and
wiring (`run_primary.py`, `report_primary.py`, `console.py`, and
`power_maneuver.py`). The readability review found an already-broken example
and tutorial after loop ports changed. That is concrete evidence of drift.
Keep one explicit wiring example for teaching; have operational examples and
the web runtime call a public factory with parameter overrides. Preserve
independent equation/integration oracles in tests rather than making every test
reuse the same implementation helper.

Two smaller opportunities are proportionate:

- `_resolve_signal_values()` and the output pass inside `_build_f()` duplicate
  graph evaluation (`engine.py:499-518`, `:672-687`). They currently agree. Use
  one implementation when changing graph behavior so snapshot and integration
  evaluation cannot diverge; measure only if this affects solver performance.
- Shared chart style and data-transform modules are already useful. The four
  chart components still repeat their outer layout, but remain short and easy
  to read. An elaborate generic chart specification would obscure this
  educational code. Likewise, independent toy graph setups in tests are often
  clearer than a large fixture factory.

The engine's use of `TypeError` as its computed-output protocol can also
misclassify an unrelated component bug. The readability review owns the missing
documentation for that contract. A future explicit component capability would
be clearer, but it is less urgent than fixing current lifecycle behavior.

## Tests: what to preserve and what to add

**Preserve:** steady-state and conservation checks, dense-output behavior,
command validation, chart updates after the
history reaches capacity, time rollback after reset, finite-value telemetry
guards, and the end-to-end SCRAM smoke test. These check different failure modes.
The smoke test already resets the persistent backend and establishes speed/run
state; it should remain a small integration check.

The engine-versus-direct-solver comparison (`tests/test_engine.py:1043`) is
currently skipped because its handwritten M1 plant is stale, so it provides no
protection. Re-enable an independent oracle using a small representative graph,
or remove the dead legacy scaffolding after retaining equivalent coverage.

**Add only around concrete risks:** concurrent reset/shutdown, paused
subscription and command visibility, invalid graph references/self-cycles,
reserved names, and process-group cleanup. A compact transport test with a fake
WebSocket could cover reconnection and permanent close without a browser.

There are a few trivial repeated tests, such as separate health status/body
checks and separate store setter values. They could be combined when touched,
but deleting them has little benefit. The important imbalance is extensive
happy-path coverage with missing lifecycle combinations, not an excessive total
test count. Avoid broad UI snapshots, tests that restate implementation internals,
or testing the full physics plant for every transport validation case.

## Scope and verification limits

Reviewed the complete engine, API runtime/application, development launcher,
frontend transport/store/types, controls/dialog, chart transforms/theme and chart
components, status widgets, package/tool configuration, engine/API/launcher tests,
frontend unit tests, and Playwright smoke test. Physics tests and examples were
sampled for integration contracts and duplication; the primary reviewer owns
physical accuracy and full baseline check results.

Focused experiments confirmed C1–C6 and the chart-domain behavior. C3 was
reproduced independently of the full suite. C7 and the smaller accessibility/
error-display concerns are source-established observations. No implementation
fixes were committed, no real network-client teardown was verified, and no
browser accessibility audit or production deployment test was performed.
