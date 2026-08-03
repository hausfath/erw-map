"""
Mineral dissolution kinetics and carbonate-system efficiency for the ERW Atlas.

Two independent pieces, deliberately kept separate because they are calibrated
and validated differently:

  rate_ca_mg_release()  -- how fast base cations come out of the rock.
                           Palandri & Kharaka three-mechanism law.
                           Validated against Gudbrandsson et al. 2011 with NO
                           free parameters (see test_kinetics.py).

  eta_dic()             -- what fraction of that released alkalinity actually
                           carries carbon, from carbonate equilibria.
                           Zero free parameters. This is the term Cascade's
                           index omits.

  flux_ceiling_t_ha_yr()-- the most carbon the drainage water can physically
                           carry away, q * [HCO3-]_max * 44. A BOUND on the
                           output of the two above, not a third factor. It shares
                           the carbonate constants with eta_dic but answers a
                           different question: eta_dic asks what share of
                           released alkalinity carries carbon at a given pH,
                           this asks how much alkalinity the water can hold at
                           all, with pH free to rise.

The product of the first two is the reactivity index. They must stay separate because
the field-trial calibration target (Beerling's CDRpot) is a cation-loss upper
bound that already assumes eta_dic = 1; folding eta_dic in before fitting would
double-count it.

All functions are numpy-vectorised and safe on 2-D arrays with NaN.
"""

from __future__ import annotations

import numpy as np

import constants as C

__all__ = [
    "arrhenius_factor",
    "ssa_geometric",
    "ssa_log_shift",
    "dissolved_fraction",
    "retreat_at_reference",
    "dissolved_fraction_at",
    "d80_to_d50",
    "mineral_rate",
    "rate_ca_mg_release",
    "carbonate_constants",
    "k_calcite",
    "eta_dic",
    "ph_half",
    "eta_transport",
    "alkalinity_ceiling_mol_l",
    "flux_ceiling_t_ha_yr",
    "cascade_baseline_index",
    "element_release",
]


# ---------------------------------------------------------------------------
# Palandri & Kharaka three-mechanism rate law
# ---------------------------------------------------------------------------
def arrhenius_factor(ea_kj: float, T_K):
    """exp[-(Ea/R)(1/T - 1/T_ref)].

    This is the form PHREEQC's RATE_PK uses. The expression as *printed* in
    OFR 2004-1068 eqn 7 is `exp(-E/(R(T-298.15)))`, which is dimensionally
    incoherent and singular at the reference temperature; it is a typo in the
    report. See constants.PK_MINERALS docstring.
    """
    ea = ea_kj * 1000.0
    return np.exp(-(ea / C.R_GAS) * (1.0 / np.asarray(T_K, dtype=float) - 1.0 / C.T_REF))


def mineral_rate(mineral: str, pH, T_K):
    """Dissolution rate of one mineral, mol m-2 s-1, far from equilibrium.

    Sums the acid, neutral and base mechanisms that the source actually
    tabulates. Mechanisms recorded as "--" contribute nothing rather than being
    silently filled in.

    The affinity term (1 - Omega^p)^q is dropped, i.e. Omega -> 0. Palandri &
    Kharaka select far-from-equilibrium data for exactly this reason (p.6), so
    it is internally consistent -- but it is also optimistic in slow-draining
    and arid soils, which is what eta_transport() exists to temper.
    """
    try:
        spec = C.PK_MINERALS[mineral]
    except KeyError:
        raise KeyError(
            f"{mineral!r} is not in constants.PK_MINERALS. Note that basaltic "
            "glass is deliberately absent -- it is not in Palandri & Kharaka. "
            "Use the Gislason & Oelkers parameters instead."
        ) from None

    a_h = np.power(10.0, -np.asarray(pH, dtype=float))
    total = np.zeros(np.broadcast(a_h, np.asarray(T_K, dtype=float)).shape)

    for mech in ("acid", "neut", "base"):
        params = spec.get(mech)
        if params is None:
            continue
        log_k25, ea_kj, n = params
        total = total + (
            np.power(10.0, log_k25) * arrhenius_factor(ea_kj, T_K) * np.power(a_h, n)
        )
    return total


# Divalent Ca + Mg cations per formula unit. CDR is driven by Ca+Mg release,
# not Si release -- Gudbrandsson et al. 2011 show Si, Ca, Mg and Fe have
# different pH dependences from the same basalt, so there is no single
# whole-rock rate law that represents CDR.
#
# IRON IS DELIBERATELY EXCLUDED, and this is a real divergence from Bertagni &
# Porporato. Their Table 1 assigns Fe2SiO4 the same alkalinity yield as Mg2SiO4
# (n = 4), which is correct as pure aqueous chemistry: Fe2+ release does raise
# alkalinity. But in an oxic agricultural soil that alkalinity is transient --
#     Fe2+ + 1/4 O2 + 5/2 H2O -> Fe(OH)3 + 2 H+
# returns the protons as the iron oxidises and precipitates as ferrihydrite or
# goethite, so no durable carbon is stored. The crediting protocols agree:
# Isometric's feedstock characterisation module computes CO2 potential from CaO,
# MgO, Na2O and K2O only, with no FeO term.
#
# Consequence: fayalite scores 0 here (vs n = 4 in B&P Table 1), and augite is
# discounted to ~1.6 of a nominal 2 to reflect its Fe content. If a future
# version credits Fe, it must also model the oxidation sink, not just the
# release.
DIVALENT_PER_FORMULA = {
    "anorthite": 1.0,      # CaAl2Si2O8
    "bytownite": 0.8,      # ~An80
    "labradorite": 0.6,    # ~An60
    "andesine": 0.4,       # ~An40
    "oligoclase": 0.2,     # ~An20
    "albite": 0.0,         # NaAlSi3O8 -- releases Na, no CDR by this route
    "forsterite": 2.0,     # Mg2SiO4
    "fayalite": 0.0,       # Fe2SiO4 -- Fe, not an alkaline earth
    "diopside": 2.0,       # CaMgSi2O6
    "augite": 1.6,         # (Ca,Mg,Fe)2Si2O6, Fe-bearing
    "enstatite": 1.0,      # MgSiO3
    "bronzite": 0.8,       # ~Mg0.8Fe0.2SiO3; Fe carries no durable alkalinity
    "wollastonite": 1.0,   # CaSiO3
}


# Moles of each element released per mole of mineral dissolved. Separate from
# DIVALENT_PER_FORMULA because a validation against measured ELEMENT release needs
# element stoichiometry, not the CDR-relevant charge sum.
#
# Si AND Fe ARE CARRIED HERE FOR A SPECIFIC REASON, not for completeness. The
# Gudbrandsson fixture measures Si, Ca, Mg and Fe, and gate 11 used only Ca and
# Mg -- so Si and Fe were free out-of-sample data going unused. With three
# minerals there are only two free surface fractions, so requiring one partition
# to reproduce FOUR elements is OVER-IDENTIFIED: it is a test rather than a fit,
# and it is the only way to constrain the surface partition from outside the
# temperature dimension (where it is aliased with activation energy). See
# gate 11b in test_kinetics.py and docs/VALIDATION.md section 3.
#
# Fe is included as an ELEMENT here while being excluded from
# DIVALENT_PER_FORMULA. That is deliberate and not a contradiction: Fe release is
# measurable and constrains the mineralogy, but it carries no durable alkalinity
# in an oxic soil, so it earns no CDR credit.
ELEMENT_PER_FORMULA = {
    "anorthite":    {"Ca": 1.0, "Mg": 0.0, "Si": 2.0, "Fe": 0.0},  # CaAl2Si2O8
    "bytownite":    {"Ca": 0.8, "Mg": 0.0, "Si": 2.2, "Fe": 0.0},  # ~An80
    "labradorite":  {"Ca": 0.6, "Mg": 0.0, "Si": 2.4, "Fe": 0.0},  # ~An60, remainder Na
    "andesine":     {"Ca": 0.4, "Mg": 0.0, "Si": 2.6, "Fe": 0.0},  # ~An40
    "oligoclase":   {"Ca": 0.2, "Mg": 0.0, "Si": 2.8, "Fe": 0.0},  # ~An20
    "albite":       {"Ca": 0.0, "Mg": 0.0, "Si": 3.0, "Fe": 0.0},  # NaAlSi3O8
    "forsterite":   {"Ca": 0.0, "Mg": 2.0, "Si": 1.0, "Fe": 0.0},  # Mg2SiO4
    "fayalite":     {"Ca": 0.0, "Mg": 0.0, "Si": 1.0, "Fe": 2.0},  # Fe2SiO4
    "diopside":     {"Ca": 1.0, "Mg": 1.0, "Si": 2.0, "Fe": 0.0},  # CaMgSi2O6
    "augite":       {"Ca": 0.7, "Mg": 0.9, "Si": 2.0, "Fe": 0.4},  # Ca0.7Mg0.9Fe0.4Si2O6
    "enstatite":    {"Ca": 0.0, "Mg": 1.0, "Si": 1.0, "Fe": 0.0},  # MgSiO3
    "bronzite":     {"Ca": 0.0, "Mg": 0.8, "Si": 1.0, "Fe": 0.2},  # ~Mg0.8Fe0.2SiO3
    "wollastonite": {"Ca": 1.0, "Mg": 0.0, "Si": 1.0, "Fe": 0.0},  # CaSiO3
}

# Alkaline-earth elements only, i.e. the ones DIVALENT_PER_FORMULA counts. Si and
# Fe are in ELEMENT_PER_FORMULA for validation and must not enter the charge sum.
CDR_ELEMENTS = ("Ca", "Mg")


# The two tables above must agree: DIVALENT_PER_FORMULA is the CDR-relevant
# charge sum and ELEMENT_PER_FORMULA is the per-element stoichiometry the
# Gudbrandsson validation uses, so a divergence means the validated function is
# not the shipped one. Two disagreed until this was asserted: augite
# (1.60 vs 1.30, so the map credited 23% more divalent charge than the
# validation tested) and bronzite (1.00 vs 0.80). Both are now reconciled to
# their stated formulae. Note the direction of the augite fix -- it RAISES
# modelled Mg release, so it makes gate 11's Mg over-prediction slightly worse
# rather than better.
def _cdr_sum(m):
    """Ca + Mg only. Si and Fe live in ELEMENT_PER_FORMULA for validation and
    must never enter the charge sum -- Fe especially, since it carries no
    durable alkalinity in an oxic soil."""
    return sum(ELEMENT_PER_FORMULA[m].get(e, 0.0) for e in CDR_ELEMENTS)


_mismatch = {m: (d, _cdr_sum(m)) for m, d in DIVALENT_PER_FORMULA.items()
             if abs(d - _cdr_sum(m)) > 1e-9}
if _mismatch:
    raise AssertionError(
        "DIVALENT_PER_FORMULA and ELEMENT_PER_FORMULA disagree on "
        f"{_mismatch} -- the validated function would not be the shipped one")
del _mismatch


def element_release(fractions: dict, element: str, pH, T_K):
    """Release rate of one element, mol m-2 s-1, for a mineral mixture.

    `fractions` maps mineral name to its share of the REACTING SURFACE (not
    necessarily its volume share -- the distinction is the whole point of the
    Gudbrandsson validation, since their own fit needed plagioclase to occupy
    83% of the surface against a 44% volume share).
    """
    norm = sum(fractions.values()) or 1.0
    total = None
    for mineral, f in fractions.items():
        nu = ELEMENT_PER_FORMULA[mineral].get(element, 0.0)
        if nu == 0.0:
            continue
        c = (f / norm) * nu * mineral_rate(mineral, pH, T_K)
        total = c if total is None else total + c
    return total if total is not None else np.zeros_like(np.asarray(pH, dtype=float))


def rate_ca_mg_release(archetype: str, pH, T_K, *, return_parts: bool = False):
    """Charge-equivalent Ca+Mg release rate for a feedstock archetype.

    Returns mol charge m-2 s-1 per unit reactive surface area, summed over the
    archetype's constituent minerals weighted by volume fraction and by
    divalent cations per formula unit.

    This is an INTENSIVE quantity: per unit surface area, with no application
    rate and no specific surface area in it. Converting to t CO2/ha/yr requires
    SSA, which is the dominant uncertainty in the whole product (geometric vs
    BET differ by 130-670x at ERW grain sizes), so that conversion lives in the
    L3 chain and is presented as a calibrated illustration, never a prediction.
    """
    spec = C.FEEDSTOCK_ARCHETYPES[archetype]
    fracs = spec["minerals"]
    norm = sum(fracs.values())

    parts = {}
    total = None
    for mineral, frac in fracs.items():
        contrib = (
            (frac / norm)
            * DIVALENT_PER_FORMULA[mineral]
            * 2.0  # charge per divalent cation
            * mineral_rate(mineral, pH, T_K)
        )
        parts[mineral] = contrib
        total = contrib if total is None else total + contrib

    return (total, parts) if return_parts else total


# ---------------------------------------------------------------------------
# Carbonate system -> alkalinity-to-DIC conversion efficiency
# ---------------------------------------------------------------------------
def _pb82(coeffs, T_K):
    a, b, c, d, e = coeffs
    T = np.asarray(T_K, dtype=float)
    return np.power(10.0, a + b * T + c / T + d * np.log10(T) + e / (T * T))


def carbonate_constants(T_K):
    """(K1, K2, K_H, Kw) from Plummer & Busenberg 1982. Verified to reproduce
    the standard 25 C values to <=0.0005 log units (test_kinetics.py)."""
    return (
        _pb82(C.PB82_K1, T_K),
        _pb82(C.PB82_K2, T_K),
        _pb82(C.PB82_KH, T_K),
        _pb82(C.PB82_KW, T_K),
    )


def k_calcite(T_K):
    """Calcite solubility product, Plummer & Busenberg 1982, same functional
    form as the acid constants. -8.480 at 25 C against the accepted -8.48."""
    return _pb82(C.PB82_KCAL, T_K)


# ---------------------------------------------------------------------------
# Drainage-concentration ceiling
# ---------------------------------------------------------------------------
def alkalinity_ceiling_mol_l(pco2_uatm, T_K, omega=None, f_ca=None):
    """Maximum drainage [HCO3-] in mol/L, set by carbonate saturation.

    THIS IS NOT eta_dic READ BACKWARDS, and the difference is the whole point.
    eta_dic answers "at this cell's pH, what share of released alkalinity carries
    carbon?" -- pH exogenous. This answers "how much alkalinity can the water hold
    at all?" -- pH ENDOGENOUS, because adding base cations at fixed pCO2 raises
    alkalinity and pH together, and raising pH is what a silicate amendment is
    for. Treating the pre-treatment pH as a ceiling gives 0.42 mmol/L at the
    median cropland cell, which is the observed alkalinity of streams draining
    UNAMENDED volcanic rock -- a baseline, not a bound.

    Closed form. With A = [HCO3-] and pH free, fixed pCO2 gives

        [H+]   = K1 * K_H * pCO2 / A                (open system, A dominates DIC)
        [CO3--] = K2 * A / [H+] = K2 * A^2 / (K1 K_H pCO2)

    and charge balance on a basalt-derived solution, 2[Ca] + 2[Mg] = A, with
    f_ca the Ca share of that divalent charge, gives [Ca] = f_ca * A / 2. Then
    Omega = [Ca][CO3--]/Ksp yields

        A = ( 2 * Omega * K1 * K_H * pCO2 * Ksp / (f_ca * K2) ) ** (1/3)

    The cube root is why this is robust: being wrong about soil pCO2 by 5x moves
    the ceiling only 1.7x. Temperature is weaker and runs the OTHER WAY from the
    rate law -- 3.56 / 3.03 / 2.58 mmol/L at 5 / 15 / 25 C -- so on the
    water-limited limb warm cropland is slightly worse per unit drainage, not
    better. That is the single most consequential consequence of this term.

    Only Ca constrains calcite, so f_ca < 1 raises the ceiling; magnesite is
    kinetically inhibited at surface temperature and is not imposed at all.

    Validated in test_kinetics.py against the textbook open-system calcite
    benchmark (pure water + calcite at 400 uatm -> ~1 mmol/L alkalinity, pH ~8.3)
    and against five independent literature anchors. Activity coefficients are 1,
    as everywhere else in this module; at these ionic strengths that biases the
    ceiling LOW by ~10-20%, i.e. conservative toward the flux being critiqued.
    """
    if omega is None:
        omega = C.FLUX_CEILING_OMEGA
    if f_ca is None:
        f_ca = C.FLUX_CEILING_F_CA
    K1, K2, KH, _ = carbonate_constants(T_K)
    Ksp = k_calcite(T_K)
    p = np.asarray(pco2_uatm, dtype=float) * 1e-6
    f = max(float(f_ca), 1e-6)
    return np.cbrt(2.0 * float(omega) * K1 * KH * p * Ksp / (f * K2))


def flux_ceiling_t_ha_yr(q_m_yr, pco2_uatm, T_K, omega=None, f_ca=None):
    """Upper bound on gross CDR, tCO2/ha/yr, from what the drainage can carry.

    ceiling = q * [HCO3-]_max * 44.01, i.e. Maher & Chamberlain's W_max = q*c_eq
    limb, stated in their SI p.1: "The theoretical maximum solute flux is achieved
    when the water spends sufficient time in the subsurface to reach equilibrium
    among the primary and secondary minerals (Wmax = qceq)."

    The other M&C limb, W_max = C_eq*tau*D_w, is not imposed: with tau = e^2 it
    binds only above q = tau*D_w = 222 mm/yr (D_w = 0.03) or 2,217 (D_w = 0.3),
    at or above the p90 of cropland drainage either way, and where it does bind
    it gives a LOWER ceiling. So the q limb is the binding one across all cropland
    and imposing it alone is conservative toward the flux being critiqued.

    q in m/yr; 1 m/yr over 1 ha is 1e7 L/ha/yr.
    """
    q = np.clip(np.asarray(q_m_yr, dtype=float), 0.0, None)
    alk = alkalinity_ceiling_mol_l(pco2_uatm, T_K, omega=omega, f_ca=f_ca)
    return q * 1e7 * alk * C.M_CO2_G_MOL / 1e6


def eta_dic(pH, pco2_uatm, T_K):
    """Fraction of released base-cation charge that carries carbon as DIC.

    Open system at fixed soil pCO2 -- the correct idealisation for soil, where
    pCO2 is buffered by root and microbial respiration rather than by a finite
    DIC pool. With h = a_H+ and Cs = K_H * pCO2:

        DIC = Cs (1 + K1/h + K1 K2/h^2)
        Alk = Cs (K1/h + 2 K1 K2/h^2) + Kw/h - h

    Both depend only on h at fixed pCO2, so

        eta = (dDIC/dh) / (dAlk/dh)
            = Cs(K1 + 2 K1 K2/h) / [ Cs(K1 + 4 K1 K2/h) + Kw + h^2 ]

    Zero free parameters.

    This is the Alkalinization Carbon-capture Efficiency (ACE) of Bertagni &
    Porporato 2022, STE 838, 156524.

    VERIFIED against the paper (Appendix A, "Derivation of ACE"). Their
    definitions are identical to the above:
        [DIC] = K_H pCO2 (1 + K1/[H+] + K1 K2/[H+]^2)
        [Alk] = K1 K_H pCO2/[H+] + 2 K1 K2 K_H pCO2/[H+]^2
                + [BT] K_B/([H+]+K_B) + Kw/[H+] - [H+]
    and their eqn A.7 takes ACE as the ratio of the two partial derivatives with
    respect to [H+], which is exactly the construction used here.

    ONE DELIBERATE DIFFERENCE: they carry a borate term, we do not. That is
    correct for our domain and the paper says so -- "in freshwater the variation
    in alkalinity may be completely associated with the carbonate buffer (max of
    ACE ~ 1), in seawater the variation in alkalinity is partially associated
    with the borate buffer (max of ACE < 1)". Soil solution is the freshwater
    case. Our maximum is 0.999, matching their freshwater limit.

    Independent confirmation that the derivation is right rather than merely
    plausible: the paper states ACE "decays again to ~0.5 (at pH>pK2) as
    bicarbonates are substituted by carbonates". This implementation reproduces
    that asymptote without it being built in -- 0.600 at pK2, 0.503 at pH 12 --
    because it falls out of the K2 term. Tested in test_kinetics.py gate 2b.

    RETRACTION. An earlier version of this docstring said the paper "contains no
    kinetic index" and that Cascade's citation of it for a "normalized weathering
    flux potential framework" was therefore unjustified. That was WRONG, and it
    was written when the paper was paywalled and had not been read (recorded in
    PLAN.md at the time). The PDF is now in the repo root. Appendix C, Eq. C.1:

        r ~ s [H+]^theta exp(-E/RT)

    "where s is the time-averaged relative soil moisture. Temperature affects the
    dissolution rate through an Arrhenius equation, where A = 60 kJ/mol is the
    mean activation energy ... The activity of the hydrogen ion is approximated
    with its concentration (theta = 1). The results for Fig. 3b are then
    normalized by introducing the proportionality constant r0 so that
    min(r/r0) = 1."

    That is a normalised weathering-flux index: first order in H+, moisture
    scaled, Arrhenius, normalised, mapped globally as their Fig. 3b. Cascade's
    citation is essentially correct.

    What survives, and it is enough on its own: Cascade implements the kinetic
    index from Appendix C while omitting the efficiency term the paper's main
    text derives, which is the term implemented here. Note also that B&P's own
    Eq. C.1 uses theta = 1, the same first-order form we criticise, and that
    their Section 5.1 already reports the rate-versus-efficiency trade-off.
    """
    K1, K2, KH, Kw = carbonate_constants(T_K)
    h = np.power(10.0, -np.asarray(pH, dtype=float))
    Cs = KH * (np.asarray(pco2_uatm, dtype=float) * 1e-6)

    num = Cs * (K1 + 2.0 * K1 * K2 / h)
    den = Cs * (K1 + 4.0 * K1 * K2 / h) + Kw + h * h
    return num / den


def ph_half(pco2_uatm, T_K):
    """pH at which eta_dic = 1/2, i.e. -log10(sqrt(K_H * pCO2 * K1)).

    This lands within 0.12 pH units of Isometric's own 5.2 screening threshold
    at their mandated 4,000 uatm, and drops to ~4.53 at their mandated 50,000
    uatm for saturated systems -- which is why paddies tolerate more acidity.
    The protocols' screening criteria fall out of the chemistry rather than
    being imposed as an ad hoc penalty.
    """
    K1, _, KH, _ = carbonate_constants(T_K)
    return -np.log10(np.sqrt(KH * (np.asarray(pco2_uatm, dtype=float) * 1e-6) * K1))


# ---------------------------------------------------------------------------
# Reactive surface area from a particle-size distribution
# ---------------------------------------------------------------------------
def ssa_geometric(d50_um, rr_width, *, rho=None, d_min_um=None, d_max_um=None):
    """Mass-weighted geometric specific surface area, m2/g, for a Rosin-Rammler
    particle-size distribution characterised by d50 and width.

    d50, NOT d80. The ERW field reports p50, so the model should speak the same
    language as the data: measured p50 for real deliveries runs 67 um (finest) to
    600 um (coarsest). An earlier version keyed on d80 because the one trial we had
    reported p80, which made every comparison to a real delivery need a conversion.

    Rosin-Rammler cumulative mass finer than d:  F(d) = 1 - exp(-(d/d_c)^n)
    so d50 fixes the scale:                      d_c = d50 / (ln 2)^(1/n)

    For spheres, surface area per unit mass goes as 6/(rho*d), so
        SSA = (6/rho) * integral (1/d) dF(d)
    which we evaluate numerically over a truncated size range rather than with
    the closed form (6/(rho*d_c))*Gamma(1 - 1/n). The closed form DIVERGES for
    n <= 1, because an unbounded fine tail carries unbounded surface area, and
    real grinds do have widths near and below 1. Truncating at d_min is both
    numerically safe and physically honest: there is a finest particle.

    THIS IS GEOMETRIC AREA, NOT BET. The two differ by 130-670x at ERW grain
    sizes, and that gap is the single largest uncertainty in any absolute CDR
    number this project produces. It is carried explicitly as a fitted roughness
    multiplier lambda, whose plausible range is constants.LAMBDA_ROUGHNESS_RANGE,
    so that an unphysical demand is visible rather than hidden.

    Note also that d80 alone is not sufficient: at fixed d80, varying the width
    over a realistic range moves SSA by more than an order of magnitude. That is
    why width is a separate argument and a separate slider, not a hidden default.
    """
    rho = C.FEEDSTOCK_DENSITY_KG_M3 if rho is None else rho
    d_min_um = C.PSD_D_MIN_UM if d_min_um is None else d_min_um
    d_max_um = C.PSD_D_MAX_UM if d_max_um is None else d_max_um

    d50 = np.asarray(d50_um, dtype=float)
    n = np.asarray(rr_width, dtype=float)
    d_c = d50 / np.power(np.log(2.0), 1.0 / n)

    # Log-spaced size bins; mass in each bin from the RR cumulative.
    edges = np.logspace(np.log10(d_min_um), np.log10(d_max_um), 400)
    def one(d_c_i, n_i):
        Fe = 1.0 - np.exp(-np.power(edges / d_c_i, n_i))
        dm = np.diff(Fe)                        # mass fraction in each bin
        dm = np.clip(dm, 0.0, None)
        tot = dm.sum()
        if tot <= 0:
            return 0.0
        dm = dm / tot                           # renormalise over the truncation
        dmid = np.sqrt(edges[:-1] * edges[1:])  # geometric-mean bin diameter, um
        # 6/(rho*d): rho in kg/m3, d in um -> m2/g needs 6/(rho[kg/m3] * d[m])
        # m2/kg = 6/(rho*d_m); /1000 for m2/g
        return float(np.sum(dm * 6.0 / (rho * dmid * 1e-6)) / 1000.0)

    if np.ndim(d_c) == 0:
        return one(float(d_c), float(n))
    return np.array([one(float(a), float(b))
                     for a, b in np.broadcast(d_c, n)]).reshape(np.shape(d_c))


def d80_to_d50(d80_um, rr_width):
    """Convert a reported d80 to d50 for a given Rosin-Rammler width.

    d80/d50 = (ln5/ln2)^(1/n), so the conversion is WIDTH-DEPENDENT: 1.76x at
    n=1.5 but 3.35x at n=0.7. Any p80 taken from the literature therefore carries
    the width assumption with it, which is a reason to prefer sources that report
    p50 directly.
    """
    return np.asarray(d80_um, dtype=float) / np.power(
        np.log(5.0) / np.log(2.0), 1.0 / np.asarray(rr_width, dtype=float))


def ssa_log_shift(d50_um, rr_width):
    """log10(SSA(d50, width) / SSA(reference)).

    The rate is linear in reactive surface area, and L1 is a log10 ratio, so a
    change of grind is a UNIFORM ADDITIVE SHIFT on L1. That is what makes a
    particle-size slider cheap: one uniform in the shader rather than a rebuild.
    """
    ref = ssa_geometric(C.PSD_REF_D50_UM, C.PSD_REF_WIDTH)
    return float(np.log10(ssa_geometric(d50_um, rr_width) / ref))


# ---------------------------------------------------------------------------
# Dissolution over a particle-size distribution (shrinking core)
# ---------------------------------------------------------------------------
def dissolved_fraction(u, rr_width, nbin=6000):
    """Mass fraction of a Rosin-Rammler feedstock dissolved, shrinking-core.

    REPLACES frac = 1 - exp(-k*X), which was a single first-order decay on the
    BULK mass. That form let the last 10% of mass dissolve as easily as the first
    10%, when physically the last 10% is the coarse tail with the least surface
    area per unit mass -- so it over-predicted the high end and could reach 100%
    in a year, which no real grind can do.

    Shrinking core instead: every particle's surface retreats at the same linear
    rate, because the reaction rate is per unit area and does not know how big the
    particle is. After a radial retreat `delta`, a particle of initial diameter d
    has diameter max(d - 2*delta, 0). The fine tail vanishes early and the coarse
    tail persists, which is the whole point.

        u = delta / d50          (dimensionless retreat)
        Fw(u, n) = 1 - integral f(x) * max(1 - 2u/x, 0)^3 dx,   x = d / d50

    Fw depends ONLY on u and the width n, because the distribution scales with
    d50. That 2-D form is what lets the browser interpolate a small table rather
    than integrate. The integral is taken untruncated; truncating at the 1-5000 um
    range ssa_geometric uses changes Fw by <=0.001 for n >= 1.5 and by up to 0.03
    at n = 0.7, where real mass sits outside that window. Documented, not hidden.

    GRIND NOW ENTERS ONCE, HERE, and no longer multiplies the rate. Under shrinking
    core the linear retreat rate is independent of particle size; finer feedstock
    weathers a larger FRACTION purely because it has less mass per unit surface,
    which this integral already captures. Keeping the old specific-surface-area
    multiplier on the rate as well would count grind twice.
    """
    u = np.atleast_1d(np.asarray(u, dtype=float))
    n = float(rr_width)
    cn = 1.0 / (np.log(2.0) ** (1.0 / n))            # d_c / d50
    edges = np.geomspace(1e-4, 60.0, nbin + 1)
    wm = np.diff(1.0 - np.exp(-((edges / cn) ** n)))
    x = np.sqrt(edges[:-1] * edges[1:])
    wm = wm / wm.sum()
    rem = np.clip(1.0 - 2.0 * u[:, None] / x[None, :], 0.0, None) ** 3
    return 1.0 - (rem * wm[None, :]).sum(axis=1)


def retreat_at_reference(target=None, d50_um=None, rr_width=None):
    """Radial retreat, in micrometres, that dissolves `target` of the reference
    grind in one year at the reference condition. This is the single anchored
    quantity in the dissolution model -- see constants.DISSOLVED_FRAC_AT_REF."""
    if target is None:
        target = C.DISSOLVED_FRAC_AT_REF
    if d50_um is None:
        d50_um = C.PSD_REF_D50_UM
    if rr_width is None:
        rr_width = C.PSD_REF_WIDTH
    lo, hi = 0.0, 10.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if float(dissolved_fraction(mid, rr_width)[0]) < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi) * d50_um


def dissolved_fraction_at(X, d50_um, rr_width, delta_ref_um=None):
    """Fraction weathered for a cell of dimensionless rate X at a given grind.

    X is the kinetic-and-transport rate relative to the reference condition, WITH
    NO surface-area term (see dissolved_fraction). The retreat scales linearly
    with it, and the grind enters as d50.
    """
    if delta_ref_um is None:
        delta_ref_um = retreat_at_reference()
    u = delta_ref_um * np.asarray(X, dtype=float) / float(d50_um)
    out = dissolved_fraction(u.ravel(), rr_width)
    return out.reshape(np.shape(X)) if np.shape(X) else float(out[0])


# ---------------------------------------------------------------------------
# Transport limitation
# ---------------------------------------------------------------------------
def eta_transport(q_m_yr, D_w=None):
    """q / (q + D_w), after Maher & Chamberlain 2014 (Science 343, 1502).

    Recasts their [HCO3-] = [HCO3-]_eq / (1 + q/D_w) as a multiplier on a
    kinetic rate, where the kinetic limit is q -> infinity. In arid cells q -> 0
    and the penalty is severe; in the humid tropics eta -> 1 and Cascade's
    far-from-equilibrium assumption is recovered.

    The functional form is well grounded. D_w IS constrained by the literature,
    just not for basalt: Maher & Chamberlain fit 0.001-0.3 m/yr from rivers
    "mostly draining granitic lithologies", with 0.3 stated as the global
    maximum and 0.03 as the collisional/craton divide. We default to 0.03 and
    carry the published range in constants.DAMKOHLER_DW_RANGE. An earlier
    version of this docstring said D_w was unconstrained, which was stale.

    THE CEILING IS NO LONGER MISSING, AND IT LIVES ELSEWHERE. Recasting their
    Eq. 3 as a multiplier on a kinetic rate keeps the shape of the curve and drops
    the finite concentration limit C_eq, which is why the CDR layer once needed a
    hard clip and then a saturating exponential. That bound is now imposed
    explicitly by flux_ceiling_t_ha_yr() and enforced by gate 12 in build_v0.py.
    It is NOT imposed here, and the separation is deliberate: see below.

    THE TAU QUESTION IS RESOLVED, AND DELIBERATELY NOT APPLIED HERE. Their Eq. 3
    as printed is C = C_eq * (tau*D_w/q) / (1 + tau*D_w/q) with tau = e^2, so the
    dimensionless factor on the FLUX is q/(q + tau*D_w). tau is NOT already folded
    into the Fig. 2 contour labels -- those reproduce to two significant figures
    from the paper's own printed parameters using bare D_w = L_phi/T_eq, while
    Fig. 2B's plotted plateaus match C_eq*tau*D_w and are 0.8 of a decade off
    without tau. So applying tau on top of a Fig-2-derived D_w would be correct
    arithmetic and the wrong thing to do HERE, because in M&C that factor
    multiplies the kinetic-limit FLUX tau*L_phi*R_n, which carries C_eq with it,
    whereas this eta multiplies a dimensionless relative reactivity, which does
    not. Swapping tau in on its own drops the median 21.9x and undershoots the
    physical ceiling by ~5x, double-penalising a rate that is ALREADY anchored to
    field data. See constants.DAMKOHLER_TAU_APPLIED_IN_ETA.

    WHICH LIMB, still open but now second-order. Their Eq. 1 makes D_w
    proportional to reactive surface area and inversely proportional to soil age,
    so annually reapplied crushed feedstock in a tilled topsoil belongs at the 0.3
    end (T_s ~ 1 yr, f_w ~ 1) rather than the 0.03 end, which the Fig. 2 caption
    ties to "L_phi of 0.1 m and T_s of 100,000 years". We keep 0.03 because the
    level is set by the explicit ceiling now rather than by this term, and because
    moving D_w here without restructuring is exactly the double-penalty above.
    What it still changes is the SHAPE of the wet-dry contrast, so it remains a
    live sensitivity case rather than a settled default.

    AND THE REGIME MATTERS MORE THAN EITHER. tau*D_w is 0.222 m/yr at D_w = 0.03
    and 2.217 at 0.3, both at or above the p90 of cropland drainage (229 mm/yr).
    So all cropland sits on the low-q limb where C -> C_eq and the flux is C_eq*q,
    and Maher 2010 p.104 states the consequence directly: beyond L_eq the flux
    c_eq*q "conveys no information on the actual weathering kinetics or available
    surface area." Empirically the same: Godsey et al. 2009 measure
    concentration-discharge slopes of -0.05 to -0.15 across 59 catchments, i.e.
    near-chemostatic, so flux scales essentially linearly with q. Treat any result
    that leans on the rate law's spatial pattern accordingly.

    q must include irrigation return flow on irrigated cells, not just
    precipitation surplus, or the Indo-Gangetic Plain is wrongly penalised.
    """
    if D_w is None:
        D_w = C.DAMKOHLER_DW_M_YR
    q = np.asarray(q_m_yr, dtype=float)
    return q / (q + D_w)


# ---------------------------------------------------------------------------
# Cascade baseline, for like-for-like comparison
# ---------------------------------------------------------------------------
def cascade_baseline_index(pH, T_K, moisture, ea_kj: float = 68.8):
    """Cascade Climate's published form: r ~ s * [H+] * exp(-Ea/RT).

    Reproduced so our critique is testable rather than asserted. Not our
    default, for two reasons documented in docs/METHODOLOGY.md:

      1. First order in [H+] spans 1e4 across cropland pH 4-8, while the
         Arrhenius term spans only ~20x across 0-30 C, so the index is ~500x
         more sensitive to pH than to temperature -- effectively a rescaled
         soil-pH map. The three-mechanism law compresses that to ~37x.
      2. It omits eta_dic, so it rewards strongly acidic soils that both the
         Isometric and Puro.earth protocols penalise.

    ON THE 68.8 kJ/mol, TWICE RETRACTED. An earlier version of this docstring
    said 68.8 was "a reasonable number for whole-basalt CDR" because our own
    mixture came out at 65.6-67.9. That defence is withdrawn: it only showed the
    two formulations agree with EACH OTHER, and Gudbrandsson et al. (2011)
    measure ~36 kJ/mol for whole-rock crystalline basalt (24-54 across pH),
    while Schaef & McGrail (2009) measure 30.3 +/- 2.4 on Columbia River basalt
    from an independent laboratory. Our shipped mixture is 61.9-69.3 over
    5-25 C, so BOTH formulations over-weight temperature by roughly 2x, and
    Cascade's 68.8 is wrong for a reason we share rather than for one that
    distinguishes us.

    Its stated provenance (White & Blum 1995, "representative of basaltic
    glass") remains unclear -- that paper reports 59.4 and 62.5 kJ/mol for
    granitoid catchments -- and the primary laboratory value for basaltic glass
    is 25.5 kJ/mol, i.e. lower still.
    """
    a_h = np.power(10.0, -np.asarray(pH, dtype=float))
    return np.asarray(moisture, dtype=float) * a_h * arrhenius_factor(ea_kj, T_K)
