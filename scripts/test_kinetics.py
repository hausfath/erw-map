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


def gate7_delivered_basalt_matches_measurement() -> None:
    """The delivered_basalt archetype must reproduce the CO2 potential implied by
    independently verified deliveries. This is the one archetype anchored to
    measurement rather than to a textbook composition, so it is the one that
    should be used for anything user-facing."""
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

    record("8. Browser constants match Python", not problems,
           f"CDR knots, L1 encoding, dissolution constant and cdrPerFrac all "
           f"identical; shift-table interpolation error "
           f"max {worst:.4f} log units ({10 ** worst - 1:+.1%} in rate) at {at}"
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

    tol = C.GUDBRANDSSON_TOLERANCE_LOG
    vol, fit = out["volume"], out["their surface fit"]
    # The gate passes on the paper's own surface fractions -- that is the fair
    # test of OUR rate law, since the surface-area split is their measurement of
    # the rock, not part of our model.
    worst_fit = max(v[1] for v in fit.values()) if fit else 9.9
    ok = worst_fit <= tol

    parts = []
    for label in ("volume", "their surface fit"):
        for el, (bias, mad, mx, n) in out[label].items():
            parts.append(f"{label[:3]}/{el} bias {bias:+.2f} MAD {mad:.2f} (n={n})")
    record("11. Gudbrandsson no-free-parameter test", ok,
           f"log10 residuals vs measured, tolerance {tol}: " + "; ".join(parts))
    gate11_gudbrandsson_no_free_parameters.detail = out


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
               gate3_ph_leverage, gate4_constants_match_source,
               gate5_monotonicity, gate6_cdrmax_vs_published,
               gate6b_archetype_ceilings,
               gate7_delivered_basalt_matches_measurement,
               gate8_browser_constants_match_python, gate9_ssa_scaling,
               gate10_zero_cdr_zero_suitability,
               gate11_gudbrandsson_no_free_parameters):
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
        for label, res in g.items():
            for el, (bias, mad, mx, n) in res.items():
                print(f"    {label:20s} {el:3s} {bias:+7.2f} {mad:6.2f} {mx:6.2f} {n:4d}")

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
    print("  Still outstanding, and it gates phase 2: the Gudbrandsson et al. 2011")
    print("  no-free-parameter test of Ca and Mg release vs pH at 5-25 C.")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
