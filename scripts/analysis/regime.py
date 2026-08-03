"""Which limb of the Maher & Chamberlain curve is global cropland actually on?

C = C_eq * tau*D_w / (q + tau*D_w),  flux = C*q.

  q << tau*D_w : C -> C_eq. flux -> C_eq*q. THERMODYNAMICALLY (water) LIMITED.
                 Kinetics, surface area and grind drop out entirely.
  q >> tau*D_w : flux -> C_eq*tau*D_w. KINETICALLY (surface-area) LIMITED.
                 Flux proportional to D_w, hence to reactive surface area.

The crossover is at q = tau*D_w. So the tau question in to_do item 0 is not
merely "eta is 3.3x too high" -- it decides which regime the whole map is in,
and therefore whether the map's rate law and grind slider control the answer
at all.
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
crop, area, q, cdr = z['crop'], z['area'], z['q'], model_cdr(z)
m = (crop > 0.01) & np.isfinite(cdr) & (cdr > 0) & (q > 0)
w = (crop * area)[m].astype('float64')
q = q[m].astype('float64')          # m/yr
cdr = cdr[m].astype('float64')

print(f"cropland area basis: {w.sum()/1e10:.3f} Mha-equivalent, {m.sum():,} cells")
print(f"q (mm/yr) area-weighted: p10 {np.interp(0.1, np.cumsum(w[np.argsort(q)])/w.sum(), np.sort(q))*1000:.0f}"
      f"  p50 {np.interp(0.5, np.cumsum(w[np.argsort(q)])/w.sum(), np.sort(q))*1000:.0f}"
      f"  p90 {np.interp(0.9, np.cumsum(w[np.argsort(q)])/w.sum(), np.sort(q))*1000:.0f}")

print()
print("Fraction of cropland AREA that is thermodynamically/water-limited")
print("(q < tau*D_w, so C is pinned at C_eq and grind/kinetics do not matter):")
print()
print(f"  {'':>12} " + "".join(f"{'D_w='+format(d,'.3f'):>14}" for d in (0.001, 0.01, 0.03, 0.1, 0.3)))
for tname, tau in (("tau = 1", 1.0), ("tau = e^2", np.e**2)):
    cells = []
    for d in (0.001, 0.01, 0.03, 0.1, 0.3):
        f = (w * (q < tau*d)).sum() / w.sum()
        cells.append(f"{f*100:13.1f}%")
    print(f"  {tname:>12} " + "".join(cells))

print()
print("Crossover drainage q = tau*D_w, in mm/yr:")
for tname, tau in (("tau = 1", 1.0), ("tau = e^2", np.e**2)):
    print(f"  {tname:>10}: " + "  ".join(f"D_w={d:.3f} -> {tau*d*1000:6.0f}"
                                          for d in (0.03, 0.1, 0.3)))

print()
print("=== The ceiling as min of the two limbs, C_eq = 3.0 mmol/L ===")
CEQ = 3.0e-3     # mol/L
def to_t(mol_per_m2):    # mol/m2/yr -> tCO2/ha/yr
    return mol_per_m2 * 1e4 * 44.01 / 1e6
def wq(v, ws, ps=(10, 50, 90)):
    o = np.argsort(v); v2, w2 = v[o], ws[o]
    c = np.cumsum(w2)/w2.sum()
    return [float(np.interp(p/100.0, c, v2)) for p in ps]

for tname, tau in (("tau = 1", 1.0), ("tau = e^2", np.e**2)):
    for d in (0.03, 0.3):
        f_water = to_t(CEQ*1000*q)                 # C_eq * q
        f_kin = to_t(CEQ*1000*tau*d)               # C_eq * tau * D_w
        ceiling = np.minimum(f_water, f_kin)
        a, b, c = wq(ceiling, w)
        binding_water = (w*(f_water < f_kin)).sum()/w.sum()
        ex = wq(cdr/ceiling, w)[1]
        print(f"  {tname:9s} D_w={d:5.3f}: ceiling p10/p50/p90 = {a:.3f}/{b:.3f}/{c:.3f}"
              f" tCO2/ha/yr | water-limb binds on {binding_water*100:5.1f}% of area"
              f" | model exceeds ceiling by {ex:5.1f}x at median")

print()
print("=== Where the water limb binds, how much of the model's machinery is inert? ===")
tau = np.e**2
for d in (0.03, 0.3):
    f_water = to_t(CEQ*1000*q)
    f_kin = to_t(CEQ*1000*tau*d)
    frac = (w*(f_water < f_kin)).sum()/w.sum()
    print(f"  tau=e^2, D_w={d}: on {frac*100:.1f}% of cropland area the flux is C_eq*q,")
    print(f"    i.e. independent of the Palandri-Kharaka rate law, the archetype")
    print(f"    mineralogy, the grind d50/width sliders, and soil temperature")
    print(f"    (except through C_eq's weak T dependence, ~1.4x over 5-25 C).")
