# ERW Atlas

A global gridded map of enhanced rock weathering (ERW) deployment potential on
croplands: where the chemistry works, where crushed basalt can actually be
delivered, and where a project would be creditable under the current carbon
protocols.

**Status: v0 preview — the map runs on real global data.**

```bash
./scripts/fetch_v0.sh      # ~25 MB of inputs, server-side resampled
python3 scripts/build_v0.py
./scripts/serve.sh         # http://localhost:8000/index.html
```

The interactive map has three layers — a suitability composite, a limiting-factor
view, and Cascade's published formulation on the same inputs for a like-for-like
comparison — plus live weight sliders that recolour ~5 million cells in a WebGL2
fragment shader with no fetch and no server. Hovering any cell reports every
input value, the composite score, the limiting factor, and which protocol screens
it fails. The whole deployable site is 4.8 MB.

**Read the in-app Methods panel before drawing conclusions.** Four inputs in v0
are documented stand-ins and one whole dimension — feedstock supply and delivered
haul cost — is not built yet. The most consequential known problems are listed
under "Honest status of v0" below.

> **Resolution, stated honestly.** v0 runs on a **0.1° grid (~11 km at the
> equator)**; the 1 km target belongs to the full build. Either way, grid spacing
> is not resolution — effective resolution will be roughly 10–50 km because the
> feedstock component is limited by quarry-inventory completeness rather than by
> pixel size. Nothing below ~1 km² (100 ha) should be read as site-specific, and
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
roughly 2× too high — and so is our own Palandri–Kharaka mixture, at 46–63 kJ/mol.

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
— excluded, marginal, passes — from exceedance probabilities, rather than as a
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

**1. Fraction weathered is not a site property — it falls with application rate.**
Within a single regime the relationship is perfectly monotonic across four
deliveries, and across all eight it fits `fw ~ rate^-0.58` (R² 0.48, n = 8). This
is the self-limiting behaviour you would expect as soil pH rises and alkalinity
export becomes drainage-limited rather than kinetically limited. **Design
consequence:** the map must never present fraction weathered as a suitability
metric, and any cross-site comparison of it has to hold application rate fixed.

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
ordering, putting acidic paddy first at 64% against the Corn Belt's 18%. That is
**not** support for the model either: because the two variables are identical here,
"normalising for grain size" and "removing the regime effect" are the same
operation, and the reversal only reveals which variable the variance was attributed
to.

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
| Drainage was a fixed 0.35 runoff coefficient on precipitation, giving η ≈ 0.32 almost everywhere | **WaterGAP2-2e groundwater recharge** — the water percolating below the root zone, with simulated irrigation return flow. Median η 0.71 with real spread 0.21–0.88 |
| `D_w` defaulted to 0.5 m/yr with a 0.1–2.0 range | **0.03 m/yr, range 0.001–0.3.** The old default was *above* Maher & Chamberlain's stated global maximum, and the range sat almost entirely outside the published one. Both errors suppressed η and partly cancelled |
| Drainage limited nearly all cropland | Drainage limits **19.5%**; reactivity limits **74.6%**, the physically expected answer for a weathering map |
| No paddy mask, so the headline paddy prediction could not appear at all | **Soil pCO₂ interpolated continuously** from flooded fraction of cell-time: GRPI Landsat inundation months × SPAM irrigated-rice sub-cell area. 7.6% of cropland area has >5% flooded cell-time |
| Surface area buried in a hardcoded `0.22` | **Two grind sliders** (d80, Rosin–Rammler width). Rate is linear in reactive area and L1 is a log ratio, so grind is a uniform shift — the value function moved into the shader to make it live |
| CO₂ layer ~6× below verified deliveries | **~2.3× below** (median 0.83 vs field-implied ~1.9 tCO₂/ha/yr), and it moved without any tuning — better physics, then removing the clip |

The λ readout is the useful diagnostic to watch: at the reference 267 µm grind,
matching a BET-scale area of 1–5 m²/g would demand a roughness multiplier of
roughly 39–196, straddling the top of the plausible 1–100 range. That is the
dominant uncertainty made visible rather than buried.

One number corrected downward in the process: distribution width moves surface
area by about **8×** over the slider range, not the 33× quoted earlier. The larger
figure assumes an untruncated fine tail; with a physical 1 µm floor it is smaller.

### Feedstock and delivered cost

Built from full-resolution GLiM (93,220 basic-igneous polygons) plus USGS MRDS
operating stone producers cross-filtered against that lithology, since MRDS has no
basalt commodity code. Two constructs, because quarry inventories are uneven:
globally an outcrop-distance **upper bound**, and where MRDS is usable the
quarry distance that actually sets cost. Inside the trusted area quarry distance
is **2.0× outcrop distance**, and that *measured* ratio scales the bound elsewhere.

A truck-only haul model gave a $252/t median — an artefact that would make ERW
uneconomic everywhere. Bulk minerals move by rail; taking the cheaper of truck and
rail-plus-transload gives **$28/$46/$65 per tonne** at p10/p50/p90 of cropland, and
**no cropland in the worst cost bracket**. With rail, basalt is within economic
reach of most cropland.

Cost is compensatory with a floor, not annihilating: expensive rock is bad, not
impossible. It is the first genuinely tradeable factor, so its slider is a real
preference rather than a what-if.

### Monthly soil temperature and moisture

Both stand-ins are gone: Lembrechts et al. (2022) soil temperature at 5–15 cm,
natively 30 arc-second and monthly, plus a ten-year TerraClimate root-zone
moisture climatology. The rate is computed **each month and the rate averaged**,
never the drivers.

**We were wrong about the size of the effect.** Air-temperature-based literature
estimates suggested ~1.4×; measured here it is median **1.04**, range 0.89–1.33.
Soil temperature at 5–15 cm is strongly damped relative to air, so the Jensen term
is much weaker than an air-based estimate implies, and the covariance term pulls
the other way in places.

It is spatially structured as the mechanism predicts, which is the real check:
Mediterranean cropland comes out *below* 1 (Andalusia 0.85, Central Valley 0.93),
where annual means flatter a site whose warm and wet seasons never coincide;
monsoon and continental come out above (Punjab 1.19, Iowa 1.18); the wet tropics
sit at ~1.

### Still not fixed

| Problem | Effect |
|---|---|


| **~53% of cropland is "marginal" on the SOC screen** | Down from 73% once the probability was computed at ~2.8 km and the *probability* averaged rather than the quantiles. The remainder is genuine: SoilGrids' predictive intervals are wide. Still a screening likelihood, not a calibrated eligibility probability, because the quantiles describe a block average and the threshold applies to a field |
| **Grid is 0.1° (~11 km), not 1 km** | The header says so. Effective resolution is coarser again |
| **Gudbrandsson kinetics test now runs, and FAILS** | See below. The rate law over-predicts measured basalt Ca and Mg release, with structured residuals. This is the most important open problem in the model |

Weight sensitivity is not hidden: moving reactivity from equal weighting to 77%
changes the decile of **63.7% of cropland area**. The sidebar reports that number
live, because a suitability map whose ranking is that weight-contingent should say
so rather than present one weighting as the answer.

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

**Why this had to be an independent test.** The CO₂ layer currently sits ~2.3×
*below* field observations while the kinetics over-predict lab rates by 3–7×.
Those errors pull in opposite directions, so they partly cancel — meaning the
surface-area multiplier has been quietly absorbing a kinetics error. Comparing to
field trials alone could never have revealed that.

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

Four layers are practically Earth Engine only: cropland fraction (ESA
WorldCover is 10 m and 124 GB globally, so local aggregation is not viable),
soil moisture (the 1 km global archive is 779 GB with no published climatology),
the Weiss et al. friction surface (no anonymous HTTP endpoint), and GSHTD. The
Earth Engine scripts are committed, but **the pipeline cannot run end to end
from a bare clone without a free GEE account.** Coarser local fallbacks (ESA
CCI-LC 300 m, ERA5-Land) exist and double as ensemble members.

Raw source data is downloaded, derived from, and deleted; only small derived
products are kept, sufficient to regenerate every figure without re-downloading.

## Sanity gates

Thresholds are set before the pipeline runs, and violations are published even
if we release anyway. Current status:

`python3 scripts/test_kinetics.py` — 11 gates, all passing:

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
