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
     - Weighted GEOMETRIC mean, not arithmetic. log S = sum(w_i log v_i), so the
       weights are elasticities and a near-zero in a physically necessary factor
       annihilates the score instead of being averaged away.
     - Limiting-factor mode is the p -> -inf member of the same power mean, so
       it shares one code path with the score.
     - Colormap and legend are generated from ONE array in engine_constants.js,
       so they cannot drift.
   ============================================================ */
(function () {
  "use strict";

  const E = window.ERW;
  const G = E.grid;
  const CRIT = E.criteria;

  const MODE_HINT = {
    score: "Weighted geometric mean of the factors below, on published absolute " +
           "breakpoints. Cells failing a protocol screen are drawn separately.",
    limiting: "The single lowest-scoring factor in each cell — the p → −∞ member " +
              "of the same power mean used for the score.",
    cascade: "Cascade Climate's published form, r ∝ s·[H⁺]·exp(−Ea/RT), on the " +
             "same inputs. Shown so the comparison is testable, not asserted.",
  };
  const FACTOR_COLORS = ["#e0704f", "#4f9fe0", "#8fd14f"];

  let gl, prog, quad, texA, texB, texC, texRamp, cpu = null;
  let mode = "score";
  let showElig = true;
  const weights = Object.assign({}, E.weights);

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
  uniform vec4 uWin;              // west, north, degPerPxX, degPerPxY  (unused here)
  uniform vec4 uGeo;              // lon0, lat0, lonSpan, latSpan of the visible box
  uniform vec4 uGrid;             // west, north, dlon, dlat of the data grid
  uniform vec2 uGridSize;
  uniform vec3 uW;                // normalised weights
  uniform int  uMode;             // 0 score, 1 limiting, 2 cascade
  uniform bool uElig;
  uniform float uEps;
  uniform vec2 uL1Enc;            // lo, hi of the stored L1 range
  uniform float uSsaShift;        // log10(SSA(d80,width) / SSA(ref))
  uniform float uKx[5], uKy[5];   // reactivity value-function knots

  const vec4 OUT_OF_DOMAIN = vec4(0.0, 0.0, 0.0, 0.0);

  vec3 factorColor(int i) {
    if (i == 0) return vec3(0.878, 0.439, 0.310);
    if (i == 1) return vec3(0.310, 0.624, 0.878);
    return vec3(0.561, 0.820, 0.310);
  }

  void main() {
    // Screen -> lon/lat -> data grid UV. Equirectangular, so this is linear.
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
    // interpolate garbage bit patterns, and it would also invent detail the
    // 0.1 degree grid does not have.
    vec4 a = vec4(texelFetch(uA, px, 0));
    vec4 b = vec4(texelFetch(uB, px, 0));
    vec4 cc = vec4(texelFetch(uC, px, 0));

    int flags = int(b.g * 255.0 + 0.5);
    bool inDomain = (flags & 1) != 0;
    if (!inDomain) { fragColor = OUT_OF_DOMAIN; return; }

    if (uElig && (flags & 2) != 0) {          // fails the SOC screen outright
      fragColor = vec4(0.30, 0.16, 0.16, 1.0);
      return;
    }

    // Dequantise. 0 is reserved for masked cells, so data starts at 5/255.
    vec3 raw = (a.rgb * 255.0 - 5.0) / 250.0;

    // tex1.r stores NORMALISED L1, not a value function, so that a change of
    // grind is one uniform here rather than a pipeline rebuild. The rate is
    // linear in reactive surface area and L1 is a log10 ratio, so particle size
    // enters as a uniform additive shift.
    float l1 = mix(uL1Enc.x, uL1Enc.y, clamp(raw.r, 0.0, 1.0)) + uSsaShift;

    // Piecewise-linear value function on ABSOLUTE breakpoints. Absolute is what
    // keeps the colour scale stable while the sliders move.
    float vr = uKy[0];
    for (int i = 0; i < 4; i++) {
      if (l1 >= uKx[i] && l1 <= uKx[i + 1]) {
        vr = mix(uKy[i], uKy[i + 1], (l1 - uKx[i]) / (uKx[i + 1] - uKx[i]));
      }
    }
    if (l1 > uKx[4]) vr = uKy[4];

    vec3 v = vec3(vr,
                  raw.g * (1.0 - uEps) + uEps,
                  raw.b * (1.0 - uEps) + uEps);
    v = clamp(v, uEps, 1.0);

    vec3 col;
    if (uMode == 1) {
      int lo = (v.x <= v.y && v.x <= v.z) ? 0 : ((v.y <= v.z) ? 1 : 2);
      col = factorColor(lo);                  // argmin in LINEAR space
    } else if (uMode == 2) {
      // Cascade baseline, from its OWN channel (tex3.r). Not the CDR channel --
      // an earlier build drew this mode from tex2.b and so showed the wrong layer.
      col = texture(uRamp, vec2(clamp(cc.r, 0.0, 1.0), 0.5)).rgb;
    } else {
      // p -> 0: weighted geometric mean. Weights are elasticities.
      float s = exp(dot(uW, log(v)));
      col = texture(uRamp, vec2(clamp(s, 0.0, 1.0), 0.5)).rgb;
    }

    // Marginal eligibility: a diagonal hatch, never a colour blend. A blend
    // would make a marginal cell read as a slightly-worse good cell, which
    // invites prospecting a site that will fail its eligibility check.
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
    const nw = normWeights();
    gl.uniform3f(u("uW"), nw[0], nw[1], nw[2]);
    gl.uniform1i(u("uMode"), mode === "score" ? 0 : (mode === "limiting" ? 1 : 2));
    gl.uniform1i(u("uElig"), showElig ? 1 : 0);
    gl.uniform1f(u("uEps"), E.epsQuantize);
    gl.uniform2f(u("uL1Enc"), E.l1Enc.lo, E.l1Enc.hi);
    gl.uniform1f(u("uSsaShift"), ssaShift());
    gl.uniform1fv(u("uKx"), new Float32Array(E.reactKnots.map(k => k[0])));
    gl.uniform1fv(u("uKy"), new Float32Array(E.reactKnots.map(k => k[1])));
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

  /* ---------------- weights ---------------- */
  function normWeights() {
    const v = CRIT.map((c) => Math.max(0, weights[c.key] || 0));
    const s = v.reduce((a, b) => a + b, 0) || 1;
    return v.map((x) => x / s);
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
      inp.value = Math.round((weights[c.key] || 0) * 100);
      inp.addEventListener("input", () => {
        weights[c.key] = +inp.value / 100;
        refresh();
      });
    });
  }

  function buildPsdSliders() {
    const P = E.psd, host = $("psd-sliders");
    const rows = [
      {k: "d80", label: "d80, particle size", unit: " \u00b5m",
       min: P.d80Range[0], max: P.d80Range[1], step: 1,
       why: `Verified 2026 deliveries span ${P.deliveryRangeUm[0]}\u2013${P.deliveryRangeUm[1]} \u00b5m. ` +
            `Reference ${P.refD80} \u00b5m is the Corn Belt trial.`},
      {k: "width", label: "Distribution width", unit: "",
       min: P.widthRange[0], max: P.widthRange[1], step: 0.05,
       why: "Rosin\u2013Rammler n. Low is a broad grind with more fines. " +
            (P.refWidthAssumed
              ? "The reference value is ASSUMED \u2014 the trial reports d80 but not the full distribution."
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
    $("psd-readout").innerHTML =
      `geometric SSA ${ssa.toFixed(4)} m\u00b2/g &nbsp;\u00b7&nbsp; ` +
      `${rel >= 1 ? rel.toFixed(2) + "\u00d7 faster" : (1 / rel).toFixed(2) + "\u00d7 slower"} ` +
      `than reference<br>` +
      `<span style="opacity:.75">BET-scale area (1\u20135 m\u00b2/g) would imply ` +
      `\u03bb \u2248 ${Math.round(1 / ssa)}\u2013${Math.round(5 / ssa)}; ` +
      `plausible range is ${P.lambdaRange[0]}\u2013${P.lambdaRange[1]}</span>`;
    const atRef = Math.abs(psd.d80 - P.refD80) < 0.5
                  && Math.abs(psd.width - P.refWidth) < 0.01;
    $("psd-tag").textContent = atRef ? "Reference" : "Custom";
  }

  function syncSliders() {
    CRIT.forEach((c, i) => {
      const inp = $("s-" + c.key);
      if (inp) inp.value = Math.round((weights[c.key] || 0) * 100);
      const nw = normWeights();
      const lab = $("v-" + c.key);
      if (lab) lab.textContent = (nw[i] * 100).toFixed(0) + "%";
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

    const eps = E.epsQuantize;
    const raw = (b) => (b - 5) / 250;
    const deq = (b) => clamp(eps, raw(b) * (1 - eps) + eps, 1);
    // Mirror the shader exactly: L1 from tex1.r, plus the grind shift, then the
    // same piecewise value function. The shared knots in engine_constants.js are
    // what keep the two from drifting.
    const l1 = E.l1Enc.lo + clamp(0, raw(A[i]), 1) * (E.l1Enc.hi - E.l1Enc.lo)
               + ssaShift();
    const KN = E.reactKnots;
    let vr = KN[0][1];
    for (let k = 0; k < KN.length - 1; k++) {
      if (l1 >= KN[k][0] && l1 <= KN[k + 1][0]) {
        vr = KN[k][1] + (KN[k + 1][1] - KN[k][1])
             * (l1 - KN[k][0]) / (KN[k + 1][0] - KN[k][0]);
      }
    }
    if (l1 > KN[KN.length - 1][0]) vr = KN[KN.length - 1][1];
    const v = [clamp(eps, vr, 1), deq(A[i + 1]), deq(A[i + 2])];
    const nw = normWeights();
    const score = Math.exp(nw.reduce((a, wv, k) => a + wv * Math.log(v[k]), 0));
    let lo = 0; for (let k = 1; k < 3; k++) if (v[k] < v[lo]) lo = k;

    const cropPct = (B[i] / 255 * 100);
    // CDR scales linearly with reactive surface area, so it moves with the grind.
    const cdr = (B[i + 2] / 255 * 10) * Math.pow(10, ssaShift());
    const pe = E.phEncoding;
    const soilPh = pe.lo + (cpu.C[i + 1] / 255) * (pe.hi - pe.lo);

    let flagHtml = "";
    if (flags & 2) flagHtml += `<div class="flag bad">Fails the SOC &gt; ${E.eligibility.socThreshold} wt% screen (P &gt; ${E.eligibility.pExcluded})</div>`;
    else if (flags & 4) flagHtml += `<div class="flag warn">Marginal on the SOC screen — cannot be cleared or excluded from these data</div>`;
    if (flags & 8) flagHtml += `<div class="flag warn">Soil pH &lt; 5.2: Isometric screens pH at validation (annotation only, no score effect)</div>`;

    box.innerHTML =
      `<div class="rt">${cell.lat.toFixed(1)}°, ${cell.lon.toFixed(1)}°</div>` +
      `<table>` +
      CRIT.map((c, k) =>
        `<tr><td class="k">${c.label}</td><td class="v">${v[k].toFixed(2)}</td></tr>`).join("") +
      `<tr><td class="k"><b>Suitability</b></td><td class="v"><b>${(score * 100).toFixed(0)}</b></td></tr>` +
      `<tr><td class="k">Limiting factor</td><td class="v">${CRIT[lo].label}</td></tr>` +
      `<tr><td class="k">Soil pH (0–15 cm)</td><td class="v">${soilPh.toFixed(2)}</td></tr>` +
      `<tr><td class="k">Cropland</td><td class="v">${cropPct.toFixed(0)}%</td></tr>` +
      `<tr><td class="k">L1 log₁₀(R/R_ref)</td><td class="v">${l1 >= 0 ? "+" : ""}${l1.toFixed(2)}</td></tr>` +
      `<tr><td class="k">Indicative gross CO₂</td><td class="v">${cdr.toFixed(2)}</td></tr>` +
      `</table>` +
      `<div class="flag">tCO₂ gross/ha/yr at ${E.feedstock.rateTHaYr} t/ha. Gross, not net; low confidence.</div>` +
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
        out.push([A[i], A[i + 1], A[i + 2], crop * wLat]);
      }
    }
    sample = out;
  }

  function scoreOf(row, nw) {
    const eps = E.epsQuantize;
    let s = 0;
    for (let k = 0; k < 3; k++) {
      const v = clamp(eps, (row[k] - 5) / 250 * (1 - eps) + eps, 1);
      s += nw[k] * Math.log(v);
    }
    return Math.exp(s);
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
    const neutral = CRIT.map(() => 1 / CRIT.length);
    if (!baseDec) baseDec = deciles(neutral);
    const nw = normWeights();
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
        ? "At the neutral default. Move a slider to see how much of the map is weight-contingent."
        : `${(pct * 100).toFixed(1)}% of cropland area changes decile vs the neutral default.`;
    $("weight-tag").textContent = pct < 0.001 ? "Neutral" : "Custom";
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

      <h3>Remaining stand-ins</h3>
      <ul>${p.substitutions.map((s) => `<li>${s}</li>`).join("")}</ul>
      <p>These mean the temperature and moisture terms are still <i>Cascade's own
      inputs</i>, so the "Cascade baseline" comparison is like-for-like, but our
      claim to a soil-temperature improvement is not yet realised. Planned:
      Lembrechts et al. (2022) monthly soil temperature at 30 arc-second, and a
      monthly soil-moisture climatology.</p>

      <h3>Fixed since the first preview</h3>
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
      0.62 purely because the physics improved. The remaining ~3× gap is reported,
      not fitted away: closing it honestly needs per-delivery particle-size
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
    syncSliders(); syncPsd(); renderLegend(); updateStability(); draw();
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
    attachPanZoom();
    document.querySelectorAll("#mode-seg .seg-btn").forEach((btn) =>
      btn.addEventListener("click", () => setMode(btn.dataset.mode)));
    $("chk-elig").addEventListener("change", (e) => {
      showElig = e.target.checked; refresh();
    });
    $("btn-reset").onclick = () => {
      Object.assign(weights, E.weights); refresh();
    };
    $("btn-psd-reset").onclick = () => {
      psd.d80 = E.psd.refD80; psd.width = E.psd.refWidth;
      $("ps-d80").value = psd.d80; $("ps-width").value = psd.width;
      refresh();
    };
    $("btn-random").onclick = () => {
      CRIT.forEach((c) => { weights[c.key] = 0.1 + Math.random() * 0.9; });
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
