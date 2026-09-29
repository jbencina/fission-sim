# Phase D — independent operator review

## Summary

**Reviewed:** `jbencina/m3-m4`, HEAD `350e0da6bf0631022dedcac0d3592a03bb34e6cd`, 2026-09-29.

**Result: 0 high, 7 medium, 6 low findings.** The secondary-side integration is
useful for the project's stated learning purpose. It is not yet a comfortable
single-screen transient console: the operator must scroll between the action,
its controlling indication, and its trend. Several remaining labels also
undercut otherwise good model-fidelity explanations.

The requested high-severity test was applied: none of the observed dashboard
problems teaches an irreparable operational misconception that cannot be
addressed by honest labeling/scope, clearer indication, or a bounded UI change.
This is an operations-realism/interface review, not a physics certification or
a general code audit.

### Preserve these improvements

- Admission demand, actual admission, and gross electrical MW are separate.
  The 100→90% exercise does not pretend to be an exact MW-demand change.
- Rod AUTO disables the manual slider and plots the active demand rather than
  the inactive manual target. AUTO ACTIVE, trip/SCRAM suspension, and ordinary
  paused mode transfers are distinguishable.
- Effective turbine trip and its operator/P-4 cause are visible in both the
  controls and schematic. Paused trip/reset and feedwater changes generally
  distinguish selected commands from frozen plant values, including reconnects.
- Feedwater MANUAL initially tracks the current demand. The `% max`, kg/s,
  `% design` readouts and explanation of maximum = 120% design are worthwhile.
- The turbine-trip confirmation explicitly warns that the exercise is
  unprotected. The SG control explains collapsed inventory and absent
  shrink/swell; the level target stays inside the model's validity limits.
- Steam pressure, dump flow, feed demand/actual, signed feed/steam mismatch,
  `T_avg − T_ref`, and level error make the secondary-side causal sequence
  understandable. Each chart has its own time axis.
- The model-limit halt is persistent, identifies the last valid displayed
  state, names omitted protection, and disables Resume. It does not masquerade
  as a reactor trip.
- Reset Simulation's confirmation honestly explains full-power reconstruction
  with retained admission demand. Late trip resets correctly set demand to
  zero rather than silently restoring the previous 100% demand.

## Scope and method

Read the Phase D plan, including amendments and D.11, and the Disposition tables
in `reviews/m3-operator-review.md` and `reviews/m4-operator-review.md`. Read the
requested controls, tooltips, status, schematic, shared status classification,
events, chart specifications, and README dashboard section. Inspected
`assets/web-ui.png`; it is a **post-turbine-trip** view, not a design-state
screenshot.

Started and drove the real stack:

- API: `uv run uvicorn fission_sim.api.app:app --host 127.0.0.1 --port 8768`
- Web: from `web/`, `FISSION_SIM_API_PORT=8768 npm run dev -- --port 5188 --strictPort`
- Chromium through Node + the repository's `@playwright/test`, **1440×900**.
  UI buttons and keyboard-operated sliders supplied the scenario actions;
  WebSocket commands established repeatable fixtures and froze capture points.
  Captures at a given checkpoint share frozen physics while the columns are
  scrolled. Thus most screenshots show **Paused**, deliberately, rather than
  implying an automatic pause during a real transient.
- Scenario times were determined from telemetry, not `10 × wall-clock sleep`.
  Accelerated runs used speed 10; the early turbine-trip and SCRAM response
  was observed at speed 1. Pauses between captures do not advance model time.
- Saved 54 viewport screenshots plus telemetry/command evidence and scripts.
  Viewed the principal overview, secondary-control/trend, readout, halt,
  confirmation, and keyboard-help captures individually; inspected the
  remaining alternate views in five scratch contact sheets.
- Harness corrections: wait for MANUAL acknowledgement before operating its
  previously disabled slider; use actual Tab navigation, rather than
  programmatic focus following a mouse click, to test keyboard help. These were
  harness issues, not dashboard defects.
- No implementation files changed. Both servers were stopped by exact PID;
  neither review port remained listening. No commit was made.

**Evidence directory (`S` below):**

```text
/home/jbencina/.copilot/session-state/1217b4be-707a-424f-96b0-7dec3ca1b8d0/files/phase-d-review/
```

Scripts: `operator-scenarios.cjs`, `follow-up.cjs`, `keyboard.cjs`.
Evidence: scenario-named `.json` files, `observations.json`,
`observations-remaining.json`, `follow-up.json`, and `keyboard.json`.

## Findings

References `[R1]`–`[R4]` are listed below. “Experience” denotes an operator
scan/task-sequencing judgment, not a claimed plant-specific requirement.

| # | severity (high/medium/low) | file:line or screen | finding | real-plant reference/experience | proposed change |
|---|---|---|---|---|---|
| 1 | medium | `web/src/layout/AppShell.tsx:44–80`; `web/src/charts/ChartGrid.tsx:16–19`; screens `01-design-steady.png`, `07-loss-feedwater-plus10s-secondary.png` | **Controls and consequences are separated by scrolling.** Initially, the steam-pressure/SG-level charts only begin at the bottom edge; feedwater and SG controls are below it. Looking at those controls scrolls SCRAM/Pause away; looking at detailed readouts loses both trip controls. Fuel temperature/reactivity occupy prime space while the secondary action's feedback is off-screen. The grouping is logically sound but the scan is not. | Experience: during a loss of heat sink, a crew needs reactor power, steam pressure, inventory/flow balance, and manual trip access together. This does not require copying a whole main control board. | Keep SCRAM, Pause/Resume, and essential trip/mode status in a persistent strip. Provide an obvious secondary-transient view or chart prioritization with power, `T_avg/T_ref`, steam pressure, SG level, and feed/steam flows together. Add visible “Turbine admission” and “Feedwater” subheadings; do not just shrink all ten plots. |
| 2 | medium | `web/src/charts/chartData.ts:21–22`; `web/src/state/telemetryStore.ts:20–24`; `web/src/widgets/EventLog.tsx:11–23`; `web/src/state/events.ts:310–311`; screens `02-admission-90-auto-plus300s-secondary.png`, `04-turbine-trip-plus90s-secondary.png`, `08-loss-feedwater-model-limit.png` | **The console loses the evolution before the exercise is over.** At +300 s the two-minute admission ramp is gone; at +90 s the turbine-trip onset and dump opening are gone from every plot. Only six events are rendered, with no way to retrieve the older retained events. Pause/speed/keyboard commands displace the initiating event. At the inventory halt, a copy of the entire long halt explanation fills the visible event pane. | Experience: seconds establish trip response; minutes establish controller recovery. A learning debrief needs both. A 60-s window is useful for prompt response but cannot explain a 3–5-minute load-change exercise. | Offer at least 1/5/15-minute simulated-time windows and suitable time-based retention, with a way to hold/review a completed transient. Expose the retained event history, optionally filter routine commands, coalesce rapid keyboard demand changes, and keep the halt event to a short summary linked to the already-visible notice. Keep the existing per-chart time axes. |
| 3 | medium | `web/src/widgets/PlantMimic.tsx:354–355`; screens `02-admission-90-auto-plus300s.png`, `05-scram-p4-plus10s.png` | **The two rod percentages use opposite conventions without saying so.** After admission reduction the schematic says “rods 62%” while the control gauge/rod chart say 38% withdrawn. After SCRAM the schematic says “rods 100%” beside a 0% control position. The bar depth is sensible, but the unlabeled number looks contradictory. | Experience: rod-position verification must have one unambiguous direction. A crew should not mentally complement an indication during trip verification. | Use `% withdrawn` consistently for numeric rod indications, or explicitly print `% inserted` on the schematic. Retain the physically intuitive insertion-depth drawing. Label the drawn bank as the control bank. |
| 4 | medium | `web/src/widgets/PlantMimic.tsx:198–202`; `web/src/widgets/tooltips.ts:151–160`; `web/src/widgets/StatusPanel.tsx:135–140`; screens `03-turbine-trip-plus10s.png`, `08-loss-feedwater-model-limit-readouts.png` | **Collapsed inventory is still presented as generic “SG LEVEL”/“SG level” in the always-visible mimic and readout.** The full caveat exists in accessible text, help, and the scrolled control section, but not at these glances. A filled SG shell with “52%” immediately after a trip looks like an indicated-level swell response. “valid 30–95%” does not identify the measurement. | [R1]: indicated SG level, density effects, shrink/swell, and instrument span are distinct from a collapsed liquid-volume fraction. This was an explicit M3/M4 carry-forward requirement. | Make “collapsed” visible in the mimic/readout label. Put “4 SGs lumped; no shrink/swell; not narrow-range indication” in a nearby persistent legend or always-visible short qualifier. Preserve the detailed help and model-limit annotation. |
| 5 | medium | `web/src/controls/SecondaryControls.tsx:305–448`; `web/src/widgets/tooltips.ts:151–170,222–260`; screen `07-loss-feedwater-plus10s-secondary.png` | **The feedwater-loss/overfill exercise warning arrives too late.** Unlike TRIP TURBINE, the feedwater/level controls do not explain before the experiment that low-low-level reactor trip/AFW start and high-high-level turbine trip/feedwater isolation are absent. The loss-of-feedwater halt notice does eventually explain the low-level omission, correctly, but the learner has already watched the unprotected excursion. | [R1]–[R3]: inventory loss invokes protection and auxiliary feedwater; high-high indicated level has separate protective consequences. These are not the model's 30/95% volume-fraction boundaries. M4 disposition #4 specifically carries this scope warning forward. | Add a compact, persistent “unprotected inventory exercise” note by level/feedwater controls, naming both omitted responses. Include the warning in help before manual extreme-demand exercises. No need to add RPS/AFW physics or a confirmation for every ordinary adjustment. |
| 6 | medium | `web/src/state/events.ts:288–305`; `web/src/widgets/StatusPanel.tsx:50–61,193–198`; screens `07-loss-feedwater-plus10s-secondary.png`, `07-loss-feedwater-plus10s-readouts.png` | **An intentional manual cutoff is presented as controller saturation, and the cutoff itself is not logged.** MANUAL initially logs 83% max; moving it to zero produces no manual-value-change event, then “Feedwater demand saturated at zero.” The readout repeats “saturated at zero” despite the MANUAL control correctly saying the operator demand is active. That suggests a controller authority problem rather than an operator-directed flow cut. | Experience: “controller at its limit” and “operator selected zero” lead to different diagnoses. [R1] distinguishes automatic control and manual overrides. The shared feedwater-mode helper already distinguishes effective manual operation. | Log committed manual-demand changes with `% max` and kg/s, including pending wording when appropriate. Reserve AUTO saturation terminology for effective AUTO; in MANUAL say “manual demand at zero/max.” Apply the same mode-aware classification to the event and readout. |
| 7 | medium | `web/src/controls/ControlPanel.tsx:280–294`; `web/src/controls/SecondaryControls.tsx:278–291`; `src/fission_sim/api/runtime.py:820–843,908–917`; screen `12-reset-scram-manual-bank-return.png` | **An early Reset Scram can terminate fast turbine closure before the valve is closed.** In the follow-up, SCRAM was recorded at t=3.4 s and reset at 4.7 s, after the UI's bank-insertion event. At t=12.6 s, demand was 0 but admission was still 6.76% and gross output 75.1 MW. Clearing the trip restores the ordinary slow admission ramp (`physics/turbine.py:407–429`). Zero demand is not proof of closed valves. Related Reset Turbine Trip help unconditionally promises that the turbine “remains closed.” | [R2], p. 12.2-10, distinguishes reactor-trip-breaker-derived P-4 from a UI reset. Experience: verifying valve closure and resetting a trip are different actions; resetting is not a shortcut to completing trip response. | Keep zero-demand reset behavior, but do not promise closure from the demand alone. Prefer a UI guard that prevents release until the simulated fast closure is complete, or explicitly warn that this is idealized signal release and show “closing, not yet shut” from actual admission. State that Reset Scram releases the control bank according to its selected mode, not a real restart procedure. |
| 8 | low | `web/src/controls/SecondaryControls.tsx:172–177`; screens `04-turbine-trip-plus90s.png`, `04b-trip-reset-pending.png` | **“Valves closing” persists after closure**, even at +90 s with actual admission displayed as 0%, and after a paused reset when no valve can move. The trip tag and demand are otherwise correct. | Experience: command, travel, and end-position indications are separate. | Use “trip active; admission closed” once actual admission is below a documented display tolerance. For frozen reset state, use “reset pending; actual admission …”, not a motion verb. |
| 9 | low | `web/src/state/plantStatus.ts:308–320,367–370`; `web/src/controls/ControlPanel.tsx:208–213`; `web/src/state/events.ts:214`; screens `10-paused-pending-trip-auto.png`, `11b-paused-admission0.png`, `11c-paused-scram.png` | **Some surrounding copy escapes the pending-state distinction.** Pause→trip→AUTO says AUTO SUSPENDED “by controller logic,” although the last step was MANUAL and the trip itself is pending. AUTO-only pending still says “AUTO owns rod demand.” A paused SCRAM event says “both banks dropping” while rods and power remain frozen. Paused admission demand is marked pending in the event, but not beside its slider. | Experience: accepted command, inhibited controller, and actual movement should not be interchangeable. The effective-value architecture is already a good foundation. | Derive the short explanatory paragraphs as well as tags from shared status. For the combined paused sequence say “AUTO selected; inactive; queued trip inhibits operation on resume.” Use “SCRAM selected; insertion pending on resume” when frozen, and place admission pending status beside demand. |
| 10 | low | `web/src/widgets/Readouts.tsx:43–58`; screens `01-design-steady-readouts.png`, `02-admission-90-auto-plus300s-readouts.png` | **Annotations still displace the identity of some readouts.** At 1440×900, “Gross MW” becomes “Gross …”; the long near-equilibrium floor estimate reduces its label to “Level f…”. The estimate of 159,062 s for a −0.6 kg/s mismatch also has more visual precision than practical meaning. | Experience: the parameter name must survive a glance; nearly balanced inventory flow is not a useful precise action clock. | Give the parameter label priority; move lengthy qualifiers to a second line/help. Retain “current-flow estimate, not a countdown,” but consider `>1 h`/“near balance” presentation for very long estimates, without changing the underlying telemetry. |
| 11 | low | `web/src/widgets/PlantMimic.tsx:168–177,340–355`; `web/src/widgets/StatusPanel.tsx`; screen `12-reset-scram-manual-bank-return.png` | **Two schematic/state cues remain potentially misleading:** the pressurizer has a fixed drawn water fill, not a measured level; after Reset Scram there is no persistent shutdown-bank-in indication, even though that retained bank is why the core remains deeply subcritical. | Experience: pressurizer level is central to interpreting insurge/outsurge; post-trip rod verification includes the banks not represented by the control-bank gauge. | Label the pressurizer fill as schematic or omit that fill until driven by real telemetry. Add a persistent “shutdown bank inserted; restart not modeled” indication after reset, sourced from effective bank state rather than the cleared SCRAM command. Actual pressurizer level is a useful next telemetry addition, not a demand for full-board scope now. |
| 12 | low | `web/src/controls/SecondaryControls.tsx:190,264`; `README.md:94–99` | **P-9 wording overgeneralizes a representative plant.** “A real plant … above about 50% (P-9)” is directionally useful but reads as universal. P-4 copy also needs to remain scoped to the turbine-trip consequence implemented here, not all P-4 functions. | [R2], p. 12.2-7: P-7-based examples use about 10%, while plants with P-9 use about 50%; p. 12.2-10 lists additional P-4 functions. | Say “In representative Westinghouse plants with P-9, a turbine trip above about 50% power also trips the reactor; thresholds/logic vary. That protection is omitted here.” Retain the unprotected warning and the model's combined dump/relief explanation. |
| 13 | low | `web/src/controls/SecondaryControls.tsx:405–408,423–446`; screens `01-design-steady-secondary.png`, `13b-keyboard-feedwater-help.png` | **The feedwater scale's visual annotation does not match its denominator.** “100% design” is centered under a `% max` slider even though its actual tick is at 83.33% of travel. Also, the “Manual” numeric label is shown while AUTO is active. The numerical conversions and help themselves are correct. | Experience: consistent scale geometry is part of reading a demand indicator; the operating mode should identify who owns that demand. | Align “100% design” with the 83.33% tick, or use a separate unambiguous legend. Label the AUTO value “Tracked demand” and the MANUAL value “Manual demand.” Replace “Returning to AUTO sends null” with operator-facing language about restoring automatic level control. |

## Scenario walk-throughs

These numbers describe this build, not target values for a real plant.
Screenshot names are relative to `S`; `-secondary` shows the lower charts and
secondary controls, and `-readouts` shows the detailed status column.

### 1. Design steady state

At t=60 s: 3,000 MW fission power and SG heat removal, 990 MW gross,
6.899 MPa steam pressure, 50.0% collapsed inventory, and approximately
1,669 kg/s steam/feedwater. `T_avg = T_ref = 583 K`; dump flow is zero.
This is a clean, comprehensible initialization with no spurious alarm traffic.
The first useful improvement is the scan layout, not another derived number.

Screens: `01-design-steady.png`, `01-design-steady-secondary.png`,
`01-design-steady-readouts.png`.

### 2. Ten-percentage-point admission reduction, rods AUTO

Selected AUTO and reduced demand from 100% to 90% using keyboard steps.
After 300 simulated seconds at speed 10: actual admission 90%, gross output
895.4 MW, fission power 2,711.4 MW, rod position/active demand 38.35% withdrawn,
`T_avg = 580.95 K` versus `T_ref = 581.20 K`, and level 49.95%.
AUTO ACTIVE and a disabled manual slider correctly convey control ownership.
The retained manual target remains separately available in the readouts.

The model shows a sensible load-following teaching sequence; the dashboard
only retains the last minute on-screen, so its final screenshot does not show
the ramp that explains the endpoint. The schematic's “rods 62%” is the
complementary-scale problem in finding #3.

Screens: `02-admission-90-auto-plus300s.png`,
`02-admission-90-auto-plus300s-secondary.png`,
`02-admission-90-auto-plus300s-readouts.png`.

### 3. Unprotected turbine trip, rods MANUAL

The confirmation correctly announces an unprotected exercise. Near +10 s:
actual admission and gross MW round to zero; steam pressure is 8.054 MPa;
dump flow approximately 1,263 kg/s; feedwater 835 kg/s versus demand
1,200 kg/s; level 51.91%; fission power 2,881.7 MW. The early flow panel is
particularly useful: turbine steam disappears, feedwater lags its command,
and dump flow takes over as pressure rises.

Near +90 s: 8.172 MPa steam pressure, about 1,592 kg/s dump flow,
50.49% level, and 2,825.3 MW fission power. This is **not** a protected
turbine-trip response. It demonstrates this model's continuing fission,
negative feedback, and available combined steam-discharge path. Do not infer
that a real condenser dump alone accommodates this sustained condition [R4].

Dump-open and pressure-band events were useful; no sustained dump/saturation
chatter was observed. Resetting this already-closed turbine showed RESET
PENDING while paused, set demand to zero, and cleared effectively after
resume without restoring old demand.

Screens: `03-turbine-trip-confirmation.png`,
`03-turbine-trip-plus10s-secondary.png`,
`04-turbine-trip-plus90s.png`,
`04-turbine-trip-plus90s-secondary.png`,
`04b-trip-reset-pending.png`.

### 4. SCRAM, P-4, and Reset Scram

With rods AUTO, SCRAM produced the expected causal indication: bank insertion,
AUTO SUSPENDED by SCRAM, turbine TRIPPED / SCRAM (P-4), falling fission power,
and subsequent dump flow. Near +10 s, fission power was 92.6 MW, control-bank
position rounded to zero, steam pressure 7.841 MPa, and dump flow 670 kg/s.
The distinction between fission power and residual stored-energy removal is
visible in the power chart. Decay heat is correctly identified as omitted in
the power help; this is not a shutdown-cooling demonstration.

A paused reset showed turbine RESET PENDING and rod PENDING; admission demand
became zero. After resume, AUTO became active but did not simply withdraw to
the retained 50% manual target. With the shutdown bank retained, the core
remained subcritical. Accordingly, reset copy should say “return to selected
rod-control mode,” not imply identical manual and AUTO motion.

An additional MANUAL test reset shortly after the bank-insertion event. It
exposed residual turbine admission after fast trip closure was released
(finding #7). The later Reset Simulation test confirmed the documented
asymmetry: actual admission returns to 100%, demand remains zero, and paused
state is preserved. That reset is a simulator convenience, not plant recovery.

Screens: `05-scram-p4-plus10s.png`, `06-reset-scram-pending.png`,
`06b-reset-scram-effective.png`, `12-reset-scram-manual-bank-return.png`,
`12b-reset-retained-admission0.png`.

### 5. Loss of feedwater to the model-limit halt

MANUAL initially selected 83.333% of maximum, preserving the approximately
1,669 kg/s demand; the UI rounded this to 83%. Zero was then commanded at
about t=13 s. At t=25 s, actual feedwater had decayed to 151 kg/s while
steam flow was 1,704 kg/s; collapsed level was 47.13%, mismatch −1,553 kg/s,
and the current-flow floor estimate about 49 s.

At t=66 s the runtime held the last valid level of 30.21%, steam pressure
7.489 MPa, and fission power 2,922.7 MW. Resume was disabled and the notice
stayed visible. It explicitly explained the conservative surrogate boundary,
the lack of real protection, and why displayed values remain just inside the
limit. This is good model-limit teaching.

The earlier 49-s estimate was not a countdown: the model halted about 41 s
after that snapshot as flows/properties continued to change. The label/help
describe this honestly. The manual-cutoff/saturation event ambiguity and
missing pre-exercise warning should nevertheless be fixed. The long notice
also compresses the schematic substantially; its duplicate event should not
consume the remaining log pane.

Screens: `07-loss-feedwater-plus10s-secondary.png`,
`07-loss-feedwater-plus10s-readouts.png`,
`08-loss-feedwater-model-limit.png`,
`08-loss-feedwater-model-limit-readouts.png`,
`08b-model-limit-reset-dialog.png`.

### 6. Level target 50→55%

With feedwater AUTO, at approximately +30 s level reached 50.94%;
feedwater was about 1,816 kg/s versus 1,661 kg/s turbine steam. At
approximately +180 s level was 54.64%, with feedwater about 1,724 kg/s.
The setpoint/demand/actual traces show an inventory correction rather than
an instantaneous physical level jump. This is a useful ordinary controller
exercise. The rise is collapsed inventory, not an indicated-level swell.

Screens: `09-level-setpoint55-plus30s-secondary.png`,
`09b-level-setpoint55-plus180s-secondary.png`.

### 7. Paused commands and reconnect

Paused at t=5.1 s, selected turbine trip, then rod AUTO. The turbine correctly
remained physically at 100% admission / 990 MW with TRIP PENDING / ON RUN.
A fresh connection preserved that distinction without needing running-frame
history. Selecting feedwater MANUAL zero while paused showed the selected
0 kg/s alongside the frozen effective 1,669 kg/s demand, and MANUAL PEND on
the mimic: particularly good feedback.

AUTO-only while paused correctly showed PENDING. The combined trip→AUTO
sequence and paused SCRAM still have the secondary wording issues described
in #9; the classifier should not be replaced wholesale.

Screens: `10-paused-pending-trip-auto.png`, `10b-paused-reconnect.png`,
`10c-paused-feedwater-pending-secondary.png`, `11-paused-auto-only.png`,
`11b-paused-admission0.png`, `11c-paused-scram.png`.

## Layout, copy, telemetry, and accessibility assessment

**Control layout:** Control bank / turbine / SG level and feedwater is the
right functional grouping. Separate trip buttons and confirmation dialogs
are acceptable for an exploratory learning application; they should not be
represented as real emergency-action timing. Do not demand extra confirmations
for each setpoint step. Make important actions persistent instead. The unusually
large rod gauge and fuel/reactivity plot allocation can yield space to the
secondary task without removing their educational content.

**Copy:** Admission versus MW, fixed-efficiency gross output, the 7.6/8.2 MPa
dump behavior, illustrative color bands rather than trips, and the floor
estimate are substantially accurate for the model. “Three-element” could
briefly name level, steam flow, and feedwater flow; “Returning to AUTO sends
null” is API language, not a learner explanation. P-9 needs a representative-
plant qualifier, and P-4 should describe only the implemented consequence.
Place omitted protection and collapsed-level caveats where the learner acts,
not just in help or at the final failure boundary.

**Readouts/charts/mimic:** The important secondary quantities are mostly
present; discoverability and time context are the larger problems. Prefer
persistent power, `T_avg/T_ref`, steam pressure, collapsed inventory, effective
modes, and feed/total-steam balance over adding more numeric tiles. Useful
next additions are actual pressurizer level and explicit shutdown-bank state.
Do not add fake per-SG narrow-range levels, AFW status, turbine speed, or
electrical-breaker indications without the corresponding model. The mimic
does not actually show turbine steam-flow kg/s despite README's broad
description; that value is available in charts/readouts.

**Events:** Cause labels, dump transitions, and band crossings are useful.
Observed sequences did not show recurrent dump-open/close or saturation
chatter. Findings #2 and #6 concern useful history and correct diagnosis,
not a request for more alarms. A few routine keyboard steps should not hide
the initiating event; model validity is not another protection alarm.

**Keyboard/accessibility basics:** Native slider Arrow/Home operation worked.
The rod slider was disabled in AUTO. Actual Tab navigation reached Reset
Simulation, the manual feedwater slider, and readout info controls; their help
was visible and accessible descriptions were present. Escape dismissed help
and canceled dialogs; dialog Tab traversal stayed between its actions and
returned focus to the opener on cancellation. Text mode/trip labels supplement
color, and the SVG has a useful accessible state summary.

The AUTO/MANUAL explanation is attached to the `group`, not each button:
consider associating it with both focusable buttons for consistent screen-reader
behavior. This review did not run a full screen-reader, touch, zoom/reflow,
contrast, or WCAG-conformance audit. The main practical readability limitations
are clipped readout names, small schematic text during a halt, and hidden
controls—not an absence of basic keyboard operation.

Keyboard evidence: `13-keyboard-reset-help.png`,
`13b-keyboard-feedwater-help.png`, `keyboard.json`.

## Reference basis

Public NRC manuals were downloaded to scratch; the SG/protection/AFW passages
were checked directly. These are representative Westinghouse teaching
documents, not a universal plant setpoint specification. In particular, do not
map their narrow-range level percentages onto this model's volume fractions.

- **[R1] NRC Technical Training Center, Westinghouse Technology Systems Manual,
  §11.1, Steam Generator Water Level Control System**, Rev. 0706:
  [ML11223A293](https://www.nrc.gov/docs/ML1122/ML11223A293.pdf).
  Control, shrink/swell, instrument-span, and override discussions; also the
  basis carried forward by the M3/M4 operator reviews.
- **[R2] Same manual, §12.2, Reactor Protection System — Reactor Trip Signals**,
  Rev. 0109:
  [ML11223A301](https://www.nrc.gov/docs/ML1122/ML11223A301.pdf).
  Printed p. 12.2-7 distinguishes low-feed-flow/low-level and low-low-level
  protection and P-7/P-9 turbine-trip configurations; p. 12.2-10 describes
  P-4; p. 12.2-12 describes the high-level override.
- **[R3] Same manual, §5.8, Auxiliary Feedwater System**, Rev. 1208:
  [ML11223A232](https://www.nrc.gov/docs/ML1122/ML11223A232.pdf).
  Purpose and automatic initiation conditions, including low-low SG level and
  feed-pump-trip inputs in the representative configuration.
- **[R4] Same manual, §11.2, Steam Dump Control System**, Rev. 0403:
  [ML11223A294](https://www.nrc.gov/docs/ML1122/ML11223A294.pdf).
  Steam-dump function, operating modes and capacity limitations; reference
  already used in the M3 disposition. This simulator's combined dump/relief
  path should not be taught as an unrestricted real condenser steam dump.

## Disposition

Triage by the orchestrator (2026-09-29). No high-severity findings. All items are fixed in D.12 (a: runtime/contract,
b: controls, c: charts/history/event log, d: readouts/schematic/status wording/events).

| # | Severity | Disposition |
|---|---|---|
| 1 | medium | fix now (D.12b persistent SCRAM / Pause strip + trip/mode status that stays visible while the right column scrolls; D.12c chart view selector All / Reactor / Secondary so power, T_avg/T_ref, steam pressure, SG level and feed/steam flow can be seen together without shrinking plots). |
| 2 | medium | fix now (D.12c: 1 / 5 / 15-minute simulated-time chart windows with time-based retention; event log shows the full retained history (scrollable) and a one-line halt summary with the full text in the notice; D.12d: routine commands filterable/coalesced in events.ts). |
| 3 | medium | fix now (D.12d): schematic rod number in % withdrawn like every other indication (drawing keeps insertion depth), labelled "control bank". |
| 4 | medium | fix now (D.12d): "collapsed" visible in the schematic and readout labels, with a short persistent qualifier (4 SGs lumped; no shrink/swell; not narrow-range). |
| 5 | medium | fix now (D.12b): persistent "unprotected inventory exercise" note by the level/feedwater controls naming the omitted low-low level reactor trip + AFW start and high-high level turbine trip + feedwater isolation. |
| 6 | medium | fix now (D.12d): mode-aware wording — "manual demand at zero/max" in MANUAL, saturation only in effective AUTO (plantStatus, readouts, events); log committed manual-demand changes (% max, kg/s; pending when paused). |
| 7 | medium | fix now (D.12a runtime: Reset Scram leaves a P-4 turbine trip latched as an operator turbine trip, and reset_turbine_trip is refused while actual admission > 0.5 % ("valves still closing"); D.12b UI: Reset Turbine Trip disabled until closed, showing "closing, n %"; help no longer promises closure from demand alone). |
| 8 | low | fix now (D.12b): "trip active; admission closed" below a documented tolerance; "reset pending" wording when frozen. |
| 9 | low | fix now (D.12b/D.12d): explanatory paragraphs derived from the shared status; paused SCRAM event "SCRAM selected; insertion pending on resume"; admission pending shown beside its slider. |
| 10 | low | fix now (D.12d): label priority in readouts; time-to-floor shows "> 1 h (near balance)" for long estimates. |
| 11 | low | fix now (D.12a adds `pzr_level` and `shutdown_position` to the frame; D.12d drives the pressurizer fill from pzr_level and shows a persistent "shutdown bank inserted — restart requires Reset Simulation" indication). |
| 12 | low | fix now (D.12b): P-9/P-4 wording scoped to representative Westinghouse plants. |
| 13 | low | fix now (D.12b): "100 % design" aligned with its 83.3 % tick; "Tracked demand" (AUTO) vs "Manual demand" (MANUAL); operator-facing wording for returning to AUTO. |
