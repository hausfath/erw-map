/* Does the live cost path reproduce the build, and does it behave off-default?
 *
 *   node tests/cost_sliders.mjs
 *
 * The delivered-cost controls rescale a value function BAKED into tex3.b. The
 * baked haul is h = r(region) * (road_km + d0), where d0 = 50 km is the fixed
 * trip charge expressed as a km-equivalent and priced at the regional rate.
 * The whole haul is therefore linear in r, so the multiplier rescale
 *
 *     v' = v / (m + v*(1 - m))
 *
 * is exact, and m + v*(1 - m) evaluates to exactly 1 at m = 1, making the
 * identity bit-exact. The fixed charge scales with m ON PURPOSE: m represents
 * the trucking market's hourly cost level, and trip time is priced at that
 * level. (An earlier design spared the fixed charge from the multiplier; it
 * confused time, which is universal, with cost, which is regional.)
 * "Exact in principle" is how the double-grind-shift bug shipped, so it gets
 * asserted here against the build's own numbers.
 *
 * Five things are checked:
 *   1. At m = 1 the rescale is the identity to floating-point exactness.
 *   2. Reported $/t at the default sliders is exactly gate + S(1/v - 1),
 *      the build's own decomposition of the baked byte -- every byte, no
 *      carve-outs (the pure-multiplier model needs no zero-distance guard).
 *   3. The GATE cost does not change v_cost at all -- the claim the UI makes --
 *      and shifts the reported $/t by exactly the gate delta, up to $25.
 *   4. The multiplier is monotone the right way and v stays in [floor, 1].
 *   5. Fixed-charge coherence per region: a zero-distance cell in rate group r
 *      bakes v = 1/(1 + r*d0/S) and must report gate + m*r*d0 at multiplier m.
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
const D0 = C.haulFixedKm;

// --- the functions under test, transcribed from app.js. Kept as a literal
// transcription rather than an import because app.js is a browser IIFE; the
// shader expression is asserted as a string below so GLSL/JS divergence is
// caught here rather than by eye on the deployed page.
const vCostLive = (vBaked, m) => {
  if (!(vBaked > 0)) return C.floor;
  return clamp(C.floor, vBaked / (m + vBaked * (1 - m)), 1);
};
const costUsdT = (vBaked, gate, m) => {
  const v = clamp(C.floor, vBaked, 1);
  return gate + m * C.haulScaleUsdT * (1 / v - 1);
};

const app = readFileSync(join(ROOT, "src/app.js"), "utf8");
const shaderExpr = app.includes(
  "vBaked / (uTruckScale + vBaked * (1.0 - uTruckScale))");

let fails = 0;
const ok = (name, cond, detail = "") => {
  console.log(`  ${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  " + detail : ""}`);
  if (!cond) fails++;
};

console.log(`cost model: gate $${C.gateUsdT}/t, fixed trip = ${D0} km at the ` +
            `regional rate, rates ` +
            Object.entries(C.truckRates).map(([k, v]) => `${k} $${v}`).join(", ") +
            `, elsewhere $${C.truckRateDefault}/t-km`);
console.log(`haul scale $${C.haulScaleUsdT}/t, floor ${C.floor}, ` +
            `multiplier range ${C.truckMultRange.join("-")}`);
console.log();

// Sample the whole encodable range of tex3.b.
const bytes = [];
for (let b = 5; b <= 255; b += 1) bytes.push(b);
const baked = bytes.map((b) => C.floor + clamp(0, (b - 5) / 250, 1) * (1 - C.floor));

console.log("1. identity at multiplier 1");
let worstId = 0;
for (const v of baked) {
  worstId = Math.max(worstId, Math.abs(vCostLive(v, 1) - v));
}
ok("v_cost unchanged at m = 1", worstId === 0, `worst |delta| = ${worstId}`);

console.log();
console.log("2. reported $/t at defaults reproduces the baked decomposition");
let worstCost = 0;
for (const v of baked) {
  const build = C.gateUsdT + C.haulScaleUsdT * (1 / v - 1);
  worstCost = Math.max(worstCost, Math.abs(costUsdT(v, C.gateUsdT, 1) - build));
}
ok("$/t identical at defaults (every byte)", worstCost < 1e-9,
   `worst |delta| = $${worstCost.toExponential(2)}/t`);

console.log();
console.log("3. the gate cost does not move v_cost (the UI's claim)");
let gateMoved = false;
for (const v of baked) {
  for (const g of [0, 3, 10, 15, 21.33, 25]) {
    const d = costUsdT(v, g, 1) - costUsdT(v, C.gateUsdT, 1);
    if (Math.abs(d - (g - C.gateUsdT)) > 1e-9) gateMoved = true;
  }
}
ok("reported $/t shifts by exactly the gate delta", !gateMoved);
ok("v_cost takes no gate argument", vCostLive.length === 2);

console.log();
console.log("4. multiplier: direction, bounds, monotonicity");
const mults = [C.truckMultRange[0], 0.5, 1, 1.5, C.truckMultRange[1]];
let bounded = true, monotone = true;
for (const v of baked) {
  let prev = Infinity;
  for (const m of mults) {
    const vv = vCostLive(v, m);
    if (!(vv >= C.floor - 1e-12 && vv <= 1 + 1e-12)) bounded = false;
    if (vv > prev + 1e-12) monotone = false;      // dearer haul -> lower v
    prev = vv;
  }
}
ok("v_cost stays within [floor, 1]", bounded);
ok("v_cost falls as the multiplier rises", monotone);
ok("shader uses the same rescale expression", shaderExpr);

console.log();
console.log("5. fixed-charge coherence: zero-distance cells by rate group");
// A cell at the quarry in group r bakes haul = r*d0. At multiplier m it must
// report gate + m*r*d0 -- the fixed charge scales with the market level.
const allRates = [...Object.values(C.truckRates), C.truckRateDefault];
let worstFix = 0;
for (const r of allRates) {
  const vZero = 1 / (1 + (r * D0) / C.haulScaleUsdT);
  for (const m of mults) {
    worstFix = Math.max(worstFix,
                        Math.abs(costUsdT(vZero, C.gateUsdT, m)
                                 - (C.gateUsdT + m * r * D0)));
  }
}
ok("zero-distance cost is gate + m*r*d0 for every group", worstFix < 1e-9,
   `worst |delta| = $${worstFix.toExponential(2)}/t`);

console.log();
console.log("effect at a US-median-haul cell ($42.5/t delivered at defaults):");
const vMed = 1 / (1 + (42.5 - C.gateUsdT) / C.haulScaleUsdT);
for (const m of mults) {
  console.log(`  x${m.toFixed(2)} -> $${costUsdT(vMed, C.gateUsdT, m).toFixed(0)}/t ` +
              `delivered, v_cost ${vCostLive(vMed, m).toFixed(3)}`);
}

console.log();
console.log(fails === 0 ? "ALL CHECKS PASS" : `${fails} CHECK(S) FAILED`);
process.exit(fails === 0 ? 0 : 1);
