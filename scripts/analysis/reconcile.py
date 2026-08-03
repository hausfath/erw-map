"""Redo the repo's flux-reconciliation audit with a defensible ceiling.

The audit in to_do.md item 0 computed the ceiling as
    q * [HCO3](pH_soil, pCO2_soil)
holding the cell's PRE-TREATMENT soil pH fixed. But pH is not exogenous: adding
base cations at fixed pCO2 raises alkalinity AND pH together. The physical
ceiling is set by carbonate saturation (calcite), not by the untreated pH.

This recomputes the exceedance under:
  A. the repo's own ceiling (fixed pH)                        -- reproduce it
  B. calcite Omega = 1 at the cell's own pCO2, f_Ca = 0.5     -- strict
  C. calcite Omega = 10 at the cell's own pCO2, f_Ca = 0.5    -- Zhang et al.'s
                                                                 nominal river
                                                                 threshold
and also reports the q distribution, because q is the other half of the ratio.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
NPZ = Path(__file__).resolve().parents[2] / "data/processed/v0_layers.npz"


# The build now SHIPS the ceiling, so v0_layers.npz carries both `cdr` (capped) and
# `cdr_uncapped`. These diagnostics reproduce the PRE-FIX state, so they must read
# `cdr_uncapped` -- reading the capped layer makes the comparison self-referential
# and reports ~1.0x exceedance by construction. Falls back to `cdr` for an npz built
# before the ceiling existed.
def model_cdr(z):
    return z["cdr_uncapped"] if "cdr_uncapped" in z.files else z["cdr"]


z = np.load(NPZ, allow_pickle=True)
ph, pco2, q, cdr = z['ph'], z['pco2'], z['q'], model_cdr(z)
crop, area = z['crop'], z['area']

m = (crop > 0.01) & np.isfinite(cdr) & (cdr > 0) & (q > 0) & np.isfinite(ph)
w = (crop * area)[m]
ph, pco2, q, cdr = ph[m], pco2[m], q[m], cdr[m]
print(f"cropland cells: {m.sum():,}   total area {w.sum()/1e4:,.0f} kha")
print(f"pco2 (uatm): p10 {np.percentile(pco2,10):.0f} p50 {np.percentile(pco2,50):.0f} "
      f"p90 {np.percentile(pco2,90):.0f}")


def wq(v, ws, ps=(10, 50, 90)):
    o = np.argsort(v); v, ws = v[o], ws[o]
    c = np.cumsum(ws) / ws.sum()
    return [float(np.interp(p / 100.0, c, v)) for p in ps]


# ---- constants at 15 C (the build averages the rate monthly; use one T here
# and report the sensitivity separately)
def pk(T_C):
    T = T_C + 273.15
    f = lambda a, b, c, d, e: 10**(a + b*T + c/T + d*np.log10(T) + e/T**2)
    KH = f(108.3865, 0.01985076, -6919.53, -40.45154, 669365.0)
    K1 = f(-356.3094, -0.06091964, 21834.37, 126.8339, -1684915.0)
    K2 = f(-107.8871, -0.03252849, 5151.79, 38.92561, -563713.9)
    Kc = 10**(-171.9065 - 0.077993*T + 2839.319/T + 71.595*np.log10(T))
    return KH, K1, K2, Kc


KH, K1, K2, Kc = pk(15.0)
P = pco2 * 1e-6            # atm
F_CA = 0.5                 # Ca share of divalent charge from basalt

# A. repo's ceiling: fixed pH
alk_A = K1 * KH * P / 10**(-ph)
# B/C. calcite-saturation ceiling, pH endogenous
alk_B = (1.0 * 2 * K1 * KH * P * Kc / (F_CA * K2))**(1/3)
alk_C = (10.0 * 2 * K1 * KH * P * Kc / (F_CA * K2))**(1/3)

# implied requirement, and ceilings, in tCO2/ha/yr.
# q is m/yr -> L/ha/yr = q * 1e4 m2 * 1000 L/m3
L_per_ha = q * 1e4 * 1e3
req = cdr * 1e6 / 44.01 / L_per_ha        # tCO2/ha/yr -> g -> mol -> mol/L

print()
print(f"{'quantity':52s} {'p10':>9} {'p50':>9} {'p90':>9}")
print("-" * 82)
for lab, v, sc in [
    ("q, drainage (mm/yr)", q * 1000, 1),
    ("model gross CDR (tCO2/ha/yr)", cdr, 1),
    ("implied [HCO3] required (mmol/L)", req * 1e3, 1),
    ("A. ceiling, repo's fixed-pH (mmol/L)", alk_A * 1e3, 1),
    ("B. ceiling, calcite Omega=1 (mmol/L)", alk_B * 1e3, 1),
    ("C. ceiling, calcite Omega=10 (mmol/L)", alk_C * 1e3, 1),
]:
    a, b, c = wq(v.astype('float64'), w)
    print(f"{lab:52s} {a:9.3f} {b:9.3f} {c:9.3f}")

print()
for lab, alk in [("A. repo, fixed pH", alk_A), ("B. calcite Omega=1", alk_B),
                 ("C. calcite Omega=10", alk_C)]:
    cap = alk * L_per_ha * 44.01 / 1e6           # tCO2/ha/yr
    ex = cdr / cap
    a, b, c = wq(cap.astype('float64'), w)
    fx = (w * ex).sum() / w.sum()
    fr = (w * (ex > 1)).sum() / w.sum()
    fr10 = (w * (ex > 10)).sum() / w.sum()
    med = wq(ex.astype('float64'), w)[1]
    print(f"{lab:22s} ceiling tCO2/ha/yr p10/p50/p90 = {a:6.3f}/{b:6.3f}/{c:6.3f}"
          f"   exceeded on {fr*100:5.1f}% of cropland, {fr10*100:5.1f}% by >10x,"
          f" median {med:8.1f}x, area-wt mean {fx:8.1f}x")

print()
print("=== If the ceiling is taken as binding, what CDR does it permit? ===")
for lab, alk in [("calcite Omega=1", alk_B), ("calcite Omega=10", alk_C)]:
    cap = alk * L_per_ha * 44.01 / 1e6
    capped = np.minimum(cdr, cap)
    a, b, c = wq(capped.astype('float64'), w)
    print(f"  under {lab:16s}: capped CDR p10/p50/p90 = {a:.3f}/{b:.3f}/{c:.3f} tCO2/ha/yr"
          f"   (area-wt mean {(w*capped).sum()/w.sum():.3f}, was "
          f"{(w*cdr).sum()/w.sum():.3f})")

print()
print("=== How much would q have to be for the model's CDR to be carryable? ===")
for lab, alk in [("calcite Omega=1", alk_B), ("calcite Omega=10", alk_C)]:
    q_need = cdr * 1e6 / 44.01 / alk / 1e7 * 1000     # mm/yr
    a, b, c = wq(q_need.astype('float64'), w)
    print(f"  at {lab:16s}: required drainage p10/p50/p90 = {a:6.0f}/{b:6.0f}/{c:6.0f} mm/yr"
          f"  (model uses {wq(q.astype('float64')*1000, w)[1]:.0f} mm/yr at the median)")

print()
print("=== Temperature sensitivity of ceiling B (median cell, pCO2 = 4000 uatm) ===")
for T in (5.0, 15.0, 25.0):
    kh, k1, k2, kc = pk(T)
    a = (2 * k1*kh*4000e-6 * kc / (0.5*k2))**(1/3)
    print(f"  T = {T:4.1f} C -> {a*1e3:5.2f} mmol/L")
