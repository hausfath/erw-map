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

OVERPASS = "https://overpass-api.de/api/interpreter"
# The public Overpass instance 504s on a whole-country quarry pull, so the query
# is tiled. Tiles are ~5 degrees, which came back reliably in testing.
COUNTRY_BBOX = {
    "IN": (68.0, 6.0, 98.0, 37.0),
    "BR": (-74.0, -34.0, -34.0, 6.0),
    "ID": (95.0, -11.0, 141.0, 6.0),
    "CN": (73.0, 18.0, 135.0, 54.0),
}
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


def main() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    countries = ["BR", "IN"]
    for a in sys.argv[1:]:
        if a.startswith("--country"):
            countries = a.split("=", 1)[1].split(",")

    rows = []
    if "BR" in countries:
        rows += fetch_anm()
    if "--skip-osm" not in sys.argv:
        for iso in countries:
            rows += fetch_osm(iso)

    INTERIM.mkdir(parents=True, exist_ok=True)
    out = INTERIM / "quarries.csv"
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
