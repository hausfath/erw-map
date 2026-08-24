"""How much aridity contrast does the transport term deliver, and does D_w matter?

  python3 scripts/analysis/dw_sensitivity.py

Written to answer a question that had been asserted both ways without being
measured: eta_transport = q/(q + D_w) is nearly saturated at the shipped
D_w = 0.03 m/yr, so does the map under-represent aridity, and would a larger D_w
fix it?

THE ANSWER IS NO, AND FOR A REASON WORTH KNOWING. Once the drainage-concentration
ceiling is applied, the wet/dry contrast in delivered carbon is ~125x and is
INVARIANT to D_w across three orders of magnitude. The ceiling is linear in q, so
it carries the aridity signal on its own. D_w is only decisive on the UNCAPPED
map -- which is what ships by default, because the ceiling is off pending review.

So the lever is the ceiling, not D_w. Raising D_w to chase an aridity contrast
would be tuning a parameter that the binding constraint has already taken over.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import constants as C  # noqa: E402
import kinetics as K  # noqa: E402

SWEEP = (0.001, 0.003, 0.01, 0.03, 0.1, 0.3, 1.0, 3.0)


def main() -> int:
    z = np.load(ROOT / "data/processed/v0_layers.npz")
    crop, area = z["crop"], z["area"]
    m = (crop >= C.CROPLAND_MIN_FRACTION) & np.isfinite(z["ph"])
    w = (crop * area)[m].astype("float64")
    ha = w * 100.0
    L1, eta, q = (np.nan_to_num(z[k][m].astype("float64"))
                  for k in ("L1", "eta", "q"))
    ceil = np.nan_to_num(z["ceiling"][m].astype("float64"))

    spec = C.FEEDSTOCK_ARCHETYPES[C.FEEDSTOCK_DEFAULT]
    ct = ((spec["CaO_wt"] / C.M_CAO + spec["MgO_wt"] / C.M_MGO)
          * 1000.0 * 2.0 * C.MOL_CO2_PER_KMOL_CHARGE_T)
    rate, d_ref = C.APPLICATION_RATE_T_HA_YR, K.retreat_at_reference()
    ug = np.concatenate([[0.0], np.geomspace(1e-5, 200.0, 900)])
    gg = np.concatenate([[0.0], K.dissolved_fraction(ug[1:], C.PSD_REF_WIDTH)])

    def wq(v, ps):
        o = np.argsort(v)
        return np.interp(ps, np.cumsum(w[o]) / w.sum(), v[o])

    def fw(v, sel):
        return float((v[sel] * w[sel]).sum() / w[sel].sum())

    # The wet/dry axis is drainage itself, because that is the variable
    # eta_transport responds to. Percentiles are area-weighted throughout.
    qmm = q * 1000.0
    e_dry, e_wet = wq(qmm, [0.05, 0.95])
    dry, wet = qmm <= e_dry, qmm >= e_wet

    print(f"cropland {w.sum() * 100 / 1e9:.3f} Gha over {int(m.sum()):,} cells")
    print(f"driest 5% of area: q <= {e_dry:.0f} mm/yr    "
          f"wettest 5%: q >= {e_wet:.0f} mm/yr")
    print(f"contrast in the DRIVERS: drainage {fw(qmm, wet) / fw(qmm, dry):.0f}x, "
          f"and the ceiling alone {fw(ceil, wet) / fw(ceil, dry):.0f}x")
    print()

    hdr = (f"{'D_w':>7} {'eta mn':>7} {'eta>.8':>7} {'wet/dry':>8} "
           f"{'Gt unc':>7} {'Gt cap':>7} {'med CDR':>8} "
           f"{'w/d unc':>8} {'w/d cap':>8} {'binds':>7} {'dec move':>9}")
    print(hdr)
    print("-" * len(hdr))

    base = None
    rows = []
    for dw in SWEEP:
        etr = q / (q + dw)
        x = (10.0 ** L1) * etr
        cdr = (np.interp(d_ref * np.clip(x, 0.0, None) / C.PSD_REF_D50_UM, ug, gg)
               * eta * rate * ct)
        cap = np.minimum(cdr, ceil)
        dec = np.searchsorted(wq(cdr, np.arange(1, 10) / 10.0), cdr)
        if abs(dw - C.DAMKOHLER_DW_M_YR) < 1e-12:
            base = dec
        rows.append((dw, dec))
        binds = 100.0 * w[cdr > ceil].sum() / w.sum()
        print(f"{dw:>7.3f} {fw(etr, np.ones_like(dry, bool)):>7.3f} "
              f"{100 * fw((etr > 0.8).astype(float), np.ones_like(dry, bool)):>6.1f}% "
              f"{fw(etr, wet) / max(fw(etr, dry), 1e-9):>7.1f}x "
              f"{(ha * cdr).sum() / 1e9:>7.3f} {(ha * cap).sum() / 1e9:>7.3f} "
              f"{wq(cdr, [0.5])[0]:>8.3f} "
              f"{fw(cdr, wet) / max(fw(cdr, dry), 1e-9):>7.1f}x "
              f"{fw(cap, wet) / max(fw(cap, dry), 1e-9):>7.1f}x "
              f"{binds:>6.1f}%"
              + ("        --" if dw == C.DAMKOHLER_DW_M_YR else ""))

    print()
    print(f"CDR-decile reshuffle against the shipped D_w = {C.DAMKOHLER_DW_M_YR}:")
    for dw, dec in rows:
        print(f"  D_w {dw:>6.3f}: "
              f"{100 * fw((dec != base).astype(float), np.ones_like(dry, bool)):>5.1f}% "
              f"of cropland area changes decile")

    print()
    print("READING THIS TABLE")
    print("  'w/d cap' barely moves across a 300x change in D_w, because the")
    print("  ceiling binds on most cropland and is linear in q. Aridity is")
    print("  already represented -- by the ceiling, which is OFF by default.")
    print("  'w/d unc' is what the shipped default map delivers, and it IS")
    print("  D_w-sensitive. Maher & Chamberlain state 0.3 m/yr as a global")
    print("  maximum, so anything above that needs its own argument.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
