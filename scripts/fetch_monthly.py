"""
Fetch monthly soil temperature and soil moisture, reduce each to the analysis
grid, and delete the source immediately.

  python3 scripts/fetch_monthly.py [--months 1,2,3] [--skip-temp] [--skip-moist]

Writes 12-band GeoTIFFs at 0.1 deg into data/interim/:
  soilT_5_15cm_monthly.tif    deg C, Lembrechts et al. 2022
  soilmoist_monthly.tif       mm root-zone storage, TerraClimate climatology

WHY MONTHLY MATTERS, and it is not mainly the annual mean being wrong:

  1. Jensen's inequality. The rate is convex in temperature, so the mean of the
     rate exceeds the rate at the mean temperature. At Ea ~ 68 kJ/mol with a
     +/-12 C seasonal cycle the monthly-integrated rate is ~1.38x the rate at the
     annual mean, rising to ~1.67x in continental croplands and ~1.02x in the wet
     tropics. Being latitude-dependent, it does not cancel -- it systematically
     tilts an annual-mean map toward the tropics.

  2. The temperature x moisture covariance, which matters more. Weathering needs
     warm AND wet at the same time. Annual means destroy that, biasing HIGH in
     Mediterranean climates (hot dry summer, cool wet winter -- the means look
     ideal but the two never coincide) and LOW in monsoon climates.

DISK DISCIPLINE. The soil-temperature rasters are 30 arcsec, float32, STRIPED
with no overviews (block shape 1 x 43201), so a coarse windowed read over
/vsicurl would transfer more than the whole file. We therefore download each
month, reduce it, and delete it before starting the next -- never holding more
than ~190 MB.
"""

from __future__ import annotations

import subprocess
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

SOILT_URL = "https://zenodo.org/records/7134169/files/soilT_{m}_5_15cm.tif"
TERRA_URL = ("https://climate.northwestknowledge.net/TERRACLIMATE-DATA/"
             "TerraClimate_soil_{y}.nc")
TERRA_YEARS = range(2011, 2021)      # 10-year climatology

# UNIT TRAP, the second one in this file and the more expensive. TerraClimate
# stores `soil` as int16 with scale_factor = 0.1 and add_offset = 0.0 (verified
# against the THREDDS .das, not assumed), and rasterio's read() returns the RAW
# stored integer -- it does not apply CF scaling. The first version of this
# function left `scale` at its 1.0 default, so every value was 10x too large and
# the file's own tag said scale_factor 1.0, which made the error self-consistent
# and therefore invisible.
#
# It survived a long time because build_v0 normalised each cell by its own annual
# maximum, and a constant factor cancels exactly in moist/max(moist). Fixing the
# normalisation without fixing this would have produced a saturation term 10x too
# large, i.e. clipped to 1 nearly everywhere.
#
# Independent confirmation that 0.1 is right, from a source that knows nothing
# about the metadata: as-built annual-maximum storage had a cropland median of
# 680 mm and exceeded SoilGrids root-zone plant-available capacity on 87.9% of
# cropland area, which is impossible for extractable water. Scaled, the median is
# 68 mm against a 141 mm capacity.
#
# Note also that TerraClimate `soil` is "Soil Moisture at End of Month", an
# instantaneous state rather than a monthly mean. See docs/METHODOLOGY.md.
TERRA_SOIL_SCALE = 0.1

# 5-15 cm rather than 0-5 cm: Isometric's near-field zone is the deeper of 20 cm
# or tillage depth + 5-10 cm, so the deeper layer is the better bracket, and the
# top 5 cm swings far more than the reacting volume does.
DEPTH_LABEL = "5-15 cm"


def grid():
    with rasterio.open(RAW / "ph_0_5.tif") as s:
        return s.transform, s.width, s.height, s.crs


def curl(url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["curl", "-sSfL", "--max-time", "1800", "-o", str(dest), url])
    return r.returncode == 0 and dest.exists() and dest.stat().st_size > 1_000_000


def onto(src_path: Path, transform, w, h, crs, *, band=1,
         resampling=Resampling.average, decimate=4,
         scale=1.0, lo_valid=-1e30, hi_valid=1e30) -> np.ndarray:
    """Reduce a source onto the analysis grid using a DECIMATED read.

    The soil-temperature rasters are 21121 x 43201 float32, i.e. 3.65 GB if read
    whole -- which thrashes memory and made the first version of this crawl.
    Passing out_shape lets GDAL average down during the read, so peak memory is
    the size of the intermediate, not the file.

    `decimate` sets how much finer than the target grid the intermediate is. 4x
    keeps enough detail that the final area-weighted average is not biased by
    reading too coarsely, while cutting memory ~250x.
    """
    with rasterio.open(src_path) as s:
        ih = min(s.height, h * decimate)
        iw = min(s.width, w * decimate)
        a = s.read(band, out_shape=(ih, iw),
                   resampling=Resampling.average).astype("float32")
        nod = s.nodatavals[band - 1]
        if nod is not None:
            a[a == nod] = np.nan
        # UNIT TRAP. The Lembrechts rasters declare no nodata, no scale and no
        # offset, but the values are DECIDEGREES Celsius, not degrees: July at
        # 5-15 cm reads 28 to 400, which is 2.8 to 40.0 C. A first pass here
        # treated them as degrees and reported a 110 C global mean.
        # Verified by percentile: /10 gives 2.8 / 12.1 / 19.0 / 25.2 / 40.0 C at
        # the 1/25/50/75/99th, and the minimum of -103.8 is a real -10.4 C rather
        # than a sentinel, so a naive "drop anything below -100" also discarded
        # valid cold cells.
        a *= scale
        a[(a < lo_valid) | (a > hi_valid)] = np.nan
        itrans = s.transform * s.transform.scale(s.width / iw, s.height / ih)
        dst = np.full((h, w), np.nan, dtype="float32")
        reproject(source=a, destination=dst,
                  src_transform=itrans, src_crs=s.crs,
                  dst_transform=transform, dst_crs=crs,
                  src_nodata=np.nan, dst_nodata=np.nan, resampling=resampling)
    return dst


def write_stack(path: Path, bands: list[np.ndarray], transform, crs, desc: str,
                *, scale: float = 1.0, lo: int = -32000, hi: int = 32000):
    """Write a 12-band stack as int16 with a scale factor recorded in the tags.

    float32 is wasteful here: decidegrees C and mm of storage both fit int16
    comfortably, and it takes the two stacks from 111 MB to 27 MB. These files are
    committed so the build runs without re-downloading 3.3 GB, so the difference
    is the difference between a clean repo and one GitHub warns about.
    """
    INTERIM.mkdir(parents=True, exist_ok=True)
    h, w = bands[0].shape
    with rasterio.open(path, "w", driver="GTiff", height=h, width=w,
                       count=len(bands), dtype="int16", crs=crs,
                       transform=transform, nodata=-32768,
                       compress="deflate", predictor=2, tiled=True) as dst:
        for i, b in enumerate(bands, 1):
            q = np.where(np.isfinite(b), np.clip(np.rint(b * scale), lo, hi), -32768)
            dst.write(q.astype("int16"), i)
            dst.set_band_description(i, f"month {i}")
        dst.update_tags(description=desc, scale_factor=str(scale))
    print(f"  wrote {path.name}  {len(bands)} bands  "
          f"{path.stat().st_size / 1e6:.1f} MB")


# ---------------------------------------------------------------------------
def fetch_soil_temperature(months, transform, w, h, crs) -> bool:
    out = INTERIM / "soilT_5_15cm_monthly.tif"
    print(f"soil temperature, {DEPTH_LABEL}, Lembrechts et al. 2022")
    bands = []
    for m in months:
        tmp = RAW / f"_soilT_{m}.tif"
        if not curl(SOILT_URL.format(m=m), tmp):
            print(f"  FAILED month {m}; aborting so a partial stack is not written")
            tmp.unlink(missing_ok=True)
            return False
        mb = tmp.stat().st_size / 1e6
        bands.append(onto(tmp, transform, w, h, crs,
                          scale=0.1, lo_valid=-60.0, hi_valid=60.0))
        tmp.unlink()                       # delete before the next download
        v = bands[-1][np.isfinite(bands[-1])]
        print(f"  month {m:2d}: {mb:6.1f} MB fetched then deleted; "
              f"land mean {v.mean():6.2f} C, range {v.min():6.1f} to {v.max():5.1f}")
    write_stack(out, bands, transform, crs,
                f"Lembrechts et al. 2022 soil temperature {DEPTH_LABEL}, deg C, monthly",
                scale=10.0, lo=-600, hi=600)
    return True


def fetch_soil_moisture(transform, w, h, crs) -> bool:
    out = INTERIM / "soilmoist_monthly.tif"
    print("soil moisture, root zone, TerraClimate climatology "
          f"{TERRA_YEARS.start}-{TERRA_YEARS.stop - 1}")
    acc = [np.zeros((h, w), dtype="float64") for _ in range(12)]
    n = 0
    for y in TERRA_YEARS:
        tmp = RAW / f"_terra_{y}.nc"
        if not curl(TERRA_URL.format(y=y), tmp):
            print(f"  FAILED year {y}; skipping it")
            tmp.unlink(missing_ok=True)
            continue
        mb = tmp.stat().st_size / 1e6
        for m in range(12):
            acc[m] += np.nan_to_num(
                onto(tmp, transform, w, h, crs, band=m + 1, decimate=1,
                     scale=TERRA_SOIL_SCALE, lo_valid=0.0, hi_valid=3000.0),
                nan=0.0)
        tmp.unlink()
        n += 1
        print(f"  {y}: {mb:6.1f} MB fetched then deleted")
    if n == 0:
        return False
    bands = [a / n for a in acc]
    v = bands[6][bands[6] > 0]
    print(f"  {n} years; July land mean {v.mean():.1f} mm root-zone storage")
    write_stack(out, bands, transform, crs,
                "TerraClimate root-zone soil moisture, mm, monthly climatology",
                scale=10.0, lo=0, hi=30000)
    return True


def main() -> int:
    transform, w, h, crs = grid()
    months = range(1, 13)
    for a in sys.argv[1:]:
        if a.startswith("--months"):
            months = [int(x) for x in a.split("=", 1)[1].split(",")]

    ok = True
    if "--skip-temp" not in sys.argv:
        ok &= fetch_soil_temperature(months, transform, w, h, crs)
    if "--skip-moist" not in sys.argv:
        ok &= fetch_soil_moisture(transform, w, h, crs)
    print()
    print("next: python3 scripts/build_v0.py")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
