"""Soil-pH sensitivity of the steady-state potential (2026-10-21).

  python3 scripts/analysis/ph_sensitivity.py

SoilGrids pH(H2O) is a static prediction trained on legacy profiles with no
liming signal, so on limed cropland it likely reads low (Brazil cropland median
5.3). This asks what the headline does if cropland pH is higher. pH enters the
model twice, in opposite directions: eta_DIC rises with pH, the Palandri-Kharaka
rate falls with it. The drainage ceiling uses no baseline pH (calcite saturation
with pH endogenous), so where it binds neither term matters.

APPROXIMATION: the stored eta and L1 layers are monthly-weighted; here they are
rescaled by eta_dic(pH')/eta_dic(pH) and rate(pH')/rate(pH) evaluated at the
annual-mean soil temperature, not re-integrated month by month. Good enough for
a sensitivity; a build-level option would need build_v0.py.
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
transform, w, h, crs = master_grid()
idx, isos, _names = country_raster(transform, w, h)
z = np.load(ROOT / "data/processed/v0_layers.npz")
crop, area, ph = z['crop'], z['area'], z['ph'].astype('float64')
f_flood = np.nan_to_num(z['f_flood'].astype('float64'))
pco2 = z['pco2'].astype('float64'); TK = z['t_ceil_c'].astype('float64') + 273.15
L1 = z['L1'].astype('float64'); eta = np.nan_to_num(z['eta'].astype('float64'))
eta_tr = np.nan_to_num(z['eta_tr'].astype('float64')); ceil_ = np.nan_to_num(z['ceiling'].astype('float64'))
m = (crop >= C.CROPLAND_MIN_FRACTION) & np.isfinite(ph) & np.isfinite(L1)
ha = crop * area * 100.0
spec = C.FEEDSTOCK_ARCHETYPES[C.FEEDSTOCK_DEFAULT]
ct = (spec['CaO_wt'] / C.M_CAO + spec['MgO_wt'] / C.M_MGO) * 1000.0 * 2.0 * C.MOL_CO2_PER_KMOL_CHARGE_T
A = C.APPLICATION_RATE_T_HA_YR
d_ref = K.retreat_at_reference()
ug = np.concatenate([[0.0], np.geomspace(1e-5, 200.0, 900)])
gg = np.concatenate([[0.0], K.dissolved_fraction(ug[1:], C.PSD_REF_WIDTH)])
i_inf = float(np.trapezoid(1.0 - gg, ug))
chem = lambda p: p + f_flood * (C.PH_FLOODED_CONVERGENCE - p)
e0 = K.eta_dic(chem(ph), pco2, TK); r0 = K.rate_ca_mg_release(C.FEEDSTOCK_DEFAULT, chem(ph), TK)

def ss(ph_new, rate_shift=True):
    e1 = K.eta_dic(chem(ph_new), pco2, TK)
    r1 = K.rate_ca_mg_release(C.FEEDSTOCK_DEFAULT, chem(ph_new), TK) if rate_shift else r0
    eta_n = eta * np.where(e0 > 0, e1 / e0, 1.0)
    L1_n = L1 + np.log10(np.where(r0 > 0, r1 / r0, 1.0))
    u1 = d_ref * np.clip(np.nan_to_num(10.0 ** L1_n) * eta_tr, 0, None) / C.PSD_REF_D50_UM
    un = np.minimum(1.0, u1 / i_inf) * eta_n * A * ct
    return un, np.minimum(un, ceil_), eta_n

regions = {'World': m, 'Brazil': m & (idx == isos.index('BR') + 1),
           'India': m & (idx == isos.index('IN') + 1), 'USA': m & (idx == isos.index('US') + 1)}
base_un, base_lim, _ = ss(ph)
tot = lambda v, s: float((ha[s] * v[s]).sum() / 1e6)
print('check vs region_potential arithmetic: world SS capped Mt', round(tot(base_lim, m), 1))
scen = {
  'baseline (SoilGrids)': ph,
  '+0.5 all cropland': ph + 0.5,
  '+0.5 eta only (no rate change)': None,
  'floor 6.0 (limed), all cropland': np.maximum(ph, 6.0),
  'floor 6.0, Brazil only': np.where(idx == isos.index('BR') + 1, np.maximum(ph, 6.0), ph),
  'floor 6.0 + 0.5 soil-water offset': np.maximum(ph, 6.0) + 0.5,
}
for k, p in scen.items():
    if p is None: un, lim, en = ss(ph + 0.5, rate_shift=False)
    else: un, lim, en = ss(p)
    row = []
    for rn, s in regions.items():
        row.append(f"{rn} {tot(un, s):6.0f}/{tot(lim, s):5.0f}")
    bz = regions['Brazil']
    print(f"{k:36s} " + ' | '.join(row) + f" | BR eta wmean {np.average(en[bz], weights=ha[bz]):.2f}")
