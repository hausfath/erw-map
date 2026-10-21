"""Technical and economic ERW potential by country at the SHIPPED parameters,
with the documented-parameter ensemble interval alongside where the ensemble
reported one (paper/country_ensemble.json, the top countries only).

  python3 scripts/analysis/country_table.py [--min-mha 1.0]

Writes docs/COUNTRY_POTENTIAL.md and docs/country_potential_shipped.csv.

Columns, all basalt at APPLICATION_RATE_T_HA_YR, steady state, gross MtCO2/yr:
  tech uncapped   kinetics alone, no drainage limit
  tech limited    capped by the drainage-concentration ceiling (the headline basis)
  econ uncapped   the subset on cells where delivered rock (gate + regional truck)
                  costs < COST_SCREEN_USD_PER_TCO2 per tonne of the application's
                  discounted lifetime carbon (5%, 60 yr) -- a UNIT cost, not clamped
                  by the ceiling, exactly as the viewer footer computes it
  econ limited    the same screen, counting drainage-limited carbon
The screen is acquisition and haul only, not a levelised cost of removal.
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import numpy as np
from rasterio.enums import Resampling

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import constants as C  # noqa: E402
import kinetics as K  # noqa: E402
from build_v0 import master_grid, onto_grid  # noqa: E402
from analysis.country_potential import country_raster  # noqa: E402
from analysis.region_potential import EU27  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
INTERIM = ROOT / "data/interim"
MIN_MHA = float(sys.argv[sys.argv.index("--min-mha") + 1]) if "--min-mha" in sys.argv else 1.0


def main() -> int:
    transform, w, h, crs = master_grid()
    z = np.load(ROOT / "data/processed/v0_layers.npz")
    crop, area, ph = z["crop"], z["area"], z["ph"]
    L1 = z["L1"].astype("float64")
    eta = np.nan_to_num(z["eta"].astype("float64"))
    eta_tr = np.nan_to_num(z["eta_tr"].astype("float64"))
    ceil_ = np.nan_to_num(z["ceiling"].astype("float64"))
    m = (crop >= C.CROPLAND_MIN_FRACTION) & np.isfinite(ph) & np.isfinite(L1)
    ha = (crop * area) * 100.0

    spec = C.FEEDSTOCK_ARCHETYPES[C.FEEDSTOCK_DEFAULT]
    ct = ((spec["CaO_wt"] / C.M_CAO + spec["MgO_wt"] / C.M_MGO)
          * 1000.0 * 2.0 * C.MOL_CO2_PER_KMOL_CHARGE_T)
    A = C.APPLICATION_RATE_T_HA_YR
    d_ref = K.retreat_at_reference()
    ug = np.concatenate([[0.0], np.geomspace(1e-5, 200.0, 900)])
    gg = np.concatenate([[0.0], K.dissolved_fraction(ug[1:], C.PSD_REF_WIDTH)])
    i_inf = float(np.trapezoid(1.0 - gg, ug))
    u1 = d_ref * np.clip(np.nan_to_num(10.0 ** L1) * eta_tr, 0.0, None) / C.PSD_REF_D50_UM
    ss_un = np.minimum(1.0, u1 / i_inf) * eta * A * ct
    ss_lim = np.minimum(ss_un, ceil_)

    # Discounted lifetime dissolved fraction D(u1), 60 years at the screen's rate,
    # on a grid then interpolated (identical to country_potential.py).
    dr = C.COST_SCREEN_DISCOUNT_RATE
    u1g = np.concatenate([[0.0], np.geomspace(1e-7, 20.0, 600)])
    Dg = np.zeros_like(u1g); prev = np.zeros_like(u1g)
    for t in range(1, 61):
        cum = np.interp(u1g * t, ug, gg)
        Dg += (cum - prev) / (1.0 + dr) ** t
        prev = cum
    D = np.interp(u1, u1g, Dg)
    cost0 = onto_grid(INTERIM / "feedstock_cost.tif", transform, w, h, crs,
                      resampling=Resampling.average).astype("float64")
    with np.errstate(divide="ignore", invalid="ignore"):
        usd_per_tco2 = cost0 / np.maximum(D * eta * ct, 1e-12)
    passes = np.isfinite(usd_per_tco2) & (usd_per_tco2 < C.COST_SCREEN_USD_PER_TCO2)

    idx, isos, names = country_raster(transform, w, h)

    ens = {}
    ej = ROOT / "paper/country_ensemble.json"
    if ej.exists():
        for r in json.load(open(ej))["rows"]:
            if r.get("iso"):
                ens[r["iso"]] = r

    def agg(sel):
        hav = ha[sel]
        if hav.sum() == 0:
            return None
        s = lambda v, extra=None: float((hav * v[sel] * (1.0 if extra is None else extra[sel])).sum() / 1e6)
        return {"mha": hav.sum() / 1e6, "tech_un": s(ss_un), "tech_lim": s(ss_lim),
                "econ_un": s(ss_un, passes), "econ_lim": s(ss_lim, passes),
                "pass_area": float((hav * passes[sel]).sum() / hav.sum()),
                "binds": float((hav * (ss_un[sel] > ceil_[sel] * 1.000001)).sum() / hav.sum())}

    rows = []
    for i, iso in enumerate(isos):
        r = agg(m & (idx == i + 1))
        if r and r["mha"] >= MIN_MHA:
            r.update({"iso": iso, "name": names[iso]}); rows.append(r)
    rows.sort(key=lambda r: -r["tech_lim"])
    world = agg(m); world.update({"iso": "WORLD", "name": "World"})
    eu = agg(m & np.isin(idx, [isos.index(i) + 1 for i in EU27 if i in isos])); eu.update({"iso": "EU27", "name": "EU27"})
    rest_mha = world["mha"] - sum(r["mha"] for r in rows)

    def fmt(x, nd=1):
        return f"{x:,.{nd}f}"

    def ens_cell(iso, key):
        r = ens.get(iso)
        if not r or key not in r:
            return ""
        lo, mid, hi = r[key]
        return f"{mid:,.0f} ({lo:,.0f}–{hi:,.0f})"

    out = ROOT / "docs/COUNTRY_POTENTIAL.md"
    lines = [
        "# ERW potential by country (basalt, shipped parameters)",
        "",
        f"Generated by `scripts/analysis/country_table.py` from the {Path('data/processed/v0_layers.npz').name} "
        f"of the current build. Basalt at {A:g} t/ha, steady state (hold {A:g} t/ha of undissolved rock, "
        "reapplying as it dissolves), gross removal. **Technical** = the kinetics; **limited** = capped by "
        "the drainage-concentration ceiling (the headline basis). **Economic** = the subset on cells where "
        f"delivered rock (quarry gate + regional trucking, great-circle × 1.35, not routed) costs under "
        f"${C.COST_SCREEN_USD_PER_TCO2:.0f} per tonne of the application's discounted lifetime carbon "
        f"({C.COST_SCREEN_DISCOUNT_RATE:.0%}, 60 yr). Acquisition and haul only, not a levelised cost, and "
        "one point on a supply curve rather than a limit: see METHODOLOGY §3c and "
        "`docs/supply_curve.json` for $150–$500 and no screen. "
        "Point values at the shipped parameters; the last two columns give the documented-parameter "
        "ensemble p50 (p5–p95) from `country_potential.py` where it reported one (top countries only; "
        "intervals are common-mode across countries and must not be combined). Countries with at least "
        f"{MIN_MHA:g} Mha of cropland in scope. The quarry inventory is complete for the US, Brazil, Mexico "
        "and France and dense for Europe via OSM; elsewhere delivered cost rests on distance to mapped "
        "mafic outcrop, so the economic columns are least reliable in Africa and Asia outside India.",
        "",
        "| Country | Cropland Mha | Tech uncapped | Tech limited | Econ uncapped | Econ limited | Area under $100/tCO₂ | Limit binds | Ensemble tech limited p50 (p5–p95) | Ensemble econ limited |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    def row(r):
        return (f"| {r['name']} | {fmt(r['mha'])} | {fmt(r['tech_un'])} | {fmt(r['tech_lim'])} | "
                f"{fmt(r['econ_un'])} | {fmt(r['econ_lim'])} | {r['pass_area']:.0%} | {r['binds']:.0%} | "
                f"{ens_cell(r['iso'], 'tech_cap')} | {ens_cell(r['iso'], 'econ_cap')} |")
    lines.append(row(world).replace("| World |", "| **World** |"))
    lines.append(row(eu))
    lines += [row(r) for r in rows]
    lines += ["", f"Rest of world (countries below {MIN_MHA:g} Mha): {fmt(rest_mha)} Mha of cropland.",
              "", "All figures MtCO₂/yr except where labelled. Gross removal, not net."]
    out.write_text("\n".join(lines) + "\n")

    with open(ROOT / "docs/country_potential_shipped.csv", "w", newline="") as f:
        wri = csv.writer(f)
        wri.writerow(["iso", "name", "cropland_mha", "tech_uncapped_mt", "tech_limited_mt",
                      "econ_uncapped_mt", "econ_limited_mt", "area_share_under_screen", "area_share_limit_binds"])
        for r in [world, eu] + rows:
            wri.writerow([r["iso"], r["name"], round(r["mha"], 3), round(r["tech_un"], 3), round(r["tech_lim"], 3),
                          round(r["econ_un"], 3), round(r["econ_lim"], 3), round(r["pass_area"], 4), round(r["binds"], 4)])
    print(f"wrote {out} and docs/country_potential_shipped.csv ({len(rows)} countries)")
    print(f"World: tech {world['tech_un']:.0f} -> {world['tech_lim']:.0f}; econ {world['econ_un']:.0f} -> {world['econ_lim']:.0f} Mt/yr; "
          f"{world['pass_area']:.0%} of area under the screen")
    for r in rows[:12]:
        print(f"  {r['name']:22s} {r['mha']:6.1f} Mha  tech {r['tech_un']:6.1f} -> {r['tech_lim']:6.1f}  "
              f"econ {r['econ_un']:6.1f} -> {r['econ_lim']:6.1f}  screen {r['pass_area']:4.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
