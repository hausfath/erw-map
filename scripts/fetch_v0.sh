#!/usr/bin/env bash
# Fetch the v0 input layers: a real, global, end-to-end dataset at 0.1 degrees.
#
# The WorldClim layers fetched below are now only a FALLBACK. Both of v0's
# original substitutions have been replaced by the real thing, and the build
# reports which path it took:
#
#   AIR temperature (WorldClim BIO1) -> Lembrechts et al. 2022 monthly soil T,
#     5-15 cm, via fetch_monthly.py.
#   PRECIPITATION (WorldClim BIO12) as a wetness proxy -> TerraClimate monthly
#     extractable soil-water storage, converted to an absolute degree of
#     saturation against the SoilGrids retention layers fetched in stage 1b.
#     BIO12 is still used, but for the wet-but-undrained gate rather than as a
#     moisture term.
#
# Everything else is the real thing: SoilGrids pH, SOC and water retention via
# ISRIC's WCS (server-side resampled, so we never download the 250 m global
# archive) and GLAD global cropland.
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

echo "1/8 SoilGrids (pH, SOC, and the quantiles the eligibility work needs)"
sg phh2o phh2o_0-5cm_mean   ph_0_5.tif
sg phh2o phh2o_5-15cm_mean  ph_5_15.tif
sg soc   soc_0-5cm_mean     soc_0_5.tif
sg soc   soc_0-5cm_Q0.05    soc_q05.tif
sg soc   soc_0-5cm_Q0.95    soc_q95.tif
sg bdod  bdod_0-5cm_mean    bdod_0_5.tif

echo "1b/8 SoilGrids water retention over the root zone (0-100 cm)"
# The DENOMINATOR that turns TerraClimate's extractable storage in mm into an
# absolute degree of saturation. Three variables, five depth intervals each:
#   wv0033  volumetric water content at 33 kPa   -- field capacity
#   wv1500  volumetric water content at 1500 kPa -- wilting point
#   bdod    bulk density                         -- porosity via 1 - rho_b/2.65
# 15 requests, ~2 MB each, ~1 min total. prep_layers.py reduces them to a single
# 3-band interim product and --delete-raw removes these.
#
# Why all three rather than one: field capacity and wilting point BRACKET the
# range TerraClimate's extractable storage lives in, and porosity is the
# denominator that turns a water content into a saturation. Using any one of them
# alone is a units error dressed as a choice -- see the MOISTURE_TERM block in
# constants.py.
for D in 0-5 5-15 15-30 30-60 60-100; do
  sg wv0033 "wv0033_${D}cm_mean" "wv0033_${D}.tif"
  sg wv1500 "wv1500_${D}cm_mean" "wv1500_${D}.tif"
  sg bdod   "bdod_${D}cm_mean"   "bdod_${D}.tif"
done

echo "2/8 WorldClim 2.1 bioclim at 10 arc-min (BIO1 air temp, BIO12 precip)"
if [ ! -s data/raw/wc_bio.zip ]; then
  curl -sSfL --max-time 900 -o data/raw/wc_bio.zip \
    "https://geodata.ucdavis.edu/climate/worldclim/2_1/base/wc2.1_10m_bio.zip"
fi
unzip -o -q data/raw/wc_bio.zip -d data/raw/wc \
  'wc2.1_10m_bio_1.tif' 'wc2.1_10m_bio_12.tif'

echo "3/8 Potapov et al. 2022 percent-cropland, 3 km (7.4 MB)"
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
echo "4/8 WaterGAP2-2e water fluxes via ISIMIP3a (885 MB, reduced then deleted)"
# THREE fluxes, not one, because which of them is "the water that weathers the
# rock" is a real open question and we would rather measure the spread than pick:
#   qr    groundwater recharge -- water reaching the AQUIFER. Exactly zero in
#         river deltas, where the water table is at the surface and drainage
#         leaves laterally to canals. Was the sole input through 2026-08-03.
#   qtot  total runoff -- the catchment-scale quantity Maher & Chamberlain
#         actually fit D_w against, so it is the internally consistent choice.
#   qs    surface runoff, so prep_layers can derive qsb = qtot - qs.
# The histsoc scenario simulates irrigation return flow, which matters on
# irrigated cropland. Units are kg m-2 s-1 (= mm/s), calendar 365_day, so
# mm/yr = value * 31536000.
WATERGAP_BASE="https://files.isimip.org/ISIMIP3a/OutputData/water_global/WaterGAP2-2e/gswp3-w5e5/historical"
for wg_var in qr qtot qs; do
  case "$wg_var" in
    qr)   wg_out=data/interim/drainage_recharge_mmyr.tif ;;
    qtot) wg_out=data/interim/drainage_qtot_mmyr.tif ;;
    qs)   wg_out=data/interim/drainage_qs_mmyr.tif ;;
  esac
  if [ ! -s "data/raw/watergap_${wg_var}.nc" ] && [ ! -s "$wg_out" ]; then
    curl -sSfL --max-time 3600 -o "data/raw/watergap_${wg_var}.nc" \
      "${WATERGAP_BASE}/watergap2-2e_gswp3-w5e5_obsclim_histsoc_default_${wg_var}_global_monthly_1901_2019.nc"
  fi
done

echo "5/8 GRPI rice-paddy inundation, 0.1 deg monthly (4 MB)"
# Note: this record publishes only the CH4 emission field, not the paddy area
# map from the paper. We use its monthly PRESENCE pattern for months-flooded and
# take sub-cell area fraction from SPAM below.
if [ ! -s data/raw/grpi_paddy.nc ] && [ ! -s data/interim/paddy_months_flooded.tif ]; then
  curl -sSfL --max-time 600 -o data/raw/grpi_paddy.nc \
    "https://zenodo.org/records/15210212/files/grpi_hemco.nc?download=1"
fi

echo "6/8 SPAM2010 physical area, all 42 crops (143 MB archive)"
# THE ARCHIVE IS KEPT, not unpacked and discarded. Two layers come out of it:
# irrigated rice for the paddy pCO2 pathway, and the two largest crops per cell
# for the readout. prep_layers streams the 42 all-technology rasters out one at a
# time rather than unpacking 1.5 GB, so the zip is the cheaper thing to hold on
# to. `prep_layers.py --delete-raw` removes it once both layers are derived.
#
# SPAM2010 v2.0 is the latest GLOBAL release (verified 2026-08-06): the 2017 and
# MapSPAM2020 products on the same Dataverse are Sub-Saharan Africa only.
if [ ! -s data/raw/spam2010.zip ] \
   && { [ ! -s data/interim/paddy_area_frac.tif ] || [ ! -s data/interim/crop_mix.tif ]; }; then
  curl -sSfL --max-time 2400 -o data/raw/spam2010.zip \
    "https://dataverse.harvard.edu/api/access/datafile/3985010"
fi
if [ -s data/raw/spam2010.zip ] && [ ! -s data/raw/spam2010V2r0_global_A_RICE_I.tif ] \
   && [ ! -s data/interim/paddy_area_frac.tif ]; then
  unzip -o -q -j data/raw/spam2010.zip "*RICE_I.tif" -d data/raw/
fi

echo "7/8 SoilGrids SOC quantiles at 0.025 deg, for a VALID exceedance probability"
# Computed at ~2.8 km then averaged, because averaging quantiles first (as an
# earlier version did) is not valid uncertainty propagation and inflated the
# "marginal" eligibility class.
for Q in Q0.05 Q0.5 Q0.95; do
  K=$(echo "$Q" | tr -d '.' | sed 's/Q0/q/' | sed 's/q05$/q05/;s/q5$/q50/;s/q95$/q95/')
  [ -s "data/raw/soc_fine_${K}.tif" ] && continue
  [ -s data/interim/soc_p_exceed.tif ] && continue
  echo "  soc_0-5cm_${Q}"
  curl -sSf --max-time 900 -o "data/raw/soc_fine_${K}.tif" \
    "${WCS}?map=/map/soc.map&SERVICE=WCS&VERSION=2.0.1&REQUEST=GetCoverage\
&COVERAGEID=soc_0-5cm_${Q}&FORMAT=GEOTIFF_INT16\
&SUBSET=long(-180,180)&SUBSET=lat(${LAT0},${LAT1})\
&SUBSETTINGCRS=http://www.opengis.net/def/crs/EPSG/0/4326\
&OUTPUTCRS=http://www.opengis.net/def/crs/EPSG/0/4326\
&SCALESIZE=long(14400),lat(5600)"
done

echo
echo "Raw inputs:"
du -sh data/raw/* 2>/dev/null | sed 's/^/  /'
echo
echo "Next: python3 scripts/prep_layers.py   # reduce the big NetCDFs"
echo "Then: python3 scripts/build_v0.py"
