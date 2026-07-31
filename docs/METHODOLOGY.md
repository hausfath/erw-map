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
Coarse inputs (WaterGAP recharge at 0.5°, paddy layers) use **nearest-neighbour**
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
        ↓  frac = 1 − exp(−k·X)
        ↓  × η_DIC  (carbonate-equilibrium efficiency)
        ↓  × application rate × tCO₂ per tonne
   gross CO₂ removal, tCO₂/ha/yr
        ↓  piecewise-linear value function on absolute breakpoints
   suitability, 0–1
        ↓  × cost multiplier ^ exponent  (off by default)
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
- **The three terms are a product with unit exponents by default**, so zero in any
  required term gives zero carbon. The sliders are **exponents**, not importance
  weights: you cannot prefer dissolution over alkalinity retention because both
  are required multiplicatively.

### Monthly integration

The rate is computed **each month and the rate averaged**, never the drivers.
Two reasons, the second larger: the rate is convex in temperature so the mean of
the rate exceeds the rate at the mean (Jensen); and weathering needs warm *and*
wet simultaneously, which annual means destroy. Measured effect: median 1.04,
range 0.89–1.33 — smaller than the ~1.4 an air-temperature-based estimate
suggests, because soil at 5–15 cm is strongly damped.

η_DIC is **rate-weighted** across months, not plainly averaged: the efficiency
that matters is the one operating while dissolution is happening.

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

## 3. Parameters

| Parameter | Value | Basis |
|---|---|---|
| Application rate | 20 t/ha/yr | stated assumption |
| Feedstock | `delivered_basalt`, 0.289 tCO₂/t | mean implied CO₂ potential of n = 3 verified deliveries, one operator |
| Reference grind | d50 150 µm, Rosin–Rammler width 1.5 | mid-range of observed 67–600 µm p50; **width is assumed** and is narrow for a commercial crush |
| Year-1 dissolved fraction at reference | 0.25 | anchored to field-reported first-period weathering (15–56%) |
| D_w | 0.03 m/yr | Maher & Chamberlain 2014, collisional/craton divide; published range 0.001–0.3 |
| Soil pCO₂, unsaturated | 4,000 µatm | Isometric v1.2 §10.4.5.7, mandated |
| Soil pCO₂, flooded | 50,000 µatm | Isometric v1.2, mandated; this is the **floor** of the literature paddy range |
| Flooded pH convergence | 6.7 | van Breemen 1987; submergence drives pH toward 6–7 |
| Quarry gate cost | $10/t | operator-reported quarry-fines prices |
| Truck haul | $0.12/t-km × 1.35 tortuosity | US trade-association rate; **not verified outside the US** |
| Haul penalty scale S | $100/t | editorial choice, stated as such |
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

1. **A concentration ceiling on the CO₂ flux.** The transport term is a Damköhler
   ratio with no `C_eq`, so nothing enforces that the carbon reported can actually
   be carried at a chemically possible bicarbonate concentration. Measured, the
   median cropland cell would need ~28 mmol/L against ~0.4 mmol/L available. This
   is the largest open problem in the model.
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
8. **Supply capacity.** Every quarry is an unlimited point source. At 20 t/ha over
   1,215 Mha the implied demand exceeds current world crushed-stone production.
9. **Road routing and seasonal access.** Haul is great-circle × a constant
   tortuosity, so a monsoon-season Gangetic haul and a Midwest haul are treated
   identically.
10. **Net removal.** Everything reported is gross alkalinity generation.

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
