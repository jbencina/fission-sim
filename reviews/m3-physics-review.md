# Milestone 3 — independent physics review

## Summary

Reviewed on 2026-09-28 against `0724977db0c2a0b3665ce27f233bc46024acc4e6`,
the M3 design and orchestrator amendments, and `reviews/validation/m3/report.md`.
Scope is the educational L1 secondary side, not a plant safety analysis. The
existing M1 core is considered only where its feedback explains M3 behavior.

**No high-severity findings. Six medium findings and one low finding follow.**
The shell conservation equations, flow signs, design steam flow, and primary/
secondary coupling are correct. The unusual equilibria are reproducible
consequences of the chosen equations, not unexplained solver behavior. They
are not benchmarks for normal, protected PWR operation.

Particularly good work:

- Internal energy is the stored state; inlet/outlet **enthalpies** correctly
  include flow work. Dump steam is counted in both mass and energy balances.
- The initialization explicitly explains and solves the IF97/HEOS pressure
  mismatch rather than hiding a spurious initial transient.
- The feedwater flash-pressure guard follows the configured temperature.
  SCRAM correctly closes turbine admission through the modeled P-4 action.
- README distinguishes admission from MW, fission power from decay heat,
  and collapsed inventory from indicated level. M3 feedwater is correctly
  described as mass matching, not perfect level control.
- The validation report preserves unexpected results instead of retuning the
  physics to hit its original acceptance bands.

I read all requested files/README sections and inspected the manual-load,
automatic-load, turbine-trip, and trip-with-SCRAM dense plots. Additional
in-memory `uv run python` checks independently reproduced the manual-load
transient, solved equilibria without the plant integrator, integrated shell
energy accumulation, and exercised unequal feedwater/steam flows. Public
reference locators below were checked directly; unverified textbook equation
numbers are not supplied. No implementation files were changed.

## Findings

Paths below are relative to the repository root. “Medium” includes limitations
that can be resolved by accurate documentation or deliberately deferred fidelity
work; it does not mean every row requires an M3 equation change.

| # | severity (high/medium/low) | file:line | finding | reference | proposed change |
|---|---|---|---|---|---|
| 1 | medium | `src/fission_sim/physics/sg_secondary.py:28–35,450–456`; `src/fission_sim/physics/turbine.py:31–50`; `src/fission_sim/control/tavg_controller.py:19–29`; `README.md:1631` | **Citations do not substantiate several specific claims.** Todreas & Kazimi Ch. 6 is nonflow/steady-flow thermodynamics and Ch. 7 is nonsteady-flow first-law analysis, not a source for a Westinghouse rod program or valve settings. Most new equations lack a precise section/equation locator; “plan value” is not an empirical source. A general Reactor Concepts chapter is not adequate evidence for the numerical control schedule. | [R1], [R2], [R4]–[R8]. | Cite transient control-volume balances specifically; use the NRC **Systems Manual** chapters/pages below for plant controls. Distinguish equations derived here, empirical plant examples, and freely chosen L1 tuning. Verify the Kearton edition/chapter before retaining it as equation provenance. |
| 2 | medium | `src/fission_sim/physics/turbine.py:425–447`; `README.md:1097–1105`; `tests/test_secondary_plant.py:75–105` | **Admission control and a turbine-power temperature program are not interchangeable.** The linear valve is defensible, but `T_ref` also uses valve opening, whereas the reference Westinghouse program uses first-stage impulse pressure as turbine-power indication. The manual endpoint is 962.216 MWe, not a 891 MWe demand; even auto ends near 900.4 MWe. Existing admission disclosures prevent this being a high finding, but “load following” must retain this qualification. | [R6] §8.1.4.2–3; [R9] Eqs. 10, 19; independent equilibria in (c)–(d). | Keep an explicitly named admission/manual-valve mode. For a true load-demand mode, add bounded steam-flow or MW feedback and base `T_ref` on the corresponding load/power signal. Do not try to fix the discrepancy solely by changing `alpha_m`. |
| 3 | medium | `src/fission_sim/control/tavg_controller.py:63–79,177–206`; `README.md:1270–1279,1340–1345` | **The rod-speed schedule is a more substantial approximation than its description suggests.** The reference has 8 steps/min from 1.5 to 3 °F error, a ramp from 3 to 5 °F, and 0.5 °F start/stop hysteresis. This implementation ramps immediately outside 0.8 K: at 3 °F error it requests about 36, not 8 steps/min. It also omits the anticipatory nuclear/turbine power-mismatch signal. Correct endpoint speeds alone do not reproduce the reference controller. | [R6] §8.1.4.2–5, pp. 8.1-6–8 and Fig. 8.1-4. | Either retain a clearly flagged **temperature-only, continuous, no-hysteresis L1 schedule**, or implement the plateau and hysteresis with matching tests. Explicitly list omitted power-mismatch compensation. Do not claim the measured transient validates a real Westinghouse controller. |
| 4 | medium | `src/fission_sim/physics/turbine.py:21–24,130–138,430–435`; `src/fission_sim/plant.py:238–240`; `tests/test_secondary_plant.py:128–139`; `README.md:1182–1190,1978` | **The 94% trip endpoint needs an explicit unprotected, ideal-heat-sink interpretation.** A smooth 100%-design-flow outlet plus unlimited, instantaneous 500 K replacement feedwater can sustain this equilibrium. Real condenser dumps, atmospheric PORVs, and safety valves have different capacities, controls, destinations, and reset behavior. Full-power turbine trip normally initiates reactor trip; P-4 is only the reverse direction. “7.6–8.3 MPa” is not a universal setpoint envelope. | [R4] pp. 11.2-1–5; [R5] §7.1.3.3–4; [R7] §12.2.3.16 and P-4/P-9 descriptions. | Label this scenario “unprotected turbine trip; reactor-trip action omitted; ideal feedwater and aggregate relief available.” Explain that it is neither a normal trip nor a validated ATWS calculation. If realistic trip/level behavior becomes a goal, separate the discharge paths and implement appropriate protection/feedwater assumptions; do not merely reduce the one outlet to 40%. |
| 5 | medium | `src/fission_sim/validation/secondary_acceptance.py:179–197`; `tests/test_secondary_plant.py:62–65,92` | **The energy criterion tests final equilibrium, not transient conservation, and assumes M3 mass matching.** It omits `dU/dt`, substitutes steam outflow for actual feedwater flow, and constructs the default 500 K feedwater parameters. That is valid at the tested default M3 endpoints, but is not the general shell first law and will be inappropriate for M4 inventory transients or custom feedwater temperature. | [R2] §5.2.2–3; independent accumulation checks in (g). | Name the existing quantity an equilibrium heat-rate mismatch. Add integrated checks of both `ΔM = ∫(m_fw − m_out)dt` and `ΔU = ∫(Q_sg + m_fw h_fw − m_out h_g)dt`, using the actual shell parameters/telemetry and a nonzero inventory change. |
| 6 | medium | `src/fission_sim/physics/sg_secondary.py:238–250`; `src/fission_sim/physics/domain.py:280–291`; `README.md:1066–1076,2021–2024` | **Inventory scale is plausible, but the claimed Model-F provenance and physical level thresholds are not established.** A 600 m³ free-fluid volume and 0.5 liquid-volume fraction imply 222.46 tonnes of liquid. No identified drawing/design table supports “150 m³ per Model-F-class shell.” A volume fraction is not a tube-top elevation or a calibrated narrow-range indication. This matters directly to M4 depletion time, controller gain, uncovering, and overfill claims. | [R8] pp. 11.1-2–3, Fig. 11.1-2; [R2] mass/volume relations. | Supply an identified SG free-fluid-volume/operating-inventory source, or label the volume and level anchors generic educational assumptions. Before M4 calls 0.30 “tube uncovering” or 0.95 “water entering the steam line,” provide a geometry mapping or explicitly call them conservative surrogate model limits, not plant-derived elevations. |
| 7 | low | `src/fission_sim/physics/sg_secondary.py:105–120,318–331`; `src/fission_sim/physics/pressurizer.py:235–254`; `README.md:1794–1796` | **Pressure-matched initialization is not a globally single-EOS closure.** The stored HEOS-consistent `U` is not exactly the internal energy reconstructed from the reported IF97 phase masses/properties. The default difference is 50.23 MJ, about 0.0164% of stored energy. This is small for L1 and is not an unexplained loss of energy through the SG boundaries. | [R3]; direct property checks in (g). | State explicitly that the root reconciles the initial pressure, not all thermodynamic identities. Keep a quantified mismatch tolerance. For a later exact closure, use one backend consistently or invert a consistent IF97 mixture relation. |

## Answers to the review questions

### (a) Is 565 K consistent with a 7.6 MPa dump setpoint?

**Yes, as a rounded no-load anchor, not an exact equality.** Using IF97:

| Quantity | Value |
|---|---:|
| `T_sat(7.6 MPa)` | 564.599096 K |
| `P_sat(565 K)` | 7.644263 MPa |
| Reference minus zero-heat saturation temperature | 0.400904 K |

The mismatch is smaller than the 0.8 K rod deadband. With negligible heat
generation, no pump heat, and no decay heat, the present dump closure parks
the primary near **564.599 K**, exactly as the validator found. During SCRAM,
automatic rods are suspended: there is no active controller forcing 565 K.
The proportional dump also needs pressure above its opening setpoint whenever
it is carrying a finite heat load.

The NRC training example uses approximately 557 °F = 564.82 K and a steam
pressure setting of 1092 psig ≈ **7.6304 MPa absolute** [R4]. Thus the chosen
anchors are credible generic values. No mandatory retuning is warranted. If
an exact zero-heat anchor is desired, derive one from the other with CoolProp.
The full-load 583 K reference is plausible and correctly matches the primary
design point; the 18 K linear program span is an L1 choice, not universal
plant data.

### (b) Is one full-capacity proportional dump/relief path acceptable?

**Acceptable as an explicitly idealized aggregate heat outlet; not as a model
of normal condenser-dump operation or valve-by-valve overpressure response.**
A pressure-only monotonic outlet is a useful L1 closure. Its chosen opening
ramp is a constitutive assumption, not a standard valve equation.

Verified examples from the NRC Westinghouse Systems Manual:

| Hardware | Reference capacity/control | Implication here |
|---|---|---|
| Condenser steam dumps | Common reference system: **40% of full-power steam flow** at a specified pressure; sized with rod response for a 50% load rejection. Temperature/load-rejection and turbine-trip modes, plus a pressure-control mode. | About **668 kg/s** when scaled to this model's nominal steam flow. Not a continuously available 100% heat sink. Condenser availability matters. |
| Atmospheric SG PORVs | One per steam line; each about **10% of its SG's rated flow**, or **2.5% of total four-loop flow**. Thus all four give about **10% total**, not 40%. Reference nominal setting: 1125 psig. | About **167 kg/s total** on the model's flow basis; reference setting ≈ **7.858 MPa absolute**. |
| Main steam safety valves | Reference: five per SG; aggregate capacity **109% of full-power steam flow**. Setpoints 1170, 1200, 1210, 1220, 1230 psig. | Full-design-flow emergency relieving capacity is credible. Those example settings are **8.168, 8.375, 8.444, 8.513, 8.582 MPa absolute**, not all below 8.3 MPa. |

Sources: [R4], [R5]. These are a **reference plant/system**, not a universal
specification. The question's approximate 7.9–8.3 MPa range overlaps some
PORV/safety settings but should not be presented as a complete generic safety
valve range. Gauge-to-absolute conversion is essential for CoolProp.

The model's 7.6–8.2 MPa opening ramp makes nearly design-flow relief available
smoothly near the first safety lift of that example. Real safety valves have
pop action, staggered lifts, and reseat/blowdown behavior; condenser dumps
normally respond to control signals, not this same static ramp. Consequently
the very small measured trip-pressure overshoot is not validated plant
performance.

Two reasonable paths:

1. **Retain the aggregate outlet for M3:** lowest effort; document unlimited
   receiving sink and replacement feedwater, and restrict interpretation.
2. **Split controlled dump, atmospheric relief, and safety relief:** modest
   additional L1 complexity with a real fidelity gain for trip and M4 level
   studies. Use separate capacities, availability, and reset assumptions.

**Recommendation:** option 1 is sufficient to accept this narrowly labeled M3;
option 2 should precede claims about realistic large load rejection or
protection behavior. Reducing the existing single capacity to 40% without
adding emergency relief is not a sound fix.

### (c) Is `m_steam ∝ load · P` adequate, or should a governor hold flow/MW?

**The valve law is an adequate near-design L1 admission relation. It is not a
MW governor.** Compressible choked-flow scaling is approximately
`m ∝ effective_area · P_upstream / sqrt(T_upstream)` for fixed gas properties
and sufficiently low downstream pressure [R9, Eqs. 10 and 19]. Treating
effective area as linear in admission and absorbing temperature, discharge
coefficient, real-steam effects, and turbine swallowing characteristics into
one calibrated coefficient is reasonable here. It should not be represented
as an exact steam-nozzle law across the entire pressure/load domain.

The calibration is dimensionally and numerically correct:

```text
k_valve = m_design / P_ref = 2.419146e-4 kg/(s·Pa)
```

At the measured manual endpoint:

```text
admission                    = 0.9
P_steam / P_ref               = 7.483795 / 6.899180
m_steam / m_design            ≈ 0.9763
net steam heat / design heat  = 0.971936
P_electric                   = 962.216 MWe
```

Pressure therefore recovers most of the flow removed by the valve closure.
The enthalpy difference changes slightly as well. **891 MWe would be a 90%
MW request; it is not the expected result of a fixed 90% valve-area request.**
This is the main distinction, not a missing factor in the electricity equation.

For an L1 load-following model, there are three concrete options:

1. **Admission mode only:** current equations, lowest effort; teach valve
   positioning and feedback, not delivery of specified MW.
2. **Steam-flow governor:** vary admission to hold a requested mass flow,
   subject to valve limits. Simple, but electrical output still varies with
   steam conditions and efficiency.
3. **MW governor:** vary admission using `P_electric` feedback, with bounded
   rate/position and saturation handling. Best match to an operator MW demand;
   does not require turbine-stage thermodynamics.

**Recommendation:** retain option 1 as an explicit mode and use option 3 when
the feature is advertised as MW load following. Do not directly force core
power to the load request. In the reference rod-control system, `T_ref` follows
turbine-power indication from impulse pressure, not raw valve position [R6].
An actual-power proxy would give about **582.50 K**, rather than 581.20 K,
at the present manual endpoint.

The electric-power equation is sound as a **fixed cycle-efficiency surrogate**:
`eta · m_steam · (h_g − h_fw)`. Here 0.33 is an effective thermal-to-electric
conversion fraction, **not turbine isentropic efficiency**, and `h_fw` is not
the turbine exhaust enthalpy. 990 MWe from 3000 MWth is plausible; off-design
efficiency, extractions, pump work, condenser duty, and generator losses are
not separately balanced.

### (d) Does manual-rods load following resemble a real PWR? Is MTC dominant?

**The direction and qualitative time ordering are right. The magnitude is
specific to this weak-feedback, fixed-admission model.** Steam removal falls,
pressure and saturation temperature rise, SG heat removal initially decreases,
the primary warms, negative moderator feedback reduces fission power, and
fuel cooling returns positive Doppler reactivity. A real reactor with rods
held can also settle hotter; it need not follow the programmed `T_ref`.

The stationary core and heat balances make the cause explicit. With rods
fixed at their design position:

```text
T_fuel = T_avg + 517 n
0 = alpha_f (T_fuel − 1100) + alpha_m (T_avg − 583)

T_avg − 583 = A (1 − n)
A = 517 alpha_f / (alpha_f + alpha_m) = 172.333 K

T_secondary = T_avg − 25 n
```

The 517 K fuel/coolant difference comes from the existing M1 heat-transfer
calibration; 25 K comes from `Q_design/UA`. These are algebraic consequences
of the stated model, not fitted new reactor data. At the independently
reproduced equilibrium:

```text
n = 0.971935753
T_avg = 587.836405 K
P_steam = 7.48379455 MPa
rho_moderator = −24.182 pcm
rho_Doppler   = +24.182 pcm
```

`alpha_m = −5 pcm/K` is a credible **weak**, high-boron hot-state choice, not
an order-of-magnitude coding error and not representative of all cycle states.
Together with `alpha_f = −2.5 pcm/K` and the 517 K fuel temperature excess,
it makes a large temperature change necessary to compensate fuel cooling.
The required warming for a true 10% fission reduction would be **17.23 K**.

However, **it is not sufficient to blame MTC alone**. Independent scalar
equilibria, keeping all other assumptions unchanged, show:

| Moderator coefficient [pcm/K] | `n`, 90% admission | `T_avg` [K] | `P_steam` [MPa] | Electric power [MWe] |
|---:|---:|---:|---:|---:|
| −5 | 0.971936 | 587.836 | 7.483795 | 962.216 |
| −10 | 0.962444 | 586.883 | 7.406175 | 952.819 |
| −20 | 0.951544 | 585.784 | 7.317231 | 942.029 |
| −30 | 0.945474 | 585.168 | 7.267780 | 936.020 |

These are sensitivity cases, not proposed plant calibrations. Even a sixfold
stronger MTC does not turn 90% admission into 90% MW.

Conversely, an ideal 891 MWe governor **with the present MTC and dump law**
would settle at approximately `n = 0.964764`, `T_avg = 589.072 K`,
`P_steam = 7.63908 MPa`, with **108.71 kg/s dumped**. At `n = 0.9` with rods
unchanged and no dump, the feedback/UA equations require 9.156 MPa steam,
well above the dump opening pressure. A governor fixes delivered MW, not
necessarily reactor power when a bypass is open.

Thus the weak MTC relative to the fuel power defect is an important
**amplifier**; pressure-compensated valve flow and the dump boundary condition
are equally necessary to explain what “following poorly” means. Retain the
existing core assumptions unless a separately sourced operating-point
calibration is undertaken.

The manual warming/pressure rise over tens to hundreds of seconds and the
stable auto response are qualitatively credible for this lumped plant.
The 5%/min demand ramp is realistic as an operating maneuver [R4], but is
not the maximum physical speed of turbine governing. `tau_gov = 1 s` and
`tau_track = 1 s` are acceptable tuning choices, not measured plant constants.
The rod conversion factors are correct: 8 and 72 steps/min over 228 steps
give `5.85e-4` and `5.26e-3 /s`. The controller sign is also correct: hot
inserts, cold withdraws. Finding 3 limits the realism claim for its schedule.

### (e) Is the collapsed-level simplification honest?

**Yes, in the present source and README.** The lever rule gives

```text
x = (V/M − v_l) / (v_v − v_l)
M_l = (1 − x) M
level_sg = M_l / (rho_l V_sec)
```

This is a liquid **volume fraction**, not a narrow-range transmitter reading
or a geometric height without a cross-sectional model. Density/quality changes
can move it at fixed total mass; the approximately 0.505 manual-load and 0.511
trip endpoints are not mass leaks.

This distinction must survive M4. A real load reduction can initially cause
**indicated level shrink**, while this model's collapsed fraction rises as
the equilibrium densities change. The reference manual explicitly explains
why level response alone can give the wrong initial feedwater-control action
[R8, p. 11.1-3 and Fig. 11.1-2]. Calling the modeled rise “swell” or treating
50% shell volume as 50% narrow-range indication would be wrong.

The source correctly lists absent recirculation, riser/downcomer dynamics,
separator carryover, void swell, and tube-metal capacity. M3's exact
`m_fw = m_steam + m_dump` closes **mass**, not level. The older plan's
“perfect level control” wording should not be reused.

### (f) Is a turbine trip settling at 94% power acceptable?

**Yes as the explicitly unprotected educational experiment defined here; no
as a normal full-power turbine-trip demonstration.** No forced change to core
feedback or arbitrary requirement for `n < 0.7` is justified.

Solving the stationary equations independently gives:

```text
n ≈ 0.941043
T_avg ≈ 593.160 K
P_steam ≈ 8.170379 MPa
m_dump ≈ 1586.62 kg/s
```

This agrees with the 600 s validator result. Roughly **2.823 GW** of continuing
reactor heat leaves through the aggregate outlet, with essentially zero
electrical output. There is no contradiction in the reactor remaining nearly
critical while a sufficiently large steam outlet and replacement feedwater
remain available.

At full power the reference plant trips the reactor on turbine trip: the
threshold is above P-9 where fitted (50% in the reference), or P-7 for other
configurations [R7]. P-4 correctly represents **reactor trip → turbine trip**;
it does not implement **turbine trip → reactor trip**. This model also holds
automatic rods on turbine trip, a declared simulation policy rather than a
complete representation of the real low-power/rod-stop logic.

The needed M3 change is presentation/qualification, not falsifying the
equilibrium. A normal protected scenario should use the existing simultaneous
trip+SCRAM case until protection logic is implemented. Even that case is only
a **fission-plus-stored-heat transient**: the near-zero heat load at 900 s is
not realistic shutdown heat removal because decay heat and pump heat are
absent. Neither scenario establishes that a real plant can remain safely at
94% power on its condenser dump.

`tau_trip = 0.5 s` is explicitly a **time constant**, not full stop-valve
closure time: 36.8% admission remains at 0.5 s, 13.5% at 1 s, and 1% at
2.303 s. It is serviceable L1 smoothing, but the sources supplied with the
code do not calibrate this curve. A plant-specific valve stroke/steam-chest
model is needed before using the calculated first-second pressure peak as
a realistic turbine-trip prediction.

### (g) SG energy bookkeeping and IF97/HEOS consistency

**The governing conservation equations are correct for the declared rigid
equilibrium control volume** [R2]:

```text
dM/dt = m_fw − m_steam − m_dump
dU/dt = Q_sg + m_fw h_fw − (m_steam + m_dump) h_g
```

There is no shaft work, moving boundary, or retained stream kinetic/potential
energy. Using `h`, rather than `u`, for mass crossing the boundary includes
flow work. Do **not** add a separate `P dV/dt` term to this rigid-tank equation.
Dry saturated `h_g` is consistent with ideal separation; carryover/superheat
are excluded. `h_fw(P_steam, 500 K)` specifies the imposed inlet state.

The derived defaults and their L1 assessment are:

| Quantity | Independently checked value | Assessment |
|---|---:|---|
| Heat input | 3000 MWth | Plausible generic four-loop design scale. |
| Saturation temperature/pressure | 558 K / 6.899180 MPa | Plausible PWR main-steam conditions; reference values vary by SG design. |
| Feedwater | 500 K, `h_fw = 0.976402 MJ/kg` | Plausible heated feedwater; constant temperature is an imposed reservoir boundary, including during trip. |
| Dry steam enthalpy | `h_g = 2.773872 MJ/kg` | Correct IF97 lookup. |
| Design steam flow | 1669.012 kg/s | Correct `Q_design/(h_g − h_fw)`; about 417.25 kg/s per equivalent SG. |
| Phase masses | 222458.10 kg liquid; 10780.96 kg vapor | Correct for the chosen 600 m³/0.5 state; empirical geometry remains finding 6. |
| Stored energy | `3.066082e11 J` | Pressure-matched initial state, not exactly the all-IF97 reconstructed energy. |
| Initial admission / level | 1 / 0.5 | Deliberate full-power calibration / arbitrary collapsed-volume anchor, not independent plant measurements. |

The root solve is legitimate initialization: it keeps the IF97-defined mass/
level while finding `U` whose HEOS `(D,U)` inversion returns `P_ref`.
Numerical bracket widths and root tolerances are solver choices, not physical
constants.

It does **not** make IF97 and HEOS identical. At design, the phase-reconstructed
IF97 energy is 50.23 MJ lower than stored `U`. A direct sweep at 3, 6.899, 7.6,
8.2, and 12 MPa and collapsed fractions 0.30, 0.50, 0.95 found energy
differences no larger than about **0.018%** at those sampled points. The mixed
feedwater/steam enthalpy choice differs from an all-IF97 design heat check by
about **18.4 ppm**. These are tolerable L1 property inconsistencies, not a
failure of the implemented open-system energy balance. An exact single-EOS
model should use all HEOS properties, or solve a consistent IF97 mixture
relation; either is a later refinement, not a required M3 redesign [R3].

Independent conservation checks, not merely the endpoint criterion:

- The 1500 s manual-load run stored **7.515392 GJ** of additional shell energy.
  Integrating `Q_sg + m_fw h_fw − m_out h_g` with 0.25 s sampling agreed within
  **26.4 kJ**, or **3.51e-6 of the accumulated change**. During the ramp,
  accumulation reached about **62.34 MW**; heat input need not equal heat
  export at every instant.
- Isolated-shell 30 s BDF checks at fixed design heat/steam flow and 80% or
  120% feedwater produced the expected **−/+10014.074 kg** mass changes.
  Integrated energy discrepancies were about **23/21 J** for approximately
  **9.72 GJ** changes. This directly exercises the unequal-flow equation M4
  will need.

The 3 MPa pressure floor is sensible: `T_sat = 507.008 K` there, above 500 K;
`P_sat(500 K) = 2.638898 MPa`. The extra `1.001 · P_fw_flash` rule properly
protects hotter configured feedwater; 0.1% is a numerical subcooling margin,
not a plant safety margin. The 12 MPa ceiling is correctly called a model
domain ceiling, **not** a permissible SG operating pressure or relief setting.
`0 < x < 1` is necessary for this two-phase closure, but insufficient to
guarantee tube coverage.

More precise wording for the low-pressure limit would be “the imposed
single-phase 500 K inlet state is no longer valid.” Real heated feedwater
throttled from a higher pressure would generally flash **partially** at nearly
constant enthalpy; it would not acquire the full vapor enthalpy returned by a
constant-temperature low-pressure property call. No flashing inlet model is
required for the current bounded M3 scope.

### (h) What does M4 level work depend on?

The important foundation is already present: independent `(M,U)` states,
actual inlet/outlet enthalpies, both steam outlets in the mass balance, a
state-derived pressure/level closure, and consistent factory wiring. No sign
error or missing SG energy term needs fixing before M4.

Before interpreting M4 as more than inventory-control education:

1. **Define the controlled level and geometry.** Retain “collapsed liquid
   volume fraction.” Either substantiate volume/thresholds or use explicitly
   surrogate limits. Stop before uncovering invalidates constant `UA`, not
   merely at `x = 1`. Do not transplant narrow-range instrument percentages.
2. **Use actual feedwater flow in both balances and validation.** A lagged,
   limited actuator means demand and delivered flow differ. Preserve the
   pressure-dependent inlet enthalpy and custom-temperature guard. Add the
   transient accumulation checks in finding 5.
3. **Be precise about “three-element.”** Level PI plus steam-flow feedforward
   driving an ideal first-order flow-tracking actuator is a useful L1
   reduction. If actual feedwater-flow feedback is implicit in that actuator,
   say so; it is not three independently modeled measurement/control loops.
   Include dump/relief flow in total SG outflow.
4. **Do not claim to model shrink/swell.** A collapsed-volume plant with
   three-element-inspired control cannot demonstrate why an indicated-level
   controller initially acts in the wrong direction. That fidelity gain
   requires a void/recirculation or measurement model [R8], not just PI gains.
5. **Make feedwater availability after trips explicit.** Main-feed isolation,
   pump power/source, auxiliary feedwater, finite replacement inventory, and
   changing feedwater temperature are not represented. Actual P-4 has
   feedwater-related actions beyond its turbine-trip action [R7]. M4 should
   not silently imply these have been implemented.
6. **Test the limits, not only nominal endpoint bands.** Loss/excess
   feedwater, recovery from actuator saturation, pressure-dependent level
   offset, manual/auto transfers, and trip-with-automatic-control all matter.
   Tuning or re-banding to a model trajectory is a regression check, not
   independent validation of real-plant response.

**Recommended M4 scope:** retain the conservative equilibrium shell and add
honestly labeled inventory control, finite actuator response, and surrogate
domain limits. Defer distributed SG hydraulics, detailed turbine stages, and
plant-specific protection calibration; they are not prerequisites for this
educational milestone.

## References and verification notes

- **[R1]** Todreas & Kazimi, *Nuclear Systems, Volume I: Thermal Hydraulic
  Fundamentals*, 2nd ed., Ch. 6, “Nonflow and Steady Flow: First and Second-Law
  Applications,” starts p. 233; Ch. 7, “Nonsteady Flow First Law Analysis,”
  starts p. 319. Chapter titles/page starts verified in the
  [publisher-supplied Google Books contents](https://books.google.com/books/about/Nuclear_Systems_Volume_I.html?id=SAvMBQAAQBAJ).
  This review did not verify textbook equation numbers.
- **[R2]** Yan, *Introduction to Engineering Thermodynamics*,
  [§5.2.2 mass conservation and §5.2.3 energy conservation](https://pressbooks.bccampus.ca/thermo1/chapter/5-2-steady-flow-and-transient-flow/),
  explicit transient control-volume equations. Also
  [DOE-HDBK-1012/1-92, Vol. 1](https://www.steamtablesonline.com/pdf/Thermodynamics-Volume1.pdf),
  HT-01 p. 34 Eq. (1-20) for quality; p. 54 for accumulation; p. 59
  Eq. (1-22) for the **steady-flow** enthalpy balance. Do not cite the latter
  alone as though it includes transient storage.
- **[R3]** [CoolProp IF97 documentation](https://coolprop.org/fluid_properties/IF97.html)
  and [IAPWS IF97 release](https://iapws.org/documents/release/IF97-Rev).
  Numerical checks used direct `CoolProp.CoolProp.PropsSI` with explicitly
  selected `IF97::Water` and `Water` backends.
- **[R4]** NRC Westinghouse Technology Systems Manual,
  [§11.2, Steam Dump Control System](https://www.nrc.gov/docs/ML1122/ML11223A294.pdf),
  printed pp. 11.2-1–5 (PDF pp. 5–9), Rev. 0403: capacity, modes, no-load
  settings, and turbine-trip heat removal.
- **[R5]** NRC Westinghouse Technology Systems Manual,
  [§7.1, Main and Auxiliary Steam Systems](https://www.nrc.gov/docs/ML1122/ML11223A244.pdf),
  §7.1.3.3 p. 7.1-5 and §7.1.3.4 p. 7.1-6 (PDF pp. 7–8), Rev. 0101:
  atmospheric PORV and safety-valve capacities/setpoints.
- **[R6]** NRC Westinghouse Technology Systems Manual,
  [§8.1, Rod Control System](https://www.nrc.gov/docs/ML1122/ML11223A252.pdf),
  §8.1.4.2–5, pp. 8.1-6–8 (PDF pp. 10–12), Fig. 8.1-4, Rev. 0209:
  power mismatch, turbine-power-derived `T_ref`, deadband, lock-up, and speeds.
- **[R7]** NRC Westinghouse Technology Systems Manual,
  [§12.2, Reactor Protection System — Reactor Trip Signals](https://www.nrc.gov/docs/ML1122/ML11223A301.pdf),
  §12.2.3.16 p. 12.2-7 and §12.2.4 pp. 12.2-10–11 (PDF pp. 11, 14–15),
  Rev. 0109: reactor trip on turbine trip, P-4, and P-9.
- **[R8]** NRC Westinghouse Technology Systems Manual,
  [§11.1, Steam Generator Water Level Control System](https://www.nrc.gov/docs/ML1122/ML11223A293.pdf),
  pp. 11.1-2–3 (PDF pp. 4–5), Fig. 11.1-2, Rev. 0706:
  measured flows/level, narrow-range program, shrink and swell.
- **[R9]** NASA Glenn,
  [Mass Flow Rate Equations](https://www.grc.nasa.gov/www/k-12/airplane/mflchk.html),
  Eq. 10 and choking condition Eq. 19. This supports the **approximate
  pressure/temperature scaling**, not an exact wet-steam turbine-valve
  correlation.

The numerical sensitivity cases are this review's calculations, not published
plant results. Plant-specific volumes, MTC/burnup states, valve curves, and
licensing setpoints should come from the selected plant's FSAR/design data;
the cited generic training examples should not be promoted to those values.

## Disposition

Triage by the orchestrator (2026-09-28). No high-severity findings, so M-gate 3 has no open high item.

| # | Severity | Disposition |
|---|---|---|
| 1 | medium | fix now (M3.9.0, docs): replace generic Todreas & Kazimi / Reactor Concepts citations with precise sources (NRC Westinghouse Technology Systems Manual chapters for rod control, steam dump and SG relief; control-volume balance section for the shell equations); mark freely chosen L1 tuning as such. |
| 2 | medium | document (M3.9.0) + defer (roadmap): name `turbine_load` "admission" everywhere, state that `T_ref` is an admission-based proxy for the impulse-pressure program; a MW/steam-flow governor mode goes on the roadmap. |
| 3 | medium | fix now (M3.9.1): add the 8 steps/min plateau from 1.5 °F to 3 °F and the ramp to 72 steps/min at 5 °F; document the omitted 0.5 °F lock-up hysteresis, step quantization and power-mismatch (nuclear/turbine) anticipation as simplifications. |
| 4 | medium | document (M3.9.0, M3.9.3): label the turbine-trip-only case "unprotected: reactor trip on turbine trip omitted; ideal feedwater and aggregate dump/relief available"; state that P-4 is only the reactor-trip→turbine-trip direction. Configurable P-7/P-9 protection deferred (roadmap, RPS milestone). |
| 5 | medium | fix now (M3.9.2): rename the equilibrium criterion "equilibrium heat-rate mismatch" and add a transient ΔU = ∫(Q_sg + ṁ_fw·h_fw − ṁ_out·h_g)dt accumulation check using actual shell parameters/telemetry. The ΔM integral with non-zero inventory change is already planned in M4.4. |
| 6 | medium | document (M3.9.0; M4.3/M4.5 for the level limits): call V_sec = 600 m³ and the level anchors generic educational assumptions (drop the unsupported "150 m³ per Model-F shell" provenance) and call 0.30/0.95 conservative surrogate model limits, not plant elevations. |
| 7 | low | document (M3.9.0): state that the U root reconciles the initial pressure only (≈0.016 % stored-energy mismatch between the HEOS U and IF97 phase split). |
