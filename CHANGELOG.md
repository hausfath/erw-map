# Changelog

Development history of the ERW Atlas, including the defects found along the
way and the reasoning behind each reversal. The map's Methods modal describes
the model as it stands; this file describes how it got there. Newest changes
first within each build.

## Two new results, July 2026

Both came from data and papers already within reach, and both change what to work
on next rather than changing the map.

**η_DIC reproduces Dietzen & Rosing's X\*, derived from a different starting
point.** They compute X\* from a soil proton budget; we compute η_DIC from
carbonate equilibrium. Same function of pH and pCO₂, agreeing to within 0.03 at
every value they report across a 40× pCO₂ range (gate 2d). Three consequences:

- It is the strongest external check in the project — two independent derivations
  from different literatures, not a transcription check.
- **The protocol-sanctioned strong-acid correction is already in the model.** The
  to-do item claiming it was a missing term was wrong in kind and has been
  reframed. Gate 2d now exists partly to prevent someone adding a second
  pH-and-pCO₂-based deduction on top and double-counting.
- **The pH measurement-convention question is closed.** The paper states its
  thresholds are on pH(H₂O) with a rationale — pH(H₂O) "is more representative of
  the soil solution … than pHCaCl₂, which is typically lower as it includes protons
  displaced from the soil exchange complex" — and both protocols' pH numbers trace
  to it. So no offset applies anywhere. Also corrected: the "5.2–7.2" range we
  quoted is not verbatim; their three thresholds are 5.20, 6.29 (pCO₂-dependent)
  and 7.10.

What survives is narrower and harder: Holden et al. 2024 measured 2% carbonic-acid
weathering at a real site where this formulation gives ~71%. An equilibrium factor
of pH and pCO₂ cannot capture continuous fertiliser loading, so the open problem is
a flux formulation, not a missing factor.

**Surface repartitioning cannot rescue the rate law (gate 11b).** The fixture
measures Si, Ca, Mg and Fe; three minerals leave two free surface fractions; so
requiring one partition to reproduce four elements is over-identified and is a test
rather than a fit. Si and Fe were added to `ELEMENT_PER_FORMULA` to enable it —
they had been sitting unused in the fixture.

- Fitting to Ca+Mg alone drives pyroxene to **exactly zero** and held-out **Fe then
  fails by 17.8 log units**, because pyroxene is the only Fe carrier. An element
  the fit never saw destroys it.
- Fitting all four with both parameters tuned on the test data still leaves the
  worst element at **0.88** against a 0.5-log tolerance.
- Constrained to the pre-registered factor-of-3 plausibility bound, Mg degrades to
  1.15.

So the residual is not a mixing problem, and strand A's per-temperature refit
should not be run — it is aliased with the activation energy and the pooled version
has now failed. This redirects the kinetics work onto the rate constants and the
missing alkaline-branch mechanism. A negative result, recorded because it closes a
line of enquiry that looked like the leading candidate.

## Post-review fixes, July 2026

Implemented after the six-reviewer audit. The **flux-reconciliation cluster is
deliberately not addressed here** — the missing concentration ceiling and the
Damköhler limb question set the map's absolute level, they need reconciling
against the field-trial literature rather than patching, and they are recorded as
the largest open problem in `docs/METHODOLOGY.md` §6 and in the Methods panel.

**Two bugs that produced wrong numbers.**

- **The grind shift was applied twice** in every browser CO₂ path — once inside
  `l1` and again on the CO₂ figure. At d50 = 40 µm that inflated gross CO₂ by
  **3.45×** and broke the stoichiometric ceiling by 3.46× (0.999 tCO₂ per tonne of
  rock against a 0.289 maximum). The shift is exactly zero at the default grind,
  so the landing map and every published figure were unaffected and the Python
  gates could not see it — the build only ever evaluates the reference condition.
  Fixed in the shader, the hover readout and the stability sampler. Verified in
  the browser: `CO₂ / (frac × 5.78)` is now constant at 0.988 across the whole
  slider range, and CO₂ at the fine extreme is 5.67 against the 5.78 ceiling.
- **The stability metric measured level, not rank.** It digitised both the
  perturbed and the baseline setting against the *baseline's* decile edges, so any
  change in level registered as instability even when no cell changed rank. Each
  setting is now digitised against its own edges. A common exponent on all three
  terms — exactly monotone in the score, therefore rank-preserving — now reads
  **2%** against ~50% before. The baseline edges are cached and invalidated on
  grind and cost, which the old code never did.

**Two structural corrections to the model.**

- **η_DIC moved outside the dissolution exponential.** Carbonate speciation does
  not slow rock dissolving; it discounts the carbon each unit of alkalinity
  carries. Inside the exponential it suppressed the predicted *fraction weathered*
  — the one layer field trials can measure — by up to ~2× in acid soils.
- **Flooded pCO₂ is no longer paired with drained pH.** SoilGrids pH is an
  air-dried, drained measurement, but submergence drives soil pH toward 6–7 (van
  Breemen 1987; +1.0–1.5 units measured in Schulz et al. 2024). The chemistry now
  uses a flooding-adjusted pH. **This closes the paddy question against the
  mechanism:** the high-pCO₂ advantage exists only below about pH 5.5 and
  submergence removes exactly that acidity, so the retracted paddy prediction now
  has a mechanistic, self-cancelling explanation rather than only a population
  one. Map effect is small (paddy-weighted median pH is already 6.4 and mean
  flooded cell-time is 0.014).

**Validation apparatus.**

- **`docs/VALIDATION.md` and `docs/METHODOLOGY.md` now exist.** Roughly 18 call
  sites cited them as the authority for the pre-registered tolerance, the
  constancy test and the sampling design, and `docs/` was empty — so the
  pre-registration lived only in a mutable Python file and a gitignored notes
  file. The Phase 2 kinetics criteria are now tracked, with amendments: a
  parameter budget, a leave-one-temperature-band-out split, Si and Fe held out as
  out-of-sample elements, and boundary solutions counted as failures. The original
  criterion 1 could not discriminate — it is passed by a trivial per-band offset
  and, when run, produced a degenerate fit with pyroxene at exactly zero for a
  rock that is 39 vol% pyroxene.
- **Gate 11 now scores on the shipped basis**: volume fractions and the Ca+Mg
  charge sum, rather than the paper's own fitted surface fractions. Those are
  three parameters fitted to the same 25 experiments, so scoring on them borrowed
  an in-sample fit into a gate titled "no free parameters". The gate got redder,
  correctly: the charge-sum residual is **+1.14 bias / 1.19 MAD**, worse than the
  per-element figures (Ca +0.50, Mg +1.59) implied.
- **New gate 6c: archetype mineralogy must mass-balance its stated oxides.** It
  **fails**, and that is the point — `delivered_basalt`'s mineral modes imply
  **1.99× its stated MgO**, and `ultramafic` states 3 wt% CaO with no Ca-bearing
  mineral at all. An independent line of evidence that olivine is over-weighted,
  reached with no external data. Related: forsterite is 11.8 vol% of the default
  archetype but supplies **80.1%** of its Ca+Mg release, so the shipped rate law
  is closer to an olivine model than a basalt one.
- **Gate 7 relabelled an arithmetic self-check.** `delivered_basalt`'s oxides were
  chosen to reproduce the CO₂ figure it verifies. It was appearing in the README's
  gate table as evidence.
- **The suite no longer reports "N passed" without context.** Exactly one gate
  compares the model against independent data and it fails; everything else is
  internal consistency, literature reproduction or an invariant.
- **`DIVALENT_PER_FORMULA` and `ELEMENT_PER_FORMULA` reconciled** and asserted
  equal at import. They disagreed on augite (1.60 vs 1.30) and bronzite (1.00 vs
  0.80), meaning the validated function was not the shipped one. Note the augite
  fix *raises* modelled Mg release, so it makes gate 11 slightly worse.

**The pH convention question, half resolved.** Isometric v1.2 states in three
places that its 5.2 threshold is measured in a soil-water slurry, i.e. pH(H₂O) —
the same basis SoilGrids reports. So no offset applies, and the dead
`PH_H2O_MINUS_CACL2` constants are removed rather than left for someone to apply:
using them would have *introduced* an error moving 55% of cropland by decile.
Puro remains unpinned (it cites only ISO 10390:2021, which permits all three
bases). A different and still-open offset is slurry versus *soil solution*, which
is what the rate law and η_DIC actually want.

## Corrections to this file, July 2026

A six-reviewer scientific audit found that several numbers recorded below were
stale, unreproducible, or measured by a broken diagnostic. The narrative is left
intact — it is the record of what was believed at the time — and the corrections
are listed here. Where an entry below states an outcome that did not occur, that
is noted rather than edited away.

| Recorded below | Actual | Why it was wrong |
|---|---|---|
| drainage limits 19.5%, reactivity 74.6% of cropland | **drainage 59.3%, reactivity 34.0%, alkalinity retention 6.7%** | Does not reproduce from the shipped layers. The map is still majority drainage-limited, i.e. the outcome that change was described as achieving did not occur. The share is also contingent on the reference condition the dissolution term is measured against |
| delivered cost $28 / $61 / $138 per tonne (p10/p50/p90) | **$14 / $43 / $123** | Computed while the gate cost was still $25/t; never recomputed after the cut to $10/t. The "23% above $100/t" figure derived from it is also withdrawn |
| $159/tCO₂ at the cropland median haul | **$149/tCO₂** | Did not follow from any stated $/t figure ($43/t ÷ 0.289 tCO₂/t = $149) |
| median CO₂ moved from 0.32 to 0.83 tCO₂/ha/yr | **0.79** | Was never 0.83 at any point in the build history |
| our Palandri–Kharaka mixture gives Ea 46–63 kJ/mol | **61.9–69.3 over 5–25 °C** (66.0 at pH 6.5) | Wrong in the flattering direction; only the metabasalt archetype reaches the low end, and it is not the shipped default |
| Ca +0.5, Mg +0.8 to +1.6 log units vs Gudbrandsson | those stand, but the **Ca+Mg charge sum the map actually uses is +1.2** | The gate reported per-element residuals; the map uses the charge sum, which is worse than either element implies. Gate 11 now scores on the charge sum under the shipped volume weighting rather than on the paper's own fitted surface fractions |
| distribution width moves surface area ~8× | **width 4.2×; grain size 8.2×** | The 8× was the diameter effect mislabelled as the width effect |
| quarry distance is 2.0× outcrop distance | unchanged, but README said 1.9× | Simple inconsistency; 2.0 is the value in `constants.py` |
| the surface-area multiplier "has been quietly absorbing a kinetics error" and the two errors "partly cancel" | **mechanically impossible** | λ never enters the CDR chain — the model works in rate ratios, which divide a constant multiplier out exactly. The absolute level is set solely by the dissolved-fraction anchor |
| Cascade cites Bertagni & Porporato for a framework that paper does not contain | **retracted; their citation is essentially correct** | B&P Appendix C, Eq. C.1 *is* a normalised weathering-flux index (θ = 1, 60 kJ/mol, Lasaga 1984, mapped as their Fig. 3b). The claim was made while the paper was paywalled and unread. The surviving critique is narrower: Cascade implements that index while omitting the efficiency term the main text derives |

One further correction, to a claim that appeared in the README rather than here:
the "63.7% of cropland changes decile" weight-sensitivity figure was produced by
a metric that compared both settings against the *baseline's* decile edges, so
pure level changes — including transformations that alter no ranking at all —
registered as instability. On a corrected rank-based metric, lowering the
reactivity exponent to 0.77 moves **15%** of cropland area and a common exponent
on all three terms moves **~2%** rather than ~50%.

## v0 preview (July 2026)

### The changelog moved here from the map

The in-app Methods section previously narrated this history inline. It now
describes the current model only; everything below is the record of what
changed and why.

### What this does differently from Cascade

**Three-mechanism kinetics.** Cascade's index is first order in hydrogen-ion
activity, which spans 10⁴ across cropland pH 4–8 while its temperature term
spans only ~20× across 0–30 °C — so it is close to a rescaled soil-pH map.
Using the three-parallel-mechanism law of Palandri & Kharaka (2004, USGS OFR
2004-1068) compresses that to ~36×. Measured: Cascade overstates pH leverage
by 281×.

The like-for-like Cascade reproduction is retained in the pipeline as an
internal diagnostic and still backs the numbers quoted here, but it is no
longer a map layer: it answers a question about our method rather than about
where to deploy.

**An alkalinity-to-DIC efficiency term.** Fast dissolution at low pH does not
store carbon, because DIC speciation shifts toward aqueous CO₂. Cascade cites
Bertagni & Porporato (2022) as the source of its framework; that paper is
*The Carbon-Capture Efficiency of Natural Water Alkalinization* and it derives
precisely the term the index omits. Added here with zero free parameters, it
reproduces the protocols' own screening thresholds: half efficiency falls at
pH 5.08 at Isometric's mandated 4,000 µatm soil pCO₂, against their 5.20
screen.

**Protocol eligibility as a mapped layer,** from exceedance probabilities on
SoilGrids quantiles rather than a point estimate.

### The independent kinetics test, and what it found

**This test fails, and it is the most important open problem in the model.**
It also caught us conceding something to Cascade that the data does not
support.

Gudbrandsson et al. (2011) measured crystalline-basalt release rates across
pH 2–11 and 5–75 °C. That isolates the rate law in a way the field trials
cannot, since grain size and loss terms there absorb any error.

Against the pre-registered 0.5 log-unit tolerance, our Palandri–Kharaka
mixture **over-predicts**: Ca by +0.5 log units, Mg by +0.8 to +1.6. The
residuals are structured, not noisy, in two separate ways.

**By temperature**, the bias grows from +0.01 at 5 °C to +1.58 at 75 °C. That
is an activation-energy error. Gudbrandsson measure an apparent Ea for
whole-rock basalt of ~36 kJ/mol (24–54 across pH). Our mixture gives 46–63,
and Cascade uses 68.8. We previously called Cascade's 68.8 "a reasonable
number reached by an unclear route" — that concession was wrong. It is roughly
2× too high, and so is ours.

This matters geographically, because temperature sensitivity is what drives
the tropical tilt. At 36 kJ/mol a soil 20 °C warmer is 2.7× faster; at 68 it
is 6.7×. The tropics-versus-temperate contrast is about 2.5× smaller than
either formulation implies.

**By pH**, Mg over-prediction peaks at pH 4–8 (+1.4 to +2.1) and nearly
vanishes below 4 and above 8 — the signature of secondary Mg/Fe phases
precipitating near neutral pH, where they are least soluble, removing Mg from
the solution the experiment measures.

**Why an independent test was necessary.** The CO₂ layer sits ~2.3× *below*
field observations while the kinetics over-predict lab rates by 3–7×. Those
pull opposite ways, so the surface-area multiplier has been quietly absorbing
a kinetics error. Comparing against field trials alone could never have shown
that. Neither problem is corrected in the default model: recorded rather than
silently retuned, because the fix is a modelling decision that needs its own
review.

### Suitability re-anchored to gross CO₂

**The defect.** Suitability used to be a weighted geometric mean of
value-function transforms of the same three physical terms that make up CO₂
removal, with a uniform 0.02 quantisation floor applied as though it were a
physical floor. The consequence: a cell with *zero* reactivity — hence zero
carbon removed — scored `exp(ln 0.02 / 3) × 100 = 27`, not 0. The floor
existed to stop 8-bit quantisation swinging the score; it should never have
manufactured suitability where the physics says none. 3.5% of cropland area
was affected.

**The fix.** Suitability is now a value function *of* gross CO₂ removal, on
absolute breakpoints in tCO₂/ha/yr, so zero removal is zero suitability by
construction rather than by tuning a floor. That also removed three sets of
arbitrary per-term breakpoints and replaced them with one set on a quantity
that has units and can be argued about.

**Why the sliders changed meaning.** They are now exponents on a physical
product, defaulting to 1. The old scheme was wrong in kind: it let excellent
alkalinity retention partly offset zero reactivity, when both are required
multiplicatively for any carbon to be stored. You cannot prefer dissolution
rate over alkalinity retention. Weights become meaningful again once genuinely
substitutable economic factors exist — delivered feedstock cost, MRV cost —
because those *are* tradeable.

**A second defect found while fixing the first.** The dissolved fraction was
hard-clipped at 0.6, which pinned 18.9% of cropland area at an identical CO₂
value — a flat top across a fifth of the map. It is now a first-order decay,
`1 − exp(−k·X)`, bounded by 1 for the right reason: you cannot dissolve more
rock than you applied. The reference dissolved fraction is anchored to the
midpoint of observation (first-period fraction weathered across the verified
deliveries spans roughly 15–56%), which also means our own 20% cap constant
was falsified by the data.

### Monthly soil temperature and moisture

Both stand-ins are gone. Soil temperature is Lembrechts et al. (2022) at
5–15 cm, natively 30 arc-second and monthly — the deeper layer because
Isometric's near-field zone is the deeper of 20 cm or tillage depth plus
5–10 cm. Moisture is a ten-year TerraClimate root-zone climatology.

The rate is now computed **each month and the rate averaged**, never the
drivers. Two reasons: the rate is convex in temperature, so the mean of the
rate exceeds the rate at the mean (Jensen); and weathering needs warm *and*
wet simultaneously, which annual means destroy.

**The effect is real but smaller than we predicted, and we were wrong about
the size.** Literature estimates based on air-temperature amplitude suggested
~1.4×. Measured here: median 1.04, range 0.89–1.33. Soil temperature at
5–15 cm is strongly damped relative to air, so the Jensen term is much weaker
than an air-based estimate implies — and the covariance term pulls the other
way in places, partly cancelling it.

It is spatially structured as the mechanism predicts: Mediterranean climates
come out *below* 1 (Andalusia 0.85, Central Valley 0.93), where annual means
flatter a site whose warm and wet seasons never coincide; monsoon and
continental cropland come out above (Punjab 1.19, Iowa 1.18); the wet tropics
sit at ~1, having little seasonality to lose.

### Feedstock and delivered cost

The largest gap versus a deployment tool, and it needed two constructs rather
than one. Lithology is *not* delivered cost: basalt under a field is
irrelevant if nobody quarries it within haul range. But usable quarry
inventories are very uneven — USGS MRDS is the only large open one, it is
reliable mainly for the United States, and USGS stopped systematic updates in
2011 while itself counting 3,531 operating US crushed-stone quarries in 2023.

So the map carries both: globally, distance to mafic outcrop from
full-resolution GLiM (1.24 million polygons, 93,220 of them basic igneous),
which is an **upper bound** since outcrop is not a quarry; and where MRDS is
usable, distance to a mafic-hosted quarry, which is what actually sets cost.
Having both in one region lets us **measure** the gap instead of asserting a
caveat: quarry distance is 2.0× outcrop distance there, and that measured
ratio is what scales the outcrop bound elsewhere.

**Truck only.** Basalt is rarely railed for ERW today, and even where rail
exists there is still a first- and last-mile trucking leg, so a rail rate
would flatter how this material actually moves. Gate cost plus truck at
$0.12/t-km over 1.35× great-circle distance gives $28 / $61 / $138 per tonne
at the 10th/50th/90th percentile of cropland. About 23% of cropland area sits
above $100/t and 3.5% above $200/t.

**This reverses an earlier change, and the earlier reasoning was bad.** A rail
mode was added because a truck-only median of $252/t "looked implausible". Two
errors: that $252 was the median over *all land*, not cropland — cropland sits
far closer to quarries, and its truck-only median is $61/t, which was always
plausible. And having misread the number, the response was to add a mechanism
that made the output look better rather than to find out why it looked odd.
When a number looks wrong, diagnose before changing the model.

**The penalty applies to the haul increment only.** A site sitting at the gate
cost takes no penalty at all, because you have to buy and crush rock wherever
you are — charging a site for that is charging it for something unavoidable
that carries no spatial information. From there the multiplier declines as
`1/(1 + (cost − gate)/S)` with S = $100/t, so the half-penalty point is
$125/t delivered.

**The gate cost was revised down from $25/t to $10/t, because the old figure
priced the wrong product.** ERW does not buy graded construction aggregate; it
buys quarry *fines* — crusher dust and screenings — which are the cheapest
class a quarry makes and in many markets an unsold byproduct it stockpiles.
The old $25 started from the USGS blended crushed-stone unit value (~$15–18/t,
averaged across all graded products) and then reasoned *upward* for finer
grinding. Both halves were wrong: fines sit below that average, not above it,
and ERW target sizes largely overlap what fines already deliver, so little
extra grinding is needed. Operators report ~$12/t (Lithos), <$10/t
(Isometric's own figure), ~$10/t (InPlanet); Brazilian pó de pedra runs
$8–10/t and Indian raw crusher dust as little as $2–3/t. UNDO, Mati and
Silicate all supply free, so the floor genuinely reaches $0.

Because the penalty applies to the haul increment only, the gate cost
*cancels out of the multiplier* — so this correction changed the reported $/t
and $/tCO₂, which were overstated, without perturbing the map at all.

The haul multiplier replaced five hand-placed breakpoints which, while also
1.0 at the gate, ramped hard enough that a cell at the *cropland median* haul
lost 38%. It now loses 27%. One stated parameter instead of five, and S is an
editorial choice rather than a derived one — which is why the readout also
reports feedstock cost per tonne of CO₂, so the trade-off can be judged in
units that mean something. At the gate that is $35/tCO₂ gross; at the cropland median haul, **$149**
($43/t divided by 0.289 tCO₂/t). *(The $159 originally recorded here did not
follow from any stated $/t figure.)*

Cost is the first genuinely *tradeable* factor here, so unlike the physical
terms it is compensatory with a floor — it discounts the score without zeroing
it. It is off by default: the landing map is a statement about physical
potential. Turning it on takes the area-weighted score from 0.48 to 0.35.

### Drainage: real recharge, and a wrong Damköhler coefficient

Transport limitation previously used a fixed runoff coefficient on
precipitation, giving a median η of 0.32 almost everywhere. It now uses
WaterGAP2-2e groundwater recharge — the water that actually percolates below
the root zone carrying bicarbonate, rather than overland flow, and which
includes simulated irrigation return flow. Separately, the default D_w was
0.5 m/yr, *above* Maher & Chamberlain's stated global maximum of 0.3, with a
sensitivity range almost entirely outside the published one; it is now 0.03
with a 0.001–0.3 range. Because η = q/(q+D_w), both errors suppressed η, and
they partly cancelled. Median η is now 0.71 with real spread (0.21–0.88), and
drainage limits 19.5% of cropland area instead of nearly all of it —
reactivity now limits 74.6%, which is the physically expected answer for a
weathering map.

### Rice paddies mapped

Soil pCO₂ is interpolated continuously from a flooded fraction of cell-time,
built from two independent halves: GRPI Landsat inundation months, and SPAM
irrigated-rice sub-cell area. Multiplying them is deliberately conservative —
it refuses to treat a cell that is 5% paddy as fully flooded, which would
inflate the very paddy prediction this project needs to test.

### The CO₂ gap narrowed without being tuned

Verified deliveries imply roughly 1.9 tCO₂/ha at 20 t/ha. This build's median
moved from 0.32 to 0.83 as the physics improved and the artificial clip came
off. The remaining ~2.3× gap is reported, not fitted away: closing it honestly
needs per-delivery particle-size distributions we do not have.

### The marginal SOC class was dropped

The SOC > 5 wt% screen turns out to be close to a non-constraint on cropland:
only 0.04% of cropland area is confidently excluded, and 96% of the cells
flagged worldwide sit north of 50°N — high SOC is a peatland and boreal-forest
phenomenon, not a farmland one. An earlier version also drew a *marginal*
class wherever the exceedance probability fell between 0.1 and 0.9. That
covered 53% of cropland, which made it the visual centre of the map while
saying almost nothing a developer could act on, so it is now reported in
Methods rather than drawn. The 53% is mostly a statement about how wide
SoilGrids' predictive intervals are: on a point estimate the same figure is
~0.2%.

### UI simplification (this pass)

The sidebar dropped from ~550 words to ~120: design-rationale paragraphs moved
into Methods or this file, the term-exponent sliders and grind-width slider
moved under a collapsed Advanced section, and the Randomise button was
removed. The hover readout dropped from 12 rows to 5–6 (suitability, gross
CO₂ with units, year-1 weathering, limiting factor, soil pH, and delivered
cost when economics is on) and can be pinned with a click. The three raw term
values (dissolution ×, alkalinity retained, drainage) left the readout: they
are directional rather than meaningful as numbers, and the Limiting factor
layer carries that signal. Methods was rewritten from a development narrative
into a description of the current model, and this changelog took the
narrative. One naming fix: "Fraction weathered", "Dissolved this year" and
"% weathered in year 1" were three names for the same quantity; it is
"Weathered in year 1" everywhere now.

The "Beyond supported resolution" banner no longer sits on screen across
~90% of the zoom range (it appeared as soon as a data cell spanned one
screen pixel, ~4× zoom, while the cap is 40×). It now flashes for ~2 s only
when a zoom-in is refused at the cap — the moment the message answers a real
question — and states the grid spacing.

The readout header now names the region under the cursor ("Iowa, United
States") instead of bare coordinates: Natural Earth 10m admin-1 rasterised
onto the analysis grid at build time (`scripts/build_admin_lookup.py`,
~350 KB total), with a ≤3-cell nearest-region fill so coarse-grid coastal
cells inherit the adjacent region rather than showing nothing.
