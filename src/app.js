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
  const FACTOR_COLORS = ["#e0704f", "#4f9fe0", "#8fd14f"];

  let gl, prog, quad, texA, texB, texC, texRamp, texRampFrac, cpu = null;
  let mode = "score";
  let showQuarries = false;
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

  uniform sampler2D uA, uB, uC, uRamp, uRampFrac;
  uniform vec4 uGeo;              // lon0, lat0, lonSpan, latSpan of the visible box
  uniform vec4 uGrid;             // west, north, dlon, dlat of the data grid
  uniform vec2 uGridSize;
  uniform vec3 uExp;              // term exponents; 1,1,1 == the physics
  uniform int  uMode;             // 0 suitability, 1 limiting, 2 fraction weathered
  uniform vec2 uL1Enc;            // lo, hi of the stored L1 range
  uniform float uSsaShift;        // log10(SSA(d50,width) / SSA(ref))
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

    if ((flags & 2) != 0) {                   // fails the SOC screen outright
      fragColor = vec4(0.30, 0.16, 0.16, 1.0);
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

    // Fraction weathered on its OWN ramp. No economics multiplier and no
    // negligible cutoff: this is a physical quantity whose zero is meaningful on
    // the ramp itself, so masking the bottom would hide real information rather
    // than protect against over-reading a near-zero score.
    if (uMode == 2) {
      vec3 fc = texture(uRampFrac, vec2(clamp(frac, 0.0, 1.0), 0.5)).rgb;
      fragColor = vec4(fc, 1.0);
      return;
    }

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
    // No marginal-eligibility hatch. It covered 53% of cropland, which made it
    // the dominant feature of the map while saying little, and it drowned out the
    // failures it was meant to accompany. Only outright failures are drawn now.
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
     quantity people reason about rather than a unitless multiplier.

     v = 1 / (1 + (cost - gate)/S)  inverts in closed form to
     cost = gate + S (1/v - 1), which is exact rather than the piecewise
     back-interpolation the five-knot version needed. */
  function costUsdT(vCost) {
    if (!E.cost) return null;
    const v = clamp(E.cost.floor, vCost, 1);
    return E.cost.gateUsdT + E.cost.haulScaleUsdT * (1 / v - 1);
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
    $("psd-readout").textContent =
      (rel >= 1 ? rel.toFixed(2) + "\u00d7 faster" : (1 / rel).toFixed(2) + "\u00d7 slower")
      + " weathering than the reference grind";
    const atRef = Math.abs(psd.d50 - P.refD50) < 2.5
                  && Math.abs(psd.width - P.refWidth) < 0.01;
    $("psd-tag").textContent = atRef ? "Reference" : "Custom";
  }

  function buildEconSliders() {
    if (!E.cost) { $("econ-group").classList.add("hidden"); return; }
    // A two-state toggle, not a continuous slider: there is no principled middle
    // value, and inventing one would be an unlabelled thumb on the scale.
    $("econ-sliders").innerHTML =
      `<p class="why" style="margin-top:10px">$${E.cost.gateUsdT}/t at the ` +
      `quarry gate plus trucking at $${E.cost.truckUsdTKm}/t-km from the ` +
      `nearest mafic quarry.</p>`;
    document.querySelectorAll("#econ-seg .seg-btn").forEach((b) => {
      b.addEventListener("click", () => {
        econ.costExp = +b.dataset.econ ? E.cost.expOn : 0;
        refresh();
      });
    });
  }

  function syncEcon() {
    if (!E.cost) return;
    const on = econ.costExp > 0;
    document.querySelectorAll("#econ-seg .seg-btn").forEach((b) =>
      b.classList.toggle("active", (+b.dataset.econ > 0) === on));
    $("econ-tag").textContent = on ? "On" : "Off";
    $("econ-readout").textContent = on
      ? "Hover the map to see delivered cost per tonne of rock and per tCO\u2082."
      : "Off: the map shows physical potential only.";
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
  function onMove(ev) {
    if (pinned) return;
    const box = document.getElementById("readout");
    const cell = cpu ? screenToCell(ev) : null;
    if (!cell) { box.classList.add("hidden"); return; }
    const B = cpu.B, i = cell.i;
    const flags = B[i + 1];
    if (!(flags & 1)) { box.classList.add("hidden"); return; }

    const t = termsAt(i);
    const g = grossCdr(t.rel, t.eDic, t.eTr);
    const econOn = econ.costExp > 0;
    const score = suitabilityOf(g.cdr) * Math.pow(t.vCost, econ.costExp);
    // Limiting term = the largest negative contribution to log X.
    let lo = 0;
    for (let k = 1; k < 3; k++) if (g.contrib[k] < g.contrib[lo]) lo = k;

    const cdr = g.cdr;
    const pe = E.phEncoding;
    const soilPh = pe.lo + (cpu.C[i + 1] / 255) * (pe.hi - pe.lo);
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
      `<tr><td class="k">Limiting factor</td><td class="v">${CRIT[lo].label}</td></tr>` +
      `<tr><td class="k">Soil pH (0–15 cm)</td><td class="v">${soilPh.toFixed(1)}</td></tr>` +
      (econOn && usdT !== null
        ? `<tr><td class="k">Delivered rock</td><td class="v">$${usdT.toFixed(0)}/t · $${(usdT / E.cost.tco2PerT).toFixed(0)}/tCO₂</td></tr>`
        : ``) +
      `</table>` +
      flagHtml +
      `<div class="flag pin-hint">Click to ${pinned ? "release" : "pin"}</div>`;
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
    const isFrac = mode === "frac";
    const stops = isFrac ? E.rampFrac : E.ramp;
    const grad = stops.map(([t, c]) => `${c} ${(t * 100).toFixed(0)}%`).join(", ");
    const obs = E.dissolvedFracObserved;
    L.innerHTML =
      `<div class="ramp" style="background:linear-gradient(90deg,${grad})"></div>` +
      `<div class="ends"><span>0</span>` +
      `<span>${isFrac ? "% weathered in year 1" : "suitability"}</span>` +
      `<span>100</span></div>` +
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
      `<span class="lbl">Fails SOC &gt; ${E.eligibility.socThreshold} wt% screen</span></div>`;
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
        ? "At the physical defaults."
        : `${(pct * 100).toFixed(1)}% of cropland area changes decile vs the `
          + `unweighted physical product.`;
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
      <p>It is a screening map, not a site-selection tool: zoom is capped on
      purpose, and every CO₂ figure is gross removal, before in-soil carbonate
      precipitation, riverine re-release and strong-acid competition.</p>

      <h3>How it is computed</h3>
      <ol>
      <li><b>Dissolution rate.</b> The Palandri &amp; Kharaka (2004,
      USGS OFR 2004-1068) three-mechanism rate law for basalt, driven by soil pH
      (SoilGrids, 0–15 cm) and monthly soil temperature (Lembrechts et al. 2022,
      5–15 cm), moisture-limited from a TerraClimate root-zone climatology. The
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
      <li><b>Drainage.</b> η = q/(q + D_w) on WaterGAP2-2e groundwater recharge
      (Maher &amp; Chamberlain 2014; D_w = ${p.dw ? p.dw.value : "?"} m/yr):
      bicarbonate must percolate below the root zone to count as exported.</li>
      <li><b>Gross CO₂ removal.</b> The product of the terms sets the fraction of
      rock dissolved in year one, 1 − exp(−k·X), anchored so the reference case
      sits at the midpoint of verified field deliveries
      (${(obs[0] * 100).toFixed(0)}–${(obs[1] * 100).toFixed(0)}% weathered).
      At ${E.feedstock.rateTHaYr} t/ha of basalt holding
      ${E.feedstock.tco2PerT} tCO₂/t, that fraction becomes tCO₂/ha/yr.</li>
      <li><b>Suitability.</b> A piecewise-linear score of gross CO₂ removal —
      ${knots} tCO₂/ha/yr — so zero removal scores zero by construction. The
      Advanced exponents lower one term at a time to test how much of the map
      depends on trusting it; they are not importance weights, because the terms
      are not substitutable.</li>
      <li><b>Delivered cost (optional).</b> $${E.cost.gateUsdT}/t at the quarry
      gate plus trucking at $${E.cost.truckUsdTKm}/t-km over
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
          operator-reported quarry-fines prices</td></tr>
        <tr><td>Trucking</td><td>$${E.cost.truckUsdTKm}/t-km ×
          ${E.cost.tortuosity} road tortuosity</td></tr>
        <tr><td>D_w (transport limitation)</td><td>${p.dw ? p.dw.value : "?"} m/yr
          (published range ${p.dw ? p.dw.range.join("–") : "?"})</td></tr>
      </table>

      <h3>Known limitations</h3>
      <p><b>The kinetics over-predict an independent laboratory test.</b> Against
      Gudbrandsson et al. (2011) crystalline-basalt dissolution (pH 2–11,
      5–75 °C), the rate mixture over-predicts Ca release by about +0.5 log units
      and Mg by +0.8 to +1.6, and the bias grows with temperature: the apparent
      activation energy here (46–63 kJ/mol) is roughly 2× the measured
      ~${E.kinetics.measuredEaKJ} kJ/mol (${E.kinetics.measuredEaRange[0]}–${E.kinetics.measuredEaRange[1]}
      across pH); Cascade's ${E.kinetics.cascadeEaKJ} has the same problem.
      Temperature sensitivity drives the tropical tilt of the map, so the
      tropics-versus-temperate contrast shown is likely ~2.5× too strong. This is
      recorded rather than silently retuned, because the fix is a modelling
      decision that needs its own review.</p>
      <p><b>The absolute CO₂ scale is uncertain to a factor of a few.</b>
      Geometric and BET surface areas differ by 130–670× at ERW grain sizes; to
      match a measured ${E.psd.betMeasured} m²/g BET, the reference grind implies
      a surface-roughness multiplier λ of roughly
      ${Math.round(E.psd.betMeasured / E.psd.refSsa)} (plausible range
      ${E.psd.lambdaRange[0]}–${E.psd.lambdaRange[1]}). The model's median CO₂
      also sits ~2.3× below what verified deliveries imply. The <i>ranking</i> is
      the product; the tonnage is an illustration.</p>
      <p><b>Gross, not net.</b> In-soil carbonate precipitation, riverine
      re-release and strong-acid competition plausibly claim 20–80% of gross
      removal, and the gap is spatially variable. Nothing here is validated
      against net measured removal.</p>
      <p><b>One input is a stand-in.</b> Soil moisture is root-zone storage in
      millimetres rather than a saturation fraction; the porosity normalisation
      is not yet applied.</p>
      <p><b>Cropland is herbaceous-only.</b> The mask reproduces Potapov et al.
      (2022) to 0.1%, but excludes perennial woody crops, temporary meadows and
      long fallow (~0.36 Gha vs FAOSTAT). Woody crops are protocol-eligible and a
      live deployment setting, so addressable area is understated, mostly in the
      tropics.</p>
      <p><b>Quarry inventories are uneven.</b> MRDS is reliable mainly for the
      US and static since 2011; mining titles (Brazil) and crowd-sourced points
      overstate producing quarries. Haul distance is great-circle × tortuosity,
      not road-routed.</p>
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
        <tr><td>Eligibility</td><td>Puro.earth ERW 2025 v1; Isometric EW-in-agriculture v1.2</td></tr>
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
  function refresh() {
    syncSliders(); syncPsd(); syncEcon(); renderLegend(); updateStability(); draw();
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
    $("weights-group").classList.toggle("hidden", m === "limiting");
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
      if (!pinned) $("readout").classList.add("hidden");
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
    $("stat-main").textContent = E.stats.croplandGha.toFixed(2) + " Gha";
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
    const [a, b, cTex] = await Promise.all([
      loadTexture("textures/tex1.png", 0), loadTexture("textures/tex2.png", 1),
      loadTexture("textures/tex3.png", 2), loadAdminIds(),
    ]);
    texA = a.tex; texB = b.tex; texC = cTex.tex;
    cpu = decodeToCPU(a.bmp, b.bmp, cTex.bmp);
    $("loading").remove();
    buildSample();

    buildSliders();
    buildPsdSliders();
    buildEconSliders();
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
      $("overlay-group").classList.add("hidden");
    }
    $("btn-reset").onclick = () => {
      CRIT.forEach((c) => { termExp[c.key] = 1; }); refresh();
    };
    $("btn-psd-reset").onclick = () => {
      psd.d50 = E.psd.refD50; psd.width = E.psd.refWidth;
      $("ps-d50").value = psd.d50; $("ps-width").value = psd.width;
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
