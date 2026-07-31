# Changelog

Development history of the ERW Atlas, including the defects found along the
way and the reasoning behind each reversal. The map's Methods modal describes
the model as it stands; this file describes how it got there. Newest changes
first within each build.

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
units that mean something. At the gate that is $35/tCO₂ gross; at the cropland
median haul, $159.

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

The readout header now names the region under the cursor ("Iowa, United
States") instead of bare coordinates: Natural Earth 10m admin-1 rasterised
onto the analysis grid at build time (`scripts/build_admin_lookup.py`,
~350 KB total), with a ≤3-cell nearest-region fill so coarse-grid coastal
cells inherit the adjacent region rather than showing nothing.
