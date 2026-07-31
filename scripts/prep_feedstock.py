"""
Build the feedstock-access layer: where mafic rock is, where it is actually
quarried, and roughly what it costs to get it to a field.

  python3 scripts/prep_feedstock.py [--delete-raw]

Writes to data/interim/:
  mafic_frac.tif            fraction of cell underlain by basic igneous rock
  mafic_km.tif              great-circle km to the nearest mafic outcrop
  quarry_km.tif             km to the nearest mafic-hosted stone quarry
  feedstock_cost.tif        indicative delivered $/t
  feedstock_conf.tif        0-1 confidence that the quarry inventory is usable

THE CONSTRUCT-VALIDITY PROBLEM, stated up front, because it shapes everything:
lithology is NOT delivered cost. Basalt outcropping under a field is close to
irrelevant if nobody quarries and crushes it within haul range. Cost is set by
quarry location x haul distance x fuel and labour.

But usable quarry inventories are very uneven. USGS MRDS is the only large open
one, it is reliable mainly for the United States, and USGS stopped systematic
updates in 2011 -- while USGS itself counted 3,531 operating US crushed-stone
quarries in 2023. So we do two things rather than pretend to one:

  - GLOBALLY: distance to mafic outcrop. This is an UPPER BOUND on availability,
    since outcrop is not a quarry.
  - WHERE MRDS IS USABLE: distance to a mafic-hosted stone quarry, which is the
    quantity that actually matters.

Having both in one region lets us MEASURE how much outcrop proximity overstates
quarry proximity, and report that ratio as the honest uncertainty everywhere
else, instead of asserting a caveat.

Haul cost is great-circle distance x a tortuosity factor, NOT network routing.
That is the minimum defensible treatment and it is labelled as such. Real routing
needs a friction surface or a road graph; see to_do.md.
"""

from __future__ import annotations

import csv
import sys
import warnings
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import reproject
from scipy import ndimage

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).parent))
import constants as C  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW, INTERIM = ROOT / "data/raw", ROOT / "data/interim"

GLIM = RAW / "glim/LiMW_GIS 2015.gdb"
MAFIC_CLASSES = ("vb", "pb")     # basic volcanic (basalt), basic plutonic (gabbro)
FINE_DEG = 0.025                 # rasterise here, then average to the grid

# Countries where MRDS coverage is dense enough to use the quarry layer at all.
# Deliberately conservative: MRDS is a US product with incidental foreign records.
MRDS_TRUSTED_BBOX = (-172.0, 18.0, -66.0, 72.0)     # continental US + AK


def grid():
    with rasterio.open(RAW / "ph_0_5.tif") as s:
        return s.transform, s.width, s.height, s.crs


def write_tif(path: Path, arr, transform, crs, nodata=np.nan, as_int=False):
    """as_int stores rounded int16, which is plenty for km and $/t and roughly
    halves the committed artefact. These files live in the repo so the build runs
    without re-downloading 1.3 GB, so size is worth caring about."""
    INTERIM.mkdir(parents=True, exist_ok=True)
    h, w = arr.shape
    if as_int:
        a = np.where(np.isfinite(arr), np.clip(np.rint(arr), -32000, 32000), -32768)
        with rasterio.open(path, "w", driver="GTiff", height=h, width=w, count=1,
                           dtype="int16", crs=crs, transform=transform,
                           nodata=-32768, compress="deflate", tiled=True) as dst:
            dst.write(a.astype("int16"), 1)
        print(f"  wrote {path.name}  {path.stat().st_size / 1e3:.0f} kB")
        return
    with rasterio.open(path, "w", driver="GTiff", height=h, width=w, count=1,
                       dtype="float32", crs=crs, transform=transform,
                       nodata=nodata, compress="deflate", tiled=True) as dst:
        dst.write(arr.astype("float32"), 1)
    print(f"  wrote {path.name}  {path.stat().st_size / 1e3:.0f} kB")


# ---------------------------------------------------------------------------
def mafic_fraction(transform, w, h, crs):
    """Rasterise GLiM basic-igneous polygons, then average to the analysis grid.

    GLiM ships in Eckert IV, so the polygons are reprojected before rasterising.
    Rasterising at 0.025 deg and averaging to 0.1 deg gives a genuine sub-cell
    FRACTION rather than a majority class, which matters because a cell that is
    20% basalt still has basalt in it.
    """
    import geopandas as gpd
    import pyogrio

    print(f"mafic outcrop from GLiM, classes {MAFIC_CLASSES}")
    where = " OR ".join(f"xx = '{c}'" for c in MAFIC_CLASSES)
    gdf = pyogrio.read_dataframe(GLIM, layer="GLiM_export", where=where,
                                 columns=["xx"])
    print(f"  {len(gdf):,} polygons read; reprojecting from Eckert IV")
    gdf = gdf.to_crs("EPSG:4326")

    fw = int(round(360.0 / FINE_DEG))
    north = transform.f
    fh = int(round((north - (transform.f + h * transform.e)) / FINE_DEG))
    ft = from_origin(-180.0, north, FINE_DEG, FINE_DEG)
    print(f"  rasterising at {FINE_DEG} deg -> {fh} x {fw}")
    fine = rasterize(((g, 1) for g in gdf.geometry if g is not None),
                     out_shape=(fh, fw), transform=ft, fill=0,
                     dtype="uint8", all_touched=False)

    frac = np.zeros((h, w), dtype="float32")
    reproject(source=fine.astype("float32"), destination=frac,
              src_transform=ft, src_crs="EPSG:4326",
              dst_transform=transform, dst_crs=crs,
              resampling=Resampling.average)
    frac = np.clip(frac, 0.0, 1.0)
    print(f"  cells with any mafic rock: {int((frac > 0).sum()):,}; "
          f"global mafic land fraction {float(frac.mean()):.3f}")
    return frac


def km_to_nearest(mask, transform, h, w):
    """Great-circle km to the nearest True cell.

    Uses a Euclidean distance transform in DEGREES and then converts, scaling
    longitude by cos(latitude). That is exact enough for a screening cost surface
    and vastly cheaper than a spherical all-pairs distance. It is NOT network
    routing -- see the module docstring.
    """
    if not mask.any():
        return np.full((h, w), np.nan, dtype="float32")
    # Distance transform with anisotropic sampling: dy in deg, dx in deg.
    dy = abs(transform.e)
    dx = abs(transform.a)
    dist_deg = ndimage.distance_transform_edt(~mask, sampling=(dy, dx))
    lat = transform.f + (np.arange(h) + 0.5) * transform.e
    # Degree -> km, with the longitude component shrinking as cos(lat). Using a
    # single factor would overstate east-west distance at high latitude.
    km_per_deg = 111.195
    scale = km_per_deg * np.sqrt(0.5 * (1.0 + np.cos(np.deg2rad(lat)) ** 2))
    return (dist_deg * scale[:, None]).astype("float32")


def load_stone_quarries():
    """MRDS records that are operating stone/aggregate producers.

    MRDS has no basalt or traprock commodity code, so 'mafic-hosted' has to come
    from a spatial join against the lithology, which is what the caller does.
    """
    src = RAW / "mrds/mrds.csv"
    if not src.exists():
        print("  SKIP quarries: data/raw/mrds/mrds.csv missing")
        return None
    keep = []
    with src.open(encoding="latin-1", errors="replace") as fh:
        for row in csv.DictReader(fh):
            if (row.get("dev_stat") or "") != "Producer":
                continue
            cs = " ".join((row.get(k) or "")
                          for k in ("commod1", "commod2", "commod3")).lower()
            if not any(t in cs for t in ("stone", "aggregate", "basalt",
                                         "trap rock", "olivine")):
                continue
            try:
                lat, lon = float(row["latitude"]), float(row["longitude"])
            except (TypeError, ValueError):
                continue
            if not (-90 < lat < 90 and -180 <= lon <= 180):
                continue
            keep.append((lon, lat))
    print(f"  {len(keep):,} operating stone/aggregate producers with coordinates")
    return np.array(keep)


def main() -> int:
    transform, w, h, crs = grid()

    frac = mafic_fraction(transform, w, h, crs)
    write_tif(INTERIM / "mafic_frac.tif", frac, transform, crs)

    print("distance to nearest mafic outcrop")
    mafic_km = km_to_nearest(frac > 0.02, transform, h, w)
    v = mafic_km[np.isfinite(mafic_km)]
    print(f"  km to mafic: p10 {np.percentile(v, 10):.0f}  "
          f"p50 {np.percentile(v, 50):.0f}  p90 {np.percentile(v, 90):.0f}")
    write_tif(INTERIM / "mafic_km.tif", mafic_km, transform, crs, as_int=True)

    print("mafic-hosted stone quarries from USGS MRDS")
    pts = load_stone_quarries()
    quarry_km = np.full((h, w), np.nan, dtype="float32")
    conf = np.zeros((h, w), dtype="float32")
    if pts is not None and len(pts):
        # Keep only quarries that sit on mafic rock: MRDS cannot tell us the rock
        # type, so the lithology has to.
        gx = ((pts[:, 0] - transform.c) / abs(transform.a)).astype(int)
        gy = ((transform.f - pts[:, 1]) / abs(transform.e)).astype(int)
        ok = (gx >= 0) & (gy >= 0) & (gx < w) & (gy < h)
        gx, gy, pts = gx[ok], gy[ok], pts[ok]
        on_mafic = frac[gy, gx] > 0.02
        print(f"  {int(on_mafic.sum()):,} of {len(pts):,} sit on mapped mafic rock "
              f"({float(on_mafic.mean()):.1%})")

        qmask = np.zeros((h, w), dtype=bool)
        qmask[gy[on_mafic], gx[on_mafic]] = True
        quarry_km = km_to_nearest(qmask, transform, h, w)

        # Confidence: MRDS is a US inventory frozen around 2011. Outside the
        # trusted box the quarry distance is not usable, and saying so is more
        # informative than blurring a bad number across the globe.
        lon = transform.c + (np.arange(w) + 0.5) * abs(transform.a)
        lat = transform.f + (np.arange(h) + 0.5) * transform.e
        W, S, E, N = MRDS_TRUSTED_BBOX
        inbox = ((lon >= W) & (lon <= E))[None, :] & ((lat >= S) & (lat <= N))[:, None]
        conf = np.where(inbox, 1.0, 0.0).astype("float32")

        # Measure how much outcrop proximity overstates quarry proximity, in the
        # one region where both are known. This is the honest uncertainty
        # elsewhere, quantified rather than asserted.
        both = inbox & np.isfinite(quarry_km) & np.isfinite(mafic_km) & (mafic_km > 0)
        if both.any():
            ratio = np.median(quarry_km[both] / np.maximum(mafic_km[both], 1e-6))
            print(f"  within the trusted inventory area, distance to a mafic "
                  f"QUARRY is {ratio:.1f}x the distance to mafic OUTCROP "
                  f"(median). Outside it, only the outcrop bound is available.")
    write_tif(INTERIM / "quarry_km.tif", quarry_km, transform, crs, as_int=True)
    write_tif(INTERIM / "feedstock_conf.tif", conf, transform, crs)

    # Indicative delivered cost. Deliberately simple and fully stated.
    print("indicative delivered cost")
    haul_km = np.where(np.isfinite(quarry_km) & (conf > 0.5), quarry_km,
                       mafic_km * C.OUTCROP_TO_QUARRY_FACTOR)
    road_km = C.ROAD_TORTUOSITY * haul_km
    truck = C.TRUCK_COST_USD_T_KM * road_km
    rail = C.RAIL_COST_USD_T_KM * road_km + C.RAIL_TRANSLOAD_USD_T
    cost = C.FEEDSTOCK_GATE_COST_USD_T + np.minimum(truck, rail)
    cross = C.RAIL_TRANSLOAD_USD_T / (C.TRUCK_COST_USD_T_KM - C.RAIL_COST_USD_T_KM)
    print(f"  truck below ~{cross:.0f} km road distance, rail above it")
    v = cost[np.isfinite(cost)]
    print(f"  $/t delivered: p10 {np.percentile(v, 10):.0f}  "
          f"p50 {np.percentile(v, 50):.0f}  p90 {np.percentile(v, 90):.0f}")
    write_tif(INTERIM / "feedstock_cost.tif", cost, transform, crs, as_int=True)

    if "--delete-raw" in sys.argv:
        import shutil
        for p in (RAW / "glim", RAW / "glim.gdb.zip", RAW / "mrds",
                  RAW / "mrds.zip"):
            if p.exists():
                mb = sum(f.stat().st_size for f in p.rglob("*")) / 1e6 \
                    if p.is_dir() else p.stat().st_size / 1e6
                shutil.rmtree(p) if p.is_dir() else p.unlink()
                print(f"  deleted data/raw/{p.name} ({mb:.0f} MB)")
    print()
    print("next: python3 scripts/build_v0.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
