# Olivine as a second feedstock, Mg-specific accounting, and multimodal transport

**Status: scoped 2026-09-05; reviewed the same day (`OLIVINE_REVIEWS_2026-09-05.md`);
phases A and B implemented on branch `olivine`. Dispositions of every review finding are
in the reviews file; this plan is left as written except for the two corrections marked.**

Three coupled questions, in the order they should be answered:

1. **Physics.** What does an olivine (dunite) feedstock do to per-hectare removal,
   given a faster rate law, ~3.5× the CO₂ per tonne, and an Mg-dominated cation
   load that changes the drainage ceiling itself?
2. **Constraints olivine brings that basalt does not.** Ni and Cr loading limits on
   cumulative application; a much thinner and more concentrated supply base; an
   Mg-dominated exchange complex.
3. **Transport.** Olivine's CO₂ density makes long-haul, seaborne and rail delivery
   plausible where it is not for basalt. Does modelling port, barge and rail
   delivery change where the economic potential sits?

The map today is basalt-only in three separate places: the kinetics archetype
(`FEEDSTOCK_DEFAULT = "delivered_basalt"`), the ceiling's Mg assumption
(`FLUX_CEILING_MG_MM = 1.0`, feedstock-independent), and the supply/cost layer
(GLiM classes `vb`, `pb` plus mafic-hosted quarries, truck only). All three have to
move together or the result is inconsistent.

---

## 0. Headline hypotheses to test, so the build has something to falsify

- **H1.** Uncapped per-hectare removal for dunite at the same grind is 3–10× basalt
  (forsterite neutral-pH rate ≈ 10^−10.64 vs a basalt mineral mix nearer 10^−11.5 to
  −12 mol m⁻² s⁻¹; CT 1.0–1.1 vs 0.295 tCO₂/t). Delivered cost per tCO₂ falls by
  the CT ratio at equal $/t rock.
- **H2.** Where the drainage limit binds, an Mg-bicarbonate drainage can carry
  more DIC before calcite saturates, so the ceiling rises. At the observed olivine
  pore-water Mg of up to 5 mM the median-cell ceiling roughly doubles (docstring of
  `alkalinity_ceiling_mol_l`; needs a computed number, not this estimate).
- **H3.** Trace-metal loading, not kinetics or drainage, caps cumulative olivine
  application on most cropland. Dunite carries ~2,000–3,000 mg/kg Ni and
  1,000–3,000 mg/kg Cr; 50 t/ha adds 100–150 kg Ni/ha, roughly +40–60 mg/kg in
  a 20 cm topsoil, against soil limits of order 50–75 mg/kg total Ni in several
  jurisdictions. **Numbers here are from memory and must be verified against
  primary regulatory texts before use.**
- **H4.** Olivine supply is concentrated (Norway dominates world production of
  ~8 Mt/yr; a few dozen dunite bodies worldwide are quarried). The economic
  potential therefore hinges on seaborne delivery to coastal cropland, not on
  local quarries. A ports-only transport model captures most of the olivine
  result; rail and barge matter mainly for the interior US, Brazil and India.
- **H5.** Field performance of olivine has been poor relative to lab rates
  (passivation, Si-rich surface layers, low observed weathering in Amann et al.
  2020 and Renforth et al. 2015). The map has **no olivine deliveries in the
  calibration set**, so the basalt anchor cannot be transferred. This is the
  largest uncalibrated term and must be labelled as such everywhere.

---

## 1. Feedstock physics module

### 1.1 Archetype
An `ultramafic` archetype already exists in `FEEDSTOCK_ARCHETYPES` (CaO 3 wt%,
MgO 40 wt%, forsterite 0.70 / enstatite 0.20). Replace it with a **sourced dunite**
archetype, anchored to an actual commercial product the way `delivered_basalt` is
anchored to assayed deliveries:

- Composition: Fo90–92 dunite, MgO 45–49 wt%, CaO <1 wt%, FeO 6–8 wt%, plus a
  serpentine share (commercial Norwegian olivine sand is ~90–95% olivine with
  serpentine, chlorite, enstatite). Source from a supplier datasheet or
  peer-reviewed characterisation, not a textbook forsterite.
- CT on the Ca+Mg basis: 2 mol CO₂ per Mg ⇒ pure forsterite 1.25 tCO₂/t; realistic
  dunite 1.0–1.1. Keep the existing `CARBONATE_EFFICIENCY_PENALTY` logic untouched.
- Trace metals as archetype fields: Ni, Cr, Co mg/kg with a range and source.
  These become inputs to §2.

### 1.2 Rate law
`rate_ca_mg_release` already mixes Palandri & Kharaka minerals by volume fraction,
so forsterite/enstatite rates come for free. Two things need attention:

- **Reference-condition rescaling.** L1 is log10(R/R_ref) with R_ref evaluated for
  `FEEDSTOCK_DEFAULT` at the reference pH and T. A second feedstock needs its own
  R_ref, or the L1 field must be re-expressed as an absolute rate and the anchor
  applied per feedstock. Cleanest: build carries an L1 stack per feedstock, and X
  = 10^L1 · k_feedstock, where k_feedstock is the lab-to-field multiplier (§1.3).
- **Temperature and pH sensitivity differ.** Forsterite Ea 79 kJ/mol neutral, 67
  acid, n_acid 0.47; the basalt mix is dominated by labradorite/augite with
  different Ea and n. So the olivine map will have a *different climate gradient*,
  not just a rescaled one. Report the wet/dry and warm/cool contrasts separately.

### 1.3 Lab-to-field multiplier (the uncalibrated term)
Options, in order of preference:
1. **Use the basalt anchor's implied lab-to-field ratio as a stand-in with a wide
   range**, and say so. Report the olivine result as a bracket: (a) same
   lab-to-field ratio as basalt; (b) olivine-specific field evidence suggesting a
   further 3–10× shortfall (Amann 2020 measured ≪1% dissolution per year at
   220 t/ha; Renforth 2015; ten Berge 2012 pot trials). Every olivine number
   carries the bracket.
2. If Eion, Vesta or another olivine operator has Isometric/Puro-verified
   removals with public grind and site, treat them as a one-cluster calibration
   check. **Verify whether such verified data exist before assuming so.**
3. A gate: `DISSOLUTION_SHAPE_FAILS_LONGITUDINAL`-style flag set TRUE for
   olivine until a field cluster exists.

### 1.4 Shrinking core and grind
Commercial olivine sand is sold at defined grades (e.g. AFS 40–60, d50 ~200–300
µm) and as finer flour. The PSD machinery is feedstock-agnostic; the supplier
grade table should be extended so the grind slider defaults sensibly for olivine.
Passivation is not in the shrinking-core model and matters more for olivine
(Si-rich leached layer at pH > 6); state it, do not model it.

### 1.5 Where η_DIC and the ceiling enter
Unchanged in form. The acid-soil efficiency is cation-independent. The ceiling is
not (§3).

---

## 2. Olivine-specific constraints

### 2.1 Trace-metal loading cap (new limiting-factor class)
Implement as a **cumulative rock budget per hectare**, not a rate: the amount of
dunite that can be applied before topsoil Ni (or Cr) reaches a regulatory
threshold from its baseline.

- Inputs: archetype Ni/Cr; a topsoil baseline Ni map (SoilGrids has no Ni;
  options are GEMAS for Europe, USGS Smith et al. 2013/2014 for the conterminous
  US, and a global default by parent material elsewhere, with confidence flag);
  a mixing depth (20 cm) and bulk density (SoilGrids).
- Thresholds: pick one regime as the central case and report others as
  sensitivities. Candidates to verify from primary texts: EU Sewage Sludge
  Directive 86/278/EEC soil limits (Ni 30–75 mg/kg by pH), EU Fertilising
  Products Regulation 2019/1009 product limits, US EPA Part 503 cumulative
  loading (Ni 420 kg/ha), Dutch intervention values, Indian FCO limits.
  These differ by an order of magnitude and that spread is the finding.
- Output: `ni_budget_t_ha` (tonnes of dunite before the threshold) and, given an
  annual application rate, `ni_years`. Express as a *sustainable annual rate*
  over a stated horizon (e.g. 20 yr) so it is comparable with the drainage
  ceiling in tCO₂/ha/yr. New class in the limiting-factor layer: "Trace-metal
  loading caps application".
- The budget is on TOTAL applied Ni (review S1/S2): every regime is a total soil
  concentration or a total applied mass, and Puro's rule 3.6.2(e) mandates the
  mass balance assuming all feedstock dissolves and no metal leaves. Bioavailability
  is a reason the risk is smaller than the number, never a discount on the budget.
  Cr in olivine is mostly Cr(III) in chromite/spinel; treat Ni as the binding
  element, with a Cr(VI) carve-out for high-Mn, low-SOC, acidic soils.

### 2.2 Mg-dominated exchange complex
Agronomic, not carbon. Report a flag where cumulative Mg addition would push the
exchangeable Ca:Mg ratio below ~2 given the soil's CEC and base saturation (SoilGrids
CEC is available). Do not make it a limiting class; surface it in the hover.

### 2.3 Supply
World olivine production is a few Mt/yr, i.e. two orders of magnitude below what a
Gt-scale ERW result would require, exactly as the US byproduct-fines cap already
caps basalt in the country table. Report a **supply-bounded** number alongside the
technical one: at current production; at a plausible scale-up bounded by the
mapped dunite resource (§4). Sources: USGS Mineral Commodity Summaries (olivine
is folded into "industrial sand" or reported by producer country), NGU for
Norway, Sibelco public statements. **All figures to be pulled fresh, not from
memory.**

---

## 3. Mg-specific ceiling and carbonate accounting

### 3.1 Ceiling Mg tied to the feedstock
The solve holds `[Mg]` fixed and constrains Ca by calcite. Make `mg_mM` a
feedstock property: basalt stays at 1 mM (Vienne/Amann/aglime observations);
dunite uses a value in the observed olivine pore-water range (docstring cites up
to 5 mM). Two ways to set it:

- **Observational (preferred first pass).** A fixed per-feedstock Mg with a range,
  as now. Simple, bounded, honest about what is known.
- **Mechanistic.** `[Mg]` from charge balance with the feedstock's Mg:Ca release
  ratio, capped by a chosen Mg-carbonate or Mg-silicate saturation (sepiolite in
  arid soils). More consistent but introduces an unbounded Mg the docstring
  already rejected once. Run as a sensitivity, not the default.

Gate: with Mg = 0 the solve reproduces the textbook Ca-only benchmark (existing
gate 13); with Mg = 5 mM it must still sit within the Mayer et al. 2025 high-Mg
PHREEQC cases (gate 13d already covers 0–5 mM, so this is a subset check).

### 3.2 Carbonate credit conditioned on soil Ca
The current credit is φ·excess with φ = ½·f_Ca, Ca-only. Extend:

- Where the soil is calcareous, Mg-derived alkalinity precipitates *soil* Ca as
  calcite, so φ → ½ for all cations. Proxy for calcareous: topsoil pH ≥ 7.5
  (SoilGrids), or HWSD/ISRIC CaCO₃ where available. Note that for dunite f_Ca is
  ~0.03, so without this conditioning the carbonate option credits olivine almost
  nothing, which is wrong in calcareous soils and right in acid ones.
- Elsewhere, keep Ca-only. Report both.
- Steady-state caveat: soil Ca is a stock; sustained precipitation needs an
  external Ca flux (irrigation water, gypsum, dust). State it; do not model it.
- Mg poisoning of calcite growth raises the Ω at which precipitation starts;
  consistent with the shipped Ω = 10^0.5. No change, but say so.

### 3.3 Interaction to keep straight
Raising the ceiling (3.1) *reduces* the excess the carbonate credit (3.2) acts on.
The two must be computed in that order and the gates must check export + credit
≤ uncapped under every feedstock.

---

## 4. Ultramafic supply inventory

GLiM has no ultramafic class; `pb` (basic plutonic) is the closest and mixes
gabbro with peridotite. Options, tiered as the quarry inventory already is:

1. **Verified producing olivine/dunite operations (points, high confidence).**
   A curated list, sourced individually: Åheim and Raubergvik (Norway, Sibelco),
   Twin Sisters (Washington, US), Day Book/Spruce Pine district (North Carolina),
   Bragança (Portugal?), Turkish and Greek ophiolite operations, Salem/Odisha
   dunite (India), Japanese and Chinese producers. **Each entry needs a primary
   source; the names above are recollection, not verified.** Expect a few dozen
   points.
2. **Mapped ultramafic bodies (polygons, medium confidence).** National surveys
   where available: USGS SGMC (lithology attribute includes ultramafic), BGS,
   NGU, Geoscience Australia surface geology, GSC for Canada, CPRM for Brazil
   (Goiás–Tocantins complexes, Niquelândia), GSI for India (Nuggihalli, Sittampundi,
   Sukinda). Rasterise as an "ultramafic outcrop" layer analogous to `mafic_frac`.
3. **Ophiolite belts (very coarse).** For countries without a usable survey layer,
   published ophiolite compilations (Dilek & Furnes 2011 map) as a low-confidence
   fallback. Also nickel-laterite districts (New Caledonia, Indonesia, Philippines,
   Cuba) sit on ultramafic bedrock.

Cross-filter OSM quarries against the ultramafic layer exactly as the mafic
pipeline does. Report the outcrop-to-quarry overstatement ratio for ultramafics
separately; expect it to be far larger than for basalt.

---

## 5. Multimodal transport

### 5.1 Why now
The current cost surface is truck-only, great-circle × 1.35, and that was a
deliberate decision (constants.py: "rail can come back if and when a
rail-served-quarry layer exists to gate it"). Olivine changes the calculus: at ~1
tCO₂/t, $25/t of ocean freight is $25/tCO₂, so cropland within 100 km of a port
anywhere in the world can receive Norwegian olivine below the $100 screen on
transport alone. Basalt at 0.295 cannot. The interesting result is therefore not
"rail makes basalt cheaper" but "seaborne olivine makes coastal cropland
economic regardless of local geology".

### 5.2 Model structure (recommended): node-delivered cost, then last-mile truck
Avoid a full routed friction surface. Instead:

1. **Nodes:** ports (World Port Index, ~3,700 entries, filtered to bulk-capable
   by harbour size/depth), inland waterway terminals (USACE for the US, UNECE
   AGN for Europe, Brazil's Paraná–Tietê and Amazon terminals, India's National
   Waterways), and rail-served aggregate terminals where a layer exists (US:
   STB/FRA rail network + MRDS rail flag; elsewhere only where a national layer
   is found).
2. **Node cost:** for each node and feedstock, the cheapest delivered $/t of rock
   from any source via the network: quarry → truck to origin node → line-haul →
   destination node, plus transload charges per handling. Ocean freight as a
   distance-based rate with a fixed component; rail and barge likewise. Line-haul
   distance from a network graph (Natural Earth 10 m railroads is coarse but
   global; OSM rail via Geofabrik is complete but heavy; sea distance via a
   simple sea-lane graph or great-circle with a land-avoidance penalty).
3. **Cell cost:** min over (direct truck from nearest quarry, truck from nearest
   N nodes of node cost + last-mile truck). Same last-mile truck rate table as
   to_do 10.5 (regionalised).
4. **Transload and per-trip fixed components** are what make short rail/barge
   hauls uneconomic; without them the model will over-favour multimodal. Sources
   to pull: USACE barge $/t-mile, STB rail waybill sample for aggregates, ocean
   bulk freight indices for minor bulks (Baltic Handysize), published transload
   fees. **Nothing from memory.**

### 5.3 What this does to basalt too
Once nodes exist, basalt by rail/barge in the US Midwest and Brazil becomes
modelable. Keep it as a scenario ("rail/barge available at mapped terminals"),
off by default for basalt per the existing reasoning, on by default for
seaborne olivine because that is how olivine is actually traded.

### 5.4 Validation
- Reproduce a few published delivered olivine prices (Sibelco to European
  foundries; US olivine f.o.b. plus freight) within a stated tolerance.
- Reproduce the USDA truck curve at the last-mile step (already benchmarked).
- Check the ocean rate against a published minor-bulk freight for a known
  route (e.g. Norway → US East Coast).

### 5.5 Effort
This is the largest block: network data, node graph, per-mode rates, and a new
cost surface per feedstock. Ports-only seaborne olivine is perhaps a quarter of
it and captures most of H4. Rail/barge for interior basins is the remainder.

---

## 6. Outputs and UI

- **Feedstock selector**: basalt / olivine / "best available" (per-cell min
  delivered $/tCO₂ subject to the trace-metal cap). Put it in the existing
  "Feedstock grind" group, renamed "Feedstock". The grind slider defaults change
  with the feedstock.
- **New limiting-factor class**: trace-metal loading.
- **New layer**: delivered cost by mode (truck / rail / barge / sea), and a
  "nearest node" hover row.
- **Country tables**: a second block per feedstock, plus a supply-bounded column
  for olivine.
- **Wider accounting**: the carbonate hint says "Ca share only" for basalt and
  "all cations in calcareous soil" when 3.2 is on.
- Every olivine number carries the uncalibrated label (§1.3) until a field
  cluster exists.

---

## 7. Gates to add (test_kinetics.py)

1. Dunite CT from oxides reproduces 1.0–1.1 tCO₂/t within the archetype range.
2. Forsterite rate at 25 °C, pH 7 reproduces Palandri & Kharaka 10^−10.64.
3. Ceiling with Mg = 0 reproduces gate 13; with Mg = 5 mM within Mayer cases.
4. export + carbonate credit ≤ uncapped under both feedstocks and both φ modes.
5. Trace-metal budget: 50 t/ha of the archetype at the stated Ni gives the stated
   topsoil increment (arithmetic check), and the class is assigned only where the
   budget binds before 20 years at the display application rate.
6. Node-cost monotonicity: adding a node never raises any cell's cost; removing
   all nodes reproduces the truck-only surface exactly.
7. Supply-bounded olivine total ≤ technical total, and the ratio is reported.

---

## 8. Phasing and recommendation

| Phase | Content | Depends on | Rough effort |
|---|---|---|---|
| A | Dunite archetype, per-feedstock L1/anchor, feedstock-tied ceiling Mg, soil-Ca-conditioned φ, gates 1–4 | nothing | 2–3 days |
| B | Trace-metal budget layer and class, Mg:Ca exchange flag, gate 5 | A | 2 days plus data hunt for baseline Ni |
| C | Ultramafic supply inventory (tiers 1–2), supply-bounded totals, gate 7 | nothing | 3–4 days, data-hungry |
| D1 | Ports-only seaborne olivine delivery, node-cost model, last-mile truck, gate 6 | C | 3–4 days |
| D2 | Rail and barge networks and terminals; extend to basalt as a scenario | D1 | 4–7 days, largest data burden |
| E | Feedstock selector UI, layers, hover, country tables, docs, paper SI or a second paper | A–D1 | 2–3 days |

**Recommendation.** Do A first and look at the answer before committing to the
rest. A alone tells us whether olivine changes the *physical* picture (H1, H2)
and is fully gated. If it does, B is mandatory before any olivine number is shown,
because H3 is likely to be the real constraint and showing olivine potential
without it would mislead. C + D1 together answer the economic question that
motivated this (H4). D2 is a separable project that also benefits basalt and can
wait.

Before implementing A, run the reviewer pass the workflow rules call for: a
geochemist on §1.3 and §3 (is transferring the basalt lab-to-field ratio to
olivine defensible even as a bracket? is the soil-Ca φ conditioning right?), a
soils/regulatory reviewer on §2.1 (which Ni regime, total vs available), and a
statistics/methods reviewer on how the uncalibrated olivine term should be
propagated in the country ensemble.

---

## 9. Decisions needed from Zeke

1. **Archetype basis.** Norwegian commercial olivine sand (Fo92, best-documented,
   the traded product) or a generic dunite? Recommend the traded product.
2. **Trace-metal regime for the central case.** Recommend the EU sludge-directive
   soil limits as central (widely cited, pH-dependent), with US 503 and Dutch
   values as sensitivities. Confirm.
3. **How to present the uncalibrated term.** Bracket (basalt ratio / olivine-field
   ratio) everywhere, or show only the conservative end with the optimistic end
   in the SI?
4. **Scope of transport.** D1 only (seaborne olivine, ports) or D1 + D2 (rail and
   barge for basalt too)? Recommend D1 first.
5. **Where it lands.** SI of the drainage paper, or a second paper on feedstock
   choice and logistics? The trace-metal and seaborne-delivery results are
   probably a paper on their own.
6. **Serpentinite.** Exclude: rates 1–2 orders slower and asbestiform-mineral
   handling; per mol Mg the CO₂ potential is identical, lower per tonne only by
   the ~13 wt% structural water (review F16). Recommend exclude.

---

## 10. Things this plan explicitly does not do

- No cation-retention term (to_do R stays blocked on data).
- No passivation kinetics for olivine; stated, not modelled.
- No Mg-carbonate precipitation (kinetically inhibited; consistent with §3).
- No routed road friction surface; the last mile stays great-circle × tortuosity.
- No claim that trace-metal thresholds are the right environmental standard; they
  are used because they are the operative regulatory constraint.
