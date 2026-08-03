"""
Build the v0 layers and the browser textures.

  python3 scripts/build_v0.py

Reads data/raw/ (see fetch_v0.sh), writes:
  data/processed/v0_layers.npz    float layers, for aggregates and hover readout
  src/textures/tex1.png           RGB = reactivity, eta_DIC, drainage value functions
  src/textures/tex2.png           RGB = cropland fraction, mask flags, flux ceiling
  src/engine_constants.js         generated; the browser's copy of constants.py
  src/colormap.js                 generated; legend stops AND the shader ramp

The area-closure gate runs here and is FATAL. It tests the latitude-weighting
independently of any ERW science: if global cropland does not reconcile with
FAOSTAT, nothing downstream can be trusted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject

sys.path.insert(0, str(Path(__file__).parent))
import constants as C  # noqa: E402
import kinetics as K  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW, PROC = ROOT / "data/raw", ROOT / "data/processed"
INTERIM = ROOT / "data/interim"
SRC = ROOT / "src"


# ---------------------------------------------------------------------------
def master_grid() -> tuple[rasterio.Affine, int, int, rasterio.crs.CRS]:
    """The pH raster defines the grid; everything else is resampled onto it."""
    with rasterio.open(RAW / "ph_0_5.tif") as s:
        return s.transform, s.width, s.height, s.crs


def onto_grid(path: Path, transform, w, h, crs, *, resampling=Resampling.average,
              band: int = 1) -> np.ndarray:  # noqa: D401
    """Reproject any source onto the master grid as float32 with NaN nodata."""
    dst = np.full((h, w), np.nan, dtype="float32")
    with rasterio.open(path) as s:
        src = s.read(band).astype("float32")
        nod = s.nodatavals[band - 1]
        if nod is not None:
            src[src == nod] = np.nan
        reproject(
            source=src, destination=dst,
            src_transform=s.transform, src_crs=s.crs,
            dst_transform=transform, dst_crs=crs,
            src_nodata=np.nan, dst_nodata=np.nan,
            resampling=resampling,
        )
    return dst


def cell_area_km2(transform, w, h) -> np.ndarray:
    """Exact spherical cell area per ROW, broadcast to the grid.

    A = R^2 * dlon * (sin(lat_top) - sin(lat_bot))

    This is the single most important line in the file. Using a constant
    (0.1 deg * 111.32 km)^2 instead overstates global cropland by ~24%, biased
    worst in exactly the high-latitude breadbaskets. Gate 1 below catches it.
    """
    R = C.EARTH_RADIUS_M / 1000.0
    dlon = np.deg2rad(abs(transform.a))
    lat_top = transform.f + np.arange(h) * transform.e
    lat_bot = lat_top + transform.e
    row = R * R * dlon * (np.sin(np.deg2rad(lat_top)) - np.sin(np.deg2rad(lat_bot)))
    return np.repeat(np.abs(row)[:, None], w, axis=1).astype("float32")


# ---------------------------------------------------------------------------
def piecewise(x, knots) -> np.ndarray:
    """Value function from ABSOLUTE breakpoints -- never min-max or percentile.

    knots is [(x0, v0), (x1, v1), ...] ascending in x. Outside the range the
    end values hold. Absolute breakpoints are what make the score domain-
    invariant and keep the colour scale stable while the user moves sliders.
    """
    xs = np.array([k[0] for k in knots], dtype="float64")
    vs = np.array([k[1] for k in knots], dtype="float64")
    out = np.interp(np.asarray(x, dtype="float64"), xs, vs)
    return np.where(np.isnan(x), np.nan, out).astype("float32")


def exceedance_lognormal(q05, q50, q95, threshold) -> np.ndarray:
    """P(X > threshold) from SoilGrids quantiles, lognormal matched in log space.

    Reconstructing a distribution from three quantiles needs an assumption;
    lognormal because SOC is positive and right-skewed. Near the threshold this
    choice is a first-order determinant of the answer, so it is documented and
    versioned rather than buried.

    IMPORTANT: these are predictive quantiles for a ~250 m BLOCK AVERAGE, not
    for a sampled field. Block averaging reduces variance, so this understates
    how often an individual field crosses the threshold. It is a screening
    likelihood, not a calibrated eligibility probability.
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        mu = np.log(np.maximum(q50, 1e-6))
        sigma = (np.log(np.maximum(q95, 1e-6)) - np.log(np.maximum(q05, 1e-6))) / C.Z_90_TWO_SIDED
        sigma = np.maximum(sigma, 1e-3)
        z = (np.log(threshold) - mu) / sigma
    # P(X > t) = 1 - Phi(z);  Phi via erf
    from scipy.special import erf
    return (0.5 * (1.0 - erf(z / np.sqrt(2.0)))).astype("float32")


# ---------------------------------------------------------------------------
def main() -> int:
    transform, w, h, crs = master_grid()
    print(f"grid {w} x {h}, {abs(transform.a):.3f} deg, "
          f"lat {transform.f:.1f} to {transform.f + h * transform.e:.1f}")

    print("resampling inputs onto the grid")
    ph05 = onto_grid(RAW / "ph_0_5.tif", transform, w, h, crs) / C.SOILGRIDS_PH_SCALE
    ph515 = onto_grid(RAW / "ph_5_15.tif", transform, w, h, crs) / C.SOILGRIDS_PH_SCALE
    # Depth-weighted over 0-15 cm, nearer the 20 cm near-field zone than
    # Cascade's whole-profile 0-200 cm average.
    ph = np.where(np.isnan(ph515), ph05, (ph05 * 5.0 + ph515 * 10.0) / 15.0)
    ph[(ph < 2.5) | (ph > 11.0)] = np.nan

    soc = onto_grid(RAW / "soc_0_5.tif", transform, w, h, crs) / 10.0   # dg/kg -> g/kg

    tair = onto_grid(RAW / "wc/wc2.1_10m_bio_1.tif", transform, w, h, crs)     # deg C
    precip = onto_grid(RAW / "wc/wc2.1_10m_bio_12.tif", transform, w, h, crs)  # mm/yr

    # Monthly soil temperature and soil moisture, if prepared. These replace the
    # two documented stand-ins AND enable monthly integration, which is the point
    # -- see integrate_monthly() below.
    mT = INTERIM / "soilT_5_15cm_monthly.tif"
    mS = INTERIM / "soilmoist_monthly.tif"
    monthly = mT.exists() and mS.exists()
    if monthly:
        # Stored as int16 decidegrees to keep the committed artefact small; the
        # scale factor lives in the file's tags so it cannot be lost.
        with rasterio.open(mT) as _s:
            t_scale = float(_s.tags().get("scale_factor", 1.0))
        soilT_m = np.stack([onto_grid(mT, transform, w, h, crs, band=b)
                            for b in range(1, 13)]) / t_scale
        moist_m = np.stack([onto_grid(mS, transform, w, h, crs, band=b)
                            for b in range(1, 13)])

    # Potapov et al. 2022 percent-cropland, 0-100 per 0.025 deg cell.
    #
    # NOT the GLAD "cropland probability" layer that an earlier version of this
    # script used. That one is Pittman et al. 2010, a MODIS classification
    # PROBABILITY over 2000-2008, and its own documentation says to threshold it
    # against national statistics rather than integrate it -- so summing
    # probability x area was not a valid area estimate. Gate 1 caught it.
    print("reprojecting Potapov percent-cropland onto the grid (area-weighted)")
    crop = onto_grid(RAW / "potapov_crop3km_2019.tif", transform, w, h, crs) / 100.0
    crop = np.clip(np.nan_to_num(crop, nan=0.0), 0.0, 1.0)

    area = cell_area_km2(transform, w, h)

    # ---- GATE 1: area closure. FATAL. Tests the latitude weighting with no ERW
    # science involved, against the cropland product's OWN published total.
    gha = float(np.nansum(crop * area)) * 100.0 / 1e9          # km2 -> ha -> Gha
    naive_km2 = (abs(transform.a) * 111.32) ** 2
    gha_naive = float(np.nansum(crop) * naive_km2) * 100.0 / 1e9
    inflation = gha_naive / gha - 1.0
    lo, hi, _ = C.GATES["cropland_area_gha"]
    ilo, ihi = C.GATES["naive_area_inflation"]

    ok_total = lo <= gha <= hi
    ok_infl = ilo <= inflation <= ihi
    print()
    print(f"  GATE 1a total: {gha:.3f} Gha vs Potapov 2019 map-based "
          f"{C.CROPLAND_POTAPOV_2019_MAP_MHA / 1000:.3f} Gha "
          f"({gha / (C.CROPLAND_POTAPOV_2019_MAP_MHA / 1000) - 1:+.1%})  "
          f"[{'PASS' if ok_total else 'FAIL'}]")
    print(f"  GATE 1b latitude weighting: dropping cos(lat) inflates by "
          f"{inflation:+.1%}, expected {ilo:.0%}-{ihi:.0%}  "
          f"[{'PASS' if ok_infl else 'FAIL'}]")
    print(f"    Reconciliation, reported not reconciled: FAOSTAT cropland is "
          f"{C.CROPLAND_FAOSTAT_2022_MHA / 1000:.3f} Gha. The "
          f"{(C.CROPLAND_FAOSTAT_2022_MHA - C.CROPLAND_POTAPOV_2019_MAP_MHA) / 1000:.3f} "
          f"Gha gap is structural:")
    for k, v in C.CROPLAND_GAP_COMPONENTS_MHA.items():
        print(f"      {v:6.0f} Mha  {k}")
    print("    For ERW this matters: permanent woody crops ARE protocol-eligible")
    print("    (Brazilian citrus is a live deployment setting), so a herbaceous-only")
    print("    mask understates addressable area, concentrated in the tropics.")
    if not (ok_total and ok_infl):
        print("  FATAL: aborting. Nothing downstream is trustworthy.")
        return 1

    # ---- Physics
    print()
    print("computing layers")
    T_K = tair + 273.15
    # Fallback wetness proxy, used only if the monthly stack is absent.
    wet = np.clip(precip / 1200.0, 0.0, 1.0)

    # ---- Drainage: real groundwater recharge, replacing the 0.35 x precip
    # placeholder. Nearest-neighbour from 0.5 deg so the coarseness stays
    # VISIBLE rather than being interpolated into a smooth field that does not
    # exist -- the effective-resolution policy in docs/METHODOLOGY.md.
    rech = INTERIM / "drainage_recharge_mmyr.tif"
    if rech.exists():
        q = onto_grid(rech, transform, w, h, crs,
                      resampling=Resampling.nearest) / 1000.0     # mm/yr -> m/yr
        q = np.clip(np.nan_to_num(q, nan=0.0), 0.0, None)
        q_source = "WaterGAP2-2e recharge"
    else:
        q = np.clip(precip / 1000.0 * 0.35, 0.0, None)
        q_source = "PLACEHOLDER 0.35 x precip -- run prep_layers.py"

    # ---- Paddy: flooded fraction of cell-time, from two independent halves.
    # months/12 comes from GRPI inundation presence (robust to CH4 emission
    # factor); the sub-cell area fraction comes from SPAM irrigated rice.
    # Multiplying them is deliberately conservative: it refuses to treat a cell
    # that is 5% paddy as fully flooded, which would inflate the very paddy
    # prediction this project needs to test rather than assume.
    pm, pa = INTERIM / "paddy_months_flooded.tif", INTERIM / "paddy_area_frac.tif"
    if pm.exists() and pa.exists():
        months = np.nan_to_num(onto_grid(pm, transform, w, h, crs,
                                         resampling=Resampling.nearest), nan=0.0)
        parea = np.nan_to_num(onto_grid(pa, transform, w, h, crs,
                                        resampling=Resampling.average), nan=0.0)
        f_flood = np.clip(parea, 0, 1) * np.clip(months / 12.0, 0, 1)
        paddy_source = "GRPI months x SPAM irrigated-rice fraction"
    else:
        f_flood = np.zeros_like(ph)
        paddy_source = "NONE -- run prep_layers.py"

    # Continuous interpolation, not a binary switch: a cell flooded three months
    # a year does not behave like one flooded year-round.
    pco2 = (C.PCO2_UNSATURATED_UATM
            + f_flood * (C.PCO2_SATURATED_UATM - C.PCO2_UNSATURATED_UATM))

    # Flooded pCO2 must not be paired with drained pH. SoilGrids pH is an
    # air-dried, drained measurement, but submergence converges soil pH toward
    # neutral (van Breemen 1987; measured +1.0-1.5 units in Schulz et al. 2024)
    # -- and the inconsistency flatters paddies, whose pCO2 advantage exists
    # only in acid soil. The CHEMISTRY uses the flooding-adjusted pH; the
    # readout and the protocol pH annotation keep the drained value, which is
    # what a validator would measure on a sampled (drained) core.
    ph_chem = ph + f_flood * (C.PH_FLOODED_CONVERGENCE - ph)

    eta_tr = K.eta_transport(q)

    if monthly:
        # MONTHLY INTEGRATION. Compute the rate each month and average the RATE,
        # never the drivers. Two distinct reasons, and the second matters more:
        #
        #  1. Jensen's inequality. The rate is convex in temperature, so the mean
        #     of the rate exceeds the rate at the mean temperature. The bias is
        #     latitude-dependent, so it does not cancel -- it tilts an
        #     annual-mean map toward the tropics.
        #  2. The temperature x moisture covariance. Weathering needs warm AND
        #     wet simultaneously. Annual means destroy that, biasing HIGH in
        #     Mediterranean climates, where the means look ideal but the two
        #     never coincide, and LOW in monsoon climates.
        soilT_K = soilT_m + 273.15
        # Relative saturation from root-zone storage, normalised by its own
        # local maximum across the year. Crude, and flagged: TerraClimate reports
        # storage in mm, not a saturation fraction, and porosity is not applied.
        smax = np.nanmax(moist_m, axis=0)
        sat_m = np.clip(moist_m / np.maximum(smax, 1e-6), 0.0, 1.0)

        rate_m = np.stack([
            K.rate_ca_mg_release(C.FEEDSTOCK_DEFAULT, ph_chem, soilT_K[i]) * sat_m[i]
            for i in range(12)])
        eta_m = np.stack([K.eta_dic(ph_chem, pco2, soilT_K[i]) for i in range(12)])

        with np.errstate(invalid="ignore"):
            reactivity = np.nanmean(rate_m, axis=0)
            eta = np.nansum(rate_m * eta_m, axis=0) / np.maximum(
                np.nansum(rate_m, axis=0), 1e-30)
        # eta is RATE-WEIGHTED, not a plain mean: the efficiency that matters is
        # the one operating when dissolution is actually happening.

        # Quantify the bias we just removed, rather than asserting it.
        annual_rate = K.rate_ca_mg_release(
            C.FEEDSTOCK_DEFAULT, ph_chem, np.nanmean(soilT_K, axis=0)
        ) * np.nanmean(sat_m, axis=0)
        clim_source = "Lembrechts monthly soil T (5-15 cm) + TerraClimate moisture"
    else:
        reactivity = K.rate_ca_mg_release(C.FEEDSTOCK_DEFAULT, ph_chem, T_K) * wet
        eta = K.eta_dic(ph_chem, pco2, T_K)
        annual_rate = None
        clim_source = "FALLBACK: annual AIR temperature + precipitation proxy"

    # ---- Drainage-concentration ceiling on the CARBON, not on the rock.
    # The carbon reported has to leave dissolved in the water that leaves, so it
    # is bounded by q * [HCO3-]_max * 44 regardless of how fast the rock
    # dissolves. See constants.py FLUX_CEILING_* for why the bound is carbonate
    # saturation with pH ENDOGENOUS, and not the cell's pre-treatment pH.
    #
    # Temperature: the annual mean, because we have no monthly q to weight by.
    # The dependence is weak (3.56/3.03/2.58 mmol/L at 5/15/25 C) and runs the
    # opposite way to the rate law. Drainage is seasonally biased toward cool wet
    # months, when the ceiling is HIGHER, so an annual mean is mildly strict --
    # by less than the 1.4x that the full 5-25 C span spans.
    T_ceil_K = (np.nanmean(soilT_m, axis=0) + 273.15) if monthly else T_K
    ceiling = K.flux_ceiling_t_ha_yr(q, pco2, T_ceil_K)
    ceiling_strict = K.flux_ceiling_t_ha_yr(
        q, pco2, T_ceil_K, omega=C.FLUX_CEILING_OMEGA_STRICT)
    alk_ceiling = K.alkalinity_ceiling_mol_l(pco2, T_ceil_K)

    ref = K.rate_ca_mg_release(
        C.FEEDSTOCK_DEFAULT, C.L1_REF["pH"], C.L1_REF["T_soil_C"] + 273.15
    ) * C.L1_REF["saturation"]
    with np.errstate(divide="ignore", invalid="ignore"):
        L1 = np.log10(reactivity / float(ref))

    cascade = K.cascade_baseline_index(ph, T_K, wet)

    # ---- Eligibility, three-state from exceedance probability.
    # Computed at ~2.8 km by prep_layers.py and then AVERAGED, because averaging
    # the quantiles first and computing the probability from those is not valid
    # uncertainty propagation -- it widened the apparent spread and inflated the
    # "marginal" class. Averaging the probability gives the expected area
    # fraction of the cell that exceeds, which is the screening quantity wanted.
    p_src = INTERIM / "soc_p_exceed.tif"
    if p_src.exists():
        p_soc = np.nan_to_num(
            onto_grid(p_src, transform, w, h, crs), nan=0.0).astype("float32")
        p_soc_method = "computed at ~2.8 km, probability averaged"
    else:
        p_soc = exceedance_lognormal(
            onto_grid(RAW / "soc_q05.tif", transform, w, h, crs) / 10.0, soc,
            onto_grid(RAW / "soc_q95.tif", transform, w, h, crs) / 10.0,
            C.SOC_EXCLUSION_WT_PCT * 10.0)
        p_soc_method = "FALLBACK: quantiles averaged first, not valid propagation"
    ph_warn = (ph < C.PH_WARNING_THRESHOLD)      # annotation only, zero score effect

    # ---- Feedstock: delivered cost, the first genuinely ECONOMIC factor.
    # Unlike the three physical terms it is compensatory -- expensive rock is bad,
    # not impossible -- so it multiplies the CDR-derived score with a floor
    # rather than annihilating it.
    fc = INTERIM / "feedstock_cost.tif"
    if fc.exists():
        cost_usd_t = onto_grid(fc, transform, w, h, crs,
                               resampling=Resampling.average)
        cost_conf = np.nan_to_num(
            onto_grid(INTERIM / "feedstock_conf.tif", transform, w, h, crs,
                      resampling=Resampling.nearest), nan=0.0)
        mafic_frac = np.nan_to_num(
            onto_grid(INTERIM / "mafic_frac.tif", transform, w, h, crs), nan=0.0)
        # Penalty on the haul increment only: 1.0 at the gate cost, where there
        # is no transport to charge for.
        v_cost = np.clip(np.nan_to_num(C.cost_value(cost_usd_t),
                                       nan=C.COST_FLOOR), C.COST_FLOOR, 1.0)
        feed_source = ("GLiM mafic outcrop + MRDS/ANM/OSM mafic-hosted "
                       "quarries, truck only")
    else:
        cost_usd_t = np.full_like(ph, np.nan)
        cost_conf = np.zeros_like(ph)
        mafic_frac = np.zeros_like(ph)
        v_cost = np.ones_like(ph)
        feed_source = "NONE -- run prep_feedstock.py"

    # ---- Suitability is now a value function of GROSS CDR, not a weighted mean
    # of transformed proxies. One set of breakpoints, on a quantity with units,
    # and zero CDR gives zero suitability by construction.
    #
    # The per-term value functions that used to live here are gone. They imposed
    # three sets of arbitrary breakpoints and, combined with a uniform 0.02
    # quantisation floor, gave a cell with zero reactivity a suitability of 27.

    # ---- Indicative gross CO2, tCO2 gross/ha/yr. LOW CONFIDENCE, and the
    # surface-area term is user-controllable rather than hidden.
    #
    # X is the dimensionless rate relative to the reference condition. The three
    # physical terms enter as a PRODUCT with unit exponents, because they are
    # terms in a physical product: no reactivity means no carbon regardless of
    # how well alkalinity would have been retained.
    ceil_t = ((C.FEEDSTOCK_ARCHETYPES[C.FEEDSTOCK_DEFAULT]["CaO_wt"] / C.M_CAO
               + C.FEEDSTOCK_ARCHETYPES[C.FEEDSTOCK_DEFAULT]["MgO_wt"] / C.M_MGO)
              * 1000.0 * 2.0 * C.MOL_CO2_PER_KMOL_CHARGE_T)
    # X carries the DISSOLUTION drivers only: rate and drainage. eta_DIC is a
    # carbon-accounting efficiency, not a rate -- carbonate speciation does not
    # slow the rock dissolving -- so it multiplies the carbon AFTER the
    # dissolved fraction. Inside the exponential it suppressed the predicted
    # fraction weathered by up to ~2x in acid soils, contaminating the one
    # layer field trials can measure.
    X = (reactivity / float(ref)) * eta_tr

    # First-order decay of remaining mass. Replaces a hard clip at 0.6 that
    # pinned 18.9% of cropland area at one value, giving the layer a flat top.
    # Shrinking core over the reference particle-size distribution, evaluated
    # through a monotone lookup: the exact integral is 6,000 size bins per cell
    # and there are 5M cells. The table is dense enough that interpolation error
    # is below the 8-bit texture quantisation -- asserted by gate 14.
    delta_ref = K.retreat_at_reference()
    u_grid = np.concatenate([[0.0], np.geomspace(1e-5, 12.0, 512)])
    g_grid = np.concatenate([[0.0], K.dissolved_fraction(u_grid[1:], C.PSD_REF_WIDTH)])
    u_cell = delta_ref * np.clip(X, 0.0, None) / C.PSD_REF_D50_UM
    frac = np.interp(u_cell, u_grid, g_grid)
    cdr_uncapped = frac * eta * C.APPLICATION_RATE_T_HA_YR * ceil_t

    # THE CEILING BINDS THE CARBON, NOT THE ROCK, and that separation is the
    # physics rather than a convenience. Rock can dissolve without the carbon
    # leaving: field trials measure 10-50x more cations retained in secondary
    # phases than exported (Hammes et al. 2025), and one mesocosm study at up to
    # 200 t/ha measured zero increase in leachate DIC while the rock demonstrably
    # weathered (Vienne et al. 2025). So `frac` -- the one layer field trials can
    # measure directly -- stays uncapped, and the GAP between frac and the capped
    # CDR is now a visible, meaningful quantity instead of an inconsistency.
    #
    # Capped AFTER eta_DIC: what has to fit in the water is the bicarbonate, and
    # that is the post-eta_DIC quantity. eta_DIC is a per-mole conversion
    # efficiency and the ceiling is a concentration bound, so they do not
    # double-count -- one asks what share of released alkalinity carries carbon,
    # the other asks how much alkalinity the water can hold at all.
    if C.FLUX_CEILING_ON:
        cdr = np.minimum(cdr_uncapped, ceiling)
    else:
        cdr = cdr_uncapped

    suit_phys = piecewise(np.log10(np.maximum(cdr, 1e-9)),
                          [(np.log10(x), y) for x, y in C.CDR_SUITABILITY_KNOTS])
    suit_phys = np.where(cdr < C.CDR_NEGLIGIBLE_T_HA_YR, 0.0, suit_phys)
    # Physical half annihilates; economic half only discounts.
    suit = suit_phys * np.power(v_cost, C.COST_EXPONENT_DEFAULT)

    # ---- Report
    m = (crop >= C.CROPLAND_MIN_FRACTION) & np.isfinite(ph)
    aw = (crop * area)[m]

    def wq(x, qs):
        v = x[m]
        g = np.isfinite(v)
        o = np.argsort(v[g])
        cw = np.cumsum(aw[g][o]) / aw[g].sum()
        return [float(v[g][o][np.searchsorted(cw, t)]) for t in qs]

    print(f"  cropland cells (>={C.CROPLAND_MIN_FRACTION:.0%}): {int(m.sum()):,}")
    print(f"  climate:         {clim_source}")
    print(f"  drainage source: {q_source}")
    print(f"  feedstock:       {feed_source}")
    print(f"  paddy source:    {paddy_source}   D_w = {C.DAMKOHLER_DW_M_YR} m/yr "
          f"(published range {C.DAMKOHLER_DW_RANGE[0]}-{C.DAMKOHLER_DW_RANGE[1]})")
    for name, arr, fmt in (("soil pH (0-15 cm)", ph, "{:.2f}"),
                           ("air temp, deg C", tair, "{:.1f}"),
                           ("L1 log10(R/Rref)", L1, "{:+.2f}"),
                           ("eta_DIC", eta, "{:.3f}"),
                           ("eta_transport", eta_tr, "{:.3f}"),
                           ("drainage q, m/yr", q, "{:.3f}"),
                           ("flooded fraction of cell-time", f_flood, "{:.3f}"),
                           ("soil pCO2, uatm", pco2, "{:.0f}"),
                           ("indicative tCO2 gross/ha/yr", cdr, "{:.2f}"),
                           ("delivered cost $/t", cost_usd_t, "{:.0f}"),
                           ("suitability, physics only", suit_phys, "{:.2f}"),
                           ("suitability with cost", suit, "{:.2f}")):
        p10, p50, p90 = wq(arr, (0.10, 0.50, 0.90))
        print(f"    {name:28s} area-weighted p10/p50/p90  "
              + " / ".join(fmt.format(v) for v in (p10, p50, p90)))

    excl = float((aw * (p_soc[m] > C.P_EXCEED_EXCLUDED)).sum() / aw.sum())
    marg = float((aw * ((p_soc[m] > C.P_EXCEED_PASSES)
                        & (p_soc[m] <= C.P_EXCEED_EXCLUDED))).sum() / aw.sum())
    # Reported, not drawn. The screen turns out to be a near-non-constraint on
    # cropland: SOC above 5 wt% is a peatland and boreal-forest phenomenon, and
    # 96% of the globally flagged cells sit north of 50N.
    print(f"    SOC>5wt% screen: {excl:.3%} of cropland area excluded "
          f"(P>{C.P_EXCEED_EXCLUDED}); {marg:.1%} would have been 'marginal', "
          f"a class now REPORTED not drawn  [{p_soc_method}]")
    paddy_share = float((aw * (f_flood[m] > 0.05)).sum() / aw.sum())
    print(f"    cells >5% flooded cell-time: {paddy_share:.1%} of cropland area")
    print(f"    pH<5.2 annotation flag: "
          f"{float((aw * ph_warn[m]).sum() / aw.sum()):.1%} of cropland area")
    # Cells inside the cropland mask that have NO monthly climate input, so the
    # rate could not be computed. Previously these fell through the texture
    # encoder's nan_to_num(L1, nan=-3.0) and were drawn as near-zero potential --
    # missing data rendered as a confident "nothing here". They are now their own
    # flagged class. Small, but it is the wrong category, not a small error.
    no_input = ~np.isfinite(L1)
    n_ni = int((m & no_input).sum())
    print(f"    NO CLIMATE INPUT: {n_ni:,} cropland cells "
          f"({float((aw * no_input[m]).sum() / aw.sum()):.3%} of area, "
          f"{float((aw * no_input[m]).sum()) * 100 / 1e6:.2f} Mha) have no monthly "
          f"soil T/moisture; flagged as no-data, not as zero potential")

    if annual_rate is not None:
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = reactivity / np.maximum(annual_rate, 1e-30)
        rr = ratio[m & np.isfinite(ratio) & (annual_rate > 0)]
        if rr.size:
            print(f"    monthly-integrated rate / rate-at-annual-mean: "
                  f"p10 {np.percentile(rr, 10):.2f}  p50 {np.percentile(rr, 50):.2f}  "
                  f"p90 {np.percentile(rr, 90):.2f}")
            print("      >1 is the Jensen effect (convex rate); <1 is the "
                  "temperature-moisture covariance penalty where warm and wet "
                  "do not coincide")

    # ---- GATE 4: zero CDR must give zero suitability. This is the defect that
    # prompted the redesign: a cell with no carbon removal scored 27.
    zero = cdr < C.CDR_NEGLIGIBLE_T_HA_YR
    worst_suit = float(np.nanmax(suit[zero])) if zero.any() else 0.0
    ok4 = worst_suit <= 1e-6
    print(f"  GATE 4 zero CDR -> zero suitability: max suitability among "
          f"{float((aw * zero[m]).sum() / aw.sum()):.1%} of cropland area with "
          f"CDR < {C.CDR_NEGLIGIBLE_T_HA_YR} is {worst_suit:.4f}  "
          f"[{'PASS' if ok4 else 'FAIL'}]")

    # ---- GATE 5: the dissolution function must not saturate against a ceiling
    frac_max = float(np.nanmax(frac))
    pinned = float((aw * (frac[m] > 0.99)).sum() / aw.sum())
    ok5 = pinned < 0.02
    print(f"  GATE 5 no flat top: max dissolved fraction {frac_max:.3f}, "
          f"{pinned:.2%} of area above 0.99  [{'PASS' if ok5 else 'FAIL'}]")

    # ---- GATE 2: indicative CO2 inside the physically plausible envelope
    p50 = wq(cdr, (0.5,))[0]
    ok2 = 0.05 <= p50 <= 10.0
    print(f"  GATE 2 indicative CO2 median {p50:.2f} in 0.05-10 tCO2/ha/yr  "
          f"[{'PASS' if ok2 else 'FAIL'}]")

    # ---- GATE 2b: global gross total against the pre-registered Tier 2 band.
    # REPORTED, NOT ENFORCED, and it currently sits BELOW the band -- which is a
    # finding rather than a failure, and the band is deliberately not widened to
    # accommodate it. docs/VALIDATION.md already states why: the published range
    # is "Consistency, NOT validation... several estimates descend from the same
    # rate-law and surface-area lineage as ours." Those estimates are not bounded
    # by drainage transport either. Beerling et al. 2024's own CDR_pot implies
    # ~29.8 mmol/L bicarbonate at Illinois tile drainage, essentially the same
    # figure this model produced before the ceiling -- so falling below a band
    # derived from that lineage is what imposing the bound is SUPPOSED to do.
    ha = (crop * area)[m] * 100.0                     # km2 -> ha
    gt = float((ha * np.nan_to_num(cdr[m])).sum() / 1e9)
    gt_un = float((ha * np.nan_to_num(cdr_uncapped[m])).sum() / 1e9)
    glo, ghi = C.GATES["global_gross_gtco2_yr"]
    inside = glo <= gt <= ghi
    print(f"  GATE 2b global gross {gt:.3f} GtCO2/yr (uncapped {gt_un:.3f}) vs "
          f"pre-registered {glo}-{ghi}  "
          f"[{'inside' if inside else 'BELOW THE BAND -- reported, band NOT widened'}]")
    if not inside:
        print(f"    the band descends from estimates that also lack a transport "
              f"bound, so this is the expected direction; see docs/VALIDATION.md "
              f"section 2 and CHANGELOG 'Flux reconciliation, August 2026'")

    # ---- GATE 3: stoichiometric ceiling never exceeded
    worst = float(np.nanmax(cdr) / C.APPLICATION_RATE_T_HA_YR)
    ok3 = worst <= ceil_t + 1e-9
    print(f"  GATE 3 stoichiometric ceiling: max {worst:.3f} <= {ceil_t:.3f} "
          f"tCO2/t  [{'PASS' if ok3 else 'FAIL'}]")

    # ---- GATE 12: the reported carbon must be carryable in the reported water.
    # This is the gate the flux-reconciliation work exists to install. It is a
    # tautology once the cap is applied, which is exactly the point: it fails
    # loudly if anyone removes the cap, changes the order of operations, or
    # reintroduces a path that writes CDR without bounding it.
    over = cdr > ceiling * (1.0 + 1e-9)
    frac_over = float((aw * over[m]).sum() / aw.sum())
    if C.FLUX_CEILING_ON:
        ok12 = frac_over <= 1e-9
        print(f"  GATE 12 flux reconciliation: {frac_over:.2%} of cropland area "
              f"reports more carbon than its drainage can carry  "
              f"[{'PASS' if ok12 else 'FAIL'}]")
    else:
        # The ceiling is computed and shipped in the texture but NOT applied, by
        # decision, pending external review. Gate 12 cannot pass in that state and
        # must not pretend to: it reports the exceedance instead, so the finding
        # stays in front of anyone who runs the build rather than disappearing
        # along with the cap.
        print(f"  GATE 12 flux reconciliation: DISABLED "
              f"(constants.FLUX_CEILING_ON = False). Reported, not enforced: "
              f"{frac_over:.1%} of cropland area reports more carbon than its "
              f"drainage can carry.")

    # What the cap actually did, reported as a finding rather than hidden.
    with np.errstate(divide="ignore", invalid="ignore"):
        exceed = cdr_uncapped / np.maximum(ceiling, 1e-12)
        implied = cdr_uncapped * 1e6 / C.M_CO2_G_MOL / np.maximum(q * 1e7, 1e-9)
    bound = (aw * (cdr_uncapped[m] > ceiling[m] * 1.000001)).sum() / aw.sum()
    e10, e50, e90 = wq(exceed, (0.1, 0.5, 0.9))
    i10, i50, i90 = wq(implied, (0.1, 0.5, 0.9))
    a10, a50, a90 = wq(alk_ceiling, (0.1, 0.5, 0.9))
    u50 = wq(cdr_uncapped, (0.5,))[0]
    s50 = wq(np.minimum(cdr_uncapped, ceiling_strict), (0.5,))[0]
    would = "binds" if C.FLUX_CEILING_ON else "WOULD bind"
    capped50 = wq(np.minimum(cdr_uncapped, ceiling), (0.5,))[0]
    print(f"    ceiling {would} on {bound:.1%} of cropland area; median "
          f"{u50:.3f} -> {capped50:.3f} tCO2/ha/yr "
          f"({u50 / max(capped50, 1e-12):.1f}x)"
          + ("" if C.FLUX_CEILING_ON else "  -- NOT APPLIED, see gate 12"))
    print(f"    Omega sensitivity: median CDR {s50:.3f} (Omega="
          f"{C.FLUX_CEILING_OMEGA_STRICT:g}, strict) to {capped50:.3f} (Omega="
          f"{C.FLUX_CEILING_OMEGA:g}, shipped default)")
    print(f"    [HCO3-] the UNCAPPED model required: p10 {i10 * 1e3:.1f}  "
          f"p50 {i50 * 1e3:.1f}  p90 {i90 * 1e3:.1f} mmol/L")
    print(f"    [HCO3-] ceiling at each cell's own pCO2 and T: p10 "
          f"{a10 * 1e3:.2f}  p50 {a50 * 1e3:.2f}  p90 {a90 * 1e3:.2f} mmol/L")
    print(f"      for scale, measured agricultural tile drainage runs 1-7 mmol/L "
          f"(Hamilton et al. 2007) and ERW trials ACHIEVE 0.11-0.75")
    print(f"    uncapped exceedance: p10 {e10:.1f}x  p50 {e50:.1f}x  "
          f"p90 {e90:.1f}x")

    # The exceedance is MONOTONIC IN TEMPERATURE, and that is the finding that
    # matters more than the level: the ceiling falls with warming while the rate
    # law climbs, so the cap removes most of the map's warm-climate advantage.
    tb = T_ceil_K - 273.15
    print("    exceedance by mean soil temperature (the gradient, not the level):")

    def med_in(v, sel_m):
        """Area-weighted median of v over the cells selected by sel_m."""
        vv, ww = v[sel_m], (crop * area)[sel_m]
        g = np.isfinite(vv)
        o = np.argsort(vv[g])
        cw = np.cumsum(ww[g][o]) / ww[g].sum()
        return float(vv[g][o][np.searchsorted(cw, 0.5)])

    warm_cool, wc_ratio = {}, (None, None)
    for lo, hi in [(0, 10), (10, 15), (15, 20), (20, 25), (25, 45)]:
        sel = m & np.isfinite(tb) & (tb >= lo) & (tb < hi)
        if sel.sum() < 100:
            continue
        share = float((crop * area)[sel].sum() / aw.sum())
        u, c = med_in(cdr_uncapped, sel), med_in(ceiling, sel)
        print(f"      {lo:2d}-{hi:2d} C  ({share:5.1%} of area): uncapped "
              f"{u:.3f}  ceiling {c:.3f}  -> {u / max(c, 1e-12):.1f}x")
        warm_cool[(lo, hi)] = (u, c)
    if (0, 10) in warm_cool and (25, 45) in warm_cool:
        (uc, cc), (uw, cw_) = warm_cool[(0, 10)], warm_cool[(25, 45)]
        wc_ratio = (uw / max(uc, 1e-12), cw_ / max(cc, 1e-12))
        print(f"      warmest/coolest ratio of the median: uncapped model "
              f"{uw / max(uc, 1e-12):.2f}x, ceiling {cw_ / max(cc, 1e-12):.2f}x "
              f"-- the ceiling does not support a warm-climate advantage, because "
              f"C_eq FALLS with warming while the rate law rises")

    # ---- Quarry overlay: copy the point list into src/ so the page can draw it
    qp = INTERIM / "quarry_points.json"
    if qp.exists():
        import shutil
        (SRC / "quarries.js").write_text(
            "/* GENERATED by scripts/build_v0.py from data/interim/quarry_points.json.\n"
            "   [lon, lat, source] per quarry. Sources: MRDS (US national register),\n"
            "   ANM (Brazilian mining-title register), OSM (crowd-sourced). */\n"
            "window.QUARRIES = " + qp.read_text() + ";\n")
        n_q = len(json.loads(qp.read_text())["points"])
        print(f"  wrote {SRC / 'quarries.js'} ({n_q:,} points)")
    else:
        n_q = 0

    # ---- Save floats for aggregates and hover readout
    PROC.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        PROC / "v0_layers.npz",
        ph=ph, tair=tair, precip=precip, soc=soc, crop=crop, area=area,
        L1=L1.astype("float32"), eta=eta.astype("float32"),
        eta_tr=eta_tr.astype("float32"), cdr=cdr.astype("float32"),
        cdr_uncapped=cdr_uncapped.astype("float32"),
        ceiling=ceiling.astype("float32"),
        alk_ceiling=alk_ceiling.astype("float32"),
        cascade=cascade.astype("float32"), p_soc=p_soc,
        q=q.astype("float32"), f_flood=f_flood.astype("float32"),
        pco2=pco2.astype("float32"),
        # The temperature the ceiling was evaluated at, so downstream figures bin
        # on the SAME basis the build reports. Binning on air temperature instead
        # shifted the headline warm/cool ratio from 4.37x to 4.63x.
        t_ceil_c=(T_ceil_K - 273.15).astype("float32"),
        transform=np.array(transform).reshape(3, 3)[:2].ravel(),
    )
    print(f"  wrote {PROC / 'v0_layers.npz'} "
          f"({(PROC / 'v0_layers.npz').stat().st_size / 1e6:.1f} MB)")

    # ---- Encode textures
    write_textures(crop, p_soc, ph_warn, cdr, m,
                   cascade=cascade, ph=ph, L1=L1, eta=eta, eta_tr=eta_tr,
                   v_cost=v_cost, cost_conf=cost_conf, ceiling=ceiling,
                   cdr_per_frac=C.APPLICATION_RATE_T_HA_YR * ceil_t,
                   no_input=no_input)
    gha_eval = float(((crop * area)[m & np.isfinite(L1)]).sum() * 100.0 / 1e9)
    emit_js(transform, w, h, gha, p50,
            cdr_per_frac=C.APPLICATION_RATE_T_HA_YR * ceil_t,
            clim_source=clim_source, monthly=monthly, n_quarries=n_q,
            gha_eval=gha_eval, soc_excluded=excl, soc_marginal=marg,
            ceiling_binds=bound, ceiling_med=wq(ceiling, (0.5,))[0],
            warm_cool=wc_ratio, exceed_med=e50)
    print()
    print("done. Open src/index.html over HTTP:")
    print("  python3 -m http.server 8000 --directory src")
    return 0


# ---------------------------------------------------------------------------
def quantize(v, floor: float) -> np.ndarray:
    """Value function -> uint8, reserving 0 EXCLUSIVELY for masked cells.

    The floor is a correctness requirement: measured, with a floor of 1e-3 a
    single 8-bit step near zero moves the composite score by 0.23. At 0.02 the
    max error is 0.006. See constants.EPS_QUANTIZE.
    """
    x = np.clip(np.nan_to_num(v, nan=0.0), floor, 1.0)
    return (5 + np.rint((x - floor) / (1.0 - floor) * 250.0)).astype("uint8")


def write_textures(crop, p_soc, ph_warn, cdr, valid,
                   *, cascade, ph, L1, eta, eta_tr, v_cost, cost_conf,
                   ceiling, cdr_per_frac, no_input) -> None:
    from PIL import Image
    out = SRC / "textures"
    out.mkdir(parents=True, exist_ok=True)
    h, w = crop.shape

    def rgba(r, g, b):
        a = np.full((h, w), 255, dtype="uint8")   # alpha ALWAYS 255, never data
        return Image.fromarray(np.dstack([r, g, b, a]), "RGBA")

    # tex1 now carries the RAW PHYSICAL TERMS, not value functions, so the shader
    # can compute gross CDR itself and derive suitability from it. Value 0 is
    # reserved for masked cells; data starts at 5/255.
    #   r = normalised L1 = log10(R/R_ref), so (R/R_ref) = 10^L1
    #   g = eta_DIC        (already 0-1, no transform needed)
    #   b = eta_transport  (already 0-1)
    # A raw value of exactly 0 must survive encoding, because zero really does
    # mean zero carbon -- hence the linear 5..255 map with no epsilon floor here.
    lo, hi = L1_ENC
    l1n = np.clip((np.nan_to_num(L1, nan=lo) - lo) / (hi - lo), 0.0, 1.0)
    enc = lambda x: np.rint(5 + np.clip(np.nan_to_num(x, nan=0.0), 0, 1) * 250.0)
    r1 = np.where(valid, np.rint(5 + l1n * 250.0), 0).astype("uint8")
    g1 = np.where(valid, enc(eta), 0).astype("uint8")
    b1 = np.where(valid, enc(eta_tr), 0).astype("uint8")

    # Bit-packed flags. NEAREST filtering only; bilinear across a flag boundary
    # would interpolate garbage bit patterns.
    flags = np.zeros((h, w), dtype="uint8")
    flags |= np.where(valid, 1, 0).astype("uint8")                       # bit0 in-domain
    flags |= np.where(p_soc > C.P_EXCEED_EXCLUDED, 2, 0).astype("uint8")  # bit1 excluded
    # bit2 was a MARGINAL state (0.1 < P <= 0.9), drawn as a hatch. Removed in an
    # earlier build: it covered 53% of cropland, which made it the dominant visual
    # feature of the map while conveying almost nothing actionable. REUSED here for
    # NO CLIMATE INPUT -- cells inside the cropland mask whose rate could not be
    # computed because the monthly soil temperature and moisture stacks have no
    # data there. They used to fall through nan_to_num below and be drawn as
    # near-zero potential, which states "no removal here" where the honest answer
    # is "we do not know".
    # Masked to the in-domain cells: L1 is NaN over every non-cropland pixel too,
    # and an unmasked flag would claim 3.5M "no input" cells instead of the 695
    # that are actually inside the map.
    flags |= np.where(no_input & valid, 4, 0).astype("uint8")            # bit2 no input
    flags |= np.where(ph_warn, 8, 0).astype("uint8")                     # bit3 pH<5.2 note

    r2 = np.rint(np.clip(crop, 0, 1) * 255).astype("uint8")

    # tex2.b USED TO BE cdr/10, an "indicative CDR" channel that nothing read --
    # dead since the shader started deriving CDR from the raw terms itself. It now
    # carries the DRAINAGE-CONCENTRATION CEILING, which the shader needs because
    # the grind slider recomputes CDR live: without the ceiling on the GPU, moving
    # the slider would walk the displayed carbon straight back through the bound.
    #
    # Stored as log10(ceiling / cdrPerFrac) so the resolution is even in log
    # space. A linear encoding over the full range would quantise the arid tail --
    # where the ceiling is 0.01-0.1 tCO2/ha/yr and matters most -- to one or two
    # steps. Value 0 stays reserved for masked cells, so a true zero ceiling
    # (q = 0) lands on 5, the bottom of the range, which is 1e-4 of cdrPerFrac and
    # far below CDR_NEGLIGIBLE anyway.
    lo_c, hi_c = CEIL_ENC
    with np.errstate(divide="ignore", invalid="ignore"):
        cn = np.log10(np.maximum(ceiling / max(cdr_per_frac, 1e-12), 1e-30))
    cn = np.clip((np.nan_to_num(cn, nan=lo_c, neginf=lo_c) - lo_c) / (hi_c - lo_c),
                 0.0, 1.0)
    b2 = np.where(valid, np.rint(5 + cn * 250.0), 0).astype("uint8")

    # tex3 carries the Cascade baseline and raw soil pH. The baseline needs its
    # own channel: an earlier version drew "Cascade baseline" from the CDR
    # channel, so the mode was showing the wrong layer under a scientific label.
    #
    # Cascade's index spans ~4 orders of magnitude across cropland, so it is
    # stored as a log10 ratio to its own area-weighted median and then rescaled.
    # A linear encoding would quantise all but the acid tropics to zero -- which
    # is itself the point of the comparison, but it has to be visible, not lost
    # in the 8-bit floor.
    casc = np.where(valid & (cascade > 0), cascade, np.nan)
    med = float(np.nanmedian(casc))
    with np.errstate(divide="ignore", invalid="ignore"):
        lc = np.log10(casc / med)
    r3 = np.where(np.isfinite(lc),
                  np.rint(np.clip((lc + 2.0) / 4.0, 0, 1) * 255), 0).astype("uint8")
    # Soil pH over 3.0-10.0 for the hover readout.
    g3 = np.where(np.isfinite(ph),
                  np.rint(np.clip((ph - 3.0) / 7.0, 0, 1) * 255), 0).astype("uint8")
    # tex3.b = the cost value function, so the shader can apply the economic
    # multiplier live. Encoded over [COST_FLOOR, 1] since that is its full range.
    b3 = np.where(valid, np.rint(5 + np.clip(
        (v_cost - C.COST_FLOOR) / (1.0 - C.COST_FLOOR), 0, 1) * 250.0),
        0).astype("uint8")

    for name, img in (("tex1", rgba(r1, g1, b1)), ("tex2", rgba(r2, flags, b2)),
                      ("tex3", rgba(r3, g3, b3))):
        p = out / f"{name}.png"
        img.save(p, optimize=True)
        print(f"  wrote {p} ({p.stat().st_size / 1e6:.2f} MB)")


# L1 storage range. Wide enough that the particle-size shift cannot push a real
# value off the end of the 8-bit encoding.
L1_ENC = (-3.0, 3.0)

# Flux-ceiling storage range, as log10(ceiling / cdrPerFrac). The ceiling cannot
# exceed the stoichiometric maximum by construction, so the top only needs a
# little headroom above 0; the bottom has to reach the arid tail, where the
# ceiling is ~1e-3 of cdrPerFrac. 250 steps over 4.3 dex is 4% per step.
CEIL_ENC = (-4.0, 0.3)

RAMP = [  # viridis-like, colour-blind safe, legible in light and dark
    (0.00, "#3b1f4d"), (0.20, "#3d4a8f"), (0.40, "#2a7b8f"),
    (0.60, "#3fa66b"), (0.80, "#a8c93a"), (1.00, "#f7e94a"),
]

# Fraction weathered gets its OWN ramp, magma-like, because it is a different
# KIND of quantity from suitability: a physical prediction with a defined unit and
# an observable counterpart, not a normative score. Sharing viridis would invite
# reading one as a restatement of the other. Both are monotonic in lightness and
# so stay colour-blind safe; they differ in hue family (magenta-orange against
# teal-green), which is the part that distinguishes them at a glance.
# Extra stops below 0.2 on purpose. The scale stays LINEAR in percent, because
# that is what makes it readable against reported field values, but a quarter of
# cropland area falls below 6% weathered and a plain magma bottom renders all of
# it as near-black. Lifting and spreading the low end distinguishes 2% from 6% --
# a real 3x difference -- without touching the mapping from value to position.
RAMP_FRAC = [
    (0.00, "#1c1233"), (0.07, "#3a1a5c"), (0.14, "#5e1f79"),
    (0.28, "#8c2981"), (0.50, "#c9457b"), (0.75, "#f1705d"),
    (1.00, "#fdc98a"),
]


def _grid_through(lo, hi, ref, n, nd):
    """n points spanning [lo, hi] with `ref` guaranteed to be an EXACT node.

    The browser interpolates the particle-size shift table bilinearly, so a
    reference grind that is not a node interpolates to a NON-ZERO shift. The
    slider therefore read "1.01x faster weathering than the reference grind"
    while its own badge said "Reference", and that +1% propagated into every
    displayed CDR. Plain np.linspace put the reference between nodes in both
    axes: 150 um fell between 126.1 and 154.8, and width 1.5 between 1.45 and
    1.60.

    Splitting the range at the reference makes the shift exactly 0 there by
    construction, and as a side benefit it puts more nodes at the fine end,
    where SSA varies fastest and the interpolation error was largest.

    Rounded here to the emitted precision so the table can be computed at the
    SAME coordinates the browser reads -- previously the grid was rounded after
    the table was computed at full precision, a second small inconsistency.
    """
    lo_n = max(2, 1 + int(round((n - 1) * (ref - lo) / (hi - lo))))
    a = np.linspace(lo, ref, lo_n)
    b = np.linspace(ref, hi, n - lo_n + 1)
    return [round(float(x), nd) for x in np.concatenate([a, b[1:]])]


# Particle-size shift-table axes. Built to pass exactly through the reference
# grind so the slider reports 1.00x there rather than 1.01x. Module level because
# test_kinetics.py gate 8 imports them to check the browser's interpolation.
_D50_GRID = _grid_through(*C.PSD_D50_SLIDER_RANGE, C.PSD_REF_D50_UM, 24, 1)
_WIDTH_GRID = _grid_through(*C.PSD_WIDTH_SLIDER_RANGE, C.PSD_REF_WIDTH, 13, 3)

# Shrinking-core dissolution table, G(u, n), for the browser. u = delta/d50 on a
# log grid; n reuses the width axis. 64 u-nodes keeps bilinear error at 0.0023 in
# fraction, below the 0.0040 the 8-bit texture quantises to anyway (gate 14).
#
# The WIDTH axis is interpolated in JS, not in the shader: the width slider is a
# single global value, so the browser only ever needs one 64-element slice at a
# time. That keeps the shader uniform to 64 floats instead of 832.
_U_LOG = (-5.0, np.log10(12.0))
_U_GRID = np.logspace(*_U_LOG, 64)
_G_TABLE = [[round(float(v), 5) for v in K.dissolved_fraction(_U_GRID, n)]
            for n in _WIDTH_GRID]


def emit_js(transform, w, h, gha, cdr_p50, cdr_per_frac=1.0, gha_eval=None,
            clim_source="unknown", monthly=False, n_quarries=0,
            soc_excluded=0.0, soc_marginal=0.0,
            ceiling_binds=0.0, ceiling_med=0.0,
            warm_cool=(None, None), exceed_med=0.0) -> None:
    if gha_eval is None:
        gha_eval = gha
    # PASS THESE IN, never reach for main()'s locals. Reading a caller local from
    # here raises NameError at the very last step of the build, which leaves a
    # STALE engine_constants.js behind while everything upstream looks fine. That
    # has now happened twice (n_q, then these two), so the signature is the guard.
    km = abs(transform.a) * 2.0 * np.pi * C.EARTH_RADIUS_M / 1000.0 / 360.0
    """One generator for BOTH the legend stops and the shader ramp, so they
    cannot drift. This is the failure mode that broke the sibling BiCRS Atlas."""
    payload = {
        "grid": {"width": w, "height": h,
                 "west": transform.c, "north": transform.f,
                 "dlon": abs(transform.a), "dlat": abs(transform.e)},
        "terms": [
            {"key": "reactivity", "label": "Dissolution rate",
             "hint": "Palandri-Kharaka Ca+Mg release, relative to pH 6.5 / 15 C"},
            {"key": "eta_dic", "label": "Alkalinity retained as DIC",
             "hint": "Carbonate-equilibrium efficiency: what share of released "
                     "alkalinity is actually held as dissolved inorganic carbon"},
            {"key": "drainage", "label": "Drainage / transport",
             "hint": "q/(q+Dw) on WaterGAP recharge; low where water residence limits export"},
        ],
        "epsQuantize": C.EPS_QUANTIZE,
        "aggP": C.AGG_P_DEFAULT,
        "ramp": RAMP,
        "rampFrac": RAMP_FRAC,
        "fracRampMax": C.FRAC_RAMP_MAX,
        "cdrKnots": C.CDR_SUITABILITY_KNOTS,
        "cdrNegligible": C.CDR_NEGLIGIBLE_T_HA_YR,
        "dissolvedFracAtRef": C.DISSOLVED_FRAC_AT_REF,
        "dissolvedFracObserved": list(C.DISSOLVED_FRAC_OBSERVED_RANGE),
        "termExponent": {"default": C.TERM_EXPONENT_DEFAULT,
                         "range": list(C.TERM_EXPONENT_RANGE)},
        # tCO2/ha/yr per unit dissolved fraction = rate x tCO2 per t feedstock.
        # The shader multiplies its computed fraction by this to get CDR.
        "cdrPerFrac": round(cdr_per_frac, 6),
        "l1Enc": {"lo": L1_ENC[0], "hi": L1_ENC[1]},
        # Drainage-concentration ceiling. ceilEnc decodes tex2.b, which stores
        # log10(ceiling / cdrPerFrac); the shader and the JS readout both need it
        # because the grind slider recomputes CDR live.
        "fluxCeiling": {
            "on": C.FLUX_CEILING_ON,
            "enc": {"lo": CEIL_ENC[0], "hi": CEIL_ENC[1]},
            "omega": C.FLUX_CEILING_OMEGA,
            "omegaStrict": C.FLUX_CEILING_OMEGA_STRICT,
            "omegaRange": list(C.FLUX_CEILING_OMEGA_RANGE),
            "fCa": C.FLUX_CEILING_F_CA,
            "source": C.FLUX_CEILING_SOURCE,
            "anchors": {k: list(v)
                        for k, v in C.FLUX_CEILING_ANCHORS_MMOL_L.items()},
            "bindsAreaFrac": round(float(ceiling_binds), 4),
            "medianTco2HaYr": round(float(ceiling_med), 4),
            # Warmest/coolest ratio of the median, uncapped vs at the ceiling.
            # Emitted rather than written into the panel copy, so the sentence in
            # app.js cannot drift from the build the way a hardcoded number would.
            "warmCoolUncapped": (None if warm_cool[0] is None
                                 else round(float(warm_cool[0]), 2)),
            "warmCoolCeiling": (None if warm_cool[1] is None
                                else round(float(warm_cool[1]), 2)),
            # Realised carbon per tonne of rock at the median cell, as a share of
            # the feedstock's stoichiometric potential. Computed, not asserted:
            # it is the cleanest single number for "how much of the rock's carbon
            # actually leaves", and it FALLS as the application rate rises because
            # the ceiling does not scale with how much rock is on the field.
            # Median exceedance of the ceiling, for the "not applied" notice.
            "exceedMedian": round(float(exceed_med), 2),
            "realisedShareOfStoich": round(
                float(ceiling_med) / C.APPLICATION_RATE_T_HA_YR
                / (cdr_per_frac / C.APPLICATION_RATE_T_HA_YR), 4),
        },
        # Shrinking-core dissolution. The browser needs delta_ref and the table
        # because the grind sliders change d50 and n, and grind now enters through
        # the particle-size integral rather than as a multiplier on the rate.
        "dissolution": {
            "model": "shrinking_core",
            "deltaRefUm": round(float(K.retreat_at_reference()), 6),
            "refD50Um": C.PSD_REF_D50_UM,
            "fracAtRef": C.DISSOLVED_FRAC_AT_REF,
            "uLog": {"lo": _U_LOG[0], "hi": round(_U_LOG[1], 6)},
            "widthGrid": _WIDTH_GRID,
            "table": _G_TABLE,
        },
        "damkohler": {"dw": C.DAMKOHLER_DW_M_YR,
                      "dwRange": list(C.DAMKOHLER_DW_RANGE),
                      "tau": round(C.DAMKOHLER_TAU, 4),
                      "tauInEta": C.DAMKOHLER_TAU_APPLIED_IN_ETA,
                      "source": C.DAMKOHLER_SOURCE},
        "psd": {
            "refD50": C.PSD_REF_D50_UM, "refWidth": C.PSD_REF_WIDTH,
            "d50Range": list(C.PSD_D50_SLIDER_RANGE),
            "widthRange": list(C.PSD_WIDTH_SLIDER_RANGE),
            "refSsa": round(K.ssa_geometric(C.PSD_REF_D50_UM, C.PSD_REF_WIDTH), 5),
            "lambdaDefault": C.LAMBDA_DEFAULT,
            "lambdaMeasured": C.LAMBDA_MEASURED,
            "lambdaBasis": C.LAMBDA_MEASURED_BASIS,
            "betMeasured": round(C.STAPAFELL_BET_CM2_PER_G / 1e4, 4),
            "refWidthNarrowForCrush": True,
            "lambdaRange": list(C.LAMBDA_ROUGHNESS_RANGE),
            "deliveryRangeUm": list(C.DELIVERY_P50_SPAN_UM),
            "deliveryP50": {k: v for k, v in C.DELIVERY_P50_UM.items() if v},
            "refWidthAssumed": C.PSD_REF_WIDTH_IS_ASSUMED,
            # Precomputed shift table so the browser needs no gamma function:
            # log10(SSA(d50, n) / SSA(ref)) on a grid the UI interpolates. Both
            # axes pass exactly through the reference grind -- see _grid_through.
            "d50Grid": _D50_GRID,
            "widthGrid": _WIDTH_GRID,
            "shiftTable": [
                [round(float(K.ssa_log_shift(d, n)), 4) for d in _D50_GRID]
                for n in _WIDTH_GRID
            ],
        },
        "kinetics": {"overpredicts": C.KINETICS_OVERPREDICTS,
                     "measuredEaKJ": C.BASALT_APPARENT_EA_MEASURED_KJ,
                     "measuredEaRange": list(C.BASALT_APPARENT_EA_MEASURED_RANGE),
                     "cascadeEaKJ": 68.8,
                     "source": C.BASALT_APPARENT_EA_SOURCE},
        "cascadeEncoding": {"kind": "log10_ratio_to_median",
                            "lo": -2.0, "hi": 2.0},
        "phEncoding": {"lo": 3.0, "hi": 10.0},
        "cost": {"floor": C.COST_FLOOR, "expDefault": C.COST_EXPONENT_DEFAULT,
                 "haulScaleUsdT": C.HAUL_PENALTY_SCALE_USD_T,
                 "tco2PerT": round(C.DELIVERED_BASALT_TCO2_PER_T, 3),
                 "gateUsdT": C.FEEDSTOCK_GATE_COST_USD_T,
                 "truckUsdTKm": C.TRUCK_COST_USD_T_KM,
                 "expOn": C.COST_EXPONENT_ON,
                 "tortuosity": C.ROAD_TORTUOSITY,
                 "outcropToQuarry": C.OUTCROP_TO_QUARRY_FACTOR,
                 "gateRange": list(C.FEEDSTOCK_GATE_COST_RANGE),
                 "gateRegional": C.FEEDSTOCK_GATE_REGIONAL_USD_T,
                 "gateSource": C.FEEDSTOCK_GATE_SOURCE,
                 "source": C.FEEDSTOCK_COST_SOURCE},
        "eligibility": {"version": C.ELIGIBILITY_VERSION,
                        "socThreshold": C.SOC_EXCLUSION_WT_PCT,
                        "pExcluded": C.P_EXCEED_EXCLUDED,
                        "pPasses": C.P_EXCEED_PASSES,
                        "marginalDrawn": False,
                        "excludedShareCropland": round(soc_excluded, 5),
                        "marginalShareCropland": round(soc_marginal, 3)},
        # Label the grid from the ACTUAL spacing, never from a constant that
        # might describe a different build. v0 is 0.1 deg (~11 km), not the 1 km
        # the plan targets, and the header must say so.
        "labels": {"grid": f"{round(abs(transform.a), 4):g}\u00b0 grid (~{km:.0f} km at the equator)",
                   "effectiveRes": C.EFFECTIVE_RES_LABEL,
                   "maxZoom": C.MAX_DISPLAY_ZOOM,
                   "build": "v0 preview"},
        "feedstock": {"archetype": C.FEEDSTOCK_DEFAULT,
                      "tco2PerT": round(C.DELIVERED_BASALT_TCO2_PER_T, 3),
                      "rateTHaYr": C.APPLICATION_RATE_T_HA_YR},
        # evaluatedGha is the area the browser's sample can actually see: in-domain
        # AND with a computable rate. Scaling a mean over evaluated cells by TOTAL
        # cropland would attribute removal to cells we declined to evaluate.
        "stats": {"croplandGha": round(gha, 3),
                  "evaluatedGha": round(gha_eval, 3),
                  "cdrMedian": round(cdr_p50, 2),
                  "quarryPoints": n_quarries},
        "provenance": {
            "soil": "SoilGrids v2.0 via ISRIC WCS (pH 0-15 cm, SOC 0-5 cm + quantiles)",
            "climate": clim_source,
            "cropland": "Potapov et al. 2022 percent-cropland, 3 km",
            "drainage": "WaterGAP2-2e groundwater recharge via ISIMIP3a, 0.5 deg",
            "paddy": "GRPI Landsat inundation months x SPAM2010 irrigated rice",
            "feedstock": ("GLiM full-resolution basic igneous outcrop + USGS MRDS "
                          "mafic-hosted stone producers, ANM SIGMINE titles "
                          "(Brazil) and OSM quarries; truck-only haul, not routed"),
            # Generated from the actual build state, never hardcoded: an earlier
            # version listed stand-ins that had already been replaced, and the
            # deployed page said so for one commit.
            "substitutions": ([] if monthly else [
                "AIR temperature stands in for monthly SOIL temperature",
                "PRECIPITATION stands in for a soil-moisture climatology",
            ]) + [
                "soil moisture is root-zone storage in mm, not a saturation "
                "fraction: porosity normalisation not yet applied",
                "kinetics over-predict measured basalt release; activation energy "
                "is ~2x too high (see the kinetics test)",
            ],
            "dw": {"value": C.DAMKOHLER_DW_M_YR,
                   "range": list(C.DAMKOHLER_DW_RANGE),
                   "source": C.DAMKOHLER_SOURCE},
        },
    }
    (SRC / "engine_constants.js").write_text(
        "/* GENERATED by scripts/build_v0.py from scripts/constants.py.\n"
        "   Do not edit. Edit constants.py and rebuild. */\n"
        "window.ERW = " + json.dumps(payload, indent=2) + ";\n"
    )
    print(f"  wrote {SRC / 'engine_constants.js'}")


if __name__ == "__main__":
    raise SystemExit(main())
