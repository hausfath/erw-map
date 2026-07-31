#!/usr/bin/env bash
# Fetch the v0 input layers: a real, global, end-to-end dataset at 0.1 degrees.
#
# v0 is deliberately coarse and uses two documented substitutions so that the
# whole pipeline and the interactive map exist and can be inspected before the
# heavy ingest is built. Both substitutions are visible in the UI:
#
#   AIR temperature (WorldClim BIO1) instead of monthly SOIL temperature.
#     This is exactly Cascade's input, so v0 can ship a like-for-like baseline
#     comparison. Planned upgrade: Lembrechts et al. 2022 monthly soil T.
#   PRECIPITATION (WorldClim BIO12) as a wetness and drainage proxy instead of
#     a soil-moisture climatology. Planned upgrade: a GEE-reduced monthly
#     soil-moisture climatology.
#
# Everything else is the real thing: SoilGrids pH and SOC via ISRIC's WCS
# (server-side resampled, so we never download the 250 m global archive) and
# GLAD global cropland.
#
# Raw downloads land in data/raw/ and are deleted after deriving products.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data/raw data/processed

W=3600; H=1400; LAT0=-56; LAT1=84       # 0.1 deg, clipped to cropland latitudes
WCS="https://maps.isric.org/mapserv"

sg() {   # sg <coverage-map> <coverage-id> <out>
  local map="$1" cov="$2" out="$3"
  if [ -s "data/raw/$out" ]; then echo "  have $out"; return; fi
  echo "  SoilGrids WCS: $cov"
  curl -sSf --max-time 300 -o "data/raw/$out" \
    "${WCS}?map=/map/${map}.map&SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage\
&COVERAGEID=${cov}&FORMAT=GEOTIFF_INT16\
&SUBSET=long(-180,180)&SUBSET=lat(${LAT0},${LAT1})\
&SUBSETTINGCRS=http://www.opengis.net/def/crs/EPSG/0/4326\
&OUTPUTCRS=http://www.opengis.net/def/crs/EPSG/0/4326\
&SCALESIZE=long(${W}),lat(${H})"
}

echo "1/6 SoilGrids (pH, SOC, and the quantiles the eligibility work needs)"
sg phh2o phh2o_0-5cm_mean   ph_0_5.tif
sg phh2o phh2o_5-15cm_mean  ph_5_15.tif
sg soc   soc_0-5cm_mean     soc_0_5.tif
sg soc   soc_0-5cm_Q0.05    soc_q05.tif
sg soc   soc_0-5cm_Q0.95    soc_q95.tif
sg bdod  bdod_0-5cm_mean    bdod_0_5.tif

echo "2/6 WorldClim 2.1 bioclim at 10 arc-min (BIO1 air temp, BIO12 precip)"
if [ ! -s data/raw/wc_bio.zip ]; then
  curl -sSfL --max-time 900 -o data/raw/wc_bio.zip \
    "https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_bio.zip"
fi
unzip -o -q data/raw/wc_bio.zip -d data/raw/wc \
  'wc2.1_10m_bio_1.tif' 'wc2.1_10m_bio_12.tif'

echo "3/6 Potapov et al. 2022 percent-cropland, 3 km (7.4 MB)"
# 0-100 percent cropland per 0.025 deg cell, EPSG:4326.
#
# NOT glad.umd.edu/croplands/tiledata/global_crop_probability.tif.gz, which an
# earlier version of this script used. That file is Pittman et al. 2010, a MODIS
# classification PROBABILITY over 2000-2008; its own documentation says to
# threshold it against national statistics rather than integrate it, so summing
# probability x cell area was not a valid area estimate. The area-closure gate
# in build_v0.py caught it (1.31 Gha against a target it could not meet).
if [ ! -s data/raw/potapov_crop3km_2019.tif ]; then
  curl -sSfL --max-time 900 -o data/raw/potapov_crop3km_2019.tif \
    "https://glad.geog.umd.edu/Potapov/Global_Crop/Data/Global_cropland_3km_2019.tif"
fi

# Discard the superseded probability layer if a previous run left it behind.
rm -f data/raw/glad_crop_prob.tif data/raw/glad_crop_prob.tif.gz
echo "4/6 WaterGAP2-2e groundwater recharge via ISIMIP3a (263 MB)"
# Recharge, not total runoff: we want water percolating below the root zone
# carrying dissolved bicarbonate, not overland flow. The histsoc scenario
# simulates irrigation return flow, which matters on irrigated cropland.
# Units are kg m-2 s-1 (= mm/s), calendar 365_day, so mm/yr = value * 31536000.
if [ ! -s data/raw/watergap_qr.nc ] && [ ! -s data/interim/drainage_recharge_mmyr.tif ]; then
  curl -sSfL --max-time 2400 -o data/raw/watergap_qr.nc \
    "https://files.isimip.org/ISIMIP3a/OutputData/water_global/WaterGAP2-2e/gswp3-w5e5/historical/watergap2-2e_gswp3-w5e5_obsclim_histsoc_default_qr_global_monthly_1901_2019.nc"
fi

echo "5/6 GRPI rice-paddy inundation, 0.1 deg monthly (4 MB)"
# Note: this record publishes only the CH4 emission field, not the paddy area
# map from the paper. We use its monthly PRESENCE pattern for months-flooded and
# take sub-cell area fraction from SPAM below.
if [ ! -s data/raw/grpi_paddy.nc ] && [ ! -s data/interim/paddy_months_flooded.tif ]; then
  curl -sSfL --max-time 600 -o data/raw/grpi_paddy.nc \
    "https://zenodo.org/records/15210212/files/grpi_hemco.nc?download=1"
fi

echo "6/6 SPAM2010 irrigated-rice physical area (143 MB, keep one 37 MB layer)"
if [ ! -s data/raw/spam2010V2r0_global_A_RICE_I.tif ] && [ ! -s data/interim/paddy_area_frac.tif ]; then
  curl -sSfL --max-time 2400 -o data/raw/spam2010.zip \
    "https://dataverse.harvard.edu/api/access/datafile/3985010"
  unzip -o -q -j data/raw/spam2010.zip "*RICE_I.tif" -d data/raw/
  rm -f data/raw/spam2010.zip
fi

echo
echo "Raw inputs:"
du -sh data/raw/* 2>/dev/null | sed 's/^/  /'
echo
echo "Next: python3 scripts/prep_layers.py   # reduce the big NetCDFs"
echo "Then: python3 scripts/build_v0.py"
