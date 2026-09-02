"""Figures for the ERL manuscript, drawn from the shipped build.

  python3 scripts/analysis/paper_figures.py [fig1 fig2 ...]

Every number on every panel is read from data/processed/v0_layers.npz and
scripts/constants.py at run time; nothing is typed in. Output goes to
paper/figures/ as PDF (vector, for submission) and PNG (300 dpi, for review).
Nothing here reads the private calibration dataset; the calibration panel takes
its (anonymised, cluster-level) inputs from constants.py aggregates only.

Conventions (docs: the dataviz method): one sequential hue for magnitude, a
fixed three-slot categorical order for identity, text in ink not series colour,
recessive axes, a legend whenever there is more than one series.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import colors as mcolors  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import constants as C  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "paper/figures"
OUT.mkdir(parents=True, exist_ok=True)

# ---- palette (reference instance of the dataviz method) -------------------
SEQ_BLUE = ["#cde2fb", "#b7d3f6", "#9ec5f4", "#86b6ef", "#6da7ec", "#5598e7",
            "#3987e5", "#2a78d6", "#256abf", "#1c5cab", "#184f95", "#104281",
            "#0d366b"]
CAT = {"blue": "#2a78d6", "orange": "#eb6834", "aqua": "#1baf7a"}
INK, INK2, INK3 = "#0b0b0b", "#52514e", "#8a8984"
NEGLIGIBLE = "#9a9994"
NOCROP = "#f4f3f0"
LAND_EDGE = "#c8c6c0"

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 7.5, "axes.titlesize": 8.5, "axes.labelsize": 7.5,
    "legend.fontsize": 7, "xtick.labelsize": 7, "ytick.labelsize": 7,
    "axes.edgecolor": INK3, "axes.linewidth": 0.5, "xtick.color": INK2,
    "ytick.color": INK2, "text.color": INK, "axes.labelcolor": INK2,
    "pdf.fonttype": 42, "savefig.dpi": 300,
})

# ---- data ------------------------------------------------------------------
Z = np.load(ROOT / "data/processed/v0_layers.npz", allow_pickle=True)
a, _, c, _, e, f = Z["transform"]
H, W = Z["crop"].shape
LON0, LON1 = c, c + a * W
LAT1, LAT0 = f, f + e * H
MASK = (Z["crop"] >= C.CROPLAND_MIN_FRACTION) & np.isfinite(Z["ph"]) & np.isfinite(Z["cdr"])
AREA_W = (Z["crop"] * Z["area"])


def land_polys():
    txt = (ROOT / "src/land.js").read_text()
    js = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
    polys = []
    for ft in js["features"]:
        g = ft["geometry"]
        rings = g["coordinates"] if g["type"] == "Polygon" else \
            [r for p in g["coordinates"] for r in p]
        for r in rings:
            polys.append(np.asarray(r))
    return polys


LAND = land_polys()


def draw_base(ax, lat_lo=-58, lat_hi=76):
    ax.set_facecolor("white")
    ax.add_collection(PolyCollection(LAND, facecolors=NOCROP, edgecolors=LAND_EDGE,
                                     linewidths=0.25, zorder=0))
    ax.set_xlim(-180, 180)
    ax.set_ylim(lat_lo, lat_hi)
    ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)


def extent():
    return (LON0, LON1, LAT0, LAT1)


def wq(v, ps):
    g = np.isfinite(v)
    o = np.argsort(v[g]); w = AREA_W[MASK][g][o]
    cw = np.cumsum(w) / w.sum()
    return [float(np.interp(p, cw, v[g][o])) for p in ps]


def panel_label(ax, s):
    ax.text(0.005, 0.99, s, transform=ax.transAxes, fontsize=9, fontweight="bold",
            va="top", ha="left", color=INK)


# ---- Figure 1: the map -----------------------------------------------------
def fig1():
    """Steady-state basis (hold A t/ha/yr; the footer and headline basis), so the
    binding fraction here matches Fig. 2 and the totals. The viewer's year-1 layer
    binds on a larger share of area; that figure goes to the SI."""
    v = steady_state_vectors()
    A = C.APPLICATION_RATE_T_HA_YR
    ss_unc = np.full(Z["crop"].shape, np.nan); ss_unc[MASK] = A * v["per_t"]
    ss_cap = np.full(Z["crop"].shape, np.nan); ss_cap[MASK] = np.minimum(A * v["per_t"], v["ceil"])
    cdr = ss_cap
    neg = MASK & (ss_cap < C.CDR_NEGLIGIBLE_T_HA_YR)
    # The viewer's own ramp (build_v0.RAMP, viridis-like, colour-blind safe), in
    # discrete bins so the legend reads as ranges rather than a log axis.
    from build_v0 import RAMP
    ramp = mcolors.LinearSegmentedColormap.from_list("atlas", RAMP)
    bounds = [C.CDR_NEGLIGIBLE_T_HA_YR, 0.1, 0.25, 0.5, 1.0, 2.0, C.CDR_SUITABILITY_TOP_T_HA_YR]
    cmap = mcolors.ListedColormap([ramp(x) for x in np.linspace(0.05, 0.98, len(bounds) - 1)])
    norm = mcolors.BoundaryNorm(bounds, cmap.N)

    # limiting class: 0 drainage cannot carry it, 1 reactivity, 2 eta_DIC / eta_tr
    L1 = Z["L1"]; eta = np.nan_to_num(Z["eta"], nan=1.0); etr = np.nan_to_num(Z["eta_tr"], nan=1.0)
    contrib = np.stack([L1, np.log10(np.maximum(eta, 1e-9)), np.log10(np.maximum(etr, 1e-9))])
    lowest = np.nanargmin(np.nan_to_num(contrib, nan=np.inf), axis=0)
    binds = ss_unc > Z["ceiling"] * 1.000001
    cls = np.where(binds, 0, np.where(lowest == 0, 1, 2)).astype(float)
    cls[~MASK | neg] = np.nan
    w = AREA_W[MASK & ~neg]
    shares = [100 * AREA_W[MASK & ~neg & (cls == k)].sum() / w.sum() for k in (0, 1, 2)]
    cat_cmap = mcolors.ListedColormap([CAT["blue"], CAT["orange"], CAT["aqua"]])

    fig, axes = plt.subplots(2, 1, figsize=(6.7, 6.3))
    ax = axes[0]
    draw_base(ax)
    im = ax.imshow(np.ma.masked_invalid(cdr), extent=extent(), origin="upper",
                   cmap=cmap, norm=norm, interpolation="nearest", zorder=2)
    ax.imshow(np.ma.masked_where(~neg, np.ones_like(cdr)), extent=extent(), origin="upper",
              cmap=mcolors.ListedColormap([NEGLIGIBLE]), interpolation="nearest", zorder=3)
    cb = fig.colorbar(im, ax=ax, orientation="horizontal", fraction=0.045, pad=0.02,
                      aspect=45, ticks=bounds, spacing="uniform")
    cb.ax.set_xticklabels([f"{b:g}" for b in bounds])
    cb.set_label("Gross CO$_2$ removal with the drainage limit, tCO$_2$ ha$^{-1}$ yr$^{-1}$ "
                 f"(at {C.APPLICATION_RATE_T_HA_YR:.0f} t ha$^{{-1}}$ basalt; steady state)",
                 color=INK2)
    cb.outline.set_visible(False)
    p50, p90 = wq(ss_cap[MASK], (0.5, 0.9))
    ax.text(0.995, 0.02, f"cropland median {p50:.2f}, p90 {p90:.2f}; "
            f"< {C.CDR_NEGLIGIBLE_T_HA_YR} shown grey",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=6.5, color=INK2)
    panel_label(ax, "a")

    ax = axes[1]
    draw_base(ax)
    ax.imshow(np.ma.masked_invalid(cls), extent=extent(), origin="upper", cmap=cat_cmap,
              vmin=-0.5, vmax=2.5, interpolation="nearest", zorder=2)
    ax.imshow(np.ma.masked_where(~neg, np.ones_like(cdr)), extent=extent(), origin="upper",
              cmap=mcolors.ListedColormap([NEGLIGIBLE]), interpolation="nearest", zorder=3)
    handles = [
        Patch(color=CAT["blue"], label=f"export capped by drainage ({shares[0]:.0f}% of area)"),
        Patch(color=CAT["orange"], label=f"dissolution rate (pH, temperature, moisture) ({shares[1]:.0f}%)"),
        Patch(color=CAT["aqua"], label=f"acid-soil efficiency or slow-drainage rate term ({shares[2]:.0f}%)"),
        Patch(color=NEGLIGIBLE, label=f"negligible, < {C.CDR_NEGLIGIBLE_T_HA_YR} tCO$_2$ ha$^{{-1}}$ yr$^{{-1}}$"),
    ]
    ax.legend(handles=handles, loc="lower left", frameon=False, ncol=2,
              bbox_to_anchor=(0.0, -0.16), handlelength=1.2, columnspacing=1.5)
    panel_label(ax, "b")
    fig.subplots_adjust(left=0.01, right=0.99, top=0.995, bottom=0.07, hspace=0.12)
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"fig1_map.{ext}", bbox_inches="tight")
    plt.close(fig)
    print(f"fig1: shares drainage/reactivity/other = {shares[0]:.1f}/{shares[1]:.1f}/{shares[2]:.1f}%")


# ---- helpers shared by figs 2-3 ------------------------------------------------
def steady_state_vectors():
    """Per-cell steady-state uncapped removal (t/ha/yr) at rate A, the ceiling,
    and area weights, on the cropland mask -- the footer basis."""
    import kinetics as K
    spec = C.FEEDSTOCK_ARCHETYPES[C.FEEDSTOCK_DEFAULT]
    ct = ((spec["CaO_wt"] / C.M_CAO + spec["MgO_wt"] / C.M_MGO)
          * 1000.0 * 2.0 * C.MOL_CO2_PER_KMOL_CHARGE_T)
    d_ref = K.retreat_at_reference()
    ug = np.concatenate([[0.0], np.geomspace(1e-5, 200.0, 900)])
    gg = np.concatenate([[0.0], K.dissolved_fraction(ug[1:], C.PSD_REF_WIDTH)])
    i_inf = float(np.trapezoid(1.0 - gg, ug))
    L1 = Z["L1"][MASK].astype("float64")
    eta = np.nan_to_num(Z["eta"][MASK].astype("float64"))
    etr = np.nan_to_num(Z["eta_tr"][MASK].astype("float64"))
    u1 = d_ref * np.clip(10.0 ** L1 * etr, 0, None) / C.PSD_REF_D50_UM
    per_t = np.minimum(1.0, u1 / i_inf) * eta * ct          # tCO2 per t rock, steady state
    ceil = np.nan_to_num(Z["ceiling"][MASK].astype("float64"))
    q = np.clip(np.nan_to_num(Z["q"][MASK].astype("float64")), 0, None)
    ha = AREA_W[MASK] * 100.0
    return dict(per_t=per_t, ceil=ceil, q=q, ha=ha, eta=eta, u1=u1, i_inf=i_inf, ct=ct)


def fig2():
    """Where and how the drainage limit binds (steady-state basis)."""
    v = steady_state_vectors()
    A = C.APPLICATION_RATE_T_HA_YR
    unc = A * v["per_t"]; cap = np.minimum(unc, v["ceil"]); ha = v["ha"]
    fig, axes = plt.subplots(1, 3, figsize=(6.7, 2.6),
                             gridspec_kw=dict(width_ratios=[1.25, 1.0, 1.0]))

    def wmean(x, sel):
        return float(np.sum(x[sel] * ha[sel]) / ha[sel].sum())

    # (a) removal by drainage decile, grouped bars, linear axis
    ax = axes[0]
    q = v["q"] * 1000.0
    o = np.argsort(q); cw = np.cumsum(ha[o]) / ha.sum()
    edges = [float(np.interp(p, cw, q[o])) for p in np.linspace(0, 1, 11)]
    mu, mc, labels = [], [], []
    for i in range(10):
        sel = (q >= edges[i]) & ((q < edges[i + 1]) if i < 9 else (q <= edges[i + 1]))
        mu.append(wmean(unc, sel)); mc.append(wmean(cap, sel))
        labels.append(f"{edges[i]:.0f}–{edges[i + 1]:.0f}")
    xs = np.arange(10); bw = 0.38
    ax.bar(xs - bw / 2, mu, bw, color=CAT["orange"], label="rate law only")
    ax.bar(xs + bw / 2, mc, bw, color=CAT["blue"], label="with drainage limit")
    for i in range(10):
        ax.text(xs[i], max(mu[i], mc[i]) + 0.04, f"{100 * mc[i] / mu[i]:.0f}%", ha="center",
                va="bottom", fontsize=5.8, color=INK2)
    ax.set_xticks(xs); ax.set_xticklabels(labels, rotation=60, ha="right", fontsize=5.8)
    ax.set_xlabel("Drainage decile of cropland, mm yr$^{-1}$")
    ax.set_ylabel("Gross removal, tCO$_2$ ha$^{-1}$ yr$^{-1}$\n(area-weighted mean)")
    ax.legend(frameon=False, loc="upper left", handlelength=1.2)
    ax.text(0.02, 0.74, "labels: share of the rate-law\nremoval the drainage can carry",
            transform=ax.transAxes, fontsize=5.8, color=INK2, va="top")
    ax.set_ylim(0, max(mu) * 1.18)
    panel_label(ax, "a")

    # (b) what the limit does to the climate gradients
    ax = axes[1]
    t = Z["tair"][MASK].astype("float64")

    def tail(key, top):
        oo = np.argsort(key); c2 = np.cumsum(ha[oo]) / ha.sum()
        return oo[c2 >= 0.95] if top else oo[c2 <= 0.05]

    groups = [("driest 5%", tail(q, False)), ("wettest 5%", tail(q, True)),
              ("coolest 5%", tail(t, False)), ("warmest 5%", tail(t, True))]
    xs = np.array([0.0, 1.0, 2.6, 3.6]); bw = 0.38
    gu = [wmean(unc, g) for _, g in groups]; gc = [wmean(cap, g) for _, g in groups]
    ax.bar(xs - bw / 2, gu, bw, color=CAT["orange"], label="rate law only")
    ax.bar(xs + bw / 2, gc, bw, color=CAT["blue"], label="with drainage limit")
    ax.set_xticks(xs); ax.set_xticklabels([g[0] for g in groups], rotation=30, ha="right", fontsize=6.2)
    ymax = max(gu + gc)
    for (i0, i1, lab) in ((0, 1, "wet ÷ dry"), (2, 3, "warm ÷ cool")):
        ax.text((xs[i0] + xs[i1]) / 2, ymax * 1.06,
                f"{lab}\nrate law {gu[i1] / gu[i0]:.0f}×\nlimited {gc[i1] / gc[i0]:.0f}×",
                ha="center", va="bottom", fontsize=6.0, color=INK2, linespacing=1.15)
    ax.set_ylim(0, ymax * 1.45)
    ax.set_ylabel("Gross removal, tCO$_2$ ha$^{-1}$ yr$^{-1}$")
    panel_label(ax, "b")

    # (c) global total vs application rate
    ax = axes[2]
    rates = np.linspace(5, 60, 23)
    g_unc = [np.sum(r * v["per_t"] * ha) / 1e9 for r in rates]
    g_cap = [np.sum(np.minimum(r * v["per_t"], v["ceil"]) * ha) / 1e9 for r in rates]
    ax.plot(rates, g_unc, color=CAT["orange"], lw=1.6, label="rate law only")
    ax.plot(rates, g_cap, color=CAT["blue"], lw=1.6, label="with drainage limit")
    ax.axvline(A, color=INK3, lw=0.6, ls=":")
    i30 = int(np.argmin(np.abs(rates - A))); i45 = int(np.argmin(np.abs(rates - 45)))
    gain = 100 * (g_cap[i45] / g_cap[i30] - 1)
    ax.annotate(f"+50% rock gives\n+{gain:.0f}% carbon", xy=(45, g_cap[i45]),
                xytext=(47, 0.22), fontsize=6.2, color=INK2, ha="center",
                arrowprops=dict(arrowstyle="-", color=INK3, lw=0.6))
    ax.set_xlabel("Application rate, t ha$^{-1}$ yr$^{-1}$")
    ax.set_ylabel("Global gross removal, GtCO$_2$ yr$^{-1}$")
    ax.set_ylim(0, None)
    ax.legend(frameon=False, loc="upper left", handlelength=1.6)
    ax.grid(True, color="#e6e5e1", lw=0.5); ax.set_axisbelow(True)
    panel_label(ax, "c")

    for ax in axes:
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    fig.tight_layout(w_pad=1.0)
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"fig2_limit.{ext}", bbox_inches="tight")
    plt.close(fig)
    binds = 100 * ha[unc > v["ceil"] * 1.000001].sum() / ha.sum()
    print(f"fig2: binds {binds:.1f}%; wet/dry {gu[1] / gu[0]:.1f}x -> {gc[1] / gc[0]:.1f}x; "
          f"warm/cool {gu[3] / gu[2]:.1f}x -> {gc[3] / gc[2]:.1f}x; +50% rock -> +{gain:.1f}%")


def fig3():
    """Economics: delivered cost vs haul, and the supply curve."""
    import rasterio
    from rasterio.enums import Resampling
    sys.path.insert(0, str(ROOT / "scripts/analysis"))
    import country_potential as CP
    import kinetics as K
    v = steady_state_vectors()
    A = C.APPLICATION_RATE_T_HA_YR
    transform, w, h, crs = CP.master_grid()
    rate = CP.onto_grid(CP.INTERIM / "truck_rate.tif", transform, w, h, crs,
                        resampling=Resampling.nearest).astype("float64")[MASK]
    cost = CP.onto_grid(CP.INTERIM / "feedstock_cost.tif", transform, w, h, crs,
                        resampling=Resampling.average).astype("float64")[MASK]
    basis = CP.onto_grid(CP.INTERIM / "cost_basis.tif", transform, w, h, crs,
                         resampling=Resampling.nearest).astype("float64")[MASK]
    haul_km = np.maximum(cost - C.FEEDSTOCK_GATE_COST_USD_T, 0.0) / np.maximum(rate, 1e-9) \
        - C.HAUL_FIXED_KM_EQUIV
    # lifetime-discounted carbon per hectare for the unit-cost screen (variant B)
    d_ref = K.retreat_at_reference()
    ug = np.concatenate([[0.0], np.geomspace(1e-5, 200.0, 900)])
    gg = np.concatenate([[0.0], K.dissolved_fraction(ug[1:], C.PSD_REF_WIDTH)])
    dr = C.COST_SCREEN_DISCOUNT_RATE
    u1g = np.concatenate([[0.0], np.geomspace(1e-7, 20.0, 600)]); Dg = np.zeros_like(u1g); prev = np.zeros_like(u1g)
    for t in range(1, 61):
        cum = np.interp(u1g * t, ug, gg); Dg += (cum - prev) / (1 + dr) ** t; prev = cum
    dpt = v["eta"] * v["ct"] * A * np.interp(v["u1"], u1g, Dg)
    unit = cost * A / np.maximum(dpt, 1e-12)        # $/tCO2, gross, unlevelised
    cap = np.minimum(A * v["per_t"], v["ceil"]); ha = v["ha"]
    ok = np.isfinite(cost) & np.isfinite(haul_km) & (dpt > 0)

    fig, axes = plt.subplots(1, 2, figsize=(6.7, 2.7))
    # (a) delivered cost vs haul, area-weighted density
    ax = axes[0]
    from build_v0 import RAMP
    ymax = 150.0
    above = 100 * ha[ok & (cost > ymax)].sum() / ha[ok].sum()
    hb = ax.hexbin(haul_km[ok], np.minimum(cost[ok], ymax), C=ha[ok] / 1e6, reduce_C_function=np.sum,
                   gridsize=(44, 26), bins="log",
                   cmap=mcolors.LinearSegmentedColormap.from_list(
                       "atlas_w", [(0.0, "#ffffff")] + [(max(t, 0.02), c) for t, c in RAMP]),
                   mincnt=1, linewidths=0.1, extent=(0, 1500, 10, ymax))
    cb = fig.colorbar(hb, ax=ax, fraction=0.05, pad=0.02)
    cb.set_label("cropland, Mha per bin (log)", color=INK2); cb.outline.set_visible(False)
    ax.axhline(C.FEEDSTOCK_GATE_COST_USD_T, color=INK3, lw=0.6, ls=":")
    ax.text(1480, C.FEEDSTOCK_GATE_COST_USD_T * 1.08, f"gate \\${C.FEEDSTOCK_GATE_COST_USD_T:.0f}/t",
            ha="right", va="bottom", fontsize=6.5, color=INK2)
    reg = 100 * ha[ok & (basis == 1)].sum() / ha[ok].sum()
    ax.text(0.03, 0.95, f"registered quarry sets the haul on {reg:.0f}% of area;\nmapped mafic outcrop elsewhere",
            transform=ax.transAxes, ha="left", va="top", fontsize=6.5, color=INK2)
    ax.set_xlabel("Effective haul to nearest feedstock, km")
    ax.set_ylabel("Delivered rock cost, US\\$ per t")
    ax.set_xlim(0, 1500); ax.set_ylim(0, ymax * 1.02)
    ax.text(1480, 2, f"{above:.0f}% of area above {ymax:.0f} USD/t, clipped to the top row", ha="right",
            va="bottom", fontsize=6.2, color=INK2)
    panel_label(ax, "a")

    # (b) supply curve: drainage-limited potential vs $/tCO2, world + top countries
    ax = axes[1]
    idx, isos, names = CP.country_raster(transform, w, h)
    idxv = idx[MASK].astype(int)
    def curve(sel):
        u = unit[sel]; c = cap[sel] * ha[sel] / 1e9
        oo = np.argsort(u); return u[oo], np.cumsum(c[oo])
    x, y = curve(ok)
    ax.plot(x, y, color=INK, lw=1.6, label="World")
    picks = [("IN", "India", CAT["blue"]), ("BR", "Brazil", CAT["orange"]), ("US", "United States", CAT["aqua"])]
    for iso, lab, col in picks:
        if iso in isos:
            sel = ok & (idxv == isos.index(iso) + 1)
            x2, y2 = curve(sel); ax.plot(x2, y2, color=col, lw=1.3, label=lab)
    ax.axvline(C.COST_SCREEN_USD_PER_TCO2, color=INK2, lw=0.8, ls="--")
    at100 = float(np.interp(C.COST_SCREEN_USD_PER_TCO2, x, y))
    ax.text(C.COST_SCREEN_USD_PER_TCO2 * 1.05, at100, f"{at100:.2f} Gt under \\${C.COST_SCREEN_USD_PER_TCO2:.0f}",
            fontsize=6.5, color=INK2, va="bottom")
    ax.set_xlim(0, 500)
    tot = float(y[-1]); at500 = float(np.interp(500.0, x, y))
    ax.text(495, at500 * 0.98, f"{100 * (tot - at500) / tot:.0f}% of the limited potential\ncosts more than 500 USD",
            ha="right", va="top", fontsize=6.2, color=INK2)
    ax.set_xlabel("Delivered rock cost per gross tCO$_2$, US\\$ (unlevelised)")
    ax.set_ylabel("Cumulative drainage-limited\npotential, GtCO$_2$ yr$^{-1}$")
    ax.legend(frameon=False, loc="upper left", handlelength=1.6)
    ax.grid(True, color="#e6e5e1", lw=0.5); ax.set_axisbelow(True)
    panel_label(ax, "b")
    for ax in axes:
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
    fig.tight_layout(w_pad=1.5)
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"fig3_economics.{ext}", bbox_inches="tight")
    plt.close(fig)
    print(f"fig3: registered basis {reg:.1f}% of area; world under $100: {at100:.3f} Gt")


FIGS = {"fig1": fig1, "fig2": fig2, "fig3": fig3}



def fig4():
    """Country potentials (ensemble) and the field calibration (anonymised)."""
    import json
    cj = PAPER / "country_ensemble.json"
    kj = PAPER / "calibration_clusters.json"
    sj = PAPER / "calibration_shape.json"
    import kinetics as K
    fig = plt.figure(figsize=(6.7, 5.4))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.35, 1.0], hspace=0.55, wspace=0.35)
    ax = fig.add_subplot(gs[0, :])
    if cj.exists():
        J = json.loads(cj.read_text())
        rows = [r for r in J["rows"] if r["name"] not in ("WORLD",)]
        rows = sorted(rows, key=lambda r: (r["name"] == "Rest of world", -r["tech_un"][1]))
        names = [r["name"].replace("United States of America", "United States") for r in rows]
        keys = [("tech_un", "rate law only", CAT["orange"], 0.0),
                ("tech_cap", "with drainage limit", CAT["blue"], 0.0),
                ("econ_cap", f"limited, delivered rock under {J['screen_usd_per_tco2']:.0f} USD per tCO$_2$", "#0d366b", 0.0)]
        n = len(rows); ys = np.arange(n)[::-1]; bh = 0.26
        for j, (k, lab, col, _) in enumerate(keys):
            p5 = np.array([r[k][0] for r in rows]); p50 = np.array([r[k][1] for r in rows]); p95 = np.array([r[k][2] for r in rows])
            yy = ys + (1 - j) * bh
            ax.barh(yy, p50, bh * 0.92, color=col, label=lab)
            ax.errorbar(p50, yy, xerr=[p50 - p5, p95 - p50], fmt="none", ecolor=INK2, elinewidth=0.6, capsize=1.5)
        ax.set_yticks(ys); ax.set_yticklabels(names, fontsize=7)
        ax.set_xlabel(f"Steady-state gross removal, MtCO$_2$ yr$^{{-1}}$ (p50; whiskers p5–p95 over {J['n_draws']:,} draws)")
        ax.legend(frameon=False, loc="upper right", handlelength=1.2, bbox_to_anchor=(1.0, 0.92))
        ax.grid(True, axis="x", color="#e6e5e1", lw=0.5); ax.set_axisbelow(True)
        gaps = {"China", "Turkey"}
        for i, nm in enumerate(names):
            if nm in gaps:
                ax.text(-0.01, ys[i], "†", transform=ax.get_yaxis_transform(), ha="right", va="center", fontsize=7, color=INK2)
        ax.text(0.995, -0.30, "† no quarry register: delivered cost from mapped outcrop only.  "
                "Intervals are common-mode across countries (same draws) and must not be added.",
                transform=ax.transAxes, ha="right", va="top", fontsize=5.8, color=INK2)
    else:
        ax.text(0.5, 0.5, "country_ensemble.json missing", ha="center", transform=ax.transAxes)
    panel_label(ax, "a")

    # (b) cluster multipliers vs grind
    ax = fig.add_subplot(gs[1, 0])
    if kj.exists():
        K_ = json.loads(kj.read_text())
        for c in K_["clusters"]:
            known = c["grind_known"]
            x = c["d50_um"] if known else C.PSD_REF_D50_UM
            col = CAT["blue"] if known else INK3
            ax.errorbar(x, c["k"], yerr=[[c["k"] - c["k_lo"]], [c["k_hi"] - c["k"]]], fmt="o", ms=5,
                        color=col, ecolor=col, elinewidth=0.9, capsize=2.5)
            ax.annotate(f"{c['cluster']}" + ("" if known else "  (grind undisclosed;\n     upper bound, drawn at ref. d50)"),
                        (x, c["k"]), xytext=(6, 4) if known else (8, -20), textcoords="offset points", fontsize=6.2, color=INK2,
                        ha="left")
        ax.axhline(1.0, color=INK3, lw=0.7, ls="--")
        ax.text(0.98, 0.03, "k = 1: the shipped anchor reproduces the delivery\n(anchor = median k of the known-grind clusters)",
                transform=ax.transAxes, ha="right", va="bottom", fontsize=5.8, color=INK2)
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_xticks([50, 100, 200, 400, 800]); ax.set_xticklabels(["50", "100", "200", "400", "800"])
        ax.set_yticks([0.1, 0.2, 0.5, 1, 2, 5]); ax.set_yticklabels(["0.1", "0.2", "0.5", "1", "2", "5"]); ax.set_ylim(0.08, 6)
        ax.set_xlabel("Supplier feedstock d50, µm"); ax.set_ylabel("Dissolution multiplier k\n(relative to the shipped anchor)")
    panel_label(ax, "b")

    # (c) the re-sampled field vs shrinking-core predictions
    ax = fig.add_subplot(gs[1, 1])
    if sj.exists():
        S = json.loads(sj.read_text())
        t1, f1, t2, f2 = S["t1_days"], S["fw1"], S["t2_days"], S["fw2"]
        ug = np.concatenate([[0.0], np.geomspace(1e-5, 200.0, 1500)])
        tt = np.linspace(0, 400, 200)
        for n, col in ((0.7, "#9ec5f4"), (1.5, CAT["blue"]), (2.5, "#0d366b")):
            gg = np.concatenate([[0.0], K.dissolved_fraction(ug[1:], n)])
            u1 = float(np.interp(f1, gg, ug))
            ax.plot(tt, 100 * np.interp(u1 * tt / t1, ug, gg), color=col, lw=1.3, label=f"shrinking core, width {n}")
        k1 = -np.log(1 - f1) / t1
        ax.plot(tt, 100 * (1 - np.exp(-k1 * tt)), color=CAT["orange"], lw=1.1, ls="--", label="first-order")
        ax.plot([t1, t2], [100 * f1, 100 * f2], "o", color=INK, ms=5, zorder=5, label="observed (same fields)")
        ax.annotate("second sampling", (t2, 100 * f2), xytext=(6, -12), textcoords="offset points", fontsize=6.2, color=INK2)
        ax.set_xlabel("Days after application"); ax.set_ylabel("Fraction weathered, %")
        ax.set_xlim(0, 400); ax.set_ylim(0, 70)
        ax.legend(frameon=False, loc="upper left", fontsize=6, handlelength=1.4)
    panel_label(ax, "c")
    for a_ in fig.axes:
        for sp in ("top", "right"):
            a_.spines[sp].set_visible(False)
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"fig4_country_calibration.{ext}", bbox_inches="tight")
    plt.close(fig)
    print("fig4 done")


PAPER = ROOT / "paper"
FIGS["fig4"] = fig4

if __name__ == "__main__":
    which = sys.argv[1:] or list(FIGS)
    for k in which:
        FIGS[k]()
        print("wrote", OUT / k)
