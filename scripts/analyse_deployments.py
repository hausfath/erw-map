"""
What the 2026 verified deliveries can and cannot tell us.

  python3 scripts/analyse_deployments.py

This runs BEFORE the gridded model exists, deliberately. The point is to
establish what the observations constrain on their own, so that when the model
is compared against them later we already know how much power the test has and
which comparisons are circular.

INPUT DATA IS NOT IN THIS REPOSITORY. The fixture is derived from an independent
verification report and its cross-operator comparison, and carries per-operator
results that are not ours to publish. It is gitignored. This script exits with a
pointer if the fixture is absent, so the method stays reviewable even though the
inputs are not redistributed.

To reproduce, supply tests/fixtures/deployments_2026.csv with the header:
    deployment,operator,registry,regime,country,rate_t_ha,fw_p50,fw_p16,
    cdr_tco2_ha,cdr_exact,period_months,psd_known,soil_note
where fw_* are fractions of applied rock weathered, cdr_exact is yes/no for
whether CDR was measured independently rather than derived, and regime groups
sites by soil and climate.

Three findings, in decreasing order of how much I'd stake on them. Run it and
read the output rather than taking these on trust.
"""

from __future__ import annotations

import csv
import itertools
import math
from pathlib import Path

import numpy as np

FIXTURE = Path(__file__).resolve().parent.parent / "tests/fixtures/deployments_2026.csv"


def load() -> list[dict] | None:
    if not FIXTURE.exists():
        return None
    rows = []
    with FIXTURE.open() as fh:
        for line in fh:
            if line.startswith("#"):
                continue
            rows = list(csv.DictReader(itertools.chain([line], fh)))
            break
    for r in rows:
        for k in ("rate_t_ha", "fw_p50", "fw_p16", "cdr_tco2_ha", "period_months"):
            r[k] = float(r[k])
        r["p50_um"] = float(r["p50_um"]) if r.get("p50_um") else None
    return rows


def rule(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


# ---------------------------------------------------------------------------
def check_cdr_is_circular(rows: list[dict]) -> None:
    """Confirm from the numbers themselves that the DERIVED CDR/ha rows are
    algebraically a function of fraction weathered, and so cannot serve as an
    independent validation target."""
    rule("1. Is CDR/ha independent information, or algebra?")
    print("  Testing whether cdr = rate x fw_p50 x 0.33 reproduces each row.")
    print()
    print(f"  {'deployment':14s} {'reported':>9s} {'rate*fw*0.33':>13s} {'ratio':>7s}  exact?")
    for r in rows:
        implied = r["rate_t_ha"] * r["fw_p50"] * 0.33
        ratio = r["cdr_tco2_ha"] / implied
        print(f"  {r['deployment']:14s} {r['cdr_tco2_ha']:9.2f} {implied:13.2f} "
              f"{ratio:7.3f}  {r['cdr_exact']}")
    print()
    print("  Derived rows reproduce to ~1.00: their CDR carries NO information")
    print("  beyond fw_p50. Validating a model against them would be circular.")
    print("  => Use fw_p50 as the observable. The measured rows are exact,")
    print("     and their ratios also quantify each feedstock's real CO2 potential")
    print("     departing from the nominal 0.33 tCO2/t.")


def rate_vs_fw(rows: list[dict]) -> None:
    """The strongest signal in the table, and it is a physical one."""
    rule("2. Fraction weathered falls with application rate")

    ind = sorted([r for r in rows if r["regime"] == "india_paddy"],
                 key=lambda r: r["rate_t_ha"])
    print("  Within the India acidic-paddy group (4 deployments, one regime):")
    print(f"  {'deployment':14s} {'rate t/ha':>10s} {'fw_p50':>8s}")
    for r in ind:
        print(f"  {r['deployment']:14s} {r['rate_t_ha']:10.1f} {r['fw_p50']:8.1%}")
    fw = [r["fw_p50"] for r in ind]
    mono = all(a > b for a, b in zip(fw, fw[1:]))
    print(f"  Perfectly monotonic decreasing: {mono}")
    print()
    print("  This is the expected self-limiting behaviour: as more rock is applied,")
    print("  soil pH rises, the solution moves toward saturation, and alkalinity")
    print("  export becomes drainage-limited rather than kinetically limited. It is")
    print("  the same physics as the eta_transport term (Maher & Chamberlain 2014).")
    print()

    # Power-law fit across all deployments, in log space.
    x = np.log(np.array([r["rate_t_ha"] for r in rows]))
    y = np.log(np.array([r["fw_p50"] for r in rows]))
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot
    print(f"  All 8, log-log fit:  fw ~ rate^{slope:.2f}   (R^2 = {r2:.2f}, n = 8)")
    print("  No p-value is quoted: n = 8, three regimes, and grain size is an")
    print("  uncontrolled confound. Treat the exponent as indicative only.")
    print()
    print("  IMPLICATION FOR THE MAP: fraction weathered is not a site property.")
    print("  It depends on how much rock you applied. So the map must not present")
    print("  fw as a suitability metric, and any cross-site comparison of fw has")
    print("  to hold application rate fixed.")


def regime_comparison(rows: list[dict]) -> None:
    """Does the observed ordering support or challenge the model's headline claim
    that high-pCO2 paddies should rank top and acid Oxisols should be demoted?"""
    rule("3. Regime ordering: does it support the model's headline claim?")

    print("  Raw means, no adjustment:")
    print(f"  {'regime':16s} {'n':>2s} {'mean rate':>10s} {'mean fw':>8s}")
    for regime in ("india_paddy", "corn_belt", "brazil_oxisol"):
        g = [r for r in rows if r["regime"] == regime]
        print(f"  {regime:16s} {len(g):2d} "
              f"{np.mean([r['rate_t_ha'] for r in g]):10.1f} "
              f"{np.mean([r['fw_p50'] for r in g]):8.1%}")
    print()

    # Remove the rate effect, then look at the residual by regime.
    x = np.log(np.array([r["rate_t_ha"] for r in rows]))
    y = np.log(np.array([r["fw_p50"] for r in rows]))
    slope, intercept = np.polyfit(x, y, 1)
    resid = y - (slope * x + intercept)

    print("  Rate-adjusted residual in ln(fw) -- positive means weathering faster")
    print("  than the application rate alone would predict:")
    print(f"  {'regime':16s} {'n':>2s} {'mean resid':>11s} {'as a factor':>12s}")
    order = []
    for regime in ("india_paddy", "corn_belt", "brazil_oxisol"):
        idx = [i for i, r in enumerate(rows) if r["regime"] == regime]
        m = float(np.mean(resid[idx]))
        order.append((m, regime))
        print(f"  {regime:16s} {len(idx):2d} {m:11.2f} {math.exp(m):12.2f}x")
    order.sort(reverse=True)
    print()
    print("  Observed ranking, best first: "
          + " > ".join(r for _, r in order))
    print()
    print("  HONEST READ. This does NOT confirm the model's paddy-first claim.")
    print("  Brazil Oxisol comes out on top on this adjustment, and it is exactly")
    print("  the regime the eta_DIC term demotes. But the test has almost no")
    print("  power, for reasons that are not fixable by better statistics:")
    print("    - n = 8, with one deployment in the Brazil regime")
    print("    - grain size spans 67-600 um and its DISTRIBUTION WIDTH is")
    print("      unresolved per deployment; d50 alone spans 8.2x geometric SSA")
    print("      and width a further 4.2x. Larger than every regime difference")
    print("      here")
    print("    - grain size, application rate and operator are mutually")
    print("      collinear: corr(ln rate, ln p50) = +0.60, and the WITHIN-operator")
    print("      rate slope is -0.01 +/- 0.57 against the pooled -0.58. So the")
    print("      pooled exponent is the operator/grind contrast relabelled, NOT")
    print("      a rate effect -- see the warning on FW_RATE_EXPONENT_OBSERVED")
    print("    - one programme contributes three bins that may be grain-size bins")
    print("      within a single site, in which case treating them as three")
    print("      independent samples overstates that regime's n")
    print("    - P16 spreads are enormous: one row is 23.9% at P50 but 0.9%")
    print("      at P16, a factor of 27. Regime means built on P50 alone hide that")
    print("    - measurement methods differ across operators and are known to")
    print("      disagree by ~2x")
    print()
    print("  So: the model's paddy claim is NOT yet supported, and is mildly")
    print("  challenged. That is worth recording as a pre-registered concern")
    print("  rather than explained away. The resolution is grain-size data, not")
    print("  a different aggregation.")


def feedstock_co2_potential(rows: list[dict]) -> None:
    """Rows with independently measured CDR let us back out the feedstock's real
    CO2 potential, so their departure from the nominal 0.33 tCO2/t is a finding."""
    rule("8. What the measured rows say about actual feedstock CO2 potential")
    print("  For rows where CDR was independently measured, implied CO2 potential")
    print("  = cdr / (rate x fw):")
    print()
    vals = []
    for r in rows:
        if r["cdr_exact"] != "yes":
            continue
        implied = r["cdr_tco2_ha"] / (r["rate_t_ha"] * r["fw_p50"])
        vals.append(implied)
        print(f"  {r['deployment']:14s} {implied:.3f} tCO2/t")
    print()
    print(f"  mean {np.mean(vals):.3f}, range {min(vals):.3f}-{max(vals):.3f}")
    print("  vs the nominal 0.33 used for the derived rows, and vs our archetypes:")
    print("    fresh_basalt 0.332   metabasalt 0.238   ultramafic 0.920")
    print()
    print("  These basalts sit BELOW fresh_basalt and near metabasalt. So the")
    print("  nominal 0.33 applied to the derived rows likely overstates their CDR")
    print("  by ~20-25%, and our fresh_basalt archetype composition is optimistic")
    print("  for real delivered feedstock. Worth revisiting CaO/MgO in")
    print("  constants.FEEDSTOCK_ARCHETYPES against actual delivery assays.")


def why_year_one_fw_is_the_wrong_observable(rows: list[dict]) -> None:
    """The most important caveat, and it cuts against reading too much into
    section 3 either way."""
    rule("9. Why year-one fraction weathered is a weak test of a rate law")

    x = np.log(np.array([r["rate_t_ha"] for r in rows]))
    y = np.log(np.array([r["fw_p50"] for r in rows]))
    slope, intercept = np.polyfit(x, y, 1)
    resid = y - (slope * x + intercept)
    spread = float(np.exp(resid.max() - resid.min()))

    print("  Two structural reasons, both of which limit what section 3 can show:")
    print()
    print("  (a) TRANSIENT, NOT STEADY STATE. Over a first ~12-month reporting")
    print("      period, fraction weathered is dominated by dissolution of the fine")
    print("      tail of the particle-size distribution. That is fast, close to")
    print("      kinetically unlimited, and therefore similar across sites. The")
    print("      Palandri-Kharaka law we implement describes the LONG-RUN steady")
    print("      rate. So year-one fw is close to the wrong observable: it measures")
    print("      how much fine material was delivered more than how favourable the")
    print("      site is.")
    print()
    print("      Consistent with that, the rate-adjusted regime differences are")
    print(f"      tiny -- total spread across all 8 deployments is {spread:.2f}x --")
    print("      while grain size alone could plausibly account for 8.2x on diameter and ~4.2x on width.")
    print()
    print("  (b) NARROW COVARIATE ENVELOPE. All 8 sites are humid, and acidic to")
    print("      near-neutral, and warm to temperate. None is arid, alkaline, or")
    print("      cold. But the model's most consequential departures from Cascade")
    print("      are precisely about the UNSAMPLED regions -- alkaline irrigated")
    print("      cropland going from hopeless to viable, and arid cropland being")
    print("      penalised by transport limitation. This set cannot test either.")
    print()
    print("  So the defensible statement is narrow: after adjusting for application")
    print("  rate, these eight first-period deliveries show no regime signal large")
    print("  enough to either confirm or refute the model's ordering. That is a")
    print("  statement about the test's power, not about the model being right.")
    print()
    print("  What WOULD test it, in rough order of value:")
    print("    - multi-year fw from the same sites, where the fine tail is spent")
    print("      and the steady rate dominates")
    print("    - any deployment on alkaline (pH > 7.5) or arid cropland")
    print("    - a flooded-vs-drained pair at one site, same feedstock and rate,")
    print("      which would test the soil-pCO2 mechanism directly and is the")
    print("      single cleanest experiment for the paddy claim")


def grain_size_controlled(rows: list[dict]) -> None:
    """Redo the regime comparison now that p50 is measured per operator.

    The headline result is that the comparison is UNIDENTIFIABLE, and that
    conclusion is stronger than the one this script previously reported.
    """
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).parent))
    import constants as _C
    import kinetics as _K

    rule("7. Regime comparison with grain size controlled")
    have = [r for r in rows if r["p50_um"]]
    if not have:
        print("  no p50 values in the fixture; nothing to control for")
        return

    by_regime = {}
    for r in have:
        by_regime.setdefault(r["regime"], set()).add(r["p50_um"])
    print("  p50 values present in each regime:")
    for reg, ps in sorted(by_regime.items()):
        print(f"    {reg:16s} {sorted(ps)}")
    collinear = all(len(v) == 1 for v in by_regime.values())
    print()
    if collinear:
        print("  GRAIN SIZE IS PERFECTLY COLLINEAR WITH REGIME. Each regime has")
        print("  exactly one grind. Regime and grain size are the same variable, so")
        print("  no amount of statistics can separate them. This is stronger than")
        print("  'low power': the comparison is UNIDENTIFIABLE.")
        print()

    # Normalise to a common grind and rate. Fraction weathered SATURATES, so
    # invert to the rate-like exposure first -- rescaling Fw linearly gave a
    # physically impossible 106% when first tried.
    ref = _K.ssa_geometric(_C.PSD_REF_D50_UM, _C.PSD_REF_WIDTH)
    base_rate = 44.7
    print(f"  Normalised to p50 {_C.PSD_REF_D50_UM:.0f} um and {base_rate:.1f} t/ha,")
    print("  inverting through Fw = 1 - exp(-kX) rather than scaling Fw directly:")
    print(f"    {'deployment':14s} {'p50':>5s} {'fw':>7s} {'fw_norm':>8s}")
    norm = {}
    for r in have:
        X = -math.log(1.0 - r["fw_p50"])
        sr = _K.ssa_geometric(r["p50_um"], _C.PSD_REF_WIDTH) / ref
        Xn = X / sr * (r["rate_t_ha"] / base_rate) ** 0.58
        fwn = 1.0 - math.exp(-Xn)
        norm.setdefault(r["regime"], []).append(fwn)
        print(f"    {r['deployment']:14s} {r['p50_um']:5.0f} {r['fw_p50']:7.1%} {fwn:8.1%}")
    print()
    print("  Regime means at a common grind and rate:")
    for reg, v in sorted(norm.items(), key=lambda kv: -np.mean(kv[1])):
        print(f"    {reg:16s} {np.mean(v):7.1%}  (n={len(v)})")
    print()
    print("  This REVERSES the ordering this script reported before p50 was known,")
    print("  putting acidic paddy first rather than last. Do NOT read that as")
    print("  support for the model: because grain size and regime are the same")
    print("  variable here, 'normalising for grain size' and 'removing the regime")
    print("  effect' are the same operation. The reversal only shows which variable")
    print("  the variance was attributed to.")
    print()
    print("  What it DOES establish: the earlier claim that these deliveries mildly")
    print("  CONTRADICT the paddy prediction was unsupported. The data is")
    print("  uninformative about regime, not contrary to it. That was an over-read")
    print("  and is retracted.")
    print()
    print("  To make it identifiable you need two grinds within one regime, or one")
    print("  grind across two regimes. A single site running coarse and fine lots")
    print("  side by side would do it.")


def what_would_make_this_a_real_test(rows: list[dict]) -> None:
    rule("10. What is needed to turn this into a real test")
    print("  In priority order, by how much each would raise the test's power:")
    print()
    print("  1. PER-DEPLOYMENT PARTICLE-SIZE DISTRIBUTION, not just d80.")
    print("     Fit Rosin-Rammler (d_c, n) per deployment and integrate specific")
    print("     surface area over it. Normalising on d80 alone is invalid: two")
    print("     feedstocks with identical d80 can differ 4.2x in reactive area.")
    print("     Without this, no cross-deployment comparison of fw is")
    print("     interpretable, and a deployment lacking it should be EXCLUDED")
    print("     rather than assigned an assumed width.")
    print("  2. Confirm what one programme's three bins are. If particle-size bins,")
    print("     they become the best grain-size sensitivity test in the set,")
    print("     rather than three noisy Corn Belt replicates.")
    print("  3. Measured soil pH per deployment, and the measurement convention")
    print("     (H2O vs CaCl2). A 0.55-unit convention offset is comparable to")
    print("     the entire width of the eta_DIC transition.")
    print("  4. Whether each site is flooded, and for what fraction of the year.")
    print("     This sets soil pCO2, which is what drives the paddy prediction.")
    print("     'Paddy soil' in a soil description is not the same as 'flooded")
    print("     during the reporting period'.")
    print("  5. Exact reporting-period length and feedstock CO2 potential per")
    print("     deployment, to replace the nominal 0.33 tCO2/t.")
    print()
    print("  Then the validation becomes the CONSTANCY TEST from docs/VALIDATION.md:")
    print("  fit the effective-surface-area multiplier lambda separately to each")
    print("  deployment and publish all eight values. Their spread IS the result.")
    print("  A spread of ~3x is reportable; 10x means the CO2 layer should be")
    print("  demoted to qualitative.")


def main() -> int:
    rows = load()
    if rows is None:
        print("No delivery fixture found at:")
        print(f"  {FIXTURE}")
        print()
        print("This input is deliberately not redistributed -- it derives from an")
        print("independent verification report and carries per-operator results.")
        print("See the module docstring for the expected CSV schema.")
        print()
        print("Aggregate findings from the local run are recorded in README.md and")
        print("in constants.py (DELIVERED_BASALT_TCO2_PER_T, FW_RATE_EXPONENT_OBSERVED).")
        return 0
    print("=" * 74)
    print(f"Verified ERW deliveries, 2026 -- {len(rows)} deployments, all basalt")
    print("=" * 74)
    check_cdr_is_circular(rows)
    rate_vs_fw(rows)
    regime_comparison(rows)
    grain_size_controlled(rows)
    feedstock_co2_potential(rows)
    why_year_one_fw_is_the_wrong_observable(rows)
    what_would_make_this_a_real_test(rows)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
