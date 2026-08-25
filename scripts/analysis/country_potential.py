"""Technical and economic ERW potential by country.

  python3 scripts/analysis/country_potential.py

A standalone analysis, not a map feature. Reports, for every country whose
technical potential exceeds 50 MtCO2/yr (plus a rest-of-world row):

  TECHNICAL potential   gross year-1 CO2 removal at the map's application rate
                        (APPLICATION_RATE_T_HA_YR t/ha/yr) summed over cropland
                        -- the map's cdr_uncapped layer, i.e. no drainage
                        ceiling. A second column applies the ceiling, which the
                        Atlas ships ON by default since 2026-08-24.
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
grinding-to-spec, MRV, or downstream losses in the screen); haul distances are
great-circle x tortuosity, not routed; and everything is on a YEAR-1 basis,
which understates the long-run carbon per tonne of rock. Under continued annual
application the cohorts telescope -- removal in year N is A*eta*CT*F(N) -- so
rock-per-carbon converges from the year-1 ~10-28 t rock/tCO2 down to the
stoichiometric 1/(eta*CT) ~ 3.5 t/t (5.1 in Brazil, where acid Cerrado soils
hold less of the alkalinity as bicarbonate). Sustaining India's 402 Mt/yr
therefore needs ~1.4 Gt rock/yr at steady state, not the 4.1 Gt/yr the year-1
framing implies. Two constraints survive the steady-state framing: supply
(1.4 Gt/yr is still ~15x total current US traprock output) and, more
fundamentally, the drainage ceiling, which is a per-year flux bound -- the
stoichiometric steady state exceeds it ~10x in India (1,185 vs 122 Mt/yr), so
if the ceiling is real it, not stoichiometry, is what annual removal converges
to. Continued annual application also accumulates rock in soil (900 t/ha over
30 years, roughly a third of the plough layer's mass); the realistic operating
mode is the reapplication cadence in docs/METHODOLOGY.md, where the map's
year-1 value is the steady state of a ~4.3-year cycle.
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


def iso_of_us(isos):
    return isos.index("US") + 1


def write_docx(path, big2, rest2, world2, screens, i_inf, w90, us_cap):
    """Export the country tables to .docx. Numbers arrive computed; this
    function only formats."""
    from docx import Document
    from docx.shared import Pt

    lo_rock, hi_rock, lo_co2, hi_co2, eta_us = us_cap
    doc = Document()
    doc.add_heading("Technical and economic ERW potential by country", 0)
    doc.add_paragraph(
        "Generated by scripts/analysis/country_potential.py from the ERW Atlas "
        "v0 build (github.com/hausfath/erw-map). All figures are GROSS CO2 "
        "removal on cropland at a 30 t/ha standing rock inventory; nothing "
        "downstream of dissolution is deducted (no spreading, grinding-to-spec, "
        "MRV, cation retention, or riverine losses).")

    doc.add_heading("Definitions", level=1)
    doc.add_paragraph(
        "Technical (year-1): first-year removal of a single 30 t/ha "
        "application, the map-layer basis and what field trials measure. "
        "Technical (steady state): hold 30 t/ha of undissolved rock, "
        "reapplying as the modelled kinetics dissolve it, capped at one full "
        "application per year (renewal basis; mean-lifetime constant "
        f"I_inf = {i_inf:.3f}). With drainage limit: the steady state bounded "
        "by the drainage-concentration ceiling -- APPLIED BY DEFAULT in the "
        "Atlas since 2026-08-24, when Mayer et al. 2025 "
        "(doi:10.21203/rs.3.rs-7811095/v1) independently corroborated the "
        "bound as 'carrying capacity'. Economic: the drainage-limited steady "
        "state on cells where delivered rock (gate + regional trucking) costs "
        "less than the screen per tonne of CO2, against each application's "
        "discounted lifetime carbon at 5%. The screen is a UNIT cost and is "
        "deliberately not reduced by the drainage limit: carbon is linear in "
        "application rate, so $/tCO2 is unchanged when an operator on a "
        "cap-bound cell scales the application down to what the drainage can "
        "carry. The screen therefore decides where hauling rock is economic; "
        "the drainage limit decides how much carbon each hectare then "
        "yields.")
    doc.add_paragraph(
        "Cost scenarios (sources: docs/TRUCK_RATE_SOURCES.md and "
        "docs/GATE_COST_AT_SCALE.md in the repo): OPTIMISTIC = current "
        "regional byproduct gates (US $12, Brazil $9, India $3, elsewhere "
        "$10/t) with haul rates x0.75; CENTRAL = uniform $10/t gate, regional "
        "haul rates x1.00; CONSERVATIVE = at-scale regional gates (US/Canada "
        "$18, Europe $17, Brazil/LatAm $12, India/S Asia $5, elsewhere $12/t) "
        "with haul x1.25. Only the US haul rate is a current primary source; "
        "the +/-25% haul band is a judgment call, not a fitted interval. "
        "Ranges in Tables 2-3 are the min-max across the three scenarios; "
        "note the scenarios vary gate structure as well as level, so the "
        "central case (uniform $10/t gate) is not always inside the two "
        "regional-gate cases -- for India, whose regional gates ($3 current, "
        "$5 at-scale) are both cheaper than $10, central is the low end.")

    rows = big2 + [dict(rest2, name="Rest of world", kmed=None),
                   dict(world2, name="WORLD", kmed=None)]

    doc.add_heading("Table 1. Technical potential", level=1)
    t = doc.add_table(rows=1 + len(rows), cols=6)
    t.style = "Table Grid"
    hdr = ("Country", "Cropland (Mha)", "Year-1 (MtCO2/yr)",
           "Steady state (MtCO2/yr)", "With drainage limit (MtCO2/yr)",
           "Median cadence (yr)")
    for j, htxt in enumerate(hdr):
        t.rows[0].cells[j].text = htxt
    for i, r in enumerate(rows, start=1):
        c = t.rows[i].cells
        c[0].text = r["name"]
        c[1].text = f"{r['mha']:.1f}" if "mha" in r else ""
        c[2].text = f"{r['tech']:.0f}"
        c[3].text = f"{r['cad']:.0f}"
        c[4].text = f"{r['cad_ceil']:.0f}"
        c[5].text = f"{r['kmed']:.1f}" if r.get("kmed") else ""

    for scr in screens:
        doc.add_heading(
            f"Table {2 if scr == screens[0] else 3}. Economic potential at "
            f"${scr:.0f}/tCO2 (drainage-limited steady-state basis)", level=1)
        t = doc.add_table(rows=1 + len(rows), cols=3)
        t.style = "Table Grid"
        for j, htxt in enumerate((
                "Country",
                "Economic potential, MtCO2/yr: central (scenario range)",
                "Share of drainage-limited potential: central (range)")):
            t.rows[0].cells[j].text = htxt
        for i, r in enumerate(rows, start=1):
            c = t.rows[i].cells
            c[0].text = r["name"]
            ec = {s2: r[f"ec_{s2}_{int(scr)}"]
                  for s2 in ("optimistic", "central", "conservative")}
            # min-max across the three scenarios rather than (cons-opt): the
            # scenarios vary gate STRUCTURE as well as level, so central (a
            # uniform $10 gate) can sit outside the two regional-gate cases --
            # it does for India, whose regional gates ($3 current, $5 at-scale)
            # are both cheaper than $10.
            lo, hi = min(ec.values()), max(ec.values())
            c[1].text = f"{ec['central']:,.0f} ({lo:,.0f}–{hi:,.0f})"
            base = max(r["cad_ceil"], 1e-9)
            c[2].text = (f"{100 * ec['central'] / base:.0f}% "
                         f"({100 * lo / base:.0f}–{100 * hi / base:.0f}%)")

    doc.add_heading("The US byproduct-fines supply cap", level=1)
    doc.add_paragraph(
        "The economic scenarios above are demand-side screens: they assume "
        "rock exists at the scenario gate price wherever the screen passes. "
        "For byproduct-gate pricing that fails at scale, because the cheap "
        "stream is limited to what quarries already produce. USGS Minerals "
        "Yearbook 2023 quantifies the US stream: reported traprock "
        "fines-class sales (stone sand, unspecified fine aggregate, crusher "
        "run/fill/waste) total 4.7 Mt/yr at $11-21/t -- a lower bound, since "
        "62 of 93 Mt/yr of US traprock is use-unspecified -- plus 3.3 Mt/yr "
        "of volcanic cinder and scoria at $8.83/t average, the only US "
        "stream priced below the Atlas's $10/t gate. A common industry rule "
        "of thumb puts crusher fines near 20% of hard-rock output "
        "(UNVERIFIED), giving an upper bound near 22 Mt rock/yr.")
    doc.add_paragraph(
        f"At steady state every acquired tonne eventually delivers eta x CT "
        f"of CO2 (eta_US = {eta_us:.2f}), so the supply-limited US potential "
        f"at byproduct prices is {lo_co2:.0f}-{hi_co2:.0f} MtCO2/yr from "
        f"{lo_rock:.0f}-{hi_rock:.0f} Mt rock/yr. This binds BELOW the "
        f"screened US potential at byproduct gates: in the United States, "
        f"supply -- not the cost screen -- is the near-term constraint. "
        f"Beyond the byproduct stream, US rock costs move to at-scale prices "
        f"(traprock averages $21.33/t f.o.b., USGS 2023), which the "
        f"conservative scenario represents. The same supply logic applies to "
        f"India's crusher-dust and Brazil's po-de-pedra streams; national "
        f"fines statistics for both were not sourced this session and the "
        f"optimistic India/Brazil columns should be read with that caveat.")

    doc.add_heading("Caveats", level=1)
    doc.add_paragraph(
        "Gross, not net. Year-1 kinetics come from a rate law that "
        "over-predicts an independent laboratory test; absolute levels are "
        "upper bounds and rank orderings are more robust than magnitudes. "
        "Haul distances are great-circle x 1.35 tortuosity, not routed. The "
        "drainage-concentration ceiling is the binding long-run constraint "
        "on almost all cropland (it caps 'steady state' down to the 'with "
        "drainage limit' column, and the economic columns are on that capped "
        "basis). It is a maximum-EFFICIENT bound: past it, calcite "
        "precipitation halves marginal efficiency rather than stopping "
        "removal, so the capped figures are a conservative reading of what "
        "lies beyond. Reapplication-trigger sensitivity: "
        f"waiting for 90% dissolution instead of holding the inventory gives "
        f"a world steady state of {w90:.0f} MtCO2/yr.")
    doc.save(str(path))


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

    # ---- Table 2: reapplication-cadence steady state -----------------------
    # The realistic operating mode: hold a standing inventory of M = A t/ha of
    # undissolved rock, topping up as it dissolves. Renewal theory gives the
    # steady-state application rate R = M / tau, where tau is the mean lifetime
    # of applied rock in that cell:
    #
    #   tau = integral(1 - F(t)) dt = I_inf / u1,  I_inf = integral(1 - Fw(u)) du
    #
    # (one PSD constant, per-cell kinetics u1). Removal = R * eta * CT, since at
    # steady state dissolved mass equals applied mass. R is CAPPED at A (one
    # full application per year): fast tropical cells would otherwise imply
    # topping up faster than annually; at the cap they run the perpetual-annual
    # steady state instead, with the standing stock below M between passes.
    # Sensitivity: timing reapplication at F = 90% of the prior cohort instead
    # of by mean lifetime gives the same telescoped removal with k = t90, always
    # lower; reported as one line.
    i_inf = np.trapezoid(1.0 - gg, ug)
    with np.errstate(divide="ignore"):
        tau = np.where(u1 > 0, i_inf / np.maximum(u1, 1e-12), np.inf)
    R = C.APPLICATION_RATE_T_HA_YR * np.minimum(1.0, 1.0 / tau)
    cad = R * eta * ct                                # tCO2/ha/yr
    cad_ceil = np.minimum(cad, ceil)

    # Economic screen on the cadence basis, matching the tool's footer:
    # per-application NPV -- delivered $/t against the application's DISCOUNTED
    # LIFETIME carbon (not a 10-year window), capped at 60 years, past which 5%
    # discounting and the dissolved tail make increments negligible. Same three
    # gate/haul scenarios as Table 1.
    #
    # VARIANT B (2026-08-24, with the drainage limit shipped on): the screen is
    # a UNIT cost and stays UNCLAMPED by the ceiling, because carbon is linear
    # in the application rate, so $/tCO2 is rate-invariant -- an operator on a
    # cap-bound cell applies less rock (down to what the drainage carries) at
    # the same cost per tonne of carbon. The CARBON counted is the capped
    # steady state (cad_ceil): the ceiling sets the quantity, the unclamped
    # unit cost sets whether hauling rock there is worth it at all. Clamping
    # the screen too (the tool's behaviour 2026-08-24 morning) priced a full
    # 30 t/ha against carbon that cannot leave and collapsed the sub-$100
    # world total 0.24 -> 0.08 Gt for no economic reason.
    dpt_life = np.zeros_like(u1)
    prev = np.zeros_like(u1)
    for t in range(1, 61):
        cum = np.interp(u1 * t, ug, gg)
        dpt_life += (cum - prev) * eta * ct / (1.0 + dr) ** t
        prev = cum
    SCREENS = (C.COST_SCREEN_USD_PER_TCO2, 150.0)   # the map's screen, and $150
    econ_cad = {}
    for scn in GATE_SCENARIOS:
        cost = gate_raster(scn) + HAUL_MULT[scn] * rate * d_eff
        with np.errstate(divide="ignore", invalid="ignore"):
            usd = cost / np.maximum(dpt_life, 1e-12)
        for scr in SCREENS:
            passes = mm & (usd < scr) & (dpt_life > 0)
            econ_cad[(scn, scr)] = np.where(passes, cad_ceil, 0.0)
    u90 = np.interp(0.9, gg, ug)
    with np.errstate(divide="ignore"):
        k90 = np.where(u1 > 0, u90 / np.maximum(u1, 1e-12), np.inf)
    cad90 = C.APPLICATION_RATE_T_HA_YR * np.minimum(1.0, 1.0 / k90) * eta * ct

    rows2 = []
    for i, iso in enumerate(isos, start=1):
        sel = mm & (idx == i)
        if not sel.any():
            continue
        hh = ha[sel]
        # area-weighted median effective cadence, years (capped below at 1)
        kc = np.maximum(tau[sel], 1.0)
        o = np.argsort(kc)
        kmed = np.interp(0.5, np.cumsum(hh[o]) / hh.sum(), kc[o])
        rows2.append({
            "iso": iso, "name": names[iso],
            "mha": hh.sum() / 1e6,
            "tech": tech[sel].sum() / 1e6,
            "cad": (cad[sel] * hh).sum() / 1e6,
            "cad_ceil": (cad_ceil[sel] * hh).sum() / 1e6,
            "rock": (R[sel] * hh).sum() / 1e9,
            "kmed": min(kmed, 99.0),
            **{f"ec_{s2}_{int(scr)}": (econ_cad[(s2, scr)][sel] * hh).sum() / 1e6
               for s2 in GATE_SCENARIOS for scr in SCREENS},
        })
    rows2.sort(key=lambda r: -r["cad"])
    keys2 = tuple(["mha", "tech", "cad", "cad_ceil", "rock"]
                  + [f"ec_{s2}_{int(scr)}"
                     for s2 in GATE_SCENARIOS for scr in SCREENS])
    world2 = {k: sum(r[k] for r in rows2) for k in keys2}
    big2 = [r for r in rows2 if r["cad"] >= THRESHOLD_MT
            or r["tech"] >= THRESHOLD_MT]
    rest2 = {k: world2[k] - sum(r[k] for r in big2) for k in keys2}

    hdr2 = (f"{'country':<22}{'tech y1':>9}{'cadence SS':>12}{'w/ drain':>10}"
            f"{'econ opt':>10}{'econ ctr':>10}{'econ cons':>10}"
            f"{'rock Gt/yr':>12}{'median cadence':>16}")
    print(f"\n\nTable 2: steady state maintaining a "
          f"{C.APPLICATION_RATE_T_HA_YR:.0f} t/ha standing rock inventory")
    print("(reapplication paced by modeled dissolution, capped at one full "
          "application per year;")
    print(" econ columns count DRAINAGE-LIMITED carbon, screened on the "
          "unclamped unit cost -- variant B)\n")
    print(hdr2)
    print(f"{'':<22}{'MtCO2/yr':>9}{'MtCO2/yr':>12}{'MtCO2/yr':>10}"
          f"{'MtCO2/yr':>10}{'MtCO2/yr':>10}{'MtCO2/yr':>10}"
          f"{'':>12}{'years':>16}")
    print("-" * len(hdr2))

    def line2(label, r, kmed=None):
        km = f"{r['kmed']:.1f}" if kmed is None and "kmed" in r else (kmed or "")
        print(f"{label:<22}{r['tech']:>9.0f}{r['cad']:>12.0f}"
              f"{r['cad_ceil']:>10.0f}{r['ec_optimistic_100']:>10.0f}"
              f"{r['ec_central_100']:>10.0f}{r['ec_conservative_100']:>10.0f}"
              f"{r['rock']:>12.2f}{km:>16}")

    for r in big2:
        line2(r["name"][:21], r)
    line2("rest of world", rest2, kmed="")
    print("-" * len(hdr2))
    line2("WORLD", world2, kmed="")
    w90 = (cad90 * ha)[mm].sum() / 1e6
    print(f"\nsensitivity: timing reapplication at 90% dissolution of the prior "
          f"cohort instead of\nmean lifetime gives a world total of "
          f"{w90:.0f} MtCO2/yr")
    print(f"PSD constant I_inf = {i_inf:.3f} (mean rock lifetime = "
          f"{i_inf:.3f}/u1 years per cell)")
    print(f"at $150/tCO2 the world economic totals are "
          f"{world2['ec_optimistic_150']:.0f} / {world2['ec_central_150']:.0f} / "
          f"{world2['ec_conservative_150']:.0f} Mt (opt/ctr/cons)")

    # ---- US byproduct-fines supply cap ------------------------------------
    # The demand-side screens above assume rock EXISTS at the scenario gate
    # price wherever the screen passes. For byproduct-gate scenarios that is
    # false at scale: the cheap stream is what quarries already produce. USGS
    # MYB 2023 quantifies it for the US (docs/GATE_COST_AT_SCALE.md):
    #   reported traprock fines-class sales (stone sand + unspecified fine +
    #     crusher run/fill/waste): 4.7 Mt/yr at $11-21/t -- a LOWER bound,
    #     since 62 of 93 Mt of traprock is use-unspecified;
    #   volcanic cinder and scoria, mafic and dirt cheap: 3.3 Mt/yr at $8.83/t
    #     average, the only US stream priced BELOW the $10 gate;
    #   heuristic upper bound: crusher fines run ~20% of hard-rock output
    #     (industry rule of thumb, UNVERIFIED), i.e. ~19 Mt/yr of traprock
    #     fines + scoria ~ 22 Mt/yr.
    # At steady state every acquired tonne eventually delivers eta*CT, so the
    # supply-limited US potential at byproduct prices is:
    us_sel = mm & (idx == iso_of_us(isos))
    eta_us = float((eta[us_sel] * ha[us_sel]).sum() / ha[us_sel].sum())
    lo_rock, hi_rock = 4.7 + 3.3, 19.0 + 3.3          # Mt rock / yr
    lo_co2, hi_co2 = lo_rock * eta_us * ct, hi_rock * eta_us * ct
    print(f"\nUS byproduct-fines supply cap (USGS MYB 2023): the cheap stream "
          f"is {lo_rock:.0f}-{hi_rock:.0f} Mt rock/yr")
    print(f"  -> {lo_co2:.0f}-{hi_co2:.0f} MtCO2/yr steady-state at "
          f"eta_US = {eta_us:.2f} -- SUPPLY, not the cost screen, binds the US "
          f"at byproduct prices")
    print(f"  (screened US potential at byproduct gates was "
          f"{[r for r in rows2 if r['iso'] == 'US'][0]['ec_optimistic_100']:.0f} "
          f"Mt; the same supply logic applies to India's crusher-dust and "
          f"Brazil's po-de-pedra streams, unquantified this session)")

    if "--docx" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--docx") + 1]).expanduser()
        write_docx(out, big2, rest2, world2, SCREENS, i_inf, w90,
                   (lo_rock, hi_rock, lo_co2, hi_co2, eta_us))
        print(f"\nwrote {out}")

    print(f"\ncountries above threshold: {len(big)}")
    print("scenarios: optimistic = current regional byproduct gates "
          "(US 12 / BR 9 / IN 3 / else 10), haul x0.75;")
    print("           central    = the map's defaults ($10 gate, haul x1.00);")
    print("           conservative = at-scale regional gates "
          "(US/CA 18 / EU 17 / BR-LatAm 12 / IN-S Asia 5 / else 12), haul x1.25")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
