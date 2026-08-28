"""
Build a quarry inventory outside the United States.

  python3 scripts/fetch_quarries.py [--country BR,IN,...] [--skip-osm]

Writes data/interim/quarries.csv with lon, lat, source, country, substance.

WHY THIS EXISTS. USGS MRDS is a US inventory, so until now every non-US cell fell
back to a distance-to-mafic-OUTCROP upper bound, scaled by a factor measured only
inside the US. Brazil and India are where the largest ERW deployments actually
are, which made that the weakest link in the cost surface.

TWO SOURCES, with different strengths:

  ANM SIGMINE (Brazil) -- authoritative. The national mining agency's title
  register, queried live over its ArcGIS REST endpoint. Carries a SUBSTANCE field
  (so basalt/diabase/gabbro can be selected directly rather than inferred from
  lithology) and a PHASE field (so exploration applications can be excluded and
  only extraction-authorised titles kept). Note the published .zip download that
  ANM's own metadata advertises is dead (404/403); the REST endpoint is the
  working route.

  OpenStreetMap -- crowd-sourced, uneven, but the only global option and the only
  usable one for India, where GSI Bhukosh and the National Geoscience Data
  Repository were both unreachable and no state portal yielded coordinates.

  INEGI DENUE (Mexico, added 2026-08-27) -- authoritative business directory of
  the national statistics agency, geocoded, updated twice a year. Sector-21
  (mining) bulk CSV, no token needed. Stone SCIAN classes kept: 212319 (otras
  piedras dimensionadas), 212321 (arena y grava), 212322 (tezontle y tepetate
  -- volcanic scoria, definitionally mafic). Like OSM and MRDS, rows are
  cross-filtered against mapped mafic lithology downstream; an establishment
  is not necessarily an active pit, which overstates supply in the same
  direction as every other source here. Added because the inventory hole made
  Veracruz -- a delivery sitting on the Trans-Mexican Volcanic Belt -- price
  as a 636 km haul to a Guanajuato MRDS record.

A title is not a quarry and a quarry is not a producing quarry. ANM titles are
legal boundaries, and a granted concession need not be active. OSM `landuse=quarry`
polygons include disused pits unless tagged otherwise. Both therefore OVERSTATE
active supply, in the same direction as the outcrop bound they replace, just less
so. That is recorded in the confidence layer rather than glossed.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW, INTERIM = ROOT / "data/raw/quarries", ROOT / "data/interim"

ANM = ("https://geo.anm.gov.br/arcgis/rest/services/SIGMINE/dados_anm/"
       "MapServer/0/query")
# Extraction-authorised phases only. AUTORIZACAO DE PESQUISA is exploration and
# REQUERIMENTO DE LAVRA is an application, so both are excluded.
ANM_PHASES = ("CONCESSÃO DE LAVRA", "LICENCIAMENTO", "REGISTRO DE EXTRAÇÃO")

# Overridable because the public instance throttles hard after sustained
# pulls -- kumi.systems runs a capable public mirror.
import os
OVERPASS = os.environ.get("OVERPASS_URL",
                          "https://overpass-api.de/api/interpreter")
# The public Overpass instance 504s on a whole-country quarry pull, so the query
# is tiled. Tiles are ~5 degrees, which came back reliably in testing.
COUNTRY_BBOX = {
    "IN": (68.0, 6.0, 98.0, 37.0),
    "BR": (-74.0, -34.0, -34.0, 6.0),
    "ID": (95.0, -11.0, 141.0, 6.0),
    "CN": (73.0, 18.0, 135.0, 54.0),
    "MX": (-118.0, 14.0, -86.0, 33.0),
    # Region pulls (2026-08-27): Europe and Asia were inventory holes -- zero
    # register points -- leaving their delivered costs entirely on the outcrop
    # bound. OSM tagging in Europe is the densest anywhere (a single 1-degree
    # German tile returns ~200 quarry features), so a region pull is the
    # highest-yield source available without national-register ingestion.
    "EU": (-11.0, 35.0, 45.0, 71.0),      # Europe incl. UK, Nordics, Balkans
    "SEA": (92.0, -11.0, 142.0, 28.0),    # Myanmar-Indonesia-Philippines
    "JP": (124.0, 30.0, 146.0, 46.0),     # Japan + Korea
    "CNE": (100.0, 20.0, 125.0, 42.0),    # east-China agricultural belt
    "TRME": (26.0, 30.0, 60.0, 42.0),     # Turkey, Caucasus, N Middle East
}

DENUE_URL = ("https://www.inegi.org.mx/contenidos/masiva/denue/"
             "denue_00_21_csv.zip")

# France: BRGM Observatoire des Materiaux WFS -- active extraction points,
# national coverage (verified 2026-08-27: ~4,735 points, lat 41.6-50.8, lon
# -4.6-9.5, WFS 2.0 paging; the service TITLE says "granulats marins" but the
# layer is metropolitan-wide). The `produit` field is a coded nomenclature we
# do not decode: like MRDS and OSM, rock type comes from the GLiM mafic
# cross-filter downstream.
BRGM_WFS = ("http://geoservices.brgm.fr/odmgm?service=WFS&version=2.0.0"
            "&request=GetFeature&typeName=ms:EXPLOIT_ACTIVE_P"
            "&count=1000&startIndex={i}")
# SCIAN 2023 stone classes plausibly hosting basalt/aggregate; caliza, marmol,
# yeso etc. are excluded as definitionally non-mafic.
DENUE_SCIAN = {"212319", "212321", "212322"}
TILE_DEG = 5.0


def curl(url: str, data: str | None = None, timeout: int = 240):
    cmd = ["curl", "-sS", "--max-time", str(timeout)]
    if data:
        cmd += ["--data-urlencode", f"data={data}"]
    cmd.append(url)
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def fetch_anm() -> list[dict]:
    """Brazil, authoritative, with substance and phase attributes."""
    print("Brazil: ANM SIGMINE mining-title register")
    subs = ("(UPPER(SUBS) LIKE '%BASALTO%' OR UPPER(SUBS) LIKE '%DIAB%' "
            "OR UPPER(SUBS) LIKE '%GABRO%')")
    ph = " OR ".join(f"FASE = '{p}'" for p in ANM_PHASES)
    where = f"{subs} AND ({ph})"
    out = RAW / "brazil_anm.geojson"
    if not out.exists():
        import urllib.parse as up
        q = up.urlencode({
            "where": where, "outFields": "PROCESSO,NOME,SUBS,FASE,UF,AREA_HA",
            "returnGeometry": "true", "f": "geojson"})
        txt = curl(f"{ANM}?{q}", timeout=400)
        if not txt:
            print("  FAILED")
            return []
        out.write_text(txt)
    feats = json.loads(out.read_text()).get("features", [])
    pts = []
    for f in feats:
        g = f.get("geometry") or {}
        c = centroid(g)
        if not c:
            continue
        p = f["properties"]
        pts.append({"lon": round(c[0], 4), "lat": round(c[1], 4),
                    "source": "ANM", "country": "BR",
                    "substance": (p.get("SUBS") or "").strip(),
                    "area_ha": p.get("AREA_HA") or ""})
    print(f"  {len(pts):,} extraction-authorised mafic titles")
    return pts


def centroid(geom) -> tuple[float, float] | None:
    """Area-free centroid of the first ring. Good enough: median title area is
    ~6 ha, far below the 0.1 degree analysis cell."""
    t = geom.get("type")
    rings = None
    if t == "Polygon":
        rings = geom.get("coordinates")
    elif t == "MultiPolygon" and geom.get("coordinates"):
        rings = geom["coordinates"][0]
    if not rings or not rings[0]:
        return None
    xs = [p[0] for p in rings[0]]
    ys = [p[1] for p in rings[0]]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def fetch_osm(iso: str) -> list[dict]:
    """OpenStreetMap landuse=quarry, tiled to avoid the public-instance timeout."""
    w, s, e, n = COUNTRY_BBOX[iso]
    print(f"{iso}: OpenStreetMap landuse=quarry, tiled at {TILE_DEG} deg")
    pts, tiles, fails = [], 0, 0
    y = s
    while y < n:
        x = w
        while x < e:
            bbox = f"{y},{x},{min(y + TILE_DEG, n)},{min(x + TILE_DEG, e)}"
            q = (f"[out:json][timeout:120];("
                 f"node[landuse=quarry]({bbox});"
                 f"way[landuse=quarry]({bbox});"
                 f");out tags center;")
            # RETRY WITH BACKOFF. The public Overpass instance throttles: a first
            # pass without retries lost 51 of 106 tiles (~48%), which silently
            # halved the inventory. Retrying recovers most of them.
            txt, attempt = None, 0
            while attempt < 4 and not txt:
                if attempt:
                    time.sleep(6 * attempt)
                txt = curl(OVERPASS, data=q, timeout=240)
                attempt += 1
            tiles += 1
            ok = False
            if txt:
                try:
                    for el in json.loads(txt).get("elements", []):
                        c = el.get("center") or ({"lat": el.get("lat"),
                                                  "lon": el.get("lon")}
                                                 if el.get("lat") else None)
                        if not c or c.get("lat") is None:
                            continue
                        tg = el.get("tags", {})
                        pts.append({
                            "lon": round(c["lon"], 4), "lat": round(c["lat"], 4),
                            "source": "OSM", "country": iso,
                            # `resource` carries rock type when present, which is
                            # a minority of features. Empty is normal, not an error.
                            "substance": (tg.get("resource") or "").strip(),
                            "area_ha": ""})
                    ok = True
                except json.JSONDecodeError:
                    pass
            if not ok:
                fails += 1
            time.sleep(2.0)          # be a good citizen on a shared endpoint
            x += TILE_DEG
        y += TILE_DEG
    print(f"  {len(pts):,} quarry features from {tiles} tiles ({fails} failed)")
    if fails:
        print(f"  WARNING: {fails}/{tiles} tiles failed even after retries, so "
              f"this is an UNDERCOUNT")
    # Ways crossing a tile boundary are returned by both tiles, so the raw count
    # exceeds the true feature count. De-duplication happens downstream.
    return pts


def fetch_denue() -> list[dict]:
    """Mexico: INEGI DENUE sector-21 bulk CSV (national, geocoded)."""
    import io as _io
    import zipfile

    print("Mexico: INEGI DENUE business directory, sector 21")
    dst = RAW / "denue_mx_21.zip"
    if not dst.exists():
        r = subprocess.run(["curl", "-sSL", "--max-time", "300",
                            "-A", "Mozilla/5.0", "-o", str(dst), DENUE_URL])
        if r.returncode != 0 or not dst.exists():
            print("  DENUE download failed; skipping")
            return []
    z = zipfile.ZipFile(dst)
    name = [n for n in z.namelist()
            if "conjunto_de_datos" in n and n.endswith(".csv")][0]
    txt = z.read(name).decode("utf-8-sig", errors="replace")
    rows = []
    for r in csv.DictReader(_io.StringIO(txt)):
        if (r.get("codigo_act") or "") not in DENUE_SCIAN:
            continue
        try:
            lat, lon = float(r["latitud"]), float(r["longitud"])
        except (TypeError, ValueError, KeyError):
            continue
        if not (14.0 < lat < 33.0 and -118.0 < lon < -86.0):
            continue
        rows.append({"lon": lon, "lat": lat, "source": "DENUE",
                     "country": "MX",
                     "substance": (r.get("nombre_act") or "")[:60],
                     "area_ha": ""})
    print(f"  {len(rows):,} stone/aggregate establishments "
          f"(SCIAN {sorted(DENUE_SCIAN)})")
    return rows


def fetch_brgm() -> list[dict]:
    """France: BRGM active extraction points over paged WFS 2.0."""
    import re

    print("France: BRGM Observatoire des Materiaux, EXPLOIT_ACTIVE_P")
    rows, i = [], 0
    while True:
        txt = curl(BRGM_WFS.format(i=i), timeout=180)
        if not txt:
            print(f"  WARNING: page at startIndex={i} failed; partial pull")
            break
        feats = re.findall(
            r"<gml:pos>([-\d.]+) ([-\d.]+)</gml:pos>(.*?)</ms:EXPLOIT_ACTIVE_P>",
            txt, re.S)
        if not feats:
            break
        for la, lo, body in feats:
            m = re.search(r"<ms:produit>([^<]*)</ms:produit>", body)
            rows.append({"lon": round(float(lo), 4),
                         "lat": round(float(la), 4),
                         "source": "BRGM", "country": "FR",
                         "substance": (m.group(1) if m else "")[:40],
                         "area_ha": ""})
        if len(feats) < 1000:
            break
        i += 1000
        time.sleep(1.0)
    print(f"  {len(rows):,} active extraction points")
    return rows


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    countries = ["BR", "IN"]
    for a in sys.argv[1:]:
        if a.startswith("--country"):
            countries = a.split("=", 1)[1].split(",")

    out = INTERIM / "quarries.csv"
    osm_add = next((a.split("=", 1)[1].split(",") for a in sys.argv[1:]
                    if a.startswith("--osm-add")), None)
    if osm_add:
        # Incremental: keep everything, append new OSM region pulls. Rows
        # duplicated across overlapping boxes collapse to unique cells in
        # prep_feedstock, so duplication is waste, not error.
        rows = []
        if out.exists():
            with out.open() as fh:
                rows = list(csv.DictReader(fh))
        for key in osm_add:
            rows += fetch_osm(key.strip())
    elif "--brgm-only" in sys.argv:
        rows = []
        if out.exists():
            with out.open() as fh:
                rows = [r for r in csv.DictReader(fh)
                        if r.get("source") != "BRGM"]
        rows += fetch_brgm()
    elif "--denue-only" in sys.argv:
        # Incremental: keep the existing ANM/OSM rows (network-expensive to
        # refetch), replace any prior DENUE rows.
        rows = []
        if out.exists():
            with out.open() as fh:
                rows = [r for r in csv.DictReader(fh)
                        if r.get("source") != "DENUE"]
        rows += fetch_denue()
    else:
        rows = []
        if "BR" in countries:
            rows += fetch_anm()
        rows += fetch_denue()
        rows += fetch_brgm()
        if "--skip-osm" not in sys.argv:
            for iso in countries:
                rows += fetch_osm(iso)

    INTERIM.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as fh:
        wr = csv.DictWriter(fh, ["lon", "lat", "source", "country",
                                 "substance", "area_ha"])
        wr.writeheader()
        wr.writerows(rows)
    print()
    print(f"wrote {out} ({len(rows):,} points, "
          f"{out.stat().st_size / 1e3:.0f} kB)")
    import collections
    print("  by source/country:",
          dict(collections.Counter(f"{r['source']}/{r['country']}" for r in rows)))
    print()
    print("next: python3 scripts/prep_feedstock.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
