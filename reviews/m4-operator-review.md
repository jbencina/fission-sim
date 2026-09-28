# Milestone 4 — independent operator review

## Summary

**Review date:** 2026-09-28. **Revision reviewed:** `93e46f7`
(`93e46f735be18ee0afa10bab17e34d041020b828`).
**Result: 0 high, 5 medium, 3 low findings.**

M4 is a useful **educational inventory-control demonstration**, not a
validated reproduction of indicated SG level or a protected feedwater-loss
transient. The small admission-ramp excursion, finite feedwater response,
and damped setpoint response are acceptable for that purpose. There is no
operator-realism reason to retune the gains just to make these traces look
more dramatic or to eliminate the post-trip offset.

Preserve what is working:

- Actual feedwater is a separate, continuous actuator state rather than an
  instantaneous identity with steam flow. A five-second lag is a reasonable
  illustrative seconds-scale response, explicitly not an equipment stroke test.
- Feed-forward includes **both turbine steam and dump flow**. The console
  now exposes actual/demanded feedwater and the signed inventory-flow mismatch.
- The steady design point and admission-ramp recovery are stable. The
  setpoint response has damped overshoot, not sustained hunting.
- Capacity limits and saturation telemetry are present; controller and
  actuator share their flow ceiling. Feedwater correctly cannot remove water.
- The console and plots explicitly identify **collapsed liquid fraction,
  four SGs lumped, no shrink/swell**. The domain messages distinguish model
  validity from plant protection. Those M3 review dispositions were worthwhile.

The principal corrections are to **operator meaning and control semantics**:
do not display an all-liquid turnover time as usable margin; do not imply
feedwater mode selection is bumpless; do not quietly offer unreachable normal
level targets; and label the new fault/post-trip exercises at the point of use.
Under the requested severity rule, none warrants “high”: each can be
adequately bounded for M4 by specific labeling, restricted controls, or a
clearly stated scenario purpose. This does not make the missing protection
acceptable in a later scenario advertised as a realistic protected response.

### Evidence and independence

- Read the M4 plan/review questions and Phase D outline, overriding
  `plan-amendments.md`, both M3 reviews **including dispositions**, the
  requested source/console/README sections, and M4 acceptance scenarios/tests.
- Read `reviews/validation/m4/report.md` and the supplied console transcript;
  opened all seven `dense/*.png` M4 plots and independently sampled the
  supplied `dense-data/*.npz` trajectories. These are the validator's
  trajectories, not a claim to have rerun its entire validation suite.
- Additional in-memory checks used the existing environment with
  `PYTHONDONTWRITEBYTECODE=1 uv run --frozen --no-sync python -`: reproduced
  the 64 s loss-of-feedwater endpoint and its displayed inventory cue;
  exercised actual console command parsing; measured manual→auto demand at
  the same plant state; followed the accepted `level 0.2` command to its
  validity limit; and repeated the 1,200 s trip/SCRAM case with BDF,
  `dense=True, max_step=0.5`.
- Public NRC PDFs [R1–R3] were retrieved and relevant text inspected in
  memory. Reference examples below are not a selected plant's licensing basis.
  Timing judgments not supported by a plant trace are identified as judgments.
- No fresh interactive-terminal session or full test-suite rerun was
  performed by this reviewer. No source, tests, docs, examples, or validation
  artifacts were edited, and no commit was made.

The dispositioned M3 issues concerning admission versus MW, aggregate
dump/relief, rod control, decay heat, SG geometry, and trip/reset behavior
are not reopened here. They are mentioned only where necessary to explain
new M4 inventory/control behavior.

## Findings

Paths and line numbers refer to the reviewed revision. References are
listed below; “operator-display judgment” denotes a design recommendation,
not a claim of a universal plant requirement.

| # | severity (high/medium/low) | file:line | finding | real-plant reference/experience | proposed change |
|---|---|---|---|---|---|
| 1 | medium | `src/fission_sim/physics/sg_secondary.py:560–563,595–606`; `examples/console.py:217–218,235–236`; `README.md:1723–1726` | **“Boil-off time” is not remaining usable inventory time.** It reads 133.3 s at design, but loss of feedwater reaches the surrogate floor about 54 s after the command. At `t=63 s`, level is 0.30208 and the cue still reads **73.1 s**, less than one second before the interpolated floor crossing. After SCRAM it becomes approximately `5.74e10 s`. The README's general “not a validated safety margin” qualification does not travel with the numerical display. | [R1] distinguishes indicated level and loss-of-heat-sink protection; [R3] requires a continuing shutdown heat-removal function. The calculation counts liquid below the model's usable band and assumes unchanged outflow; it is not a crew action clock. | Prefer `level_margin_low` and level/flow trends on the main display. If retained, label this diagnostic **“total liquid inventory / current steam outflow; not time to model limit or trip”**, with `n/a`/“outflow negligible” near zero flow. An optional separately named **model-limit trend estimate** must use inventory above the floor and stated flow/pressure assumptions, never a safety countdown. |
| 2 | medium | `src/fission_sim/control/feedwater_controller.py:325–348,401–403`; `examples/console.py:414–430`; `README.md:1328–1329` | **Feedwater transfers are not bumpless.** Manual mode freezes rather than tracks the PI state. After five seconds at zero manual demand, actual flow is 614.0 kg/s; selecting AUTO changes demand immediately from zero to **1,702.3 kg/s** at that same state. Flow remains continuous only because of actuator lag. Numeric manual selection is also a simultaneous mode change and demand change, not a hold-current-output transfer. A bare `feedwater` silently selects AUTO. | [R1] describes distinct manual/automatic feed regulating functions. Operationally a mode-only transfer should not unexpectedly reposition a regulating device; the specific example here is a direct model measurement, not a purported plant benchmark. Anti-windup at saturation is not manual-output tracking. | Document current commands as **non-bumpless overrides/resumption** now. For Phase D, provide an explicit manual/hold transfer that tracks the existing output and an automatic controller state that tracks manual output before transfer. Test output continuity in both directions after sustained manual operation and during actuator motion. Preserve intentional numeric demand steps. Require explicit `auto`; make bare `feedwater` show status/help. |
| 3 | medium | `examples/console.py:399–411`; `src/fission_sim/control/feedwater_controller.py:318–323`; `M3-M4-IMPLEMENTATION-PLAN.md:1908` | **Ordinary level commands accept targets beyond the model's usable range without warning.** Both `level 0.2` and `level 0.98` receive normal success acknowledgments. Independently, a fresh plant commanded to 0.20 reaches `sg_tubes_uncovered` at 110 s with its automatic controller still pursuing the target. The proposed Phase D range starts at 0.20 and would repeat the problem. | Operator-interface judgment: a normal regulating setpoint and a deliberate model-boundary experiment are different actions. The accepted command range is not an operating envelope, and finite/range validation alone does not establish a reachable target. | Constrain ordinary targets to a documented configurable band **inside** 0.30–0.95, allowing transient margin; reject or explicitly confirm out-of-domain experimental targets. Do not call that band a plant NR operating range. Warn that a stored setpoint does not control feedwater while manual override is selected. |
| 4 | medium | `scripts/validate_secondary.py:728–738`; `src/fission_sim/physics/domain.py:316–329`; `README.md:2249–2250`; `examples/console.py:429–430` | **The two new boundary exercises need their own unprotected-scenario labels.** “Loss of feedwater at power” runs to about 97.4% fission power at the floor; maximum manual feed reaches the overfill ceiling with no high-high isolation. The low-limit explanation and README are helpful, but the plot titles and command context do not say which expected automatic actions are absent; overfill lacks the corresponding protection explanation. | [R1] §11.1.3.1: low-low level initiates reactor trip/AFW; high-high initiates turbine trip, main-feed isolation and feed-pump trips in the reference system. [R2] also has an anticipatory low-level/flow-mismatch trip. | Label these **unprotected inventory-depletion/overfill experiments, reactor protection/AFW or high-high isolation absent**. State that the halt is neither a protective trip nor a calculation of actual damage onset. Explain the expected protected response beside each scenario. Model a genuine feedwater equipment failure separately from operator manual demand in M5; returning AUTO must not repair a failed pump. |
| 5 | medium | `tests/test_sg_level_plant.py:97–101`; `src/fission_sim/control/feedwater_controller.py:272–275,340–358`; `examples/console.py:215,233–234`; `README.md:2251` | **The post-trip result is bounded inventory with an uncontrollable residual, not recovery to setpoint or a realistic post-trip feedwater lineup.** Level ends at 0.516390, demand zero, `mode="auto"`, `saturated=True`; the test named “level_recovers” accepts this permanent offset. The console displays AUTO but omits saturation. The same ideal normal-power flow-feed-forward controller remains selected down to essentially zero steam flow, without a low-flow mode or feedwater-isolation logic. | [R1] §11.1.2 uses a different low-power feedwater arrangement in its representative plant, and §11.1.4 describes protection overrides. Real shutdown feeding supports ongoing heat removal, not merely normal-power three-element tracking at vanishing measured flows. | Call the test/result **“level remains bounded; zero-feed saturation leaves a persistent offset.”** Show **AUTO — ZERO-FLOW LIMIT / above target** and label continued low-power automatic operation as an L1 surrogate. Carry low-flow/manual-or-single-element behavior and protection overrides into M5 design. Do not introduce negative feedwater, a fictitious drain, or a gain change just to force 0.50. |
| 6 | low | `examples/console.py:28–30,269–270,424–430`; `README.md:1755`; `src/fission_sim/control/feedwater_controller.py:325–328` | **Manual fraction has a non-obvious denominator.** `feedwater 1` means 120% of design steam flow, not nominal full-power feed, and not a valve position. `feedwater 0.5` is 1,001.4 kg/s, or 60% design; design balance requires approximately 0.8333 of maximum. The acknowledgment says “of maximum,” but abbreviated help does not. | [R1] separates regulating-valve position, pump-speed control and measured feed flow. A flow-demand surrogate is acceptable for L1 if its units are explicit. | Label control and help **“fraction of maximum feedwater flow (default max = 120% design)”**. Show kg/s and % design alongside the manual demand. Do not draw a physical valve-position indicator from this fraction. |
| 7 | low | `examples/console.py:213–216,418–419,542–558`; supplied `console-operator-transcript.txt` | **Command acknowledgment, equipment snapshot and halt time can describe different instants.** The transcript shows an AUTO acknowledgment beside a MANUAL snapshot, and vice versa. At speed 60 it reports “stopped at 1260 s” after attempting the 1320 s endpoint. This particularly confuses interpretation of M4's short feed-loss margin. | Operator-display judgment: selected mode, effective mode, data age and event time must be distinguishable. A last-valid display time is useful but is not the limit-crossing time. | Mark command changes pending until the next snapshot, or refresh effective control indications consistently. Say **“last displayed valid state: …; violation detected on next advance”**; report the accepted invalid endpoint separately when available. Preserve the existing speed-1 recommendation for trip observation; do not advertise accelerated readout times as precise event times. |
| 8 | low | `scripts/validate_secondary.py:151–193`; `M3-M4-IMPLEMENTATION-PLAN.md:1895–1920` | **The M4 plots do not show the variables needed to explain level control.** They retain rod/admission panels but omit actual/demanded feedwater, flow mismatch, saturation, and a plotted level target. Autoscaling makes the 0.18-point admission excursion look comparable to much larger inventory transients. | [R1] describes the level/steam/feed signals a crew compares. Controller internals are secondary; actual inventory addition/removal and target are essential. | Add a feedwater-demand/actual/total-steam panel, level target, event markers, and saturation indication. Provide a fixed-range inventory view alongside a labeled zoom. Draw model-limit lines on boundary cases and distinguish them from future protection thresholds. Carry the dashboard list below into Phase D. |

## Scenario expectations versus model

Level percentages in this section are **100 × collapsed liquid volume
fraction**, not percent narrow-range or wide-range indication. Unless noted,
events start at `t=10 s`; reported extrema are sampled, not continuous-time
guarantees.

### 1. Steady design point and inventory accounting

**Expectation:** matched inlet/outlet flow, stable inventory, and no
continuing corrective motion at a balanced operating point.

**Model:** level remains 0.50 for 600 s; feedwater and steam are approximately
1,669.012 kg/s. The separate 80% admission conservation case changes shell
mass by **−3,149.6 kg** while conserving the integrated boundary flows.

**Assessment:** preserve both tests. They demonstrate that level is now a
dynamic inventory consequence, not enforced by perfect mass matching.
They do not calibrate a real SG's instrument span or operating inventory.

### 2. Ten percentage-point admission reduction

This is a **roughly two-minute admission ramp at five points/min**, not a
ten-percent instantaneous MW step.

**Crew expectation:** steam/feed mismatch calls for prompt feed reduction;
level trim acts more slowly. Real narrow-range level has an initial
**shrink contribution** as pressure rises and voids collapse. Level response
can reverse as inventory changes and the controller responds.

**Model:** level peaks at **0.5018016 at 100 s**, undershoots to **0.4994661**,
and ends at **0.5000020 at 1,800 s**. Sampled level stays within 0.0001 of
target from approximately 847 s onward. This is a maximum **0.1802
percentage-point** excursion, not 1.8 points or a 0.18-point NR excursion.

**Assessment:** stable, appropriately small inventory disturbance with a
minutes-scale trim. That is operationally credible as an **inventory-only
control exercise**. It is not possible to certify that amplitude as “the
range a crew sees” without geometry, void dynamics and instrument calibration.
A real NR trace could show appreciably more movement and initially the
opposite direction. Existing labels and README make this distinction well.
No gain change is requested.

### 3. Level-setpoint step, 0.50 → 0.55

**Crew expectation:** a modest setpoint adjustment produces a controlled
feedwater mismatch; the crew watches direction, rate, and margin rather than
expecting instantaneous level motion. A five-point **collapsed-volume**
increase is not the same amount of water as five points on a real NR span.

**Model:** the first target crossing is about **207 s after the command**;
level peaks at **0.559884 at 423 s**, approximately 6.9 minutes after the
command. Overshoot is **0.9884 percentage points of collapsed fraction**,
or 19.8% of the requested change. At 1,200 s level is **0.5499016**.
The sampled trace remains within ±0.001 of target from 968 s and within
±0.0005 from 1,036 s: “about 20 minutes settling” describes a small final
tail, not a 20-minute delay before feedwater responds.

**Assessment:** the response is slow and somewhat underdamped, but acceptable
for the declared 300 s-reset educational inventory trim. About one point of
overshoot does not itself indicate a bad control model. A crew would see
feedwater change within seconds and most level movement in the first few
minutes. Do not advertise the exact settling time as measured Westinghouse
controller performance or teach waiting 20 minutes to address a declining
level. The validator's independent PI calculation explains the trace; it
does not turn it into a plant benchmark.

### 4. Loss of normal feedwater at power

**Crew expectation:** a large feed/steam mismatch and adverse level trend
are apparent early. In a protected plant, applicable low-level/mismatch or
low-low-level protection initiates reactor trip, and AFW initiation is
verified. Plant-specific loss-of-feedwater/trip procedures govern response;
waiting for literal tube uncovering is not the normal sequence.

**Model:** setting manual demand to zero does not instantly stop actual flow.
The five-second lag leaves approximately **614 kg/s after 5 s** and
**226 kg/s after 10 s**. The first invalid one-second endpoint is
**64 s**, about **54 s after demand removal**, at level 0.297719,
`n=0.973899`, steam pressure 7.495 MPa, and negligible feedwater.
The electrical proxy rises to about 1,071 MW; it is not evidence that losing
feedwater is a permissible way to increase generation.

**Assessment:** the inventory-loss direction and rapid approach to the
surrogate floor are internally understandable. The inventory above the floor
is only part of the 222 t liquid inventory. The 133 s all-liquid cue is
therefore not an estimate of remaining useful heat-sink time. The endpoint
is neither a reactor trip nor a prediction that real tube uncovering occurs
54 s after a plant feed-pump trip. Label this as an unprotected all-SG
inventory experiment and retain the clear stop.

The validator's true 0.1 s stepping reaches its first invalid endpoint at
63.6 s, with a 0.1 s input-scheduling offset. Its interpolated dense-case
floor crossing is approximately 63.476 s, not exactly 64 s. The existing
agreement is adequate for this L1 timescale; do not report a whole-second
domain check as a root-localized protective actuation.

### 5. Maximum manual feedwater / overfill

**Crew expectation:** feed exceeds steam removal, inventory rises, and
high-level alarms precede high-high protective actions. The representative
Westinghouse high-high function isolates main feed, trips feed pumps and the
turbine; reactor-trip consequences depend on the applicable turbine-trip
protection logic and power. Manual control does not normally defeat these
protection overrides.

**Model:** manual 1.0 commands **2,002.815 kg/s**. At the **543 s absolute**
halt, about **533 s after the command**, outflow is approximately
1,637.0 kg/s and excess inflow is 365.8 kg/s. Level reaches 0.950509 and
fission power is approximately 1.00660.

**Assessment:** a minutes-scale overfill is coherent with that sustained
excess inflow and the assumed inventory. It is not a prediction that a
protected plant can continue feeding until “95% NR,” nor a validated time to
moisture carryover. The high-limit message correctly calls the threshold a
surrogate; add the missing expected high-high protection explanation.

### 6. Turbine trip plus SCRAM with automatic feedwater

**Model:** level rises immediately, reaching **0.520867 at 18 s**, with a
second small hump before settling at **0.516390**. Shell mass gains
approximately **4.301 t**. At 1,200 s, demand is zero, actual feedwater is
negligible, and dump flow is only about `3.94e-6 kg/s`. The last 300 s of the
validator's trace change level by approximately `3.1e-8`: this is not an
unfinished slow recovery to 0.50.

**Assessment:** fast steam cutoff plus slower feedwater reduction explains
the initial inventory gain. Do not describe it as simulated indicated-level
shrink/swell. Saturation at zero flow is a legitimate loss of control
authority; no gain setting can make a one-way inlet withdraw water.
The back-calculation integral's positive final value is not, by itself,
evidence of runaway windup.

**What a crew would see/do conceptually:** verify the trip and required
feedwater/heat-sink actions, compare available level channels and trends, and
control feeding to the applicable post-trip band while maintaining heat
removal. Real NR level can initially shrink even while total inventory is
increasing. A bounded indication modestly above target is not a reason to
invent a drain or dump steam solely to force an exact 50% reading.
In a real shutdown, continuing decay-heat removal produces continuing
secondary demand; the model's near-zero-outflow endpoint lacks that mechanism.
This is the **new M4 consequence** of the already-dispositioned M3 heat-source
limitation, not a request to reopen it as an M4 physics defect.

The representative plant uses manual bypass-valve control below about
20% power [R1]; other plants have different low-power/single-element
arrangements. The important requirement is to identify the model's ideal
all-power AUTO as a surrogate, not impose that particular 20% setting on
every PWR.

### 7. Manual/automatic feedwater and console use

The supplied recovery exercise works: AUTO restores feed and reverses the
declining level. It does **not** demonstrate bumpless transfer. At the
five-second transfer point, command jumps to 1,702.3 kg/s while flow is
614.0 kg/s; initial flow slope changes to approximately **+217.7 kg/s²**.
The next five-second endpoint is approximately 1,316.1 kg/s. This is an
intentional recovery demand after a large mismatch, not a mode-only transfer.

The commands are short and discoverable, nonfinite numeric entries are
rejected, and actual versus demanded flow is visible. Improve denominator,
mode-transfer and pending-command wording rather than adding many new
operator inputs. Distinguish a physical feedwater failure from manual zero
flow when a failure library is introduced.

The validation's 0.5 s maximum integration step and one-second samples are
reasonable for the five-second actuator and minutes-scale trim. Preserve
finer early-trip evidence for fast peaks. Console speed 60 skips a minute
between observations—longer than the default feed-loss margin—and is useful
for a known settling tail, not observation or intervention in a feed-loss
exercise.

## Dashboard (Phase D) must show

1. **Honest level identity.** For M4 use one clearly labeled **“SG collapsed
   liquid fraction — four SGs lumped; no shrink/swell; not an indicated
   level”** gauge and trend. Show fraction or percent with the same units
   on target and actual. Do not draw four independently instrumented SGs
   from this single state.
2. **Future NR and WR have different jobs.** Once instrumentation is modeled,
   make **narrow-range level** the primary normal feedwater-control display,
   and provide **wide-range level separately** for broader inventory and
   loss-of-heat-sink assessment. WR is not merely a zoomed-out NR axis and
   collapsed fraction is not automatically WR. [R1] places the reference
   NR lower tap **above the U-tube bundle**, illustrating why 0% NR does not
   mean an empty SG and why model 0.30 cannot be called an NR trip setting.
3. **Target, error, trend, and model margin.** Show `level_setpoint`,
   `fw_ctrl.level_error`, `level_margin_low`, and upper validity margin
   (`0.95 − level_sg`, derived if necessary). Mark 0.30/0.95 as **model
   boundaries**, visually distinct from alarms/protection. A normal-color
   band is a chosen educational operating band, not an assurance of safety.
4. **Feedwater demand and actual delivery.** Show `m_fw_demand`, actual
   `m_fw`, capacity `m_fw_max`, manual fraction with its denominator, and
   AUTO/MANUAL state. Add **zero-limit / maximum-limit** status using
   saturation plus demand. A diagnostic integral view is optional; the
   crew-facing message is loss of control authority, not the integral number.
5. **Steam and inventory-flow balance.** Show turbine steam, dump/relief
   steam, total outflow, and **feed − total outflow** with an explicit sign.
   Keep a short flow trend next to the level trend. Label quantities as
   four-SG aggregate flows, not per-SG values.
6. **Thermal/heat-sink context.** Steam pressure, dump available/flowing,
   `T_avg`, `T_ref`, signed temperature error, fission power versus SG heat
   removal, admission demand/actual, and gross electrical proxy. Preserve
   existing primary pressure, pressurizer level, rods, and effective trip
   state. Do not imply zero fission power means zero real shutdown heat.
7. **No reassuring boil-off countdown.** Prefer inventory margin. If the
   ratio is retained, demote it to a qualified diagnostic per finding 1;
   distinguish zero-feed hypothetical turnover from a net-depletion trend.
8. **Control availability and pending changes.** Explicit mode-transfer
   controls, output matching, selected versus effective state, setpoint
   inactive in manual, failure/override status, and—when M5 exists—main-feed
   isolation and AFW demand versus delivered flow.
9. **Time and events.** Simulation time, speed, sample age, command/event
   timestamps, first-out protection cause, and model-limit halt state.
   Retain simulation-time history fine enough to see the first 30 seconds
   even when the display is accelerated. Show target and event markers on
   charts and a readable inventory-scale view alongside detailed zoom.

Items already resolved by M3—effective P-4 trip indication, actual rods
versus demand, and explicit re-admission after signal release—remain
requirements, not new M4 findings. Phase D must not regress them.

## M5 alarms/trips

### Minimum operator-facing protection slice

1. **SG low-level alarm and adverse feed/steam-mismatch alarm.** Annunciate
   before the surrogate validity floor. Identify falling inventory,
   inadequate delivered feed, and unavailable equipment rather than relying
   on a level-only “green/red” display.
2. **SG low-low-level reactor trip and AFW initiation.** Separate the
   protective signal, latched reactor-trip consequence, AFW start command,
   and actual AFW delivery. In the reference design the initiating condition
   is voted low-low level in **any one SG**, not the average of four. M4
   can only represent a lumped condition; it cannot yet validate single-SG
   failure discrimination or voting.
3. **Anticipatory low-level plus steam/feed-flow-mismatch trip.** Include
   this in the design decision, not only a last-ditch low-low threshold:
   [R1–R2] describe this function. Model the required coincidence rather than
   tripping on every harmless brief mismatch.
4. **SG high-level alarm; high-high turbine trip and main-feedwater
   isolation/feed-pump trip.** Protective overrides take precedence over
   manual demand as well as AUTO. Annunciate each consequence and effective
   isolation state. The turbine-trip→reactor-trip consequence follows the
   selected plant/generic protection configuration, not a new universal rule
   invented for level control.
5. **AFW automatic and manual initiation with delivery feedback.** Cover
   total loss of main feedwater and low-low level. Add other representative
   initiating conditions—such as safety injection or loss of applicable
   electrical supply—only when their source signals/equipment exist.
   [R3] also discusses AMSAC; do not claim ATWS mitigation merely because
   a normal low-level start signal is implemented.
6. **Main-feed isolation and low-power control state.** Decide explicitly
   how reactor trip/low temperature and other implemented protective signals
   override the normal controller. [R1] §11.1.4 identifies these relationships.
   A zero PI demand is not the same thing as a positively isolated feed train.
7. **Latching, reset permissives, hysteresis and annunciation.** Alarm
   acknowledgment must not reset a trip. Level recovery must not silently
   re-open isolated main feed or restore the previous high manual demand.
   Include first-out cause, manual/automatic initiation, pump start failure,
   insufficient delivered AFW, and source availability as those states are
   introduced. AFW must not chatter off as soon as level crosses its start
   threshold.

### Trip points: reference examples, not model defaults

The verified NRC reference has the following **narrow-range instrument**
settings [R1–R2]. They are useful evidence that real protective actions occur
before the modeled extreme inventory conditions, not values to paste into
`level_sg`:

| Reference function | Example in the cited Westinghouse manual |
|---|---|
| Low-low SG level | 11.5% NR; two of three channels in any one SG; reactor trip and AFW initiation |
| Low level coincident with flow mismatch | 25.5% NR with steam flow exceeding feed flow; the reference also specifies separate channel/coincidence logic |
| High-high SG level | 69% NR; two of three channels in any one SG; turbine trip, main-feed isolation and main-feed-pump trip |

The example normal level program reaches approximately **44% NR**, not the
model's 50% collapsed fraction. All those values depend on the calibrated
span and design; none establishes a universal PWR alarm or trip point.
Select a reference plant and use its current FSAR/Technical Specifications
before claiming plant-specific settings.

For an expressly generic **L1 M5**, choose and label configurable surrogate
protection thresholds inside the valid inventory band. Their ordering should
be:

```text
0.30 model floor < low-low < low warning < normal target
normal target < high warning < high-high < 0.95 model ceiling
```

Ordering alone is insufficient: demonstrate dynamic margin for detection,
trip/feed-isolation response, and AFW delivery. Do not convert the reference
11.5%/69% NR directly to collapsed fractions, use the 0.30/0.95 validity
limits as protective setpoints, or silently promote Phase D's proposed
0.4–0.6 display band into a licensing setting.

### M5 scenario acceptance expectations

- **Protected loss of feedwater:** show mismatch/level warning, the specified
  protective actuation, reactor/turbine response, main/auxiliary feed status,
  and **delivered** AFW supporting a continuing heat sink. Preserve the
  unprotected M4 case separately. A pump icon changing color is not evidence
  of heat-removal recovery.
- **Protected overfeed:** show alarm, high-high actuation, reduction of actual
  main-feed flow despite a retained maximum manual command, and inventory
  response that remains inside the validity ceiling. Test subsequent
  reset/transfer without silently restoring the old overfeed command.
- **Post-trip level management:** distinguish normal feed, low-flow control,
  isolation, AFW and heat removal. Retain the zero-flow saturation case as a
  control-authority demonstration, not evidence of indefinite safe shutdown.
- **Timing matters:** [R3]'s reference AFW design permits up to 60 s from
  initiation to rated delivery; that is an example requirement, not a
  universal delay to copy. It is already comparable to this model's entire
  unprotected feed-loss margin. Evaluate the combined trip/heat-input/AFW
  trajectory rather than guessing an acceptable start delay from the 133 s
  turnover cue or assuming an instantaneous full-capacity AFW source.
- **Heat-source scope:** a first M5 logic/actuator slice may retain the
  explicitly labeled no-decay-heat limitation. A claim that AFW provides
  realistic sustained post-trip cooling needs the previously deferred
  residual heat source and an appropriate auxiliary-feedwater boundary,
  rather than simply reusing an ideal full-power feedwater supply.

## Reference basis

- **[R1] NRC Technical Training Center, Westinghouse Technology Systems
  Manual, §11.1, Steam Generator Water Level Control System**, Rev. 0706:
  [ML11223A293](https://www.nrc.gov/docs/ML1122/ML11223A293.pdf).
  Printed pp. 11.1-1–3 describe power range, programmed level, flow/level
  control and shrink/swell; pp. 11.1-4–5 and Fig. 11.1-4 describe instrument
  spans and protection; p. 11.1-6 describes flow indications and overrides.
  In this manual **Fig. 11.1-2** illustrates shrink/swell, while the
  instrument geometry is **Fig. 11.1-4**.
- **[R2] Same manual, §12.2, Reactor Protection System — Reactor Trip
  Signals**, Rev. 0109:
  [ML11223A301](https://www.nrc.gov/docs/ML1122/ML11223A301.pdf).
  §§12.2.3.13–14, printed p. 12.2-7, and Table 12.2-1 distinguish
  anticipatory low-feed-flow/low-level protection from low-low-level trip,
  including the reference coincidence logic.
- **[R3] Same manual, §5.8, Auxiliary Feedwater System**, Rev. 1208:
  [ML11223A232](https://www.nrc.gov/docs/ML1122/ML11223A232.pdf).
  Printed pp. 5.8-1–2 describe the heat-removal purpose and example delivery
  requirement; pp. 5.8-4–5 list automatic initiation conditions. Its
  particular equipment lineup and setpoints are not universal four-loop
  plant requirements.

## Disposition

Triage by the orchestrator (2026-09-28). No high-severity findings, so M-gate 3 has no open high item.

| # | Severity | Disposition |
|---|---|---|
| 1 | medium | fix now (same as physics #1): new `time_to_level_floor_s` telemetry shown in the console next to a relabelled boil-off cue. |
| 2 | medium | fix now (M4.7.1 controller tracking in manual → bumpless manual→auto; M4.7.3 console: a bare `feedwater` no longer silently selects AUTO; `feedwater auto` is explicit). |
| 3 | medium | fix now (M4.7.3): console `level` accepts an ordinary band inside the validity limits (0.35–0.90) and explains the limits otherwise. Carried into Phase D notes (plan's 0.2–0.9 range must shrink). |
| 4 | medium | fix now (M4.7.3 plot titles/console acknowledgements; M4.7.0 README): label loss-of-feedwater and overfill as unprotected inventory-boundary exercises; name the omitted low-low level reactor trip/AFW start and high-high level turbine trip/feedwater isolation. |
| 5 | medium | fix now (M4.7.3 console shows controller saturation) + document (M4.7.0 post-trip residual; no low-power feedwater mode). Low-flow feedwater mode and isolation logic deferred to M5 roadmap. |
| 6 | low | fix now (M4.7.3): help/acknowledgement say "fraction of maximum feedwater flow (max = 120 % design)", with kg/s and % design. |
| 7 | low | fix now (M4.7.3): halt message says "last displayed valid state …; violation detected on next advance". Pending-command indication deferred to Phase D. |
| 8 | low | fix now (M4.7.3): validation plots add a feedwater demand/actual/steam panel and a level-target line on level panels; model-limit lines on boundary cases. |
