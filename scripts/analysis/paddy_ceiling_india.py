"""Field-level drainage-concentration ceiling for a central-India rice paddy.

  python3 scripts/analysis/paddy_ceiling_india.py

WHY THIS EXISTS. The map's ceiling is a CELL mean: f_flood (GRPI months x SPAM
rice fraction) dilutes paddy chemistry by the non-rice share of the cell, and
one annual q at one blended pCO2 carries it. A project whose fields are 100%
bunded paddy needs the FIELD-level version, and the field version has
structure the cell version cannot see (research round 2026-08-24, four
literature threads, sources in docs/PADDY_CEILING_INDIA.md):

  1. TWO EXPORT PATHWAYS AT VERY DIFFERENT CONCENTRATIONS. Percolation moves
     vertically through the puddled layer and plow pan -- through the
     amendment -- and leaves at porewater DIC, bounded by calcite saturation
     at FLOODED soil pCO2 (measured 5-70 kPa, bulk ~20 kPa: Kirk et al. 2019,
     doi:10.1111/pce.13638, VERIFIED; the protocol's 50,000 uatm = 5 kPa sits
     at the BOTTOM of that range). Surface/bund drainage leaves from the
     ponded floodwater, which is nearly degassed: ~1 mM DIC at the
     floodwater-soil boundary in the same verified source. Averaging the two
     into one q x one concentration -- what the map does -- misprices both.
  2. THE WATER IS MEASURED, NOT MODELLED, AT ANALOG SITES. Verified season
     percolation 831-963 mm on a Delhi silt/clay loam (Vibhute et al. 2017,
     doi:10.31018/jans.v9i3.1370, read in full); heavier central-India
     clays sit lower -- bounded inference 300-600 mm/season -- plus surface
     drainage 150-400 mm. WaterGAP qtot at the central-India deployment
     cells (486-609 mm/yr) sits inside that envelope, which is corroboration
     for the map input, not a replacement for site measurement.
  3. ADDITIONALITY HAS A BASELINE TO CLEAR. Regional shallow groundwater
     already carries 4.2-11.4 mmol/L alkalinity (Rajnandgaon tube wells,
     n = 160, Yadav et al. 2020, doi:10.1016/j.gsd.2020.100352, VERIFIED)
     and is commonly calcite-supersaturated; rain-fed FIELD drainage baseline
     is nearer river values, 1.4-2.3 mmol/L (Mahanadi, Acharya et al. 2022,
     doi:10.3389/frwa.2022.846438, VERIFIED). The additional (creditable)
     capacity is ceiling minus baseline, per pathway.

WHAT THIS IS NOT. Not a site prediction: no paddy DIC EXPORT flux has ever
been measured under ERW anywhere (confirmed gap, four search threads), so
this is a carrying-capacity envelope built from measured components, awaiting
the site's own drainage chemistry. The map's own conventions hold: gross CO2,
alkalinity only (no CO2(aq) credit), calcite-saturation bound at the
project's own temperature.
"""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import constants as C  # noqa: E402
import kinetics as K  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

# Mean soil temperature for the ceiling, deg C. The deployment cells'
# annual-mean ceiling temperature is 23-25 C (v0_layers t_ceil_c); the flooded
# season is the monsoon, slightly cooler than the annual daytime extremes.
T_CEIL_C = 25.0

# --- scenario axes, each with its verification status -----------------------
# Flooded-season soil pCO2, uatm. Measured range 5-70 kPa (49,000-690,000
# uatm), bulk soil ~20 kPa (~200,000) in the one verified primary source
# (Kirk et al. 2019, one calcareous Philippine soil, pot experiment).
# Conservative = the Isometric-mandated 50,000 (the bottom of the measured
# range); central = 100,000 (low-middle of the range, deliberately below the
# single-soil bulk measurement); optimistic = 200,000 (that measurement).
# The near-cube-root in the solve keeps the spread modest.
PCO2_FLOOD = {"conservative": 50_000.0, "central": 100_000.0,
              "optimistic": 200_000.0}
# Calcite saturation index at which export is efficiency-capped, same axis
# and same solve as the map (validated against Mayer et al. 2025 PHREEQC to
# 0.95-1.00, gate 13d; paddy pCO2 EXTRAPOLATES beyond the validated 5,000-
# 20,000 uatm grid -- stated, and mild, via the cube root).
SI = {"conservative": 0.0, "central": 0.5, "optimistic": 1.0}
# Dissolved Mg, mM. Basalt-typical 1 mM central (map default); high-rate
# applications (the verified central-India deployments ran 45-100 t/ha) can
# plausibly push higher; no paddy measurement exists either way.
MG_MM = {"conservative": 0.5, "central": 1.0, "optimistic": 3.0}
# Season percolation through the amended root zone, mm. Bounded inference for
# puddled heavy central-India soils (research note section b): the verified
# lighter-soil analog measured 831-963.
PERC_MM = {"conservative": 300.0, "central": 450.0, "optimistic": 600.0}
# Surface/bund drainage, mm/season: bypasses the soil profile, leaves at
# floodwater concentration. Verified analog spans 17.5 (dry yr) - 269 (wet).
SURF_MM = {"conservative": 150.0, "central": 250.0, "optimistic": 400.0}
# Floodwater DIC at the point of overflow, mmol/L. Kirk et al. 2019 measured
# ~1 mM at the floodwater boundary (VERIFIED); scenario spread for depth of
# degassing.
C_FLOODWATER_MM = {"conservative": 0.5, "central": 1.0, "optimistic": 1.5}
# Dry-season percolation through the (cracked, drained) fallow, mm/yr, at the
# drained-soil ceiling. Minor term; unverified, bounded low.
DRY_MM = {"conservative": 0.0, "central": 50.0, "optimistic": 100.0}
# Baseline alkalinity of unamended field drainage, mmol/L, subtracted for the
# ADDITIONAL capacity. Anchored on Mahanadi river water 1.4-2.3 (VERIFIED)
# and the low-lithology tail of regional groundwater; conservative = higher
# baseline = less headroom.
BASELINE_MM = {"conservative": 3.0, "central": 2.0, "optimistic": 1.0}

M_CO2 = C.M_CO2_G_MOL


def t_per_ha(mm, mmol_l):
    """mm of water at mmol/L alkalinity -> tCO2/ha (1 mm/ha = 1e4 L)."""
    return mm * 1e4 * mmol_l * 1e-3 * M_CO2 / 1e6


def main() -> int:
    TK = T_CEIL_C + 273.15
    print("Field-level drainage-concentration ceiling: central-India paddy")
    print(f"(100% paddy field, ceiling T = {T_CEIL_C:.0f} C; the map's cell "
          f"values dilute by the cell's non-rice share)\n")
    hdr = (f"{'':>34}{'conservative':>14}{'central':>10}{'optimistic':>12}")
    print(hdr)
    rows = {}
    for s in ("conservative", "central", "optimistic"):
        alk_f = float(K.alkalinity_ceiling_mol_l(
            PCO2_FLOOD[s], TK, omega=10.0 ** SI[s], mg_mM=MG_MM[s])) * 1e3
        alk_d = float(K.alkalinity_ceiling_mol_l(
            C.PCO2_UNSATURATED_UATM, TK, omega=10.0 ** SI[s],
            mg_mM=MG_MM[s])) * 1e3
        perc = t_per_ha(PERC_MM[s], alk_f)
        surf = t_per_ha(SURF_MM[s], C_FLOODWATER_MM[s])
        dry = t_per_ha(DRY_MM[s], alk_d)
        gross = perc + surf + dry
        # Baseline leaves in the same water; subtract from the percolation
        # and dry-season pathways (the floodwater term is already nearly
        # baseline: monsoon rain over soil).
        addl = (t_per_ha(PERC_MM[s], max(alk_f - BASELINE_MM[s], 0.0))
                + surf
                + t_per_ha(DRY_MM[s], max(alk_d - BASELINE_MM[s], 0.0)))
        rows[s] = dict(alk_f=alk_f, perc=perc, surf=surf, dry=dry,
                       gross=gross, addl=addl)

    def line(label, key, fmt="{:.2f}"):
        print(f"{label:>34}" + "".join(
            f"{fmt.format(rows[s][key]):>{w}}" for s, w in
            (("conservative", 14), ("central", 10), ("optimistic", 12))))

    line("percolation ceiling, mmol/L", "alk_f")
    line("percolation pathway, tCO2/ha/yr", "perc")
    line("surface-drainage pathway", "surf")
    line("dry-season pathway", "dry")
    line("GROSS carrying capacity", "gross")
    line("ADDITIONAL (baseline-netted)", "addl")

    print(f"\nmap cell values at the verified central-India deployment sites, "
          f"for scale: ceiling 0.95-1.41 tCO2/ha/yr\n(cell means: f_flood "
          f"0.16-0.17 where GRPI sees the paddy, 0 where it does not; the "
          f"field-level\nnumbers above are the like-for-like comparison for a "
          f"project's own fields)")

    # Optional: compare with the verified deliveries if the private fixture
    # is present (gitignored; per-operator data is not ours to publish).
    fx = ROOT / "tests/fixtures/deployments_2026.csv"
    if fx.exists():
        txt = [l for l in fx.read_text().splitlines(keepends=True)
               if not l.startswith("#")]
        dep = [r for r in csv.DictReader(io.StringIO("".join(txt)))
               if r["regime"] == "india_paddy" and r["country"] == "IN"]
        if dep:
            print("\nverified central-India paddy deployments "
                  "(dissolution-based CDR, local fixture):")
            for r in dep:
                cdr = float(r["cdr_tco2_ha"]) * 12.0 / float(r["period_months"])
                g, a = rows["central"]["gross"], rows["central"]["addl"]
                print(f"  {r['deployment']:12s} {cdr:5.2f} tCO2/ha/yr claimed "
                      f"dissolution -> {cdr / g:4.1f}x the central gross "
                      f"capacity, {cdr / a:4.1f}x the additional")
            print("  (>1x does not mean over-crediting: dissolved cations can "
                  "be retained, re-exported\n   later, or precipitated -- but "
                  ">1x cannot leave the field dissolved in the year claimed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
