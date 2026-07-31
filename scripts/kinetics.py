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

The product of the two is the reactivity index. They must stay separate because
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
    "d80_to_d50",
    "mineral_rate",
    "rate_ca_mg_release",
    "carbonate_constants",
    "eta_dic",
    "ph_half",
    "eta_transport",
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
    "bronzite": 1.0,       # ~(Mg,Fe)SiO3
    "wollastonite": 1.0,   # CaSiO3
}


# Moles of each element released per mole of mineral dissolved. Separate from
# DIVALENT_PER_FORMULA because a validation against measured ELEMENT release needs
# element stoichiometry, not the CDR-relevant charge sum.
ELEMENT_PER_FORMULA = {
    "anorthite":    {"Ca": 1.0, "Mg": 0.0},   # CaAl2Si2O8
    "bytownite":    {"Ca": 0.8, "Mg": 0.0},
    "labradorite":  {"Ca": 0.6, "Mg": 0.0},   # ~An60, remainder Na
    "andesine":     {"Ca": 0.4, "Mg": 0.0},
    "oligoclase":   {"Ca": 0.2, "Mg": 0.0},
    "albite":       {"Ca": 0.0, "Mg": 0.0},
    "forsterite":   {"Ca": 0.0, "Mg": 2.0},   # Mg2SiO4
    "fayalite":     {"Ca": 0.0, "Mg": 0.0},
    "diopside":     {"Ca": 1.0, "Mg": 1.0},   # CaMgSi2O6
    "augite":       {"Ca": 0.7, "Mg": 0.6},   # (Ca,Mg,Fe)2Si2O6, Fe-bearing
    "enstatite":    {"Ca": 0.0, "Mg": 1.0},   # MgSiO3
    "bronzite":     {"Ca": 0.0, "Mg": 0.8},
    "wollastonite": {"Ca": 1.0, "Mg": 0.0},   # CaSiO3
}


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

    Worth flagging: Cascade cites this paper as the source of a "normalized
    weathering flux potential framework" while implementing only kinetics. The
    paper's actual title is "The Carbon-Capture Efficiency of Natural Water
    Alkalinization", and it contains no kinetic index -- it is precisely the
    efficiency term their formulation omits.
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
# Transport limitation
# ---------------------------------------------------------------------------
def eta_transport(q_m_yr, D_w=None):
    """q / (q + D_w), after Maher & Chamberlain 2014 (Science 343, 1502).

    Recasts their [HCO3-] = [HCO3-]_eq / (1 + q/D_w) as a multiplier on a
    kinetic rate, where the kinetic limit is q -> infinity. In arid cells q -> 0
    and the penalty is severe; in the humid tropics eta -> 1 and Cascade's
    far-from-equilibrium assumption is recovered.

    The functional form is well grounded. D_w is NOT constrained by the
    literature -- treat it as a sensitivity parameter over
    constants.DAMKOHLER_DW_RANGE and do not present a single value as known.

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

    In fairness: the effective Ea of a basalt mixture for Ca+Mg release works
    out to 65.6-67.9 kJ/mol, so 68.8 is a reasonable number for whole-basalt
    CDR. Its stated provenance (White & Blum 1995, "representative of basaltic
    glass") is unclear -- that paper reports 59.4 and 62.5 kJ/mol for granitoid
    catchments -- and the primary laboratory value for basaltic glass is
    25.5 kJ/mol.
    """
    a_h = np.power(10.0, -np.asarray(pH, dtype=float))
    return np.asarray(moisture, dtype=float) * a_h * arrhenius_factor(ea_kj, T_K)
