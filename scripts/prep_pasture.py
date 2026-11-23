"""
Reduce HYDE grazing-land grids to one small area-fraction GeoTIFF.

  python3 scripts/prep_pasture.py PATH [--label "HYDE 3.5, 2023"]

PATH is a HYDE land-use zip (e.g. 2023AD_lu.zip), or a directory holding its
unpacked .asc grids. Output: data/interim/pasture_frac.tif, the fraction of
each 5-arc-minute cell that is HYDE "pasture", stored as uint16 x 10000.
build_v0.py area-averages it onto the map grid; the viewer's "Include managed
pasture" option reads the result. Without the file the build ships no pasture
layer and the option is disabled.

WHAT "PASTURE" MEANS HERE. HYDE splits FAO "permanent meadows and pastures"
into pasture and rangeland by climate, not by observed management: grazing
land with an aridity index above 0.5 is called pasture and "assumed to be more
intensively managed" (HYDE 3.2.1 release notes). It is not a map of land that
is fertilised, limed or reachable by a spreader. Rangeland (about three times
the area, mostly arid, median drainage 50 mm/yr) is deliberately left out.

SOURCE. Klein Goldewijk et al., History Database of the Global Environment.
Current release: https://public.yoda.uu.nl/geo/UU01/F45D44.html (CC BY 4.0).
Utrecht's file server answers scripted clients with a browser check, so the
download is a manual step. HYDE 3.2.1 (to 2017) is on an open mirror,
doi:10.17026/dans-25g-gez3.

Cell areas are computed on the sphere here, not read from HYDE's garea_cr.asc,
so only the one land-use file is needed. The printed total is the check: HYDE
pasture is about 0.8 Gha in every recent release.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

sys.path.insert(0, str(Path(__file__).parent))
import constants as C  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/interim/pasture_frac.tif"
SCALE = 10000


def find_pasture_asc(src: Path, tmp: Path) -> Path:
    """The pasture<year>AD.asc grid inside a zip or directory."""
    if src.is_file() and src.suffix == ".asc":
        return src
    if src.is_file():
        # Info-ZIP, not zipfile: HYDE archives use Deflate64, which Python's
        # zipfile cannot inflate.
        subprocess.run(["unzip", "-o", "-q", "-j", str(src), "pasture*.asc",
                        "-d", str(tmp)], check=True)
        src = tmp
    hits = sorted(p for p in src.rglob("pasture*.asc"))
    if not hits:
        raise SystemExit(f"no pasture*.asc under {src}")
    return hits[-1]


def read_asc(path: Path):
    hdr = {}
    with path.open() as f:
        for _ in range(6):
            k, v = f.readline().split()
            hdr[k.lower()] = float(v)
    a = np.loadtxt(path, skiprows=6, dtype="float32")
    assert a.shape == (int(hdr["nrows"]), int(hdr["ncols"])), a.shape
    return np.where(a == hdr["nodata_value"], np.nan, a), hdr


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 1
    with tempfile.TemporaryDirectory() as td:
        asc = find_pasture_asc(Path(args[0]).expanduser(), Path(td))
        km2, hdr = read_asc(asc)
    year = re.search(r"pasture(\d+)AD", asc.name)
    label = (sys.argv[sys.argv.index("--label") + 1] if "--label" in sys.argv
             else f"HYDE, {year.group(1) if year else 'year unknown'}")

    h, w = km2.shape
    d = 360.0 / w
    north = hdr["yllcorner"] + h * d
    assert abs(hdr["xllcorner"] + 180) < 1e-6 and abs(north - 90) < 1e-3, hdr
    lat_top = np.deg2rad(north - np.arange(h) * d)
    lat_bot = np.deg2rad(north - (np.arange(h) + 1) * d)
    R = C.EARTH_RADIUS_M / 1000.0
    cell = (R * R * np.deg2rad(d) * (np.sin(lat_top) - np.sin(lat_bot)))[:, None]

    total = float(np.nansum(km2)) / 1e7
    frac = np.clip(np.nan_to_num(km2 / cell), 0.0, 1.0)
    kept = float((frac * cell).sum()) / 1e7
    print(f"  {asc.name}: pasture {total:.3f} Gha; as clipped cell fractions "
          f"{kept:.3f} Gha ({kept / total - 1:+.2%})")
    if not 0.6 < total < 1.0:
        raise SystemExit("pasture total is outside 0.6-1.0 Gha: wrong file, "
                         "wrong units, or a HYDE definition change")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(OUT, "w", driver="GTiff", height=h, width=w, count=1,
                       dtype="uint16", crs="EPSG:4326",
                       transform=from_origin(-180.0, north, d, d),
                       compress="deflate", predictor=2, tiled=True) as dst:
        dst.write(np.rint(frac * SCALE).astype("uint16"), 1)
        dst.update_tags(source=label, scale=str(SCALE),
                        definition="HYDE pasture: grazing land, aridity index > 0.5")
    print(f"  wrote {OUT.name}  [{label}]  {OUT.stat().st_size / 1e6:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
