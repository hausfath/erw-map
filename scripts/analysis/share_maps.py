"""Two standalone, shareable maps from the current build:

  docs/figures/erw_suitability_econ.png   suitability with economics ON (the
                                          viewer's landing layer), year-1 basis
  docs/figures/erw_weathered_year1.png    share of applied basalt weathered in
                                          the first year at the reference grind

  python3 scripts/analysis/share_maps.py [--region eu]

--region eu draws only EU27 + UK cropland on a European extent, with the
statistics in the captions computed over those cells; files get an _eu suffix.

Same arithmetic as the viewer: suitability is the piecewise value function of
gross removal (drainage-limited, year 1), multiplied by the delivered-cost
value function v = 1/(1 + haul/S) with the gate cancelling; the weathered
fraction is the shrinking-core dissolved fraction at the reference grind,
unbounded by the ceiling. Colours are the viewer's own ramps (build_v0.RAMP,
RAMP_FRAC). Every number in the captions is computed here.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import colors as mcolors  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from rasterio.enums import Resampling  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import constants as C  # noqa: E402
import kinetics as K  # noqa: E402
from build_v0 import RAMP, RAMP_FRAC, master_grid, onto_grid, piecewise  # noqa: E402
from analysis.paper_figures import LAND, Z, extent, AREA_W  # noqa: E402
import analysis.paper_figures as PF  # noqa: E402
from analysis.region_potential import EU27  # noqa: E402

REGIONS = {
    "world": {"title_where": "the world's cropland", "xlim": (-170, 180), "ylim": (-57, 74),
              "figsize": (13.5, 8.2), "suffix": "", "isos": None, "ax_rect": [0.01, 0.13, 0.98, 0.72],
              # caption statistics: an empty ocean corner (lower left, above the legend)
              "stats": {"x": 0.005, "ha": "left", "va": "bottom", "y1": 0.105, "y2": 0.06}},
    "eu": {"title_where": "cropland in the EU and UK", "xlim": (-12, 35), "ylim": (34, 71.5),
           "figsize": (10.5, 10.2), "suffix": "_eu", "isos": EU27 + ["GB"], "ax_rect": [0.01, 0.12, 0.98, 0.74],
           # the Barents Sea corner; the lower left is Iberia
           "stats": {"x": 0.995, "ha": "right", "va": "top", "y1": 0.99, "y2": 0.99}},
}
REGION = REGIONS[sys.argv[sys.argv.index("--region") + 1] if "--region" in sys.argv else "world"]
MASK = PF.MASK.copy()
if REGION["isos"]:
    from analysis.country_potential import country_raster
    _t, _w, _h, _crs = master_grid()
    _idx, _isos, _names = country_raster(_t, _w, _h)
    MASK &= np.isin(_idx, [_isos.index(i) + 1 for i in REGION["isos"] if i in _isos])

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/figures"
OUT.mkdir(parents=True, exist_ok=True)

INK, INK2, INK3 = "#141414", "#4f4f4c", "#8a8984"
NOCROP, LAND_EDGE, NEGLIGIBLE, SEA = "#efeeea", "#cfcdc7", "#8f8e89", "#ffffff"
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "text.color": INK, "savefig.dpi": 220,
})


def base(ax):
    ax.set_facecolor(SEA)
    ax.add_collection(PolyCollection(LAND, facecolors=NOCROP, edgecolors=LAND_EDGE,
                                     linewidths=0.3, zorder=0))
    ax.set_xlim(*REGION["xlim"]); ax.set_ylim(*REGION["ylim"])
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)


def wq(v, ps):
    g = np.isfinite(v)
    o = np.argsort(v[g]); w = AREA_W[MASK][g][o]
    cw = np.cumsum(w) / w.sum()
    return [float(np.interp(p, cw, v[g][o])) for p in ps]


def layers():
    transform, w, h, crs = master_grid()
    spec = C.FEEDSTOCK_ARCHETYPES[C.FEEDSTOCK_DEFAULT]
    ct = ((spec["CaO_wt"] / C.M_CAO + spec["MgO_wt"] / C.M_MGO)
          * 1000.0 * 2.0 * C.MOL_CO2_PER_KMOL_CHARGE_T)
    A = C.APPLICATION_RATE_T_HA_YR
    L1 = Z["L1"].astype("float64"); eta = np.nan_to_num(Z["eta"].astype("float64"))
    eta_tr = np.nan_to_num(Z["eta_tr"].astype("float64")); ceil_ = np.nan_to_num(Z["ceiling"].astype("float64"))
    d_ref = K.retreat_at_reference()
    ug = np.concatenate([[0.0], np.geomspace(1e-5, 12.0, 512)])
    gg = np.concatenate([[0.0], K.dissolved_fraction(ug[1:], C.PSD_REF_WIDTH)])
    u1 = d_ref * np.clip(np.nan_to_num(10.0 ** L1) * eta_tr, 0.0, None) / C.PSD_REF_D50_UM
    frac = np.interp(u1, ug, gg)
    cdr = np.minimum(frac * eta * A * ct, ceil_)
    suit_phys = piecewise(np.log10(np.maximum(cdr, 1e-9)),
                          [(np.log10(x), y) for x, y in C.CDR_SUITABILITY_KNOTS])
    suit_phys = np.where(cdr < C.CDR_NEGLIGIBLE_T_HA_YR, 0.0, suit_phys)
    cost = onto_grid(ROOT / "data/interim/feedstock_cost.tif", transform, w, h, crs,
                     resampling=Resampling.average).astype("float64")
    v_cost = np.clip(np.nan_to_num(C.cost_value(cost), nan=C.COST_FLOOR), C.COST_FLOOR, 1.0)
    suit = suit_phys * np.power(v_cost, C.COST_EXPONENT_DEFAULT)
    return frac, cdr, suit, A


def footer(fig, text):
    fig.text(0.012, 0.012, text, fontsize=8.5, color=INK3, ha="left", va="bottom")
    fig.text(0.988, 0.012, "hausfath.github.io/erw-map", fontsize=8.5, color=INK3,
             ha="right", va="bottom")


def suitability_map(suit, cdr, A):
    ramp = mcolors.LinearSegmentedColormap.from_list("atlas", RAMP)
    arr = np.full(suit.shape, np.nan); arr[MASK] = 100.0 * suit[MASK]
    neg = MASK & (cdr < C.CDR_NEGLIGIBLE_T_HA_YR)
    arr[neg] = np.nan
    fig = plt.figure(figsize=REGION["figsize"])
    ax = fig.add_axes(REGION["ax_rect"])
    base(ax)
    im = ax.imshow(np.ma.masked_invalid(arr), extent=extent(), origin="upper", cmap=ramp,
                   vmin=0, vmax=100, interpolation="nearest", zorder=2)
    ax.imshow(np.ma.masked_where(~neg, np.ones_like(arr)), extent=extent(), origin="upper",
              cmap=mcolors.ListedColormap([NEGLIGIBLE]), interpolation="nearest", zorder=3)
    fig.text(0.012, 0.955, "Where enhanced rock weathering makes the most sense"
             + (" in Europe" if REGION["suffix"] else ""),
             fontsize=22, fontweight="bold", color=INK, ha="left", va="top")
    fig.text(0.012, 0.905,
             f"Suitability of {REGION['title_where']} for basalt at {A:.0f} t/ha, with delivered rock cost. "
             "Score follows gross CO₂ removal per hectare, capped by what the drainage water can carry, "
             "then discounted by the haul from the nearest mafic quarry.",
             fontsize=11.5, color=INK2, ha="left", va="top", wrap=True)
    cax = fig.add_axes([0.30, 0.085, 0.40, 0.022])
    cb = fig.colorbar(im, cax=cax, orientation="horizontal", ticks=[0, 20, 40, 60, 80, 100])
    cb.outline.set_visible(False); cb.ax.tick_params(labelsize=9.5, colors=INK2, length=0)
    knots = ", ".join(f"{y * 100:.0f} = {x:g}" for x, y in C.CDR_SUITABILITY_KNOTS if y > 0)
    cb.set_label(f"Suitability, 0–100.  Score to gross removal: {knots} tCO₂/ha/yr",
                 fontsize=10, color=INK2)
    p50, p90 = wq(100.0 * suit[MASK], (0.5, 0.9))
    handles = [Patch(color=NEGLIGIBLE, label=f"Negligible removal, < {C.CDR_NEGLIGIBLE_T_HA_YR} tCO₂/ha/yr"),
               Patch(facecolor=NOCROP, edgecolor=LAND_EDGE, label="Not cropland")]
    ax.legend(handles=handles, loc="lower left", frameon=False, fontsize=9.5,
              bbox_to_anchor=(0.0, 0.0), handlelength=1.4)
    # Statistics sit above the legend in the empty ocean corner, never over land.
    st = REGION["stats"]
    ax.text(st["x"], st["y1"], f"{'EU + UK c' if REGION['suffix'] else 'C'}ropland median score {p50:.0f}, top decile above {p90:.0f}",
            transform=ax.transAxes, ha=st["ha"], va=st["va"], fontsize=9.5, color=INK2)
    footer(fig, f"ERW Atlas, build of {date.today():%d %b %Y}. Gross removal, not net; economics are "
                "acquisition and haul only. 0.1° grid, ~10–50 km effective resolution.")
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"erw_suitability_econ{REGION['suffix']}.{ext}", facecolor="white")
    plt.close(fig)
    print(f"suitability: median {p50:.1f}, p90 {p90:.1f}; negligible on "
          f"{100 * AREA_W[neg].sum() / AREA_W[MASK].sum():.1f}% of area")


def weathered_map(frac):
    ramp = mcolors.LinearSegmentedColormap.from_list("atlas_frac", RAMP_FRAC)
    top = C.FRAC_RAMP_MAX
    arr = np.full(frac.shape, np.nan); arr[MASK] = 100.0 * np.minimum(frac[MASK], top)
    fig = plt.figure(figsize=REGION["figsize"])
    ax = fig.add_axes(REGION["ax_rect"])
    base(ax)
    im = ax.imshow(np.ma.masked_invalid(arr), extent=extent(), origin="upper", cmap=ramp,
                   vmin=0, vmax=100 * top, interpolation="nearest", zorder=2)
    fig.text(0.012, 0.955, "How fast does crushed basalt weather?" + (" Europe" if REGION["suffix"] else ""),
             fontsize=22, fontweight="bold", color=INK, ha="left", va="top")
    fig.text(0.012, 0.905,
             f"Share of applied basalt (d50 {C.PSD_REF_D50_UM:.0f} µm) predicted to dissolve in the first "
             "year, from soil pH, monthly soil temperature and moisture, and drainage. Anchored to "
             f"{C.DISSOLVED_FRAC_AT_REF * 100:.0f}% at the reference condition by verified field deliveries.",
             fontsize=11.5, color=INK2, ha="left", va="top", wrap=True)
    cax = fig.add_axes([0.30, 0.085, 0.40, 0.022])
    ticks = np.linspace(0, 100 * top, 5)
    cb = fig.colorbar(im, cax=cax, orientation="horizontal", ticks=ticks)
    cb.ax.set_xticklabels([f"{t:.0f}%" if t < 100 * top - 1e-9 else f"≥ {t:.0f}%" for t in ticks])
    cb.outline.set_visible(False); cb.ax.tick_params(labelsize=9.5, colors=INK2, length=0)
    cb.set_label("Weathered in year 1, % of applied rock", fontsize=10, color=INK2)
    p10, p50, p90 = wq(100.0 * frac[MASK], (0.1, 0.5, 0.9))
    lo, hi = C.DISSOLVED_FRAC_OBSERVED_RANGE
    ax.legend(handles=[Patch(facecolor=NOCROP, edgecolor=LAND_EDGE, label="Not cropland")],
              loc="lower left", frameon=False, fontsize=9.5, bbox_to_anchor=(0.0, 0.0), handlelength=1.4)
    st = REGION["stats"]
    ax.text(st["x"], st["y2"], f"{'EU + UK c' if REGION['suffix'] else 'C'}ropland p10 / median / p90: {p10:.0f} / {p50:.0f} / {p90:.0f}%\n"
            f"Verified deliveries measured {lo * 100:.0f}–{hi * 100:.0f}% at their own grinds and sites",
            transform=ax.transAxes, ha=st["ha"], va=st["va"], fontsize=9.5, color=INK2, linespacing=1.4)
    footer(fig, f"ERW Atlas, build of {date.today():%d %b %Y}. Rock dissolving, not carbon leaving: "
                "not bounded by the drainage limit. 0.1° grid, ~10–50 km effective resolution.")
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"erw_weathered_year1{REGION['suffix']}.{ext}", facecolor="white")
    plt.close(fig)
    print(f"weathered: p10/p50/p90 {p10:.1f}/{p50:.1f}/{p90:.1f}%")


def main() -> int:
    frac, cdr, suit, A = layers()
    suitability_map(suit, cdr, A)
    weathered_map(frac)
    print(f"wrote {OUT}/erw_suitability_econ{REGION['suffix']}.png and erw_weathered_year1{REGION['suffix']}.png (+pdf)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
