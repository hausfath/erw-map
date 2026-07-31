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
    score: "A value function of gross CO₂ removal, on absolute breakpoints in " +
           "tCO₂/ha/yr. Zero removal is zero suitability by construction.",
    limiting: "Which of the three physical terms costs the most at each cell — " +
              "the largest negative contribution to the log of the product.",
    cascade: "Cascade Climate's published form, r ∝ s·[H⁺]·exp(−Ea/RT), on the " +
             "same inputs. Shown so the comparison is testable, not asserted.",
  };
  const FACTOR_COLORS = ["#e0704f", "#4f9fe0", "#8fd14f"];

  let gl, prog, quad, texA, texB, texC, texRamp, cpu = null;
  let mode = "score";
  let showElig = true;
  // Term exponents, NOT importance weights. Default 1 means the composite is
  // exactly the physical product, so gross CDR -- and hence suitability -- is
  // zero wherever any required term is zero.
  const termExp = {reactivity: 1, eta_dic: 1, drainage: 1};
  const K_DISS = -Math.log(1 - E.dissolvedFracAtRef);
  // Economic weight. A real preference, not a what-if: cost genuinely trades off
  // against physical potential in a way the physical terms do not trade off
  // against each other.
  const econ = {costExp: E.cost ? E.cost.expDefault : 0};
  const CRIT = E.terms;

  // Data extent, from the generated grid constants.
  const DATA = {
    north: G.north, south: G.north - G.height * G.dlat,
    get latSpan() { return this.north - this.south; },
    get latMid() { return (this.north + this.south) / 2; },
  };
  // Particle size. Held separately from the weights because it is a physical
  // assumption about the feedstock, not a preference about what matters.
  const psd = { d80: E.psd.refD80, width: E.psd.refWidth };

  /* Bilinear lookup into the precomputed log10(SSA/SSA_ref) table. Precomputed
     in Python so the browser needs no gamma function and cannot disagree with
     the pipeline about the integral. */
  function ssaShift() {
    const P = E.psd, gx = P.d80Grid, gy = P.widthGrid, T = P.shiftTable;
    const f = (arr, v) => {
      if (v <= arr[0]) return [0, 0];
      if (v >= arr[arr.length - 1]) return [arr.length - 2, 1];
      let i = 0; while (i < arr.length - 2 && v > arr[i + 1]) i++;
      return [i, (v - arr[i]) / (arr[i + 1] - arr[i])];
    };
    const [i, fi] = f(gx, psd.d80), [j, fj] = f(gy, psd.width);
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

  function hex2rgb(h) {
    return [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16),
            parseInt(h.slice(5, 7), 16)];
  }
  function rampColorAt(t) {
    const r = E.ramp;
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
  const rampCss = (t) => "rgb(" + rampColorAt(t).join(",") + ")";

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

  uniform sampler2D uA, uB, uC, uRamp;
  uniform vec4 uGeo;              // lon0, lat0, lonSpan, latSpan of the visible box
  uniform vec4 uGrid;             // west, north, dlon, dlat of the data grid
  uniform vec2 uGridSize;
  uniform vec3 uExp;              // term exponents; 1,1,1 == the physics
  uniform int  uMode;             // 0 suitability, 1 limiting, 2 cascade
  uniform bool uElig;
  uniform vec2 uL1Enc;            // lo, hi of the stored L1 range
  uniform float uSsaShift;        // log10(SSA(d80,width) / SSA(ref))
  uniform float uKdiss;           // -ln(1 - dissolved fraction at reference)
  uniform float uCdrPerFrac;      // tCO2/ha/yr per unit dissolved fraction
  uniform float uNegligible;      // CDR below this is "no meaningful potential"
  uniform float uCx[6], uCy[6];   // suitability knots, x in log10(tCO2/ha/yr)
  uniform float uCostExp;         // exponent on the compensatory cost multiplier
  uniform float uCostFloor;

  const vec4 OUT_OF_DOMAIN = vec4(0.0, 0.0, 0.0, 0.0);
  const vec4 NEGLIGIBLE    = vec4(0.16, 0.17, 0.19, 1.0);

  vec3 factorColor(int i) {
    if (i == 0) return vec3(0.878, 0.439, 0.310);
    if (i == 1) return vec3(0.310, 0.624, 0.878);
    return vec3(0.561, 0.820, 0.310);
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

    int flags = int(b.g * 255.0 + 0.5);
    if ((flags & 1) == 0) { fragColor = OUT_OF_DOMAIN; return; }

    if (uElig && (flags & 2) != 0) {          // fails the SOC screen outright
      fragColor = vec4(0.30, 0.16, 0.16, 1.0);
      return;
    }

    if (uMode == 2) {                          // Cascade baseline, own channel
      vec3 cb = texture(uRamp, vec2(clamp(cc.r, 0.0, 1.0), 0.5)).rgb;
      fragColor = vec4(cb, 1.0);
      return;
    }

    // Dequantise the RAW physical terms. Value 0 is reserved for masked cells,
    // so data occupies 5..255 -- and a decoded zero is a true zero, which
    // matters because zero really does mean no carbon.
    float l1  = mix(uL1Enc.x, uL1Enc.y, clamp((a.r * 255.0 - 5.0) / 250.0, 0.0, 1.0))
                + uSsaShift;
    float rel = pow(10.0, l1);                          // R / R_ref
    float eDic = clamp((a.g * 255.0 - 5.0) / 250.0, 0.0, 1.0);
    float eTr  = clamp((a.b * 255.0 - 5.0) / 250.0, 0.0, 1.0);

    // Terms in a PHYSICAL PRODUCT, with unit exponents by default. No carbon is
    // stored unless all three are non-zero, so a compensatory mean would be
    // wrong in kind: it let good alkalinity retention offset zero reactivity.
    float lr = uExp.x * log(max(rel,  1e-12));
    float ld = uExp.y * log(max(eDic, 1e-12));
    float lt = uExp.z * log(max(eTr,  1e-12));

    if (uMode == 1) {                          // which term costs the most here
      int lo = (lr <= ld && lr <= lt) ? 0 : ((ld <= lt) ? 1 : 2);
      fragColor = vec4(factorColor(lo), 1.0);
      return;
    }

    // Gross CDR, then suitability as a value function OF THAT. Zero CDR gives
    // zero suitability by construction rather than by tuning a floor.
    float X = exp(lr + ld + lt);
    float frac = 1.0 - exp(-uKdiss * X);       // saturates at 1, no flat top
    float cdr = frac * uCdrPerFrac * pow(10.0, uSsaShift);

    if (cdr < uNegligible) { fragColor = NEGLIGIBLE; return; }

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
    float vCost = uCostFloor
                + clamp((cc.b * 255.0 - 5.0) / 250.0, 0.0, 1.0) * (1.0 - uCostFloor);
    sc *= pow(vCost, uCostExp);

    vec3 col = texture(uRamp, vec2(clamp(sc, 0.0, 1.0), 0.5)).rgb;

    // Marginal eligibility: a hatch, never a colour blend. A blend would make a
    // marginal cell read as a slightly-worse good cell.
    if (uElig && (flags & 4) != 0) {
      float d = mod(gl_FragCoord.x + gl_FragCoord.y, 14.0);
      if (d < 2.0) col = mix(col, vec3(0.910, 0.702, 0.224), 0.45);
    }
    fragColor = vec4(col, 1.0);
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

  function makeRampTexture() {
    // Built from the SAME array the legend reads, so they cannot disagree.
    const n = 256, px = new Uint8Array(n * 4);
    for (let i = 0; i < n; i++) {
      const c = rampColorAt(i / (n - 1));
      px[i * 4] = c[0]; px[i * 4 + 1] = c[1]; px[i * 4 + 2] = c[2]; px[i * 4 + 3] = 255;
    }
    const t = gl.createTexture();
    gl.activeTexture(gl.TEXTURE3);
    gl.bindTexture(gl.TEXTURE_2D, t);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8, n, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, px);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    return t;
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
    gl.uniform1i(u("uElig"), showElig ? 1 : 0);
    gl.uniform2f(u("uL1Enc"), E.l1Enc.lo, E.l1Enc.hi);
    gl.uniform1f(u("uSsaShift"), ssaShift());
    gl.uniform1f(u("uKdiss"), K_DISS);
    gl.uniform1f(u("uCdrPerFrac"), E.cdrPerFrac);
    gl.uniform1f(u("uNegligible"), E.cdrNegligible);
    gl.uniform1fv(u("uCx"), new Float32Array(E.cdrKnots.map(k => Math.log10(k[0]))));
    gl.uniform1fv(u("uCy"), new Float32Array(E.cdrKnots.map(k => k[1])));
    gl.uniform1f(u("uCostExp"), econ.costExp);
    gl.uniform1f(u("uCostFloor"), E.cost ? E.cost.floor : 1.0);
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, texA);
    gl.uniform1i(u("uA"), 0);
    gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, texB);
    gl.uniform1i(u("uB"), 1);
    gl.activeTexture(gl.TEXTURE2); gl.bindTexture(gl.TEXTURE_2D, texC);
    gl.uniform1i(u("uC"), 2);
    gl.activeTexture(gl.TEXTURE3); gl.bindTexture(gl.TEXTURE_2D, texRamp);
    gl.uniform1i(u("uRamp"), 3);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);

    drawLand(box);
    $("zoomcap").classList.toggle("hidden", box.degPerPx > G.dlon * 0.9);
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
  function grossCdr(rel, eDic, eTr) {
    const lr = termExp.reactivity * Math.log(Math.max(rel, 1e-12));
    const ld = termExp.eta_dic * Math.log(Math.max(eDic, 1e-12));
    const lt = termExp.drainage * Math.log(Math.max(eTr, 1e-12));
    const X = Math.exp(lr + ld + lt);
    const frac = 1 - Math.exp(-K_DISS * X);
    return {cdr: frac * E.cdrPerFrac * Math.pow(10, ssaShift()),
            frac, contrib: [lr, ld, lt]};
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
    const A = cpu.A, C3 = cpu.C;
    const raw = (b) => clamp(0, (b - 5) / 250, 1);
    const l1 = E.l1Enc.lo + raw(A[i]) * (E.l1Enc.hi - E.l1Enc.lo) + ssaShift();
    const fl = E.cost ? E.cost.floor : 1;
    return {rel: Math.pow(10, l1), l1, eDic: raw(A[i + 1]), eTr: raw(A[i + 2]),
            vCost: fl + raw(C3[i + 2]) * (1 - fl)};
  }

  /* Invert the cost value function to report $/t, so the readout shows the
     quantity people actually reason about rather than a unitless multiplier. */
  function costUsdT(vCost) {
    if (!E.cost) return null;
    const K = E.cost.knots;
    for (let i = 0; i < K.length - 1; i++) {
      const [x0, y0] = K[i], [x1, y1] = K[i + 1];
      if (vCost <= y0 && vCost >= y1) {
        return x0 + (x1 - x0) * (y0 - vCost) / (y0 - y1 || 1);
      }
    }
    return vCost >= K[0][1] ? K[0][0] : K[K.length - 1][0];
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
    const P = E.psd, host = $("psd-sliders");
    const rows = [
      {k: "d80", label: "d80 \u2014 80% of mass is finer", unit: " \u00b5m",
       min: P.d80Range[0], max: P.d80Range[1], step: 1,
       why: `Verified 2026 deliveries span ${P.deliveryRangeUm[0]}\u2013${P.deliveryRangeUm[1]} \u00b5m. ` +
            `Reference ${P.refD80} \u00b5m is the Corn Belt trial.`},
      {k: "width", label: "Distribution width", unit: "",
       min: P.widthRange[0], max: P.widthRange[1], step: 0.05,
       why: "Rosin\u2013Rammler n: low is a broad grind with more fines. " +
            "This is the DOMINANT unknown here \u2014 across this range it moves " +
            "surface area 7.7\u00d7 at fixed d80. " +
            (P.refWidthAssumed
              ? "The default is ASSUMED, and narrow for a commercial crush, so it " +
                "probably understates reactive surface."
              : "")},
    ];
    host.innerHTML = "";
    rows.forEach((r) => {
      const d = document.createElement("div");
      d.className = "slider";
      d.innerHTML =
        `<div class="row"><span class="name">${r.label}</span>` +
        `<span class="val" id="pv-${r.k}"></span></div>` +
        `<input type="range" id="ps-${r.k}" min="${r.min}" max="${r.max}" step="${r.step}">` +
        `<div class="why">${r.why}</div>`;
      host.appendChild(d);
      const inp = d.querySelector("input");
      inp.value = psd[r.k];
      inp.addEventListener("input", () => { psd[r.k] = +inp.value; refresh(); });
    });
  }

  function syncPsd() {
    const P = E.psd;
    const d = $("pv-d80"), w = $("pv-width");
    if (d) d.textContent = psd.d80.toFixed(0) + " \u00b5m";
    if (w) w.textContent = psd.width.toFixed(2);
    const ssa = ssaNow();
    const rel = Math.pow(10, ssaShift());
    // Show the implied roughness multiplier that a BET-scale area would demand.
    // If a fit ever needs lambda far outside 1-100 the model is being asked
    // something unphysical -- that is a falsification bound, not a knob.
    // lambda is now reported against a MEASURED BET, not an assumed 1-5 m2/g
    // range. The old readout implied lambda 39-197 at the reference grind, which
    // straddled the falsification ceiling and made our own default look
    // unphysical -- an artefact of the unsourced anchor, not of the model.
    const lamNeeded = P.betMeasured / ssa;
    const inBounds = lamNeeded >= P.lambdaRange[0] && lamNeeded <= P.lambdaRange[1];
    $("psd-readout").innerHTML =
      `geometric SSA ${ssa.toFixed(4)} m\u00b2/g &nbsp;\u00b7&nbsp; ` +
      `${rel >= 1 ? rel.toFixed(2) + "\u00d7 faster" : (1 / rel).toFixed(2) + "\u00d7 slower"} ` +
      `than reference<br>` +
      `<span style="opacity:.75">to match the measured ${P.betMeasured} m\u00b2/g BET of a ` +
      `real crushed basalt, roughness \u03bb \u2248 <b>${lamNeeded.toFixed(0)}</b> ` +
      `(bound ${P.lambdaRange[0]}\u2013${P.lambdaRange[1]}${inBounds ? "" : ", OUT OF BOUNDS"}). ` +
      `Their fines were sieved out, so a real crush at this d80 would need less.</span>`;
    const atRef = Math.abs(psd.d80 - P.refD80) < 0.5
                  && Math.abs(psd.width - P.refWidth) < 0.01;
    $("psd-tag").textContent = atRef ? "Reference" : "Custom";
  }

  function buildEconSliders() {
    if (!E.cost) { $("econ-group").classList.add("hidden"); return; }
    const host = $("econ-sliders");
    host.innerHTML =
      `<div class="slider"><div class="row">` +
      `<span class="name">Weight on delivered cost</span>` +
      `<span class="val" id="v-costexp"></span></div>` +
      `<input type="range" id="s-costexp" min="0" max="150" step="5">` +
      `<div class="why">0 ignores cost entirely; 1.00 applies it in full. ` +
      `Gate $${E.cost.gateUsdT}/t, truck $${E.cost.truckUsdTKm}/t-km, ` +
      `rail $${E.cost.railUsdTKm}/t-km plus $${E.cost.railTransloadUsdT}/t ` +
      `transload. Great-circle distance, not routed.</div></div>`;
    const inp = $("s-costexp");
    inp.value = Math.round(econ.costExp * 100);
    inp.addEventListener("input", () => {
      econ.costExp = +inp.value / 100; refresh();
    });
  }

  function syncEcon() {
    if (!E.cost) return;
    const inp = $("s-costexp");
    if (inp) inp.value = Math.round(econ.costExp * 100);
    const lab = $("v-costexp");
    if (lab) lab.textContent = econ.costExp.toFixed(2);
    $("econ-tag").textContent = econ.costExp === 0 ? "Ignored"
      : (Math.abs(econ.costExp - E.cost.expDefault) < 0.005 ? "Full" : "Custom");
    $("econ-readout").innerHTML =
      `Where the quarry inventory is unusable, outcrop distance is scaled by ` +
      `${E.cost.outcropToQuarry}\u00d7 to approximate quarry distance \u2014 a ratio ` +
      `<i>measured</i> inside the trusted inventory area, not assumed.`;
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

  function onMove(ev) {
    const box = document.getElementById("readout");
    const cell = cpu ? screenToCell(ev) : null;
    if (!cell) { box.classList.add("hidden"); return; }
    const A = cpu.A, B = cpu.B, i = cell.i;
    const flags = B[i + 1];
    if (!(flags & 1)) { box.classList.add("hidden"); return; }

    const t = termsAt(i);
    const g = grossCdr(t.rel, t.eDic, t.eTr);
    const scorePhys = suitabilityOf(g.cdr);
    const score = scorePhys * Math.pow(t.vCost, econ.costExp);
    // Limiting term = the largest negative contribution to log X.
    let lo = 0;
    for (let k = 1; k < 3; k++) if (g.contrib[k] < g.contrib[lo]) lo = k;

    const cropPct = (B[i] / 255 * 100);
    const cdr = g.cdr;
    const pe = E.phEncoding;
    const soilPh = pe.lo + (cpu.C[i + 1] / 255) * (pe.hi - pe.lo);

    let flagHtml = "";
    if (flags & 2) flagHtml += `<div class="flag bad">Fails the SOC &gt; ${E.eligibility.socThreshold} wt% screen (P &gt; ${E.eligibility.pExcluded})</div>`;
    else if (flags & 4) flagHtml += `<div class="flag warn">Marginal on the SOC screen — cannot be cleared or excluded from these data</div>`;
    if (flags & 8) flagHtml += `<div class="flag warn">Soil pH &lt; 5.2: Isometric screens pH at validation (annotation only, no score effect)</div>`;

    box.innerHTML =
      `<div class="rt">${cell.lat.toFixed(1)}°, ${cell.lon.toFixed(1)}°</div>` +
      `<table>` +
      `<tr><td class="k">Dissolution rate, R/R_ref</td><td class="v">${t.rel < 0.01 ? t.rel.toExponential(1) : t.rel.toFixed(2)}×</td></tr>` +
      `<tr><td class="k">Alkalinity retained</td><td class="v">${t.eDic.toFixed(3)}</td></tr>` +
      `<tr><td class="k">Drainage / transport</td><td class="v">${t.eTr.toFixed(3)}</td></tr>` +
      `<tr><td class="k">Dissolved this year</td><td class="v">${(g.frac * 100).toFixed(1)}%</td></tr>` +
      `<tr><td class="k"><b>Gross CO₂</b></td><td class="v"><b>${cdr < 0.01 ? cdr.toExponential(1) : cdr.toFixed(2)}</b></td></tr>` +
      `<tr><td class="k">Delivered feedstock</td><td class="v">$${(costUsdT(t.vCost) || 0).toFixed(0)}/t</td></tr>` +
      `<tr><td class="k">Suitability, physics</td><td class="v">${(scorePhys * 100).toFixed(0)}</td></tr>` +
      `<tr><td class="k"><b>Suitability, with cost</b></td><td class="v"><b>${(score * 100).toFixed(0)}</b></td></tr>` +
      `<tr><td class="k">Limiting term</td><td class="v">${CRIT[lo].label}</td></tr>` +
      `<tr><td class="k">Soil pH (0–15 cm)</td><td class="v">${soilPh.toFixed(2)}</td></tr>` +
      `<tr><td class="k">Cropland</td><td class="v">${cropPct.toFixed(0)}%</td></tr>` +
      `</table>` +
      `<div class="flag">Suitability is a value function OF gross CO₂ ` +
      `(tCO₂ gross/ha/yr at ${E.feedstock.rateTHaYr} t/ha), so zero removal is ` +
      `zero suitability. Gross, not net; low confidence.</div>` +
      flagHtml;
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
      L.innerHTML = CRIT.map((c, i) =>
        `<div class="lrow"><span class="sw" style="background:${FACTOR_COLORS[i]}"></span>` +
        `<span class="lbl">${c.label}</span></div>`).join("") + eligRows();
      return;
    }
    const grad = E.ramp.map(([t, c]) => `${c} ${(t * 100).toFixed(0)}%`).join(", ");
    const isCascade = mode === "cascade";
    L.innerHTML =
      `<div class="ramp" style="background:linear-gradient(90deg,${grad})"></div>` +
      `<div class="ends"><span>${isCascade ? "low" : "0"}</span>` +
      `<span>${isCascade ? "relative reactivity" : "suitability"}</span>` +
      `<span>${isCascade ? "high" : "100"}</span></div>` +
      (isCascade ? "" :
        `<p class="hint">Anchored to gross CO₂: ` +
        E.cdrKnots.map(([x, y]) => `${(y * 100).toFixed(0)}&nbsp;=&nbsp;${x}`).join(", ") +
        ` tCO₂ gross/ha/yr at ${E.feedstock.rateTHaYr}&nbsp;t/ha.</p>` +
        `<div class="lrow"><span class="sw" style="background:#292b30"></span>` +
        `<span class="lbl">Negligible: &lt; ${E.cdrNegligible} tCO₂/ha/yr</span></div>`) +
      (isCascade
        ? `<p class="hint">Cascade's index spans ~4 orders of magnitude, so most
             cropland sits near the bottom of any linear ramp. That flatness is
             the point of the comparison, not a rendering fault.</p>`
        : "") +
      eligRows();
  }

  function eligRows() {
    if (!showElig) return "";
    return `<div class="lrow" style="margin-top:9px"><span class="sw" style="background:#4d2929"></span>` +
      `<span class="lbl">Excluded: SOC &gt; ${E.eligibility.socThreshold} wt%</span></div>` +
      `<div class="lrow"><span class="sw hatchsw"></span>` +
      `<span class="lbl">Marginal — cannot be cleared</span></div>`;
  }

  /* Fraction of cropland area whose decile moves away from the neutral default.
     Computed on an area-weighted decimated sample, per the sampling note in
     docs/METHODOLOGY.md — uniform sampling of a lat/lon grid over-samples high
     latitudes, which would bias this toward the boreal margin. */
  let sample = null;
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
        out.push([A[i], A[i + 1], A[i + 2], crop * wLat, cpu.C[i + 2]]);
      }
    }
    sample = out;
  }

  function scoreOf(row, exps) {
    const raw = (b) => clamp(0, (b - 5) / 250, 1);
    const rel = Math.pow(10, E.l1Enc.lo + raw(row[0]) * (E.l1Enc.hi - E.l1Enc.lo)
                             + ssaShift());
    const X = Math.exp(exps[0] * Math.log(Math.max(rel, 1e-12))
                     + exps[1] * Math.log(Math.max(raw(row[1]), 1e-12))
                     + exps[2] * Math.log(Math.max(raw(row[2]), 1e-12)));
    const cdr = (1 - Math.exp(-K_DISS * X)) * E.cdrPerFrac
                * Math.pow(10, ssaShift());
    const fl = E.cost ? E.cost.floor : 1;
    const vc = fl + raw(row[4] === undefined ? 255 : row[4]) * (1 - fl);
    return suitabilityOf(cdr) * Math.pow(vc, econ.costExp);
  }

  function deciles(nw) {
    const rows = sample.map((r) => [scoreOf(r, nw), r[3]]).sort((a, b) => a[0] - b[0]);
    const tot = rows.reduce((a, r) => a + r[1], 0);
    const edges = []; let acc = 0, next = 1;
    for (const r of rows) {
      acc += r[1];
      while (next < 10 && acc / tot >= next / 10) { edges.push(r[0]); next++; }
    }
    return { rows, edges };
  }

  let baseDec = null;
  function updateStability() {
    if (!sample) return;
    const neutral = CRIT.map(() => 1);
    if (!baseDec) baseDec = deciles(neutral);
    const nw = CRIT.map((c) => termExp[c.key]);
    const dec = (v, edges) => { let d = 0; while (d < edges.length && v >= edges[d]) d++; return d; };
    let moved = 0, tot = 0;
    for (const r of sample) {
      const a = dec(scoreOf(r, neutral), baseDec.edges);
      const b = dec(scoreOf(r, nw), baseDec.edges);
      tot += r[3];
      if (a !== b) moved += r[3];
    }
    const pct = tot ? moved / tot : 0;
    $("stability").textContent =
      pct < 0.001
        ? "At unit exponents, i.e. the physical product. Lower a term to see how "
          + "much of the map depends on trusting it."
        : `${(pct * 100).toFixed(1)}% of cropland area changes decile vs the `
          + `unweighted physical product.`;
    $("weight-tag").textContent = pct < 0.001 ? "Physics" : "Down-weighted";
  }

  /* ---------------- methods modal ---------------- */
  function methodsHTML() {
    const p = E.provenance;
    return `
      <h2>Methods, caveats &amp; sources</h2>
      <p class="hint">${E.labels.grid}, ${E.labels.effectiveRes}. Version
      <code>${E.eligibility.version}</code>.</p>

      <div class="flagbox"><p><b>This is a v0 preview.</b> The physics core is
      built and gated, but four inputs are stand-ins and one whole dimension —
      feedstock supply and delivered haul cost — is not built yet. Read the
      substitutions below before drawing any conclusion from the map.</p></div>

      <h3>What this does differently from Cascade</h3>
      <p><b>Three-mechanism kinetics.</b> Cascade's index is first order in
      hydrogen-ion activity, which spans 10⁴ across cropland pH 4–8 while its
      temperature term spans only ~20× across 0–30 °C — so it is close to a
      rescaled soil-pH map. Using the three-parallel-mechanism law of Palandri
      &amp; Kharaka (2004, USGS OFR 2004-1068) compresses that to ~36×. Measured:
      Cascade overstates pH leverage by 281×.</p>
      <p><b>An alkalinity-to-DIC efficiency term.</b> Fast dissolution at low pH
      does not store carbon, because DIC speciation shifts toward aqueous CO₂.
      Cascade cites Bertagni &amp; Porporato (2022) as the source of its
      framework; that paper is <i>The Carbon-Capture Efficiency of Natural Water
      Alkalinization</i> and it derives precisely the term the index omits. Added
      here with zero free parameters, it reproduces the protocols' own screening
      thresholds: half efficiency falls at pH 5.08 at Isometric's mandated
      4,000 µatm soil pCO₂, against their 5.20 screen.</p>
      <p><b>Protocol eligibility as a mapped layer,</b> in three states rather
      than two, from exceedance probabilities on SoilGrids quantiles.</p>

      <h3>The independent kinetics test, and what it found</h3>
      <div class="flagbox"><p><b>This test fails, and it is the most important open
      problem in the model.</b> It also caught us conceding something to Cascade
      that the data does not support.</p></div>
      <p>Gudbrandsson et al. (2011) measured crystalline-basalt release rates across
      pH 2–11 and 5–75 °C. That isolates the rate law in a way the field trials
      cannot, since grain size and loss terms there absorb any error.</p>
      <p>Against the pre-registered 0.5 log-unit tolerance, our Palandri–Kharaka
      mixture <b>over-predicts</b>: Ca by +0.5 log units, Mg by +0.8 to +1.6. The
      residuals are structured, not noisy, in two separate ways.</p>
      <p><b>By temperature</b>, the bias grows from +0.01 at 5 °C to +1.58 at 75 °C.
      That is an activation-energy error. Gudbrandsson measure an apparent Ea for
      whole-rock basalt of <b>~36 kJ/mol</b> (24–54 across pH). Our mixture gives
      46–63, and Cascade uses 68.8. <b>We previously called Cascade's 68.8 "a
      reasonable number reached by an unclear route" — that concession was wrong.</b>
      It is roughly 2× too high, and so is ours.</p>
      <p>This matters geographically, because temperature sensitivity is what drives
      the tropical tilt. At 36 kJ/mol a soil 20 °C warmer is 2.7× faster; at 68 it
      is 6.7×. <b>The tropics-versus-temperate contrast is about 2.5× smaller than
      either formulation implies.</b></p>
      <p><b>By pH</b>, Mg over-prediction peaks at pH 4–8 (+1.4 to +2.1) and nearly
      vanishes below 4 and above 8 — the signature of secondary Mg/Fe phases
      precipitating near neutral pH, where they are least soluble, removing Mg from
      the solution the experiment measures.</p>
      <p><b>Why an independent test was necessary.</b> The CO₂ layer sits ~2.3×
      <i>below</i> field observations while the kinetics over-predict lab rates by
      3–7×. Those pull opposite ways, so the surface-area multiplier has been
      quietly absorbing a kinetics error. Comparing against field trials alone
      could never have shown that. Neither problem is corrected in the default
      model: recorded rather than silently retuned, because the fix is a modelling
      decision that needs its own review.</p>

      <h3>Remaining stand-ins</h3>
      <ul>${p.substitutions.map((s) => `<li>${s}</li>`).join("")}</ul>
      <p>These mean the temperature and moisture terms are still <i>Cascade's own
      inputs</i>, so the "Cascade baseline" comparison is like-for-like, but our
      claim to a soil-temperature improvement is not yet realised. Planned:
      Lembrechts et al. (2022) monthly soil temperature at 30 arc-second, and a
      monthly soil-moisture climatology.</p>

      <h3>Suitability is now anchored to gross CO₂</h3>
      <p><b>The defect.</b> Suitability used to be a weighted geometric mean of
      value-function transforms of the same three physical terms that make up CO₂
      removal, with a uniform 0.02 quantisation floor applied as though it were a
      physical floor. The consequence: a cell with <i>zero</i> reactivity — hence
      zero carbon removed — scored <code>exp(ln 0.02 / 3) × 100 = 27</code>, not 0.
      The floor existed to stop 8-bit quantisation swinging the score; it should
      never have manufactured suitability where the physics says none. 3.5% of
      cropland area was affected.</p>
      <p><b>The fix.</b> Suitability is now a value function <i>of</i> gross CO₂
      removal, on absolute breakpoints in tCO₂/ha/yr, so zero removal is zero
      suitability by construction rather than by tuning a floor. That also removed
      three sets of arbitrary per-term breakpoints and replaced them with one set
      on a quantity that has units and can be argued about.</p>
      <p><b>Why the sliders changed meaning.</b> They are now exponents on a
      physical product, defaulting to 1. The old scheme was wrong in kind: it let
      excellent alkalinity retention partly offset zero reactivity, when both are
      required multiplicatively for any carbon to be stored. You cannot prefer
      dissolution rate over alkalinity retention. Weights become meaningful again
      once genuinely substitutable economic factors exist — delivered feedstock
      cost, MRV cost — because those <i>are</i> tradeable.</p>
      <p><b>A second defect found while fixing the first.</b> The dissolved
      fraction was hard-clipped at 0.6, which pinned <b>18.9% of cropland area at
      an identical CO₂ value</b> — a flat top across a fifth of the map. It is now
      a first-order decay, <code>1 − exp(−k·X)</code>, bounded by 1 for the right
      reason: you cannot dissolve more rock than you applied. The reference
      dissolved fraction is anchored to the midpoint of observation (first-period
      fraction weathered across the verified deliveries spans roughly 15–56%),
      which also means our own 20% cap constant was falsified by the data.</p>

      <h3>Monthly soil temperature and moisture</h3>
      <p>Both stand-ins are gone. Soil temperature is Lembrechts et al. (2022) at
      5–15 cm, natively 30 arc-second and monthly — the deeper layer because
      Isometric's near-field zone is the deeper of 20 cm or tillage depth plus
      5–10 cm. Moisture is a ten-year TerraClimate root-zone climatology.</p>
      <p>The rate is now computed <b>each month and the rate averaged</b>, never
      the drivers. Two reasons: the rate is convex in temperature, so the mean of
      the rate exceeds the rate at the mean (Jensen); and weathering needs warm
      <i>and</i> wet simultaneously, which annual means destroy.</p>
      <p><b>The effect is real but smaller than we predicted, and we were wrong
      about the size.</b> Literature estimates based on air-temperature amplitude
      suggested ~1.4×. Measured here: median 1.04, range 0.89–1.33. Soil
      temperature at 5–15 cm is strongly damped relative to air, so the Jensen
      term is much weaker than an air-based estimate implies — and the covariance
      term pulls the other way in places, partly cancelling it.</p>
      <p>It is spatially structured as the mechanism predicts: Mediterranean
      climates come out <i>below</i> 1 (Andalusia 0.85, Central Valley 0.93), where
      annual means flatter a site whose warm and wet seasons never coincide;
      monsoon and continental cropland come out above (Punjab 1.19, Iowa 1.18);
      the wet tropics sit at ~1, having little seasonality to lose.</p>

      <h3>Feedstock and delivered cost</h3>
      <p>The largest gap versus a deployment tool, and it needed two constructs
      rather than one. Lithology is <i>not</i> delivered cost: basalt under a field
      is irrelevant if nobody quarries it within haul range. But usable quarry
      inventories are very uneven — USGS MRDS is the only large open one, it is
      reliable mainly for the United States, and USGS stopped systematic updates
      in 2011 while itself counting 3,531 operating US crushed-stone quarries in
      2023.</p>
      <p>So the map carries both: globally, distance to mafic outcrop from
      full-resolution GLiM (1.24 million polygons, 93,220 of them basic igneous),
      which is an <b>upper bound</b> since outcrop is not a quarry; and where MRDS
      is usable, distance to a mafic-hosted quarry, which is what actually sets
      cost. Having both in one region lets us <b>measure</b> the gap instead of
      asserting a caveat: quarry distance is <b>2.0× outcrop distance</b> there,
      and that measured ratio is what scales the outcrop bound elsewhere.</p>
      <p><b>Haul mode matters more than it looks.</b> A truck-only model gave a
      $252/t median and $1,240/t at the 90th percentile, which would make ERW
      uneconomic almost everywhere — an artefact, not a finding. Bulk minerals move
      by rail. Taking the cheaper of truck and rail-plus-transload (crossover
      ~133 km) gives $28/$46/$65 per tonne at the 10th/50th/90th percentile of
      cropland. Notably <b>no cropland falls in the worst cost bracket</b>: with
      rail, basalt is within economic reach of most cropland.</p>
      <p>Cost is the first genuinely <i>tradeable</i> factor here, so unlike the
      physical terms it is compensatory with a floor — it discounts the score
      without zeroing it, because expensive rock is bad rather than impossible.
      That also makes its slider a real preference rather than a what-if.</p>
      <p>Still not routed: distance is great-circle times a tortuosity factor.
      Real routing needs a friction surface or a road graph.</p>

      <h3>The SOC screen, computed correctly</h3>
      <p>Previously the q05/q50/q95 quantiles were resampled to the analysis grid
      and the probability computed from the <i>averaged quantiles</i>. Averaging
      quantiles is not averaging distributions, so that was not valid uncertainty
      propagation, and it widened the apparent spread and inflated the marginal
      class. The probability is now computed at ~2.8 km and the <b>probability</b>
      is averaged, which is valid — the result is the expected area fraction of the
      cell that exceeds. Marginal cropland drops from 73% to <b>53%</b>.</p>
      <p>Reduced but not removed: SoilGrids quantiles describe a ~250 m block
      average while the protocol threshold applies to a sampled field, so this
      remains a screening likelihood rather than a calibrated eligibility
      probability.</p>

      <h3>Fixed earlier in this preview</h3>
      <p><b>Drainage is now real recharge, and the Damköhler coefficient was
      wrong.</b> Transport limitation previously used a fixed runoff coefficient
      on precipitation, giving a median η of 0.32 almost everywhere. It now uses
      WaterGAP2-2e groundwater recharge — the water that actually percolates
      below the root zone carrying bicarbonate, rather than overland flow, and
      which includes simulated irrigation return flow. Separately, the default
      D_w was 0.5 m/yr, <i>above</i> Maher &amp; Chamberlain's stated global
      maximum of 0.3, with a sensitivity range almost entirely outside the
      published one; it is now 0.03 with a 0.001–0.3 range. Because η = q/(q+D_w),
      both errors suppressed η, and they partly cancelled. Median η is now 0.71
      with real spread (0.21–0.88), and drainage limits 19.5% of cropland area
      instead of nearly all of it — reactivity now limits 74.6%, which is the
      physically expected answer for a weathering map.</p>
      <p><b>Rice paddies are now mapped.</b> Soil pCO₂ is interpolated
      continuously from a flooded fraction of cell-time, built from two
      independent halves: GRPI Landsat inundation months, and SPAM irrigated-rice
      sub-cell area. Multiplying them is deliberately conservative — it refuses to
      treat a cell that is 5% paddy as fully flooded, which would inflate the very
      paddy prediction this project needs to test.</p>
      <p><b>The CO₂ gap narrowed without being tuned.</b> Verified deliveries
      imply roughly 1.9 tCO₂/ha at 20 t/ha. This build's median moved from 0.32 to
      0.83 as the physics improved and the artificial clip came off. The remaining
      ~2.3× gap is reported, not fitted away: closing it honestly needs per-delivery particle-size
      distributions we do not have.</p>

      <h3>Known problems, stated plainly</h3>
      <p><b>Surface area is now a control, not a hidden constant.</b> The grind
      sliders move the reactivity term and the CO₂ figure directly, because rate
      is linear in reactive surface area. Note what the panel reports: at the
      reference 267 µm grind, matching a BET-scale area of 1–5 m²/g would demand a
      roughness multiplier λ of roughly 39–196, which straddles the top of the
      plausible 1–100 range. That is the dominant uncertainty in the product made
      visible rather than buried.</p>
      <p><b>Most cropland is "marginal" on the SOC screen.</b> On a point
      estimate only ~0.2% of cropland area would be excluded; carrying SoilGrids'
      predictive spread honestly puts ~73% in the band where the threshold can be
      neither cleared nor confirmed. That says more about how wide those
      predictive intervals are than about the soils. Two further caveats: the
      quantiles describe a ~250 m <i>block average</i>, not a sampled field, so
      they understate how often an individual field crosses the threshold; and
      averaging quantiles onto a coarser grid, as done here, is not a valid
      uncertainty propagation.</p>
      <p><b>Cropland is herbaceous-only.</b> The mask reproduces Potapov et al.
      (2022) to within 0.1% (1.215 vs 1.216 Gha), but that definition excludes
      perennial woody crops, temporary meadows and long fallow — about 0.36 Gha
      relative to FAOSTAT. Woody crops <i>are</i> protocol-eligible and are a live
      deployment setting in Brazilian citrus, so addressable area is understated,
      concentrated in the tropics.</p>

      <h3>Not claimed</h3>
      <p>Nothing here is "validated". The CO₂ layer is <b>gross alkalinity
      generation potential</b>, not net removal; the gap (in-soil carbonate
      precipitation, riverine re-release, strong-acid competition) is plausibly
      20–80% and spatially variable. Specific surface area alone spans 130–670×
      between geometric and BET values at ERW grain sizes — it sets the level of
      that layer and cancels in any relative comparison, which is why the ranking
      is the product and the tonnage is an illustration. This is not a
      site-selection tool: zoom is capped on purpose.</p>

      <h3>Sources</h3>
      <table>
        <tr><th>Layer</th><th>Source</th></tr>
        <tr><td>Soil pH, SOC + quantiles</td><td>${p.soil}</td></tr>
        <tr><td>Climate</td><td>${p.climate}</td></tr>
        <tr><td>Cropland</td><td>${p.cropland}</td></tr>
        <tr><td>Drainage</td><td>${p.drainage || "—"}</td></tr>
        <tr><td>Rice paddy</td><td>${p.paddy || "—"}</td></tr>
        <tr><td>Kinetics</td><td>Palandri &amp; Kharaka 2004, USGS OFR 2004-1068</td></tr>
        <tr><td>Carbonate system</td><td>Plummer &amp; Busenberg 1982, GCA 46, 1011</td></tr>
        <tr><td>Efficiency term</td><td>Bertagni &amp; Porporato 2022, STE 838, 156524</td></tr>
        <tr><td>Transport limitation</td><td>Maher &amp; Chamberlain 2014, Science 343, 1502 —
          D_w = ${E.provenance.dw ? E.provenance.dw.value : "?"} m/yr,
          published range ${E.provenance.dw ? E.provenance.dw.range.join("\u2013") : "?"}</td></tr>
        <tr><td>Particle size</td><td>Rosin\u2013Rammler over a ${E.psd.d80Range[0]}\u2013${E.psd.d80Range[1]} \u00b5m
          d80 range; geometric area, not BET</td></tr>
        <tr><td>Eligibility</td><td>Puro.earth ERW 2025 v1; Isometric EW-in-agriculture v1.2</td></tr>
        <tr><td>Coastlines</td><td>Natural Earth 110m (public domain)</td></tr>
      </table>
      <p>Feedstock archetype <code>${E.feedstock.archetype}</code> at
      ${E.feedstock.tco2PerT} tCO₂/t, anchored to verified deliveries rather than
      a textbook basalt. Code MIT; each dataset keeps its own licence.</p>`;
  }

  /* ---------------- wiring ---------------- */
  function refresh() {
    syncSliders(); syncPsd(); syncEcon(); renderLegend(); updateStability(); draw();
  }

  function setMode(m) {
    mode = m;
    document.querySelectorAll("#mode-seg .seg-btn").forEach((b) =>
      b.classList.toggle("active", b.dataset.mode === m));
    $("mode-hint").textContent = MODE_HINT[m];
    $("weights-group").classList.toggle("hidden", m !== "score");
    // Grind does not apply to Cascade's index: their formulation has no surface
    // area term at all, which is part of the point of showing it.
    $("psd-group").classList.toggle("hidden", m === "cascade");
    $("econ-group").classList.toggle("hidden", m !== "score" || !E.cost);
    refresh();
  }

  function attachPanZoom() {
    const c = $("gl");
    let drag = null;
    c.addEventListener("mousedown", (e) => {
      drag = { x: e.clientX, y: e.clientY, lon: view.lon, lat: view.lat };
      c.style.cursor = "grabbing";
    });
    window.addEventListener("mouseup", () => { drag = null; c.style.cursor = "crosshair"; });
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
    c.addEventListener("mouseleave", () => $("readout").classList.add("hidden"));
    c.addEventListener("wheel", (e) => {
      e.preventDefault();
      view.zoom = clamp(1, view.zoom * (e.deltaY < 0 ? 1.15 : 1 / 1.15), 40);
      clampView();
      draw();
    }, { passive: false });
    const zoomBy = (f) => {
      view.zoom = clamp(1, view.zoom * f, 40); clampView(); draw();
    };
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
    $("elig-version").textContent = E.eligibility.version;
    $("elig-hint").textContent =
      `Excluded above P=${E.eligibility.pExcluded} of crossing SOC ` +
      `${E.eligibility.socThreshold} wt%; hatched between ` +
      `${E.eligibility.pPasses} and ${E.eligibility.pExcluded}. A hatch, not a ` +
      `blend — a marginal site should not read as a slightly worse good site.`;
    $("stat-main").textContent = E.stats.croplandGha.toFixed(2) + " Gha";
    $("attrib").textContent =
      "SoilGrids · WorldClim · Potapov et al. cropland · Natural Earth";
    $("method-body").innerHTML = methodsHTML();

    initGL();
    texRamp = makeRampTexture();
    const [a, b, cTex] = await Promise.all([
      loadTexture("textures/tex1.png", 0), loadTexture("textures/tex2.png", 1),
      loadTexture("textures/tex3.png", 2),
    ]);
    texA = a.tex; texB = b.tex; texC = cTex.tex;
    cpu = decodeToCPU(a.bmp, b.bmp, cTex.bmp);
    buildSample();

    buildSliders();
    buildPsdSliders();
    buildEconSliders();
    attachPanZoom();
    document.querySelectorAll("#mode-seg .seg-btn").forEach((btn) =>
      btn.addEventListener("click", () => setMode(btn.dataset.mode)));
    $("chk-elig").addEventListener("change", (e) => {
      showElig = e.target.checked; refresh();
    });
    $("btn-reset").onclick = () => {
      CRIT.forEach((c) => { termExp[c.key] = 1; }); refresh();
    };
    $("btn-psd-reset").onclick = () => {
      psd.d80 = E.psd.refD80; psd.width = E.psd.refWidth;
      $("ps-d80").value = psd.d80; $("ps-width").value = psd.width;
      refresh();
    };
    $("btn-random").onclick = () => {
      CRIT.forEach((c) => { termExp[c.key] = 0.3 + Math.random() * 0.7; });
      refresh();
    };
    $("open-method").onclick = () => $("method-modal").classList.remove("hidden");
    $("method-close").onclick = () => $("method-modal").classList.add("hidden");
    $("method-modal").addEventListener("click", (e) => {
      if (e.target.id === "method-modal") $("method-modal").classList.add("hidden");
    });

    clampView();
    setMode("score");
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
