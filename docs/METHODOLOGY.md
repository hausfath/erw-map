# Methodology

The model chain, its parameters, and the choices that are not forced by physics.
`docs/VALIDATION.md` covers the gates and the pre-registered criteria;
`CHANGELOG.md` covers how the model got here.

For the same material as **equations** rather than prose, build the methodology
report: `python3 scripts/analysis/make_methods_report.py` writes
`docs/methodology_report.tex` and compiles it. It is generated from the same
constants and the same built grid as this file.

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
Belt, taking the negligible class from 1.15% to 6.71% of cropland area.

**`qtot` is the default.** Maher & Chamberlain fit `D_w` against catchment
discharge per unit area, which *is* `qtot`, so driving a `qtot`-calibrated `D_w`
with recharge penalises the flux twice — the same double-counting logic as
`DAMKOHLER_TAU_APPLIED_IN_ETA`. It also fixes the defect without creating another:
negligible class 1.15% → 0.18% of area, every delta clears, no region worsens, and
the >90%-weathered tail only moves 0.24% → 0.31%.

The counter-argument, which is why `qr` is kept as a reported sensitivity: surface
runoff has little contact time with topsoil rock, so `qtot` credits water that
arguably weathered nothing. Against it, `D_w` is an *effective* catchment-scale
parameter that already absorbs the distinction. Read the two as a bracket —
2.10 (`qr`) to 2.43 (`qtot`) GtCO₂/yr global gross, printed every build as gate 2d.

Gate 2c enforces the impossibility that `qr` violated: a cell receiving more than
1,000 mm/yr of rain cannot drain less than 1 mm/yr. Currently 0.024% of cropland
area, against a 0.05% allowance for 0.5° cells straddling a wet/arid boundary.
`scripts/analysis/drainage_variable.py` reproduces all of it.

### Monthly integration

The rate is computed **each month and the rate averaged**, never the drivers.
Two reasons, the second larger: the rate is convex in temperature so the mean of
the rate exceeds the rate at the mean (Jensen); and weathering needs warm *and*
wet simultaneously, which annual means destroy. Measured effect: area-weighted median **1.15**,
p10–p90 1.01–1.34 — smaller than the ~1.4 an air-temperature-based estimate
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
| cropland area above 50% weathered | 18.1% | 15.9% |
| above 75% | 5.5% | **2.6%** |
| above 90% | 1.2% | **0.31%** |
| above 99% | 0.04% | **0.00%** |
| p50 / p90 / p99 | 15.8 / 66.2 / 91.7% | 16.6 / 59.6 / 84.1% |

The median barely moves; the extreme tail is cut by about two thirds. Note it does
**not** make 100% unreachable — a cell with 40× the reference reactivity still gets
there, which is a kinetics question rather than a particle-size one.

The integral is untruncated. Truncating at the 1–5000 µm range `ssa_geometric`
uses changes Fw by ≤0.001 for n ≥ 1.5 and by up to 0.03 at n = 0.7, where real mass
sits outside that window.

### Soil moisture: an absolute saturation, and what it cost to get there

**Fixed 2026-08-24.** Two stacked defects, one of which was hiding the other.

**Defect 1, the normalisation.** The build used to compute
`sat_m = moist_m / max(moist_m over the year)`, normalising each cell by **its
own** annual maximum. That removes absolute wetness and leaves only seasonal
shape, so it did not weaken the aridity signal, it deleted it. Area-weighted over
the 406,991 cropland cells, the term correlated **−0.886** with the coefficient of
variation of monthly storage and only **+0.147** with storage itself. The driest
and wettest 5% of cropland scored **identically, 0.653 both**, across a 272× range
in real soil water — a dry cell is dry all year, so its seasonality is flat, so it
read as saturated. The Nile valley, at 6 mm mean root-zone storage, scored
**0.973**, higher than NW Europe. Worst of all, the Indo-Gangetic Plain holds more
water than the US Corn Belt (746 vs 629 mm) and was down-weighted **36%** against
it purely for having a monsoon, inverting the temperature × moisture covariance
that monthly integration exists to capture.

This was **not** the "porosity normalisation not yet applied" caveat previously
recorded here, which describes a missing constant divisor — that would rescale
uniformly and cancel in `reactivity/reference`. A spatially varying rescale does
not cancel.

**Defect 2, the units, invisible because of defect 1.** TerraClimate stores `soil`
as int16 with `scale_factor = 0.1`, and `rasterio.read()` returns the raw integer.
`fetch_monthly.py` never applied it, so the committed layer was **10× too large**
and its own tag said `scale_factor: 1.0`, making the error self-consistent. It
survived because a constant factor cancels exactly in `moist/max(moist)`. Fixing
the normalisation without fixing this would have produced a saturation term 10×
too large, i.e. clipped to 1 almost everywhere. Confirmed independently of the
metadata: as-built annual-maximum storage had a cropland median of 680 mm and
exceeded SoilGrids root-zone plant-available capacity on **87.9%** of cropland
area, impossible for extractable water. Scaled, the median is 68 mm against a
141 mm capacity.

A related tripwire, checked and found inert: `hi_valid=5000.0` was written meaning
5000 mm but bit at 500 real mm. Nothing in the written product exceeds it and
**0.000%** of land area lost a month, so re-tagging the committed raster is exactly
equivalent to re-downloading 1.1 GB. The validity range is now expressed in real
mm.

**The fix is a chain, not a divisor.** TerraClimate reports *extractable* storage
in mm — water above the wilting point — so it cannot be divided by a capacity and
called a saturation. Three steps, each with its own denominator from SoilGrids
water retention integrated over 0–100 cm (`wv0033`, `wv1500`, `bdod`):

```
f     = clip(storage_mm / (fc_mm − wp_mm), 0, 1)     fraction of plant-available
θ     = θ_wp + f · (θ_fc − θ_wp)                    absolute water content
S     = θ / θ_sat,   θ_sat = 1 − ρ_b/2.65           degree of saturation
```

This answers the question this section used to leave open — field capacity,
saturation, or plant-available water, which differ by ~2×. **None of them alone.**
Field capacity and wilting point *bracket* the range the storage occupies; pore
volume is the denominator that turns a content into a saturation. Cropland medians
over 0–100 cm: FC 308 mm, WP 138 mm, plant-available 154 mm, pore volume 487 mm.

**What this term is for, and what it is not for.** Because θ has a wilting-point
floor, S spans only ~0.34–1.0 over cropland, so the reactivity spread it produces
(1.21 dex p10–p90) is no wider than the broken term's (1.23 dex). That is a
*result*, not a failure to fix anything: the moisture term is a modest
wetted-surface-area modulator and **it should not be asked to carry the aridity
signal**. Dissolution does not stop at the wilting point — films persist — so a
term that falls to ~0 in the Nile valley (a `clip(storage/300 mm)` stand-in gives
0.021) is *more* wrong than one giving 0.31.

Measured alternatives, all re-running the monthly integration:

| definition | mean S | p10–p90 spread | area changing decile | rank corr |
|---|---|---|---|---|
| self-normalised (removed) | 0.546 | 1.23 dex (17×) | — | 1.000 |
| `clip(storage/300mm)` stand-in | 0.706 | 1.63 dex (43×) | 64.3% | 0.864 |
| extractable / plant-available | 0.336 | 2.11 dex (130×) | 71.2% | 0.833 |
| **θ/θ_sat, shipped** | **0.476** | **1.21 dex (16×)** | **58.5%** | **0.930** |
| no moisture term (ensemble bracket) | 1.000 | 1.11 dex (13×) | 58.1% | 0.956 |

The last row is the one worth sitting with: simply *deleting* the old term
rearranged 58.1% of cropland area by decile against 64.3% for replacing it, which
is how little signal it carried. `MOISTURE_TERM = "none"` ships that bracket.

**Gate 2e** now requires the term to be monotone in wetness — wettest 5% over
driest 5% ≥ 1.25 and correlation with log₁₀ storage ≥ 0.50 — and fails any
per-cell normalisation. It reads 0.333 (1 mm) vs 0.625 (205 mm), ratio 1.88, corr
+0.575.

**Linearity in S is a convention, not a result.** Nothing in the literature
constrains the exponent for mineral dissolution in soils, and wetted surface area
plausibly saturates well below full saturation, which argues for `S**b` with
b < 1. Shipped at b = 1 (`MOISTURE_EXPONENT`), with b in the ensemble.

**Two limitations that these inputs cannot close.** TerraClimate publishes *Soil
Moisture at End of Month*, an instantaneous state used here as a monthly mean. And
the drainage `q` comes from WaterGAP `histsoc`, which simulates irrigation return
flow, so `η_transport` sees irrigation while a rain-fed soil-water balance does
not — hence the Nile valley reading dry on a field that is in fact wet. Every
irrigated cell therefore has a moisture term and a drainage term that disagree
about how wet it is. Closing this needs an irrigation mask as a third input.

### Where the aridity signal actually lives: the ceiling, not D_w

An earlier version of this section claimed the map had no aridity signal and that
`D_w` was the blocking item. Measured, that was wrong on both counts.
`scripts/analysis/dw_sensitivity.py` sweeps `D_w` over three orders of magnitude:

| `D_w` m/yr | η_tr mean | η_tr >0.8 | wet/dry **uncapped** | wet/dry **capped** | Gt uncapped | Gt capped |
|---|---|---|---|---|---|---|
| 0.001 | 0.984 | 99.3% | 3.2× | **125.3×** | 2.77 | 0.893 |
| 0.010 | 0.899 | 86.9% | 5.5× | **125.1×** | 2.63 | 0.892 |
| **0.030** (shipped) | **0.787** | **62.4%** | **9.9×** | **124.8×** | **2.43** | **0.888** |
| 0.100 | 0.593 | 21.4% | 23.9× | **124.0×** | 2.04 | 0.874 |
| 0.300 (published max) | 0.379 | 1.8% | 58.7× | 131.4× | 1.52 | 0.817 |
| 1.000 | 0.182 | 0.1% | 148.1× | 179.7× | 0.91 | 0.659 |

Wet/dry compares the area-weighted mean of the wettest 5% of cropland by drainage
against the driest 5% — a 141× contrast in `q` itself, and 149× in the ceiling.

**Two corrections fall out.** First, η_transport in isolation is the wrong quantity
to judge: it spans only 4.4× wet-to-dry, but delivered carbon spans **9.9×**
uncapped, because the dissolution response to X is nonlinear. Second and more
important, **with the ceiling applied the contrast is 125× and does not depend on
`D_w` at all** — 125.3× at 0.001 against 124.8× at 0.03. The ceiling is linear in
`q` and binds on 95.1% of cropland area, so it has already taken the aridity signal
over.

So the aridity bottleneck *is* represented in this model, by the
drainage-concentration ceiling described in §2b — **applied by default since
2026-08-24**. `D_w` matters only for the uncapped map, which is now the
sensitivity case (the top-level toggle, off) rather than the default.

**`D_w` is therefore not being retuned.** Maher & Chamberlain state 0.3 m/yr as a
global maximum, the shipped 0.03 is their craton/collisional divide, and there is
no basis in this sweep for moving off a published fit — moving it would be tuning
a parameter to produce a contrast the binding constraint already supplies. The
argument that crushed feedstock justifies a higher effective `D_w` than natural
saprolite still stands on its own merits and is recorded in `constants.py`; it is
just not an aridity argument.

What does remain open is whether the aridity response should be *shaped* like
Calabrese et al.'s Budyko formulation rather than emerging from a q-linear
ceiling. That needs the paper read and PET as an input; neither is done. (The
citation itself is still unverified — see `constants.py`.)

## 2b. The drainage-concentration ceiling — APPLIED BY DEFAULT SINCE 2026-08-24

> **Status: ON.** Held out of the defaults 2026-08-03 → 2026-08-24 pending
> review by the wider ERW community; applied by default once the first external
> corroboration arrived (Mayer et al. 2025 — see the validation subsection
> below). The CO₂ layer, the footer totals, the cost screen and every derived
> product are now capped at this bound.
>
> **In the viewer** the bound is a live top-level toggle — *Apply the drainage
> limit*. The ceiling is written to `tex2.b` whether or not it is applied, so the
> shader switches it without a rebuild, and every dependent readout follows: the
> footer total, the limiting-factor class, the hover box's "without the drainage
> limit" row, the legend and the Methods text. Switching it off shows the
> uncapped pre-review behaviour, in which the map's CO₂ figures exceed this
> bound on **95.1% of cropland by a median factor of 3.8×** and should be read
> as an upper bound on dissolution rather than carbon shown to leave the field.
>
> **In the derived products** — the `cdr` array, gate 12, the cost screen —
> `constants.FLUX_CEILING_ON = True` is the switch; set it to `False` and
> rebuild to remove the bound outside the browser too.


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

The bound is where the rising pH meets **carbonate saturation**. Since 2026-08-24
the solve is the structure of Mayer et al. 2025 (see below): dissolved Mg is held
**explicit** at an observed value — it has no solubility control at surface
temperature, so it is set by feedstock release and bounded by field measurements
(~1 mM in basalt mesocosm leachate, up to 5 mM for olivine-rich dunite) — and only
Ca is constrained by calcite. Charge balance `2[Ca] + 2[Mg] = [HCO₃⁻]` with fixed
pCO₂ and calcite saturation state Ω gives the cubic

    A³ − 2[Mg]·A² − 2 · Ω · K₁ · K_H · pCO₂ · K_sp / (γ₂ γ₁² · K₂) = 0,  A = [HCO₃⁻]_max

with Davies activity coefficients γ iterated on ionic strength (I = 1.5·A). At
[Mg] = 0 and unit activities this reduces to the closed form the map used
2026-08-03 to 2026-08-24 (with f_Ca tying Mg to Ca as a fixed charge share). The
near-cube-root is what makes this robust: being wrong about soil pCO₂ by 5× moves
the ceiling only ~1.7×.

**External validation and parameter centering — Mayer et al. 2025.** Terradot's
science team independently published this same bound as "carrying capacity"
(J_CDR = recharge × [DIC]_max; Research Square preprint,
doi:10.21203/rs.3.rs-7811095/v1, posted 2025-12-16), with [DIC]_max from PHREEQC
(wateq4f) over soil pCO₂ 5,000–20,000 ppmv × calcite SI 0–1 × Mg 0–5 mM ×
temperature. Three points of contact, all checked:

1. **Chemistry.** Our solve reproduces all 54 of their PHREEQC cases to
   **0.95–1.00** (median 0.974), pH within ±0.19, with the expected small low
   bias from neglected ion pairs — gate 13d asserts it on every test run, from
   `tests/fixtures/mayer2025_tableS1.csv`. The temperature slope matches their
   Fig. 4 (−26% alkalinity from 5 → 25 °C at their central case).
2. **Parameters.** The shipped central is now **their** central case: calcite
   SI = 0.5 (Ω ≈ 3.16, the saturated-to-slightly-supersaturated state observed
   in amended pore waters, Buckingham & Henderson 2024) and Mg = 1 mM
   (basalt-typical). Ω = 1 remains the strict reading; Ω = 10 (Zhang et al.
   2022's river-inhibition threshold, the shipped default until 2026-08-24)
   becomes the permissive end. Strict-to-central spans 0.290–0.395 tCO₂/ha/yr
   at the cropland median, and that spread is the honest uncertainty on the
   level. pCO₂ stays per-cell (4,000 µatm drained → 50,000 saturated, the
   Isometric protocol values), which brackets their 5,000–20,000 scenario band.
3. **Global integral.** Evaluating our grid under their central configuration
   (recharge for q, uniform 10,000 µatm, SI 0.5, Mg 1 mM) gives
   **0.359 GtCO₂/yr on cropland against their published 0.34** (their full
   geochemical range: 0.15–0.85) — a 6% agreement from disjoint datasets
   (WaterGAP vs Mohan et al. 2018 recharge, SPAM vs Dynamic World cropland,
   soil-T climatology vs MODIS 2024). Reported by the build on every run.

Two framing points adopted from them, and two differences kept. Adopted: this is
the **maximum-efficient** level, not an absolute cap — past it, calcite
precipitation halves marginal efficiency (a precipitated Ca carries one carbon
rather than balancing two bicarbonates) instead of stopping removal; and Mg-rich
feedstocks raise the ceiling (their headline sensitivity; here that is the
`mg_mM` parameter, 0 → 5 mM spans 4.2 → 10.8 mmol/L at 4,000 µatm, 15 °C). Kept:
our q is total runoff (their recharge is our qr sensitivity case — see §on
drainage variables), and our exported carbon counts alkalinity only, not their
~5% CO₂(aq) inclusion. Caveat kept in view: it is a company-funded preprint, not
yet peer-reviewed.

**Five independent anchors on the resulting 3.7–7.1 mmol/L** (Ω 1–10 at
4,000 µatm, 15 °C), none sharing assumptions with the closed form:

| anchor | mmol/L |
|---|---|
| Zhang et al. 2022 riverine carbon transport potential, back-converted | 4.3–13.0 |
| Hamilton et al. 2007 Midwest agricultural **tile drainage** and limed-row-crop porewater | 1–7 |
| Meybeck pristine-river 99th percentile | 5.95 |
| Meybeck carbonate-terrain streams | 3.15 |
| soil-pH backstop: holding 10 mmol/L needs pH 8.16 at 4,000 µatm | ~10 |

**Effect, measured** (at the Mayer-central parameters, 2026-08-24 build). The
ceiling binds on **95.1% of cropland area**; the median falls 1.396 → 0.395
tCO₂/ha/yr (3.5×). But the level is not the point:

| mean soil T | uncapped | ceiling | exceedance |
|---|---|---|---|
| 0–10 °C | 0.746 | 0.309 | 2.4× |
| 10–15 °C | 1.026 | 0.458 | 2.2× |
| 15–20 °C | 1.532 | 0.344 | 4.5× |
| 20–25 °C | 3.021 | 0.554 | 5.5× |
| 25–45 °C | 3.549 | 0.456 | 7.8× |

`C_eq` **falls** with warming while the rate law rises, so the exceedance rises
nearly monotonically with temperature and the warmest/coolest ratio of the median
goes from **4.75× uncapped to 1.47× at the ceiling**. Imposing the bound therefore
removes most of the map's warm-climate gradient rather than merely rescaling the
level, and that is the most consequential thing about this term.

**It also decouples carbon from application rate, which is the first place this
term changes a deployment decision.** The ceiling depends on drainage and carbonate
chemistry, not on how much rock is on the field. So when the application rate went
from 20 to 30 t/ha in August 2026:

| | 20 t/ha | 30 t/ha |
|---|---|---|
| uncapped median CDR | 0.931 | 1.396 (+50%, linear in rate) |
| **capped median CDR** | **0.385** | **0.396 (+2.7%)** |
| global gross, capped | 0.669 | **0.711 GtCO₂/yr (+6.3%)** |
| cropland area where the cap binds | 88.1% | 95.1% |
| realised carbon per tonne of rock, median cell | 6.6% of stoichiometric | **4.6%** |

**50% more rock bought 6.3% more carbon.** Adding feedstock past the point where
drainage saturates raises the fraction of the map that is transport-limited instead
of raising the tonnage, and it lowers the realised efficiency per tonne. That is a
physical result, not a modelling artefact, and it is the kind of thing an uncapped
rate law cannot say.

The strength of the sublinearity tracks the ceiling's level: on the
groundwater-recharge drainage this section was first written against, 50% more rock
bought 1.8% more carbon and the capped median did not move at all; on total runoff
under the pre-2026-08-24 Ω = 10 parameters it bought 10.0%; at the Mayer-central
parameters, whose lower ceiling binds on 95.1% of area, it buys 6.3%. The direction
is robust to every parameterisation tried; the magnitude is not.

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
0.11–0.75 mmol/L, i.e. **7–46× *below*** this ceiling (median ceiling 5.09 mmol/L
at the Mayer-central parameters), because cations are retained rather than
exported (§6 item 1). The ceiling is a rail that makes an impossible
claim impossible; the level is a lab-to-field rate problem and belongs to the
kinetics work.

**Paddy-field view (Advanced toggle, 2026-08-24).** The map's f_flood is a cell
mean — GRPI inundation months × SPAM rice area — which is correct for a cell
average and systematically dilute for a *project*, whose fields are all paddy.
The viewer therefore carries a second texture (tex5) with L1, η_DIC and the
ceiling recomputed at 100% paddy area (the cell's observed inundation months
kept), on exactly the baseline encodings, so the toggle is a byte-source swap
that composes with every other control. On the 41,711 paddy-bearing cells the
ceiling rises ×1.59 (median) and the drainage class clears on 23% of them
(concentrated where inundation runs most of the year: the Bengal delta, SE
Asia); central India stays drainage-limited even at full paddy chemistry,
because dissolution there outruns the protocol-pCO₂ ceiling. Off-paddy cells
are byte-identical by construction and asserted at build time. For
field-level project screening beyond the toggle (pathway-split water, measured
pCO₂ range, baseline netting), see `scripts/analysis/paddy_ceiling_india.py`
and `docs/PADDY_CEILING_INDIA.md`.

**The pH-target basis (viewer option, 2026-08-26).** The saturation basis lets
pore water rise to calcite saturation, which on drained cropland means
pH 7.7–7.9 — agronomically basic, and operating at Ω ≈ 3 on a kinetic-
inhibition argument. The sidebar therefore offers a stricter basis: pore water
held at **pH ≤ 7.5** (in-situ at field pCO₂), which keeps calcite Ω ≈ 0.3 on
drained cropland — no precipitation risk by construction — and reads the
alkalinity off the same open-system relations with the pH pinned instead of Ω
(`kinetics.alkalinity_at_ph_mol_l`, gate 13e asserts the two are the same
relation). Saturation still binds first wherever its pH is below the target,
which is the high-pCO₂ paddy case, so paddies are barely touched and the cut
falls on drained temperate cropland. Global steady state on this basis:
**0.442 GtCO₂/yr against 0.717 at saturation** (7.0 / 7.25 / 7.75 targets give
roughly 0.15 / 0.26 / 0.62). The **headline stays on saturation** — it is the
published Mayer et al. 2025 anchor — and the footer labels the basis whenever
the option is selected. One conversion trap, stated in the constant and the
function: the target is an in-situ pore-water pH at field pCO₂, roughly 0.5–1
unit *below* the same soil's lab-paste pH, and alkalinity moves ~10× per pH
unit — do not retune it against agronomic (lab-basis) pH targets without
converting.

**Known limitation.** On saturated (paddy) cells the protocol-mandated 50,000 µatm
lifts the ceiling to 9.6–13.3 mmol/L at the shipped central (6.6–13.3 including
the strict case), at or above every anchor above, and no measured paddy drainage
DIC exists to check it against. Reported by gate 13c rather than tolerance-fudged;
it is the standing justification for field-data ask #6.

Gates: **12** in `build_v0.py` (nothing may report more carbon than its drainage can
carry), **13/13b/13c** in `test_kinetics.py`.

### What "per year" means: two bases, one per surface

Since August 2026 the tool carries two time bases deliberately. The **map layers
and hover readout are year-1** — the first year's removal from one application,
the quantity field trials can measure. The **footer total is a steady state**:
hold 30 t/ha of undissolved rock on each field, reapplying as the modelled
kinetics dissolve it (renewal theory: sustainable application rate =
min(1, u₁/I∞) applications per year, I∞ = ∫(1−Fw)du = 0.144 the mean-lifetime
constant of the reference grind), capped at one full application per year. The
two nearly coincide globally — 2.60 against 2.43 GtCO₂/yr, within 7% — because
fresh rock dissolves faster per tonne while a maintained stock is continuously
replenished, and the effects almost cancel. They differ regionally with
weathering speed: fast tropical cells run at the annual cap (Brazil's cadence
potential is 34% above its year-1), slow cool cells reapply every decade or two
(Russia's is 29% below). The build prints the steady-state reference every run,
and the footer must reproduce it to its ~0.5% sampling error. The economic
screen moved with it: delivered cost is tested against each application's
**discounted lifetime carbon** (5%, capped at 60 years), not a 10-year window.

**The screen and the drainage limit compose deliberately (2026-08-24, with the
limit shipped on).** The screen is a *unit* cost, and carbon is linear in the
application rate, so $/tCO₂ is rate-invariant: an operator on a cap-bound cell
applies less rock — down to the largest inventory the drainage can carry — at
the same cost per tonne of carbon. The screen's lifetime carbon is therefore
**not clamped by the ceiling** (clamping it priced a full 30 t/ha against
carbon the model says cannot leave, roughly doubling median $/tCO₂ and
collapsing the sub-$100 area 0.27 → 0.05 Gha for no economic reason), while
the carbon *counted* in the footer **is capped**. The screen decides where
hauling rock is economic at all; the drainage limit decides how much carbon
each kept hectare then yields. Under the $100 screen: 0.24 GtCO₂/yr on
0.27 Gha (the same 0.27 Gha the screen kept before the ceiling shipped, as
the unit-cost argument requires).

The rest of this section explains the year-1 basis the map layers keep.

The CDR layer is the **first year's removal from one application**. Stating the
application rate per year and drawing year-1 removal are only the same thing if
you reapply every year, and you cannot: a field takes a multi-year break between
applications.

The two errors partly cancel, and it is worth showing how far rather than relying on
it. Run the shrinking-core model forward and the median cell weathers **16.6% in year
one and 73.8% by year ten**, so one application delivers ~4.3× its year-one carbon
over a decade — a 10-year yield of **6.04 tCO₂/ha** at the median. Under a
reapplication interval of *k* years the steady-state annual removal is that yield
divided by *k*:

| reapplication interval | average t/ha/yr | steady-state tCO₂/ha/yr |
|---|---|---|
| every year | 30.0 | 6.04 |
| every 2 years | 15.0 | 3.02 |
| every 3 years | 10.0 | 2.01 |
| **every 4 years** | **7.5** | **1.51** |
| every 5 years | 6.0 | 1.21 |
| every 7 years | 4.3 | 0.86 |
| every 10 years | 3.0 | 0.60 |

The map shows **1.40** tCO₂/ha/yr, which lands between the four- and five-year
intervals at an equivalent cadence of **4.3 years**. So the year-one framing still
approximates a plausible operational cadence at steady state, and annual
reapplication (6.04) would badly overstate it — but a field on a longer rotation
than about four years will remove less than the map shows. Stated here because the
"/yr" label otherwise invites reading it as a sustainable annual rate from annual
application, which it is not.

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
| Flux ceiling applied? | **Yes — since 2026-08-24** | `FLUX_CEILING_ON = True`; held off 2026-08-03 → 2026-08-24 pending review, applied once Mayer et al. 2025 corroborated the bound |
| Application rate | **30 t/ha/yr** | stated assumption; raised from 20 in Aug 2026 to sit nearer commercial practice |
| Feedstock | `delivered_basalt`, 0.289 tCO₂/t | mean implied CO₂ potential of n = 3 verified deliveries, one operator |
| Reference grind | d50 150 µm, Rosin–Rammler width 1.5 | mid-range of observed 67–600 µm p50; **width is assumed** and is narrow for a commercial crush |
| Year-1 dissolved fraction at reference | 0.25 | **the only free parameter.** Nearest the *median* of the eight verified deliveries (26.4%), not the midpoint of their 15.4–55.9% range as previously stated. Those deliveries are not at the reference grind: renormalised they span 8.7–71.3%, median 31.7%. And X = 1 implies η_transport = 1, i.e. infinite drainage — at median cropland drainage the same cell weathers 18.5% |
| Suitability = 100 at | **8.69 tCO₂/ha/yr** | the stoichiometric maximum, `rate × tCO₂/t`, computed. The old 10 was **above** the maximum and so unreachable in every build |
| Fraction-weathered ramp top | **0.65** | readability: p50 is 15%, p90 59%. Clamps 7.3% of area, labelled "≥ 65" |
| D_w | 0.03 m/yr | Maher & Chamberlain 2014, collisional/craton divide; published range 0.001–0.3 |
| Flux-ceiling Ω (calcite) | 10^0.5 (SI 0.5), strict case 1, permissive 10 | central = Mayer et al. 2025 / Buckingham & Henderson 2024 observed pore-water saturation; permissive = Zhang et al. 2022 inhibition threshold |
| Flux-ceiling dissolved Mg | 1 mM (range 0–5) | explicit, basalt-typical (Vienne 2022); Mg escapes the calcite constraint, so Mg-rich feedstock raises the ceiling |
| Flux-ceiling activities | Davies, iterated | validated against Mayer et al. 2025's 54 PHREEQC cases to 0.95–1.00 (gate 13d) |
| Ceiling basis | calcite saturation (headline); pH ≤ 7.5 pore-water target as a viewer option | pH basis keeps Ω ≈ 0.3 (no precipitation risk); 0.442 vs 0.717 GtCO₂/yr |
| Soil pCO₂, unsaturated | 4,000 µatm | Isometric v1.2 §10.4.5.7, mandated |
| Soil pCO₂, flooded | 50,000 µatm | Isometric v1.2, mandated; this is the **floor** of the literature paddy range |
| Flooded pH convergence | 6.7 | van Breemen 1987; submergence drives pH toward 6–7 |
| Quarry gate cost | $10/t | operator-reported quarry-fines prices — a **current-procurement** (byproduct) price. At scale, dedicated basalt runs $15–22/t in the US/Europe (US traprock averages $21.33/t, USGS 2023); see `docs/GATE_COST_AT_SCALE.md`. Slider spans $0–25 |
| Truck haul | regional $/t-km (US/CA 0.10, EU 0.09, BR/LatAm 0.055, IN/S Asia 0.045, CN/SE Asia 0.07, Africa 0.11, else 0.08) on road km + 50 km fixed-trip equivalent ($2.25–5.50/t regionally), × 1.35 tortuosity | per-entry sources and vintages in `constants.TRUCK_RATE_GROUPS` and `docs/TRUCK_RATE_SOURCES.md`; only the US rate is a current primary. Live multiplier under Advanced; see §3b |
| Haul penalty scale S | $100/t | editorial choice, stated as such |
| Headline cost screen | **$100/tCO₂** against each application's discounted lifetime carbon at 5% | applies to the footer total when economics is on; acquisition and haul only, not a levelised cost. Was a 10-yr window until Aug 2026. A unit cost, unclamped by the drainage limit (the counted carbon is capped) — prices the drainage-optimal application |
| SOC exclusion | 5 wt%, P > 0.9 | Puro.earth rule 3.9.1(c) |

### 3b. The haul model: regional rates plus a fixed per-trip trucking charge

Until August 2026 haulage was one global number, $0.12/t-km, flagged in
`constants.py` as an assumption with no citation. Sourcing it
(`docs/TRUCK_RATE_SOURCES.md`) produced two findings, and both are now in the
model rather than in a caveat:

**1. The rate is regional, and the old error was structured.** USDA grain-truck
rates (Q2 2026, 25 t payload) make $0.10–0.12/t-km a genuinely good current US
number at the map's 171-mile median haul — and NITI Aayog 2021 puts India at
~$0.045–0.05, the World Bank's corridor survey (2007, CPI-inflated) puts Brazil
near $0.055. So the uniform $0.12 was right in the US and ~2–2.5× high in the two
countries with the most ERW deployment. Since the gate cancels out of `v_cost`,
the truck rate is the only cost parameter doing spatial work: the bias mapped
straight into suitability-with-cost, against exactly the cropland the physics
favours. The shipped surface is now `r(region)`, rasterised from Natural Earth
countries at cost-build time (`prep_feedstock.py --cost-only` rebuilds it without
re-downloading the lithology archives), with per-entry sources and vintages in
`constants.TRUCK_RATE_GROUPS`. Only the US entry is a current primary; Brazil,
China and Europe rest on 2007 corridor prices inflated by US CPI, India on a 2021
national average, and the `elsewhere` default of $0.08 is a judgment call, not a
sourced figure.

**2. Haul has a fixed component, priced regionally.** The USDA per-mile rate
falls with distance — $0.187/t-km at 25 miles, $0.120 at 100, $0.102 at 200 —
exactly the signature of a per-trip cost (loading, unloading, positioning)
spread over more km. Decomposed: fixed $3.6–6.0/t plus $0.083–0.098/t-km
marginal, i.e. an implied `F/r` of 37–72 km. The model prices it at the
midpoint, as a **km-equivalent**: `cost = gate + r(region)·(d + 50 km)`. The
form matters: trip *time* (~45 min under the loader, tipping, positioning) is
roughly universal, but its *price* follows the local hourly trucking cost —
which is what `r` embodies — so the fixed charge is $5.00/t in the US, $4.50 in
Europe, $2.75 in Brazil, $2.25 in India, $5.50 in Africa. (A first version
shipped it as a flat global $5/t, which priced an Indian driver's half-hour at
US wages; superseded the same week.) A pure `rate × distance` model understates
short hauls and overstates long ones; the fixed charge fixes the shape, and it
means `v_cost` peaks at `1/(1 + r·50/S)` — 0.948 (Africa) to 0.978 (India) — at
zero distance rather than 1: even a farm beside the quarry pays the truck's
loading and tipping time. **No double count with the gate:** the gate price is
f.o.b. quarry, which includes the *quarry's* loading service; the trip charge is
the *hauler's* fixed cost, decomposed from trucking rates that exclude the
commodity. Different party, different invoice. The gate still cancels
exactly.

Measured on the shipped build: cropland delivered cost is **$16 / $34 / $100**
(p10/p50/p90), against $14/$43/$123 under the old model — cheaper across the
Global South, floored at gate + r·50 km ($12.25–15.50/t regionally) near
quarries. Per tonne of CO₂ that is $42–54 gross at gate-plus-trip-charge and
$118 at the cropland median.

The two Advanced controls are deliberately asymmetric and the UI says so:

- **The haul-rate multiplier moves the map.** It scales the regional per-km rates
  together (×0.25–2.5; cropland median delivered cost runs $16–70/t across it),
  *including* the fixed trip charge — which is time priced at the market level
  the multiplier represents. (A first version spared the fixed charge from the
  multiplier, confusing universal *time* with regional *cost*; reversed when the
  charge was regionalised.) The multiplier range is an **exploration bracket,
  not a confidence interval**.
- **The gate cost does not move the map**, because `v = 1/(1 + (cost − gate)/S)`
  is independent of the gate by construction. It moves the reported $/t and
  $/tCO₂, and through the $/tCO₂ screen it moves the headline total.

`tests/cost_sliders.mjs` asserts: the multiplier rescale of the baked texture is
the bit-exact identity at ×1; reported $/t at defaults reproduces the build's own
decomposition on every encodable byte; the gate shifts reported cost by exactly
the gate delta and cannot touch `v_cost`; a zero-distance cell in every rate
group reports gate + m·r·50 km; and the GLSL uses the same expression as the
JS.

**Still unvalidated.** There is no cost gate in `build_v0.py` and no comparison
against delivered costs in the verified-delivery fixture — benchmarked is not
calibrated, and the distance under the rate is still great-circle × 1.35, not
routed.

### Choices that are not forced by physics

- **Absolute breakpoints, not percentiles**, for the suitability value function.
  Min-max collapses a 3–4 order range; percentile manufactures gradient where
  there is none and would make the colour scale move as sliders move. Absolute
  breakpoints keep the scale stable and domain-invariant — at the cost of
  inheriting the level uncertainty directly, which is why a factor-3 level error
  moves the mean score by ~19 points.
- **Cost is compensatory with a floor**, unlike the physical terms. Expensive rock
  is bad, not impossible. It is the first genuinely tradeable factor in the model.
- **The cost penalty applies to the haul increment only.** The gate cost cancels
  out of the map, because every site must buy and crush rock and that carries no
  spatial information. With the fixed trip charge the increment is
  `r·(d + 50 km) > 0` everywhere, so the multiplier peaks at 0.948–0.978
  (regionally) rather than 1. Note
  the cancellation is only coherent while the gate cost is globally uniform;
  regionalising it (BR $9, IN $3, US $12 are known) would make it real spatial
  information and require revisiting the logic. The *truck rate* being regional
  poses no such problem — it multiplies a distance, so it is spatial information
  by construction.
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
