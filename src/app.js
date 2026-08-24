/* ============================================================
   ERW Atlas — interactive layer.

   A single global equirectangular texture pair, composited in a WebGL2
   fragment shader so the weight sliders recolour ~5M cells with no fetch and
   no server. The score is computed on the GPU from packed value-function
   channels; the same values are kept CPU-side for the hover readout, so the
   numbers shown are the inputs rather than the colours.

   Deliberate choices, each with a reason:
     - Equirectangular, not Web Mercator. The analysis grid IS equirectangular,
       so this avoids a reprojection and the tile seams that come with it. It
       also refuses Mercator's area exaggeration, which matters when the thing
       being mapped is per-hectare.
     - Suitability is a value function OF GROSS CDR, not a weighted mean of
       proxies for it. The three physical terms enter as a product with unit
       exponents, so zero removal gives zero suitability by construction. An
       earlier design used a compensatory geometric mean with a uniform 0.02
       quantisation floor, which gave a cell with no carbon removal a score of 27.
     - The sliders are term EXPONENTS, not importance weights: you cannot prefer
       dissolution rate over alkalinity retention, because both are required
       multiplicatively for any carbon to be stored.
     - Colormap and legend are generated from ONE array in engine_constants.js,
       so they cannot drift.
   ============================================================ */
(function () {
  "use strict";

  const E = window.ERW;
  const G = E.grid;

  const MODE_HINT = {
    score: "Overall ERW potential, 0–100, scaled from gross CO₂ " +
           "removal per hectare.",
    limiting: "The factor that most limits CO₂ removal at each location.",
    frac: "Share of the applied rock predicted to weather in the first year, " +
          "at the current grind.",
  };
  // Index 3 is the drainage-concentration ceiling, not one of the three terms.
  // Must match factorColor() in the shader: vec3(0.796, 0.549, 0.902).
  const FACTOR_COLORS = ["#e0704f", "#4f9fe0", "#8fd14f", "#cb8ce6"];
  const CEIL_LABEL = "Drainage cannot carry it";

  let gl, prog, quad, texA, texB, texC, texD, texRamp, texRampFrac, cpu = null;
  let mode = "score";
  let showQuarries = false;
  let showMafic = false;
  // Term exponents, NOT importance weights. Default 1 means the composite is
  // exactly the physical product, so gross CDR -- and hence suitability -- is
  // zero wherever any required term is zero.
  const termExp = {reactivity: 1, eta_dic: 1, drainage: 1};
  // Economic weight. A real preference, not a what-if: cost genuinely trades off
  // against physical potential in a way the physical terms do not trade off
  // against each other.
  const econ = {
    costExp: E.cost ? E.cost.expDefault : 0,
    // The two delivered-cost assumptions, live. Defaults are the build's own
    // values, so the shipped view is the built view. truckMult multiplies the
    // REGIONAL per-km rates baked into the texture (US $0.10, Brazil $0.055,
    // India $0.045, ...); a single $/t-km number stopped being meaningful when
    // the rates became regional.
    gate: E.cost ? E.cost.gateUsdT : 0,
    truckMult: 1,
  };

  const CRIT = E.terms;
  // Drainage-concentration ceiling. Falls back to OFF with a neutral encoding if
  // an older engine_constants.js is served, so a stale build degrades to the
  // previous behaviour rather than throwing on load.
  const FC = E.fluxCeiling || {on: false, enc: {lo: -4, hi: 0.3}};

  /* Whether the drainage-concentration ceiling is APPLIED, at runtime. The bound
     is computed in the build and shipped in tex2.b either way -- that separation
     is what makes this a toggle rather than a rebuild -- and constants.FLUX_CEILING_ON
     sets where the control starts. It is off by default because the bound is out
     for review by the ERW community (docs/rfc_flux_reconciliation.tex), not because
     it is cheap to compute.

     Read through this variable, never FC.on, or half the map applies the bound and
     half does not. FC.enc and FC.omega stay on FC: those are data, not the switch. */
  let ceilOn = !!FC.on;

  // Data extent, from the generated grid constants.
  const DATA = {
    north: G.north, south: G.north - G.height * G.dlat,
    get latSpan() { return this.north - this.south; },
    get latMid() { return (this.north + this.south) / 2; },
  };
  // Particle size. Held separately from the weights because it is a physical
  // assumption about the feedstock, not a preference about what matters.
  const psd = { d50: E.psd.refD50, width: E.psd.refWidth };

  /* Bilinear lookup into the precomputed log10(SSA/SSA_ref) table. Precomputed
     in Python so the browser needs no gamma function and cannot disagree with
     the pipeline about the integral. */
  function ssaShift() {
    const P = E.psd, gx = P.d50Grid, gy = P.widthGrid, T = P.shiftTable;
    const f = (arr, v) => {
      if (v <= arr[0]) return [0, 0];
      if (v >= arr[arr.length - 1]) return [arr.length - 2, 1];
      let i = 0; while (i < arr.length - 2 && v > arr[i + 1]) i++;
      return [i, (v - arr[i]) / (arr[i + 1] - arr[i])];
    };
    const [i, fi] = f(gx, psd.d50), [j, fj] = f(gy, psd.width);
    const a = T[j][i] + (T[j][i + 1] - T[j][i]) * fi;
    const b = T[j + 1][i] + (T[j + 1][i + 1] - T[j + 1][i]) * fi;
    return a + (b - a) * fj;
  }

  /* Implied geometric SSA, m2/g, for display. */
  const ssaNow = () => E.psd.refSsa * Math.pow(10, ssaShift());

  // view: centre lon/lat + a zoom multiplier on the fit-to-data scale.
  const view = { lon: 10, lat: DATA.latMid, zoom: 1 };

  /* ---------------- helpers ---------------- */
  const $ = (id) => document.getElementById(id);
  const clamp = (lo, v, hi) => Math.max(lo, Math.min(hi, v));

  /* Multiplier on the regional per-km rates baked into tex3.b. */
  function truckScale() {
    return econ.truckMult;
  }

  /* Baked v_cost -> v_cost at the current rate multiplier. The whole haul --
     including the fixed trip charge, which is 50 km of driving priced at the
     regional rate -- is linear in the rate, so v' = v/(m + v(1-m)) is exact
     and the bit-exact identity at m = 1. Mirrors the shader; the Node harness
     in tests/ asserts they agree. */
  function vCostLive(vBaked) {
    const fl = E.cost ? E.cost.floor : 1;
    if (!(vBaked > 0)) return fl;
    const m = truckScale();
    return clamp(fl, vBaked / (m + vBaked * (1 - m)), 1);
  }

  /* True when both cost assumptions sit at the build's own values. */
  function econAtRef() {
    if (!E.cost) return true;
    return Math.abs(econ.gate - E.cost.gateUsdT) < 1e-9
        && Math.abs(econ.truckMult - 1) < 1e-12;
  }

  function hex2rgb(h) {
    return [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16),
            parseInt(h.slice(5, 7), 16)];
  }
  function rampColorAt(t, stops) {
    const r = stops || E.ramp;
    t = clamp(0, t, 1);
    for (let i = 1; i < r.length; i++) {
      if (t <= r[i][0]) {
        const [t0, c0] = r[i - 1], [t1, c1] = r[i];
        const f = (t - t0) / (t1 - t0 || 1);
        const a = hex2rgb(c0), b = hex2rgb(c1);
        return [0, 1, 2].map((k) => Math.round(a[k] + (b[k] - a[k]) * f));
      }
    }
    return hex2rgb(r[r.length - 1][1]);
  }
  const rampCss = (t, stops) => "rgb(" + rampColorAt(t, stops).join(",") + ")";

  /* ---------------- shader ---------------- */
  const VS = `#version 300 es
  in vec2 aPos;
  out vec2 vUV;
  uniform vec4 uWin;              // west, north, degPerPxX, degPerPxY
  void main() {
    // aPos is a full-screen quad in clip space; derive lon/lat then UV.
    vUV = aPos;
    gl_Position = vec4(aPos * 2.0 - 1.0, 0.0, 1.0);
  }`;

  const FS = `#version 300 es
  precision highp float;          // mediump banded visibly on test hardware
  in vec2 vUV;
  out vec4 fragColor;

  uniform sampler2D uA, uB, uC, uD, uRamp, uRampFrac;
  uniform int uShowMafic;         // 1 = tint GLiM mafic outcrop
  uniform vec4 uGeo;              // lon0, lat0, lonSpan, latSpan of the visible box
  uniform vec4 uGrid;             // west, north, dlon, dlat of the data grid
  uniform vec2 uGridSize;
  uniform vec3 uExp;              // term exponents; 1,1,1 == the physics
  uniform int  uMode;             // 0 suitability, 1 limiting, 2 fraction weathered
  uniform vec2 uL1Enc;            // lo, hi of the stored L1 range
  uniform vec2 uCeilEnc;          // lo, hi of log10(ceiling / cdrPerFrac) in tex2.b
  uniform int  uCeilOn;           // 1 = apply the drainage-concentration ceiling
  // Shrinking-core dissolution. uG is a 64-node slice of G(u, n) at the CURRENT
  // width, interpolated in JS because the width slider is global. u = delta/d50,
  // so the grind enters HERE and no longer multiplies the rate -- under shrinking
  // core the linear retreat rate does not depend on particle size.
  uniform float uG[64];
  uniform vec2  uGLogU;           // lo, hi of log10(u) spanned by uG
  uniform float uUScale;          // deltaRef / d50, i.e. u = uUScale * X
  uniform float uCdrPerFrac;      // tCO2/ha/yr per unit dissolved fraction
  uniform float uNegligible;      // CDR below this is "no meaningful potential"
  uniform float uFracRampMax;     // top of the fraction-weathered colour ramp
  uniform float uCx[6], uCy[6];   // suitability knots, x in log10(tCO2/ha/yr)
  uniform float uCostExp;         // exponent on the compensatory cost multiplier
  uniform float uCostFloor;
  // Live rescale of the baked cost value function. tex3.b stores
  // v = 1/(1 + haul/S) with haul = r(region) * (road_km + 50), the 50 km being
  // the fixed trip time priced at the regional rate. The whole haul is linear
  // in r, so the multiplier rescale v' = v / (m + v*(1 - m)) is exact -- and
  // the fixed charge scales with m ON PURPOSE: m represents the market's
  // hourly cost level, which trip time shares. Written in this form so m = 1
  // is the bit-exact identity: m + v*(1 - m) evaluates to exactly 1 at m = 1.
  uniform float uTruckScale;      // m, the multiplier on regional rates

  const vec4 OUT_OF_DOMAIN = vec4(0.0, 0.0, 0.0, 0.0);
  const vec4 NEGLIGIBLE    = vec4(0.16, 0.17, 0.19, 1.0);
  // Distinct from NEGLIGIBLE on purpose: "we do not know" and "there is nothing
  // here" are different claims and must not share a colour.
  const vec4 NO_INPUT      = vec4(0.42, 0.44, 0.47, 1.0);
  // Earthy and desaturated on purpose: it reads as geology rather than as data,
  // and it collides with neither ramp (teal-yellow, magenta-orange) nor the
  // quarry dots (orange / aqua / gold).
  const vec3 MAFIC         = vec3(0.549, 0.478, 0.388);

  // One blend, used on every in-domain return path so the overlay does not
  // silently vanish in the fraction-weathered and limiting-factor layers.
  vec4 withMafic(vec3 c, float mafic) {
    return vec4(mafic > 0.02 ? mix(c, MAFIC, mafic * 0.55) : c, 1.0);
  }

  vec3 factorColor(int i) {
    if (i == 0) return vec3(0.878, 0.439, 0.310);
    if (i == 1) return vec3(0.310, 0.624, 0.878);
    if (i == 2) return vec3(0.561, 0.820, 0.310);
    return vec3(0.796, 0.549, 0.902);          // 3 = drainage cannot carry it
  }

  void main() {
    // Screen -> lon/lat -> data grid. Equirectangular, so this is linear.
    float lon = uGeo.x + vUV.x * uGeo.z;
    float lat = uGeo.y - (1.0 - vUV.y) * uGeo.w;
    if (lon < -180.0 || lon > 180.0) { fragColor = OUT_OF_DOMAIN; return; }

    float gx = (lon - uGrid.x) / uGrid.z;
    float gy = (uGrid.y - lat) / uGrid.w;
    if (gx < 0.0 || gy < 0.0 || gx >= uGridSize.x || gy >= uGridSize.y) {
      fragColor = OUT_OF_DOMAIN; return;
    }
    ivec2 px = ivec2(int(gx), int(gy));

    // NEAREST fetch. Bilinear across a bit-packed flag boundary would
    // interpolate garbage bit patterns, and would invent detail the grid lacks.
    vec4 a = vec4(texelFetch(uA, px, 0));
    vec4 b = vec4(texelFetch(uB, px, 0));
    vec4 cc = vec4(texelFetch(uC, px, 0));
    float mafic = uShowMafic == 1 ? texelFetch(uD, px, 0).r : 0.0;

    int flags = int(b.g * 255.0 + 0.5);
    if ((flags & 1) == 0) {
      // Outside the cropland domain the map is otherwise transparent, but three
      // quarters of mafic outcrop lives out here and "where is the nearest
      // feedstock" is a question about exactly that land.
      if (mafic > 0.02) { fragColor = vec4(MAFIC, mafic * 0.62); return; }
      fragColor = OUT_OF_DOMAIN; return;
    }

    if ((flags & 2) != 0) {                   // fails the SOC screen outright
      fragColor = withMafic(vec3(0.30, 0.16, 0.16), mafic);
      return;
    }

    // No monthly climate input, so the rate is undefined here. Drawn in every
    // mode, including "weathered in year 1": there is no number to show.
    if ((flags & 4) != 0) { fragColor = withMafic(NO_INPUT.rgb, mafic); return; }

    // Dequantise the RAW physical terms. Value 0 is reserved for masked cells,
    // so data occupies 5..255 -- and a decoded zero is a true zero, which
    // matters because zero really does mean no carbon.
    // NO grind term here any more. Grind acts through the particle-size integral
    // below, not as a surface-area multiplier on the rate.
    float l1  = mix(uL1Enc.x, uL1Enc.y, clamp((a.r * 255.0 - 5.0) / 250.0, 0.0, 1.0));
    float rel = pow(10.0, l1);                          // R / R_ref
    float eDic = clamp((a.g * 255.0 - 5.0) / 250.0, 0.0, 1.0);
    float eTr  = clamp((a.b * 255.0 - 5.0) / 250.0, 0.0, 1.0);

    // Terms in a PHYSICAL PRODUCT, with unit exponents by default. No carbon is
    // stored unless all three are non-zero, so a compensatory mean would be
    // wrong in kind: it let good alkalinity retention offset zero reactivity.
    float lr = uExp.x * log(max(rel,  1e-12));
    float ld = uExp.y * log(max(eDic, 1e-12));
    float lt = uExp.z * log(max(eTr,  1e-12));

    // Gross CDR, then suitability as a value function OF THAT. Zero CDR gives
    // zero suitability by construction rather than by tuning a floor.
    // eta_DIC stays OUT of the dissolution exponential: carbonate speciation
    // does not slow the rock dissolving, it discounts the carbon carried per
    // unit dissolved. Inside the exponential it also suppressed the predicted
    // fraction weathered by up to ~2x in acid soils -- the one layer field
    // trials can measure.
    float X = exp(lr + lt);

    // Shrinking core over the Rosin-Rammler distribution, by lookup. Replaces
    // frac = 1 - exp(-k*X), which decayed the BULK mass at one rate and so let the
    // coarse tail dissolve as easily as the fines.
    float frac;
    {
      float u = uUScale * X;
      float t = (log(max(u, 1e-30)) / log(10.0) - uGLogU.x)
                / (uGLogU.y - uGLogU.x) * 63.0;
      if (t <= 0.0)       { frac = 0.0; }
      else if (t >= 63.0) { frac = uG[63]; }
      else {
        int i = int(t);
        frac = mix(uG[i], uG[i + 1], t - float(i));
      }
    }

    // Fraction weathered on its OWN ramp. No economics multiplier and no
    // negligible cutoff: this is a physical quantity whose zero is meaningful on
    // the ramp itself, so masking the bottom would hide real information rather
    // than protect against over-reading a near-zero score.
    //
    // This layer is deliberately NOT bounded by the drainage ceiling below. It is
    // the rock dissolving, which is a different quantity from the carbon leaving.
    if (uMode == 2) {
      // Ramp spans 0..uFracRampMax, not 0..1: most of cropland sits below 60%
      // weathered, so a full-range ramp spent its top 40% on ~2% of the map.
      // Values above the top clamp, and the legend labels that end with ">=".
      vec3 fc = texture(uRampFrac, vec2(clamp(frac / uFracRampMax, 0.0, 1.0), 0.5)).rgb;
      fragColor = withMafic(fc, mafic);
      return;
    }

    // No grind factor here: grind is inside frac, through the particle-size
    // integral. It was applied twice once before, via a surface-area multiplier
    // on the rate AND again on the CO2 figure, which inflated CO2 by 3.45x at the
    // fine end and broke the stoichiometric ceiling.
    float cdr = frac * exp(ld) * uCdrPerFrac;

    // DRAINAGE-CONCENTRATION CEILING. The carbon has to leave dissolved in the
    // water that leaves, so it is bounded by q * [HCO3-]_max * 44 no matter how
    // fast the rock dissolves. This MUST be applied here and not only in Python:
    // the grind slider recomputes cdr live on the GPU, so without it the slider
    // would walk the displayed carbon straight back through the bound.
    //
    // Deliberately NOT applied to frac above. Rock can dissolve without the
    // carbon leaving -- that is the retention lag field trials measure -- so the
    // fraction-weathered layer stays unbounded and the gap between the two is
    // real information rather than an inconsistency.
    float ceil = pow(10.0, mix(uCeilEnc.x, uCeilEnc.y,
                               clamp((b.b * 255.0 - 5.0) / 250.0, 0.0, 1.0)))
                 * uCdrPerFrac;
    bool ceilBinds = uCeilOn == 1 && ceil < cdr;
    if (uCeilOn == 1) cdr = min(cdr, ceil);

    // Which term costs the most here. The ceiling gets its OWN state rather than
    // being folded into the drainage term: when it binds, the limit is not that
    // the water moves too slowly, it is that the water cannot hold the carbon at
    // any speed -- and on 91.0% of cropland that is the operative limit, which is
    // exactly the thing a reader needs to be told.
    if (uMode == 1) {
      if (ceilBinds) { fragColor = withMafic(factorColor(3), mafic); return; }
      int lo = (lr <= ld && lr <= lt) ? 0 : ((ld <= lt) ? 1 : 2);
      fragColor = withMafic(factorColor(lo), mafic);
      return;
    }

    if (cdr < uNegligible) { fragColor = withMafic(NEGLIGIBLE.rgb, mafic); return; }

    float lc = log(cdr) / log(10.0);
    float sc = uCy[0];
    for (int i = 0; i < 5; i++) {
      if (lc >= uCx[i] && lc <= uCx[i + 1]) {
        sc = mix(uCy[i], uCy[i + 1], (lc - uCx[i]) / (uCx[i + 1] - uCx[i]));
      }
    }
    if (lc > uCx[5]) sc = uCy[5];

    // Economic discount. Compensatory, with a floor, so it never zeroes a cell
    // that has real physical potential -- only the physics annihilates.
    float vBaked = uCostFloor
                 + clamp((cc.b * 255.0 - 5.0) / 250.0, 0.0, 1.0) * (1.0 - uCostFloor);
    // The QUARRY GATE COST DELIBERATELY DOES NOT APPEAR HERE. v_cost penalises the
    // haul increment only -- v = 1/(1 + (F + r*d)/S) -- so the gate cancels
    // out of the multiplier exactly. It moves the reported $/t and the cost
    // screen, never the colour. The UI says so, because a slider that visibly
    // does nothing otherwise reads as broken.
    float vCost = clamp(vBaked / (uTruckScale + vBaked * (1.0 - uTruckScale)),
                        uCostFloor, 1.0);
    sc *= pow(vCost, uCostExp);

    vec3 col = texture(uRamp, vec2(clamp(sc, 0.0, 1.0), 0.5)).rgb;
    // No marginal-eligibility hatch. It covered 53% of cropland, which made it
    // the dominant feature of the map while saying little, and it drowned out the
    // failures it was meant to accompany. Only outright failures are drawn now.
    fragColor = withMafic(col, mafic);
  }`;

  function compile(src, type) {
    const s = gl.createShader(type);
    gl.shaderSource(s, src); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
      throw new Error(gl.getShaderInfoLog(s) + "\n" + src);
    }
    return s;
  }

  function initGL() {
    const c = $("gl");
    gl = c.getContext("webgl2", { antialias: false, premultipliedAlpha: false });
    if (!gl) throw new Error("WebGL2 is required (MapLibre v6 dropped WebGL1 too).");
    prog = gl.createProgram();
    gl.attachShader(prog, compile(VS, gl.VERTEX_SHADER));
    gl.attachShader(prog, compile(FS, gl.FRAGMENT_SHADER));
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      throw new Error(gl.getProgramInfoLog(prog));
    }
    quad = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, quad);
    gl.bufferData(gl.ARRAY_BUFFER,
      new Float32Array([0, 0, 1, 0, 0, 1, 1, 1]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, "aPos");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  }

  async function loadTexture(url, unit) {
    const blob = await (await fetch(url)).blob();
    // premultiplyAlpha:'none' is load-bearing. The default premultiplies and
    // silently destroys the RGB channels of any pixel with alpha < 255 -- it is
    // the colour channels that are corrupted, not alpha. We also write
    // alpha = 255 everywhere in the encoder, which is the real defence.
    const bmp = await createImageBitmap(blob, {
      premultiplyAlpha: "none", colorSpaceConversion: "none",
    });
    const t = gl.createTexture();
    gl.activeTexture(gl.TEXTURE0 + unit);
    gl.bindTexture(gl.TEXTURE_2D, t);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
    gl.pixelStorei(gl.UNPACK_COLORSPACE_CONVERSION_WEBGL, gl.NONE);
    gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, gl.RGBA, gl.UNSIGNED_BYTE, bmp);
    for (const p of [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER]) {
      gl.texParameteri(gl.TEXTURE_2D, p, gl.NEAREST);
    }
    for (const p of [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T]) {
      gl.texParameteri(gl.TEXTURE_2D, p, gl.CLAMP_TO_EDGE);
    }
    return { tex: t, bmp: bmp };
  }

  function makeRampTexture(stops, unit) {
    // Built from the SAME array the legend reads, so they cannot disagree.
    const n = 256, px = new Uint8Array(n * 4);
    for (let i = 0; i < n; i++) {
      const c = rampColorAt(i / (n - 1), stops);
      px[i * 4] = c[0]; px[i * 4 + 1] = c[1]; px[i * 4 + 2] = c[2]; px[i * 4 + 3] = 255;
    }
    const t = gl.createTexture();
    gl.activeTexture(unit);
    gl.bindTexture(gl.TEXTURE_2D, t);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, n, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, px);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    return t;
  }

  /* Region ids for the readout header, CPU-only: admin.png packs a 16-bit
     Natural Earth admin-1 id into R,G. Optional — the readout falls back to
     bare coordinates if the texture or the name table is missing. */
  let adminIds = null;
  async function loadAdminIds() {
    try {
      const blob = await (await fetch("textures/admin.png")).blob();
      const bmp = await createImageBitmap(blob, {
        premultiplyAlpha: "none", colorSpaceConversion: "none",
      });
      const cv = document.createElement("canvas");
      cv.width = G.width; cv.height = G.height;
      const ctx = cv.getContext("2d", { willReadFrequently: true });
      ctx.drawImage(bmp, 0, 0);
      adminIds = ctx.getImageData(0, 0, G.width, G.height).data;
    } catch (e) { adminIds = null; }
  }

  function regionNameAt(i) {
    if (!adminIds || !window.ADMIN) return null;
    const id = adminIds[i] + (adminIds[i + 1] << 8);
    return id ? window.ADMIN.names[id] || null : null;
  }

  /* What is grown here, CPU-only for the same reason as the region lookup:
     nothing is coloured by crop, so this never reaches the GPU. crops.png packs
     four 6-bit fields into RGB (see build_v0.write_crop_texture):

       bits 0-5 id1 | 6-11 id2 | 12-17 share1 | 18-23 share2

     Optional throughout — an older build without crops.png simply omits the
     row rather than breaking the readout. */
  let cropIds = null;
  async function loadCropMix() {
    try {
      const blob = await (await fetch("textures/crops.png")).blob();
      const bmp = await createImageBitmap(blob, {
        premultiplyAlpha: "none", colorSpaceConversion: "none",
      });
      const cv = document.createElement("canvas");
      cv.width = G.width; cv.height = G.height;
      const ctx = cv.getContext("2d", { willReadFrequently: true });
      ctx.drawImage(bmp, 0, 0);
      cropIds = ctx.getImageData(0, 0, G.width, G.height).data;
    } catch (e) { cropIds = null; }
  }

  /* [{name, share, aggregate}, ...] largest first, or null. Shares are of the
     cell's CROPPED area, which is not the same denominator as the cropland
     fraction the rest of the readout uses -- said so in the label. */
  function cropsAt(i) {
    const CR = E.crops;
    if (!cropIds || !CR || !CR.names) return null;
    const word = cropIds[i] | (cropIds[i + 1] << 8) | (cropIds[i + 2] << 16);
    const id1 = word & 63, id2 = (word >> 6) & 63;
    if (!id1) return null;
    const lv = CR.shareLevels || 63;
    const out = [];
    const push = (id, q) => {
      const nm = CR.names[id];
      if (id && nm) out.push({name: nm, share: q / lv});
    };
    push(id1, (word >> 12) & 63);
    push(id2, (word >> 18) & 63);
    return out.length ? out : null;
  }

  /* ---------------- CPU-side copy for the readout ---------------- */
  function decodeToCPU(bmpA, bmpB, bmpC) {
    const cv = document.createElement("canvas");
    cv.width = G.width; cv.height = G.height;
    const ctx = cv.getContext("2d", { willReadFrequently: true });
    const grab = (bmp) => {
      ctx.clearRect(0, 0, cv.width, cv.height);
      ctx.drawImage(bmp, 0, 0);
      return ctx.getImageData(0, 0, cv.width, cv.height).data;
    };
    return { A: grab(bmpA), B: grab(bmpB), C: grab(bmpC) };
  }

  /* ---------------- geometry of the current view ---------------- */
  function visibleBox() {
    const c = $("gl");
    const wCss = c.clientWidth || 1, hCss = c.clientHeight || 1;
    // Zoom 1 = fit the whole DATA extent. Taking the max of the two required
    // scales means the more constraining axis wins, so nothing is cropped at
    // the default view. Using 360/w alone let the latitude span reach 320 deg,
    // which put the top edge at an impossible latitude and shrank the world
    // into the middle of the frame.
    const degPerPxCss = Math.max(360 / wCss, DATA.latSpan / hCss) / view.zoom;
    const lonSpan = wCss * degPerPxCss, latSpan = hCss * degPerPxCss;
    return {
      lon0: view.lon - lonSpan / 2, lat0: view.lat + latSpan / 2,
      lonSpan, latSpan,
      degPerPxCss,                        // for mouse deltas (CSS pixels)
      degPerPx: degPerPxCss,              // alias; zoom-cap test uses this
    };
  }

  /* Keep the data in view: never pan so far that the grid leaves the frame. */
  function clampView() {
    const b = visibleBox();
    if (b.lonSpan >= 360) view.lon = 0;
    else view.lon = clamp(-180 + b.lonSpan / 2, view.lon, 180 - b.lonSpan / 2);
    if (b.latSpan >= DATA.latSpan) view.lat = DATA.latMid;
    else {
      view.lat = clamp(DATA.south + b.latSpan / 2, view.lat,
                       DATA.north - b.latSpan / 2);
    }
  }

  function draw() {
    const c = $("gl");
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.round(c.clientWidth * dpr), h = Math.round(c.clientHeight * dpr);
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    gl.viewport(0, 0, w, h);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    if (!texA) return;

    const box = visibleBox();
    gl.useProgram(prog);
    const u = (n) => gl.getUniformLocation(prog, n);
    gl.uniform4f(u("uGeo"), box.lon0, box.lat0, box.lonSpan, box.latSpan);
    gl.uniform4f(u("uGrid"), G.west, G.north, G.dlon, G.dlat);
    gl.uniform2f(u("uGridSize"), G.width, G.height);
    gl.uniform3f(u("uExp"), termExp.reactivity, termExp.eta_dic, termExp.drainage);
    gl.uniform1i(u("uMode"), mode === "score" ? 0 : (mode === "limiting" ? 1 : 2));
    gl.uniform2f(u("uL1Enc"), E.l1Enc.lo, E.l1Enc.hi);
    gl.uniform2f(u("uCeilEnc"), FC.enc.lo, FC.enc.hi);
    gl.uniform1i(u("uCeilOn"), ceilOn ? 1 : 0);
    const gslice = gSlice();
    gl.uniform1fv(u("uG[0]"), gslice);
    gl.uniform2f(u("uGLogU"), E.dissolution.uLog.lo, E.dissolution.uLog.hi);
    gl.uniform1f(u("uUScale"), E.dissolution.deltaRefUm / psd.d50);
    gl.uniform1f(u("uCdrPerFrac"), E.cdrPerFrac);
    gl.uniform1f(u("uNegligible"), E.cdrNegligible);
    gl.uniform1f(u("uFracRampMax"), E.fracRampMax || 1.0);
    gl.uniform1i(u("uShowMafic"), showMafic ? 1 : 0);
    gl.uniform1fv(u("uCx"), new Float32Array(E.cdrKnots.map(k => Math.log10(k[0]))));
    gl.uniform1fv(u("uCy"), new Float32Array(E.cdrKnots.map(k => k[1])));
    gl.uniform1f(u("uCostExp"), econ.costExp);
    gl.uniform1f(u("uCostFloor"), E.cost ? E.cost.floor : 1.0);
    gl.uniform1f(u("uTruckScale"), truckScale());
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, texA);
    gl.uniform1i(u("uA"), 0);
    gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, texB);
    gl.uniform1i(u("uB"), 1);
    gl.activeTexture(gl.TEXTURE2); gl.bindTexture(gl.TEXTURE_2D, texC);
    gl.uniform1i(u("uC"), 2);
    gl.activeTexture(gl.TEXTURE5); gl.bindTexture(gl.TEXTURE_2D, texD);
    gl.uniform1i(u("uD"), 5);
    gl.activeTexture(gl.TEXTURE3); gl.bindTexture(gl.TEXTURE_2D, texRamp);
    gl.uniform1i(u("uRamp"), 3);
    gl.activeTexture(gl.TEXTURE4); gl.bindTexture(gl.TEXTURE_2D, texRampFrac);
    gl.uniform1i(u("uRampFrac"), 4);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);

    drawLand(box);
  }

  /* Coastlines on a 2-D overlay canvas above the GL canvas. */
  let landCv;
  function drawLand(box) {
    if (!landCv) {
      landCv = document.createElement("canvas");
      landCv.style.cssText = "position:absolute;inset:0;width:100%;height:100%;pointer-events:none";
      $("map-wrap").insertBefore(landCv, $("readout"));
    }
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.round(landCv.clientWidth * dpr), h = Math.round(landCv.clientHeight * dpr);
    if (landCv.width !== w || landCv.height !== h) { landCv.width = w; landCv.height = h; }
    const g = landCv.getContext("2d");
    g.clearRect(0, 0, w, h);
    const sx = w / box.lonSpan, sy = h / box.latSpan;
    const X = (lon) => (lon - box.lon0) * sx;
    const Y = (lat) => (box.lat0 - lat) * sy;

    // Clip to the data band. Without this, Antarctica and the high Arctic are
    // outlined in regions the analysis does not cover, which makes empty space
    // read as a broken map rather than as absence of data.
    g.save();
    g.beginPath();
    g.rect(0, Y(DATA.north), w, Y(DATA.south) - Y(DATA.north));
    g.clip();

    const light = window.matchMedia("(prefers-color-scheme: light)").matches;
    g.lineWidth = Math.max(0.7, 0.8 * dpr);
    g.strokeStyle = light ? "rgba(60,85,105,0.55)" : "rgba(150,175,195,0.55)";
    g.beginPath();
    for (const f of window.LAND.features) {
      const polys = f.geometry.type === "Polygon"
        ? [f.geometry.coordinates] : f.geometry.coordinates;
      for (const poly of polys) {
        for (const ring of poly) {
          for (let i = 0; i < ring.length; i++) {
            const x = X(ring[i][0]), y = Y(ring[i][1]);
            if (i === 0) g.moveTo(x, y); else g.lineTo(x, y);
          }
          g.closePath();
        }
      }
    }
    g.stroke();

    // Quarry points. Drawn on the 2-D overlay rather than in the shader because
    // they are vector features at a finer scale than the raster grid, and because
    // they should stay legible when zoomed out without becoming a solid blob.
    if (showQuarries && window.QUARRIES) {
      const pts = window.QUARRIES.points;
      const src = {MRDS: "#e8734a", ANM: "#4ad2a8", OSM: "#c9a227"};
      const rad = Math.max(1.1, Math.min(3.4, 0.9 * dpr * Math.sqrt(view.zoom)));
      g.globalAlpha = 0.85;
      for (let i = 0; i < pts.length; i++) {
        const x = X(pts[i][0]), y = Y(pts[i][1]);
        if (x < -8 || y < -8 || x > w + 8 || y > h + 8) continue;
        g.beginPath();
        g.fillStyle = src[pts[i][2]] || "#999";
        g.arc(x, y, rad, 0, 6.2832);
        g.fill();
      }
      g.globalAlpha = 1;
    }

    // Graticule every 30 deg, so the projection is legible.
    g.lineWidth = Math.max(0.4, 0.5 * dpr);
    g.strokeStyle = light ? "rgba(60,85,105,0.13)" : "rgba(150,175,195,0.13)";
    g.beginPath();
    for (let lon = -180; lon <= 180; lon += 30) { g.moveTo(X(lon), 0); g.lineTo(X(lon), h); }
    for (let lat = -60; lat <= 80; lat += 30) { g.moveTo(0, Y(lat)); g.lineTo(w, Y(lat)); }
    g.stroke();
    g.restore();
  }

  /* ---------------- physics, mirroring the shader ----------------
     One definition each, used by the hover readout and the stability sample.
     The shader has its own copy in GLSL; gate 8 in test_kinetics.py asserts the
     generated constants both read from agree with Python. */
  function grossCdr(rel, eDic, eTr, ceil) {
    const lr = termExp.reactivity * Math.log(Math.max(rel, 1e-12));
    const ld = termExp.eta_dic * Math.log(Math.max(eDic, 1e-12));
    const lt = termExp.drainage * Math.log(Math.max(eTr, 1e-12));
    // Dissolution drivers only in X; eta_DIC discounts the carbon afterwards
    // (it does not slow the rock). rel already carries the grind shift, so cdr
    // must not multiply by it again -- see the matching shader comments.
    const X = Math.exp(lr + lt);
    const frac = fracOf(X);
    // The ceiling bounds the CARBON and not the rock, so frac is returned
    // unbounded and cdr is capped. Mirrors the shader exactly; gate 8 in
    // test_kinetics.py asserts both read the same generated constants.
    const uncapped = frac * Math.exp(ld) * E.cdrPerFrac;
    const capped = (ceilOn && ceil !== undefined) ? Math.min(uncapped, ceil)
                                                 : uncapped;
    return {cdr: capped, cdrUncapped: uncapped, ceil, frac,
            ceilBinds: ceilOn && ceil !== undefined && ceil < uncapped,
            contrib: [lr, ld, lt]};
  }

  function suitabilityOf(cdr) {
    if (cdr < E.cdrNegligible) return 0;
    const KN = E.cdrKnots, lc = Math.log10(cdr);
    let v = KN[0][1];
    for (let i = 0; i < KN.length - 1; i++) {
      const x0 = Math.log10(KN[i][0]), x1 = Math.log10(KN[i + 1][0]);
      if (lc >= x0 && lc <= x1) {
        v = KN[i][1] + (KN[i + 1][1] - KN[i][1]) * (lc - x0) / (x1 - x0);
      }
    }
    if (lc > Math.log10(KN[KN.length - 1][0])) v = KN[KN.length - 1][1];
    return v;
  }

  /* Decode the raw physical terms at a cell index. */
  function termsAt(i) {
    const A = cpu.A, B = cpu.B, C3 = cpu.C;
    const raw = (b) => clamp(0, (b - 5) / 250, 1);
    const l1 = E.l1Enc.lo + raw(A[i]) * (E.l1Enc.hi - E.l1Enc.lo);   // no grind term
    const fl = E.cost ? E.cost.floor : 1;
    return {rel: Math.pow(10, l1), l1, eDic: raw(A[i + 1]), eTr: raw(A[i + 2]),
            ceil: decodeCeil(B[i + 2]),
            vCost: fl + raw(C3[i + 2]) * (1 - fl)};
  }

  /* Shrinking-core dissolution, mirroring the shader exactly. One definition each
     for the width slice and the fraction; gate 14 asserts they agree with Python.

     MEMOISED, and it matters more than it looks. The slice depends on psd.width
     alone, but fracOf() called it on every invocation, and fracOf() runs once per
     sampled cell in cdrOfRow() plus once per year in the cost screen's 10-year
     loop -- around 14 calls per cell across updateStability() and globalGt(). At
     ~45k sampled cells that was ~630k rebuilds of a 64-element Float32Array per
     refresh, which was the whole of a 1.4 s slider response. Nothing about the
     numbers changes: same table, same interpolation, computed once per width. */
  let gsCache = null, gsKey = NaN;
  function gSlice() {
    if (gsCache && gsKey === psd.width) return gsCache;
    const D = E.dissolution, ws = D.widthGrid;
    let j = 0;
    while (j < ws.length - 2 && psd.width > ws[j + 1]) j++;
    const f = clamp(0, (psd.width - ws[j]) / (ws[j + 1] - ws[j]), 1);
    const a = D.table[j], b = D.table[j + 1];
    gsCache = Float32Array.from(a, (v, i) => v + (b[i] - v) * f);
    gsKey = psd.width;
    return gsCache;
  }

  /* Mean-lifetime constant of the current grind: I_inf = integral(1 - Fw(u)) du
     over the same u grid as gSlice(). Renewal theory turns it into the footer's
     steady state: holding an inventory of one application, the sustainable
     application rate is u1/I_inf applications per year (capped at 1), because
     I_inf/u1 is the mean lifetime of applied rock. Integrated by trapezoid on
     the log-spaced grid, plus the below-grid sliver where 1 - Fw ~ 1. Memoised
     per width, like the slice itself. */
  let iInfCache = NaN, iInfKey = NaN;
  function iInfOf() {
    if (iInfKey === psd.width && !Number.isNaN(iInfCache)) return iInfCache;
    const D = E.dissolution, g = gSlice(), n = g.length;
    const step = (D.uLog.hi - D.uLog.lo) / (n - 1);
    let acc = Math.pow(10, D.uLog.lo) * (1 - g[0] / 2);
    let uPrev = Math.pow(10, D.uLog.lo);
    for (let i = 1; i < n; i++) {
      const u = Math.pow(10, D.uLog.lo + i * step);
      acc += (u - uPrev) * (1 - (g[i - 1] + g[i]) / 2);
      uPrev = u;
    }
    iInfCache = acc; iInfKey = psd.width;
    return acc;
  }

  /* Interpolate the slice at a given log10(u). Split out from fracOf() so the
     multi-year cost screen can hoist the logarithm: u scales linearly in t, so
     log10(u_t) = log10(u_1) + log10(t) and the ten years cost one log instead of
     ten. Exact arithmetic, not an approximation. */
  function fracAtLog10u(l10u, g, D) {
    if (!(l10u > -Infinity)) return 0;               // X <= 0, or NaN
    const t = (l10u - D.uLog.lo) / (D.uLog.hi - D.uLog.lo) * (g.length - 1);
    if (!(t > 0)) return 0;
    if (t >= g.length - 1) return g[g.length - 1];
    const i = t | 0;
    return g[i] + (g[i + 1] - g[i]) * (t - i);
  }

  function fracOf(X, years) {
    const D = E.dissolution, g = gSlice();
    const u = (D.deltaRefUm / psd.d50) * X * (years === undefined ? 1 : years);
    if (!(u > 0)) return 0;
    return fracAtLog10u(Math.log10(u), g, D);
  }

  /* tex2.b holds log10(ceiling / cdrPerFrac), so the arid tail keeps resolution.
     One definition, used by the hover readout and the stability sample. */
  function decodeCeil(byte) {
    const t = clamp(0, (byte - 5) / 250, 1);
    return Math.pow(10, FC.enc.lo + t * (FC.enc.hi - FC.enc.lo)) * E.cdrPerFrac;
  }

  /* Invert the cost value function to report $/t, so the readout shows the
     quantity people reason about rather than a unitless multiplier.

     v = 1 / (1 + (cost - gate)/S)  inverts in closed form to
     cost = gate + S (1/v - 1), which is exact rather than the piecewise
     back-interpolation the five-knot version needed. */
  function costUsdT(vBaked) {
    if (!E.cost) return null;
    // Takes the BAKED v from tex3.b, not a rescaled one. The baked haul is
    // r(region) * (road_km + 50 km of fixed trip time), linear in the rate,
    // so the multiplier applies to all of it. The gate is the LIVE value,
    // which is why it moves this number while never touching the shader.
    const v = clamp(E.cost.floor, vBaked, 1);
    return econ.gate + truckScale() * E.cost.haulScaleUsdT * (1 / v - 1);
  }

  function buildSliders() {
    const host = $("sliders");
    host.innerHTML = "";
    CRIT.forEach((c) => {
      const d = document.createElement("div");
      d.className = "slider";
      d.innerHTML =
        `<div class="row"><span class="name">${c.label}</span>` +
        `<span class="val" id="v-${c.key}"></span></div>` +
        `<input type="range" min="0" max="100" step="1" id="s-${c.key}">` +
        `<div class="why">${c.hint}</div>`;
      host.appendChild(d);
      const inp = d.querySelector("input");
      inp.value = Math.round(termExp[c.key] * 100);
      inp.addEventListener("input", () => {
        termExp[c.key] = +inp.value / 100;
        refresh();
      });
    });
  }

  function buildPsdSliders() {
    const P = E.psd;
    // d50 lives in the Feedstock grind group; the distribution-width slider is
    // an expert control and lives under Advanced. Full rationale for both, and
    // the roughness-multiplier check, is in Methods.
    const rows = [
      {k: "d50", host: "psd-sliders",
       label: "Grain size d50 (\u00b5m)",
       min: P.d50Range[0], max: P.d50Range[1], step: 5,
       why: `Half the rock mass is finer than this. 2026 field deliveries ` +
            `span ${P.deliveryRangeUm[0]}\u2013${P.deliveryRangeUm[1]} \u00b5m.`},
      {k: "width", host: "adv-psd-slider",
       label: "Grind distribution width",
       min: P.widthRange[0], max: P.widthRange[1], step: 0.05,
       why: "Rosin\u2013Rammler n: lower is a broader grind with more fines " +
            "and more reactive surface at the same d50."},
    ];
    rows.forEach((r) => {
      const d = document.createElement("div");
      d.className = "slider";
      d.innerHTML =
        `<div class="row"><span class="name">${r.label}</span>` +
        `<span class="val" id="pv-${r.k}"></span></div>` +
        `<input type="range" id="ps-${r.k}" min="${r.min}" max="${r.max}" step="${r.step}">` +
        `<div class="why">${r.why}</div>`;
      $(r.host).appendChild(d);
      const inp = d.querySelector("input");
      inp.value = psd[r.k];
      inp.addEventListener("input", () => { psd[r.k] = +inp.value; refresh(); });
    });
  }

  function syncPsd() {
    const P = E.psd;
    const d = $("pv-d50"), w = $("pv-width");
    if (d) d.textContent = psd.d50.toFixed(0) + " \u00b5m";
    if (w) w.textContent = psd.width.toFixed(2);
    const rel = Math.pow(10, ssaShift());
    const atRef = Math.abs(psd.d50 - P.refD50) < 2.5
                  && Math.abs(psd.width - P.refWidth) < 0.01;
    // At the reference itself, "1.00x faster weathering than the reference grind"
    // is a tautology dressed as a measurement. Both axes of the shift table now
    // pass exactly through the reference, so rel is exactly 1 here rather than the
    // 1.01 an interpolated grid used to give -- say so plainly instead.
    $("psd-readout").textContent = atRef
      ? "The reference grind, against which the other settings are compared"
      : (rel >= 1 ? rel.toFixed(2) + "\u00d7 faster" : (1 / rel).toFixed(2) + "\u00d7 slower")
        + " weathering than the reference grind";
    $("psd-tag").textContent = atRef ? "Reference" : "Custom";
  }

  function buildEconSliders() {
    if (!E.cost) { $("econ-group").classList.add("hidden"); return; }
    // A two-state toggle, not a continuous slider: there is no principled middle
    // value, and inventing one would be an unlabelled thumb on the scale.
    // Rendered by syncEcon() from the live slider values, not from the build
    // constants: the sliders under Advanced can move both, and a static caption
    // would then describe assumptions the map is no longer using.
    $("econ-sliders").innerHTML = `<p class="why" style="margin-top:10px" ` +
      `id="econ-basis"></p>`;
    document.querySelectorAll("#econ-seg .seg-btn").forEach((b) => {
      b.addEventListener("click", () => {
        econ.costExp = +b.dataset.econ ? E.cost.expOn : 0;
        refresh();
      });
    });
  }

  /* The two delivered-cost assumptions, under Advanced.

     They are deliberately NOT symmetric in effect, and the UI has to say so:

       rate multiplier  moves the map. It scales the regional per-km rates
                        baked into the texture, INCLUDING the fixed trip
                        charge, which is 50 km of driving priced at the
                        regional rate (haul = m*r(region)*(d + 50)). An
                        earlier version spared the fixed charge from the
                        multiplier; that confused time with cost -- trip time
                        is universal, its price follows the market level the
                        multiplier represents.
       gate cost        does NOT move the map. v = 1/(1 + (cost - gate)/S) is
                        independent of the gate by construction, so the colour
                        cannot change. It moves the reported $/t and $/tCO2,
                        and through the $/tCO2 screen the headline total.

     Without that caption the gate slider looks broken. */
  function buildEconAssumptionSliders() {
    const host = $("econ-assumption-sliders");
    if (!E.cost || !host) return;
    const gr = E.cost.gateRange || [0, 15];
    const tr = E.cost.truckMultRange || [0.25, 2.5];
    const rr = E.cost.truckRates || {};
    const rateList = Object.keys(rr)
      .map((k) => `${k} $${rr[k]}`).join(", ");
    const rows = [
      {k: "truckMult", label: "Haul rate \u00d7 regional baseline",
       min: tr[0], max: tr[1], step: 0.05,
       why: "Multiplies the regional per-km rates baked into the map (" +
            rateList + "; elsewhere $" + (E.cost.truckRateDefault || "?") +
            "), on great-circle distance \u00d7 " + E.cost.tortuosity +
            " tortuosity plus " + E.cost.haulFixedKm +
            " km of fixed trip time priced at the same rate " +
            "($2.25\u20135.50/t by region). Moves the map."},
      {k: "gate", label: "Quarry gate ($/t)",
       min: gr[0], max: gr[1], step: 0.5,
       why: "Rock at the quarry before haulage. The default is today\u2019s " +
            "byproduct-fines price; at scale, dedicated basalt runs " +
            "$15\u201322/t in the US and Europe (US traprock averages " +
            "$21.33/t, USGS 2023). Changes the reported cost and the " +
            "$/tCO\u2082 screen, but not the map colour \u2014 the cost " +
            "penalty applies to the haul increment only."},
    ];
    rows.forEach((r) => {
      const d = document.createElement("div");
      d.className = "slider";
      d.innerHTML =
        `<div class="row"><span class="name">${r.label}</span>` +
        `<span class="val" id="ev-${r.k}"></span></div>` +
        `<input type="range" id="es-${r.k}" min="${r.min}" max="${r.max}" ` +
        `step="${r.step}">` +
        `<div class="why">${r.why}</div>`;
      host.appendChild(d);
      const inp = d.querySelector("input");
      inp.value = econ[r.k];
      inp.addEventListener("input", () => { econ[r.k] = +inp.value; refresh(); });
    });
  }

  function syncEconAssumptions() {
    if (!E.cost || !$("ev-truckMult")) return;
    $("ev-truckMult").textContent = "\u00d7" + econ.truckMult.toFixed(2);
    $("ev-gate").textContent = "$" + econ.gate.toFixed(0);
    const k = truckScale();
    const ref = econAtRef();
    // At the reference, "1.00x the regional baselines" is a tautology dressed as
    // a measurement -- the same trap the grind readout documents. Say it plainly.
    $("econ-assumption-readout").textContent = ref
      ? "The build\u2019s own assumptions, against which the map was generated"
      : (Math.abs(k - 1) < 1e-9
          ? "Gate cost changed; reported cost moves, the map does not"
          : "Haul " + (k >= 1 ? k.toFixed(2) + "\u00d7 dearer" : (1 / k).toFixed(2)
             + "\u00d7 cheaper")
            + " than the regional baselines, fixed trip charge included");
  }

  function syncEcon() {
    if (!E.cost) return;
    const on = econ.costExp > 0;
    document.querySelectorAll("#econ-seg .seg-btn").forEach((b) =>
      b.classList.toggle("active", (+b.dataset.econ > 0) === on));
    $("econ-tag").textContent = on ? "On" : "Off";
    const basis = $("econ-basis");
    if (basis) {
      basis.innerHTML = `$${econ.gate.toFixed(0)}/t at the quarry gate, a ` +
        `fixed trip charge worth ${E.cost.haulFixedKm} km of driving, plus ` +
        `regional ` +
        `rates ($${E.cost.truckRates ? E.cost.truckRates["India/South Asia"] : "?"}` +
        `\u2013$${E.cost.truckRates ? E.cost.truckRates["Africa"] : "?"}/t-km; ` +
        `US $${E.cost.truckRates ? E.cost.truckRates["US/Canada"] : "?"}) from ` +
        `the nearest mafic quarry.` + (econAtRef() ? "" :
          ` <b>Adjusted from the build\u2019s $${E.cost.gateUsdT}/t gate and ` +
          `\u00d71.00 haul.</b>`);
    }
    // Two distinct effects, and the second is easy to miss: the toggle discounts
    // the MAP by cost, and it also restricts the headline TOTAL to cells under the
    // $/tCO2 screen. Say both.
    const scr = E.cost && E.cost.screenUsdPerTco2;
    $("econ-readout").textContent = on
      ? (scr ? `Total below restricted to cells under $${scr}/tCO\u2082, costed `
              + `against each application\u2019s discounted lifetime carbon at `
              + `${(E.cost.screenDiscount * 100).toFixed(0)}%. `
             : "")
        + "Hover the map for cost per tonne of rock and per tCO\u2082."
      : "Off: the map shows physical potential only, and the total below is "
        + "unrestricted.";
  }

  /* The drainage-limit control's caption. States what the bound is, that it is
     under review rather than settled, and where to watch its effect -- the footer
     total recomputes live, so the size of the change is shown rather than asserted
     here. No number is hardcoded in this text. */
  function syncFlux() {
    const om = FC.omega ?? "—";
    $("flux-hint").innerHTML = ceilOn
      ? `<b>On.</b> Gross CO₂ is capped at q·[HCO₃⁻]<sub>max</sub>·44 — `
        + `the carbon has to leave dissolved in the water that leaves, so it is `
        + `bounded by carbonate saturation (calcite Ω = ${om}) no matter how fast `
        + `the rock dissolves. <i>Fraction weathered</i> stays uncapped on purpose: `
        + `rock can dissolve without the carbon being exported. Watch the total below. `
        + `<b>This bound is out for review by the ERW community and is not a settled `
        + `part of the model</b> — see Methods.`
      : `<b>Off — the shipped default.</b> Nothing bounds the reported carbon by `
        + `the water available to carry it, so the CO₂ layer is an upper limit on `
        + `dissolution rather than carbon shown to leave the field. Turning this on `
        + `applies the drainage-concentration ceiling; it cuts the level several-fold `
        + `and changes which term limits most cropland. Held off pending outside `
        + `review — see Methods.`;
  }

  function syncSliders() {
    CRIT.forEach((c) => {
      const inp = $("s-" + c.key);
      if (inp) inp.value = Math.round(termExp[c.key] * 100);
      const lab = $("v-" + c.key);
      if (lab) {
        const e = termExp[c.key];
        lab.textContent = e.toFixed(2) + (Math.abs(e - 1) < 0.005 ? " (physics)" : "");
      }
    });
  }

  /* ---------------- readout ---------------- */
  function screenToCell(ev) {
    const c = $("gl"), r = c.getBoundingClientRect();
    const box = visibleBox();
    const fx = (ev.clientX - r.left) / r.width, fy = (ev.clientY - r.top) / r.height;
    const lon = box.lon0 + fx * box.lonSpan, lat = box.lat0 - fy * box.latSpan;
    const gx = Math.floor((lon - G.west) / G.dlon);
    const gy = Math.floor((G.north - lat) / G.dlat);
    if (gx < 0 || gy < 0 || gx >= G.width || gy >= G.height) return null;
    return { gx, gy, lon, lat, i: (gy * G.width + gx) * 4 };
  }

  let pinned = false;
  // Last cell drawn in the readout, so the box can be RE-rendered when a slider
  // changes the numbers without the mouse moving. Without this a pinned readout
  // silently went stale -- a latent bug that predates the drainage ceiling but
  // that the ceiling makes invisible, because "the number did not change" is
  // frequently the CORRECT answer once the cap binds, so a stale box and a
  // correct one look identical.
  let lastCell = null, lastPos = null;

  function onMove(ev) {
    if (pinned) return;
    lastPos = {clientX: ev.clientX, clientY: ev.clientY};
    lastCell = cpu ? screenToCell(ev) : null;
    renderReadout();
  }

  /* Re-render the readout for lastCell. Called by onMove and by refresh(). */
  function renderReadout() {
    const box = document.getElementById("readout");
    const cell = lastCell, ev = lastPos;
    if (!cell || !ev || !cpu) { box.classList.add("hidden"); return; }
    const B = cpu.B, i = cell.i;
    const flags = B[i + 1];
    if (!(flags & 1)) { box.classList.add("hidden"); return; }

    // No climate input: every downstream number would be an artefact of the
    // encoder's NaN fallback, so show none of them.
    if (flags & 4) {
      const rg = regionNameAt(i);
      box.innerHTML =
        `<div class="rt">${rg ? rg : `${cell.lat.toFixed(1)}°, ${cell.lon.toFixed(1)}°`}</div>` +
        `<div class="flag warn">No monthly soil temperature or moisture data here, ` +
        `so this cell was not evaluated. It is not a prediction of zero.</div>`;
      box.classList.remove("hidden");
      const wr = $("map-wrap").getBoundingClientRect();
      box.style.left = Math.min(ev.clientX - wr.left + 14, wr.width - 290) + "px";
      box.style.top = (ev.clientY - wr.top + 14) + "px";
      return;
    }

    const t = termsAt(i);
    const g = grossCdr(t.rel, t.eDic, t.eTr, t.ceil);
    const econOn = econ.costExp > 0;
    const score = suitabilityOf(g.cdr) * Math.pow(vCostLive(t.vCost), econ.costExp);
    // Limiting term = the largest negative contribution to log X -- unless the
    // drainage cannot carry the carbon at all, which outranks any of the three
    // because it is a bound rather than a rate.
    let lo = 0;
    for (let k = 1; k < 3; k++) if (g.contrib[k] < g.contrib[lo]) lo = k;
    const limLabel = g.ceilBinds ? CEIL_LABEL : CRIT[lo].label;

    const cdr = g.cdr;
    const pe = E.phEncoding;
    const soilPh = pe.lo + (cpu.C[i + 1] / 255) * (pe.hi - pe.lo);
    const cropList = cropsAt(i);
    const cropRest = cropList
      ? Math.max(0, 1 - cropList.reduce((a, c) => a + c.share, 0)) : 0;
    const usdT = costUsdT(t.vCost);

    let flagHtml = "";
    if (flags & 2) flagHtml += `<div class="flag bad">Excluded: soil organic carbon likely &gt; ${E.eligibility.socThreshold} wt%</div>`;
    if (flags & 8) flagHtml += `<div class="flag warn">Soil pH &lt; 5.2 — Isometric screens this at validation</div>`;

    const region = regionNameAt(i);
    box.innerHTML =
      `<div class="rt">${region ? region : `${cell.lat.toFixed(1)}°, ${cell.lon.toFixed(1)}°`}` +
      `${region ? `<span class="rt-ll"> · ${cell.lat.toFixed(1)}°, ${cell.lon.toFixed(1)}°</span>` : ""}</div>` +
      `<table>` +
      `<tr><td class="k">Suitability${econOn ? " (with cost)" : ""}</td><td class="v"><b>${(score * 100).toFixed(0)}</b></td></tr>` +
      `<tr><td class="k">Gross CO₂ removal</td><td class="v"><b>${cdr < 0.01 ? cdr.toExponential(1) : cdr.toFixed(2)}</b> tCO₂/ha/yr</td></tr>` +
      `<tr><td class="k">Weathered in year 1</td><td class="v">${(g.frac * 100).toFixed(1)}%</td></tr>` +
      // Shown only when it binds. LABEL THE QUANTITY THAT IS PRINTED: an earlier
      // version called this row "Drainage ceiling" while printing the UNCAPPED
      // figure, so it read as though the ceiling were the larger number and
      // contradicted the removal above it. When the cap binds the ceiling IS the
      // removal already shown, so the only new information is what dissolution
      // alone would have given. Units repeated, because that was the other half
      // of the confusion.
      (g.ceilBinds
        ? `<tr><td class="k">Without the drainage limit</td><td class="v">` +
          `${g.cdrUncapped < 0.01 ? g.cdrUncapped.toExponential(1) : g.cdrUncapped.toFixed(2)}` +
          ` tCO₂/ha/yr</td></tr>`
        : ``) +
      `<tr><td class="k">Limiting factor</td><td class="v">${limLabel}</td></tr>` +
      `<tr><td class="k">Soil pH (0–15 cm)</td><td class="v">${soilPh.toFixed(1)}</td></tr>` +
      // Context, not an input. The model reads crop identity nowhere except rice,
      // and then only through soil pCO2 -- so this sits below the physics rows
      // rather than among them. Two crops because one is a minority of the cell
      // more often than not: median dominant share 46%. "of cropped area" is
      // load-bearing wording, since SPAM's denominator is not the cropland
      // fraction used elsewhere in this box.
      (cropList
        ? `<tr><td class="k">Grown here</td><td class="v">` +
          cropList.map((c) => `${c.name} ${Math.round(c.share * 100)}%`).join(" · ") +
          // "rest", not "other": SPAM's own vocabulary already contains
          // "other cereals", "other oilcrops" and so on, and a row reading
          // "other oilcrops 41% · other 44%" makes the remainder look like
          // another crop category.
          (cropRest >= E.crops.minShare
            ? ` · rest ${Math.round(cropRest * 100)}%` : ``) +
          `</td></tr>`
        : ``) +
      (econOn && usdT !== null
        ? `<tr><td class="k">Delivered rock</td><td class="v">$${usdT.toFixed(0)}/t · $${(usdT / E.cost.tco2PerT).toFixed(0)}/tCO₂</td></tr>`
        : ``) +
      `</table>` +
      flagHtml +
      // Generated here rather than patched in by setPinned, because renderReadout
      // now also runs while pinned (on slider changes) and would overwrite it.
      `<div class="flag pin-hint">${pinned ? "Pinned — click or Esc to release"
                                           : "Click to pin"}</div>`;
    box.classList.remove("hidden");
    const wrap = $("map-wrap").getBoundingClientRect();
    let x = ev.clientX - wrap.left + 14, y = ev.clientY - wrap.top + 14;
    if (x + 280 > wrap.width) x = ev.clientX - wrap.left - 292;
    if (y + 210 > wrap.height) y = Math.max(6, ev.clientY - wrap.top - 220);
    box.style.left = x + "px"; box.style.top = y + "px";
  }

  /* ---------------- legend + stability ---------------- */
  function renderLegend() {
    const L = $("legend");
    if (mode === "limiting") {
      const rows = CRIT.map((c, i) =>
        `<div class="lrow"><span class="sw" style="background:${FACTOR_COLORS[i]}"></span>` +
        `<span class="lbl">${c.label}</span></div>`);
      // The ceiling is a bound, not a term, so it is listed last and only when
      // it is actually in force.
      if (ceilOn) rows.push(
        `<div class="lrow"><span class="sw" style="background:${FACTOR_COLORS[3]}"></span>` +
        `<span class="lbl">${CEIL_LABEL}</span></div>`);
      L.innerHTML = rows.join("") + eligRows();
      return;
    }
    const isFrac = mode === "frac";
    const stops = isFrac ? E.rampFrac : E.ramp;
    const grad = stops.map(([t, c]) => `${c} ${(t * 100).toFixed(0)}%`).join(", ");
    const obs = E.dissolvedFracObserved;
    L.innerHTML =
      `<div class="ramp" style="background:linear-gradient(90deg,${grad})"></div>` +
      `<div class="ends"><span>0</span>` +
      `<span>${isFrac ? "% weathered in year 1" : "suitability"}</span>` +
      `<span>${isFrac ? "&ge;&nbsp;" + ((E.fracRampMax || 1) * 100).toFixed(0) : "100"}</span></div>` +
      (isFrac
        ? `<p class="hint">Measured year-one weathering across the verified 2026
             deliveries spans <b>${(obs[0] * 100).toFixed(0)}–${(obs[1] * 100).toFixed(0)}%</b>.
             Moves with the grind setting.</p>`
        : `<p class="hint">Score &rarr; gross CO₂ removal: ` +
          E.cdrKnots.filter(([, y]) => y > 0)
            .map(([x, y]) => `${(y * 100).toFixed(0)}&nbsp;=&nbsp;${x}`).join(", ") +
          ` tCO₂/ha/yr at ${E.feedstock.rateTHaYr}&nbsp;t/ha applied.
          Gross removal, not net.</p>` +
          `<div class="lrow"><span class="sw" style="background:#292b30"></span>` +
          `<span class="lbl">Negligible: &lt; ${E.cdrNegligible} tCO₂/ha/yr</span></div>`) +
      eligRows();
  }

  function eligRows() {
    return `<div class="lrow" style="margin-top:9px"><span class="sw" style="background:#4d2929"></span>` +
      `<span class="lbl">Fails SOC &gt; ${E.eligibility.socThreshold} wt% screen</span></div>` +
      `<div class="lrow"><span class="sw" style="background:#6b7078"></span>` +
      `<span class="lbl">No climate input — not evaluated</span></div>`;
  }

  /* Fraction of cropland area whose decile moves away from the neutral default.
     Computed on an area-weighted decimated sample, per the sampling note in
     docs/METHODOLOGY.md — uniform sampling of a lat/lon grid over-samples high
     latitudes, which would bias this toward the boreal margin. */
  let sample = null;
  let lastKeptAreaFrac = 1;      // set by globalGt(); area surviving the cost screen
  function buildSample() {
    if (!cpu) return;
    const A = cpu.A, B = cpu.B, out = [];
    const step = 3;
    for (let gy = 0; gy < G.height; gy += step) {
      const lat = G.north - (gy + 0.5) * G.dlat;
      const wLat = Math.cos(lat * Math.PI / 180);      // area weight
      for (let gx = 0; gx < G.width; gx += step) {
        const i = (gy * G.width + gx) * 4;
        if (!(B[i + 1] & 1)) continue;
        const crop = B[i] / 255;
        if (crop < 0.01) continue;
        out.push([A[i], A[i + 1], A[i + 2], crop * wLat, cpu.C[i + 2], B[i + 2]]);
      }
    }
    sample = out;
  }

  const rawByte = (b) => clamp(0, (b - 5) / 250, 1);

  /* Gross CDR for one sampled cell. One definition, used by the suitability score,
     the decile edges and the global total in the footer, so those three can never
     disagree about what is being drawn. */
  function xOfRow(row, exps) {
    const rel = Math.pow(10, E.l1Enc.lo + rawByte(row[0]) * (E.l1Enc.hi - E.l1Enc.lo));
    return Math.exp(exps[0] * Math.log(Math.max(rel, 1e-12))
                  + exps[2] * Math.log(Math.max(rawByte(row[2]), 1e-12)));
  }
  const eDicOfRow = (row, exps) =>
    Math.pow(Math.max(rawByte(row[1]), 1e-12), exps[1]);

  function cdrOfRow(row, exps) {
    const X = xOfRow(row, exps), eDic = eDicOfRow(row, exps);
    let cdr = fracOf(X) * eDic * E.cdrPerFrac;
    // Same ceiling as the shader and the hover readout. Without it here the
    // stability metric and the decile edges would be computed on a different
    // model from the one being drawn.
    if (ceilOn && row[5] !== undefined) cdr = Math.min(cdr, decodeCeil(row[5]));
    return cdr;
  }

  function scoreOf(row, exps) {
    const fl = E.cost ? E.cost.floor : 1;
    const vc = fl + rawByte(row[4] === undefined ? 255 : row[4]) * (1 - fl);
    return suitabilityOf(cdrOfRow(row, exps))
           * Math.pow(vCostLive(vc), econ.costExp);
  }

  /* Global gross removal, GtCO2/yr, from the gridded data rather than a stored
     number: the area-weighted mean CDR over the decimated sample, scaled by total
     cropland area. It therefore MOVES with the grind and term sliders, which a
     stored figure could not. row[3] is crop x cos(lat), proportional to true cell
     area, so the weighted mean is unbiased. */
  function globalGt() {
    if (!sample || !sample.length) return null;
    const exps = [termExp.reactivity, termExp.eta_dic, termExp.drainage];
    // With the economics toggle ON the headline is restricted to cells whose
    // delivered feedstock and haul come in under the $/tCO2 screen. Per tonne of
    // CO2, not per tonne of rock: rock cost is nearly uncorrelated with CDR, so a
    // rock-cost screen barely discriminates, while this one rewards cells that
    // produce enough carbon to justify the haul.
    const screening = econ.costExp > 0 && E.cost && E.cost.screenUsdPerTco2;
    const rate = E.feedstock.rateTHaYr, fl = E.cost ? E.cost.floor : 1;
    // THE FOOTER IS ON A STEADY-STATE BASIS (Aug 2026), not year 1: hold a
    // standing inventory of one application (rate t/ha) of undissolved rock,
    // topping up as it dissolves. Renewal theory makes this exact from the same
    // cohort kinetics: the sustainable application rate is min(1, u1/I_inf)
    // applications per year (I_inf/u1 is the mean lifetime of applied rock),
    // and at steady state dissolved mass equals applied mass, so removal is
    // that rate x eta_DIC x carbon per tonne. Capped at one full application
    // per year; the drainage ceiling still bounds the flux. The map layers
    // stay on the year-1 basis -- that is the quantity field trials measure.
    const DR = (E.cost && E.cost.screenDiscount) || 0;
    // The cost screen is a per-application NPV, which is the marginal decision
    // an operator faces even at steady state: cost now against the
    // application's DISCOUNTED LIFETIME carbon -- extended (Aug 2026) from a
    // 10-year window to the application's whole weathering life, capped at
    // TMAX years, past which 5% discounting and the dissolved tail make the
    // increments negligible. Early-exits once the cohort is spent.
    const TMAX = 60;
    const D = E.dissolution, g = gSlice(), kU = D.deltaRefUm / psd.d50;
    const CPF = E.cdrPerFrac, iInf = iInfOf();
    const pow = new Float64Array(TMAX + 1), l10t = new Float64Array(TMAX + 1);
    for (let t = 1; t <= TMAX; t++) { pow[t] = Math.pow(1 + DR, t); l10t[t] = Math.log10(t); }
    let num = 0, den = 0, kept = 0;
    for (const r of sample) {
      const X = xOfRow(r, exps), eDic = eDicOfRow(r, exps);
      const u1 = kU * X;
      const l10u1 = X > 0 ? Math.log10(u1) : -Infinity;
      const ceil = (ceilOn && r[5] !== undefined) ? decodeCeil(r[5]) : Infinity;
      // Steady-state removal, capped at one application per year and at the
      // drainage ceiling.
      let cdr = Math.min(1, u1 / iInf) * eDic * CPF;
      if (!(cdr > 0)) cdr = 0;
      if (cdr > ceil) cdr = ceil;
      if (screening) {
        const usdT = costUsdT(fl + rawByte(r[4] === undefined ? 255 : r[4]) * (1 - fl));
        let tonnes = 0, prev = 0;
        for (let t = 1; t <= TMAX; t++) {
          const cum = fracAtLog10u(l10u1 + l10t[t], g, D);
          let yr = (cum - prev) * eDic * CPF;
          prev = cum;
          // The ceiling bounds EXPORT each year, so it must be applied per year
          // rather than to the total -- extra years buy much less under it.
          if (yr > ceil) yr = ceil;
          tonnes += yr / pow[t];
          if (cum > 0.9995) break;               // cohort spent
        }
        if (!(tonnes > 0) || usdT === null
            || usdT * rate / tonnes >= E.cost.screenUsdPerTco2) { den += r[3]; continue; }
        kept += r[3];
      }
      num += cdr * r[3]; den += r[3];
    }
    if (!(den > 0)) return null;
    lastKeptAreaFrac = screening ? kept / den : 1;
    // Scale by the EVALUATED area, not all cropland: the sample only covers cells
    // with a computable rate, and multiplying its mean by the full extent would
    // credit removal to the cells we declined to evaluate.
    const gha = E.stats.evaluatedGha ?? E.stats.croplandGha;
    return (num / den) * gha;                              // t/ha/yr x Gha -> Gt
  }

  /* Area-weighted decile edges from a precomputed score array, aligned with
     `sample`. Takes scores rather than exponents so the neutral baseline's scores
     can be computed once and reused by both the edges and the comparison loop.
     Sorts an Int32Array of indices instead of building 45k two-element arrays. */
  function edgesFrom(scores) {
    const n = scores.length;
    const idx = new Int32Array(n);
    for (let i = 0; i < n; i++) idx[i] = i;
    idx.sort((a, b) => scores[a] - scores[b]);
    let tot = 0;
    for (let i = 0; i < n; i++) tot += sample[i][3];
    const edges = []; let acc = 0, next = 1;
    for (let k = 0; k < n; k++) {
      acc += sample[idx[k]][3];
      while (next < 10 && acc / tot >= next / 10) { edges.push(scores[idx[k]]); next++; }
    }
    return edges;
  }

  function scoresFor(exps) {
    const out = new Float64Array(sample.length);
    for (let i = 0; i < sample.length; i++) out[i] = scoreOf(sample[i], exps);
    return out;
  }

  // The neutral baseline depends on the grind, the cost exponent, whether the
  // drainage ceiling is applied, and the two delivered-cost assumptions -- but NOT
  // on the term exponents, so its SCORES and its edges are cached and invalidated
  // on exactly those. The old code cached them and never invalidated, which is why
  // moving the grind slider produced spurious instability; the ceiling toggle was
  // then added to the key for the same reason, having been left out once already.
  // The truck rate belongs here because it moves every score. The GATE cost does
  // not move any score, but it is in the key anyway: it costs one string compare,
  // and the failure mode of omitting a setting from this key has now bitten twice.
  // Caching the scores as well as the edges is what lets updateStability() do one
  // pass.
  let baseScores = null, baseEdges = null, baseKey = null;
  function neutralBase() {
    const key = ssaShift().toFixed(6) + "|" + econ.costExp + "|" + (ceilOn ? 1 : 0)
              + "|" + econ.gate.toFixed(4) + "|" + econ.truckMult.toFixed(6);
    if (baseKey !== key || !baseScores) {
      baseScores = scoresFor(CRIT.map(() => 1));
      baseEdges = edgesFrom(baseScores);
      baseKey = key;
    }
    return {scores: baseScores, edges: baseEdges};
  }

  function updateStability() {
    if (!sample) return;
    const atDefault = CRIT.every((c) => Math.abs(termExp[c.key] - 1) < 1e-9);
    // AT THE DEFAULTS THE ANSWER IS ZERO BY CONSTRUCTION, so say so without
    // touching the sample. Both settings are then the same exponents digitised
    // against the same edges, so every cell lands in the same decile and `moved`
    // is exactly 0. Computing it anyway cost ~170 ms per slider event -- three
    // passes over 45k cells and a sort -- to rediscover an identity, which was the
    // bulk of the map's sluggishness on the grind and economics controls.
    if (atDefault) {
      $("stability").textContent = "At the physical defaults.";
      // Set the tag on this path too. The early return skipped it at first, which
      // left the summary reading "Down-weighted" after a Reset to physics.
      $("weight-tag").textContent = "Physics";
      return;
    }
    const nw = CRIT.map((c) => termExp[c.key]);
    // Each setting is digitised against ITS OWN area-weighted decile edges, so
    // this is a rank statistic: a monotone change (level shift, common exponent)
    // moves nothing, and only genuine re-ranking counts. An earlier version
    // compared both settings against the baseline's edges, which reported pure
    // level changes as instability -- a x2 level shift read as "85% moved".
    const base = neutralBase();
    const eN = base.edges, sN = base.scores;
    const sW = scoresFor(nw);
    const eW = edgesFrom(sW);
    const dec = (v, edges) => { let d = 0; while (d < edges.length && v >= edges[d]) d++; return d; };
    let moved = 0, tot = 0;
    for (let i = 0; i < sample.length; i++) {
      const w = sample[i][3];
      tot += w;
      if (dec(sN[i], eN) !== dec(sW[i], eW)) moved += w;
    }
    const pct = tot ? moved / tot : 0;
    $("stability").textContent =
      pct < 0.001
        ? "At the physical defaults."
        : `${(pct * 100).toFixed(0)}% of cropland area ranks in a different `
          + `decile than under the physical defaults.`;
    $("weight-tag").textContent = pct < 0.001 ? "Physics" : "Down-weighted";
  }

  /* ---------------- methods modal ---------------- */
  function methodsHTML() {
    const p = E.provenance;
    const obs = E.dissolvedFracObserved;
    const knots = E.cdrKnots.filter(([, y]) => y > 0)
      .map(([x, y]) => `${(y * 100).toFixed(0)} = ${x}`).join(", ");
    return `
      <h2>Methods, caveats &amp; sources</h2>
      <p class="hint">${E.labels.grid}, ${E.labels.effectiveRes}. Protocol screens
      <code>${E.eligibility.version}</code>.</p>

      <div class="flagbox"><p><b>This is a v0 preview.</b> The kinetics
      over-predict an independent laboratory test, one input is a stand-in, and
      the absolute CO₂ scale is uncertain to a factor of a few (see Known
      limitations). Treat the map as a relative ranking, not a site-level
      prediction.</p></div>

      <h3>What this map shows</h3>
      <p>For each ~11 km cell of the world's cropland, the map estimates how much
      CO₂ crushed basalt spread on that land could remove in its first year, from
      the physics of rock weathering: how fast the rock dissolves in that soil
      and climate, how much of the released alkalinity is stored as dissolved
      inorganic carbon, and whether drainage carries it out of the soil. The
      three layers are three views of the same calculation:
      <b>Suitability</b>, a 0–100 score of gross CO₂ removal;
      <b>Limiting factor</b>, the term that costs each cell the most; and
      <b>Weathered in year&nbsp;1</b>, the fraction of applied rock predicted to
      dissolve — the quantity field trials can measure.</p>
      <p>Read the limiting-factor layer with ${ceilOn ? "two caveats. First, " +
      "<b>&ldquo;drainage cannot carry it&rdquo; is a bound, not a term</b>: where " +
      "the drainage-concentration ceiling binds it outranks all three factors, " +
      "because no rate can push more carbon out than the water can hold. That is " +
      "most of the map. Second, among" : "one caveat. Among"} the three terms, the two
      efficiency terms have a natural zero (efficiency&nbsp;=&nbsp;1) but the
      dissolution term is measured against a reference condition (pH&nbsp;6.5,
      15&nbsp;°C), so the answer moves with that choice: a reference
      0.5&nbsp;pH units lower and 5&nbsp;°C warmer would make dissolution rank
      largest more often. It shows which term is furthest from its best case, not
      an absolute ranking of mechanisms.</p>
      <p>It is a screening map, not a site-selection tool: zoom is capped on
      purpose, and every CO₂ figure is gross removal. Two time bases coexist:
      the <b>map layers and hover readout are year-1</b> (the quantity field
      trials can measure), while the <b>footer total is a steady state</b> —
      hold ${E.feedstock.rateTHaYr} t/ha of undissolved rock on each field,
      reapplying as the modelled kinetics dissolve it, capped at one full
      application per year. Fast tropical cells run at the cap; slow cool cells
      reapply every decade or two. The two bases nearly coincide globally
      (within ~7%) but differ regionally with weathering speed.
      ${ceilOn
        ? "Carbonate saturation enters only as an upper bound on what the drainage " +
          "can carry, not as a modelled precipitation loss; cation retention in the " +
          "soil, riverine re-release and strong-acid competition are all still " +
          "outstanding."
        : "Nothing downstream of dissolution is deducted: not the drainage limit " +
          "(computed, but switched off — see Known limitations), not cation " +
          "retention in the soil, not riverine re-release, and not strong-acid " +
          "competition."}</p>

      <h3>How it is computed</h3>
      <ol>
      <li><b>Dissolution rate.</b> The Palandri &amp; Kharaka (2004,
      USGS OFR 2004-1068) three-mechanism rate law for basalt, driven by soil pH
      (SoilGrids, 0–15 cm) and monthly soil temperature (Lembrechts et al. 2022,
      5–15 cm), moisture-limited by the degree of soil-water saturation — a
      TerraClimate extractable-storage climatology divided through SoilGrids
      field capacity, wilting point and pore volume over 0–100 cm. The
      rate is computed month by month and then averaged, because weathering needs
      warm and wet at the same time. (An index first-order in hydrogen-ion
      activity, as in Cascade, is close to a rescaled soil-pH map; the
      three-mechanism law compresses that pH leverage by more than two orders of
      magnitude.)</li>
      <li><b>Reactive surface area.</b> A Rosin–Rammler particle-size
      distribution from the grind controls (reference d50 ${E.psd.refD50} µm,
      width ${E.psd.refWidth}). Geometric area, not BET; rate is linear in
      surface area.</li>
      <li><b>Alkalinity retained as DIC.</b> The carbonate-equilibrium efficiency
      of Bertagni &amp; Porporato (2022), with zero free parameters. Fast
      dissolution in very acid soil stores little carbon; this term is why. Soil
      pCO₂ is raised in rice paddies, mapped as Landsat inundation months ×
      SPAM irrigated-rice area.</li>
      <li><b>Drainage.</b> η = q/(q + D_w) on ${E.provenance.drainage}
      (Maher &amp; Chamberlain 2014; D_w = ${p.dw ? p.dw.value : "?"} m/yr):
      bicarbonate has to leave the field in the drainage water to count as
      exported. Total runoff rather than groundwater recharge, because recharge
      is zero in river deltas where the water table is at the surface and
      drainage leaves laterally.</li>
      <li><b>Gross CO₂ removal.</b> The product of the terms sets how far each
      particle's surface retreats, and a shrinking-core integral over the
      grain-size distribution turns that into the fraction of rock dissolved in
      year one — so the fine tail is spent early and coarse grains persist.
      Anchored so the reference case sits at the median of verified field
      deliveries
      (${(obs[0] * 100).toFixed(0)}–${(obs[1] * 100).toFixed(0)}% weathered).
      At ${E.feedstock.rateTHaYr} t/ha of basalt holding
      ${E.feedstock.tco2PerT} tCO₂/t, that fraction becomes tCO₂/ha/yr.</li>
      <li><b>Suitability.</b> A piecewise-linear score of gross CO₂ removal —
      ${knots} tCO₂/ha/yr — so zero removal scores zero by construction. The
      Advanced exponents lower one term at a time to test how much of the map
      depends on trusting it; they are not importance weights, because the terms
      are not substitutable.</li>
      <li><b>Delivered cost (optional).</b> $${E.cost.gateUsdT}/t at the quarry
      gate, plus trucking at regional rates on road distance <i>plus
      ${E.cost.haulFixedKm} km</i> — the fixed trip time (the hauler's loading,
      tipping and positioning, ~$2.25–5.50/t by region; the quarry's own loading
      service is already inside the f.o.b. gate price) \u2014
      ${Object.entries(E.cost.truckRates || {}).map(([k, v]) => `${k} $${v}`)
        .join(", ")}, elsewhere $${E.cost.truckRateDefault}/t-km
      (sources and vintages in docs/TRUCK_RATE_SOURCES.md; only the US rate is
      current) \u2014 over
      ${E.cost.tortuosity}× great-circle distance to the nearest mafic-hosted
      quarry (US MRDS, Brazil ANM, OSM). Where no quarry inventory is usable,
      distance to mafic outcrop (GLiM) is scaled by ${E.cost.outcropToQuarry}×,
      the quarry-to-outcrop ratio measured where both are known. The discount
      applies to the haul increment only — every site must buy and crush rock, so
      the gate cost carries no spatial information — and it never zeroes a cell
      with real physical potential. Truck only, not network-routed.</li>
      <li><b>Protocol screen.</b> Cells whose soil organic carbon likely exceeds
      ${E.eligibility.socThreshold} wt% (exceedance probability &gt;
      ${E.eligibility.pExcluded} on SoilGrids quantiles; the Puro.earth and
      Isometric exclusion) are drawn dark red. Only
      ${(E.eligibility.excludedShareCropland * 100).toFixed(2)}% of cropland is
      confidently excluded — high-SOC soils are a peatland and boreal phenomenon,
      not a farmland one.</li>
      </ol>

      <h3>Key assumptions</h3>
      <table>
        <tr><th>Assumption</th><th>Value</th></tr>
        <tr><td>Application rate</td><td>${E.feedstock.rateTHaYr} t/ha/yr</td></tr>
        <tr><td>Feedstock</td><td>delivered basalt, ${E.feedstock.tco2PerT} tCO₂/t
          (anchored to verified deliveries)</td></tr>
        <tr><td>Reference grind</td><td>d50 ${E.psd.refD50} µm, width
          ${E.psd.refWidth} (width assumed; narrow for a commercial crush)</td></tr>
        <tr><td>Year-1 dissolved fraction at reference</td>
          <td>${(E.dissolvedFracAtRef * 100).toFixed(0)}%, anchored to verified
          deliveries (${(obs[0] * 100).toFixed(0)}–${(obs[1] * 100).toFixed(0)}%)</td></tr>
        <tr><td>Quarry gate cost</td><td>$${E.cost.gateUsdT}/t, from
          operator-reported quarry-fines prices — today's byproduct deals, not
          an at-scale price (US traprock averages $21.33/t, USGS 2023; see
          docs/GATE_COST_AT_SCALE.md)</td></tr>
        <tr><td>Trucking</td><td>regional $/t-km (US
          $${E.cost.truckRates ? E.cost.truckRates["US/Canada"] : "?"}, Brazil
          $${E.cost.truckRates ? E.cost.truckRates["Brazil/Latin America"] : "?"},
          India $${E.cost.truckRates ? E.cost.truckRates["India/South Asia"] : "?"})
          on road km + ${E.cost.haulFixedKm} km fixed-trip equivalent, ×
          ${E.cost.tortuosity} road tortuosity</td></tr>
        <tr><td>D_w (transport limitation)</td><td>${p.dw ? p.dw.value : "?"} m/yr
          (published range ${p.dw ? p.dw.range.join("–") : "?"})</td></tr>
        <tr><td>Drainage ceiling, calcite Ω${ceilOn ? "" : " (not applied)"}</td><td>${FC.omega ?? "—"}
          (strict case ${FC.omegaStrict ?? "—"}; precipitation is negligible below
          Ω&nbsp;≈&nbsp;10, so the shipped value is the generous one)</td></tr>
        <tr><td>Ca share of divalent charge</td><td>${FC.fCa ?? "—"}
          (only Ca constrains calcite; a lower share raises the ceiling)</td></tr>
      </table>

      <h3>Known limitations</h3>
      <div class="flagbox"><p><b>Weathered cations do not all leave the soil, and
      the map does not model the ones that stay.</b> Field measurements find
      <b>10–50× more base cations retained</b> in exchange sites, iron and
      manganese oxide pools and neoformed clays than are exported in leachate
      (Hammes et al. 2025), with retarded fractions of 93–98% (te Pas et al.
      2025). This map reports the export that would occur at steady state with no
      lag, so the CO₂ figures are still likely high — by a factor of roughly 2–4
      against the trials that have measured drainage chemistry directly. Modelled
      export lag times reach 5–22 years (Kanzaki et al. 2025). This is the largest
      missing term and it is blocked on data, not effort.</p></div>
      ${ceilOn ? `<p><b>The carbon is bounded by the water that carries it.</b>
      Gross CO₂ removal is capped at what the drainage can hold as bicarbonate
      without carbonate precipitating — around ${FC.medianTco2HaYr ? FC.medianTco2HaYr.toFixed(2) : "0.22"}
      tCO₂/ha/yr at the median cell. The cap binds on
      <b>${FC.bindsAreaFrac ? (FC.bindsAreaFrac * 100).toFixed(0) : "97"}% of
      cropland</b>, and where it binds the dissolution rate, mineral mix, grind
      <i>and application rate</i> no longer change the answer. Spreading more rock
      than the drainage can carry the carbon from raises the share of the map that
      is transport-limited rather than raising the tonnage. At
      ${E.feedstock.rateTHaYr}&nbsp;t/ha the median cell realises just
      ${FC.realisedShareOfStoich ? (FC.realisedShareOfStoich * 100).toFixed(1) : "—"}%
      of the feedstock's stoichiometric CO₂ potential as exported carbon.</p>`
      : `<div class="flagbox"><p><b>A drainage limit on the carbon is computed but
      deliberately NOT applied, pending review by the wider ERW community.</b> The
      carbon reported here has to leave the field dissolved in the water that leaves
      the field, which bounds it at roughly
      ${FC.medianTco2HaYr ? FC.medianTco2HaYr.toFixed(2) : "0.22"} tCO₂/ha/yr at the
      median cell. Every figure on this map is above that bound — on
      <b>${FC.bindsAreaFrac ? (FC.bindsAreaFrac * 100).toFixed(0) : "99"}% of
      cropland</b>, by a median factor of about
      ${FC.exceedMedian ? FC.exceedMedian.toFixed(0) : "5"}× — so the CO₂ layer
      should be read as an upper bound on dissolution, not as carbon that can be
      shown to leave. The bound is implemented, gated and documented; it is switched
      off only because it moves the map's absolute level by several-fold and that is
      worth outside scrutiny before it ships. See the changelog for the analysis and
      how to re-enable it.</p></div>`}
      <p><b>The kinetics over-predict an independent laboratory test.</b> Against
      Gudbrandsson et al. (2011) crystalline-basalt dissolution (pH 2–11,
      5–75 °C), the Ca+Mg charge sum the map actually uses over-predicts by
      about <b>+1.2 log units</b> on the shipped mineral weighting — worse than
      the per-element figures (Ca +0.5, Mg +1.6) suggest. The bias grows with
      temperature: the apparent activation energy here (62–69 kJ/mol) is roughly
      2× the measured ~${E.kinetics.measuredEaKJ} kJ/mol
      (${E.kinetics.measuredEaRange[0]}–${E.kinetics.measuredEaRange[1]} across
      pH), and Schaef &amp; McGrail (2009) measure 30 kJ/mol on Columbia River
      basalt from an independent laboratory; Cascade's ${E.kinetics.cascadeEaKJ}
      has the same problem, so it is wrong for a reason we share. This inflates
      the tropics-versus-temperate contrast by roughly 2×.
      ${ceilOn
        ? "It no longer propagates to the CO₂ layer over most of the map, though: " +
          "the drainage ceiling above binds first and does not reward warmth, so the " +
          "tropical tilt now shows up in &ldquo;weathered in year 1&rdquo; rather " +
          "than in the tonnage."
        : "With the drainage limit switched off it propagates in full to the CO₂ " +
          "layer, so the warm-climate advantage this map shows is roughly 2× too " +
          "strong on the kinetics alone, before the drainage bound is even " +
          "considered."}</p>
      <p><b>The mineral mix is olivine-dominated.</b> Forsterite is 12% of the
      modelled rock by volume but supplies 80% of its base-cation release, so the
      map's pH and temperature response is closer to olivine's than to basalt's.
      Independently, the archetypes' mineral modes imply up to 2× their stated
      MgO, which is a second line of evidence for the same problem. Both are
      recorded rather than retuned, because the fix is a modelling decision that
      needs its own review.</p>
      <p><b>Surface area sets the absolute scale and is uncertain by orders of
      magnitude.</b> Geometric and BET areas differ by 130–670× at ERW grain
      sizes. The roughness multiplier λ (about
      ${Math.round(E.psd.betMeasured / E.psd.refSsa)} to match a measured
      ${E.psd.betMeasured} m²/g BET) is reported as a plausibility
      <i>diagnostic</i> only — it does not enter the calculation, because the map
      works in rate <i>ratios</i> and a constant multiplier cancels. What does set
      the level is the dissolved-fraction anchor, calibrated to field-reported
      year-one weathering.</p>
      <p><b>Gross, not net.</b> In-soil carbonate precipitation, riverine
      re-release and strong-acid competition plausibly claim 20–80% of gross
      removal, and the gap is spatially variable. Nothing here is validated
      against net measured removal.</p>
      <p><b>The aridity contrast depends on a term that is off.</b> With the
      drainage limit applied, gross removal spans ~125&times; from the wettest to
      the driest 5% of cropland, close to the 141&times; contrast in the drainage
      data. Without it — the default — the span is ~10&times;. The larger figure
      is the defensible one.</p>
      <p><b>Irrigation is half-visible.</b> Drainage includes irrigation return
      flow; the soil-water balance behind the moisture term does not. On irrigated
      land the two disagree about how wet the field is.</p>
      <p><b>Cropland is herbaceous-only.</b> The mask reproduces Potapov et al.
      (2022) to 0.1%, but excludes perennial woody crops, temporary meadows and
      long fallow (~0.36 Gha vs FAOSTAT). Woody crops are protocol-eligible and a
      live deployment setting, so addressable area is understated, mostly in the
      tropics.</p>
      <p><b>Quarry inventories are uneven.</b> MRDS is reliable mainly for the
      US and static since 2011; mining titles (Brazil) and crowd-sourced points
      overstate producing quarries. Haul distance is great-circle × tortuosity,
      not road-routed.</p>
      <p><b>The haul rates are benchmarked, not calibrated.</b> Trucking is
      priced with regional rates (only the US entry is current — USDA grain-truck
      rates; Brazil, China and Europe rest on 2007 World Bank corridor prices
      inflated by US CPI, India on a 2021 national average) plus a fixed trip
      charge of ${E.cost ? E.cost.haulFixedKm : 50} km-equivalent priced at the
      regional rate. Nothing validates
      the resulting cost surface against real delivered costs, and haul distance
      is modelled, not routed. The rate multiplier and gate cost are sliders
      under Advanced so the dependence is visible rather than buried; sources and
      vintages are in docs/TRUCK_RATE_SOURCES.md.</p>
      <p><b>Screening probabilities are not calibrated.</b> SoilGrids quantiles
      describe ~250 m block averages, not sampled fields, so field-scale
      threshold exceedance is understated; the SOC screen is a screening
      likelihood, not an eligibility probability.</p>

      <h3>Sources</h3>
      <table>
        <tr><th>Layer</th><th>Source</th></tr>
        <tr><td>Soil pH, SOC + quantiles</td><td>${p.soil}</td></tr>
        <tr><td>Climate</td><td>${p.climate}</td></tr>
        <tr><td>Cropland</td><td>${p.cropland}</td></tr>
        <tr><td>Drainage</td><td>${p.drainage || "—"}</td></tr>
        <tr><td>Rice paddy</td><td>${p.paddy || "—"}</td></tr>
        <tr><td>Feedstock supply</td><td>${p.feedstock || "—"}</td></tr>
        <tr><td>Kinetics</td><td>Palandri &amp; Kharaka 2004, USGS OFR 2004-1068</td></tr>
        <tr><td>Carbonate system</td><td>Plummer &amp; Busenberg 1982, GCA 46, 1011</td></tr>
        <tr><td>Efficiency term</td><td>Bertagni &amp; Porporato 2022, STE 838, 156524</td></tr>
        <tr><td>Transport limitation</td><td>Maher &amp; Chamberlain 2014, Science 343, 1502</td></tr>
        <tr><td>Kinetics test</td><td>Gudbrandsson et al. 2011, GCA 75</td></tr>
        <tr><td>Eligibility</td><td>Puro.earth ERW Edition 2025 v2 (approved
          Mar 2026); Isometric EW-in-agriculture v1.2</td></tr>
        <tr><td>Coastlines</td><td>Natural Earth 110m (public domain)</td></tr>
        <tr><td>Region names</td><td>Natural Earth 10m admin-1 (public domain)</td></tr>
      </table>
      <p>Code MIT; each dataset keeps its own licence. The full development
      history — what changed between preview builds, the defects found on the
      way, and why each call was made — is in the
      <a class="ext" href="https://github.com/hausfath/erw-map/blob/main/CHANGELOG.md"
      target="_blank" rel="noopener">changelog on GitHub</a>.</p>`;
  }

  /* ---------------- wiring ---------------- */
  /* Footer headline. Recomputed on every refresh so it tracks the sliders. */
  function updateHeadline() {
    const gt = globalGt();
    $("stat-main").textContent = gt === null ? "—" : gt.toFixed(2) + " GtCO\u2082/yr";
    // Computed live from the gridded data so it tracks the sliders, which means it
    // reads the 8-bit textures and a 1-in-3 decimation: about 0.5% above the exact
    // area-weighted total the build prints. Said here rather than papered over.
    $("stat-main").title = gt === null ? "" :
      "Steady state maintaining a standing rock inventory, reapplication paced " +
      "by the modeled dissolution and capped at one application per year -- not " +
      "the year-1 basis the map layers use. Area-weighted over " +
      (E.stats.evaluatedGha ?? E.stats.croplandGha).toFixed(2) +
      " Gha of evaluated cropland, recomputed from the grid at the current " +
      "settings; sampled 1 cell in 3 from 8-bit textures.";
    const gha = (E.stats.evaluatedGha ?? E.stats.croplandGha) * lastKeptAreaFrac;
    const scr = econ.costExp > 0 && E.cost && E.cost.screenUsdPerTco2;
    $("stat-label").textContent = gt === null
      ? "cropland in scope"
      : (scr
          ? `steady-state gross removal holding ${E.feedstock.rateTHaYr} t/ha of `
            + `rock, where delivered rock costs under `
            + `$${E.cost.screenUsdPerTco2}/tCO\u2082 against each application\u2019s `
            + `lifetime carbon at ${(E.cost.screenDiscount * 100).toFixed(0)}%, `
            + `on ${gha.toFixed(2)} Gha`
          : `steady-state gross removal holding ${E.feedstock.rateTHaYr} t/ha of `
            + `rock, over ${gha.toFixed(2)} Gha of cropland`)
        + (ceilOn ? "" : ", drainage limit not applied");
  }

  /* The two whole-sample statistics -- the stability sentence and the footer total
     -- are the only expensive things in a refresh. The map itself draws in ~4 ms,
     so they are debounced off the input path rather than run inline: dragging a
     slider now redraws every frame and the two numbers settle once, shortly after
     you stop. The delay is short enough to read as instant for a single click and
     long enough that a drag never queues a second pass.

     They are NOT approximations and nothing about them changes -- this is purely
     when they run. flushStats() runs them synchronously, which is what the first
     paint uses so the footer never shows its placeholder on load. */
  const STATS_DEBOUNCE_MS = 80;
  let statsTimer = null;
  function flushStats() {
    if (statsTimer !== null) { clearTimeout(statsTimer); statsTimer = null; }
    updateStability();
    updateHeadline();
  }
  function scheduleStats() {
    if (statsTimer !== null) clearTimeout(statsTimer);
    statsTimer = setTimeout(() => { statsTimer = null; flushStats(); }, STATS_DEBOUNCE_MS);
  }

  function refresh() {
    syncSliders(); syncPsd(); syncEconAssumptions(); syncEcon(); renderLegend();
    draw();
    // Keep the readout consistent with what is drawn. A pinned box in particular
    // has no mousemove to bring it up to date. Cheap, so it stays inline.
    renderReadout();
    scheduleStats();
  }

  function setMode(m) {
    mode = m;
    document.querySelectorAll("#mode-seg .seg-btn").forEach((b) =>
      b.classList.toggle("active", b.dataset.mode === m));
    $("mode-hint").textContent = MODE_HINT[m];
    // Grind and term sensitivity both feed the dissolution product, so they act
    // on the fraction-weathered layer too. Economics does not: fraction weathered
    // is a physical prediction, and discounting it by haul cost would be a
    // category error.
    //
    // Advanced itself now stays open in every mode, and only the TERM-EXPONENT
    // block is mode-specific. The drainage limit lives in Advanced and has to be
    // reachable from the limiting-factor layer above all -- that layer gives the
    // ceiling its own colour when it binds, so hiding the switch would hide the
    // control for a class the legend is showing. The distribution-width slider
    // comes along, which is right: grind feeds `frac`, so it moves what binds.
    $("term-sensitivity").classList.toggle("hidden", m === "limiting");
    $("psd-group").classList.toggle("hidden", false);
    $("econ-group").classList.toggle("hidden", m !== "score" || !E.cost);
    refresh();
  }

  function attachPanZoom() {
    const c = $("gl");
    let drag = null;
    const setPinned = (p) => {
      pinned = p;
      const box = $("readout");
      box.classList.toggle("pinned", p);
      const hint = box.querySelector(".pin-hint");
      if (hint) hint.textContent = p ? "Pinned — click or Esc to release" : "Click to pin";
    };
    c.addEventListener("mousedown", (e) => {
      drag = { x: e.clientX, y: e.clientY, lon: view.lon, lat: view.lat };
      c.style.cursor = "grabbing";
    });
    window.addEventListener("mouseup", (e) => {
      // A press that barely moved is a click: toggle the readout pin so the
      // numbers can be read, compared, or screenshotted without chasing them.
      if (drag && Math.hypot(e.clientX - drag.x, e.clientY - drag.y) < 5) {
        if (pinned) { setPinned(false); onMove(e); }
        else if (!$("readout").classList.contains("hidden")) setPinned(true);
      }
      drag = null; c.style.cursor = "crosshair";
    });
    window.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && pinned) { setPinned(false); $("readout").classList.add("hidden"); }
    });
    window.addEventListener("mousemove", (e) => {
      if (!drag) { return; }
      // Mouse deltas are CSS pixels, so the scale must be too. Using the
      // device-pixel scale made dragging move at half speed on retina.
      const d = visibleBox().degPerPxCss;
      view.lon = drag.lon - (e.clientX - drag.x) * d;
      view.lat = drag.lat + (e.clientY - drag.y) * d;
      clampView();
      draw();
    });
    c.addEventListener("mousemove", onMove);
    c.addEventListener("mouseleave", () => {
      // Drop lastCell as well, or a later refresh() would resurrect a box the
      // pointer has already left.
      if (!pinned) { lastCell = null; $("readout").classList.add("hidden"); }
    });
    // The zoom-cap notice only appears when a zoom-in is actually refused at
    // the ceiling — the moment it answers a real question. Shown persistently
    // (as it once was) it covered ~90% of the usable zoom range.
    const ZOOM_MAX = 40;
    let capTimer = null;
    const zoomBy = (f) => {
      const z = clamp(1, view.zoom * f, ZOOM_MAX);
      if (f > 1 && z === view.zoom && z >= ZOOM_MAX) {
        const el = $("zoomcap");
        el.classList.remove("hidden");
        clearTimeout(capTimer);
        capTimer = setTimeout(() => el.classList.add("hidden"), 2200);
      }
      view.zoom = z; clampView(); draw();
    };
    c.addEventListener("wheel", (e) => {
      e.preventDefault();
      zoomBy(e.deltaY < 0 ? 1.15 : 1 / 1.15);
    }, { passive: false });
    $("zin").onclick = () => zoomBy(1.4);
    $("zout").onclick = () => zoomBy(1 / 1.4);
    $("zreset").onclick = () => {
      view.lon = 10; view.lat = DATA.latMid; view.zoom = 1; clampView(); draw();
    };
    window.addEventListener("resize", draw);
  }

  async function main() {
    $("res-label").textContent =
      `${E.labels.build} · ${E.labels.grid} · ${E.labels.effectiveRes}`;
    updateHeadline();
    const nq = (window.QUARRIES && window.QUARRIES.points.length) || 0;
    const bySrc = {};
    if (nq) window.QUARRIES.points.forEach((p) => {
      bySrc[p[2]] = (bySrc[p[2]] || 0) + 1;
    });
    const SRC_NAME = {MRDS: "US MRDS", ANM: "Brazil ANM", OSM: "OSM"};
    $("quarry-hint").innerHTML = nq
      ? `${nq.toLocaleString()} mafic-hosted quarries (` +
        Object.entries(bySrc).map(([k, v]) =>
          `<span style="color:${{MRDS: "#e8734a", ANM: "#4ad2a8",
            OSM: "#c9a227"}[k] || "#999"}">\u25cf</span> ${SRC_NAME[k] || k} ` +
          `${v.toLocaleString()}`).join(", ") + `).`
      : "No quarry inventory built. Run scripts/fetch_quarries.py.";
    $("attrib").textContent =
      "SoilGrids · WorldClim · Potapov et al. cropland · Natural Earth";
    $("zoomcap").textContent = `Zoom capped — the data is a ${E.labels.grid}`;
    $("method-body").innerHTML = methodsHTML();

    initGL();
    texRamp = makeRampTexture(E.ramp, gl.TEXTURE3);
    texRampFrac = makeRampTexture(E.rampFrac, gl.TEXTURE4);
    const [a, b, cTex, , dTex] = await Promise.all([
      loadTexture("textures/tex1.png", 0), loadTexture("textures/tex2.png", 1),
      loadTexture("textures/tex3.png", 2), loadAdminIds(),
      loadTexture("textures/tex4.png", 5), loadCropMix(),
    ]);
    texA = a.tex; texB = b.tex; texC = cTex.tex; texD = dTex.tex;
    cpu = decodeToCPU(a.bmp, b.bmp, cTex.bmp);
    $("loading").remove();
    buildSample();

    buildSliders();
    buildPsdSliders();
    buildEconSliders();
    buildEconAssumptionSliders();
    attachPanZoom();
    document.querySelectorAll("#mode-seg .seg-btn").forEach((btn) =>
      btn.addEventListener("click", () => setMode(btn.dataset.mode)));
    const cq = $("chk-quarries");
    if (window.QUARRIES && window.QUARRIES.points.length) {
      cq.addEventListener("change", (e) => {
        showQuarries = e.target.checked; refresh();
      });
    } else {
      cq.disabled = true;
    }
    // Mafic outcrop. Deliberately separate from the quarry overlay: quarries are
    // a real but very unevenly complete inventory (three national registers and
    // OSM), so outside those countries the absence of a dot says nothing. Outcrop
    // is global and answers "is there mafic rock near here at all".
    $("chk-mafic").addEventListener("change", (e) => {
      showMafic = e.target.checked; refresh();
    });
    $("mafic-hint").innerHTML =
      `<span style="color:#8c7a63">\u25a0</span> GLiM mafic and ultramafic ` +
      `outcrop, drawn on and off cropland. Where quarry coverage is thin this is ` +
      `the better guide to whether feedstock is nearby \u2014 but outcrop is not ` +
      `a quarry, and says nothing about whether the rock is permitted, crushed ` +
      `or for sale.`;
    // Drainage limit. The bound is shipped in the texture whether or not it is
    // applied, so this is a real switch rather than a request for a rebuild. It is
    // an Advanced control on purpose: it moves the absolute level several-fold and
    // it is the one term in the model that is out for external review.
    const fx = $("chk-flux");
    fx.checked = ceilOn;
    fx.addEventListener("change", (e) => {
      ceilOn = e.target.checked;
      // The Methods panel's text is ceiling-conditional and is built once at load,
      // so it has to be regenerated or it describes the other setting.
      $("method-body").innerHTML = methodsHTML();
      syncFlux();
      refresh();
    });
    syncFlux();

    $("btn-reset").onclick = () => {
      CRIT.forEach((c) => { termExp[c.key] = 1; }); refresh();
    };
    $("btn-psd-reset").onclick = () => {
      psd.d50 = E.psd.refD50; psd.width = E.psd.refWidth;
      $("ps-d50").value = psd.d50; $("ps-width").value = psd.width;
      refresh();
    };
    $("btn-econ-reset").onclick = () => {
      if (!E.cost) return;
      econ.gate = E.cost.gateUsdT; econ.truckMult = 1;
      $("es-gate").value = econ.gate; $("es-truckMult").value = econ.truckMult;
      refresh();
    };
    $("open-method").onclick = () => $("method-modal").classList.remove("hidden");
    $("method-close").onclick = () => $("method-modal").classList.add("hidden");
    $("method-modal").addEventListener("click", (e) => {
      if (e.target.id === "method-modal") $("method-modal").classList.add("hidden");
    });

    clampView();
    setMode("score");
    // First paint takes the statistics synchronously: the debounce exists to keep a
    // DRAG smooth, and on load there is nothing to keep smooth. Letting the timer
    // handle it would show the footer's placeholder for 80 ms on every visit.
    flushStats();
  }

  main().catch((err) => {
    document.getElementById("map-wrap").innerHTML =
      `<div style="padding:40px;color:#d9534f;font:14px system-ui">` +
      `<b>Could not start.</b><br>${err.message}<br><br>` +
      `<span style="color:#9fb0c0">Serve over HTTP, not file:// — ` +
      `<code>python3 -m http.server 8000 --directory src</code></span></div>`;
    console.error(err);
  });
})();
