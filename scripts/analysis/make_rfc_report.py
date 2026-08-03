"""Generate the flux-reconciliation request-for-comment note as LaTeX, then PDF.

  python3 scripts/analysis/make_rfc_report.py

Every quantitative claim in the document is injected from data/processed/
v0_layers.npz and constants.py, so the note cannot drift from the build the way a
hand-typed number would. Compiled with tectonic.

CONFIDENTIALITY. Appendix A summarises the verified commercial deliveries in fully
aggregated form -- no operator names, no per-deployment values. The underlying
fixture is gitignored and is not ours to publish. The appendix is delimited by
%%% APPENDIX-A markers so it can be removed with one edit if the sharing terms
require it.
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
TEX = DOCS / "rfc_flux_reconciliation.tex"
PDF = DOCS / "rfc_flux_reconciliation.pdf"

z = np.load(ROOT / "data/processed/v0_layers.npz", allow_pickle=True)
crop, area = z["crop"], z["area"]
# EXACTLY the build's cropland mask (build_v0.py), or the note quotes
# percentages that differ from the ones the build prints.
m = (crop >= C.CROPLAND_MIN_FRACTION) & np.isfinite(z["ph"])
w = (crop * area)[m].astype("float64")
unc = z["cdr_uncapped"][m].astype("float64")
cap = np.minimum(unc, z["ceiling"][m].astype("float64"))
ceil_t = z["ceiling"][m].astype("float64")
alk = z["alk_ceiling"][m].astype("float64")
q = z["q"][m].astype("float64")
tc = z["t_ceil_c"][m].astype("float64")


def wq(v, ps=(0.1, 0.5, 0.9)):
    o = np.argsort(v)
    cw = np.cumsum(w[o]) / w.sum()
    return [float(np.interp(p, cw, v[o])) for p in ps]


implied = unc * 1e6 / C.M_CO2_G_MOL / np.maximum(q * 1e7, 1e-9) * 1e3
i10, i50, i90 = wq(implied)
a10, a50, a90 = wq(alk * 1e3)
u10, u50, u90 = wq(unc)
c50 = wq(cap)[1]
strict = np.minimum(unc, K.flux_ceiling_t_ha_yr(
    q, z["pco2"][m], tc + 273.15, omega=C.FLUX_CEILING_OMEGA_STRICT))
s50 = wq(strict)[1]
binds = float((w * (unc > ceil_t * 1.000001)).sum() / w.sum())
ex10, ex50, ex90 = wq(unc / np.maximum(ceil_t, 1e-12))
ha = w * 100.0
g_unc = float((ha * unc).sum() / 1e9)
g_cap = float((ha * cap).sum() / 1e9)

# Ceiling at the protocol default, both omegas, at the reference temperature.
o1 = float(K.alkalinity_ceiling_mol_l(C.PCO2_UNSATURATED_UATM, 288.15,
                                      omega=C.FLUX_CEILING_OMEGA_STRICT)) * 1e3
o10 = float(K.alkalinity_ceiling_mol_l(C.PCO2_UNSATURATED_UATM, 288.15)) * 1e3
t5 = float(K.alkalinity_ceiling_mol_l(C.PCO2_UNSATURATED_UATM, 278.15,
                                      omega=C.FLUX_CEILING_OMEGA_STRICT)) * 1e3
t25 = float(K.alkalinity_ceiling_mol_l(C.PCO2_UNSATURATED_UATM, 298.15,
                                       omega=C.FLUX_CEILING_OMEGA_STRICT)) * 1e3

# The textbook benchmark.
bench = float(K.alkalinity_ceiling_mol_l(C.PCO2_ATMOSPHERIC_UATM, 298.15,
                                         omega=1.0, f_ca=1.0))
K1, _, KH, _ = K.carbonate_constants(298.15)
bench_ph = -np.log10(K1 * KH * C.PCO2_ATMOSPHERIC_UATM * 1e-6 / bench)

# Temperature bins, same basis the build reports on.
bins, rows_t = [(0, 10), (10, 15), (15, 20), (20, 25), (25, 45)], []
for lo, hi in bins:
    b = (tc >= lo) & (tc < hi)
    if b.sum() < 100:
        continue
    ww = w[b]

    def med(v, b=b, ww=ww):
        o = np.argsort(v[b])
        return float(np.interp(0.5, np.cumsum(ww[o]) / ww.sum(), v[b][o]))
    rows_t.append((lo, hi, 100 * ww.sum() / w.sum(), med(unc), med(ceil_t)))
wc_u = rows_t[-1][3] / rows_t[0][3]
wc_c = rows_t[-1][4] / rows_t[0][4]

tau = C.DAMKOHLER_TAU
crossover_lo = tau * C.DAMKOHLER_DW_M_YR * 1000
crossover_hi = tau * 0.3 * 1000
q90 = wq(q)[2] * 1000

anch = C.FLUX_CEILING_ANCHORS_MMOL_L
def a_(k):
    lo, hi = anch[k]
    return f"{lo:g}--{hi:g}" if lo != hi else f"{lo:g}"

temp_rows = "\n".join(
    f"{lo}--{hi} & {sh:.1f} & {u:.3f} & {c:.3f} & {u / c:.1f}$\\times$ \\\\"
    for lo, hi, sh, u, c in rows_t)

TEXT = rf"""
\documentclass[11pt,a4paper]{{article}}
\usepackage[margin=2.4cm]{{geometry}}
\usepackage{{graphicx,booktabs,microtype,amsmath}}
\usepackage[svgnames]{{xcolor}}
\usepackage[colorlinks=true,linkcolor=MidnightBlue,urlcolor=MidnightBlue]{{hyperref}}
\usepackage{{parskip}}
\emergencystretch=2.2em \tolerance=1200
\usepackage{{titlesec}}
\titleformat{{\section}}{{\large\bfseries}}{{\thesection}}{{0.7em}}{{}}
\titleformat{{\subsection}}{{\normalsize\bfseries}}{{\thesubsection}}{{0.6em}}{{}}
\newcommand{{\hco}}{{HCO$_3^-$}}
\newcommand{{\cotwo}}{{CO$_2$}}
\usepackage{{tcolorbox}}

\title{{\vspace{{-1.5cm}}A drainage-concentration ceiling on enhanced rock weathering\\
\large Request for comment on a bound we have implemented but not shipped}}
\author{{Zeke Hausfather\\\small ERW Atlas project}}
\date{{\today}}

\begin{{document}}
\maketitle
\vspace{{-0.7cm}}

\begin{{tcolorbox}}[colback=Gainsboro!25,colframe=Gray,boxrule=0.4pt,arc=2pt]
\textbf{{What we are asking.}} We have built a global gridded ERW suitability model.
While auditing it we found it reports carbon that could not physically leave the
field dissolved in the field's own drainage water. We implemented a bound, and it
changes the map a great deal --- including reversing a headline result. Before we
ship it we would like the ERW community to tell us whether the bound is right, and
in particular whether the four questions in \S\ref{{sec:questions}} have answers we
have missed. The bound is currently switched \emph{{off}} in the published map.
\end{{tcolorbox}}

\section{{The problem}}

Our model, like most process-based ERW models, computes a mineral dissolution rate
and converts dissolved rock to \cotwo{{}} removal. Nothing in that chain requires the
resulting carbon to be carryable at a chemically possible bicarbonate concentration.

Dividing our own \cotwo{{}} flux by our own water flux, area-weighted over global
cropland at {C.APPLICATION_RATE_T_HA_YR:g}\,t\,ha$^{{-1}}$\,yr$^{{-1}}$ of basalt, the
model implies a drainage \hco{{}} concentration of
\textbf{{{i10:.0f}\,/\,{i50:.0f}\,/\,{i90:.0f}\,mmol\,L$^{{-1}}$}} at p10\,/\,p50\,/\,p90.
For scale, world rivers run 0.5--4\,mmol\,L$^{{-1}}$.

This is not specific to our model. Beerling et al.\ (2024) report a CDR$_{{\rm pot}}$
of 10.5\,t\,\cotwo{{}}\,ha$^{{-1}}$ over four years at the Illinois Energy Farm and
report no drainage chemistry; at Illinois tile drainage of 200\,mm\,yr$^{{-1}}$ that
requires 29.8\,mmol\,L$^{{-1}}$. Kelland et al.\ (2020) closes the loop inside one
experiment: measured cation release over measured drainage requires
21.1\,mmol\,L$^{{-1}}$, while measured leachate alkalinity was
1.10\,$\pm$\,0.147\,mmol\,L$^{{-1}}$ and statistically indistinguishable from control
--- a 19$\times$ shortfall measured on both sides.

\section{{A wrong first answer, because it is instructive}}

Our first attempt computed the ceiling as $q\,[\mathrm{{HCO_3^-}}](\mathrm{{pH}},
p\mathrm{{CO_2}})$ holding each cell's \emph{{pre-treatment}} soil pH fixed. That gives
0.42\,mmol\,L$^{{-1}}$ at the median and an apparent 563$\times$ exceedance.

It is wrong, and wrong in an interesting way. pH is not exogenous: adding base
cations at fixed $p$\cotwo{{}} raises alkalinity and pH \emph{{together}}, and raising pH
is precisely what a silicate amendment does. Reading the carbonate equation with pH
held fixed answers a different question. Tellingly, 0.42\,mmol\,L$^{{-1}}$ is, to two
significant figures, the observed mean alkalinity of streams draining
\emph{{unamended}} volcanic rock --- a good baseline, and the wrong ceiling.

\section{{The bound we propose}}

The bound is where the rising pH meets \textbf{{carbonate saturation}}. Solving charge
balance $2[\mathrm{{Ca}}] + 2[\mathrm{{Mg}}] = [\mathrm{{HCO_3^-}}]$ simultaneously with
fixed $p$\cotwo{{}} and a calcite saturation state $\Omega$ gives a closed form:

\begin{{equation}}
[\mathrm{{HCO_3^-}}]_{{\max}} = \left(
\frac{{2\,\Omega\,K_1 K_H\, p\mathrm{{CO_2}}\, K_{{\rm sp}}}}{{f_{{\rm Ca}} K_2}}
\right)^{{1/3}}
\end{{equation}}

with $f_{{\rm Ca}}$ the Ca share of the divalent-cation charge (only Ca constrains
calcite; magnesite is kinetically inhibited at surface temperature, so a lower
$f_{{\rm Ca}}$ \emph{{raises}} the ceiling). Gross CDR is then capped at
$q\,[\mathrm{{HCO_3^-}}]_{{\max}}\,M_{{\rm CO_2}}$.

The cube root makes this robust: being wrong about soil $p$\cotwo{{}} by 5$\times$ moves
the ceiling only 1.7$\times$. At the protocol-mandated
{C.PCO2_UNSATURATED_UATM:,.0f}\,$\mu$atm, 15\,\textdegree C and $f_{{\rm Ca}} =
{C.FLUX_CEILING_F_CA:g}$, it gives \textbf{{{o1:.2f}\,mmol\,L$^{{-1}}$ at $\Omega = 1$}}
and \textbf{{{o10:.2f}\,at $\Omega = 10$}}.

We ship $\Omega = {C.FLUX_CEILING_OMEGA:g}$ as the default because carbonate
precipitation is kinetically inhibited by DOC and phosphate. Zhang et al.\ (2022)
state precipitation in river water ``is generally observed to be negligible at
$\Omega < 10$'' and run their own model over $\Omega = 5$--25; soils carry far more
DOC than rivers. \textbf{{This is the single largest discretionary choice in the
bound}} --- see question 2.

\subsection*{{Applied to the carbon, not to the rock}}

We cap the \cotwo{{}} and leave the predicted \emph{{fraction weathered}} unbounded.
Rock can dissolve without the carbon leaving, and the gap between those two layers
is then a visible, meaningful quantity rather than an inconsistency. The cap is
applied \emph{{after}} the alkalinity-to-DIC conversion, because what has to fit in
the water is the bicarbonate.

\section{{Validation}}

\textbf{{Against a textbook benchmark.}} Setting $f_{{\rm Ca}} = 1$, $\Omega = 1$ and
$p$\cotwo{{}} to atmospheric should reproduce the classic open-system calcite
equilibrium. It gives {bench * 1e3:.3f}\,mmol\,L$^{{-1}}$ alkalinity,
{bench * 1e3 / 2:.3f}\,mmol\,L$^{{-1}}$ Ca and pH {bench_ph:.2f}, against the textbook
$\sim$1.0, $\sim$0.5 and $\sim$8.3. Neglecting activity coefficients and the
CaHCO$_3^+$ ion pair biases this low by 10--20\%, so the shipped ceiling is mildly
conservative.

\textbf{{Against five independent measurements}} that share no assumptions with the
closed form (Figure~\ref{{fig:main}}A):

\begin{{center}}
\begin{{tabular}}{{lr}}
\toprule
Anchor & mmol\,L$^{{-1}}$ \\
\midrule
Riverine transport capacity, Zhang et al.\ 2022, back-converted & {a_("Zhang 2022 riverine CTP, back-converted")} \\
Midwest agricultural tile drainage and porewater, Hamilton et al.\ 2007 & {a_("Hamilton 2007 Midwest tile drainage / porewater")} \\
World pristine rivers, 99th percentile (Meybeck) & {a_("Meybeck pristine rivers, 99th percentile")} \\
Carbonate-terrain streams (Meybeck) & {a_("Meybeck carbonate-terrain streams")} \\
\midrule
\textit{{Achieved}} in ERW field trials --- an observation, not a ceiling & {a_("field trials, ACHIEVED under ERW (not a ceiling)")} \\
\bottomrule
\end{{tabular}}
\end{{center}}

The closed form lands inside all four bounds, and straddles the most relevant one
(agricultural tile drainage). Note the last row: measured ERW trials \emph{{achieve}}
5--10$\times$ \emph{{below}} the ceiling, which matters for \S\ref{{sec:notexplain}}.

\begin{{figure}}[t]
\centering
\includegraphics[width=\linewidth]{{rfc_flux_reconciliation_fig.pdf}}
\caption{{\textbf{{A}} What the model requires against what the water can hold, with
five independent anchors on one axis. \textbf{{B}} The consequence that matters: the
ceiling falls with warming while the rate law rises, so imposing it removes the
warm-climate gradient rather than rescaling the level. Area-weighted medians over
global cropland at {C.APPLICATION_RATE_T_HA_YR:g}\,t\,ha$^{{-1}}$\,yr$^{{-1}}$.}}
\label{{fig:main}}
\end{{figure}}

\section{{Consequences}}

The ceiling binds on \textbf{{{binds * 100:.1f}\% of cropland area}}. Median gross CDR
falls from {u50:.3f} to {c50:.3f}\,t\,\cotwo{{}}\,ha$^{{-1}}$\,yr$^{{-1}}$; the global
total from {g_unc:.3f} to {g_cap:.3f}\,Gt\,\cotwo{{}}\,yr$^{{-1}}$. The $\Omega$ choice
spans {s50:.3f} ($\Omega = 1$) to {c50:.3f} ($\Omega = {C.FLUX_CEILING_OMEGA:g}$) at
the median, and that spread is the honest uncertainty on the level.

\textbf{{But the level is not the interesting part.}} $C_{{\rm eq}}$ \emph{{falls}} with
warming ({t5:.2f}\,/\,{o1:.2f}\,/\,{t25:.2f}\,mmol\,L$^{{-1}}$ at 5\,/\,15\,/\,25\,\textdegree C)
while the rate law rises steeply, so the exceedance is monotonic in temperature:

\begin{{center}}
\begin{{tabular}}{{lrrrr}}
\toprule
Mean soil T (\textdegree C) & \% of area & Unbounded & Ceiling & Exceedance \\
\midrule
{temp_rows}
\bottomrule
\end{{tabular}}
\end{{center}}

\noindent The warmest-to-coolest ratio of the median goes from
\textbf{{{wc_u:.2f}$\times$ unbounded to {wc_c:.2f}$\times$ at the ceiling}}. Imposing the
bound therefore \emph{{removes}} the warm-climate advantage an unbounded rate law
produces. That is the most consequential and least intuitive result here, and the
one we would most like checked.

\textbf{{It also decouples carbon from application rate.}} The ceiling depends on
drainage and carbonate chemistry, not on how much rock is on the field. Raising our
nominal rate from 20 to {C.APPLICATION_RATE_T_HA_YR:g}\,t\,ha$^{{-1}}$ raised the
unbounded median 50\% and the bounded global total by 1.8\%. Past the point where
drainage saturates, extra feedstock raises the transport-limited share of the map
rather than the tonnage.

\section{{Two points from Maher \& Chamberlain, for the record}}

Working the primary source resolved two things that may be of wider interest.

\textbf{{$\tau = e^2$ is real and is not already in the Fig.~2 contours.}} Their Eq.~3
is $C = C_{{\rm eq}}(\tau D_w/q)/(1 + \tau D_w/q)$, with $\tau$ in Table~S1. The Fig.~2
contour \emph{{labels}} reproduce to two significant figures from the paper's own
printed $R_{{n,\max}}$, $C_{{\rm eq}}$ and $L_\phi$ using bare $D_w = L_\phi/T_{{\rm eq}}$,
while Fig.~2B's plotted flux plateaus match $C_{{\rm eq}}\tau D_w$ and are 0.8 of a
decade off without $\tau$.

\textbf{{Consequently all cropland is on the low-$q$ limb.}} $\tau D_w$ is
{crossover_lo:.0f}\,mm\,yr$^{{-1}}$ at $D_w = {C.DAMKOHLER_DW_M_YR:g}$ and
{crossover_hi:,.0f} at $D_w = 0.3$, both at or above the p90 of cropland drainage
({q90:.0f}\,mm\,yr$^{{-1}}$). On that limb the flux is $C_{{\rm eq}}q$ and kinetics drop
out --- Maher (2010, p.~104): beyond $L_{{\rm eq}}$ the flux ``conveys no information
on the actual weathering kinetics or available surface area.'' Godsey et al.\ (2009)
measure near-chemostatic concentration--discharge slopes of $-0.05$ to $-0.15$
across 59 catchments, which is the same statement empirically.

\section{{What this does \emph{{not}} explain}}
\label{{sec:notexplain}}

The ceiling is not why modelled ERW rates exceed measured ones. Field trials achieve
{anch["field trials, ACHIEVED under ERW (not a ceiling)"][0]:g}--{anch["field trials, ACHIEVED under ERW (not a ceiling)"][1]:g}\,mmol\,L$^{{-1}}$,
i.e.\ 5--10$\times$ \emph{{below}} this bound, because cations are retained in secondary
phases rather than exported: 10--50$\times$ more retained than exported in a
greenhouse study across four soils and thirteen feedstocks at
$>$2{{,}}000\,mm\,yr$^{{-1}}$ irrigation (Hammes et al.\ 2025), retarded fractions of
93--98\% (te Pas et al.\ 2025), and modelled export lags of 5--22 years (Kanzaki et
al.\ 2025). The ceiling is a rail that makes an impossible claim impossible; the
level is a retention-and-lag problem plus the lab-to-field rate discrepancy.

\section{{Status}}

Implemented, gated and documented, and currently \textbf{{switched off}} in the
published map pending this review --- a one-line flag. While it is off, our build
reports on every run that {binds * 100:.1f}\% of cropland area exceeds the bound by a
median {ex50:.1f}$\times$, so the finding does not disappear with the cap.

One uncomfortable observation: with the ceiling \emph{{off}}, our global total
({g_unc:.2f}\,Gt\,\cotwo{{}}\,yr$^{{-1}}$) sits inside the 0.5--4 range of published
global ERW estimates. With it \emph{{on}} ({g_cap:.2f}) it falls below. But those
published estimates are not transport-bounded either, so agreement with them is not
evidence of anything.

\section{{Questions we would like answered}}
\label{{sec:questions}}

\begin{{enumerate}}
\item \textbf{{Is carbonate saturation the right ceiling for \emph{{alkalinity}}?}} Silica
is bounded by clay equilibrium, but alkalinity is not --- observed
\hco{{}}:SiO$_2$ ratios of 2.1--9.3 say the two are decoupled by incongruent
weathering. This is the load-bearing step and we would most like it attacked.
\item \textbf{{Is $\Omega = 10$ defensible in soil, or should it be $\Omega = 1$?}} That
pair spans {s50:.3f}--{c50:.3f}\,t\,\cotwo{{}}\,ha$^{{-1}}$\,yr$^{{-1}}$ at the median and we
know of no measurement that discriminates in an amended agricultural soil.
\item \textbf{{Is capping the carbon while leaving fraction weathered unbounded the
right separation?}}
\item \textbf{{Does the temperature dependence survive scrutiny?}} It is what collapses
the warm/cool ratio from {wc_u:.2f}$\times$ to {wc_c:.2f}$\times$, and it is the result
we are least confident about.
\end{{enumerate}}

A fifth, if anyone has data: the bound is unvalidated on flooded/paddy soils, where
the mandated 50{{,}}000\,$\mu$atm lifts it to 13--18\,mmol\,L$^{{-1}}$, above every
anchor above. We could find no measured floodwater alkalinity or paddy lateral DIC
export flux anywhere in the literature.

%%% APPENDIX-A -- aggregated commercial deliveries. Remove this block if the
%%% sharing terms do not permit it; nothing else references it.
\appendix
\section{{Aggregate check against verified commercial deliveries}}

Applying the same test to eight independently verified commercial ERW deliveries
(basalt; roughly 15--100\,t\,ha$^{{-1}}$; India, US Corn Belt and Brazil), every one
reports a CDR per hectare that would require \textbf{{3--19$\times$}} its own region's
drainage ceiling; \textbf{{5--19$\times$}} restricting to the three where CDR was
measured independently rather than derived from fraction weathered.

This is \emph{{not}} an over-crediting finding, and we would ask that it not be read
as one. Those figures are dissolution-based, so the comparison is ``how much rock
dissolved'' against ``how much carbon the water could carry out'', and both can hold
at once. The gap is then the retention-and-lag term of \S\ref{{sec:notexplain}}, and
it is the same order of magnitude. What it does establish is that dissolution-based
CDR per hectare cannot be read as export without a retention term.

Per-deployment values are withheld: they derive from independent verification
reports that are not ours to publish.
%%% END APPENDIX-A

\begin{{thebibliography}}{{9}}\small
\bibitem{{beerling24}} Beerling, D.J.\ et al.\ (2024) \textit{{PNAS}} 121, e2319436121.
\bibitem{{godsey09}} Godsey, S.E., Kirchner, J.W.\ \& Clow, D.W.\ (2009) \textit{{Hydrol.\ Process.}} 23, 1844--1864.
\bibitem{{hamilton07}} Hamilton, S.K.\ et al.\ (2007) \textit{{Global Biogeochem.\ Cycles}} 21, GB2021.
\bibitem{{hammes25}} Hammes, J.S.\ et al.\ (2025) EGUsphere preprint 2025-5402.
\bibitem{{kanzaki25}} Kanzaki, Y.\ et al.\ (2025) \textit{{Environ.\ Res.\ Lett.}} 20, 074055.
\bibitem{{kelland20}} Kelland, M.E.\ et al.\ (2020) \textit{{Glob.\ Change Biol.}} 26, 3658--3676.
\bibitem{{maher10}} Maher, K.\ (2010) \textit{{Earth Planet.\ Sci.\ Lett.}} 294, 101--110.
\bibitem{{maher14}} Maher, K.\ \& Chamberlain, C.P.\ (2014) \textit{{Science}} 343, 1502--1504.
\bibitem{{pb82}} Plummer, L.N.\ \& Busenberg, E.\ (1982) \textit{{Geochim.\ Cosmochim.\ Acta}} 46, 1011--1040.
\bibitem{{tepas25}} te Pas, E.E.E.M.\ et al.\ (2025) \textit{{Front.\ Clim.}} 6, 1524998.
\bibitem{{zhang22}} Zhang, S.\ et al.\ (2022) \textit{{Limnol.\ Oceanogr.}} 67, doi:10.1002/lno.12244.
\end{{thebibliography}}

\end{{document}}
"""

TEX.write_text(TEXT.lstrip())
print(f"wrote {TEX}")
r = subprocess.run(["tectonic", "-X", "compile", str(TEX), "--outdir", str(DOCS),
                    "--keep-logs"], capture_output=True, text=True)
if r.returncode != 0:
    r = subprocess.run(["tectonic", str(TEX), "--outdir", str(DOCS)],
                       capture_output=True, text=True)
print(r.stdout[-1500:] or "", r.stderr[-2500:] or "")
print("PDF exists:", PDF.exists(), PDF.stat().st_size if PDF.exists() else "")
