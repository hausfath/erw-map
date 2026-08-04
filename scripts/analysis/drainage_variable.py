"""Which WaterGAP water flux should drive the transport term?

The map has always used qr, DIFFUSE GROUNDWATER RECHARGE. That is exactly zero on
0.10% of cropland area, concentrated in river deltas where the water table is at
the surface and field drainage leaves laterally to canals rather than percolating
to an aquifer -- so those cells rendered as "negligible ERW potential" in some of
the wettest cropland on Earth (the Mekong Delta, the Red River delta, the middle
Yangtze).

This compares the four candidates on the shipped model, changing NOTHING else:

  qr    groundwater recharge   -- water reaching the aquifer
  qsb   subsurface runoff      -- water that reached the stream through the soil
  qs    surface runoff         -- fast component
  qtot  total runoff = qs+qsb  -- what Maher & Chamberlain fit D_w against

TWO THINGS TO TEST, and they pull in opposite directions.

  1. Is qsb usefully different from qr? In WaterGAP, recharge feeds the
     groundwater store and that store discharges as baseflow, so over a 30-year
     mean qsb should be close to qr minus groundwater abstraction. If so, qsb
     inherits the delta zeros and fixes nothing.

  2. Is qtot the internally consistent choice? M&C fit D_w = 0.03 m/yr against
     RIVER data, i.e. catchment discharge per unit area, which is qtot. Driving a
     qtot-calibrated D_w with qr is a units-of-water mismatch that penalises the
     flux twice. Against that: surface runoff has little contact time with topsoil
     rock, so qtot overstates the water that actually weathered anything.

Reports, changes nothing. Run after prep_layers.py.
"""
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import constants as C            # noqa: E402
import kinetics as K             # noqa: E402
from build_v0 import onto_grid, master_grid   # noqa: E402

VARIANTS = [
    ("qr   groundwater recharge  (SHIPPED)", "drainage_recharge_mmyr.tif"),
    ("qsb  subsurface runoff", "drainage_qsb_mmyr.tif"),
    ("qs   surface runoff", "drainage_qs_mmyr.tif"),
    ("qtot total runoff", "drainage_qtot_mmyr.tif"),
]

z = np.load(ROOT / "data/processed/v0_layers.npz", allow_pickle=True)
transform, w_, h_, crs = master_grid()
crop, area = z["crop"], z["area"]
m = (crop >= C.CROPLAND_MIN_FRACTION) & np.isfinite(z["L1"])
ha = (crop * area)[m] * 100.0
L1 = z["L1"][m].astype("float64")
eta = z["eta"][m].astype("float64")
precip = z["precip"][m].astype("float64")

rows, cols = np.where(m)
lat = transform.f + (rows + 0.5) * transform.e
lon = transform.c + (cols + 0.5) * transform.a

spec = C.FEEDSTOCK_ARCHETYPES[C.FEEDSTOCK_DEFAULT]
TCO2_PER_T = ((spec["CaO_wt"] / C.M_CAO + spec["MgO_wt"] / C.M_MGO)
              * 1000.0 * 2.0 * C.MOL_CO2_PER_KMOL_CHARGE_T)
RATE = C.APPLICATION_RATE_T_HA_YR

# Same shrinking-core lookup the build uses.
_dref = K.retreat_at_reference()
_UG = np.concatenate([[0.0], np.geomspace(1e-5, 12.0, 512)])
_GG = np.concatenate([[0.0], K.dissolved_fraction(_UG[1:], C.PSD_REF_WIDTH)])


def load(name):
    """mm/yr -> m/yr on the analysis grid, NEAREST as the build does."""
    q = onto_grid(ROOT / "data/interim" / name, transform, w_, h_, crs,
                  resampling=Resampling.nearest) / 1000.0
    return np.clip(np.nan_to_num(q, nan=0.0), 0.0, None)[m].astype("float64")


def cdr_of(q):
    X = (10 ** L1) * K.eta_transport(q)
    frac = np.interp(_dref * np.clip(X, 0.0, None) / C.PSD_REF_D50_UM, _UG, _GG)
    return frac * eta * RATE * TCO2_PER_T, frac


def aw(v, ps=(0.5,)):
    o = np.argsort(v)
    cw = np.cumsum(ha[o]) / ha.sum()
    return [float(np.interp(p, cw, v[o])) for p in ps]


qs_ = {lbl: load(f) for lbl, f in VARIANTS}
print(f"D_w = {C.DAMKOHLER_DW_M_YR * 1000:.0f} mm/yr, so eta_transport = q/(q + D_w)")
print(f"cropland in domain: {m.sum():,} cells, {ha.sum() / 1e9:.3f} Gha\n")

print("=" * 100)
print("1. IS qsb JUST qr? (the steady-state worry)")
print("=" * 100)
qr, qsb = qs_[VARIANTS[0][0]], qs_[VARIANTS[1][0]]
both = (qr > 0) | (qsb > 0)
print(f"  area-weighted median, mm/yr:  qr {aw(qr)[0]*1000:6.1f}   qsb {aw(qsb)[0]*1000:6.1f}")
r = qsb[both] / np.maximum(qr[both], 1e-9)
print(f"  qsb/qr where either is > 0:   median {np.median(r):.2f}")
print(f"  cells where BOTH are 0:       {int(((qr <= 0) & (qsb <= 0)).sum()):,}")
print(f"  qr == 0 but qsb > 0:          {int(((qr <= 0) & (qsb > 0)).sum()):,}")
print(f"  correlation of log1p:         {np.corrcoef(np.log1p(qr*1000), np.log1p(qsb*1000))[0,1]:.3f}")

print()
print("=" * 100)
print("2. WHAT EACH VARIABLE DOES TO THE MAP")
print("=" * 100)
print(f"  {'drainage variable':<38} {'q p50':>7} {'GtCO2/yr':>9} {'med t/ha':>9} "
      f"{'dark':>6} {'dark%area':>10} {'>90% wthrd':>11}")
print("  " + "-" * 96)
res = {}
for lbl, _ in VARIANTS:
    q = qs_[lbl]
    cdr, frac = cdr_of(q)
    dark = cdr < C.CDR_NEGLIGIBLE_T_HA_YR
    res[lbl] = (q, cdr, frac)
    print(f"  {lbl:<38} {aw(q)[0]*1000:7.1f} {(ha*cdr).sum()/1e9:9.3f} {aw(cdr)[0]:9.3f} "
          f"{int(dark.sum()):6,} {100*ha[dark].sum()/ha.sum():9.2f}% "
          f"{100*ha[frac > 0.90].sum()/ha.sum():10.2f}%")

print()
print("=" * 100)
print("3. THE DELTA CELLS THAT STARTED THIS")
print("=" * 100)
boxes = [("Mekong Delta", 9.0, 11.5, 104.5, 107.0),
         ("Red River delta", 20.0, 21.6, 105.6, 107.2),
         ("Middle Yangtze", 29.0, 31.5, 111.5, 114.5),
         ("Java", -8.5, -5.8, 105.0, 114.5),
         ("US Corn Belt", 38.0, 45.0, -100.0, -85.0),
         ("Indo-Gangetic Plain", 24.0, 31.0, 74.0, 88.0),
         ("Amazon/Cerrado", -18.0, -5.0, -60.0, -45.0)]
print(f"  {'region':<22} {'':>6} " + "".join(f"{lbl.split()[0]:>10}" for lbl, _ in VARIANTS))
for name, la0, la1, lo0, lo1 in boxes:
    b = (lat > la0) & (lat < la1) & (lon > lo0) & (lon < lo1)
    if b.sum() == 0:
        continue
    hb = ha[b]

    def med(v, b=b, hb=hb):
        o = np.argsort(v[b])
        return float(np.interp(0.5, np.cumsum(hb[o]) / hb.sum(), v[b][o]))
    print(f"  {name:<22} {'q mm':>6} " +
          "".join(f"{med(qs_[l])*1000:10.1f}" for l, _ in VARIANTS))
    print(f"  {'':<22} {'t/ha':>6} " +
          "".join(f"{med(res[l][1]):10.3f}" for l, _ in VARIANTS))
    print(f"  {'':<22} {'dark%':>6} " +
          "".join(f"{100*hb[(res[l][1][b] < C.CDR_NEGLIGIBLE_T_HA_YR)].sum()/hb.sum():9.1f}%"
                  for l, _ in VARIANTS))

print()
print("=" * 100)
print("4. WHERE THE CHANGE LANDS, qr -> qtot, by 10-degree latitude band")
print("=" * 100)
cdr_qr, cdr_qt = res[VARIANTS[0][0]][1], res[VARIANTS[3][0]][1]
print(f"  {'lat band':>12} {'Gha':>7} {'GtCO2 qr':>9} {'GtCO2 qtot':>11} {'change':>9}")
for la in range(-50, 70, 10):
    b = (lat >= la) & (lat < la + 10)
    if b.sum() == 0 or ha[b].sum() < 1e6:
        continue
    a, g1, g2 = ha[b].sum(), (ha[b]*cdr_qr[b]).sum()/1e9, (ha[b]*cdr_qt[b]).sum()/1e9
    print(f"  {f'{la} to {la+10}':>12} {a/1e9:7.3f} {g1:9.3f} {g2:11.3f} "
          f"{100*(g2-g1)/max(g1,1e-12):8.1f}%")

print()
print("  Biggest ABSOLUTE gains, qr -> qtot, by 5-degree box:")
d = ha * (cdr_qt - cdr_qr) / 1e9
kb = {}
for la, lo, v in zip(lat, lon, d):
    k = (int(np.floor(la/5)*5), int(np.floor(lo/5)*5))
    kb[k] = kb.get(k, 0.0) + v
for (la, lo), v in sorted(kb.items(), key=lambda x: -x[1])[:10]:
    print(f"    {la:4d}..{la+5:<4d}N {lo:5d}..{lo+5:<5d}E  +{v*1000:6.1f} MtCO2/yr")
