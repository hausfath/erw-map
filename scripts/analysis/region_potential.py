"""Steady-state ERW potential for arbitrary country groups, at the shipped
parameters (basalt, APPLICATION_RATE_T_HA_YR or --rate), uncapped and
drainage-limited, summed over cropland hectares.

  python3 scripts/analysis/region_potential.py [--rate 30] [--members]

Groups are defined below; add one and rerun. Not an ensemble: one number per
group at the shipped parameters, the same arithmetic as the viewer footer.
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

EU27 = ["AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU",
        "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"]
GROUPS = {"EU27": EU27, "UK": ["GB"], "EU27 + UK": EU27 + ["GB"]}


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
    A = float(sys.argv[sys.argv.index("--rate") + 1]) if "--rate" in sys.argv else C.APPLICATION_RATE_T_HA_YR
    d_ref = K.retreat_at_reference()
    ug = np.concatenate([[0.0], np.geomspace(1e-5, 200.0, 900)])
    gg = np.concatenate([[0.0], K.dissolved_fraction(ug[1:], C.PSD_REF_WIDTH)])
    i_inf = float(np.trapezoid(1.0 - gg, ug))
    u1 = d_ref * np.clip(np.nan_to_num(10.0 ** L1) * eta_tr, 0.0, None) / C.PSD_REF_D50_UM
    ss_un = np.minimum(1.0, u1 / i_inf) * eta * A * ct
    ss_lim = np.minimum(ss_un, ceil_)
    y1_un = np.interp(u1, ug, gg) * eta * A * ct
    y1_lim = np.minimum(y1_un, ceil_)

    idx, isos, names = country_raster(transform, w, h)

    def report(label, iso_list):
        codes = [isos.index(i) + 1 for i in iso_list if i in isos]
        missing = [i for i in iso_list if i not in isos]
        sel = m & np.isin(idx, codes)
        hav = ha[sel]
        if hav.sum() == 0:
            print(f"{label:12s} no cropland cells"); return
        tot = lambda v: float((hav * v[sel]).sum() / 1e6)
        binds = float((hav * (ss_un[sel] > ceil_[sel] * 1.000001)).sum() / hav.sum())
        print(f"{label:12s} {hav.sum() / 1e6:7.1f} Mha | SS {tot(ss_un):7.1f} -> {tot(ss_lim):6.1f} Mt/yr "
              f"({tot(ss_un) / hav.sum() * 1e6:.2f} -> {tot(ss_lim) / hav.sum() * 1e6:.2f} t/ha/yr) | "
              f"Y1 {tot(y1_un):7.1f} -> {tot(y1_lim):6.1f} | limit binds {binds:5.1%}"
              + (f" | missing {missing}" if missing else ""))

    print(f"basalt {A:g} t/ha, shipped parameters; SS = steady state, Y1 = year 1; "
          f"uncapped -> drainage-limited, MtCO2/yr gross\n")
    for label, lst in GROUPS.items():
        report(label, lst)
    if "--members" in sys.argv:
        print()
        for iso in EU27 + ["GB"]:
            report(names.get(iso, iso)[:12], [iso])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
