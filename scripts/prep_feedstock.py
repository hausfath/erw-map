"""
Build the feedstock-access layer: where mafic rock is, where it is actually
quarried, and roughly what it costs to get it to a field.

  python3 scripts/prep_feedstock.py [--delete-raw] [--cost-only]

--cost-only rebuilds ONLY feedstock_cost.tif and truck_rate.tif from the
interim distance/confidence products already on disk, so a change to the cost
MODEL (rates, fixed component) never forces a re-download of the raw lithology
archives that the disk policy deletes.

Writes to data/interim/:
  mafic_frac.tif            fraction of cell underlain by basic igneous rock
  mafic_km.tif              great-circle km to the nearest mafic outcrop
  quarry_km.tif             km to the nearest mafic-hosted stone quarry
  feedstock_cost.tif        indicative delivered $/t: gate + r(region)*(d+50km)
  truck_rate.tif            the regional $/t-km surface used in that cost
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

Haul is TRUCK ONLY, at great-circle distance x a tortuosity factor, NOT network
routing. Truck-only because basalt is rarely railed for ERW today and rail still
requires first- and last-mile trucking. Real routing needs a friction surface or a
road graph; see to_do.md.
"""

from __future__ import annotations

import csv
import json
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

# Confidence assigned to each inventory source, used to decide whether the quarry
# distance is trustworthy enough to replace the outcrop bound. Graded rather than
# binary, because an authoritative national register and a crowd-sourced layer are
# not the same evidence.
SOURCE_CONFIDENCE = {
    "MRDS": 1.0,   # US national register; stale since ~2011 but authoritative
    "ANM": 1.0,    # Brazilian national mining-title register, daily updated
    "OSM": 0.6,    # crowd-sourced, uneven coverage, but the only global option
}
CONF_USABLE = 0.5      # above this, prefer quarry distance over the outcrop bound


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


def load_external_quarries():
    """Non-US inventory built by fetch_quarries.py.

    ANM rows carry a substance field so basalt/diabase/gabbro is selected
    directly. OSM rows mostly do not, so they are cross-filtered against the
    lithology by the caller, the same way MRDS is.
    """
    src = INTERIM / "quarries.csv"
    if not src.exists():
        print("  no external inventory (run scripts/fetch_quarries.py)")
        return []
    rows = []
    with src.open() as fh:
        for r in csv.DictReader(fh):
            try:
                rows.append((float(r["lon"]), float(r["lat"]), r["source"],
                             r["country"], r.get("substance", "")))
            except (TypeError, ValueError):
                continue
    import collections
    print("  external inventory: "
          + ", ".join(f"{k} {v:,}" for k, v in
                      collections.Counter(f"{r[2]}/{r[3]}" for r in rows).items()))
    return rows


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


NE_ADMIN0_URL = ("https://naciscdn.org/naturalearth/50m/cultural/"
                 "ne_50m_admin_0_countries.zip")


def truck_rate_raster(transform, w, h, crs) -> np.ndarray:
    """Regional truck rate, $/t-km per cell, from Natural Earth admin-0.

    Rates and their sources live in constants.TRUCK_RATE_GROUPS; this function
    only paints them onto the grid. Coastal cells whose centre misses every
    polygon inherit the nearest country's rate (same trick as the admin-name
    lookup); remaining unlabelled land gets TRUCK_RATE_DEFAULT.

    FALLBACK: if geopandas or the download is unavailable, returns a uniform
    surface at the old global TRUCK_COST_USD_T_KM, loudly -- a build should
    degrade to the pre-regional behaviour, never silently to a wrong mix.
    """
    print("regional truck rates from Natural Earth admin-0")
    try:
        import geopandas as gpd
    except ImportError:
        print(f"    WARNING: geopandas unavailable; UNIFORM fallback at "
              f"${C.TRUCK_COST_USD_T_KM}/t-km")
        return np.full((h, w), C.TRUCK_COST_USD_T_KM, dtype="float32")

    zp = RAW / "ne_50m_admin_0_countries.zip"
    if not zp.exists():
        import urllib.request
        try:
            urllib.request.urlretrieve(NE_ADMIN0_URL, zp)
        except Exception as e:  # noqa: BLE001 -- degrade, never die, on network
            print(f"    WARNING: Natural Earth download failed ({e}); UNIFORM "
                  f"fallback at ${C.TRUCK_COST_USD_T_KM}/t-km")
            return np.full((h, w), C.TRUCK_COST_USD_T_KM, dtype="float32")

    ctry = gpd.read_file(f"zip://{zp}")
    # Natural Earth quirk: ISO_A2 is "-99" for France, Norway and a few others;
    # ISO_A2_EH ("everything held equal") carries the real code there.
    iso_col = "ISO_A2_EH" if "ISO_A2_EH" in ctry.columns else "ISO_A2"
    shapes = []
    for _, row in ctry.iterrows():
        iso = str(row.get(iso_col) or "")
        if iso in ("-99", "nan"):
            iso = ""
        rate = C.truck_rate_for(iso, str(row.get("CONTINENT") or ""))
        shapes.append((row.geometry, rate))

    rate = rasterize(shapes, out_shape=(h, w), transform=transform,
                     fill=np.nan, dtype="float32", all_touched=False)

    # Nearest-country fill for coastal cells, bounded so open ocean stays NaN.
    labelled = np.isfinite(rate)
    dist, (iy, ix) = ndimage.distance_transform_edt(
        ~labelled, return_indices=True)
    near = (dist > 0) & (dist <= 3)
    rate[near] = rate[iy[near], ix[near]]

    # Report the areal mix OVER LABELLED LAND, so a bad join is visible in the
    # build log. Reporting over the whole grid buried the signal under ocean
    # cells, which are about to get the default painted on them harmlessly.
    lab = np.isfinite(rate)
    vals, counts = np.unique(np.round(rate[lab], 4), return_counts=True)
    label_of = {round(g["rate"], 4): name
                for name, g in C.TRUCK_RATE_GROUPS.items()}
    label_of[round(C.TRUCK_RATE_DEFAULT, 4)] = "default/elsewhere"
    label_of[round(C.TRUCK_COST_USD_T_KM, 4)] = "UNIFORM FALLBACK"
    for v, n in sorted(zip(vals, counts), key=lambda t: -t[1]):
        print(f"    ${v:.3f}/t-km  {100 * n / lab.sum():5.1f}% of labelled land  "
              f"({label_of.get(round(float(v), 4), '??')})")

    # Whatever remains unlabelled (open ocean, tiny islands beyond the fill
    # radius) gets the default rather than NaN, so cost stays defined wherever
    # haul is.
    rate = np.where(lab, rate, C.TRUCK_RATE_DEFAULT)
    return rate.astype("float32")


def build_cost(transform, w, h, crs, mafic_km, quarry_km, conf) -> None:
    """Delivered cost, deliberately simple and fully stated:

        cost = gate + F + r(region) * road_km

    F is the fixed per-trip charge (loading/unloading, USDA GTOR curve) and
    r(region) the regional truck rate -- both new in Aug 2026, see
    docs/TRUCK_RATE_SOURCES.md and constants.TRUCK_RATE_GROUPS. Before that the
    model was a single global $0.12/t-km with no fixed component, which was
    right for the US and ~2-2.5x high for Brazil and India.
    """
    print("indicative delivered cost")
    haul_km = np.where(np.isfinite(quarry_km) & (conf > CONF_USABLE), quarry_km,
                       mafic_km * C.OUTCROP_TO_QUARRY_FACTOR)
    # Truck for the whole haul. Basalt is rarely railed for ERW today, and rail
    # still needs a first- and last-mile truck leg, so a rail rate would flatter
    # current practice. See constants.TRUCK_COST_USD_T_KM for why an earlier
    # rail mode was removed.
    road_km = C.ROAD_TORTUOSITY * haul_km
    rate = truck_rate_raster(transform, w, h, crs)
    # The fixed per-trip charge is a km-equivalent priced at the regional rate:
    # ~45 min of loading/tipping/positioning = ~50 km of driving, so the whole
    # haul is one product. See constants.HAUL_FIXED_KM_EQUIV for the reversal
    # this replaces (a global $5/t that priced Indian trip time at US wages).
    cost = (C.FEEDSTOCK_GATE_COST_USD_T
            + rate * (road_km + C.HAUL_FIXED_KM_EQUIV))
    print(f"  truck only: regional rate on ({C.ROAD_TORTUOSITY}x great-circle "
          f"+ {C.HAUL_FIXED_KM_EQUIV:.0f} km fixed-trip equivalent)")

    # ROUND TRIP, fatal: the written surface must decompose back into exactly
    # gate + F + r*d. Catches a unit slip or a misaligned rate raster here,
    # where all three pieces are still in hand, rather than three artefacts
    # downstream in a browser readout.
    chk = np.isfinite(cost) & np.isfinite(road_km) & (road_km > 1.0)
    resid = np.abs(cost[chk] - C.FEEDSTOCK_GATE_COST_USD_T
                   - rate[chk] * (road_km[chk] + C.HAUL_FIXED_KM_EQUIV))
    if chk.any() and float(resid.max()) > 1e-3:
        raise SystemExit(f"cost round-trip failed: max residual "
                         f"${float(resid.max()):.4f}/t")
    print(f"  round trip gate+r*(d+50): max residual ${float(resid.max()):.1e}/t "
          f"over {int(chk.sum()):,} cells  [PASS]")

    v = cost[np.isfinite(cost)]
    print(f"  $/t delivered: p10 {np.percentile(v, 10):.0f}  "
          f"p50 {np.percentile(v, 50):.0f}  p90 {np.percentile(v, 90):.0f}")
    write_tif(INTERIM / "feedstock_cost.tif", cost, transform, crs, as_int=True)
    write_tif(INTERIM / "truck_rate.tif", rate, transform, crs)


def cost_only() -> int:
    """Rebuild the cost (and rate) tifs from interim products already on disk."""
    transform, w, h, crs = grid()

    def rd(name):
        with rasterio.open(INTERIM / name) as s:
            a = s.read(1).astype("float32")
            nod = s.nodatavals[0]
            if nod is not None and np.isfinite(nod):
                a[a == nod] = np.nan
            return a

    try:
        mafic_km, quarry_km, conf = (rd(n) for n in
                                     ("mafic_km.tif", "quarry_km.tif",
                                      "feedstock_conf.tif"))
    except rasterio.errors.RasterioIOError as e:
        print(f"--cost-only needs the interim distance products: {e}")
        return 1
    build_cost(transform, w, h, crs, mafic_km, quarry_km, conf)
    return 0


def main() -> int:
    if "--cost-only" in sys.argv:
        return cost_only()
    transform, w, h, crs = grid()

    frac = mafic_fraction(transform, w, h, crs)
    write_tif(INTERIM / "mafic_frac.tif", frac, transform, crs)

    print("distance to nearest mafic outcrop")
    mafic_km = km_to_nearest(frac > 0.02, transform, h, w)
    v = mafic_km[np.isfinite(mafic_km)]
    print(f"  km to mafic: p10 {np.percentile(v, 10):.0f}  "
          f"p50 {np.percentile(v, 50):.0f}  p90 {np.percentile(v, 90):.0f}")
    write_tif(INTERIM / "mafic_km.tif", mafic_km, transform, crs, as_int=True)

    print("mafic-hosted stone quarries")
    pts = load_stone_quarries()
    ext = load_external_quarries()
    quarry_km = np.full((h, w), np.nan, dtype="float32")
    conf = np.zeros((h, w), dtype="float32")
    kept_pts = []          # for the map overlay
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
        for i in np.where(on_mafic)[0]:
            kept_pts.append((pts[i, 0], pts[i, 1], "MRDS"))

        # Confidence starts as the MRDS box: a US inventory frozen around 2011.
        lon = transform.c + (np.arange(w) + 0.5) * abs(transform.a)
        lat = transform.f + (np.arange(h) + 0.5) * transform.e
        W, S, E, N = MRDS_TRUSTED_BBOX
        inbox = ((lon >= W) & (lon <= E))[None, :] & ((lat >= S) & (lat <= N))[:, None]
        conf = np.where(inbox, SOURCE_CONFIDENCE["MRDS"], 0.0).astype("float32")

        # Add the non-US inventory. ANM rows are selected on SUBSTANCE, so they
        # need no lithology cross-filter; OSM rows mostly lack a rock type and are
        # cross-filtered against the mafic map exactly as MRDS is.
        added = {"ANM": 0, "OSM": 0}
        for lo, la, source, country, subs in ext:
            ex = int((lo - transform.c) / abs(transform.a))
            ey = int((transform.f - la) / abs(transform.e))
            if not (0 <= ex < w and 0 <= ey < h):
                continue
            if source != "ANM" and frac[ey, ex] <= 0.02:
                continue                      # OSM: require mapped mafic rock
            qmask[ey, ex] = True
            kept_pts.append((lo, la, source))
            added[source] = added.get(source, 0) + 1
            # Raise confidence over the country this inventory covers. Done as a
            # generous radius around each point rather than a country polygon,
            # because a national register only tells you about the ground it
            # actually surveyed.
            c_new = SOURCE_CONFIDENCE.get(source, 0.5)
            r = 25                             # ~250 km at 0.1 deg
            y0, y1 = max(0, ey - r), min(h, ey + r + 1)
            x0, x1 = max(0, ex - r), min(w, ex + r + 1)
            np.maximum(conf[y0:y1, x0:x1], c_new, out=conf[y0:y1, x0:x1])
        print("  added to the mask: "
              + ", ".join(f"{k} {v:,}" for k, v in added.items() if v))

        quarry_km = km_to_nearest(qmask, transform, h, w)

        # Measure how much outcrop proximity overstates quarry proximity, wherever
        # an inventory exists. This is the honest uncertainty elsewhere,
        # quantified rather than asserted.
        both = (conf > CONF_USABLE) & np.isfinite(quarry_km) \
            & np.isfinite(mafic_km) & (mafic_km > 0)
        if both.any():
            ratio = np.median(quarry_km[both] / np.maximum(mafic_km[both], 1e-6))
            print(f"  within the trusted inventory area, distance to a mafic "
                  f"QUARRY is {ratio:.1f}x the distance to mafic OUTCROP "
                  f"(median). Outside it, only the outcrop bound is available.")
    write_tif(INTERIM / "quarry_km.tif", quarry_km, transform, crs, as_int=True)
    write_tif(INTERIM / "feedstock_conf.tif", conf, transform, crs)

    build_cost(transform, w, h, crs, mafic_km, quarry_km, conf)

    # Point list for the map overlay. Rounded to 2 dp (~1 km), which is finer than
    # the display grid, and de-duplicated per cell so dense clusters do not bloat
    # the payload.
    seen, pl = set(), []
    for lo, la, src in kept_pts:
        k = (round(lo, 2), round(la, 2), src)
        if k not in seen:
            seen.add(k)
            pl.append(k)
    pj = INTERIM / "quarry_points.json"
    pj.write_text(json.dumps({"points": [[a, b, c] for a, b, c in sorted(pl)]},
                             separators=(",", ":")))
    print(f"  wrote {pj.name}: {len(pl):,} unique points "
          f"({pj.stat().st_size / 1e3:.0f} kB) for the map overlay")

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
