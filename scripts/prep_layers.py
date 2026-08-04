"""
Reduce the large NetCDF sources to small GeoTIFFs on a plain lat/lon grid.

  python3 scripts/prep_layers.py [--delete-raw]

Exists so that `build_v0.py` never has to open a 263 MB NetCDF, and so the raw
downloads can be deleted per the project's download -> derive -> delete rule.
Outputs land in data/interim/ and are a few hundred kB each.

  drainage_recharge_mmyr.tif   WaterGAP2-2e groundwater recharge (qr), 30-yr mean
  drainage_qtot_mmyr.tif       WaterGAP2-2e total runoff (qs + qsb)
  drainage_qs_mmyr.tif         WaterGAP2-2e surface runoff
  drainage_qsb_mmyr.tif        subsurface runoff, derived as qtot - qs
  paddy_months_flooded.tif     GRPI months per year with rice-paddy inundation
  paddy_area_frac.tif          SPAM2010 irrigated-rice area fraction of cell
  soc_p_exceed.tif             P(SOC > 5 wt%), computed fine then averaged

Run with --delete-raw once the outputs look right.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject

sys.path.insert(0, str(Path(__file__).parent))
import constants as C  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW, INTERIM = ROOT / "data/raw", ROOT / "data/interim"

CLIMATOLOGY_YEARS = 30      # trailing window used for the recharge mean


def write_tif(path: Path, arr: np.ndarray, west: float, north: float,
              dlon: float, dlat: float, *, nodata=np.nan) -> None:
    INTERIM.mkdir(parents=True, exist_ok=True)
    h, w = arr.shape
    with rasterio.open(
        path, "w", driver="GTiff", height=h, width=w, count=1,
        dtype="float32", crs="EPSG:4326",
        transform=from_origin(west, north, dlon, dlat),
        nodata=nodata, compress="deflate", tiled=True,
    ) as dst:
        dst.write(arr.astype("float32"), 1)
    print(f"  wrote {path.name}  {arr.shape}  {path.stat().st_size / 1e3:.0f} kB")


def orient_north_down(arr: np.ndarray, lat: np.ndarray):
    """Return (arr, north) with row 0 at the northern edge.

    NetCDF latitude axes disagree on direction -- WaterGAP is descending, GRPI is
    ascending -- and getting this wrong flips a hemisphere silently. Always drive
    it off the coordinate variable rather than assuming.
    """
    if lat[1] > lat[0]:                     # ascending: flip to north-down
        arr = arr[::-1] if arr.ndim == 2 else arr[:, ::-1]
        lat = lat[::-1]
    dlat = abs(float(lat[1] - lat[0]))
    return arr, float(lat[0]) + dlat / 2.0, dlat


# ---------------------------------------------------------------------------
# WaterGAP2-2e water-flux variables we reduce, and where each one lands.
#
# WHY MORE THAN ONE. The transport term needs the water flux through the
# weathering zone, and WaterGAP publishes four candidates that differ by an order
# of magnitude over cropland:
#
#   qr    diffuse groundwater recharge -- water reaching the AQUIFER
#   qs    surface runoff              -- fast component, incl. soil-routed
#                                        lateral flow WaterGAP cannot separate
#   qtot  total runoff = qs + qsb     -- the catchment-scale quantity Maher &
#                                        Chamberlain fit D_w against
#   qsb   subsurface runoff (derived here as qtot - qs)
#
# qr alone is EXACTLY ZERO on 0.10% of cropland area, concentrated in river
# deltas -- the Mekong, the Red River, the middle Yangtze -- where the water
# table is at the surface and drainage leaves laterally to canals rather than
# percolating to an aquifer. Those cells rendered as "negligible ERW potential"
# in some of the wettest cropland on Earth. Carrying all of them lets the
# variable choice be a measured sensitivity instead of an assumption.
WATERGAP_FLUXES = {
    # var: (output filename, human label)
    "qr":   ("drainage_recharge_mmyr.tif", "groundwater recharge"),
    "qtot": ("drainage_qtot_mmyr.tif", "total runoff"),
    "qs":   ("drainage_qs_mmyr.tif", "surface runoff"),
}


def _watergap_mean(src: Path, var: str):
    """Long-term mean of a WaterGAP flux, mm/yr, north-down.

    Returns (mmyr, north, dlat, dlon, nyr).
    """
    import netCDF4 as nc

    d = nc.Dataset(src)
    q = d[var]
    n = q.shape[0]
    start = max(0, n - CLIMATOLOGY_YEARS * 12)

    # Mean over whole years, accumulated in chunks so we never hold the array.
    acc = np.zeros(q.shape[1:], dtype="float64")
    nyr = 0
    for k in range(start, n - 11, 12):
        yr = np.asarray(q[k:k + 12], dtype="float64")
        yr = np.where(yr > 1e19, np.nan, yr)
        with np.errstate(invalid="ignore"):
            acc += np.nanmean(yr, axis=0)
        nyr += 1

    # kg m-2 s-1 is mm/s for water. Calendar is 365_day.
    # q [mm/yr] = value * 365 * 86400 = value * 31,536,000
    mmyr = (acc / max(nyr, 1)) * 31_536_000.0
    lat = np.asarray(d["lat"][:])
    lon = np.asarray(d["lon"][:])
    mmyr, north, dlat = orient_north_down(mmyr.astype("float32"), lat)
    dlon = abs(float(lon[1] - lon[0]))
    d.close()
    return mmyr, north, dlat, dlon, nyr


def prep_drainage() -> bool:
    """Reduce every available WaterGAP2-2e water flux to a 30-yr mean, mm/yr.

    Only qr is REQUIRED -- it is what the shipped build reads, so a run with just
    watergap_qr.nc present still succeeds. qtot and qs are reduced when present
    and let build_v0 select the drainage variable; qsb is derived as qtot - qs
    rather than downloaded, since it is a further 340 MB for a difference we
    already have both terms of.

    The histsoc scenario runs with historically evolving irrigated area and
    withdrawals, so irrigation return flow is simulated and folded into all of
    these -- which matters for the Indo-Gangetic Plain and other irrigated
    regions.
    """
    got = {}
    for var, (out, label) in WATERGAP_FLUXES.items():
        src = RAW / f"watergap_{var}.nc"
        if not src.exists():
            if (INTERIM / out).exists():
                print(f"  drainage {var}: raw absent, keeping existing {out}")
                got[var] = None       # already derived, nothing to recompute
                continue
            lvl = "SKIP" if var == "qr" else "absent"
            print(f"  {lvl} drainage {var} ({label}): "
                  f"data/raw/watergap_{var}.nc missing (see fetch_v0.sh)")
            continue
        print(f"drainage: WaterGAP2-2e {label} ({var})")
        mmyr, north, dlat, dlon, nyr = _watergap_mean(src, var)
        v = mmyr[np.isfinite(mmyr) & (mmyr > 0)]
        print(f"  {nyr}-year mean, mm/yr over land: p10 {np.percentile(v, 10):.0f}  "
              f"p50 {np.percentile(v, 50):.0f}  p90 {np.percentile(v, 90):.0f}")
        write_tif(INTERIM / out, mmyr, -180.0, north, dlon, dlat)
        got[var] = (mmyr, north, dlat, dlon)

    # qsb = qtot - qs, the water that reached the stream THROUGH the soil column.
    # Clipped at zero: the two means are independent reductions of the same run
    # and tiny negative residuals are rounding, not physics.
    if got.get("qtot") is not None and got.get("qs") is not None:
        (tot, north, dlat, dlon), (sur, *_) = got["qtot"], got["qs"]
        sub = np.clip(tot - sur, 0.0, None)
        sub = np.where(np.isfinite(tot) & np.isfinite(sur), sub, np.nan)
        v = sub[np.isfinite(sub) & (sub > 0)]
        print("drainage: subsurface runoff (qsb), derived as qtot - qs")
        print(f"  mm/yr over land: p10 {np.percentile(v, 10):.0f}  "
              f"p50 {np.percentile(v, 50):.0f}  p90 {np.percentile(v, 90):.0f}")
        write_tif(INTERIM / "drainage_qsb_mmyr.tif", sub, -180.0, north, dlon, dlat)

    return "qr" in got


def prep_paddy_months() -> bool:
    """GRPI -> months per year with rice-paddy inundation.

    GRPI publishes only the CH4 emission field, not the underlying paddy area
    map described in the paper. We therefore use the MONTHLY PRESENCE pattern
    (emission > 0 in a month => flooded that month), which is robust to the
    emission factor, and take the sub-cell AREA fraction from SPAM instead.
    Using the CH4 magnitude as an area proxy would fold in emission-factor
    variation from water management, organic amendments and temperature.

    Sanity check on the source: integrating the emissions gives ~40 Tg CH4/yr,
    at the top of the 25-40 Tg/yr literature range for rice, so the underlying
    paddy extent is at least globally calibrated.
    """
    import netCDF4 as nc

    src = RAW / "grpi_paddy.nc"
    if not src.exists():
        print("  SKIP paddy months: data/raw/grpi_paddy.nc missing")
        return False
    print("paddy: GRPI months flooded")
    d = nc.Dataset(src)
    e = np.asarray(d["emi_ch4"][:])                 # (12, lat, lon)
    months = (e > 0).sum(axis=0).astype("float32")
    lat = np.asarray(d["lat"][:])
    lon = np.asarray(d["lon"][:])
    months, north, dlat = orient_north_down(months, lat)
    active = months > 0
    print(f"  cells with paddy: {int(active.sum()):,}; "
          f"median months flooded where present: {np.median(months[active]):.0f}")
    write_tif(INTERIM / "paddy_months_flooded.tif", months, -180.0, north,
              abs(float(lon[1] - lon[0])), dlat)
    d.close()
    return True


def prep_paddy_area() -> bool:
    """SPAM2010 irrigated rice physical area (ha per cell) -> fraction of cell.

    This is the conservative half of the paddy layer. Without it, a cell with 5%
    paddy and 95% upland wheat would be assigned the flooded soil pCO2 in full,
    which would inflate exactly the paddy prediction we are trying to test. The
    standing rule is to prefer the option conservative toward the claim being
    critiqued.
    """
    src = RAW / "spam2010V2r0_global_A_RICE_I.tif"
    if not src.exists():
        alt = sorted(RAW.glob("*RICE_I.tif"))
        if not alt:
            print("  SKIP paddy area: SPAM irrigated-rice GeoTIFF missing")
            return False
        src = alt[0]
    print(f"paddy: SPAM irrigated-rice area fraction ({src.name})")
    with rasterio.open(src) as s:
        ha = s.read(1).astype("float64")
        if s.nodata is not None:
            ha[ha == s.nodata] = 0.0
        ha[~np.isfinite(ha)] = 0.0
        t = s.transform
        h, w = s.shape
        # Cell area in hectares, exact on the sphere, per row.
        R = C.EARTH_RADIUS_M / 1000.0
        dlon = np.deg2rad(abs(t.a))
        lat_top = t.f + np.arange(h) * t.e
        lat_bot = lat_top + t.e
        km2 = np.abs(R * R * dlon * (np.sin(np.deg2rad(lat_top))
                                     - np.sin(np.deg2rad(lat_bot))))
        cell_ha = np.repeat((km2 * 100.0)[:, None], w, axis=1)
        frac = np.clip(ha / np.maximum(cell_ha, 1e-9), 0.0, 1.0).astype("float32")
        v = frac[frac > 0]
        print(f"  cells with irrigated rice: {int((frac > 0).sum()):,}; "
              f"median fraction where present: {np.median(v):.3f}; "
              f"total {ha.sum() / 1e6:.1f} Mha")
        # Compare against PHYSICAL area, not harvested area: harvested area
        # double-counts multi-cropped paddy. Global rice physical area is
        # ~110-120 Mha, of which the irrigated share is roughly 70-80 Mha, so a
        # total in the 60s Mha is plausible and slightly on the low side.
        write_tif(INTERIM / "paddy_area_frac.tif", frac, t.c, t.f, abs(t.a), abs(t.e))
    return True


def prep_soc_exceedance() -> bool:
    """P(SOC > 5 wt%) computed at ~2.8 km, then AVERAGED to the analysis grid.

    This corrects a real methodological error. The build previously resampled the
    q05/q50/q95 quantiles to 0.1 deg and computed the probability from the
    averaged quantiles. Averaging quantiles is not averaging distributions, so
    that was not valid uncertainty propagation -- and it inflated the "marginal"
    class, because averaging widened the apparent spread.

    Averaging the PROBABILITY is valid: the mean of an indicator's expectation
    over sub-cells is the expected AREA FRACTION of the coarse cell that exceeds
    the threshold, which is exactly the quantity a screening map wants.

    Two caveats that going finer reduces but does not remove:
      - Change of support. SoilGrids quantiles describe a ~250 m block average,
        while the protocol threshold applies to a sampled field. Block averaging
        reduces variance, so this still understates how often an individual field
        crosses. It is a screening likelihood, not a calibrated eligibility
        probability. 2.8 km is closer to field scale than 11 km, not equal to it.
      - Reconstructing a distribution from three quantiles needs an assumption;
        lognormal, matched in log space, because SOC is positive and right-skewed.
    """
    need = {k: RAW / f"soc_fine_{k}.tif" for k in ("q05", "q50", "q95")}
    missing = [k for k, v in need.items() if not v.exists()]
    if missing:
        print(f"  SKIP SOC exceedance: missing {missing} (see fetch_v0.sh stage 7)")
        return False
    print("SOC exceedance probability at ~2.8 km, then averaged")

    from scipy.special import erf
    with rasterio.open(need["q50"]) as s:
        t, w, h = s.transform, s.width, s.height
        q50 = s.read(1).astype("float64") / 10.0        # dg/kg -> g/kg
    with rasterio.open(need["q05"]) as s:
        q05 = s.read(1).astype("float64") / 10.0
    with rasterio.open(need["q95"]) as s:
        q95 = s.read(1).astype("float64") / 10.0

    thr = C.SOC_EXCLUSION_WT_PCT * 10.0                 # 5 wt% = 50 g/kg
    valid = (q50 > 0) & (q95 > 0) & (q05 > 0)
    with np.errstate(divide="ignore", invalid="ignore"):
        mu = np.log(np.maximum(q50, 1e-6))
        sigma = np.maximum(
            (np.log(np.maximum(q95, 1e-6)) - np.log(np.maximum(q05, 1e-6)))
            / C.Z_90_TWO_SIDED, 1e-3)
        z = (np.log(thr) - mu) / sigma
        p = 0.5 * (1.0 - erf(z / np.sqrt(2.0)))
    p = np.where(valid, p, np.nan).astype("float32")

    fin = p[np.isfinite(p)]
    print(f"  at 2.8 km over land: mean P {fin.mean():.3f}; "
          f"P>0.9 {float((fin > 0.9).mean()):.2%}, "
          f"0.1<P<=0.9 {float(((fin > 0.1) & (fin <= 0.9)).mean()):.2%}")

    # Average the PROBABILITY onto the analysis grid here, so the committed
    # artefact is small and so the valid-propagation step is done once, in one
    # place, rather than implicitly by whatever resampling the build happens to
    # use. Resampling.average on a probability field is the right operation: the
    # result is the expected area fraction of the coarse cell that exceeds.
    from rasterio.transform import from_origin as _fo
    with rasterio.open(RAW / "ph_0_5.tif") as g:
        gt, gw, gh, gcrs = g.transform, g.width, g.height, g.crs
    dst = np.full((gh, gw), np.nan, dtype="float32")
    reproject(source=p, destination=dst,
              src_transform=_fo(t.c, t.f, abs(t.a), abs(t.e)),
              src_crs="EPSG:4326",
              dst_transform=gt, dst_crs=gcrs,
              src_nodata=np.nan, dst_nodata=np.nan,
              resampling=Resampling.average)
    d = dst[np.isfinite(dst)]
    print(f"  averaged to the analysis grid: mean P {d.mean():.3f}; "
          f"P>0.9 {float((d > 0.9).mean()):.2%}, "
          f"0.1<P<=0.9 {float(((d > 0.1) & (d <= 0.9)).mean()):.2%}")
    write_tif(INTERIM / "soc_p_exceed.tif", dst, gt.c, gt.f, abs(gt.a), abs(gt.e))
    return True


def main() -> int:
    made = [prep_drainage(), prep_paddy_months(), prep_paddy_area(),
            prep_soc_exceedance()]
    if "--delete-raw" in sys.argv and all(made):
        for f in ("watergap_qr.nc", "watergap_qtot.nc", "watergap_qs.nc",
                  "grpi_paddy.nc",
                  "spam2010V2r0_global_A_RICE_I.tif",
                  "soc_fine_q05.tif", "soc_fine_q50.tif", "soc_fine_q95.tif"):
            p = RAW / f
            if p.exists():
                mb = p.stat().st_size / 1e6
                p.unlink()
                print(f"  deleted data/raw/{f} ({mb:.0f} MB)")
    elif "--delete-raw" in sys.argv:
        print("  NOT deleting raw: at least one layer was skipped")
    print()
    print("next: python3 scripts/build_v0.py")
    return 0 if any(made) else 1


if __name__ == "__main__":
    raise SystemExit(main())
