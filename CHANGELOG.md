# Changelog

Development history of the ERW Atlas, including the defects found along the
way and the reasoning behind each reversal. The map's Methods modal describes
the model as it stands; this file describes how it got there. Newest changes
first within each build.

## Delivered-cost assumptions are sliders, and the haul rate is admitted to be a guess

Both economic assumptions are now live under Advanced: quarry gate $0–15/t and
truck haul $0.03–0.30/t-km.

**No texture change was needed, which is worth recording.** `tex3.b` stores the
finished value function `v = 1/(1 + haul/S)` rather than a distance, so at first
glance the sliders needed a new distance channel. They do not: haul is linear in
the rate, so rescaling by `k = rate/rate_baked` is exact — `v' = v/(k + v(1−k))` —
and the existing byte is a lossless encoding of haul cost. Checked before relying
on it: no cropland area sits at the value-function floor (p1 of `v_cost` is 0.296
against a floor of 0.05), so the inversion is nowhere ill-conditioned, and one
least-significant bit is worth 2–7% in recovered km, far inside the error of a
great-circle × 1.35 haul model.

**The two sliders are deliberately asymmetric, and the UI has to say so.** The
truck rate moves the map. The gate cost cannot, because `v = 1/(1 + (cost − gate)/S)`
is independent of the gate by construction — a fact `constants.py` has recorded for
months but which would make the slider look broken if left unexplained. It does move
the reported $/t and, through the $/tCO₂ screen, the headline total: 0.59 GtCO₂/yr
on 0.19 Gha at $10/t against **0.39 on 0.11 Gha** at $15/t. A $5/t gate change moves
the headline economic figure by a third while the map is pixel-identical.

**`tests/cost_sliders.mjs`** asserts the identity at the build's own rate is exact
(worst delta 0), that reported $/t at the defaults reproduces the build's
`gate + S(1/v − 1)` to 1e-9, that the gate shifts reported cost by exactly the gate
delta and cannot touch `v_cost`, that `v_cost` stays in [floor, 1] and falls
monotonically as haul gets dearer, and that the GLSL uses the same expression as the
JS.

**On the number itself: $0.12/t-km is an assumption, and a doc row overstated it.**
`docs/METHODOLOGY.md` credited it to a "US trade-association rate", which the code
has never supported — `FEEDSTOCK_COST_SOURCE` has always called it an assumption.
Corrected. There is also no cost gate in `build_v0.py`, no cost row in
`docs/VALIDATION.md`, and no comparison against the verified-delivery fixture, so
the whole delivered-cost surface is unvalidated while every physical layer has a
gate. The slider range is an exploration bracket, not a confidence interval, and
says so.

Sensitivity, measured: median delivered cost $18/t at $0.03/t-km, $43/t at the
shipped $0.12, $92/t at $0.30; median `v_cost` 0.924 to 0.548 across the same span.

Also fixed while here: the neutral-baseline cache key now includes both cost
settings. Omitting a setting from that key has caused a visible bug twice (the
grind slider, then the ceiling toggle), so the gate is in the key even though it
cannot change a score.

## D_w does not carry the aridity signal. The ceiling does, and it is switched off

The moisture work left an obvious follow-on: `η_transport = q/(q + D_w)` is nearly
saturated at `D_w = 0.03 m/yr` — area-weighted mean 0.787, 62.4% of cropland area
above 0.8, wettest-5%/driest-5% ratio only 4.4× against a 141× contrast in the
drainage itself. The apparent conclusion was that the map under-represents aridity
and that a larger `D_w` was the fix. `scripts/analysis/dw_sensitivity.py` sweeps
`D_w` over 0.001–3.0 m/yr and refutes both halves.

**η_transport in isolation is the wrong quantity.** Delivered carbon spans **9.9×**
wet-to-dry at the shipped `D_w`, not 4.4×, because the dissolution response to X is
nonlinear. Quoting the transport term's own range understates the contrast the map
actually draws.

**And the capped contrast does not depend on `D_w` at all:**

| `D_w` | wet/dry uncapped | wet/dry **capped** | Gt uncapped | Gt capped |
|---|---|---|---|---|
| 0.001 | 3.2× | **125.3×** | 2.77 | 0.893 |
| 0.030 (shipped) | 9.9× | **124.8×** | 2.43 | 0.888 |
| 0.100 | 23.9× | **124.0×** | 2.04 | 0.874 |
| 0.300 (published max) | 58.7× | 131.4× | 1.52 | 0.817 |

Three orders of magnitude in `D_w`, and the capped wet/dry contrast moves by 1%.
The drainage-concentration ceiling is linear in `q` and binds on 91% of cropland
area, so it has already absorbed the aridity signal — the ceiling alone carries a
149× wet/dry contrast, against 141× in `q`. The aridity bottleneck **is** in this
model. It is in the term that is off by default.

**So `D_w` is not being retuned.** The lever is `FLUX_CEILING_ON`, which is a
review question already in front of the ERW community via the flux-reconciliation
note, not a parameter question. Moving off Maher & Chamberlain's published fit to
manufacture a contrast the binding constraint already supplies would be tuning.
The separate argument that crushed feedstock justifies a higher effective `D_w`
than natural saprolite still stands on its own merits — it is just not an aridity
argument, and `constants.py` now says so.

What remains genuinely open is whether the aridity response should be *shaped*
like Calabrese et al.'s Budyko formulation rather than emerging from a q-linear
bound. That needs PET as an input and the paper read; the citation is still flagged
unverified.

Corrected in this pass: `constants.py`, `docs/METHODOLOGY.md` §2, the methodology
report's transport section and limitations list, and the Methods modal, all of
which had briefly carried the stronger "no aridity signal" claim.

## Soil moisture: an absolute saturation, and the 10× unit error it was hiding

The moisture term normalised each cell by **its own annual maximum**:

```python
smax  = np.nanmax(moist_m, axis=0)
sat_m = np.clip(moist_m / np.maximum(smax, 1e-6), 0.0, 1.0)
```

That is not a weak aridity signal, it is a different variable. Area-weighted over
the 406,991 cropland cells the term correlated **−0.886** with the coefficient of
variation of monthly storage and **+0.147** with storage itself: it measured
seasonality. The driest and wettest 5% of cropland scored **identically at 0.653**
across a 272× range in real soil water, because a dry cell is dry all year, so its
seasonality is flat, so it reads saturated. The Nile valley at 6 mm mean root-zone
storage scored **0.973**, higher than NW Europe. The Indo-Gangetic Plain, wetter
than the US Corn Belt (746 vs 629 mm), was down-weighted **36%** against it purely
for having a monsoon — inverting the temperature × moisture covariance that monthly
integration was introduced to capture.

The old caveat called this "porosity normalisation not yet applied", which
describes a missing *constant* divisor. A constant would cancel in
`reactivity/reference`. A spatially varying one does not.

**And the normalisation was hiding a second defect.** TerraClimate stores `soil`
as int16 with `scale_factor = 0.1`; `rasterio.read()` returns the raw integer, and
`fetch_monthly.py` never applied it. The committed layer was **10× too large**,
and because `write_stack` recorded `scale_factor: 1.0` the error was
self-consistent and therefore invisible. It survived precisely because a constant
factor cancels in `moist/max(moist)` — fixing the normalisation alone would have
produced a saturation 10× too large, clipped to 1 nearly everywhere.

Confirmed two independent ways: the THREDDS `.das` states `scale_factor = 0.1`
(and `description = "Soil Moisture at End of Month"`, an instantaneous state we
use as a monthly mean — now a documented limitation); and as-built annual-maximum
storage had a cropland median of 680 mm, exceeding SoilGrids plant-available
capacity on **87.9% of cropland area**, which is impossible for extractable water.
Scaled, the median is 68 mm against 141 mm.

A tripwire checked and found inert: `hi_valid=5000.0` was written meaning 5000 mm
but bit at **500** real mm. Nothing in the written product exceeds it and 0.000% of
land area lost a month, so re-tagging the committed raster to `scale_factor=10.0`
is exactly equivalent to re-downloading 1.1 GB — the stored integers are already
mm×10, so the re-tag reproduces what the fixed fetch writes.

**The fix is a chain, not a divisor.** TerraClimate reports *extractable* storage,
water above the wilting point, so it cannot be divided by a capacity and called a
saturation:

```
f = clip(storage / (fc − wp), 0, 1);  θ = wp + f·(fc − wp);  S = θ / θ_sat
```

with `fc`/`wp` from SoilGrids `wv0033`/`wv1500` and `θ_sat = 1 − ρ_b/2.65` from
`bdod`, all integrated over 0–100 cm into a new 3-band `rootzone_capacity.tif`.
This settles the question the old note left open — field capacity, saturation, or
plant-available water, which differ by ~2×. **None alone:** fc and wp bracket the
range the storage occupies, and pore volume is what converts a content into a
saturation.

**The uncomfortable part of the result.** Because θ has a wilting-point floor, S
spans only ~0.34–1.0, so the reactivity spread it produces (1.21 dex) is *no wider*
than the broken term's (1.23 dex). Simply deleting the old term rearranges 58.1% of
cropland area by decile against 64.3% for replacing it — that is how little signal
it carried. The conclusion is that the moisture term is a wetted-surface modulator
and must not be asked to carry aridity: dissolution does not stop at the wilting
point, so a term that falls to 0.021 in the Nile valley is more wrong, not less.

**Which raised a question about D_w — since answered, differently than expected.**
`η_transport` is indeed nearly saturated: area-weighted mean **0.787**, **62.4%** of
cropland area above 0.8, wettest/driest ratio only **4.4×**. The first version of
this entry concluded the map therefore had no aridity signal and that `D_w` was the
blocking item. `scripts/analysis/dw_sensitivity.py` shows both halves of that were
wrong. See the next entry.

**Gate 2e** now requires the term to be monotone in wetness — wettest/driest ≥ 1.25
and corr with log₁₀ storage ≥ 0.50 — and fails any per-cell normalisation. Reads
0.333 (1 mm) vs 0.625 (205 mm), ratio 1.88, corr +0.575.

**What moved:** global gross 2.49 → **2.43** GtCO₂/yr, with the ceiling applied
0.910 → **0.888**; median CDR 1.59 → **1.40** tCO₂/ha/yr; the ceiling binds on
93.0% → **91.0%** of cropland area; the uncapped warm/cool gradient steepened
3.95× → **4.75×**; median fraction weathered in year one 18.7% → **16.6%** and by
year ten 78.1% → **73.8%**. Propagated to `README.md`, `docs/METHODOLOGY.md` §2,
`docs/VALIDATION.md`, the methodology report, the Methods modal and the shader
comment.

## A methodology report with the equations

`scripts/analysis/make_methods_report.py` generates a ~10-page PDF setting out
every process in the model chain as equations: the Palandri & Kharaka
three-mechanism rate law and its two fidelity notes (the Arrhenius typo at OFR
eqn 7, and dropping the affinity term), the charge-weighted mixture rate and why
iron is excluded, monthly integration with rate-weighted eta_DIC, the
Rosin-Rammler surface-area integral and why the closed form cannot be used below
n = 1, shrinking-core dissolution, the transport term and the choice of water
flux, the Bertagni & Porporato efficiency derivation, Plummer & Busenberg
constants, stoichiometric potential, the carbonate-saturation ceiling and the
instructive wrong answer that preceded it, the suitability value function,
delivered cost and the ten-year discounted $/tCO2 screen, and the lognormal SOC
exceedance.

Built on the same discipline as the RFC note: every model parameter and every
distributional statistic is injected from constants.py and the built grid, so the
document cannot drift from the code. Writing it forced that to be true rather
than merely claimed -- a first draft carried a dozen figures copied from the
prose docs, and three of them were wrong once computed. One application delivers
4.0x its year-one carbon over a decade, not the 4.2x carried over; the SOC screen
flags 88% of its area north of 50N, not 96% of its cells, which is a different
quantity; and the exponential-versus-shrinking-core tail comparison is 2.15% to
0.77%, not 2.2%.

Three LaTeX traps worth recording, since the next generated document will hit
them. \cotwo and \hco defined as CO$_2$ toggle math mode OFF inside an equation
and break any \left...\right pair around them -- \ensuremath fixes it. Python's
:.1% format emits a bare %, which is a LaTeX comment that silently swallows the
rest of the line, including a table row's \\ terminator; the generator now
refuses to emit LaTeX containing an unescaped percent sign. And amssymb already
defines \checkmark.

## The readout says what is grown there

SPAM2010 was already being downloaded in full and thrown away: fetch_v0.sh pulled
the 143 MB all-crops physical-area archive, extracted irrigated rice for the paddy
pCO2 pathway, and deleted the other 41. The readout now names the two largest
crops in a cell and their share of its cropped area.

TWO CROPS, NOT ONE, AND THAT WAS THE POINT OF CHECKING FIRST. Measured over the
shipped grid, the dominant crop holds a median of only 46% of a cell's cropped
area, and just 41.7% of cropland has any crop above half:

    largest crop     p25 35%   p50 46%   p75 60%
    largest two      p25 58%   p50 71%   p75 83%
    largest three    p25 72%   p50 83%   p75 92%

A one-word label would read "wheat" on the North China Plain, where it means
wheat 25%, maize 23%, vegetables 16%. Two crops plus a "rest" remainder reach a
median 71% and say plainly when a cell is mixed. Three would reach 83% and do not
fit the encoding.

The data holds up. Area is conserved to under 0.05% through the regrid, the
global totals reproduce published physical areas (rice 113.8, wheat 199.5, maize
151.3, soybean 97.9 Mha), and twelve regional spot-checks are agronomically
right: Iowa maize 62% / soybean 38%, Mato Grosso soybean 68% / maize 32% (the
safrinha double crop), Punjab wheat 46% / rice 21%, Sahel cowpea 35% / pearl
millet 33%, Badajoz "other oilcrops" 41% for Extremadura's olives.

CONTEXT, NOT AN INPUT. Crop identity feeds nothing in the model chain except rice,
via soil pCO2. SPAM is a downscaling model rather than an observation, its
reference year is 2010 (predating Brazilian soy expansion and Corn Belt rotation
shifts), and its cropped area is 79% of Potapov cropland at the median cell -- so
the row says "of cropped area", which is not the denominator the rest of the box
uses. SPAM2010 v2.0 is nonetheless the latest GLOBAL release, verified against the
Harvard Dataverse: the SPAM2017 and MapSPAM2020 products there are Sub-Saharan
Africa only.

Mechanically: prep_layers streams the 42 rasters out of the zip one at a time
rather than unpacking 1.5 GB, and aggregation is area-conserving -- SPAM gives
hectares per 5-arcmin cell, which is EXTENSIVE, so resampling it with `average`
would silently rescale it. Storage is src/textures/crops.png, CPU-only like
admin.png, four 6-bit fields packed into RGB with alpha held at 255 because a 2D
canvas stores premultiplied colour. Masked to the cropland domain, since SPAM
allocates crops to 716k cells against the map's 407k and the rest can never be
hovered: 1.70 MB unmasked against 1.10 MB masked. The deployable site is now
6.3 MB, and the README's "5 MB" was already stale before this.

A BUG I WROTE AND THE VERIFICATION CAUGHT. The streaming top-2 update compared
the incoming crop against a second place it had already overwritten on the line
above, so a crop taking second place moved the VALUE but left the ID behind. Iowa
shipped as "maize 62%" with soybean's 38% attached to id 0, and Ukraine's second
crop came out labelled barley when it was wheat -- a wrong name, not a missing
one, which is the worse failure. Gate 16 could not see it: it checks that the
packing round-trips, not that the right crop went in. There is now a brute-force
check that re-derives the top two from a full sort over all 42 crops at 50,000
random cells and refuses to write the layer on any disagreement. It went in
because a comment I had written claimed gate 16 already covered this, and it did
not.

Also renamed SPAM's REST category from "other crops" to "miscellaneous crops": a
row reading "other oilcrops 41% · other 44%" made the remainder look like another
crop category, so the remainder is now "rest".

## The drainage limit is a toggle, and the controls stopped being sluggish

TWO CHANGES, and the second is why the first is usable.

THE DRAINAGE-CONCENTRATION CEILING IS NOW A LIVE CONTROL, under Advanced ->
"Apply the drainage limit". This needed no new data: the bound has always been
written to tex2.b whether or not it is applied, precisely so the shader could
recompute CDR live without walking it back through the bound. So the switch was
already latent in the format and this exposes it.

Everything downstream follows the toggle, which was the actual work -- twelve
call sites read the flag, and half a map applying a bound is worse than none:
the footer total and its "drainage limit not applied" suffix, the
limiting-factor layer's own colour class and its legend row, the hover box's
"without the drainage limit" row, and the Methods panel's conditional text
(rebuilt on change, since it is generated once at load and would otherwise
describe the other setting).

It reproduces the Python build exactly: 0.91 GtCO2/yr with the ceiling on
against the build's 0.910, and 2.49 against 2.488 off. That is also a check on
the tex2.b encoding, since the browser reaches the ceiling through an 8-bit log
channel and Python does not.

`constants.FLUX_CEILING_ON` now sets the SHIPPED DEFAULT rather than being the
only way in. It stays False: the bound is out for review, and flipping it would
make an unreviewed bound the headline figure, which is the thing the review
exists to avoid. The derived products -- the `cdr` array, gate 12, the cost
screen -- still follow the constant, so applying the bound outside the browser
is still a rebuild.

Advanced now stays open in every layer and only the term-exponent block is
mode-specific. The drainage toggle has to be reachable from the limiting-factor
layer above all, because that layer gives the ceiling its own colour when it
binds -- hiding the switch would hide the control for a class the legend is
showing. The distribution-width slider comes along, which is right: grind feeds
`frac`, so it moves what binds.

Caught while wiring it: the neutral baseline's decile cache keyed on grind and
cost exponent but not on the ceiling, so toggling it would have left the
stability baseline scored under the other setting. Same class of bug the comment
above that cache already warns about. Also fixed a stale summary tag -- the
at-defaults short-circuit added below returned before setting it, so it read
"Down-weighted" after a Reset to physics.

## The controls stopped being sluggish, and it was never the rendering

The map felt slow on the grain-size slider and the toggles. Profiled rather than
guessed: the GPU draw was 4 ms of a 1,400 ms slider event. All the rest was two
CPU statistics passes over the 45,155-cell decimated sample, run inline on every
input event -- updateStability() at ~170 ms and the footer's globalGt() at ~88 ms.

    slider input, mean per event      1,400 ms -> 2.5 ms   (max 5.8)
    mode switch                                  -> 1-3 ms
    quarry / mafic / drainage toggle              -> 4-17 ms

Nothing about resolution, the shader, or any number changed:

- gSlice() memoised on psd.width. It rebuilt a 64-element Float32Array on EVERY
  fracOf() call, and fracOf() runs once per sampled cell plus once per year in
  the cost screen's ten-year loop -- about 630k rebuilds per refresh. 5.4x alone.
- updateStability() returns immediately at the term defaults, where the answer is
  zero by construction: same exponents, same edges, so every cell lands in the
  same decile. It was spending three passes and a 45k sort to rediscover an
  identity -- and the defaults are the landing state and where anyone touching
  only the grind or the economics toggle sits.
- The neutral baseline's per-cell scores are cached beside its edges, so the
  non-default path does one pass instead of two. edgesFrom() sorts an Int32Array
  of indices rather than building 45k two-element arrays.
- globalGt() hoists what was constant: X and eta_DIC once per row rather than
  twice, the ceiling out of the year loop (constant in t, and costing ten
  Math.pow calls per cell inside decodeCeil), and log10(u_t) as
  log10(u_1) + log10(t). Discount factors are stored as pow[] and DIVIDED by
  rather than pre-inverted and multiplied, so the arithmetic stays bit-identical
  and no cell on the screen threshold can flip.

The two statistics are then debounced 80 ms off the input path, so a drag redraws
every frame and the numbers settle once after it stops. First paint calls
flushStats() synchronously so the footer never shows its placeholder.

VERIFIED BIT-IDENTICAL. Extracted the numeric core verbatim from both the old and
new src/app.js into a Node harness, fed both the same 45,155-row sample decoded
from the shipped textures in Python, and compared globalGt to 15 significant
figures, the kept-area fraction and the stability sentence across 120 settings
(4 grain sizes x 3 widths x 5 term-exponent combinations x economics on/off).
Zero mismatches.

## Drainage is total runoff, not groundwater recharge, August 2026

Found by looking at the map. Dark blobs over the Mekong Delta turned out to be cells
where the drainage water flux `q` was **exactly zero**, so `eta_transport = q/(q+D_w)`
was zero and gross CDR was zero, which renders as the "negligible" swatch. Zero
drainage across 1,570 mm/yr of rain is not a dry climate, it is a wrong variable.

`q` came from WaterGAP2-2e `qr`, **diffuse groundwater recharge**. In a delta the
water table is at the surface, so nothing percolates to an aquifer and WaterGAP
correctly reports zero; field drainage still leaves laterally to canals with its
bicarbonate in it. **Zero recharge is not zero drainage.** The defect covered 0.10%
of cropland area, 57% of it the Mekong Delta, then the Red River delta and the middle
Yangtze — every cluster a delta or lake floodplain, which is the signature you would
expect.

THE OBVIOUS FIX FAILS, AND THAT IS THE USEFUL PART. `qtot - qs` = subsurface runoff
`qsb` is "water that reached the stream through the soil", which sounds exactly right.
But in WaterGAP, recharge feeds the groundwater store and that store discharges as
baseflow, so over a 30-year mean `qsb` is `qr` relabelled: global land medians 33.5
vs 32.6 mm/yr, ratio 1.00 at the cropland median, log-log correlation 0.81. It clears
the delta zeros and creates worse ones where groundwater is pumped — **26% of the
Indo-Gangetic Plain** and 4% of the US Corn Belt go dark, taking the global negligible
class from 0.79% to 6.60% of cropland area. Trading deltas for the Indo-Gangetic
Plain is a bad trade. This was predicted from WaterGAP's structure before the 622 MB
of downloads, then measured; both are recorded because the prediction is the reason
`qsb` is not the shipped answer.

`qtot` (total runoff) is the new default, for two reasons that agree. Maher &
Chamberlain fit `D_w` against the Gaillardet river dataset — catchment discharge per
unit area, which IS `qtot` — so driving a `qtot`-calibrated `D_w` with recharge
penalises the flux twice, the same double-counting logic as
`DAMKOHLER_TAU_APPLIED_IN_ETA`. And it fixes the defect without creating another.

    area-weighted cropland medians      qr 74.8   qsb 75.2   qs 83.7   qtot 177.8 mm/yr
    eta_transport, median               0.71 -> 0.86
    global gross, unbounded             2.149 -> 2.488 GtCO2/yr   (+15.8%)
    median gross CDR                    1.268 -> 1.589 tCO2/ha/yr (+25.3%)
    negligible class                    0.79% -> 0.10% of cropland area
    wet-but-undrained (gate 2c)         0.124% -> 0.022% of area
    >90% weathered in year one          0.63% -> 0.77% of area
    headline under the $100 screen      0.50 -> 0.60 GtCO2/yr on 0.17 -> 0.19 Gha

The change is broad, not a delta patch: +7% to +30% by latitude band, biggest in the
irrigated subtropics, with the Indo-Gangetic Plain and Pakistan taking the largest
absolute gains. That is the case `eta_transport`'s own docstring already flagged when
it said q must include irrigation return flow.

The honest caveat, and why `qr` stays as a reported sensitivity rather than being
deleted: surface runoff has little contact time with topsoil rock, so `qtot` credits
water that arguably weathered nothing. The counter is that `D_w` is an effective
parameter fit at catchment scale where nearly all runoff has passed through regolith.
Read them as a bracket, 2.15 to 2.49 GtCO2/yr, printed every build as gate 2d.

IT ALSO REVERSED TWO THINGS WE HAD WRITTEN DOWN AS FINDINGS.

The ceiling is `q x [HCO3-]max x 44`, so understating the water understated the bound
in direct proportion. With the flux ceiling on, the global total goes **0.360 ->
0.910 GtCO2/yr**, which moves it from BELOW its pre-registered 0.5-4.0 band to inside
it — without the band being widened. `docs/VALIDATION.md` had argued at length that
falling below was the expected consequence of imposing a bound the comparison
literature lacks. That argument still holds on its own terms, but the specific
shortfall was substantially an input error. A result that reads as a deep finding can
still be carrying one.

And the warm-climate result weakened. The ceiling took the warmest/coolest ratio from
4.37x to **0.91x** on recharge, i.e. it reversed the gradient; on total runoff it goes
3.95x to **1.41x**, strongly reduced but not reversed. The direction is robust, the
reversal is not, and the RFC note now says so and tells earlier readers not to quote
it. Deployment-level exceedances fell the same way, 3-19x to 1-8x.

NEW GATE 2c, the one that would have caught this: a cell receiving more than a metre
of rain a year cannot drain less than a millimetre. That is an impossibility rather
than a tuned tolerance, so the 0.05%-of-area allowance is for 0.5-degree cells
straddling a wet/arid boundary, not for regions. Gate 2d reports the qr-vs-qtot
bracket on every build so the choice stays visible instead of settling into a default.

THREE UNRELATED DEFECTS FOUND WHILE PROPAGATING THE NUMBERS, all pre-existing:

- The RFC note shipped **"the global total from nan to nan"**. The 695 cropland cells
  with no climate input carry NaN CDR, which poisoned the area-weighted SUMS while
  leaving every percentile intact, so it survived review. Now `nan_to_num`, matching
  what gate 2b in the build already did.
- `docs/METHODOLOGY.md` and the RFC both said field trials achieve **"5-10x below"**
  the ceiling. Computed against the median ceiling of 6.65 mmol/L it is **9-60x**.
  Arithmetic error, not a stale number — the ceiling concentration does not depend on
  the drainage variable. Correcting it strengthens the argument it appears in: trials
  sit further below the bound, so the bound explains even less of the level. Now
  computed in the generator rather than asserted.
- The Methods panel still described dissolution as **`1 - exp(-k*X)`** and the anchor
  as the "midpoint" of verified deliveries. Both were superseded when shrinking core
  landed and when the anchor was corrected to the median. The panel now describes the
  shrinking-core integral and reads the drainage source from provenance, so it cannot
  drift from the build again.

The reapplication-cadence check moved too, and not in the comfortable direction. The
map's year-one figure used to sit on a five-year interval; it now sits on **four**
(1.59 tCO2/ha/yr against 1.59 for k=4). Most of that is drainage — the year-one
weathered fraction went 14.9% to 18.7% — and the rest is a construction fix: the old
table multiplied the stoichiometric maximum by the *median* 10-year fraction, mixing
percentiles from different cells and overstating the yield ~6%. A field on a rotation
longer than four years removes less than the map shows.

Reproduce all of it with `scripts/analysis/drainage_variable.py`. Revert with one
constant, `DRAINAGE_VARIABLE = "qr"`, and a rebuild.

## Economics on by default, and a mafic-outcrop overlay

ECONOMICS DEFAULTS TO ON. It was off, on the argument that the landing map should
state physical potential and economics should be opted into. That lost to a stronger
argument: the unscreened map implies 2.15 GtCO2/yr across essentially all cropland,
and almost none of that is deployable at a price anyone would pay, so leading with
the physical figure put the less useful number in front. The landing state is now
0.50 GtCO2/yr on 0.17 Gha under the $100/tCO2 screen.

The counter-argument is recorded rather than discarded: economics adds a gate cost,
a truck rate, a tortuosity factor and a quarry inventory of very uneven
completeness, none as well constrained as the physics. The toggle still switches it
off, the footer states its basis either way, and if the cost inputs turn out to be
badly wrong the flag flips back rather than being patched around.

MAFIC OUTCROP OVERLAY, alongside the quarry points. Quarries are a real inventory
but a very unevenly complete one -- three national registers plus OSM -- so outside
those countries an absent dot says nothing. GLiM mafic and ultramafic outcrop is
global and answers the prior question: is there mafic rock near here at all.

Drawn ON AND OFF cropland, which needed the shader restructured: 74% of mafic
outcrop lies outside the cropland domain, where the map is otherwise transparent.
The tint also applies on every in-domain return path -- suitability, limiting
factor, fraction weathered, negligible, SOC-excluded and no-input -- through a
single withMafic() blend, so it cannot silently vanish in one layer.

Its own texture (tex4, 0.40 MB) rather than a spare channel. tex3.r still holds the
Cascade baseline, which nothing currently reads but which is a documented
comparison layer and should not be quietly deleted to save a file.

Sanity-checked geologically rather than by eye: Deccan, Siberian Traps, Columbia
River, Parana and the Ethiopian highlands all return mafic fraction 1.00; the Corn
Belt and Ganges plain return 0.00.

## The cost screen is costed over ten years, not one, August 2026

The $/tCO2 screen divided a ONE-OFF rock cost by ONE YEAR of removal. The rock keeps
weathering, so that overstated cost by about 3.2x. It now uses the discounted carbon
a single application delivers over ten years, through the same shrinking-core model
the map draws: retreat accumulates linearly in time, so cumulative Fw = G(u*t) and
year t delivers the increment. Cost at t=0, tonnes at the end of years 1..10,
discounted at 5%. Threshold set to $100/tCO2.

    median $/tCO2, old basis (year 1 only)     946
    median $/tCO2, 10 years at 5%              299

    headline with economics ON   0.50 GtCO2/yr on 0.17 Gha  (<$100, 10 yr, 5%)
    previously                   0.50 GtCO2/yr on 0.12 Gha  (<$200, year 1)

The total barely moves but the SELECTION changes: a stricter threshold on a fairer
basis keeps 13.9% of area rather than 10.1%, and different cells.

THE DISCOUNT RATE BARELY MATTERS; THE HORIZON DOES. Across 0-12% the median moves
$253-$367 and the qualifying total only -21%. Across horizons at 5% it moves $993
(1 yr) -> $488 (3) -> $380 (5) -> $299 (10). Using any multi-year window was the
decision that mattered.

Two honest limits. Shrinking core captures the geometric slowdown as particles
shrink but NOT passivation, secondary-mineral armouring or depletion of the most
reactive phases, so real ten-year yields decline faster than the 70% this implies.
And it interacts with the drainage ceiling: with the ceiling on, each year's EXPORT
is capped, so extra years buy far less -- median $953/tCO2 and only 6.8% of area
under $200. The screen applies the ceiling per year, not to the total, and follows
FLUX_CEILING_ON.

WHY THE YEAR-ONE HEADLINE IS STILL THE RIGHT ONE. The rate is stated per year while
the CDR layer is the first year from one application, which only coincide under
annual reapplication -- and a field takes a multi-year break. Both errors cancel,
and it is worth showing rather than assuming. Steady-state annual removal at a
reapplication interval of k years is (rate/k) x eventual yield:

    every 1 yr   6.04 tCO2/ha/yr        every 5 yr   1.21
    every 2 yr   3.02                   every 7 yr   0.86
    every 3 yr   2.01                   every 10 yr  0.60

The map shows 1.27, which sits almost exactly on a five-year interval. So the
year-one framing approximates a realistic cadence at steady state; annual
reapplication (6.04) would badly overstate it. Now documented, because the "/yr"
label otherwise invites exactly that misreading.

The dissolution table's u range went from 12 to 100 so the same lookup can run ten
years at the finest grind. Costs 0.0004 in worst-case interpolation error.

## The headline total responds to the economics toggle, August 2026

With economics ON the footer total is now restricted to cells whose delivered
feedstock and haul come in under **$200 per tonne of CO2**: 0.50 GtCO2/yr on
0.12 Gha, against 2.15 GtCO2/yr on 1.21 Gha unrestricted. The map itself is
unchanged -- economics still discounts suitability compositely, as before -- so this
affects the headline only, and the toggle's caption now says both things.

PER TONNE OF CO2, NOT PER TONNE OF ROCK, and the difference is the whole point.
Rock cost is nearly uncorrelated with CDR in this model, because haul distance is
driven by quarry geography while CDR is driven by soil and climate. So a rock-cost
screen barely discriminates -- under $100/t rock keeps 83.7% of area and 83.3% of
the carbon -- whereas a $/tCO2 screen keeps 10% of area and 23% of the carbon,
because it rewards cells that produce enough carbon to justify the haul.

For scale, the unscreened global mean is roughly $1,000/tCO2 on feedstock and haul
alone, before grinding, spreading, MRV or any net-versus-gross deduction. That is
what makes a $200 screen bite so hard, and it follows directly from 30 t/ha of rock
buying only ~1.8 tCO2/ha/yr.

The browser recovers $/t by inverting the cost value function out of an 8-bit
texture channel, which is lossy, so this was checked rather than assumed: no cell
reaches the value-function floor where the inversion would saturate (max delivered
cost $429/t against a $1,910/t saturation point), round-trip error is 0.43% at the
median and 1.3% at worst, and the screened total via the texture lands within 0.12%
of the exact figure computed from the raster.

Also corrected here: the unrestricted headline now reads 2.15 rather than 2.16,
because it scales by evaluated area rather than total cropland. That matches the
2.149 the build prints.

## Headline stat is now the CO2 total, and the panel stops claiming a bound it is not applying

The footer read "1.22 Gha cropland in scope", which is an input to the model rather
than a result. It now reads the GLOBAL GROSS REMOVAL, computed live from the gridded
data: the area-weighted mean CDR over the decimated sample, scaled by the EVALUATED
cropland area. Because it is computed rather than stored it moves with the sliders --
0.68 GtCO2/yr at a 700 um grind, 2.16 at the reference, 4.50 at 40 um.

Two things done properly rather than approximately:

  - It scales by evaluatedGha (1.21), not total cropland (1.215). The sample only
    covers cells with a computable rate, so scaling its mean by the full extent
    would credit removal to the cells we declined to evaluate.
  - It reads 8-bit textures on a 1-in-3 decimation, so it lands ~0.5% above the
    exact area-weighted total the build prints (2.16 vs 2.149). The decimation
    itself costs only 0.2%; the rest is texture quantisation. Stated in the stat's
    tooltip rather than papered over or fudged to match.

cdrOfRow is now one definition shared by the suitability score, the decile edges and
this total, so the three cannot disagree about what is being drawn.

METHODS PANEL. Three passages still asserted the drainage ceiling was in force,
which it is not:

  - the limiting-factor caveat led with "drainage cannot carry it is a bound, not a
    term... That is most of the map"
  - the gross-removal note said carbonate saturation "enters only as an upper bound
    on what the drainage can carry"
  - the kinetics note claimed the temperature bias "no longer propagates to the CO2
    layer... the drainage ceiling above binds first"

That last one was the worst: with the ceiling off the tropical tilt propagates in
FULL, so the panel was reassuring the reader about a correction that is switched
off. All three are now conditional, and the off-state text says plainly that
nothing downstream of dissolution is deducted. The assumptions table marks the
ceiling rows "(not applied)".

## Shrinking-core dissolution, and two scales that could not be reached

**Dissolution is now shrinking core over the particle-size distribution**, not a
single first-order decay on the bulk mass. The old frac = 1 - exp(-k*X) let the
last 10% of rock dissolve as easily as the first 10%, when physically that last 10%
is the coarse tail with the least surface area per unit mass. Every particle's
surface now retreats at the same linear rate, so the fines vanish early and the
coarse tail persists.

    u = delta/d50,  Fw(u,n) = 1 - integral f(x) max(1 - 2u/x, 0)^3 dx

Fw depends only on u and the width, which is what lets the browser interpolate a
64x13 table rather than integrate 6,000 size bins per pixel (gate 14 bounds that at
0.0019, below the 8-bit step).

  cropland area above 75% weathered   6.4%  -> 3.4%
  above 90%                           1.8%  -> 0.63%
  above 99%                           0.11% -> 0.01%
  p50 / p90 / p99            13.9/65.0/94.0 -> 14.9/58.6/87.1%

The median barely moves and the extreme tail is cut by about two thirds. It does
NOT make 100% unreachable: a cell with 40x reference reactivity still gets there,
which is a kinetics question, not a particle-size one.

**Grind moved out of the rate.** Under shrinking core the linear retreat rate does
not depend on particle size, so the surface-area multiplier on the rate is gone and
grind enters once, through the integral. Keeping both would count the same physics
twice. Gate 15 asserts the shader's L1 decode carries no surface-area term. The
grind readout no longer says "x faster weathering" -- it reports surface area,
which is what it actually measures.

**Suitability 100 was arithmetically impossible, in every build.** The top knot sat
at 10 tCO2/ha/yr, but the stoichiometric maximum is rate x the feedstock's CO2
potential: 8.69 at 30 t/ha, and 5.79 at the old 20. So roughly the top 8 points of
the scale were dead. The top knot is now the stoichiometric maximum itself,
computed, so 100 means "every tonne applied dissolved and every available cation
carried its carbon". The lower knots stay absolute, which is what keeps scores
comparable between builds.

**The fraction-weathered ramp spanned 0-100% and spent 40% of its colour on 2% of
cropland.** Top is now 0.65, labelled ">= 65", which clamps 7.3% of area. 0.80
would clamp 2.2% and 0.90 only 0.6%, so this is a readability-versus-headroom trade
made at the readability end.

**Where DISSOLVED_FRAC_AT_REF comes from, corrected.** The note claimed it was
"anchored to the MIDPOINT OF OBSERVATION". It is not the midpoint (35.7%) but
nearest the median (26.4%) of the eight verified deliveries. Worse, those
deliveries are not at the reference grind -- renormalised to a common grind and
rate they span 8.7-71.3% with median 31.7%, so a number defined at a normalised
condition was justified by un-normalised observations. And the reference condition
is under-specified on the transport side: frac = 0.25 at X = 1 implies
eta_transport = 1, i.e. infinite drainage, which no site has. At median cropland
drainage the same cell weathers 18.5%. Still an anchor rather than a fit, but the
old wording oversold how well determined it is.

## Missing climate input is drawn as missing, August 2026

695 cropland cells -- 0.35 Mha, 0.03% of cropland area, almost all high-latitude
Scandinavia -- are inside the cropland mask but have no monthly soil temperature or
moisture, so the rate is undefined. They were falling through the texture encoder's
nan_to_num(L1, nan=-3.0), which turned NaN into a relative reactivity of 0.001 and
drew them as near-zero potential. Small in area, but the wrong category: it states
"no removal here" where the honest answer is "we did not evaluate this".

They now set flag bit 2 (free since the marginal-SOC hatch was removed), render in a
distinct grey in every layer, are excluded from the decimated sample behind the
stability metric and decile edges, and the hover readout says so in words instead of
printing numbers derived from the fallback. The build reports the count and area on
every run.

The flag is masked to the in-domain cells. Unmasked it claimed 3.5M "no input"
pixels, because L1 is NaN over every non-cropland pixel too.

## Flux ceiling switched OFF pending outside review, August 2026

Held, not reverted. `constants.FLUX_CEILING_ON = False` and rebuild; that is the
entire change. The bound stays implemented, gated, documented and written to the
texture, and flipping the flag back to True restores every behaviour. The round trip
is verified in both directions.

Why: the ceiling moves the map's absolute level several-fold -- global gross 2.209 ->
0.360 GtCO2/yr, median 1.189 -> 0.220 tCO2/ha/yr -- on a chain of reasoning that has
not yet been outside this repo. That judgement is worth other ERW scientists' eyes
before it ships. The four questions most likely to be contested are listed in to_do
item 0.

Reverting the commits would have been the wrong way to do this. It would have thrown
away the gates, the five literature anchors, the Maher tau/D_w resolution and the
deployment test along with the switch, and re-deriving them later is most of the
work. A flag costs one line and loses nothing.

WHAT DELIBERATELY STAYS LIVE WHILE IT IS OFF, so the finding cannot quietly vanish
with the cap:

- Gate 12 no longer enforces; it REPORTS. Every build now prints that 98.9% of
  cropland area reports more carbon than its drainage can carry, median 6.2x over.
- The Methods panel swaps the active description for a flagbox saying the CO2 layer
  is an upper bound on dissolution, not carbon shown to leave the field.
- The ceiling is still computed and still written to tex2.b, so re-enabling needs no
  data migration.
- Section 11 of analyse_deployments.py is untouched: the verified deliveries still
  exceed their own drainage ceilings by 3-19x. That is a finding about the
  deliveries, not a setting of this model.

An uncomfortable symmetry worth stating plainly, now recorded in VALIDATION section
5: with the ceiling OFF the map passes its pre-registered global consistency band
(2.209 inside 0.5-4.0); with it ON the map fails that band (0.360) but satisfies the
physics. Passing the band is therefore not evidence of anything, and while the
ceiling is off no absolute CO2 figure from this map should be quoted without the
caveat.

## Application rate 20 -> 30 t/ha, and the grind slider tells the truth at its own reference

**Application rate raised to 30 t/ha**, because 20 sat below what commercial projects
actually spread. The consequence is the most useful thing the flux ceiling has produced
so far, and it is not what a linear model would predict.

| | 20 t/ha | 30 t/ha |
|---|---|---|
| uncapped median CDR | 0.792 | 1.189 tCO2/ha/yr (+50%, linear in rate) |
| **capped median CDR** | **0.220** | **0.220 (unchanged)** |
| global gross, capped | 0.354 | **0.360 GtCO2/yr (+1.8%)** |
| global gross, uncapped | 1.472 | 2.209 GtCO2/yr (+50%) |
| cropland area where the cap binds | 96.5% | 98.9% |
| realised carbon per tonne of rock, median cell | 3.8% of stoichiometric | **2.5%** |
| rock spread | 24.2 Gt/yr | 36.3 Gt/yr |

**50% more rock bought 1.8% more carbon.** The ceiling is set by drainage and carbonate
chemistry, not by how much rock is on the field, so past the point where drainage
saturates, extra feedstock raises the share of the map that is transport-limited rather
than the tonnage -- and it lowers the realised efficiency per tonne. Item 9's supply
constraint got 1.5x harder for almost nothing, which makes it the binding practical
limit well before geology is.

Two honest caveats. The dissolved fraction is held at DISSOLVED_FRAC_AT_REF regardless
of rate, so the uncapped layer scales linearly. Whether that is wrong, and in which
direction, is NOT known: an earlier draft of this entry claimed the delivery set implied
a -0.58 sublinear exponent and hence a ~27% over-credit, which is withdrawn --
constants.py already documents that -0.58 is the operator/grind contrast wearing a rate
label, with a within-operator slope of -0.01 +/- 0.57. And the ceiling bounds EXPORT, so
it does not follow that the extra rock is wasted -- it may weather and sit in the soil,
which is the retention question, not this one.

**The trial comparison is no longer at matched rate.** The trials span roughly 20 to
200 t/ha rather than sharing one rate, and per-trial rates in this repo are being
corrected. A "0.05-0.15 tCO2/ha/yr" band written earlier was produced by normalising
several trials to 20 t/ha linearly, which is exactly the unsafe operation, and should
not be read as a measured range. What survives: the capped median is 0.220 at both 20
and 30 t/ha, so conclusions resting on the ceiling are rate-insensitive, while any
conclusion comparing absolute tonnages to trials needs matched rates.

**The grind slider no longer contradicts itself.** It reported "1.01x faster weathering
than the reference grind" while its own badge said "Reference", and that +1% propagated
into every displayed CDR, because the shift multiplies the reactivity the shader reads.
Cause: the 24x13 shift table is interpolated bilinearly in the browser, and plain
linspace axes put the reference between nodes on both -- 150 um fell between 126.1 and
154.8, width 1.5 between 1.45 and 1.60. Both axes are now built to pass exactly through
the reference, so the shift is exactly 0 there by construction, asserted by gate 8
rather than hoped for. Worst-case interpolation error elsewhere moved 0.8% -> 0.9%,
which is a fair trade for exactness at the default every user loads into. The readout
at the reference now says so in words instead of printing a tautological 1.00x.

## Flux reconciliation, August 2026

The largest open problem in the model is closed. It was real, it was mis-sized by
~50–100×, and the interesting part turned out not to be the level.

**What the model was missing.** The carbon reported has to leave the field dissolved
in the water that leaves the field. Nothing enforced that. Recasting Maher &
Chamberlain's `q/(q+D_w)` as a multiplier on a kinetic rate keeps the shape of their
curve and drops the finite concentration limit `C_eq`, which is why the CO₂ layer
first needed a hard clip at 0.6 and then a saturating exponential — both patching a
missing physical bound at the wrong level.

**What shipped.** `cdr = min(cdr, q · [HCO₃⁻]_max · 44)`, with `[HCO₃⁻]_max` set by
calcite saturation at each cell's own soil pCO₂ and temperature, solving charge
balance `2[Ca]+2[Mg] = [HCO₃⁻]` simultaneously with fixed pCO₂. Enforced by gate 12
in the build and gates 13/13b/13c in the kinetics suite, and applied in the shader
too, because the grind slider recomputes CDR live and would otherwise walk the
displayed carbon straight back through the bound.

**The audit's own ceiling was wrong, in the other direction.** It computed
`q · [HCO₃⁻](pH, pCO₂)` holding each cell's *pre-treatment* pH fixed. But pH is
endogenous — adding base cations at fixed pCO₂ raises alkalinity and pH together, and
raising pH is what a silicate amendment is for. That gave 0.42 mmol/L at the median,
which is ~8–15× too strict and is, to two significant figures, the observed mean
alkalinity of streams draining **unamended** volcanic rock. A good baseline; the
wrong ceiling. The corrected bound is **3.0–6.5 mmol/L**, agreed by five independent
anchors — Zhang et al. 2022's riverine transport potential back-converted (4.3–13.0),
Hamilton et al. 2007's measured Midwest agricultural tile drainage (1–7), Meybeck's
pristine-river 99th percentile (5.95) and carbonate-terrain streams (3.15), and a
soil-pH backstop at ~10. So the model was **4–9× over, not 563×**.

**The finding is a climate-gradient error, not a level error.** `C_eq` falls with
warming (3.56 / 3.03 / 2.58 mmol/L at 5 / 15 / 25 °C) while the rate law rises
steeply, so exceedance is monotonic in temperature: 1.8× in the coldest cropland to
8.6× in the hottest. The warmest-to-coolest ratio of the median CDR goes from
**4.37× uncapped to 0.91× at the ceiling**. The map's warm-climate advantage — its
most visually prominent and most quotable feature — was an artefact of an unbounded
rate law. Median CDR 0.792 → 0.220 tCO₂/ha/yr, and the cap binds on 96.5% of
cropland area.

**Two Maher & Chamberlain questions closed from the primary source, and both
deliberately not acted on in `eta_transport`.** τ = e² is real and is *not* already
folded into the Fig. 2 contours: those labels reproduce to two significant figures
from the paper's own printed parameters using bare `D_w = L_φ/T_eq`, while Fig. 2B's
plotted flux plateaus match `C_eq·τ·D_w` and are 0.8 of a decade off without τ. And
ERW belongs at the high D_w limb (~0.3), because the published 0.003–0.3 range is
generated at fixed path length by varying soil age, and 0.03 is the caption's
"T_s of 100,000 years" — a hundred-millennium regolith standing in for a mineral one
year old. **Neither is applied to `eta_transport`.** In M&C that factor multiplies
the kinetic-limit flux `τ·L_φ·R_n`, which carries `C_eq` with it; ours multiplies a
dimensionless relative reactivity, which does not. Swapping τ in alone drops the
median 21.9× and undershoots the physical ceiling by ~5×, double-penalising a rate
already anchored to field data. Recorded as `DAMKOHLER_TAU_APPLIED_IN_ETA = False`.

**The corollary is now demonstrable in the app.** With τ, `τD_w` is at or above the
p90 of cropland drainage on either limb, so all cropland sits where the flux is
`C_eq·q` and the rate law drops out — Maher 2010 p.104: beyond L_eq the flux
"conveys no information on the actual weathering kinetics or available surface area",
and Godsey et al. 2009 measure near-chemostatic C–Q slopes of −0.05 to −0.15 across
59 catchments. Dragging the grind slider from 700 to 40 µm now moves *fraction
weathered* from 3.9% to 46% while the exported carbon stays pinned at the ceiling,
and the limiting-factor label reverts to "Dissolution rate" only once the grind is
coarse enough for the rate to genuinely bind.

**The cap bounds the carbon, not the rock, and that separation is the physics.**
`frac` — the one layer field trials can measure — is left unbounded. Rock can
dissolve without the carbon leaving; the gap between the two layers is the retention
problem, and it is now visible instead of being an inconsistency.

**The 28.5 mmol/L was never specific to this map.** Beerling et al. 2024's CDR_pot
of 10.5 tCO₂/ha over four years implies 29.8 mmol/L at Illinois tile drainage of
200 mm/yr, and that paper reports no drainage chemistry at all. Kelland et al. 2020
closes the loop inside one experiment: measured cation release requires 21.1 mmol/L
against measured leachate alkalinity of 1.10 ± 0.147, statistically indistinguishable
from control. A 19× shortfall measured on both sides. The instinct to treat this as
existential for ERW generally rather than as a local bug was correct.

**What it did not fix, now recorded as a new to-do item.** The level. Field trials
achieve 0.11–0.75 mmol/L, 5–10× *below* this ceiling, because cations are retained in
secondary phases rather than exported — 10–50× more retained than exported (Hammes
et al. 2025), retarded fractions of 93–98% (te Pas et al. 2025). The capped map still
sits ~2–4× above the trials that measured drainage chemistry directly, against
Dupla et al. 2025's 0.100 ± 0.030 tCO₂/ha/yr (that trial applied 20 t/ha, which was
also the map's rate at the time of this entry; the map moved to 30 t/ha shortly after,
and per-trial rates in this repo are being corrected). Cation retention is
now the largest missing term and is entered in `to_do.md` as item R with explicit
entry criteria, because it is blocked on data rather than on effort — and because the
one retention proxy that is readily griddable, CEC, is the wrong pool: SMEW
attributes the gap primarily to CEC adsorption while both measurement studies find
the exchangeable pool is the *minority* sink.

**Reported, not fudged.** On saturated paddy cells the protocol-mandated 50,000 µatm
lifts the ceiling to 13–18 mmol/L, above every anchor, and the literature contains no
measured floodwater alkalinity or paddy lateral DIC export flux to check it against.
Gate 13c records this rather than widening a tolerance to make it pass.

**Also fixed in passing.** A pre-existing bug where a **pinned hover readout went
stale** when a slider changed the numbers. It predates this work but the ceiling would
have made it invisible, because "the number did not change" is frequently now the
correct answer.

Full analysis, including the five anchors and the three-way cross-check, in
`FLUX_RECONCILIATION_2026-08.md`; the four analysis scripts are in
`scripts/analysis/`.

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
