# Reviews of OLIVINE_SCOPING_2026-09.md, 2026-09-05

Three reviewer agents (Opus) read the scoping plan and the relevant code before
implementation began. Their findings are reproduced below, lightly reformatted,
with the disposition taken in the build. Finding numbers are referenced from
`scripts/constants.py` (SECOND FEEDSTOCK section) as F (geochemistry),
M (methods/statistics) and S (soils/regulatory).

Four source-verification agents (Sonnet) ran alongside; their compact reports
follow the reviews. Anything they marked UNVERIFIED stayed out of the constants.

---

## Dispositions (summary)

| Finding | Disposition |
|---|---|
| F1 rate ratio 3–10× wrong; use ~5–6.5 | Adopted. Computed 5.6× at reference; gate 16b pins 4.0–6.0 across pH 4.5–8, 10–25 °C |
| F2 "different climate gradient" unsupported | Adopted; framing dropped |
| F3 basalt anchor is 80% forsterite; ~2× attribution uncertainty | Adopted into the constants note and the Methods text |
| F4 field bracket 3–10× unsupported; dose-dependent | Adopted: branch factors, basalt-anchored shipped, others derived by `olivine_field_check.py` (pending); no pooled interval |
| F5 passivation should be a term | Not modelled; stated as unbounded in application rate (`OLIVINE_PASSIVATION_MODELLED = False`) |
| F6 Mg = 5 mM degenerate ceiling | Adopted: central 2 mM, gate 16d asserts 2[Mg]/A ≤ 0.75 (build p90 0.733) |
| F7 ceiling doubling only on drained soils | Adopted; p10/p50/p90 of the cell ratio reported (1.18/1.21/1.28 at 2 mM) |
| F8 pH-target basis erases the Mg upside | Noted in constants; pH basis is withdrawn from the UI, SI sensitivity only |
| F9 5 mM sourced to 220 t/ha | Adopted: 5 mM is the upper sensitivity |
| F10 Ω should be Mg/Ca-dependent | Deferred, noted |
| F11 calcareous φ = ½ is carbon-neutral | Adopted: conditioning REJECTED; Ca-only credit for both feedstocks |
| F12 exchange stock as the credit basis | Deferred to to_do 12b (needs SoilGrids CEC) |
| F13 silica supersaturation, sepiolite | Adopted as a build diagnostic (47.6% of area at 2 mM); not applied |
| F14 Fo92 divalent count 1.84 | Adopted (`divalent` override on the archetype) |
| F15 η_DIC pH input perturbed by olivine | Noted, not modelled |
| F16 serpentinite exclusion reason | Corrected in the plan |
| F17 gate as mixture ratio | Adopted (gate 16b) |
| F18 gates: silica, degeneracy, Ca stock | Silica and degeneracy adopted; Ca-stock with 12b |
| M1a k on absolute retreat | Adopted: L1 relative to the basalt reference, retreat scale geometric only (a first cut double-counted the rate; build reported 17.7×, now gate 16c) |
| M1b conditional-on-branch reporting | Adopted in design; ensemble work (A′) pending |
| M1d elasticity per column | Pending (A′) |
| M2a/2b common-mode mode errors, per-leg fixed costs | For the transport phase (D1/D2, pending) |
| M3a selection inside draws | For A′ |
| M4a supply bound pair | For C2/A′ |
| M G8–G10 gates | 16c/16f adopted; the rest with A′/D1 |
| M6a split C into C1 (origins) and C2 (outcrop) | Adopted: `data/olivine_operations.csv` is C1 |
| M6b/6c B before E; ensemble is a line item | Adopted |
| S1 Puro mandates the mass-balance construct | Adopted; budget on TOTAL applied Ni |
| S2 "dissolved rock" caveat wrong | Adopted; caveat removed |
| S3 compute the budget for basalt too | Pending a sourced basalt Ni (agent running); archetype field is None = "no assay" |
| S4 Puro Table 4.3 as central | Adopted: `TRACE_METAL_REGIME_DEFAULT = "puro_2025"`; sludge directive and loading rules are the strict end of the segment |
| S6 mixing depth a parameter | Adopted |
| S7 Cr secondary; Cr(VI) carve-out | Adopted (Cr secondary); Cr(VI) flag deferred |
| S8 Ca:Mg flag not computable | Adopted: dropped |
| S9 baseline Ni | Single global assumption with range; flagged |
| S10 EU FPR product limits exclude dunite | Adopted into constants and Methods |
| S11 asbestiform screening | Adopted as a supply-inventory gate (constants; plan §4) |
| S12 EU food Ni MLs | Noted in Methods text |
| S13 gate rate 50 vs 30 | Fixed |

---

## Geochemistry review

F1 — "3–10× faster at the same grind" is too wide and its stated basis is wrong. MUST-FIX. Running the actual `rate_ca_mg_release` with a Fo92 dunite against `delivered_basalt` gives a charge-release ratio of 4.6–6.6 across pH 4.5–8.0 and 10–25 °C. The 6× rate ratio and the 3.5× CT ratio do not multiply into per-hectare removal: release is in charge units, so year-1 removal scales as the rate ratio alone; CT governs rock lifetime and $/tCO₂.

F2 — "a different climate gradient" is not supported. SHOULD. Effective Ea over 10–25 °C at pH 6.5: basalt 66.3 kJ/mol, ultramafic 68.8. The pH gradient differs by under 1.5×.

F3 — the basalt anchor is already ~80% an olivine anchor. MUST-FIX (state it). At pH 6.5, 15 °C, delivered_basalt's modelled Ca+Mg charge release is 80.1% forsterite, 13.8% labradorite, 6.1% augite, from 10 vol% olivine. Gudbrandsson's fitted surface fractions (olivine 2.8% vs 17% by volume) would reallocate to ~44% forsterite: a ~2× attribution uncertainty on the transferred anchor.

F4 — the "further 3–10× shortfall" bracket is unsupported and the wrong shape. MUST-FIX. Amann et al. 2020 measured 10^−13.12 (coarse) and 10^−13.75 (fine) mol m⁻² s⁻¹ (BET) at 220 t/ha, 220–950× below PK forsterite at pH 8, 15 °C. ten Berge et al. 2012 at low dose: 14.8% weathered at 1.63 t/ha against a modelled 4–9%, falling to 1.1% at 204 t/ha, a 13× dose dependence in one experiment. The map's 30 t/ha sits between them with no observation. Phase A cannot resolve H1.

F5 — passivation must be a term, not a caveat. SHOULD.

F6 — at Mg = 5 mM the ceiling stops being a ceiling. MUST-FIX. At 4,000 µatm, 15 °C, Mg = 5 mM gives A = 10.80 mmol/L of which 2[Mg]/A = 92.6%, [Ca] = 0.398 mM. The cubic asymptotes to A → 2[Mg].

F7 — "roughly doubles" is right only on drained soils. 5 mM / 1 mM ratios at 15 °C: 2.16 at 4,000 µatm, 1.78 at 10,000, 1.57 at 20,000.

F8 — the Mg upside is erased under the pH-target basis. Under min(pH-target, calcite ceiling) the olivine gain over 1 mM is 1.00× at ≤ 10,000 µatm. Endogenous pH at the 5 mM solution is 8.14.

F9 — the 5 mM value is sourced to a 220 t/ha mesocosm and applied at 30 t/ha. MUST-FIX. Central 2–3 mM, 5 mM as the upper sensitivity.

F10 — Ω = 10^0.5 should not be carried over unchanged (Mg inhibition at Mg/Ca 12.6). CONSIDER.

F11 — the calcareous-soil φ = ½ argument is carbon-neutral at steady state. MUST-FIX. If the Ca comes from dissolving soil carbonate the cycle is net zero. Soil calcareousness identifies where Ca is present, not where it is renewably supplied.

F12 — the exchange stock is quantifiable: at CEC 15, 90% BS, 70% Ca, 20 cm, BD 1.3, ~123 kmol Ca/ha, 5.4 tCO₂/ha one-off, 0.27 tCO₂/ha/yr over 20 years. Condition φ on SoilGrids CEC × base saturation as a depleting stock.

F13 — the ceiling solution is supersaturated with respect to amorphous silica; sepiolite consumes exactly the alkalinity being counted. MUST-FIX. At A = 10.8 mmol/L all-Mg, [Si] = 2.7 mM against ~1.8–2.0 mM (25 °C) and ~1.1 mM (10 °C). Sepiolite: 4 Mg²⁺ + 6 H₄SiO₄ → Mg₄Si₆O₁₅(OH)₂·6H₂O + 8 H⁺. Gate 11 already records a Mg-specific over-prediction of +1.4 to +2.1 log units.

F14 — Fe accounting: CT right, rate-side charge 10% high. Fo90–92 is (Mg1.8–1.84Fe0.16–0.2)SiO₄ → 3.6–3.68 eq, not 4.

F15 — η_DIC reads pre-treatment pH; Amann measured pore-water pH ~9 at 220 t/ha. CONSIDER.

F16 — serpentinite: per mol Mg the CT is identical; lower per tonne only by ~13 wt% water. The rate argument is the real one.

F17 — gate 2 is a table echo. Replace with a mixture-level ratio gate, 4.6–6.6.

F18 — add gates: silica saturation; degeneracy 2[Mg]/A ≤ 0.75; carbonate credit ≤ Ca stock; olivine ceiling gain 1.00× under the pH basis at ≤ 10,000 µatm.

## Methods / statistics review

M1a MUST-FIX: k is not dimensionless across feedstocks as written; define it on an absolute retreat and gate that the basalt anchor is unchanged by the refactor.
M1b MUST-FIX: do not marginalise over the lab-to-field branch; report conditional-on-branch ensembles, no pooled median.
M1c SHOULD: the honest width is a bound; the upper branch is an upper bound, not a p95.
M1d SHOULD: report ∂log(total)/∂log(k) per column; the drainage-limited columns should be far less k-sensitive.
M1e CONSIDER: k and CT are not independent (serpentine share).
M1f CONSIDER: re-centre the ceiling-Mg draw per feedstock.
M2a MUST-FIX: min-over-options is a biased-low estimator; make mode errors common-mode within a draw.
M2b MUST-FIX: per-leg fixed costs and a stated parcel size for ocean legs.
M2c SHOULD: report second-best-minus-best margins and mode-flip shares.
M2d SHOULD: nearest-N errs upward (conservative); say so or use multi-source Dijkstra.
M3a MUST-FIX: "best available feedstock" must be selected inside each draw; report the probability olivine wins per cell.
M3b SHOULD: report Best − max(basalt, olivine) at aggregate.
M3c SHOULD: sample the trace-metal regime as a categorical axis.
M4a MUST-FIX: supply-bounded totals as a bound pair (cheapest-first vs proportional), inside each draw.
M4b SHOULD: state the ranking objective (tCO₂ exported per tonne delivered).
M G8: assert delivered $/tCO₂ × CT_selected == delivered $/t. G9: best-available stack elementwise equal to one of the single-feedstock stacks. G10: credit == 0 where the ceiling does not bind; credit non-increasing in Mg; cap on cumulative application.
M6a SHOULD: split C into C1 (verified origins) and C2 (outcrop); D1 depends on C1 only.
M6b MUST-FIX: E depends on B. M6c MUST-FIX: add A′ (ensemble) after A. M6d CONSIDER: report B as binds / does not bind under regime R.

## Soils / regulatory review

Headline: under every regime verified, Ni caps dunite at 1–7 t/ha/yr against the 30 t/ha display rate. Build §2.1 first.

S1 MUST-FIX: Puro ERW 2025 v2.0 Rule 3.6.2(e) mandates the mass balance assuming all feedstock dissolves and no metal leaves. Adopt it.
S2 MUST-FIX: delete the "dissolved rock" caveat; every regime is total soil concentration or total applied mass.
S3 MUST-FIX: compute the budget for basalt too (at ~100 mg/kg Ni, 30 t/ha/yr is exactly the 86/278 3 kg/ha/yr ceiling); the calibration feedstock file has no Ni/Cr.
S4 MUST-FIX: Puro Table 4.3 (Ni 150, Cr 100 mg/kg) as central; sludge directive band only defined for pH 6–7. Sensitivities: 86/278 Annex IA 30–75, Annex IC 3 kg/ha/yr; EPA 503 cumulative 420 kg/ha and annual 21; CONAMA 420 VP 30 / VI-agrícola 70; CCME 45; Germany BBodSchV Ni 15/50/70 by texture.
S5: at Ni 3,060 mg/kg (Flipkens et al. 2021: 980–4,890 mg/kg), 20 cm, BD 1.3, baseline 20: Puro 110 t/ha; 503 137; 86/278 at 75 47; at 30 8.5; Annex IC 1.0 t/ha/yr. Regime choice spans ~13× (~30× with Annex IC).
S6 SHOULD: mixing depth explicit; no-till gives 4× the increment.
S7 SHOULD: Cr secondary is right (chromite-hosted Cr(III); 86/278 and 503 omit Cr), with a Cr(VI) carve-out for high-Mn, low-SOC, acidic soils (Oze et al. 2007). Åheim Cr 69–2,380 mg/kg.
S8 MUST-FIX: the Ca:Mg flag is not computable (SoilGrids has CEC only, not fetched).
S9 SHOULD: baseline Ni from GEMAS and USGS PP 1802; parent-material default keyed to GLiM elsewhere; digestion basis differs.
S10 MUST-FIX: EU FPR 2019/1009 Annex I caps Ni at 90 (PFC 2) / 100 (PFC 3(B)) mg/kg; dunite exceeds by ~30×.
S11 MUST-FIX: Puro requires asbestiform screening ≤ 0.25 wt% for ultramafic feedstocks.
S12 CONSIDER: EU Regulation 2024/1987 Ni MLs in food from 1 July 2025.
S13 CONSIDER: gate 5 rate 50 vs 30; pH basis for banded limits.
Amann et al. 2020 conclude that Ni- and Cr-rich olivine is not recommended for cropland ERW.

---

## Source-verification reports (compact)

### Composition
Sibelco OLIDENSE 0/40 datasheet: MgO 47.0, SiO₂ 43.0, Fe₂O₃ 7.5 wt%. Amann et al. 2020 Table 1 (XRF, n = 3): MgO 44.99, SiO₂ 40.14, Fe₂O₃ 6.75, CaO 0.40, Al₂O₃ 0.70, MnO 0.09, LOI 6.48; ~90% olivine (Fo92), remainder lizardite, Cr-chlorite/chromite; Ni 2889 ± 18, Cr 2156 ± 3, Co 105 ± 2 mg/kg. Grain sizes: Amann fine p80 43.5 µm, coarse p80 1020 µm; ten Berge 7% < 2 µm, 66% 2–50, 27% 50–200 µm. Palandri & Kharaka forsterite confirmed via the PHREEQC rates database reproduction of Table 23: acid −6.85 / 67.2 / 0.47; neutral −10.64 / 79.0. Oelkers et al. 2018 review: BET-normalised refits are ~4 log units lower than geometric ones; passivation evidence is mostly high-T/high-pCO₂, soil relevance unverified.

### Regulatory limits and baselines
86/278/EEC Annex IA Ni 30–75 mg/kg (pH 6–7), Cr not fixed; Annex IC 3 kg Ni/ha/yr (10-yr average). FPR 2019/1009 Ni 90 (liming) / 100 (inorganic fertiliser, soil improver); Cr(VI) 2. 40 CFR 503.13 Ni 420 mg/kg ceiling, 420 kg/ha cumulative, 21 kg/ha/yr; Cr absent. Netherlands Ni target 35 / intervention 190 (a conflicting page says 100). CONAMA 420/2009 Ni prevention 30 / agricultural investigation 70; Cr 75 / 150. Puro ERW 2025 Table 4.3 Ni 150 / Cr 100 mg/kg soil. Isometric feedstock module v1.1 §3.4.1: reporting required, no numeric ceiling. Baselines: USGS DS 801 conterminous US median Ni 13.5 mg/kg (0–5 cm); GEMAS not readable in-session; SoilGrids and WoSIS carry no Ni. Dupla et al. 2023 (basalt, 40 t/ha/yr): Ni limit exceeded after 10 yr (secondary summary only).

### Field evidence
Amann et al. 2020: 220 t/ha, 340 d reported, pore-water pH to 8–9 (fine), 10^−13.12 to 10^−13.75 mol Mg m⁻² s⁻¹ (BET), 0.023–0.049 tCO₂/ha/yr, "~3 orders below the theoretical optimum"; pore-water Ni above the WHO drinking-water value. ten Berge et al. 2012: 1.63–204 t/ha, 32 weeks, pH 4.89 → 5.96, 14.8% dissolved at the lowest dose falling to 1.1% at the highest; grass Ni 0.53 → 2.67 mg/kg. Renforth 2015 and Dietzen 2018: paywalled, unverified. Eion (Puro): 748 CORCs issued 2025, per-tonne dissolution not disclosed. No olivine-vs-basalt field meta-analysis found.

### Supply and freight
Turkey 469,545 t (2019, USGS MYB); India 87,395 t (2020–21, IBM); Norway Åheim ~1.4 Mt/yr (2014, NGU), ~50% of world supply, tonnage not disclosed by DMF; US byproduct only. Producing operations with coordinates in `data/olivine_operations.csv`. Freight: STB Waybill 2024 crushed stone $0.056/ton-mile; USDA barge St Louis ~$25–27/t (grain proxy, 2026); ANTT Brazil rail cement $0.034–0.036/t-km (2024); NITI Aayog India rail $0.0238/t-km (FY2018-19); Handysize T/C $21,350/day (Sep 2026); no free $/t ocean route figure; no transload charges found. Geodata: World Port Index (public domain), Natural Earth railroads, Geofabrik OSM, USACE NWN (US), UNECE AGN (Europe, unverified); no global navigable-rivers attribute exists.
