# Implementation accuracy review

Baseline: `5dc6e641ef7807e323a5b9c90637696a60ad07e4`.
Reviewed by the primary agent. Implementation was kept unchanged.
Independently re-verified on 2026-09-26; see the audit section of
[README.md](README.md) for what changed. A8–A10 and the second branch of A2
come from that pass.

## Assessment

The individual point-kinetics equations and most component equations are
recognizable, readable educational models. The main physical defect is at a
component boundary: the fuel stores heat, but that storage is bypassed when
heating the primary loop. Several explanations also assign physical meanings
the implementation does not support.

The right next step is to repair those boundaries and explanations, then
calibrate the existing model. Spatial neutronics, a turbine, detailed rod
geometry, and a full two-phase primary loop are not prerequisites for a useful
learning simulator.

P1 means a central result is materially wrong; P2 means a concrete behavior or
teaching error worth fixing soon; P3 means a narrower limitation or correction.
Numerical evidence is reproducible with [reproduce.py](reproduce.py).

## Confirmed findings

### A1 — P1: The loop receives fission power instead of heat leaving the fuel

**Locations:** `src/fission_sim/physics/core.py:403-405`, `:434-436`;
`src/fission_sim/physics/primary_loop.py:353`;
`src/fission_sim/api/runtime.py:160-164`;
`tests/test_primary_plant.py:152-175`.

The core computes a fuel energy balance:

```text
C_f dT_f/dt = P_fission - Q_fc
Q_fc = hA_fc (T_f - T_cool)
```

However, its exported `power_thermal` is `P_fission`, and the loop uses that
directly as its heat input. Summing the implemented fuel and two loop thermal
storage terms therefore gives:

```text
dE_fuel/dt + dE_loop/dt = 2 P_fission - Q_fc - Q_sg
required for this interface = P_fission - Q_sg
residual = P_fission - Q_fc
```

Internal heat transfer must cancel between the two components. This conclusion
is an algebraic check of the code against the control-volume first law, not a
comparison with a higher fidelity reactor model. [Control-volume energy balance,
Yan §5.2](https://pressbooks.bccampus.ca/thermo1/chapter/5-2-steady-flow-and-transient-flow/).

**Reproduction:** keep design fuel/coolant temperatures and reduce normalized
fission power to `n=0.1`. Fission is 300 MW, heat leaving fuel is 3,000 MW, and
the SG removes 3,000 MW. The implemented fuel and loop each lose 2,700 MW, for
5,400 MW total storage loss; the external deficit is only 2,700 MW.

This occurs on an ordinary integrated SCRAM, too. Trigger SCRAM at `t=2 s`:

| Time after SCRAM | Fission power sent to loop | Heat actually leaving modeled fuel |
|---|---:|---:|
| 0.1 s | 1,499 MW | 2,986 MW |
| 0.5 s | 532 MW | 2,851 MW |
| 1 s | 324 MW | 2,653 MW |
| 2 s | 210 MW | 2,266 MW |
| 5 s | 134 MW | 1,363 MW |

**Impact:** fuel heat disappears without warming coolant. Cooldown, moderator
feedback, surge, and pressure trajectories respond to the wrong heat input.
During heatup the mismatch creates excess modeled stored energy instead.
Steady-state agreement hides the defect because `P_fission = Q_fc` there.

**Window, and interaction with A3.** The defect acts over the fuel time
constant `tau_fuel = M_fuel c_p_fuel / hA_fc = 5.17 s`, so it distorts
roughly the first 10–15 s of a transient rather than the whole trajectory.
That is exactly the window the SCRAM and rod-step demonstrations occupy.
Fixing A1 alone is not sufficient. With the configured 30,000 kg of thermal
mass the loop's own time constant is `(M_hot + M_cold) c_p / UA = 1.375 s`,
shorter than the fuel's (A9). Once fuel heat is routed correctly, that loop
still responds about four times faster than its represented inventory
implies. A1 and A3 together set the transient response; fix them together.

**Recommendation:** expose a distinct fuel-to-coolant heat-transfer signal and
use it consistently in the loop and surge calculation. Keep fission power as
a separate displayed quantity. An algebraic heat-transfer component consuming
fuel and coolant temperatures can preserve the engine's state-derived output
convention. A change to the component protocol is another option, but is not
required to fix this equation.

**Testing:** replace or supplement the misleadingly named transient energy
test with a balance evaluated while storage is changing. The existing test
only compares power with SG removal at `t=200 s`, after settling. It cannot
detect incorrect heat capacity or this missing interface. One non-equilibrium
balance and one coupled transient regression are sufficient.

### A2 — P2: Accepted controls leave the liquid-water domain without a model-limit response

**Locations:** `src/fission_sim/physics/coolprop.py:73-78`, `:96-99`;
`src/fission_sim/physics/surge.py:147-149`;
`src/fission_sim/physics/pressurizer.py:238-258`;
`src/fission_sim/api/runtime.py:449-455`.

The primary model assumes liquid coolant, but `density_PT` and `enthalpy_PT`
use unconstrained HEOS queries. The comment claims that HEOS silently
extrapolates near saturation. In fact, the property library can return vapor
properties on the other side or reject an ambiguous saturation state.
[CoolProp's phase documentation](https://coolprop.org/coolprop/HighLevelAPI.html#vapor-liquid-and-saturation-states)
describes exactly this behavior; it was reproduced with the locked version 7.2.0.

**Reproduction:** build the production runtime engine and repeatedly call
`engine.step(0.1, rod_command=0.6)`. This accepted UI/API command fails after the
last completed time `t=4.6 s`, with a CoolProp `ValueError` at approximately
16.4545 MPa and 622.780 K. The last successful snapshot has only 0.266 K
subcooling margin. The runtime catches the error and pauses, but exposes no
reason distinguishing a model-domain failure from an operator pause.

At the failure the rod is at 0.546, worth +644 pcm, essentially one dollar
(`sum(beta_i) = 650 pcm`), with `n = 1.78`. The accepted command was a
+1,400 pcm (2.15 $) demand; A8 explains why a 10 % rod move carries that
much reactivity.

**The crash is the benign branch.** Repeating the same command with the
loop's thermal masses set to the physically consistent value
(`M_hot = M_cold = 61,696 kg`, half of `M_loop_initial`) produces **no
error**. The hot leg crosses saturation at `t = 7.5 s`; by `t = 30–60 s` it
runs 8–9 K superheated while `density_PT` silently returns about
103 kg/m³, a vapor density, into the surge calculation. Spray is pinned at
25 kg/s and the simulation keeps running with nothing shown to the operator.
Fixing A3 alone therefore converts a loud failure into a silent invalid
state. The domain check recommended below is required regardless of the
other fixes; `reproduce.py --transients` shows both branches.

The pressurizer likewise derives quality with a two-phase lever rule without
checking that its mass/energy state is inside the saturation dome.

**Recommendation:** define the supported physical domain and stop at its
boundary with a clear model-limit status and last valid state. Check positive
inventory, valid pressure, liquid subcooling, and pressurizer quality as
appropriate. Account for solver trial states when enforcing the boundary.
Changing property backends, clamping quality, or forcing a liquid phase after
boiling starts does not make the current equations valid there.

This does **not** require adding boiling physics or automatic reactor
protection. A clear educational limitation is sufficient. Test one accepted
control path that reaches the boundary and verify a useful response.

### A3 — P2: Thermal-inertia parameters contradict their physical explanation

**Locations:** `src/fission_sim/physics/primary_loop.py:104-109`, `:181-183`,
`:289-297`; `src/fission_sim/physics/surge.py:135-144`.

The loop's two effective thermal masses total 30,000 kg. Its own physical
inventory calculation gives 123,392.6 kg of water at the design point. Both
temperature states also drive the expansion of the whole 175 m³ loop. Calling
the smaller number the combined water-plus-metal heat capacity, with metal
dominating, is inconsistent with this interpretation.

At the model's fixed `c_p=5,500 J/(kg K)`, the configured storage is 165 MJ/K;
the represented water alone would contribute about 679 MJ/K under the same
constant-heat-capacity approximation. A 300 MW imbalance thus changes modeled
average temperature at 1.82 K/s rather than about 0.442 K/s before any metal
storage is added. This factor is computed from repository parameters, not an
assumed plant-specific inventory.

**Recommendation:** choose and document a consistent interpretation. If the
states represent the whole inventory temperature, derive the water part of
thermal inertia from that inventory and add any justified metal equivalent.
If they represent only active subvolumes or deliberately accelerated teaching
dynamics, identify those volumes, justify the reduced response, and reconcile
the surge volume. Fixed thermal inertia is a reasonable simplification; the
current physical explanation for its value is not.

### A4 — P2: SCRAM timing claims are contradicted by the actuator equation and test

**Locations:** `src/fission_sim/physics/rod_controller.py:94-116`, `:269-272`;
`tests/test_rod_controller.py:243-267`; `README.md:925`, `:1176`.

The first-order tracker slows exponentially as it approaches the target. With
the defaults, a SCRAM from position 0.5 follows `position=0.5 exp(-t)`; the
speed cap only meets the raw rate at the initial instant. From position 1.0,
the cap binds for **one** second, followed by `0.5 exp(-(t-1))`.

| Initial fraction withdrawn | Position after 2 s | Position after 4 s |
|---|---:|---:|
| 0.5 | 0.067668 | 0.009158 |
| 1.0 | 0.183940 | 0.024894 |

The test named `test_scram_reaches_zero_in_2s` actually checks position at four
seconds against a loose 0.05 threshold. Its comment says the speed cap binds
for two seconds, while its printed numerical estimate corresponds to one.
The passing test therefore does not establish the documented behavior.
The test docstring at `:247-248` also promises "constant-velocity full
insertion in exactly 2 s".

The same comment block holds a second wrong statement: `rod_controller.py:95`
says the `v_scram` clip binds "for scram from any realistic position
(>0.05)". The clip binds only while `|error| > v_scram * tau = 0.5`, ten
times that threshold.

**Recommendation:** either describe the current smooth actuator honestly,
including a defined insertion tolerance, or choose a SCRAM-specific trajectory
that reaches that tolerance in the intended time. Retain the simple normal
motion approximation. Replace the existing test with an assertion at the
advertised time and an independently derived expectation; do not add another
test that merely restates `clip()`.

### A5 — P2: Several teaching explanations describe different physics

These overlap [readability R2](readability.md#r2--p2-teaching-text-assigns-the-wrong-meaning-to-several-model-outputs)
and should be one editorial fix, not separate duplicated work.

| Location | Issue | Correction |
|---|---|---|
| `web/src/widgets/tooltips.ts:143` | Attributes the shown shutdown tail to decay heat, which the core does not model. | Label displayed power as modeled fission power; explain that delayed neutrons sustain residual fissions and that fission-product decay heat is omitted. |
| `api/runtime.py:605-606`, `DEVELOPMENT.md:197-199` | Says delayed-neutron precursors keep the reactor from going subcritical; runtime says the precursors continue fissioning. | Precursors decay and emit neutrons. A subcritical reactor can still have residual fission power. Reactivity and power are different quantities. |
| `web/src/widgets/tooltips.ts:72` | Explains Doppler feedback as neutrons slowing more easily. | Hotter fuel broadens absorption resonances, increasing neutron capture, especially in U-238. |
| `physics/core.py:154-157` | Associates positive moderator coefficient with low boron and gives an unqualified operating-rule claim. | High soluble-boron concentration can make the coefficient more positive. Keep the constant negative coefficient as the chosen operating-regime approximation; remove unsupported general rules. |
| `web/src/widgets/thresholds.ts:31`, `:48` | Describes arbitrary display bands as safety limits and 200 pcm as a prompt-criticality concern. | Mark them as illustrative alert bands. This model's prompt-critical threshold is `sum(beta_i)=0.006502`, or 650.2 pcm. The average fuel state does not predict a fuel-failure threshold. |

The kinetics distinction follows from the delayed-source terms in the model
and the standard point-reactor equations. [O'Rourke, Ramsey and Temple, §2,
equations (1a–b)](https://laro.lanl.gov/view/pdfCoverPage?download=true&filePid=13158275280003761&instCode=01LANL_INST).
Decay heat is energy from radioactive fission-product decay. [NRC explanation](https://www.nrc.gov/regulations-legislation/fact-sheets-brochures/backgrounder-on-the-three-mile-island-accident).
The Doppler and soluble-boron corrections are supported by
[IAEA NS-G-1.12, Appendix I.4–I.5](https://www-pub.iaea.org/MTCD/Publications/PDF/Pub1221_web.pdf#page=55).
That older publication is used here for the physics explanation; it is
superseded and is not being cited as a current operating requirement.

The absence of decay heat is acceptable for a clearly labeled fission-kinetics
demonstration. It is inappropriate to use its trace as total post-shutdown heat
or imply that the feature is already implemented.

### A6 — P3: The fixed expansion coefficient's stated bias is reversed

**Locations:** `src/fission_sim/physics/primary_loop.py:148-153`;
`src/fission_sim/physics/surge.py:139-143`.

The comments say the design-frozen coefficient underpredicts cooldown surge
and overpredicts heatup surge. At 15.5 MPa, the repository's CoolProp wrapper
returns `beta_T = 0.002667, 0.003256, 0.004270 /K` at 568, 583, and 598 K.
The fixed value 0.0033 is larger at the cold end and smaller at the hot end.
For otherwise equal inputs it therefore **overpredicts** the magnitude at
lower temperatures and **underpredicts** it at higher temperatures. These
statements refer to temperature relative to the reference, not simply the
sign of a transient.

The same comment gives the wrong numeric range. It says `beta_T` spans
"~2.0e-3 to ~3.0e-3 /K, sometimes higher near 583 K"; the wrapper returns
2.67e-3 to 4.27e-3 /K across 568–598 K, and 583 K is mid-range, not a peak.

**Recommendation:** correct the explanation. Keeping a constant coefficient
near the design point is reasonable; dynamic properties are optional.

### A7 — P3: The surge helper's mean temperature is not the published `T_avg`, and the comment's error bound is unsupported

**Locations:** `src/fission_sim/physics/surge.py:130-136`;
`src/fission_sim/physics/primary_loop.py:353-356`, `:400-403`.

The helper estimates `dT_avg/dt` as `(Q_core-Q_sg)/((M_hot+M_cold)c_p)`.
That expression is exactly the time derivative of the **mass-weighted**
mean temperature for any masses, and it is the energy-consistent driver of
net expansion. It equals the derivative of the loop's published
**arithmetic** `T_avg` (`primary_loop.py:403`) only when the masses are
equal. The comment's claim that asymmetry changes the answer by only a few
percent has no general bound.

**Reproduction:** set `M_hot=10,000`, `M_cold=20,000 kg`; start at reference
temperatures with the hot leg one kelvin warmer; hold `Q_core=Q_sg=3 GW`.
The published `T_avg` changes at `-0.4625 K/s` while the helper reports zero
surge. Net stored energy is unchanged in this case, so zero is the
defensible physical answer. The defect is that two different "average"
temperatures coexist without the code saying so.

**Recommendation:** correct the comment and state which mean drives surge.
Either publish a mass-weighted average as well, or document that the
arithmetic `T_avg` used for SG heat transfer and feedback is not the one
that drives surge. Do not rewrite the helper around the arithmetic mean;
that would make it less physical. The default symmetric configuration is
unaffected either way.

### A8 — P2: The operator's rod command carries the whole 14,000 pcm bank worth

**Locations:** `src/fission_sim/physics/rod_controller.py:117-129`, `:344`;
`src/fission_sim/api/runtime.py` rod-command validation;
`web/src/controls/ControlPanel.tsx:278`.

Rod worth is linear with `rho_total_worth = 0.14`, so the full 0→1 stroke is
14,000 pcm and the operator slider spans the entire shutdown worth. A move
from 0.5 to 0.6 is a +1,400 pcm (2.15 $) demand; one dollar is 4.6 % of
travel. At the normal rate `v_normal = 0.01 /s` the bank inserts reactivity
at 140 pcm/s. A real control bank has on the order of 1,000–1,500 pcm over
its full travel. The number used here is the worth of the whole rod set,
appropriate for SCRAM but not for the operator's fine control.

This is the root cause of A2. Any accepted command of a few tenths reaches
prompt criticality within seconds, and the coolant follows within a few more
because the loop's inertia is also small (A3, A9).

**Recommendation:** separate control-bank worth from shutdown worth, or
bound the operator command to a band around the design position that maps
to a realistic control-bank worth. Say in the UI what one slider step is
worth in pcm. Keep linear worth; an S-curve is optional. One test that a
full-range operator command stays below prompt critical is enough.

### A9 — P3: The loop's thermal time constant is shorter than the fuel's

**Locations:** `src/fission_sim/physics/primary_loop.py:104-109`;
`src/fission_sim/physics/steam_generator.py` (`UA`);
`src/fission_sim/physics/core.py` (`M_fuel`, `c_p_fuel`, `hA_fc`).

| Quantity | Value |
|---|---:|
| `tau_fuel = M_fuel c_p_fuel / hA_fc` | 5.17 s |
| `tau_loop = (M_hot + M_cold) c_p / UA`, configured | 1.375 s |
| `tau_loop` with the represented 123,393 kg inventory | 5.66 s |

In a real plant the primary inventory responds far more slowly than the fuel.
Here the ordering is inverted, so with A1 the coolant tracks fission power
almost instantly. This is the mechanism behind the 4.6 s saturation in A2 and
the quantitative form of A3. No fix beyond A3 is needed; it is listed so the
corrected parameters can be checked against this ordering.

### A10 — P3: Parameter comments state numbers the code does not support

| Location | Comment | Problem |
|---|---|---|
| `core.py:158-159` | "published PWR range -1 to -5×10⁻⁵ /K at hot full power" for the moderator coefficient | That is −0.6 to −2.8 pcm/°F. Commonly cited hot-full-power values are on the order of −5 to −30 pcm/°F, about −1e-4 to −5e-4 /K. The chosen −5e-5 /K is a defensible weak beginning-of-cycle value; the stated range is not. Verify against a cited table before changing the value. |
| `primary_loop.py:134-142` | Derives "~80–100 m³ for piping + RPV" by subtracting steam-generator primary volume, then uses 175 m³ | SG primary volume is part of the expanding inventory and should not be subtracted; either way the arithmetic does not produce 175 m³. |
| `primary_loop.py:227` vs `:96`; `README.md:928` | "~32 K at design" vs "ΔT ≈ 29.5 K"; the README gives hot/cold ~596/~564 K | Derived references are 597.7/568.3 K, ΔT = 29.5 K. One design point, three sets of numbers. `c_p = 5,500` vs CoolProp 5,736 J/(kg K) at the design point is a further 4 % that is harmless but worth a note. |
| `rod_controller.py:95` | Scram clip binds "from any realistic position (>0.05)" | The threshold is 0.5 (A4). |
| `tests/test_primary_plant.py:38` | Lists `m_dot_surge` as a loop input | The port is now `P_primary`. |

These are teaching-text defects, not model defects. Fix them together with
A5 and the readability items.

## Reasonable simplifications and remaining modeling limits

- **Point kinetics:** the neutron and six precursor equations have consistent
  signs and units; precursor equilibrium scales correctly with initial neutron
  population. The source-free approximation is reasonable near powered
  operation. An exactly zero neutron/precursor state cannot start itself, so
  this is not yet a source-driven cold-start model.
- **Feedback:** constant negative temperature coefficients and one fuel
  temperature can illustrate stabilizing feedback near a chosen reference.
  They do not model burnup-dependent coefficients, spatial peaking, xenon,
  boron changes, or fuel failure. None is required just to fix A1.
- **SG and secondary sink:** fixed `UA`, an average temperature difference,
  and a fixed-temperature reservoir are honest low-order heat-removal models.
  They cannot predict secondary inventory, turbine response, or loss-of-feedwater
  behavior. Allowing signed heat flow through a heat exchanger is reasonable.
- **Pressurizer:** total mass/internal energy, a saturated equilibrium closure,
  and direction-specific stream enthalpy are sensible lumped choices inside
  the two-phase domain. The shared surge function makes loop/pressurizer mass
  exchange cancel. Passing mass conservation alone does not validate the
  physical size of surge or close the plant energy balance.
- **Pressurizer coupling remains approximate:** the loop thermal equations
  omit matching surge/spray enthalpy exchange and do not enforce inventory
  against density/rigid volume as pressure varies. Document these limits and
  quantify their effect before presenting full-plant energy conservation.
  Their importance depends on the scenario; this review does not demand a
  compressible hydraulic network for the current educational scope.
- **Flow-work explanation needs correction:** `pressurizer.py:386-389` says
  flow work vanishes for a rigid tank. Rigid-wall boundary work vanishes;
  stream flow work is already included in `h=u+Pv`. The implemented enthalpy
  balance is appropriate. A future vapor outlet adds an outgoing enthalpy
  term under the same framework. [MIT explanation of enthalpy and flow work](https://web.mit.edu/16.unified/www/FALL/thermodynamics/chapter_6.htm).
- **Mixed property backends:** deriving the initial vessel inventory with IF97
  and inverting it with HEOS gives 15.499345 MPa instead of exactly 15.5 MPa
  (about 655 Pa difference). This is small relative to the 150 kPa deadband
  and is not a priority at L1. Avoid calling the closure exactly self-consistent.
- **Controller:** proportional control, a deadband, actuator saturation, and
  manual overrides implement the stated control law. Missing integral action
  or valve dynamics is not automatically a defect.
- **Numerics:** BDF is appropriate for stiff neutron/thermal timescales, and
  pure component evaluations suit adaptive solver trials. A fixed `max_step`
  does not guarantee hitting every discontinuity or narrow pulse in an
  arbitrary scenario callback; explicit event segmentation is a future need
  if short scheduled pulses become supported scenarios.

## Verification and limits

Read all physics/control code, engine integration, production wiring, relevant
UI descriptions, examples, and physics/plant tests. Ran the existing test suite
and direct balance/property/actuator/coupled-transient probes. The standalone
core demo's inconsistent reference temperature is recorded in readability R3.

The sources above support governing equations and specific explanatory
corrections. This review did not verify every inherited textbook page/equation
number, exact plant parameter, or claimed percentage accuracy. Several NRC and
OSTI full-text requests failed; the NRC decay-heat definition was available in
its indexed official page, while the LANL manuscript, IAEA appendix, MIT notes,
CoolProp docs, and control-volume text were directly readable. Inherited
`.claude/agents` descriptions were not used as scientific authority.

No independent plant benchmark or licensing analysis was performed. The
strongest conclusions here are reproducible internal inconsistencies, not
claims of a validated high fidelity plant model.

The second pass re-read every cited location, re-ran every probe, and added
the rod-worth, time-constant, and silent-saturation probes to
[reproduce.py](reproduce.py). It confirmed the point-kinetics constants
(Keepin U-235 six-group values), the SG `UA`, the secondary saturation
temperature, and the flow-work and mixed-backend statements above.
