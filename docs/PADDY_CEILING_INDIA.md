# The drainage ceiling in flooded paddies, and a field-level version for central India

Research note, 2026-08-24. Four literature threads run in parallel (paddy water
DIC measurements; India paddy water balance; central-India baseline water
chemistry; paddy pCO₂ and carbonate behaviour), plus an audit of the map's own
paddy inputs. Every number is tagged VERIFIED (read from the primary full
text this session) or UNVERIFIED (source confirmed to exist; content from
abstract, snippet, or secondary citation). Companion calculator:
`scripts/analysis/paddy_ceiling_india.py`.

Session constraint, stated: the WebSearch budget was exhausted before the
threads ran, so everything below came through direct fetches of primary PDFs
and scholarly APIs. Breadth suffered; the specific gaps are listed in §7.

## 1. The map input defect this found (fixed)

The paddy mask multiplied GRPI inundation months by **SPAM irrigated-rice**
area. Central and eastern Indian kharif paddy is largely **rainfed lowland** —
bunded, puddled, flooded all season, not irrigated — so every verified
India-paddy deployment cell sat at f_flood ≈ 0 and got drained-soil chemistry
(4,000 µatm, ~4.4 mmol/L ceiling). Rebuilt from SPAM all-technology rice
(113.8 Mha globally, vs ~65 irrigated-only; global physical rice area is
110–120 Mha): the deployment cells now read f_flood 0.16–0.17 (central India)
and 0.65 (north Bengal), cropland with >5% flooded cell-time goes 7.6 → 10.3%,
India's drainage-limited steady state 94 → 103 MtCO₂/yr, world 696 → 717.
Residual: GRPI's 0.1° presence grid has holes — one verified paddy site reads
months = 0 while every neighbour reads 6 — so cell f_flood is a floor at paddy
sites. Truly upland (never-flooded) rice is still screened out by months = 0.

## 2. What is measured in paddy water (thread 1 + 4)

- **Kirk, Manful, Rahman et al. 2019** (Plant Cell Environ 42:3197,
  doi:10.1111/pce.13638, open access, **VERIFIED**): bulk flooded-soil
  solution [H₂CO₃* + HCO₃⁻] ≈ **40 mM** (calcareous Philippine soil, pot
  experiment, ~20 kPa CO₂); **~1 mM at the floodwater–soil boundary**. Soil
  CO₂ in submerged rice soils spans **5–70 kPa** (their citation of
  Ponnamperuma 1972/Kirk 2004; that range itself UNVERIFIED at primary level,
  both paywalled).
- The protocol's saturated pCO₂ (Isometric v1.2: 50,000 µatm = 5.07 kPa) sits
  at the **bottom** of the measured range; Kirk's bulk measurement (~20 kPa ≈
  200,000 µatm) is 4× it. Via the near-cube-root, that is a ~1.6× ceiling
  difference — the map's paddy ceiling is conservative on this axis.
- **No DIC/alkalinity EXPORT flux from any ERW-amended paddy has ever been
  published** — confirmed as a genuine gap across all threads, not a search
  failure. Nearest misses: Wang et al. 2024 (wollastonite paddy,
  doi:10.1007/s11104-024-06570-5, **VERIFIED absence** — solid-phase carbon
  only, no water chemistry); Xu et al. 2026 (basalt+biochar paddy pots,
  doi:10.1007/s11104-025-08168-x — HCO₃⁻ up 43–60% vs control but reported
  per g soil, extraction ratio inaccessible); Katoh et al. 2004 percolation
  leaching (doi:10.1080/00380768.2004.10408529, UNVERIFIED, bot-blocked).
- Calcite saturation/precipitation behaviour *inside* flooded paddies:
  literature gap. Kögel-Knabner et al. 2010 (Geoderma 157:1,
  doi:10.1016/j.geoderma.2010.03.009, paywalled) is the review most likely to
  hold a synthesis.

**Structural consequence, now in the calculator:** a paddy exports through two
pathways at very different concentrations. Percolation passes through the
amendment and leaves at porewater DIC (bounded by calcite saturation at
flooded pCO₂ — order 6–25 mmol/L depending on scenario). Surface/bund
drainage leaves from the ponded floodwater, nearly degassed (~1 mM, VERIFIED).
One blended q × one blended concentration — the map's cell treatment —
misprices both. The map keeps its cell treatment (documented); the project
calculator splits the pathways.

## 3. The water balance (thread 2)

- **VERIFIED analog** (Vibhute et al. 2017, J Appl Nat Sci 9:1373,
  doi:10.31018/jans.v9i3.1370, read in full): conventional puddled rice,
  Delhi silt/clay loam — deep percolation **831–963 mm/season** (55–58% of
  applied water, nearly rainfall-independent), surface runoff 17.5 (dry yr) to
  269 mm (wet yr), ETc 547–622 mm.
- Central-India puddled Vertisols/Inceptisols are less permeable; the
  classic 1–5 mm/day heavy-clay percolation (Bouman et al., **UNVERIFIED this
  session** — paywalled) × 110–140 flooded days gives 150–650 mm/season.
  **Bounded inference: percolation 300–600 mm/season (central ~450), surface
  drainage 150–400 (central ~250)**; 65–80% of outflow passes the root zone.
- WaterGAP qtot at the central-India deployment cells is 486–609 mm/yr —
  inside that envelope. The map's water input is corroborated at these sites,
  not the source of the paddy error.
- Rabi (dry-season) rice is a small canal-command practice in Chhattisgarh/MP
  (UNVERIFIED, consistent with the one dry-season trial found); dry-season
  fallow percolation is minor.
- The direct central-India Vertisol percolation measurements likely exist in
  Mohanty & Painuli 2004 / Mohanty et al. 2007 (Soil & Tillage Research,
  doi:10.1016/j.still.2003.10.001, doi:10.1016/j.still.2006.03.005) —
  paywalled, worth institutional access.

## 4. Baseline chemistry and headroom (thread 3)

- **VERIFIED**: Rajnandgaon district (Chhattisgarh rice belt) tube wells,
  n = 160: total alkalinity tehsil means **4.2–11.4 mmol/L** (district mean
  ≈ 8.9; individual wells to 18) — partly limestone-terrain lithology (Yadav
  et al. 2020, doi:10.1016/j.gsd.2020.100352, Table 1 read directly).
- **VERIFIED**: lower Mahanadi river water **1.4–2.3 mmol/L**, groundwater
  2.3–6.3, with most samples calcite-SUPERSATURATED, worst pre-monsoon
  (Acharya et al. 2022, doi:10.3389/frwa.2022.846438).
- Reading: the additionality baseline for FIELD drainage (monsoon rain
  transiting the amended soil) is nearer the river values, 1–3 mmol/L; the
  deep-groundwater 4–11 mmol/L matters instead for **downstream durability**
  (exported alkalinity entering already-saturated aquifers can precipitate —
  a loss the model does not price, in either direction of the ledger).
- CGWB district brochures (Seoni, Balaghat, Bilaspur, Raipur, GPM) could not
  be fetched from this environment (site unreachable) — the single best
  remaining data pull, and a manual 10-minute job.

## 5. The field-level envelope (calculator output, 2026-08-24)

Scenario = {pCO₂_flood 50k/100k/200k µatm; SI 0/0.5/1; Mg 0.5/1/3 mM;
percolation 300/450/600 mm; surface 150/250/400 mm at 0.5/1/1.5 mmol/L;
baseline 3/2/1 mmol/L}; T = 25 °C; same carbonate solve the map uses
(PHREEQC-validated at 5,000–20,000 µatm, gate 13d; paddy pCO₂ extrapolates
beyond that grid — mild, via the cube root).

| | conservative | central | optimistic |
|---|---|---|---|
| percolation ceiling, mmol/L | 6.2 | 12.2 | 25.4 |
| GROSS carrying capacity, tCO₂/ha/yr | 0.85 | 2.62 | 7.34 |
| ADDITIONAL (baseline-netted) | 0.45 | 2.18 | 7.03 |

Against the verified central-India deployments (dissolution-based CDR,
2.1–4.3 tCO₂/ha/yr): **0.8–1.6× the central gross capacity** (1.9–2.0× at the
two highest), versus 1.6–4.9× over the map's pre-fix cell ceiling. At the
field level the claimed dissolution is roughly AT carrying capacity — neither
comfortably below it (the conservative case says 2–5× over) nor absurdly
above it (the optimistic case absorbs all of it). Which case obtains is a
measurable property of the site's drainage water.

## 6. What this means for evaluating a central-India paddy project

1. The binding question is not "does the model allow it" but **what the
   site's percolation water actually carries**. One season of drainage-water
   DIC/alkalinity + Ca + Mg + pH + volume (percolation and bund overflow
   separately, wet and dry season) discriminates the entire conservative-to-
   optimistic range above. If the project's existing water chemistry includes
   these, the envelope collapses to a site number immediately.
2. Additionality needs the **unamended baseline** on matched fields — the
   regional prior (1–3 mmol/L field drainage) is wide and
   lithology-dependent.
3. Downstream durability is a separate open item: regional groundwater is
   commonly already calcite-saturated, so exported alkalinity may partially
   re-precipitate off-field. Nobody's model (ours, Mayer's) prices this.
4. The map's cell numbers understate a paddy project's own fields even after
   the mask fix (cell means dilute by the non-rice share, and GRPI has
   holes). Use the field-level calculator for project screening; use the map
   for regional ranking.

## 7. Follow-ups, in value order

1. CGWB district brochures (manual download) — baseline by district.
2. Site drainage chemistry vs. this envelope (the project's own data).
3. Mohanty & Painuli 2004 / Mohanty 2007 (institutional access) — measured
   central-India Vertisol percolation.
4. Kögel-Knabner et al. 2010 review — carbonate behaviour in paddies.
5. Xu et al. 2026 methods (extraction ratio) — the first ERW-paddy HCO₃⁻
   increment, currently unconvertible to mmol/L.
