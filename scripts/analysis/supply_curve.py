"""Supply curve: steady-state ERW potential against the $/tCO2 acquisition-and-haul
screen, at the shipped parameters.

  python3 scripts/analysis/supply_curve.py

Same arithmetic as country_potential.py at its central draw and as the viewer
footer: steady state (one standing application, reapplication paced by the
kinetics, at most one per year), gross, basalt at APPLICATION_RATE_T_HA_YR; the
screen prices rock purchase plus truck haul against the DISCOUNTED LIFETIME
carbon of one application (60 yr, COST_SCREEN_DISCOUNT_RATE), unclamped by the
drainage ceiling (variant B). It is a demand-side screen: no quarry-volume cap,
and grinding, spreading and MRV are not in it.

Why it exists (2026-10-21): a supplier pointed out that a single $100/tCO2
screen was doing much of the work in the headline, when the costs it prices
are today's byproduct gate and today's quarry inventory. The viewer now takes
the threshold as a choice; this script is the docs' version of the same curve.

Writes docs/supply_curve.json and docs/figures/erw_supply_curve.{png,pdf}.
Reproduces the shipped $100 headline (0.197 GtCO2/yr) as a check.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import constants as C  # noqa: E402
import kinetics as K  # noqa: E402
from build_v0 import master_grid, onto_grid, INTERIM  # noqa: E402
from analysis.country_potential import country_raster  # noqa: E402
from rasterio.enums import Resampling  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
THRESHOLDS = [50, 75, 100, 150, 200, 300, 500, 750, 1000]
COUNTRIES = ["IN", "BR", "US", "CN", "ID"]


def main() -> int:
    transform, w, h, crs = master_grid()
    z = np.load(ROOT / "data/processed/v0_layers.npz")
    crop, area, ph = z["crop"], z["area"], z["ph"]
    L1 = z["L1"].astype("float64")
    m = (crop >= C.CROPLAND_MIN_FRACTION) & np.isfinite(ph) & np.isfinite(L1)
    ha = (crop * area) * 100.0
    eta = np.nan_to_num(z["eta"].astype("float64"))
    eta_tr = np.nan_to_num(z["eta_tr"].astype("float64"))
    ceil_ = np.nan_to_num(z["ceiling"].astype("float64"))
    cost = onto_grid(INTERIM / "feedstock_cost.tif", transform, w, h, crs,
                     resampling=Resampling.average).astype("float64")

    spec = C.FEEDSTOCK_ARCHETYPES[C.FEEDSTOCK_DEFAULT]
    ct = ((spec["CaO_wt"] / C.M_CAO + spec["MgO_wt"] / C.M_MGO)
          * 1000.0 * 2.0 * C.MOL_CO2_PER_KMOL_CHARGE_T)
    A = C.APPLICATION_RATE_T_HA_YR
    d_ref = K.retreat_at_reference()
    ug = np.concatenate([[0.0], np.geomspace(1e-5, 200.0, 900)])
    gg = np.concatenate([[0.0], K.dissolved_fraction(ug[1:], C.PSD_REF_WIDTH)])
    i_inf = float(np.trapezoid(1.0 - gg, ug))
    u1 = d_ref * np.clip(np.nan_to_num(10.0 ** L1) * eta_tr, 0.0, None) / C.PSD_REF_D50_UM
    un = np.minimum(1.0, u1 / i_inf) * eta * A * ct
    lim = np.minimum(un, ceil_)

    # Discounted lifetime tCO2 per tonne of rock, as in country_potential.py.
    dr = C.COST_SCREEN_DISCOUNT_RATE
    u1g = np.concatenate([[0.0], np.geomspace(1e-7, 20.0, 600)])
    Dg = np.zeros_like(u1g)
    prev = np.zeros_like(u1g)
    for t in range(1, C.COST_SCREEN_YEARS + 1):
        cum = np.interp(u1g * t, ug, gg)
        Dg += (cum - prev) / (1.0 + dr) ** t
        prev = cum
    dpt = eta * ct * np.interp(u1, u1g, Dg)
    usd = np.where((dpt > 0) & np.isfinite(cost), cost / np.maximum(dpt, 1e-12), np.inf)

    idx, isos, names = country_raster(transform, w, h)
    regions = {"World": m}
    for iso in COUNTRIES:
        if iso in isos:
            regions[names.get(iso, iso)] = m & (idx == isos.index(iso) + 1)

    def mt(v, s):
        return float((ha[s] * v[s]).sum() / 1e6)

    out = {"basis": ("steady state, gross, basalt "
                     f"{A:g} t/ha; screen = rock purchase + truck haul per "
                     f"discounted lifetime tCO2 ({C.COST_SCREEN_YEARS} yr, "
                     f"{dr:.0%}), unclamped by the drainage ceiling; gate "
                     f"${C.FEEDSTOCK_GATE_COST_USD_T:g}/t"),
           "units": "MtCO2/yr", "thresholds_usd_per_tco2": THRESHOLDS,
           "regions": {}}
    print(out["basis"])
    print(f"{'region':16s} " + " ".join(f"<${t:<5d}" for t in THRESHOLDS) + "   none")
    for name, s in regions.items():
        r = {"limited": [mt(lim, s & (usd < t)) for t in THRESHOLDS],
             "uncapped": [mt(un, s & (usd < t)) for t in THRESHOLDS],
             "limited_none": mt(lim, s), "uncapped_none": mt(un, s)}
        out["regions"][name] = {k: (np.round(v, 1).tolist() if isinstance(v, list)
                                    else round(v, 1)) for k, v in r.items()}
        print(f"{name[:16]:16s} " + " ".join(f"{v:6.0f}" for v in r["limited"])
              + f" {r['limited_none']:6.0f}   (drainage-limited)")
        print(f"{'':16s} " + " ".join(f"{v:6.0f}" for v in r["uncapped"])
              + f" {r['uncapped_none']:6.0f}   (no drainage limit)")

    world100 = out["regions"]["World"]["limited"][THRESHOLDS.index(100)]
    print(f"\ncheck: World drainage-limited under $100 = {world100:.0f} Mt "
          "(shipped headline 0.20 Gt; CHANGELOG 2026-09-01)")
    assert abs(world100 - 197) < 10, "supply curve no longer reproduces the shipped headline"

    (ROOT / "docs/supply_curve.json").write_text(json.dumps(out, indent=1))
    figure(out)
    return 0


def figure(out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    INK, INK2, GRID = "#1f2328", "#59636e", "#d8dee4"
    BLUE, ORANGE = "#2a78d6", "#eb6834"
    plt.rcParams.update({"font.family": "sans-serif",
                         "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
                         "font.size": 12, "pdf.fonttype": 42})
    W = out["regions"]["World"]
    x = np.array(out["thresholds_usd_per_tco2"], float)
    fig, ax = plt.subplots(figsize=(8, 5.2), dpi=200)
    fig.subplots_adjust(left=0.1, right=0.8, top=0.8, bottom=0.14)
    for key, col, lab in (("uncapped", ORANGE, "No drainage limit"),
                          ("limited", BLUE, "Drainage-limited\n(shipped default)")):
        y = np.array(W[key]) / 1000.0
        ax.plot(x, y, color=col, lw=2, marker="o", ms=5, zorder=3)
        none = W[key + "_none"] / 1000.0
        ax.axhline(none, color=col, lw=1, ls=(0, (3, 3)), zorder=2)
        ax.text(1080, none, f"{lab}\nno screen: {none:.2f}", color=INK, fontsize=10,
                va="center", ha="left")
    ax.axvline(100, color=INK2, lw=1, zorder=1)
    y100 = W["limited"][out["thresholds_usd_per_tco2"].index(100)] / 1000.0
    ax.annotate(f"\\$100 screen: {y100:.2f} Gt", (100, y100), xytext=(160, 0.07),
                fontsize=10, color=INK, arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
    ax.set_xscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels([f"\\${int(v)}" for v in x])
    ax.minorticks_off()
    ax.set_xlim(45, 1050)
    ax.set_ylim(0, None)
    ax.set_xlabel(r"Screen: rock purchase + haul (US\$ per tCO$_2$, discounted lifetime carbon)")
    ax.set_ylabel("Potential (GtCO$_2$ yr$^{-1}$)")
    ax.grid(axis="y", color=GRID, lw=0.8)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_color(GRID)
    ax.tick_params(colors=INK2)
    fig.text(0.1, 0.94, "How much ERW potential passes a cost screen", fontsize=15,
             fontweight="bold", color=INK, ha="left")
    fig.text(0.1, 0.875, "Global cropland, basalt, steady state, gross removal. The screen "
             "covers rock and trucking only:\nno grinding, spreading or MRV, and no quarry "
             "supply limit. A scenario at today's prices.",
             fontsize=10, color=INK2, ha="left", va="top", linespacing=1.4)
    for ext in ("png", "pdf"):
        fig.savefig(ROOT / f"docs/figures/erw_supply_curve.{ext}")
    print("wrote docs/figures/erw_supply_curve.{png,pdf}")


if __name__ == "__main__":
    raise SystemExit(main())
