"""
Gates for the kinetics core. Run before building anything downstream.

  python3 scripts/test_kinetics.py

These are pre-registered checks, not exploratory ones. The point is that they
can fail and thereby falsify part of the approach. Failures are reported, not
smoothed over.

Gate 1  Plummer & Busenberg 1982 reproduces the standard 25 C constants.
Gate 2  eta_dic derives the protocols' own pH screening thresholds.
Gate 3  The three-mechanism law compresses pH leverage vs Cascade's n=1 form.
Gate 4  Constants match the primary PDF, re-extracted rather than trusted.
Gate 5  Monotonicity: rate rises with T, eta_dic rises with pH and pCO2.
Gate 6  Per-mineral CO2 capacity matches published values.
Gate 7  delivered_basalt reproduces the measured deliveries.
Gate 8  The generated browser constants reproduce Python (anti-drift).
Gate 9  Specific surface area scales sensibly with grind.
Gate 10 Zero CDR gives zero suitability, and dissolution saturates smoothly.

Gate 11 Gudbrandsson et al. 2011: reproduce MEASURED Ca and Mg release from
        crystalline basalt across pH 2-11 and 5-75 C with no fitted parameters.
        The only genuinely independent test of the rate law -- the field trials
        cannot isolate it because grain size and loss terms absorb the error.
        Scored on the SHIPPED basis (volume fractions, Ca+Mg charge sum).
Gate 11b Can any single surface partition reproduce all FOUR measured elements?
        Two free parameters against Si, Ca, Mg and Fe, so it is over-identified
        and is a test rather than a fit. Answer: no. Reported, not hidden.
Gate 13 The drainage-concentration ceiling reproduces the textbook open-system
        calcite benchmark (pure water + calcite at 400 uatm -> ~1 mmol/L
        alkalinity, pH ~8.3), which tests the algebra, the calcite constant and
        the charge-balance coupling in one shot.
Gate 13b That ceiling lands inside five independent measured anchors on drained
        cropland, and FALLS with warming -- the property that makes it remove the
        map's warm-climate gradient rather than merely rescale the level.
Gate 13c REPORTED, not scored: on saturated (paddy) cells the mandated 50,000
        uatm lifts the ceiling above every anchor, and no measured paddy drainage
        DIC exists to check it against. Standing justification for field-data
        ask #6.
Gate 13d The ceiling's Mg-explicit Davies solve reproduces all 54 independent
        PHREEQC (wateq4f) cases of Mayer et al. 2025 Table S.1 within
        [0.93, 1.02], with the expected small low bias from neglected ion
        pairs, and matches their Fig. 4 temperature slope.

Two gates fail, both informatively: 11 (the rate law over-predicts) and 6c (the
archetypes' mineral modes do not mass-balance their stated oxides). Note that a
count of passes is not a count of validation evidence -- see the summary the
script prints, and docs/VALIDATION.md section 1.
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

import constants as C  # noqa: E402
import kinetics as K  # noqa: E402

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def record(gate: str, ok: bool | None, detail: str) -> None:
    status = SKIP if ok is None else (PASS if ok else FAIL)
    results.append((gate, status, detail))


# ---------------------------------------------------------------------------
def gate1_carbonate_constants() -> None:
    """Plummer & Busenberg at 25 C vs accepted literature values."""
    K1, K2, KH, Kw = K.carbonate_constants(298.15)
    expect = {"log K1": (math.log10(K1), -6.352), "log K2": (math.log10(K2), -10.329),
              "log KH": (math.log10(KH), -1.468), "log Kw": (math.log10(Kw), -14.000)}
    worst, worst_name = 0.0, ""
    for name, (got, lit) in expect.items():
        d = abs(got - lit)
        if d > worst:
            worst, worst_name = d, name
    ok = worst <= 5e-4
    record("1. Plummer-Busenberg 25 C constants", ok,
           f"max deviation {worst:.5f} log units ({worst_name}); tolerance 0.0005")


def gate2_protocol_thresholds() -> None:
    """eta_dic's half-efficiency point should land on the protocols' own
    screening thresholds without being told about them."""
    T = 288.15  # 15 C
    unsat = float(K.ph_half(C.PCO2_UNSATURATED_UATM, T))
    sat = float(K.ph_half(C.PCO2_SATURATED_UATM, T))

    # Isometric screens at pH 5.2 for unsaturated cropping systems.
    gap = abs(unsat - C.PH_WARNING_THRESHOLD)
    ok = gap < 0.25 and sat < unsat
    record("2. eta_dic derives protocol pH thresholds", ok,
           f"pH_half(4,000 uatm)={unsat:.2f} vs Isometric 5.20 (gap {gap:.2f}); "
           f"pH_half(50,000 uatm)={sat:.2f}, so paddies tolerate "
           f"{unsat - sat:.2f} more pH units of acidity")


def gate2b_ace_high_ph_asymptote() -> None:
    """Bertagni & Porporato state ACE "decays again to ~0.5 (at pH>pK2) as
    bicarbonates are substituted by carbonates".

    This is the sharpest available check that our closed form is genuinely their
    ACE and not merely something plausible: the 0.5 asymptote is not built in,
    it emerges from the K2 term. If this fails, the derivation is wrong.
    """
    T = 298.15
    K1, K2, _, _ = K.carbonate_constants(T)
    pk2 = -math.log10(float(K2))

    at_pk2 = float(K.eta_dic(pk2, C.PCO2_ATMOSPHERIC_UATM, T))
    far = float(K.eta_dic(13.0, C.PCO2_ATMOSPHERIC_UATM, T))
    peak = float(np.max(K.eta_dic(np.arange(6.5, 8.5, 0.05),
                                  C.PCO2_ATMOSPHERIC_UATM, T)))

    # Asymptote to 0.5, a plateau near 1 below it, and ~0.6 at pK2 itself.
    ok = (abs(far - C.ACE_HIGH_PH_ASYMPTOTE) < 0.01
          and peak > 0.99
          and 0.55 < at_pk2 < 0.65)
    record("2b. ACE high-pH asymptote (B&P Appendix A)", ok,
           f"plateau max {peak:.3f} (their freshwater limit ~1); "
           f"ACE(pK2={pk2:.2f})={at_pk2:.3f}; ACE(pH 13)={far:.4f} "
           f"vs their stated ~{C.ACE_HIGH_PH_ASYMPTOTE}")


def gate2c_charge_vs_bertagni_table1() -> None:
    """Cross-check charge accounting against B&P Table 1 'n'. Independent of the
    Puro.earth check in gate 6: different source, different units, same physics."""
    import kinetics as _K

    pairs = {"CaSiO3": "wollastonite", "Mg2SiO4": "forsterite",
             "Fe2SiO4": "fayalite"}
    lines, bad = [], []
    for formula, mineral in pairs.items():
        theirs = C.BP22_ALKALINITY_PER_MOLE[formula]
        ours = _K.DIVALENT_PER_FORMULA[mineral] * 2.0
        agree = abs(ours - theirs) < 1e-9
        # Fayalite is an intentional divergence, documented in kinetics.py.
        expected_divergence = mineral == "fayalite"
        if not agree and not expected_divergence:
            bad.append(mineral)
        note = "" if agree else (" (intentional: Fe excluded)"
                                if expected_divergence else " MISMATCH")
        lines.append(f"{formula} ours {ours:.0f} vs B&P {theirs}{note}")

    record("2c. Charge per mole vs B&P Table 1", not bad,
           "; ".join(lines) + (f"; unexpected: {bad}" if bad else ""))


def gate2d_eta_dic_reproduces_dietzen_rosing_xstar() -> None:
    """eta_DIC must reproduce Dietzen & Rosing's X*, derived a different way.

    This is the strongest external check in the project, and it was found late.

    They define X* from a soil PROTON BUDGET -- "the proportion of the weathering
    reactions that converted carbonic acid to bicarbonate rather than consuming
    excess acidity" -- and tabulate it against pH and pCO2. We compute eta_DIC
    from CARBONATE EQUILIBRIUM following Bertagni & Porporato, with no knowledge
    of their formulation. Two independent derivations from different literatures
    landing on the same function of (pH, pCO2) is much stronger evidence than
    either alone, and it spans a 40x range in pCO2.

    It also settles a question that was blocking work: their thresholds are on
    pH(H2O), stated explicitly, and both protocols' pH numbers trace to this
    paper -- so no measurement-convention offset applies anywhere here.

    AND it reframes the strong-acid problem. X* IS the protocol-sanctioned
    strong-acid correction, so this model already contains it; what is open is
    whether an equilibrium form of it survives continuous fertiliser loading.
    """
    lines, worst = [], 0.0
    for ph, pco2, theirs in C.DIETZEN_ROSING_XSTAR:
        ours = float(K.eta_dic(ph, pco2, C.T_REF))
        worst = max(worst, abs(ours - theirs))
        lines.append(f"pH {ph:.2f}/{pco2:.0f}uatm ours {ours:.3f} vs X* {theirs:.2f}")
    ok = worst <= C.DIETZEN_ROSING_XSTAR_TOL
    record("2d. eta_DIC reproduces Dietzen & Rosing X* (independent derivation)",
           ok, f"max deviation {worst:.3f}, tolerance "
               f"{C.DIETZEN_ROSING_XSTAR_TOL}; " + "; ".join(lines))


def gate3_ph_leverage() -> None:
    """The three-mechanism law must compress pH leverage relative to Cascade's
    first-order form. If it does not, the central critique is wrong."""
    T = 288.15
    ph = np.array([4.0, 8.0])

    ours = K.rate_ca_mg_release("fresh_basalt", ph, T)
    ours_ratio = float(ours[0] / ours[1])

    casc = K.cascade_baseline_index(ph, T, 1.0)
    casc_ratio = float(casc[0] / casc[1])

    # Arrhenius span over 0-30 C at Cascade's Ea, for context.
    t_span = float(K.arrhenius_factor(68.8, 303.15) / K.arrhenius_factor(68.8, 273.15))

    ok = ours_ratio < casc_ratio / 20.0
    record("3. pH leverage compressed vs Cascade n=1", ok,
           f"pH 4->8 rate ratio: ours {ours_ratio:.0f}x, Cascade {casc_ratio:.0f}x "
           f"(overstated {casc_ratio / ours_ratio:.0f}x); "
           f"temperature 0-30 C spans {t_span:.0f}x")


def gate4_constants_match_source() -> None:
    """Re-extract the kinetic constants from the primary PDF rather than
    trusting the transcription. Fabricated rate parameters would be the worst
    error to carry into this build."""
    root = Path(__file__).resolve().parent.parent
    candidates = [root / "tests/fixtures/pk2004_tables.txt",
                  root / "data/raw/pk2004.txt"]
    src = next((p for p in candidates if p.exists()), None)
    if src is None:
        record("4. Constants match primary PDF", None,
               "tests/fixtures/pk2004_tables.txt missing. Regenerate with "
               "scripts/fetch_pk_tables.sh, then re-run.")
        return

    text = src.read_text(errors="replace")
    checked, mismatches = 0, []
    for mineral, spec in C.PK_MINERALS.items():
        acid = spec.get("acid")
        if acid is None:
            continue
        log_k, ea, n = acid
        # Find the mineral's table row and confirm the three acid-mechanism
        # numbers appear on it in order.
        pat = re.compile(
            rf"^\s*{mineral}\s+{re.escape(f'{log_k:.2f}')}\s+{re.escape(f'{ea:.1f}')}"
            rf"\s+{re.escape(f'{n:.3f}')}",
            re.IGNORECASE | re.MULTILINE,
        )
        checked += 1
        if not pat.search(text):
            mismatches.append(mineral)

    ok = not mismatches
    record("4. Constants match primary PDF", ok,
           f"{checked - len(mismatches)}/{checked} acid-mechanism rows matched "
           f"{C.PK_SOURCE}"
           + (f"; MISMATCHED: {', '.join(mismatches)}" if mismatches else ""))

    # The negative claim matters too: basaltic glass is not in this report.
    body = text.lower()
    tbl_hits = [
        ln for ln in body.splitlines()
        if ("glass" in ln or "basalt" in ln) and re.search(r"-\d+\.\d+\s+\d+\.\d+", ln)
    ]
    record("4b. Basaltic glass absent from PK tables", not tbl_hits,
           "confirmed: 'glass'/'basalt' appear only in prose and references, "
           "never in a parameter row"
           if not tbl_hits else f"unexpected table-like hits: {tbl_hits[:2]}")


def gate5_monotonicity() -> None:
    """Cheap invariants that catch real bugs."""
    T = np.array([273.15, 283.15, 293.15, 303.15])
    r = K.rate_ca_mg_release("fresh_basalt", 6.5, T)
    t_mono = bool(np.all(np.diff(r) > 0))

    ph = np.array([4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0])
    e = K.eta_dic(ph, C.PCO2_UNSATURATED_UATM, 288.15)
    ph_mono = bool(np.all(np.diff(e) > 0))

    pco2 = np.array([400.0, 4_000.0, 20_000.0, 50_000.0])
    e2 = K.eta_dic(5.0, pco2, 288.15)
    pco2_mono = bool(np.all(np.diff(e2) > 0))

    # Rate must fall with rising pH over the acid-dominated range.
    r2 = K.rate_ca_mg_release("fresh_basalt", np.array([4.0, 5.0, 6.0, 7.0]), 288.15)
    ph_rate_mono = bool(np.all(np.diff(r2) < 0))

    ok = t_mono and ph_mono and pco2_mono and ph_rate_mono
    record("5. Monotonicity invariants", ok,
           f"rate rises with T: {t_mono}; rate falls with pH: {ph_rate_mono}; "
           f"eta_dic rises with pH: {ph_mono}; eta_dic rises with pCO2: {pco2_mono}")


def gate6_cdrmax_vs_published() -> None:
    """Validate the stoichiometry engine against PUBLISHED per-mineral CO2
    capacities before trusting any composition-derived ceiling.

    This is the external check: reproduce a known published number and report
    the agreement, rather than testing our arithmetic against our own guess.
    """
    rows, worst, worst_name = [], 0.0, ""
    for mineral, (mw, n_di, n_mono, published) in C.CDRMAX_REFERENCE.items():
        charge_kmol = (1e6 / mw) * (2 * n_di + 1 * n_mono) / 1000.0
        ours = charge_kmol * C.MOL_CO2_PER_KMOL_CHARGE_T
        rel = abs(ours - published) / published
        if rel > worst:
            worst, worst_name = rel, mineral
        rows.append(f"{mineral} {ours:.3f} vs {published:.3f} ({rel:+.1%})")

    ok = worst <= C.CDRMAX_REL_TOL
    record("6. CDRmax vs published per-mineral values", ok,
           f"max deviation {worst:.1%} ({worst_name}), tolerance "
           f"{C.CDRMAX_REL_TOL:.0%}, vs {C.CDRMAX_SOURCE}")
    gate6_cdrmax_vs_published.rows = rows


def gate6b_archetype_ceilings() -> None:
    """Per-archetype stoichiometric ceilings, computed from oxide composition.
    Any grid cell implying more CO2 per tonne than its archetype's ceiling is a
    bug. The only absolute bound is pure forsterite."""
    lines, worst = [], 0.0
    for name, spec in C.FEEDSTOCK_ARCHETYPES.items():
        kmol = (spec["CaO_wt"] / C.M_CAO + spec["MgO_wt"] / C.M_MGO) * 1000.0
        tco2_per_t = kmol * 2.0 * C.MOL_CO2_PER_KMOL_CHARGE_T
        worst = max(worst, tco2_per_t)
        lines.append(f"{name} {tco2_per_t:.3f}")
    ok = worst <= C.GATES["max_tco2_per_t_any_feedstock"]
    record("6b. Archetype ceilings below pure forsterite", ok,
           "t CO2/t: " + ", ".join(lines)
           + f"; absolute bound {C.GATES['max_tco2_per_t_any_feedstock']}")


def gate6c_mineralogy_mass_balance() -> None:
    """Each archetype's MINERAL LIST must mass-balance its stated OXIDES.

    Nothing checked this before, and it is the one internal consistency test
    that can catch a mis-specified archetype with no external data at all. The
    two halves of a spec are used by different parts of the model -- the mineral
    list drives rate_ca_mg_release (hence the whole map's pH and temperature
    response) while the oxides set the stoichiometric CO2 ceiling -- so if they
    disagree the model is describing two different rocks.

    EXPECTED TO FAIL as of this commit, and the failure is informative: it is an
    independent line of evidence that olivine is over-weighted in the mineral
    lists, agreeing in direction with gate 11's Mg over-prediction by a
    completely different route. Recorded rather than papered over; fixing it
    means re-deriving the mineral modes (e.g. from a CIPW norm on the measured
    oxides), which is a modelling decision needing its own review.

    Mineral formula masses and densities are local to this gate because they are
    only needed here; volume fractions are converted to mass fractions before
    the oxides are summed.
    """
    # (formula mass g/mol, density g/cm3, CaO per formula, MgO per formula)
    MIN = {
        "labradorite":  (270.8, 2.70, 0.6, 0.0),   # ~An60
        "albite":       (262.2, 2.62, 0.0, 0.0),
        "anorthite":    (278.2, 2.73, 1.0, 0.0),
        "augite":       (231.6, 3.35, 0.7, 0.9),   # Ca0.7Mg0.9Fe0.4Si2O6
        "diopside":     (216.6, 3.28, 1.0, 1.0),
        "forsterite":   (140.7, 3.27, 0.0, 2.0),
        "enstatite":    (100.4, 3.20, 0.0, 1.0),
    }
    lines, worst = [], 0.0
    for name, spec in C.FEEDSTOCK_ARCHETYPES.items():
        fr = spec["minerals"]
        if any(m not in MIN for m in fr):
            continue
        # volume -> mass, renormalised over the named phases exactly as
        # rate_ca_mg_release renormalises them.
        mass = {m: v * MIN[m][1] for m, v in fr.items()}
        tot = sum(mass.values())
        cao = sum((mass[m] / tot) * MIN[m][2] * C.M_CAO / MIN[m][0] for m in fr)
        mgo = sum((mass[m] / tot) * MIN[m][3] * C.M_MGO / MIN[m][0] for m in fr)
        rc = cao / spec["CaO_wt"] if spec["CaO_wt"] else float("inf")
        rm = mgo / spec["MgO_wt"] if spec["MgO_wt"] else float("inf")
        worst = max(worst, abs(math.log(max(rc, 1e-9))), abs(math.log(max(rm, 1e-9))))
        lines.append(f"{name}: CaO {cao:.3f} vs {spec['CaO_wt']:.3f} "
                     f"({rc:.2f}x), MgO {mgo:.3f} vs {spec['MgO_wt']:.3f} "
                     f"({rm:.2f}x)")
    tol = 0.15                       # 15% either way
    ok = worst <= math.log(1.0 + tol)
    record("6c. Archetype mineralogy mass-balances its stated oxides", ok,
           f"implied from mineral modes vs stated, tolerance +/-{tol:.0%}: "
           + "; ".join(lines))


def gate7_delivered_basalt_matches_measurement() -> None:
    """ARITHMETIC SELF-CHECK, not a validation. Relabelled deliberately.

    This asserts that delivered_basalt's CaO/MgO reproduce
    DELIVERED_BASALT_TCO2_PER_T -- but those oxide values were chosen to hit
    that target, so the gate tests arithmetic rather than the archetype. It
    used to appear in the README's gate table as evidence, which overstated
    what it shows. Keep it (a broken constant would be caught) but do not count
    it as an independent test. n = 3 deliveries, one operator, one feedstock
    source -- state that wherever 0.289 appears.

    Note also gate 6c: the same oxides do not mass-balance the mineral list.
    """
    spec = C.FEEDSTOCK_ARCHETYPES["delivered_basalt"]
    kmol = (spec["CaO_wt"] / C.M_CAO + spec["MgO_wt"] / C.M_MGO) * 1000.0
    ours = kmol * 2.0 * C.MOL_CO2_PER_KMOL_CHARGE_T
    target = C.DELIVERED_BASALT_TCO2_PER_T
    lo, hi = C.DELIVERED_BASALT_RANGE
    rel = abs(ours - target) / target

    fresh = C.FEEDSTOCK_ARCHETYPES["fresh_basalt"]
    fresh_kmol = (fresh["CaO_wt"] / C.M_CAO + fresh["MgO_wt"] / C.M_MGO) * 1000.0
    fresh_tco2 = fresh_kmol * 2.0 * C.MOL_CO2_PER_KMOL_CHARGE_T

    ok = rel < 0.02 and lo <= ours <= hi
    record("7. delivered_basalt matches verified deliveries", ok,
           f"{ours:.3f} vs measured mean {target:.3f} tCO2/t ({rel:+.1%}), "
           f"inside observed range {lo:.3f}-{hi:.3f}; fresh_basalt would be "
           f"{fresh_tco2:.3f}, i.e. +{(fresh_tco2 / ours - 1):.0%} optimistic")


def gate8_browser_constants_match_python() -> None:
    """The generated src/engine_constants.js must reproduce Python.

    This is the anti-drift gate. The browser applies the reactivity value
    function and the particle-size shift itself, so those definitions now exist
    in two places at runtime. Hand-mirrored constants silently breaking
    production is exactly what happened to the sibling BiCRS Atlas, so the
    agreement is asserted rather than assumed.

    Two tolerances, for different reasons:
      knots      must match EXACTLY (they are the same literal, emitted).
      shift table is a 24x13 grid the browser interpolates bilinearly, so a
                 small interpolation error against the exact integral is
                 expected; it is bounded here, not ignored.
    """
    import json

    root = Path(__file__).resolve().parent.parent
    js = root / "src/engine_constants.js"
    if not js.exists():
        record("8. Browser constants match Python", None,
               "src/engine_constants.js not built yet; run scripts/build_v0.py")
        return

    txt = js.read_text()
    payload = json.loads(txt[txt.index("{"):txt.rindex(";")])

    try:
        from build_v0 import L1_ENC
    except Exception as exc:            # build_v0 imports rasterio
        record("8. Browser constants match Python", None,
               f"could not import build_v0 ({type(exc).__name__})")
        return

    problems = []
    # The suitability knots and the dissolution constant are the two things the
    # browser now computes with, so they are what must not drift.
    if [list(k) for k in C.CDR_SUITABILITY_KNOTS] != [list(k) for k in payload["cdrKnots"]]:
        problems.append("cdrKnots differ")
    if [payload["l1Enc"]["lo"], payload["l1Enc"]["hi"]] != list(L1_ENC):
        problems.append("l1Enc differs")
    if abs(payload["dissolvedFracAtRef"] - C.DISSOLVED_FRAC_AT_REF) > 1e-9:
        problems.append("dissolvedFracAtRef differs")
    if abs(payload["cdrNegligible"] - C.CDR_NEGLIGIBLE_T_HA_YR) > 1e-9:
        problems.append("cdrNegligible differs")
    # cdrPerFrac must equal rate x tCO2 per tonne for the default archetype,
    # because the shader multiplies its dissolved fraction by exactly this.
    spec = C.FEEDSTOCK_ARCHETYPES[C.FEEDSTOCK_DEFAULT]
    expect = (C.APPLICATION_RATE_T_HA_YR
              * (spec["CaO_wt"] / C.M_CAO + spec["MgO_wt"] / C.M_MGO)
              * 1000.0 * 2.0 * C.MOL_CO2_PER_KMOL_CHARGE_T)
    if abs(payload["cdrPerFrac"] - expect) > 1e-4:
        problems.append(f"cdrPerFrac {payload['cdrPerFrac']} != {expect:.4f}")

    # The flux ceiling is decoded and applied in the shader as well as here, so
    # its encoding is now part of the anti-drift surface.
    try:
        from build_v0 import CEIL_ENC
    except Exception:
        CEIL_ENC = None
    fc = payload.get("fluxCeiling")
    if fc is None:
        problems.append("fluxCeiling missing from payload")
    else:
        if CEIL_ENC is not None and [fc["enc"]["lo"], fc["enc"]["hi"]] != list(CEIL_ENC):
            problems.append("fluxCeiling.enc differs")
        if bool(fc["on"]) != bool(C.FLUX_CEILING_ON):
            problems.append("fluxCeiling.on differs")
        for key, val in (("omega", C.FLUX_CEILING_OMEGA),
                         ("omegaStrict", C.FLUX_CEILING_OMEGA_STRICT),
                         ("mgMM", C.FLUX_CEILING_MG_MM)):
            if key not in fc or abs(fc[key] - val) > 1e-9:
                problems.append(f"fluxCeiling.{key} differs or missing")
        if bool(fc.get("activities")) != bool(C.FLUX_CEILING_ACTIVITIES):
            problems.append("fluxCeiling.activities differs")
    # Paddy-field view (tex5): the viewer trusts the encodings are shared with
    # the baseline channels, so the payload block must exist and be sane.
    pvw = payload.get("paddyView")
    if pvw is None or not (0.0 <= pvw.get("areaFrac", -1) <= 1.0):
        problems.append("paddyView missing or invalid")

    # Bilinear-interpolate the emitted table the way app.js does, and compare
    # against the exact integral at points deliberately BETWEEN grid nodes.
    P = payload["psd"]
    gx, gy, T = P["d50Grid"], P["widthGrid"], P["shiftTable"]

    def lookup(d50, width):
        def frac(arr, v):
            if v <= arr[0]:
                return 0, 0.0
            if v >= arr[-1]:
                return len(arr) - 2, 1.0
            i = 0
            while i < len(arr) - 2 and v > arr[i + 1]:
                i += 1
            return i, (v - arr[i]) / (arr[i + 1] - arr[i])
        i, fi = frac(gx, d50)
        j, fj = frac(gy, width)
        a = T[j][i] + (T[j][i + 1] - T[j][i]) * fi
        b = T[j + 1][i] + (T[j + 1][i + 1] - T[j + 1][i]) * fi
        return a + (b - a) * fj

    worst, at = 0.0, ""
    # Probe deliberately BETWEEN grid nodes, and at the measured delivery p50
    # values, since those are the points the map will actually be asked about.
    for d50 in (67.0, 100.0, 120.0, 150.0, 333.0, 600.0):
        for wid in (0.7, 1.1, 1.5, 2.0, 2.5):
            e = abs(lookup(d50, wid) - K.ssa_log_shift(d50, wid))
            if e > worst:
                worst, at = e, f"d50={d50:.0f} n={wid}"
    if worst > 0.01:                    # 0.01 log10 = 2.3% in rate
        problems.append(f"shift table off by {worst:.4f} log units at {at}")

    # THE REFERENCE GRIND MUST INTERPOLATE TO EXACTLY ZERO. Not "small": zero.
    # Both axes are built to pass through it (build_v0._grid_through) precisely so
    # the slider cannot say "1.01x faster weathering than the reference grind" while
    # its own badge says "Reference". That +1% also propagated into every displayed
    # CDR, since the shift multiplies the reactivity the shader reads.
    at_ref = lookup(C.PSD_REF_D50_UM, C.PSD_REF_WIDTH)
    if abs(at_ref) > 1e-12:
        problems.append(f"shift at the reference grind is {at_ref:+.6f}, not 0 "
                        f"(factor {10 ** at_ref:.4f}x) -- the reference is not a "
                        f"node on both axes")

    record("8. Browser constants match Python", not problems,
           f"CDR knots, L1 encoding, dissolution constant and cdrPerFrac all "
           f"identical; shift is EXACTLY {at_ref:+.0f} at the reference grind; "
           f"worst interpolation error elsewhere {worst:.4f} log units "
           f"({10 ** worst - 1:+.1%} in rate) at {at}"
           + ("; " + "; ".join(problems) if problems else ""))


def gate9_ssa_scaling() -> None:
    """Surface area must scale sensibly with grind, and the honest version of a
    claim made earlier in this project needs correcting.

    An earlier note said distribution width moves SSA by 'up to 33x' at fixed
    d80. That figure comes from an UNTRUNCATED Rosin-Rammler tail, where
    arbitrarily fine particles carry unbounded area. With a physical 1 um floor
    the width effect over the slider range is closer to 8x. Both the number and
    the reason are recorded so the smaller, correct figure is the one quoted.
    """
    ref = K.ssa_geometric(C.PSD_REF_D50_UM, C.PSD_REF_WIDTH)
    fine = K.ssa_geometric(C.DELIVERY_P50_SPAN_UM[0], C.PSD_REF_WIDTH)
    coarse = K.ssa_geometric(C.DELIVERY_P50_SPAN_UM[1], C.PSD_REF_WIDTH)
    broad = K.ssa_geometric(C.PSD_REF_D50_UM, C.PSD_WIDTH_SLIDER_RANGE[0])
    narrow = K.ssa_geometric(C.PSD_REF_D50_UM, C.PSD_WIDTH_SLIDER_RANGE[1])

    d_effect = fine / coarse
    w_effect = broad / narrow
    monotone = fine > ref > coarse and broad > narrow
    # 6/(rho*d) puts geometric SSA for a few-hundred-micron grind at ~0.01-0.1
    plausible = 0.001 < ref < 1.0
    ok = monotone and plausible and 3.0 < d_effect < 20.0 and 3.0 < w_effect < 15.0
    record("9. SSA scales with grind", ok,
           f"ref {ref:.4f} m2/g at d50 {C.PSD_REF_D50_UM:.0f} um; "
           f"observed p50 span {C.DELIVERY_P50_SPAN_UM[0]:.0f} vs "
           f"{C.DELIVERY_P50_SPAN_UM[1]:.0f} um -> {d_effect:.1f}x; "
           f"width {C.PSD_WIDTH_SLIDER_RANGE[0]} vs "
           f"{C.PSD_WIDTH_SLIDER_RANGE[1]} -> {w_effect:.1f}x "
           f"(NOT the 33x an untruncated tail gives)")


def gate10_zero_cdr_zero_suitability() -> None:
    """Zero carbon removal must give zero suitability.

    This is the defect that prompted tying suitability to CDR. Suitability used
    to be a weighted geometric mean of value-function transforms of the same
    three physical terms, with a uniform 0.02 quantisation floor applied as if it
    were a physical floor. A cell with zero reactivity -- hence zero carbon --
    scored exp(ln(0.02)/3) x 100 = 27. The floor existed to stop 8-bit
    quantisation swinging the score; it should never have manufactured
    suitability where the physics says none.
    """
    import numpy as np

    knots = C.CDR_SUITABILITY_KNOTS
    k = -math.log(1.0 - C.DISSOLVED_FRAC_AT_REF)

    def suit(cdr):
        if cdr < C.CDR_NEGLIGIBLE_T_HA_YR:
            return 0.0
        xs = [math.log10(x) for x, _ in knots]
        ys = [y for _, y in knots]
        return float(np.interp(math.log10(cdr), xs, ys))

    # The old scheme, for the record.
    old = math.exp(math.log(C.EPS_QUANTIZE) / 3.0) * 100.0

    checks = {
        "zero reactivity": 0.0,
        "zero alkalinity retention": 0.0,
        "zero drainage": 0.0,
    }
    # Each with the other two terms perfect.
    cases = [(0.0, 1.0, 1.0), (1e6, 0.0, 1.0), (1e6, 1.0, 0.0)]
    worst = 0.0
    for (rel, ed, et), name in zip(cases, checks):
        X = rel * ed * et
        cdr = (1.0 - math.exp(-k * X)) * C.APPLICATION_RATE_T_HA_YR * 0.29
        worst = max(worst, suit(cdr))

    # Monotone increasing, and saturating rather than clipping.
    mono = all(suit(a) <= suit(b) for a, b in zip([0.05, 0.2, 1, 3, 8],
                                                 [0.2, 1, 3, 8, 20]))
    big = 1.0 - math.exp(-k * 1e4)
    ok = worst == 0.0 and mono and big < 1.0 + 1e-12 and big > 0.999

    record("10. Zero CDR -> zero suitability", ok,
           f"all three annihilating cases give suitability {worst:.1f} "
           f"(the superseded geometric-mean scheme gave {old:.0f}); "
           f"monotone {mono}; dissolution saturates to {big:.4f}, never clipped")


def gate11_gudbrandsson_no_free_parameters() -> None:
    """THE independent test of the kinetics: reproduce measured Ca and Mg release
    from crystalline basalt across pH 2-11 and 5-75 C with NO fitted parameters.

    Independent in a way the field trials are not. It tests the rate law and the
    mineral mixing directly, with no surface-area multiplier, no application rate
    and no downstream loss terms to absorb error.

    Pre-registered tolerance: 0.5 log units (docs/VALIDATION.md).

    Run twice, deliberately:
      - VOLUME fractions, which is what a naive mixture model uses;
      - the paper's own fitted RELATIVE SURFACE AREAS.
    The gap between the two is the finding. Their fit needed plagioclase at 83% of
    the reacting surface against a 44% volume share, so a volume-fraction model
    should under-predict Ca and over-predict Mg. If it does, the discrepancy is
    understood rather than mysterious.

    TWO CORRECTIONS TO HOW THIS GATE USED TO BE SCORED. Both made it look better
    than it was:

      1. It passed/failed on the paper's own fitted SURFACE fractions, justified
         as "their measurement of the rock, not part of our model". But the
         fixture header records those numbers as what their mixing model NEEDED
         to fit within 0.5 log units -- i.e. three parameters fitted to the same
         25 experiments being predicted, which will have absorbed every other
         error in their model. A gate titled "no free parameters" cannot be
         scored on a borrowed in-sample fit. It now keys on VOLUME fractions,
         which is what build_v0.py actually ships.
      2. It reported Ca and Mg separately, but the map uses their CHARGE SUM
         (rate_ca_mg_release), and the sum is worse than either element implies.
         The charge-sum residual is now computed and reported, restricted to the
         cropland domain the map occupies (5-25 C, pH 4-8.5), because the pooled
         5-75 C figure is dominated by experiments at temperatures no cropland
         reaches. The restricted figure is a DIAGNOSTIC, never the pass
         criterion -- restricting a range post hoc to improve a statistic is
         exactly the move that has to be declared.
    """
    import csv as _csv

    root = Path(__file__).resolve().parent.parent
    src = root / "tests/fixtures/gudbrandsson2011_basalt.csv"
    if not src.exists():
        record("11. Gudbrandsson no-free-parameter test", None,
               "tests/fixtures/gudbrandsson2011_basalt.csv missing")
        return

    rows = []
    with src.open() as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            rows = [r for r in _csv.DictReader([line] + fh.readlines())]
            break
    obs = [r for r in rows if r.get("outlier") == "0"]

    # Their rates are per cm2 of BET surface; ours are per m2. 1 m2 = 1e4 cm2.
    CM2_PER_M2 = 1.0e4
    out = {}
    for label, fr in (("volume", C.STAPAFELL_VOLUME_FRACTIONS),
                      ("their surface fit", C.STAPAFELL_SURFACE_FRACTIONS)):
        res = {}
        for el in ("Ca", "Mg"):
            d = []
            for r in obs:
                v = r.get(f"log_r_{el}")
                if not v:
                    continue
                pred = K.element_release(fr, el, float(r["pH"]),
                                         float(r["T_C"]) + 273.15)
                if pred <= 0:
                    continue
                d.append(math.log10(float(pred) / CM2_PER_M2) - float(v))
            if d:
                a = np.array(d)
                res[el] = (float(np.mean(a)), float(np.mean(np.abs(a))),
                           float(np.max(np.abs(a))), len(a))
        out[label] = res

    # ---- The CHARGE SUM, which is the quantity the map actually uses.
    # Ca + Mg in charge equivalents, exactly as rate_ca_mg_release builds it, so
    # a pass here would mean the shipped function reproduces the rock.
    charge = {}
    for label, fr in (("volume", C.STAPAFELL_VOLUME_FRACTIONS),
                      ("their surface fit", C.STAPAFELL_SURFACE_FRACTIONS)):
        for band, keep in (("all 5-75 C", lambda r: True),
                           ("cropland 5-25 C, pH 4-8.5",
                            lambda r: float(r["T_C"]) <= 25.0
                            and 4.0 <= float(r["pH"]) <= 8.5)):
            d = []
            for r in obs:
                if not keep(r):
                    continue
                vca, vmg = r.get("log_r_Ca"), r.get("log_r_Mg")
                if not vca or not vmg:
                    continue
                pH, T_K = float(r["pH"]), float(r["T_C"]) + 273.15
                # Measured charge: 2 equivalents per divalent cation.
                meas = 2.0 * (10.0 ** float(vca) + 10.0 ** float(vmg))
                pred = 0.0
                for mineral, f in fr.items():
                    nu = K.ELEMENT_PER_FORMULA[mineral]
                    pred += ((f / sum(fr.values())) * 2.0
                             * (nu.get("Ca", 0.0) + nu.get("Mg", 0.0))
                             * float(K.mineral_rate(mineral, pH, T_K)))
                if pred <= 0 or meas <= 0:
                    continue
                d.append(math.log10(pred / CM2_PER_M2) - math.log10(meas))
            if d:
                a = np.array(d)
                charge[(label, band)] = (float(np.mean(a)),
                                         float(np.mean(np.abs(a))), len(a))

    tol = C.GUDBRANDSSON_TOLERANCE_LOG
    vol = out["volume"]
    # PASS/FAIL ON THE SHIPPED BASIS: volume fractions, charge sum, full range.
    # Not on the paper's fitted surface fractions -- those are three parameters
    # fitted to this same dataset, so scoring on them borrows an in-sample fit.
    key = ("volume", "all 5-75 C")
    worst = charge[key][1] if key in charge else (
        max(v[1] for v in vol.values()) if vol else 9.9)
    ok = worst <= tol

    parts = []
    for label in ("volume", "their surface fit"):
        for el, (bias, mad, mx, n) in out[label].items():
            parts.append(f"{label[:3]}/{el} bias {bias:+.2f} MAD {mad:.2f} (n={n})")
    for (label, band), (bias, mad, n) in charge.items():
        parts.append(f"{label[:3]}/CHARGE [{band}] bias {bias:+.2f} "
                     f"MAD {mad:.2f} (n={n})")
    record("11. Gudbrandsson independent test (scored on the SHIPPED basis: "
           "volume fractions, Ca+Mg charge sum)", ok,
           f"log10 residuals vs measured, tolerance {tol}: " + "; ".join(parts))
    gate11_gudbrandsson_no_free_parameters.detail = {"per_element": out,
                                                     "charge_sum": charge}


def gate11b_surface_partition_overidentified() -> None:
    """Can ANY single surface partition reproduce all four measured elements?

    This is the test that decides whether "the reacting surface is not the volume
    share" can rescue the rate law -- strand A of the kinetics plan. It uses data
    we already held and were not using.

    THE LOGIC. Stapafell is modelled as three minerals, so a surface partition on
    the simplex has only TWO free parameters. The fixture measures FOUR elements
    (Si, Ca, Mg, Fe). Requiring one partition to reproduce all four is therefore
    OVER-IDENTIFIED by two degrees of freedom -- a genuine test rather than a fit.

    Why this matters more than another temperature-banded refit: a per-temperature
    surface refit is aliased with an activation-energy error (the fitted olivine
    share trends with 1/T, implying an Ea offset indistinguishable from the one
    recovered from the residual slope), so it cannot distinguish the two
    hypotheses it was written to distinguish. Si and Fe constrain the partition
    from OUTSIDE the temperature dimension, which breaks that alias.

    Reported, in order of how much each tells you:

      1. Fit to Ca+Mg only, then score Si and Fe HELD OUT. This is the honest
         out-of-sample test, and it fails spectacularly -- see below.
      2. Fit to all four at once, unconstrained. If no partition passes here,
         with two parameters fitted directly to the test data, then surface
         repartitioning is not the answer and no amount of it will be.
      3. Fit to all four constrained within a factor of 3 of the volume share,
         which is the pre-registered plausibility bound (docs/VALIDATION.md s3).
         An unconstrained fit that only works at the simplex boundary is not a
         physical result.

    WHAT IT FOUND, recorded because it is a negative result worth keeping:
    fitting to Ca+Mg alone drives augite to ZERO -- for a rock that is 39 vol%
    pyroxene -- and Fe, the held-out element, then collapses by roughly 18 log
    units, because augite is the only Fe carrier in the mineral set. So the
    Ca+Mg-optimal partition is decisively falsified by an element it was not
    fitted to. And even fitting all four together, no partition reaches the
    0.5-log tolerance on every element. The residual is not a mixing problem.
    """
    import csv as _csv

    root = Path(__file__).resolve().parent.parent
    src = root / "tests/fixtures/gudbrandsson2011_basalt.csv"
    if not src.exists():
        record("11b. Surface partition over-identified by Si and Fe", None,
               "fixture missing")
        return
    try:
        from scipy.optimize import minimize
    except Exception as exc:
        record("11b. Surface partition over-identified by Si and Fe", None,
               f"scipy unavailable ({type(exc).__name__})")
        return

    obs = [r for r in _csv.DictReader(
        l for l in src.open() if not l.startswith("#")) if r.get("outlier") == "0"]
    MINS = list(C.STAPAFELL_VOLUME_FRACTIONS)
    ELS = ("Si", "Ca", "Mg", "Fe")
    CM2_PER_M2 = 1.0e4

    def resid(fr, el):
        d = []
        norm = sum(fr.values())
        for r in obs:
            v = r.get(f"log_r_{el}")
            if not v:
                continue
            pH, T_K = float(r["pH"]), float(r["T_C"]) + 273.15
            tot = 0.0
            for mineral in MINS:
                nu = K.ELEMENT_PER_FORMULA[mineral].get(el, 0.0)
                if nu:
                    tot += (fr[mineral] / norm) * nu * float(
                        K.mineral_rate(mineral, pH, T_K))
            if tot <= 0:
                continue
            d.append(math.log10(tot / CM2_PER_M2) - float(v))
        return np.array(d) if d else np.array([9.9])

    def mad(fr, els):
        return {e: (float(resid(fr, e).mean()),
                    float(np.abs(resid(fr, e)).mean())) for e in els}

    def unpack(x):
        w = np.exp(np.concatenate([[0.0], x]))
        return dict(zip(MINS, w / w.sum()))

    def fit(els, bound=None):
        def obj(x):
            fr = unpack(x)
            pen = 0.0
            if bound:
                for mineral in MINS:
                    ratio = fr[mineral] / C.STAPAFELL_VOLUME_FRACTIONS[mineral]
                    if ratio > bound or ratio < 1.0 / bound:
                        pen += 10.0 * abs(math.log(ratio))
            return sum(np.abs(resid(fr, e)).mean() for e in els) / len(els) + pen
        best = None
        for seed in ([0, 0], [1, -1], [-1, 1], [2, -2], [0, -3]):
            r = minimize(obj, seed, method="Nelder-Mead",
                         options=dict(maxiter=6000, xatol=1e-4, fatol=1e-4))
            if best is None or r.fun < best.fun:
                best = r
        return unpack(best.x)

    tol = C.GUDBRANDSSON_TOLERANCE_LOG
    cases = {}
    cases["volume (shipped)"] = (C.STAPAFELL_VOLUME_FRACTIONS,
                                 mad(C.STAPAFELL_VOLUME_FRACTIONS, ELS))
    fr_camg = fit(("Ca", "Mg"))
    cases["fit Ca+Mg, Si/Fe HELD OUT"] = (fr_camg, mad(fr_camg, ELS))
    fr_all = fit(ELS)
    cases["fit all four, unconstrained"] = (fr_all, mad(fr_all, ELS))
    fr_bnd = fit(ELS, bound=3.0)
    cases["fit all four, within 3x volume"] = (fr_bnd, mad(fr_bnd, ELS))

    # The finding: does ANY partition reach tolerance on every element?
    best_worst = min(max(v for _, v in res.values()) for _, res in cases.values())
    any_passes = best_worst <= tol

    parts = []
    for label, (fr, res) in cases.items():
        shares = "/".join(f"{fr[m]:.2f}" for m in MINS)
        els = " ".join(f"{e} {res[e][1]:.2f}" for e in ELS)
        parts.append(f"[{label}] {shares} -> {els}")

    # This gate PASSES when the over-identification is informative, i.e. when it
    # successfully discriminates. It reports the negative result rather than
    # failing on it -- gate 11 already carries the red flag for the rate law.
    record("11b. Surface partition over-identified by Si and Fe",
           True,
           f"best achievable worst-element MAD {best_worst:.2f} vs tolerance "
           f"{tol} -> surface repartitioning "
           f"{'CAN' if any_passes else 'CANNOT'} rescue the rate law. "
           + "; ".join(parts))
    gate11b_surface_partition_overidentified.detail = cases


def gate13_flux_ceiling_chemistry() -> None:
    """The drainage-concentration ceiling, against a textbook benchmark.

    The closed form solves charge balance, fixed pCO2 and calcite saturation
    simultaneously. The clean external check is the classic open-system calcite
    equilibrium: pure water plus calcite at atmospheric pCO2 gives roughly
    1 mmol/L alkalinity, 0.5 mmol/L Ca and pH ~8.3 (any aqueous-geochemistry
    text; e.g. Drever, The Geochemistry of Natural Waters). Setting f_Ca = 1 and
    Omega = 1 must reproduce that, which tests the algebra, the calcite constant
    and the charge-balance coupling in one shot.

    The textbook figure is the infinite-dilution one, so activities are OFF
    here to compare like with like (the shipped ceiling has them ON; gate 13d
    validates that path against PHREEQC). Without them the CaHCO3+ ion pair and
    activity neglect bias the result LOW by ~10-20% at these ionic strengths,
    so the tolerance is one-sided-ish.
    """
    a = float(K.alkalinity_ceiling_mol_l(C.PCO2_ATMOSPHERIC_UATM, 298.15,
                                        omega=1.0, f_ca=1.0, activities=False))
    K1, _, KH, _ = K.carbonate_constants(298.15)
    pH = -math.log10(K1 * KH * C.PCO2_ATMOSPHERIC_UATM * 1e-6 / a)
    ok = (0.85e-3 <= a <= 1.05e-3) and (8.0 <= pH <= 8.4)
    record("13. Flux-ceiling chemistry vs calcite benchmark", ok,
           f"pure water + calcite at {C.PCO2_ATMOSPHERIC_UATM:.0f} uatm -> "
           f"alkalinity {a * 1e3:.3f} mmol/L, Ca {a * 1e3 / 2:.3f}, pH {pH:.2f}; "
           f"textbook ~1.0 / ~0.5 / ~8.3")


def gate13b_flux_ceiling_within_observed_range() -> None:
    """The ceiling must land inside independently measured drainage chemistry.

    Not a validation -- the anchors are analogues, not replicates of amended
    cropland. It is a falsification test: if the closed form put the ceiling at
    0.4 or at 30 mmol/L it would sit outside everything ever measured and the
    model would be bounding the carbon at the wrong level. The tightest and most
    relevant anchor is Hamilton et al. 2007 (GBC 21, GB2021), which measured
    1-7 mmol/L in Midwest agricultural tile drainage and limed-row-crop
    porewater, the closest available analogue to the quantity being bounded.

    Scored on DRAINED cropland only, at the protocol's mandated 4,000 uatm. The
    saturated (paddy) case is reported separately by gate 13c because it is not
    checkable against anything -- see that gate.

    Also asserts the direction of the temperature dependence, because it is the
    single most consequential property of this term: C_eq FALLS with warming
    while the rate law rises, so the ceiling removes most of the map's
    warm-climate advantage rather than merely rescaling it.
    """
    lo_env = min(v[0] for v in C.FLUX_CEILING_ANCHORS_MMOL_L.values())
    hi_env = max(v[1] for v in C.FLUX_CEILING_ANCHORS_MMOL_L.values())
    probes = [float(K.alkalinity_ceiling_mol_l(
                  C.PCO2_UNSATURATED_UATM, T_C + 273.15, omega=om)) * 1e3
              for T_C in (5.0, 15.0, 25.0)
              for om in (C.FLUX_CEILING_OMEGA_STRICT, C.FLUX_CEILING_OMEGA)]
    inside = all(lo_env <= v <= hi_env for v in probes)

    cold = float(K.alkalinity_ceiling_mol_l(C.PCO2_UNSATURATED_UATM, 278.15))
    warm = float(K.alkalinity_ceiling_mol_l(C.PCO2_UNSATURATED_UATM, 298.15))
    falls = warm < cold
    hlo, hhi = C.FLUX_CEILING_ANCHORS_MMOL_L[
        "Hamilton 2007 Midwest tile drainage / porewater"]
    record("13b. Flux ceiling inside measured drainage chemistry", inside and falls,
           f"drained cropland ceiling spans {min(probes):.2f}-{max(probes):.2f} "
           f"mmol/L over 5-25 C and Omega {C.FLUX_CEILING_OMEGA_STRICT:g}-"
           f"{C.FLUX_CEILING_OMEGA:g}, inside the {lo_env:.2f}-{hi_env:.2f} "
           f"envelope of five independent anchors and straddling the most "
           f"relevant one ({hlo:g}-{hhi:g}, Hamilton et al. 2007). Warming "
           f"LOWERS it, {cold * 1e3:.2f} -> {warm * 1e3:.2f} mmol/L over 5-25 C "
           f"({'correct sign' if falls else 'WRONG SIGN'})"
           + ("" if inside else "; a probe fell outside the envelope"))


def gate13c_paddy_ceiling_is_unvalidated() -> None:
    """REPORTED, not scored: on saturated cells the ceiling exceeds every anchor.

    The protocol mandates 50,000 uatm for saturated systems (Isometric EW-in-
    agriculture v1.2, requirement R-D338-0), and since the ceiling goes as
    pCO2^(1/3) that lifts it to roughly 13-18 mmol/L at the shipped Omega -- above
    the top of every anchor available, including Zhang et al. 2022's
    back-converted riverine limit.

    This is not resolvable here, and deliberately not tolerance-fudged into a
    pass. The literature contains NO measured floodwater alkalinity or paddy
    lateral DIC export flux: every ERW-in-paddy trial reached measured only
    solid-phase carbon. So on the 10.3% of cropland with material flooded
    cell-time the ceiling is an extrapolation, not a bound checked against
    anything. It is also the loosest part of the term, so it constrains those
    cells least -- which is the honest way round, but it means paddy CDR in this
    map is bounded mostly by the kinetics and not by this gate.

    Recorded as the standing justification for field-data ask #6 (one measured
    paddy drainage-water DIC or alkalinity export flux).
    """
    hi_env = max(v[1] for v in C.FLUX_CEILING_ANCHORS_MMOL_L.values())
    probes = [float(K.alkalinity_ceiling_mol_l(
                  C.PCO2_SATURATED_UATM, T_C + 273.15, omega=om)) * 1e3
              for T_C in (5.0, 15.0, 25.0)
              for om in (C.FLUX_CEILING_OMEGA_STRICT, C.FLUX_CEILING_OMEGA)]
    record("13c. Paddy ceiling exceeds every anchor (reported)", None,
           f"at the mandated {C.PCO2_SATURATED_UATM:.0f} uatm the ceiling is "
           f"{min(probes):.2f}-{max(probes):.2f} mmol/L against an anchor "
           f"envelope topping out at {hi_env:.2f}; no measured paddy drainage "
           f"DIC exists to check it. Unvalidated on ~10.3% of cropland area")


def gate13d_ceiling_reproduces_mayer_phreeqc() -> None:
    """The ceiling's carbonate solve must reproduce an independent PHREEQC grid.

    Mayer et al. 2025 (doi:10.21203/rs.3.rs-7811095/v1, Table S.1, transcribed
    in tests/fixtures/mayer2025_tableS1.csv) ran phreeqci 3.7.3 / wateq4f over
    54 open-system cases: pCO2 x calcite SI x fixed Mg, at 25 C. That is
    exactly the system alkalinity_ceiling_mol_l solves in its Mg-explicit form,
    so every case is a free external check of the algebra, the constants, and
    the Davies activity iteration at once -- by the strongest independent
    geochemistry code there is, run by people who did not know this closed
    form exists.

    Tolerances: every case within [0.93, 1.02] of PHREEQC total alkalinity,
    median within [0.95, 1.00], and the model's own pH within +/-0.20. The
    expected signature is a SMALL LOW bias (neglected CaHCO3+/MgHCO3+ ion
    pairs), so a median above 1.00 would mean something is wrong in the other
    direction, not extra credit. Also asserts the temperature slope at their
    central case: alkalinity must fall 22-30% from 5 C to 25 C (their Fig. 4
    reports ~26% for DIC).
    """
    import csv
    fx = Path(__file__).parent.parent / C.MAYER_2025_FIXTURE
    if not fx.exists():
        record("13d. Ceiling vs Mayer et al. 2025 PHREEQC grid", None,
               f"fixture missing: {fx}")
        return
    rows = [r for r in csv.DictReader(
        (ln for ln in fx.read_text().splitlines() if not ln.startswith("#")))]
    T = 298.15
    K1, _, KH, _ = (float(x) for x in K.carbonate_constants(T))
    ratios, ph_errs = [], []
    for r in rows:
        a_ph = float(r["alk_mg_hco3_l"]) / 61.0168e3        # mg HCO3 -> mol/L
        a = float(K.alkalinity_ceiling_mol_l(
            float(r["pco2"]), T, omega=10.0 ** float(r["si"]),
            mg_mM=float(r["mg_mM"]), activities=True))
        ratios.append(a / a_ph)
        ph_errs.append(-math.log10(K1 * KH * float(r["pco2"]) * 1e-6 / a)
                       - float(r["ph"]))
    ratios.sort()
    med = ratios[len(ratios) // 2]
    worst_ph = max(abs(e) for e in ph_errs)
    ok = (len(rows) == 54 and ratios[0] >= 0.93 and ratios[-1] <= 1.02
          and 0.95 <= med <= 1.00 and worst_ph <= 0.20)

    mc = C.MAYER_2025_CENTRAL_CASE
    a5 = float(K.alkalinity_ceiling_mol_l(mc["pco2_uatm"], 278.15,
               omega=10.0 ** mc["si"], mg_mM=mc["mg_mM"]))
    a25 = float(K.alkalinity_ceiling_mol_l(mc["pco2_uatm"], 298.15,
                omega=10.0 ** mc["si"], mg_mM=mc["mg_mM"]))
    slope = 1.0 - a25 / a5
    ok = ok and (0.22 <= slope <= 0.30)
    record("13d. Ceiling vs Mayer et al. 2025 PHREEQC grid", ok,
           f"{len(rows)} cases: ours/PHREEQC {ratios[0]:.3f}-{ratios[-1]:.3f}, "
           f"median {med:.3f} (expected small LOW bias: ion pairs neglected); "
           f"pH within +/-{worst_ph:.2f}; 5->25 C alkalinity slope "
           f"-{slope:.0%} vs their Fig. 4 ~-26%")


def gate14_dissolution_table_matches_exact() -> None:
    """The browser's shrinking-core lookup must reproduce the exact integral.

    The shader cannot integrate 6,000 size bins per pixel, so it interpolates a
    64 x 13 table of G(u, n). This asserts the interpolated value against the exact
    integral at points deliberately BETWEEN nodes on both axes, which is where a
    table is wrong if it is wrong.

    Tolerance 0.004 in fraction weathered, which is the 8-bit texture quantisation
    step -- there is no point being more accurate than the thing downstream.
    """
    import json

    root = Path(__file__).resolve().parent.parent
    js = root / "src/engine_constants.js"
    if not js.exists():
        record("14. Dissolution table matches the exact integral", None,
               "src/engine_constants.js not built yet; run scripts/build_v0.py")
        return
    txt = js.read_text()
    D = json.loads(txt[txt.index("{"):txt.rindex(";")]).get("dissolution")
    if D is None:
        record("14. Dissolution table matches the exact integral", False,
               "no dissolution block in the payload")
        return

    lo, hi, T, ws = D["uLog"]["lo"], D["uLog"]["hi"], D["table"], D["widthGrid"]
    nu = len(T[0])

    def lookup(u, n):
        j = 0
        while j < len(ws) - 2 and n > ws[j + 1]:
            j += 1
        fj = min(max((n - ws[j]) / (ws[j + 1] - ws[j]), 0.0), 1.0)
        t = (math.log10(u) - lo) / (hi - lo) * (nu - 1)
        if t <= 0:
            return 0.0
        if t >= nu - 1:
            return T[j][nu - 1] + (T[j + 1][nu - 1] - T[j][nu - 1]) * fj
        i = int(t)
        a = T[j][i] + (T[j][i + 1] - T[j][i]) * (t - i)
        b = T[j + 1][i] + (T[j + 1][i + 1] - T[j + 1][i]) * (t - i)
        return a + (b - a) * fj

    worst, at = 0.0, ""
    for u in (2e-5, 3.7e-4, 0.0031, 0.019, 0.047, 0.31, 1.7, 9.0):
        for n in (0.78, 1.1, 1.5, 1.93, 2.31):
            e = abs(lookup(u, n) - float(K.dissolved_fraction(u, n)[0]))
            if e > worst:
                worst, at = e, f"u={u:g} n={n}"
    # And the reference must come back as the anchor, exactly.
    dref = K.retreat_at_reference()
    at_ref = lookup(dref / C.PSD_REF_D50_UM, C.PSD_REF_WIDTH)
    ref_err = abs(at_ref - C.DISSOLVED_FRAC_AT_REF)

    ok = worst <= 0.004 and ref_err <= 0.004
    record("14. Dissolution table matches the exact integral", ok,
           f"worst interpolation error {worst:.4f} in fraction at {at} "
           f"(tolerance 0.004, the 8-bit step); at the reference grind the table "
           f"returns {at_ref:.4f} against the {C.DISSOLVED_FRAC_AT_REF} anchor "
           f"(off by {ref_err:.4f})")


def gate15_no_grind_double_count() -> None:
    """Grind must enter the CDR chain exactly ONCE.

    Under shrinking core the linear retreat rate does not depend on particle size,
    so the old specific-surface-area multiplier on the rate had to go when the
    particle-size integral came in. If both were live, a finer grind would raise
    the rate AND shrink the particles, counting the same physics twice -- which is
    the defect that once inflated CO2 by 3.45x at the fine end.

    Asserted structurally: the shader must not add the SSA shift into L1.
    """
    root = Path(__file__).resolve().parent.parent
    app = (root / "src/app.js")
    if not app.exists():
        record("15. Grind is not double-counted", None, "src/app.js not found")
        return
    src = app.read_text()
    # The rate path is the l1 decode; it must be free of the SSA shift.
    i = src.find("float l1  = mix(uL1Enc.x")
    seg = src[i:src.find(";", i)] if i >= 0 else ""
    bad = "uSsaShift" in seg
    still_used = "uSsaShift" in src
    record("15. Grind is not double-counted", (not bad) and (not still_used),
           "the shader's L1 decode carries no surface-area term, and uSsaShift is "
           "gone from the shader entirely; grind acts only through the "
           "particle-size integral"
           + ("; FOUND uSsaShift in the L1 decode" if bad else "")
           + ("; uSsaShift still present elsewhere in the shader" if still_used and not bad else ""))


def report_calibration_arithmetic() -> None:
    """Not a gate -- context that catches the error class that bit us once.

    An earlier draft used 50 t/ha for the Beerling anchor when the paper applied
    50 t/ha/yr for 4 years = 200 t/ha cumulative. The implied dissolved fraction
    is the tell: 22% is plausible, 88% would be pinned at the ceiling.
    """
    a = C.CALIBRATION_ANCHOR
    meta = C.FEEDSTOCK_ARCHETYPES["metabasalt"]
    kmol = (meta["CaO_wt"] / C.M_CAO + meta["MgO_wt"] / C.M_MGO) * 1000.0
    tco2_per_t = kmol * 2.0 * C.MOL_CO2_PER_KMOL_CHARGE_T

    for label, applied in (("as published (200 t/ha)", a["cumulative_t_ha"]),
                           ("the wrong anchor (50 t/ha)", 50.0)):
        ceiling = applied * tco2_per_t
        frac = a["cdr_pot_tco2_ha"] / ceiling
        flag = "plausible" if frac < 0.5 else "AT THE CEILING -- wrong"
        print(f"    {label:28s} ceiling {ceiling:6.1f} tCO2/ha -> "
              f"{frac:5.1%} dissolved over 4 yr  [{flag}]")


def main() -> int:
    print("=" * 78)
    print("ERW Atlas -- kinetics gates")
    print("=" * 78)

    for fn in (gate1_carbonate_constants, gate2_protocol_thresholds,
               gate2b_ace_high_ph_asymptote, gate2c_charge_vs_bertagni_table1,
               gate2d_eta_dic_reproduces_dietzen_rosing_xstar,
               gate3_ph_leverage, gate4_constants_match_source,
               gate5_monotonicity, gate6_cdrmax_vs_published,
               gate6b_archetype_ceilings, gate6c_mineralogy_mass_balance,
               gate7_delivered_basalt_matches_measurement,
               gate8_browser_constants_match_python, gate9_ssa_scaling,
               gate10_zero_cdr_zero_suitability,
               gate11_gudbrandsson_no_free_parameters,
               gate11b_surface_partition_overidentified,
               gate13_flux_ceiling_chemistry,
               gate13b_flux_ceiling_within_observed_range,
               gate13c_paddy_ceiling_is_unvalidated,
               gate13d_ceiling_reproduces_mayer_phreeqc,
               gate14_dissolution_table_matches_exact,
               gate15_no_grind_double_count):
        try:
            fn()
        except Exception as exc:  # a crashing gate is a failing gate
            record(fn.__name__, False, f"raised {type(exc).__name__}: {exc}")

    width = max(len(g) for g, _, _ in results)
    for gate, status, detail in results:
        print(f"  [{status}] {gate:<{width}}  {detail}")

    g = getattr(gate11_gudbrandsson_no_free_parameters, "detail", None)
    if g:
        print()
        print("  Gudbrandsson residuals, log10(predicted / measured):")
        print(f"    {'weighting':20s} {'el':3s} {'bias':>7s} {'MAD':>6s} {'max':>6s} {'n':>4s}")
        for label, res in g["per_element"].items():
            for el, (bias, mad, mx, n) in res.items():
                print(f"    {label:20s} {el:3s} {bias:+7.2f} {mad:6.2f} {mx:6.2f} {n:4d}")
        print()
        print("  Ca+Mg CHARGE SUM -- the quantity the map uses. The shipped basis")
        print("  is volume fractions; the surface-fit rows are the paper's own")
        print("  in-sample fit and are a diagnostic upper bound, not our model.")
        print(f"    {'weighting':20s} {'band':26s} {'bias':>7s} {'MAD':>6s} {'n':>4s}")
        for (label, band), (bias, mad, n) in g["charge_sum"].items():
            print(f"    {label:20s} {band:26s} {bias:+7.2f} {mad:6.2f} {n:4d}")

    rows = getattr(gate6_cdrmax_vs_published, "rows", None)
    if rows:
        print()
        print("  Per-mineral CDRmax, ours vs published (t CO2 / t mineral):")
        for r in rows:
            print(f"    {r}")

    print()
    print("  Calibration anchor arithmetic (context, not a gate):")
    report_calibration_arithmetic()

    n_fail = sum(1 for _, s, _ in results if s == FAIL)
    n_skip = sum(1 for _, s, _ in results if s == SKIP)
    print()
    print(f"  {len(results) - n_fail - n_skip} passed, {n_fail} failed, {n_skip} skipped")
    print()
    # Be explicit about what this suite is and is not. "14 passed" reads as 14
    # pieces of validation evidence, and it is not: exactly ONE gate compares
    # the model against independent measurements it was not built from, and it
    # fails. The rest are unit conversions, reproductions of published
    # constants, monotonicity invariants, internal consistency checks and
    # code-drift assertions -- all worth having, none of them validation.
    print("  WHAT THIS SUITE IS. Three gates carry real evidential weight:")
    print("    11  the only test against independent measurements of the RATE LAW")
    print("        (Gudbrandsson 2011). It FAILS -- the Ca+Mg charge sum the map")
    print("        uses over-predicts by ~1.2 log units on the shipped basis.")
    print("    2d  eta_DIC vs Dietzen & Rosing's X*, derived from a proton budget")
    print("        rather than carbonate equilibrium. PASSES to within 0.03 across")
    print("        a 40x pCO2 range -- the strongest external check here, and it")
    print("        means the strong-acid correction is already in the model.")
    print("    11b an over-identified structural test: two free surface fractions")
    print("        against four measured elements. Answers a question rather than")
    print("        validating a layer, and the answer is that repartitioning the")
    print("        reacting surface CANNOT rescue the rate law.")
    print("  Gate 6c also fails: the archetypes' mineral modes imply up to 2x")
    print("  their stated MgO. Every other gate is an internal consistency or")
    print("  literature-reproduction check, not validation, and gate 7 is an")
    print("  arithmetic self-check that should not be counted at all.")
    print("  No layer in this model is 'validated'. See docs/VALIDATION.md.")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
