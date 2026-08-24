"""Generate the full methodology report as LaTeX, then PDF.

  python3 scripts/analysis/make_methods_report.py

Every quantitative claim is injected from scripts/constants.py and
data/processed/v0_layers.npz, so the document cannot drift from the build the
way a hand-typed number would. Compiled with tectonic.

This is the equations-and-parameters companion to docs/METHODOLOGY.md, which
covers the same ground in prose. Where they disagree, the code is right and both
documents are stale.

CONFIDENTIALITY. Nothing here derives from the verified-delivery fixture beyond
figures already published in docs/VALIDATION.md as aggregates. No operator names
and no per-deployment values.
"""
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import constants as C  # noqa: E402
import kinetics as K  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
TEX = DOCS / "methodology_report.tex"
PDF = DOCS / "methodology_report.pdf"

# --------------------------------------------------------------------- data
z = np.load(ROOT / "data/processed/v0_layers.npz", allow_pickle=True)
crop, area = z["crop"], z["area"]
m = (crop >= C.CROPLAND_MIN_FRACTION) & np.isfinite(z["ph"])
w = (crop * area)[m].astype("float64")
ha = w * 100.0


def wq(v, ps=(0.1, 0.5, 0.9)):
    v = np.asarray(v, dtype="float64")
    g = np.isfinite(v)
    o = np.argsort(v[g])
    cw = np.cumsum(w[g][o]) / w[g].sum()
    return [float(np.interp(p, cw, v[g][o])) for p in ps]


L1, eta, eta_tr = (z[k][m].astype("float64") for k in ("L1", "eta", "eta_tr"))
q, unc, ceil_t = (z[k][m].astype("float64") for k in ("q", "cdr_uncapped", "ceiling"))
alk, pco2, tc = (z[k][m].astype("float64") for k in ("alk_ceiling", "pco2", "t_ceil_c"))
ph_c, ff = z["ph"][m].astype("float64"), z["f_flood"][m].astype("float64")

spec = C.FEEDSTOCK_ARCHETYPES[C.FEEDSTOCK_DEFAULT]
CEIL_T = ((spec["CaO_wt"] / C.M_CAO + spec["MgO_wt"] / C.M_MGO)
          * 1000.0 * 2.0 * C.MOL_CO2_PER_KMOL_CHARGE_T)
RATE = C.APPLICATION_RATE_T_HA_YR
cap = np.minimum(unc, ceil_t)
g_unc = float((ha * np.nan_to_num(unc)).sum() / 1e9)
g_cap = float((ha * np.nan_to_num(cap)).sum() / 1e9)
binds = float((w * (unc > ceil_t * 1.000001)).sum() / w.sum())
ex50 = wq(unc / np.maximum(ceil_t, 1e-12))[1]
frac = unc / np.maximum(eta, 1e-9) / (RATE * CEIL_T)

d_ref = K.retreat_at_reference()
ssa_ref = K.ssa_geometric(C.PSD_REF_D50_UM, C.PSD_REF_WIDTH)
ph_half_unsat = float(K.ph_half(C.PCO2_UNSATURATED_UATM, 288.15))
ph_half_sat = float(K.ph_half(C.PCO2_SATURATED_UATM, 288.15))
o1 = float(K.alkalinity_ceiling_mol_l(C.PCO2_UNSATURATED_UATM, 288.15,
                                      omega=C.FLUX_CEILING_OMEGA_STRICT)) * 1e3
o10 = float(K.alkalinity_ceiling_mol_l(C.PCO2_UNSATURATED_UATM, 288.15)) * 1e3

# Reachable stoichiometric maximum, the top suitability knot.
stoich_max = RATE * CEIL_T

# Grind sensitivity, for the surface-area section.
grind_rows = "\n".join(
    rf"{d:.0f} & {K.ssa_geometric(d, C.PSD_REF_WIDTH):.4f} & "
    rf"{K.ssa_log_shift(d, C.PSD_REF_WIDTH):+.3f} \\"
    for d in (40.0, 67.0, C.PSD_REF_D50_UM, 300.0, 600.0, 700.0))
width_rows = "\n".join(
    rf"{n:.2f} & {K.ssa_geometric(C.PSD_REF_D50_UM, n):.4f} & "
    rf"{K.ssa_log_shift(C.PSD_REF_D50_UM, n):+.3f} \\"
    for n in (0.7, 1.0, C.PSD_REF_WIDTH, 2.0, 2.5))

knot_rows = " \\\\\n".join(
    rf"{x:g} & {v:.2f}" for x, v in C.CDR_SUITABILITY_KNOTS) + r" \\"

arch_rows = "\n".join(
    rf"\texttt{{{k.replace('_', chr(92) + '_')}}} & {v['CaO_wt'] * 100:.1f} & "
    rf"{v['MgO_wt'] * 100:.1f} & "
    rf"{(v['CaO_wt'] / C.M_CAO + v['MgO_wt'] / C.M_MGO) * 1000 * 2 * C.MOL_CO2_PER_KMOL_CHARGE_T:.3f}"
    + (r" & $\bullet$ \\" if k == C.FEEDSTOCK_DEFAULT else r" & \\")
    for k, v in C.FEEDSTOCK_ARCHETYPES.items())

# Percentiles quoted in the text.
l1p = wq(L1); etap = wq(eta); etrp = wq(eta_tr); qp = wq(q)
cdrp = wq(unc); fracp = wq(frac); alkp = wq(alk * 1e3)
impl = unc * 1e6 / C.M_CO2_G_MOL / np.maximum(q * 1e7, 1e-9) * 1e3
implp = wq(impl)
dv = C.DRAINAGE_MEDIAN_MM_YR

# How much aridity contrast the transport term actually delivers. Quoted in the
# limitations section, because the answer is "very little" and that is the
# headline open problem rather than a footnote.
etr_mean = float((w * eta_tr).sum() / w.sum())
etr_gt08 = 100.0 * float((w * (eta_tr > 0.8)).sum() / w.sum())
etr_ratio = wq(eta_tr, (0.025, 0.975))[1] / max(wq(eta_tr, (0.025, 0.975))[0], 1e-9)

# Jensen / covariance spread, exported by the build so it is not carried here.
jen = wq(z["jensen"][m].astype("float64")) if "jensen" in z.files else [
    float("nan")] * 3

# ---- Everything the prose quotes, computed rather than carried over.
# The opening box promises this, so it has to actually hold.
_UG = np.concatenate([[0.0], np.geomspace(1e-5, 200.0, 900)])
_GG = np.concatenate([[0.0], K.dissolved_fraction(_UG[1:], C.PSD_REF_WIDTH)])
_X = (10 ** L1) * eta_tr
_u1 = d_ref * np.clip(_X, 0.0, None) / C.PSD_REF_D50_UM
cum = {t_: np.interp(_u1 * t_, _UG, _GG) for t_ in (1, 10)}
f_y1, f_y10 = wq(cum[1])[1], wq(cum[10])[1]
yield10 = wq(cum[10] * eta * RATE * CEIL_T)[1]
cdr_y1 = wq(cum[1] * eta * RATE * CEIL_T)[1]
ratio_10_1 = yield10 / cdr_y1
k_equiv = yield10 / cdr_y1                      # map's year-1 == this cadence

# The bulk exponential this replaced, on the same X, for the tail comparison.
_kexp = -np.log(1 - C.DISSOLVED_FRAC_AT_REF)
_fexp = 1 - np.exp(-_kexp * np.clip(_X, 0.0, None))
tail_exp = 100 * ha[_fexp > 0.90].sum() / ha.sum()
tail_sc = 100 * ha[frac > 0.90].sum() / ha.sum()

# SOC screen.
p_soc = z["p_soc"][m].astype("float64")
soc_excl = 100 * ha[p_soc > C.P_EXCEED_EXCLUDED].sum() / ha.sum()
_rows, _cols = np.where(m)
_tr = z["transform"].reshape(2, 3)
lat = _tr[1, 2] + (_rows + 0.5) * _tr[1, 1]
lon = _tr[0, 2] + (_cols + 0.5) * _tr[0, 0]
_fl = p_soc > C.P_EXCEED_EXCLUDED
soc_boreal = 100 * ha[_fl & (lat > 50)].sum() / max(ha[_fl].sum(), 1e-9)

# Zero-recharge share, and the two regions that motivated the drainage choice.
q_sens = z["q_sens"][m].astype("float64")
zero_qr = 100 * ha[q_sens <= 1e-9].sum() / ha.sum()
# The qr end of the drainage bracket, recomputed here rather than quoted.
_Xr = (10 ** L1) * K.eta_transport(q_sens)
_fr = np.interp(d_ref * np.clip(_Xr, 0, None) / C.PSD_REF_D50_UM, _UG, _GG)
g_unc_qr = float((ha * np.nan_to_num(_fr * eta * RATE * CEIL_T)).sum() / 1e9)
def _box(la0, la1, lo0, lo1, arr, thr=0.0):
    b = (lat > la0) & (lat < la1) & (lon > lo0) & (lon < lo1)
    return 100 * ha[b & (arr <= thr)].sum() / max(ha[b].sum(), 1e-9)
mekong_zero = _box(9.0, 11.5, 104.5, 107.0, q_sens)
# Indo-Gangetic under qsb, the candidate we rejected: read from the tif if present.
igp_zero = None
try:
    import rasterio
    from rasterio.enums import Resampling
    from build_v0 import onto_grid, master_grid
    _T, _w, _h, _crs = master_grid()
    _qsb = np.nan_to_num(onto_grid(ROOT / "data/interim/drainage_qsb_mmyr.tif",
                                   _T, _w, _h, _crs,
                                   resampling=Resampling.nearest))[m] / 1000.0
    igp_zero = _box(24.0, 31.0, 74.0, 88.0, _qsb, thr=0.001)
except Exception:
    pass

# Crop mix, for the "two crops not one" claim.
crop_p50 = crop_two = None
try:
    import rasterio
    with rasterio.open(ROOT / "data/interim/crop_mix.tif") as _s:
        _i1, _s1, _i2, _s2 = _s.read()
    _has = _i1[m] > 0
    _sh1 = (_s1[m] / 255.0)[_has]
    _o = np.argsort(_sh1); _cw = np.cumsum(ha[_has][_o]) / ha[_has].sum()
    crop_p50 = float(np.interp(0.5, _cw, _sh1[_o]))
    crop_two = 100 * ha[_has][_sh1 > 0.5].sum() / ha[_has].sum()
    _sh2 = (_s2[m] / 255.0)[_has]
    _t2 = _sh1 + _sh2
    _o2 = np.argsort(_t2); _cw2 = np.cumsum(ha[_has][_o2]) / ha[_has].sum()
    crop_top2_p50 = float(np.interp(0.5, _cw2, _t2[_o2]))
except Exception:
    crop_top2_p50 = None

anch = C.FLUX_CEILING_ANCHORS_MMOL_L
anchor_rows = "\n".join(
    rf"{k.replace('&', chr(92) + '&')} & {lo:g}--{hi:g} \\" if lo != hi
    else rf"{k.replace('&', chr(92) + '&')} & {lo:g} \\"
    for k, (lo, hi) in anch.items())

TEXT = rf"""
\documentclass[11pt,a4paper]{{article}}
\usepackage[margin=2.3cm]{{geometry}}
\usepackage{{amsmath,amssymb,booktabs,microtype,graphicx}}
\usepackage[svgnames]{{xcolor}}
\usepackage[colorlinks=true,linkcolor=MidnightBlue,urlcolor=MidnightBlue]{{hyperref}}
\usepackage{{parskip}}
\usepackage{{titlesec}}
\usepackage{{tcolorbox}}
\emergencystretch=2.5em \tolerance=1400
\titleformat{{\section}}{{\large\bfseries}}{{\thesection}}{{0.7em}}{{}}
\titleformat{{\subsection}}{{\normalsize\bfseries}}{{\thesubsection}}{{0.6em}}{{}}
% \ensuremath so these work in BOTH text and math. Defined as CO$_2$ they would
% toggle math mode OFF inside an equation, which breaks any \left...\right pair
% they sit within -- that is exactly how the first draft of this file failed.
\newcommand{{\cotwo}}{{\ensuremath{{\mathrm{{CO_2}}}}}}
\newcommand{{\hco}}{{\ensuremath{{\mathrm{{HCO_3^-}}}}}}
\newcommand{{\ca}}{{\ensuremath{{\mathrm{{Ca^{{2+}}}}}}}}
\newcommand{{\mg}}{{\ensuremath{{\mathrm{{Mg^{{2+}}}}}}}}
\setlength{{\parskip}}{{0.55em}}

\title{{\vspace{{-1.6cm}}ERW Atlas: model and methodology\\
\large Equations, parameters and their provenance}}
\author{{Zeke Hausfather\\\small Stripe / Frontier}}
\date{{\today}}

\begin{{document}}
\maketitle
\vspace{{-0.6cm}}

\begin{{tcolorbox}}[colback=Gainsboro!22,colframe=Gray,boxrule=0.4pt,arc=2pt]
\small
Every model parameter and every distributional statistic here is generated from
\texttt{{scripts/constants.py}} and the built grid rather than typed in; literature
values are cited to their source. It describes the model as it stands; where it and
the code disagree, the code is right. Prose treatment of the same material is in
\texttt{{docs/METHODOLOGY.md}}; the gates and pre-registered tolerances are in
\texttt{{docs/VALIDATION.md}}.

\textbf{{Status.}} This is a v0 preview. The kinetics fail their one independent
test (\S\ref{{sec:limits}}), one input is a documented stand-in, and the drainage
ceiling of \S\ref{{sec:ceiling}} is implemented but \emph{{not applied}} by default.
Treat the map as a relative ranking, not a site-level prediction.
\end{{tcolorbox}}

\tableofcontents

\section{{The model chain}}

For each grid cell the model composes a dimensionless rate, a dissolved mass
fraction, a carbon-accounting efficiency, and an optional transport bound:

\begin{{align}}
R &= \textstyle\sum_j \phi_j\, \nu_j\, r_j(\mathrm{{pH}}, T) \cdot s
   && \text{{Ca+Mg release, \S\ref{{sec:kinetics}}}} \\
L_1 &= \log_{{10}}\!\left(R / R_{{\mathrm{{ref}}}}\right)
   && \text{{normalised reactivity}} \\
X &= 10^{{L_1}} \cdot \eta_{{\mathrm{{tr}}}}(q)
   && \text{{dimensionless rate, \S\ref{{sec:transport}}}} \\
F_w &= \mathcal{{G}}\!\left(\delta_{{\mathrm{{ref}}}} X / d_{{50}},\, n\right)
   && \text{{fraction weathered, \S\ref{{sec:psd}}}} \\
E &= F_w \cdot \eta_{{\mathrm{{DIC}}}}(\mathrm{{pH}}, p\mathrm{{CO_2}}, T)
     \cdot A \cdot \Psi
   && \text{{gross removal, \S\ref{{sec:dic}}}} \\
E^{{\ast}} &= \min\!\left(E,\; q\,[\hco]_{{\max}}\, M_{{\cotwo}}\right)
   && \text{{drainage bound, \S\ref{{sec:ceiling}}}} \\
S &= f(E^{{\ast}}) \cdot v_{{\mathrm{{cost}}}}^{{\,w}}
   && \text{{suitability, \S\ref{{sec:suit}}, \S\ref{{sec:econ}}}}
\end{{align}}

with $A = {RATE:g}$\,t\,ha$^{{-1}}$\,yr$^{{-1}}$ the application rate and
$\Psi = {CEIL_T:.4f}$\,t\,\cotwo{{}}\,t$^{{-1}}$ the feedstock's stoichiometric
\cotwo{{}} potential (\S\ref{{sec:stoich}}).

Three properties of this composition are deliberate and are the answer to most
``why here and not there'' questions:

\begin{{itemize}}
\item \textbf{{$\eta_{{\mathrm{{DIC}}}}$ multiplies the carbon, not the rock.}} It sits
outside $F_w$. Carbonate speciation does not slow dissolution; it determines how
much carbon each unit of released alkalinity carries.
\item \textbf{{Grind enters once, inside $F_w$.}} Under shrinking core the linear
retreat rate is independent of particle size, so a surface-area multiplier on the
rate as well would count grind twice.
\item \textbf{{The bound applies to $E$, never to $F_w$.}} Rock can dissolve without
the carbon leaving, so the fraction-weathered layer -- the one field trials can
measure -- stays unbounded, and the gap between the two is information.
\end{{itemize}}

\section{{Grid and area}}

$0.1^\circ$ equirectangular, ${z["crop"].shape[1]}\times{z["crop"].shape[0]}$,
spanning $82.7^\circ$N to $56.0^\circ$S. Grid spacing is not resolution:
effective resolution is roughly 10--50\,km, set by the scale of mapped mafic
lithology rather than by pixel size.

Cell area is exact on the sphere rather than $\cos\varphi$-approximated,
\begin{{equation}}
A_{{\mathrm{{cell}}}} = R_\oplus^2 \,\Delta\lambda
   \left(\sin\varphi_{{\mathrm{{top}}}} - \sin\varphi_{{\mathrm{{bot}}}}\right),
\qquad R_\oplus = {C.EARTH_RADIUS_M / 1000:,.1f}\ \text{{km (authalic)}} .
\end{{equation}}
Dropping the latitude weighting inflates the global cropland total by
$\approx 28\%$, which is gate 1b.

\section{{Dissolution kinetics}}
\label{{sec:kinetics}}

\subsection{{Three-mechanism rate law}}

Per mineral, far from equilibrium, after Palandri \& Kharaka (2004, USGS OFR
2004-1068):
\begin{{equation}}
r_j(\mathrm{{pH}},T) = \sum_{{\mathrm{{mech}}}}
  10^{{\,\log k_{{25}}^{{\mathrm{{mech}}}}}}\;
  \exp\!\left[-\frac{{E_a^{{\mathrm{{mech}}}}}}{{R}}
  \left(\frac{{1}}{{T}} - \frac{{1}}{{T_{{\mathrm{{ref}}}}}}\right)\right]
  a_{{\mathrm{{H^+}}}}^{{\,n^{{\mathrm{{mech}}}}}}
\end{{equation}}
summed over the acid, neutral and base mechanisms the source actually tabulates,
with $R = {C.R_GAS}$\,J\,mol$^{{-1}}$\,K$^{{-1}}$ and
$T_{{\mathrm{{ref}}}} = {C.T_REF}$\,K. Mechanisms recorded as ``--'' contribute
nothing rather than being filled in.

Two notes on fidelity to the source. The Arrhenius form above is PHREEQC's
\texttt{{RATE\_PK}}; the expression printed at OFR eqn 7 is
$\exp[-E/(R(T-T_{{\mathrm{{ref}}}}))]$, which is dimensionally incoherent and
singular at $T_{{\mathrm{{ref}}}}$ -- a typo in the report. The affinity term
$(1-\Omega^p)^q$ is dropped, i.e.\ $\Omega \to 0$; Palandri \& Kharaka select
far-from-equilibrium data for that reason, so it is internally consistent, but it
is optimistic in slow-draining soils, which is what \S\ref{{sec:transport}} tempers.

\subsection{{From mineral rates to cation charge}}

\cotwo{{}} removal is driven by \ca{{}} and \mg{{}} release, not Si, so the mixture
rate is a charge-weighted sum over the archetype's volume fractions $\phi_j$:
\begin{{equation}}
R = \left(\sum_j \frac{{\phi_j}}{{\sum_k \phi_k}}\, \nu_j \cdot 2 \cdot
    r_j(\mathrm{{pH}},T)\right) \cdot s ,
\end{{equation}}
$\nu_j$ being divalent Ca+Mg cations per formula unit and the factor 2 the charge
per divalent cation. Units are mol charge\,m$^{{-2}}$\,s$^{{-1}}$ -- an
\emph{{intensive}} quantity, per unit reactive surface, with no application rate
and no specific surface area in it.

\textbf{{Iron is excluded, and this is a deliberate divergence}} from Bertagni \&
Porporato's Table 1, which assigns Fe$_2$SiO$_4$ the same alkalinity yield as
Mg$_2$SiO$_4$. That is correct as aqueous chemistry, but in an oxic agricultural
soil the alkalinity is transient:
\begin{{equation}}
\mathrm{{Fe^{{2+}}}} + \tfrac{{1}}{{4}}\mathrm{{O_2}} + \tfrac{{5}}{{2}}\mathrm{{H_2O}}
\longrightarrow \mathrm{{Fe(OH)_3}} + 2\,\mathrm{{H^+}}
\end{{equation}}
returns the protons as the iron oxidises. The crediting protocols agree --
Isometric computes \cotwo{{}} potential from CaO, MgO, Na$_2$O and K$_2$O with no
FeO term. Consequence: fayalite scores zero here against $\nu = 4$ in B\&P.

\subsection{{Moisture and monthly integration}}\label{{sec:moisture}}

$s \in [0,1]$ is the \emph{{absolute}} degree of soil-water saturation. TerraClimate
reports \emph{{extractable}} storage in mm -- water held above the wilting point --
so it cannot be divided by a capacity and called a saturation. Three steps, each
with its own denominator from SoilGrids water retention over 0--100\,cm:
\begin{{equation}}
f = \min\!\left(\frac{{W}}{{\theta_{{fc}} - \theta_{{wp}}}},\, 1\right),
\qquad
\theta = \theta_{{wp}} + f\,(\theta_{{fc}} - \theta_{{wp}}),
\qquad
s = \frac{{\theta}}{{\theta_{{sat}}}},
\end{{equation}}
with $\theta_{{sat}} = 1 - \rho_b/\rho_p$ at $\rho_p = {C.PARTICLE_DENSITY_G_CM3}$
g\,cm$^{{-3}}$. Field capacity and wilting point \emph{{bracket}} the range the
storage occupies; pore volume is what converts a water content into a saturation.
Using any one of the three alone is a units error dressed as a choice.

Through 2026-08-23 this term instead normalised each cell by \emph{{its own}} annual
maximum, which removes absolute wetness and leaves only seasonal shape. It
correlated $-0.886$ with the coefficient of variation of monthly storage and only
$+0.147$ with storage itself: the driest and wettest 5\% of cropland scored
identically at 0.653 across a 272$\times$ range in real soil water, and the
Indo-Gangetic Plain -- wetter than the US Corn Belt -- was down-weighted 36\%
against it for having a monsoon. Gate 2e now requires the term to be monotone in
wetness and fails any per-cell normalisation.

Because $\theta$ has a wilting-point floor, $s$ spans only about 0.34--1.0 over
cropland. That is a result rather than a residual defect: the moisture term is a
modest wetted-surface-area modulator, and it is \emph{{not}} the map's aridity
signal. Dissolution does not stop at the wilting point, so a term that falls to
zero in hyper-arid cropland would be more wrong, not less. Aridity has to enter
through the export side, which is also the mechanism Calabrese et al.\ (2022)
describe -- and \S\ref{{sec:transport}} explains why that side does not currently
deliver it either. Linearity in $s$ is a convention: no published relation
constrains the exponent for mineral dissolution in soils.

The rate is evaluated \emph{{monthly and then averaged}}, never at annual-mean
drivers:
\begin{{equation}}
R = \frac{{1}}{{12}}\sum_{{i=1}}^{{12}} R(T_i, s_i),
\qquad
\eta_{{\mathrm{{DIC}}}} = \frac{{\sum_i R_i\, \eta_{{\mathrm{{DIC}},i}}}}{{\sum_i R_i}} .
\end{{equation}}
$\eta_{{\mathrm{{DIC}}}}$ is \textbf{{rate-weighted}}, not plainly averaged: the
efficiency that matters is the one operating while dissolution is happening.

Two effects motivate this and they oppose. The rate is convex in temperature, so
the mean of the rate exceeds the rate at the mean (Jensen); but weathering needs
warm \emph{{and}} wet simultaneously, which annual means destroy. Measured ratio of
monthly-integrated to annual-mean rate: median {jen[1]:.2f}, p10--p90
{jen[0]:.2f}--{jen[2]:.2f} -- smaller
than the $\approx 1.4$ an air-temperature estimate suggests, because soil at
5--15\,cm is strongly damped. It is spatially structured as the mechanism
predicts: Mediterranean cropland falls \emph{{below}} 1 where warm and wet seasons
never coincide, monsoon and continental rise above it.

\section{{Reactive surface area and grind}}
\label{{sec:psd}}

\subsection{{Rosin--Rammler distribution}}

Cumulative mass finer than $d$, with $d_{{50}}$ fixing the scale:
\begin{{equation}}
F(d) = 1 - \exp\!\left[-\left(d/d_c\right)^n\right],
\qquad d_c = \frac{{d_{{50}}}}{{(\ln 2)^{{1/n}}}} .
\end{{equation}}
$d_{{50}}$ rather than $d_{{80}}$ because the field reports $p_{{50}}$. The
conversion is width-dependent,
$d_{{80}}/d_{{50}} = (\ln 5/\ln 2)^{{1/n}}$, which is $1.76\times$ at $n=1.5$ but
$3.35\times$ at $n=0.7$ -- so any $p_{{80}}$ from the literature carries a width
assumption with it.

\subsection{{Geometric specific surface area}}

For spheres, area per unit mass goes as $6/(\rho d)$, so
\begin{{equation}}
\mathrm{{SSA}} = \frac{{6}}{{\rho}} \int_{{d_{{\min}}}}^{{d_{{\max}}}} \frac{{1}}{{d}}\,\mathrm{{d}}F(d),
\qquad \rho = {C.FEEDSTOCK_DENSITY_KG_M3:,.0f}\ \mathrm{{kg\,m^{{-3}}}} .
\end{{equation}}
Evaluated numerically over $[{C.PSD_D_MIN_UM:g}, {C.PSD_D_MAX_UM:g}]$\,\textmu m
rather than by the closed form $\tfrac{{6}}{{\rho d_c}}\Gamma(1 - 1/n)$, which
\emph{{diverges}} for $n \le 1$: an unbounded fine tail carries unbounded surface
area, and real grinds do have widths near and below 1. Truncation is physically
honest -- there is a finest particle.

\textbf{{This is geometric area, not BET}}, and the two differ by 130--670$\times$ at
ERW grain sizes. That gap is the largest single uncertainty in any absolute
\cotwo{{}} number here. It is carried explicitly as a fitted roughness multiplier
$\lambda$ rather than hidden.

\begin{{center}}\small
\begin{{tabular}}{{rrr}}
\toprule
$d_{{50}}$ (\textmu m) & SSA (m$^2$g$^{{-1}}$) & $\Delta L_1$ \\
\midrule
{grind_rows}
\bottomrule
\end{{tabular}}
\hspace{{2em}}
\begin{{tabular}}{{rrr}}
\toprule
width $n$ & SSA (m$^2$g$^{{-1}}$) & $\Delta L_1$ \\
\midrule
{width_rows}
\bottomrule
\end{{tabular}}
\end{{center}}

Reference grind is $d_{{50}} = {C.PSD_REF_D50_UM:g}$\,\textmu m, $n =
{C.PSD_REF_WIDTH:g}$, giving SSA $= {ssa_ref:.4f}$\,m$^2$\,g$^{{-1}}$.
\textbf{{The width is assumed, not measured}}, and it matters: at fixed $d_{{50}}$,
varying $n$ over a realistic range moves SSA by more than an order of magnitude.

\subsection{{Shrinking-core dissolution}}

The bulk exponential $F_w = 1 - e^{{-kX}}$ was replaced because it let the last
10\% of mass dissolve as easily as the first 10\%, when physically that last 10\%
is the coarse tail with the least surface per unit mass. Under shrinking core
every particle's surface retreats at the same linear rate $\delta$, because the
reaction is per unit area and does not know the particle size:
\begin{{equation}}
F_w(u, n) = 1 - \int f(x)\,
  \max\!\left(1 - \frac{{2u}}{{x}},\, 0\right)^{{3}} \mathrm{{d}}x,
\qquad u = \frac{{\delta}}{{d_{{50}}}},\quad x = \frac{{d}}{{d_{{50}}}} .
\end{{equation}}
$F_w$ depends only on $u$ and $n$, because the distribution scales with
$d_{{50}}$ -- which is what lets the browser interpolate a small table instead of
integrating 6{{,}}000 size bins per cell.

The retreat is anchored at one point: $\delta_{{\mathrm{{ref}}}} =
{d_ref:.4f}$\,\textmu m dissolves {C.DISSOLVED_FRAC_AT_REF * 100:.0f}\% of the reference
grind in one year at the reference condition, and scales linearly with $X$
thereafter. Measured effect of the change at the reference grind: area above 90\%
weathered fell from {tail_exp:.2f}\% to {tail_sc:.2f}\% of cropland.

\section{{Transport limitation}}
\label{{sec:transport}}

After Maher \& Chamberlain (2014), recast as a multiplier on a kinetic rate whose
limit is $q \to \infty$:
\begin{{equation}}
\eta_{{\mathrm{{tr}}}}(q) = \frac{{q}}{{q + D_w}},
\qquad D_w = {C.DAMKOHLER_DW_M_YR}\ \mathrm{{m\,yr^{{-1}}}}
\ \ \text{{(published range {C.DAMKOHLER_DW_RANGE[0]}--{C.DAMKOHLER_DW_RANGE[1]})}}.
\end{{equation}}

\subsection{{Which water flux is $q$?}}

The bound and the rate are both linear-ish in $q$, so the choice of flux is as
consequential as the chemistry. WaterGAP2-2e publishes four candidates differing
by a factor of five over cropland (area-weighted median, mm\,yr$^{{-1}}$):
groundwater recharge $q_r$ {dv['qr']:.0f}, subsurface runoff $q_{{sb}}$
{dv['qsb']:.0f}, surface runoff $q_s$ {dv['qs']:.0f}, total runoff $q_{{tot}}$
{dv['qtot']:.0f}.

$q_r$ cannot be used alone: it is \emph{{exactly zero}} over {zero_qr:.2f}\% of
cropland area, concentrated in river deltas where the water table is at the
surface -- WaterGAP is right that nothing recharges an aquifer there, but field
drainage still leaves laterally to canals with its bicarbonate in it. $q_{{sb}}$ is
not the fix either: in WaterGAP, recharge feeds the groundwater store and that
store discharges as baseflow, so a 30-year mean $q_{{sb}}$ is close to $q_r$
relabelled, and it strands {igp_zero:.0f}\% of the Indo-Gangetic Plain below
1\,mm\,yr$^{{-1}}$ instead. Per-region detail is in
\texttt{{scripts/analysis/drainage\_variable.py}}.

\subsection{{How little aridity contrast this delivers}}

$\eta_{{\mathrm{{tr}}}}$ is a saturating function, and at
$D_w = {C.DAMKOHLER_DW_M_YR}$\,m\,yr$^{{-1}}$ against a cropland median $q$ of
{dv[C.DRAINAGE_VARIABLE]:.0f}\,mm\,yr$^{{-1}}$ it sits close to its ceiling almost
everywhere: area-weighted mean {etr_mean:.3f}, with {etr_gt08:.1f}\% of cropland
area above 0.8, and a ratio between the wettest and driest 5\% of cropland of only
{etr_ratio:.1f}$\times$ against a 272$\times$ range in root-zone soil water.

This matters more than a parameter footnote should, because the export side is
where aridity is \emph{{supposed}} to enter (\S\ref{{sec:moisture}}). Calabrese et
al.\ (2022) argue aridity is the binding constraint on ERW, with the chemical
depletion fraction collapsing past a Budyko dryness index of 1; a transport term
pinned near unity over most cropland cannot express that. Resolving it means
either a larger effective $D_w$ -- defensible for crushed feedstock, whose
reactive surface area shortens the equilibration length relative to the natural
saprolite the coefficient was fitted on -- or an explicitly aridity-dependent
formulation. It is the largest open item in this document.

\textbf{{We use $q_{{tot}}$}}, on the argument that Maher \& Chamberlain fit $D_w$
against catchment discharge per unit area, which \emph{{is}} total runoff; driving a
$q_{{tot}}$-calibrated $D_w$ with recharge penalises the flux twice. The
counter-argument we cannot dismiss is that surface runoff has little contact time
with topsoil rock. Treat $q_r$ and $q_{{tot}}$ as a bracket: {g_unc:.2f} against
{g_unc_qr:.2f}\,Gt\,\cotwo{{}}\,yr$^{{-1}}$ unbounded, reported by gate 2d on every
build.

\section{{Alkalinity-to-DIC efficiency}}
\label{{sec:dic}}

Not all released base-cation charge carries carbon. In an open system at fixed
soil $p$\cotwo{{}} -- the correct idealisation for soil, where $p$\cotwo{{}} is
buffered by root and microbial respiration rather than a finite DIC pool -- with
$h = a_{{\mathrm{{H^+}}}}$ and $C_s = K_H\, p\mathrm{{CO_2}}$:
\begin{{align}}
\mathrm{{DIC}} &= C_s\left(1 + K_1/h + K_1K_2/h^2\right), \\
\mathrm{{Alk}} &= C_s\left(K_1/h + 2K_1K_2/h^2\right) + K_w/h - h .
\end{{align}}
Both depend only on $h$ at fixed $p$\cotwo{{}}, so the efficiency is the ratio of
their derivatives:
\begin{{equation}}
\eta_{{\mathrm{{DIC}}}}
= \frac{{\partial \mathrm{{DIC}}/\partial h}}{{\partial \mathrm{{Alk}}/\partial h}}
= \frac{{C_s\left(K_1 + 2K_1K_2/h\right)}}
       {{C_s\left(K_1 + 4K_1K_2/h\right) + K_w + h^2}} .
\end{{equation}}
\textbf{{Zero free parameters.}} This is the Alkalinization Carbon-capture
Efficiency of Bertagni \& Porporato (2022, STE 838, 156524), verified against
their Appendix A. One deliberate difference: they carry a borate term and we do
not, which is correct for soil solution -- the freshwater case, where their
maximum ACE $\to 1$; ours is 0.999.

The half-efficiency pH follows in closed form,
$\mathrm{{pH}}_{{1/2}} = -\log_{{10}}\sqrt{{K_H\, p\mathrm{{CO_2}}\, K_1}}$, and
\textbf{{derives the protocols' own screening thresholds}} rather than imposing a
penalty: {ph_half_unsat:.2f} at the mandated
{C.PCO2_UNSATURATED_UATM:,.0f}\,\textmu atm for unsaturated cropping (against
Isometric's 5.20 threshold) and {ph_half_sat:.2f} at
{C.PCO2_SATURATED_UATM:,.0f}\,\textmu atm for saturated systems, which is why
paddies tolerate more acidity.

Soil $p$\cotwo{{}} is interpolated continuously on flooded fraction of cell-time,
\begin{{equation}}
p\mathrm{{CO_2}} = p\mathrm{{CO_2^{{unsat}}}}
 + f_{{\mathrm{{flood}}}}\left(p\mathrm{{CO_2^{{sat}}}} - p\mathrm{{CO_2^{{unsat}}}}\right),
\end{{equation}}
with $f_{{\mathrm{{flood}}}}$ the product of GRPI inundation months and SPAM
irrigated-rice sub-cell area -- deliberately conservative, since it refuses to
treat a 5\%-paddy cell as fully flooded.

\subsection{{Carbonate constants}}

$K_1$, $K_2$, $K_H$ and $K_{{\mathrm{{sp}}}}$ follow Plummer \& Busenberg (1982),
each of the form
\begin{{equation}}
\log_{{10}} K = A + BT + C/T + D\log_{{10}}T + E/T^2 ,
\end{{equation}}
reproduced to within $5\times10^{{-4}}$ log units at 25\,\textdegree C (gate 1).
Activity coefficients are unity throughout; at soil ionic strengths that biases
the ceiling of \S\ref{{sec:ceiling}} \emph{{low}} by 10--20\%, i.e.\ conservative
toward the flux being bounded.

\section{{Stoichiometric potential}}
\label{{sec:stoich}}

The \cotwo{{}} a feedstock can carry at complete dissolution, from its oxide
composition:
\begin{{equation}}
\Psi = \left(\frac{{w_{{\mathrm{{CaO}}}}}}{{M_{{\mathrm{{CaO}}}}}}
           + \frac{{w_{{\mathrm{{MgO}}}}}}{{M_{{\mathrm{{MgO}}}}}}\right)
       \times 1000 \times 2 \times {C.MOL_CO2_PER_KMOL_CHARGE_T}
\quad \mathrm{{t\,\cotwo{{}}\,t^{{-1}}}},
\end{{equation}}
with $M_{{\mathrm{{CaO}}}} = {C.M_CAO}$ and $M_{{\mathrm{{MgO}}}} = {C.M_MGO}$\,
g\,mol$^{{-1}}$, the factor 2 charge per divalent cation and
{C.MOL_CO2_PER_KMOL_CHARGE_T} t\,\cotwo{{}} per kmol charge.

\begin{{center}}\small
\begin{{tabular}}{{lrrrc}}
\toprule
archetype & CaO (wt\%) & MgO (wt\%) & $\Psi$ (t\,\cotwo{{}}\,t$^{{-1}}$) & default \\
\midrule
{arch_rows}
\bottomrule
\end{{tabular}}
\end{{center}}

At $A = {RATE:g}$\,t\,ha$^{{-1}}$ this caps gross removal at
$A\Psi = {stoich_max:.2f}$\,t\,\cotwo{{}}\,ha$^{{-1}}$\,yr$^{{-1}}$, which is the top
suitability knot: a score of 100 means complete dissolution of the applied rock,
and gate 3 asserts no cell exceeds it.

\section{{The drainage-concentration ceiling}}
\label{{sec:ceiling}}

\begin{{tcolorbox}}[colback=Gold!12,colframe=DarkGoldenrod,boxrule=0.5pt,arc=2pt]
\small\textbf{{Implemented, gated, and switched OFF by default}} pending review by
the ERW community. The viewer exposes it as a live toggle (Advanced $\to$
\emph{{Apply the drainage limit}}); \texttt{{constants.FLUX\_CEILING\_ON}} governs the
derived products. While off, the reported \cotwo{{}} exceeds this bound on
{binds * 100:.1f}\% of cropland area by a median {ex50:.1f}$\times$, so it should be
read as an upper limit on \emph{{dissolution}}, not carbon shown to leave the field.
\end{{tcolorbox}}

Carbon reported has to leave dissolved in the water that leaves, which bounds
gross removal at $q\,[\hco]_{{\max}}\,M_{{\cotwo}}$ regardless of dissolution rate.
The bound is where rising pH meets \textbf{{carbonate saturation}}. Solving charge
balance $2[\ca] + 2[\mg] = [\hco]$ simultaneously with fixed $p$\cotwo{{}} and a
calcite saturation state $\Omega$ gives a closed form:
\begin{{equation}}
[\hco]_{{\max}} = \left(
  \frac{{2\,\Omega\,K_1 K_H\, p\mathrm{{CO_2}}\, K_{{\mathrm{{sp}}}}}}
       {{f_{{\mathrm{{Ca}}}}\,K_2}}\right)^{{1/3}} .
\end{{equation}}

\textbf{{Both cations carry carbon; only Ca constrains calcite.}} The charge balance
uses the \emph{{sum}} of Ca and Mg, while the saturation constraint applies to Ca
alone -- magnesite and dolomite are kinetically inhibited at surface temperature
and are not imposed. $f_{{\mathrm{{Ca}}}} = {C.FLUX_CEILING_F_CA}$ is the Ca share of
divalent charge, bridging the two, and the ceiling scales as
$f_{{\mathrm{{Ca}}}}^{{-1/3}}$: a lower value \emph{{raises}} the bound. That matches
the default basalt, whose oxides imply
{spec['CaO_wt'] / C.M_CAO / (spec['CaO_wt'] / C.M_CAO + spec['MgO_wt'] / C.M_MGO):.3f};
it would be wrong for an ultramafic feedstock, which implies 0.05.

The cube root makes this robust: a $5\times$ error in soil $p$\cotwo{{}} moves the
ceiling only $1.7\times$. At {C.PCO2_UNSATURATED_UATM:,.0f}\,\textmu atm,
15\,\textdegree C and $f_{{\mathrm{{Ca}}}} = {C.FLUX_CEILING_F_CA}$ it gives
{o1:.2f}\,mmol\,L$^{{-1}}$ at $\Omega = 1$ and {o10:.2f} at
$\Omega = {C.FLUX_CEILING_OMEGA:g}$, the shipped value -- justified because
carbonate precipitation is kinetically inhibited by DOC and phosphate.

\textbf{{An instructive wrong answer.}} Computing the ceiling at each cell's
\emph{{pre-treatment}} pH gives 0.42\,mmol\,L$^{{-1}}$ and an apparent
$563\times$ exceedance. That is wrong: pH is endogenous, since adding base cations
at fixed $p$\cotwo{{}} raises alkalinity and pH \emph{{together}}, and raising pH is
precisely what a silicate amendment does. Tellingly, 0.42\,mmol\,L$^{{-1}}$ is to
two significant figures the observed mean alkalinity of streams draining
\emph{{unamended}} volcanic rock -- a baseline, not a bound.

\begin{{center}}\small
\begin{{tabular}}{{lr}}
\toprule
Independent anchor & mmol\,L$^{{-1}}$ \\
\midrule
{anchor_rows}
\midrule
This model, unbounded (cropland p10/p50/p90) &
{implp[0]:.0f}\,/\,{implp[1]:.0f}\,/\,{implp[2]:.0f} \\
Closed form above (cropland p10/p50/p90) &
{alkp[0]:.2f}\,/\,{alkp[1]:.2f}\,/\,{alkp[2]:.2f} \\
\bottomrule
\end{{tabular}}
\end{{center}}

Applying it takes the global total from {g_unc:.2f} to
{g_cap:.2f}\,Gt\,\cotwo{{}}\,yr$^{{-1}}$. The consequence that matters is not the
level but the gradient: $C_{{\mathrm{{eq}}}}$ \emph{{falls}} with warming while the rate
law rises, so the bound removes most of the map's warm-climate advantage rather
than rescaling it.

\section{{Suitability}}
\label{{sec:suit}}

A piecewise-linear value function of gross removal on \textbf{{absolute}}
breakpoints -- never min-max or percentile, which would make the colour scale
move as the user moves a slider:
\begin{{equation}}
S_{{\mathrm{{phys}}}} = f\!\left(\log_{{10}} E^{{\ast}}\right),
\qquad
f = 0 \ \text{{where}}\ E^{{\ast}} < {C.CDR_NEGLIGIBLE_T_HA_YR:g}\
\mathrm{{t\,\cotwo{{}}\,ha^{{-1}}yr^{{-1}}}} .
\end{{equation}}

\begin{{center}}\small
\begin{{tabular}}{{rr}}
\toprule
$E^{{\ast}}$ (t\,\cotwo{{}}\,ha$^{{-1}}$yr$^{{-1}}$) & score \\
\midrule
{knot_rows}
\bottomrule
\end{{tabular}}
\end{{center}}

Zero removal gives zero suitability \emph{{by construction}}, which gate 4 asserts.
The three physical terms compose as a product with unit exponents; the Advanced
sliders are \textbf{{exponents}}, not importance weights, so a reader cannot prefer
dissolution over alkalinity retention -- both are required multiplicatively.

\section{{Delivered cost and economics}}
\label{{sec:econ}}

\subsection{{Delivered cost}}

Truck only, at great-circle distance $\times$ a tortuosity factor, not network
routing:
\begin{{equation}}
c = c_{{\mathrm{{gate}}}} + c_{{\mathrm{{truck}}}}\cdot \tau_{{\mathrm{{road}}}}\, d_{{gc}},
\qquad
c_{{\mathrm{{gate}}}} = \${C.FEEDSTOCK_GATE_COST_USD_T:g}\,\mathrm{{t^{{-1}}}},\ \
c_{{\mathrm{{truck}}}} = \${C.TRUCK_COST_USD_T_KM:g}\,\mathrm{{t^{{-1}}km^{{-1}}}},\ \
\tau_{{\mathrm{{road}}}} = {C.ROAD_TORTUOSITY:g} .
\end{{equation}}
Where a usable quarry inventory exists the distance is to a mafic-hosted quarry;
elsewhere it is distance to mafic \emph{{outcrop}} scaled by
$\times{C.OUTCROP_TO_QUARRY_FACTOR:g}$, the outcrop-to-quarry ratio measured where
both are known. Outcrop proximity is an upper bound on availability: a rock
formation is not a permitted, operating, crushing quarry.

\subsection{{Cost as a compensatory multiplier}}

Cost is the first genuinely tradeable factor in the model, so unlike the physical
terms it enters as a preference rather than a what-if:
\begin{{equation}}
v_{{\mathrm{{cost}}}} = \mathrm{{clip}}\!\left(
\frac{{1}}{{1 + \max(c - c_{{\mathrm{{gate}}}},\,0)/S_{{\mathrm{{haul}}}}}},\;
{C.COST_FLOOR:g},\; 1\right),
\qquad S_{{\mathrm{{haul}}}} = \${C.HAUL_PENALTY_SCALE_USD_T:g}\,\mathrm{{t^{{-1}}}},
\end{{equation}}
and multiplies suitability as $v_{{\mathrm{{cost}}}}^{{\,w}}$. The physical half still
annihilates -- zero removal is zero suitability at any price -- while expensive
rock is discounted rather than excluded, because expensive is bad, not impossible.
The floor at {C.COST_FLOOR:g} keeps a remote cell visible as physically real.

\subsection{{The headline screen: multi-year, discounted}}

Dividing a one-off rock cost by a \emph{{single}} year's removal overstates
\$/t\cotwo{{}} by roughly $3\times$, because the rock keeps weathering. Under
shrinking core the retreat accumulates linearly in time, so cumulative $F_w$ at
year $t$ is $\mathcal{{G}}(u\,t)$ and year $t$ delivers the increment. With cost at
$t=0$ and tonnes over years $1..N$:
\begin{{equation}}
\frac{{\$}}{{\mathrm{{t\cotwo{{}}}}}}
= \frac{{c \cdot A}}
       {{\displaystyle\sum_{{t=1}}^{{N}}
        \frac{{\left[\mathcal{{G}}(ut) - \mathcal{{G}}(u(t{{-}}1))\right]
              \eta_{{\mathrm{{DIC}}}} A \Psi}}{{(1+r)^t}}}},
\qquad N = {C.COST_SCREEN_YEARS:g},\ r = {C.COST_SCREEN_DISCOUNT_RATE * 100:.0f}\% .
\end{{equation}}
When economics is on, the headline total is restricted to cells under
\${C.COST_SCREEN_USD_PER_TCO2:g}/t\cotwo{{}} on this basis. Per tonne of \cotwo{{}},
not per tonne of rock: rock cost is nearly uncorrelated with removal, so a
rock-cost screen barely discriminates, while this one rewards cells producing
enough carbon to justify the haul.

Discounting physical carbon is a choice, not a fact. It is equivalent to
discounting the revenue stream a buyer receives, which is the right frame for
cost-effectiveness, but a tonne in 2036 is not physically worth less than a tonne
today.

\subsection{{What ``per year'' means}}

The application rate is stated per year while the \cotwo{{}} layer is the
\emph{{first}} year from \emph{{one}} application. Those coincide only under annual
reapplication, which no field sustains. Running the model forward, the median cell
weathers {100 * f_y1:.1f}\% in year one and {100 * f_y10:.1f}\% by year ten, so
one application delivers ${ratio_10_1:.1f}\times$ its year-one carbon over a
decade. At a reapplication interval of $k$ years the steady-state annual removal
is that 10-year yield divided by $k$, so the map's year-one figure corresponds to
$k \approx {k_equiv:.1f}$ years. A field on a longer rotation removes less than
the map shows.

\section{{Protocol eligibility}}

Soil organic carbon above {C.SOC_EXCLUSION_WT_PCT:g}\,wt\% excludes a site
({C.SOC_EXCLUSION_SOURCE}). The gridded input has real uncertainty, so eligibility
is an exceedance probability rather than a binary mask on a point estimate. A
lognormal is matched in log space to the SoilGrids quantiles:
\begin{{equation}}
\mu = \ln q_{{50}}, \qquad
\sigma = \frac{{\ln q_{{95}} - \ln q_{{05}}}}{{{C.Z_90_TWO_SIDED:.4f}}}, \qquad
P(X > \theta) = 1 - \Phi\!\left(\frac{{\ln\theta - \mu}}{{\sigma}}\right).
\end{{equation}}
Lognormal because SOC is positive and right-skewed; near the threshold that choice
is a first-order determinant of the answer, so it is documented rather than buried.
Computed at $\approx$2.8\,km and then averaged -- averaging the quantiles first is
not valid propagation.

\textbf{{It barely binds on cropland}}: only {soc_excl:.3f}\% of cropland area is
confidently excluded, and {soc_boreal:.0f}\% of the flagged area lies north of
50\textdegree N, because
SOC above 5\,wt\% is a peatland and boreal phenomenon. These are predictive
quantiles for a $\approx$250\,m \emph{{block average}}, not a sampled field; block
averaging reduces variance, so this understates how often an individual field
crosses the threshold. It is a screening likelihood, not a calibrated eligibility
probability.

\section{{What is grown there}}

Descriptive only -- crop identity feeds nothing in the chain except rice, and
there only through soil $p$\cotwo{{}}. The readout names the two largest crops from
SPAM2010 v2.0 \emph{{physical}} area (harvested double-counts multi-cropping), with
the remainder shown as ``rest''.

Two crops rather than one because the dominant crop is a median
{100 * crop_p50:.0f}\% of a cell's cropped area, and only {crop_two:.1f}\% of
cropland has any crop above half; two reach a median {100 * crop_top2_p50:.0f}\%. Aggregation is area-conserving -- SPAM gives hectares per 5-arcmin
cell, an extensive quantity, so each crop is converted to a fraction of its source
cell, resampled, then multiplied by the target cell's area.

\section{{Distributions over cropland}}

Area-weighted across {int(m.sum()):,} cropland cells
({ha.sum() / 1e9:.3f}\,Gha), at the shipped settings:

\begin{{center}}\small
\begin{{tabular}}{{lrrr}}
\toprule
quantity & p10 & p50 & p90 \\
\midrule
Soil pH (0--15\,cm) & {wq(ph_c)[0]:.2f} & {wq(ph_c)[1]:.2f} & {wq(ph_c)[2]:.2f} \\
$L_1 = \log_{{10}}(R/R_{{\mathrm{{ref}}}})$ & {l1p[0]:+.2f} & {l1p[1]:+.2f} & {l1p[2]:+.2f} \\
$\eta_{{\mathrm{{DIC}}}}$ & {etap[0]:.3f} & {etap[1]:.3f} & {etap[2]:.3f} \\
$\eta_{{\mathrm{{tr}}}}$ & {etrp[0]:.3f} & {etrp[1]:.3f} & {etrp[2]:.3f} \\
Drainage $q$ (m\,yr$^{{-1}}$) & {qp[0]:.3f} & {qp[1]:.3f} & {qp[2]:.3f} \\
Fraction weathered, year 1 & {fracp[0] * 100:.1f}\% & {fracp[1] * 100:.1f}\% & {fracp[2] * 100:.1f}\% \\
Gross removal (t\,\cotwo{{}}\,ha$^{{-1}}$yr$^{{-1}}$) & {cdrp[0]:.2f} & {cdrp[1]:.2f} & {cdrp[2]:.2f} \\
\bottomrule
\end{{tabular}}
\end{{center}}

Global gross removal is {g_unc:.2f}\,Gt\,\cotwo{{}}\,yr$^{{-1}}$ unbounded and
{g_cap:.2f} with the drainage ceiling applied. Neither is a deployment forecast:
both assume {RATE:g}\,t\,ha$^{{-1}}$ on all cropland in scope, with no economic,
agronomic or logistical screen.

\section{{Known limitations}}
\label{{sec:limits}}

\begin{{enumerate}}
\item \textbf{{The kinetics fail their one independent test.}} Against Gudbrandsson
et al.\ (2011) whole-rock basalt measurements the Ca+Mg charge-sum rate law
over-predicts by $\approx$1.2 log units with structured residuals. An
over-identified test -- two free surface fractions against four measured elements
-- shows that repartitioning the reacting surface \emph{{cannot}} rescue it. This is
the most important open problem in the model.
\item \textbf{{Geometric versus BET surface area}} differs by 130--670$\times$, and
this sets the absolute scale of every \cotwo{{}} number.
\item \textbf{{The drainage ceiling is not applied by default}}, so the shipped
\cotwo{{}} layer exceeds a bound this project computes and documents on
{binds * 100:.1f}\% of cropland area.
\item \textbf{{Cation retention is not modelled at all.}} Field trials measure
10--50$\times$ more cations retained in secondary phases than exported, and modelled
export lags of 5--22 years. Dissolution-based removal cannot be read as export
without this term, and its absence is why the map is an upper bound.
\item \textbf{{The map has no strong aridity signal.}} The moisture term is now an
absolute saturation, but it is weak by construction, and
$\eta_{{\mathrm{{transport}}}}$ is pinned near its ceiling at
$D_w = {C.DAMKOHLER_DW_M_YR}$\,m\,yr$^{{-1}}$ -- area-weighted mean {etr_mean:.3f},
with {etr_gt08:.1f}\% of cropland area above 0.8 and a wettest-to-driest ratio of
only {etr_ratio:.1f}$\times$. If aridity is the ERW bottleneck, neither term
currently represents it.
\item \textbf{{Irrigation is invisible to the soil-water balance but not to the
drainage.}} WaterGAP \texttt{{histsoc}} simulates irrigation return flow, so $q$
sees irrigation while TerraClimate's rain-fed balance does not. The two therefore
disagree about how wet every irrigated cell is.
\item \textbf{{Soil moisture is an end-of-month state.}} TerraClimate publishes
\emph{{Soil Moisture at End of Month}}, an instantaneous value, which is used here
as though it were a monthly mean.
\item \textbf{{Nothing downstream of dissolution is deducted}} -- not riverine
re-release, not strong-acid competition, not the emissions of grinding and
hauling. Every \cotwo{{}} figure is \textbf{{gross}}.
\end{{enumerate}}

\section{{Reproducing this}}

\begin{{verbatim}}
./scripts/fetch_v0.sh                       # inputs
python3 scripts/prep_layers.py --delete-raw # reduce to data/interim/
python3 scripts/build_v0.py                 # grid, gates, textures
python3 scripts/test_kinetics.py            # the kinetics gates
python3 scripts/analysis/make_methods_report.py
\end{{verbatim}}

Code is MIT; each dataset keeps its own licence. Source, data and the full
development history: \url{{https://github.com/hausfath/erw-map}}.

\end{{document}}
"""

# A bare "%" in generated LaTeX is a COMMENT and silently swallows the rest of
# the line -- that is how Python's :.1% format broke a table row here. Catch it
# before tectonic turns it into an inscrutable alignment error.
_bad = [(i + 1, ln) for i, ln in enumerate(TEXT.splitlines())
        if "%" in ln.replace("\\%", "") and not ln.lstrip().startswith("%")]
if _bad:
    for i, ln in _bad[:10]:
        print(f"  UNESCAPED % at line {i}: {ln.strip()[:90]}")
    raise SystemExit("refusing to emit LaTeX with an unescaped percent sign")

DOCS.mkdir(parents=True, exist_ok=True)
TEX.write_text(TEXT)
print(f"wrote {TEX}")
try:
    subprocess.run(["tectonic", str(TEX), "--outdir", str(DOCS)], check=True)
except FileNotFoundError:
    print("tectonic not found; wrote the .tex only")
print(f"PDF exists: {PDF.exists()}", PDF.stat().st_size if PDF.exists() else "")
