# Milestone 4 independent validation

- **Date:** 2026-09-28 (UTC).
- **Implementation commit:** `25bb5ca3a160bfe0a3f40580c5759a46a62a16f2`
  (`fix(m4): one feedwater flow ceiling for controller and actuator`).
- **HEAD at report completion:** `8c41149af07bc1cf3e781326a0115e0955645e07`.
  The intervening commit changes only the concurrent `README.md` and
  `DEVELOPMENT.md` documentation task, not the validated implementation.
- **Contract:** `M3-M4-IMPLEMENTATION-PLAN.md`, Milestone gates, What M4 adds,
  M4.4, M4.6, and Review Focus 4–5; the orchestrator's `plan-amendments.md`
  takes precedence. This assessment covers the implemented continuous
  back-calculation anti-windup, not the older conditional-freeze pseudocode.
- **Scope:** the educational L1 feedwater actuator, three-element controller,
  collapsed SG level, and model-domain limits; not validation against a real plant.
- **Isolation:** this report is the only repository file created by the validator.
  No source, tests, documentation, or examples were edited; concurrent changes
  to `README.md` and `DEVELOPMENT.md` were excluded from this review. No commit
  was created.
- **Environment:** Python 3.11.15, NumPy 2.4.4, SciPy 1.17.1, CoolProp 7.2.0;
  existing `uv` environment, with no dependency changes.
- **Scratch root (`$S` below):**
  `/home/jbencina/.copilot/session-state/1217b4be-707a-424f-96b0-7dec3ca1b8d0/files/m4-validate-gate/`.

## Commands, timing, and coverage

Commands ran from the repository root. Timings are observed wall times on a
shared host: dense validation, test execution, and portions of the selected
step/console runs overlapped, so these are not exclusive-machine benchmarks.

| Command | Wall time | Result |
|---|---:|---|
| `MPLBACKEND=Agg uv run python scripts/validate_secondary.py --milestone m4 --out-dir "$S/dense"` | 68.948 s | Exit 0; all 17 criteria pass; seven PNGs |
| `MPLBACKEND=Agg uv run python scripts/validate_secondary.py --milestone m3 --out-dir "$S/m3-regression"` | 79.402 s | Exit 0; all 35 criteria pass; eight PNGs |
| `uv run pytest tests/test_sg_level_plant.py tests/test_secondary_plant.py tests/test_feedwater.py tests/test_feedwater_controller.py tests/test_model_domain.py -q` | 132.187 s | `102 passed in 131.61s (0:02:11)` |
| `make test` | 195.840 s | `433 passed in 193.63s (0:03:13)`; web: `Test Files 9 passed (9)`, `Tests 75 passed (75)` |
| `MPLBACKEND=Agg uv run python "$S/capture_scenarios.py" --step-dt 0.1 --scenarios m4_trip_scram_level --duration 30 --no-plots --out-dir "$S/benchmark"` | 11.497 s | Thirty simulated seconds; 9.658 s integration/sampling |
| `MPLBACKEND=Agg uv run python "$S/capture_scenarios.py" --step-dt 0.1 --scenarios m4_steady m4_loss_of_feedwater m4_trip_scram_level --out-dir "$S/step"` | 361.848 s | Exit 0; all seven selected criteria pass; three PNGs and true 0.1 s loss-of-feedwater steps |
| `MPLBACKEND=Agg uv run python "$S/capture_scenarios.py" --no-plots --out-dir "$S/dense-data"` | 64.284 s | Exit 0; all 16 scenario criteria repeat; factory row is only in the original CLI |
| `uv run python "$S/console_pty.py"` | 31.886 s | Two unmodified console processes, both exit 0 |
| `uv run python "$S/spot_checks.py"` | 2.059 s | Independent inventory, actuator, PI-response, and anti-windup calculations |
| `uv run python "$S/summarize.py"` | 0.200 s | Saved-array extrema, mode differences, and 18-PNG manifest |

`uv run python scripts/validate_secondary.py --help` confirms that the CLI has
`--step-dt`, but no scenario selector. At the measured early-trip cost, the
approximately 6,007 simulated seconds actually used by the seven M4 cases
would project to **32.2 minutes** of 0.1 s stepping if that cost persisted.
This is a conservative projection, not a measured full-suite runtime.
Accordingly, step-mode validation was restricted to the three requested cases:
600 s steady, loss of feedwater through its model limit, and 1,200 s trip+SCRAM.
All seven scenarios were run in the normal dense/default mode.

The scratch capture harness imports the real validator's scenario definitions,
`_run_scenario`, `_run_until_model_limit`, plotter, and criterion evaluation;
it does not replace the plant equations, integrator, or thresholds. There is
one important CLI limitation: `run_m4` hard-codes `dt=1.0` for both halting
scenarios even when passed `--step-dt 0.1`. The scratch harness explicitly calls
the existing `_run_until_model_limit(..., dt=0.1)` for the selected
loss-of-feedwater case, so that case really exercises 10 Hz stepping.
The complete unmodified CLI was **not** run with `--step-dt 0.1`.

“Dense” below means BDF `run(..., dense=True, max_step=0.5)` with 1 s readouts
for the non-halting scenarios; by design, the two model-limit cases use
`engine.step(1.0)` even in that mode. The selected step runs use
`engine.step(0.1)`, check the domain after every step, and retain approximately
1 s readouts except for the limit case, which retains every 0.1 s snapshot.
Reported extrema are sampled extrema, not continuous-time peak guarantees.
The first out-of-domain accepted endpoint is retained for the halting plots;
these are not root-localized event times.

The full Python suite remains below amendment A1's approximately four-minute
budget even with concurrent validation. Vitest completed in 664 ms; Vite
printed existing `esbuild`/`optimizeDeps.esbuildOptions` deprecation warnings
from the React plugin, but no test failed or was skipped.

## Dense M4 criteria, exactly as printed

```text
| criterion | measured | limit | pass |
|---|---:|---:|:---:|
| m4 steady: max level error | 1.44329e-15 | < 0.001 | yes |
| m4 steady: final feed/steam mismatch | 7.90148e-15 | < 0.005 | yes |
| m4 mass integral: shell mass accumulation | 4.19387e-06 | < 0.001 | yes |
| m4 mass integral: nonzero ΔM | 3149.6 | > 100 kg | yes |
| m4 mass integral: shell energy accumulation | 0.000303791 | < 0.001 | yes |
| m4 load auto level: max level excursion | 0.00180162 | < 0.05 | yes |
| m4 load auto level: final level residual | 1.99392e-06 | < 0.005 | yes |
| m4 setpoint step: final setpoint residual | 9.8366e-05 | < 0.01 | yes |
| m4 setpoint step: overshoot ceiling | 0.559884 | < 0.57 | yes |
| m4_loss_of_feedwater: limit | sg_tubes_uncovered | sg_tubes_uncovered | yes |
| m4_loss_of_feedwater: halt time | 64 | 30..600 s | yes |
| m4_feedwater_max: limit | sg_overfill | sg_overfill | yes |
| m4_feedwater_max: halt time | 543 | 200..2000 s | yes |
| m4 trip scram level: min level | 0.5 | > 0.30 | yes |
| m4 trip scram level: max level | 0.520867 | < 0.95 | yes |
| m4 trip scram level: final level residual | 0.0163898 | < 0.02 | yes |
| factory: nondefault shell feedwater defaults | 2002.81 | derived | yes |
```

## M3 regression criteria, exactly as printed

The standard plant now contains the M4 controller and actuator. Consequently,
“M3 regression” verifies the retained acceptance contract, not bit-identical
trajectories from the earlier flow-matching-only implementation.

```text
| criterion | measured | limit | pass |
|---|---:|---:|:---:|
| steady: final n | 1.11022e-16 | < 0.001 | yes |
| steady: final T_avg error | 0 | < 0.05 K | yes |
| steady: final P_steam error | 2.79397e-09 | < 5000.0 Pa | yes |
| steady: final level error | 1.44329e-15 | < 0.001 | yes |
| steady: final turbine admission error | 0 | < 1e-09 | yes |
| equilibrium: heat-rate mismatch | 5.40415e-15 | < 0.005 | yes |
| mass match: shell mass accumulation | 4.19387e-06 | < 0.001 | yes |
| mass match: nonzero ΔM | 3149.6 | > 100 kg | yes |
| load manual: final n | 0.971936 | 0.96..0.98 | yes |
| load manual: final T_avg | 587.836 | 586..590 K | yes |
| load manual: final P_steam | 7.4838e+06 | 7.35e+06..7.65e+06 Pa | yes |
| load manual: T_avg warmed | 587.836 | > 583.5 K | yes |
| load manual: P_steam rose | 584616 | > 100000 Pa | yes |
| load manual: equilibrium heat-rate mismatch | 3.62007e-06 | < 0.01 | yes |
| load manual: shell energy accumulation | 4.72388e-05 | < 0.001 | yes |
| load auto: final T_ref | 0 | < 1e-6 K | yes |
| load auto: |T_avg - T_ref| | 0.29053 | <= 1.0 K | yes |
| load auto: rods inserted | 0.383475 | < 0.5 | yes |
| load auto: final n | 0.903945 | 0.88..0.95 | yes |
| turbine trip: max P_steam | 8.17427e+06 | < 8500000.0 Pa | yes |
| turbine trip: max m_dump | 1597.45 | > 0 kg/s | yes |
| turbine trip: final load | 5.05014e-31 | < 0.001 | yes |
| turbine trip: final n | 0.941048 | 0.93..0.96 | yes |
| turbine trip: final T_avg | 593.16 | 591..595 K | yes |
| turbine trip: final P_steam | 8.17029e+06 | 8e+06..8.35e+06 Pa | yes |
| scram alone: final load | 1.16076e-137 | < 0.001 | yes |
| scram alone: max P_steam | 7.84064e+06 | < 8500000.0 Pa | yes |
| scram alone: final n | 2.75996e-06 | < 0.01 | yes |
| trip scram: final n | 6.78558e-08 | < 0.01 | yes |
| trip scram: min primary subcooling | 20.1961 | > 0 K | yes |
| huge shell: max |T_avg(M2)-T_avg(M3)| | 0.000261045 | < 0.5 K | yes |
| domain: P_STEAM_MIN above P_sat(T_fw) | 361102 | > 0 Pa | yes |
| domain: low steam pressure | steam_pressure | steam_pressure | yes |
| domain: dry shell | sg_dry | sg_dry | yes |
| domain: solid shell | sg_solid | sg_solid | yes |
```

## M4 dense/default plot inspection

All **18 generated PNGs** were opened individually: seven M4 dense/default,
eight M3 regression, and three selected step-mode plots. No additional PNGs
were generated by the benchmark or dense telemetry capture. The production
plots do not include feedwater, demand, or integral panels; the following
flow/controller numbers are taken from the separately saved telemetry arrays.

### `dense/m4_steady.png` — 600 s

Level stays at 0.5, feedwater and steam both remain 1,669.012 kg/s, and the
controller demand matches them with an integral indistinguishable from zero.
`P_steam = 6.899180 MPa`, `n = 1`, and `T_avg = 583 K` are flat, with no
dump flow, drift, or visible oscillation.

### `dense/m4_mass_integral.png` — 600 s

During the manual-rod ramp to 80% admission, level peaks at 0.503807 at
184 s, then dips to 0.498694 before ending at 0.498779; the shell loses
3,149.599 kg and final feedwater is 1,619.435 kg/s against 1,480.453 kg/s
turbine steam plus 138.155 kg/s dump flow.
Demand ends at 1,619.466 kg/s and the integral at −0.289296 s, while
`P_steam = 7.649666 MPa`, `n = 0.964281`, and `T_avg = 589.155874 K`;
the small continuing inventory recovery is not a failed conservation check.

### `dense/m4_load_auto_level.png` — 1,800 s

Level rises to 0.501802, undershoots to 0.499466, and returns to 0.500001994;
final feedwater/demand are 1,509.041/1,509.041 kg/s against
1,509.047 kg/s steam, with zero dump flow and an integral of only
`8.04631e-5 s`.
The early primary-temperature and steam-pressure peaks are 583.902983 K
and 7.086933 MPa, after which rod insertion brings `n` to 0.903945,
`T_avg` to 580.909470 K, and `P_steam` to 6.931036 MPa, without a sustained
oscillation.

### `dense/m4_setpoint_step.png` — 1,200 s

The 0.50→0.55 setpoint change at 10 s produces a smooth rise with a
0.559884 peak at 423 s and a final level of 0.549901634; demand peaks at
1,836.474 kg/s ahead of actual feedwater's 1,823.677 kg/s peak, and the
integral peaks at 4.333140 s before falling to −0.093198 s.
The added relatively cool feedwater briefly reduces `T_avg` to 582.610532 K
and `P_steam` to 6.853808 MPa, raising `n` to 1.002192 through temperature
feedback; the endpoint is nearly restored thermally at 583.003345 K,
6.899559 MPa, and `n = 0.999979909`.
Final feedwater is 1,668.363 kg/s versus 1,669.104 kg/s steam, so the small
remaining level error is part of a damped settling tail, not exact equilibrium.

### `dense/m4_loss_of_feedwater.png` — halt at 64 s

After manual demand is set to zero at 10 s, actual feedwater decays with its
5 s actuator lag and level falls monotonically to 0.297718664 at the first
invalid 1 s endpoint, correctly raising `sg_tubes_uncovered`.
The integral is frozen near zero in manual mode; final feedwater is only
0.034042 kg/s versus 1,813.243 kg/s turbine steam, the dump is still closed,
`P_steam = 7.495384 MPa`, `n = 0.973898693`, and `T_avg = 587.686094 K`.
Despite the slight reactor-power reduction, the pressure-driven electrical
proxy rises to 1,070.687 MW; there is no modeled protective SCRAM before the
simulation-validity limit.

### `dense/m4_feedwater_max.png` — halt at 543 s

Manual maximum demand drives actual feedwater to 2,002.815 kg/s while final
steam flow is only 1,637.008 kg/s, so level rises smoothly to 0.950509448
and correctly raises `sg_overfill` before a solid-shell property failure.
The controller integral remains frozen near zero, dump flow stays zero,
and the colder primary settles near `T_avg = 581.862315 K` and
`P_steam = 6.766885 MPa`, with a small temperature-feedback power increase to
`n = 1.006601334`.
The 365.806 kg/s final excess inlet flow explains the continued near-linear
level rise even after temperatures and pressure have largely settled.

### `dense/m4_trip_scram_level.png` — 1,200 s

Level **rises**, rather than initially shrinking: the rapid steam cutoff and
slower feedwater actuator produce a 0.520867 peak at 18 s, a second small
hump, and a persistent final level of 0.516389838; total shell mass ends
4,300.888 kg above its initial value.
The controller eventually commands zero feedwater, actual flow becomes
negligible, and the integral settles to 4.425256 s under back-calculation
while dump flow falls to `3.93831e-6 kg/s`; it cannot remove the excess
inventory once useful steam removal has disappeared.
`P_steam` peaks at 7.840638 MPa and tends to 7.600000 MPa, `n` decays to
`1.66865e-9`, and `T_avg` tends to 564.599096 K, with no sustained tail
oscillation but no return to the exact level setpoint either.

## M3 regression plot inspection

Every PNG named here was opened with the image-viewing tool. These production
six-panel plots show level, pressure/dump flow, power, temperatures, rods, and
admission/electric output; they do **not** plot feedwater flow, controller
demand, or integral. M4 flow/controller measurements in the following
assessment come from saved telemetry, not from guessing unplotted curves.

### `m3-regression/steady.png` — 600 s

Level is flat at 0.5, `n = 1`, `T_avg = 583 K`, and `P_steam = 6.899180 MPa`,
with stationary rods, 990 MW electrical output, and no dump flow.
Feedwater and steam remain balanced at 1,669.012 kg/s; there is no visible
drift or oscillation.

### `m3-regression/energy_balance.png` — 60 s

This shorter equilibrium run is also entirely flat: level 0.5, `n = 1`,
583 K primary temperature, 6.899180 MPa steam pressure, and zero dump flow.
The feed/steam balance is unchanged, and the final equilibrium heat-rate
mismatch is only `5.40415e-15` fractionally.

### `m3-regression/mass_match.png` — 600 s

As admission ramps to 80% with fixed rods, power drops to about 0.964 while
the primary warms to about 589.2 K and pressure rises to about 7.65 MPa,
opening the dump to roughly 140 kg/s.
Level first rises to about 0.5038, then undershoots to about 0.4987 as
feedwater control removes excess inventory; this is no longer the old
constant-mass M3 placeholder, and the actual mass change is −3,149.6 kg.

### `m3-regression/load_manual.png` — 1,500 s

At 90% admission, fixed rods leave `n = 0.971936`, `T_avg = 587.836 K`, and
`P_steam = 7.4838 MPa`, with the dump shut and electrical output recovering
after an initial dip.
Level rises to roughly 0.5030, undershoots to roughly 0.4990, then returns
close to 0.5 as the flow trim settles; unlike the old M3 plant, inventory is
regulated rather than held identically constant.

### `m3-regression/load_auto.png` — 1,800 s

Automatic rods insert to 0.383475 after a small temperature/pressure
overshoot, leaving `n = 0.903945` and `T_avg = 580.909470 K`, 0.290530 K below
the 581.2 K reference, with steam pressure about 6.931 MPa and no dump flow.
Level peaks near 0.5018, dips near 0.4995, and settles within `1.99392e-6`
of 0.5 as feedwater catches up with the reduced steam flow; no sustained
tail oscillation is visible.

### `m3-regression/turbine_trip.png` — 600 s

The unprotected trip closes turbine admission but leaves `n = 0.941048`,
`T_avg = 593.160 K`, and `P_steam = 8.17029 MPa`, with the combined dump/relief
path carrying approximately 1,586 kg/s instead of the turbine.
Level first rises above 0.520, then drops slightly below 0.5 and is recovering
at the endpoint as automatic feedwater trims inventory; this is explicitly
not a normal protected reactor trip.

### `m3-regression/scram_alone.png` — 600 s

SCRAM also closes the turbine through P-4, drops power to `2.75996e-6`, and
cools the primary toward 564.599 K while pressure peaks at 7.84064 MPa and
then approaches the 7.6 MPa dump threshold.
Level rises to about 0.5209 before relaxing to about 0.5164, rather than
initially shrinking or returning to 0.5; both feedwater and steam removal
approach zero after the dump pulse.

### `m3-regression/trip_scram.png` — 900 s

The simultaneous trip and SCRAM reproduce the SCRAM-alone transient,
including the level overshoot and persistent approximately 0.5164 level,
near-zero final flows, and steam pressure near 7.6 MPa.
By 900 s, `n = 6.78558e-8`, `T_avg` is approximately 564.599 K, and the
minimum sampled primary subcooling margin is still 20.1961 K.

The huge-shell comparison and static domain criteria produce no PNG; their
absence from this plot list is intentional.

## Step-mode comparison and numerical behavior

The selected step runs took **43.923 s** for steady state, **22.712 s** for
loss of feedwater, and **291.572 s** for trip+SCRAM, excluding interpreter
startup and plotting. All completed; the loss-of-feedwater run stopped at
the intended domain limit, not a property exception or solver failure.

| Criterion | Dense/default | True step 0.1 s | Limit | Both pass |
|---|---:|---:|---|:---:|
| Steady maximum level error | `1.44329e-15` | `1.44329e-15` | < 0.001 | yes |
| Steady final feed/steam fractional mismatch | `7.90148e-15` | `4.22321e-15` | < 0.005 | yes |
| Loss-of-feedwater limit | `sg_tubes_uncovered` | `sg_tubes_uncovered` | exact match | yes |
| Loss-of-feedwater first invalid endpoint [s] | 64.0 | 63.6 | 30–600 | yes |
| Trip+SCRAM minimum level | 0.5 | 0.5 | > 0.30 | yes |
| Trip+SCRAM maximum level | 0.520867 | 0.520865 | < 0.95 | yes |
| Trip+SCRAM final level residual | 0.0163898 | 0.0163897 | < 0.02 | yes |

**`step/m4_steady.png`:** This is visually indistinguishable from the dense
steady plot: level remains 0.5, feedwater matches 1,669.012 kg/s steam flow,
`n = 1`, `T_avg = 583 K`, and `P_steam = 6.899180 MPa`.
The integral remains at roundoff scale and there is no visible drift.

**`step/m4_loss_of_feedwater.png`:** The same smooth inventory decline,
primary warming, and pressure rise appear, but the finer domain-check cadence
halts at 63.6 s and level 0.299898055 instead of the coarser 64 s endpoint.
At that point feedwater is 0.037655 kg/s against 1,812.440 kg/s steam flow,
the integral is frozen near zero in manual mode, `P_steam = 7.492066 MPa`,
`n = 0.974067803`, and `T_avg = 587.656038 K`.

**`step/m4_trip_scram_level.png`:** The pressure pulse and double-peaked level
rise have the same shape as dense mode, and level settles to 0.516389686
while feedwater demand remains zero and the tracked integral tends to
4.425215 s.
By 1,200 s both physical flows are effectively zero, pressure is 7.600000 MPa,
`n = 1.67352e-9`, and `T_avg = 564.599096 K`; the fine step mode does not
remove the physical/controller reason for the residual level.

The step clock reaches `9.99999999999998`, not exactly 10, after 100 additions
of 0.1. Thus `t >= 10` changes the held input at approximately **10.1 s**
in these step runs; dense mode switches at 10 s. The loss-of-feedwater
snapshot first shows the new zero demand at 10.2 s because the external is
applied over the interval starting at 10.1 s. This scheduling difference and
the 1 s versus 0.1 s domain-check cadence must be separated from integration
error when comparing endpoints.

Linear interpolation of the last two loss-of-feedwater level samples puts
the floor crossing at **63.476440 s** with 1 s steps and **63.576602 s** with
0.1 s steps. Subtracting the latter run's 0.1 s input delay leaves only
**0.000162 s** difference; this is an interpolation comparison, not an
event-root accuracy claim.

For trip+SCRAM, the maximum same-time sampled differences are 0.000443 in
level, 17.618 kPa in steam pressure, 0.082936 K in primary temperature,
0.014197 in `n`, and 25.225 kg/s in actual feedwater during the fast
transient. The final level differs by only `1.51836e-7`; both runs' last
300 s have level spans below `3.12e-8`. The large relative differences
between effectively-zero shutdown tails are numerical-floor effects,
not meaningful physical differences.

The 0.1 s trip+SCRAM run printed one visible warning:

```text
scipy/integrate/_ivp/bdf.py:416: RuntimeWarning: invalid value encountered in subtract
  D[order + 2] = d - D[order + 1]
```

Nevertheless, every selected scenario completed, every captured numeric
telemetry series passed an explicit `np.isfinite` scan, and all criteria
passed. The earlier M3 report documents a reproduction of this warning in
unused SciPy difference-array storage; this M4 observation is consistent
with that explanation but does not prove the origin of this particular
allocation. No solver configuration, warning filter, or plant state was
altered to obtain a pass.

## Console exercise for the operator reviewer

The cleaned short transcript is `$S/console-operator-transcript.txt`, with
the exact terminal streams in `console-level-loss.raw` and
`console-automatic-transfer.raw`. The scratch `console_pty.py` launches the
unmodified `uv run python examples/console.py` with a real pseudo-terminal;
it does not import a replacement console or fake plant snapshots.

1. **Level step and sustained loss, `--speed 60` (24.173 s wall):**
   `level 0.55` is accepted at the initial display. Level is 51.9% at
   60 s, 55.8% at 300 s, and about 55.0% at 1,200 s.
   `feedwater 0.0` is then accepted; at the last displayed valid state,
   1,260 s, level is 32.3%, actual feedwater rounds to 0.0 kg/s, steam is
   1,818.8 kg/s, `n = 0.9726`, and `T_avg = 587.90 K`.
   The next attempted advance produces the clear `sg_tubes_uncovered`
   explanation and exits successfully, rather than continuing a dry-shell
   calculation.
2. **Return to automatic, separate fresh plant, `--speed 5` (7.637 s wall):**
   `feedwater 0.0` is applied at the initial display, followed by
   `feedwater auto` at 5 s. Actual feedwater is 614.0 kg/s at 5 s, recovers
   to 1,316.1 kg/s at 10 s and 1,733.6 kg/s at 30 s; demand at 30 s is
   1,739.0 kg/s against 1,677.9 kg/s steam flow, and level has turned upward.
   The operator then quits normally.

Two processes are necessary because a model-limit halt terminates the
console; it cannot accept `feedwater auto` afterward. This is a command and
display exercise, not the source of the precise 64 s acceptance halt time.
The fast console advances 60 simulated seconds at a time and reports the
last displayed valid time in its halt sentence: 1,260 s here, although the
failed domain check follows the attempted 1,320 s endpoint.

## Independent spot checks

The saved source/output are `$S/spot_checks.py` and `$S/spot-checks.txt`.
These calculations call `CoolProp.CoolProp.PropsSI` directly and use
inventory algebra and a linear transfer function, not the production plant
integrator or the acceptance helper's balance formula. Default parameter
objects are used only to read the specified gains, volume, and actuator
time constant.

### 1. Loss-of-feedwater halt time and actuator lag

Raw CoolProp at the 558 K design saturation point gives:

```text
P0                   = 6,899,179.981586 Pa
rho_liquid           = 741.526992767 kg/m³
rho_vapor            = 35.936538575 kg/m³
V_secondary          = 600 m³
design steam flow    = 1,669.012362332 kg/s
rho_liquid * V       = 444,916.195660 kg
(rho_liquid-rho_vapor) * V = 423,354.272515 kg
```

A liquid-only inventory estimate for the 0.50→0.30 margin is
`0.20*rho_liquid*V = 88,983.239 kg`. Dividing by design steam flow,
adding the 5 s equivalent feedwater inventory from the actuator's
exponential decay, and adding the 10 s event start gives **68.315 s**.
Allowing for the vapor that fills the released liquid volume uses
`M(L,P) = V*[rho_vapor + (rho_liquid-rho_vapor)*L]`, reducing the initial
mass margin to **84,670.855 kg** and the halt prediction to **65.731 s**.

The observed first invalid endpoint is 64 s. The shorter time is consistent
with increasing steam pressure and flow: using the observed final pressure
in the independent density calculation gives an 85,096.482 kg margin, and
using the observed mean post-event steam flow of 1,747.927 kg/s refines the
estimate to **63.458 s**, close to the 63.476 s interpolated crossing.
This last refinement is a cross-check using measured pressure/flow, not an
independent prediction of those trajectories.

The unforced actuator separately predicts
`m_fw(t) = m_design*exp[-(t-10)/5]`. At 5, 10, and 15 s after the event,
the analytic/observed flows are:

| Time after demand removal [s] | Analytic [kg/s] | Observed [kg/s] |
|---:|---:|---:|
| 5 | 613.995335 | 613.986468 |
| 10 | 225.876261 | 225.869731 |
| 15 | 83.095233 | 83.091628 |

All differ by less than 0.005% in the 1 s stepping run. The initial console
“boil-off time” of about 133 s is instead **all liquid mass / steam flow**;
it is not the roughly 54 s remaining until this model's tube-uncovering floor.

### 2. Level-setpoint response from the PI gains and inventory capacity

For a fixed-pressure small perturbation, define
`C = (rho_liquid-rho_vapor)*V = 423,354.273 kg per unit level`.
With `K_p = 3340 kg/s per unit level`,
`K_i = 11.133333 kg/s² per unit level`, and `tau_fw = 5 s`,
the linearized closed-loop transfer function is

```text
level(s) / setpoint(s)
    = (K_p*s + K_i) / (tau_fw*C*s³ + C*s² + K_p*s + K_i)
```

The poles are **−0.00403934 ± 0.00332996i s⁻¹** and
**−0.19192133 s⁻¹**. Thus this is not a single first-order level time
constant: the dominant settling envelope is **247.565 s**, close to the
no-actuator estimate `2*C/K_p = 253.506 s`, while the actuator mode is about
5.21 s. The PI zero also matters; using a generic second-order overshoot
formula without that zero would be misleading.

Inverse partial fractions of this independent linear response predict:

| Quantity | Linear prediction | Coupled-plant observation |
|---|---:|---:|
| First 63.2% of commanded change, after the event | 103.03 s | 104 s |
| First crossing of 0.55, after the event | 207.26 s | 207 s |
| Peak level | 0.559782755 | 0.559884317 |
| Absolute peak time, including 10 s event start | 424.30 s | 423 s |
| Level at 1,200 s | 0.549912533 | 0.549901634 |

This independently explains both the roughly seven-minute peak and the
visible overshoot with the specified gains; no tuning change is needed to
explain or pass the result. The small differences are expected because the
linear calculation omits the coupled pressure/density/thermal response.

### 3. Back-calculation at the post-trip lower flow limit

At the final trip+SCRAM state, `e = 0.5-L = −0.0163898379382`,
outflow is `3.93831e-6 kg/s`, the clipped demand is zero, and `T_t = 30 s`.
Setting the specified derivative
`dI/dt = e + (u_clipped-u_raw)/(K_i*T_t)` to zero gives

```text
I_equilibrium = e*(T_t-K_p/K_i) - outflow/K_i
              = 4.42525588958 s
I_observed    = 4.42525580592 s
u_raw         = -5.47420680276 kg/s
dI/dt         = 2.78862e-9
```

The positive tracked integral despite a negative level error is therefore
the expected back-calculation equilibrium, not uncontrolled windup. It
keeps a finite controller state but cannot make a nonnegative feedwater
actuator remove the above-setpoint inventory.

## Oddities, limitations, and severity

1. **Medium — passing the post-trip band does not mean recovery to setpoint.**
   The level first rises, and its final 0.516390 value uses about 82% of the
   allowed 0.02 residual band. In the last 300 s it moves by only about
   `3.1e-8`, so this is effectively a persistent offset, not a slowly
   converging 0.5 target. The plant gained 4.301 tonnes during the transient,
   the actuator cannot remove water, and useful steam removal vanishes in
   this no-decay-heat model. The acceptance-test name and older narrative
   “shrinks then recovers” should not be interpreted as an observed result.
   This is an important M-gate 3 realism discussion, not a failed numeric
   M-gate 2 criterion.
2. **Medium — loss-of-feedwater inventory margin is much shorter than the
   displayed boil-off cue.** The initial all-liquid boil-off estimate is
   approximately 133 s, but the model validity boundary is reached only
   about 54 s after loss of feedwater. The limit message correctly calls
   this a conservative surrogate rather than a real plant trip setpoint;
   an operator-facing display should not present `boil_off_time_s` as
   “time until safe operation ends.”
3. **Medium — inherited protection and secondary-work simplifications
   remain visible.** Loss of feedwater retains approximately 97.4% fission
   power until the simulation halts, maximum manual feedwater is not
   overridden before overfill, and an unprotected turbine trip still
   leaves about 94.1% fission power feeding the simplified dump. The
   loss-of-feedwater electrical proxy also rises from 990 to 1,071 MW
   while fission power falls, because pressure and the algebraic steam-work
   proxy respond differently from core power. These trajectories should
   remain labeled educational and unprotected; neither a real RPS nor
   detailed turbine-generator limits are being validated here.
4. **Low — visible but bounded overshoot and settling residuals.**
   The setpoint case overshoots 0.55 by 0.009884, or 0.9884 percentage
   points of full-scale level and 19.8% of the requested five-point change.
   The independent PI calculation reproduces it. The automatic load case
   also has a small level undershoot and a 0.290530 K final rod-controller
   deadband offset; the conservation case has a remaining level error
   of −0.001221 at 600 s. None shows sustained oscillation or violates its
   prescribed criterion.
5. **Low — the step CLI does not honor its cadence option for halting
   cases.** Both limit branches of `run_m4` always use 1 s steps. The
   validation harness explicitly supplied 0.1 s to the existing helper
   for loss of feedwater, so the required fine-cadence evidence exists,
   but a future user relying on the CLI flag alone would miss it.
   Full seven-scenario step-mode coverage and 0.1 s overfill coverage were
   not claimed or performed.
6. **Low — numerical warning without a failed solution.**
   One SciPy BDF warning occurred during the 0.1 s trip+SCRAM run; the
   run finished, all saved telemetry was finite, and no BDF step failure
   or property-closure failure occurred in any scenario. The dense run's
   tiny negative rod excursion (`−7.9e-22`) and differing effectively-zero
   shutdown tails are roundoff artifacts. The warning is retained in
   `m4-step.log`, not suppressed.
7. **Low — event timing and console display latency can mislead.**
   The 0.1 s repeated-addition clock delays the event by one step, while
   domain limits are detected at discrete accepted endpoints. The console
   reports its last displayed valid time after a limit and briefly
   combines new command acknowledgements with the previous snapshot's
   flow/mode; at `--speed 60` those displays can differ by a full simulated
   minute. The transcript documents this instead of treating the console
   timestamp as an exact model-limit crossing.
8. **Low — plot scope is narrower than controller-validation scope.**
   Production plots omit actual feedwater, controller demand, and integral
   panels, and their autoscaled/twin axes can visually overlay constant
   curves with different units. This review supplemented them with saved
   flow/control arrays and explicit calculations. The plotted level is
   collapsed liquid volume fraction for four lumped SGs, not a real
   narrow-range instrument with shrink/swell.

No high-severity implementation defect was established in this validation.
The medium observations above should be available to the independent
physics/operator reviewers; they are not claims of real-plant fidelity.

## Artifacts and verdict

- `m4-dense.log`, `m3-regression.log`: untouched CLI tables and wall times.
- `focused-tests.log`, `make-test.log`: complete test output and timings.
- `dense/`, `m3-regression/`, `step/`: all 18 inspected PNGs.
- `dense-data/*.npz`, `step/*.npz`, and their `summaries.json`/
  `criteria.json`: captured trajectories, extrema, endpoints, and criteria.
- `trajectory-summary.txt`: flow/control numbers, dense-versus-step
  comparisons, and the complete PNG manifest.
- `spot_checks.py`, `spot-checks.txt`: reproducible independent calculations.
- `console-operator-transcript.txt`, `console-*.raw`, `console-driver.log`:
  operator-review transcript and exact terminal evidence.
- `capture_scenarios.py`, `console_pty.py`, `summarize.py`: scratch-only
  reproducibility helpers; no repository implementation edits.

All 17 dense M4 criteria, all 35 retained M3 criteria, all seven selected
true-step criteria, all 102 focused tests, all 433 full Python tests, and
all 75 web tests pass. Both level boundaries stop with the intended
learner-readable model limits, and independent calculations explain the
inventory timescale, level-control transient, and saturation residual.
This passes the requested validation-report gate; independent physics/
operator sign-off and the concurrent documentation gate remain separate.

M-gate 2: PASS
