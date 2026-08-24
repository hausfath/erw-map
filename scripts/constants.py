"""
Every tunable constant in the ERW Atlas, in one place.

This module is the single source of truth. `emit_constants.py` writes the
subset the browser needs into `src/engine_constants.js` and `src/colormap.js`,
so a value can never be defined twice and drift.

Provenance rules (see docs/METHODOLOGY.md for the model chain and
docs/VALIDATION.md for the gates):
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
# Calcite solubility product, same paper and same functional form with e = 0.
# Needed for the drainage-concentration ceiling below, not for eta_DIC.
PB82_KCAL = (-171.9065, -0.077993, 2839.319, 71.595, 0.0)

# Soil pCO2, microatmospheres. These are MANDATED values, not our estimates:
# Isometric "Enhanced Weathering in Agriculture" protocol v1.2, section
# 10.4.5.7 / Equation 29 Method B, requires 4,000 uatm for unsaturated cropping
# systems and 50,000 uatm for saturated systems such as rice paddies.
PCO2_UNSATURATED_UATM = 4_000.0
PCO2_SATURATED_UATM = 50_000.0
PCO2_ATMOSPHERIC_UATM = 400.0
PCO2_SOURCE = "Isometric EW-in-agriculture protocol v1.2 s10.4.5.7"

# ---------------------------------------------------------------------------
# Dietzen & Rosing 2023, Int. J. Greenhouse Gas Control 125, 103872 (CC-BY).
# "Quantification of CO2 uptake by enhanced weathering of silicate minerals
# applied to acidic soils."
#
# WHY THIS IS HERE, AND IT IS THE STRONGEST EXTERNAL CHECK IN THE PROJECT.
# They define a correction factor X* -- "the proportion of the weathering
# reactions that converted carbonic acid to bicarbonate rather than consuming
# excess acidity" -- derived from a soil proton budget. We compute eta_DIC from
# carbonate equilibrium following Bertagni & Porporato. Different starting
# points, different literatures, and the SAME FUNCTION of (pH, pCO2): our
# eta_dic reproduces every X* value they report to within 0.03, including three
# pCO2-dependent thresholds spanning a 40x pCO2 range. Gate 2d asserts it.
#
# So the protocol-sanctioned strong-acid correction is ALREADY IN THIS MODEL. It
# is not a missing term. What remains open is whether an equilibrium formulation
# of it survives continuous fertiliser loading -- Holden et al. 2024 measured 2%
# carbonic at a site where this formulation gives ~71%, which is a 35x gap that
# no reformulation of X* explains. See to_do.md item 3.
#
# pH BASIS, WHICH THIS PAPER SETTLES. All their thresholds and X* are on
# pH(H2O), stated explicitly with a physical rationale: pH(H2O) "is more
# representative of the soil solution and therefore the conditions that the GRF
# is dissolving in than pHCaCl2, which is typically lower as it includes protons
# displaced from the soil exchange complex". They measured CaCl2 separately and
# used it only to track change over time. 1N KCl is not used. Since both
# Puro.earth's and Isometric's pH numbers trace to this paper, the whole family
# of protocol thresholds is on the SoilGrids-native basis and NO OFFSET APPLIES
# anywhere in this pipeline.
# ---------------------------------------------------------------------------
DIETZEN_ROSING_SOURCE = ("Dietzen & Rosing 2023, IJGGC 125, 103872, "
                         "doi:10.1016/j.ijggc.2023.103872 (CC-BY)")
DIETZEN_ROSING_PH_BASIS = "H2O"
# (pH, pCO2 uatm, their reported X*). Their Table 1 thresholds are stated as the
# pH at which X* > 0.98; the first two rows are their field site and their
# stated lower bound for viability.
DIETZEN_ROSING_XSTAR = (
    (5.79, 1_000.0, 0.83),    # their Vojens field site
    (5.20, 1_000.0, 0.25),    # "below this, credits may not be worth the MRV cost"
    (6.29, 1_000.0, 0.98),    # Table 1, X* > 0.98
    (5.99, 4_000.0, 0.98),    # Table 1, X* > 0.98
    (5.49, 40_000.0, 0.98),   # Table 1, X* > 0.98
)
DIETZEN_ROSING_XSTAR_TOL = 0.05
# Their three distinct pH thresholds, all pH(H2O). NOTE: the "5.2-7.2" range
# quoted in some secondary summaries (and previously in our own docs) is not
# verbatim in the paper -- the upper bound is 7.1, and 6.29 is a third, separate
# threshold sitting between them.
DIETZEN_ROSING_PH_THRESHOLDS = {
    "not_worth_applying_below": 5.20,
    "no_acid_correction_needed_above": 6.29,   # at 1,000 uatm; pCO2-dependent
    "carbonate_precipitation_risk_above": 7.10,
}
# At their site, correcting cation-based uptake for strong acids cut the estimate
# from 437 to 364 kg CO2/ha, i.e. the uncorrected figure was 20% high.
DIETZEN_ROSING_SITE_OVERESTIMATE = 0.20

# ---------------------------------------------------------------------------
# Soil pH convention. RESOLVED for Isometric; no offset is applied.
#
# An earlier version carried PH_H2O_MINUS_CACL2 = 0.55 as a pending correction,
# on the worry that the protocol thresholds might be stated on a CaCl2/KCl
# basis reading ~0.55 units below SoilGrids' native pH(H2O). Applying that
# offset would have moved 55% of cropland area by decile, so it mattered.
#
# It does not apply. Isometric EW-in-agriculture v1.2 states in three separate
# places -- the rule text, the parameter table and the measurement-requirements
# table -- that its 5.2 threshold is "as measured in a soil-water slurry", i.e.
# pH(H2O), the same basis SoilGrids reports. Applying an offset would therefore
# have INTRODUCED an error of exactly the magnitude we were trying to avoid.
# The constants are removed rather than left dead, so nobody re-applies them.
#
# Two related questions remain genuinely open, and neither is this one:
#   1. Puro.earth specifies only ISO 10390:2021, which permits H2O, CaCl2 or
#      KCl side by side, so its basis is unpinned at the protocol level. Both
#      of its numeric thresholds trace to Dietzen & Rosing 2023, the same paper
#      Isometric implements on a water basis -- suggestive, not proof.
#   2. SLURRY vs SOIL SOLUTION is a different offset and still unhandled. The
#      rate law and eta_dic both want H+ activity in the water actually
#      contacting the grain; a dilute slurry reads above in-situ soil solution
#      at field water content, plausibly by 0.2-0.5 units. Direction: we
#      overstate eta_DIC and understate rate. Not corrected here because the
#      magnitude is not established for cropland at field capacity.
# ---------------------------------------------------------------------------
PH_CONVENTION = "H2O"
PH_CONVENTION_RESOLVED = (
    "Isometric v1.2 states the 5.2 screen is measured in a soil-water slurry, "
    "i.e. pH(H2O) as SoilGrids reports it; no offset applies. Puro cites only "
    "ISO 10390:2021 and remains unpinned."
)
SOILGRIDS_PH_SCALE = 10.0         # SoilGrids stores pH * 10
SOILGRIDS_SOC_UNITS = "dg/kg"     # divide by 10 for g/kg

# Flooding drives soil pH toward neutrality, so flooded pCO2 must not be paired
# with a drained pH. SoilGrids is an air-dried, drained measurement; van Breemen
# (1987, Neth. J. Agric. Sci. 35, 271, p.274) reports that on submergence "the
# pH of acidic soils increases, and that the pH of alkaline soils decreases,
# while the pH generally stabilizes at values between approximately 6 and 7
# after several weeks or months of flooding". Measured instance: Schulz et al.
# (2024, ES&T 58, 10601) saw pH at 15 cm rise from 4.5-5.2 to 6.0-6.2 over 16
# weeks. 6.7 is the midpoint of van Breemen's stated 6-7 band.
#
# This matters for the paddy question specifically, and it cuts AGAINST the
# paddy mechanism: the high-pCO2 advantage exists only below about pH 5.5, and
# submergence removes exactly that acidity. So the retracted paddy prediction
# has a mechanistic, self-cancelling explanation rather than only a population
# one. Effect on this map is small (paddy-weighted median pH is already 6.4 and
# mean flooded cell-time is 0.014), so this is a consistency fix, not a
# re-ranking.
PH_FLOODED_CONVERGENCE = 6.7
PH_FLOODED_CONVERGENCE_RANGE = (6.0, 7.0)
PH_FLOODED_SOURCE = (
    "van Breemen 1987, Neth. J. Agric. Sci. 35, 271 (p.274); "
    "Schulz et al. 2024, ES&T 58, 10601 (+1.0-1.5 units over 16 weeks)"
)

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
M_CO2_G_MOL = 44.009                     # g mol-1, unrounded; the flux ceiling
                                         # is a bound so it uses the exact mass

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

# Stapafell crystalline basalt as characterised by Gudbrandsson et al. 2011, for
# the no-free-parameter kinetics validation. Reported VOLUME fractions.
# Their own mixing model needed RELATIVE SURFACE AREAS of 83.3 / 13.9 / 2.8
# (plagioclase / pyroxene / olivine) to fit within 0.5 log units, against volume
# fractions of 44 / 39 / 17 -- so the surface is far more plagioclase-rich than
# the rock is. Both are recorded because the difference between them IS the test.
STAPAFELL_VOLUME_FRACTIONS = {"labradorite": 0.44, "augite": 0.39,
                              "forsterite": 0.17}
STAPAFELL_SURFACE_FRACTIONS = {"labradorite": 0.833, "augite": 0.139,
                               "forsterite": 0.028}
STAPAFELL_BET_CM2_PER_G = 7030.0
GUDBRANDSSON_SOURCE = ("Gudbrandsson et al. 2011, GCA 75, 5496-5509; rates for "
                       "Ca/Mg derived from their Table 4 concentrations via "
                       "their Eq. 5")
# Pre-registered pass criterion, from docs/VALIDATION.md.
GUDBRANDSSON_TOLERANCE_LOG = 0.5

# MEASURED apparent activation energy for whole-rock crystalline basalt, from
# Gudbrandsson et al. 2011 Table 5 (Si release, Arrhenius fit over 5-75 C):
#   pH 3: 54.1   pH 4: 33.8   pH 5: 35.2   pH 9: 33.9   pH 10: 35.0   pH 11: 24.2
# Mean ~36 kJ/mol.
#
# THIS RETRACTS A CONCESSION WE MADE TO CASCADE. We previously wrote that the
# effective Ea of a basalt mixture for Ca+Mg release is 65.6-67.9 kJ/mol, and that
# Cascade's 68.8 was therefore "a good number reached by an unsupported route".
# Measured whole-rock basalt is ~36. So Cascade's value is roughly 2x too high --
# and so is our own Palandri-Kharaka mixture, whose effective Ea comes out at
# 61.9-69.3 kJ/mol over 5-25 C depending on pH (66.0 at pH 6.5). Both
# over-weight temperature. NOTE: this range was previously stated as 46-63,
# which was wrong in the flattering direction -- only the metabasalt archetype
# reaches the low end, and the shipped delivered_basalt does not. Recomputed
# directly from rate_ca_mg_release over the cropland temperature band.
#
# The consequence is geographic and it is not small: at 36 kJ/mol a soil 20 C
# warmer is 2.7x faster, at 68 it is 6.7x. The tropics-versus-temperate contrast
# is therefore about 2.5x SMALLER than either formulation implies.
BASALT_APPARENT_EA_MEASURED_KJ = 36.0
BASALT_APPARENT_EA_MEASURED_RANGE = (24.2, 54.1)
BASALT_APPARENT_EA_SOURCE = "Gudbrandsson et al. 2011 GCA 75, Table 5 (Si, 5-75 C)"

# Per-mineral Palandri-Kharaka rates over-predict measured basalt release, and the
# residual is STRUCTURED, not noise (test_kinetics.py gate 11 prints the breakdown):
#   - by temperature: bias grows +0.01 -> +1.58 log units from 5 to 75 C, which is
#     the activation-energy problem above;
#   - by pH: Mg over-prediction peaks at pH 4-8 (+1.4 to +2.1) and nearly vanishes
#     at pH 2-4 and above pH 8. That is the signature of secondary Mg/Fe phases
#     precipitating near neutral pH, where they are least soluble, removing Mg
#     from the outlet solution the experiment measures.
#
# Neither is corrected in the default model yet. Recording the diagnosis rather
# than silently retuning, because the fix is a modelling decision that needs its
# own review, and because an unexplained tuning would hide the finding.
KINETICS_OVERPREDICTS = True

# Mean implied CO2 potential of independently verified basalt deliveries, and
# the spread across them. Used by gate 7.
DELIVERED_BASALT_TCO2_PER_T = 0.289
DELIVERED_BASALT_RANGE = (0.256, 0.334)
DELIVERED_BASALT_SOURCE = ("2026 verified basalt deliveries, independently measured "
                           "subset; input data held locally, not redistributed")

# Apparent dependence of fraction weathered on application rate: fw ~ rate^-0.58
# (R2 0.48, n=8). NOT used in the model.
#
# DO NOT TREAT THIS AS A RATE EFFECT. It is confounded beyond repair in this
# dataset, and the confounding was missed when the constant was added:
#
#   - corr(ln rate, ln p50) = +0.60. Operators who apply high rates also grind
#     coarse (Mati: 44.7 t/ha at 600 um) and operators who apply low rates grind
#     fine (Lithos/Terradot: ~20 t/ha at 67-120 um).
#   - The WITHIN-operator slope -- same feedstock, same grind -- is
#     -0.01 +/- 0.57, i.e. indistinguishable from zero.
#   - Grind is perfectly nested in operator, so the independent cluster count is
#     4, not 8, and one of those is a singleton.
#
# So -0.58 is the operator/grind contrast wearing a rate label. Using it to
# "normalise to a common application rate", as analyse_deployments.py once did,
# removes the grind contrast a SECOND time through a coefficient that IS the
# grind contrast -- which is why that normalisation appeared to reverse the
# regime ordering. That reversal is withdrawn.
#
# What the constant still legitimately establishes: FRACTION WEATHERED IS NOT A
# SITE PROPERTY. It depends on how much rock was applied, so the map must never
# present it as a suitability metric, and any cross-site comparison has to hold
# both application rate AND grind fixed. Identifying a real rate exponent needs
# two rates within one grind at the same site; see docs/VALIDATION.md.
FW_RATE_EXPONENT_OBSERVED = -0.58
FW_RATE_EXPONENT_IS_CONFOUNDED = True
FW_RATE_EXPONENT_WITHIN_OPERATOR = (-0.013, 0.572)   # slope, standard error
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
#
# 30 t/ha as of 2026-08, raised from 20 because 20 sat below what commercial
# projects actually spread. Two things to know about the consequence, because
# neither is intuitive:
#
#  1. THE FLUX CEILING DOES NOT SCALE WITH THIS. It is set by drainage and
#     carbonate chemistry, not by how much rock is on the field, so on the ~97% of
#     cropland where the cap already binds, adding 50% more rock adds no carbon at
#     all. Raising the rate mostly raises the fraction of the map that is
#     transport-limited rather than raising the tonnage. That is the physics, not
#     a modelling artefact -- and it is the first place the ceiling changes what a
#     deployment decision looks like.
#  2. The dissolved FRACTION is held at DISSOLVED_FRAC_AT_REF regardless of rate,
#     so this scales the uncapped carbon linearly. Whether that is wrong, and in
#     which direction, IS NOT KNOWN -- see FW_RATE_EXPONENT_OBSERVED above and its
#     note. -0.58 is the operator/grind contrast wearing a rate label, the
#     within-operator slope is -0.01 +/- 0.57, and using it to correct for rate
#     removes the grind contrast twice. So do NOT reach for it to "fix" this.
APPLICATION_RATE_T_HA_YR = 30.0
APPLICATION_RATE_PREVIOUS_T_HA_YR = 20.0   # for the changelog and the rate note

# ---------------------------------------------------------------------------
# Annual dissolution fraction.
#
# First-order decay of the remaining mass:
#     frac = 1 - exp(-k * X)
# where X is the dimensionless rate relative to the reference condition,
#     X = (R/R_ref) * eta_DIC * eta_transport
# and the dissolution model turns X into a fraction weathered.
#
# THE EXPONENTIAL WAS REPLACED BY SHRINKING CORE, August 2026. The old form,
# frac = 1 - exp(-k*X) with k = -ln(1 - DISSOLVED_FRAC_AT_REF), was a single
# first-order decay on the BULK mass: it let the last 10% of the rock dissolve as
# easily as the first 10%, when physically that last 10% is the coarse tail with
# the least surface area per unit mass. It could reach 100% in a year, which no
# real grind does. See kinetics.dissolved_fraction.
#
# Consequence of the swap, at the reference grind: fraction weathered rises
# slightly at low X (+1 pp) and falls in the middle and upper range, worst around
# X = 8 at -8 pp. It converges again at very high X, because enough capacity does
# eventually consume even the coarse tail.
#
# The shrinking-core form also moved GRIND out of the rate. Under shrinking core
# the linear retreat rate does not depend on particle size, so the old
# surface-area multiplier on the rate is gone and grind now enters once, through
# the particle-size integral. Keeping both would count it twice.
#
# Both replace a hard clip at 0.6, which pinned 18.9% of cropland area at an
# identical value and gave the CDR layer a flat top across a fifth of the map.
#
# WHERE 0.25 COMES FROM. Corrected 2026-08 -- the previous version of this note
# overstated how well determined it is, and got the statistic wrong.
#
# It is the ONLY free parameter in the dissolution model, set by hand so that a
# cell at the reference condition weathers 25% of the applied rock in year one.
# Three things a reader needs, none of which the old note said:
#
#  1. IT IS NOT THE MIDPOINT of the observed range, which the old note claimed.
#     First-period fraction weathered across the eight 2026 verified deliveries
#     spans 15.4-55.9%. Midpoint 35.7%, mean 32.8%, MEDIAN 26.4%. 0.25 is nearest
#     the median, and coincides almost exactly with one delivery (25.0%).
#  2. THE OBSERVATIONS ARE NOT AT THE REFERENCE CONDITION. No delivery is at
#     d50 150 um / width 1.5: they run 67, 120 and 600 um at 15-100 t/ha. Renormal-
#     ised to a common grind and rate the same eight span 8.7-71.3% with a median
#     of 31.7%, not 15-56% with a median of 26%. So a number defined at a
#     normalised condition is being justified by un-normalised observations.
#     Neither range is a sound basis: analyse_deployments.py shows grind is
#     perfectly collinear with regime here, so the renormalisation is itself
#     unidentifiable. Both are reported; neither is load-bearing.
#  3. THE REFERENCE CONDITION IS UNDER-SPECIFIED ON THE TRANSPORT SIDE. L1_REF
#     pins pH, temperature and saturation but says nothing about drainage, and
#     frac = DISSOLVED_FRAC_AT_REF is defined at X = 1, which requires
#     eta_transport = 1, i.e. INFINITE drainage. No real site meets that. A cell
#     with exactly reference kinetics at the median cropland drainage
#     (eta_tr = 0.71) weathers 18.5%, not 25%.
#
# It remains an anchor rather than a fit, and docs/VALIDATION.md still requires
# per-delivery particle-size distributions before any real fit. But "anchored to
# the midpoint of observation" was wrong twice over and is withdrawn.
# ---------------------------------------------------------------------------
DISSOLVED_FRAC_AT_REF = 0.25
DISSOLVED_FRAC_OBSERVED_RANGE = (0.154, 0.559)          # raw, each at its own grind
DISSOLVED_FRAC_OBSERVED_MEDIAN = 0.264
DISSOLVED_FRAC_NORMALISED_RANGE = (0.087, 0.713)        # to d50 150 um and 44.7 t/ha
DISSOLVED_FRAC_NORMALISED_MEDIAN = 0.317
DISSOLVED_FRAC_REF_REQUIRES_ETA_TR = 1.0                # X = 1 implies infinite drainage

# Top of the fraction-weathered COLOUR RAMP. Not a cap on the quantity -- the
# layer still reports its true value in the readout, and cells above this clamp to
# the top colour with the legend labelled ">=".
#
# The old ramp spanned 0-100% and spent 40% of its colour range on 2% of cropland
# area. Under shrinking core the distribution is p50 15%, p90 59%, p99 87%, so
# most of the map lives below 60% and the top of the ramp was close to unused.
# 0.65 clamps 7.3% of area; 0.80 would clamp 2.2% and 0.90 only 0.6%, so this is a
# readability-versus-headroom trade and 0.65 is the readability end of it.
#
# NOTE the shrinking-core swap did NOT make 100% unreachable, only much harder:
# 0.01% of cropland area still exceeds 99%, down from 0.11% under the exponential.
# Cells get there by having 40x the reference reactivity, which is a kinetics
# question, not a particle-size one.
FRAC_RAMP_MAX = 0.65
FRAC_RAMP_CLAMPED_AREA_FRAC = 0.073     # measured; reported in the build

# ---------------------------------------------------------------------------
# Suitability is a value function of GROSS CDR, on absolute breakpoints in
# tCO2 gross/ha/yr at APPLICATION_RATE_T_HA_YR.
#
# This is the fix for a real defect: suitability was a weighted geometric mean of
# value-function transforms of the same three physical terms that make up CDR,
# with a uniform 0.02 quantisation floor applied as if it were a physical floor.
# The consequence was that a cell with ZERO reactivity -- hence zero carbon
# removal -- scored exp(ln(0.02)/3) x 100 = 27 rather than 0. The floor existed
# to stop 8-bit quantisation from swinging the score; it should never have
# manufactured suitability where the physics says none.
#
# Tying suitability to CDR also removes three sets of arbitrary value-function
# breakpoints (one per physical term) and replaces them with one set on a
# quantity that has units and can be argued about.
#
# Zero CDR now gives zero suitability BY CONSTRUCTION, not by tuning.
#
# THE TOP KNOT WAS UNREACHABLE, and had been since it was written. It sat at
# 10 tCO2/ha/yr, but you cannot get 10 tCO2/ha/yr out of the applied rock: the
# stoichiometric maximum is APPLICATION_RATE x the feedstock's CO2 potential,
# which is 8.69 at 30 t/ha and was 5.79 at the old 20 t/ha. So a score of 100 was
# not merely unreached in this build, it was arithmetically impossible in every
# build, and roughly the top 8 points of the scale were dead.
#
# The top knot is now the STOICHIOMETRIC MAXIMUM itself, computed rather than
# stated. 100 therefore means "every tonne applied has dissolved and every
# available cation has carried its carbon" -- an interpretable anchor, and one
# that stays correct if the rate or the feedstock changes. The lower knots stay
# as absolute values, because they are the ones that make the score comparable
# between builds; only the endpoint is tied to what is physically attainable.
#
# It remains true that the breakpoints are absolute and do NOT move with the
# grind or term-exponent sliders, which is what keeps the colour scale stable
# while a reader explores. The application rate is not a slider.
# ---------------------------------------------------------------------------
_STOICH_MAX_T_HA_YR = (APPLICATION_RATE_T_HA_YR
                       * (FEEDSTOCK_ARCHETYPES[FEEDSTOCK_DEFAULT]["CaO_wt"] / M_CAO
                          + FEEDSTOCK_ARCHETYPES[FEEDSTOCK_DEFAULT]["MgO_wt"] / M_MGO)
                       * 1000.0 * 2.0 * MOL_CO2_PER_KMOL_CHARGE_T)
CDR_SUITABILITY_KNOTS = [
    (0.02, 0.0),     # at or below this, negligible: rendered as its own state
    (0.10, 0.20),
    (0.50, 0.40),
    (1.50, 0.60),
    (4.00, 0.80),
    (round(_STOICH_MAX_T_HA_YR, 2), 1.0),   # complete dissolution; see above
]
# Below this, a cell is drawn as "negligible potential" rather than given a
# low-but-nonzero colour. A near-zero score and a genuine zero are different
# claims and should not share a ramp.
CDR_NEGLIGIBLE_T_HA_YR = 0.02

# The three physical terms multiply into CDR with UNIT exponents by default,
# because they are terms in a physical product, not competing preferences: you
# cannot care more about dissolution rate than about whether the alkalinity
# retains carbon, since both are required for any carbon to be stored. The
# sliders therefore expose term SENSITIVITY (default 1 = the physics), not
# importance weights that sum to one.
TERM_EXPONENT_DEFAULT = 1.0
TERM_EXPONENT_RANGE = (0.0, 1.0)

# ---------------------------------------------------------------------------
# Particle size. Exposed in the UI because specific surface area is the single
# largest uncertainty in any absolute CDR figure here, and burying it in a
# hardcoded constant hid the dominant term from the reader.
#
# The verified 2026 deliveries span 67-600 um. On diameter alone that is ~9x in
# geometric surface area; allowing distribution width to vary at fixed d80 adds
# up to another order of magnitude. Both are therefore user-controllable, and
# neither is presented as known.
# ---------------------------------------------------------------------------
FEEDSTOCK_DENSITY_KG_M3 = 3000.0     # basalt
PSD_D_MIN_UM = 1.0                   # finest particle; truncates the RR tail
PSD_D_MAX_UM = 5000.0
# d50, not d80: the ERW field reports p50, so the slider should speak the same
# language as the deliveries. Default 150 um sits in the middle of the observed
# spread and is consistent with the Beerling trial: their reported p80 of 267 um
# converts to a p50 of 152 um at our reference width.
PSD_REF_D50_UM = 150.0
PSD_REF_WIDTH = 1.5                  # Rosin-Rammler n; UNMEASURED, see below
PSD_D50_SLIDER_RANGE = (40.0, 700.0)   # brackets the observed p50 span 67-600 um

# MEASURED p50 for the 2026 verified deliveries. This is the data that was
# blocking the constancy test, and it is a 9x span in diameter -- far larger than
# the 3.35x rate-adjusted spread between climate regimes, which is why grain size
# had to be controlled before any regime comparison meant anything.
DELIVERY_P50_UM = {
    "mati": 600.0,          # all three Mati sites, coarsest in the set
    "terradot": 120.0,      # reported as 90-150; midpoint used
    "lithos": 67.0,         # finest in the set
    "alt_carbon": None,     # unknown; excluded from grain-normalised comparison
}
DELIVERY_P50_SPAN_UM = (67.0, 600.0)
# Beerling et al. 2024 report p80, not p50. Converting needs a width, and the
# conversion is width-dependent (1.76x at n=1.5, 3.35x at n=0.7), so the
# assumption travels with the number.
BEERLING_P80_UM = 267.0
PSD_WIDTH_SLIDER_RANGE = (0.7, 2.5)   # broad .. narrow grind

# The reference WIDTH is an assumption, not a measurement: the Corn Belt trial
# reports p80 but, as far as we have found, not the full distribution. Every
# absolute number scales with this choice, which is precisely why it is a slider.
#
# It is also the DOMINANT remaining unknown in this part of the model, now that
# p50 is measured. Moving n across the slider range at fixed d50 moves geometric
# SSA by several-fold and moves the lambda implied by the measured BET anchor
# across most of the plausible roughness range.
#
# n = 1.5 is on the NARROW side for a crushed product. Narrow values describe
# classified or sieved material, of which Gudbrandsson's fines-removed fraction is
# an example; a commercial crush retains its fine tail and is broader. We have not
# changed the default, because doing so without a measured distribution would just
# swap one assumption for another -- but the direction of the likely error is
# known, and it means the current default probably UNDERSTATES reactive surface.
PSD_REF_WIDTH_IS_ASSUMED = True
PSD_WIDTH_IS_DOMINANT_UNKNOWN = True

# Roughness multiplier on geometric SSA, to be FITTED per deployment once
# per-deployment particle-size distributions are available. Values outside this
# range falsify the model rather than needing a bigger multiplier:
# lambda < 1 is below geometric and unphysical; lambda > 100 implies BET-scale
# reactivity for coarse grains, i.e. the kinetics are wrong, not the area.
LAMBDA_ROUGHNESS_RANGE = (1.0, 100.0)

# MEASURED anchor, replacing an unsourced one. The UI previously reported the
# lambda implied by a BET of "1-5 m2/g", which was secondhand and too high --
# it made the reference grind look like it needed lambda 39-197, straddling the
# falsification ceiling and implying our own default was unphysical.
#
# We already hold a real measurement. Gudbrandsson et al. 2011 crushed Stapafell
# basalt to a 45-125 um sieve fraction, gravitationally settled the fines OUT, and
# measured 7030 cm2/g = 0.703 m2/g by 11-point krypton BET. That fraction implies
# d80 ~= 109 um and a geometric SSA of 0.0255 m2/g for mass uniform across it, so
#
#     lambda = 0.703 / 0.0255 = 27.5
#
# Comfortably inside 1-100. And the caveat cuts the helpful way: because their
# fines were removed, a real ERW feedstock at the same d80 carries more fine
# surface and would need a LOWER lambda still. 27 is an upper bound for
# classified material, not a central estimate for a crushed product.
LAMBDA_MEASURED = 27.5
LAMBDA_MEASURED_BASIS = ("Gudbrandsson et al. 2011: 45-125 um sieve fraction with "
                         "fines removed, 0.703 m2/g krypton BET, implied d80 109 um")
LAMBDA_DEFAULT = LAMBDA_MEASURED

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

# SUPERSEDED by CDR_SUITABILITY_KNOTS and TERM_EXPONENT_DEFAULT above.
#
# These were equal weights over a compensatory geometric mean. The scheme was
# wrong in kind for the physical terms: it let excellent alkalinity retention
# partly offset zero reactivity, when in fact zero reactivity means zero carbon
# regardless. Kept here only to document what changed.
#
# Weights DO become meaningful again once genuinely substitutable economic
# factors exist -- delivered feedstock cost, MRV cost -- because those are
# tradeable in a way the physics is not. At that point the structure is
#     suitability = f(gross CDR) x (weighted compensatory economic term)
# with the physical half still annihilating.
WEIGHTS_DEFAULT_SUPERSEDED = {
    "reactivity": 0.25, "eta_dic": 0.25, "feedstock_cost": 0.25, "drainage": 0.25,
}

# Cropland fraction is deliberately ABSENT from the weights. It is an extensive
# quantity, not a suitability criterion: a cell at 5% cropland in an otherwise
# ideal location is an excellent place for ERW, on the cropland present.
# Including it would also double-count, since it already weights every
# aggregate. It is display alpha and the area weight, nothing else.
CROPLAND_IS_A_WEIGHT = False
CROPLAND_MIN_FRACTION = 0.01      # below this, drop the cell (coastal slivers)

# ---------------------------------------------------------------------------
# WHAT IS GROWN HERE. Descriptive only -- crop identity feeds NOTHING in the
# model chain except rice, and that only through the paddy soil-pCO2 pathway
# (see PADDY / f_flood). It is in the readout because ERW economics, agronomy
# and protocol eligibility all differ by crop, and a reader looking at a cell
# needs to know whether they are looking at flooded paddy or a soy rotation.
#
# WHY TWO CROPS AND NOT ONE. Measured over the shipped grid: the single
# dominant crop holds a median of only 46% of a cell's cropped area, and just
# 41.7% of cropland area has any crop above half. A one-word label would be a
# minority of the cell more often than not -- "wheat" on the North China Plain
# means wheat 25%, maize 23%, vegetables 16%. Two crops reach a median 71% and
# self-document when the cell is genuinely mixed, which one label cannot.
# Three would reach 83%, and do not fit the encoding; the remainder is shown as
# "other" instead so the total always reads to 100%.
#
# SPAM2010 v2.0 is the latest GLOBAL release, verified 2026-08-06 against the
# Harvard Dataverse: the 2017 and MapSPAM2020 products are Sub-Saharan Africa
# only. The 2010 reference year is therefore current-best and also a real
# limitation -- Brazilian soy expansion and Corn Belt rotation shifts postdate
# it. PHYSICAL area, not harvested: harvested double-counts multi-cropping, so
# shares would not sum to the land actually farmed.
SPAM_CITATION = ("IFPRI SPAM2010 v2.0 global physical area, "
                 "doi:10.7910/DVN/PRFF8V (latest global release)")
SPAM_REFERENCE_YEAR = 2010
# Shares below this are not worth a line in a readout; they are inside SPAM's
# own allocation uncertainty and inside the 1.6% quantisation of the encoding.
CROP_MIN_DISPLAY_SHARE = 0.05
# Six of the 42 classes are catch-alls. Flagged so the readout can say "other
# cereals" rather than implying a specific crop was identified.
SPAM_AGGREGATE_CODES = ("REST", "OCER", "OOIL", "OPUL", "OFIB", "ORTS")
# code -> display name. SPAM's own 42-crop vocabulary; names follow the
# MapSPAM technical documentation.
SPAM_CROP_NAMES = {
    "ACOF": "arabica coffee", "BANA": "banana", "BARL": "barley",
    "BEAN": "bean", "CASS": "cassava", "CHIC": "chickpea",
    "CNUT": "coconut", "COCO": "cocoa", "COTT": "cotton",
    "COWP": "cowpea", "GROU": "groundnut", "LENT": "lentil",
    "MAIZ": "maize", "OCER": "other cereals", "OFIB": "other fibres",
    "OILP": "oil palm", "OOIL": "other oilcrops", "OPUL": "other pulses",
    "ORTS": "other roots", "PIGE": "pigeonpea", "PLNT": "plantain",
    "PMIL": "pearl millet", "POTA": "potato", "RAPE": "rapeseed",
    "RCOF": "robusta coffee", "REST": "miscellaneous crops", "RICE": "rice",
    "SESA": "sesame", "SMIL": "small millet", "SORG": "sorghum",
    "SOYB": "soybean", "SUGB": "sugarbeet", "SUGC": "sugarcane",
    "SUNF": "sunflower", "SWPO": "sweet potato", "TEAS": "tea",
    "TEMF": "temperate fruit", "TOBA": "tobacco", "TROF": "tropical fruit",
    "VEGE": "vegetables", "WHEA": "wheat", "YAMS": "yam",
}
# Bit budget for src/textures/crops.png. The image is decoded on the CPU only
# and never sampled by the shader, but ALPHA STAYS 255 anyway: a 2D canvas
# stores premultiplied colour, so any alpha below 255 corrupts RGB on the
# getImageData round trip. That leaves 24 bits for four fields.
#   id1 6 bits (42 crops < 64), id2 6 bits, share1 6 bits, share2 6 bits
# Shares therefore quantise to 1/63 = 1.6%, which rounds a displayed whole
# percent by at most 0.8 points -- orders of magnitude inside SPAM's own
# allocation uncertainty. Gate 16 asserts the round trip.
CROP_ID_BITS = 6
CROP_SHARE_BITS = 6
CROP_SHARE_LEVELS = (1 << CROP_SHARE_BITS) - 1      # 63

# ---------------------------------------------------------------------------
# THE MOISTURE TERM. Degree of saturation, absolute -- never self-normalised.
#
# WHAT WAS WRONG. Through 2026-08-23 the build computed
#     smax  = nanmax(moist_m, axis=0)
#     sat_m = clip(moist_m / smax, 0, 1)
# i.e. it normalised each cell by ITS OWN annual maximum. That removes absolute
# wetness and leaves only within-year seasonal shape, and it is not a weakening
# of the aridity signal but a destruction of it. Measured, area-weighted over the
# 406,991 cropland cells:
#   corr(term, CV of monthly storage)  -0.886   <- what it actually measured
#   corr(term, log10 storage)          +0.147   <- what it was supposed to measure
# The driest and wettest 5% of cropland scored IDENTICALLY, 0.653 both, across a
# 272x range in real soil water: a dry cell is dry all year, so its seasonality
# is flat, so it reads saturated. The Nile valley at 6 mm mean root-zone storage
# scored 0.973, higher than NW Europe. The Indo-Gangetic Plain holds more water
# than the US Corn Belt and was down-weighted 36% against it purely for having a
# monsoon -- inverting the temperature x moisture covariance that monthly
# integration exists to capture.
#
# THE FIX IS A CHAIN, NOT A DIVISOR. TerraClimate reports EXTRACTABLE storage in
# mm -- water held above the wilting point -- so it cannot be divided by a
# capacity and called a saturation. Three steps, each with its own denominator:
#   f     = clip(storage_mm / (fc_mm - wp_mm), 0, 1)     fraction of available
#   theta = theta_wp + f * (theta_fc - theta_wp)         absolute water content
#   S     = theta / theta_sat                            degree of saturation
# This answers the question the earlier note left open -- field capacity,
# saturation, or plant-available water, which differ by ~2x. None of them alone:
# fc and wp BRACKET the range the storage lives in, and pore volume is the
# denominator that turns a content into a saturation.
#
# WHAT THIS TERM IS FOR, AND WHAT IT IS NOT FOR. Because theta has a
# wilting-point floor, S spans roughly 0.34-1.0 over cropland -- a 2.9x range, so
# the reactivity spread it produces (1.21 dex p10-p90) is no wider than the
# broken term's (1.23 dex). That is a RESULT, not a failure to fix anything: the
# moisture term is a modest wetted-surface-area modulator and it should not be
# asked to carry the aridity signal. Dissolution does not stop at the wilting
# point -- films persist -- so a term that goes to ~0 in the Nile valley (the
# clip(storage/300mm) stand-in gives 0.021) is MORE wrong than one giving 0.31.
# Aridity has to come from the export side (q, eta_transport, and the drainage
# ceiling), which is also Calabrese et al. 2022's own mechanism: their chemical
# depletion fraction collapses past PET/P = 1 because weathering products are not
# flushed, not because the rock stops dissolving.
#
# WHERE THE ARIDITY SIGNAL ACTUALLY LIVES -- MEASURED, and not where a first
# reading of the above suggests. eta_transport IS nearly saturated at
# D_w = 0.03 m/yr: area-weighted mean 0.787, 62.4% of cropland area above 0.8,
# and a wettest-5%-to-driest-5% ratio of only 4.4x. But eta_transport in
# isolation is the wrong quantity to judge. On DELIVERED CARBON the contrast is
# 9.9x uncapped, and with the drainage ceiling applied it is 125x -- against a
# 141x contrast in the drainage data itself.
#
# And the capped contrast is INVARIANT TO D_W: 125.3x at D_w = 0.001, 124.8x at
# 0.03, 124.0x at 0.1. Three orders of magnitude, no effect. The ceiling is
# linear in q and binds on 91% of cropland area, so it has already taken the
# aridity signal over. See scripts/analysis/dw_sensitivity.py.
#
# The consequence for what to do next: raising D_w is NOT the fix. It only moves
# the uncapped map, and the uncapped map is the default only because the ceiling
# is switched off pending review. The lever is FLUX_CEILING_ON, which is a
# review question, not a parameter question. Do not tune D_w to chase a contrast
# that the binding constraint already supplies.
#
# LINEARITY IS A CONVENTION, NOT A RESULT. The rate is taken as first order in S.
# Nothing in the literature constrains the exponent for mineral dissolution in
# soils; wetted surface area plausibly saturates well below full saturation,
# which argues for S**b with b < 1. Shipped as b = 1 with b in the ensemble.
#
# KNOWN INCONSISTENCY, not fixable with these inputs. The drainage q comes from
# WaterGAP histsoc, which simulates irrigation return flow, so eta_transport sees
# irrigation. A rain-fed soil-water balance does not -- hence the Nile valley
# reading dry on a field that is in fact wet. Every irrigated cell therefore has
# a moisture term and a drainage term that disagree about how wet it is. Closing
# this needs an irrigation mask as a third input.
# ---------------------------------------------------------------------------
MOISTURE_TERM = "saturation"       # "saturation" | "none" (ensemble bracket)
MOISTURE_EXPONENT = 1.0            # b in S**b; see LINEARITY above
PARTICLE_DENSITY_G_CM3 = 2.65      # quartz-dominated mineral density, for porosity
# CITATION STATUS: both strings below carry volume/page numbers that were NOT
# verified against the primary source in the session that added them (the web
# search budget was exhausted). The Calabrese reference was carried over from
# to_do.md rather than read from the paper. Check both before either appears in
# anything published, and drop the volume/pages if they cannot be confirmed.
SOILGRIDS_RETENTION_CITATION = (
    "Poggio et al. 2021, SOIL 7:217-240 (SoilGrids 2.0) [citation UNVERIFIED]; "
    "water retention wv0033/wv1500 and bulk density bdod, 0-100 cm"
)
ARIDITY_BOTTLENECK_CITATION = (
    "Calabrese et al. 2022, Environ. Sci. Technol. 56:15261-15272, "
    "'The Aridity Bottleneck' (Budyko dryness index vs chemical depletion) "
    "[citation UNVERIFIED]"
)
TERRACLIMATE_IS_END_OF_MONTH = True   # instantaneous state, not a monthly mean

# Reference condition for L1. Published, absolute, so L1 is domain-invariant.
# L1 is reported as log10(R / R_ref) on a diverging scale centred at zero and
# labelled in x-reference units -- NOT as a 0-1 index, which invites reading
# 0.5 as "half as reactive".
#
# saturation 0.6 is not arbitrary and is now physically anchored: the cropland
# median field capacity is 313 mm against a 500 mm pore volume over 0-100 cm, so
# S = 0.63 IS field capacity. The reference cell is a soil at field capacity.
L1_REF = {"pH": 6.5, "T_soil_C": 15.0, "saturation": 0.6}
L1_LOG_HALF_RANGE = 30.0          # 'A': clamp at +/- log10(A)

# ---------------------------------------------------------------------------
# Transport limitation (Maher & Chamberlain 2014, Science 343, 1502).
#   eta_transport = q / (q + D_w)
#
# D_w IS constrained by the literature, contrary to an earlier note here. Read
# from the paper directly: their fitted Damkohler coefficients span roughly
# 0.001-0.3 m/yr, with 0.3 stated as the GLOBAL MAXIMUM and 0.03 as the
# collisional/craton divide. An earlier version of this file used 0.5 as the
# default with a 0.1-2.0 sensitivity range -- i.e. a default ABOVE their global
# maximum and a range almost entirely outside the published one. Because
# eta = q/(q+D_w), too large a D_w suppresses eta everywhere, so that error was
# itself part of why the drainage term dominated the whole map.
#
# Magnitude of the correction, at q = 0.35 m/yr:
#   D_w 0.5  -> eta 0.41   (the old default)
#   D_w 0.3  -> eta 0.54   (their global maximum)
#   D_w 0.03 -> eta 0.92   (their craton/collisional divide)  <- new default
#
# TWO CAVEATS, both important and neither resolved:
#  1. Their fit uses the Gaillardet et al. 1999 river dataset, which the paper
#     states is "mostly draining granitic lithologies", with basalt asserted to
#     "follow the same general behavior" only by analogy in a supplementary
#     figure. There is NO basalt-specific empirical D_w.
#  2. Crushed ERW feedstock has far more reactive surface area than natural
#     saprolite, which shortens the equilibration length and genuinely argues
#     for a higher effective D_w than a natural-catchment fit gives. A value
#     above 0.3 may therefore be defensible for ERW -- but it needs an argument,
#     which is why it lives in its own clearly-labelled sensitivity case below
#     rather than in the default.
# ---------------------------------------------------------------------------
TRANSPORT_LIMITATION_DEFAULT_ON = True     # promoted: q and D_w are both real now
DAMKOHLER_DW_M_YR = 0.03
DAMKOHLER_DW_RANGE = (0.001, 0.3)
DAMKOHLER_SOURCE = "Maher & Chamberlain 2014, Science 343, 1502 (Fig. 2 contours)"

# ---------------------------------------------------------------------------
# WHICH WATER FLUX IS q? Measured, not assumed. See
# scripts/analysis/drainage_variable.py, which produced every number below.
#
# WaterGAP2-2e publishes four candidates and they differ by a factor of 5 over
# cropland (area-weighted median, mm/yr):
#
#   qr    groundwater recharge      74.8   water reaching the AQUIFER
#   qsb   subsurface runoff         75.2   reached the stream through the soil
#   qs    surface runoff            83.7   fast component
#   qtot  total runoff = qs + qsb  177.8   catchment discharge per unit area
#
# THE MAP USED qr THROUGH 2026-08-03, AND IT HAD A VISIBLE DEFECT. qr is
# EXACTLY ZERO on 0.10% of cropland area, concentrated in river deltas -- the
# Mekong (23% of its cropland area rendered "negligible"), the Red River (24%),
# the middle Yangtze (4%). In a delta the water table is at the surface, so
# nothing percolates to an aquifer and WaterGAP correctly reports zero recharge;
# but field drainage still leaves laterally to canals, carrying its bicarbonate
# with it. Zero recharge is not zero drainage, and the map was reading it as
# "no ERW potential" in some of the wettest cropland on Earth.
#
# qsb IS NOT THE FIX, though it looks like the obvious one. In WaterGAP, recharge
# feeds the groundwater store and that store discharges as baseflow, so over a
# 30-year mean qsb is very nearly qr relabelled: global land medians 33.5 vs 32.6
# mm/yr, ratio 1.00 at the median over cropland, log-log correlation 0.81. It
# does clear the delta zeros, but it introduces WORSE ones of its own where
# groundwater is heavily pumped -- 26% of the Indo-Gangetic Plain and 4% of the
# US Corn Belt go dark, taking the global dark class from 0.79% to 6.60% of
# cropland area. Trading deltas for the Indo-Gangetic Plain is a bad trade.
#
# qtot IS THE DEFAULT, for two reasons that agree:
#  1. CONSISTENCY. Maher & Chamberlain fit D_w against the Gaillardet river
#     dataset, i.e. against catchment discharge per unit area, which IS qtot.
#     Driving a qtot-calibrated D_w with recharge is a units-of-water mismatch
#     that penalises the flux twice -- the same double-penalty logic that
#     governs DAMKOHLER_TAU_APPLIED_IN_ETA above.
#  2. IT FIXES THE DEFECT WITHOUT CREATING ANOTHER. Dark class 0.79% -> 0.10%
#     of cropland area; every delta clears; NO region gets worse; and the
#     implausible-dissolution tail (>90% weathered in year 1) only moves
#     0.63% -> 0.77% of area, so it does not undo the shrinking-core fix.
#
# THE HONEST CAVEAT, which is why qr stays as a documented sensitivity rather
# than being deleted: surface runoff has little contact time with topsoil rock,
# so qtot credits water that arguably weathered nothing. The counter is that
# D_w is an EFFECTIVE parameter fit at catchment scale, where nearly all runoff
# has passed through regolith, so it already absorbs that. Treat qr and qtot as
# a bracket: 2.149 vs 2.488 GtCO2/yr global gross, a 16% spread, small next to
# the map's other uncertainties and reported as such.
#
# WHERE THE CHANGE LANDS -- broad, not a delta patch. +7% to +30% by latitude
# band, largest in the irrigated subtropics: the Indo-Gangetic Plain and
# Pakistan (15-30N, 65-80E) account for the biggest absolute gains, which is
# exactly the case eta_transport's docstring already flagged when it said "q
# must include irrigation return flow on irrigated cells".
#
# To switch back, change DRAINAGE_VARIABLE to "qr" and rebuild. Nothing else.
# ---------------------------------------------------------------------------
DRAINAGE_VARIABLE = "qtot"
DRAINAGE_SOURCES = {                       # variable -> data/interim filename
    "qr":   "drainage_recharge_mmyr.tif",
    "qsb":  "drainage_qsb_mmyr.tif",
    "qs":   "drainage_qs_mmyr.tif",
    "qtot": "drainage_qtot_mmyr.tif",
}
DRAINAGE_LABELS = {
    "qr":   "WaterGAP2-2e groundwater recharge",
    "qsb":  "WaterGAP2-2e subsurface runoff (qtot - qs)",
    "qs":   "WaterGAP2-2e surface runoff",
    "qtot": "WaterGAP2-2e total runoff",
}
DRAINAGE_SENSITIVITY = "qr"                # the conservative bound, for the band
# Area-weighted cropland medians, mm/yr, from drainage_variable.py. Recorded so a
# future change to the reduction is caught rather than absorbed.
DRAINAGE_MEDIAN_MM_YR = {"qr": 74.8, "qsb": 75.2, "qs": 83.7, "qtot": 177.8}

# Explicitly separate, explicitly not the default. Use only with the
# surface-area argument stated alongside any result that depends on it.
DW_ERW_ENHANCED_SENSITIVITY = (0.3, 1.0)
DW_ERW_ENHANCED_RATIONALE = (
    "Crushed feedstock has orders of magnitude more reactive surface area than "
    "saprolite, shortening equilibration time and raising effective D_w above "
    "the natural-catchment fit. Not empirically constrained for ERW."
)

# The tau question, RESOLVED from the primary source, August 2026. Recorded here
# because it changes what D_w means rather than what it is.
#
# M&C Eq. 3 as printed is C = C_eq * (tau*D_w/q) / (1 + tau*D_w/q) with
# tau = e^2, so the dimensionless factor on the FLUX is q/(q + tau*D_w). tau is
# NOT already folded into the Fig. 2 contour labels: those labels reproduce to
# two significant figures from the paper's own printed R_n,max = 1085 umol/L/yr,
# C_eq = 375 umol/L and L_phi = 0.1 m using bare D_w = L_phi/T_eq, while Fig. 2B's
# plotted flux plateaus match C_eq*tau*D_w and are 0.8 of a decade off without
# tau. So applying tau on top of a Fig-2-derived D_w is correct.
#
# Consequence: tau*D_w = 2.217 m/yr at D_w = 0.3, or 0.222 at D_w = 0.03. Either
# way that is at or above the p90 of cropland drainage (229 mm/yr), so ALL
# cropland sits on the low-q limb where C -> C_eq and the flux is C_eq*q. On that
# limb the rate law, mineralogy, grind and temperature drop out of the flux
# entirely -- Maher 2010 p. 104 states it directly: beyond L_eq the flux c_eq*q
# "conveys no information on the actual weathering kinetics or available surface
# area."
#
# WE DELIBERATELY DO NOT APPLY tau INSIDE eta_transport. In M&C the q/(q+tau*D_w)
# factor multiplies the kinetic-limit FLUX tau*L_phi*R_n, which carries C_eq with
# it; our eta multiplies a dimensionless relative reactivity, which does not. So
# swapping tau in on its own drops the median 21.9x and undershoots the physical
# ceiling by ~5x, double-penalising a rate that is ALREADY anchored to field
# data. The ceiling below is the correct expression of the same physics.
DAMKOHLER_TAU = 2.718281828459045 ** 2      # e^2, M&C 2014 Eq. 3 and Table S1
DAMKOHLER_TAU_APPLIED_IN_ETA = False
DAMKOHLER_TAU_SOURCE = (
    "Maher & Chamberlain 2014 Eq. 3 + Table S1 ('tau -- Scaling parameter "
    "(e^n) -- e^n, n = 2'); SI p.1 'allows for the concentration to reach "
    "99.9% of ceq when the travel time equals the equilibrium time'"
)

# ---------------------------------------------------------------------------
# DRAINAGE-CONCENTRATION CEILING on the carbon flux
#
# The carbon reported has to leave the field dissolved in the water that leaves
# the field. That bounds it at  q * [HCO3-]_max * 44,  independently of how fast
# the rock dissolves. Without this bound the model implied 28.5 mmol/L HCO3- in
# drainage at the median cropland cell.
#
# WHAT SETS [HCO3-]_max. Not the cell's pre-treatment pH: pH is endogenous, and
# adding base cations at fixed pCO2 raises alkalinity and pH together (that is
# the same carbonate equation eta_dic uses, read the other way). Holding pH fixed
# gives 0.42 mmol/L at the median, which is ~8-15x too strict -- and is, to two
# significant figures, the observed mean alkalinity of streams draining
# UNAMENDED volcanic rock (0.42 mmol/L, Meybeck, EOLSS "Chemical Characteristics
# of Rivers" Table 1A). A good baseline; the wrong ceiling.
#
# The bound is where the rising pH meets CARBONATE SATURATION. Solving charge
# balance 2[Ca]+2[Mg] = [HCO3-] simultaneously with fixed pCO2 and calcite
# saturation state Omega gives the closed form in kinetics.alkalinity_ceiling.
#
# Omega = 1 is the strict thermodynamic reading. Omega = 10 is the shipped
# default because carbonate precipitation is kinetically inhibited by DOC and
# phosphate: Zhang et al. 2022 state precipitation in river water "is generally
# observed to be negligible at Omega < 10" and run their own model over
# Omega = 5-25, and soils carry far more DOC than rivers. Both are reported.
#
# FIVE INDEPENDENT ANCHORS on the resulting 3.0-6.5 mmol/L, none sharing
# assumptions with the closed form:
#   Zhang et al. 2022 riverine carbon transport potential, back-converted
#     (7.1-21.3 GtCO2/yr over 37,288 km3/yr global discharge)   4.3-13.0 mmol/L
#   Hamilton et al. 2007 Midwest agricultural TILE DRAINAGE and
#     limed-row-crop porewater (the closest analogue there is)     1-7 mmol/L
#   Meybeck pristine-river 99th percentile (363 mg/L)                5.95
#   Meybeck carbonate-terrain streams, the natural high case         3.15
#   soil-pH backstop: holding 10 mmol/L needs pH 8.16 at 4,000 uatm,
#     above essentially all non-calcareous cropland              ceiling ~10
#
# WHAT THIS IS NOT. It is not the reason the map's level is high. Field trials
# achieve 0.11-0.75 mmol/L, i.e. 5-10x BELOW this ceiling, because cations are
# retained in secondary phases rather than exported (10-50x more retained than
# exported, Hammes et al. 2025). The ceiling is a rail that makes an impossible
# claim impossible; the level problem is the lab-to-field rate discrepancy and
# belongs to the kinetics item. See to_do.md items 0 and 2.
# ---------------------------------------------------------------------------
# ---- OFF BY DECISION, 2026-08-03. Not abandoned, and not reverted.
#
# The bound below is implemented, gated, documented and shipped in the texture --
# it is simply not APPLIED, because it moves the map's absolute level several-fold
# and Zeke wants the wider ERW community to weigh in before it does. Everything
# needed to turn it back on is present and tested.
#
# TO RE-ENABLE: set this to True and re-run scripts/build_v0.py. That is the whole
# procedure. The round trip is verified: gate 12 flips from a reported diagnostic
# back to a hard PASS, the Methods panel swaps its "computed but not applied"
# flagbox for the active description, the limiting-factor layer regains its fourth
# class, and the hover readout regains its "Without the drainage limit" row. No
# other file needs touching.
#
# WHAT STAYS LIVE WHILE IT IS OFF, deliberately:
#   - the ceiling is still computed, still written to tex2.b, and still emitted in
#     engine_constants.js, so re-enabling needs no data migration
#   - gate 12 still REPORTS the exceedance (98.9% of cropland area, median 6.2x)
#     instead of vanishing along with the cap
#   - the Methods panel carries a flagbox saying the CO2 layer is an upper bound on
#     dissolution rather than carbon shown to leave
#   - section 11 of analyse_deployments.py still runs the same test against the
#     verified deliveries, since that is a finding about the deliveries and not a
#     setting of this model
#
# WHAT THIS FLAG NOW CONTROLS. Since 2026-08-04 the viewer carries a runtime
# toggle for the ceiling under Advanced ("Apply the drainage limit"), because the
# bound is written to tex2.b whether or not it is applied and the shader can
# therefore switch it live. So this constant sets the SHIPPED DEFAULT -- the state
# the map lands in -- rather than being the only way to turn the bound on. The
# Python side still follows it exactly: build_v0's `cdr` array, gate 12 and the
# cost screen all key off this flag, so a reader who wants the bound applied in
# the DERIVED PRODUCTS, not just in the browser, still flips it here and rebuilds.
#
# Keep it False while the bound is out for review. Flipping it to True makes an
# unreviewed bound the headline figure, which is the thing the review exists to
# avoid; the toggle lets anyone see the consequence without that.
#
# The one thing to know if you re-enable: gate 2b now reports the global total
# INSIDE its pre-registered 0.5-4.0 band (0.910 GtCO2/yr). It was below the band
# until the drainage variable was corrected to total runoff -- see
# DRAINAGE_VARIABLE, which moved the bounded total 2.5x.
FLUX_CEILING_ON = False
FLUX_CEILING_OMEGA = 10.0                  # shipped default, kinetically inhibited
FLUX_CEILING_OMEGA_STRICT = 1.0            # thermodynamic reading, reported alongside
FLUX_CEILING_OMEGA_RANGE = (1.0, 10.0)
# Share of the divalent-cation charge carried by Ca rather than Mg. Only Ca
# constrains calcite; magnesite is kinetically inhibited at surface temperature,
# so a lower f_Ca RAISES the ceiling. Basalt releases Ca and Mg in roughly equal
# charge, so 0.5. Sensitivity at 10,000 uatm, Omega = 1: f_Ca 0.9 -> 3.38,
# 0.5 -> 4.11, 0.2 -> 5.57, 0.05 -> 8.85 mmol/L.
FLUX_CEILING_F_CA = 0.5
FLUX_CEILING_F_CA_RANGE = (0.2, 0.9)
FLUX_CEILING_SOURCE = (
    "calcite saturation at the cell's own soil pCO2 and temperature, with "
    "charge balance 2[Ca]+2[Mg] = [HCO3-]; Plummer & Busenberg 1982 constants. "
    "Omega < 10 inhibition after Zhang et al. 2022, Limnol. Oceanogr. 67, "
    "doi:10.1002/lno.12244"
)
# Anchors above, as data so the app and the docs cannot drift from this file.
FLUX_CEILING_ANCHORS_MMOL_L = {
    "Zhang 2022 riverine CTP, back-converted": (4.3, 13.0),
    "Hamilton 2007 Midwest tile drainage / porewater": (1.0, 7.0),
    "Meybeck pristine rivers, 99th percentile": (5.95, 5.95),
    "Meybeck carbonate-terrain streams": (3.15, 3.15),
    "field trials, ACHIEVED under ERW (not a ceiling)": (0.11, 0.75),
}

# ---------------------------------------------------------------------------
# Feedstock delivered cost.
#
# Deliberately simple, and every number stated rather than buried. This is a
# screening cost surface, NOT a routed haul model: distance is great-circle times
# a tortuosity factor. Real routing needs a friction surface or a road graph.
#
# GATE COST: $10/t, revised DOWN from $25/t. The old figure reasoned from the
# wrong product entirely.
#
# ERW does not buy graded construction aggregate. It buys quarry FINES -- crusher
# dust, screenings, manufactured-sand feed -- which is the cheapest product class
# a quarry makes and in many markets an unsold byproduct it stockpiles. The old
# $25/t started from the USGS blended crushed-stone unit value (~$15-18/t f.o.b.,
# an average across ALL graded products and end uses) and then reasoned UPWARD for
# "finer grinding". Both halves of that were wrong: fines sit below the blended
# average, not above it, and the target sizes largely overlap what fines already
# deliver, so little or no extra grinding is needed.
#
# What operators actually report:
#   Lithos          ~$12/t, ground basalt delivered by quarries described as
#                   "delighted to be rid of" it
#   Isometric       states industry-wide that "rock dust costs less than $10 per
#                   tonne of basalt", calling waste fines an ideal ERW feedstock
#   InPlanet (BR)   ~$10/t quarry byproduct, D50 111 um straight from the stream
#   Brazil          po de pedra at R$45-50/t (~$8-10/t), quarry price list
#   India           raw crusher dust reported as low as ~Rs200/t (~$2-3/t), vs
#                   ~$17-26/t for finished manufactured sand
#   Free            UNDO, Mati Carbon and Silicate all supply material to farmers
#                   at no charge, so the floor really can reach $0
#
# Grinding, where needed, is small: from a 300 um waste-fines baseline, reaching
# p80 100 um costs ~$1/t and p80 50 um ~$2/t (Frontiers in Climate 2024).
#
# NOTE this constant does NOT move the map. Because the penalty applies to the
# haul increment only, v = 1/(1 + haul/S), the gate cost cancels out of the
# multiplier entirely. Lowering it changes the REPORTED $/t and $/tCO2 -- which is
# the point, since those were overstated -- without perturbing the spatial pattern.
# ---------------------------------------------------------------------------
FEEDSTOCK_GATE_COST_USD_T = 10.0     # quarry fines at the gate
FEEDSTOCK_GATE_COST_RANGE = (0.0, 15.0)
FEEDSTOCK_GATE_REGIONAL_USD_T = {   # indicative, not yet applied spatially
    "BR": 9.0,      # po de pedra, quarry price list
    "IN": 3.0,      # raw crusher dust; weakly sourced, single vendor figure
    "US": 12.0,     # Lithos reported
}
FEEDSTOCK_GATE_SOURCE = (
    "Operator-reported quarry-fines prices (Lithos ~$12/t, Isometric <$10/t, "
    "InPlanet ~$10/t); Brazilian po de pedra R$45-50/t; Indian crusher dust "
    "~Rs200/t. Several operators supply free, so the true floor can be $0.")
ROAD_TORTUOSITY = 1.35               # great-circle -> road distance

# TRUCK ONLY. Basalt for ERW is rarely railed today, and even where rail exists
# there is still a first- and last-mile trucking leg, so a rail rate would flatter
# the cost of moving this material in current practice.
#
#   cost_haul = truck_rate * road_distance
#
# THIS REVERSES A CHANGE WE MADE EARLIER, AND THE EARLIER REASONING WAS BAD.
# A truck-only model was replaced with min(truck, rail + transload) because the
# truck median "looked implausible" at $252/t. Two errors in that:
#   1. $252 was the median over ALL LAND, not over cropland. Cropland sits much
#      closer to quarries. Truck-only on cropland is $61/t median, which is
#      entirely plausible and always was.
#   2. Having mis-read the number, we added a mechanism to make the output look
#      better rather than diagnosing why it looked odd. That is backwards.
# The lesson is the standing one: when a number looks wrong, find out why before
# changing the model.
#
# Rail can come back if and when a rail-served-quarry layer exists to gate it,
# rather than being assumed available everywhere.
# HOW CONFIDENT ARE WE IN 0.12? NOT VERY, AND THIS IS THE WEAKEST NUMBER IN THE
# ECONOMIC HALF OF THE MODEL. Stated plainly because it is easy to mistake for a
# sourced parameter:
#
#  1. It began as a citation-free assumption. It now has benchmarks -- see
#     docs/TRUCK_RATE_SOURCES.md (2026-08-24) -- but benchmarks are not a
#     calibration, and they show the single global value is regionally wrong:
#     USDA grain-truck rates put the US at $0.10-0.12/t-km at this map's median
#     haul (0.12 is a good US number), while Brazil sits near $0.05-0.06 and
#     India near $0.045-0.05, so 0.12 overstates delivered cost ~2x in the two
#     countries with the most ERW deployment. USDA's distance curve also implies
#     a fixed $4-6/t per-trip component this model lacks.
#  2. Nothing validates it. There is no cost gate in build_v0.py, no cost row in
#     docs/VALIDATION.md, and no comparison against delivered costs in the
#     verified-delivery fixture. The whole delivered-cost surface is unvalidated,
#     unlike the physical layers.
#  3. A single global rate cannot be right. Real haulage rates vary severalfold
#     with fuel price, backhaul availability, road quality, truck size limits,
#     minimum load charges, and whether the operator owns the fleet. Brazil,
#     India and the US Midwest are not one number.
#  4. It is a per-km rate applied to a distance that is itself modelled --
#     great-circle x ROAD_TORTUOSITY, with no routing, no terrain and no border
#     crossings -- so the rate and the distance carry independent error that
#     multiply.
#  5. It is NOT weakly held in its effect. Unlike the gate cost, this rate moves
#     the map: v_cost depends on the haul increment, so the spatial pattern of
#     the economic discount and the cost-screened headline total both scale with
#     it.
#
# What can be said for it: 0.12 puts the cropland median delivered cost at $43/t
# and the p90 at $123/t, and USDA GTOR (Q2 2026) makes it a genuinely good US
# rate: $0.120/t-km at 100-mile hauls, $0.102 at 200 miles, against this map's
# 171-mile median haul. That upgrades the default from "plausible" to "sourced
# for the US" -- and simultaneously establishes it is the WRONG number for
# Brazil, India, and most of Asia. Regionalisation is the fix, tracked in
# to_do.md; the full source table is docs/TRUCK_RATE_SOURCES.md.
#
# THE RANGE BELOW IS AN EXPLORATION BRACKET, NOT A PUBLISHED INTERVAL. The
# endpoints are chosen to span plausible regional variation so the slider can
# show how much of the economic layer depends on this one unsourced number.
# Do not quote them as a confidence interval.
TRUCK_COST_USD_T_KM = 0.12    # retained as the US anchor and the uniform
                              # FALLBACK if the country raster cannot be built;
                              # the shipped surface uses TRUCK_RATE_GROUPS below
TRUCK_COST_RANGE = (0.03, 0.30)
TRUCK_COST_IS_UNSOURCED = False   # sourced for the US; regional entries carry
                                  # their own source and vintage below

# ---------------------------------------------------------------------------
# REGIONAL TRUCK RATES, USD per tonne-km, applied spatially at cost-build time
# (prep_feedstock.py rasterises them from Natural Earth admin-0). Full source
# table with quotes and conversion arithmetic: docs/TRUCK_RATE_SOURCES.md.
#
# Why regional: a single global rate is not wrong on average, it is wrong in a
# STRUCTURED way -- $0.12 is a good current US number (USDA GTOR Q2 2026) and
# ~2-2.5x too high for Brazil and India, the two most active ERW deployment
# countries. Because the gate cancels out of v_cost, the truck rate is the only
# cost parameter doing spatial work, so that bias mapped straight into
# suitability-with-cost and penalised exactly the cropland the physics favours.
#
# Group membership resolves in order: explicit ISO list first, then continent,
# then TRUCK_RATE_DEFAULT. Vintage flags matter: only the US rate is current;
# Brazil/China/Europe rest on the World Bank's 2007 corridor prices inflated by
# US CPI (a crude adjustment), and India on a 2021 national average. Replace
# entries with current primaries as they are sourced, not by re-tuning.
TRUCK_RATE_GROUPS = {
    "US/Canada": {
        "rate": 0.10, "iso": ["US", "CA"],
        "source": "USDA GTOR Q2 2026: $0.120/t-km at 100 mi, $0.102 at 200 mi, "
                  "25 t payload; midpoint of the map's haul distribution",
        "vintage": 2026},
    "Europe": {
        "rate": 0.09, "continents": ["Europe"],
        "source": "World Bank 2009 Fig 2.1: W Europe 5 c/t-km (2007) x1.55 CPI "
                  "~0.078; CNR France cost $1.59/veh-km 2007. WEAK, dated",
        "vintage": 2007},
    "Brazil/Latin America": {
        "rate": 0.055,
        "iso": ["MX", "GT", "BZ", "HN", "SV", "NI", "CR", "PA", "CU", "DO",
                "HT", "JM", "TT"],
        "continents": ["South America"],
        "source": "World Bank 2009 Fig 2.1: Brazil 3.5 c/t-km (2007) x1.55 CPI "
                  "= 0.054. Dated; ANTT minimum-freight tables are the upgrade",
        "vintage": 2007},
    "India/South Asia": {
        "rate": 0.045, "iso": ["IN", "PK", "BD", "LK", "NP", "BT"],
        "source": "NITI Aayog/RMI 2021 Exhibit 3-1: road INR 3.6/t-km = $0.048 "
                  "at 2021 fx; WB 2007 Pakistan 2 c/t-km corroborates the level",
        "vintage": 2021},
    "China/SE Asia": {
        "rate": 0.07,
        "iso": ["CN", "TW", "VN", "TH", "ID", "MY", "PH", "KH", "LA", "MM"],
        "source": "World Bank 2009 Fig 2.1: China 5 c/t-km (2007) x1.55 CPI "
                  "= 0.078, rounded down for the cheaper SE Asian members. WEAK",
        "vintage": 2007},
    "Africa": {
        "rate": 0.11, "continents": ["Africa"],
        "source": "World Bank 2009 Fig 2.1: corridor PRICES 6-11 c/t-km (2007), "
                  "cartel-inflated above cost; mid-range x CPI. Wide spread",
        "vintage": 2007},
}
# Everything unmatched: Russia, Central Asia, Middle East, Australia/NZ, Japan,
# Korea, Oceania. 0.08 is a judgment call between the US and emerging-Asia
# levels, NOT a sourced figure -- flagged so nobody quotes it as one.
TRUCK_RATE_DEFAULT = 0.08
# Pinned to the default BEFORE continent matching. Natural Earth files Russia
# under continent "Europe", which would give it the European rate; nothing in
# docs/TRUCK_RATE_SOURCES.md supports that, so it stays at the unresearched
# default rather than inheriting a rate by cartographic convention.
TRUCK_RATE_ISO_DEFAULT = ["RU"]
TRUCK_RATE_MULT_RANGE = (0.25, 2.5)   # the Advanced slider, a global multiplier
                                      # on the regional surface

# The FIXED per-trip haul component, $/t: loading, unloading and positioning,
# paid once regardless of distance. Decomposed from the same USDA GTOR curve:
# the per-mile rate falls with distance because this fixed cost is spread over
# more km ($7.53/t total at 25 mi vs $19.36 at 100 mi implies fixed $3.6-6.0/t
# plus $0.083-0.098/t-km marginal). Consequences, both deliberate:
#   - v_cost no longer reaches 1.0 anywhere: at zero distance the transport
#     penalty is F/S, i.e. v_max = 1/(1 + F/S) ~ 0.952. The old rule
#     "v = 1 exactly at the gate" is superseded -- even a farm beside the
#     quarry pays loading and unloading.
#   - The gate still cancels exactly. F is transport, not gate.
HAUL_FIXED_USD_T = 5.0


def truck_rate_for(iso_a2, continent):
    # Regional truck rate for a country; ISO match wins over continent.
    for _g in TRUCK_RATE_GROUPS.values():
        if iso_a2 and iso_a2 in _g.get("iso", ()):
            return _g["rate"]
    if iso_a2 in TRUCK_RATE_ISO_DEFAULT:
        return TRUCK_RATE_DEFAULT
    for _g in TRUCK_RATE_GROUPS.values():
        if continent and continent in _g.get("continents", ()):
            return _g["rate"]
    return TRUCK_RATE_DEFAULT
FEEDSTOCK_COST_SOURCE = ("USGS crushed-stone unit values for the gate cost; "
                         "truck haul rate is an ASSUMPTION with no citation and "
                         "no validation -- see TRUCK_COST_USD_T_KM. Truck only: "
                         "basalt is rarely railed, and rail still needs "
                         "first/last-mile truck")

# Outcrop distance -> quarry distance where no usable inventory exists.
# MEASURED at 2.0 inside the trusted MRDS area (prep_feedstock.py reports it),
# not assumed. An earlier value of 3.0 here was a guess.
OUTCROP_TO_QUARRY_FACTOR = 2.0

# Delivered-cost value function. Unlike the physical terms, cost IS a compensatory
# economic factor -- expensive rock is bad, not impossible -- so it keeps a
# non-zero floor and does NOT annihilate the score.
#
# Penalty applies to the HAUL INCREMENT ONLY, not to total delivered cost:
#
#     v_cost = 1 / (1 + (cost - gate) / S)
#
# so the gate cost cancels: it is unavoidable everywhere -- you have to buy and
# crush the rock wherever you are -- so charging a site for it would charge it
# for something it cannot avoid and that carries no spatial information. Since
# HAUL_FIXED_USD_T was added (Aug 2026), cost - gate = F + r*d > 0 everywhere,
# so v tops out at 1/(1 + F/S) ~ 0.95 at zero distance rather than reaching 1:
# even a farm beside the quarry pays loading and unloading.
#
# This replaces five hand-placed knots that were 1.0 at $25 but ramped hard: a
# cell at the CROPLAND MEDIAN of $61/t lost 38%, which is a heavy penalty for a
# workable delivered price. The new form is gentler in the working range (0.74 at
# $61), monotone, smooth, and has ONE stated parameter instead of five.
#
# S is an editorial choice and there is no non-arbitrary value for it, so it is
# named rather than buried: S = $100/t puts the half-penalty point at $125/t
# delivered. Sensitivity, as v at $61 / $138 / $400 per tonne:
#     S = $75  -> 0.68 / 0.40 / 0.17
#     S = $100 -> 0.74 / 0.47 / 0.21     <- default
#     S = $150 -> 0.81 / 0.57 / 0.29
# The readout reports feedstock cost per tonne CO2 alongside, so a reader can
# judge the trade-off in units that mean something rather than trusting S.
HAUL_PENALTY_SCALE_USD_T = 100.0
COST_FLOOR = 0.05

# Screen used by the headline total when the economics toggle is ON. Per tonne of
# CO2, NOT per tonne of rock, because that is the quantity a buyer transacts in and
# because the two screens keep very different cells: rock cost is nearly
# uncorrelated with CDR here (a <$100/t-rock screen keeps 83.7% of area and 83.3%
# of the carbon), whereas a $/tCO2 screen rewards cells that produce enough carbon
# to justify the haul.
#
# Effect at 200: 0.503 GtCO2/yr on 0.122 Gha, i.e. 23% of the unscreened total on
# 10% of the area. For scale the unscreened global mean is ~$1,000/tCO2 on
# feedstock and haul alone -- before grinding, spreading, MRV or any net deduction
# -- which is what makes the screen bite so hard.
#
# It bounds ACQUISITION AND TRANSPORT ONLY. It is not a levelised cost and must not
# be read as one.
# Basis, corrected 2026-08. The screen used to divide a ONE-OFF rock cost by ONE
# YEAR of CDR, which overstates cost by ~3.2x because the rock keeps weathering.
# It now uses the discounted carbon a single application delivers over 10 years,
# run through the same shrinking-core model the map draws: retreat accumulates
# linearly with time, so cumulative Fw = G(u*t) and year t delivers the increment.
#
#   cost at t = 0; tonnes at the end of years 1..10, discounted at (1+r)^-t
#
# Effect at the median cell: $946/tCO2 on the old basis, $299 on this one.
#
# THE DISCOUNT RATE BARELY MATTERS; THE HORIZON DOES. Across 0-12% the median moves
# $253-$367 and the qualifying total only -21%. Across horizons at 5% it moves
# $993 (1 yr) -> $488 (3) -> $380 (5) -> $299 (10). So the decision that mattered
# was using any multi-year window at all, not which rate.
#
# Discounting physical carbon is a convention, not a fact: it is equivalent to
# discounting the revenue a buyer receives, which is right for cost-effectiveness,
# but a tonne in ten years is not physically worth less than a tonne today.
#
# OPTIMISTIC IN ONE RESPECT. Shrinking core captures the geometric slowdown as
# particles shrink but NOT surface passivation, secondary-mineral armouring or
# depletion of the most reactive phases, so real multi-year yields decline faster
# than the 70%-by-year-10 this implies.
#
# AND IT INTERACTS WITH THE DRAINAGE CEILING. With the ceiling on, each year's
# EXPORT is capped, so extra years buy much less: median $953/tCO2 at 5% and only
# 6.8% of area under $200. The screen follows FLUX_CEILING_ON for that reason.
COST_SCREEN_USD_PER_TCO2 = 100.0
COST_SCREEN_YEARS = 10
COST_SCREEN_DISCOUNT_RATE = 0.05


def cost_value(cost_usd_t):
    """v_cost from delivered $/t. Defined here so Python and the emitted JS
    constants cannot disagree about the shape."""
    import numpy as _np
    x = _np.asarray(cost_usd_t, dtype=float)
    v = 1.0 / (1.0 + _np.maximum(x - FEEDSTOCK_GATE_COST_USD_T, 0.0)
               / HAUL_PENALTY_SCALE_USD_T)
    return _np.clip(v, COST_FLOOR, 1.0)

# Cost is the FIRST genuinely tradeable factor in this model, so unlike the
# physical terms it is a real preference rather than a what-if. It enters as an
# exponent on a compensatory multiplier:
#
#     suitability = f(gross CDR) * v_cost ^ w_cost
#
# The physical half still annihilates -- zero removal is zero suitability at any
# cost -- while expensive rock reduces the score without zeroing it, because
# expensive is bad, not impossible.
#
# DEFAULT ON as of 2026-08. It was off, on the argument that the landing map
# should be a statement about physical potential and economics a layer the reader
# opts into. That argument lost to a stronger one: the unscreened map implies
# 2.15 GtCO2/yr across essentially all cropland, and almost none of that is
# deployable at any price a buyer would pay. Presenting the physical figure first
# and the affordable one behind a toggle put the less useful number in front.
#
# The counter-argument has not gone away and is worth keeping in view: economics
# adds a gate cost, a truck rate, a tortuosity factor and a quarry inventory of
# very uneven completeness, none of which is as well constrained as the physics.
# The mitigation is that the toggle still switches it OFF, the caption states the
# basis on both settings, and turning it off is a visible change rather than a
# hidden one. If the cost inputs are ever shown to be badly wrong, flip this back
# rather than patching around it.
#
# On means 1.0, the straightforward reading of "delivered cost matters". There is
# deliberately no middle default: inventing a 0.5 to soften it would be an
# unlabelled editorial thumb on the scale.
COST_EXPONENT_DEFAULT = 1.0
COST_EXPONENT_ON = 1.0

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
    # The moisture term must be MONOTONE IN WETNESS. This is the gate that would
    # have caught the self-normalisation defect: under it the driest and wettest
    # 5% of cropland both scored 0.653, a ratio of 1.00, and the correlation with
    # log10 storage was +0.147. Any term that normalises a cell by its own annual
    # maximum fails both. The thresholds are deliberately weak -- a term that is
    # merely ordered correctly clears them -- because the point is to catch a
    # sign error, not to legislate a slope.
    "moisture_wet_dry_ratio_min": 1.25,
    "moisture_storage_corr_min": 0.50,
    # Stoichiometric ceiling is computed PER ARCHETYPE from its oxide
    # composition, not set as one global number -- an early draft used a single
    # basalt-derived 0.45 and ultramafic legitimately exceeded it. The only
    # absolute bound is pure forsterite, the most CO2-dense silicate in
    # CDRMAX_REFERENCE; anything above that is a bug.
    "max_tco2_per_t_any_feedstock": 1.30,
    # Observed first-period fraction weathered in the 2026 verified deliveries
    # spans roughly 15-56%/yr, so an earlier value of 0.20 here was FALSIFIED BY
    # THE DATA rather than being a conservative choice. Raised above the observed
    # maximum. The bound is now a bug-catcher, not a model assumption: the
    # dissolution function saturates smoothly toward 1 and cannot exceed it.
    "max_annual_dissolved_fraction": 0.70,
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
    # A cell that receives more than a metre of rain a year cannot drain a
    # millimetre. This is not a tuned tolerance, it is an impossibility: any
    # water flux failing it is a defect in the drainage VARIABLE, not a dry
    # climate. Installed after groundwater recharge (qr) was found to be exactly
    # zero across the Mekong, Red River and middle Yangtze deltas -- 0.10% of
    # cropland area drawn as "no ERW potential" in some of the wettest cropland
    # on Earth. The allowance is for 0.5-deg cells that straddle a wet/arid
    # boundary, not for whole regions. See DRAINAGE_VARIABLE.
    "wet_but_undrained_area_frac": 0.0005,      # 0.05% of cropland area
    "wet_precip_mm_yr": 1000.0,
    "undrained_q_mm_yr": 1.0,
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
