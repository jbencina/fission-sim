# Milestone 3 independent validation

- **Date:** 2026-09-28 (UTC).
- **Implementation commit:** `c1bc081` (`git rev-parse --short HEAD` at validation start).
- **HEAD at report completion:** `0724977`; the intervening commit changes only the concurrent `README.md`, `DEVELOPMENT.md`, and `tests/test_docs.py` documentation task, not the validated implementation.
- **Contract:** `M3-M4-IMPLEMENTATION-PLAN.md`, Physics design, Milestone gates, M3.6, and M3.8 Step 1, with the orchestrator's `plan-amendments.md` taking precedence.
- **Scope:** secondary shell, turbine/dump, M3 flow-matching feedwater, automatic rods, and model-domain acceptance. This is validation of an educational L1 model, not real-plant performance.
- **Isolation:** no implementation, test, documentation, or example files were edited by this validator. Concurrent changes to `README.md`, `DEVELOPMENT.md`, and `tests/test_docs.py` were excluded from this assessment.
- **Scratch root:** `/home/jbencina/.copilot/session-state/1217b4be-707a-424f-96b0-7dec3ca1b8d0/files/m3-validate/`.

## Commands and timing

All commands ran from `/home/jbencina/repos/fission-sim` using the existing `uv` environment. In the commands below, `$S` denotes the scratch root above. Timings are observed wall times on the shared host, not exclusive-machine benchmarks; the dense CLI and pytest ran concurrently.

| Command | Wall time | Result |
|---|---:|---|
| `uv run python scripts/validate_secondary.py --help` | 1.736 s | CLI has `--step-dt`, but no scenario-selection flag |
| `MPLBACKEND=Agg uv run python scripts/validate_secondary.py --milestone m3 --out-dir "$S/dense"` | 58.837 s | Exit 0; all 33 printed criteria pass; eight PNGs |
| `uv run pytest tests/test_secondary_plant.py tests/test_model_domain.py tests/test_sg_secondary.py tests/test_turbine.py tests/test_tavg_controller.py tests/test_feedwater_controller.py -q` | 54.235 s | `96 passed in 53.70s` |
| `MPLBACKEND=Agg uv run python "$S/capture_scenarios.py" --mode step --out-dir "$S/benchmark" --scenarios steady turbine_trip --duration 30` | 1.753 s steady + 8.081 s trip integration | Thirty simulated seconds each; timing excludes interpreter startup |
| `MPLBACKEND=Agg uv run python "$S/capture_scenarios.py" --mode dense --out-dir "$S/dense"` | 49.031 s | Exit 0; repeatable dense measurements, saved NPZ trajectories and JSON extrema |
| `MPLBACKEND=Agg uv run python "$S/capture_scenarios.py" --mode step --out-dir "$S/step" --scenarios steady load_auto turbine_trip` | 362.513 s | Exit 0; all 15 selected criteria pass; existing validator's `_run_scenario(..., step_dt=0.1)` path |
| `uv run python "$S/spot_checks.py"` | 1.429 s | Independent raw-CoolProp and scalar-root calculations below |
| `printf 'auto\nturbine_load 0.9\ntrip\nq\n' \| uv run python examples/console.py` | 1.685 s | Exit 1 by design: console rejects non-TTY stdin |
| `uv run python "$S/console_pty.py"` | 41.846 s | Real unmodified `uv run python examples/console.py --speed 60` under a scripted pseudo-terminal; exit 0 |
| `uv run python -` (saved-array finiteness, clock arithmetic, and isolated SciPy scratch-buffer diagnostic) | 0.539 s | All captured telemetry finite; output saved in `numerical-notes.txt` |

The short step benchmark projects roughly 28.6 minutes for the eight scenarios' 6,360 simulated seconds if the trip benchmark cost persists, before the additional huge-shell comparison. On that conservative early projection, step validation was deliberately restricted to the required steady and turbine-trip cases plus automatic load reduction; the full step-suite runtime was not measured. The scratch harness imports the existing validator and calls its own scenario definitions, domain checking, criterion evaluation, and plotting; it does not substitute a different integrator or different acceptance limits.

Dense trajectories are sampled every 1 s from BDF dense output with `max_step=0.5`; step trajectories use `engine.step(0.1)`, check every accepted step, and save approximately 1 s readouts. Plot extrema are therefore sampled extrema, not guarantees about sub-sample peaks. The focused test command requested for this review passed; the repository-wide M-gate 1 suite remains the orchestrator's separate responsibility.

## Dense criteria, exactly as printed

The text block preserves the original output verbatim, including the unescaped vertical bars in two criterion names.

```text
| criterion | measured | limit | pass |
|---|---:|---:|:---:|
| steady: final n | 1.11022e-16 | < 0.001 | yes |
| steady: final T_avg error | 0 | < 0.05 K | yes |
| steady: final P_steam error | 2.79397e-09 | < 5000.0 Pa | yes |
| steady: final level error | 1.44329e-15 | < 0.001 | yes |
| steady: final turbine load error | 0 | < 1e-09 | yes |
| energy balance: secondary energy residual | 3.8147e-15 | < 0.005 | yes |
| mass match: shell mass drift | 0 | < 1.0 kg | yes |
| load manual: final n | 0.971936 | 0.96..0.98 | yes |
| load manual: final T_avg | 587.836 | 586..590 K | yes |
| load manual: final P_steam | 7.48379e+06 | 7.35e+06..7.65e+06 Pa | yes |
| load manual: T_avg warmed | 587.836 | > 583.5 K | yes |
| load manual: P_steam rose | 584615 | > 100000 Pa | yes |
| load manual: secondary energy residual | 1.18862e-11 | < 0.01 | yes |
| load auto: final T_ref | 0 | < 1e-6 K | yes |
| load auto: |T_avg - T_ref| | 0.287776 | <= 1.0 K | yes |
| load auto: rods inserted | 0.393108 | < 0.5 | yes |
| load auto: final n | 0.909533 | 0.88..0.95 | yes |
| turbine trip: max P_steam | 8.17206e+06 | < 8500000.0 Pa | yes |
| turbine trip: max m_dump | 1591.3 | > 0 kg/s | yes |
| turbine trip: final load | 1.12541e-244 | < 0.001 | yes |
| turbine trip: final n | 0.941044 | 0.93..0.96 | yes |
| turbine trip: final T_avg | 593.16 | 591..595 K | yes |
| turbine trip: final P_steam | 8.17038e+06 | 8e+06..8.35e+06 Pa | yes |
| scram alone: final load | 4.35261e-144 | < 0.001 | yes |
| scram alone: max P_steam | 7.85335e+06 | < 8500000.0 Pa | yes |
| scram alone: final n | 2.75996e-06 | < 0.01 | yes |
| trip scram: final n | 6.78557e-08 | < 0.01 | yes |
| trip scram: min primary subcooling | 20.1961 | > 0 K | yes |
| huge shell: max |T_avg(M2)-T_avg(M3)| | 0.000273998 | < 0.5 K | yes |
| domain: P_STEAM_MIN above P_sat(T_fw) | 361102 | > 0 Pa | yes |
| domain: low steam pressure | steam_pressure | steam_pressure | yes |
| domain: dry shell | sg_dry | sg_dry | yes |
| domain: solid shell | sg_solid | sg_solid | yes |
```

## Step-mode comparison

All selected step scenarios completed with no model-domain halt and passed the same criteria as their dense counterparts. Integration/sampling wall times were **33.636 s for steady**, **236.773 s for automatic load reduction**, and **88.926 s for turbine trip**; the 362.513 s total also includes import, plotting, and saving overhead.

| Criterion | Dense | Step 0.1 s | Limit | Both pass |
|---|---:|---:|---|:---:|
| Steady final n error | 1.11022e-16 | 1.11022e-16 | < 0.001 | yes |
| Steady final T_avg error [K] | 0 | 0 | < 0.05 | yes |
| Steady final P_steam error [Pa] | 2.79397e-09 | 2.79397e-09 | < 5000 | yes |
| Steady final level error | 1.44329e-15 | 1.44329e-15 | < 0.001 | yes |
| Steady final turbine-load error | 0 | 0 | < 1e-9 | yes |
| Automatic final T_ref error [K] | 0 | 0 | < 1e-6 | yes |
| Automatic final absolute T_avg − T_ref [K] | 0.287776 | 0.295655 | ≤ 1.0 | yes |
| Automatic final rod position | 0.393108 | 0.393239 | < 0.5 | yes |
| Automatic final n | 0.909533 | 0.909609 | 0.88–0.95 | yes |
| Trip maximum P_steam [Pa] | 8.17206e6 | 8.17206e6 | < 8.5e6 | yes |
| Trip maximum dump flow [kg/s] | 1591.30 | 1591.30 | > 0 | yes |
| Trip final turbine load | 1.12541e-244 | 9.88131e-324 | < 0.001 | yes |
| Trip final n | 0.941044 | 0.941044 | 0.93–0.96 | yes |
| Trip final T_avg [K] | 593.160 | 593.160 | 591–595 | yes |
| Trip final P_steam [Pa] | 8.17038e6 | 8.17038e6 | 8.0e6–8.35e6 | yes |

**Steady step plot:** `step/steady.png` was opened and is indistinguishable from the dense plot: `n = 1`, `T_avg = T_ref = 583 K`, steam pressure 6.899180 MPa, and no dump flow. Level and rods remain 0.5, electrical output remains 990 MW, and the captured physical series are identical across modes.

**Automatic-load step plot:** `step/load_auto.png` was opened and shows the same short warming/pressure overshoot followed by rod insertion and stable power reduction; the final values are `n = 0.909609`, `T_avg = 581.495655 K` versus `T_ref = 581.2 K`, steam pressure 6.976797 MPa, and zero dump flow. Level settles to 0.500666, rods to 0.393239, and electrical output to 900.513 MW; compared with dense mode the final temperature differs by only 0.007880 K, rod position by 0.00013136 (about 0.030 of a 228-step bank step), and electrical output by 0.075475 MW. Neither mode has sustained tail chatter: in the last 300 s the rod position is exactly constant in the saved arrays, and the temperature span is below `5e-9 K`.

**Turbine-trip step plot:** `step/turbine_trip.png` was opened and has the same runback to `n = 0.941044`, final `T_avg = 593.160278 K` versus a 565 K reference, steam pressure 8.170380 MPa with approximately 1,586.62 kg/s dump flow, level 0.510837, stationary rods at 0.5, and essentially zero electrical output. The important early difference is a one-step trip delay: repeated addition gives `t = 9.9999999999999805` after 100 steps, so `t >= 10` first becomes true at about 10.1 s. This accounts for transient same-time differences up to 20.43 kPa steam pressure, 0.09243 K primary temperature, and 29.76 MW electrical output at the rapidly closing valves; final temperature differs by only `8.1e-8 K` and final pressure by 0.00167 Pa.

### Numerical warning

The step run printed one visible `RuntimeWarning: invalid value encountered in subtract` from SciPy 1.17.1 `bdf.py:416` while running the automatic-load case. It nevertheless completed every step and criterion, and a separate scan found all saved telemetry finite. This is recorded, not suppressed.

Inspection of the installed solver shows that its difference array is allocated with `np.empty`, with only rows 0 and 1 initialized; the early auxiliary update reads a higher-order row before it becomes relevant to error estimation. An isolated scalar-ODE diagnostic that places a signaling NaN in that unused first-step storage reproduces the exact warning while all accepted solutions remain finite and the solve completes. This establishes a plausible dependency-internal scratch-buffer explanation, **not** a retrospective proof of the original allocation; the plant run itself was not modified or injected with any value. Treat this as a low-severity numerical-diagnostics follow-up, not an observed plant-domain failure.

## Plot inspection and trajectories

Each listed dense PNG was opened with the image-viewing tool, rather than judged from table values alone. Temperatures are K, pressure is MPa, dump flow is kg/s, electric power is MW, and `n`, collapsed level, and rod position are fractions.

### Steady — 600 s

`dense/steady.png`: `n` remains 1 and `T_avg = T_ref = 583`; steam pressure stays 6.899180 with no dump flow. Level stays 0.5, rods stay 0.5, and electrical output stays 990, with no visible drift or oscillation.

### Steady energy balance — 60 s

`dense/energy_balance.png`: This shorter steady run shows the same flat `n = 1`, coincident 583 K temperatures, and 6.899180 MPa steam pressure with the dump shut. Collapsed level and rods remain 0.5 and electrical output 990; the measured fractional shell-energy residual is only `3.8147e-15`.

### Flow-matching mass test — 300 s

`dense/mass_match.png`: After the demand changes to 0.8, the governor takes roughly four minutes to reach that admission; `n` decreases only to 0.964395 while `T_avg` rises to 589.161 and `T_ref` falls to 579.4. Steam pressure reaches 7.649789 and opens the dump to about 138.50, while the collapsed level rises to 0.506411 even though shell mass is exactly constant. Rods stay 0.5 and electrical output falls to 873.112, with visible changes of slope as the dump opens and the governor completes its ramp.

### Load reduction, rods manual — 1,500 s

`dense/load_manual.png`: `n` settles to 0.971936, not 0.9, and the primary warms to 587.836 while the load program asks for `T_ref = 581.2`. Steam pressure settles to 7.483795 with no dump flow, level rises to 0.504997, and rods stay 0.5. Electrical output initially dips to 942.778 before recovering to 962.216 as higher steam pressure compensates for much of the admission reduction.

### Load reduction, rods automatic — 1,800 s

`dense/load_auto.png`: `T_avg` first peaks at 583.560 and then settles to 581.488, 0.287776 above the 581.2 reference, while rods insert from 0.5 to 0.393108 and `n` settles to 0.909533 after a small dip to 0.908387. Steam pressure has a small double-peaked transient up to 7.024807 before settling at 6.976180 without opening the dump, and level peaks at 0.501077 before settling to 0.500661. Electrical output settles to 900.437; the dense plot shows a brief change in rod-motion rate near the deadband, but no sustained late-time rod chatter or power oscillation.

### Turbine trip without SCRAM — 600 s

`dense/turbine_trip.png`: Electrical output rapidly falls to essentially zero and the load reference falls to 565, but rods remain at 0.5 and the reactor only runs back to `n = 0.941044`; the primary settles hot at 593.160. Steam pressure peaks at 8.172064, then settles at 8.170380 as the dump takes approximately 1,586.62 kg/s, and collapsed level rises to 0.510837. The very small pressure overshoot and slow tail are bounded; the important realism limitation is that this is a nearly full-power reactor feeding the simplified dump, not a normal protected plant trip.

### SCRAM alone / P-4 interlock — 600 s

`dense/scram_alone.png`: Rods insert to zero, `n` drops sharply and decays to `2.75996e-6`, and the interlocked turbine loses its electrical output while `T_ref` falls to 565. The primary cools to 564.5992; steam pressure first peaks at 7.853353 with a 704.75 kg/s dump pulse, then approaches 7.600002 as the dump nearly closes. Collapsed level peaks at 0.508142 before settling to 0.505987, rather than returning to 0.5, because flow matching conserves mass but does not regulate liquid volume.

### Turbine trip with SCRAM — 900 s

`dense/trip_scram.png`: The first 600 s have the same trajectory as SCRAM alone, confirming that the extra turbine-trip signal adds no separate transient when P-4 is already active; by 900 s, rods are zero, `n = 6.78557e-8`, and electrical output is zero. `T_avg` approaches 564.599099 against `T_ref = 565`, steam pressure approaches 7.60000005, and dump flow falls to 0.000138 after the same initial pressure/dump pulse. Level settles to 0.505987 and the smallest sampled primary subcooling margin remains 20.1961 K.

The huge-shell comparison produces a numerical criterion rather than a PNG: maximum primary-temperature difference from M2 is 0.000273998 K over 300 s. The remaining domain rows are static property/domain checks, not missing trajectory plots.

## Oddities and interpretation

1. **Medium — admission is not electrical-load demand.** A 10% manual admission reduction produces only a 2.806% final reactor-power reduction and approximately 962 MW instead of 891 MW. This is explained by the specified linear valve law, pressure rise, and weak moderator feedback; the independently solved equilibrium agrees. It is the anticipated amendment A6 behavior, not a reason to retune defaults during validation.
2. **Medium — an unprotected turbine trip leaves almost full reactor power.** The trip-without-SCRAM case retains 94.1% fission power and a primary temperature about 28.16 K above the no-load reference. The single proportional dump has essentially design-flow capacity and no reactor-protection trip is modeled; the scenario must remain explicitly labeled as an unprotected educational case.
3. **Medium — post-SCRAM heat removal becomes negligible too quickly for real shutdown cooling.** At 900 s the model has almost zero fission power and dump flow and is parked at the dump-pressure saturation temperature. This follows the current omission of decay heat and a real secondary cooling system; the 0.401 K difference from the 565 K no-load program is also explained by `T_sat(7.6 MPa) = 564.599096 K`, not a failed active temperature controller.
4. **Low — constant shell mass does not mean constant indicated level.** Level settles at 50.500% after the manual load reduction and 51.084% after turbine trip, despite zero M3 inventory drift. Changing saturated densities and quality alter collapsed liquid volume; real swell/shrink and narrow-range instrument behavior are not represented. These offsets are bounded and are not evidence of a mass leak or a functioning three-element level controller.
5. **Low — transient overshoot and deadband offset.** Automatic rods permit a maximum positive temperature error of 1.33532 K during the ramp, a small power undershoot, and a final 0.287776 K error; the manual case has a roughly 19.44 MW electrical undershoot relative to its final output. The transient excursions are not covered by the final-value temperature criterion, but are consistent with thermal lag, the controller deadband, and the governor/pressure response; the dense run does not sustain a limit cycle.
6. **Low — property-backend differences matter at ppm precision.** A deliberately all-IF97 hand check differs by 55.292 kW out of 3 GW (18.431 ppm) because the wrapper actually uses HEOS for compressed-liquid `h_fw`, while saturated steam properties use IF97. Repeating the independent calculation with those documented backends closes the design balance to about one micro-watt; this is not an unexplained energy leak.
7. **Low — presentation limitations.** The pressure/dump plot has different y-axes but no visible legend identifying the red dump curve, so a red zero-flow line can visually appear at an arbitrary pressure. The actual console is terminal-only and omits dump flow from its status line; its `rod = 0.5000` status field is the stale manual command during auto, whereas the primary table correctly shows actual position 0.3931.
8. **Low — finite-step scheduling and deadband endpoints are mode-dependent.** The `t >= 10` predicate trips at approximately 10.1 s in the floating-point step clock, and the 0.1 s held load-ramp inputs produce a slightly different automatic-rod stopping point. The measured differences are quantified above, remain far inside acceptance margins, and do not produce sustained chatter; event timing should not be compared as if the two input schedules were identical.
9. **Low — one solver-internal warning, without a failed trajectory.** The SciPy BDF warning and its controlled scratch-buffer reproduction are documented above. Tiny shutdown-rod excursions (`−2.13e-22`) and different effectively-zero turbine-load tails (`~1e-244` dense versus subnormal `~1e-323` stepped) are also numerical-floor artifacts, not physical rod withdrawal or meaningful electrical output.

## Independent spot checks

These calculations call `CoolProp.CoolProp.PropsSI` directly and use algebra/scalar roots, not the production acceptance helper's energy formula or the time integrator. The scratch source and complete output are `spot_checks.py` and `spot-checks.txt`.

### 1. Design shell energy balance and electrical output

At 558 K saturated steam:

```text
P_ref = 6,899,179.981586 Pa
h_g(IF97) = 2,773,871.812921 J/kg
h_fw(HEOS, P_ref, 500 K) = 976,401.603768 J/kg
delta_h = 1,797,470.209153 J/kg
m_design = 3,000,000,000 / delta_h = 1,669.012362332 kg/s
```

The actual initial snapshot has the same steam flow, so `m_design * delta_h = 2,999,999,999.9999986 W`, versus `Q_sg = 3,000,000,000 W`; the independently evaluated residual is `-1.43e-6 W`. Multiplying by 0.33 gives 990 MW. Using IF97 for feedwater instead gives `h_fw = 976,434.732467 J/kg`; the resulting 18.431 ppm difference accounts for the backend sensitivity noted above.

### 2. Automatic-rod equilibrium at 90% admission

The temperature program gives `T_ref(0.9) = 565 + 18*0.9 = 581.2 K`. With `UA = 120 MW/K`, solve independently for pressure:

```text
120e6 * (T_avg - T_sat(P))
    = 0.9 * (m_design/P_ref) * P * [h_g(P) - h_fw(P, 500 K)]
n = Q / 3e9
T_fuel = T_avg + 517*n
rho_rod = 2.5e-5*(T_fuel - 1100) + 5e-5*(T_avg - 583)
rod_position = 0.5 + rho_rod/0.012
```

At exactly 581.2 K, this gives **P = 6.953692714 MPa, n = 0.906750364, rod = 0.388312371**. At the actual dense endpoint, 581.487776 K, it gives **P = 6.976180460 MPa, n = 0.909532529, rod = 0.393107595**, agreeing with the independent trajectory readout to the displayed precision. The ±0.8 K deadband permits approximate equilibria from `n = 0.89904` to `0.91449`; the measured endpoint does not need to be exactly 90% power or exactly at the reference temperature.

### 3. Manual rods and trip re-banding

At the design rod position, zero steady reactivity gives
`n = 1 - 3*(T_avg - 583)/517`; heat transfer also gives
`T_secondary = T_avg - 25*n`. Solving those relations with raw-CoolProp saturation and each specified outflow law gives:

| Case | Independent n | Independent T_avg [K] | Independent P_steam [MPa] | Interpretation |
|---|---:|---:|---:|---|
| 0.9 admission, manual rods | 0.971935753 | 587.836405200 | 7.483794551 | Matches the dense final state; A6 re-banding is justified |
| Turbine trip, design-position rods | 0.941043031 | 593.160250907 | 8.170379430 | Matches the 600 s trajectory within its small remaining settling tail |

The independently computed trip outflow is 1,586.6172 kg/s, consistent with the final measured dump flow. The 3 MPa domain floor also exceeds `P_sat(500 K) = 2.638897756 MPa` by 361,102.244 Pa, confirming amendment A3's liquid-feedwater margin.

## Console/operator handoff

Ordinary scripted stdin is **not supported**: the unmodified CLI exits with
`examples/console.py is interactive — run it from a terminal, not a pipe.`
That actual attempt is preserved as `console-transcript.txt`.

For a usable operator review, `console_pty.py` additionally drove the real console through a pseudo-terminal: `auto` and `turbine_load 0.9` at t = 0, `trip` after t = 1800 s, and `q` after t = 2400 s, with `--speed 60`. It completed normally in 41.846 s; this is an actual terminal session, not a reimplementation of console command handling. The short transcript is **`console-operator-transcript.txt`**, with unabridged ANSI output in `console-pty.raw`.

Before the trip the console shows `n ≈ 0.9095`, `T_avg ≈ 581.49 K`, rods 0.3931, and roughly 900 MW. After the trip, automatic rod action is suspended and the already-inserted rods stay at 0.3931: by t = 2400 s the console shows `n ≈ 0.8566`, `T_avg ≈ 590.61 K`, steam pressure 8.119 MPa, level 51.0%, and zero electrical output. This differs appropriately from the acceptance turbine-trip scenario, which starts with rods at 0.5 and full power.

## Artifacts

Relative to the scratch root:

- `dense/{steady,energy_balance,mass_match,load_manual,load_auto,turbine_trip,scram_alone,trip_scram}.png`: all eight dense scenario plots, individually opened and inspected.
- `step/{steady,load_auto,turbine_trip}.png`: selected 0.1 s scenario plots, all individually opened and inspected.
- `dense.log`, `step.log`, `pytest.log`, and corresponding timing files: original run output.
- `dense/*.npz`, `step/*.npz`, and each directory's `summary.json`: captured numerical evidence.
- `capture_scenarios.py`, `compare_captures.py`, `spot_checks.py`, and `console_pty.py`: read-only scratch reproduction tools.
- `trajectory-comparison.txt`, `numerical-notes.txt`, `spot-checks.txt`: independent numerical evidence and diagnostics.
- `console-transcript.txt`, `console-operator-transcript.txt`, `console-pty.raw`: console handoff, including the real successful terminal session.

## Gate decision

All 33 dense criteria and all 15 selected step-mode criteria pass; the requested test selection reports **96 passed in 53.70s**. All eleven scenario PNGs were opened, the main equilibria were independently checked, and the actual console completed the operator sequence. There is no high-severity finding or unexplained physical trajectory; the stated L1 realism limitations and low-severity numerical/presentation observations should be handed to the independent physics and operator reviewers rather than hidden by changing defaults.

M-gate 2: PASS

## Re-validation after M3.9.n (2026-09-28, commit e1c96f1)

This append-only re-validation covers `3716061` (rod-speed plateau), `54cfcf2`
and `04cd835` (transient shell-energy accumulation and its printed criterion),
`4127bf2` (console/operator labels), and `e1c96f1` (documentation). HEAD remained
`e1c96f1` throughout. No source, tests, documentation outside this report, or
examples were edited, and no commit was created. The pre-existing untracked
`M3-M4-IMPLEMENTATION-PLAN.md` was left untouched.

**Artifact root (`$S`):**
`/home/jbencina/.copilot/session-state/1217b4be-707a-424f-96b0-7dec3ca1b8d0/files/m3-revalidate/`.
`$H` below denotes the original scratch harness,
`../m3-validate/capture_scenarios.py`, relative to that root.

### Commands, timing, and scope

| Command | Wall time | Result |
|---|---:|---|
| `MPLBACKEND=Agg uv run python scripts/validate_secondary.py --milestone m3 --out-dir "$S"` | 56.25 s | Exit 0; **34/34 criteria pass**; eight dense PNGs |
| `MPLBACKEND=Agg uv run python "$H" --mode dense --out-dir "$S/metrics" --scenarios steady load_auto turbine_trip` | 23.75 s | Exit 0; repeatable telemetry capture; **15/15 selected criteria pass** |
| `MPLBACKEND=Agg uv run python "$H" --mode step --out-dir "$S/step" --scenarios steady turbine_trip` | 117.74 s | Exit 0; **11/11 criteria pass**, using the validator's `step_dt=0.1` path |
| `make test` | **110.27 s** | Exit 0; **375 Python tests and 75 JavaScript tests pass** |

The CLI still has no scenario-selection flag. As in the original validation,
the unchanged scratch harness imports the current CLI's scenario definitions,
calls `_run_scenario(..., step_dt=0.1)`—the same path selected by
`--step-dt 0.1`—and uses its domain checks, criteria, and plotting. The two
600 s stepped integrations took **34.348 s** for steady and **80.460 s** for
turbine trip; total command time includes imports, plots, and file writes.
Automatic load reduction was re-validated in dense mode, not stepped mode,
for this requested rerun.

Commands overlapped on the shared host; these are observed wall times, not
exclusive-machine benchmarks. Dense extrema use the unchanged 1 s readout
cadence and BDF `max_step=0.5`; stepped trajectories check every 0.1 s step
and save approximately 1 s readouts. Reported extrema therefore remain
sampled extrema, not sub-sample guarantees.

### New dense criteria table

Values below are the CLI's printed values; literal vertical bars in criterion
names are escaped for a valid Markdown table. All **34** rows pass, including
the new transient-energy row.

| Criterion | Measured | Limit | Pass |
|---|---:|---|:---:|
| steady: final n | 1.11022e-16 | < 0.001 | yes |
| steady: final T_avg error | 0 | < 0.05 K | yes |
| steady: final P_steam error | 2.79397e-09 | < 5000.0 Pa | yes |
| steady: final level error | 1.44329e-15 | < 0.001 | yes |
| steady: final turbine admission error | 0 | < 1e-09 | yes |
| equilibrium: heat-rate mismatch | 3.8147e-15 | < 0.005 | yes |
| mass match: shell mass drift | 0 | < 1.0 kg | yes |
| load manual: final n | 0.971936 | 0.96..0.98 | yes |
| load manual: final T_avg | 587.836 | 586..590 K | yes |
| load manual: final P_steam | 7.48379e+06 | 7.35e+06..7.65e+06 Pa | yes |
| load manual: T_avg warmed | 587.836 | > 583.5 K | yes |
| load manual: P_steam rose | 584615 | > 100000 Pa | yes |
| load manual: equilibrium heat-rate mismatch | 1.18864e-11 | < 0.01 | yes |
| load manual: shell energy accumulation | **2.59456e-05** | **< 0.001** | **yes** |
| load auto: final T_ref | 0 | < 1e-6 K | yes |
| load auto: \|T_avg - T_ref\| | 0.276799 | <= 1.0 K | yes |
| load auto: rods inserted | 0.383704 | < 0.5 | yes |
| load auto: final n | 0.904078 | 0.88..0.95 | yes |
| turbine trip: max P_steam | 8.17206e+06 | < 8500000.0 Pa | yes |
| turbine trip: max m_dump | 1591.3 | > 0 kg/s | yes |
| turbine trip: final load | 1.12541e-244 | < 0.001 | yes |
| turbine trip: final n | 0.941044 | 0.93..0.96 | yes |
| turbine trip: final T_avg | 593.16 | 591..595 K | yes |
| turbine trip: final P_steam | 8.17038e+06 | 8e+06..8.35e+06 Pa | yes |
| scram alone: final load | 4.35261e-144 | < 0.001 | yes |
| scram alone: max P_steam | 7.85335e+06 | < 8500000.0 Pa | yes |
| scram alone: final n | 2.75996e-06 | < 0.01 | yes |
| trip scram: final n | 6.78557e-08 | < 0.01 | yes |
| trip scram: min primary subcooling | 20.1961 | > 0 K | yes |
| huge shell: max \|T_avg(M2)-T_avg(M3)\| | 0.000273998 | < 0.5 K | yes |
| domain: P_STEAM_MIN above P_sat(T_fw) | 361102 | > 0 Pa | yes |
| domain: low steam pressure | steam_pressure | steam_pressure | yes |
| domain: dry shell | sg_dry | sg_dry | yes |
| domain: solid shell | sg_solid | sg_solid | yes |

The new energy quantity is
`max(abs(ΔU_sec − integral(Q_sg + m_fw*h_fw − (m_steam + m_dump)*h_g))) / max(abs(ΔU_sec))`
over the manual-load transient, using trapezoidal integration of sampled
telemetry. Its measured error is **0.002595% of the largest stored-energy
change**, below the **0.1%** limit. It is distinct from the final-equilibrium
heat-rate mismatch, whose label now accurately describes what it checks.

### Required 0.1 s step-mode criteria

| Criterion | Dense | Step 0.1 s | Limit | Both pass |
|---|---:|---:|---|:---:|
| Steady final n error | 1.11022e-16 | 1.11022e-16 | < 0.001 | yes |
| Steady final T_avg error [K] | 0 | 0 | < 0.05 | yes |
| Steady final P_steam error [Pa] | 2.79397e-09 | 2.79397e-09 | < 5000 | yes |
| Steady final level error | 1.44329e-15 | 1.44329e-15 | < 0.001 | yes |
| Steady final turbine-admission error | 0 | 0 | < 1e-9 | yes |
| Trip maximum P_steam [Pa] | 8.17206e6 | 8.17206e6 | < 8.5e6 | yes |
| Trip maximum dump flow [kg/s] | 1591.3 | 1591.3 | > 0 | yes |
| Trip final turbine admission | 1.12541e-244 | 9.88131e-324 | < 0.001 | yes |
| Trip final n | 0.941044 | 0.941044 | 0.93–0.96 | yes |
| Trip final T_avg [K] | 593.16 | 593.16 | 591–595 | yes |
| Trip final P_steam [Pa] | 8.17038e6 | 8.17038e6 | 8.0e6–8.35e6 | yes |

Both stepped PNGs were opened. Steady remains flat at the design values;
trip remains bounded with stationary rods and an open combined dump/relief
path. All captured fields in the five dense/stepped NPZ files are finite.
The re-captured dense steady and turbine-trip arrays are identical to the
pre-fix captures, confirming that these non-auto trajectories did not change.

The previously reported floating-point input-scheduling effect remains:
the step clock is `9.99999999999998` after 100 steps, so the held trip input
first activates at approximately 10.1 s. Same-index transient differences
reach 20.43 kPa, 0.09243 K, and 29.76 MW, but final trip temperature and
pressure differ by only `8.10e-8 K` and `0.00167 Pa`. This is not a new
post-fix discrepancy.

### Opened PNGs and label confirmation

The actual generated **`load_auto.png` and `turbine_trip.png`** were opened
with the image-viewing tool, as were `step/steady.png` and
`step/turbine_trip.png`; the following is visual confirmation, not just a
source-code inspection.

- **Admission:** automatic-load title reads “100% to 90% turbine admission,
  rods automatic.” Electrical panels distinguish gross electrical power
  [MW], turbine admission demand [%], and turbine admission actual [%].
  In the trip case, the untouched operator demand remains 100% while actual
  admission closes to zero; the legend correctly distinguishes these signals.
- **Collapsed liquid fraction:** the axis reads “SG collapsed liquid
  fraction [-]” and the panel title reads “4 SGs lumped; no shrink/swell.”
  It is no longer presented as an unexplained indicated SG level.
- **Unprotected trip:** the trip title explicitly says automatic reactor
  trip on turbine trip is omitted and ideal feedwater plus combined
  dump/relief remain available. The footer explicitly limits P-4 to the
  SCRAM-to-turbine-trip direction and says this is not a normal protected trip.
- **Pressure/dump legend:** blue “Steam pressure P_steam [MPa]” and red
  “Combined dump/relief flow m_dump [kg/s]” are both visible, with their
  respective axes. This resolves the prior unlabeled-red-line finding.

The console itself was not driven again in this scoped rerun; these plot
checks do not purport to be a second interactive-console inspection.

### Rods-auto before/after the 8 steps/min plateau

These are independently recomputed from the original and new saved dense
trajectories, not copied from rounded plot labels. Signed error means
`T_avg − T_ref`; the acceptance row above uses its absolute final value.

| Quantity | Before M3.9.n | After M3.9.n |
|---|---:|---:|
| Maximum positive temperature error [K] | +1.335317 at 67 s | **+2.008057 at 89 s** |
| Final signed temperature error [K] | +0.287776 | **−0.276799** |
| Maximum T_avg [K] | 583.559854 | 583.900938 |
| Final T_avg [K], with T_ref = 581.2 K | 581.487776 | 580.923201 |
| Minimum / final n | 0.908387 / 0.909533 | 0.899580 / 0.904078 |
| Final rod position | 0.393108 | 0.383704 |
| Last rod movement above 1e-10 per saved interval [s] | 154 | 188 |
| Maximum / final steam pressure [MPa] | 7.024807 / 6.976180 | 7.086630 / 6.932105 |
| Final gross electrical output [MW] | 900.437 | 895.037 |
| Rod-direction reversals above 1e-10 per saved interval | 0 | 0 |
| Last-300-s rod-position range | 0 | 0 |
| Last-300-s temperature-error range [K] | 4.60e-9 | 5.47e-9 |

The slower minimum-speed region permits a larger initial temperature error
and a longer insertion interval. Thermal lag subsequently carries temperature
slightly below the reference, but the endpoint remains inside the 0.8 K
controller deadband and the 1.0 K acceptance tolerance. The plot shows one
bounded warming/cooling excursion and a small power undershoot followed by
settling, **not sustained limit cycling**. Rod motion is monotone insertion
then hold; there is no sampled withdrawal or tail chatter. Dump flow remains
zero throughout this maneuver.

A direct public-API spot check returns `speed = 5.8e-4 1/s` at errors just
above 0.8 K and at 1.0, 1.5, and 1.666667 K—**7.9344 steps/min** using the
documented 228-step bank, i.e. the rounded 8 steps/min plateau. The
2.008057 K transient peak legitimately enters the ramp above that plateau.
The two regimes should not be confused with an 8 steps/min speed cap.

### Full `make test` result

The full target ran both suites and exited 0. Summary lines from
`make-test.txt`:

```text
======================= 375 passed in 108.44s (0:01:48) ========================
 Test Files  9 passed (9)
      Tests  75 passed (75)
   Duration  561ms (transform 824ms, setup 0ms, import 1.13s, tests 204ms, environment 1ms)
wall_time_seconds=110.27
```

### New observations and severity

1. **Low — larger but settling rods-auto excursion.** Peak positive error
   increases from 1.335317 K to 2.008057 K and the final offset changes sign.
   This is visible and quantified above; it is not hidden behind the
   final-value criterion. All final bands pass, no model-domain halt occurs,
   and no sustained limit cycle is observed.
2. **Low — one stale README example endpoint.** At `e1c96f1`,
   `README.md:1388` still says the automatic maneuver inserts the bank to
   “about 0.393 withdrawn”; the new reproducible endpoint is **0.383704**.
   The documented speed program is current, but that illustrative endpoint
   predates the plateau change. Left untouched under the validator's
   report-only scope; this is non-gating documentation drift.
3. **Low — frontend tooling deprecation diagnostics.** The full test run
   prints Vite warnings that `vite:react-babel` specifies deprecated
   `esbuild` and `optimizeDeps.esbuildOptions`, and says oxc options take
   precedence. All nine JavaScript test files pass. These are observed
   maintenance warnings, not evidence of a physics regression or proof that
   the M3 fixes introduced a frontend problem.

No new medium/high-severity finding or failed numerical trajectory was
observed. Dense CLI, dense capture, and both required stepped cases emitted
no numerical warnings. The earlier SciPy warning occurred in stepped
`load_auto`, which was not rerun here, so its absence in this narrower step
selection is **not** evidence that the dependency issue was fixed.
The original L1 model limitations—admission rather than MW demand,
unprotected trip behavior, ideal feedwater, collapsed rather than indicated
level, and omitted decay heat—still apply; clearer labels do not add the
missing physical systems.

### Re-validation artifacts and decision

Under `$S`: `dense.txt`, `capture.txt`, `step.txt`, `make-test.txt`, their
`*-time.txt` wall-time files, the eight root-level dense PNGs,
`step/{steady,turbine_trip}.png`, `metrics/{steady,load_auto,turbine_trip}.npz`,
`step/{steady,turbine_trip}.npz`, the two `summary.json` files,
`rod-comparison.json`, and `step-comparison.json` preserve the evidence.

All 34 dense criteria and all 11 required stepped criteria pass; the full
Python/JavaScript test gate passes; the requested plot labels are present;
the updated automatic-rod response remains bounded and settles without
observed limit cycling. The low-severity notes above do not invalidate the
educational L1 milestone acceptance contract.

M3 re-validated: PASS
