"""
What the verified deliveries can and cannot tell us -- and the calibration
they set.

  python3 scripts/analyse_deployments.py

INPUT DATA IS NOT IN THIS REPOSITORY. This reads a cross-supplier calibration
dataset (deliveries.csv, feedstock.csv) assembled from supplier bundles, project
design documents and verification reports. It carries per-supplier results that
are not ours to publish, so it is gitignored. The script exits with the expected
schema if the files are absent, so the method stays reviewable even though the
inputs are not redistributed. ONLY CROSS-SUPPLIER AGGREGATES leave this script:
the constants it prints at the end are medians, ranges and counts, never a
supplier's own number.

To reproduce, supply calibration_data/calibration/deliveries.csv with (at least)
the columns:
    delivery_slug, company, country, region, tracer, app_rate_t_ha,
    elapsed_days, elapsed_src, fw_p50_pct, fw_p16_pct, fw_p84_pct,
    fw_is_cumulative, latitude, longitude, coord_src, crop, sampling_depth_cm,
    porewater_ph, porewater_alkalinity_ueq_l
and calibration_data/calibration/feedstock.csv with:
    company, ca_mg_kg, mg_mg_kg, na_mg_kg, k_mg_kg, p50_um, p50_src
and, optionally, fields.csv with delivery_slug, field_id (used only to
recognise a later re-sampling of the same fields).
fw_* are percent of MEASURED rock addition weathered (not of applied mass);
elapsed_days is the weathering duration the fraction refers to, blank where it is
not recoverable; fw_is_cumulative marks a second sampling of the same fields;
coord_src distinguishes measured/field-scale coordinates from a regional guess
(`approximate_region_centroid`), which this script refuses to join to the grid.

Sections, in the order they are needed:
  1. Inventory and provenance -- which rows can carry a rate at all.
  2. Time-normalisation to one year through the model's own shrinking-core
     shape (d50-free, width-dependent), bracketed where the shape is known to
     be wrong.
  3. The one longitudinal constraint in the set: the rate falls far faster
     than shrinking core at ANY Rosin-Rammler width predicts.
  4. Feedstock CO2 potential on the map's Ca+Mg basis -> DELIVERED_BASALT_*.
  5. Site- and grind-conditioned dissolution multipliers (the pre-registered
     constancy test of docs/VALIDATION.md) -> DISSOLVED_FRAC_AT_REF and the
     supplier-cluster spread the country ensemble samples.
  6. Rate exponent, pooled versus within-supplier (still confounded; not used).
  7. Porewater pH + alkalinity -> implied in-situ soil pCO2, the first field
     constraint on the paddy pCO2 assumption.
  8. Does dissolution-based CDR fit in the drainage water?
  9. What is not identifiable, and what would make it so.

Run it and read the output rather than taking the docstring on trust.
"""

from __future__ import annotations

import csv
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import constants as C  # noqa: E402
import kinetics as K  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CALIB = ROOT / "calibration_data/calibration"
DELIVERIES = CALIB / "deliveries.csv"
FEEDSTOCK = CALIB / "feedstock.csv"
FIELDS = CALIB / "fields.csv"          # optional; identifies re-sampled fields
NPZ = ROOT / "data/processed/v0_layers.npz"

# Regions a delivery may be attributed to when it shares no per-location
# coordinates. Boxes are cropland-weighted at lookup; the median X inside them is
# a REGIONAL value and is flagged as such wherever it is used. Keyed by the
# dataset's own `region` string.
REGION_BOXES = {
    "Southern Brazil (PR/SP/MS/GO)": (-26.5, -15.0, -56.0, -45.0),
}

# Deliveries observed for less than this are too short for a one-year
# extrapolation to be trusted on any single curve shape; they enter the anchor
# as a BRACKET (raw lower bound, shrinking-core upper bound) and their central
# value is the geometric midpoint. See section 3 for why.
SHORT_OBSERVATION_DAYS = 300.0


# ---------------------------------------------------------------------------
def _f(v):
    try:
        return float(v) if v not in ("", None) else None
    except ValueError:
        return None


def load():
    if not (DELIVERIES.exists() and FEEDSTOCK.exists()):
        return None, None
    with DELIVERIES.open() as fh:
        rows = list(csv.DictReader(fh))
    with FEEDSTOCK.open() as fh:
        feed = list(csv.DictReader(fh))
    for r in rows:
        for k in ("app_rate_t_ha", "elapsed_days", "fw_p50_pct", "fw_p16_pct",
                  "fw_p84_pct", "latitude", "longitude", "sampling_depth_cm",
                  "porewater_ph", "porewater_alkalinity_ueq_l"):
            r[k] = _f(r.get(k))
        r["fw_is_cumulative"] = str(r.get("fw_is_cumulative", "")).lower() == "true"
    for f in feed:
        for k in ("ca_mg_kg", "mg_mg_kg", "na_mg_kg", "k_mg_kg", "p50_um"):
            f[k] = _f(f.get(k))
    return rows, feed


def rule(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


# ---- dissolution-shape helpers ---------------------------------------------
_UG = np.concatenate([[0.0], np.geomspace(1e-5, 200.0, 1500)])
_GG = {}


def _table(n):
    if n not in _GG:
        _GG[n] = np.concatenate([[0.0], K.dissolved_fraction(_UG[1:], n)])
    return _GG[n]


def G(u, n=None):
    n = C.PSD_REF_WIDTH if n is None else n
    return float(np.interp(u, _UG, _table(n)))


def u_of(fw, n=None):
    n = C.PSD_REF_WIDTH if n is None else n
    return float(np.interp(min(max(fw, 0.0), 0.999), _table(n), _UG))


def fw_at_days(fw, t_obs, t_new, n=None):
    """Move an observed fraction from t_obs to t_new along the shrinking-core
    curve. Retreat is linear in time, so u scales with t; d50 cancels."""
    return G(u_of(fw, n) * t_new / t_obs, n)


# ---- grid helpers ----------------------------------------------------------
class Grid:
    def __init__(self):
        self.ok = NPZ.exists()
        if not self.ok:
            return
        z = np.load(NPZ, allow_pickle=True)
        self.z = z
        self.a, _, self.c, _, self.e, self.f = z["transform"]
        self.keys = ("L1", "eta_tr", "eta", "q", "ph", "tair", "pco2",
                     "f_flood", "alk_ceiling", "ceiling")

    def at(self, lat, lon, hw=1):
        """Median over cropland cells in a (2hw+1)^2 window; hw=1 is ~33 km."""
        z = self.z
        row = int(math.floor((lat - self.f) / self.e))
        col = int(math.floor((lon - self.c) / self.a))
        sl = np.s_[max(row - hw, 0):row + hw + 1, max(col - hw, 0):col + hw + 1]
        m = ((z["crop"][sl] >= C.CROPLAND_MIN_FRACTION)
             & np.isfinite(z["L1"][sl]) & np.isfinite(z["ph"][sl]))
        if not m.any():
            return None
        out = {k: float(np.nanmedian(z[k][sl][m])) for k in self.keys}
        out["n"] = int(m.sum())
        out["X"] = 10.0 ** out["L1"] * out["eta_tr"]
        return out

    def region(self, box):
        z = self.z
        lat0, lat1, lon0, lon1 = box
        r0 = int(math.floor((lat1 - self.f) / self.e))
        r1 = int(math.floor((lat0 - self.f) / self.e))
        c0 = int(math.floor((lon0 - self.c) / self.a))
        c1 = int(math.floor((lon1 - self.c) / self.a))
        sl = np.s_[r0:r1 + 1, c0:c1 + 1]
        m = (z["crop"][sl] >= C.CROPLAND_MIN_FRACTION) & np.isfinite(z["L1"][sl])
        X = (10.0 ** z["L1"][sl][m]) * z["eta_tr"][sl][m]
        w = (z["crop"][sl] * z["area"][sl])[m]
        o = np.argsort(X)
        cw = np.cumsum(w[o]) / w.sum()
        q = lambda p: float(X[o][min(np.searchsorted(cw, p), len(o) - 1)])
        out = {k: float(np.nanmedian(z[k][sl][m])) for k in self.keys}
        out.update(n=int(m.sum()), X=q(0.5), X_p25=q(0.25), X_p75=q(0.75))
        return out


# ---------------------------------------------------------------------------
def inventory(rows, feed):
    rule("1. Inventory and provenance")
    comps = sorted({r["company"] for r in rows})
    print(f"  {len(rows)} removals/deployments across {len(comps)} suppliers, "
          f"{len({r['country'] for r in rows})} countries.")
    print()
    print(f"  {'delivery':28s} {'tracer':>6s} {'t/ha':>6s} {'days':>5s} "
          f"{'elapsed':>9s} {'Fw p50':>7s} {'coords':>34s}")
    for r in rows:
        tr = "none" if r["tracer"].startswith("none") else r["tracer"][:6]
        el = f"{r['elapsed_days']:5.0f}" if r["elapsed_days"] else "    -"
        print(f"  {r['delivery_slug']:28s} {tr:>6s} {r['app_rate_t_ha']:6.1f} {el} "
              f"{(r['elapsed_src'] or '-'):>9s} {r['fw_p50_pct']:6.1f}% "
              f"{r['coord_src']:>34s}")
    no_t = [r for r in rows if r["elapsed_days"] is None]
    cum = [r for r in rows if r["fw_is_cumulative"]]
    print()
    print(f"  {len(no_t)} rows have NO recoverable weathering duration and cannot "
          f"carry a rate;")
    print(f"  {len(cum)} row is a CUMULATIVE re-sampling of fields already in the set;")
    print(f"  {sum(1 for r in rows if r['elapsed_src'] == 'measured')} rows have "
          f"elapsed time measured from sample dates, the rest stated or inferred.")
    print(f"  Grind (p50) is disclosed for "
          f"{sum(1 for f in feed if f['p50_um'])} of {len(feed)} suppliers; "
          f"no supplier has a PSD curve or a measured surface area.")
    print()
    print("  Two observables masquerade as one: suppliers without an immobile")
    print("  tracer establish the Fw denominator from the pre/post soil cation")
    print("  jump; tracer suppliers infer it from Ti or Cu. Sampling depth also")
    print("  differs where it is known at all. Neither is corrected below; both")
    print("  are nested in supplier, which is why every aggregate here is taken")
    print("  over SUPPLIER CLUSTERS rather than over rows.")


def field_ids():
    """delivery_slug -> set of field ids, from fields.csv (optional)."""
    out = {}
    if not FIELDS.exists():
        return out
    with FIELDS.open() as fh:
        for r in csv.DictReader(fh):
            out.setdefault(r["delivery_slug"], set()).add(r["field_id"])
    return out


def usable_rows(rows):
    """Rows that can carry a year-1 rate: a duration exists, and the row is not
    the superseded first sampling of fields re-sampled later. 'Same fields' is
    decided from field ids, not from region and rate -- two deliveries from one
    supplier can share both and still be different land."""
    ids = field_ids()
    pred = set()
    for c in [r for r in rows if r["fw_is_cumulative"]]:
        for r in rows:
            if (r is c or r["fw_is_cumulative"] or not r["elapsed_days"]
                    or not c["elapsed_days"]
                    or r["elapsed_days"] >= c["elapsed_days"]):
                continue
            a, b = ids.get(r["delivery_slug"]), ids.get(c["delivery_slug"])
            if a and b and len(a & b) / len(a) > 0.5:
                pred.add(r["delivery_slug"])
    if not ids:
        print("  WARNING: fields.csv absent; cannot identify re-sampled fields, so "
              "no early sampling is excluded")
    out = [r for r in rows if r["elapsed_days"] and r["delivery_slug"] not in pred]
    return out, pred


def time_normalise(rows):
    rule("2. Time-normalisation to one year")
    print("  Fw is observed at 93-429 d, not at one year. Moved to 365 d along the")
    print("  model's own shrinking-core curve (u scales with time; d50 cancels, only")
    print("  the width enters). RAW is a lower bound on the one-year value where")
    print("  t < 365 d; the shrinking-core value is an UPPER bound because section 3")
    print("  shows the real curve flattens faster. Central = geometric midpoint.")
    print()
    print(f"  {'delivery':28s} {'days':>5s} {'raw':>6s} {'n=0.9':>6s} "
          f"{'n=1.5':>6s} {'n=2.3':>6s} {'central':>8s}")
    for r in rows:
        t = r["elapsed_days"]
        fw = r["fw_p50_pct"] / 100.0
        vals = {n: fw_at_days(fw, t, 365.0, n) for n in (0.9, 1.5, 2.3)}
        sc = vals[C.PSD_REF_WIDTH]
        lo, hi = (min(fw, sc), max(fw, sc))
        r["fw365_raw"], r["fw365_sc"] = fw, sc
        r["fw365"] = math.sqrt(lo * hi) if t < SHORT_OBSERVATION_DAYS else sc
        r["fw365_lo"], r["fw365_hi"] = lo, hi
        print(f"  {r['delivery_slug']:28s} {t:5.0f} {fw:6.1%} {vals[0.9]:6.1%} "
              f"{vals[1.5]:6.1%} {vals[2.3]:6.1%} {r['fw365']:8.1%}"
              + ("  <- bracketed" if t < SHORT_OBSERVATION_DAYS else ""))
    fws = sorted(r["fw365"] for r in rows)
    print()
    print(f"  One-year fraction weathered, each at its OWN grind, rate and site: "
          f"{fws[0]:.1%}-{fws[-1]:.1%}, median {np.median(fws):.1%} (n = {len(fws)}).")
    print("  This is the legend's 'measured spread'. It is NOT the anchor: none of")
    print("  these sits at the reference grind or the reference condition.")
    return fws


def longitudinal_shape_test(rows, pred):
    rule("3. The one longitudinal constraint: does the shape decay fast enough?")
    cums = [r for r in rows if r["fw_is_cumulative"]]
    if not cums or not pred:
        print("  no cumulative re-sampling in the set; skipped")
        return
    c = cums[0]
    p = next(r for r in rows if r["delivery_slug"] in pred
             and r["company"] == c["company"])
    f1, t1 = p["fw_p50_pct"] / 100.0, p["elapsed_days"]
    f2, t2 = c["fw_p50_pct"] / 100.0, c["elapsed_days"]
    r_early = f1 / t1
    r_late = (f2 - f1) / (t2 - t1)
    print(f"  Same fields sampled twice: {f1:.1%} at {t1:.0f} d, then {f2:.1%} "
          f"cumulative at {t2:.0f} d.")
    print(f"  Mean rate {r_early * 100:.3f} pp/d over the first interval, "
          f"{r_late * 100:.3f} pp/d over the second: {r_late / r_early:.0%} of "
          f"the initial rate.")
    print()
    print(f"  Predicted second value from the first, per curve shape:")
    for n in (0.5, 0.7, 1.0, 1.5, 2.5):
        print(f"    shrinking core, width {n:3.1f}: {fw_at_days(f1, t1, t2, n):5.1%}")
    k1 = -math.log(1 - f1) / t1
    print(f"    first-order exponential   : {1 - math.exp(-k1 * t2):5.1%}")
    print(f"    OBSERVED                  : {f2:5.1%}")
    print()
    print("  No Rosin-Rammler width reproduces the decline, and first-order is worse.")
    print("  The first interval's duration is INFERRED, not measured, so test its")
    print("  leverage: the shrinking-core prediction at width "
          f"{C.PSD_REF_WIDTH} matches the observation only if the first sampling was")
    for t1_alt in (t1, 150.0, 180.0, 210.0):
        print(f"    at {t1_alt:3.0f} d -> {fw_at_days(f1, t1_alt, t2):5.1%}")
    outp = ROOT / "paper/calibration_shape.json"
    if outp.parent.exists():
        import json as _json
        outp.write_text(_json.dumps(dict(
            t1_days=t1, fw1=round(f1, 4), t2_days=t2, fw2=round(f2, 4),
            predictions={str(n): round(fw_at_days(f1, t1, t2, n), 4)
                         for n in (0.5, 0.7, 1.0, 1.5, 2.5)},
            first_order=round(1 - math.exp(-k1 * t2), 4),
            t1_alternatives={str(t): round(fw_at_days(f1, t, t2), 4)
                             for t in (t1, 150.0, 180.0, 210.0)},
            note="one re-sampled field, cluster-level; duration of the first "
                 "interval is inferred, not measured"), indent=1))
    print("  i.e. roughly twice as late as stated. Either the duration is wrong by")
    print("  ~2x or a reactive fine/glassy fraction is consumed faster than any")
    print("  size distribution alone implies. Both are live; the dataset cannot")
    print("  separate them. Consequence for calibration: one-year values")
    print(f"  extrapolated from observations shorter than {SHORT_OBSERVATION_DAYS:.0f} d")
    print("  are BRACKETED, not trusted, and the early sampling of a re-sampled")
    print("  field is excluded from the anchor in favour of the later one.")
    return r_late


def co2_potential(feed):
    rule("4. Feedstock CO2 potential on the map's Ca+Mg basis")
    print("  The archetype counts Ca and Mg only (2 mol CO2 per mol). Certified")
    print("  potentials that also count Na and K are NOT like-for-like, so every")
    print("  supplier is recomputed from its own feedstock chemistry on one basis.")
    print()
    vals = []
    for f in feed:
        if f["ca_mg_kg"] is None or f["mg_mg_kg"] is None:
            print(f"  {f['company']:12s} Ca/Mg chemistry blank in feedstock.csv -- "
                  f"cannot enter the mean (a gap in the dataset, not a measurement)")
            continue
        ca = f["ca_mg_kg"] / 1000.0 / 40.078
        mg = f["mg_mg_kg"] / 1000.0 / 24.305
        camg = 2.0 * (ca + mg) * C.M_CO2_G_MOL / 1000.0
        extra = ""
        if f["na_mg_kg"] is not None:
            na = f["na_mg_kg"] / 1000.0 / 22.990
            kk = (f["k_mg_kg"] or 0.0) / 1000.0 / 39.098
            allb = (2.0 * (ca + mg) + na + kk) * C.M_CO2_G_MOL / 1000.0
            extra = f"   (+Na+K basis {allb:.3f}, +{allb / camg - 1:.0%})"
        vals.append(camg)
        print(f"  {f['company']:12s} Ca+Mg basis {camg:.3f} tCO2/t{extra}")
    spec = C.FEEDSTOCK_ARCHETYPES["delivered_basalt"]
    ours = ((spec["CaO_wt"] / C.M_CAO + spec["MgO_wt"] / C.M_MGO)
            * 1000.0 * 2.0 * C.MOL_CO2_PER_KMOL_CHARGE_T)
    mean = float(np.mean(vals))
    print()
    print(f"  Supplier mean {mean:.3f} tCO2/t, range {min(vals):.3f}-{max(vals):.3f} "
          f"(n = {len(vals)} suppliers, each one vote).")
    print(f"  delivered_basalt archetype: {ours:.4f}; constant "
          f"DELIVERED_BASALT_TCO2_PER_T = {C.DELIVERED_BASALT_TCO2_PER_T}"
          f" ({ours / mean - 1:+.1%} vs this mean)")
    print("  Counting Na and K, as the protocols do, would add roughly a tenth for")
    print("  the feedstocks that report them; the map's Ca+Mg basis is the")
    print("  conservative one and is kept.")
    return mean, (min(vals), max(vals)), len(vals)


def constancy_test(rows, feed, grid):
    rule("5. Site- and grind-conditioned dissolution multipliers (constancy test)")
    if not grid.ok:
        print("  SKIP: data/processed/v0_layers.npz missing; run scripts/build_v0.py")
        return None
    p50 = {f["company"]: f["p50_um"] for f in feed}
    d_ref = K.retreat_at_reference()
    u_ref = d_ref / C.PSD_REF_D50_UM
    print("  For each delivery: the map's own dimensionless rate X = 10^L1 x eta_tr")
    print("  at the delivery's cells (3x3 cropland median, ~33 km), the model's")
    print("  predicted one-year fraction at the SUPPLIER'S grind under the shipped")
    print("  anchor, and the multiplier k on the reference retreat that would make")
    print("  the model reproduce the observation:  k = u_obs / (delta_ref x X / d50).")
    print("  k = 1 means the shipped anchor is right for that delivery.")
    print()
    print(f"  {'delivery':28s} {'X':>5s} {'d50':>5s} {'model':>6s} {'obs':>6s} "
          f"{'k_lo':>6s} {'k':>6s} {'k_hi':>6s}  note")
    recs = []
    for r in rows:
        if r["coord_src"] == "approximate_region_centroid":
            box = REGION_BOXES.get(r["region"])
            if box is None:
                print(f"  {r['delivery_slug']:28s} no usable coordinates and no region "
                      f"box; skipped")
                continue
            g = grid.region(box)
            note = f"REGIONAL X (IQR {g['X_p25']:.2f}-{g['X_p75']:.2f}, {g['n']} cells)"
        else:
            g = grid.at(r["latitude"], r["longitude"], hw=1)
            if g is None:
                print(f"  {r['delivery_slug']:28s} no cropland cells at coordinates; skipped")
                continue
            note = f"{r['coord_src']}"
        X = g["X"]
        d50 = p50.get(r["company"])
        rec = dict(slug=r["delivery_slug"], company=r["company"], X=X, g=g,
                   grind_known=d50 is not None, rate=r["app_rate_t_ha"])
        for tag, d in (("known", d50),) if d50 else (("ref", C.PSD_REF_D50_UM),):
            u_model = d_ref * X / d
            rec["k_lo"] = u_of(r["fw365_lo"]) / u_model
            rec["k_hi"] = u_of(r["fw365_hi"]) / u_model
            rec["k"] = u_of(r["fw365"]) / u_model
            rec["fw_model"] = G(u_model)
            rec["d50"] = d
        recs.append(rec)
        gn = f"{rec['d50']:5.0f}" if d50 else "  ?  "
        print(f"  {rec['slug']:28s} {X:5.2f} {gn} {rec['fw_model']:6.1%} "
              f"{r['fw365']:6.1%} {rec['k_lo']:6.3f} {rec['k']:6.3f} {rec['k_hi']:6.3f}"
              f"  {note}" + ("" if d50 else "; grind UNKNOWN -> k at reference grind "
                                             "is an UPPER BOUND"))
    print()
    # Cluster by supplier.
    clusters = {}
    for rec in recs:
        clusters.setdefault(rec["company"], []).append(rec)
    print("  Supplier clusters (median k over the supplier's usable rows; bracket =")
    print("  min k_lo to max k_hi):")
    cl = []
    for co, rs in clusters.items():
        k = float(np.median([x["k"] for x in rs]))
        lo = min(x["k_lo"] for x in rs)
        hi = max(x["k_hi"] for x in rs)
        known = all(x["grind_known"] for x in rs)
        cl.append(dict(company=co, k=k, lo=lo, hi=hi, known=known, n=len(rs),
                       d50=rs[0]["d50"]))
        print(f"    {co:12s} n={len(rs)}  d50 {rs[0]['d50']:4.0f} um  "
              f"k {k:.3f}  [{lo:.3f}, {hi:.3f}]"
              + ("" if known else "   (grind unknown; upper bound)"))
    known = [c for c in cl if c["known"]]
    k_star = float(np.median([c["k"] for c in known]))
    frac_ref = G(u_ref * k_star)
    print()
    print(f"  ANCHOR. Median k over the {len(known)} known-grind clusters = "
          f"{k_star:.3f}, i.e. the model at the reference condition and grind")
    print(f"  should weather {frac_ref:.1%} in year one, not "
          f"{C.DISSOLVED_FRAC_AT_REF:.0%} -- shipped constant "
          f"DISSOLVED_FRAC_AT_REF = {C.DISSOLVED_FRAC_AT_REF}"
          f" ({'CONSISTENT' if abs(C.DISSOLVED_FRAC_AT_REF - frac_ref) < 0.005 else 'STALE'}).")
    all_med = float(np.median([c["k"] for c in cl]))
    print(f"  Including the unknown-grind cluster at its upper bound: median k "
          f"{all_med:.3f} -> {G(u_ref * all_med):.1%}. The known-grind value is")
    print("  used because a bound is not an estimate, and because it is the")
    print("  conservative side of the two.")
    spread = max(c["k"] for c in known) / min(c["k"] for c in known)
    fr_lo = G(u_ref * min(c["k"] for c in known))
    fr_hi = G(u_ref * max(c["k"] for c in known))
    print()
    print(f"  SPREAD. Cluster k ranges {min(c['k'] for c in known):.3f}-"
          f"{max(c['k'] for c in known):.3f} ({spread:.1f}x); as reference-condition "
          f"year-1 fractions {fr_lo:.1%}-{fr_hi:.1%}.")
    print(f"  docs/VALIDATION.md pre-registered: ~3x reportable, 10x demotes the CO2")
    print(f"  layer to qualitative. {spread:.1f}x sits between. The spread is")
    print("  STRUCTURED, not noise: k rises with d50 across the clusters -- the")
    print("  finest grind is over-predicted several-fold and the coarsest is about")
    print("  right -- so the shrinking-core grind dependence (Fw ~ 1/d50 at small")
    print("  retreat) is too steep for these deliveries, OR the p50 values are not")
    print("  comparable (sieve vs laser, crusher fines with an unreported broad")
    print("  tail), OR tracer-free denominators and depth differences track grind")
    print("  because all three are nested in supplier. Width is the likeliest")
    print("  culprit and no PSD exists to test it. Reported, not tuned away.")
    # Structural alternative for the grind dependence (statistics review): under
    # the shipped Fw ~ d50^-1, k rises with d50. Removing the grind dependence
    # entirely (d50^0) maps k -> k * d50/d_ref and WIDENS the spread, so the data
    # favour an intermediate dependence. The fitted slope is one degree of
    # freedom on three clusters and is reported, not adopted.
    kd = [(c["k"], c["d50"]) for c in known]
    k0 = [k * d / C.PSD_REF_D50_UM for k, d in kd]
    slope = float(np.polyfit(np.log([d for _, d in kd]), np.log([k for k, _ in kd]), 1)[0])
    print(f"  GRIND DEPENDENCE. Shipped Fw ~ d50^-1: cluster spread {spread:.1f}x. "
          f"A d50-insensitive variant (d50^0) would give {max(k0) / min(k0):.0f}x. "
          f"ln k vs ln d50 slope {slope:.2f} (n = {len(kd)}, 1 df) implies "
          f"Fw ~ d50^{-(1 - slope):.2f}; not fitted (one-free-parameter budget).")
    within = [max(x["k"] for x in rs) / min(x["k"] for x in rs)
              for rs in clusters.values() if len(rs) > 1]
    print(f"  Within-supplier spread of k (same feedstock, method, climate): "
          f"{min(within):.1f}-{max(within):.1f}x.")
    # ---- robustness of the anchor to analyst choices (statistics review,
    # 2026-09-02): leave-one-cluster-out, the geometric mean, the bracketing
    # threshold, and the window size. Printed, and exported anonymised.
    print()
    print("  ROBUSTNESS of the anchor:")
    kk = sorted(c["k"] for c in known)
    loo = [G(u_ref * float(np.median([x for j, x in enumerate(kk) if j != i])))
           for i in range(len(kk))]
    print(f"    leave-one-cluster-out anchor: {min(loo):.3f}-{max(loo):.3f} "
          f"(shipped {frac_ref:.3f}); with n = {len(kk)} the median IS the middle "
          f"cluster, so the anchor rests on one supplier's rows.")
    print(f"    geometric mean of clusters: {G(u_ref * float(np.exp(np.mean(np.log(kk))))):.3f}")
    ts = sorted({r["elapsed_days"] for r in rows})
    near = [t for t in ts if SHORT_OBSERVATION_DAYS <= t < SHORT_OBSERVATION_DAYS + 30]
    if near:
        print(f"    rows observed at {near} d sit within 30 d of the "
              f"{SHORT_OBSERVATION_DAYS:.0f}-d bracketing threshold; raising the "
              f"threshold past them brackets the deciding cluster (see the "
              f"specification list below).")
    export = [dict(cluster=chr(65 + i), d50_um=c["d50"] if c["known"] else None,
                   grind_known=c["known"], n_rows=c["n"], k=round(c["k"], 3),
                   k_lo=round(c["lo"], 3), k_hi=round(c["hi"], 3),
                   frac_ref=round(G(u_ref * c["k"]), 4))
              for i, c in enumerate(sorted(cl, key=lambda c: (not c["known"], c["d50"] or 1e9)))]
    outp = ROOT / "paper/calibration_clusters.json"
    if outp.parent.exists():
        import json as _json
        outp.write_text(_json.dumps(dict(
            anchor=round(frac_ref, 4), k_star=round(k_star, 3),
            loo_range=[round(min(loo), 4), round(max(loo), 4)],
            with_unknown_grind=round(G(u_ref * all_med), 4),
            short_observation_days=SHORT_OBSERVATION_DAYS, clusters=export,
            note="anonymised supplier clusters; no name is paired with a value"),
            indent=1))
        print(f"    wrote anonymised cluster table -> {outp.relative_to(ROOT)}")
    return dict(k_star=k_star, frac_ref=frac_ref, cluster_frac_range=(fr_lo, fr_hi),
                spread=spread, n_known=len(known), n_clusters=len(cl),
                cl=cl, recs=recs, k_all=all_med, loo=(min(loo), max(loo)))


def rate_exponent(rows):
    rule("6. Rate exponent, pooled versus within-supplier (not used in the model)")
    x = np.log([r["app_rate_t_ha"] for r in rows])
    y = np.log([r["fw365"] for r in rows])
    s, b = np.polyfit(x, y, 1)
    r2 = 1 - np.sum((y - (s * x + b)) ** 2) / np.sum((y - y.mean()) ** 2)
    print(f"  Pooled log-log fit over {len(rows)} usable rows: fw ~ rate^{s:.2f} "
          f"(R2 {r2:.2f}).")
    # Within-supplier: demean by company, fit the pooled within slope.
    comps = sorted({r["company"] for r in rows})
    xw, yw = [], []
    for co in comps:
        idx = [i for i, r in enumerate(rows) if r["company"] == co]
        if len(idx) < 2 or np.ptp(x[idx]) < 1e-6:
            continue
        xw.extend(x[idx] - x[idx].mean())
        yw.extend(y[idx] - y[idx].mean())
    if len(xw) >= 3:
        xw, yw = np.array(xw), np.array(yw)
        sw = float(np.sum(xw * yw) / np.sum(xw * xw))
        res = yw - sw * xw
        se = float(np.sqrt(np.sum(res ** 2) / max(len(xw) - 2, 1) / np.sum(xw * xw)))
        print(f"  Within-supplier slope (only suppliers with >1 rate): {sw:.2f} "
              f"+/- {se:.2f}, on {len(xw)} rows.")
    n_rate_var = sum(1 for co in comps
                     if np.ptp([r["app_rate_t_ha"] for r in rows
                                if r["company"] == co]) > 1e-6)
    print(f"  Only {n_rate_var} of {len(comps)} suppliers vary application rate at all;")
    print("  rate, grind, method and climate remain nested in supplier, so the")
    print("  pooled exponent is still the supplier contrast wearing a rate label.")
    print("  What survives: fraction weathered is not a site property, and the map")
    print("  must not present it as one.")
    return float(s), float(r2), len(rows)


def porewater_pco2(rows, recs):
    rule("7. Porewater pH + alkalinity -> implied in-situ soil pCO2")
    have = [r for r in rows if r["porewater_ph"] and r["porewater_alkalinity_ueq_l"]]
    if not have:
        print("  no porewater chemistry in the set")
        return None
    print("  At pH ~6.5 alkalinity is bicarbonate, and open-system carbonate")
    print("  equilibrium gives pCO2 = [HCO3-] x a_H+ / (K1 KH). Evaluated at the")
    print("  cell's mean air temperature (a degassed sample would read HIGHER pH")
    print("  and so UNDER-state pCO2; these are lower-bound-leaning estimates).")
    print()
    print(f"  {'delivery':28s} {'crop':>6s} {'pH':>5s} {'alk ueq/L':>9s} "
          f"{'pCO2 uatm':>10s} {'map cell':>9s}")
    vals = []
    byX = {x["slug"]: x for x in recs}
    for r in have:
        g = byX.get(r["delivery_slug"], {}).get("g")
        T = (g["tair"] if g else 25.0) + 273.15
        K1, _, KH, _ = K.carbonate_constants(T)
        h = 10.0 ** (-r["porewater_ph"])
        p = r["porewater_alkalinity_ueq_l"] * 1e-6 * h / (K1 * KH) * 1e6
        vals.append(p)
        cell = f"{g['pco2']:9,.0f}" if g else "        -"
        print(f"  {r['delivery_slug']:28s} {(r['crop'] or '-')[:6]:>6s} "
              f"{r['porewater_ph']:5.2f} {r['porewater_alkalinity_ueq_l']:9.0f} "
              f"{p:10,.0f} {cell}")
    print()
    print(f"  Implied pCO2 {min(vals):,.0f}-{max(vals):,.0f} uatm across "
          f"{len(vals)} site means (one supplier, one region, method unstated).")
    print(f"  Protocol values: {C.PCO2_UNSATURATED_UATM:,.0f} drained, "
          f"{C.PCO2_SATURATED_UATM:,.0f} saturated. The flooded rows land near the")
    print("  saturated value; the UPLAND rows land there too, which says wet")
    print("  tropical soil respiration, not flooding per se, sets these numbers.")
    print("  First field constraint on the paddy pCO2 assumption in the set; n is")
    print("  four site-means from one bundle, so it is a plausibility check, not")
    print("  a calibration. The measured alkalinities (2-3 mmol/L) are also well")
    print("  BELOW calcite saturation at that pCO2: these fields are kinetically")
    print("  limited, not transport-limited, which is what the map says of them.")
    return (min(vals), max(vals), len(vals))


def flux_ceiling_check(rows, recs, co2, co2_by_company):
    rule("8. Does dissolution-based CDR fit in the drainage water?")
    print("  Reported dissolution x the supplier's Ca+Mg potential, per year, as a")
    print("  bicarbonate concentration in the cell's own drainage, against calcite")
    print("  saturation at the cell's soil pCO2 and temperature.")
    print()
    print(f"  {'delivery':28s} {'t/ha':>6s} {'q mm':>5s} {'tCO2/ha':>8s} "
          f"{'implied':>8s} {'ceiling':>8s} {'over':>6s}")
    ratios = []
    byX = {x["slug"]: x for x in recs}
    for r in rows:
        rec = byX.get(r["delivery_slug"])
        if rec is None or r["coord_src"] == "approximate_region_centroid":
            continue
        g = rec["g"]
        cp = co2_by_company.get(r["company"]) or co2
        flag = "" if co2_by_company.get(r["company"]) else " (supplier mean potential)"
        cdr = r["app_rate_t_ha"] * r["fw365"] * cp
        implied = cdr * 1e6 / C.M_CO2_G_MOL / max(g["q"] * 1e7, 1e-9)
        ratio = implied / g["alk_ceiling"]
        ratios.append(ratio)
        print(f"  {r['delivery_slug']:28s} {r['app_rate_t_ha']:6.1f} {g['q'] * 1000:5.0f} "
              f"{cdr:8.2f} {implied * 1e3:7.1f}m {g['alk_ceiling'] * 1e3:7.2f}m "
              f"{ratio:5.1f}x{flag}")
    n_over = sum(1 for v in ratios if v > 1.0)
    print()
    print(f"  {n_over} of {len(ratios)} joinable deliveries exceed their own "
          f"drainage-concentration ceiling ({min(ratios):.1f}-{max(ratios):.1f}x).")
    print("  Not an over-crediting finding: these are DISSOLUTION figures, and the")
    print("  gap is the retention-and-lag term (exchange sites, Fe/Mn oxides,")
    print("  neoformed clays). What it establishes: dissolution-based CDR/ha cannot")
    print("  be read as export without a retention term, so this set cannot anchor")
    print("  the map's absolute EXPORT level -- it anchors dissolution only, which")
    print("  is exactly what section 5 uses it for.")
    return n_over, len(ratios), (min(ratios), max(ratios))


def what_is_not_identifiable(rows, feed, res):
    rule("9. What is not identifiable, and what would make it so")
    print("  Grind, tracer method, sampling depth, climate and application rate")
    print(f"  are all nested in supplier: {len(feed)} clusters, "
          f"{res['n_known'] if res else '?'} with a disclosed grind, one of them")
    print("  temperate. So the k spread in section 5 cannot be attributed to any")
    print("  one of them. In priority order:")
    print("   1. PARTICLE-SIZE DISTRIBUTIONS, not p50 -- the width decides whether")
    print("      the coarse supplier's high k is a broad fine tail or fast kinetics.")
    print("   2. Measured bulk density and sampling depth from every supplier; two")
    print("      batches from one supplier imply densities ~40% apart.")
    print("   3. Repeat samplings of the SAME fields. The one pair in the set")
    print("      constrains the curve shape more than any new site would.")
    print("   4. Per-location coordinates where only a state centroid was shared.")
    print("   5. A flooded-vs-drained pair, same feedstock and rate, at one site.")


def main() -> int:
    rows, feed = load()
    if rows is None:
        print("No calibration dataset found at:")
        print(f"  {DELIVERIES}")
        print(f"  {FEEDSTOCK}")
        print()
        print("These inputs are deliberately not redistributed -- they derive from")
        print("supplier bundles and verification reports and carry per-supplier")
        print("results. See the module docstring for the expected CSV schema.")
        print()
        print("Aggregate findings from the local run are recorded in README.md and")
        print("in constants.py (DISSOLVED_FRAC_AT_REF, DISSOLVED_FRAC_REF_CLUSTER_RANGE,")
        print("DELIVERED_BASALT_TCO2_PER_T).")
        return 0
    grid = Grid()
    print("=" * 74)
    print(f"Verified ERW deliveries -- {len(rows)} removals/deployments, "
          f"{len(feed)} suppliers, all basalt")
    print("=" * 74)
    inventory(rows, feed)
    use, pred = usable_rows(rows)
    print(f"\n  Rate-usable rows: {len(use)} of {len(rows)} (no duration: "
          f"{sum(1 for r in rows if not r['elapsed_days'])}; superseded early "
          f"sampling: {len(pred)}).")
    fws = time_normalise(use)
    longitudinal_shape_test(rows, pred)
    co2, co2_rng, n_co2 = co2_potential(feed)
    co2_by = {}
    for f in feed:
        if f["ca_mg_kg"] is not None and f["mg_mg_kg"] is not None:
            co2_by[f["company"]] = 2.0 * (f["ca_mg_kg"] / 1000.0 / 40.078
                                          + f["mg_mg_kg"] / 1000.0 / 24.305) \
                * C.M_CO2_G_MOL / 1000.0
    res = constancy_test(use, feed, grid)
    slope, r2, n_fit = rate_exponent(use)
    pw = porewater_pco2(rows, res["recs"] if res else [])
    if res:
        flux_ceiling_check(use, res["recs"], co2, co2_by)
    what_is_not_identifiable(rows, feed, res)

    rule("CONSTANTS (cross-supplier aggregates only)")
    print(f"  DELIVERED_BASALT_TCO2_PER_T = {co2:.3f}   # Ca+Mg basis, "
          f"n = {n_co2} suppliers")
    print(f"  DELIVERED_BASALT_RANGE = ({co2_rng[0]:.3f}, {co2_rng[1]:.3f})")
    print(f"  DISSOLVED_FRAC_OBSERVED_RANGE = ({fws[0]:.3f}, {fws[-1]:.3f})   "
          f"# one-year, own grind/site, n = {len(fws)}")
    print(f"  DISSOLVED_FRAC_OBSERVED_MEDIAN = {np.median(fws):.3f}")
    if res:
        print(f"  DISSOLVED_FRAC_AT_REF = {res['frac_ref']:.4f}  -> set to 2 s.f. "
              f"{round(res['frac_ref'], 2)}   # median k {res['k_star']:.3f} over "
              f"{res['n_known']} known-grind clusters")
        print(f"  DISSOLVED_FRAC_REF_CLUSTER_RANGE = "
              f"({res['cluster_frac_range'][0]:.3f}, {res['cluster_frac_range'][1]:.3f})"
              f"   # {res['spread']:.1f}x spread")
        print(f"  DISSOLVED_FRAC_AT_REF_ALT_WITH_UNKNOWN_GRIND = "
              f"{G(K.retreat_at_reference() / C.PSD_REF_D50_UM * res['k_all']):.3f}")
    print(f"  FW_RATE_EXPONENT_OBSERVED = {slope:.2f}   # R2 {r2:.2f}, n = {n_fit}; "
          f"confounded, not used")
    if pw:
        print(f"  PADDY_PCO2_FIELD_IMPLIED_UATM = ({pw[0]:,.0f}, {pw[1]:,.0f})   "
              f"# n = {pw[2]} site means")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
