"""Rice-paddy ERW potential (basalt), India and the world, with and without the
drainage limit.

  python3 scripts/analysis/paddy_potential.py

WHAT IS COUNTED. Paddy area = the SPAM all-rice fraction of each cell x cell
area, on cells GRPI shows inundated (months > 0): the same paddy filter the
build uses for f_flood. Cells with SPAM rice but GRPI months = 0 are reported
separately (GRPI's presence grid has holes; f_flood is a floor at paddy sites).
Every total is a SUM over paddy hectares of a per-hectare removal, i.e.
area-weighted by construction; the per-hectare figures quoted alongside are
paddy-area-weighted means and medians.

TWO CHEMISTRIES, reported side by side:
  cell mean   the map's shipped layers: f_flood dilutes paddy chemistry by
              the non-rice share of the cell (pH toward 6.7 and pCO2 toward
              50,000 uatm only in proportion to the flooded cell-time).
  paddy view  the build's tex5 chemistry: every paddy-bearing cell treated
              as 100% paddy with its observed inundation months -- the right
              basis for "what would rice fields deliver", and the one used
              for the headline here.

TWO TIME BASES, as everywhere in the repo: steady state (hold 30 t/ha of
undissolved basalt, reapplying as it dissolves, capped at one application
per year; the paper's basis) and year 1 (the map layers). With and without
the drainage-concentration ceiling in each case. Gross removal, not net; the
paddy ceiling at the protocol's 50,000 uatm is UNVALIDATED (gate 13c) and
sits at the bottom of the measured flooded-soil pCO2 range, so the limited
numbers lean conservative.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import constants as C  # noqa: E402
import kinetics as K  # noqa: E402
from build_v0 import master_grid  # noqa: E402
from analysis.country_potential import country_raster  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

FOCUS = ["IN", "CN", "ID", "BD", "VN", "TH", "MM", "PH", "PK", "BR", "US", "JP", "KR", "NG"]


def main() -> int:
    transform, w, h, crs = master_grid()
    z = np.load(ROOT / "data/processed/v0_layers.npz")
    for key in ("L1_pad", "eta_pad", "ceiling_pad", "paddy_area_frac", "paddy_months"):
        if key not in z.files:
            raise SystemExit(f"{key} missing from v0_layers.npz -- rebuild with the "
                             f"2026-09-14 build_v0.py (paddy-view floats saved)")
    crop, area, ph = z["crop"], z["area"], z["ph"]
    L1, L1p = z["L1"].astype("float64"), z["L1_pad"].astype("float64")
    eta, etap = np.nan_to_num(z["eta"].astype("float64")), np.nan_to_num(z["eta_pad"].astype("float64"))
    eta_tr = np.nan_to_num(z["eta_tr"].astype("float64"))
    ceil_c, ceil_p = np.nan_to_num(z["ceiling"].astype("float64")), np.nan_to_num(z["ceiling_pad"].astype("float64"))
    parea, months = z["paddy_area_frac"].astype("float64"), z["paddy_months"].astype("float64")

    m = (crop >= C.CROPLAND_MIN_FRACTION) & np.isfinite(ph) & np.isfinite(L1)
    ha_paddy = np.clip(parea, 0, 1) * area * 100.0            # ha of rice per cell
    inund = months > 0
    sel = m & inund & (ha_paddy > 0)
    sel_hole = m & ~inund & (ha_paddy > 0)

    # ---- kinetics scaffolding, identical to the build's and the footer's
    spec = C.FEEDSTOCK_ARCHETYPES[C.FEEDSTOCK_DEFAULT]
    ct = ((spec["CaO_wt"] / C.M_CAO + spec["MgO_wt"] / C.M_MGO)
          * 1000.0 * 2.0 * C.MOL_CO2_PER_KMOL_CHARGE_T)
    A = C.APPLICATION_RATE_T_HA_YR
    d_ref = K.retreat_at_reference()
    ug = np.concatenate([[0.0], np.geomspace(1e-5, 200.0, 900)])
    gg = np.concatenate([[0.0], K.dissolved_fraction(ug[1:], C.PSD_REF_WIDTH)])
    i_inf = float(np.trapezoid(1.0 - gg, ug))

    def per_ha(L1x, etax, ceilx):
        u1 = d_ref * np.clip(np.nan_to_num(10.0 ** L1x) * eta_tr, 0.0, None) / C.PSD_REF_D50_UM
        ss_un = np.minimum(1.0, u1 / i_inf) * etax * A * ct
        y1_un = np.interp(u1, ug, gg) * etax * A * ct
        return {"ss_un": ss_un, "ss_lim": np.minimum(ss_un, ceilx),
                "y1_un": y1_un, "y1_lim": np.minimum(y1_un, ceilx), "ceil": ceilx}

    chem = {"cell mean": per_ha(L1, eta, ceil_c), "paddy view": per_ha(L1p, etap, ceil_p)}

    idx, isos, names = country_raster(transform, w, h)

    def region_mask(iso):
        return sel if iso == "WORLD" else (sel & (idx == isos.index(iso) + 1))

    def wq(v, wts, qs):
        o = np.argsort(v)
        cw = np.cumsum(wts[o]) / wts.sum()
        return [float(v[o][np.searchsorted(cw, t)]) for t in qs]

    print("Rice-paddy ERW potential, basalt, 30 t/ha; paddy area = SPAM rice fraction x cell "
          "area on GRPI-inundated cells; totals are sums over paddy hectares (area-weighted)")
    print(f"  steady-state basis: I_inf = {i_inf:.3f}; CO2 potential {ct:.3f} tCO2/t; "
          f"ceiling Omega = {C.FLUX_CEILING_OMEGA:.3g}, Mg = {C.FLUX_CEILING_MG_MM:g} mM\n")

    rows = []
    for iso in ["WORLD"] + FOCUS:
        r = region_mask(iso)
        if r.sum() == 0:
            continue
        hav = ha_paddy[r]
        mha = hav.sum() / 1e6
        hole_mha = ha_paddy[sel_hole & (True if iso == "WORLD" else (idx == isos.index(iso) + 1))].sum() / 1e6
        out = {"iso": iso, "name": "World" if iso == "WORLD" else names[iso],
               "paddy_mha": mha, "spam_rice_no_grpi_mha": hole_mha}
        for label, ch in chem.items():
            for k in ("ss_un", "ss_lim", "y1_un", "y1_lim"):
                out[f"{label}|{k}|Mt"] = float((hav * ch[k][r]).sum() / 1e6)
                out[f"{label}|{k}|mean"] = float((hav * ch[k][r]).sum() / hav.sum())
            out[f"{label}|binds"] = float((hav * (ch["ss_un"][r] > ch["ceil"][r] * 1.000001)).sum() / hav.sum())
            out[f"{label}|ceil_p50"] = wq(ch["ceil"][r], hav, (0.5,))[0]
            out[f"{label}|exceed_p50"] = wq(ch["ss_un"][r] / np.maximum(ch["ceil"][r], 1e-12), hav, (0.5,))[0]
        rows.append(out)

    hdr = (f"{'region':14s} {'paddy Mha':>9s} {'(no GRPI)':>9s} | {'chemistry':10s} | "
           f"{'SS uncapped':>11s} {'SS limited':>10s} | {'Y1 uncapped':>11s} {'Y1 limited':>10s} | "
           f"{'binds':>6s} {'ceil p50':>8s} {'exceed p50':>10s}")
    print(hdr)
    print("-" * len(hdr))
    for o in rows:
        for j, label in enumerate(chem):
            lead = f"{o['name'][:14]:14s} {o['paddy_mha']:9.1f} {o['spam_rice_no_grpi_mha']:9.1f}" if j == 0 else " " * 34
            print(f"{lead} | {label:10s} | "
                  f"{o[f'{label}|ss_un|Mt']:8.1f} Mt {o[f'{label}|ss_lim|Mt']:7.1f} Mt | "
                  f"{o[f'{label}|y1_un|Mt']:8.1f} Mt {o[f'{label}|y1_lim|Mt']:7.1f} Mt | "
                  f"{o[f'{label}|binds']:6.1%} {o[f'{label}|ceil_p50']:8.2f} {o[f'{label}|exceed_p50']:9.1f}x")
    print("\nper-hectare, paddy-area-weighted MEAN tCO2/ha/yr (steady state; uncapped -> limited):")
    for o in rows[:2]:
        for label in chem:
            print(f"  {o['name']:8s} {label:10s} {o[f'{label}|ss_un|mean']:.2f} -> {o[f'{label}|ss_lim|mean']:.2f}")

    # Sanity anchors for the AREA, the quantity everything is weighted by.
    print("\nAREA CHECK: SPAM all-rice physical area reproduced on this grid; compare with FAOSTAT "
          "rice area harvested (multi-cropping makes harvested > physical). Verify the FAO figures "
          "before quoting them; they are not read from a file here.")
    w_ = rows[0]; i_ = next(o for o in rows if o["iso"] == "IN")
    print(f"  world paddy on inundated cells {w_['paddy_mha']:.1f} Mha (+{w_['spam_rice_no_grpi_mha']:.1f} Mha "
          f"SPAM rice where GRPI shows no inundation); India {i_['paddy_mha']:.1f} (+{i_['spam_rice_no_grpi_mha']:.1f})")

    import json
    (ROOT / "data/processed").mkdir(exist_ok=True, parents=True)
    with open(ROOT / "data/processed/paddy_potential.json", "w") as f:
        json.dump({"basis": "basalt 30 t/ha; steady state and year 1; Mt CO2/yr; paddy = SPAM rice x GRPI-inundated",
                   "rows": rows}, f, indent=1)
    print("\nwrote data/processed/paddy_potential.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
