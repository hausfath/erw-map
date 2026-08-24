"""Technical and economic ERW potential by country.

  python3 scripts/analysis/country_potential.py

A standalone analysis, not a map feature. Reports, for every country whose
technical potential exceeds 50 MtCO2/yr (plus a rest-of-world row):

  TECHNICAL potential   gross year-1 CO2 removal at the map's application rate
                        (APPLICATION_RATE_T_HA_YR t/ha/yr) summed over cropland
                        -- the map's cdr_uncapped layer, i.e. no drainage
                        ceiling. A second column applies the ceiling, since it
                        is computed and gated even though it ships off.
  ECONOMIC potential    the subset passing the map's cost screen: acquisition
                        plus haul under COST_SCREEN_USD_PER_TCO2 per tonne,
                        costed over COST_SCREEN_YEARS years of weathering
                        discounted at COST_SCREEN_DISCOUNT_RATE -- exactly the
                        footer's arithmetic, reproduced here from the same
                        constants and kinetics.

The economic range comes from three gate/haul scenarios built ONLY from values
already sourced in the repo (docs/TRUCK_RATE_SOURCES.md and
docs/GATE_COST_AT_SCALE.md):

  optimistic     current regional byproduct gates (FEEDSTOCK_GATE_REGIONAL:
                 US $12, BR $9, IN $3; $10 elsewhere), haul rates x0.75
  central        the map's own defaults: $10 gate everywhere, haul x1.00
  conservative   at-scale regional gates (FEEDSTOCK_GATE_AT_SCALE: US/CA $18,
                 EU $17, BR/LatAm $12, IN/S Asia $5, else $12), haul x1.25

The +/-25% haul band is a judgment call on rate vintages (only the US rate is a
current primary), not a sourced interval -- stated here so nobody quotes it as
one. Unlike the map, scenarios apply REGIONAL gates freely: this is an offline
sum of screened tonnage, so the gate-cancellation constraint on the map's value
function does not apply.

CAVEATS that bound every number below: gross removal, not net (no spreading,
grinding-to-spec, MRV, or downstream losses in the screen); year-1 kinetics at
30 t/ha/yr on ALL cropland simultaneously, which at country scale exceeds any
plausible basalt supply (see GATE_COST_AT_SCALE: 3 Mha at 30 t/ha equals the
entire US traprock output); haul distances are great-circle x tortuosity, not
routed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from rasterio.enums import Resampling
from rasterio.features import rasterize
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import constants as C  # noqa: E402
import kinetics as K  # noqa: E402
from build_v0 import master_grid, onto_grid  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
INTERIM = ROOT / "data/interim"

THRESHOLD_MT = 50.0          # report countries above this technical potential

# Scenario gates by rate-group label (the truck_rate raster's regions), from
# constants. "current regional" extends FEEDSTOCK_GATE_REGIONAL's three
# operator-sourced entries with the map's $10 default elsewhere.
GATE_SCENARIOS = {
    "optimistic": {"US/Canada": 12.0, "Brazil/Latin America": 9.0,
                   "India/South Asia": 3.0, "default": 10.0},
    "central": {"default": C.FEEDSTOCK_GATE_COST_USD_T},
    "conservative": {**C.FEEDSTOCK_GATE_AT_SCALE_USD_T,
                     "default": C.FEEDSTOCK_GATE_AT_SCALE_USD_T["elsewhere"]},
}
HAUL_MULT = {"optimistic": 0.75, "central": 1.0, "conservative": 1.25}


def country_raster(transform, w, h):
    """ISO_A2 index raster from the Natural Earth zip prep_feedstock cached."""
    import geopandas as gpd

    zp = ROOT / "data/raw/ne_50m_admin_0_countries.zip"
    ctry = gpd.read_file(f"zip://{zp}")
    iso_col = "ISO_A2_EH" if "ISO_A2_EH" in ctry.columns else "ISO_A2"
    isos, names, shapes = [], {}, []
    for _, row in ctry.iterrows():
        iso = str(row.get(iso_col) or "")
        if iso in ("-99", "nan", ""):
            iso = str(row.get("ADM0_A3") or "??")
        if iso not in isos:
            isos.append(iso)
            names[iso] = str(row.get("NAME") or iso)
        shapes.append((row.geometry, isos.index(iso) + 1))

    idx = rasterize(shapes, out_shape=(h, w), transform=transform,
                    fill=0, dtype="int32", all_touched=False)
    # Same 3-cell coastal fill as the rate raster, so cropland pixels whose
    # centre falls just offshore keep their country.
    dist, (iy, ix) = ndimage.distance_transform_edt(idx == 0, return_indices=True)
    near = (dist > 0) & (dist <= 3)
    idx[near] = idx[iy[near], ix[near]]
    return idx, isos, names


def main() -> int:
    transform, w, h, crs = master_grid()
    z = np.load(ROOT / "data/processed/v0_layers.npz")
    crop, area, ph = z["crop"], z["area"], z["ph"]
    m = (crop >= C.CROPLAND_MIN_FRACTION) & np.isfinite(ph)
    ha = (crop * area) * 100.0                        # true hectares per cell

    cdr = np.nan_to_num(z["cdr_uncapped"].astype("float64"))
    ceil = np.nan_to_num(z["ceiling"].astype("float64"))
    L1 = z["L1"].astype("float64")
    eta = np.nan_to_num(z["eta"].astype("float64"))
    eta_tr = np.nan_to_num(z["eta_tr"].astype("float64"))

    # Delivered-cost building blocks. The cost tif is gate10 + r*(d + d0), so
    # the effective distance (d + d0) recovers exactly; the round-trip gate in
    # prep_feedstock guarantees the decomposition to <1e-3 $/t.
    rate = onto_grid(INTERIM / "truck_rate.tif", transform, w, h, crs,
                     resampling=Resampling.nearest).astype("float64")
    cost0 = onto_grid(INTERIM / "feedstock_cost.tif", transform, w, h, crs,
                      resampling=Resampling.average).astype("float64")
    d_eff = np.maximum(cost0 - C.FEEDSTOCK_GATE_COST_USD_T, 0.0) \
        / np.maximum(rate, 1e-9)

    # Map rate-group labels onto cells via the rate value (rates are distinct
    # by construction; assert rather than assume).
    group_rate = {k: g["rate"] for k, g in C.TRUCK_RATE_GROUPS.items()}
    vals = list(group_rate.values()) + [C.TRUCK_RATE_DEFAULT]
    assert len(set(np.round(vals, 4))) == len(vals), "rate values must be unique"

    def gate_raster(scn):
        g = np.full_like(rate, GATE_SCENARIOS[scn]["default"])
        for label, gv in GATE_SCENARIOS[scn].items():
            if label in group_rate:
                g[np.isclose(rate, group_rate[label])] = gv
        return g

    # Ten-year discounted carbon per tonne of rock -- the footer's screen
    # arithmetic, from the same kinetics.
    spec = C.FEEDSTOCK_ARCHETYPES[C.FEEDSTOCK_DEFAULT]
    ct = ((spec["CaO_wt"] / C.M_CAO + spec["MgO_wt"] / C.M_MGO)
          * 1000.0 * 2.0 * C.MOL_CO2_PER_KMOL_CHARGE_T)
    d_ref = K.retreat_at_reference()
    ug = np.concatenate([[0.0], np.geomspace(1e-5, 200.0, 900)])
    gg = np.concatenate([[0.0], K.dissolved_fraction(ug[1:], C.PSD_REF_WIDTH)])
    x = np.nan_to_num(10.0 ** L1) * eta_tr
    u1 = d_ref * np.clip(x, 0.0, None) / C.PSD_REF_D50_UM
    yrs, dr = C.COST_SCREEN_YEARS, C.COST_SCREEN_DISCOUNT_RATE
    disc_t_per_t = np.zeros_like(u1)
    prev = np.zeros_like(u1)
    for t in range(1, yrs + 1):
        cum = np.interp(u1 * t, ug, gg)
        disc_t_per_t += (cum - prev) * eta * ct / (1.0 + dr) ** t
        prev = cum

    idx, isos, names = country_raster(transform, w, h)

    # Per-cell tonnages.
    tech = cdr * ha                                   # tCO2/yr, uncapped
    tech_cap = np.minimum(cdr, ceil) * ha
    econ = {}
    for scn in GATE_SCENARIOS:
        cost = gate_raster(scn) + HAUL_MULT[scn] * rate * d_eff
        with np.errstate(divide="ignore", invalid="ignore"):
            usd_per_tco2 = cost / np.maximum(disc_t_per_t, 1e-12)
        passes = m & (usd_per_tco2 < C.COST_SCREEN_USD_PER_TCO2) \
            & (disc_t_per_t > 0)
        econ[scn] = np.where(passes, tech, 0.0)

    # Aggregate by country.
    rows = []
    mm = m.copy()
    for i, iso in enumerate(isos, start=1):
        sel = mm & (idx == i)
        if not sel.any():
            continue
        rows.append({
            "iso": iso, "name": names[iso],
            "mha": ha[sel].sum() / 1e6,                        # ha -> Mha
            "tech": tech[sel].sum() / 1e6,
            "tech_cap": tech_cap[sel].sum() / 1e6,
            **{f"econ_{s}": econ[s][sel].sum() / 1e6 for s in GATE_SCENARIOS},
        })
    rows.sort(key=lambda r: -r["tech"])

    world = {k: sum(r[k] for r in rows)
             for k in ("mha", "tech", "tech_cap",
                       "econ_optimistic", "econ_central", "econ_conservative")}
    big = [r for r in rows if r["tech"] >= THRESHOLD_MT]
    rest = {k: world[k] - sum(r[k] for r in big) for k in world}

    hdr = (f"{'country':<22}{'cropland':>9}{'technical':>11}{'w/ drain':>10}"
           f"{'econ opt':>10}{'econ ctr':>10}{'econ cons':>10}{'cons-opt %tech':>15}")
    unit = (f"{'':<22}{'Mha':>9}{'MtCO2/yr':>11}{'MtCO2/yr':>10}"
            f"{'MtCO2/yr':>10}{'MtCO2/yr':>10}{'MtCO2/yr':>10}{'':>15}")
    print(f"\nTechnical and economic ERW potential by country "
          f"(threshold {THRESHOLD_MT:.0f} MtCO2/yr technical)")
    print(f"rate {C.APPLICATION_RATE_T_HA_YR:.0f} t/ha/yr on all cropland; "
          f"screen ${C.COST_SCREEN_USD_PER_TCO2:.0f}/tCO2 over "
          f"{yrs} yr at {dr:.0%}, acquisition + haul only\n")
    print(hdr)
    print(unit)
    print("-" * len(hdr))

    def line(label, r):
        span = (f"{100 * r['econ_conservative'] / max(r['tech'], 1e-9):.0f}"
                f"-{100 * r['econ_optimistic'] / max(r['tech'], 1e-9):.0f}%")
        print(f"{label:<22}{r['mha']:>9.1f}{r['tech']:>11.0f}"
              f"{r['tech_cap']:>10.0f}{r['econ_optimistic']:>10.0f}"
              f"{r['econ_central']:>10.0f}{r['econ_conservative']:>10.0f}"
              f"{span:>15}")

    for r in big:
        line(r["name"][:21], r)
    line("rest of world", rest)
    print("-" * len(hdr))
    line("WORLD", world)

    print(f"\ncountries above threshold: {len(big)}")
    print("scenarios: optimistic = current regional byproduct gates "
          "(US 12 / BR 9 / IN 3 / else 10), haul x0.75;")
    print("           central    = the map's defaults ($10 gate, haul x1.00);")
    print("           conservative = at-scale regional gates "
          "(US/CA 18 / EU 17 / BR-LatAm 12 / IN-S Asia 5 / else 12), haul x1.25")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
