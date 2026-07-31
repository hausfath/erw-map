"""
Reduce the large NetCDF sources to small GeoTIFFs on a plain lat/lon grid.

  python3 scripts/prep_layers.py [--delete-raw]

Exists so that `build_v0.py` never has to open a 263 MB NetCDF, and so the raw
downloads can be deleted per the project's download -> derive -> delete rule.
Outputs land in data/interim/ and are a few hundred kB each.

  drainage_recharge_mmyr.tif   WaterGAP2-2e groundwater recharge, 30-yr mean
  paddy_months_flooded.tif     GRPI months per year with rice-paddy inundation
  paddy_area_frac.tif          SPAM2010 irrigated-rice area fraction of cell

Run with --delete-raw once the outputs look right.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

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
def prep_drainage() -> bool:
    """WaterGAP2-2e total groundwater recharge -> long-term mean, mm/yr.

    Recharge, not total runoff: we want the water that percolates below the root
    zone carrying dissolved bicarbonate, not overland flow that never reacted
    with soil. The histsoc scenario runs with historically evolving irrigated
    area and withdrawals, so irrigation return flow is simulated and folded in --
    which matters for the Indo-Gangetic Plain and other irrigated regions.
    """
    import netCDF4 as nc

    src = RAW / "watergap_qr.nc"
    if not src.exists():
        print("  SKIP drainage: data/raw/watergap_qr.nc missing (see fetch_v0.sh)")
        return False
    print("drainage: WaterGAP2-2e groundwater recharge")
    d = nc.Dataset(src)
    q = d["qr"]
    n = q.shape[0]
    months = CLIMATOLOGY_YEARS * 12
    start = max(0, n - months)

    # Mean over whole years, accumulated in chunks so we never hold the array.
    acc = np.zeros(q.shape[1:], dtype="float64")
    nyr = 0
    for k in range(start, n - 11, 12):
        yr = np.asarray(q[k:k + 12], dtype="float64")
        yr = np.where(yr > 1e19, np.nan, yr)
        with np.errstate(invalid="ignore"):
            acc += np.nanmean(yr, axis=0)
        nyr += 1
    mean_rate = acc / max(nyr, 1)

    # kg m-2 s-1 is mm/s for water. Calendar is 365_day.
    # q [mm/yr] = value * 365 * 86400 = value * 31,536,000
    mmyr = mean_rate * 31_536_000.0
    lat = np.asarray(d["lat"][:])
    mmyr, north, dlat = orient_north_down(mmyr.astype("float32"), lat)

    v = mmyr[np.isfinite(mmyr) & (mmyr > 0)]
    print(f"  {nyr}-year mean, mm/yr over land: p10 {np.percentile(v, 10):.0f}  "
          f"p50 {np.percentile(v, 50):.0f}  p90 {np.percentile(v, 90):.0f}")
    print(f"  the placeholder it replaces (0.35 x precip) gave ~350 mm/yr, "
          f"~{350 / np.percentile(v, 50):.0f}x too high at the median")
    write_tif(INTERIM / "drainage_recharge_mmyr.tif", mmyr, -180.0, north,
              abs(float(np.asarray(d["lon"][:])[1] - np.asarray(d["lon"][:])[0])), dlat)
    d.close()
    return True


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


def main() -> int:
    made = [prep_drainage(), prep_paddy_months(), prep_paddy_area()]
    if "--delete-raw" in sys.argv and all(made):
        for f in ("watergap_qr.nc", "grpi_paddy.nc",
                  "spam2010V2r0_global_A_RICE_I.tif"):
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
