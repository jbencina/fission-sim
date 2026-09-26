# Software craft review

Baseline: `5dc6e641ef7807e323a5b9c90637696a60ad07e4`.
Branch: `review/accuracy-readability-craft`.
Implementation was preserved during this review. Experiments used inline scripts,
temporary processes, or an in-memory copy of the application.
Independently re-verified on 2026-09-26; see the audit section of
[README.md](README.md). C3 was reframed, C6 was downgraded, C8–C10 are new,
and several sections gained detail from that pass.

## Overall assessment

The main decomposition is sound: physics components are independent of HTTP and
React; the engine owns integration; the runtime owns commands and subscriptions;
the browser separates transport, state, chart transforms, and presentation.
There is useful test coverage of equations, graph behavior, commands, and chart
state. A framework rewrite or a much larger test suite would not improve this
project proportionately.

The clearest craft problems are in lifecycle behavior. Concurrent resets can
create two integration tasks, paused clients cannot obtain fresh command
state, and the API test suite is red in the project's own virtual environment
because Starlette's `TestClient` and CPython 3.13+ task-group cancellation
interact badly. The first two are real bugs with narrow triggers; the third
is a harness incompatibility rather than a user-visible defect, but it hides
the only coverage of command validation. Smaller gaps affect graph
diagnostics, the engine's output-classification protocol, malformed-message
handling, developer process cleanup, and test timeouts.

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

**Trigger width:** the race needs the second reset to be dispatched in the
same event-loop turn as the first. Delaying it by a single `asyncio.sleep(0)`
leaves one task and no orphan. A single client cannot trigger it because the
receive task awaits each command before reading the next message
(`app.py:187-202`); it takes two clients whose reset messages land in one
loop iteration. P2 stands because the orphan survives `stop()` and the fix is
small, but this is not an everyday interaction.

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
Note that seeding as recommended breaks `test_resume_publishes_running_true`
(`tests/api/test_runtime_pause_publish.py:81-89`) as written: it subscribes,
pauses synchronously, and asserts the first dequeued frame has
`running=False`, so a seeded running frame would arrive first. Adjust that
test alongside the change. The silence assertion at `:64-69` only forbids
frames when nothing changes and is compatible with publish-on-command.

### C3 — P2: API tests fail at `TestClient` WebSocket teardown on CPython 3.13 and later

**Evidence:** `src/fission_sim/api/app.py:204-215`;
`tests/api/test_websocket.py:66`; `pyproject.toml:5` (`requires-python = ">=3.11"`).

With the repository lock's installed packages, normal `TestClient` WebSocket
context exit raises `concurrent.futures.CancelledError` on CPython 3.13.1 and
3.14.0. The same suite passes on 3.11.16 and 3.12.14. The project declares
3.11+ and its own `.venv` is 3.14, so the suite is red as checked out. This is
separate from receiving frames or command responses: a session can exchange
valid data and then fail while disconnecting. The full run reports nine API
failures with this symptom.

**Reproduction:** The focused command

```sh
.venv/bin/python -m pytest tests/api/test_websocket.py::test_websocket_receives_at_least_5_frames -vv
```

failed during `WebSocketTestSession.__exit__`. A second experiment opened five
independent sessions and received three frames from each: all five baseline
sessions failed at exit. In an in-memory copy of `app.py`, replacing only
`asyncio.TaskGroup`/`create_task` with
`anyio.create_task_group`/`start_soon` produced zero failures in five sessions.

**Cause:** CPython 3.13 added an "un-cancel and re-cancel the parent" step to
`TaskGroup.__aexit__` (`asyncio/taskgroups.py:166-178`; absent from 3.12).
When Starlette's `TestClient` cancels the endpoint from its AnyIO cancellation
scope (`starlette/testclient.py:110-123`) while the group is cancelling a
sibling child, that re-cancel surfaces as `CancelledError` at context exit.
A minimal endpoint with send and receive children in an `asyncio.TaskGroup`
reproduces it; the same endpoint with one child, or with an AnyIO task group,
does not.

**Scope:** a real uvicorn server on 3.14 with a `websockets` client, over two
clean closes and a TCP abort, logs no traceback and no `CancelledError`.
This is a test-harness incompatibility, not a defect users can observe. It
stays P2 because the suite is red in the project's own environment and
because `handle_command` validation is tested only through this harness
(see the tests section).

**Recommendation:** Use task-group/cancellation ownership compatible with the
ASGI framework, and rerun the existing API suite. Replacing
`asyncio.TaskGroup` with `anyio.create_task_group` at `app.py:207-209` takes
the nine tests to green on 3.14 (verified with an in-memory copy). If
adopting AnyIO directly, declare it as a direct dependency. Keep disconnect
cleanup covered; swallowing `CancelledError` broadly or relaxing the tests
would hide lifecycle failures.

### C4 — P3: Graph finalization misses invalid references, a self-cycle, and a name collision

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
3. Register an external `x=5.0` and a module output port also named `x` that
   has a consumer. Finalize succeeds; `snapshot()["signals"]["x"]` reports the
   module's value while consumers of the external still receive `5.0`, because
   `signal_values` is keyed by bare name (`:504`, `:516`) and the producer
   check (`:329-343`) ignores externals. Like C5, this corrupts the snapshot
   schema without affecting the integration.

**Impact:** A learner extending or wiring components receives a low-level error
after a supposedly successful validation step. Signals from another graph can
also alias local names rather than identifying the intended producer.

**Recommendation:** Validate each consumed external and producer port during
finalization, and retain self-dependencies for computed components. If foreign
handles must be rejected even when names coincide, give signals an engine
identity. Cover the three concrete cases with small graph tests. No general
graph framework is needed.

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

### C6 — P3: Developer cleanup misses descendants of an exited process leader

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
the cleanup function itself, so it cannot catch this. This is P3 by the
convention above: normal Ctrl-C works because the leader is alive, and the
trigger is a wrapper or reloader dying while its children survive. The fix is
still worth making because it is a few lines.

A related shape problem: both signal handlers (`dev.py:140`, `:162`) run the
blocking cleanup inline, including `proc.wait()`. The main loop's `poll()`
(`:278`) holds the non-reentrant `Popen` wait lock, so a signal delivered in
that window can deadlock the handler's final wait. The standard shape, where
the handler sets a flag and the loop cleans up, avoids this; the loop also
re-runs `_terminate_children()` after a handler already did (`:281-298`).

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
resort. Add one shared helper that selects telemetry versus acknowledgement
messages; none exists today (`test_commands.py:46-62` do not filter by type),
and `test_command_does_not_disconnect` currently accepts the immediate ACK as
proof that telemetry continues (`:99-106`; its comment at `:101` calls the
command "unknown", but it is valid).

### C8 — P3: The engine discards its finalize-time classification and re-probes by exception on every evaluation

**Evidence:** `src/fission_sim/engine/engine.py:395-403`, `:441-449`,
`:499-518`, `:557-560`, `:672-687`.

`finalize()` classifies each module as state-derived or computed by calling
`outputs(state)` and catching `TypeError`, then stores only `("output", name)`
in `_eval_order`. Both evaluation paths therefore go through `_call_outputs`,
which repeats the try/except on every call. On the standard plant that is two
raised-and-caught `TypeError`s per right-hand-side evaluation (`sg` and
`pzr_ctrl`), thousands per BDF step. The two components also signal
"computed" differently: `SteamGenerator` raises its own `TypeError`;
`PressurizerController` uses a keyword-only `inputs`.

The misclassification risk is reproducible now, not hypothetical: a
state-derived `outputs()` containing an unrelated `TypeError` (for example
`state[0] + None`) passes `finalize()` silently as "computed" and fails only
at the first `snapshot()` or `step()`.

**Recommendation:** store the kind in `_eval_order` at finalize and dispatch
on it; that removes the per-call probe and most of the misclassification
risk. An explicit capability flag on components is cleaner still and is what
the readability review (R4) should then document. One test that a
state-derived module raising `TypeError` inside `outputs()` is reported at
finalize is enough.

### C9 — P3: A malformed client message ends the session without a close frame

**Evidence:** `src/fission_sim/api/app.py:26-27`, `:188`, `:213-215`;
`src/fission_sim/api/runtime.py:840`; `tests/api/test_commands.py:314-328`.

`receive_json()` raises `JSONDecodeError` for non-JSON text and `KeyError`
for a binary frame. Both propagate to `except* Exception`, which logs and
returns without `websocket.close()`. A live probe shows the client sees an
abnormal close with no close frame and the server logs "WebSocket session
ended with error". The module docstring and the runtime say malformed
commands get an error frame; the only test covers valid-JSON `[]`.

**Recommendation:** catch decode errors in the receive task, send the
existing error envelope, and continue. One test with a non-JSON text frame
covers it.

### C10 — P3: Runtime concurrency claims do not match the code, and one failure path is silent

**Evidence:** `src/fission_sim/api/runtime.py:256`, `:293-294`, `:418-425`,
`:433`, `:454-455`, `:460`, `:482`, `:495-499`, `:531`, `:565-643`,
`:630-631`, `:762-836`, `:806-811`.

- The `asyncio.Lock` protects nothing: no `async with self._lock` body
  contains an `await`, the public setters bypass it, and frames are tagged
  from `self._cmd` outside it (`:433`, `:460`), so a frame's `scrammed` or
  `speed` can differ from the values used for that step. The docstrings at
  `:256` and `:293-294` describe protection and "thread-safe setters" that do
  not exist. Either make the lock span the step-and-publish sequence or delete
  it and the claims.
- Exceptions outside the guarded `engine.step()` call, such as in
  `snapshot()` or `_build_telemetry_frame` (`:433`, `:460`), end the step task
  with no log and no done-callback. Sockets stay open with no frames, and
  `stop()` (`:531`) re-raises the stored exception later during lifespan
  shutdown or `reset()`. Add a done-callback that logs and sets
  `running=False`.
- Dead or divergent code: the `dead` list and `except Exception` in
  `_publish` (`:482`, `:495-499`) are unreachable because `put_nowait` raises
  only `QueueFull`; `set_speed`'s `ValueError` (`:630-631`) is unreachable
  through the API and uses a different rule (`> 0`) from `handle_command`
  (`{1, 2, 5, 10}`, `:806-811`). Keep one validation rule.

## Smaller frontend observations

- **Chart time window changes with speed.** The store retains 600 frames
  (`web/src/state/telemetryStore.ts:104-109`), while chart transforms keep
  every other frame, about 301 points, always including the oldest
  (`web/src/charts/chartData.ts:43-45`). At 10× and 10 Hz, those
  frames span 599 simulated seconds. `chartTheme.ts:34` specifies `[-60, 0]`,
  but the installed Recharts X axis defaults to `allowDataOverflow=false`, so it
  expands to the data. A direct transform plus the installed Recharts domain
  helper returned `[-599, 0]`. This conflicts with the chart comments promising
  the last 60 seconds; choose an explicit simulated-time window or document a
  speed-dependent history. One transform test with accelerated timestamps would
  cover a fixed-window decision. No rendered browser check was performed.
- **Decimation flips its sample set every tick.** `chartData.ts:43-45` keeps
  even buffer indices. With a full ring buffer each new frame shifts index
  parity, so the retained timestamps alternate between two complementary
  halves of the history (`{100, 102, 104, 105}` then `{101, 103, 105, 106}`).
  At 10 Hz with animation off, noisy series are redrawn through alternating
  point sets. Anchor decimation to frame time or a monotonic counter.
  `chartData.test.ts` uses two-frame histories and cannot observe this.
- **Errors are collected but never shown.** `wsClient.ts:119-120` forwards error
  envelopes to the store, but no rendered component subscribes to `lastError`.
  A rejected command has no visible explanation. A small dismissible status
  message would make the existing error pipeline useful; no new notification
  framework is necessary. Two things to fix when doing so: `ws.onerror`
  (`wsClient.ts:142-145`) fires for sockets the app itself closed, including
  the React StrictMode double-mount in development (`main.tsx:12`), and
  nothing ever clears `lastError` (`onopen` at `:92-100` does not reset it),
  so a stale reconnect message would overwrite or outlive a command-rejection
  detail. Separately, the store's `reset()` (`telemetryStore.ts:129-134`)
  has no caller and its comment is wrong: spreading `initialState` sets
  `status: 'connecting'`, which would disable every control on a live socket
  until the next reconnect.
- **Modal focus is incomplete.** `ConfirmDialog.tsx:76-92` moves focus inside
  and handles Escape, but does not keep Tab within the modal or restore focus
  afterward. This is source inspection, not a keyboard browser test. The
  readability review separately covers hover-only educational tooltips.
- **Worth keeping:** TypeScript is strict, `web/src` has no `any` or
  `@ts-ignore`, and `isFrame` (`types/telemetry.ts:215-223`) validates keys,
  numeric type, and finiteness at the transport boundary.

## DRY and maintainability

The highest-value extraction is a shared standard-plant builder. There are
five near-identical copies of the same seven modules, five externals, and
topology: `runtime.py:121-167`, `examples/run_primary.py:54-93`,
`report_primary.py:91-126`, `console.py:74-117`, and
`power_maneuver.py:68-107`. They differ only in call order and in whether
parameters are passed or inlined. The readability review found an
already-broken example and tutorial after loop ports changed. That is
concrete evidence of drift. Keep one explicit wiring example for teaching;
have operational examples and the web runtime call a public factory with
parameter overrides. A public module is the right shape because examples
cannot reasonably import a private helper from the API package; that would
pull FastAPI into physics examples. Preserve independent equation/integration
oracles in tests rather than making every test reuse the same implementation
helper.

Two smaller opportunities are proportionate:

- `_resolve_signal_values()` and the output pass inside `_build_f()` duplicate
  graph evaluation (`engine.py:499-518`, `:672-687`). They are textually
  identical apart from a missing `else: raise AssertionError`, so `_build_f`
  can call `self._resolve_signal_values(y, externals)` directly at no cost.
  Do that when touching C8 so snapshot and integration evaluation cannot
  diverge.
- `DenseSolution.at()` and `signal()` (`engine.py:820-828`, `:882-890`)
  temporarily overwrite the engine's `_t` and `_state` from a read-only
  adapter, solely because `_build_snapshot` reads `self._t`; the `_state`
  write is never read. Pass `t` as an argument. On a miss, `signal()` also
  re-calls every module's `telemetry()` after already building the full
  snapshot (`:898-907`).
- Shared chart style and data-transform modules are already useful. The four
  chart components still repeat their outer layout, but remain short and easy
  to read. An elaborate generic chart specification would obscure this
  educational code. Likewise, independent toy graph setups in tests are often
  clearer than a large fixture factory.

The engine's use of `TypeError` as its computed-output protocol is C8 above;
the readability review (R4) owns the missing documentation for that contract.

## Tests: what to preserve and what to add

**Preserve:** steady-state and conservation checks, dense-output behavior,
command validation, chart updates after the history reaches capacity, the
frontend time-rollback-after-reset check, finite-value telemetry guards, and
the end-to-end SCRAM smoke test. These check different failure modes.
The smoke test already resets the persistent backend and establishes speed/run
state; it should remain a small integration check.

The engine-versus-direct-solver comparison (`tests/test_engine.py:1043`) is
currently skipped because its handwritten M1 plant is stale, so it provides no
protection. Re-enable an independent oracle using a small representative graph,
or remove the dead legacy scaffolding after retaining equivalent coverage.

**Fix these assertions before adding more:**

- `tests/api/test_runtime.py:97-103` is vacuous: after 0.5 s at 1× the clock
  reads about 0.5 and the test asserts `t < 1.0`, which passes with the reset
  removed. The frontend rollback test (`telemetryStore.test.ts:53`) is real.
- `tests/api/test_commands.py:40-43` (`_set_speed`) claims to consume the
  response and does not. `_recv_frame` and `_collect_until` treat
  acknowledgements as telemetry, so `first = _recv_frame(ws)` at `:137`
  receives the ack, `:139` silently defaults `rod_start` to 0.5, `:105` seeds
  `t_start = 0.0`, and the assertion at `:152` is correspondingly weak.
- `except Exception: break` (`tests/api/test_websocket.py:73-75`, `:133-134`)
  hides why a socket broke.
- `handle_command` validation (`runtime.py:744-844`) has no direct unit test;
  it is exercised only through the harness that is red on 3.13+. That is the
  concrete instance of the advice below about not testing the full plant for
  every validation case.
- Small redundancies: `test_subscription_delivers_frames`
  (`test_runtime.py:106-116`) is subsumed by `test_all_required_keys_present`
  (`:119-131`); the `runtime` fixture is duplicated (`test_runtime.py:40-46`,
  `test_runtime_pause_publish.py:27-33`); `@pytest.mark.asyncio` is redundant
  with `asyncio_mode = "auto"`; `telemetryStore.test.ts:136-152` spends three
  tests on a `reset()` that has no caller.

**Add only around concrete risks:** concurrent reset/shutdown, paused
subscription and command visibility, invalid graph references/self-cycles/name
collisions, reserved names, output misclassification at finalize, malformed
client messages, and process-group cleanup. A compact transport test with a
fake WebSocket could cover reconnection and permanent close without a browser.

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
fixes were committed, and no browser accessibility audit or production
deployment test was performed. The second pass verified real network-client
teardown and the Python-version dependence (C3), reran C1, C2, and C4–C6,
measured the per-call probe count (C8), and probed the malformed-message
path (C9) against a live server.
