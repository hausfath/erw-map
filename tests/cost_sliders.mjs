/* Does the live cost path reproduce the build, and does it behave off-default?
 *
 *   node tests/cost_sliders.mjs
 *
 * The delivered-cost sliders rescale a value function that was BAKED into
 * tex3.b at the build's own truck rate, rather than recomputing cost from a
 * distance layer. That is exact in principle -- haul is linear in the rate, so
 * v' = v/(k + v(1-k)) -- but "exact in principle" is how the double-grind-shift
 * bug shipped, so it gets asserted here against the build's own numbers.
 *
 * Four things are checked:
 *   1. At k = 1 the rescale is the identity to floating-point exactness.
 *   2. Reported $/t at the default sliders matches gate + haul from the build.
 *   3. The GATE cost does not change v_cost at all -- the claim the UI makes.
 *   4. The truck rate is monotone in the right direction and stays in [floor, 1].
 */
import {readFileSync} from "node:fs";
import {fileURLToPath} from "node:url";
import {dirname, join} from "node:path";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");

// engine_constants.js assigns window.ERW; supply a window and read it back.
const src = readFileSync(join(ROOT, "src/engine_constants.js"), "utf8");
const E = new Function("window", `${src}; return window.ERW;`)({});
const C = E.cost;

const clamp = (lo, v, hi) => Math.max(lo, Math.min(hi, v));

// --- the two functions under test, transcribed from app.js. Kept as a literal
// transcription rather than an import because app.js is a browser IIFE; any
// divergence between these and the shipped code is itself a finding, so the
// shader line is asserted separately below.
const truckScale = (truck) => truck / C.truckUsdTKm;
const vCostLive = (vBaked, truck) => {
  const k = truckScale(truck);
  if (!(vBaked > 0)) return C.floor;
  return clamp(C.floor, vBaked / (k + vBaked * (1 - k)), 1);
};
const costUsdT = (vBaked, gate, truck) => {
  const v = clamp(C.floor, vBaked, 1);
  return gate + C.haulScaleUsdT * (1 / v - 1) * truckScale(truck);
};

// The same expression the fragment shader evaluates, so a divergence in the
// GLSL is caught here rather than by eye on the deployed page.
const shaderExpr = readFileSync(join(ROOT, "src/app.js"), "utf8")
  .includes("vBaked / (uTruckScale + vBaked * (1.0 - uTruckScale))");

let fails = 0;
const ok = (name, cond, detail = "") => {
  console.log(`  ${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  " + detail : ""}`);
  if (!cond) fails++;
};

console.log(`cost model: gate $${C.gateUsdT}/t, truck $${C.truckUsdTKm}/t-km, ` +
            `haul scale $${C.haulScaleUsdT}/t, floor ${C.floor}`);
console.log(`truck slider range $${C.truckRange[0]}-${C.truckRange[1]}/t-km, ` +
            `unsourced flag ${C.truckUnsourced}`);
console.log();

// Sample the whole encodable range of tex3.b, plus the observed cropland span.
const bytes = [];
for (let b = 5; b <= 255; b += 1) bytes.push(b);
const baked = bytes.map((b) => C.floor + clamp(0, (b - 5) / 250, 1) * (1 - C.floor));

console.log("1. identity at the build's own truck rate");
let worstId = 0;
for (const v of baked) {
  worstId = Math.max(worstId, Math.abs(vCostLive(v, C.truckUsdTKm) - v));
}
ok("v_cost unchanged at k = 1", worstId === 0,
   `worst |delta| = ${worstId}`);

console.log();
console.log("2. reported $/t reproduces gate + haul from the baked value");
// The build defines cost = gate + S(1/v - 1). At the default sliders the live
// path must return exactly that.
let worstCost = 0;
for (const v of baked) {
  const build = C.gateUsdT + C.haulScaleUsdT * (1 / v - 1);
  const live = costUsdT(v, C.gateUsdT, C.truckUsdTKm);
  worstCost = Math.max(worstCost, Math.abs(live - build));
}
ok("$/t identical at defaults", worstCost < 1e-9,
   `worst |delta| = $${worstCost.toExponential(2)}/t`);

console.log();
console.log("3. the gate cost does not move v_cost (the UI's claim)");
let gateMoved = false;
for (const v of baked) {
  for (const g of [0, 3, 10, 15]) {
    // v_cost has no gate argument at all; assert the reported cost DOES move by
    // exactly the gate delta, which is the other half of the same claim.
    const d = costUsdT(v, g, C.truckUsdTKm) - costUsdT(v, C.gateUsdT, C.truckUsdTKm);
    if (Math.abs(d - (g - C.gateUsdT)) > 1e-9) gateMoved = true;
  }
}
ok("reported $/t shifts by exactly the gate delta", !gateMoved);
ok("v_cost takes no gate argument", vCostLive.length === 2);

console.log();
console.log("4. truck rate: direction, bounds, monotonicity");
const rates = [C.truckRange[0], 0.06, C.truckUsdTKm, 0.2, C.truckRange[1]];
let bounded = true, monotone = true;
for (const v of baked) {
  let prev = Infinity;
  for (const r of rates) {
    const vv = vCostLive(v, r);
    if (!(vv >= C.floor - 1e-12 && vv <= 1 + 1e-12)) bounded = false;
    if (vv > prev + 1e-12) monotone = false;      // dearer haul -> lower v
    prev = vv;
  }
}
ok("v_cost stays within [floor, 1]", bounded);
ok("v_cost falls as the haul rate rises", monotone);
ok("shader uses the same rescale expression", shaderExpr);

console.log();
console.log("effect at the median cropland cell (delivered $43/t at defaults):");
const vMed = 1 / (1 + (43 - C.gateUsdT) / C.haulScaleUsdT);
for (const r of rates) {
  const c = costUsdT(vMed, C.gateUsdT, r);
  console.log(`  $${r.toFixed(3)}/t-km -> $${c.toFixed(0)}/t delivered, ` +
              `v_cost ${vCostLive(vMed, r).toFixed(3)}`);
}

console.log();
console.log(fails === 0 ? "ALL CHECKS PASS" : `${fails} CHECK(S) FAILED`);
process.exit(fails === 0 ? 0 : 1);
