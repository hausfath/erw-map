# ERW Atlas — global gridded enhanced rock weathering deployment map

## Context

We want a spatially gridded map of enhanced rock weathering (ERW) potential and
recommended deployment areas, playing the same role for ERW that the BiCRS Atlas
(`../BiCRS Map`) plays for biomass CDR — but on a raster grid rather than county
polygons, and global rather than national.

The starting point is Cascade Climate's [Weathering Potential
Explorer](https://cascadeclimate.org/blog/weathering-potential-explorer): a global
1 km Google Earth Engine app that computes a relative weathering-potential index
from soil pH, air temperature and soil moisture. It is the right foundation, and
Cascade is admirably explicit that it omits feedstock availability, economics,
hydrology and lifecycle emissions.

Three things motivate building our own rather than just using theirs:

1. **Feedstock is missing and it is decisive.** Cascade says so directly: the tool
   has "no information on rock type, mineral composition, or proximity to quarries
   or mines," and that "it is the economic and operational conditions, rather than
   weathering potential alone, that determine whether ERW is viable." A map without
   delivered feedstock cost cannot recommend deployment areas.

2. **The published formulation has two substantive problems** (found during
   research for this plan, both reviewed by a geochemistry expert agent and
   confirmed with primary sources — see "Scientific approach" below). Cascade's
   index is first-order in hydrogen-ion activity, which makes it a rescaled soil-pH
   map, and it omits the alkalinity-to-DIC conversion efficiency — the very quantity
   the paper they cite for their framework actually derives. Net effect: their map
   ranks strongly acidic tropical soils highest, when both the Isometric and
   Puro.earth protocols penalize exactly those soils.

3. **Protocol eligibility is mappable and absent.** The Isometric and Puro.earth
   ERW methodologies contain hard, gridded-data-shaped screens (soil organic carbon
   above 5 wt%, soil pH below 5.2, water-body proximity, post-2020 land conversion)
   that determine whether a site can be credited at all.

**Intended outcome:** a public, reproducible, static web map at
`github.com/hausfath/erw-map` that shows where ERW is physically effective, where
feedstock can actually be delivered, and where a project would be creditable — with
the weighting exposed to the user rather than hidden, and with the uncertainty and
effective resolution stated honestly rather than smoothed over.

### Decisions already taken

| Decision | Choice |
|---|---|
| Domain | Global, Cascade parity, 1 km grid spacing |
| Interactivity | Live client-side re-weighting in a WebGL fragment shader |
| Headline metric | Dimensionless index, plus a separately-flagged low-confidence CO₂ layer |
| Added factors | Feedstock supply and delivered cost; protocol eligibility gates |
| Not included | MRV cost surface, agronomic lime-displacement co-benefit, downstream river/ocean retention (deferred; see "Deferred") |

---

## Scientific approach

This is where most of the project's value sits, so it comes first. Every change
below was reviewed against primary sources; where the source could not be verified
that is stated explicitly.

### Baseline: reproduce Cascade exactly

Ship `r ∝ s · [H⁺] · exp(−Eₐ/RT)` with Eₐ = 68.8 kJ/mol as a comparison layer.
Non-negotiable — a critique of their formulation is not credible without a
like-for-like reproduction beside it.

### Change 1 — three-mechanism dissolution kinetics

Cascade's first-order proton dependence spans 10⁴ across cropland pH 4–8, while
their Arrhenius term spans only ~20× across 0–30 °C. The index is therefore ~500×
more sensitive to pH than to temperature (arithmetic verified). Replace with the
standard three-parallel-mechanism rate law from **Palandri & Kharaka 2004** (USGS
Open-File Report 2004-1068, eqn 7 p.5):

```
R = Σ_mechanisms  k_m^298 · exp[ −(Ea_m/R)(1/T − 1/298.15) ] · a_H+^n_m
```

Note the report's *printed* exponential form is dimensionally incoherent and
singular at 298.15 K; use the form above (which is what PHREEQC implements). The
base mechanism uses a negative exponent on `a_H+`, which the report states
explicitly is a data-reduction convenience.

Parameters are tabulated per mineral (Table 13 p.24 plagioclase, Table 23 p.35
orthosilicates, Table 26 p.37 pyroxenes). **All of these were independently
re-extracted from the primary PDF during planning and match exactly** — albite
−10.16/65.0/0.457, anorthite −3.50/16.6/1.411, labradorite −7.87/42.1/0.626,
bytownite −5.85/29.3/1.018, forsterite −6.85/67.2/0.470, augite −6.82/78.0/0.700,
diopside −6.36/96.1/0.710, enstatite −9.02/80.0/0.600, wollastonite −5.37/54.7/0.400.
Fabricated kinetic constants would be the worst error to carry into this build, so
re-run that extraction as a test rather than transcribing by hand.

Two corrections to my own initial assumptions, both material:

- **Proton orders are not uniformly 0.3–0.5.** Albite is 0.457 but anorthite is
  **1.411**. Rate does flatten above pH 5–6 for plagioclase but keeps falling for
  the mafic minerals (forsterite 43×, augite 166× across pH 4–8). Do not assert
  general flattening.
- **Basaltic glass is not in Palandri & Kharaka.** Verified independently: "glass" and
  "basalt" appear in that report *only in the reference list*, never in a parameter
  table. Use Gislason & Oelkers 2003 instead (Eₐ = 25.5 kJ/mol, apparent n_H ≈ 0.33;
  watch the pre-exponential's cm⁻² units — a 10⁴ trap, and one value that was quoted
  secondhand rather than read, so check it against the paper before hardcoding). Do
  not implement their Al-explicit form; we have no gridded Al³⁺ activity. Under
  gibbsite buffering the pH dependence of glass dissolution nearly cancels entirely,
  so run pH-invariant glass as the bounding sensitivity case.

Sum **charge-equivalent Ca + Mg release**, not Si release. Gudbrandsson et al. 2011
show Si, Ca, Mg and Fe have different pH dependences from the same basalt, so no
single whole-rock rate law can represent CDR.

Net effect: pH dynamic range drops from 10⁴ to ~37×, comparable to the temperature
range, so the index stops being a pH map. Regions that gain are near-neutral warm
wet croplands (Indo-Gangetic Plain, limed Cerrado, Nile Delta, Java, North China
Plain); strongly acidic humid-tropical Oxisols lose their top rank.

**Concede the fair point:** the effective Eₐ of a basalt mixture for Ca+Mg release
works out to 65.6–67.9 kJ/mol, so Cascade's 68.8 is a good number for whole-basalt
CDR, arrived at by an unsupported route. Say so — it is the fair-minded finding and it
buys credibility for the rest.

On provenance, be careful and non-accusatory. Cascade attributes 68.8 kJ/mol to White &
Blum 1995 as "representative of basaltic glass," but that paper reports apparent
activation energies of 59.4 (SiO₂) and 62.5 (Na) kJ/mol from 68 *granitoid* catchments —
catchment-scale apparent values for granitoid, not laboratory basaltic glass — and the
68.8 figure was not located in it. State that the provenance is unclear and that the
primary laboratory value for basaltic glass is 25.5 kJ/mol. Do not assert fabrication.

### Change 2 — alkalinity-to-DIC conversion efficiency (the biggest change)

Fast dissolution at low pH does not produce CDR, because DIC speciation shifts
toward aqueous CO₂ rather than bicarbonate. Cascade cites Bertagni & Porporato 2022
as their "normalized weathering flux potential framework," but that paper is titled
*The Carbon-Capture Efficiency of Natural Water Alkalinization* and defines the
Alkalinization Carbon-capture Efficiency, ACE ≡ d[DIC]/d[Alk] — **it is the
efficiency term Cascade omitted, and contains no kinetic index.** The citation is
inverted.

Add η_DIC as a multiplicative factor. For an open system at fixed soil pCO₂ (the
correct idealization for soil, where pCO₂ is buffered by respiration), with
h = a_H+ and C = K_H·pCO₂:

```
η_DIC = C(K1 + 2·K1·K2/h) / [ C(K1 + 4·K1·K2/h) + Kw + h² ]
```

Half-efficiency point: `pH_half = −log₁₀ √(K_H · pCO₂ · K1)`. Temperature-dependent
K1, K2, K_H, Kw from **Plummer & Busenberg 1982** (the PHREEQC expressions; verified
to reproduce the standard 25 °C values). Skip ionic-strength corrections and document
that choice — soil-solution ionic strength is 0.001–0.05 M and the activity
correction is small relative to everything else here.

This has zero free parameters and **derives the protocols' own screening thresholds.**
Verified numerically during planning (independent reimplementation, not transcription):

| Check | Result |
|---|---|
| Plummer–Busenberg at 25 °C vs literature `log K1 −6.352, K2 −10.329, K_H −1.468, Kw −14.000` | reproduced to **≤0.0005 log units** |
| pH_half at Isometric's mandated 4,000 µatm (unsaturated) | **5.08** vs their 5.2 screening threshold |
| pH_half at Isometric's mandated 50,000 µatm (saturated/paddy) | **4.53** — why paddies tolerate more acidity |
| pH_half at atmospheric 400 µatm | 5.58 |
| η_DIC at pH 5.2, 4,000 µatm, 15 °C | 0.636 (half-efficiency crossed just below the threshold) |

Kinetics × η_DIC puts the optimum at **pH 5.35 upland (4,000 µatm) and 4.80 in
paddies (50,000 µatm)** — computed with the implemented code, not estimated — against
Puro.earth's stated preferred range of 5.2–7.2, whose lower bound the upland optimum
essentially reproduces.

The ranking flip is also confirmed against the implementation, on four illustrative
sites normalized to each method's own maximum:

| Site | Cascade | rank | Ours | rank |
|---|---|---|---|---|
| Acid tropical Oxisol, upland | 1.0000 | 1 | 0.2559 | **2** |
| Java rice paddy | 0.0697 | 2 | 1.0000 | **1** |
| Illinois maize (Beerling trial) | 0.0055 | 3 | 0.1240 | 4 |
| Indo-Gangetic, irrigated, pH 8 | 0.0003 | 4 | 0.1330 | **3** |

Dynamic range across these four collapses from **2,955× to 8×**. That collapse, more
than any single rank change, is the substantive difference: Cascade's index is close to
binary (acid tropics bright, everything else numerically negligible), while the revised
one is a usable gradient in which alkaline irrigated cropland goes from hopeless to
comparable with the US Corn Belt. η_DIC also turns over slightly
above pH 8 (0.993) as the carbonate ion term grows, which is physically right and
which a monotonic penalty function would have missed.

**Caveat on provenance:** Bertagni & Porporato 2022 is paywalled and was not read in
full during planning. The ACE definition, the "sharp transition in a narrow pH
interval" finding, and the paper's actual subject are verified from the abstract; the
closed form above is **our derivation following their definition**, not a
transcription of their equation. Check it against their published equation before
release, and cite it as derived.

The most striking consequence: **rice paddies move from mid-pack to top-ranked**,
because high soil pCO₂ buys near-perfect η_DIC at moderate pH. Cascade cannot see
this at all because pCO₂ is absent from their formulation. Flag the known one-sided
bias that reducing conditions mobilize Fe²⁺/Mn²⁺ whose later oxidation reconsumes
alkalinity.

Use **observed** (baseline) soil pH, not feedstock-perturbed pH. It is what Isometric
actually screens on, the CEC-to-buffer-capacity mapping needed for perturbed pH is
not gridded, and observed pH is conservative in the direction the protocols care
about. Defuse the circularity objection empirically with a uniform ΔpH = +0.3/+0.6
sensitivity test rather than rhetorically.

**pH convention is a first-order bookkeeping issue, not a footnote.** SoilGrids
reports pH in H₂O; pH(H₂O) runs 0.5–0.6 units above pH(CaCl₂/KCl), which is
comparable to the entire width of the ACE transition. Pick one convention, state it,
apply an explicit offset, sensitivity-test it. Also: use the 0–5 and 5–15 cm layers,
**not** Cascade's 0–200 cm — a whole-profile average feeding a surface reaction.

### Change 3 — soil temperature, monthly

Rank this third; it is real but smaller than the first two.

- Use **soil** temperature (Isometric's near-field zone is the deeper of 20 cm or
  tillage depth + 5–10 cm), from Lembrechts et al. 2022 *Global maps of soil
  temperature* (1 km, monthly, Zenodo + GEE, calibrated against the SoilTemp
  in-situ database). ERA5-Land `stl2` (7–28 cm) as the depth sensitivity test — note
  `stl2`, not `stl1`, brackets the 20 cm near-field zone.
- **Compute the rate monthly and sum; never average the drivers.** Two reasons.
  First, Jensen's inequality: at Eₐ = 68.8 with a ±12 °C seasonal cycle about 10 °C,
  the monthly-integrated rate is **1.38×** the rate at the annual mean, rising to
  1.67× in continental croplands and ~1.02× in the humid tropics. The bias is
  latitude-dependent, so it does not cancel — it systematically tilts the map toward
  the tropics, which is the direction that flatters Cascade's headline. Second and
  more important, annual means destroy the **temperature × moisture covariance**,
  which biases high in Mediterranean climates (the annual means look ideal but warm
  and wet never coincide) and low in monsoon climates.
- Also evaluate the rate law at **250 m and then average up to 1 km** for the soil
  terms. Because the rate is convex in T and in [H⁺], rate-of-the-mean underestimates
  mean-of-the-rate, and the bias grows with within-cell variance. Aggregating
  SoilGrids 250 m to 1 km while keeping both mean and variance is cheap and hands us
  the second-order correction term for the climate layers directly.

### Change 4 — moisture

Be honest: there is no well-constrained moisture function for mineral dissolution in
unsaturated soil. What we can defensibly do:

- **Normalize by porosity** (S = θ/φ, φ from SoilGrids bulk density). Unambiguous
  improvement — Cascade's raw volumetric θ means different things in sand and clay,
  aliasing onto the soil-texture layer they already carry. High confidence.
- Default linear in S, purely to keep the comparison with Cascade interpretable.
- Report an **envelope** across S^0.5, Millington–Quirk relative diffusivity
  (θ^(7/3)/φ²), and a field-capacity plateau form. The spread is the honest
  uncertainty on this term.
- Note that GSSM1km is 0–5 cm while the reaction zone is 0–20 cm, so it will
  understate reactive moisture. Document.

### Change 5 — transport limitation (sensitivity, promote if bounded)

Cascade assumes far-from-equilibrium dissolution everywhere, which is the most
optimistic possible assumption and fails exactly where their map is brightest and
driest. Add, following Maher & Chamberlain 2014:

```
η_transport = q / (q + D_w)
```

with q = drainage/recharge (m/yr, from a global runoff product; must include
irrigation return flow on irrigated cells). Form is solid; **D_w is not constrained**
— treat as a sensitivity parameter over a literature range and attempt to bound it
from the field trials. Promote to default only if that succeeds.

### Explicitly not attempted

| Item | Why |
|---|---|
| Al-explicit basaltic-glass rate law | Needs gridded Al³⁺ activity, which does not exist |
| Spatially resolved secondary clay precipitation | Controlled by micro-environment Al/Si activity; no gridded constraint. Global haircut with a stated range instead |
| A single whole-rock basalt rate law | Different elements have different pH dependences from the same rock |
| Grain-size normalization from p80 alone | Rosin–Rammler width changes surface area by up to 33× at fixed p80. Need full particle-size distributions or exclude the trial |
| Fertilizer strong-acid competition folded into the score | Magnitude is first-order (at Indo-Gangetic N rates with ammonium sulfate the competing acid load can exceed the entire alkalinity supply) but the leaching fraction is unconstrained. Ship as a **separate diagnostic layer** at leaching fractions 0.2 and 0.8 |
| Site-level recommendations | 1 km cannot support sub-100 ha decisions. Repeat Cascade's caveat |

---

## Output layers

Three layers with deliberately different epistemic status.

### L1 — relative weathering reactivity (physical, dimensionless)

Kinetics × η_DIC × moisture, monthly-integrated. **Do not publish on a 0–1 scale** —
that invites reading 0.5 as "half as reactive." Publish as log₁₀ ratio to a stated
reference condition on a diverging scale centred at zero, labelled in ×-reference
units:

```
R_ref     = R(pH 6.5, T_soil 15 °C, S 0.6)     ← published, absolute
L1        = log10( R / R_ref )
L1_shader = clamp( 0.5 + L1 / (2·log10 A), 0, 1 )   ← A published, e.g. 30
```

Absolute breakpoints, so the value of a cell does not change if we later restrict
the domain. Keep the 0–1 form as a shader input only.

### L2 — deployment suitability (normative screening construct, 0–100)

**Normalization: absolute piecewise-linear value functions with published
breakpoints. Not min-max, not percentile.** This is the single most important
statistical decision in the project, for three reasons:

- Min-max is fatal given L1's 3–4 order-of-magnitude range: nearly every cell lands
  below 0.02 and the map becomes a binary mask of the humid acidic tropics with all
  temperate cropland in a uniform dark field.
- Percentile is worse because it is less obviously wrong. Most cropland sits in a
  narrow band of the reactivity distribution; a rank transform stretches that band
  across the colour scale, so the visible gradient across the US Midwest reflects
  **rank density, not physical difference**, and a reader will read it as signal.
- Distribution-derived normalization is **incompatible with the slider UI.** If
  inputs are rank-transformed, the composite's distribution changes shape as weights
  move, so a fixed colour scale means different things at different settings and
  users would read part of the recolouring as a change in suitability. Absolute value
  functions keep the scale stable under weight changes, which is a requirement for
  the interaction to be interpretable at all.

**Aggregation: weighted power mean, default p → 0 (weighted geometric mean), with
published per-criterion floors.**

```
L2 = 100 · ( Σ_i w_i · v_i^p )^(1/p) ,  Σ w_i = 1 ,  v_i ∈ [ε_i, 1]
```

Three reasons this family is right, and the third decides it:

1. It contains every candidate as a special case: p=1 arithmetic, p→0 geometric,
   p=−1 harmonic, and **p→−∞ = min, which is exactly the limiting-factor mode.** The
   limiting-factor display is not a separate computation, it is the extreme member of
   the same family — one code path in the shader.
2. It turns a hidden structural assumption into an exposed, testable parameter.
3. Under p→0, `log L2 = Σ wᵢ log vᵢ` is **linear in the weights**, so each weight is
   an elasticity (a 1% change in criterion i changes L2 by wᵢ percent — explicable to
   a user), the score is invariant to the arbitrary slope of each value function, and
   the full first-order Sobol decomposition is available in closed form with zero
   interaction terms.

Handle "too harsh a zero" with explicit published floors per criterion (reactivity
ε=0, truly annihilating; feedstock cost ε≈0.05, expensive is bad not impossible),
**not** with an ad-hoc hybrid where some factors multiply and others average. The
harshness judgment becomes a visible number rather than a consequence of which mean
we picked.

**Cropland fraction is removed from the composite.** It is an extensive quantity, not
a suitability criterion. A cell at 5% cropland in an otherwise ideal location is an
excellent place for ERW — on the cropland present. Keeping it in the score also
double-counts, because it would influence the score *and* any area aggregate of that
score. Cropland fraction becomes display alpha plus the area weight for every
aggregate and for L3.

**Weights: equal by default, labelled "Neutral (equal weights) — not a
recommendation."** Justify as declining to assert a preference ordering, not as "the
factors are equally important" (which is false). Reject AHP: eigenvector weights are
unstable to small perturbations, the 1–9 scale is arbitrary, and with no panel it is
one person's judgment laundered through linear algebra. Reject fitting weights to
observed deployments: n is a few dozen, siting is endogenous to existing
partnerships, and it silently converts L2 from normative (where deployment *should*
occur) to predictive (where companies *do* deploy) — a different quantity, badly
estimated.

### L3 — gross alkalinity generation potential, as CO₂-equivalent

**Rename away from "CDR."** Readers will see "CDR" and not "gross," and the gap
between gross weathering and net CDR (in-soil carbonate precipitation, riverine
re-release, strong-acid competition) is plausibly 20–80% and spatially variable —
the difference between 1.5 and 0.4 GtCO₂/yr. Units labelled **tCO₂ gross/ha/yr**
everywhere including the colourbar and download filenames.

Chain: Palandri–Kharaka rate → effective specific surface area → application rate ×
mineral fractions → Ca+Mg charge stoichiometry → η_DIC → η_transport → 0.044
tCO₂/kmol charge → seconds/yr → downstream haircut.

**Surface area is the dominant uncertainty and it is worse than I assumed.**
Geometric SSA at 267 µm is 0.0075 m²/g against BET values of 1–5 m²/g — a
**133–667×** discrepancy, and it grows with particle size, so at ERW-relevant coarse
grinds it is 2–2.7 orders of magnitude, not 1–2. Propagated to L3 at 20 t/ha this
spans 0.008 to 3.16 tCO₂/ha/yr. Critically, it is **one global multiplier**, so it
shifts the whole map together and cancels exactly in any relative comparison. That
asymmetry should drive the entire presentation strategy: it dominates L3's absolute
level and is irrelevant to L2's ranking.

Consequently: **render L3 in 3–4 log-spaced bins, not a continuous ramp** (a
continuous ramp on a quantity with 10× structural uncertainty is a lie told by
graphic design), put the structural range in the colourbar caption, do not make L3
the landing layer, and never let the UI emit a national L3 total without the
ensemble range beside it.

Include a **shrinking-particle** surface-area evolution term, `SSA(t) = SSA₀·(1−X)^(2/3)`,
so we do not predict linear-in-time CDR forever. Beerling's near-linear observed
cumulative rise over 4 years constrains the shape.

---

## Calibration and validation

### Two errors in my initial framing, both corrected

1. **Beerling et al. 2024 applied 200 t/ha, not 50.** Verbatim from the paper:
   "crushed basalt applied each fall over 4 y (50 t ha⁻¹ y⁻¹) gave a conservative
   time-integrated cumulative CDR potential of 10.5 ± 3.8 t CO₂ ha⁻¹." Four annual
   applications of 50 t/ha. Calibrating against a 4×-understated rate would have
   inflated the global map ~4×. The corrected implied dissolution is 10.5/47.6 = **22%
   over 4 years**, which is physically plausible; at 50 t/ha it would have been ~88%,
   i.e. pinned at the stoichiometric ceiling — which is how the error surfaced. Also
   note the paper's 116 t in 0–10 cm versus 84 t in 10–30 cm is **plough
   redistribution, not dissolution**.
2. **Beerling's CDRpot already assumes η_DIC = 1.** It is a cation-loss-derived upper
   bound. Calibrating the full product (kinetics × η_DIC × η_transport) against it
   would let the scaling constant silently absorb 1/(η_DIC·η_transport) at the
   Illinois site and over-predict everywhere else. **Fix: calibrate the kinetic-and-
   transport half against CDRpot with η_DIC held at 1, then apply η_DIC as a
   forward-only multiplier.** Equivalently, the calibration target is cation release,
   not CDR — which is what the trial actually measures.

### Superseded: we now have eight verified deliveries, not three trials

`tests/fixtures/deployments_2026.csv` replaces the three-field-trial design this
section was originally written around. Eight independently verified basalt
deliveries from the 2026 reporting round, across Indian acidic paddy soils, the US
Corn Belt and Brazilian Oxisols, under both Puro and Isometric. Findings, from
`scripts/analyse_deployments.py`:

1. **Validate against fraction weathered, not CDR/ha.** For rows without an
   independent CDR measurement,
   CDR/ha reproduces `rate × fw × 0.33` to within 1.4%, so it is algebra and
   carries no independent information. Using it as a target would be circular.
2. **Fraction weathered is not a site property.** It falls with application rate —
   perfectly monotonic across the four Indian deployments, `fw ~ rate^-0.58`
   across all eight. The map must never present it as a suitability metric.
3. **Delivered basalt is 0.289 tCO₂/t, not 0.33.** Mean over the rows carrying an
   independent CDR measurement. A measurement-anchored
   `delivered_basalt` archetype is now the default; fresh basalt is 14% optimistic.
4. **The paddy prediction is mildly challenged.** Rate-adjusted, the observed
   ordering is Brazil Oxisol > Corn Belt > India paddy — the reverse of the model.
   Total spread is only 3.35×, against a 7.5–33× unresolved grain-size confound,
   so the test has very little power. Recorded as a pre-registered concern.

Two structural limits mean first-year data cannot settle item 4 either way:
year-one fraction weathered is dominated by the fast, roughly site-independent
dissolution of the fine tail rather than the long-run steady rate the law
describes; and all eight sites are humid and acidic-to-near-neutral, so the
covariate envelope excludes precisely the arid, alkaline and cold cropland where
this model departs most from Cascade.

**Highest-value additional data, in order:** per-deployment particle-size
distributions (fit Rosin–Rammler and integrate surface area; exclude any
deployment lacking one rather than assuming a width); confirmation of whether one
programme's three bins are particle-size bins; measured soil pH with its convention; and whether each site
was actually flooded during the reporting period, since "paddy soil" in a soil
description is not the same thing. The cleanest single experiment for the
mechanism is a flooded-versus-drained pair at one site, same feedstock and rate.

### What we are entitled to claim

One-parameter calibration with two out-of-sample checks is **a plausibility
demonstration, not validation.** The test has almost no power: one global multiplier
exhausts the level information, leaving two ratios to test, and the structural
uncertainty already spans a factor of several in exactly those ratios. Every check is
confounded with grain size, which *is* the dominant uncertainty term. Measurement
methods (soil cation depletion, porewater flux, ion-exchange resin) disagree by
~2× and sometimes on sign, so observational uncertainty is comparable to model
uncertainty and a 2-point test is nearly guaranteed to pass regardless.

**Do not use the word "validated" anywhere, including tooltips.** The defensible
claim is: the rate expression with a single global constant fitted to trial A
reproduces the order of magnitude at trials B and C; this demonstrates the model is
not grossly inconsistent with field observations; it does not establish predictive
skill; and Z% of global cropland area lies outside the climate–soil envelope the
trials sample.

**Publish the covariate-hull figure.** Plot the trials in (soil pH, soil temperature,
moisture) space against global cropland *area* and report the fraction of cropland
area inside their convex hull. Expect well under 20%. This is the most honest
validation graphic available and it is nearly free.

### Pre-registered falsification criteria — commit before looking

| Test | Fails if |
|---|---|
| **Constancy** (highest value, nearly free) | Fit the scaling constant separately to each trial and publish all three. Spread of ~3× → say so. Spread of 10× → drop L3 to qualitative |
| Physical plausibility of λ | Fitted roughness multiplier on geometric SSA outside 1–100. λ<1 is unphysical; λ>100 means the kinetics are wrong, not the surface area |
| Out-of-sample residual | Scotland or Brazil missing by >3× while Illinois is exact → the single-constant assumption is refuted |
| Ordering | Model predicts trial B > C in areal rate and observations robustly reverse it |
| **Gudbrandsson test** (do this first) | Our mineral mixture must reproduce Gudbrandsson et al. 2011 measured Ca and Mg release vs pH at 5–25 °C to within ~0.5 log units **with no free parameters**. The only genuinely independent test of the kinetics, separate from the field trials |

Grain-size normalization must fit Rosin–Rammler to each trial's full particle-size
distribution and integrate SSA over it. **If a trial's distribution is unavailable,
exclude the trial** rather than assume a width — p80 alone is invalid.

### Release-gating sanity checks

Set all thresholds before running the pipeline; publish the pass/fail table
**including the fails**, following the `../BiCRS Map/PLAN.md` §10 convention.

**Tier 1, hard gates — these can genuinely falsify:**
- **Area closure:** Σ(cropland fraction × cell area) reproduces FAOSTAT global arable
  + permanent cropland (~1.55–1.6 Gha) within 10%, top-20 countries within 25%. Tests
  the area handling independently of any ERW science. A trial run on the GLAD 3 km
  cropland layer gives **17.8 M km² = 1.78 Gha** cos-latitude-weighted, so this gate is
  achievable — and the same run gives the naive equal-area answer as 22.1 M km²,
  i.e. **+24.3%**, which is the exact size of the bug this gate catches. The error is
  systematically worst in the high-latitude breadbaskets (Canadian prairies, northern
  Europe, Ukraine, Russia). Precompute a per-row spherical area vector
  `R²·Δλ·(sin φ_top − sin φ_bot)` once and reuse it everywhere; never let a bare
  `.sum()` of cells reach a headline number. Note that cropland *fraction* is an
  area ratio and so is latitude-safe; any *sum* of it is not.
- Scale note, corrected from an earlier estimate: cells carrying any cropland number
  **~47 M (>10% threshold) to ~65 M (>1%), best estimate ~55 M** — not the 10–16 M I
  first assumed. A 30 arcsec cell is 0.86 km² at the equator but ~0.61 km² at 45°N, and
  cropland cells are fractional with mean cover ~35–45%. Every memory and size estimate
  scales with this number.
- **Stoichiometric ceiling:** implied tCO₂ per tonne feedstock ≤ 0.33 for a Ca+Mg-rich
  basalt (computed from the actual assumed composition). Any cell above it is a bug.
- **Fraction dissolved:** ≤10–20%/yr, never >100% cumulative.
- **Monotonicity unit tests:** L1 rises with T and falls with pH at fixed everything
  else; L2 monotone in each criterion; L3 linear in application rate.
- **Categorical integrity:** the set of unique lithology class values is unchanged
  after any regrid. This failure mode arrives via a default GDAL resampling in a
  one-line reproject.

**Tier 2, soft and informative — consistency, not validation:**
- Global gross potential lands in ~0.5–4 GtCO₂/yr. Note in print that this is a very
  weak constraint: the published range spans an order of magnitude and several
  estimates descend from the same rate-law and surface-area lineage, so agreement is
  partly agreement with our own ancestors.
- **Primary Tier-2 check is pattern, not total:** rank correlation of per-hectare
  national potential against the Beerling group's national/state results (expect
  ρ ≈ 0.6–0.9). Tests the pattern, which is what L2 is for and which a single global
  constant cannot tune.
- Publish a reconciliation table where we disagree. Worth more than an agreement
  claim.

**Anti-tuning safeguard, in the methods text:** the scaling constant is fitted to
field trials only, never to the global total; its value and provenance are written
down before global aggregates are computed and not revisited. If the total lands
outside 0.5–4 Gt, that is reported as a finding, not a reason to adjust.

---

## Uncertainty

Two kinds, presented differently. Collapsing them into one "uncertainty layer" is the
mistake to avoid.

> **Structural uncertainty governs the map's *level* and is communicated as a single
> stated range. Input uncertainty governs the map's *local contrast* and is
> communicated per-pixel.**

**Inputs → analytic first-order propagation in log space.** The rate is a product of
power-law and exponential terms, so ln R is near-linear in ln{H⁺}, 1/T and the
moisture function:

```
σ²(ln R) ≈ (n·ln10)²σ²(pH) + (Ea/RT²)²σ²(T) + (∂ln f/∂θ)²σ²(θ) + cross terms
```

**Include the T–θ cross term** or state that it is dropped and in which direction that
biases — soil temperature and moisture are strongly negatively correlated in many
climates. Validate the linearization with a 200-draw Monte Carlo on a 1% stratified
sample and publish the check; that is what makes this design publishable rather than
assumed. Combined input uncertainty is roughly ±40–50%, i.e. ~1.5× — about an order
of magnitude less important than the structural terms, confirming the initial
instinct. But it is the only term that varies pixel-to-pixel, so it deserves a layer
regardless: a user comparing two nearby candidate fields sees exactly that term, and
the structural terms cancel for them entirely.

Do **not** claim errors cancel in aggregate. SoilGrids residuals correlate over
hundreds of metres to a few km, but reanalysis errors correlate at synoptic to
continental scales and do not average down over a country at all.

**Structure → an explicit ensemble of defensible choices, N ≈ 12–20**, via fractional
factorial over {rate-law variant} × {Eₐ lo/mid/hi} × {n lo/mid/hi} × {surface area:
geometric / roughness-corrected / BET} × {moisture function} × {soil-T product} ×
{θ product} × {cropland mask}. Report inter-member spread of the global L3 total
(expect 5–20×) and an inter-member rank-agreement map for L2.

Present the two separately and state explicitly that the structural ensemble is *a
range of defensible choices, not a probability distribution* — the framing IPCC uses
for model ensembles, which this audience will recognize.

### Eligibility under threshold uncertainty: three states, not two

Protocol thresholds are sharp but the gridded estimates are not, and there are two
biases worth naming:

- SoilGrids predictions are shrunk toward the conditional mean, so the predicted SOC
  distribution is narrower than the truth and marginal 4–6% soils are pulled toward
  the middle. Not correctable without the unshrunk conditional distribution.
- **Change of support:** Puro's 5% threshold applies to a sampled field; SoilGrids
  quantiles are predictive quantiles for a 250 m block average. Averaging reduces
  variance, so block-average SOC crosses 5% less often than field SOC does. Our
  exceedance probability is therefore **not** the probability a given field fails, and
  it is biased in a known direction. Label it with painful precision — "P(SoilGrids
  250 m block-average SOC exceeds 5 wt%)" — and call it a *screening likelihood*.

Reconstruct the distribution from q05/q50/q95 with a lognormal matched in log space
(`μ = ln q50`, `σ = (ln q95 − ln q05)/3.29`), report the fit residual against the
observed log-space asymmetry, and document the choice — near the threshold it is a
first-order determinant of the probability.

| State | Condition | Rendering |
|---|---|---|
| Excluded | P(exceed) > 0.9 | Solid exclusion |
| **Marginal** | 0.1 – 0.9 | Distinct hatch, *not* a blend |
| Passes | P(exceed) < 0.1 | Normal |

This beats a continuous multiplier because the user is doing a go/no-go screen and a
multiplier makes a marginal cell look like a slightly-worse good cell, inviting a
developer to prospect a site that will fail eligibility. It beats a binary mask
because it does not assert a distinction between 4.9% and 5.1% that the data cannot
support.

**Do not multiply eligibility into L2 by default** — that conflates "less suitable"
with "less likely to be creditable," which are different failure modes with different
remedies (one is physics; the other a soil test resolves in a week). Report raw L2 and
eligibility-discounted L2 separately. Version the thresholds (`puro_v2025_soc_5pct`)
in config and put the version in the legend so the map cannot silently go stale. Note
that **Isometric's pH<5.2 criterion is a warning, not an exclusion** — make it an
annotation flag with zero score effect rather than burying an editorial decision in a
score.

Do not report a confidence interval on eligible *area* from per-cell probabilities —
SOC and pH errors are spatially autocorrelated, so eligible area is far more uncertain
than independence implies. Either run a few conditional simulations with a fitted
correlation range, or report no CI.

---

## Feedstock and delivered cost

Cascade's largest omission, and the reviewers reframed it usefully: **lithology is the
wrong variable for delivered cost.** Basalt outcropping under a field is nearly
irrelevant if there is no quarry within haul range. Cost is set by quarry location ×
haul distance × fuel and labour.

**Build from a point inventory plus a travel-time surface, with lithology as a
secondary "could a quarry exist here" layer:**

1. **Quarry and slag points.** USGS MRDS (`https://mrdata.usgs.gov/mrds/mrds-csv.zip`,
   24.6 MB, 304,328 points, `DEV_STAT`=Producer, commodity `STN_C`=crushed stone,
   `OLV`=olivine) cross-filtered against basalt lithology; OSM `landuse=quarry` via
   Geofabrik extracts; Maus et al. 2022 global mining polygons (PANGAEA
   `10.1594/PANGAEA.942325`, 44,929 polygons, GeoPackage, land-use footprint with no
   commodity attribute); Global Energy Monitor Iron & Steel and Cement trackers for
   alkaline byproducts. **State the currency problem plainly:** MRDS stopped
   systematic updates in 2011 and the USGS active-mines layer is frozen at 2003, while
   USGS counted 3,531 operating US crushed-stone quarries in 2023. There is no current
   maintained national quarry layer. Inventory completeness varies by country, which
   is a more honest and more informative uncertainty structure than a uniform blur.
2. **Haul cost via accumulated cost-distance on a friction surface**, not global
   network routing. Use the Weiss et al. global motorized friction surface (1 km,
   purpose-built, publicly downloadable) to compute travel time from the nearest
   feedstock source, then convert to $/t with a stated per-hour trucking cost and
   payload. Far more tractable than planet-scale OSM routing and directly citable.
3. **Lithology at full resolution.** Replace the 0.5° convenience grid with the
   full-resolution GLiM vector (1.24 M polygons). The link in
   `../co2-storage-map/data/research/geodata_sources.md` lines 58–68 is **verified live
   with range support** (`https://www.dropbox.com/s/9vuowtebp9f1iud/LiMW_GIS%202015.gdb.zip?dl=1`,
   ~1.1 GB). Filter level-1 classes `vb` (volcanic basic) and `pb` (plutonic basic),
   export the subset, delete the source. This takes the feedstock component from 55 km
   to a few km — eliminating the single worst resolution mismatch in the stack. The
   55 km ceiling was self-imposed by using the convenience raster.
4. **Reuse what is already on disk** in `../co2-storage-map/data/raw/lithology/`
   (extracted and ready): `lip_shapefiles_ernst_youbi2017.zip` (Ernst & Youbi flood-basalt
   province outlines), `plates_global_ophiolites.zip` (PLATES/UTIG global ophiolite
   compilation), `usgs_ds414_ultramafic_us.zip` (US ultramafics), and the GLiM 0.5°
   raster. Ultramafic and serpentinite double as the asbestos-risk flag.

   **But treat these as a head start, not the layer.** That project assembled them for
   a different question — subsurface injection targets for in-situ mineralization — and
   its own `docs/METHODOLOGY.md` records the coverage gaps (no polygons for rift/arc
   volcanics, offshore basalt, or harrats). Three mismatches for ERW:
   - Injection wants thick confined formations; ERW wants **near-surface outcrop that
     can be quarried**. Same rock names, different selection criterion.
   - The ophiolite compilation is matched by geographic descriptor, so its geometry is
     coarse — fine for flagging a province, not for a delivered-cost surface.
   - Nothing in it locates **production**. A basalt province with no operating quarry
     supplies no feedstock, which is why the point inventory above, not the lithology,
     carries the cost layer.

   So: use LIP outlines to give flood-basalt provinces their own visual tier (Deccan,
   Columbia River, Paraná, Siberian Traps are the large well-characterized targets),
   use ophiolites and US ultramafics for the asbestos flag, and get the actual
   feedstock geometry from full-resolution GLiM plus quarry points.

Run **three named feedstock archetypes** (fresh basalt, metabasalt, ultramafic/dunite)
as separate layers rather than assuming one basalt — mineralogy shifts rate by more
than an order of magnitude and real deployments use local material.

---

## Spatial handling

| Trap | Mitigation |
|---|---|
| EPSG:4326 cell area varies with latitude, and so does nominal resolution (a 1/120° cell is ~930 m N–S but ~460 m E–W at 60°N) | **Do the analysis in an equal-area grid** (EASE-Grid 2.0 or Equi7 at 1 km), reproject to 3857 only for display tiles. Removes the whole error class rather than mitigating it, and makes haul distances valid. Carry an explicit per-cell area raster; never call `mean()` on a 4326 raster |
| Mixed native resolutions create false precision | Carry a per-cell effective-resolution layer (coarsest materially-contributing input; keep it simple, do not build an information-theoretic measure). **Never bilinear a coarse layer onto a fine grid** — it manufactures smooth ramps a viewer reads as real gradients. Use nearest neighbour and **let the blockiness be visible**; visible blocks communicate resolution better than any caveat text |
| Categorical resampling | Nearest neighbour or majority only; for lithology compute **class fractions** per target cell rather than resampling a code. Unit-test that unique values are unchanged |
| Spatial autocorrelation inflates effective sample size | Prefer reporting **classification agreement** (fraction of cropland area where two layers agree on tercile) over correlation. If a correlation is unavoidable, estimate n_eff by block bootstrap with blocks exceeding the fitted variogram range (expect n_eff ~10²–10³ over global cropland, not 10⁷) and report it alongside. No p-values |
| Domain-dependent bins | Absolute breakpoints, frozen ramp, **never auto-stretch to the visible extent** — auto-stretch-on-zoom would recolour the map on pan and users would believe the data changed |
| Cropland mask choice | WorldCover / ESA-CCI / GFSAD / Potapov disagree 20–30% globally and much more spatially. The whole domain rests on this choice; run a second mask as an ensemble member (nearly free) and report the movement. Use a **1 km cropland fraction, never a majority binary mask** — a >50% mask discards smallholder cropland, i.e. most of sub-Saharan Africa and much of South and Southeast Asia, exactly where the soil-pH co-benefit case is strongest |
| Soil depth interval | SOC declines steeply with depth, so a 0–5 cm layer exceeds 5 wt% far more often than 0–30 cm — plausibly doubling or halving excluded area. Fix and state the interval; run the sensitivity |
| Coastline slivers | Apply one common land/water mask last, drop cells below ~1% cropland fraction, assert the count of isolated single-pixel cropland cells is sane |
| Aggregates from display tiles | Never compute national aggregates from 8-bit tiles; compute from float source and ship precomputed numbers |

**Stop calling it "1 km."** Grid spacing and resolution are different things. Say
**"1 km grid, ~10–50 km effective resolution"** in the title, legend and filenames.
**Cap the zoom** at the level the coarsest material input resolves, or replace the
continuous surface above that zoom with a coarse block overlay and a "beyond supported
resolution" panel. The moment of misuse is precisely when someone zooms to their
field and reads a per-field number; expect "zoom to my farm" to be the most-requested
feature and refuse it on purpose, with the reason in the UI.

---

## Frontend

### Measured sizes drive the architecture

A background agent built a real global cropland grid and measured actual tile counts
and compressed sizes rather than estimating. Tiles containing cropland, and the
resulting archive size for the **pair** of RGBA textures:

| Pyramid | Tiles with cropland | PNG | WebP | Fits GitHub's 100 MB/file? |
|---|---|---|---|---|
| z0–z6 (~2.4 km/px) | 1,334 | 79 MB | **62 MB** | Yes, comfortably |
| z0–z7 (~1.2 km/px) | 4,129 | 245 MB | **193 MB** | No — 2× over as one file |
| z0–z8 (~611 m/px) | 12,907 | 1,237 MB | 958 MB | No — 10× over |

Measured mean cropland coverage of a populated tile is 23% at z7 and 42% at z8, and
WebP saves ~22% over PNG at the same content. Numbers are extrapolated from 24 sampled
tiles per level on a ~3 km cropland grid, so treat them as ±30%, not exact.

Sizes were independently derived twice and agree (245 MB PNG / 192 MB WebP at z0–z7).

**Hosting was tested in a real cross-origin Chrome page, not just with curl:**

| Host | Plain GET | Range GET | Verdict |
|---|---|---|---|
| GitHub Pages | 200 | **206** | Works |
| Hugging Face datasets (`resolve/`) | 200 | **206**, ETag + Content-Range *exposed*, redirect-safe | **Works, best cross-origin** |
| jsDelivr `/gh/` | 200 | 206, full preflight | Works |
| raw.githubusercontent | 200 | 206 (headers not exposed) | Works |
| **GitHub Releases** | ✗ | ✗ | **Unusable** |
| Zenodo | ✗ | ✗ (206 via curl, no CORS) | Unusable in-browser |

**Drop GitHub Releases.** Range works but it returns **zero** `access-control-*`
headers, preflight `OPTIONS` returns 405, it 302s to a signed URL that expires in ~60
minutes, and it sets `content-disposition: attachment`. Real Chrome `fetch` from a
cross-origin page fails outright. I had this in an earlier draft as a leading option;
it is dead.

Git LFS is also out — Pages serves the pointer file, not the content — so the 100 MB
per-file git limit binds for anything in-repo.

**Two hazards worth knowing before they cost a day:**
- **Never put Cloudflare (or any proxy) in front of GitHub Pages for PMTiles.**
  `pmtiles@4.4.1` *throws* if the server answers a Range request with `200` and a
  Content-Length exceeding the request ("Check that your storage backend supports HTTP
  Byte Serving"). A Cloudflare-fronted Pages host returned exactly that in testing.
- `pmtiles` sets `cache: "no-store"` on every range request on Chrome/Windows, so
  Windows users get no HTTP caching of tile bytes at all.

**If splitting, split by geography, not by zoom** — one PMTiles instance per region
plus a tiny static JSON index saying which archive owns a tile. This is a
fetch-routing problem, not a shader problem: each tile is its own draw call with its
own samplers bound. (Measured `MAX_TEXTURE_IMAGE_UNITS = 16`, so binding more is
possible anyway.)

### Decision: two tiers

**Tier 1 — single global texture, no tiling. This is the landing experience.**
Two RGBA textures at 4096×2048 (~10 km at the equator): 8.4 Mpx each, **67 MB of GPU
memory for both**, and only a few MB on disk. Zero tile-pyramid code, instant global
re-weighting, works on mobile, works offline, ships in the repo.

This is not a resolution compromise, and that is the point. The statistics review
concluded the product's *effective* resolution is 10–50 km because the feedstock
component is inventory-limited, so a 10 km default display is **honest rather than
degraded**. It also sidesteps the two worst failure modes at once: tile-boundary seams
from bilinear filtering, and GPU memory pressure (8192×4096 would be 268 MB and
14000×5200 would be 582 MB for the pair — the latter unusable on laptops).

**Tier 2 — z0–z7 WebP PMTiles, loaded lazily when the user zooms past the Tier-1
limit.** Display capped at z7, matching the 1 km analysis grid spacing, which is where
the zoom cap belongs anyway for the honesty reasons above. Hosting, in order:
1. **Hugging Face datasets** — the strongest option. Verified 206 with ETag and
   Content-Range exposed via `access-control-expose-headers`, redirect-safe, and it
   takes a single multi-GB archive so no splitting is needed at all.
2. **In-repo on GitHub Pages, split by region** into sub-100 MB archives. Same-origin,
   so CORS is moot, and Range is verified.
3. **Cloudflare R2** free tier (10 GB storage, 10 M GETs/month, free egress) — fine,
   but it requires a payment method on file, which the first two do not.

Build Tier 1 first and completely. Tier 2 is additive; if it slips the product works.

### Render stack: hand-rolled MapLibre custom layer, not deck.gl

Pin `maplibre-gl@6.1.0` and `pmtiles@4.4.1` (vendor `dist/pmtiles.js`, ~20 KB IIFE),
`go-pmtiles@1.31.2` for the build. **Skip deck.gl.**

The deck.gl shader hook does exist (`DECKGL_FILTER_COLOR`, injectable via
`getShaders()`), so that is not the objection. The objections are concrete:
`BitmapLayer` carries a single `bitmapTexture`, so the second texture needs a
hand-added sampler and `model.setBindings()` regardless; deck.gl v9 uses std140 UBO
shader modules, so the weights need a `uniformTypes` module with `vec4` padding to
dodge float-array alignment; and it costs **449 KB gzip** on top of MapLibre's 245 KB.
That is most of the custom-layer work anyway, plus a large dependency, in a project
whose ethos is vendored files and no build step.

There is also a **silent-corruption path through deck.gl**: `loaders.gl` calls
`createImageBitmap(blob)` with no options unless `options.imagebitmap` is passed, and
its `safeCreateImageBitmap` catches the error and *silently retries with no options* if
they are rejected — which reintroduces premultiplication (see below).

**Both candidate stacks are WebGL2-only** (MapLibre v6 removed WebGL1), so the
WebGL1 question is moot and we get useful capabilities for free: native integer
textures (`R8UI` + `texelFetch` makes bit-packed flag unpacking exact by construction),
and a measured `MAX_ARRAY_TEXTURE_LAYERS = 2048`, which makes `TEXTURE_2D_ARRAY` the
right substrate for the Tier-2 tile cache — one bind, 2048 slots, eviction is slot
reuse, no per-tile texture churn.

Two MapLibre-specific gotchas: custom layers must output **premultiplied** colour
(MapLibre sets `blendFunc(ONE, ONE_MINUS_SRC_ALPHA)`), which is harmless while alpha is
0 or 1 but will bite the moment we draw semi-transparent marginal-eligibility cells; and
the stale-container-size bug documented at the bottom of `../BiCRS Map/src/app.js`
(`refitMap()`) will recur with a custom WebGL layer.

### Data encoding — the premultiplied-alpha trap, resolved by experiment

A 4×1 RGBA PNG with known values was round-tripped through each upload path and read
back with `readPixels`:

| Path | Expected `200,150,100,128` | Expected `10,20,30,1` |
|---|---|---|
| `createImageBitmap(blob)` **default** | `100,75,50,128` ✗ | `0,0,0,1` ✗ |
| `{premultiplyAlpha:'none'}` | `200,150,100,128` ✓ | `10,20,30,1` ✓ |
| `{premultiplyAlpha:'premultiply'}` | `100,75,50,128` ✗ | `0,0,0,1` ✗ |
| **any path, with alpha = 255** | exact | exact |

Three findings that invert the usual advice:

- **The corruption destroys RGB, not alpha.** Alpha survived exactly in every path;
  low-alpha pixels have their colour channels annihilated to 0. So the danger is not
  "don't store data in alpha" — it is that a low alpha *destroys your other channels*.
- **`UNPACK_PREMULTIPLY_ALPHA_WEBGL` had no effect** on an `ImageBitmap` source. Only
  the decode-time `premultiplyAlpha` option governs. Do not rely on the `pixelStorei`.
- **Writing alpha = 255 everywhere was exact in every single path**, including the
  default. That, not the flags, is the real defence.

Recipe: `createImageBitmap(blob, {premultiplyAlpha:'none', colorSpaceConversion:'none'})`,
plus the `pixelStorei` calls as belt-and-braces, `RGBA8`, `NEAREST`/`NEAREST`,
`CLAMP_TO_EDGE` on both axes, no mipmaps. In the Python encoder write **alpha = 255
everywhere**, put mask flags in a colour channel, and strip `gAMA`/`sRGB`/`iCCP` chunks.

**Bit precision, measured through the actual aggregator** (max |ΔScore|): 6-bit 0.091,
7-bit 0.057, **8-bit 0.024**, 16-bit 0.0001. 8-bit is marginal on raw values and fine
once the floor is applied — see below. Two quantities genuinely need 16-bit as **hi/lo
channel pairs**: monthly soil temperature (8-bit step is 0.275 °C over −25…45 °C, need
~0.1) and SOC (step 1.57 g/kg over 0–400, need ~1.0). Since the shipped layers are
normalized annual factors, this mostly affects the **hover readout** rather than the
shader, so pack the hi/lo pairs into the second texture rather than widening the first.

**The `ε` floor is a correctness requirement, not a nicety.** Measured: with ε = 1e-3,
one 8-bit step near zero moves the score by **0.23** — catastrophic. Raising the floor
to **ε = 0.02** (normalize at build time so the lowest non-masked value quantizes to
5/255, and reserve 0 *exclusively* for hard-masked cells) drops max score error to
**0.0060**, rms 0.0007 — about 5% of one legend class. Also: **keep the
limiting-factor argmin in linear space.** Log-encoding the channels marginally
improves score error but raises limiting-factor label flips from 0.53% to **1.89%**.

Tiles need a **1-pixel buffer with interior sampling**: the analysis grid is 30″
EPSG:4326 while tiles are Web Mercator, so without a buffer the reprojection
reintroduces seams at every tile edge even with `NEAREST`.

Never compute a reported number from the 8-bit display data. National aggregates and
popup values come from the float source.

**Two cheap experiments still outstanding**, both timed out during planning; run them
in the Tier-1 spike:
- Does a colour-chunk-tagged PNG shift RGB under `colorSpaceConversion:'none'` versus
  default? (Mitigated meanwhile by stripping the chunks and verifying with `pngcheck`.)
- Do browsers truncate 16-bit PNG to 8 bits on decode? Strongly expected yes, which is
  why hi/lo packing is planned rather than native 16-bit — but it is an assumption.

Information architecture carries over from `../BiCRS Map/src/app.js`: fixed sidebar,
segmented mode switcher, dynamically rebuilt legend with live area counts, slide-in
detail panel with per-cell values and sources, deep-link URL hash, methodology modal.
The rendering substrate changes from Leaflet SVG polygons to a WebGL raster layer.

Shader-side essentials already settled by the statistics review:

- Precompute `log vᵢ` into texture channels at build time. The shader is then a pure
  dot product plus one `exp` — the cheapest possible response to slider movement.
  Quantize `log v` over `[log εᵢ, 0]`; the floors needed for the mathematics also
  provide the quantization range. Guard `log(0)` with `max(v, 1e-6)` even with floors.
- Use `highp`. `mediump` on some mobile GPUs has a ~10-bit mantissa and a composite
  built from 8-bit textures with `pow`/`exp` will band, which users read as data
  structure.
- Normalize weights in the shader. Note the UX subtlety that with Σw=1 enforced,
  dragging all sliders up is a no-op — put "weights are relative; only ratios matter"
  in the UI or expect bug reports.
- The limiting-factor mode is `p → −∞` in the same power mean, so it shares the code
  path.

Sketch (Tier 1, one quad, two textures):

```glsl
#version 300 es                      // WebGL2 only; MapLibre v6 dropped WebGL1
precision highp float;               // mediump banding is visible; see risks
uniform sampler2D uTexA, uTexB;      // RGB = 6 value-function channels, alpha = 255
uniform usampler2D uFlags;           // R8UI, exact via texelFetch (no interpolation)
uniform vec3 uWa, uWb;               // user weights, normalized on the CPU
uniform int  uMode;                  // 0 score, 1 limiting factor
uniform sampler2D uRamp;             // 256x1, built from the same array as the legend
out vec4 fragColor;

const float EPS = 0.02;              // measured floor; 1e-3 swings the score by 0.23

void main() {
  uint flags = texelFetch(uFlags, ivec2(gl_FragCoord.xy), 0).r;
  if (isExcluded(flags)) { fragColor = premul(EXCLUDED); return; }

  // v_i in LINEAR space: argmin label flips rise 0.53% -> 1.89% if log-encoded
  float v[6]; dequantize(texture(uTexA, vUV).rgb, texture(uTexB, vUV).rgb, v);
  if (uMode == 1) { fragColor = premul(factorColor(argmin(v))); return; }

  // p -> 0 : log S = sum(w_i * log v_i). Weights are elasticities.
  vec3 la = log(max(vec3(v[0], v[1], v[2]), EPS));
  vec3 lb = log(max(vec3(v[3], v[4], v[5]), EPS));
  float s = exp(dot(uWa, la) + dot(uWb, lb));

  vec4 c = texture(uRamp, vec2(clamp(s, 0.0, 1.0), 0.5));
  if (isMarginal(flags)) c = hatch(c, gl_FragCoord.xy);   // hatch, never a blend
  fragColor = premul(c);             // MapLibre expects premultiplied output
}
```

**Colormap and legend stay in sync by construction, not by discipline:** the ramp
texture and the sidebar legend breaks are both generated from the same
`engine_constants.js` that `emit_constants.py` writes out of `constants.py`. Add a test
asserting the ramp texture's sampled colors match the legend swatch colors — this is
precisely the drift class that broke BiCRS in production.

### Hover and click readout

Keep a **CPU-side copy of the decoded data** in typed arrays alongside the GPU upload,
in a Map keyed by `z/x/y`. Hit-testing is then `latlng → (row, col)` arithmetic and an
array index — simpler and faster than the polygon hit-testing BiCRS does, and it needs
no GPU readback. Measured cost: 256×256×4×2 textures = 512 KB per tile, so **~6 MB for
the 12 visible tiles**; Tier 1's single texture pair is ~50 MB of heap.

Recompute the score in JS with the same weights and reconcile against the shader by
sharing the one generated constants file. Sub-millisecond, exact, and it yields every
input value.

Reject `readPixels`: it forces a pipeline stall (~5–15 ms) and returns the *colour*,
not the inputs. Reject re-fetching on hover (network latency on every mouse move).

Popup numbers come from the float source, not the 8-bit display data.

### Honesty affordances in the UI
- Default labelled "Neutral (equal weights) — not a recommendation."
- A "randomize within plausible range" button. Nothing communicates "this is a choice"
  faster than watching the map move when you press a button.
- Live stability readout: fraction of cropland area whose decile differs from the
  equal-weight default under current weights, from an area-weighted decimated sample.
- Never show a bare score. Popups read "L2 = 72 (58–81 across the published weight
  ensemble)."
- On-the-fly country summaries must come from an **area-weighted** decimated sample
  (uniform sampling of a 4326 raster over-samples high latitudes) with the sampling
  error stated. Never report a national mean of a normalized score — report
  area-weighted deciles, cropland area above absolute thresholds, and L3 totals, all
  of which are domain-invariant.

### The headline figure: weight-stability, not the score map

Sample K = 500–1000 weight vectors from a Dirichlet on the simplex (α ≈ 5 for a
plausible ensemble, α = 1 as a stress case) and record per cell:

```
π(cell) = P( L2 > 60 | w ~ Dirichlet )
```

Threshold on the **absolute** value, not the top decile of each draw's own
distribution, or domain-dependent normalization sneaks back in. Cost is ~10¹¹ flops —
seconds on a GPU, ~10 minutes chunked in numpy.

Expected result, worth stating as a prediction: the humid tropics and acidic-soil
regions are robust, and **the entire temperate breadbasket is weight-contingent.**
That is exactly the caveat a reader needs and exactly what a weighted-sum map hides.

Do **not** run a Sobol Monte Carlo over the weight simplex. Under the geometric mean
`log L2` is linear in the weights, so the complete first-order decomposition is closed
form with no interaction terms; a Monte Carlo there would be visibly wasted compute.
Point the compute at the genuine nonlinearities instead: `p` and the value-function
breakpoints. Expectation to test: **the structural ensemble is wider than the weight
ensemble**, which if true is the honest headline — the choice of aggregation form
matters more than the choice of weights — and preempts "you just picked weights" by
showing the weights were not the biggest lever.

### Ranked frontend risks

| Risk | Mitigation |
|---|---|
| Premultiplied alpha silently destroying RGB | Write **alpha = 255 everywhere** in the encoder — proven exact in every upload path. Everything else is belt-and-braces |
| `ε` floor too low, so one 8-bit step swings the score by 0.23 | ε = 0.02, with 0 reserved for hard-masked cells only. Measured error then 0.006 |
| 16-bit PNG truncation assumption wrong | Cheap round-trip experiment in the Tier-1 spike; hi/lo packing is planned regardless |
| Tile sizes ±25–30% (measured on synthetic fractal fields with a real mask) | Build one region from real data and measure before committing to a hosting tier |
| GPU memory on mobile | Tier 1 at 4096×2048 is 67 MB for both textures. The 8192×4096 opt-in is 268 MB and is the single biggest OOM risk, so keep it opt-in |
| Legend drifting from the shader colormap | One Python source emits both the legend stops and the 256×1 ramp texture, plus an equality test |
| Tile seams from the 4326→3857 reprojection | 1-pixel tile buffer, sample the interior, `NEAREST` + `CLAMP_TO_EDGE` on both axes |
| `refitMap()` stale-container-size bug recurring | Documented at the bottom of `../BiCRS Map/src/app.js`; port the fix deliberately |
| GDAL not installed (`gdalwarp` not on PATH) | Explicit phase-0a prerequisite |

---

## Data inventory

Every entry needs a version check before use ("verify it is the latest published
version"). Sources marked **verified** had their download endpoint tested during
planning.

| Layer | Source | Res | Notes |
|---|---|---|---|
| Soil pH, SOC, bulk density, CEC + Q0.05/Q0.5/Q0.95 | SoilGrids v2.0 (ISRIC), 0–5/5–15/15–30 cm | 250 m | **Verified:** VRTs live and range-readable at `files.isric.org/soilgrids/latest/data/<var>/`, `rasterXSize=159246`, Interrupted Goode Homolosine, `Int16`, nodata −32768, `relativeToVRT="1"` COGs. Q0.05/Q0.95 exist for both `phh2o` and `soc` — exactly what the exceedance-probability work needs. `gdalwarp -t_srs EPSG:4326 -tr 0.00833333 … /vsicurl/<vrt>` works without downloading globally. **Two gotchas:** `BlockYSize=6` (striped, not square-tiled) so random access is inefficient — **warp region by region, never globally in one shot**; and pH is stored ×10 while SOC is in dg/kg |
| Soil temperature, monthly | Lembrechts et al. 2022, Zenodo record 7134169 (concept `10.5281/zenodo.4558731`) | **native 30 arcsec** | **Verified, and a real win:** monthly layers are distributed as `soilT_{1..12}_{0_5cm,5_15cm}.tif` — 24 GeoTIFFs, ~181–192 MB each, ~4.4 GB total, CC BY 4.0, `206` + `accept-ranges` so `/vsicurl` streams them. **Natively on our exact target grid, so no resampling and no ERA5 fallback needed.** Note the GEE mirror exposes only the annual SBIO bands, not the monthly ones, so this must come from Zenodo. Absolute °C, not a soil-minus-air offset. The 2025 GloSVeT successor is 0.05°, so not an upgrade |
| Soil temperature, deep | ERA5-Land `stl2` (7–28 cm) | ~9 km | Depth sensitivity for the 20 cm near-field zone |
| Air temperature | GSHTD v1.0, 2001–2020, monthly | 1 km | **Cascade parity comparison only**, not the Arrhenius argument. Original host (`cjgeodata.cug.edu.cn`) was unreachable during planning — may be geo-restriction rather than downtime; the community GEE mirror `projects/sat-io/open-datasets/GSHTD/TMEAN` is the fallback. Derive the annual mean ourselves from monthly |
| Soil moisture | **Decision needed at build time.** GSSM1km (Han et al. 2023) is 1 km daily 2000–2020 but the global archive is **779 GB and GEE-only**; figshare carries a Europe subset only, and no climatology is published. SMCR (*Scientific Data* 2025, Zenodo) is newer, better validated against 372 in-situ stations, 1 km daily 1980–2023, but still ~185 GB per time chunk | 1 km | **Recommended: GEE-side reduction to a monthly climatology, exporting only the small result.** Falls back to ERA5-Land `swvl2` (7–28 cm, ~9 km) if GEE is unavailable. 0–5 cm depth mismatch against the 0–20 cm reaction zone stands either way — document it |
| Cropland fraction | ESA WorldCover via GEE `reduceResolution` export; GLAD 3 km global cropland (`gladxfer.umd.edu`, 7.4 MB) as a quick scaffold; ESA CCI-LC 300 m local fallback; GFSAD1000 for irrigated/rainfed | 1 km frac | Fraction, never majority binary. **Streaming WorldCover locally is not viable: 2,651 tiles, 124 GB, mean 47 MB/tile** (counted via S3 pagination). This is the one place GEE is unambiguously the right answer |
| Drainage / recharge | Global runoff product (GRUN or LSM drainage) | ~0.5° | For η_transport; add irrigation return flow |
| Irrigation | GMIA / MIRCA | ~5 arcmin | Modifies q and θ; makes the Indo-Gangetic Plain viable |
| Lithology | **GLiM full-resolution vector, 1.24 M polygons — verified live** | few km | Filter `vb`, `pb`; replaces the 0.5° grid |
| Flood basalts, ophiolites, US ultramafic | Already on disk in `../co2-storage-map/data/raw/lithology/` | vector | Reuse; ultramafic doubles as asbestos flag |
| Quarries and mines | USGS MRDS **verified** (24.6 MB, 304,328 pts); OSM `landuse=quarry`; Maus et al. 2022 (PANGAEA) | point/poly | Stale currency is a stated caveat |
| Alkaline byproducts | GEM Iron & Steel Tracker (Mar 2026 release), GEM Cement & Concrete | point | Download is behind a JS click-through |
| Travel-time friction | Weiss et al. 2020 motorized friction surface, GEE asset `projects/malariaatlasproject/assets/accessibility/friction_surface/2019_v5_1` | ~928 m | Basis for haul cost. Units are **minutes to traverse one metre**, accumulated as cost-distance. The 2019 v5.1 surface supersedes the 2015 one. **GEE or the R `malariaAtlas` package only** — no anonymous HTTP GeoTIFF endpoint exists |
| Water bodies | HydroLAKES / JRC Global Surface Water | — | Puro water-proximity exclusion |
| Post-2020 conversion | Hansen Global Forest Change loss-year | 30 m → 1 km frac | Puro rule 3.9.1a |
| N fertilizer | Lu & Tian, or EarthStat crop-specific N | ~5 arcmin | Strong-acid diagnostic layer only |
| Validation targets | Beerling et al. 2025 *Nature* US outputs (Zenodo `10.5281/zenodo.14755423`, 124 MB zipped / 11.8 GB expanded); `github.com/thutyecology/ERW` country-level CSVs | — | Pattern check only, not validation |

### Google Earth Engine is a required pipeline stage

Verification turned up a hard dependency that changes the pipeline shape: **four
layers are practically GEE-only.** Cropland fraction (ESA WorldCover is 10 m and
2.6 TB globally, so aggregating locally is not viable), soil moisture (779 GB global
archive, no published climatology), the Weiss friction surface (no anonymous HTTP
endpoint), and GSHTD (original host unreachable).

This is not a workaround, it is the right architecture and it is what Cascade does
too. Add an explicit **stage 0**: a small, version-controlled set of GEE scripts that
do the heavy reduction server-side and export only 1 km global GeoTIFFs — a monthly
soil-moisture climatology, a cropland-fraction grid, the friction surface, and the
GSHTD annual mean. Exports are tens to low hundreds of MB, land in `data/raw/gee/`,
and everything downstream is local Python. Commit the GEE scripts to the repo so the
step is reproducible even though it is not runnable from `build_all.sh`.

Two consequences to accept up front: the pipeline is **not** fully reproducible from a
bare `git clone` without a free GEE account (document this prominently in the README),
and GEE export quotas may force chunking. Local fallbacks exist for the two layers
that matter most — ESA CCI-LC 300 m for cropland and ERA5-Land `swvl2` for moisture —
both coarser, and both worth wiring up as ensemble members anyway since the cropland
mask choice is already a planned ensemble dimension.

Field-trial anchors: Beerling et al. 2024 PNAS (Illinois, 200 t/ha over 4 yr,
10.5 ± 3.8 tCO₂/ha, p80 267 µm); UNDO Scotland (Frontiers in Climate 2025,
0.33–0.53 tCO₂/ha over 1.5 yr at 78–126 t/ha); a tropical trial if a full
particle-size distribution is obtainable.

---

## Repository layout

```
erw-map/
  README.md               pipeline walkthrough, live URL, MIT license
  PLAN.md                 this plan, condensed; §"Sanity checks" gate table
  LICENSE                 MIT (code); data-source licenses noted in METHODOLOGY
  docs/
    METHODOLOGY.md        following ../BiCRS Map/docs/METHODOLOGY.md structure:
                          uncertainties ranked by decision-leverage, consolidated
                          source table per layer, every tunable constant in one table
    KINETICS.md           rate law, Palandri-Kharaka parameters, eta_DIC derivation
    VALIDATION.md         pre-registered gates, per-trial constants, covariate hull
    SENSITIVITY.md        weight ensemble, structural ensemble, pi map
  gee/                    stage 0: Earth Engine reduction scripts (see above).
                          Committed for reproducibility; run manually, not from build_all.sh
  scripts/
    download_raw.sh       curl into gitignored data/raw/; delete after processing
    build_all.sh          numbered sequential stages
    grid.py               equal-area analysis grid, cell-area raster
    soils.py              SoilGrids warp, quantile -> exceedance probabilities
    climate.py            monthly soil T and moisture
    cropland.py           cropland fraction, masks
    feedstock.py          GLiM filter, quarry points, friction cost-distance
    kinetics.py           Palandri-Kharaka + Gislason-Oelkers, eta_DIC, eta_transport
    engine.py             L1/L2/L3, value functions, power mean  <- single source of truth
    constants.py          every tunable in one module
    emit_constants.py     writes src/engine_constants.js + src/colormap.js from
                          constants.py -- legend stops and the 256x1 shader ramp
                          texture come from the same array, so drift is impossible
    encode_textures.py    value functions -> packed RGB PNG/WebP, alpha=255 always,
                          colour chunks stripped, 16-bit hi/lo pairs for soil T and SOC
    ensemble.py           structural ensemble, pi map, uncertainty
    checks.py             the pre-registered gate suite
    tiles.py              pyramid build
  src/                    static site
  data/
    raw/                  gitignored
    processed/            small derived products, sufficient to regenerate all figures
```

Two conventions carried over deliberately from BiCRS:

- **One shared engine module** imported by everything, so scope variants and docs
  cannot diverge.
- **Emit engine constants from Python into the JS bundle** (`emit_constants.py` →
  `src/engine_constants.js`). BiCRS planned this and never shipped it, and the
  hand-mirrored `PATHWAY_PAYLOAD`/`PAYLOAD_OF` pair silently broke production as a
  result (`../BiCRS Map/to_do.md` item 10). Do it from day one — the value-function
  breakpoints, floors, weights and colormap breaks all need to exist in exactly one
  place.

Disk discipline per standing instructions: check sizes before committing;
download → derive → delete; keep derived files small and sufficient to regenerate
every figure without re-downloading; long jobs in the background.

---

## Build phases

| # | Phase | Gate to pass before continuing |
|---|---|---|
| 0a | Prerequisites: install GDAL ≥3.8 (**`gdalwarp` is not currently on PATH**), pin `rasterio==1.5.0`, `numpy==2.2.1`, `Pillow==11.1.0` | `gdalwarp` runs; `/vsicurl` reads a SoilGrids VRT |
| 0b | GEE exports: cropland fraction, monthly soil-moisture climatology, friction surface, GSHTD annual mean | Exports land at expected grid and extent; sizes within tens–hundreds of MB |
| 0c | Tier-1 render spike: one hard-coded texture pair, custom MapLibre WebGL2 layer, weight sliders. Run the two outstanding encoding experiments (colour-chunk RGB shift, 16-bit PNG truncation) | Slider recolors without a fetch; round-trip readback is byte-exact |
| 1 | Equal-area grid, cell-area raster, cropland fraction | **Area closure** vs FAOSTAT within 10% |
| 2 | `kinetics.py`: Palandri–Kharaka + Gislason–Oelkers, η_DIC | **Gudbrandsson test** within 0.5 log units, no free parameters |
| 3 | Soils and monthly climate onto the grid | Monotonicity unit tests; 250 m→1 km mean and variance both retained |
| 4 | L1 monthly-integrated, plus the Cascade-parity baseline layer | Side-by-side difference map produced and explicable |
| 5 | Feedstock: GLiM full-res, quarry points, friction cost-distance | Delivered-cost surface sane against known quarry economics |
| 6 | Eligibility probabilities, three-state masks | Excluded-area sensitivity to soil depth interval reported |
| 7 | L2 value functions, floors, power mean; `emit_constants.py` | Constants exist in exactly one place |
| 8 | L3 calibration | **Per-trial constants published; λ within 1–100; stoichiometric ceiling** |
| 9 | Ensembles: weight π map, structural ensemble, input uncertainty | Linearization check vs 200-draw MC on 1% stratified sample |
| 10 | Tier-1 global texture + frontend | Legend/shader colormap equality test; zoom cap in place; alpha = 255 asserted in the encoder |
| 10b | Tier-2 PMTiles pyramid (optional, additive) | Real-data z7 size measured for one region before choosing a hosting tier |
| 11 | Docs, sanity-check table including fails, GitHub Pages | Full gate table published |

Phases 1–2 are the real risk. If the Gudbrandsson test fails badly the kinetic
approach needs rethinking before anything else is built, so it comes second and
before any data engineering beyond the grid.

---

## Deferred (not in this build)

- MRV cost surface from Isometric's sampling-density tables (Appendix 3: 3-plot soils
  at 1 sample per 0.075 ha; plot fraction 2.5% below 1000 ha tapering to 1% above
  10,000 ha). Needs a global field-size layer to be meaningful.
- Agronomic lime-displacement co-benefit.
- Downstream river and ocean retention (Kanzaki et al. 2023 36×36 ocean grid;
  Puro.earth's flat 20% ocean-loss default).
- A US high-resolution scope (gNATSGO/POLARIS soils, PRISM climate, USDA CDL, USGS
  SGMC lithology, NTAD network routing). The code should be structured with BiCRS's
  scope-config pattern so this can be added without touching render code.

---

## Verification

**Pipeline:** `scripts/build_all.sh` runs end to end from a clean checkout after
`download_raw.sh`, and `scripts/checks.py` prints the full pre-registered gate table
with pass/fail. Release requires every Tier-1 gate green and every Tier-2 result
published whether or not it agrees.

**Numerical:** unit tests for monotonicity, the stoichiometric ceiling, categorical
regrid integrity, and area closure. A separate test asserts the JS constants emitted
by `emit_constants.py` match `constants.py`.

**Reproduction check before extending anything:** reproduce Cascade's index and
confirm our implementation of *their* formula recovers their published percentile
pattern, then reproduce Gudbrandsson's measured Ca and Mg release with no free
parameters. Report both numerically before building L2 or L3.

**Frontend:** load the built site over HTTP, confirm slider movement recolors without
a fetch, confirm the limiting-factor mode agrees with a Python computation of
`p → −∞` on a sample of cells, confirm hover readouts match the float source at those
cells, confirm the legend breaks match the shader colormap, confirm the zoom cap
engages, and check rendering in both light and dark themes at mobile and desktop
widths. Verify figures visually per standing instructions: axis units labelled,
adequate title/subtitle separation, no overlapping text.

**Physical plausibility spot check:** L3 at 20 t/ha basalt must land in roughly
0.3–10 tCO₂ gross/ha/yr across agricultural regions. Values far outside that envelope
mean a unit or assumption error, not a discovery.
