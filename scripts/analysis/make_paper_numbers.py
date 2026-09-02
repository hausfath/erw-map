"""Every number quoted in the ERL manuscript, as LaTeX macros.

  python3 scripts/analysis/make_paper_numbers.py   -> paper/numbers.tex

The manuscript never types a number: it writes \\GtLimited, \\BindsPct, etc.
Each macro here is computed from data/processed/v0_layers.npz, scripts/constants.py,
paper/country_ensemble.json (written by country_potential.py --json) and the
anonymised calibration exports (written by analyse_deployments.py). Re-run after
any rebuild; the manuscript recompiles against the new values.

Nothing here reads the private calibration dataset.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import constants as C  # noqa: E402
import paper_figures as PF  # noqa: E402  (loads the grid once)

ROOT = Path(__file__).resolve().parents[2]
PAPER = ROOT / "paper"
OUT = PAPER / "numbers.tex"

macros: dict[str, str] = {}


def m(name, value):
    macros[name] = value


def num(x, nd=2):
    return f"{x:.{nd}f}"


def pct(x, nd=0):
    return f"{100 * x:.{nd}f}"


def wq(x, w, ps):
    o = np.argsort(x); cw = np.cumsum(w[o]) / w.sum()
    return [float(np.interp(p, cw, x[o])) for p in ps]


# ---- build-derived --------------------------------------------------------
v = PF.steady_state_vectors()
A = C.APPLICATION_RATE_T_HA_YR
unc = A * v["per_t"]; cap = np.minimum(unc, v["ceil"]); ha = v["ha"]
G = lambda x: float(np.sum(x * ha) / 1e9)
m("GtLimited", num(G(cap), 2))
m("GtLimitedThree", num(G(cap), 3))
m("GtUncapped", num(G(unc), 2))
m("GtExcess", num(G(unc) - G(cap), 2))
m("CutPct", pct(1 - G(cap) / G(unc)))
binds = unc > v["ceil"] * 1.000001
m("BindsPct", pct(ha[binds].sum() / ha.sum()))
ratio = unc / np.maximum(v["ceil"], 1e-9); ok = v["ceil"] > 1e-9
m("MedianExceedance", num(wq(ratio[ok], ha[ok], [0.5])[0], 1))
p10, p50, p90 = wq(cap, ha, [0.1, 0.5, 0.9])
m("CapMedian", num(p50, 2)); m("CapPNinety", num(p90, 2))
m("CroplandGha", num(ha.sum() / 1e9, 2))
m("CroplandMha", f"{ha.sum() / 1e6:,.0f}")
# year-1 basis, for the SI
y1_unc = PF.Z["cdr_uncapped"][PF.MASK].astype("float64"); y1_cap = PF.Z["cdr"][PF.MASK].astype("float64")
m("GtLimitedYearOne", num(float(np.nansum(y1_cap * ha) / 1e9), 3))
m("GtUncappedYearOne", num(float(np.nansum(y1_unc * ha) / 1e9), 3))
m("BindsPctYearOne", pct(ha[y1_unc > PF.Z["ceiling"][PF.MASK] * 1.000001].sum() / ha.sum()))
# binding fraction at the leave-one-cluster-out anchor range (k relative to shipped)
import kinetics as _K
_ug = np.concatenate([[0.0], np.geomspace(1e-5, 200.0, 900)])
_gg = np.concatenate([[0.0], _K.dissolved_fraction(_ug[1:], C.PSD_REF_WIDTH)])
_uof = lambda fr: float(np.interp(fr, _gg, _ug))
_kj = PAPER / "calibration_clusters.json"
if _kj.exists():
    _K_ = json.loads(_kj.read_text())
    _b = []
    for fr in _K_["loo_range"]:
        kk = _uof(fr) / _uof(C.DISSOLVED_FRAC_AT_REF)
        _i_inf = float(np.trapezoid(1.0 - _gg, _ug))
        per_t = np.minimum(1.0, kk * v["u1"] / _i_inf) * v["eta"] * v["ct"]
        _b.append(ha[A * per_t > v["ceil"] * 1.000001].sum() / ha.sum())
    m("BindsLOOLo", pct(min(_b))); m("BindsLOOHi", pct(max(_b)))
# application-rate response
rates = {r: float(np.sum(np.minimum(r * v["per_t"], v["ceil"]) * ha) / 1e9) for r in (20.0, 30.0, 45.0, 60.0)}
m("RateGainFiftyPct", pct(rates[45.0] / rates[30.0] - 1))
m("RateGainDoublePct", pct(rates[60.0] / rates[30.0] - 1))
# climate contrasts
q = v["q"]; t = PF.Z["tair"][PF.MASK].astype("float64")
def tail(key, top):
    oo = np.argsort(key); c2 = np.cumsum(ha[oo]) / ha.sum()
    return oo[c2 >= 0.95] if top else oo[c2 <= 0.05]
def wm(x, sel): return float(np.sum(x[sel] * ha[sel]) / ha[sel].sum())
m("WetDryUncapped", num(wm(unc, tail(q, True)) / wm(unc, tail(q, False)), 0))
m("WetDryLimited", num(wm(cap, tail(q, True)) / wm(cap, tail(q, False)), 0))
m("WarmCoolUncapped", num(wm(unc, tail(t, True)) / wm(unc, tail(t, False)), 0))
m("WarmCoolLimited", num(wm(cap, tail(t, True)) / wm(cap, tail(t, False)), 1))
# ceiling chemistry
alk = PF.Z["alk_ceiling"][PF.MASK].astype("float64") * 1e3
a10, a50, a90 = wq(alk[np.isfinite(alk)], ha[np.isfinite(alk)], [0.1, 0.5, 0.9])
m("CeilMmolPTen", num(a10, 1)); m("CeilMmolMedian", num(a50, 1)); m("CeilMmolPNinety", num(a90, 1))
qq = wq(q * 1000, ha, [0.1, 0.5, 0.9])
m("DrainageMedianMm", f"{qq[1]:.0f}"); m("DrainagePTenMm", f"{qq[0]:.0f}"); m("DrainagePNinetyMm", f"{qq[2]:.0f}")
# pedogenic carbonate bound (to-do item 12; quoted as a range in Discussion)
spec = C.FEEDSTOCK_ARCHETYPES["delivered_basalt"]
fca = (spec["CaO_wt"] / C.M_CAO) / (spec["CaO_wt"] / C.M_CAO + spec["MgO_wt"] / C.M_MGO)
exc = np.maximum(unc - v["ceil"], 0)
m("PedogenicLow", num(0.5 * fca * G(exc), 2)); m("PedogenicHigh", num(0.5 * G(exc), 2))
m("FCa", num(fca, 2))

# ---- constants ------------------------------------------------------------
m("AppRate", f"{A:.0f}")
m("CtPerT", f"{C.DELIVERED_BASALT_TCO2_PER_T:.3f}")
m("CtLo", f"{C.DELIVERED_BASALT_RANGE[0]:.3f}"); m("CtHi", f"{C.DELIVERED_BASALT_RANGE[1]:.3f}")
m("CtNSuppliers", f"{C.DELIVERED_BASALT_N_SUPPLIERS}")
m("AnchorPct", pct(C.DISSOLVED_FRAC_AT_REF)); m("AnchorOldPct", "25")
m("ClusterLoPct", pct(C.DISSOLVED_FRAC_REF_CLUSTER_RANGE[0], 1)); m("ClusterHiPct", pct(C.DISSOLVED_FRAC_REF_CLUSTER_RANGE[1], 1))
m("ClusterSpread", f"{C.DISSOLVED_FRAC_REF_CLUSTER_SPREAD:.1f}")
m("ObsLoPct", pct(C.DISSOLVED_FRAC_OBSERVED_RANGE[0])); m("ObsHiPct", pct(C.DISSOLVED_FRAC_OBSERVED_RANGE[1]))
m("ObsN", f"{C.DISSOLVED_FRAC_OBSERVED_N}")
m("AnchorAltUnknownPct", pct(C.DISSOLVED_FRAC_AT_REF_IF_UNKNOWN_GRIND_INCLUDED))
m("PaddyPcoLo", f"{C.PADDY_PCO2_FIELD_IMPLIED_UATM[0] / 1000:.0f}"); m("PaddyPcoHi", f"{C.PADDY_PCO2_FIELD_IMPLIED_UATM[1] / 1000:.0f}")
m("PcoDrained", f"{C.PCO2_UNSATURATED_UATM:,.0f}"); m("PcoSaturated", f"{C.PCO2_SATURATED_UATM:,.0f}")
m("OmegaCentral", "10^{0.5}"); m("MgMM", f"{C.FLUX_CEILING_MG_MM:.0f}")
m("PhTarget", f"{C.FLUX_CEILING_PH_TARGET:.1f}")
m("RefDFifty", f"{C.PSD_REF_D50_UM:.0f}"); m("RefWidth", f"{C.PSD_REF_WIDTH:.1f}")
m("DeliverySpanLo", f"{C.DELIVERY_P50_SPAN_UM[0]:.0f}"); m("DeliverySpanHi", f"{C.DELIVERY_P50_SPAN_UM[1]:.0f}")
m("GateUsd", f"{C.FEEDSTOCK_GATE_COST_USD_T:.0f}"); m("ScreenUsd", f"{C.COST_SCREEN_USD_PER_TCO2:.0f}")
m("Dw", f"{C.DAMKOHLER_DW_M_YR:g}")
_mg = getattr(C, "MAYER_2025_GLOBAL_GT", 0.34)
_mg = _mg.get("central", 0.34) if isinstance(_mg, dict) else _mg
m("MayerGt", f"{_mg:.2f}")
m("EaMeasured", f"{C.BASALT_APPARENT_EA_MEASURED_KJ:.0f}")
m("SuitTop", f"{C.CDR_SUITABILITY_TOP_T_HA_YR:.0f}"); m("CdrNegligible", f"{C.CDR_NEGLIGIBLE_T_HA_YR:g}")
m("QuarryPoints", "13,602")   # from the build's overlay count; see README

# ---- economics (shipped parameters) --------------------------------------
try:
    from rasterio.enums import Resampling
    import country_potential as CP
    import kinetics as K
    transform, w, h, crs = CP.master_grid()
    rate = CP.onto_grid(CP.INTERIM / "truck_rate.tif", transform, w, h, crs, resampling=Resampling.nearest).astype("float64")[PF.MASK]
    cost = CP.onto_grid(CP.INTERIM / "feedstock_cost.tif", transform, w, h, crs, resampling=Resampling.average).astype("float64")[PF.MASK]
    basis = CP.onto_grid(CP.INTERIM / "cost_basis.tif", transform, w, h, crs, resampling=Resampling.nearest).astype("float64")[PF.MASK]
    c10, c50, c90 = wq(cost[np.isfinite(cost)], ha[np.isfinite(cost)], [0.1, 0.5, 0.9])
    m("CostPTen", f"{c10:.0f}"); m("CostMedian", f"{c50:.0f}"); m("CostPNinety", f"{c90:.0f}")
    m("RegisteredBasisPct", pct(ha[basis == 1].sum() / ha.sum()))
    d_ref = K.retreat_at_reference()
    ug = np.concatenate([[0.0], np.geomspace(1e-5, 200.0, 900)])
    gg = np.concatenate([[0.0], K.dissolved_fraction(ug[1:], C.PSD_REF_WIDTH)])
    dr = C.COST_SCREEN_DISCOUNT_RATE
    u1g = np.concatenate([[0.0], np.geomspace(1e-7, 20.0, 600)]); Dg = np.zeros_like(u1g); prev = np.zeros_like(u1g)
    for tt in range(1, 61):
        cum = np.interp(u1g * tt, ug, gg); Dg += (cum - prev) / (1 + dr) ** tt; prev = cum
    dpt = v["eta"] * v["ct"] * A * np.interp(v["u1"], u1g, Dg)
    okc = np.isfinite(cost) & (dpt > 0)
    d_eff = np.maximum(cost - C.FEEDSTOCK_GATE_COST_USD_T, 0.0) / np.maximum(rate, 1e-9)
    def screen(gate):
        cc = (gate + rate * d_eff) * A
        p = okc & (cc / np.maximum(dpt, 1e-12) < C.COST_SCREEN_USD_PER_TCO2)
        return float(np.sum(cap[p] * ha[p]) / 1e9), float(ha[p].sum() / 1e9)
    g10, a10_ = screen(10.0); g18, a18 = screen(18.0); g21, a21 = screen(21.5)
    m("ScreenGt", num(g10, 2)); m("ScreenGha", num(a10_, 2))
    m("ScreenGtGateEighteen", num(g18, 2)); m("ScreenGtGateTwentyOne", num(g21, 3))
    unitc = cost * A / np.maximum(dpt, 1e-12)
    m("UnitCostMedian", f"{wq(unitc[okc], ha[okc], [0.5])[0]:.0f}")
except Exception as ex:  # pragma: no cover
    print("economics macros skipped:", ex)

# ---- country ensemble -----------------------------------------------------
cj = PAPER / "country_ensemble.json"
if cj.exists():
    J = json.loads(cj.read_text())
    m("NDraws", f"{J['n_draws']:,}")
    m("ThresholdMt", f"{J.get('threshold_mt', 50):.0f}")
    rows = {r["name"]: r for r in J["rows"]}
    def fmt(r, key, nd=0):
        p5, p50, p95 = r[key]
        return f"{p50:,.{nd}f} ({p5:,.{nd}f}--{p95:,.{nd}f})"
    W = rows["WORLD"]
    for key, nm in (("tech_un", "WorldUncapped"), ("econ_un", "WorldEconUncapped"),
                    ("tech_cap", "WorldLimited"), ("econ_cap", "WorldEconLimited")):
        m(nm, fmt(W, key))
        m(nm + "PFifty", f"{W[key][1]:,.0f}"); m(nm + "PFive", f"{W[key][0]:,.0f}"); m(nm + "PNinetyFive", f"{W[key][2]:,.0f}")
    m("WorldLimitedGtRange", f"{W['tech_cap'][0] / 1e3:.2f}--{W['tech_cap'][2] / 1e3:.2f}")
    m("WorldLimitedGtPFifty", f"{W['tech_cap'][1] / 1e3:.2f}")
    for iso, nm in (("India", "India"), ("Brazil", "Brazil"), ("United States of America", "US")):
        r = next((x for x in J["rows"] if x["name"] == iso), None)
        if r:
            for key, suf in (("tech_un", "Uncapped"), ("econ_un", "EconUncapped"), ("tech_cap", "Limited"), ("econ_cap", "EconLimited")):
                m(nm + suf, fmt(r, key)); m(nm + suf + "PFifty", f"{r[key][1]:,.0f}")
            m(nm + "Mha", f"{r['mha']:,.0f}")
    if J.get("india_brazil_limited_ratio"):
        rr = J["india_brazil_limited_ratio"]
        m("IndiaBrazilRatio", f"{rr[1]:.1f} ({rr[0]:.1f}--{rr[2]:.1f})")
    m("EnsembleLimitedPFiftyGt", num(J["ensemble_world_p50"]["limited_gt"], 2))
    m("EnsembleUncappedPFiftyGt", num(J["ensemble_world_p50"]["uncapped_gt"], 2))
    for scn, d in J["per_scenario_econ_cap"].items():
        m("EconLimited" + scn.capitalize(), f"{d['world'][1]:,.0f}")
    se = J["mc_se_world"]["tech_cap"]
    m("MCSELimited", f"{se[0]:.0f}/{se[1]:.0f}/{se[2]:.0f}")
    m("CountryRowsN", f"{len([r for r in J['rows'] if r['iso']])}")
else:
    print("country_ensemble.json not found; country macros skipped")

# ---- calibration (anonymised exports) -------------------------------------
kj = PAPER / "calibration_clusters.json"
if kj.exists():
    K_ = json.loads(kj.read_text())
    known = [c for c in K_["clusters"] if c["grind_known"]]
    m("ClusterKLo", f"{min(c['k'] for c in known):.2f}"); m("ClusterKHi", f"{max(c['k'] for c in known):.2f}")
    m("KStar", f"{K_['k_star']:.2f}")
    m("LOOLoPct", pct(K_["loo_range"][0], 1)); m("LOOHiPct", pct(K_["loo_range"][1], 1))
    m("NClusters", f"{len(K_['clusters'])}"); m("NKnownGrind", f"{len(known)}")
    for c in K_["clusters"]:
        m(f"Cluster{c['cluster']}K", f"{c['k']:.2f}")
        m(f"Cluster{c['cluster']}Lo", f"{c['k_lo']:.2f}"); m(f"Cluster{c['cluster']}Hi", f"{c['k_hi']:.2f}")
        m(f"Cluster{c['cluster']}D", f"{c['d50_um']:.0f}" if c["d50_um"] else "undisclosed")
        m(f"Cluster{c['cluster']}N", f"{c['n_rows']}")
sj = PAPER / "calibration_shape.json"
if sj.exists():
    S = json.loads(sj.read_text())
    m("ShapeTOne", f"{S['t1_days']:.0f}"); m("ShapeTTwo", f"{S['t2_days']:.0f}")
    m("ShapeFwOne", pct(S["fw1"])); m("ShapeFwTwo", pct(S["fw2"]))
    preds = [S["predictions"][k] for k in S["predictions"]]
    m("ShapePredLo", pct(min(preds))); m("ShapePredHi", pct(max(preds)))
    m("ShapeFirstOrder", pct(S["first_order"]))
    r_early = S["fw1"] / S["t1_days"]; r_late = (S["fw2"] - S["fw1"]) / (S["t2_days"] - S["t1_days"])
    m("ShapeRateFallPct", pct(r_late / r_early))

# ---- write -----------------------------------------------------------------
lines = ["% Generated by scripts/analysis/make_paper_numbers.py -- do not edit by hand.",
         f"% {len(macros)} macros."]
for k, val in sorted(macros.items()):
    lines.append(f"\\newcommand{{\\{k}}}{{{val}}}")
OUT.write_text("\n".join(lines) + "\n")
print(f"wrote {OUT} ({len(macros)} macros)")
for k in ("GtLimited", "GtUncapped", "BindsPct", "MedianExceedance", "RateGainFiftyPct",
          "WetDryUncapped", "WetDryLimited", "WarmCoolUncapped", "WarmCoolLimited",
          "ScreenGt", "ScreenGha", "RegisteredBasisPct", "CostMedian", "PedogenicLow", "PedogenicHigh"):
    print(f"  {k:22s} {macros.get(k)}")


# ---- SI table fragments -----------------------------------------------------
def write_tables():
    if cj.exists():
        J = json.loads(cj.read_text())
        lines = [r"\begin{tabular}{lrrrrr}", r"\toprule",
                 r"Country & Mha & Rate law only & With drainage limit & Rate law, under \$" + str(int(J["screen_usd_per_tco2"])) + r" & Limited, under \$" + str(int(J["screen_usd_per_tco2"])) + r" \\",
                 r"\midrule"]
        for r in J["rows"]:
            nm = r["name"].replace("United States of America", "United States")
            if nm in ("China", "Turkey"):
                nm += r"$^\dagger$"
            cells = " & ".join(f"{r[k][1]:,.0f} ({r[k][0]:,.0f}--{r[k][2]:,.0f})" for k in ("tech_un", "tech_cap", "econ_un", "econ_cap"))
            if r["name"] == "WORLD":
                lines.append(r"\midrule")
                cells = " & ".join(f"\\textbf{{{r[k][1]:,.0f}}} ({r[k][0]:,.0f}--{r[k][2]:,.0f})" for k in ("tech_un", "tech_cap", "econ_un", "econ_cap"))
            lines.append(f"{nm} & {r['mha']:,.1f} & {cells} \\\\")
        lines += [r"\bottomrule", r"\end{tabular}"]
        (PAPER / "table_country.tex").write_text("\n".join(lines) + "\n")
        print("wrote table_country.tex")
    if kj.exists():
        K_ = json.loads(kj.read_text())
        lines = [r"\begin{tabular}{lcccccc}", r"\toprule",
                 r"Cluster & $d_{50}$, $\mu$m & Rows & $k$ & Bracket & Ref.\ year-1 $F_w$ & In anchor \\",
                 r"\midrule"]
        for c in K_["clusters"]:
            d = f"{c['d50_um']:.0f}" if c["d50_um"] else "undisclosed"
            used = "yes" if c["grind_known"] else "no (upper bound)"
            lines.append(f"{c['cluster']} & {d} & {c['n_rows']} & {c['k']:.2f} & {c['k_lo']:.2f}--{c['k_hi']:.2f} & {100 * c['frac_ref']:.1f}\\% & {used} \\\\")
        lines += [r"\midrule", f"Anchor (median of known-grind clusters) & & & {K_['k_star']:.2f} & LOO {100 * K_['loo_range'][0]:.1f}--{100 * K_['loo_range'][1]:.1f}\\% & {100 * K_['anchor']:.1f}\\% & \\\\",
                  r"\bottomrule", r"\end{tabular}"]
        (PAPER / "table_calibration.tex").write_text("\n".join(lines) + "\n")
        print("wrote table_calibration.tex")


write_tables()


# ---- SI: wider accounting sensitivity (solid carbonate, system-wide) --------
def write_wider_table():
    """Steady-state totals under the four combinations of the two viewer
    options, world and the three largest countries. Mirrors the shader:
    credit = phi x max(E - ceiling, 0); system-wide sets eta_DIC = 1."""
    import country_potential as CP
    transform, w, h, crs = CP.master_grid()
    idx, isos, names = CP.country_raster(transform, w, h)
    idxv = idx[PF.MASK].astype(int)
    phi = C.PEDOGENIC_CARBONATE_PHI
    eta_ = np.clip(v["eta"], 1e-9, 1.0)
    unc_def = A * v["per_t"]; unc_sw = unc_def / eta_
    ceil_ = v["ceil"]
    def combo(unc_, carbonate):
        cap_ = np.minimum(unc_, ceil_)
        return cap_ + (phi * np.maximum(unc_ - ceil_, 0.0) if carbonate else 0.0)
    cols = {"default": combo(unc_def, False), "carbonate": combo(unc_def, True),
            "systemwide": combo(unc_sw, False), "both": combo(unc_sw, True)}
    uncs = {"default": unc_def, "systemwide": unc_sw}
    groups = [("World", None), ("India", "IN"), ("United States", "US"), ("Brazil", "BR")]
    lines = [r"\begin{tabular}{lrrrrrr}", r"\toprule",
             r"& \multicolumn{4}{c}{Drainage-limited} & \multicolumn{2}{c}{Rate law only} \\",
             r"\cmidrule(lr){2-5}\cmidrule(lr){6-7}",
             r"& default & + solid carbonate & + system-wide & both & default & system-wide \\",
             r"\midrule"]
    out = {}
    for nm, iso in groups:
        sel = np.ones_like(ha, dtype=bool) if iso is None else (idxv == isos.index(iso) + 1)
        vals = [float(np.sum(cols[k][sel] * ha[sel]) / 1e6) for k in ("default", "carbonate", "systemwide", "both")]
        vals += [float(np.sum(uncs[k][sel] * ha[sel]) / 1e6) for k in ("default", "systemwide")]
        out[nm] = vals
        if iso is None:
            lines.append(f"{nm} & " + " & ".join(f"{x / 1e3:.3f}" for x in vals) + r" \\")
        else:
            lines.append(f"{nm} & " + " & ".join(f"{x:.0f}" for x in vals) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    (PAPER / "table_wider.tex").write_text("\n".join(lines) + "\n")
    W = out["World"]
    m("WiderCarbonateGt", num((W[1] - W[0]) / 1e3, 2))
    m("WiderCarbonateAllGt", num(0.5 / phi * (W[1] - W[0]) / 1e3, 2))
    m("WiderSystemWideLimitedPct", pct(W[2] / W[0] - 1, 1))
    m("WiderSystemWideUncappedPct", pct(W[5] / W[4] - 1, 1))
    m("WiderBothGt", num(W[3] / 1e3, 2))
    m("WiderIndiaSystemWidePct", pct(out["India"][2] / out["India"][0] - 1, 0))
    m("WiderUSSystemWidePct", pct(out["United States"][2] / out["United States"][0] - 1, 0))
    m("WiderBrazilSystemWidePct", pct(out["Brazil"][2] / out["Brazil"][0] - 1, 0))
    m("PhiCarbonate", f"{phi:.3f}")
    print("wrote table_wider.tex")
    # re-emit numbers.tex with the new macros
    lines = ["% Generated by scripts/analysis/make_paper_numbers.py -- do not edit by hand.",
             f"% {len(macros)} macros."]
    for k, val in sorted(macros.items()):
        lines.append(f"\\newcommand{{\\{k}}}{{{val}}}")
    OUT.write_text("\n".join(lines) + "\n")


write_wider_table()
