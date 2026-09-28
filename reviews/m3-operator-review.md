# Milestone 3 — independent operator review

## Summary

**Review date:** 2026-09-28. **Baseline reviewed:** `0724977`.
**HEAD at completion:** `f61b7d9`. The intervening README/test-comment commit
was inspected; it changes no physics, controls, or console behavior. File/line
references below use the completion revision.
**Result: 0 high, 6 medium, 3 low findings.**

M3 is a useful educational demonstration of primary/secondary power mismatch,
with credible **directions** of pressure, temperature, and automatic rod response.
Preserve the steady design point, rate-limited admission changes, hot-coolant
rod insertion, approximately two-second full-travel shutdown-bank insertion,
SCRAM-to-turbine-trip connection, and bumpless console auto→manual transfer.
The automatic load-reduction trace settles without sustained rod hunting.

The important qualifications are operator-facing. “Load” is admission rather
than regulated MW; “SG level” is collapsed liquid volume rather than a
narrow-range instrument; and the full-power turbine-trip-only case is an
**unprotected experiment**, not a normal Westinghouse trip. After SCRAM, the
plant reaches approximately the expected no-load temperature, but does so
through a pressure-relief surrogate with no decay heat, not a complete
post-trip temperature-control and heat-removal system.

**Recommendation on P-9:** do not make a full protection-system implementation
a condition of M3. Label the unprotected case explicitly now, including at the
console command and plot, and offer the existing simultaneous turbine-trip /
SCRAM case as the protected-response illustration. Implement configurable,
latched protection in its planned milestone. For units using P-9, turbine trip
above approximately 50% reactor power initiates reactor trip; this is not a
universal Westinghouse threshold—other configurations use P-7 at approximately
10% [R4]. Do not call the current no-SCRAM experiment a validated ATWS scenario.

No finding requires a high rating under the requested rule: the limitations
can be bounded honestly by specific labels, corrected indications, or a clearly
restricted scenario purpose. A general “educational simulator” disclaimer alone
does not communicate these distinctions.

### Evidence and scope

- Read the specified components, plant wiring, console, relevant README
  sections, M3 acceptance tests/helpers, plan, and overriding amendments.
- Read `reviews/validation/m3/report.md`, inspected the operational dense PNGs,
  and independently sampled the supplied NPZ trajectories. These are the
  validator's trajectories, not a claim that this review reran its full suite.
- Read the supplied pseudo-terminal console transcript. Additional in-memory
  `PYTHONDONTWRITEBYTECODE=1 uv run --frozen python -` checks exercised the real
  plant and console functions: automatic admission reduction, mode transfer,
  SCRAM/P-4, SCRAM release, no-load-reference variation, automatic-mode turbine
  trip, and secondary-domain messages. No new full interactive-terminal run
  or repository-wide test run was performed.
- Repeated the first 70–80 seconds of SCRAM response with `max_step=0.1 s`;
  checked sampled snapshots. Reference documents below were fetched from the
  NRC and relevant PDF text inspected in memory.
- Only this review file was written by the reviewer; no implementation,
  tests, documentation, examples, or validation artifacts were edited.

## Findings

References [R1]–[R4] are identified at the end. They describe representative
Westinghouse systems, not the licensing basis of a particular four-loop unit.

| # | severity (high/medium/low) | file:line | finding | real-plant reference/experience | proposed change |
|---|---|---|---|---|---|
| 1 | medium | `README.md:187-192,1184-1191`; `scripts/validate_secondary.py:486`; `examples/console.py:200-203`; `src/fission_sim/plant.py:226-248` | **The turbine-trip-only case is numerically described but insufficiently identified as unprotected.** From full power it leaves 94.1% fission power feeding the lumped dump; with automatic rods selected, automatic action is suspended, not a runback to no load. “Without SCRAM” alone does not explain that an expected automatic reactor trip is absent. | [R4], turbine-trip reactor-trip function and P-9/P-7 distinctions. [R2], limited condenser-dump capacity and load-rejection capability. | Label the case **“Unprotected turbine trip: automatic reactor protection omitted; ideal feedwater and combined dump/relief available.”** State the expected protected response and plant-specific threshold. Add this warning to console help/acknowledgment, README scenario text, and plot title/caption. Keep the experiment separate from the simultaneous-trip illustration; defer actual configurable protection logic to its milestone. |
| 2 | medium | `src/fission_sim/physics/turbine.py:430-447`; `README.md:227,1184-1191`; `tests/test_secondary_plant.py:142-156` | **The correct-looking no-load endpoint must not be presented as proof of realistic post-trip control or cooling.** At 600 s, `T_avg=564.5992 K`, near `T_ref=565 K`, but dump flow is only 0.0056 kg/s. Changing only the no-load reference to 560 or 570 K leaves the endpoint unchanged. The dump never reads `T_avg` or `T_ref`; the endpoint follows `T_sat(7.6 MPa)` as modeled heat input vanishes. | [R2] distinguishes temperature-controlled trip/load-rejection dumping from steam-pressure control and describes removal of stored energy **and decay heat**. Its representative condenser dump passes 40% full-power steam flow, not the model's combined-path design flow. | Attach a scenario/readout caveat: **“Pressure-only combined dump/relief surrogate; shutdown endpoint is not active Tavg regulation; decay heat omitted.”** Preserve the near-565 K default rather than tuning it merely to eliminate the 0.4 K offset. Later separate condenser dump, atmospheric relief/safety action, availability/permissives, and residual heat before claiming realistic post-trip cooling. |
| 3 | medium | `scripts/validate_secondary.py:478-483`; `examples/console.py:24-25,148,281-293`; `src/fission_sim/physics/turbine.py:425-447` | **Operator-facing “load” still suggests an MW setpoint.** The README correctly distinguishes admission, but plot titles say “100% to 90% load” and the console shows `load=0.900`. Manual rods leave approximately 962 MW, not the 891 MW implied by a 10% reduction from 990 MW. `T_ref` also follows admission, not independently measured turbine power. | [R1], temperature/power-mismatch control uses turbine impulse pressure as a load indication. [R2], load-change capability concerns plant power, not an arbitrary fixed valve-position change. | Use **“turbine admission demand/actual”** consistently in captions and readouts; show gross MW separately. Describe these tests as **10 percentage-point admission reductions at 5 percentage-points/min**. Label the admission-based temperature program as an L1 proxy. A later MW governor and turbine-power signal can support a genuine 10% load-demand exercise. |
| 4 | medium | `examples/console.py:133,147`; `scripts/validate_secondary.py:163-165`; `src/fission_sim/physics/sg_secondary.py:18-21,509-512` | **The generic level label hides a qualitatively important instrument limitation.** Level rises from 50% to 50.50% in the manual reduction and 51.08% in turbine trip. That is collapsed liquid volume at changing saturation conditions, not evidence that real indicated SG level rises during the initial steam-demand collapse. The source/README caveat is good, but it does not travel with the display. | [R3], shrink/swell, three-element control, and distinct narrow-/wide-range instruments. Rising pressure and loss of boiling voids produce an initial shrink contribution; feed/steam mismatch and subsequent control actions can reverse the later trend. | Label every M3 level plot/readout **“SG collapsed liquid fraction — no indicated-level shrink/swell.”** State that four SGs are lumped into one volume. Do not present 50% as a calibrated narrow-range setpoint, or map future narrow-range alarms directly onto this fraction. M4 level feedback alone will not create missing void/instrument dynamics. |
| 5 | medium | `examples/console.py:122-150`; `src/fission_sim/physics/turbine.py:518-525`; `src/fission_sim/control/tavg_controller.py:338-348`; `M3-M4-IMPLEMENTATION-PLAN.md:1906` | **The status line confuses selected commands with actual equipment/control state.** Confirmed: automatic rods at 0.3931 still show `rod=0.5000`; SCRAM-only closes the turbine while the status says `trip=OFF`; after turbine trip it still says `rods=auto` although `acting=False`. Phase D proposes a turbine-trip indication sourced from command state, which would repeat the P-4 ambiguity. | [R1], demand versus rod-position indication; [R4], reactor trip actually trips the turbine. A crew must distinguish mode selected, automatic action available, trip cause, and physical response. | Display actual rod position, active rod demand, and any retained manual command under separate names. Derive effective turbine-trip status from `turbine.trip_active`, with explicit-trip/SCRAM cause shown separately. Show **AUTO ACTIVE / AUTO SUSPENDED / MANUAL** using `tavg_ctrl.acting`. Carry these distinctions into Phase D and test SCRAM-only indication. Preserve the working auto→manual synchronization. |
| 6 | medium | `examples/console.py:196-207`; `src/fission_sim/physics/turbine.py:340-354,390-399` | **Clearing a trip signal doubles as immediate re-admission toward the old demand.** After a 600 s SCRAM hold, console `r` clears effective turbine trip without a separate turbine-reset action; admission reaches 0.02499 and modeled electrical output approximately 26.9 MW after 30 s. Likewise, `untrip` resumes the previous admission demand when SCRAM is absent. This is a sandbox signal release, not a plant restart/reset sequence. | [R4] bases P-4 on reactor-trip-breaker status. Real trip reset, rod-drive restoration, turbine valve/speed control, and generator synchronization are distinct functions; their detailed sequencing is plant-specific and absent here. | At minimum label `r`/`untrip` as **idealized signal releases that resume the retained admission demand**, not reactor/turbine restart. Prefer keeping admission demand at zero or retaining a turbine-trip latch until an explicit re-admission action. Phase D must not make “reset trip” silently restore an old high demand. No full startup model is requested for M3. |
| 7 | low | `src/fission_sim/control/tavg_controller.py:63-84,196-206`; `README.md:1335-1344,1528` | **The numerical endpoints are recognizable, but the schedule is not a faithful Westinghouse controller.** It lacks lock-up hysteresis and power-mismatch anticipation, ramps speed immediately above the deadband, and uses continuous position instead of discrete steps. The retained manual actuator limit of 1% travel/s is about 137 steps/min on the same 228-step scale, above the stated automatic maximum. | [R1], §§8.1.4.1–8.1.4.5: representative control starts at 1.5°F error, stops at 1°F, uses 8 steps/min over the small-error region, and reaches 72 at 5°F; it also includes power-mismatch compensation. | Keep the stable L1 settings, but describe **±0.8 K** explicitly and list the omitted hysteresis, minimum-speed plateau, step quantization, and anticipatory signal. Keep manual-motion timing labeled illustrative. Add hysteresis/step realism only when needed for the next fidelity level; do not retune a stable controller solely to match one representative manual. |
| 8 | low | `src/fission_sim/physics/domain.py:263-291`; `README.md:208` | **Domain messages are largely understandable, but the low-pressure explanation blurs a guard margin with actual flashing.** At 2.90 MPa the default 500 K feedwater is still liquid; its saturation pressure is approximately 2.64 MPa. Also, neither the 12 MPa ceiling nor dry/solid termination is a protection setpoint or a declaration of safe operation below it. | Saturation-property distinction already established in the amendment and validator. [R3]/[R4] distinguish operating indications and protective functions from the mathematical edge of a model. | Say **“Below the model's 3.00 MPa guard band; approaching the configured feedwater flashing boundary (about 2.64 MPa at 500 K).”** For a custom temperature, use its configured threshold. Retain plain-language “boiled dry” / “filled solid,” and add **“simulation validity limit, not plant protection.”** Avoid implying the constant-UA model remains operationally adequate until every drop is gone. |
| 9 | low | `examples/console.py:137-175,387-405`; `scripts/validate_secondary.py:155-161` | **The secondary transient is hard to follow on the current console.** There is no dump-flow indication, feed/steam comparison, explicit temperature error, or persistent admission-demand display. The status line is already about 229 characters before a long message, despite the 92-character layout; wrapped lines compromise redraws. At `--speed 60`, each displayed sample skips a minute of plant time. The pressure/dump plot also lacks a combined visible legend. | Operator-display judgment: heat-sink status and trends, not just final values, explain a load rejection. A 1 Hz display is useful at normal speed; one-minute snapshots are not a first-30-seconds trip display. | Split controls and secondary readouts into terminal-width-aware rows; show dump flow, actual/demand admission, signed temperature error, and flow mismatch. Add a visible pressure/dump legend and use full signal labels. Recommend speed 1 for trip observation; retain higher-rate simulation-time histories/event timestamps when accelerated, rather than demanding faster integration solely for UI refresh. |

## Control settings: what a crew would recognize

- **5%/min:** recognizable as a representative automatic load-following
  design capability [R2], not a universal normal operating ramp permission at
  every power level. The code's `8.33e-4/s` is 4.998 percentage-points/min,
  making a ten-point change take approximately 120 s plus the governor tail.
  It limits admission, not measured MW. The scenario's ramp and the console's
  step in demand both produce finite actuator motion.
- **Deadband:** `0.8 K` is **±1.44°F**, approximately the familiar ±1.5°F
  pickup threshold, not a 1.5°F total-width band. A small final error is normal.
  Actual representative circuitry has hysteresis and a compensated total-error
  signal; this model uses temperature error alone [R1].
- **8–72 steps/min:** the implemented values give approximately
  **7.93–72.50 steps/min** on the assumed 228-step stroke. That is a suitable
  L1 scale: about one step every 7.5 s at minimum and every 0.83 s at maximum.
  Maximum automatic demand is approximately 0.53% full travel/s. This should
  not be conflated with the faster illustrative manual actuator.
- **Transfers and trips:** the tested console auto→manual transfer changes
  actual rod position by zero over the following one-second step. Preserve
  that behavior. Holding automatic rod demand during a trip avoids an
  inappropriate recovery demand in this simplified model, but a blanket
  turbine-trip hold is not a complete account of every plant's below-P-9
  control logic.

## Scenario-by-scenario expectations versus model

Unless stated otherwise, numerical results below are the supplied dense
trajectories, whose event/ramp starts at `t=10 s`. Pressures are absolute.
Level percentages denote the model's **collapsed volume fraction**, not a
calibrated SG level indication.

### 1. Design steady state; steady energy balance

**Expectation:** nuclear/thermal power, gross electrical output, temperature
program, steam pressure, and feed/steam flows balance. No continuing rod
motion or dump flow is needed.

**Model:** `n=1`, `T_avg=T_ref=583 K`, `P_steam=6.89918 MPa`, rods at 0.5,
level 50%, and 990 MW remain steady through 600 s. The shorter energy-balance
case has the same operating point.

**Assessment:** good baseline. The 50% lumped rod position and 50% liquid
fraction are initialization choices, not a claimed full-power rod-bank lineup
or a plant-specific narrow-range level calibration.

### 2. Ten-point admission reduction, rods manual/fixed

**Expectation:** reducing turbine steam demand initially raises steam pressure,
reduces primary-to-secondary heat transfer, and warms the primary.
`T_ref` decreases, so `T_avg − T_ref` becomes positive. Negative temperature
feedback reduces fission power, but without manual rod insertion there is no
reason for Tavg to return to its program. Real indicated SG level has an
initial pressure/void-collapse **shrink** contribution; slower feedwater
response and inventory imbalance affect the subsequent trend.

**Model:** admission reaches 0.9 in approximately two minutes. At 1500 s,
`n=0.971936`, `T_avg=587.836 K`, `T_ref=581.2 K`, error **+6.636 K**,
`P_steam=7.483795 MPa`, level **50.49975%**, and rods remain at 0.5.
No dump opens. Gross electrical output bottoms near 942.8 MW then recovers
to 962.2 MW as pressure restores much of the steam flow.

**Assessment:** the thermal/pressure/error directions are coherent for this
fixed-admission experiment. The endpoint is **not** a real 10% MW reduction,
and the slight liquid-fraction rise is **not** a prediction of indicated
shrink/swell. Leaving rods untouched for 25 minutes is a feedback-demonstration
condition, not an example of an operator maintaining the temperature program.

### 3. Ten-point admission reduction, rods automatic

**Expectation:** an initial positive temperature mismatch demands rod insertion;
power declines and Tavg approaches the reduced reference. Steam pressure may
rise before the reactor follows. Pressure need not return exactly to its
full-load value. For a modest controlled ramp, sustained dumping is not
expected when rod control can accommodate the change. Indicated SG level
initially reflects shrink and flow mismatch, then feedwater control restores
its applicable program.

**Model:** first sampled rod insertion occurs at `t=42 s`, approximately
32 s after the ramp starts, when temperature error crosses 0.8 K.
`T_avg` peaks at 583.560 K; maximum positive error is 1.335 K.
`P_steam` peaks at 7.024807 MPa, then settles at 6.976180 MPa with no dump flow.
At 1800 s, `T_avg=581.4878 K`, error **+0.2878 K**, rods **0.393108**,
`n=0.909533`, and gross output **900.44 MW**. Level peaks at **50.1077%**
and settles at **50.0661%**. No sustained late-time rod motion is visible.

**Assessment:** credible, stable **L1 temperature-only control** behavior;
do not “fix” the residual temperature error merely because it is nonzero.
The delayed initial rod response is consistent with the deliberately omitted
power-mismatch anticipation [R1]. The nearly flat level is not proof of a
well-tuned real feedwater controller: M3 makes inflow equal outflow by identity.

### 4. Turbine trip without reactor trip

**Expectation in the representative protected plant:** above the applicable
turbine-trip/reactor-trip threshold, turbine trip initiates reactor trip.
Steam pressure and temperature mismatch initially rise as the turbine heat
sink disappears; rods insert on reactor trip and available dumps remove
stored/residual heat. Real SG level initially shrinks, with subsequent behavior
depending on heat release, dumping, and feedwater actions. There is no
credible normal full-power protected endpoint at 94% fission power and zero MW.

**Model's deliberately unprotected experiment:** admission collapses,
`T_ref` approaches 565 K, pressure peaks at **8.172064 MPa**, and the combined
dump/relief carries approximately **1587 kg/s** at the endpoint. At 600 s,
`n=0.941044`, `T_avg=593.160 K`, error **+28.160 K**, level **51.08372%**,
and gross electrical output is effectively zero. Rods remain at 0.5.
A separate automatic-mode run gives the same endpoint with
`rod_auto=True`, `acting=False`.

**Assessment:** useful for illustrating loss of turbine heat removal under
explicitly artificial boundary conditions, not a normal trip response.
The console transcript trips after an automatic reduction, rather than from
full power: it consequently settles near `n=0.8566`, `T_avg=590.61 K`,
`P_steam=8.119 MPa`, with rods held near 0.3931. These results are consistent
with different initial conditions, not conflicting validations.

### 5. SCRAM alone, with P-4 turbine trip

**Expectation:** reactor trip gives rod insertion and turbine trip; the turbine
does not continue drawing full-load steam. The initial pressure/temperature
transient is followed by cooling toward a no-load temperature near
**557°F / 565 K**, with a continuing heat sink required for residual heat.
The post-trip display should support verifying rod insertion, falling neutron
power, turbine trip, secondary heat removal, primary pressure, and SG inventory.
It must not imply natural circulation is demonstrated by this constant-flow
primary model.

**Model:** P-4 works. `trip_active=True` while the explicit `turbine_trip`
external remains false. Steam pressure peaks at **7.853353 MPa** at `t=19 s`,
with a **704.75 kg/s** dump pulse. `T_avg=565.093 K` at `t=60 s`; by 600 s
it is **564.5992 K** (approximately 556.61°F), error **−0.4008 K**.
Pressure approaches 7.600002 MPa and level settles at **50.59871%**.
At that time dump flow is only **0.0056 kg/s** and SG heat transfer
approximately **9.7 kW**.

**Assessment:** correct trip direction and a recognizable no-load temperature
anchor. **No**, this does not establish that a real steam-dump temperature
controller holds the plant there. Independent runs with no-load references
560, 565, and 570 K all reached the identical 564.5992 K endpoint.
It is the pressure/saturation equilibrium of a model without decay heat.
Do not teach that secondary cooling/feedwater becomes unnecessary a few
minutes after reactor trip. Main/auxiliary feedwater sequencing and associated
trip actions are also absent, so this is not an E-0 procedure simulation.

### 6. Simultaneous turbine trip and SCRAM

The trajectory agrees with SCRAM alone through their common interval, as it
should: the explicit turbine-trip signal adds no separate closure once P-4
is active. By 900 s, temperature is still approximately 564.5991 K, but dump
flow is only **0.000138 kg/s**. The quoted minimum primary subcooling of
20.196 K demonstrates staying inside this model's liquid-primary assumption,
not real-plant safety acceptance.

Use this as the protected-trip **illustration** rather than the unprotected
case, while explicitly retaining the decay-heat, dump-control, and level
limitations. Both signals are scheduled together; the scenario does not
validate P-9 sensing, delay, or trip latching.

### 7. Flow-matching mass test, huge-shell regression, domain cases

The 100%→80% admission mass test demonstrates exact inventory closure, not
“perfect level control”: level changes to approximately **50.6411%** while
mass is constant, and dumping begins as steam pressure exceeds 7.6 MPa.
The enormous-shell comparison is a regression toward the former fixed sink,
not an operating scenario.

The low-pressure, dry-shell, and water-solid cases produce understandable
model-limit explanations. The dry/solid language is better than presenting a
quality number alone. Keep the distinction between **a model halt** and
**automatic plant protection** prominent; the static calls do not validate a
loss-of-feedwater sequence or real SG protection thresholds.

### Timing and observation

The existing `max_step=0.5 s` dense runs and 1 s samples adequately expose the
minute-scale admission ramp and rod-control recovery. They do not certify
subsecond valve closure or capture every intersample peak. The finer SCRAM
check reproduced the approximately 7.85336 MPa peak and first sampled dump
flow above 1 kg/s at about **4.2 s after SCRAM**: the surrogate waits for
pressure, rather than receiving a trip/load-rejection opening demand.

Also, `tau_trip=0.5 s` is a **time constant**, not “fully closed in 0.5 s.”
Admission remains 36.8% after 0.5 s, 13.5% after 1 s, and 1.83% after 2 s.
This is a lumped flow transient, not a validated turbine stop-valve stroke or
generator-breaker sequence. Use explicit simulation-time event markers and a
first-30-seconds trend view; `--speed 60` is suitable for the long tail, not
for observing that sequence.

## Dashboard (Phase D) must show

### Required for the first secondary-side dashboard

1. **Temperature program and response together:** `T_avg`, `T_ref`, signed
   `T_avg − T_ref`, the ±0.8 K control band, and common-time trends.
   Optional °F display helps relate the approximately 557°F no-load anchor
   to the SI model. Keep primary `T_hot`, `T_cold`, pressure and pressurizer
   level accessible. Primary-loop ΔT and turbine impulse pressure are
   different quantities; do not label one as the other.
2. **Actual power versus command:** fission/NI fraction and gross
   `P_electric` in MW; **admission demand versus actual admission**, ramp
   direction/rate, and trip override. Neither admission nor electrical output
   is a direct core-power control. Do not invent turbine RPM, grid frequency,
   or generator-breaker status before those are modeled.
3. **Steam heat sink:** `P_steam`, `T_secondary`, `m_steam`, `m_dump`,
   `Q_sg`, and dump open/closed status. Show the 7.6–8.2 MPa surrogate
   operating range separately from domain limits. Identify the modeled
   path as **combined dump/relief**, not confirmed condenser availability.
4. **Dump demand and position distinction:** M3 can expose its algebraic
   fraction (`m_dump / m_steam_design`) as **modeled opening/demand**.
   It has no separately lagged valve position, limit-switch feedback, or
   availability input. Show those as not modeled, not as fabricated
   independent indications. Future separate dump hardware needs demand,
   actual position, availability, and discharge destination.
5. **SG inventory and flow balance:** clearly labeled **collapsed liquid
   fraction**, `m_fw`, turbine steam flow, dump flow, and
   **`m_fw − (m_steam + m_dump)`**. Explain that mismatch is identically
   zero in M3. For M4, add actual/demand feedwater, level setpoint and error,
   controller mode, and saturation indications. Do not label collapsed
   fraction “narrow range” or “wide range.”
6. **Rod-control state:** selected mode **and** active/suspended status with
   cause; actual control-bank position, active demand, retained manual
   command only if relevant, direction of motion, and bank travel limits.
   Show shutdown-bank insertion as well as control-bank position after
   SCRAM. These are lumped banks, not individual-rod position indications.
7. **Effective trips and causes:** reactor-trip command/state as available;
   effective turbine trip from `trip_active`, identifying P-4 versus direct
   turbine trip; missing-P-9/RPS banner during an unprotected exercise.
   A command acknowledgment is not confirmation of valve closure or rod
   insertion. Preserve bumpless manual transfer and make reset/re-admission
   semantics explicit.
8. **Useful histories and events:** synchronized pressure, temperature error,
   power, rods, level, and all three flows; 1–5 s readable updates at normal
   speed, higher-resolution stored trip history, simulation-time trip/dump/
   mode-change markers, and a conspicuous acceleration indicator.
   Do not lose an entire trip transient between accelerated display frames.
9. **Limit versus alarm:** display the last valid sample/time, halted reason,
   and violated model assumption. Distinguish advisory bands, model-domain
   bounds, and future protection settings. The planned 40–60% level
   highlights and 12 MPa ceiling are not plant licensing limits.

### When the corresponding systems exist

- Separate condenser dump and atmospheric relief/safety indications,
  condenser availability/vacuum, manual dump controls and control mode.
- Per-SG narrow-/wide-range indications only after appropriate geometry and
  measurement modeling; main/auxiliary feedwater availability and actions
  before loss-of-feedwater or post-trip procedure exercises.
- Configurable reactor-protection permissives/trip latches and causes,
  decay-heat/total-heat-removal indication, and credible restart restrictions
  before protected transient or shutdown-cooling claims.

These are staged requirements, not a request to add a full main control board
to M3. The first tier largely uses existing telemetry; the principal gaps are
correct naming, effective status, dump fraction, and history presentation.

## Reference basis

- **[R1] NRC Technical Training Center, Westinghouse Technology Systems
  Manual, §8.1, Rod Control System**, particularly §§8.1.4.1–8.1.4.5 and
  printed p. 8.1-8, Rev. 0209:
  [ML11223A252](https://www.nrc.gov/docs/ML1122/ML11223A252.pdf).
  Supports rod speeds, manual selection, temperature/power-mismatch
  circuits, deadband and lock-up. The model's simplified schedule is not
  identical to this representative implementation.
- **[R2] Same manual, §11.2, Steam Dump Control System**, Rev. 0403:
  [ML11223A294](https://www.nrc.gov/docs/ML1122/ML11223A294.pdf).
  Supports 5%/min and 10% step control capability, representative 40% dump
  capacity, separate pressure/temperature modes, no-load temperature near
  557°F, and stored-energy/decay-heat removal. These capabilities require
  the stated plant configuration and available heat sink.
- **[R3] Same manual, §11.1, Steam Generator Water Level Control System**,
  Rev. 0706, control discussion and Figs. 11.1-2 / 11.1-4:
  [ML11223A293](https://www.nrc.gov/docs/ML1122/ML11223A293.pdf).
  Supports shrink/swell, flow/level control, and narrow-/wide-range
  instrument distinctions. Its example level program differs from 50%;
  that is a reason not to equate model volume fraction with plant indication.
- **[R4] Same manual, §12.2, Reactor Protection System — Reactor Trip
  Signals**, Rev. 0109, turbine-trip discussion, interlocks, and Table 12.2-2:
  [ML11223A301](https://www.nrc.gov/docs/ML1122/ML11223A301.pdf).
  Supports reactor-trip-breaker-derived P-4 turbine trip and distinguishes
  the P-9 approximately 50% configuration from P-7-based turbine-trip logic.
  M3 implements only the P-4 turbine-trip consequence, not all P-4 functions
  or the associated sensing/breaker logic.

## Disposition

Triage by the orchestrator (2026-09-28). No high-severity findings, so M-gate 3 has no open high item.

| # | Severity | Disposition |
|---|---|---|
| 1 | medium | fix now (M3.9.3 labels in console help/acknowledgement, validation plot titles; M3.9.0 README scenario text): "Unprotected turbine trip: automatic reactor protection omitted; ideal feedwater and combined dump/relief available". Configurable P-9 protection deferred (roadmap). |
| 2 | medium | document (M3.9.0): the ~564.6 K post-trip endpoint is the pressure-controlled dump's saturation temperature, not active T_avg regulation; decay heat omitted. Keep the 565 K default. |
| 3 | medium | fix now (M3.9.3 console/plot labels "turbine admission demand/actual", MW shown separately; M3.9.0 README wording "10 percentage-point admission reduction at 5 points/min"). |
| 4 | medium | fix now (M3.9.3 console/plot labels "SG collapsed liquid fraction — no shrink/swell; four SGs lumped"; M3.9.0 README). |
| 5 | medium | fix now (M3.9.3): console shows actual rod position, active rod demand and retained manual command separately; effective turbine-trip status from turbine telemetry with cause (explicit trip / SCRAM via P-4); rod control AUTO ACTIVE / AUTO SUSPENDED / MANUAL from `tavg_ctrl.acting`. Carried into Phase D notes. |
| 6 | medium | fix now (M3.9.3): console `r`/`untrip` leave turbine admission demand at 0 so re-admission is an explicit operator action; label as idealized signal release, not a restart. A model-level turbine-trip latch deferred to Phase D/RPS. |
| 7 | low | fix now with physics #3 (M3.9.1) + document. |
| 8 | low | fix now (M3.9.0): domain message wording ("below the model's 3.00 MPa guard band; the configured feedwater would flash near X MPa"), and "simulation validity limit, not plant protection". |
| 9 | low | partly fix now (M3.9.3: dump flow, signed T_avg − T_ref, feed/steam mismatch in the console status, visible pressure/dump legend in validation plots); terminal layout rework deferred to Phase D. |
