"""
Every tunable constant in the ERW Atlas, in one place.

This module is the single source of truth. `emit_constants.py` writes the
subset the browser needs into `src/engine_constants.js` and `src/colormap.js`,
so a value can never be defined twice and drift.

Provenance rules, following data/SCHEMA.md:
  - Every kinetic constant carries its table and page in the primary source.
  - Values transcribed from a PDF are checked by `test_kinetics.py`, which
    re-extracts them from the source text. Never hand-edit without re-running it.
"""

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------
R_GAS = 8.314462618          # J mol-1 K-1
T_REF = 298.15               # K, reference temperature for Arrhenius k25
SEC_PER_YEAR = 31_556_952.0  # s yr-1 (365.2425 d)

# ---------------------------------------------------------------------------
# Mineral dissolution kinetics
# Palandri, J.L. & Kharaka, Y.K. (2004), USGS Open-File Report 2004-1068,
# "A compilation of rate parameters of water-mineral interaction kinetics for
# application to geochemical modeling."  https://pubs.usgs.gov/of/2004/1068/
#
# Rate law, report eqn 7 p.5.  NOTE the exponential as *printed* in the report
# is dimensionally incoherent and singular at 298.15 K; the intended and
# universally implemented form (and what PHREEQC's RATE_PK uses) is
#     exp[ -(Ea/R) * (1/T - 1/T_REF) ]
# which is what kinetics.py implements.  Do not "correct" toward the printed form.
#
# The base mechanism uses a NEGATIVE reaction order on a_H+; the report states
# p.5 that this is a data-reduction convenience, not a mechanistic claim.
#
# Units, verbatim from the table footnotes:
#   log k : rate constant at 25 C, pH = 0, mol m-2 s-1
#   E     : Arrhenius activation energy, kJ mol-1
#   n     : reaction order with respect to H+
#
# `None` means the source tabulates "--" (no data). A missing acid-mechanism n
# (fayalite) means the acid term is not usable for that mineral.
# ---------------------------------------------------------------------------
PK_SOURCE = "Palandri & Kharaka 2004, USGS OFR 2004-1068"

# (log_k25, Ea_kJ, n) per mechanism; Ea converted to J mol-1 at use.
PK_MINERALS = {
    # --- Table 13 p.24, Plagioclase feldspars ---
    "albite":       {"acid": (-10.16, 65.0, 0.457), "neut": (-12.56, 69.8, 0.0),
                     "base": (-15.60, 71.0, -0.572), "table": "13 p.24"},
    "oligoclase":   {"acid": (-9.67, 65.0, 0.457),  "neut": (-11.84, 69.8, 0.0),
                     "base": None, "table": "13 p.24"},
    "andesine":     {"acid": (-8.88, 53.5, 0.541),  "neut": (-11.47, 57.4, 0.0),
                     "base": None, "table": "13 p.24"},
    "labradorite":  {"acid": (-7.87, 42.1, 0.626),  "neut": (-10.91, 45.2, 0.0),
                     "base": None, "table": "13 p.24"},
    "bytownite":    {"acid": (-5.85, 29.3, 1.018),  "neut": (-9.82, 31.5, 0.0),
                     "base": None, "table": "13 p.24"},
    "anorthite":    {"acid": (-3.50, 16.6, 1.411),  "neut": (-9.12, 17.8, 0.0),
                     "base": None, "table": "13 p.24"},

    # --- Table 23 p.35, Orthosilicates ---
    "forsterite":   {"acid": (-6.85, 67.2, 0.470),  "neut": (-10.64, 79.0, 0.0),
                     "base": None, "table": "23 p.35"},
    # Fayalite's acid-mechanism n is tabulated as blank in the source.
    "fayalite":     {"acid": None,                  "neut": (-12.80, 94.4, 0.0),
                     "base": None, "table": "23 p.35"},

    # --- Table 26 p.37, Pyroxenes and pyroxenoids.
    # This table has NO base-mechanism column at all. The report notes p.36 that
    # for enstatite and augite data exist only to pH ~7, that the neutral k is a
    # synthetic cut-off constant, and that E_neut was SET EQUAL to E_acid.
    # Treat pH > 7 pyroxene rates as extrapolation.
    "augite":       {"acid": (-6.82, 78.0, 0.700),  "neut": (-11.97, 78.0, 0.0),
                     "base": None, "table": "26 p.37"},
    "bronzite":     {"acid": (-8.30, 47.2, 0.650),  "neut": (-11.70, 66.1, 0.0),
                     "base": None, "table": "26 p.37"},
    "diopside":     {"acid": (-6.36, 96.1, 0.710),  "neut": (-11.11, 40.6, 0.0),
                     "base": None, "table": "26 p.37"},
    "enstatite":    {"acid": (-9.02, 80.0, 0.600),  "neut": (-12.72, 80.0, 0.0),
                     "base": None, "table": "26 p.37"},
    "wollastonite": {"acid": (-5.37, 54.7, 0.400),  "neut": (-8.88, 54.7, 0.0),
                     "base": None, "table": "26 p.37"},
}

# Minerals whose acid-mechanism data the report flags as pH<=7 only.
PK_ACID_EXTRAPOLATED_ABOVE_PH7 = ("augite", "enstatite")

# ---------------------------------------------------------------------------
# Basaltic glass.
#
# IMPORTANT: basaltic glass is NOT in Palandri & Kharaka. Verified by full-text
# search of OFR 2004-1068: the strings "glass" and "basalt" appear only in its
# reference list, never in a parameter table. Anyone adding a "PK basaltic
# glass" entry above is inventing it.
#
# Gislason & Oelkers (2003), Geochim. Cosmochim. Acta 67, 3817-3832, give
#     r+ = A_A * exp(-E_A/RT) * (a_H+^3 / a_Al3+)^(1/3)
# valid 6-300 C, 1 < pH < 11.
#
# We cannot evaluate that form: there is no gridded a_Al3+, and inventing one
# would be worse than approximating. So we use the APPARENT proton order that
# the experiments display (~1/3) with the published activation energy, and we
# carry the Al-buffering structural uncertainty as an explicit sensitivity case
# (under gibbsite buffering the pH dependence very nearly cancels, making glass
# dissolution close to pH-invariant).
#
# UNVERIFIED: A_A and E_A below were reported to us secondhand, not read from
# the paper. Note especially that A_A is quoted in mol cm-2 s-1, NOT m-2 -- a
# 1e4 trap. Check both against the paper before trusting GLASS_RATE_VERIFIED.
# ---------------------------------------------------------------------------
GLASS_SOURCE = "Gislason & Oelkers 2003, GCA 67, 3817-3832"
GLASS_RATE_VERIFIED = False       # flip only after reading the primary source
GLASS_LOG_A_MOL_CM2_S = -5.6      # mol Si cm-2 s-1  <-- cm2, not m2
GLASS_EA_KJ = 25.5
GLASS_N_H_APPARENT = 1.0 / 3.0
GLASS_N_H_SENSITIVITY = (0.0, 1.0 / 3.0)   # pH-invariant (Al-buffered) .. apparent

# ---------------------------------------------------------------------------
# Carbonate system, for the alkalinity->DIC conversion efficiency (eta_DIC).
#
# Plummer, L.N. & Busenberg, E. (1982), Geochim. Cosmochim. Acta 46, 1011-1040.
# These are the expressions PHREEQC uses. Preferred over Millero, which is
# parameterised on salinity and is the wrong domain for soil solution.
#
# Verified: reproduces the standard 25 C values to <=0.0005 log units
#   log K1 -6.352, log K2 -10.329, log KH -1.468, log Kw -14.000
#
# Ionic-strength (activity) corrections are deliberately omitted: soil-solution
# ionic strength is 0.001-0.05 M and the correction is small relative to the
# structural uncertainties. Documented in docs/METHODOLOGY.md.
# ---------------------------------------------------------------------------
PB82_SOURCE = "Plummer & Busenberg 1982, GCA 46, 1011-1040"
PB82_K1 = (-356.3094, -0.06091964, 21834.37, 126.8339, -1_684_915.0)
PB82_K2 = (-107.8871, -0.03252849, 5151.79, 38.92561, -563_713.9)
PB82_KH = (108.3865, 0.01985076, -6919.53, -40.45154, 669_365.0)
PB82_KW = (-283.971, -0.05069842, 13323.0, 102.24447, -1_119_669.0)

# Soil pCO2, microatmospheres. These are MANDATED values, not our estimates:
# Isometric "Enhanced Weathering in Agriculture" protocol v1.2, section
# 10.4.5.7 / Equation 29 Method B, requires 4,000 uatm for unsaturated cropping
# systems and 50,000 uatm for saturated systems such as rice paddies.
PCO2_UNSATURATED_UATM = 4_000.0
PCO2_SATURATED_UATM = 50_000.0
PCO2_ATMOSPHERIC_UATM = 400.0
PCO2_SOURCE = "Isometric EW-in-agriculture protocol v1.2 s10.4.5.7"

# ---------------------------------------------------------------------------
# Soil pH convention.
#
# This is a first-order bookkeeping issue, not a footnote. SoilGrids reports
# pH in H2O. Isometric specifies a soil-water slurry; Puro.earth's thresholds
# derive from mixed conventions. pH(H2O) typically runs 0.5-0.6 units ABOVE
# pH(CaCl2/KCl), which is comparable to the entire width of the eta_DIC
# transition -- so getting this wrong shifts the whole map.
#
# We work in pH(H2O) (the SoilGrids native convention) and record the offset
# so the protocol thresholds can be moved onto the same basis explicitly.
# ---------------------------------------------------------------------------
PH_CONVENTION = "H2O"
PH_H2O_MINUS_CACL2 = 0.55         # units; sensitivity range below
PH_H2O_MINUS_CACL2_RANGE = (0.4, 0.7)
SOILGRIDS_PH_SCALE = 10.0         # SoilGrids stores pH * 10
SOILGRIDS_SOC_UNITS = "dg/kg"     # divide by 10 for g/kg

# ---------------------------------------------------------------------------
# Protocol eligibility thresholds. VERSIONED -- these change, and the map must
# not silently go stale. The version string is rendered into the legend.
# ---------------------------------------------------------------------------
ELIGIBILITY_VERSION = "puro_v2025_isometric_v1.2"

# Puro.earth ERW methodology Draft Edition 2025 v.1, rule 3.9.1c: field sites
# with mean SOC > 5 wt% prior to the ERW activity are not eligible for crediting.
SOC_EXCLUSION_WT_PCT = 5.0
SOC_EXCLUSION_SOURCE = "Puro.earth ERW 2025 v1 rule 3.9.1c"

# Isometric v1.2 s10.4.5.7: below pH 5.2 non-carbonic acid neutralisation may
# dominate. NOTE this is a WARNING that triggers screening during validation,
# NOT an exclusion. It is carried as an annotation flag with zero score effect;
# encoding a warning as a score deduction would bury an editorial judgement
# inside a number.
PH_WARNING_THRESHOLD = 5.2
PH_WARNING_IS_EXCLUSION = False
PH_WARNING_SOURCE = "Isometric EW protocol v1.2 s10.4.5.7"

# Three-state eligibility rendering. A binary mask on a point estimate asserts
# a distinction between 4.9 and 5.1 wt% that the data cannot support; a
# continuous multiplier makes a marginal cell look like a slightly-worse good
# cell, which invites prospecting a site that will fail its eligibility check.
P_EXCEED_EXCLUDED = 0.9
P_EXCEED_PASSES = 0.1

# Reconstructing a distribution from SoilGrids Q0.05/Q0.50/Q0.95 requires an
# assumption. Lognormal, matched in log space, because SOC is positive and
# right-skewed. The 3.29 is 2 * 1.645 (the 90% two-sided normal z).
QUANTILE_DIST = "lognormal"
Z_90_TWO_SIDED = 3.289707253902945

# ---------------------------------------------------------------------------
# Feedstock stoichiometry.
#
# Silicate weathering: 2 mol CO2 per mol divalent cation released.
# Carbonate weathering: 1 mol CO2 per mol Ca2+ -- i.e. 50% less efficient.
# Used as a HARD CEILING check: no cell may imply more CO2 per tonne than this.
# ---------------------------------------------------------------------------
MOL_CO2_PER_KMOL_CHARGE_T = 0.044        # t CO2 per kmol charge
M_CAO, M_MGO = 56.077, 40.304            # g mol-1

# Published maximum CO2 uptake per tonne of pure mineral, t CO2 / t.
# Puro.earth ERW Methodology Draft Edition 2025 v.1, Table 1.1 p.20.
# Used as an EXTERNAL check on our stoichiometry engine: reproduce these before
# trusting any archetype ceiling. (molar_mass g/mol, divalent_per_formula,
# monovalent_per_formula, published_tco2_per_t)
CDRMAX_REFERENCE = {
    "forsterite":   (140.693, 2, 0, 1.260),   # Mg2SiO4
    "wollastonite": (116.160, 1, 0, 0.759),   # CaSiO3
    "diopside":     (216.550, 2, 0, 0.816),   # CaMgSi2O6
    "enstatite":    (100.387, 1, 0, 0.883),   # MgSiO3
    "anorthite":    (278.207, 1, 0, 0.310),   # CaAl2Si2O8
    "albite":       (262.223, 0, 1, 0.176),   # NaAlSi3O8, Na is monovalent
}
CDRMAX_SOURCE = "Puro.earth ERW 2025 v1 Table 1.1 p.20"
CDRMAX_REL_TOL = 0.06     # 6%; their atomic weights and rounding differ slightly

# Charge equivalents of alkalinity released per mole of mineral dissolved.
# Bertagni & Porporato 2022, Table 1 ("n"). A second, independent external check
# on our charge accounting -- different source, different units, same physics.
#
# NOTE Fe2SiO4: B&P assign n = 4, we assign 0. Not an error in either. See the
# comment on DIVALENT_PER_FORMULA in kinetics.py -- Fe2+ alkalinity is undone by
# oxidation to Fe(OH)3 in oxic soils, and the crediting protocols count only
# Ca, Mg, Na and K.
BP22_ALKALINITY_PER_MOLE = {
    "CaSiO3": 2,          # wollastonite
    "Mg2SiO4": 4,         # forsterite
    "Fe2SiO4": 4,         # fayalite -- we deliberately use 0, see above
    "CaCO3": 2,           # but carbon content 1, so net ACEM max is 1
    "CaMg(CO3)2": 4,      # dolomite, carbon content 2, net max 2
}
BP22_SOURCE = "Bertagni & Porporato 2022, STE 838 156524, Table 1"

# ACEM = n * ACE - C  (their eqn 6). For carbonates C > 0, so ACEM goes NEGATIVE
# at low pH: dissolving CaCO3 in acid is a CO2 source, not a sink. This is the
# mechanism behind the 50% carbonate penalty and is why carbonate content has to
# be measured rather than assumed away.
BP22_CARBON_IN_MINERAL = {"CaSiO3": 0, "Mg2SiO4": 0, "Fe2SiO4": 0,
                          "CaCO3": 1, "CaMg(CO3)2": 2}

# B&P state ACE decays to ~0.5 above pK2 as bicarbonate gives way to carbonate.
# Our derivation reproduces this without being told to; gate 2b asserts it.
ACE_HIGH_PH_ASYMPTOTE = 0.5

# Carbonate feedstocks release 1 mol CO2 per mol Ca2+ rather than 2, i.e. they
# are 50% less efficient than silicates per mole of base cation. Carbonate
# content must therefore be measured, not assumed away.
CARBONATE_EFFICIENCY_PENALTY = 0.5

FEEDSTOCK_ARCHETYPES = {
    # Named archetypes rather than one assumed basalt: real deployments use
    # locally sourced material and mineralogy shifts rate by >1 order of
    # magnitude. Mineral fractions are volume fractions, normalised at use.
    "fresh_basalt":  {"CaO_wt": 0.100, "MgO_wt": 0.080,
                      "minerals": {"labradorite": 0.45, "augite": 0.30,
                                   "forsterite": 0.10}},
    "metabasalt":    {"CaO_wt": 0.075, "MgO_wt": 0.055,
                      "minerals": {"albite": 0.35, "augite": 0.25,
                                   "diopside": 0.15}},
    "ultramafic":    {"CaO_wt": 0.030, "MgO_wt": 0.400,
                      "minerals": {"forsterite": 0.70, "enstatite": 0.20}},
    # Anchored to MEASURED deliveries rather than to a textbook composition.
    # Derived from the subset of 2026 verified deliveries that carry
    # independently measured CDR (see the local-only fixture described in
    # analyse_deployments.py). Their mean implied CO2 potential is 0.289
    # tCO2/t of rock. That sits below fresh_basalt
    # (0.332) and near metabasalt (0.238), i.e. real delivered basalt is less
    # CO2-dense than a fresh-basalt idealisation. Gate 7 asserts this
    # reproduces the measured mean.
    #
    # Prefer this archetype for anything user-facing. Using fresh_basalt would
    # overstate delivered CDR by ~15%, and the nominal 0.33 tCO2/t applied to
    # the derived rows of that table overstates by ~20-25%.
    "delivered_basalt": {"CaO_wt": 0.090, "MgO_wt": 0.068,
                         "minerals": {"labradorite": 0.45, "augite": 0.30,
                                      "forsterite": 0.10}},
}
FEEDSTOCK_DEFAULT = "delivered_basalt"

# Mean implied CO2 potential of independently verified basalt deliveries, and
# the spread across them. Used by gate 7.
DELIVERED_BASALT_TCO2_PER_T = 0.289
DELIVERED_BASALT_RANGE = (0.256, 0.334)
DELIVERED_BASALT_SOURCE = ("2026 verified basalt deliveries, independently measured "
                           "subset; input data held locally, not redistributed")

# Observed dependence of fraction weathered on application rate, from the same
# table: fw ~ rate^-0.58 (R2 0.48, n=8), and perfectly monotonic within the
# 4 India deployments. NOT used in the model -- recorded because it establishes
# that FRACTION WEATHERED IS NOT A SITE PROPERTY. It depends on how much rock
# was applied, so the map must never present it as a suitability metric and any
# cross-site comparison has to hold application rate fixed.
FW_RATE_EXPONENT_OBSERVED = -0.58
FW_RATE_EXPONENT_R2 = 0.48

# ---------------------------------------------------------------------------
# Cropland reference totals. These are DIFFERENT QUANTITIES and the gap between
# them is real, not an error to be tuned away.
#
# Potapov et al. 2022, Nature Food 3, 19-28 -- satellite extent of ANNUAL AND
# PERENNIAL HERBACEOUS crops. Their definition explicitly excludes perennial
# woody crops, permanent pasture and shifting cultivation, and caps recognised
# fallow at 4 years.
CROPLAND_POTAPOV_2019_MAP_MHA = 1215.5
CROPLAND_POTAPOV_2019_SAMPLE_MHA = 1244.2
CROPLAND_POTAPOV_2019_SAMPLE_CI_MHA = 62.7
CROPLAND_POTAPOV_SOURCE = "Potapov et al. 2022, Nature Food 3, 19-28, Table 1"

# FAOSTAT 2022 cropland, from FAOSTAT Analytical Brief 88.
# 1,573 Mha = arable 1,384 (temporary crops 1,085 + temporary meadows 137
# + fallow 162) + permanent crops 190.
CROPLAND_FAOSTAT_2022_MHA = 1573.0
CROPLAND_FAOSTAT_SOURCE = "FAO, FAOSTAT Analytical Brief 88, Land statistics 2001-2022"

# The ~350 Mha gap is structural, and mostly these three FAOSTAT categories that
# herbaceous satellite mapping does not see. Report it; do not reconcile it.
CROPLAND_GAP_COMPONENTS_MHA = {
    "permanent (woody) crops": 190.0,   # orchards, oil palm, coffee, cocoa
    "temporary meadows and pastures": 137.0,
    "fallow beyond the 4-year window": 162.0,
}

# For ERW this gap is not merely bookkeeping. Permanent woody crops ARE eligible
# under both protocols, and some of the highest-profile deployments to date are
# in Brazilian citrus. So a herbaceous-only cropland mask UNDERSTATES the
# addressable area, and that understatement is concentrated in the tropics.
# Flagged as a known v0 limitation, and a candidate ensemble member.

# Nominal application rate for the indicative-CDR layer. Stated on the map.
APPLICATION_RATE_T_HA_YR = 20.0

# ---------------------------------------------------------------------------
# L2 composite: value functions, floors, aggregation.
#
# Normalisation uses ABSOLUTE breakpoints, never min-max or percentile over the
# domain. Three reasons, in docs/METHODOLOGY.md: min-max collapses a 3-4 order
# range so all temperate cropland goes dark; percentile manufactures apparent
# gradient where the physics says cells are near-identical; and any
# distribution-derived transform makes the colour scale mean different things at
# different slider settings, which breaks the interaction.
# ---------------------------------------------------------------------------
# Weighted power mean, S = (sum w_i v_i^p)^(1/p).
#   p = 1     arithmetic (fully compensatory)
#   p -> 0    geometric  <- DEFAULT; log S is linear in w, so weights are
#                            elasticities and Sobol indices are closed-form
#   p = -1    harmonic
#   p -> -inf min        <- this IS the "limiting factor" mode, same code path
AGG_P_DEFAULT = 0.0
AGG_P_SENSITIVITY = (1.0, 0.0, -1.0, float("-inf"))

# Per-criterion floors. This is where the "how harsh is a zero" judgement
# lives -- explicitly, per criterion, rather than as a side effect of which
# mean was chosen.
#
# EPS_QUANTIZE is a correctness requirement, not a nicety: measured, with a
# floor of 1e-3 a single 8-bit step near zero moves the score by 0.23. At 0.02
# the max error is 0.0060 (rms 0.0007), ~5% of one legend class. Value 0 is
# reserved EXCLUSIVELY for hard-masked cells.
EPS_QUANTIZE = 0.02
CRITERION_FLOORS = {
    "reactivity":      0.0,    # truly annihilating: no reactivity, no CDR
    "feedstock_cost":  0.05,   # very expensive rock is bad, not impossible
    "eta_dic":         0.0,    # annihilating for the same reason
    "drainage":        0.05,
}

# Equal weights by default. Justified as declining to assert a preference
# ordering -- NOT as "these factors are equally important", which is false.
# Labelled in the UI as "Neutral (equal weights) - not a recommendation".
WEIGHTS_DEFAULT = {
    "reactivity":     0.25,
    "eta_dic":        0.25,
    "feedstock_cost": 0.25,
    "drainage":       0.25,
}

# Cropland fraction is deliberately ABSENT from the weights. It is an extensive
# quantity, not a suitability criterion: a cell at 5% cropland in an otherwise
# ideal location is an excellent place for ERW, on the cropland present.
# Including it would also double-count, since it already weights every
# aggregate. It is display alpha and the area weight, nothing else.
CROPLAND_IS_A_WEIGHT = False
CROPLAND_MIN_FRACTION = 0.01      # below this, drop the cell (coastal slivers)

# Reference condition for L1. Published, absolute, so L1 is domain-invariant.
# L1 is reported as log10(R / R_ref) on a diverging scale centred at zero and
# labelled in x-reference units -- NOT as a 0-1 index, which invites reading
# 0.5 as "half as reactive".
L1_REF = {"pH": 6.5, "T_soil_C": 15.0, "saturation": 0.6}
L1_LOG_HALF_RANGE = 30.0          # 'A': clamp at +/- log10(A)

# ---------------------------------------------------------------------------
# Transport limitation (Maher & Chamberlain 2014). eta = q / (q + D_w).
# Form is well grounded; D_w is NOT constrained, so this is a sensitivity
# parameter and the layer is off by default until D_w can be bounded from the
# field trials.
# ---------------------------------------------------------------------------
TRANSPORT_LIMITATION_DEFAULT_ON = False
DAMKOHLER_DW_M_YR = 0.5
DAMKOHLER_DW_RANGE = (0.1, 2.0)

# ---------------------------------------------------------------------------
# Grid. Analysis is done on an EQUAL-AREA grid, not EPSG:4326, so that "1 km"
# means 1 km everywhere and haul distances are valid. 4326 is used only as the
# ingest CRS and 3857 only for display tiles.
#
# In 4326 a 1/120 deg cell is ~930 m N-S but only ~460 m E-W at 60N, and cell
# area falls as cos(lat). Measured: summing cropland cells without a proper
# area weight overstates global cropland by +24.3%, worst in exactly the
# high-latitude breadbaskets. Never let a bare .sum() reach a headline number.
# ---------------------------------------------------------------------------
ANALYSIS_CRS = "EPSG:6933"        # NSIDC EASE-Grid 2.0 Global, equal-area
ANALYSIS_RES_M = 1000.0
INGEST_RES_DEG = 1.0 / 120.0      # 30 arcsec
DISPLAY_CRS = "EPSG:3857"
EARTH_RADIUS_M = 6_371_007.181    # authalic radius, matches EASE-Grid 2.0

# Effective resolution is NOT the grid spacing. The feedstock component is
# inventory-limited, so the product is honestly described as "1 km grid,
# ~10-50 km effective resolution" -- in the title, legend and filenames.
GRID_SPACING_LABEL = "1 km grid"
EFFECTIVE_RES_LABEL = "~10-50 km effective resolution"
MAX_DISPLAY_ZOOM = 7              # deliberate cap; see docs/METHODOLOGY.md

# ---------------------------------------------------------------------------
# Release-gating sanity checks. Thresholds are set BEFORE the pipeline runs and
# violations are published even if we release anyway. See docs/VALIDATION.md.
# ---------------------------------------------------------------------------
GATES = {
    # Gate against the CROPLAND PRODUCT'S OWN published total, not FAOSTAT.
    # Potapov et al. 2022 (Nature Food 3, 19-28) report, for 2019, a map-based
    # global cropland area of 1,215.5 Mha and a sample-based estimate of
    # 1,244.2 +/- 62.7 Mha. Our raster sum must reproduce the map-based figure,
    # because that is the same quantity computed the same way.
    "cropland_area_gha": (1.15, 1.30, 0.10),
    "cropland_top20_rel_tol": 0.25,
    # Validates the latitude weighting itself: dropping the cos(lat) term should
    # inflate the total by roughly this much. If the inflation is outside this
    # band, the area code is wrong regardless of what the total comes to.
    "naive_area_inflation": (0.20, 0.35),
    # Stoichiometric ceiling is computed PER ARCHETYPE from its oxide
    # composition, not set as one global number -- an early draft used a single
    # basalt-derived 0.45 and ultramafic legitimately exceeded it. The only
    # absolute bound is pure forsterite, the most CO2-dense silicate in
    # CDRMAX_REFERENCE; anything above that is a bug.
    "max_tco2_per_t_any_feedstock": 1.30,
    "max_annual_dissolved_fraction": 0.20,
    "max_cumulative_dissolved_fraction": 1.00,
    # Tier 2 external consistency. Consistency, NOT validation: the published
    # range spans an order of magnitude and several estimates descend from the
    # same rate-law and surface-area lineage as ours.
    "global_gross_gtco2_yr": (0.5, 4.0),
    "national_rank_corr_vs_beerling": 0.6,
    # Physical plausibility of the fitted effective-surface-area multiplier.
    # lambda < 1 is below geometric and unphysical; > 100 means the kinetics are
    # wrong rather than the surface area.
    "lambda_range": (1.0, 100.0),
}

# The scaling constant is fitted to field trials ONLY, never to the global
# total, and is not revisited after global aggregates are computed. If the
# total lands outside the range above, that is reported as a finding.
CALIBRATION_ANCHOR = {
    "trial": "Beerling et al. 2024 PNAS, Univ. Illinois Energy Farm",
    # 50 t/ha/yr for 4 years = 200 t/ha CUMULATIVE. An earlier draft of this
    # project had 50 t/ha, which would have inflated the global map ~4x.
    "application_t_ha_yr": 50.0,
    "years": 4,
    "cumulative_t_ha": 200.0,
    "cdr_pot_tco2_ha": 10.5,
    "cdr_pot_tco2_ha_sd": 3.8,
    "p80_um": 267.0,
    # CDRpot is derived from Ti-normalised Ca+Mg LOSS x 2, so it already
    # assumes eta_DIC = 1 and no downstream losses. Calibrate the kinetic and
    # transport half against it with eta_DIC HELD AT 1, then apply eta_DIC
    # forward only -- otherwise the constant absorbs 1/(eta_DIC*eta_transport)
    # at Illinois and over-predicts everywhere else.
    "target_is_cation_release": True,
    "hold_eta_dic_at_one_during_fit": True,
}
