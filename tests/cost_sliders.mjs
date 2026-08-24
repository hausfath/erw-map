/* Does the live cost path reproduce the build, and does it behave off-default?
 *
 *   node tests/cost_sliders.mjs
 *
 * The delivered-cost controls rescale a value function BAKED into tex3.b at the
 * build's regional truck rates and fixed per-trip charge F, rather than
 * recomputing cost from a distance layer. The baked haul increment is
 * h = F + r(region)*d; the slider multiplies only the per-km part, so
 * h' = F + m*(h - F), and in v-space with a = v*(1 + F/S):
 *
 *     v' = v / (a + m*(1 - a))
 *
 * exact because h is affine in m, and written in that form so m = 1 is the
 * bit-exact identity (a + (1 - a) rounds to exactly 1). "Exact in principle"
 * is how the double-grind-shift bug shipped, so it gets asserted here against
 * the build's own numbers.
 *
 * Five things are checked:
 *   1. At m = 1 the rescale is the identity to floating-point exactness.
 *   2. Reported $/t at the default sliders is exactly gate + S(1/v - 1),
 *      the build's own decomposition of the baked byte.
 *   3. The GATE cost does not change v_cost at all -- the claim the UI makes --
 *      and shifts the reported $/t by exactly the gate delta.
 *   4. The multiplier is monotone the right way and v stays in [floor, 1].
 *   5. The FIXED charge is not multiplied: at the zero-distance byte
 *      (v = 1/(1 + F/S)) the reported cost is gate + F at EVERY multiplier.
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
const F = C.haulFixedUsdT;
const fFrac = F / C.haulScaleUsdT;

// --- the functions under test, transcribed from app.js. Kept as a literal
// transcription rather than an import because app.js is a browser IIFE; the
// shader expression is asserted as a string below so GLSL/JS divergence is
// caught here rather than by eye on the deployed page.
const vCostLive = (vBaked, m) => {
  if (!(vBaked > 0)) return C.floor;
  const a = Math.min(vBaked * (1 + fFrac), 1);   // zero-distance guard
  return clamp(C.floor, vBaked / (a + m * (1 - a)), 1);
};
const costUsdT = (vBaked, gate, m) => {
  const v = clamp(C.floor, vBaked, 1);
  const haul = C.haulScaleUsdT * (1 / v - 1);
  return gate + F + m * Math.max(haul - F, 0);   // zero-distance guard
};

const app = readFileSync(join(ROOT, "src/app.js"), "utf8");
const shaderExpr =
  app.includes("float aFix = min(vBaked * (1.0 + uHaulFix), 1.0);")
  && app.includes("vBaked / (aFix + uTruckScale * (1.0 - aFix))");

let fails = 0;
const ok = (name, cond, detail = "") => {
  console.log(`  ${cond ? "PASS" : "FAIL"}  ${name}${detail ? "  " + detail : ""}`);
  if (!cond) fails++;
};

console.log(`cost model: gate $${C.gateUsdT}/t, fixed $${F}/t, regional rates ` +
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
// Exactness is claimed over PRODUCIBLE bytes (haul >= F). Bytes past the
// zero-distance point encode quantisation jitter, and the guard deliberately
// reports gate + F for them instead of gate + (something < gate + F).
let worstCost = 0, worstGuard = 0;
for (const v of baked) {
  const haul = C.haulScaleUsdT * (1 / v - 1);
  const live = costUsdT(v, C.gateUsdT, 1);
  if (haul >= F) {
    worstCost = Math.max(worstCost, Math.abs(live - (C.gateUsdT + haul)));
  } else {
    worstGuard = Math.max(worstGuard, Math.abs(live - (C.gateUsdT + F)));
  }
}
ok("$/t identical at defaults (producible bytes)", worstCost < 1e-9,
   `worst |delta| = $${worstCost.toExponential(2)}/t`);
ok("past zero-distance, cost is pinned at gate + F", worstGuard < 1e-9,
   `worst |delta| = $${worstGuard.toExponential(2)}/t`);

console.log();
console.log("3. the gate cost does not move v_cost (the UI's claim)");
let gateMoved = false;
for (const v of baked) {
  for (const g of [0, 3, 10, 15]) {
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
console.log("5. the fixed charge is not multiplied");
const vZeroDist = 1 / (1 + fFrac);           // the byte a zero-distance cell bakes
let fixedMoved = 0;
for (const m of mults) {
  fixedMoved = Math.max(fixedMoved,
                        Math.abs(costUsdT(vZeroDist, C.gateUsdT, m)
                                 - (C.gateUsdT + F)));
}
ok("zero-distance cost is gate + F at every multiplier", fixedMoved < 1e-9,
   `worst |delta| = $${fixedMoved.toExponential(2)}/t`);
let vzMoved = 0;
for (const m of mults) {
  vzMoved = Math.max(vzMoved, Math.abs(vCostLive(vZeroDist, m) - vZeroDist));
}
ok("zero-distance v_cost is multiplier-invariant", vzMoved < 1e-12,
   `worst |delta| = ${vzMoved.toExponential(2)}`);

console.log();
console.log("effect at a US-median-haul cell ($43/t delivered at defaults):");
const vMed = 1 / (1 + (43 - C.gateUsdT) / C.haulScaleUsdT);
for (const m of mults) {
  console.log(`  x${m.toFixed(2)} -> $${costUsdT(vMed, C.gateUsdT, m).toFixed(0)}/t ` +
              `delivered, v_cost ${vCostLive(vMed, m).toFixed(3)}`);
}

console.log();
console.log(fails === 0 ? "ALL CHECKS PASS" : `${fails} CHECK(S) FAILED`);
process.exit(fails === 0 ? 0 : 1);
