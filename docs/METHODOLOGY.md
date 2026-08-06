# Methodology

The model chain, its parameters, and the choices that are not forced by physics.
`docs/VALIDATION.md` covers the gates and the pre-registered criteria;
`CHANGELOG.md` covers how the model got here.

Every number below is generated from `scripts/constants.py`. If this file and
that file disagree, the code is right and this file is stale — say so in a PR.

---

## 1. Grid and resolution

0.1° equirectangular, 3600 × 1400, spanning 82.7°N to 56.0°S. That is ~11 km at
the equator, but **grid spacing is not resolution**: effective resolution is
roughly 10–50 km because the feedstock component is limited by the scale of
mapped mafic lithology (GLiM's realised average source scale is ~1:3,750,000),
not by pixel size.

The pH raster defines the master grid; everything else is reprojected onto it.
Coarse inputs (WaterGAP total runoff at 0.5°, paddy layers) use **nearest-neighbour**
on purpose, so the blockiness is visible rather than smoothed into detail the
source does not have.

Zoom is capped in the viewer. Nothing below ~1 km² should be read as
site-specific.

## 2. The model chain

```
soil pH, soil T, soil moisture
        ↓  Palandri & Kharaka three-mechanism rate law, per mineral
        ↓  summed over the archetype's minerals by VOLUME fraction
     reactivity  →  L1 = log10(reactivity / reference)
        ↓  × grind shift, log10(SSA(d50, width) / SSA(reference))
        ↓  × η_transport = q / (q + D_w)
      X (dimensionless, relative to the reference condition)
        ↓  frac = shrinking core over the Rosin–Rammler PSD  (grind enters HERE)
        ↓  × η_DIC  (carbonate-equilibrium efficiency)
        ↓  × application rate × tCO₂ per tonne
        ↓  min(·, q · [HCO₃⁻]_max · 44)   drainage-concentration ceiling
   gross CO₂ removal, tCO₂/ha/yr
        ↓  piecewise-linear value function on absolute breakpoints
   suitability, 0–1
        ↓  × cost multiplier ^ exponent  (ON by default; toggle switches it off)
   suitability with cost
```

### Where each term enters, and why there

- **η_DIC multiplies the carbon, not the rock.** It is outside the dissolution
  exponential. Carbonate speciation does not slow dissolution; it determines how
  much carbon each unit of released alkalinity carries. It was inside the
  exponential until July 2026, which suppressed the predicted *fraction
  weathered* — the one layer field trials can measure — by up to ~2× in acid
  soils.
- **The grind shift is additive on L1 and applied once.** Rate is linear in
  reactive surface area and L1 is a log ratio, so a change of grind is a uniform
  additive shift, which is what lets the slider be a single shader uniform. It
  was applied twice until July 2026 (once inside L1, once again on the CO₂
  figure), inflating CO₂ by up to 3.45× at the fine end of the slider and
  breaking the stoichiometric ceiling.
- **The ceiling bounds the carbon, not the rock.** `frac` — the one layer field
  trials can measure — is deliberately left unbounded, and only the CO₂ is capped.
  Rock can dissolve without the carbon leaving: field trials measure 10–50× more
  cations retained in secondary phases than exported, and one mesocosm study at up
  to 200 t/ha measured zero increase in leachate DIC while the rock demonstrably
  weathered. So the gap between the fraction-weathered layer and the capped CO₂
  layer is real information, not an inconsistency. The cap is applied *after*
  η_DIC, because what has to fit in the water is the bicarbonate.
- **The three terms are a product with unit exponents by default**, so zero in any
  required term gives zero carbon. The sliders are **exponents**, not importance
  weights: you cannot prefer dissolution over alkalinity retention because both
  are required multiplicatively.

### Which water flux is q?

`η_transport = q/(q + D_w)` needs the water flux through the weathering zone.
WaterGAP2-2e publishes four candidates and they differ by a factor of five over
cropland (area-weighted median, mm/yr): groundwater recharge `qr` 74.8, subsurface
runoff `qsb` 75.2, surface runoff `qs` 83.7, **total runoff `qtot` 177.8**.

The map used `qr` until August 2026. `qr` is *exactly zero* on 0.10% of cropland
area, all of it in river deltas where the water table is at the surface — 23% of
the Mekong Delta's cropland, 24% of the Red River delta, 4% of the middle Yangtze
drew as "negligible potential" in some of the wettest cropland on Earth. WaterGAP
is right that nothing percolates to an aquifer there; the water still leaves the
field laterally to canals with its bicarbonate in it. Zero recharge is not zero
drainage.

`qsb` is not the fix. In WaterGAP, recharge feeds the groundwater store and the
store discharges as baseflow, so a 30-year mean `qsb` is `qr` relabelled (global
land medians 33.5 vs 32.6 mm/yr). It clears the deltas and creates worse zeros
where groundwater is pumped: 26% of the Indo-Gangetic Plain and 4% of the US Corn
Belt, taking the negligible class from 0.79% to 6.60% of cropland area.

**`qtot` is the default.** Maher & Chamberlain fit `D_w` against catchment
discharge per unit area, which *is* `qtot`, so driving a `qtot`-calibrated `D_w`
with recharge penalises the flux twice — the same double-counting logic as
`DAMKOHLER_TAU_APPLIED_IN_ETA`. It also fixes the defect without creating another:
negligible class 0.79% → 0.10% of area, every delta clears, no region worsens, and
the >90%-weathered tail only moves 0.63% → 0.77%.

The counter-argument, which is why `qr` is kept as a reported sensitivity: surface
runoff has little contact time with topsoil rock, so `qtot` credits water that
arguably weathered nothing. Against it, `D_w` is an *effective* catchment-scale
parameter that already absorbs the distinction. Read the two as a bracket —
2.15 (`qr`) to 2.49 (`qtot`) GtCO₂/yr global gross, printed every build as gate 2d.

Gate 2c enforces the impossibility that `qr` violated: a cell receiving more than
1,000 mm/yr of rain cannot drain less than 1 mm/yr. Currently 0.024% of cropland
area, against a 0.05% allowance for 0.5° cells straddling a wet/arid boundary.
`scripts/analysis/drainage_variable.py` reproduces all of it.

### Monthly integration

The rate is computed **each month and the rate averaged**, never the drivers.
Two reasons, the second larger: the rate is convex in temperature so the mean of
the rate exceeds the rate at the mean (Jensen); and weathering needs warm *and*
wet simultaneously, which annual means destroy. Measured effect: median 1.04,
range 0.89–1.33 — smaller than the ~1.4 an air-temperature-based estimate
suggests, because soil at 5–15 cm is strongly damped.

η_DIC is **rate-weighted** across months, not plainly averaged: the efficiency
that matters is the one operating while dissolution is happening.

### Dissolution: shrinking core, not a bulk exponential

`frac = 1 − exp(−k·X)` was a single first-order decay on the **bulk mass**. The
particle-size distribution entered only through specific surface area, which
scaled the rate; it never shaped the dissolution curve. So the model let the last
10% of the rock dissolve as easily as the first 10%, when physically that last 10%
is the coarse tail with the least surface area per unit mass — and it could reach
100% in a year, which no real grind does.

It is now shrinking core: every particle's surface retreats at the same linear
rate, so after a radial retreat δ a particle of initial diameter d has diameter
max(d − 2δ, 0). The fines vanish early and the coarse tail persists.

    u = δ / d50,    Fw(u, n) = 1 − ∫ f(x)·max(1 − 2u/x, 0)³ dx,   x = d / d50

Fw depends only on u and the width n, which is what lets the browser interpolate a
64 × 13 table instead of integrating (gate 14 bounds that at 0.0019 in fraction,
below the 8-bit step). δ scales linearly with X, anchored so that the reference
grind gives `DISSOLVED_FRAC_AT_REF` at X = 1.

Measured effect on the shipped map, at the reference grind:

| | exponential | shrinking core |
|---|---|---|
| cropland area above 50% weathered | 17.9% | 15.7% |
| above 75% | 7.6% | **4.4%** |
| above 90% | 2.2% | **0.77%** |
| above 99% | 0.15% | **0.01%** |
| p50 / p90 / p99 | 18.0 / 68.7 / 95.0% | 18.7 / 61.8 / 88.4% |

The median barely moves; the extreme tail is cut by about two thirds. Note it does
**not** make 100% unreachable — a cell with 40× the reference reactivity still gets
there, which is a kinetics question rather than a particle-size one.

The integral is untruncated. Truncating at the 1–5000 µm range `ssa_geometric`
uses changes Fw by ≤0.001 for n ≥ 1.5 and by up to 0.03 at n = 0.7, where real mass
sits outside that window.

### Soil moisture: a known defect, stated plainly

`sat_m = moist_m / max(moist_m over the year)` normalises each cell by **its own**
annual maximum, which removes absolute wetness and leaves only seasonal shape. A
uniformly arid cell has flat seasonality and therefore reads as near-saturated.
Measured: the driest 5% of cropland (8.1 mm mean root-zone storage) scores a
*higher* saturation term (0.72) than the wettest 5% (2,194 mm → 0.69). A 272×
range in real water becomes 0.95×.

This is **not** the "porosity normalisation not yet applied" caveat previously
recorded, which describes a missing constant divisor — that would rescale
uniformly and cancel in `reactivity/reference`. A spatially varying rescale does
not cancel.

Fixing it needs porosity or available water capacity to convert mm of storage
into a saturation fraction, and it interacts with the transport term: aridity
currently enters the model only through `η_transport`, so a fix must decide
whether moisture limitation of the *rate* and transport limitation of the
*export* are separate physics or double counting. Substituting a plausible
absolute saturation moves **64% of cropland area** by reactivity decile, so this
is a first-order open item, not a units nicety.

## 2b. The drainage-concentration ceiling — COMPUTED BUT NOT APPLIED

> **Status: switched OFF by default, pending review by the wider ERW community.**
> Everything below is implemented, gated and shipped; it is simply not applied to
> the CO₂ layer by default.
>
> **In the viewer** the bound is a live toggle — Advanced → *Apply the drainage
> limit*. The ceiling is written to `tex2.b` whether or not it is applied, so the
> shader switches it without a rebuild, and every dependent readout follows: the
> footer total, the limiting-factor class, the hover box's "without the drainage
> limit" row, the legend and the Methods text. Turning it on live reproduces the
> build's own figure to the digit (0.91 GtCO₂/yr against the build's 0.910).
>
> **In the derived products** — the `cdr` array, gate 12, the cost screen —
> `constants.FLUX_CEILING_ON = False` remains the switch; flip it to `True` and
> rebuild to apply the bound outside the browser too.
> While it is off, the map's CO₂ figures are **above this bound on 93.0% of
> cropland, by a median factor of 2.9×**, so they should be read as an upper bound
> on dissolution rather than as carbon that can be shown to leave the field. Gate 12
> reports that exceedance on every build rather than letting it disappear with the
> cap. The numbers quoted in this section are what the ceiling *would* impose.


The carbon reported has to leave the field dissolved in the water that leaves the
field. That bounds gross CO₂ removal at `q · [HCO₃⁻]_max · 44` regardless of how
fast the rock dissolves. Before this was imposed the model implied **28.5 mmol/L**
bicarbonate in drainage at the median cropland cell (19.7 mmol/L on the total-runoff
drainage the map now uses; 28.5 was the figure on groundwater recharge).

**What sets `[HCO₃⁻]_max`.** Not the cell's pre-treatment pH. pH is endogenous:
adding base cations at fixed pCO₂ raises alkalinity and pH together, which is the
same carbonate equation η_DIC uses, read the other way. Holding pH fixed gives
0.42 mmol/L at the median — and that figure is, to two significant figures, the
observed mean alkalinity of streams draining **unamended** volcanic rock (Meybeck,
EOLSS *Chemical Characteristics of Rivers*, Table 1A). A good baseline, and exactly
the wrong thing to use as a ceiling, because removing mineral-supply limitation is
what ERW is for.

The bound is where the rising pH meets **carbonate saturation**. Solving charge
balance `2[Ca] + 2[Mg] = [HCO₃⁻]` simultaneously with fixed pCO₂ and calcite
saturation state Ω gives

    [HCO₃⁻]_max = ( 2 · Ω · K₁ · K_H · pCO₂ · K_sp / (f_Ca · K₂) ) ^ (1/3)

The cube root is what makes this robust: being wrong about soil pCO₂ by 5× moves
the ceiling only 1.7×.

**Ω = 10 ships; Ω = 1 is the strict reading and is reported alongside.** Carbonate
precipitation is kinetically inhibited by DOC and phosphate — Zhang et al. 2022
state it "is generally observed to be negligible at Ω < 10" and run their own model
over Ω = 5–25 — and soils carry far more DOC than rivers. The pair spans 0.240 to
0.510 tCO₂/ha/yr at the cropland median, and that spread is the honest uncertainty
on the level.

**Five independent anchors on the resulting 3.0–6.5 mmol/L**, none sharing
assumptions with the closed form:

| anchor | mmol/L |
|---|---|
| Zhang et al. 2022 riverine carbon transport potential, back-converted | 4.3–13.0 |
| Hamilton et al. 2007 Midwest agricultural **tile drainage** and limed-row-crop porewater | 1–7 |
| Meybeck pristine-river 99th percentile | 5.95 |
| Meybeck carbonate-terrain streams | 3.15 |
| soil-pH backstop: holding 10 mmol/L needs pH 8.16 at 4,000 µatm | ~10 |

**Effect, measured.** The ceiling binds on **93.0% of cropland area**; the median
falls 1.589 → 0.510 tCO₂/ha/yr (3.1×). But the level is not the point:

| mean soil T | uncapped | ceiling | exceedance |
|---|---|---|---|
| 0–10 °C | 0.777 | 0.410 | 1.9× |
| 10–15 °C | 1.058 | 0.600 | 1.8× |
| 15–20 °C | 1.566 | 0.447 | 3.5× |
| 20–25 °C | 3.037 | 0.711 | 4.3× |
| 25–45 °C | 3.067 | 0.578 | 5.3× |

`C_eq` **falls** with warming while the rate law rises, so the exceedance is
monotonic in temperature and the warmest/coolest ratio of the median goes from
**3.95× uncapped to 1.41× at the ceiling**. Imposing the bound therefore removes
the map's warm-climate gradient rather than merely rescaling the level, and that is
the most consequential thing about this term.

**It also decouples carbon from application rate, which is the first place this
term changes a deployment decision.** The ceiling depends on drainage and carbonate
chemistry, not on how much rock is on the field. So when the application rate went
from 20 to 30 t/ha in August 2026:

| | 20 t/ha | 30 t/ha |
|---|---|---|
| uncapped median CDR | 1.059 | 1.589 (+50%, linear in rate) |
| **capped median CDR** | **0.478** | **0.510 (+6.6%)** |
| global gross, capped | 0.837 | **0.910 GtCO₂/yr (+8.6%)** |
| cropland area where the cap binds | 82.3% | 93.0% |
| realised carbon per tonne of rock, median cell | 8.3% of stoichiometric | **5.9%** |

**50% more rock bought 8.6% more carbon.** Adding feedstock past the point where
drainage saturates raises the fraction of the map that is transport-limited instead
of raising the tonnage, and it lowers the realised efficiency per tonne. That is a
physical result, not a modelling artefact, and it is the kind of thing an uncapped
rate law cannot say.

The sublinearity was starker on the groundwater-recharge drainage this section was
first written against — 50% more rock bought 1.8% more carbon, and the capped median
did not move at all. Total runoff raises the ceiling in proportion, so it binds on
93.0% of area rather than 98.9% and leaves the rate some room. The direction is
robust to the drainage variable; the magnitude is not, and it is worth knowing that
the most quotable version of this result was the one on the more conservative
water flux.

Two caveats on it. The dissolved *fraction* is held at `DISSOLVED_FRAC_AT_REF`
regardless of rate, so the uncapped layer scales linearly with rate. **Whether that
is wrong, and in which direction, is not known.** An earlier version of this section
claimed the delivery set implied a sublinear exponent near −0.58 and therefore a ~27%
over-credit; checked against the deliveries directly, that is not supported — three
deliveries sharing one feedstock p50 differ only in rate, and two sitting 6% apart in
rate have fractions weathered differing by 2.1×, so the scatter at matched rate and
grind exceeds any rate signal. Recovering the exponent needs the blocked design in
`to_do.md` field-data ask #4. And the flux ceiling is an upper bound on *export*, so it
does not follow that the extra rock is wasted — it may weather and sit in the soil,
which is the retention question in §6 item 1, not this one.

**What it is not.** It is not why the map's level was high. Field trials achieve
0.11–0.75 mmol/L, i.e. **9–60× *below*** this ceiling (median ceiling 6.65 mmol/L),
because cations are retained rather than exported (§6 item 1). This read "5–10×"
until August 2026, which was an arithmetic error rather than a stale number — the
ceiling concentration does not depend on the drainage variable. Correcting it
strengthens the point: trials sit further below the bound than stated, so the bound
explains even less of the level. The ceiling is a rail that makes an impossible
claim impossible; the level is a lab-to-field rate problem and belongs to the
kinetics work.

**Known limitation.** On saturated (paddy) cells the protocol-mandated 50,000 µatm
lifts the ceiling to 13–18 mmol/L at Ω = 10, above every anchor above, and no
measured paddy drainage DIC exists to check it against. Reported by gate 13c rather
than tolerance-fudged; it is the standing justification for field-data ask #6.

Gates: **12** in `build_v0.py` (nothing may report more carbon than its drainage can
carry), **13/13b/13c** in `test_kinetics.py`.

### What "per year" means, and why the year-one figure is the right one

The application rate is stated per year, but the CDR layer is the **first year's
removal from one application**. Those are only the same thing if you reapply every
year, and you cannot: a field takes a multi-year break between applications.

The two errors partly cancel, and it is worth showing how far rather than relying on
it. Run the shrinking-core model forward and the median cell weathers **18.7% in year
one and 78.1% by year ten**, so one application delivers ~4.2× its year-one carbon
over a decade — a 10-year yield of **6.37 tCO₂/ha** at the median. Under a
reapplication interval of *k* years the steady-state annual removal is that yield
divided by *k*:

| reapplication interval | average t/ha/yr | steady-state tCO₂/ha/yr |
|---|---|---|
| every year | 30.0 | 6.37 |
| every 2 years | 15.0 | 3.19 |
| every 3 years | 10.0 | 2.12 |
| **every 4 years** | **7.5** | **1.59** |
| every 5 years | 6.0 | 1.27 |
| every 7 years | 4.3 | 0.91 |
| every 10 years | 3.0 | 0.64 |

The map shows **1.59** tCO₂/ha/yr, which lands on a **four-year** interval. So the
year-one framing still approximates a plausible operational cadence at steady state,
and annual reapplication (6.37) would badly overstate it — but the equivalent cadence
is shorter than the five years this section previously claimed, and a field on a
longer rotation than four years will remove less than the map shows. Stated here
because the "/yr" label otherwise invites reading it as a sustainable annual rate
from annual application, which it is not.

Two corrections behind the shift from five years to four. Most of it is the drainage
variable: on groundwater recharge the year-one fraction was 14.9% and the equivalent
interval 4.5 years. The rest is a construction fix — the earlier table multiplied the
stoichiometric maximum by the *median* 10-year fraction, mixing percentiles from
different cells and overstating the yield by about 6%. The figures above are the
median of the full product, the same chain the map itself evaluates.

### What is grown here

Descriptive only. Crop identity enters the model chain nowhere except rice, and
there only through soil pCO₂ on flooded cells; the readout carries it because ERW
economics, agronomy and protocol eligibility all differ by crop.

Source is SPAM2010 v2.0 **physical** area (harvested double-counts
multi-cropping). All 42 crops are aggregated onto the analysis grid and the two
largest are kept per cell, with the remainder shown as "rest" so the row always
totals 100%.

**Aggregation is area-conserving.** SPAM gives hectares per 5-arcmin cell, an
extensive quantity, so resampling it with `average` onto a coarser grid would
silently rescale it. Each crop is converted to a fraction of its own source cell,
resampled, then multiplied back by the target cell's area — the same pattern the
rice layer already used. Checked: rice, wheat, maize and soybean round-trip to
within 0.05% of their source totals and reproduce the published global physical
areas (113.8 / 199.5 / 151.3 / 97.9 Mha).

**Two crops, not one**, because the dominant crop is a median 46% of a cell's
cropped area — see the table in the README. 99.5% of cropland area gets a named
crop and 96.9% gets a second above the 5% display floor.

Stored in `src/textures/crops.png`, which is **CPU-only** and never reaches the
GPU, like `admin.png`. Four 6-bit fields pack into RGB — `id1 | id2 | share1 |
share2` — with alpha held at 255 because a 2D canvas stores premultiplied colour
and any alpha below 255 would corrupt RGB on the `getImageData` round trip. Shares
therefore quantise to 1.6%, moving a displayed whole percent by at most 0.8
points, which gate 16 asserts. The image is masked to the cropland domain: SPAM
allocates crops to 716k cells against the map's 407k, and the 316k outside can
never be hovered, which is both more honest and most of the file size (1.70 MB
unmasked against 1.10 MB masked).

Gates: **16** in `build_v0.py` (packing round trip), plus a brute-force check in
`prep_layers.py` that re-derives the top two from a full sort over all 42 crops at
50,000 random cells and refuses to write the layer if the streaming result
disagrees.

### Cells with no climate input

695 cropland cells (0.35 Mha, 0.03% of cropland area, almost all high-latitude
Scandinavia) fall inside the cropland mask but have no monthly soil temperature or
moisture, so the rate is undefined there. They used to fall through the texture
encoder's `nan_to_num(L1, nan=−3.0)` and were drawn as near-zero potential —
**missing data rendered as a confident "nothing here"**. They now carry their own
flag bit and are drawn in a distinct grey in every layer, excluded from the
decimated sample, and the hover readout says the cell was not evaluated rather than
showing numbers derived from the NaN fallback.

## 3. Parameters

| Parameter | Value | Basis |
|---|---|---|
| Flux ceiling applied? | **No — off pending review** | `FLUX_CEILING_ON = False`; computed and reported, not applied |
| Application rate | **30 t/ha/yr** | stated assumption; raised from 20 in Aug 2026 to sit nearer commercial practice |
| Feedstock | `delivered_basalt`, 0.289 tCO₂/t | mean implied CO₂ potential of n = 3 verified deliveries, one operator |
| Reference grind | d50 150 µm, Rosin–Rammler width 1.5 | mid-range of observed 67–600 µm p50; **width is assumed** and is narrow for a commercial crush |
| Year-1 dissolved fraction at reference | 0.25 | **the only free parameter.** Nearest the *median* of the eight verified deliveries (26.4%), not the midpoint of their 15.4–55.9% range as previously stated. Those deliveries are not at the reference grind: renormalised they span 8.7–71.3%, median 31.7%. And X = 1 implies η_transport = 1, i.e. infinite drainage — at median cropland drainage the same cell weathers 18.5% |
| Suitability = 100 at | **8.69 tCO₂/ha/yr** | the stoichiometric maximum, `rate × tCO₂/t`, computed. The old 10 was **above** the maximum and so unreachable in every build |
| Fraction-weathered ramp top | **0.65** | readability: p50 is 15%, p90 59%. Clamps 7.3% of area, labelled "≥ 65" |
| D_w | 0.03 m/yr | Maher & Chamberlain 2014, collisional/craton divide; published range 0.001–0.3 |
| Flux-ceiling Ω (calcite) | 10, strict case 1 | precipitation "negligible at Ω < 10", Zhang et al. 2022; both reported |
| Flux-ceiling f_Ca | 0.5 | basalt releases Ca and Mg in roughly equal charge; only Ca constrains calcite |
| Soil pCO₂, unsaturated | 4,000 µatm | Isometric v1.2 §10.4.5.7, mandated |
| Soil pCO₂, flooded | 50,000 µatm | Isometric v1.2, mandated; this is the **floor** of the literature paddy range |
| Flooded pH convergence | 6.7 | van Breemen 1987; submergence drives pH toward 6–7 |
| Quarry gate cost | $10/t | operator-reported quarry-fines prices |
| Truck haul | $0.12/t-km × 1.35 tortuosity | US trade-association rate; **not verified outside the US** |
| Haul penalty scale S | $100/t | editorial choice, stated as such |
| Headline cost screen | **$100/tCO₂**, 10 yr at 5% | applies to the footer total when economics is on; acquisition and haul only, not a levelised cost |
| SOC exclusion | 5 wt%, P > 0.9 | Puro.earth rule 3.9.1(c) |

### Choices that are not forced by physics

- **Absolute breakpoints, not percentiles**, for the suitability value function.
  Min-max collapses a 3–4 order range; percentile manufactures gradient where
  there is none and would make the colour scale move as sliders move. Absolute
  breakpoints keep the scale stable and domain-invariant — at the cost of
  inheriting the level uncertainty directly, which is why a factor-3 level error
  moves the mean score by ~19 points.
- **Cost is compensatory with a floor**, unlike the physical terms. Expensive rock
  is bad, not impossible. It is the first genuinely tradeable factor in the model.
- **The cost penalty applies to the haul increment only.** A site at the gate cost
  takes no penalty, because every site must buy and crush rock and that carries no
  spatial information — so the gate cost cancels out of the map. Note this
  cancellation is only coherent while the gate cost is globally uniform;
  regionalising it (BR $9, IN $3, US $12 are known) would make it real spatial
  information and require revisiting the logic.
- **Iron is excluded from alkalinity.** Fe²⁺ release does raise alkalinity, but in
  an oxic agricultural soil re-oxidation returns the protons, so no durable carbon
  is stored. Both protocols agree. Consequence: fayalite scores zero, augite is
  discounted to 1.6 of a nominal 2.
- **Na and K are excluded**, which is conservative by 11–19% relative to both
  protocols' own oxide lists. Stated as a choice, since the justification cites an
  authority that includes them.

## 4. Sampling

The sidebar's stability diagnostic uses an **area-weighted, decimated** sample:
every 3rd cell in each direction, weighted by `cropland fraction × cos(latitude)`.

- Area weighting is required because uniform sampling of a lat/lon grid
  over-samples high latitudes, which would bias the statistic toward the boreal
  margin. Gate 1b tests the weighting independently by asserting the naive-area
  inflation lands in 20–35%.
- A systematic 1-in-9 lattice is unbiased for a population proportion absent
  periodicity at the stride. Several inputs are nearest-neighbour resampled from
  0.5° (5×5 identical blocks), and 3 and 5 are coprime, so no resonance arises.
- The reported precision is **one significant figure on purpose.** With spatial
  autocorrelation and 5×5 replicated blocks the effective sample is far smaller
  than the cell count, so a decimal place would be false precision.

### The stability metric is rank-based

Each setting is digitised against **its own** area-weighted decile edges, so the
statistic measures re-ranking. Until July 2026 both settings were digitised
against the *baseline's* edges, which reported pure level changes as instability:
a monotone transformation that alters no ranking whatsoever registered ~50%, and
a ×2 level shift registered 85%. The published "63.7% of cropland changes decile"
figure came from that broken metric and is withdrawn; the corrected value for the
same perturbation is ~15%.

## 5. Uncertainty treatment

**SOC exceedance** is computed at ~2.8 km and the **probability** is averaged onto
the analysis grid. Averaging the quantiles first and computing the probability
from those is not valid propagation — it preserves the sub-cell spread where the
true block-average distribution is narrower, inflating σ and pushing mass toward
0.5. Note the averaging makes the result an **expected areal fraction exceeding
the threshold**, not a probability that the cell exceeds; the 0.9 and 0.1
thresholds should be read in those terms.

Two caveats stand either way: SoilGrids quantiles describe a ~250 m **block
average** rather than a sampled field, so field-scale exceedance is understated;
and this is a screening likelihood, not a calibrated eligibility probability.

**Ionic-strength corrections are omitted** from the carbonate system. Soil
solution ionic strength is 0.001–0.05 M and the correction is small relative to
the structural uncertainties in the chain.

## 6. What the model does not contain

Recorded so absence is deliberate rather than accidental. Ordered roughly by
likely effect on the map.

1. **Cation retention in secondary phases — now the largest missing term.**
   Weathered Ca and Mg do not all leave: they are held on exchange sites, in
   reducible Fe/Mn-oxide pools and in neoformed clays. Greenhouse work across 4
   soils × 13 feedstocks found **10–50× more cations retained than exported via
   leachate** (Hammes et al. 2025, EGUsphere 2025-5402), and column work puts the
   retarded fraction at **92.7–98.3%** (te Pas et al. 2025, *Front. Clim.*
   6:1524998). The model has no retention term at all, so it reports the export
   that *would* occur at steady state with no lag. Flagged as item 3 in `to_do.md`,
   and blocked on data rather than on effort — see that entry for what would
   unblock it. Note the modelling and measurement literatures disagree on the
   dominant sink: SMEW attributes the gap primarily to CEC adsorption while the
   two measurement studies find the exchangeable pool is the *minority* sink, so a
   CEC-based term would model the wrong thing.
2. **Strong-acid (nitrogen fertiliser) competition.** The rate law does not care
   which acid supplied the proton, but dissolution driven by HNO₃/H₂SO₄ generates
   no alkalinity. Both protocols treat this as a separate deduction; we carry the
   pH annotation with zero score effect. A 3-year Minnesota trial found base
   cation to alkalinity ratios above 1:1 and often 2:1.
3. **Secondary mineral precipitation**, which is both a real CDR loss and the
   likely cause of the pH 4–8 Mg residual. Pedogenic carbonate returns only half
   the CO₂ per Ca; clay neoformation returns none. Spatially co-directional with
   η_DIC, i.e. the model rewards high pH and does not penalise the sink that grows
   with it.
4. **A base (alkaline) dissolution mechanism.** P&K tabulate none for
   plagioclase (except albite), pyroxenes or olivine, so the model asserts
   monotonic decline with pH — while the repo's own fixture shows measured basalt
   has a minimum around pH 6–9 and rises above it. 40% of cropland is above pH 7.
5. **Basaltic glass**, absent from P&K entirely, present in real feedstock, and
   with a much lower activation energy.
6. **Chemical affinity effects that matter.** Bulk far-from-equilibrium is
   essentially exact for the primary phases (Q/K ~10⁻¹⁶ for forsterite in soil
   water), so a (1 − Q/K) term would buy nothing. What is missing is **Al
   inhibition** (implementable with gridded pH alone under gibbsite buffering) and
   pore-scale saturation, both of which bias the acid end high.
7. **The liming feedback.** ERW raises soil pH, and the map applies a static pH to
   a process whose purpose is to change it.
8. **Supply capacity.** Every quarry is an unlimited point source. At 30 t/ha over
   1,215 Mha the implied demand is **36.3 Gt of rock a year**, which is of the same
   order as total world aggregate production and therefore not a spreadable quantity.
   The 20 → 30 t/ha change made this constraint 1.5× harder while adding almost no
   carbon (see §2b), so it is now the binding practical limit long before geology is.
9. **Road routing and seasonal access.** Haul is great-circle × a constant
   tortuosity, so a monsoon-season Gangetic haul and a Midwest haul are treated
   identically.
10. **Net removal.** Everything reported is gross alkalinity generation.

### Overlays

**Quarry locations** — 5,295 mafic-hosted quarries from three national registers
(US MRDS, Brazil ANM) and OSM. Coverage is very uneven: outside those countries the
absence of a dot means the register does not exist, not that the rock does not.

**Mafic rock outcrop** — GLiM mafic and ultramafic outcrop fraction, drawn on *and
off* cropland because **74% of it is outside the cropland domain** and "is there
feedstock near here" is a question about exactly the land the rest of the map
ignores. It is the better guide where quarry coverage is thin. It is not a quarry:
outcrop says nothing about whether the rock is permitted, crushed or for sale.

Sanity-checked against the flood basalt provinces — Deccan, Siberian Traps,
Columbia River, Paraná and the Ethiopian highlands all return a mafic fraction of
1.00, while the Corn Belt and the Ganges plain return 0.00.

## 7. Deliberate design choices in the viewer

- **Equirectangular, not Web Mercator.** The analysis grid is equirectangular, so
  this avoids a reprojection and its seams, and it refuses Mercator's area
  exaggeration — which matters when the mapped quantity is per-hectare.
- **NEAREST texture sampling.** Bilinear across a bit-packed flag boundary would
  interpolate garbage bit patterns and would invent detail the grid lacks.
- **One colour-ramp array** generates both the legend and the shader ramp, so they
  cannot drift. This is the failure mode that broke a sibling project.
- **The limiting-factor layer is reference-dependent**, and the legend says so.
  The two efficiency terms have a natural zero (efficiency = 1) but the
  dissolution term is measured against a chosen reference condition, and the
  answer moves with it: on the shipped reference (pH 6.5, 15 °C) drainage limits
  the largest share of cropland, while a reference 1 pH unit lower and 10 °C
  warmer makes dissolution dominant. It shows which term is furthest from its
  best case, not an absolute ranking of mechanisms.
