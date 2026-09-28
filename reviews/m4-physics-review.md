# Milestone 4 — independent physics review

## Summary

**Review date:** 2026-09-28. **Revision reviewed:**
`93e46f735be18ee0afa10bab17e34d041020b828`.
Scope: M4 steam-generator inventory/level dynamics, feedwater actuation and
control, secondary conservation, and interpretation of the supplied validation
trajectories. This is an educational L1 model review, not plant qualification.

**Result: no high findings, four medium findings, three low suggestions.**
The M4 governing equations, signs, default controller gains, and
back-calculation implementation are physically and dimensionally coherent.
The measured setpoint overshoot and load-ramp excursion are explicable without
retuning. The persistent post-trip offset is an actuator-authority limitation,
not failed anti-windup. The loss-of-feedwater electrical-power increase is
**not evidence of an energy-balance error**: steam flow increases and stored
secondary energy is depleted. Its precise magnitude remains an unvalidated
cycle-efficiency proxy.

Specific strengths:

- Actual **lagged feedwater flow**, not controller demand, enters both shell
  balances. Steam through both turbine and dump paths is counted.
- Stored energy is internal energy; boundary transport correctly uses
  enthalpy, including flow work. M4 checks nonzero inventory accumulation
  instead of relying on the former flow-matching identity.
- Controller and actuator share the resolved shell parameters and the same
  flow ceiling. That agreement makes the saturation correction meaningful.
- Back-calculation has the correct sign and gain normalization, unwinds from
  both limits, and avoids the discontinuous integral-freeze switching that
  caused BDF difficulty.
- The README distinguishes collapsed liquid fraction from indicated level,
  identifies the actuator/gains as L1 tuning choices, and already includes
  shrink/swell plus geometry/instrument mapping on the L2 roadmap.
- The 0.30/0.95 limits are explicitly surrogates, and the unsupported Model-F
  volume provenance has been removed. Those M3 dispositions are respected.
- The validator retained counterintuitive results and documented the
  persistent offset rather than forcing the model to satisfy an expected
  narrative.

### Evidence and independence

Reviewed the requested source, wiring, acceptance helpers/tests, README
sections, plan/amendments, M3 dispositions, and relevant M4 validation-report
sections. Opened the dense load-ramp, setpoint-step, mass-integral,
loss-of-feedwater, and trip-plus-SCRAM plots. Sampled the validator's saved
NPZ trajectories; those samples are distinguished below from new calculations.

Additional checks ran entirely in memory with bytecode writing disabled:

- A new 600 s admission-ramp run, independently reconstructing mass and
  energy integrals from actual flows and direct CoolProp calls at 1 s and
  0.25 s readout spacing.
- A new loss-of-feedwater run through 63 s, still inside the level domain,
  using `max_step=0.1 s`; all sampled snapshots passed domain checks.
- An independently derived linear closed-loop response, exact
  pressure/inventory decompositions of level, a reachable manual/automatic
  transfer, and BDF upper/lower saturation-recovery checks.
- Verification of the public conservation equations, NRC level-control
  discussion, choked-flow scaling, and Todreas/Kazimi chapter title.

The full pytest/web suites were **not rerun by this reviewer**; their passing
results are evidence supplied by the milestone validator. Only this review
file was written. No source, tests, documentation, examples, or validation
artifacts were modified, and no commit was made.

## Findings — Important / Suggestions

Paths are relative to the repository root. Medium findings concern specific
learner-facing interpretation or citation gaps, not required retuning of the
accepted L1 equations. None requires a high rating under the requested rule.

| # | severity (high/medium/low) | file:line | finding | reference | proposed change |
|---|---|---|---|---|---|
| 1 | medium | `src/fission_sim/physics/sg_secondary.py:560–563,595–600`; `README.md:186,1723–1726` | **The inventory/flow cue is not time remaining to M4's level boundary.** `M_l/m_out` starts at 133.29 s, whereas the new 0.30 boundary is reached about 53.5 s after zero feedwater demand. Even a frozen-pressure estimate to that boundary is only 50.73 s before actuator rundown is included. The README's safety disclaimer helps, but “how long would the water last?” still hides the distinction newly made important by M4. | [R1] §5.2.2; [R3] level/inventory distinction; calculation in answer 5. | Preserve the API if desired, but label this explicitly **total-liquid inventory divided by present steam flow, not time to the low-level model limit**. State the constant-flow/property assumptions. Optionally add a separately named approximate time-to-surrogate-limit diagnostic. At negligible steam flow, use an explicit unavailable/unbounded indication rather than presenting the epsilon-denominator result as a forecast. |
| 2 | medium | `tests/test_sg_level_plant.py:97–101`; `README.md:1302–1303,2251` | **The post-trip test name says “recovers,” but the setpoint is no longer attainable.** The final level is 0.516390 and changes by only about `3.1e-8` over the final 300 s. The positive tracked integral is correct; zero feedwater cannot drain the shell, and no useful sustained steaming remains without decay heat. This is the new M4 control consequence of the already-dispositioned M3 shutdown simplification. | [R1] mass balance; [R2] §11.4, actuator saturation; answer 6. | Name the check “remains bounded with one-way-flow residual,” and explain the persistent offset next to the acceptance result/controller limitations. Test bounded level, negligible final feedwater, and finite tracked integral; do not require exact setpoint recovery or introduce negative feedwater to manufacture it. |
| 3 | medium | `README.md:2249`; `src/fission_sim/physics/turbine.py:446–465` | **The newly exercised inventory-depletion transient needs an explicit electrical-proxy explanation.** The 990→1071 MW rise is plausible in direction at fixed admission, but it is not validated turbine-generator performance or a measure of current reactor/SG heat. Pressure raises steam flow by 8.64%; `h_g−h_fw` actually falls by 0.45%. Calling the rise simply a rising “steam-work” factor would teach the wrong mechanism. The inherited M3 proxy itself need not be changed. | [R1] §5.2.3; [R4] properties; [R5] Eqs. 10, 19; answer 7. | Add a M4 loss-of-feedwater note: unprotected fixed-admission experiment; stored inventory/energy is being consumed; electrical output is a fixed-cycle-efficiency proxy, not a transient turbine work balance. Retain the equation for L1. A later turbine model should use inlet/exhaust states and appropriate efficiencies, not clamp output to instantaneous fission power. |
| 4 | medium | `src/fission_sim/physics/feedwater.py:23–25,111–118,245–251`; `src/fission_sim/control/feedwater_controller.py:45–47,340–346` | **New M4 comments misidentify Todreas & Kazimi Ch. 7 as a feedwater-system/control reference.** That chapter is “Nonsteady Flow First Law Analysis,” not provenance for this pump/valve lag or PI law. The gains are honestly labeled choices, and the corrected Åström/Murray §11.4 citation is appropriate; the remaining attribution is separate from that fix. | [R6] verified contents; [R2] control structure; [R3] actual SG control architecture. | Cite Ch. 7 only for applicable transient first-law reasoning. Attribute the first-order actuator to an explicitly chosen L1 constitutive model, PI/back-calculation to the control reference, and real three-element signals to NRC §11.1. Do not imply the textbook supplies the 5 s lag or 120% ceiling. This concerns newly added M4 comments, not reopening corrected M3 citations. |
| 5 | low | `src/fission_sim/control/feedwater_controller.py:324–338,402–403`; `tests/test_feedwater_controller.py:107–115` | **Freezing the integral in manual is not bumpless manual/automatic transfer.** In a reachable run with manual demand 0.9 from 10 to 100 s, level reaches 0.527994; switching to auto changes demand from 1802.53 to 1563.60 kg/s, a 238.93 kg/s step. Actual flow remains continuous through the 5 s lag. This is an intentional simple controller, not a conservation defect. | [R2] §11.4, “Manual Control and Tracking”; answer 2. | Document that transfer can introduce a demand step. If bumpless feedwater transfer becomes a requirement, track the manual output with the automatic controller state and synchronize the manual command on the opposite transfer; add a transfer test. |
| 6 | low | `src/fission_sim/control/feedwater_controller.py:259–262`; `README.md:2049–2050` | **`I` is not always the literal time integral of level error.** Back-calculation modifies it in saturation, and manual mode freezes it. In the trip tail, negative level error coexists with positive `I≈4.425 s`, correctly. The unqualified state definition can make correct telemetry look like a sign error. | [R2] §11.4; implemented anti-windup equation; answer 2. | Define it as the **tracked PI integral state**, equal to the accumulated level error only during unsaturated automatic operation, with the appropriate initial offset. Retain the existing telemetry key for compatibility. |
| 7 | low | `tests/test_sg_level_plant.py:39–45`; `src/fission_sim/validation/secondary_acceptance.py:305–349` | **The mass-conservation acceptance normalization is much looser than the observed accuracy.** A tolerance of `0.001 M_initial` allows about 233 kg residual, approximately 7.3% of this transient's maximum inventory change, although the observed error is only 0.98 kg. The separate `abs(ΔM)>100 kg` condition alone does not ensure the signal exceeds that allowed error. | [R1] §5.2.2; independent quadrature convergence in answer 8. | Keep an absolute numerical floor but also scale the residual to nonzero accumulated inventory change, or require the test signal to greatly exceed the allowed error. Distinguish mass-normalized and change-normalized fractions in reports. No current mass-balance failure was found. |

## Answers to the review questions

### 1. Gains and closed-loop behavior

**Keep the defaults for this L1 plant.** The units and magnitudes are coherent:

```text
K_p = 3340 kg/(s · unit collapsed fraction)
K_i = 11.133333 kg/(s² · unit collapsed fraction)
T_i = K_p/K_i = 300 s
```

A 0.05 error initially adds 167 kg/s, about 10% of the 1669.012 kg/s design
flow. This is a five-percentage-point change in the model's whole-volume
fraction, not five percentage points of a narrow-range transmitter.

For fixed saturation pressure, the mixture mass/volume relation [R1, R4] is

```text
M = V [rho_v + (rho_l − rho_v)L]
C_L = ∂M/∂L |_P = V(rho_l − rho_v)
```

At 558 K and 6.89918 MPa, direct IF97 calls give
`rho_l=741.527 kg/m³`, `rho_v=35.9365 kg/m³`, and
**`C_L=423354.27 kg per unit level`**. Using `rho_l V` alone overestimates
that capacity by about 5.1%, because vapor occupies the volume vacated by water.

Linearizing the stated actuator and unsaturated PI law gives the following
review-derived transfer function, not a claimed plant correlation:

```text
L(s)/L_set(s) =
  (K_p s + K_i)/(tau_fw C_L s³ + C_L s² + K_p s + K_i)
```

Its poles are `−0.191921 s⁻¹` and
`−0.00403934 ± 0.00332996i s⁻¹`. The dominant decay envelope is about
248 s; settling takes several such times, not one 5 s actuator time constant.
For this fixed-pressure cubic the Routh condition reduces to
`K_p > tau_fw K_i`, equivalently `T_i > tau_fw`; 300 s versus 5 s is
comfortably stable. This is a local check, not a stability proof for every
coupled operating condition.

| Setpoint-step quantity | Independent linear calculation | Supplied coupled trajectory |
|---|---:|---:|
| Maximum level following 0.50→0.55 at 10 s | 0.559783 | 0.559884 |
| Absolute peak time | 424.3 s | 423 s |
| Overshoot above 0.55 | 0.009783 | 0.009884 |

The observed overshoot is **19.77% of the requested step**, or **0.9884
percentage points of full-scale collapsed fraction**. The PI zero matters:
using the textbook zero-free second-order overshoot formula alone would
underpredict this response. The final 1200 s residual of `9.84e-5` is
consistent with a damped settling tail.

The automatic admission-ramp excursion of **0.0018016** is only **0.18016
percentage points**, with a final residual near `2e-6`. It is reasonable for
this ideal-measurement, no-swell plant, not evidence of unusually good real
instrumented SG control.

For comparison, the NRC reference controller uses a **two-minute integral
time** and a lagged actual-level signal [R3, p. 11.1-3]. The model's five-minute
reset is a defensible slower L1 choice on a different level coordinate; do
not import the NRC gain/reset settings without the corresponding instrument,
flow loop, and void dynamics. Changed shell volume or measurement scaling
requires a fresh tuning assessment.

### 2. Back-calculation and its tracking time

**The implemented scheme is correct.** With `u_raw=m_out+K_p e+K_i I`:

```text
u_c = clip(u_raw, 0, m_fw,max)
dI/dt = e + (u_c − u_raw)/(K_i T_t)
T_t = 30 s
```

This is standard back-calculation expressed in the code's integral-state
units [R2, §11.4]. Dividing by `K_i` is necessary because `I` has units of
seconds of level error, rather than units of flow.

- Upper clipping gives a negative tracking correction; lower clipping gives
  a positive correction. Both limits permit unwinding.
- Unsaturated operation gives exactly `dI/dt=e`.
- The right-hand side is continuous at clipping boundaries, though not
  differentiable there. That is a useful numerical improvement over the
  former discontinuous conditional-freeze rule; retaining BDF is appropriate.
- `T_t=30 s` lies between the 5 s actuator and 300 s reset. It is a reasonable
  tracking choice, **not a published universal SG setting** or a mandatory
  `T_i/10` rule.
- The correction models **demand-limit saturation**, not the difference
  between demand and actual lagged flow. This is adequate for the present
  ideal flow-tracking actuator with the shared ceiling. It would not cover
  an unmodeled pump failure, pressure-dependent capacity, or valve deadband.

For fixed error/outflow at a saturated equilibrium,
`u_raw=u_c+K_i T_t e`. Thus zero integral derivative need not mean zero
error or raw demand exactly at the clip. At the post-trip endpoint:

```text
e          = −0.01638984
m_out      ≈ 3.94e-6 kg/s
I_eq       = e(T_t − T_i) − m_out/K_i = 4.425256 s
u_raw      ≈ −5.47421 kg/s
u_c        = 0
```

These match the saved trajectory. The positive integral is **not windup or a
sign error**. Independent mixture-capacity toy loops with saturated upward
and downward steps both integrated successfully with BDF and returned near
their setpoints by 1200 s. No additional hard integral clamp is necessary
for these demonstrated cases.

Manual operation remains a different limitation: freezing `I` prevents new
manual-mode windup but does not track the selected manual output. For a later
bumpless design, a manual tracking target is
`I_track=(u_manual−m_out−K_p e)/K_i`, approached through a documented tracking
time or initialized consistently at transfer [R2]. This is not required to
repair the current automatic anti-windup.

### 3. Does collapsed level move in the right direction after a load change?

**Yes, for this collapsed saturated-volume coordinate. It need not have the
same initial sign as indicated level.**

Differentiating the mixture relation above gives

```text
dL/dt = (m_fw − m_out)/[V(rho_l − rho_v)]
        − [L rho_l'(P) + (1−L)rho_v'(P)]/(rho_l−rho_v) · dP/dt
```

The derivatives are **along saturation**, not isothermal compressibilities.
Near the design point, the constant-mass sensitivity is
`∂L/∂P ≈ +0.0085854 per MPa`. Rising saturation temperature reduces liquid
density sufficiently that the collapsed fraction increases despite the
opposing vapor-density contribution.

At the saved automatic-ramp level peak, `t=100 s`:

```text
pressure increase                         = 0.187655 MPa
mass increase                             = 81.24 kg
level change from pressure at fixed M0     = +0.00160851
additional level change from actual ΔM     = +0.00019310
total                                     = +0.00180162
```

This is an exact finite-change decomposition using IF97 densities, not
merely a qualitative story. The small mass contribution includes the
feedwater lag and PI response. The pressure/property term accounts for
about 89% of the peak excursion.

A real steam-demand reduction has an initial **void-collapse shrink**
contribution [R3, p. 11.1-3, Fig. 11.1-2]. That contribution is absent here.
Do not flip the current mass-balance or level-feedback sign to imitate it.

### 4. L2 shrink/swell: should it be on the roadmap, and in what form?

**Yes; the existing roadmap entry is appropriate.** A useful upgrade needs
a distinction between conserved inventory, bubble distribution, geometric
surface elevation, and the instrument signal. Adding a PI gain or relabeling
`level_sg` does not create shrink/swell.

Two concrete paths:

1. **Indication-only transient surrogate — small effort, limited fidelity.**
   Retain `(M,U)` and collapsed level, then add a separately named indicated
   signal. For example, a pressure washout can have
   `tau_P dp_f/dt=P−p_f` and `delta H_void=−K_P(P−p_f)`, with positive
   `K_P` in m/Pa. It gives positive swell on falling pressure and shrink on
   rising pressure without adding or removing inventory. Heat-input and
   feedwater-subcooling effects would need separately justified terms.
   This is an empirical transient indication model, not a phase balance;
   it cannot by itself predict steady load-dependent void holdup or dryout.
2. **Conservative bubble/recirculation model with instrument mapping —
   moderate-to-large effort, meaningful L2 gain.** Keep total mass and energy
   balances, but resolve at least riser/boiling-region and dome/downcomer
   inventories or their distribution. A conceptual entrained-vapor balance
   is `dM_b/dt=Gamma_evap−Gamma_cond−m_sep`, with `V_b=M_b/rho_v(P)`.
   Consequently
   `dV_b/dt=(Gamma_evap−Gamma_cond−m_sep)/rho_v
   − (V_b/rho_v)(d rho_v/dP)dP/dt`.
   Use geometry to convert the relevant liquid plus entrained-vapor volumes
   to surface elevation, then calculate differential-pressure indication
   from tap elevations, reference-leg density, and local mixture densities.
   All evaporation/condensation and interregion transfers must be equal and
   opposite in companion balances: **do not add an independent bubble mass
   on top of the existing equilibrium vapor inventory**.

**Recommendation: option 2 for an actual L2 level component; option 1 only
as an explicitly empirical intermediate teaching aid.** The displayed
geometric surface is not automatically a narrow-range differential-pressure
reading, especially with a downcomer.

These are proposed model structures motivated by [R1, R3], not quotations
of a calibrated Model-F correlation. The supplied evidence does not establish
a defensible Model-F bubble residence time, riser area, or pressure-washout
gain; obtain them from identified geometry and transient data rather than
inventing constants. Re-tune/test level control after adding this path,
including both load directions and the inverse initial indication.

### 5. The 0.30/0.95 surrogates, 5 s actuator, and 120% ceiling

**Acceptable educational choices; not verified Model-F limits or equipment
ratings.** At the reference pressure, the current volume coordinate implies:

| Collapsed fraction | Liquid volume | Vapor volume | Total shell mass |
|---|---:|---:|---:|
| 0.30 | 180 m³ | 420 m³ | 148.57 t |
| 0.50 | 300 m³ | 300 m³ | 233.24 t |
| 0.95 | 570 m³ | 30 m³ | 423.75 t |

There is no area-versus-height curve, tube displacement map, recirculation
void distribution, separator elevation, or tap calibration with which to
identify 0.30 as actual tube top or 0.95 as actual carryover onset. In
particular, 0.95 leaves finite steam space; it does not mean a solid vessel.
“Conservative” here can describe a buffer inside the mathematical liquid/
vapor endpoints, **not established conservatism relative to a real plant**.
The M3 disposition to call these generic surrogate limits is sufficient;
it is not reopened as a new defect.

The initial mass margin to 0.30 at fixed pressure is **84.671 t**, not the
entire 222.458 t liquid inventory. With zero feedwater and frozen properties/
outflow, the surrogate-limit estimate is

```text
t_low,approx = V(rho_l−rho_v) max(L−0.30,0)/m_out = 50.73 s
```

The 5 s exponential feedwater rundown adds approximately
`tau_fw m_design=8.345 t` of inlet inventory, equivalent to about another
5 s at design outflow. Rising pressure/outflow then shortens the transient.
The supplied finer run places the crossing around 63.5 s absolute time,
about 53.5 s after the 10 s command; the 1 s endpoint checker reports 64 s.
That scale is consistent with the inventory equations.

The actuator equation is a credible **closed-loop flow-response surrogate**:
5 s means 63.2% response in 5 s and about 95% in 15 s, not complete valve
closure in 5 s. Calling the zero-demand case a command/rundown experiment is
more precise than claiming a calibrated pump-trip coastdown.

The maximum is **2002.815 kg/s**, leaving **333.802 kg/s** headroom above
design outflow. A five-point level error's 167 kg/s proportional correction
fits comfortably inside that headroom. A 120% flow capability is a
reasonable illustrative overcapacity, but cannot be asserted available
throughout the entire pressure range without pump/head and valve data.
Current comments acknowledge those omissions. No retuning is warranted.

### 6. Persistent post-trip level 0.516: acceptable for L1?

**Yes, if identified as a persistent one-sided-control residual, not normal
post-trip level recovery.**

At the early peak (`t=18 s`), the shell has gained 5.318 t:
mass accumulation contributes about `+0.012961` level and the pressure/
density change another `+0.007906`, giving the observed `0.520867`.
Rapid turbine closure with slower feedwater response explains the inventory
increase without invoking swell.

At 1200 s:

```text
L                                  = 0.51638984
P                                  ≈ 7.600000 MPa
net shell mass gain                = 4.30089 t
fixed-initial-mass pressure effect  = +0.00598705 level
additional mass effect             = +0.01040279 level
```

Thus the remaining level elevation is **not solely the 4.3 t mass gain**.
At the final pressure, returning to 0.50 would require removing about
6.776 t. The controller can stop adding water but cannot remove that mass.
As fission/stored-heat removal decays and the pressure-controlled outlet
closes, the no-decay-heat plant supplies no sustained removal mechanism.
Integral action cannot overcome that physical constraint.

Preserve the residual in L1. Do not introduce negative feedwater, a hidden
mass sink, or an arbitrary integral clamp to force 0.50. Decay heat and an
available steam-removal path would change the later inventory evolution;
main/auxiliary feedwater transitions and realistic post-trip cooling remain
separate future physics. This does not reopen the settled omission of decay
heat as an M4 implementation blocker.

### 7. Loss of feedwater: why does electricity rise while fission falls?

**Plausible direction under the modeled unprotected, fixed-admission
conditions; not a demonstrated turbine-work or SG-energy error.**

The supplied 64 s endpoint is the first sampled point outside the surrogate
level limit, so use it to explain the reported value, not to claim validity
below 0.30:

| Quantity | Initial | At 64 s |
|---|---:|---:|
| Steam pressure | 6.89918 MPa | 7.49538 MPa |
| Turbine admission | 1.0 | 1.0 |
| Turbine steam flow | 1669.012 kg/s | 1813.243 kg/s |
| Saturated steam enthalpy `h_g` | 2.773872 MJ/kg | 2.765885 MJ/kg |
| Feedwater enthalpy `h_fw` | 0.976402 MJ/kg | 0.976547 MJ/kg |
| Proxy specific electric work `0.33(h_g−h_fw)` | 593.165 kJ/kg | 590.482 kJ/kg |
| Electrical proxy | 990.000 MW | 1070.687 MW |
| Fission power | 3000.000 MW | 2921.696 MW |

The actual code uses IF97 saturation properties and HEOS `(P,T)` feedwater
enthalpy. Matching those choices matters for precise replication.

The pressure-scaled valve gives a **1.086417 flow ratio**. The proxy specific
work ratio is **0.995476**; their product is **1.081502**, exactly the
electrical-output ratio. Therefore **increasing `h_g−h_fw` is not the cause**.
Fixed-area steam admission can pass more mass as upstream pressure rises;
the approximate choked-flow pressure dependence supports that direction
[R5], without validating the exact steam-valve law.

Removing relatively cold feedwater removes a thermal sink as well as a mass
source. In this saturated shell, pressure can rise while total stored energy
falls: total mass falls faster, and the remaining fluid's specific internal
energy increases. A new, still-in-domain run at **63 s** gave:

```text
level                              = 0.302076
electrical proxy                   = 1069.790 MW
fission power                      = 2922.715 MW
Q_sg                               = 2.885098 GW
m_out h_g − m_fw h_fw               = 5.010887 GW
dU_sec/dt                          = −2.125789 GW
U_sec(63) − U_sec(0)                = −94.2068 GJ
M_sec(63) − M_sec(0)                = −84.2307 t
change in U_sec/M_sec               = +110.867 kJ/kg
```

The first law closes: the shell is supplying a substantial part of the
outgoing enthalpy from stored energy. Neither steam flow nor electricity
must instantaneously track fission power during that depletion.

However, `eta=0.33` is an **effective cycle-efficiency factor**, not a turbine
isentropic efficiency. `h_fw` is not turbine exhaust enthalpy. At unequal
inlet/outlet flows, `m_steam(h_g−h_fw)` is not the actual shell net enthalpy
export either. In this no-dump case, the identity is

```text
m_steam(h_g−h_fw) = Q_sg − dU_sec/dt + h_fw dM_sec/dt
```

It would be wrong to replace the electrical proxy by `eta Q_sg`, cap it at
`eta P_fission`, or simply use `eta Q_steam_net` to “fix” the rise.

As a limited plausibility check, ideal isentropic expansion from the two
inlet states to an **illustrative, not modeled, 10 kPa** exhaust gives enthalpy
drops of about 932.2 and 937.8 kJ/kg [R1, R4]. There is no thermodynamic
requirement for turbine work per kilogram to collapse over this pressure
change. That calculation is not a proposed turbine calibration or proof of
1071 MW: real extractions, reheating, moisture, condenser conditions, generator
limits, governing, and protective trips are absent.

**Recommendation:** retain the existing L1 proxy, explain this M4 transient,
and reserve quantitative turbine claims for a model with explicit inlet/
exhaust states and cycle assumptions.

### 8. M4 energy and mass bookkeeping

**Correct within the stated shell closure; no missing M4 conservation term
was found.** The appropriate integrated checks [R1] are

```text
ΔM_sec = ∫(m_fw − m_steam − m_dump)dt
ΔU_sec = ∫[Q_sg + m_fw h_fw − (m_steam+m_dump)h_g]dt
```

The plant wires the same actual actuator flow into both balances, and the
validation helper obtains enthalpies from the run rather than constructing
an unrelated default shell. `Q_steam_net=m_out h_g−m_fw h_fw` is also correct
when feedwater and steam differ.

My new 600 s, 100→80% admission-ramp run reproduced:

```text
final ΔM_sec                 = −3149.599 kg
maximum |ΔM_sec|             = 3184.64 kg
final ΔU_sec                 = +5.76074 GJ
maximum |ΔU_sec|             ≈ 7.9149 GJ
```

Independent integration used direct CoolProp enthalpies, actual inlet/outlet
flows, and SG heat, not the production accumulation helper:

| Readout interval | Maximum mass-integral error | Error / initial mass | Error / max inventory change | Maximum energy-integral error | Error / max energy change |
|---|---:|---:|---:|---:|---:|
| 1 s | 0.97817 kg | `4.19387e-6` | `3.07154e-4` | 2.40433 MJ | `3.03791e-4` |
| 0.25 s | 0.05529 kg | `2.37054e-7` | `1.73616e-5` | 0.15662 MJ | `1.97880e-5` |

These are two quadratures of the same new dense solution. The approximately
second-order reduction with finer readout supports ordinary trapezoidal
sampling error, rather than a hidden energy or mass source. The 1 s values
also independently reproduce the validator's reported fractions.

The energy assertion is scaled to **energy change**, whereas the mass
assertion is scaled to **initial inventory**; they are not directly comparable
accuracy measures. Tightening the mass criterion would improve regression
sensitivity, but the measured result already passes a change-relative 0.1%
check.

This establishes shell boundary bookkeeping, not exact single-EOS
thermodynamic consistency or a whole turbine/condenser/feedwater-cycle energy
balance. The small IF97/HEOS closure discrepancy was already documented and
dispositioned in M3; M4 has not turned it into an unexplained boundary-energy
loss.

## References and verification notes

- **[R1]** Yan, *Introduction to Engineering Thermodynamics*,
  [§5.2.2, mass conservation; §5.2.3, energy conservation](https://pressbooks.bccampus.ca/thermo1/chapter/5-2-steady-flow-and-transient-flow/).
  These explicitly include transient accumulation and enthalpy transport.
  The public displayed equations are unnumbered; section locators are used
  rather than inventing equation numbers. The mixture and controller
  linearizations in this review are identified derivations from the stated
  relations, not claimed quotations.
- **[R2]** Åström and Murray, *Feedback Systems*, 2nd ed.,
  [Ch. 11, §11.4, “Integral Windup,” including “Manual Control and Tracking”](https://fbswiki.org/wiki/index.php/PID_Control).
  The public chapter contents were checked. The linked Caltech chapter PDF
  could not be independently retrieved because of a certificate-chain error;
  no unverified page/equation number is supplied. The code's normalization
  of back-calculation was checked algebraically and numerically.
- **[R3]** NRC, *Westinghouse Technology Systems Manual*,
  [§11.1, Steam Generator Water Level Control System, ML11223A293](https://www.nrc.gov/docs/ML1122/ML11223A293.pdf),
  printed pp. 11.1-2–3, PDF pp. 4–5, and Fig. 11.1-2, Rev. 0706.
  PDF text checked directly in memory. In particular, p. 11.1-3 describes
  lagging level so flow error initially dominates, the two-minute PI
  integral time, and shrink on decreasing load. This is a representative
  system, not a Model-F geometry or plant-specific tuning certificate.
- **[R4]** [CoolProp IF97 documentation](https://coolprop.org/fluid_properties/IF97.html)
  and [IAPWS IF97 release](https://iapws.org/documents/release/IF97-Rev).
  Numerical property checks used explicit `IF97::Water` saturation calls;
  exact reproduction of inlet enthalpy used `Water`/HEOS as in the existing
  wrapper. The inventory scale and temperature are model inputs, not
  inferred plant design data.
- **[R5]** NASA Glenn,
  [Mass Flow Rate Equations](https://www.grc.nasa.gov/www/k-12/airplane/mflchk.html),
  Eq. 10 and choking condition Eq. 19, checked directly. This supports
  approximate upstream-pressure/temperature scaling, not an exact
  saturated-steam turbine correlation.
- **[R6]** Todreas and Kazimi, *Nuclear Systems, Volume I: Thermal Hydraulic
  Fundamentals*, 2nd ed. Ch. 6 begins at p. 233, “Nonflow and Steady Flow:
  First and Second-Law Applications”; Ch. 7 begins at p. 319,
  “Nonsteady Flow First Law Analysis.” Titles/page starts checked in the
  [publisher-supplied Google Books contents](https://books.google.com/books/about/Nuclear_Systems_Volume_I.html?id=SAvMBQAAQBAJ).
  No feedwater-actuator or PI tuning equation is attributed to that chapter.

## Disposition

Triage by the orchestrator (2026-09-28). No high-severity findings, so M-gate 3 has no open high item.

| # | Severity | Disposition |
|---|---|---|
| 1 | medium | fix now (M4.7.1 telemetry + M4.7.3 console + M4.7.0 docs): keep `boil_off_time_s` but label it "total liquid ÷ present steam flow, not time to the model limit"; add a separately named `time_to_level_floor_s` (liquid above the 0.30 surrogate floor ÷ present net outflow; None when not draining). |
| 2 | medium | fix now (M4.7.1): rename the post-trip test to a bounded-level/one-way-feedwater-residual check (bounded level, negligible final feedwater, finite tracked integral); M4.7.0 documents the persistent offset. |
| 3 | medium | document (M4.7.0): loss-of-feedwater electrical rise is pressure-driven steam-flow growth at fixed admission while stored inventory/energy is consumed; P_electric is a fixed-efficiency proxy, not a transient turbine work balance. |
| 4 | medium | fix now (M4.7.0): drop the Todreas & Kazimi Ch. 7 attribution for the actuator lag and PI law; label the lag an L1 constitutive choice, PI/back-calculation → Åström & Murray §11.4, three-element signals → NRC WTSM §11.1. |
| 5 | low | fix now (M4.7.1), together with operator #2: in manual, the integral tracks the manual demand with the back-calculation tracking term (Åström & Murray §11.4 "Manual Control and Tracking") so manual→auto transfer is bumpless. |
| 6 | low | document (M4.7.0): define the state as the tracked PI integral state. |
| 7 | low | fix now (M4.7.1): scale the mass-accumulation residual to the accumulated inventory change (with an absolute floor) instead of 0.1 % of total mass. |
