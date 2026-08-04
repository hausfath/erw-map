"""Figure for the flux-reconciliation request-for-comment note.

Two panels, because the argument has two halves and they are different kinds of
claim:

  A  the concentration argument -- what the model requires against what the water
     can hold, with five independent literature anchors on the same log axis.
     This is the whole case in one image.
  B  the consequence that matters -- the ceiling falls with warming while the rate
     law rises, so imposing it removes the warm-climate gradient rather than
     merely rescaling the level.

Every number is computed from data/processed/v0_layers.npz and constants.py. No
literals in the plotting code except the published anchor intervals, which live in
constants.FLUX_CEILING_ANCHORS_MMOL_L.

Palette: dataviz categorical slots 1-3 (#2a78d6, #eb6834, #1baf7a), validated
colorblind-safe (worst adjacent deutan dE 9.2, normal-vision dE 27.6). Aqua sits
below 3:1 on a light surface, so every mark is directly labelled -- the relief rule.
"""
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import constants as C  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
NPZ = ROOT / "data/processed/v0_layers.npz"
OUT = ROOT / "docs/rfc_flux_reconciliation_fig.pdf"

BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
INK, MUTED, GRID = "#1a1a19", "#5b5b57", "#e3e3df"

z = np.load(NPZ, allow_pickle=True)
crop, area = z["crop"], z["area"]
# EXACTLY the build's cropland mask (build_v0.py), or the note quotes
# percentages that differ from the ones the build prints.
m = (crop >= C.CROPLAND_MIN_FRACTION) & np.isfinite(z["ph"])
w = (crop * area)[m].astype("float64")
unc = z["cdr_uncapped"][m].astype("float64")
ceil_t = z["ceiling"][m].astype("float64")
alk = z["alk_ceiling"][m].astype("float64")
q = z["q"][m].astype("float64")
tsoil = None
if "cdr" in z.files:
    pass


def wq(v, ps):
    o = np.argsort(v)
    cw = np.cumsum(w[o]) / w.sum()
    return [float(np.interp(p, cw, v[o])) for p in ps]


implied = unc * 1e6 / C.M_CO2_G_MOL / np.maximum(q * 1e7, 1e-9)   # mol/L
i10, i50, i90 = wq(implied * 1e3, (0.1, 0.5, 0.9))
a10, a50, a90 = wq(alk * 1e3, (0.1, 0.5, 0.9))

def fmt(v):
    """Plain decimals. 1.4e+02 has no place on a figure a reader must skim."""
    if v >= 100:
        return f"{v:,.0f}"
    if v >= 10:
        return f"{v:.0f}"
    if v >= 1:
        return f"{v:.1f}"
    return f"{v:.2f}"


fig, (axA, axB) = plt.subplots(
    2, 1, figsize=(8.4, 8.4), gridspec_kw={"height_ratios": [1.2, 1.0], "hspace": 0.60})

# ---------------------------------------------------------------- panel A
# Labels live in a left gutter as y-tick text, not floating above the marks. The
# first version drew them at y+0.4 and the label-to-bar mapping became ambiguous
# as soon as two rows sat close together.
anchors = C.FLUX_CEILING_ANCHORS_MMOL_L
rows = [
    ("What the model requires\n(unbounded, cropland p10–p90)", i10, i90, i50, BLUE),
    ("What the water can hold\n(calcite saturation, Ω = 1–10)", a10, a90, a50, ORANGE),
    ("Riverine transport capacity\n(Zhang et al. 2022, back-converted)",
     *anchors["Zhang 2022 riverine CTP, back-converted"], None, AQUA),
    ("Agricultural tile drainage, measured\n(Hamilton et al. 2007)",
     *anchors["Hamilton 2007 Midwest tile drainage / porewater"], None, AQUA),
    ("World rivers, 99th percentile\n(Meybeck)",
     *anchors["Meybeck pristine rivers, 99th percentile"], None, AQUA),
    ("Carbonate-terrain streams\n(Meybeck)",
     *anchors["Meybeck carbonate-terrain streams"], None, AQUA),
    ("Achieved in ERW field trials\n(observation, not a ceiling)",
     *anchors["field trials, ACHIEVED under ERW (not a ceiling)"], None, AQUA),
]

ys = np.arange(len(rows))[::-1]
for y, (lbl, lo, hi, mid, col) in zip(ys, rows):
    if hi - lo > 1e-9:
        axA.plot([lo, hi], [y, y], color=col, lw=6, solid_capstyle="round",
                 zorder=3, alpha=0.95)
        txt = f"{fmt(lo)}–{fmt(hi)}"
    else:
        axA.plot([lo], [y], "o", ms=8, color=col, zorder=3)
        txt = fmt(lo)
    if mid is not None:
        axA.plot([mid], [y], "o", ms=7.5, color=col, mec="#fcfcfb", mew=1.8, zorder=5)
        txt += f"   (median {fmt(mid)})"
    axA.text(hi * 1.35, y, txt, va="center", ha="left", fontsize=8.5, color=INK,
             zorder=4)

axA.set_yticks(ys)
axA.set_yticklabels([r[0] for r in rows], fontsize=8.6, color=INK, linespacing=1.35)
axA.set_xscale("log")
axA.set_xlim(0.07, 320)
axA.set_ylim(-0.7, len(rows) - 0.3)
axA.set_xlabel("Drainage-water bicarbonate concentration (mmol L$^{-1}$)", fontsize=9.5)
axA.tick_params(axis="x", labelsize=8.5, colors=MUTED, length=3)
axA.tick_params(axis="y", length=0)
axA.xaxis.label.set_color(INK)
for s_ in ("top", "right", "left"):
    axA.spines[s_].set_visible(False)
axA.spines["bottom"].set_color(GRID)
axA.grid(axis="x", color=GRID, lw=0.7, zorder=0)
axA.set_axisbelow(True)
axA.set_title("A   The model requires more bicarbonate than any measured water carries",
              fontsize=11, color=INK, loc="left", pad=12, fontweight="bold")

# ---------------------------------------------------------------- panel B
# Same temperature basis the build reports on, not air temperature.
tb = z["t_ceil_c"] if "t_ceil_c" in z.files else z["tair"]
tsel = tb[m].astype("float64")
bins = [(0, 10), (10, 15), (15, 20), (20, 25), (25, 45)]
names, u_med, c_med = [], [], []
for lo, hi in bins:
    b = (tsel >= lo) & (tsel < hi)
    if b.sum() < 100:
        continue
    ww = w[b]

    def med(v, b=b, ww=ww):
        o = np.argsort(v[b])
        return float(np.interp(0.5, np.cumsum(ww[o]) / ww.sum(), v[b][o]))
    names.append(f"{lo}–{hi}")
    u_med.append(med(unc))
    c_med.append(med(ceil_t))

y = np.arange(len(names))[::-1]
for yy, u, c in zip(y, u_med, c_med):
    axB.plot([c, u], [yy, yy], color=GRID, lw=2.6, solid_capstyle="round", zorder=2)
    axB.plot([u], [yy], "o", ms=8.5, color=BLUE, mec="#fcfcfb", mew=1.5, zorder=4)
    axB.plot([c], [yy], "o", ms=8.5, color=ORANGE, mec="#fcfcfb", mew=1.5, zorder=4)
    axB.text(u * 1.16, yy, f"{u / c:.1f}×", va="center", ha="left",
             fontsize=8.8, color=INK, zorder=5)

axB.set_yticks(y)
axB.set_yticklabels(names, fontsize=9, color=INK)
axB.set_ylabel("Mean soil temperature (°C)", fontsize=9.5, color=INK)
axB.set_xscale("log")
axB.set_xlim(0.09, 14)
axB.set_ylim(-0.75, len(names) - 0.25)
axB.set_xlabel("Gross CO$_2$ removal (t CO$_2$ ha$^{-1}$ yr$^{-1}$), area-weighted median",
               fontsize=9.5)
axB.xaxis.label.set_color(INK)
axB.tick_params(labelsize=8.5, colors=MUTED, length=3)
axB.tick_params(axis="y", length=0)
for s_ in ("top", "right", "left"):
    axB.spines[s_].set_visible(False)
axB.spines["bottom"].set_color(GRID)
axB.grid(axis="x", color=GRID, lw=0.7, zorder=0)
axB.set_axisbelow(True)
# Legend ABOVE the plotting area: inside it, it collided with the warmest row.
axB.legend(handles=[
    Line2D([], [], marker="o", ls="", ms=7.5, color=BLUE, mec="#fcfcfb",
           label="Model, unbounded"),
    Line2D([], [], marker="o", ls="", ms=7.5, color=ORANGE, mec="#fcfcfb",
           label="Drainage ceiling"),
], loc="lower left", bbox_to_anchor=(0.0, 1.005), ncol=2, frameon=False,
    fontsize=8.8, handletextpad=0.4, columnspacing=1.6)
wc_u, wc_c = u_med[-1] / u_med[0], c_med[-1] / c_med[0]
# The verb follows the number. On groundwater recharge wc_c was 0.91, so "removes"
# was right; on total runoff it is 1.41 and the gradient survives, much diminished.
_verb = ("reverses" if wc_c < 1.0
         else "removes most of" if wc_c < 0.5 * wc_u else "reduces")
axB.set_title(
    f"B   The ceiling falls with warming while the rate law rises, so imposing it\n"
    f"     {_verb} the warm-climate gradient: warmest/coolest {wc_u:.2f}× → {wc_c:.2f}×",
    fontsize=11, color=INK, loc="left", pad=30, fontweight="bold")

fig.savefig(OUT, bbox_inches="tight", facecolor="#fcfcfb")
print(f"wrote {OUT}")
print(f"  implied p10/p50/p90 = {i10:.1f}/{i50:.1f}/{i90:.1f} mmol/L")
print(f"  ceiling p10/p50/p90 = {a10:.2f}/{a50:.2f}/{a90:.2f} mmol/L")
print(f"  warm/cool: unbounded {wc_u:.2f}x, ceiling {wc_c:.2f}x")
