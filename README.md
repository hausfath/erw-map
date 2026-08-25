# ERW Atlas

A global gridded map of enhanced rock weathering (ERW) deployment potential on
croplands: where the chemistry works, where crushed basalt can actually be
delivered, and where a project would be creditable under the current carbon
protocols.

**Status: v0 preview — the map runs on real global data.**

```bash
./scripts/fetch_v0.sh      # ~25 MB of inputs, server-side resampled
python3 scripts/build_v0.py
python3 scripts/build_admin_lookup.py   # optional: region names for the hover readout
./scripts/serve.sh         # http://localhost:8000/index.html
```

The interactive map has three layers, plus live sliders that recolour ~5 million
cells in a WebGL2 fragment shader with no fetch and no server:

- **Suitability** — a value function of gross CO₂ removal on absolute breakpoints
  in tCO₂/ha/yr, so zero removal is zero suitability by construction.
- **Limiting factor** — which of the three physical terms costs the most at each
  cell.
- **Weathered in year 1** — the share of applied rock predicted to weather in year
  one, on its own colour ramp because it is a different kind of quantity: a
  physical prediction with an observable counterpart, and therefore the layer the
  field deliveries can actually check.

Hovering any cell reports the suitability score, gross CO₂ removal, year-1
weathering, limiting factor, soil pH, what is grown there, delivered cost when
economics is on, and any protocol screen it fails; click to pin the readout. The
whole deployable site is 6.3 MB.

Development history — what changed between preview builds, the defects found on
the way, and why each call was made — lives in [CHANGELOG.md](CHANGELOG.md).

**For the equations**, `scripts/analysis/make_methods_report.py` generates a
~10-page methodology PDF covering every process in the chain: the three-mechanism
rate law, the Rosin–Rammler surface-area integral, shrinking-core dissolution, the
transport term, alkalinity-to-DIC efficiency, the carbonate-saturation ceiling,
stoichiometry, the suitability value function, delivered cost and the discounted
$/tCO₂ screen, and the eligibility exceedance probability. Every model parameter
and distributional statistic in it is injected from `constants.py` and the built
grid, so it cannot drift from the code. The `.tex` is committed; run the script to
build the PDF (PDFs are gitignored).

A like-for-like reproduction of Cascade's published formulation is retained in the
pipeline and still backs the comparison numbers quoted below, but it is no longer a
map layer: it answers a question about our method rather than about where to
deploy.

**Read the in-app Methods panel before drawing conclusions.** Two inputs in v0 are
documented stand-ins and the kinetics fail their independent test. The most
consequential known problems are listed under "Honest status of v0" below.

> **Resolution, stated honestly.** v0 runs on a **0.1° grid (~11 km at the
> equator)**; the 1 km target belongs to the full build. Either way, grid spacing
> is not resolution — effective resolution will be roughly 10–50 km because the
> feedstock component is limited by the resolution of mapped mafic lithology rather
> than by pixel size. Nothing below ~1 km² (100 ha) should be read as site-specific, and
> the map caps zoom on purpose rather than inviting you to look up your field.

## What this adds to the state of the art

The starting point is Cascade Climate's [Weathering Potential
Explorer](https://cascadeclimate.org/blog/weathering-potential-explorer), which
is the right foundation and is admirably explicit about what it leaves out. This
project changes four things.

**1. Feedstock and delivered cost.** Cascade states plainly that it carries "no
information on rock type, mineral composition, or proximity to quarries or
mines," and that "it is the economic and operational conditions, rather than
weathering potential alone, that determine whether ERW is viable." A map that
recommends deployment areas has to include them.

**2. Three-mechanism dissolution kinetics.** Cascade's index is first order in
hydrogen-ion activity. Across cropland pH 4–8 that spans 10⁴, while its
Arrhenius term spans only ~20× across 0–30 °C, so the index is ~500× more
sensitive to pH than to temperature — effectively a rescaled soil-pH map. Using
the standard three-parallel-mechanism law from [Palandri & Kharaka
2004](https://pubs.usgs.gov/of/2004/1068/) compresses that pH leverage to ~36×,
comparable to the temperature range. Measured in `scripts/test_kinetics.py`:
Cascade's form overstates pH leverage by **281×**.

**Correction to an earlier version of this README.** We previously conceded that
Cascade's activation energy of 68.8 kJ/mol was "a reasonable number for
whole-basalt Ca+Mg release, reached by an unclear route." That concession was
wrong, and the independent kinetics test below is what caught it. Gudbrandsson et
al. (2011) *measure* an apparent activation energy for whole-rock crystalline
basalt of **~36 kJ/mol** (range 24–54 across pH). Cascade's 68.8 is therefore
roughly 2× too high — and so is our own Palandri–Kharaka mixture, at 62–69 kJ/mol
over 5–25 °C (an earlier version of this line said 46–63, which was wrong in the
flattering direction: only the metabasalt archetype reaches the low end).

That matters geographically, because temperature sensitivity is what drives the
tropical tilt: at 36 kJ/mol a soil 20 °C warmer is 2.7× faster, at 68 kJ/mol it is
6.7×. **The tropics-versus-temperate contrast is about 2.5× smaller than either
formulation implies.** Not yet corrected in the default model — recorded rather
than silently retuned, because the fix needs its own review.

**3. The alkalinity-to-DIC efficiency term.** Fast dissolution at low pH does
not produce carbon removal, because DIC speciation shifts toward aqueous CO₂
rather than bicarbonate. Cascade cites Bertagni & Porporato (2022) as the source
of their framework — but that paper is *The Carbon-Capture Efficiency of Natural
Water Alkalinization*, and it defines exactly the efficiency term their index
omits. Adding it, with zero free parameters, **derives the protocols' own
screening thresholds** rather than imposing a penalty:

| Soil pCO₂ | Source | pH at half efficiency |
|---|---|---|
| 4,000 µatm | Isometric v1.2, mandated for unsaturated cropping | **5.08** (vs their 5.20 screening threshold) |
| 50,000 µatm | Isometric v1.2, mandated for saturated systems | **4.53** (why paddies tolerate more acidity) |

The largest modelled consequence is that rice paddies move from mid-pack to
top-ranked, which Cascade's formulation cannot see because soil pCO₂ is absent
from it. **That prediction is not yet supported by observation, and is mildly
challenged** — see "What the verified deliveries say" below. It is recorded as a
pre-registered concern rather than presented as a result.

The verification also closed a caveat: η_DIC was derived from B&P's definition
rather than transcribed, so it needed checking against the paper. It now
reproduces their Appendix A structure exactly, and independently reproduces their
stated (and non-obvious) result that efficiency decays to ≈0.5 above pK₂ as
bicarbonate gives way to carbonate — 0.5003 at pH 13, which falls out of the K₂
term rather than being built in.

**4. Protocol eligibility as a mapped layer.** Soil organic carbon above 5 wt%
excludes a site from crediting (Puro.earth ERW 2025 rule 3.9.1c), and the
gridded inputs have real uncertainty, so eligibility is rendered as three states
— from exceedance probabilities on SoilGrids quantiles, rather than as a
binary mask on a point estimate.

## What the verified deliveries say

Eight independently verified basalt deliveries from the 2026 reporting round,
across three soil and climate regimes, were analysed with
`scripts/analyse_deployments.py`.

**The input data is not in this repository.** It derives from an independent
verification report and its cross-operator comparison, and carries per-operator
results that are not ours to publish. The script is here and exits with the
expected CSV schema if the fixture is absent, so the method stays reviewable even
though the inputs are not redistributed. Only aggregate findings appear below.

**1. Fraction weathered is not a site property.** Across all eight deliveries it
fits `fw ~ rate^-0.58` (R² 0.48, n = 8), which looks like the self-limiting
behaviour you would expect as soil pH rises and export becomes drainage-limited.

**That exponent is not a rate effect, and treating it as one was an error.**
Application rate, grind and operator are mutually collinear in this dataset:
corr(ln rate, ln p50) = **+0.60**, because the operators who apply high rates also
grind coarse. The **within-operator** slope — same feedstock, same grind — is
**−0.01 ± 0.57**, indistinguishable from zero. Grind is perfectly nested in
operator, so the independent cluster count is **4**, not 8.

So −0.58 is the operator/grind contrast wearing a rate label. That matters because
`analyse_deployments.py` used it to "normalise to a common application rate",
which removed the grind contrast a second time through a coefficient that *is* the
grind contrast — see finding 3, whose ordering reversal is withdrawn as an artefact
of that double-removal rather than merely hedged.

**Design consequence, which survives intact:** the map must never present fraction
weathered as a suitability metric, and any cross-site comparison has to hold both
application rate **and** grind fixed.

**2. Real delivered basalt is less CO₂-dense than a fresh-basalt idealisation.**
Averaged over the deliveries carrying an independent CDR measurement, implied CO₂
potential is **0.289 tCO₂ per tonne of rock**. A `delivered_basalt` archetype
anchored to that is now the default; a textbook fresh basalt would have been 14%
optimistic, and the nominal 0.33 tCO₂/t commonly applied overstates by 20–25%.

**3. The regime comparison is unidentifiable, and an earlier claim here is
retracted.** This README previously said the deliveries "mildly challenge" the
paddy prediction, because after adjusting for application rate the tropical-Oxisol
regime came out ahead of the acidic-paddy one. Measured p50 values are now in hand,
and that claim was an over-read.

Grain size is **perfectly collinear with regime**: every Corn Belt row is 67 µm,
every paddy row is 600 µm, the single Brazil row is 120 µm. Regime and grain size
are the *same variable* in this dataset, so no analysis can separate them. That is
stronger than low power — the comparison is unidentifiable. And the confound is
large: 9× in diameter, roughly 8× in surface area, against a rate-adjusted regime
spread of only 3.35×.

Normalising to a common grind (inverting through `Fw = 1 − exp(−kX)`, since scaling
fraction weathered directly produced a physically impossible 106%) *reverses* the
ordering, putting acidic paddy first at 64% against the Corn Belt's 18%. **That
reversal is now withdrawn entirely.** It is not merely uninformative — it is an
artefact. The normalisation used the −0.58 rate exponent from finding 1, which is
itself the grind contrast, so the procedure removed one degree of freedom twice.
Rate, grind and regime are three labels for one variable here, and no
rearrangement of them recovers a regime effect.

What it establishes is narrower and more useful: **these deliveries are
uninformative about regime, not contrary to it.**

Making it identifiable needs two grinds within one regime, or one grind across two
regimes — a single site running coarse and fine lots side by side would do it.

The cleanest experiment that *would* test the mechanism is a flooded-versus-drained
pair at one site with the same feedstock and application rate.

## Honest status of v0

What is real: the kinetics, the efficiency term, the eligibility probabilities,
the cropland mask and the area weighting. Global cropland reproduces Potapov et
al. (2022) to within 0.1% (1.215 vs 1.216 Gha), which validates the area pipeline
independently of any ERW science.

### Suitability is anchored to gross CO₂

Suitability used to be a weighted geometric mean of value-function transforms of
the same three physical terms that make up CO₂ removal, with a uniform 0.02
quantisation floor treated as a physical floor. A cell with **zero** reactivity —
zero carbon removed — scored `exp(ln 0.02 / 3) × 100 = 27`. That affected 3.5% of
cropland area, and the two layers correlated at 0.943 in log space, so the
composite was carrying almost no information the CO₂ layer did not already have.

Suitability is now a value function **of** gross CO₂, on absolute breakpoints in
tCO₂/ha/yr. Zero removal gives zero suitability by construction. Verified in the
browser: all 17,818 negligible-CO₂ cells read exactly 0.

The sliders changed meaning as a result. They are **exponents on a physical
product**, defaulting to 1. The old scheme was wrong in kind — it let good
alkalinity retention partly offset zero reactivity, when both are required
multiplicatively. Weights become meaningful again once genuinely substitutable
economic factors exist (delivered feedstock cost, MRV cost), because those *are*
tradeable in a way the physics is not.

Fixing that surfaced a second defect: the dissolved fraction was hard-clipped at
0.6, pinning **18.9% of cropland area at one identical CO₂ value** — a flat top
across a fifth of the map. It is now first-order decay, `1 − exp(−k·X)`, bounded
by 1 because you cannot dissolve more rock than you applied. Anchoring the
reference fraction to observation (15–56% first-period across the verified
deliveries) also showed our own 20% annual-dissolution cap was falsified by data.

### Fixed earlier in this pass

| Was | Now |
|---|---|
| Drainage was a fixed 0.35 runoff coefficient on precipitation, giving η ≈ 0.32 almost everywhere | **WaterGAP2-2e total runoff** (`qtot`) via ISIMIP3a, with simulated irrigation return flow. Median η_transport **0.86**, spread 0.51–0.95, on a median drainage of **178 mm/yr**. Groundwater recharge (`qr`) was used until August 2026 and is retained as the conservative bound — see [Which water flux is q?](#which-water-flux-is-q) |
| `D_w` defaulted to 0.5 m/yr with a 0.1–2.0 range | **0.03 m/yr, range 0.001–0.3.** The old default was *above* Maher & Chamberlain's stated global maximum, and the range sat almost entirely outside the published one. Both errors suppressed η and partly cancelled |
| Drainage limited nearly all cropland | Recomputed from the shipped layers: drainage limits **59.3%**, reactivity **34.0%**, alkalinity retention **6.7%**. The 19.5%/74.6% split previously stated here does not reproduce and has been withdrawn — the map is still majority drainage-limited, and that share is itself contingent on the reference condition the dissolution term is measured against |
| No paddy mask, so the headline paddy prediction could not appear at all | **Soil pCO₂ interpolated continuously** from flooded fraction of cell-time: GRPI Landsat inundation months × SPAM irrigated-rice sub-cell area. 7.6% of cropland area has >5% flooded cell-time |
| Surface area buried in a hardcoded `0.22` | **Two grind sliders** (d50, Rosin–Rammler width). Rate is linear in reactive area and L1 is a log ratio, so grind is a uniform shift — the value function moved into the shader to make it live |
| CO₂ layer ~6× below verified deliveries | **median 0.79 tCO₂/ha/yr** vs a field-implied ~1.9, and it moved without tuning — better physics, then removing the clip. But see the reconciliation caveat below: most of that apparent gap is the reference-condition choice, and the absolute level is now known to be unreconciled with the water flux |

The λ readout is a plausibility diagnostic, not a constraint the model is bound
by: at the reference **150 µm** grind, matching the **measured 0.703 m²/g** BET of
a real crushed basalt implies a roughness multiplier of about **27**, comfortably
inside the plausible 1–100 range. An earlier version quoted λ 39–196 against an
unsourced "BET 1–5 m²/g" anchor, which put our own default above the falsification
ceiling; that anchor was wrong, not the model. Note also that λ **does not enter
the calculation** — the map works in rate ratios, which divide a constant
multiplier out — so it cannot be read as evidence the absolute scale is
constrained.

Two numbers corrected in the process: distribution width moves surface area by
about **4.2×** over the slider range and **grain size** by about **8.2×** over the
observed 67–600 µm p50 span. The 33× figure quoted earlier assumed an untruncated
fine tail; with a physical 1 µm floor it is smaller, and the 8× was the diameter
effect mislabelled as the width effect.

### Feedstock and delivered cost

Built from full-resolution GLiM (93,220 basic-igneous polygons) plus a quarry
point inventory cross-filtered against that lithology. Two constructs, because
inventory completeness is uneven: globally an outcrop-distance **upper bound**, and
where the inventory is usable the quarry distance that actually sets cost. Inside
the trusted area quarry distance is **2.0× outcrop distance**, and that *measured*
ratio scales the bound elsewhere.

The inventory is **5,295 mafic-hosted quarries** from three sources of differing
standing. **USGS MRDS** (1,829) is the US national register, with no basalt
commodity code, so producers are cross-filtered against lithology. **ANM SIGMINE**
(1,681) is Brazil's mining-title register, queried over its ArcGIS REST endpoint;
it carries an explicit substance field, so basalt, diabase and gabbro are selected
directly rather than inferred, and a phase field, so only extraction-authorised
titles are kept. They concentrate in Rio Grande do Sul, Paraná, Santa Catarina and
São Paulo, which is the Paraná flood-basalt province and a good sanity check.
**OpenStreetMap** (1,785) is crowd-sourced and the only global option.

Three limits on this, stated because they all push the same way:

- **A title is not a producing quarry.** ANM titles are legal boundaries and OSM
  `landuse=quarry` includes disused pits. Both overstate active supply — in the same
  direction as the outcrop bound they replace, just less so. MRDS is worse on
  currency: it stopped systematic updates in 2011.
- **India has no authoritative source and is the real gap.** GSI Bhukosh timed out,
  the National Geoscience Data Repository returned 403, and no state portal yielded
  coordinates, so India's 934 mask quarries are OSM-only. That matters because it is
  an active deployment geography.
- **The OSM pull is an undercount.** The public Overpass endpoint throttles hard:
  50 of 106 tiles still failed after retries with backoff. Retrying lifted the raw
  pull from 14,259 to 18,467 points (+30%, and +59% for India), but the residual
  failures are reported rather than allowed to silently shrink the inventory. A
  Geofabrik plus osmium pass would remove the throttling entirely and is the next
  step.

Worth knowing how little of that inventory growth reaches the map: the +30% in raw
points added only ~107 quarries to the mask and moved the area-weighted median
delivered cost from $45/t to $43/t. The binding filter is the mafic-lithology
intersection, not the inventory size — only **24.8%** of stone producers sit on
GLiM-mapped basic igneous rock. Inventory completeness is therefore not currently
the limiting uncertainty in the cost surface; lithology resolution is.

Haul is **truck only**: basalt is rarely railed for ERW today, and even where rail
exists there is still a first- and last-mile trucking leg.

**Trucking is priced regionally, with a fixed per-trip charge** (August 2026 —
research in [`docs/TRUCK_RATE_SOURCES.md`](docs/TRUCK_RATE_SOURCES.md)):
`cost = gate + r(region) × (road km + 50 km)`, with r from USDA grain-truck rates
for the US/Canada ($0.10/t-km), NITI Aayog for India/South Asia ($0.045), and
World Bank corridor prices for Brazil/Latin America ($0.055), China/SE Asia
($0.07), Europe ($0.09) and Africa ($0.11); $0.08 elsewhere. Only the US entry is
a current primary; the others carry 2007–2021 vintages, flagged per entry in
`constants.py`. The 50 km is the fixed trip charge — the hauler's loading,
tipping and positioning time — decomposed from the USDA distance curve (implied
F/r of 37–72 km) and expressed as a km-equivalent because trip *time* is
universal while its *price* follows the local rate: $5.00/t in the US, $2.25 in
India, $5.50 in Africa.

This replaced a single global $0.12/t-km — a genuinely good US number that was
~2–2.5× too high for Brazil and India, the two most active ERW deployment
countries. Because the gate cancels out of the cost multiplier, the truck rate is
the only cost parameter doing spatial work, so that bias mapped straight into
suitability-with-cost and penalised exactly the cropland the physics favours.
Cropland median delivered cost is now **$34/t** (p10 $16, p90 $100), against
$43/123 under the old model.

Both cost assumptions are live under **Advanced**: a haul-rate multiplier
(×0.25–2.5 on the regional baselines, fixed trip charge included; median
delivered cost runs $16/t to $70/t across it) and the gate cost ($0–25/t; the
top of the range reaches the at-scale US price). They are asymmetric and the UI
says so: the multiplier **moves the map**, while the gate **cannot**, because
the penalty applies to the haul increment only. The gate still moves the
headline economic total through the $/tCO₂ screen. `tests/cost_sliders.mjs`
asserts the live path reproduces the build exactly at the default positions,
that a zero-distance cell in every rate group reports gate + m·r·50 km, and
that the gate cannot touch the multiplier.

**The gate cost was revised down from $25/t to $10/t, because the old figure priced
the wrong product.** ERW does not buy graded construction aggregate; it buys quarry
*fines* — crusher dust and screenings — the cheapest class a quarry makes and in
many markets an unsold byproduct. The old $25 started from the USGS blended
crushed-stone unit value (~$15–18/t across all graded products) and reasoned
*upward* for grinding. Both halves were wrong: fines sit below that average, and
ERW target sizes largely overlap what fines already deliver. Reported prices:
~$12/t (Lithos), <$10/t (Isometric's own figure), ~$10/t (InPlanet), $8–10/t for
Brazilian pó de pedra, $2–3/t for Indian raw crusher dust. UNDO, Mati and Silicate
all supply free, so the floor genuinely reaches $0.

Because the penalty applies to the haul increment only, the gate cost **cancels out
of the multiplier** — this correction fixes reported $/t and $/tCO₂, which were
overstated, without perturbing the map.

**This reverses an earlier change, and the earlier reasoning was bad.** A rail mode
was added because a truck-only median of $252/t "looked implausible". Two errors:
that $252 was the median over *all land*, not cropland — cropland sits far closer
to quarries, and its truck-only median was $43/t under that model, which was
always plausible. And
having misread the number, the response was to add a mechanism that made the output
look better rather than to find out why it looked odd. The standing rule applies:
when a number looks wrong, diagnose before changing the model.

**The penalty applies to the haul increment only.** The gate cost cancels — you
must buy and crush rock wherever you are, so it carries no spatial information —
and the multiplier declines as `1/(1 + (cost − gate)/S)` with S = $100/t, putting
the half-penalty point at $125/t delivered. Since the fixed trip charge was
added, the increment is `r·(d + 50 km) > 0` everywhere, so the multiplier peaks
at 0.948–0.978 (regionally, at zero distance) rather than 1: even a farm beside
the quarry pays for the truck's loading and tipping time. This form replaced
five hand-placed breakpoints that ramped hard enough for a mid-range cell to
lose 38%; the cell at today's cropland median of $34/t loses 19%.

S is an editorial choice, not a derived one, so the readout reports feedstock cost
per tonne CO₂ alongside — **$42–54/tCO₂ gross at gate-plus-trip-charge
(regionally), $118 at the cropland median** ($12.25–15.50 and $34 per tonne of
rock divided by 0.289 tCO₂/t) —
letting the trade-off be judged in units that mean something.

Cost is compensatory with a floor, not annihilating: expensive rock is bad, not
impossible. It is **on by default** as of August 2026. It used to be off, so that
the landing map was a statement about physical potential — but the unscreened map
implies 2.43 GtCO₂/yr across essentially all cropland, and almost none of that is
deployable at a price anyone would pay. Leading with the physical figure put the
less useful number in front. The toggle still switches it off, and the footer states
its basis either way.

### Monthly soil temperature and moisture

Both stand-ins are gone: Lembrechts et al. (2022) soil temperature at 5–15 cm,
natively 30 arc-second and monthly, plus a ten-year TerraClimate root-zone
moisture climatology. The rate is computed **each month and the rate averaged**,
never the drivers.

The moisture term is an **absolute degree of saturation** as of August 2026. It
used to normalise each cell by its own annual maximum, which measured seasonality
rather than wetness and scored the driest and wettest 5% of cropland identically —
see [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) §2, which also records the 10×
unit error that defect was concealing. The storage is now divided through
SoilGrids field capacity, wilting point and pore volume over 0–100 cm, and gate 2e
fails any per-cell normalisation.

**We were wrong about the size of the effect.** Air-temperature-based literature
estimates suggested ~1.4×; measured here it is area-weighted median **1.15**, p10–p90 1.01–1.34.
Soil temperature at 5–15 cm is strongly damped relative to air, so the Jensen term
is much weaker than an air-based estimate implies, and the covariance term pulls
the other way in places.

It is spatially structured as the mechanism predicts, which is the real check:
Mediterranean cropland comes out *below* 1 (Andalusia 0.85, Central Valley 0.93),
where annual means flatter a site whose warm and wet seasons never coincide;
monsoon and continental come out above (Punjab 1.19, Iowa 1.18); the wet tropics
sit at ~1.

### What is grown here

The readout names the **two largest crops** in a cell and their share of its
cropped area, from [SPAM2010
v2.0](https://doi.org/10.7910/DVN/PRFF8V) physical area. Physical, not harvested:
harvested double-counts multi-cropping, so shares would not sum to the land
actually farmed.

**Two crops rather than one, because one is a minority of the cell more often
than not.** Measured over the shipped grid, the single dominant crop holds a
median of just **46%** of a cell's cropped area, and only 41.7% of cropland area
has any crop above half:

| | p25 | **p50** | p75 |
|---|---|---|---|
| largest crop | 35% | **46%** | 60% |
| largest two | 58% | **71%** | 83% |
| largest three | 72% | **83%** | 92% |

A one-word label would read "wheat" on the North China Plain, where it means
wheat 25%, maize 23%, vegetables 16%. Two crops plus the remainder reach a median
71% and say plainly when a cell is mixed, which one label cannot. Three would
reach 83% and do not fit the encoding.

**It is context, not an input.** Crop identity feeds nothing in the model chain
except rice, and then only through the paddy soil-pCO₂ pathway. Three limitations
worth stating: SPAM is a *downscaling model* that allocates subnational statistics
onto a cropland mask, not an observation, so per-pixel crop identity carries real
uncertainty; the reference year is **2010**, which predates Brazilian soy
expansion and Corn Belt rotation shifts; and SPAM's cropped area is 79% of
Potapov cropland at the median cell, so "share of cropped area" is not the same
denominator as the cropland fraction used elsewhere in the readout.

SPAM2010 v2.0 is the latest *global* release, verified against the Harvard
Dataverse on 2026-08-06 — the SPAM2017 and MapSPAM2020 products there are
Sub-Saharan Africa only.

### Which water flux is q?

The transport term needs the water flux through the weathering zone, and
WaterGAP2-2e publishes four candidates that differ by a factor of five over
cropland (area-weighted median, mm/yr):

| variable | median | what it is |
|---|---|---|
| `qr` | 74.8 | diffuse groundwater recharge — water reaching the aquifer |
| `qsb` | 75.2 | subsurface runoff — reached the stream through the soil |
| `qs` | 83.7 | surface runoff |
| **`qtot`** | **177.8** | **total runoff = `qs` + `qsb`** |

The map used `qr` until August 2026, and it had a visible defect. `qr` is *exactly
zero* on 0.10% of cropland area, concentrated in river deltas — 23% of the Mekong
Delta's cropland area, 24% of the Red River delta, 4% of the middle Yangtze
rendered as "negligible ERW potential" in some of the wettest cropland on Earth.
In a delta the water table is at the surface, so nothing percolates to an aquifer
and WaterGAP correctly reports zero recharge; field drainage still leaves
laterally to canals, carrying its bicarbonate with it. **Zero recharge is not zero
drainage.**

`qsb` looks like the obvious fix and is not. In WaterGAP, recharge feeds the
groundwater store and that store discharges as baseflow, so over a 30-year mean
`qsb` is very nearly `qr` relabelled — global land medians 33.5 vs 32.6 mm/yr,
ratio 1.00 at the cropland median. It clears the delta zeros but introduces worse
ones where groundwater is heavily pumped: **26% of the Indo-Gangetic Plain** and 4%
of the US Corn Belt go dark, taking the global negligible class from 0.79% to
6.60% of cropland area. Trading deltas for the Indo-Gangetic Plain is a bad trade.

`qtot` is the default, for two reasons that agree. Maher & Chamberlain fit `D_w`
against the Gaillardet river dataset — catchment discharge per unit area, which
*is* `qtot` — so driving a `qtot`-calibrated `D_w` with recharge penalises the flux
twice. And it fixes the defect without creating another: the negligible class falls
to 0.10% of area, every delta clears, no region gets worse, and the
implausible-dissolution tail (>90% weathered in year one) only moves 0.63% → 0.77%
of area.

**The honest caveat**, which is why `qr` is retained as a documented sensitivity
rather than deleted: surface runoff has little contact time with topsoil rock, so
`qtot` credits water that arguably weathered nothing. The counter is that `D_w` is
an *effective* parameter fit at catchment scale, where nearly all runoff has passed
through regolith, so it already absorbs that. Treat the two as a bracket —
**2.10 (`qr`) to 2.43 (`qtot`) GtCO₂/yr** global gross, a 16% spread that the build
prints every run as gate 2d.

The change is broad, not a delta patch: +7% to +30% by latitude band, largest in
the irrigated subtropics, with the Indo-Gangetic Plain and Pakistan accounting for
the biggest absolute gains. That is exactly the case `eta_transport`'s docstring
already flagged when it said *q* must include irrigation return flow.

Gate 2c now asserts the impossibility directly: a cell receiving more than a metre
of rain a year cannot drain less than a millimetre. Run
`scripts/analysis/drainage_variable.py` to reproduce every figure above.

### Still not fixed

| Problem | Effect |
|---|---|
| **The SOC screen barely binds on cropland** | Only 0.04% of cropland area is confidently excluded (P > 0.9), and 96% of the cells flagged worldwide are north of 50°N: SOC above 5 wt% is a peatland and boreal-forest phenomenon. A *marginal* class (0.1 < P < 0.9) covering 53% of cropland was drawn in an earlier version and is now reported rather than mapped — it was the dominant visual feature of the map while saying little that was actionable, and it is largely a statement about the width of SoilGrids' predictive intervals (on a point estimate the same figure is ~0.2%). Still a screening likelihood, not a calibrated eligibility probability, because the quantiles describe a block average and the threshold applies to a field |
| **Grid is 0.1° (~11 km), not 1 km** | The header says so. Effective resolution is coarser again |
| **The drainage-concentration ceiling is now APPLIED by default (2026-08-24), and it is the binding term almost everywhere** | The ceiling (`cdr ≤ q·[HCO₃⁻]_max·44`, from calcite saturation with pH endogenous, Davies activities, Mg 1 mM explicit) was held out of the defaults 2026-08-03 → 2026-08-24 pending outside review — see [`docs/rfc_flux_reconciliation.tex`](docs/rfc_flux_reconciliation.tex). The first review arrived: Mayer et al. 2025 (doi:10.21203/rs.3.rs-7811095/v1, Terradot preprint) independently publish the same bound as "carrying capacity"; our solve reproduces their 54 PHREEQC cases to 0.95–1.00 (gate 13d) and their global integral to 6% (0.359 vs 0.34 GtCO₂/yr). With the cap on, the steady-state footer total is 0.70 GtCO₂/yr (year-1 basis 0.71, vs 2.43 uncapped), the cap binds on **95.1%** of cropland area (median exceedance of the unbounded model: **3.8×**), and it is a *maximum-efficient* bound — past it, calcite precipitation halves marginal efficiency rather than stopping removal. The top-level toggle *Apply the drainage limit* shows the uncapped historical behaviour; `constants.FLUX_CEILING_ON` governs the derived products. Caveat: the corroboration is one company-funded preprint, not yet peer-reviewed |
| **Gudbrandsson kinetics test now runs, and FAILS** | See below. The rate law over-predicts measured basalt Ca and Mg release, with structured residuals. This is the most important open problem in the model |

Weight sensitivity is not hidden: lowering the reactivity exponent from 1.00 to
0.77 moves **15% of cropland area** into a different decile, and halving it moves
**38%**. The sidebar reports this live.

The **63.7%** previously quoted here was an artefact of a broken metric: it
digitised both the perturbed and baseline settings against the *baseline's* decile
edges, so any change in level — including transformations that alter no ranking at
all — registered as instability. A common exponent on all three terms is exactly
monotone in the score and now reads ~2%, against ~50% under the old metric. The
figure also described weights summing to one, a parameterisation that no longer
exists.

## The independent kinetics test, and what it found

`tests/fixtures/gudbrandsson2011_basalt.csv` holds measured crystalline-basalt
release rates across pH 2–11 and 5–75 °C, obtained from the full paper as
reproduced in the lead author's openly-mirrored PhD thesis. Ca and Mg rates are
*our arithmetic on their measurements* — the paper tabulates concentrations and
prints a rate column only for Si — derived via their own Eq. 5 and checked by
recomputing their printed Si rates to within 0.02–0.05 log units.

This is the only test that isolates the rate law. The field trials cannot: grain
size and loss terms absorb the error.

**It fails the pre-registered 0.5 log-unit tolerance**, and the residuals are
structured rather than noisy:

| Weighting | Element | Bias | MAD |
|---|---|---|---|
| Volume fractions | Ca | +0.50 | 0.68 |
| Volume fractions | Mg | +1.58 | 1.58 |
| Their fitted surface fractions | Ca | +0.49 | 0.59 |
| Their fitted surface fractions | Mg | +0.82 | 0.92 |

Two separate problems, both diagnosable:

- **By temperature**, bias grows monotonically from +0.01 at 5 °C to +1.58 at
  75 °C. That is the activation-energy error above: our temperature sensitivity is
  roughly twice what the rock shows.
- **By pH**, Mg over-prediction peaks at pH 4–8 (+1.4 to +2.1) and nearly vanishes
  below pH 4 and above pH 8. That is the signature of secondary Mg/Fe phases
  precipitating near neutral pH, where they are least soluble, removing Mg from
  the outlet solution the experiment measures.

**Why this had to be an independent test.** The kinetics over-predict lab rates
while the CO₂ layer sits below field observations, so a field comparison alone
would have shown a model that looked roughly right in aggregate while being wrong
in its parts. Only a test that isolates the rate law can separate those.

> **Correction, 2026-07.** This paragraph used to say the two errors "pull in
> opposite directions, so they partly cancel — meaning the surface-area
> multiplier has been quietly absorbing a kinetics error." That mechanism is
> wrong. λ never enters the CDR chain: the model works in rate *ratios*
> (`L1 = log10(R/R_ref)`), which divides any constant surface-area multiplier out
> exactly. The absolute level is set solely by the dissolved-fraction anchor. The
> two errors are real and both documented, but they live in different parts of
> the model and cannot cancel.

## Two results from the July 2026 review worth stating up front

**η_DIC is independently corroborated, by a route we did not use.** Dietzen &
Rosing (2023, *IJGGC* 125, 103872, CC-BY) derive a correction factor X\* from a
soil **proton budget** — "the proportion of the weathering reactions that converted
carbonic acid to bicarbonate rather than consuming excess acidity." We compute
η_DIC from **carbonate equilibrium**, following Bertagni & Porporato. The two land
on the same function of soil pH and pCO₂, agreeing to within **0.03 at every value
they report**, across a 40× range in pCO₂:

| pH | pCO₂ | their X\* | our η_DIC |
|---|---|---|---|
| 5.79 | 1,000 µatm | 0.83 | 0.851 |
| 5.20 | 1,000 µatm | 0.25 | 0.276 |
| 6.29 | 1,000 µatm | 0.98 | 0.982 |
| 5.99 | 4,000 µatm | 0.98 | 0.983 |
| 5.49 | 40,000 µatm | 0.98 | 0.983 |

Two independent derivations from different literatures agreeing to three decimal
places is stronger evidence than either alone, and it is asserted by gate 2d. It
also means **the protocol-sanctioned strong-acid correction is already in this
model** rather than missing — and it settles a measurement-convention question that
was blocking work, since the paper states its thresholds are on pH(H₂O), the basis
SoilGrids reports, so no offset applies anywhere here.

The caveat that survives is sharper for being narrower: Holden et al. (2024)
measured a full acidity budget at a real site and found **2% of weathering was
carbonic-acid-driven** where this formulation gives ~71%. An equilibrium factor of
pH and pCO₂ evidently cannot capture continuous fertiliser loading, and that is now
the open question rather than "add a term we lack."

**Repartitioning the reacting surface cannot rescue the rate law.** Gudbrandsson's
own mixing model needed plagioclase at 83% of the reacting surface against a 44%
volume share, which made "the surface is not the volume" the leading candidate
explanation for our residuals. It has now been tested rather than assumed. The
fixture measures **four** elements (Si, Ca, Mg, Fe) while three minerals leave only
**two** free surface fractions, so the problem is over-identified — a test, not a
fit. Gate 11b:

- Fitting to Ca+Mg alone gives a respectable-looking result on what it was fitted
  to, then **held-out Fe falsifies it by 17.8 log units**, because it drives
  pyroxene to exactly zero and pyroxene is the only Fe carrier in the set.
- Fitting all four at once, with both parameters tuned directly on the test data,
  still leaves the worst element at **0.88** against a 0.5-log tolerance.
- Every partition that fits well is a boundary solution with ~0% pyroxene, for a
  rock that is 39 vol% pyroxene. Constrained to a factor of 3 of the volume share,
  Mg degrades straight back to 1.15.

So the residual is **not a mixing problem**, and the planned per-temperature
surface refit should not be run — it is aliased with the activation energy and the
pooled version of the same idea has now failed. That redirects the kinetics work
onto the rate constants themselves and onto the missing alkaline-branch mechanism.

## What it deliberately does not claim

- **No layer is called "validated."** With one fitted scaling constant and fewer
  than twenty short field trials worldwide, using different feedstocks, grain
  sizes and mutually disagreeing measurement methods, the honest claim is that
  the model is not grossly inconsistent with observation. See
  `docs/VALIDATION.md`.
- The CO₂ layer is **gross alkalinity generation potential**, not net CDR. The
  gap between them (in-soil carbonate precipitation, riverine re-release,
  strong-acid competition) is plausibly 20–80% and spatially variable.
- Specific surface area is the dominant uncertainty in that layer: geometric and
  BET values differ by 130–670× at ERW grain sizes. It is one global multiplier,
  so it sets the map's *level* and cancels in any relative comparison — which is
  why the suitability ranking is the product and the CO₂ number is an
  illustration.
- Not a site-selection tool.

## Running it

```bash
# Kinetics gates. Run these first; they gate everything downstream.
python3 scripts/test_kinetics.py

# Re-verify the kinetic constants against the primary USGS report
# (downloads the PDF, extracts the parameter rows, deletes the PDF)
./scripts/fetch_pk_tables.sh
```

Requires Python 3.13, `numpy`, `rasterio` (which bundles GDAL, so the GDAL CLI
is not needed), `pyproj`, `Pillow`, `scipy`. Building the data layers also needs
a free Google Earth Engine account — see "Reproducibility caveat" below.

## Layout

```
scripts/
  constants.py            every tunable in one place; the single source of truth
  kinetics.py             Palandri-Kharaka rate law, eta_DIC, transport limitation
  test_kinetics.py        11 pre-registered gates -- run before anything else
  analyse_deployments.py  what the verified 2026 deliveries can and cannot test
  fetch_v0.sh             v0 inputs (SoilGrids WCS, WorldClim, Potapov cropland)
  build_v0.py             layers, area gate, PNG textures, generated JS constants
  serve.sh                local HTTP server for the map
  extract_pk_fixture.py   re-extracts kinetic constants from the primary PDF
  fetch_pk_tables.sh      regenerates the test fixture from source
src/                      the deployable site (4.8 MB): index.html, app.js,
                          styles.css, generated engine_constants.js, textures/
gee/                      Earth Engine reduction scripts (stage 0, for the 1 km build)
tests/fixtures/           USGS OFR 2004-1068 extract; verified 2026 deliveries
docs/                     METHODOLOGY, KINETICS, VALIDATION, SENSITIVITY
```

`src/engine_constants.js` is **generated** by `build_v0.py` from `constants.py`,
and it carries the colour ramp that both the shader and the sidebar legend read —
so a value cannot be defined twice and drift. That is the failure mode that broke
the sibling [BiCRS Atlas](../BiCRS%20Map) in production.

`constants.py` is the single source of truth. `emit_constants.py` will generate
the browser's copy so a value cannot be defined twice and drift — a failure mode
that broke the sibling [BiCRS Atlas](../BiCRS%20Map) in production.

## Reproducibility caveat

Three layers are practically Earth Engine only: cropland fraction (ESA
WorldCover is 10 m and 124 GB globally, so local aggregation is not viable),
the Weiss et al. friction surface (no anonymous HTTP endpoint), and GSHTD.
Soil moisture came off that list in August 2026: TerraClimate's annual NetCDFs
are ~110 MB each and `fetch_monthly.py` streams ten of them, and the retention
denominator comes from the same ISRIC WCS as pH. The
Earth Engine scripts are committed, but **the pipeline cannot run end to end
from a bare clone without a free GEE account.** Coarser local fallbacks (ESA
CCI-LC 300 m, ERA5-Land) exist and double as ensemble members.

Raw source data is downloaded, derived from, and deleted; only small derived
products are kept, sufficient to regenerate every figure without re-downloading.

## Sanity gates

Thresholds are set before the pipeline runs, and violations are published even
if we release anyway. Current status:

`python3 scripts/test_kinetics.py` — **18 gates, 16 passing and 2 failing.**

Be careful how that count is read. Exactly **one** gate compares the model
against independent measurements it was not built from (gate 11, Gudbrandsson et
al. 2011), and it **fails**. One more (gate 2d) cross-checks η_DIC against a
completely independent derivation and passes — see below, it is the strongest
external check here. One more (gate 11b) is an over-identified structural test
that answers a question rather than validating a layer. A second failing gate (6c) is an internal
consistency check. Everything else is a unit conversion, a reproduction of a
published constant, a monotonicity invariant, or a code-drift assertion — all
worth having, none of them validation. Gate 7 in particular is an arithmetic
self-check: `delivered_basalt`'s oxides were chosen to reproduce the CO₂ figure
it verifies, so it tests arithmetic rather than the archetype.

| Gate | Result |
|---|---|
| Plummer & Busenberg carbonate constants at 25 °C | max deviation 0.00047 log units |
| η_DIC derives protocol pH thresholds | 5.08 vs Isometric's 5.20 |
| η_DIC high-pH asymptote vs B&P Appendix A | 0.5003 at pH 13 vs their stated ≈0.5 |
| Charge per mole vs B&P Table 1 | agrees, except Fe by design (see below) |
| pH leverage compressed vs Cascade's n=1 form | 36× vs 10,000× |
| Kinetic constants match the primary USGS report | 12/12 rows |
| Basaltic glass absent from Palandri & Kharaka | confirmed |
| Per-mineral CO₂ capacity vs Puro.earth Table 1.1 | max deviation 4.7% |
| `delivered_basalt` vs verified deliveries | 0.290 vs 0.289 tCO₂/t measured |

One gate failed on first run and was informative: a stoichiometric ceiling set
from basalt, which ultramafic legitimately exceeded. The threshold was wrong, not
the chemistry, so it was replaced with the published-value comparison above.

**One deliberate divergence from the literature.** B&P's Table 1 assigns Fe₂SiO₄
the same alkalinity yield as Mg₂SiO₄, which is correct as aqueous chemistry — Fe²⁺
release does raise alkalinity. But in oxic agricultural soil that alkalinity is
undone as the iron oxidises and precipitates (`Fe²⁺ + ¼O₂ + 5/2H₂O → Fe(OH)₃ +
2H⁺`), so no durable carbon is stored. The crediting protocols agree: Isometric
computes CO₂ potential from CaO, MgO, Na₂O and K₂O with no FeO term. Iron is
therefore excluded here, and the gate asserts the divergence is intentional rather
than silently tolerating it.

Outstanding and gating the next phase: the **Gudbrandsson et al. 2011
no-free-parameter test** of Ca and Mg release against pH at 5–25 °C. It is the
only genuinely independent test of the kinetics, separate from any field
calibration.

## License

Code MIT. Input datasets keep their own licenses and are not redistributed; see
[LICENSE](LICENSE) and `docs/METHODOLOGY.md`.
