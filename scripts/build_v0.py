"""
Build the v0 layers and the browser textures.

  python3 scripts/build_v0.py

Reads data/raw/ (see fetch_v0.sh), writes:
  data/processed/v0_layers.npz    float layers, for aggregates and hover readout
  src/textures/tex1.png           RGB = reactivity, eta_DIC, drainage value functions
  src/textures/tex2.png           RGB = cropland fraction, mask flags, indicative CDR
  src/engine_constants.js         generated; the browser's copy of constants.py
  src/colormap.js                 generated; legend stops AND the shader ramp

The area-closure gate runs here and is FATAL. It tests the latitude-weighting
independently of any ERW science: if global cropland does not reconcile with
FAOSTAT, nothing downstream can be trusted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject

sys.path.insert(0, str(Path(__file__).parent))
import constants as C  # noqa: E402
import kinetics as K  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW, PROC = ROOT / "data/raw", ROOT / "data/processed"
INTERIM = ROOT / "data/interim"
SRC = ROOT / "src"


# ---------------------------------------------------------------------------
def master_grid() -> tuple[rasterio.Affine, int, int, rasterio.crs.CRS]:
    """The pH raster defines the grid; everything else is resampled onto it."""
    with rasterio.open(RAW / "ph_0_5.tif") as s:
        return s.transform, s.width, s.height, s.crs


def onto_grid(path: Path, transform, w, h, crs, *, resampling=Resampling.average,
              band: int = 1) -> np.ndarray:
    """Reproject any source onto the master grid as float32 with NaN nodata."""
    dst = np.full((h, w), np.nan, dtype="float32")
    with rasterio.open(path) as s:
        src = s.read(band).astype("float32")
        nod = s.nodatavals[band - 1]
        if nod is not None:
            src[src == nod] = np.nan
        reproject(
            source=src, destination=dst,
            src_transform=s.transform, src_crs=s.crs,
            dst_transform=transform, dst_crs=crs,
            src_nodata=np.nan, dst_nodata=np.nan,
            resampling=resampling,
        )
    return dst


def cell_area_km2(transform, w, h) -> np.ndarray:
    """Exact spherical cell area per ROW, broadcast to the grid.

    A = R^2 * dlon * (sin(lat_top) - sin(lat_bot))

    This is the single most important line in the file. Using a constant
    (0.1 deg * 111.32 km)^2 instead overstates global cropland by ~24%, biased
    worst in exactly the high-latitude breadbaskets. Gate 1 below catches it.
    """
    R = C.EARTH_RADIUS_M / 1000.0
    dlon = np.deg2rad(abs(transform.a))
    lat_top = transform.f + np.arange(h) * transform.e
    lat_bot = lat_top + transform.e
    row = R * R * dlon * (np.sin(np.deg2rad(lat_top)) - np.sin(np.deg2rad(lat_bot)))
    return np.repeat(np.abs(row)[:, None], w, axis=1).astype("float32")


# ---------------------------------------------------------------------------
def piecewise(x, knots) -> np.ndarray:
    """Value function from ABSOLUTE breakpoints -- never min-max or percentile.

    knots is [(x0, v0), (x1, v1), ...] ascending in x. Outside the range the
    end values hold. Absolute breakpoints are what make the score domain-
    invariant and keep the colour scale stable while the user moves sliders.
    """
    xs = np.array([k[0] for k in knots], dtype="float64")
    vs = np.array([k[1] for k in knots], dtype="float64")
    out = np.interp(np.asarray(x, dtype="float64"), xs, vs)
    return np.where(np.isnan(x), np.nan, out).astype("float32")


def exceedance_lognormal(q05, q50, q95, threshold) -> np.ndarray:
    """P(X > threshold) from SoilGrids quantiles, lognormal matched in log space.

    Reconstructing a distribution from three quantiles needs an assumption;
    lognormal because SOC is positive and right-skewed. Near the threshold this
    choice is a first-order determinant of the answer, so it is documented and
    versioned rather than buried.

    IMPORTANT: these are predictive quantiles for a ~250 m BLOCK AVERAGE, not
    for a sampled field. Block averaging reduces variance, so this understates
    how often an individual field crosses the threshold. It is a screening
    likelihood, not a calibrated eligibility probability.
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        mu = np.log(np.maximum(q50, 1e-6))
        sigma = (np.log(np.maximum(q95, 1e-6)) - np.log(np.maximum(q05, 1e-6))) / C.Z_90_TWO_SIDED
        sigma = np.maximum(sigma, 1e-3)
        z = (np.log(threshold) - mu) / sigma
    # P(X > t) = 1 - Phi(z);  Phi via erf
    from scipy.special import erf
    return (0.5 * (1.0 - erf(z / np.sqrt(2.0)))).astype("float32")


# ---------------------------------------------------------------------------
def main() -> int:
    transform, w, h, crs = master_grid()
    print(f"grid {w} x {h}, {abs(transform.a):.3f} deg, "
          f"lat {transform.f:.1f} to {transform.f + h * transform.e:.1f}")

    print("resampling inputs onto the grid")
    ph05 = onto_grid(RAW / "ph_0_5.tif", transform, w, h, crs) / C.SOILGRIDS_PH_SCALE
    ph515 = onto_grid(RAW / "ph_5_15.tif", transform, w, h, crs) / C.SOILGRIDS_PH_SCALE
    # Depth-weighted over 0-15 cm, nearer the 20 cm near-field zone than
    # Cascade's whole-profile 0-200 cm average.
    ph = np.where(np.isnan(ph515), ph05, (ph05 * 5.0 + ph515 * 10.0) / 15.0)
    ph[(ph < 2.5) | (ph > 11.0)] = np.nan

    soc = onto_grid(RAW / "soc_0_5.tif", transform, w, h, crs) / 10.0   # dg/kg -> g/kg
    soc_q05 = onto_grid(RAW / "soc_q05.tif", transform, w, h, crs) / 10.0
    soc_q95 = onto_grid(RAW / "soc_q95.tif", transform, w, h, crs) / 10.0

    tair = onto_grid(RAW / "wc/wc2.1_10m_bio_1.tif", transform, w, h, crs)     # deg C
    precip = onto_grid(RAW / "wc/wc2.1_10m_bio_12.tif", transform, w, h, crs)  # mm/yr

    # Potapov et al. 2022 percent-cropland, 0-100 per 0.025 deg cell.
    #
    # NOT the GLAD "cropland probability" layer that an earlier version of this
    # script used. That one is Pittman et al. 2010, a MODIS classification
    # PROBABILITY over 2000-2008, and its own documentation says to threshold it
    # against national statistics rather than integrate it -- so summing
    # probability x area was not a valid area estimate. Gate 1 caught it.
    print("reprojecting Potapov percent-cropland onto the grid (area-weighted)")
    crop = onto_grid(RAW / "potapov_crop3km_2019.tif", transform, w, h, crs) / 100.0
    crop = np.clip(np.nan_to_num(crop, nan=0.0), 0.0, 1.0)

    area = cell_area_km2(transform, w, h)

    # ---- GATE 1: area closure. FATAL. Tests the latitude weighting with no ERW
    # science involved, against the cropland product's OWN published total.
    gha = float(np.nansum(crop * area)) * 100.0 / 1e9          # km2 -> ha -> Gha
    naive_km2 = (abs(transform.a) * 111.32) ** 2
    gha_naive = float(np.nansum(crop) * naive_km2) * 100.0 / 1e9
    inflation = gha_naive / gha - 1.0
    lo, hi, _ = C.GATES["cropland_area_gha"]
    ilo, ihi = C.GATES["naive_area_inflation"]

    ok_total = lo <= gha <= hi
    ok_infl = ilo <= inflation <= ihi
    print()
    print(f"  GATE 1a total: {gha:.3f} Gha vs Potapov 2019 map-based "
          f"{C.CROPLAND_POTAPOV_2019_MAP_MHA / 1000:.3f} Gha "
          f"({gha / (C.CROPLAND_POTAPOV_2019_MAP_MHA / 1000) - 1:+.1%})  "
          f"[{'PASS' if ok_total else 'FAIL'}]")
    print(f"  GATE 1b latitude weighting: dropping cos(lat) inflates by "
          f"{inflation:+.1%}, expected {ilo:.0%}-{ihi:.0%}  "
          f"[{'PASS' if ok_infl else 'FAIL'}]")
    print(f"    Reconciliation, reported not reconciled: FAOSTAT cropland is "
          f"{C.CROPLAND_FAOSTAT_2022_MHA / 1000:.3f} Gha. The "
          f"{(C.CROPLAND_FAOSTAT_2022_MHA - C.CROPLAND_POTAPOV_2019_MAP_MHA) / 1000:.3f} "
          f"Gha gap is structural:")
    for k, v in C.CROPLAND_GAP_COMPONENTS_MHA.items():
        print(f"      {v:6.0f} Mha  {k}")
    print("    For ERW this matters: permanent woody crops ARE protocol-eligible")
    print("    (Brazilian citrus is a live deployment setting), so a herbaceous-only")
    print("    mask understates addressable area, concentrated in the tropics.")
    if not (ok_total and ok_infl):
        print("  FATAL: aborting. Nothing downstream is trustworthy.")
        return 1

    # ---- Physics
    print()
    print("computing layers")
    T_K = tair + 273.15
    # Wetness proxy: still a v0 substitute for a soil-moisture climatology.
    wet = np.clip(precip / 1200.0, 0.0, 1.0)

    # ---- Drainage: real groundwater recharge, replacing the 0.35 x precip
    # placeholder. Nearest-neighbour from 0.5 deg so the coarseness stays
    # VISIBLE rather than being interpolated into a smooth field that does not
    # exist -- the effective-resolution policy in docs/METHODOLOGY.md.
    rech = INTERIM / "drainage_recharge_mmyr.tif"
    if rech.exists():
        q = onto_grid(rech, transform, w, h, crs,
                      resampling=Resampling.nearest) / 1000.0     # mm/yr -> m/yr
        q = np.clip(np.nan_to_num(q, nan=0.0), 0.0, None)
        q_source = "WaterGAP2-2e recharge"
    else:
        q = np.clip(precip / 1000.0 * 0.35, 0.0, None)
        q_source = "PLACEHOLDER 0.35 x precip -- run prep_layers.py"

    # ---- Paddy: flooded fraction of cell-time, from two independent halves.
    # months/12 comes from GRPI inundation presence (robust to CH4 emission
    # factor); the sub-cell area fraction comes from SPAM irrigated rice.
    # Multiplying them is deliberately conservative: it refuses to treat a cell
    # that is 5% paddy as fully flooded, which would inflate the very paddy
    # prediction this project needs to test rather than assume.
    pm, pa = INTERIM / "paddy_months_flooded.tif", INTERIM / "paddy_area_frac.tif"
    if pm.exists() and pa.exists():
        months = np.nan_to_num(onto_grid(pm, transform, w, h, crs,
                                         resampling=Resampling.nearest), nan=0.0)
        parea = np.nan_to_num(onto_grid(pa, transform, w, h, crs,
                                        resampling=Resampling.average), nan=0.0)
        f_flood = np.clip(parea, 0, 1) * np.clip(months / 12.0, 0, 1)
        paddy_source = "GRPI months x SPAM irrigated-rice fraction"
    else:
        f_flood = np.zeros_like(ph)
        paddy_source = "NONE -- run prep_layers.py"

    # Continuous interpolation, not a binary switch: a cell flooded three months
    # a year does not behave like one flooded year-round.
    pco2 = (C.PCO2_UNSATURATED_UATM
            + f_flood * (C.PCO2_SATURATED_UATM - C.PCO2_UNSATURATED_UATM))

    reactivity = K.rate_ca_mg_release(C.FEEDSTOCK_DEFAULT, ph, T_K) * wet
    eta = K.eta_dic(ph, pco2, T_K)
    eta_tr = K.eta_transport(q)

    ref = K.rate_ca_mg_release(
        C.FEEDSTOCK_DEFAULT, C.L1_REF["pH"], C.L1_REF["T_soil_C"] + 273.15
    ) * C.L1_REF["saturation"]
    with np.errstate(divide="ignore", invalid="ignore"):
        L1 = np.log10(reactivity / float(ref))

    cascade = K.cascade_baseline_index(ph, T_K, wet)

    # ---- Eligibility, three-state from exceedance probability
    p_soc = exceedance_lognormal(soc_q05, soc, soc_q95, C.SOC_EXCLUSION_WT_PCT * 10.0)
    ph_warn = (ph < C.PH_WARNING_THRESHOLD)      # annotation only, zero score effect

    # ---- Value functions, absolute breakpoints.
    # NOTE reactivity is NOT baked into a texture any more. Because a change of
    # grind is a uniform additive shift on L1, shipping L1 itself and applying
    # the value function in the shader is what makes the particle-size slider
    # possible. See REACT_KNOTS.
    v_react = piecewise(L1, REACT_KNOTS)
    v_eta = piecewise(eta, [(0.0, 0.0), (0.3, 0.25), (0.6, 0.6),
                            (0.9, 0.95), (1.0, 1.0)])
    v_drain = piecewise(eta_tr, [(0.0, 0.05), (0.3, 0.35), (0.6, 0.7), (0.9, 1.0)])

    # ---- Indicative gross CO2, tCO2 gross/ha/yr. LOW CONFIDENCE.
    # One global effective-surface-area multiplier, NOT yet calibrated against
    # the verified deliveries -- that requires per-deployment particle-size
    # distributions we do not have. Scaled here only so the layer sits inside
    # the observed 0.3-10 envelope; treat as illustrative, not predictive.
    ceil_t = ((C.FEEDSTOCK_ARCHETYPES[C.FEEDSTOCK_DEFAULT]["CaO_wt"] / C.M_CAO
               + C.FEEDSTOCK_ARCHETYPES[C.FEEDSTOCK_DEFAULT]["MgO_wt"] / C.M_MGO)
              * 1000.0 * 2.0 * C.MOL_CO2_PER_KMOL_CHARGE_T)
    frac = np.clip(0.22 * (reactivity / float(ref)) * eta * eta_tr, 0.0, 0.6)
    cdr = frac * C.APPLICATION_RATE_T_HA_YR * ceil_t

    # ---- Report
    m = (crop >= C.CROPLAND_MIN_FRACTION) & np.isfinite(ph)
    aw = (crop * area)[m]

    def wq(x, qs):
        v = x[m]
        g = np.isfinite(v)
        o = np.argsort(v[g])
        cw = np.cumsum(aw[g][o]) / aw[g].sum()
        return [float(v[g][o][np.searchsorted(cw, t)]) for t in qs]

    print(f"  cropland cells (>={C.CROPLAND_MIN_FRACTION:.0%}): {int(m.sum()):,}")
    print(f"  drainage source: {q_source}")
    print(f"  paddy source:    {paddy_source}   D_w = {C.DAMKOHLER_DW_M_YR} m/yr "
          f"(published range {C.DAMKOHLER_DW_RANGE[0]}-{C.DAMKOHLER_DW_RANGE[1]})")
    for name, arr, fmt in (("soil pH (0-15 cm)", ph, "{:.2f}"),
                           ("air temp, deg C", tair, "{:.1f}"),
                           ("L1 log10(R/Rref)", L1, "{:+.2f}"),
                           ("eta_DIC", eta, "{:.3f}"),
                           ("eta_transport", eta_tr, "{:.3f}"),
                           ("drainage q, m/yr", q, "{:.3f}"),
                           ("flooded fraction of cell-time", f_flood, "{:.3f}"),
                           ("soil pCO2, uatm", pco2, "{:.0f}"),
                           ("indicative tCO2 gross/ha/yr", cdr, "{:.2f}")):
        p10, p50, p90 = wq(arr, (0.10, 0.50, 0.90))
        print(f"    {name:28s} area-weighted p10/p50/p90  "
              + " / ".join(fmt.format(v) for v in (p10, p50, p90)))

    excl = float((aw * (p_soc[m] > C.P_EXCEED_EXCLUDED)).sum() / aw.sum())
    marg = float((aw * ((p_soc[m] > C.P_EXCEED_PASSES)
                        & (p_soc[m] <= C.P_EXCEED_EXCLUDED))).sum() / aw.sum())
    print(f"    SOC>5wt% screen: {excl:.1%} of cropland area excluded, "
          f"{marg:.1%} marginal")
    paddy_share = float((aw * (f_flood[m] > 0.05)).sum() / aw.sum())
    print(f"    cells >5% flooded cell-time: {paddy_share:.1%} of cropland area")
    print(f"    pH<5.2 annotation flag: "
          f"{float((aw * ph_warn[m]).sum() / aw.sum()):.1%} of cropland area")

    # ---- GATE 2: indicative CO2 inside the physically plausible envelope
    p50 = wq(cdr, (0.5,))[0]
    ok2 = 0.05 <= p50 <= 10.0
    print(f"  GATE 2 indicative CO2 median {p50:.2f} in 0.05-10 tCO2/ha/yr  "
          f"[{'PASS' if ok2 else 'FAIL'}]")

    # ---- GATE 3: stoichiometric ceiling never exceeded
    worst = float(np.nanmax(cdr) / C.APPLICATION_RATE_T_HA_YR)
    ok3 = worst <= ceil_t + 1e-9
    print(f"  GATE 3 stoichiometric ceiling: max {worst:.3f} <= {ceil_t:.3f} "
          f"tCO2/t  [{'PASS' if ok3 else 'FAIL'}]")

    # ---- Save floats for aggregates and hover readout
    PROC.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        PROC / "v0_layers.npz",
        ph=ph, tair=tair, precip=precip, soc=soc, crop=crop, area=area,
        L1=L1.astype("float32"), eta=eta.astype("float32"),
        eta_tr=eta_tr.astype("float32"), cdr=cdr.astype("float32"),
        cascade=cascade.astype("float32"), p_soc=p_soc,
        q=q.astype("float32"), f_flood=f_flood.astype("float32"),
        pco2=pco2.astype("float32"),
        transform=np.array(transform).reshape(3, 3)[:2].ravel(),
    )
    print(f"  wrote {PROC / 'v0_layers.npz'} "
          f"({(PROC / 'v0_layers.npz').stat().st_size / 1e6:.1f} MB)")

    # ---- Encode textures
    write_textures(v_react, v_eta, v_drain, crop, p_soc, ph_warn, cdr, m,
                   cascade=cascade, ph=ph, L1=L1)
    emit_js(transform, w, h, gha, p50)
    print()
    print("done. Open src/index.html over HTTP:")
    print("  python3 -m http.server 8000 --directory src")
    return 0


# ---------------------------------------------------------------------------
def quantize(v, floor: float) -> np.ndarray:
    """Value function -> uint8, reserving 0 EXCLUSIVELY for masked cells.

    The floor is a correctness requirement: measured, with a floor of 1e-3 a
    single 8-bit step near zero moves the composite score by 0.23. At 0.02 the
    max error is 0.006. See constants.EPS_QUANTIZE.
    """
    x = np.clip(np.nan_to_num(v, nan=0.0), floor, 1.0)
    return (5 + np.rint((x - floor) / (1.0 - floor) * 250.0)).astype("uint8")


def write_textures(v_react, v_eta, v_drain, crop, p_soc, ph_warn, cdr, valid,
                   *, cascade, ph, L1) -> None:
    from PIL import Image
    out = SRC / "textures"
    out.mkdir(parents=True, exist_ok=True)
    h, w = crop.shape

    def rgba(r, g, b):
        a = np.full((h, w), 255, dtype="uint8")   # alpha ALWAYS 255, never data
        return Image.fromarray(np.dstack([r, g, b, a]), "RGBA")

    eps = C.EPS_QUANTIZE
    # tex1.r holds NORMALISED L1, not the value function. The shader applies the
    # piecewise function after adding the particle-size shift.
    lo, hi = L1_ENC
    l1n = np.clip((np.nan_to_num(L1, nan=lo) - lo) / (hi - lo), 0.0, 1.0)
    r1 = np.where(valid, np.rint(5 + l1n * 250.0), 0).astype("uint8")
    g1 = np.where(valid, quantize(v_eta, eps), 0).astype("uint8")
    b1 = np.where(valid, quantize(v_drain, C.CRITERION_FLOORS["drainage"]), 0).astype("uint8")

    # Bit-packed flags. NEAREST filtering only; bilinear across a flag boundary
    # would interpolate garbage bit patterns.
    flags = np.zeros((h, w), dtype="uint8")
    flags |= np.where(valid, 1, 0).astype("uint8")                       # bit0 in-domain
    flags |= np.where(p_soc > C.P_EXCEED_EXCLUDED, 2, 0).astype("uint8")  # bit1 excluded
    flags |= np.where((p_soc > C.P_EXCEED_PASSES)
                      & (p_soc <= C.P_EXCEED_EXCLUDED), 4, 0).astype("uint8")  # bit2 marginal
    flags |= np.where(ph_warn, 8, 0).astype("uint8")                     # bit3 pH<5.2 note

    r2 = np.rint(np.clip(crop, 0, 1) * 255).astype("uint8")
    b2 = np.rint(np.clip(np.nan_to_num(cdr) / 10.0, 0, 1) * 255).astype("uint8")

    # tex3 carries the Cascade baseline and raw soil pH. The baseline needs its
    # own channel: an earlier version drew "Cascade baseline" from the CDR
    # channel, so the mode was showing the wrong layer under a scientific label.
    #
    # Cascade's index spans ~4 orders of magnitude across cropland, so it is
    # stored as a log10 ratio to its own area-weighted median and then rescaled.
    # A linear encoding would quantise all but the acid tropics to zero -- which
    # is itself the point of the comparison, but it has to be visible, not lost
    # in the 8-bit floor.
    casc = np.where(valid & (cascade > 0), cascade, np.nan)
    med = float(np.nanmedian(casc))
    with np.errstate(divide="ignore", invalid="ignore"):
        lc = np.log10(casc / med)
    r3 = np.where(np.isfinite(lc),
                  np.rint(np.clip((lc + 2.0) / 4.0, 0, 1) * 255), 0).astype("uint8")
    # Soil pH over 3.0-10.0 for the hover readout.
    g3 = np.where(np.isfinite(ph),
                  np.rint(np.clip((ph - 3.0) / 7.0, 0, 1) * 255), 0).astype("uint8")
    b3 = np.zeros_like(g3)

    for name, img in (("tex1", rgba(r1, g1, b1)), ("tex2", rgba(r2, flags, b2)),
                      ("tex3", rgba(r3, g3, b3))):
        p = out / f"{name}.png"
        img.save(p, optimize=True)
        print(f"  wrote {p} ({p.stat().st_size / 1e6:.2f} MB)")


# Reactivity value function, on ABSOLUTE breakpoints in L1 = log10(R/R_ref).
# Shared with the shader via engine_constants.js so there is one definition.
REACT_KNOTS = [(-2.0, 0.0), (-1.0, 0.15), (0.0, 0.5), (0.7, 0.85), (1.5, 1.0)]

# L1 storage range. Wide enough that the particle-size shift cannot push a real
# value off the end of the 8-bit encoding.
L1_ENC = (-3.0, 3.0)

RAMP = [  # viridis-like, colour-blind safe, legible in light and dark
    (0.00, "#3b1f4d"), (0.20, "#3d4a8f"), (0.40, "#2a7b8f"),
    (0.60, "#3fa66b"), (0.80, "#a8c93a"), (1.00, "#f7e94a"),
]


def emit_js(transform, w, h, gha, cdr_p50) -> None:
    km = abs(transform.a) * 2.0 * np.pi * C.EARTH_RADIUS_M / 1000.0 / 360.0
    """One generator for BOTH the legend stops and the shader ramp, so they
    cannot drift. This is the failure mode that broke the sibling BiCRS Atlas."""
    payload = {
        "grid": {"width": w, "height": h,
                 "west": transform.c, "north": transform.f,
                 "dlon": abs(transform.a), "dlat": abs(transform.e)},
        "weights": C.WEIGHTS_DEFAULT,
        "floors": C.CRITERION_FLOORS,
        "epsQuantize": C.EPS_QUANTIZE,
        "aggP": C.AGG_P_DEFAULT,
        "criteria": [
            {"key": "reactivity", "tex": 1, "ch": 0, "label": "Weathering reactivity",
             "hint": "Palandri-Kharaka Ca+Mg release rate, relative to pH 6.5 / 15 C"},
            {"key": "eta_dic", "tex": 1, "ch": 1, "label": "Alkalinity retained as DIC",
             "hint": "Carbonate-equilibrium efficiency; the term Cascade omits"},
            {"key": "drainage", "tex": 1, "ch": 2, "label": "Drainage / transport",
             "hint": "q/(q+Dw); low where water residence limits export"},
        ],
        "ramp": RAMP,
        "reactKnots": REACT_KNOTS,
        "l1Enc": {"lo": L1_ENC[0], "hi": L1_ENC[1]},
        "psd": {
            "refD80": C.PSD_REF_D80_UM, "refWidth": C.PSD_REF_WIDTH,
            "d80Range": list(C.PSD_D80_SLIDER_RANGE),
            "widthRange": list(C.PSD_WIDTH_SLIDER_RANGE),
            "refSsa": round(K.ssa_geometric(C.PSD_REF_D80_UM, C.PSD_REF_WIDTH), 5),
            "lambdaDefault": C.LAMBDA_DEFAULT,
            "lambdaRange": list(C.LAMBDA_ROUGHNESS_RANGE),
            "deliveryRangeUm": [67, 500],
            "refWidthAssumed": C.PSD_REF_WIDTH_IS_ASSUMED,
            # Precomputed shift table so the browser needs no gamma function:
            # log10(SSA(d80, n) / SSA(ref)) on a grid the UI interpolates.
            "d80Grid": [round(x, 1) for x in np.linspace(*C.PSD_D80_SLIDER_RANGE, 24).tolist()],
            "widthGrid": [round(x, 3) for x in np.linspace(*C.PSD_WIDTH_SLIDER_RANGE, 13).tolist()],
            "shiftTable": [
                [round(float(K.ssa_log_shift(d, n)), 4)
                 for d in np.linspace(*C.PSD_D80_SLIDER_RANGE, 24)]
                for n in np.linspace(*C.PSD_WIDTH_SLIDER_RANGE, 13)
            ],
        },
        "cascadeEncoding": {"kind": "log10_ratio_to_median",
                            "lo": -2.0, "hi": 2.0},
        "phEncoding": {"lo": 3.0, "hi": 10.0},
        "eligibility": {"version": C.ELIGIBILITY_VERSION,
                        "socThreshold": C.SOC_EXCLUSION_WT_PCT,
                        "pExcluded": C.P_EXCEED_EXCLUDED,
                        "pPasses": C.P_EXCEED_PASSES},
        # Label the grid from the ACTUAL spacing, never from a constant that
        # might describe a different build. v0 is 0.1 deg (~11 km), not the 1 km
        # the plan targets, and the header must say so.
        "labels": {"grid": f"{round(abs(transform.a), 4):g}\u00b0 grid (~{km:.0f} km at the equator)",
                   "effectiveRes": C.EFFECTIVE_RES_LABEL,
                   "maxZoom": C.MAX_DISPLAY_ZOOM,
                   "build": "v0 preview"},
        "feedstock": {"archetype": C.FEEDSTOCK_DEFAULT,
                      "tco2PerT": round(C.DELIVERED_BASALT_TCO2_PER_T, 3),
                      "rateTHaYr": C.APPLICATION_RATE_T_HA_YR},
        "stats": {"croplandGha": round(gha, 3), "cdrMedian": round(cdr_p50, 2)},
        "provenance": {
            "soil": "SoilGrids v2.0 via ISRIC WCS (pH 0-15 cm, SOC 0-5 cm + quantiles)",
            "climate": "WorldClim 2.1 BIO1 / BIO12, 10 arc-min",
            "cropland": "Potapov et al. 2022 percent-cropland, 3 km",
            "drainage": "WaterGAP2-2e groundwater recharge via ISIMIP3a, 0.5 deg",
            "paddy": "GRPI Landsat inundation months x SPAM2010 irrigated rice",
            "substitutions": [
                "AIR temperature stands in for monthly SOIL temperature",
                "PRECIPITATION stands in for a soil-moisture climatology",
                "no feedstock or haul-cost layer yet",
            ],
            "dw": {"value": C.DAMKOHLER_DW_M_YR,
                   "range": list(C.DAMKOHLER_DW_RANGE),
                   "source": C.DAMKOHLER_SOURCE},
        },
    }
    (SRC / "engine_constants.js").write_text(
        "/* GENERATED by scripts/build_v0.py from scripts/constants.py.\n"
        "   Do not edit. Edit constants.py and rebuild. */\n"
        "window.ERW = " + json.dumps(payload, indent=2) + ";\n"
    )
    print(f"  wrote {SRC / 'engine_constants.js'}")


if __name__ == "__main__":
    raise SystemExit(main())
