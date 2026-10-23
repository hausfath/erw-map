# Flux reconciliation — analysis and implementation

**IMPLEMENTED 2026-08-03.** The ceiling described below now ships: see
`CHANGELOG.md` "Flux reconciliation, August 2026", `to_do.md` item 0 (closed) and
item R (cation retention, newly opened and blocked on data). Code:
`kinetics.alkalinity_ceiling_mol_l` / `flux_ceiling_t_ha_yr`, applied in
`build_v0.py` and in the shader, gated by build gate 12 and kinetics gates
13/13b/13c. Shipped effect: binds on 96.5% of cropland, median 0.792 -> 0.220
tCO2/ha/yr, warmest/coolest ratio 4.37x -> 0.91x.

**One consequence found at implementation time, recorded here because it is not in
the analysis below.** The capped global gross total is **0.354 GtCO2/yr** against a
pre-registered Tier 2 consistency band of 0.5-4.0. The band was NOT widened. It
descends from published estimates that also lack a transport bound, so falling below
it is the expected direction -- but it means the map no longer has an external
consistency check on its absolute level, and the field trials are now the only
anchor. Reported by build gate 2b and in `docs/VALIDATION.md` section 5.

---

## Original analysis (own work, pre-literature-integration)

All numbers computed in `ceiling.py`, `reconcile.py`, `mc_ceiling.py`, `regime.py`
against `data/processed/v0_layers.npz` (405,725 cropland cells, area-weighted).

## Validation of the carbonate chemistry first

Plummer & Busenberg (1982) constants, dilute solution, activity coefficients = 1:

| | computed at 25 °C | published |
|---|---|---|
| K_H | 0.03405 mol/kg/atm | 0.0344 |
| pK1 | 6.352 | 6.352 |
| pK2 | 10.329 | 10.329 |
| pK_calcite | 8.480 | 8.480 |

Benchmark, pure water + calcite open to 400 µatm: computed alkalinity 0.949 mmol/L,
Ca 0.475 mmol/L, pH 8.20 against the textbook ~1.0 mmol/L / pH ~8.3. The small
low bias comes from neglecting activity coefficients and the CaHCO₃⁺ ion pair, both
of which would *raise* the ceiling by ~10–20%, so every ceiling below is mildly
conservative toward the model being critiqued.

## Finding 1: the audit's ceiling is ~10× too strict, because it holds pH fixed

The audit computed `ceiling = q · [HCO₃⁻](pH_soil, pCO₂_soil)` with the cell's
**pre-treatment** pH. But pH is not exogenous. At fixed pCO₂ the carbonate system
ties [HCO₃⁻] and pH together in one equation, and adding base cations moves *both*:

| [HCO₃⁻] | pH required at 4,000 µatm | at 10,000 µatm |
|---|---|---|
| 0.5 mmol/L | 6.86 | 6.46 |
| 2.0 | 7.46 | 7.06 |
| 4.0 | 7.76 | 7.36 |
| 28.5 | 8.61 | 8.21 |

Reading it as "pH 6.77 permits only 0.41 mmol/L" is the same equation read
backwards. The whole point of a silicate amendment is to raise pH, and the liming
effect of basalt is well documented. So the audit's "the model uses low pH for fast
dissolution and requires high pH to carry the product out" is not the contradiction
it looks like — 28.5 mmol/L needs pH 8.6, which *is* implausible for cropland, but
2–7 mmol/L needs pH 7.5–8.0, which is not.

The real bound is where the rising pH runs into **carbonate saturation**. Solving
charge balance (2[Ca]+2[Mg] = [HCO₃⁻]) simultaneously with fixed pCO₂ and calcite
Ω, with Ca and Mg splitting the divalent charge equally as basalt gives:

| pCO₂ (µatm) | calcite Ω=1 | calcite Ω=10 |
|---|---|---|
| 1,000 | 1.91 | 4.11 |
| 4,000 | 3.03 | 6.52 |
| 10,000 | 4.11 | 8.85 |
| 20,000 | 5.17 | 11.15 |
| 100,000 | 8.85 | 19.06 |

The dependence is pCO₂^(1/3), so being wrong about soil pCO₂ by 5× moves the ceiling
only 1.7×. Temperature is weaker still: 3.56 / 3.03 / 2.58 mmol/L at 5 / 15 / 25 °C.

Ω=1 is the strict reading; Ω≈10 is defensible because carbonate precipitation is
kinetically inhibited by DOC and phosphate — Zhang et al. 2022 state precipitation
in river water "is generally observed to be negligible at Ω < 10" and run their own
model over Ω = 5–25. Soils have far more DOC than rivers.

## Finding 1b: the M&C ambiguities are RESOLVED from the primary source

Both holds in item 0 can be lifted. Sources obtained: M&C 2014 main text and full SI
(sseh.uchicago.edu/doc/Maher_and_Chamberlin_2014.pdf and `..._SI.pdf`), Maher 2010
(`.../Maher_2010.pdf`).

**τ is real, τ = e², and it is NOT already folded into Fig. 2's contours.** Eq. 3 as
printed is `C = C_eq·(τD_w/q)/(1 + τD_w/q)`, and Table S1 lists "τ — Scaling
parameter (eⁿ) — eⁿ, n = 2". SI p. 1: "The scaling factor, τ = e2, allows for the
concentration to reach 99.9% of ceq when the travel time equals the equilibrium
time." Verified three ways, the decisive one being that Fig. 2's contour *labels*
(0.003, 0.03, 0.3) are reproducible to 2 s.f. from the paper's own printed
parameters using bare `D_w = Lφ·R_n,max·f_w/C_eq` with **no τ**, while Fig. 2B's
plotted flux plateaus match `C_eq·τ·D_w` and are 0.8 of a decade off without τ.
**So applying τ on top of a Fig-2-derived D_w is correct and does not double-count.**

**ERW belongs at the HIGH D_w limb, ~0.3, not 0.03.** The published 0.003–0.3 range
is generated at fixed `Lφ = 0.1 m` by varying soil age `T_s` alone. `D_w = 0.03` is
the caption's "Lφ of 0.1 m and Ts of 100,000 years" (`f_w = 0.105`); `D_w = 0.3` is
`T_s < 1 kyr`, `f_w ≈ 1`. Annually reapplied crushed feedstock has `T_s` of order
1 year, and a tilled topsoil has `Lφ = 0.2 m × 0.45 ≈ 0.09 m`, matching the paper's
assumed 0.1 m. Both discriminating parameters put ERW at the `f_w → 1` end member,
which the paper labels "the global maximum Dw". **The repo's 0.03 default imports a
100,000-year soil age into a system whose reactive mineral is one year old**, and the
earlier 0.5 → 0.03 "correction" moved the wrong way. Caveat: 0.3 is not a physical
cap — it is the max *inferred for global rivers* at natural surface area — so this is
a directional conclusion, not a number.

**Consequence: τD_w ≈ e²×0.3 = 2.22 m/yr, so the crossover q = τD_w is 2,217 mm/yr
and 100.0% of cropland is on the water-limited limb.** Even at the repo's D_w = 0.03,
τ alone puts 89.3% there.

**Also confirmed: two hard bounds, not one.** SI p. 1: "The theoretical maximum
solute flux is achieved when the water spends sufficient time in the subsurface to
reach equilibrium among the primary and secondary minerals (Wmax = qceq)." So
`W ≤ C_eq·q` and `W ≤ C_eq·τ·D_w`, and Eq. 3 is the smooth blend. The
`cdr ≤ q·[HCO₃⁻]·44` fix item 0 proposes is exactly the `W_max = q·c_eq` limb and is
directly supported.

**And the grind corollary is confirmed with a mechanism.** In M&C, `k_eff` and `A`
enter the flux through exactly one channel (`R_n → T_eq → D_w`); there is no separate
kinetic multiplier. So a grind-dependent rate *and* a grind-dependent `D_w` applies
the same physical quantity twice. Quantified at q = 0.3 m/yr: a 10× rise in `D_w`
raises `C/C_eq` from 0.425 to 0.881 (+107%) if `D_w = 0.03`, but from 0.881 to 0.987
(+12%) if `D_w = 0.30`. High `D_w` and "grind is the dominant lever" are close to
mutually exclusive.

**One number to check in the pipeline:** M&C's `C_eq = 375` is **µmol/L**, but text
extraction of the print PDF renders µ as m ("375 mmol/liter"). Anything sourced from
a text-extracted copy needs checking for a 1000× error.

## Finding 2: FOUR independent routes agree on 3–6.5 mmol/L

| route | ceiling on drainage [HCO₃⁻] |
|---|---|
| carbonate equilibria, calcite Ω=1→10 at 4,000 µatm, Ca:Mg charge 1:1 | **3.03 – 6.52 mmol/L** |
| Zhang et al. 2022 riverine CTP back-converted (7.1–21.3 GtCO₂/yr ÷ 37,288 km³/yr) | **4.3 – 13.0 mmol/L** added |
| Meybeck pristine-river 99th percentile (363 mg/L HCO₃⁻) | **5.95 mmol/L** |
| Meybeck carbonate-rock streams, the natural high case (192 mg/L) | **3.15 mmol/L** |
| Zhang et al. Fig. 5 US catchment alkalinity flux at 200–400 mm runoff | ~2.5 – 10 mmol/L (weakest — per-catchment runoff unknown) |

And for context, the same Meybeck table (EOLSS, *Chemical Characteristics of Rivers*,
Table 1; my column alignment validated by a charge balance closing to 1.8%):

| | HCO₃⁻ mmol/L |
|---|---|
| pristine-river median | 1.26 |
| **streams draining volcanic rocks** | **0.42** |
| granite/gneiss streams | 0.13 |

Four independent routes landing in 3–6.5 mmol/L is a real cross-check, not shared
assumptions: a closed-form calcite bound, a full iterative model over 3,365 GLORICH
sites, and the observed 99th percentile of world pristine rivers.

**And the repo's 0.42 mmol/L is, to two significant figures, the observed mean
alkalinity of streams draining volcanic rock.** That is a well-chosen *baseline* for
unamended basalt terrain — and it is exactly the wrong thing to use as a *ceiling*,
because removing the mineral-supply limitation is what ERW is for.

**So: the audit's 0.42 mmol/L is ~8–15× too strict, and the model's 28.5 mmol/L is
~4–9× too high.** The problem is real and in the direction stated, but roughly
50–100× smaller than "563× exceedance" implies.

### The one place I disagree with the primary-source read

M&C's `C_eq` is a **silica** equilibrium (375 µmol/L SiO₂ granitic, ~560 basaltic),
set by metastable feldspar–clay equilibrium. It is tempting to convert it to an
alkalinity ceiling via rock stoichiometry — congruent basalt gives HCO₃⁻:Si = 1.28,
hence ~0.72 mmol/L, which would make the problem *worse* than the repo says. **That
conversion is refuted by observation.** Measured HCO₃⁻:SiO₂ is 2.1 in volcanic-rock
streams and 9.3 in the median pristine river, i.e. 2–9× the congruent ratio, because
incongruent weathering retains Si in secondary clay and exports the cations. Silica is
bounded by clay equilibrium; alkalinity is bounded by charge balance and carbonate
saturation. So the carbonate-system ceiling is the operative one for CDR accounting,
and the silica `C_eq` is not.

## Finding 3: re-run of the audit with the corrected ceiling

Reproduced the audit first: 98.5% of cropland exceeds the fixed-pH ceiling (audit
says 98.6%), area-weighted mean exceedance 470× (audit says 563×; residual is
probably masking). Then with the corrected ceiling:

| ceiling | ceiling tCO₂/ha/yr p10/p50/p90 | % area exceeded | % by >10× | median exceedance | area-wt mean |
|---|---|---|---|---|---|
| audit, fixed pH | 0.001 / 0.009 / 0.086 | 98.5 | 82.4 | 61× | 470× |
| calcite Ω=1 | 0.011 / **0.102** / 0.324 | 99.6 | 43.9 | **8.7×** | 13.4× |
| calcite Ω=10 | 0.023 / **0.219** / 0.698 | 97.2 | 17.4 | **4.0×** | 6.2× |

Model gross CDR is 0.161 / 0.794 / 3.175 tCO₂/ha/yr p10/p50/p90.

Capping at the ceiling: median CDR 0.794 → 0.102 (Ω=1) or 0.219 (Ω=10) tCO₂/ha/yr;
area-weighted mean 1.218 → 0.146 or 0.306.

**The capped values, 0.1–0.2 tCO₂/ha/yr at 20 t/ha, are close to what ERW field
trials report.** That is the single most useful result here and needs checking
against the field-trial extraction.

## Finding 4: the ceiling is nearly insensitive to the τ and D_w controversy

Item 0 treats "missing τ" and "wrong D_w limb" as an unresolved ±order-of-magnitude.
But in Maher & Chamberlain the flux has two limbs,

    F = C_eq · q · τD_w/(q + τD_w),   crossover at q = τD_w

  * q ≪ τD_w: F → C_eq·q. **Water/thermodynamically limited.** Kinetics, surface
    area and grind drop out entirely — this is Maher 2010's "conveys no information
    on the actual weathering kinetics or available surface area".
  * q ≫ τD_w: F → C_eq·τ·D_w. **Surface-area limited.** Flux ∝ D_w ∝ A.

Taking the ceiling as min of the two limbs at C_eq = 3.0 mmol/L:

| | median ceiling tCO₂/ha/yr | water limb binds on | model exceeds by |
|---|---|---|---|
| τ=1, D_w=0.03 | 0.040 | 25.7% of area | 25.6× |
| τ=1, D_w=0.30 | 0.099 | 94.9% | 9.4× |
| τ=e², D_w=0.03 | 0.099 | 89.3% | 9.8× |
| τ=e², D_w=0.30 | 0.099 | 100.0% | 9.2× |

Three of four corners give the *same* median ceiling, because the water limb binds.
Only the τ=1, D_w=0.03 corner is surface-area limited, and it gives a *lower*
ceiling. So **the τ/D_w question cannot rescue the level** — it moves the answer
between 9× and 26× too high. Acquiring the M&C SI is therefore much less urgent
than item 0 claims for the *level*; it stays important for the *regime*.

## Finding 5: the sharper version of item 0's "mutually exclusive claims"

Item 0 frames the corollary as the two halves of the model contradicting each other.
The precise statement is better: **the τ value decides which regime the entire map
is in**, and hence whether most of the model's machinery controls the answer at all.

Fraction of cropland area that is water-limited (q < τD_w), so that the flux is
C_eq·q and the rate law is inert:

| | D_w=0.001 | 0.01 | 0.03 | 0.1 | 0.3 |
|---|---|---|---|---|---|
| τ=1 | 1.6% | 11.6% | 25.7% | 60.1% | 94.9% |
| τ=e² | 9.4% | 49.6% | **89.3%** | 99.7% | 100.0% |

At the repo's own D_w=0.03, τ=e² puts 89% of cropland on the limb where the
Palandri–Kharaka rate law, the archetype mineralogy, the grind d50/width sliders
and soil temperature all drop out of the flux. τ=1 puts only 26% there.

Mitigating this: the map's CDR is *already* mostly q-driven, so the pattern damage
is less than the level damage. Area-weighted correlations on log₁₀ CDR: vs log q
+0.819, vs L1 (rate) +0.720, vs η_transport +0.795, vs soil pH −0.589. Spread:
log CDR 0.567 dex, log q 0.648, L1 0.448. Imposing the ceiling is therefore mostly
a **re-anchoring**, not a re-shaping — the model's q-dependence on the water limb
(η → q/D_w, so flux ∝ rate·q) already has the right shape in q; what is wrong is
that the prefactor is a kinetic rate rather than C_eq·D_w, and that `rate` should
not be in the expression at all on that limb.

## Finding 6 (THE IMPORTANT ONE): the ceiling is not a level error, it is a climate gradient error

The ceiling depends on q and, weakly, on temperature — and the temperature
dependence runs the *wrong way* for the map. C_eq falls with warming (3.56 / 3.03 /
2.58 mmol/L at 5 / 15 / 25 °C) because carbonate solubility and CO₂ solubility both
decline. The rate law meanwhile rises steeply with temperature. So on the
water-limited limb, warm climates are slightly *worse* per unit drainage, and better
only insofar as they are wetter.

Binned by mean air temperature, area-weighted medians, ceiling at calcite Ω=10 with
T-dependent constants:

| T bin (°C) | % cropland area | q p50 (mm/yr) | model CDR p50 | ceiling p50 | exceedance |
|---|---|---|---|---|---|
| 0–10 | 30.2% | 64 | 0.380 | 0.215 | 2.2× |
| 10–15 | 16.7% | 92 | 0.543 | 0.275 | 2.4× |
| 15–20 | 16.8% | 49 | 0.797 | 0.139 | 5.9× |
| 20–25 | 13.6% | 96 | 2.002 | 0.264 | 8.2× |
| 25–40 | 22.7% | 90 | 1.755 | 0.233 | 8.5× |

Warmest bin / coolest bin ratio of the median:

| | warm/cool |
|---|---|
| model CDR | **4.62×** |
| flux ceiling | **1.08×** |
| drainage q alone | 1.41× |

**The map reports a 4.6× warm-climate advantage; the flux ceiling supports 1.08×.**
The exceedance is monotonic in temperature, 2.2× → 8.5×. So imposing the ceiling
would not merely rescale the map — it would remove essentially the whole
warm-climate gradient, which is the map's most visually prominent feature and the
one most likely to be quoted.

By region (ceiling at Ω=10, fixed 15 °C, area-weighted medians):

| region | q p50 mm/yr | ceiling Ω=1 | ceiling Ω=10 | model | exceedance |
|---|---|---|---|---|---|
| NW Europe | 180 | 0.240 | 0.517 | 0.724 | **1.4×** |
| North China Plain | 160 | 0.218 | 0.470 | 0.668 | **1.4×** |
| US Corn Belt | 134 | 0.178 | 0.383 | 1.218 | 3.2× |
| Indo-Gangetic Plain | 81 | 0.121 | 0.261 | 1.189 | 5.0× |
| Brazil Cerrado | 221 | 0.295 | 0.635 | 3.378 | 5.3× |
| SE Australia | 11 | 0.015 | 0.031 | 0.303 | 7.9× |
| Sahel | 108 | 0.143 | 0.309 | 2.317 | 8.6× |
| global | 75 | 0.102 | 0.219 | 0.794 | 4.0× |

In the temperate humid croplands where every field trial actually sits, the model is
only 1.4–3.2× above the Ω=10 ceiling. The overshoot is concentrated in the tropics
and the arid zone, where there are no trials — i.e. exactly the covariate gap
already flagged as field-data ask #5. This is testable: matched-rate trials in the
tropics should *not* show 4–5× temperate CDR.

## Finding 7: q is NOT the larger error — I checked and this one is mostly defused

The model's q is WaterGAP2-2e **groundwater recharge** (`qr`), chosen deliberately
(`prep_layers.py:68`) to exclude overland flow "that never reacted with soil".
Cropland distribution: 8 / 75 / 229 mm/yr at p10/p50/p90.

Drainage required for the model's own CDR to be carryable: 120 / 582 / 2,234 mm/yr
at Ω=1, or 56 / 270 / 1,037 at Ω=10 — against 75 mm/yr at the median.

My initial worry was that groundwater recharge omits artificial subsurface (tile)
drainage and lateral interflow, which are the dominant solute-export pathways on
exactly the croplands ERW targets. **Checked against the raster and it mostly does
not hold.** WaterGAP recharge medians on cropland by region: US Corn Belt 134,
NW Europe 180, North China Plain 160, Brazil Cerrado 221 mm/yr. Corn Belt tile
drainage is reported in the 100–300 mm/yr range, so 134 mm/yr is the right order.
The global cropland median of 75 mm/yr is low because it is dragged down by arid
cropland (p10 = 8 mm/yr), not because the humid croplands are underestimated. And
`prep_layers.py` uses the `histsoc` scenario, which simulates irrigation return
flow, so the Indo-Gangetic case is at least partly covered.

Residual concern, now second-order: WaterGAP `qr` is groundwater recharge, so
seasonally perched tile flow over a slowly permeable subsoil may be routed to fast
surface runoff rather than recharge in the model's own scheme. Worth one check
against a measured tile-drainage dataset, but it is not the order-of-magnitude
correction I initially suspected, and it does not change Finding 6.

## Finding 8: two structurally different fixes converge — and a third would be wrong

`build_v0.py:373` has `X = (reactivity/ref) * eta_tr`, and `eta_tr` enters
**absolutely**, not relative to the reference cell's own η. So D_w is not a free
knob: changing it moves the level, and the level is already anchored elsewhere
(`k_diss = −ln(1 − DISSOLVED_FRAC_AT_REF)`, giving frac = 0.25 at X = 1).

Median cropland gross CDR under each option:

| | Ω=1 | Ω=10 |
|---|---|---|
| as shipped | 0.794 | 0.794 |
| **A.** keep the architecture, add `cdr ≤ C_eq·q·44` as a hard bound | **0.100** | **0.214** |
| **B.** replace it on the water limb with `cdr = C_eq·q·η_DIC`, no rate law | **0.096** | **0.207** |
| **C.** only swap D_w/τ inside `eta_transport` (τ=e², D_w=0.03 / 0.30) | 0.300 | 0.041 |

**A and B agree to 4%.** Two structurally different fixes — one bounding the existing
kinetic model, one discarding it — land on the same number. That is the strongest
evidence available that ~0.1–0.2 tCO₂/ha/yr at 20 t/ha is the right level.

**C is the trap that item 0's "do not fix any part of this piecemeal" was protecting
against, and now there is a precise reason.** Swapping in the resolved M&C parameters
(τ=e², D_w=0.3) drops the median to 0.041, undershooting the ceiling by 5×, because it
applies a transport penalty to a kinetic rate that was *already* anchored to field
data. In M&C the `q/(q+τD_w)` factor multiplies the kinetic-limit flux `τ·Lφ·R_n`,
which carries `C_eq` with it. The repo's η multiplies a dimensionless relative
reactivity, which does not. **So the τ and D_w resolutions must not be applied to
`eta_transport` in isolation.** Fix the ceiling (A), or restructure (B) — not C.

Recommendation: **A**, because it is hours of work, needs no new data, keeps the
existing validation harness, and B's conclusion (the rate law is inert on 100% of
cropland) is better *reported* than *baked in* while it rests on one paper's τ.

## Finding 9 (THE ANSWER TO THE ACTUAL QUESTION): the flux ceiling is a real bound, but it is NOT what is limiting

Verified against the primary text, not a search summary: **McBride, Skov, Wade et al.
(2025), "Quantifying potential carbon dioxide removal via enhanced weathering using
porewater from a field trial in Scotland", *Frontiers in Climate* 7:1606574,
doi:10.3389/fclim.2025.1606574.** Dumyat, near Stirling (56.15 °N, −3.89 °W), crushed
Hillend basalt at 0 / 23 / 78 / 126 t/ha, 576 days, porewater by rhizon at 5 and 10 cm,
bicarbonate by charge balance × accumulated P−ET (mean daily P−ET 2.8 mm, so 1,613 mm
over the trial).

Table 3, 5 cm depth, treatment minus control:

| rate t/ha | pCDR tCO₂/ha | per t rock | p | % of theoretical max reached |
|---|---|---|---|---|
| 23 | 0.11 ± 0.11 | 0.0047 | 0.355 (ns) | 1.70% |
| 78 | **0.33 ± 0.11** | 0.0042 | 0.0037 | 1.50% |
| 126 | **0.53 ± 0.13** | 0.0042 | 0.0001 | 1.54% |

Inverting their own method gives the **ERW-attributable porewater bicarbonate
increment: 0.47 mmol/L (78 t/ha) to 0.75 mmol/L (126 t/ha)**, and 0.16 at 23 t/ha.
Mass-normalised pCDR is near-constant across a 5.5× range of application rate
(0.0047 / 0.0042 / 0.0042), so scaling to the repo's 20 t/ha is defensible:
**≈0.053–0.060 tCO₂/ha/yr**.

Two decisive details:

1. **Achieved concentration is 0.47–0.75 mmol/L — 5–10× BELOW the 3–6.5 mmol/L
   thermodynamic ceiling.** The ceiling was nowhere near binding.
2. The paper confirms this independently: soil inorganic carbon stayed "below the
   detection limit (0.1 wt.% inorganic carbon)... indicating that under the conditions
   observed in this experiment, that direct pCDR occurred only through the generation
   of bicarbonate. This was expected, given the pH conditions were below pH 7." **No
   carbonate precipitated, i.e. calcite saturation was never reached.**

And they reached only **1.1–1.7% of theoretical maximum CDR** in 1.6 years. The
binding constraint at this site was dissolution and cation retention, not transport.

### Direct validation at this site's own grid cell

The build's cell for Dumyat: pH 5.67, T_air 8.6 °C, q = 331 mm/yr (WaterGAP recharge;
the site's own P−ET is 1,022 mm/yr, so q is if anything conservative here).

| | tCO₂/ha/yr at 20 t/ha |
|---|---|
| **measured, scaled to 20 t/ha** | **0.053 – 0.060** |
| model as shipped | **1.921** (≈33× measured) |
| model + ceiling, Ω=1 | 0.442 (≈8× measured) |
| model + ceiling, Ω=10 | 0.951 (≈17× measured) |

**So imposing the flux ceiling closes roughly half the discrepancy in log space and
leaves a factor of ~8–17.** The flux ceiling is a genuine bound the model violates,
and worth implementing as a rail — but it is not the explanation for the level, and
fixing it alone would leave the map still an order of magnitude high against the one
site where I can do a like-for-like comparison.

This matches the seed paper's own conclusion. Zhang et al. 2022 (L&O, doi:10.1002/
lno.12244) is explicit: "our results support the notion that the transport of dissolved
constituents in surface waters is unlikely to be a primary bottleneck limiting the CDR
potential of ERW", and they disclaim the rest: "our model does not consider other
bottlenecks in the CDR potential of ERW, such as limited dissolution of feedstock at
application sites."

**Bottom line for the to-do list: item 0 is correctly diagnosed as a defect but
wrongly sized and wrongly prioritised.** It is not existential for ERW — the
literature's consistent answer, at river scale (Zhang) and porewater scale (McBride),
is that transport is not the bottleneck. It is a ~4–9× overstatement in this map
specifically, cheap to fix, and it should be demoted from "existential, tabled" to
"implement the rail, then go after the anchor and the kinetics" — i.e. behind item 2.

## Finding 10: two more 2025 studies, and they settle it

**Hammes, Hartmann, Barth, Linke, Smet, Hagens, Pogge von Strandmann, Reershemius,
Casimiro, Vienne, Stoeckel, Steffens & Paessler (2025), "Soil processes govern
alkalinity and cation retention in enhanced weathering for carbon dioxide removal",
EGUsphere preprint egusphere-2025-5402, doi:10.5194/egusphere-2025-5402** (Carbon
Drawdown Initiative + Hamburg + Wageningen + Mainz + Newcastle). Greenhouse, 4 soil
types / 7 batches × 13 feedstocks, ryegrass, two years, **irrigation >2,000 mm/yr and
temperature >19 °C, deliberately chosen to accelerate weathering.** Verbatim:

> "The added alkalinity fluxes ranged from 400 mmeq m-2 to 1200 mmeq m-2 and reflected
> a CO2-sequestration rate of ~0.1 to 0.3 tons per ha per year." (at 40 t/ha)

> "Detailed analyses of cation pools (exchangeable, carbonates, oxides and clay)
> revealed large changes within the first year where **10-50 times more cations were
> retained than exported via leachate**, making the realised CDR potential as
> alkalinity relatively small compared to the CDR potential of cations retained."

> "Alkalinity production was highly variable among the treatments and **some even
> showed a loss of alkalinity compared to their controls**."

> "Matrix analyses of soil properties versus feedstock revealed that alkalinity
> production from acidic soils was highest. **At higher pH-levels (> 7 pH), carbonate
> mineral saturation likely constrains further dissolution, potentially favouring
> carbonate formation.**"

**This is the decisive test.** At 2,000 mm/yr the flux ceiling would permit 2.67
(Ω=1) to 5.74 (Ω=10) tCO₂/ha/yr. Observed was 0.1–0.3. **The transport bound was
9–57× away from binding, in an experiment engineered to make water non-limiting.**
Implied leachate alkalinity: 0.114–0.341 mmol/L, against a 3.0–6.5 mmol/L ceiling.
And the last quote is the literature independently locating my calcite ceiling — as a
constraint that bites *only above pH 7*, which is where 40% of the map's cropland sits.

**Vienne, Frings, Rijnders, Suhrhoff, Reershemius, Poetra, Hartmann, Niron, Portillo
Estrada, Steinwidder, Boito & Vicca (2025), "Weathering without inorganic CDR revealed
through cation tracing", EGUsphere preprint egusphere-2025-1667,
doi:10.5194/egusphere-2025-1667.** Mesocosms, corn, basalt at 0–200 t/ha, 101 days:

> "Surprisingly, we observed **no significant inorganic CDR**, as leaching of dissolved
> inorganic carbon did not increase, and soil carbonate content even declined over time."

> "This mass balance showed that **most base cation charges were retained as
> (hydr)oxides in the reducible pool of the top soil**, while increases in the
> exchangeable pool were about a factor 10 smaller."

> "...a maximum CO2 removal potential of the weathered base cations (i.e., CDR
> potential) of **18 kg CO₂ t⁻¹ basalt**." (= 6.2% of the repo's 0.289 tCO₂/t
> stoichiometric potential — so dissolution was not slow; realisation was nil)

### The convergence, all normalised to 20 t/ha

| | tCO₂/ha/yr |
|---|---|
| McBride 2025, Scotland field, pH<7, 1.6 yr, 5 cm porewater | **0.053** |
| Hammes 2025, greenhouse, 4 soils × 13 feedstocks, 2 yr, accelerated | **0.050 – 0.150** |
| Vienne 2025, mesocosm, 101 d | realised ≈ **0** (potential 0.36) |
| map + flux ceiling, global median (Ω=1 / Ω=10) | 0.100 / 0.214 |
| **map as shipped, global median** | **0.794** |

Three independent 2025 studies land at 0–0.15. The flux ceiling brings the map to
0.10–0.21, i.e. to the right order of magnitude and the top of the observed range.
The remaining factor of ~2–4 is cation retention, which the map does not represent at
all (METHODOLOGY §6 item 3 already flags secondary precipitation as absent).

## Answer to the question asked

**How has the ERW literature treated flux constraints?** As a bound worth checking and
then setting aside. Zhang et al. 2022 is the only paper to make it the central
question, and it answers in the negative at river scale. Nobody has found transport to
be the binding constraint in a real soil.

**Where is it a limiting factor?** Essentially nowhere that has been measured — the
observed shortfall from transport bounds is 9–57×. It becomes binding only in models
that, like this one, generate fluxes an order of magnitude above field observations.
The one place a *concentration* limit genuinely bites is above pH 7, where carbonate
saturation starts to convert dissolution into pedogenic carbonate rather than exported
bicarbonate (Hammes et al.) — and that is a 50%-efficiency penalty, not a wall, since
carbonate formed from silicate-derived Ca returns only one of two CO₂.

**So item 0 is real, mis-sized, and mis-prioritised.** It is a ~4–9× overstatement, not
563×; not existential for ERW; and cheap to fix. The genuinely existential number for
ERW in this literature is the 10–50× cation retention factor, which is a different
problem and is currently listed nowhere in the to-do.

## Still running (three literature agents)

- Field-trial drainage alkalinity/DIC: does anything measured approach 3–7 mmol/L,
  and do measured CDR fluxes cluster at 0.1–0.2 tCO₂/ha/yr?
- Actual cropland root-zone drainage including tile flow, to test Finding 6.
- Whether the ERW modelling literature imposes a concentration ceiling as standard.
- Whether the Ω>1 case is a hard wall or a 50%-efficiency penalty (pedogenic
  carbonate from silicate-derived Ca returns one of two CO₂, so it is still CDR at
  half efficiency; clay neoformation returns none). METHODOLOGY §6 item 3 already
  flags secondary precipitation as absent.

---

## Finding 11: chemostasis is direct empirical support for the water-limited limb

**Godsey, Kirchner & Clow (2009)**, *Hydrological Processes* 23(13):1844–1864,
doi:10.1002/hyp.7315, n = 59 USGS Hydrologic Benchmark Network catchments:

> "We show that these catchments exhibit nearly chemostatic behaviour; their stream
> concentrations of weathering products such as Ca, Mg, Na, and Si typically vary by
> factors of only 3 to 20 while discharge varies by several orders of magnitude."

> "The means of the best-fit log–log concentration–discharge slopes vary between
> approximately −0.05 and −0.15 (SE of the slope ~0.01–0.02) for each of the
> solutes... No slope is within two SEs of −1."

So `C ≈ a·Q^(−0.1)`, i.e. concentration is nearly invariant and **flux ≈ C·q scales
essentially linearly with q**. That is the water-limited limb, measured. Extended to
2,186 catchments by Godsey, Hartmann & Kirchner (*Hydrol. Process.* 33:3056–3069) as
"broadly consistent" — with the caveat that chemostasis constrains variability at a
site, not the level across sites (cross-site mean concentration correlates negatively
with long-term precipitation).

M&C 2014's own SI makes the connection explicitly: "If travel time is sufficient to
allow the fluid to reach equilibrium with the solids, the primary control on the
solute flux is discharge — such systems are one example of 'chemostatic' behavior."

**Correction to carry forward:** West, Galy & Bickle (2005) give **no fixed runoff or
erosion threshold** for the kinetic/supply crossover — their §4.3 is titled
"Variability of kinetic thresholds" and the crossover is climate-dependent. Their
fitted kinetic law has runoff exponent b = 0.80 ± 0.32 and Ea = 74 ± 29 kJ/mol.

## Finding 12: a fifth anchor, and this one is agricultural and verified

**Hamilton, Kurzman, Arango, Jin & Robertson (2007)**, "Evidence for carbon
sequestration by agricultural liming", *Global Biogeochem. Cycles* 21:GB2021,
doi:10.1029/2006GB002738, n = 34 sites in Iowa/Michigan/Illinois:

| setting | HCO₃⁻ / alkalinity |
|---|---|
| **Midwest agricultural tile drainage** | **~1–6 mmol/L, occasionally ~7** |
| **cropland soil porewater, limed row crop, 1 m lysimeters** | **up to 6–7 mmol/L** |
| non-agricultural background soil solution | < 2 mmol/L |

This is the closest available analogue to the quantity the map needs — actual
solute-carrying drainage under actual cropland — and it lands squarely on the
3.0–6.5 mmol/L calcite bound computed in Finding 1. Supporting, less firmly:
Larkin et al. 2022 ERW trial catchments in Sabah, 1.3–7.1 mmol/L (HCO₃⁻ >99% of
alkalinity); global freshwater aquifers median 4.5, P95 8.6 mmol/L (Wood et al. 2022).
Both second-hand, not read directly.

**28 mmol/L was not found in any verified non-evaporite, non-brine, non-soda-lake
setting.** Note also that the flagship Beerling et al. Corn Belt trial reports no
porewater alkalinity at all — it explicitly "avoids the need to trace and measure
soluble EW CDR reaction products (alkalinity, cations, and dissolved inorganic
carbon)" — so it does not constrain this question either way.

## Finding 13: the real explanation for the level, with citations

**White & Brantley (2003)**, *Chemical Geology* 202:479–506, p. 495: "Each mineral
exhibits about a six order of magnitude range from the fastest experimental rate to
the lowest field rate." Their Panola Granite case gives **~250×** for fresh-mineral
lab rates applied to a field profile.

**Brantley, S. L. (2025)**, "Understanding the Lab–Field Discrepancy in Mineral
Dissolution From Flasks to Enhanced Rock Weathering", *Reviews of Geophysics*
63(4):e2025RG000881, doi:10.1029/2025RG000881 (citation and abstract verified via
Crossref; **full text paywalled**, so the model-bounding recommendations are unread):

> "In general, field rates become increasingly slower than lab rates at larger spatial
> and temporal scales because of factors related to surface area, hydrology,
> heterogeneities, biota, and system–level effects. **This implies surface area is not
> always an appropriate scaling factor.**"

> "The measurements of enhanced rates of basalt weathering on croplands published so
> far are relatively consistent with previously published lab and field rates of basalt
> weathering **because the durations of weathering are small**. But the rates of CO₂
> consumption from the atmosphere are very slow, and will decrease with time,
> necessitating huge acreages of basalt spreading to reach gigatons of CO₂
> sequestration."

This is the authoritative statement that the map's level problem is a lab-to-field
rate problem, not a flux problem — and the surface-area warning is an independent
strike against the grind slider being the map's main lever. **Acquiring this full text
should displace the M&C SI at the top of the acquisitions list, since the M&C
questions are now closed.**

## Finding 14: the paddy pCO₂ default may be 4× too low

The build already interpolates pCO₂ from 4,000 (drained) to 50,000 µatm (saturated) by
`f_flood` (`build_v0.py:240–241`), correctly sourced to Isometric v1.2 §10.4.5.7. That
matches protocol requirement R-D338-0 verbatim: "projects operating in unsaturated
systems are required to select 4,000 ppm and in saturated systems 50,000 ppm, unless
direct measurements of soil gas flux are taken." Cropland pCO₂ in the build runs 4,000
to 47,701 µatm; cells with `f_flood > 0.3` (n = 1,809) sit at 18,510/21,888/30,900
p10/p50/p90. No defect.

But **Kirk, Manful, Rahman et al. (2019)**, *Plant Cell Environ.* 42(12):3197–3207,
doi:10.1111/pce.13638 (open access, read directly): "Large dissolved CO₂
concentrations develop in submerged rice soils (equivalent partial pressures 5–70
kPa)", with their own measured bulk soil value ≈ 20 kPa — i.e. **~200,000 µatm, four
times the protocol's saturated default.** Since the ceiling scales as pCO₂^(1/3), that
raises the paddy alkalinity ceiling by only ~1.6× (3.03 → 4.8 mmol/L at Ω=1), so it is
a second-order effect on the level. It is first-order for field-data ask #6, because it
means the measurable paddy drainage DIC signal is larger than the protocol default
predicts. Caveat: these are equivalent partial pressures back-calculated from dissolved
CO₂ via Henry's law, not gas-phase measurements.

## Consolidated: five independent anchors on the drainage alkalinity ceiling

| route | mmol/L |
|---|---|
| calcite saturation, Ω=1→10, 4,000 µatm, Ca:Mg charge 1:1 (own calc, validated) | 3.03 – 6.52 |
| Zhang et al. 2022 riverine CTP back-converted | 4.3 – 13.0 |
| **Hamilton et al. 2007 Midwest tile drainage and cropland porewater** | **1 – 7** |
| Meybeck pristine-river 99th percentile | 5.95 |
| Meybeck carbonate-terrain streams | 3.15 |

Against: repo audit ceiling 0.42 (≈8–15× too strict, and equal to the observed
*unamended* volcanic-catchment mean); model requirement 28.5 (≈4–9× too high);
observed achieved ERW increment in the field 0.11–0.75 (5–10× below the ceiling).

---

# REVISION after the field-trial extraction

Three corrections to the above, one of them important enough to reverse a conclusion.

## Revision 1: the 28 mmol/L is NOT specific to this map — Zeke's original call was right

I wrote above that item 0 "is not existential for ERW". **That was wrong, and the
original decision to table it as existential was better judgement than my correction.**

The flagship field trial has the same arithmetic property. **Beerling et al. 2024**,
*PNAS* 121:e2319436121, Illinois Energy Farm, metabasalt 50 t/ha/yr × 4 = 200 t/ha,
reports **CDR_pot 10.5 ± 3.8 tCO₂/ha cumulative over 4 years** by Ti immobile-element
mass balance — and reports **no drainage or porewater chemistry at all.** At Illinois
tile drainage of 200–400 mm/yr that requires:

| tile drainage | implied [HCO₃⁻] |
|---|---|
| 200 mm/yr | **29.8 mmol/L** |
| 300 mm/yr | 19.9 mmol/L |
| 400 mm/yr | 14.9 mmol/L |

**29.8 against this map's 28.5.** The map is not anomalous; it reproduces the implied
concentration of the field's most-cited result, because both convert a dissolution-side
potential into a carbon claim without checking carryability. Beerling's own wording
concedes the gap: the curve "represents the rates expected for weathered cations
**eventually** exported", and elsewhere "the transport flux of cations and DIC species
in drainage water can significantly lag the rate of EW".

The same check on **Kelland et al. 2020** (*GCB* 26:3658–3676) closes internally over
one experiment: measured cation release of 5,328 meq/m² over 120 days against measured
drainage of 252 mm requires **21.1 mmol/L**; measured leachate alkalinity was
**1.10 ± 0.147 mmol/L**, statistically indistinguishable from the 1.148 ± 0.245 control
(p > 0.05). A **19× shortfall**, measured on both sides in one system.

So the correct framing for the to-do is not "this map has a bug" but "**this map
inherits a defect that is general to solid-phase ERW accounting, and it is one of the
few places where the inconsistency can be made visible.**" That is a stronger reason to
implement the ceiling, not a weaker one — and it makes the ceiling a contribution rather
than a repair.

## Revision 2: "is transport limiting" resolves into two different questions

The literature says yes to one and no to the other, and conflating them is what made
item 0 hard to size.

**(a) Is a concentration CEILING being hit in the field? No.** Achieved ERW-attributable
concentrations are 0.076–0.75 mmol/L (Jones 2025 lysimeter to McBride 2025), against a
3–6.5 mmol/L bound. Hammes et al. ran >2,000 mm/yr specifically to remove water as a
constraint and still saw 10–50× more cations retained than exported. Zhang et al. 2022
reach the same verdict at river scale.

**(b) Is water flux a first-order control on REALISED export? Yes, emphatically** — and
this is the part I understated. The relevant peer-reviewed statement is
**Kanzaki et al. 2025**, *Environ. Res. Lett.* 20:074055, on CONUS croplands:

> "the condition that CDR_diss ≫ CDR_adv is ubiquitous spatially and persists for
> extended periods"

with flux-weighted lags to 25/50/75% of CDR capacity of **5, 8 and 22 years** (Midwest
/ Southeast / Pacific reaching 50% at 10 / 3 / 7 years), and "low CEC values, large
fluid infiltration rates… should all favour more rapid alkalinity export". They also
warn that solid-phase tracers give "a 'potential' CDR that may or may not be realized".
Supporting: **Amann et al. 2022** (*Front. Clim.* 4:929268) — "The hydrologic
conditions, which determine the residence times in the pore space… **can be more
important than small grain size**", with finer grains giving *lower* area-normalised
rates through reduced hydraulic conductivity; and **Knapp & Tipper 2022**
(*Front. Clim.* 4:928215) — efficacy "is a function of the capacity rivers have for
transporting the products… **rather than the dissolution capacity of soils**".

**This strengthens Findings 4, 5 and 11, not weakens them.** "CDR_diss ≫ CDR_adv
ubiquitously" is precisely the statement that cropland sits on the water-limited limb.
Amann's result that finer grinding *reduced* the rate is a direct empirical strike
against the grind slider being the map's principal lever, and it lands independently of
the Maher algebra and of Brantley's surface-area warning.

So: **q belongs at the centre of this model and the ceiling belongs on top of it. What
does not belong is a kinetic rate law carrying the spatial signal.**

## Revision 3: the best-matched validation point available

**Dupla, Bertagni & Grand (2025)**, *Environ. Sci. Technol.* 59:25751–25764. Three
Swiss vineyards, temperate Cambisols pH 6.4–7.5, basanite 80% <52 µm, **20 t/ha single
application** — the map's exact rate — 1,000 days, **DIC measured directly on a TOC-L
analyser** (one of only two ERW trials in the whole extraction that did so; most infer
HCO₃⁻ by charge balance):

| | tCO₂/ha/yr at 20 t/ha |
|---|---|
| **Dupla et al. 2025, measured** | **0.100 ± 0.030** |
| map + flux ceiling, calcite Ω=1 | **0.100** |
| map + flux ceiling, calcite Ω=10 | 0.214 |
| map as shipped | 0.794 |

No normalisation required. The Ω=1 ceiling reproduces the measured value exactly, which
is better agreement than the method deserves and should be read as order-of-magnitude
confirmation rather than precision. Their own framing: the result is "10 to 30 times
lower than the upper rates reported", and roughly half of modelled release was "lost to
sinks of base cations… as well as suboptimal conversion of alkalinity to DIC".

Every measured *aqueous export* value in the extraction is ≤0.4 tCO₂/ha/yr: 0 (Vienne
2026, to 200 t/ha), 0.018 (Vienne 2022), 0.023–0.049 (Amann 2020, at 220 t/ha), 0.100
(Dupla 2025), 0.1–0.3 (Hammes 2025), 0.22–0.35 (McBride 2025), 0.40 (Larkin 2022, one
plot of three). Every value above 1 tCO₂/ha/yr in the literature is solid-phase,
exchangeable-pool or soil-TIC based.

## Caveats on my own field anchors, now that I have the details

- **McBride 2025 control background flux is 0.438–0.656 tCO₂/ha, i.e. background ≈
  signal.** The 0.33–0.53 treatment values are differences of two similar numbers. And
  the feedstock D50 was **1,006 µm**, far coarser than the map's 67–600 µm observed
  span, so it is a conservative site for the map. Treat my 0.053 tCO₂/ha/yr scaling as
  soft.
- **Hammes 2025 and Jordan 2026 are preprints**, not peer reviewed. Hammes carries much
  of the retention argument.
- **Rice paddy aqueous carbon is essentially a void** in the reachable literature: no
  verified measured floodwater alkalinity or paddy lateral DIC export flux. Every
  ERW-in-paddy trial found only solid-phase carbon. This confirms field-data ask #6 as
  genuinely unmet, and Gong 2026 (*JEM* 405:129708) and Katoh et al. 2004
  (*SSPN* 50:721–729) are the acquisitions.

## Two directly usable parameterisations

- **Strong acid, item 3.** Dietzen & Rosing 2023's X* framework is quantitative and
  pH-keyed: **17% loss at pH 5.79; X* < 0.25 below pH 5.2; no correction needed above
  pH 6.29; halves again above pH 7.1** — so cation-based accounting is valid only in the
  band **pH 6.29–7.1**. Corroborated at Hubbard Brook (X* = 0.21 against a 20%
  bicarbonate-vs-Ca shortfall). Compare Fortner et al. 2012's **67% overestimate** in a
  tilled corn watershed, Knapp & Tipper's 5–25%, and Beerling 2024's own 5.2% from
  202 kg N/ha of UAN. The spread across those is itself the uncertainty.
- **Retention, the missing item.** te Pas 2025 partitions it: only **6.5–12.3%** of
  weathered cations were BaCl₂-exchangeable, ≤34% in carbonates, ≤32.5% adsorbed,
  **31.6–92.7% unidentified**; retarded fractions **98.3% Mg, 98.2% Ca, 92.7% Na**.
  Vienne 2026 finds the **reducible Fe/Mn-oxide pool dominant with the exchangeable pool
  ~10× smaller**. **So a CEC-based retention term would model the minority sink.** This
  matters if item 3's implementation reaches for CEC.

## Citation corrections to carry into the to-do

- **Amann et al. 2020** is an **Antwerp mesocosm**, not a German field trial, and there
  is **no Amann paper in IJGGC**. The "constraints" paper is *Front. Clim.* 4:929268 (2022).
- **Dietzen et al. 2018** is Dietzen, Harrison & Michelsen-Correa — **Rosing is not an
  author** — and is a **closed-jar incubation with zero drainage**, so it cannot speak
  to export at all. Its 12.5–16.6 tCO₂/ha/yr-equivalent headline is overstated ≥4× by
  Dietzen's own later X* framework. **Dietzen & Rosing 2023** (*IJGGC* 125:103872) is a
  Danish field trial with **Greenlandic glacial rock flour**, not olivine.
- **te Pas** has two papers: 2023 (*Front. Clim.* 4:954064) and **2025 (6:1524998)**,
  the latter holding the retention partitioning and not previously on the list.
- **Larkin et al. 2022** is Sabah oil palm (*Front. Clim.* 4:959229), not temperate.
- **Clarkson et al. 2024** is *Front. Clim.* 6:1345224, not PNAS.

## Revised recommendation

1. **Implement the ceiling as `min(kinetic flux, C_cap(pH, pCO₂)·q)`** with C_cap from
   carbonate equilibrium hard-capped at calcite saturation. Hours of work, no new data,
   and given Revision 1 it is a publishable check rather than a bug fix. Run Ω=1 and
   Ω=10 as the sensitivity pair; that spans 0.100–0.214 at the median and brackets
   Dupla's measured 0.100.
2. **Do not touch `eta_transport`'s D_w/τ in isolation** (option C, Finding 8).
3. **Add cation retention as a new item, above the current item 3.** It is a 10–50×
   effect against strong acid's 1.05–3×, and it is the single largest missing term.
   Do not implement it on CEC.
4. **Report the exceedance as a climate gradient** (Finding 6), because 4.6× → 1.08×
   on the warm/cool ratio is the map's most consequential claim.
5. **Acquisitions, reordered:** Brantley 2025 *Rev. Geophys.* full text first (the M&C
   SI questions are now closed); then te Pas 2025 and Dupla 2025 SI; then Gong 2026 and
   Katoh 2004 for the paddy void.

---

# ADDENDUM: how the ERW modelling literature handles the aqueous side

Delegated reading, publisher versions; flagged as second-hand where noted.

## Omitting a saturation constraint is NON-standard. This map is the outlier.

| imposes a saturation / affinity / charge-balance constraint | does not |
|---|---|
| Beerling et al. 2020 (*Nature* 583:242) | Bertagni & Porporato 2022 (an efficiency, by design) |
| SCEPTER, all versions incl. Baek 2023 | Calabrese et al. 2022 (a **Perspective**, no model of its own) |
| Cipolla et al. 2021a/b, 2022 | Cascade WPE (unverified; declines to report tonnes) |
| **Bertagni et al. 2025 (SMEW)** | Isometric v1.2 (unverified) |
| Zhang et al. 2022 (river scale) | |

That settles the question the to-do could not: a concentration or affinity bound is
standard practice, and its absence here is a genuine outlier rather than a defensible
simplification. It also means **nobody has published the specific `q/(q+D_w)`
structural critique**, so Finding 1b and Finding 8 are novel.

## The real explanation for the level, and it is item 2 not item 0

**Bertagni, Calabrese, Cipolla, Noto & Porporato (2025)**, *JAMES*,
doi:10.1029/2024MS004224 — the SMEW model. Its rate law carries a saturation index Ω
explicitly, and its headline empirical result is the one this map most needs to hear:

> "weathering rates are consistently lower than traditionally assumed **by up to two
> orders of magnitude**"

with an empirical dissolution factor F_D "consistently below one for most experimental
setups and rock types", because Palandri's parameters come from "dissolution experiments
in stirred reactors without diffusive limitations and under conditions **far from
equilibrium**."

**This map uses Palandri & Kharaka.** Combined with White & Brantley's six-orders-of-
magnitude lab-to-field range and Brantley 2025's surface-area warning, the level problem
is a lab-rate problem, and it belongs to item 2. The flux ceiling caps the symptom.

SMEW also quantifies secondary carbonate as "a **50% reduction in CO₂ removal
efficiency**", consistent with the half-efficiency reasoning above.

**A disagreement worth preserving rather than resolving.** SMEW attributes the
potential-versus-effective gap "primarily due to **CEC adsorption**". te Pas 2025 and
Vienne 2026 measured the opposite — only 6.5–12.3% BaCl₂-exchangeable, with the
reducible Fe/Mn-oxide pool dominant. Modelling and measurement disagree on the dominant
retention sink. Do not pick one silently.

## External motivation for item 1 that the to-do does not have

**Calabrese, Wild, Bertagni, Bourg, White, Aburto, Cipolla, Noto & Porporato (2022)**,
*ES&T* 56:15261–15272 (a Perspective; confirm the author list against the DOI, since
Bertagni & Porporato 2022's reference list omits Aburto from an "Under Review"
version). Its central argument is **"The Aridity Bottleneck"**: a Budyko dryness index
`D_I = PET/P` with an empirical chemical depletion fraction that "abruptly declines" for
D_I > 1.

So the group most focused on ERW hydrology argues aridity is *the* bottleneck — while
this map's moisture term divides out absolute wetness by per-cell max normalisation
(item 1), turning a 272× range in real water into 0.95×. **Item 1 is not a units nicety;
it deletes the variable the hydrology literature considers primary.** That is a stronger
case for item 1 than the to-do currently makes, and it is now independent of item 0.

The same paper is a usefully citable acknowledgement that the saturation question is
open rather than overlooked: "the quantitative effect of other parameters such as fluid
saturation is debated… [experiments point] toward a possible abrupt transition in the
weathering kinetics triggered by fluid saturation."

Its one field number, second-hand: Hubbard Brook wollastonite, ~0.025–0.12 tCO₂/ha over
**15 years** for a 3.44 t/ha application.

## A convention trap in η_DIC worth one check

Three denominators are in circulation and they are easy to conflate:

- **Beerling et al. 2020 SI:** η = 0.86 gives "**1.72 mol of CO₂ removed per mol of
  divalent cation** added to the oceans", falling to 1.0 if the carbon instead
  precipitates as pedogenic carbonate.
- **Bertagni & Porporato 2022:** "In seawater, the average alkalinization efficiency is
  around 80%: namely, for every 1 mol of alkaline cation added, the ocean water… [takes]
  up **0.8 mol of CO₂**… In freshwaters, the efficiency can vary from 0 to 100%. It is
  maximized at pH in the range of 6−8… and minimized in acidic waters with a pH below 5."
- **This map:** `ceil_t` uses `× 2.0`, i.e. **1 CO₂ per charge equivalent = 2 CO₂ per
  divalent cation** — the gross silicate-weathering stoichiometry before any ocean
  carbonate return.

The map's 2.0 is internally consistent with reporting gross alkalinity generation
(METHODOLOGY §6 item 10), and the 2.0 → 1.72 step is exactly the gross-to-net gap that
item 8 flags as needing a timescale. But cation *charge* versus cation *mole*
denominators differ by 2×, so anyone importing 0.8 or 1.72 into this pipeline without
converting will halve twice or double-count. **Worth pinning the convention explicitly
where η_DIC is applied.** Also: cite Bertagni & Porporato's acidity index as "**ACE**"
(published STOTEN), not "ACCE" (the ESSOAr preprint).

## One caveat on my own Zhang back-conversion anchor

**Bertagni, Regnier, Yan & Porporato (2024)**, *GRL* 51:e2024GL111310, builds a
Damköhler analogue on CO₂ *degassing* rather than dissolution, and states: "we neglect
carbonate mineral precipitation due to the limited observational evidence of carbonate
precipitation in rivers." Zhang et al. 2022's entire ceiling *is* river carbonate
precipitation, so the two river-side constraints differ in mechanism.

They are less contradictory than they look — Zhang explore Ω = 5–25 precisely *because*
precipitation is inhibited, citing that it is "generally observed to be negligible at
Ω < 10". Both agree river carbonate precipitation is weak. But it does mean the calcite
bound is thermodynamic and kinetically evadable, which is why the Ω=10 reading
(6.5 mmol/L) is the honest pragmatic ceiling rather than Ω=1. **The genuinely hard
backstop is soil pH:** carrying 28.5 mmol/L needs pH 8.61 at 4,000 µatm, and holding
even 10 mmol/L needs pH 8.16, above essentially all non-calcareous cropland. So the
absolute bound is ~10 mmol/L and the working bound is 3–6.5.
