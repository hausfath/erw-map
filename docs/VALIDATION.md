# Validation and pre-registered gates

This file is the authority the code defers to. `test_kinetics.py`,
`constants.py`, `analyse_deployments.py` and `app.js` all cite it; until July
2026 it did not exist, which meant the pre-registered tolerances lived only in a
mutable Python file and the decision criteria lived only in a gitignored notes
file. That is fixed by this document being tracked.

**Nothing in this model is "validated."** One test compares the model against
independent measurements it was not built from, and it fails. Everything else is
internal consistency. Read the next section before quoting any gate count.

---

## 1. What the gate suite is, and is not

`python3 scripts/test_kinetics.py` runs 18 gates. As of July 2026: **16 pass, 2
fail.** The count is close to meaningless without the breakdown:

| Category | Gates | What a pass means |
|---|---|---|
| **Independent test** | 11 | The rate law reproduces measurements it was not fitted to. **Currently FAILS.** |
| **Independent cross-derivation** | 2d | eta_DIC reproduces Dietzen & Rosing's X*, derived from a proton budget rather than carbonate equilibrium, to within 0.03 across a 40x pCO2 range. **The strongest external check here.** |
| **Over-identified structural test** | 11b | Two free surface fractions against four measured elements. Answers "can repartitioning the reacting surface fix the rate law?" — **no.** |
| Internal consistency | 6c, 8, 10 | Two parts of our own code agree with each other |
| Literature reproduction | 1, 2, 2b, 2c, 4, 4b, 6 | We transcribed a published constant correctly |
| Invariants | 5, 9, 10 | The functions behave monotonically where physics requires |
| **Physical impossibility** | 2c (build) | No cell receiving more than a metre of rain a year drains less than a millimetre. Installed August 2026 after groundwater recharge was found to be exactly zero across three major river deltas. |
| Arithmetic self-check | 6b, 7 | A constant was not fat-fingered |

Gate 7 deserves singling out because it used to be presented as evidence:
`delivered_basalt`'s CaO and MgO were *chosen* to reproduce
`DELIVERED_BASALT_TCO2_PER_T`, so the gate verifies arithmetic, not the
archetype. It is also anchored to n = 3 deliveries from one operator and one
feedstock source. State that wherever 0.289 tCO₂/t appears.

## 2. Pre-registered tolerances

Fixed before the tests were run. Changing any of these requires a commit that
changes only this file and says why.

| Quantity | Tolerance | Where enforced |
|---|---|---|
| Gudbrandsson residuals, log₁₀ | **0.5** on mean absolute deviation | `GUDBRANDSSON_TOLERANCE_LOG`, gate 11 |
| Carbonate constants at 25 °C | 0.0005 log units | gate 1 |
| η_DIC-derived pH thresholds vs protocols | 0.25 pH units | gate 2 |
| Per-mineral CDRmax vs Puro Table 1.1 | 6% | gate 6 |
| Archetype mineralogy vs stated oxides | ±15% | gate 6c |
| eta_DIC vs Dietzen & Rosing X* | 0.05 absolute | gate 2d |
| Surface partition, all four elements | 0.5 log units (same as gate 11) | gate 11b |
| Cropland area vs Potapov et al. | 2% | gate 1, FATAL |
| Stoichiometric ceiling | hard bound, no tolerance | gate 3 |
| Drainage-concentration ceiling | hard bound, no tolerance — **currently NOT enforced**, see §5 | gate 12 (build) |
| Ceiling vs open-system calcite benchmark | 0.85–1.05 mmol/L, pH 8.0–8.4 | gate 13 |
| Ceiling inside measured drainage anchors | envelope of five anchors, drained cells only | gate 13b |
| Wet-but-undrained cropland | **0.05% of area** (precip > 1,000 mm/yr and q < 1 mm/yr) | gate 2c (build) |
| Crop-mix packing round trip | ids exact; share error ≤ half a quantisation step (0.79 pp) | gate 16 (build) |
| Streaming top-2 crops vs a full sort | exact on 50,000 random cells, or the layer is not written | `prep_layers.prep_crop_mix` |

### What is frozen alongside the 0.5-log tolerance

A tolerance alone is gameable by changing what is measured. For gate 11 the
following are frozen with it, and a change to any of them is a change to the
gate:

- **Statistic:** mean absolute deviation of log₁₀(predicted / measured). Not
  RMSE, not median, not bias.
- **Sample:** the 25 non-outlier rows of `gudbrandsson2011_basalt.csv`. The one
  excluded row (`11-05`, log r(Ca) exceeding log r(Si)) is excluded on a stated
  physical inconsistency, not on its residual. Note the exclusion is
  *conservative toward us* — that point has anomalously high observed Ca, so
  dropping it **raises** our reported bias. Both figures should be reported.
- **Evaluation basis:** **volume fractions**, which is what `build_v0.py` ships.
  Not the paper's fitted surface fractions — those are three parameters fitted to
  this same dataset, so scoring on them borrows an in-sample fit into a gate
  titled "no free parameters". This was corrected in July 2026; the gate got
  redder.
- **Quantity:** the **Ca+Mg charge sum**, which is what the map uses. Per-element
  residuals are reported as diagnostics. The charge sum is worse than either
  element implies (+1.2 log units vs Ca +0.5).

### Declared post-hoc diagnostics, which are never pass criteria

Restricting a range after seeing the residuals improves the statistic, so it must
be declared. Gate 11 reports a **5–25 °C, pH 4–8.5** band because cropland soil
does not reach 50–75 °C, and the pooled figure is dominated by experiments there.
The justification is a priori but the restriction was applied after the fact, so:
the restricted figure is a diagnostic, the **pooled figure is the gate**, and the
gate stays red until it genuinely passes. Note also n = 5 in that band — too few
to carry a conclusion.

## 3. Decision criteria for the kinetics work (Phase 2)

Registered before the work is run. The originals lived in a gitignored notes
file; they are reproduced here with amendments from the July 2026 statistical
review, which found the first one could not discriminate.

1. **Surface-area repartitioning (strand A) is adopted only if** it improves
   *held-out* prediction, not in-sample MAD.
   - **Amended.** The original criterion ("Mg MAD below 1.0 without worsening
     Ca") is passed by any device with one free level per temperature band — a
     trivial per-band offset reaches 0.55 — so the threshold sat below the
     null and had no discriminating power. When actually run, the fit produced a
     **degenerate boundary solution with pyroxene driven to exactly zero in all
     four bands**, for a rock that is 39 vol% pyroxene.
   - **Parameter budget:** at most **one** new free parameter. Two free
     fractions per temperature band is 8 parameters against a 4-point residual
     trend, and is not identifiable.
   - **Held-out split:** leave-one-temperature-band-out is the only honest split
     available at n = 25. Fit on 5/25/50 °C, predict 75 °C, and vice versa.
     Report the held-out MAD.
   - **Out-of-sample element: DONE, and it returned a negative result.**
     Implemented as **gate 11b** (July 2026). The fixture carries **Si and Fe**,
     which gate 11 did not use; three minerals give two free surface fractions, so
     requiring one partition to reproduce four elements is over-identified by two
     degrees of freedom. Result: **no partition reaches the 0.5-log tolerance on
     all four elements**, best achievable worst element 0.88, even with both
     parameters fitted directly to the test data. And the Ca+Mg-optimal partition
     drives pyroxene to exactly zero and is then falsified by held-out Fe at
     **17.76 log units**. So surface repartitioning is falsified as a sufficient
     fix, the residual is not a mixing problem, and **strand A's per-temperature
     refit should not be run** — the pooled version of the same idea has now been
     tested and failed.
   - **Boundary solutions are a failure, not a pass.** Constrain surface share to
     within a factor of 3 of volume share (per Gudbrandsson's own 83/14/2.8
     against volume 44/39/17) and treat a solution on the simplex boundary as a
     rejection.

2. **A lower activation energy is adopted only if** an apparent Ea fitted to our
   own mixture restricted to 5–25 °C still disagrees with the measured value over
   that same range, with the disagreement stated as a confidence interval rather
   than a point comparison. With 12 points the CI on an Arrhenius slope is wide.

3. **A and C are not separable, contrary to the original note.** Making the
   mineral weighting temperature-dependent aliases it with Ea exactly: the fitted
   olivine-share trend implies an Ea offset of ~31 kJ/mol, statistically
   indistinguishable from the ~41 recovered from the residual slope. So the
   original criterion 1 clause — "if the fitted olivine share also falls with
   temperature, the mixture Ea is emergent and (C) is superseded" — **cannot be
   used**: it fires under both competing hypotheses. Identification must come
   from outside the temperature dimension, which is what the Si/Fe constraint
   above is for.

4. **Any adopted change ships as an explicit ensemble pair**, never a silent
   switch: per-mineral P&K as-is, and the alternative. Report the
   tropics/temperate ratio and the global gross total for both, computed with the
   same sampling design.

5. **Gate 11 stays red until it genuinely passes.** Do not relax the threshold,
   and do not relax the frozen statistic, sample, basis or quantity in §2 either
   — that is the same move by another route. If no formulation passes on Mg, that
   is a publishable finding about basalt kinetics and a limit on what any ERW map
   can claim, not something to hide.

6. **Falsification.** If no candidate improves held-out prediction, keep P&K and
   say so. A review concluding "we were right" is valid only because these
   criteria were written first.

7. **Stopping rule.** At most **five** candidate formulations may be tried, and
   every one tried must be reported, including those that failed. Without this
   the effective multiplicity is unbounded.

8. **Direction of the level effect is pre-stated.** Before implementing any fix,
   write down whether it is expected to raise or lower the global CO₂ level. The
   gate suite currently has an asymmetry worth naming: gates 3 and 5 fail when
   the level is too *high* and nothing fails when it is too *low*, so an
   unchecked sequence of fixes could drift upward. `GATE 2` should be made
   two-sided.

## 4. Field validation: what is and is not identifiable

The eight verified 2026 deliveries **cannot** identify a regime effect, and this
is a property of the data rather than of the analysis:

- Grain size is **perfectly collinear with regime** (Corn Belt 67 µm, paddy
  600 µm, Brazil 120 µm) and nested in operator.
- Application rate is collinear with grind too: corr(ln rate, ln p50) = +0.60.
- Independent cluster count: **4**, one a singleton.
- Within-operator rate slope: **−0.01 ± 0.57**.

So rate, grind, operator and regime are four labels for approximately one degree
of freedom. `FW_RATE_EXPONENT_OBSERVED = −0.58` is that one contrast, and must
not be used to normalise for rate — doing so removes the grind contrast twice.

### The constancy test, amended

Fitting λ separately per deployment and publishing the spread is worth doing, but
because grind is nested in operator the pooled spread conflates site-to-site
variability with grind mis-specification. **Only the within-cluster spread is
interpretable** (Mati's 3 sites, Lithos's 3 bins — **RESOLVED 2026-08: the bins are
all p50 = 67 µm, so they are not grain-size bins.** They are a rate contrast at fixed
grind, 25 / 50 / 47 t/ha, and two of them sit 6% apart in rate with fractions
weathered differing 2.1× — which is the direct evidence that the pooled −0.58 is not
a rate effect. Original text follows: confirm whether the Lithos
bins are sites or grain-size bins first, because if they are grain-size bins they
are the best grind test in the set). Pre-register that.

### Minimum identifying designs, with power

Residual SD in ln(fw) after removing an operator mean and a common rate slope:
**σ ≈ 0.455** (≈1.58× multiplicative, df = 3, so σ itself is uncertain — treat as
order of magnitude). At α = 0.05, 80% power:

| Target contrast | Unpaired, per group | Within-site blocked |
|---|---|---|
| 1.5× | ~20 deliveries | ~5 pairs |
| 2× | ~7 deliveries | ~2 pairs |
| 3× | ~3 deliveries | ~1 pair |

An observational cross-operator comparison therefore needs ~20 deliveries per
regime to see a 1.5× effect, i.e. 40–80 for a balanced design. That will not
exist. The identifying designs are small and blocked:

1. **Split-field, two grinds, one site.** Same feedstock, rate and reporting
   period. n = 3–4 sites × 2 grinds. The only way to separate λ from regime, and
   the highest-value experiment available.
2. **Flooded versus drained pair at one site.** The only clean test of the
   η_DIC/paddy mechanism, which is the map's most distinctive claim.
3. **Two rates within one grind at ≥3 sites.** Recovers the rate exponent that
   −0.58 currently misattributes. **Note the Lithos bins are now known to be a rate
   contrast at fixed grind and they do NOT deliver this** — the within-bin scatter
   exceeds the rate signal — so this ask is still open and needs a designed split.
4. **One deployment on alkaline (pH > 7.5) or arid cropland.** Zero of the eight
   sample where the model departs most from Cascade, so the covariate envelope
   has no leverage on the claims being made. Even n = 1 is a qualitative
   falsification test there.

Items 1–3 are ~10–14 additional deliveries as blocked contrasts against ~60
observationally. That ratio is the argument to put to operators.

### Also needed, and cheap

- **Measured PSD and BET for any real feedstock.** Both are now mandatory under
  Isometric's Feedstock Characterization Module v1.2 (Apr 2026) and Puro's
  quantitative XRD requirement, so the data should exist in recent verification
  dossiers. BET alongside PSD collapses the largest uncertainty in the product
  directly instead of fitting λ.
- **One measured paddy drainage-water DIC or alkalinity export flux.** That
  single number decides whether the Fe-redox seasonal term is first-order or nil.

## 5. Known asymmetries and open audit items

- **The drainage-concentration ceiling is OFF pending external review (2026-08-03),
  so the shipped map violates a bound this repo computes and documents.** On 91.0%
  of cropland area the CO₂ layer exceeds what the drainage could carry, by a median
  factor of 2.9×. (Both figures fell when the drainage variable changed from
  groundwater recharge to total runoff in August 2026 — the ceiling scales with `q`,
  so a larger water flux raises the bound faster than it raises the rate. On
  recharge it was 98.9% of area at 6.2×.) This is a deliberate, reported state, not an oversight: gate 12
  prints the exceedance on every build, the Methods panel carries a flagbox, the
  viewer exposes the bound as a live toggle under Advanced so a reader can see its
  consequence without a rebuild, and `FLUX_CEILING_ON = True` restores enforcement
  in the derived products in one line. The reason to hold it
  is that it moves the absolute level several-fold and that judgement is worth
  outside scrutiny — but while it is off, **no absolute CO₂ figure from this map
  should be quoted without that caveat.**
- **The ceiling-on total now sits INSIDE its pre-registered Tier 2 band, and the
  band was never widened to achieve that.** With the ceiling imposed, global gross
  removal is **0.910 GtCO₂/yr** against a pre-registered 0.5–4.0; with it off, 2.488,
  also inside. Reported by gate 2b in the build, not enforced.

  This is a reversal worth stating plainly. Through 2026-08-03 the ceiling-on total
  was **0.360 GtCO₂/yr**, below the band, and this document argued at length that
  falling below was the expected consequence of imposing a bound the comparison
  literature lacks. That argument still holds on its own terms, but the specific
  shortfall was substantially an artefact of using groundwater recharge for `q`:
  the ceiling is `q · [HCO₃⁻]_max · 44`, so understating the water understated the
  bound directly. Correcting the drainage variable moved the ceiling-on total 2.5×,
  into the band, without touching the ceiling itself. Two lessons: a pre-registered
  band did its job by surviving un-widened, and a result that reads as a deep
  finding can still be carrying an input error.

  Widening the band to fit would defeat the purpose of pre-registering it. The
  substantive point is in §2's own wording — the published range is "Consistency,
  NOT validation… several estimates descend from the same rate-law and surface-area
  lineage as ours" — and those estimates are not bounded by drainage transport
  either. Beerling et al. 2024's CDR_pot implies ~29.8 mmol/L bicarbonate at
  Illinois tile drainage, essentially the figure this model produced before the
  ceiling. Falling below a band derived from that lineage is what imposing the bound
  is supposed to do, but it does mean that under the ceiling the map has no external
  consistency check on its absolute level, and the field trials are the only anchor.
  Note the uncomfortable symmetry: with the ceiling OFF the map passes the band, and
  with it ON the map fails the band but satisfies the physics. Passing that band is
  therefore not evidence of anything.
- **The trial comparison is not like-for-like on application rate, and the obvious
  fix is invalid.** The map applies **30 t/ha**. The trials do not share a single
  rate: they span roughly 20 to 200 t/ha, and only some are at or near the map's
  rate. **Application rates per trial are being corrected by ZH — do not rely on the
  per-trial rates quoted elsewhere in this repo until that is done.** The figures I
  previously wrote as a "0.05–0.15 tCO₂/ha/yr" band were produced by normalising
  several trials to 20 t/ha linearly, which is precisely the operation this bullet
  warns against, so that band should not be treated as a measured range.

  What survives the correction, and why it is worth stating separately: measured
  per-tonne efficiency is **sublinear** in application rate, so rescaling any trial
  to the map's rate by a simple ratio manufactures agreement that does not exist. In
  either direction. The one comparison that is rate-insensitive here is the flux
  ceiling itself — the map's capped median moves only **0.478 → 0.510 tCO₂/ha/yr
  from 20 to 30 t/ha**, because the ceiling does not scale with how much rock is
  applied. (It was flat at 0.220 for both rates until the drainage variable was
  corrected in August 2026; total runoff raises the ceiling, so it now binds on 91.0%
  of area rather than 98.9% and leaves the rate a little room. Still an 8.6% gain in
  capped global total for 50% more rock.) So conclusions that rest on the ceiling are
  nearly unaffected by the rate change; conclusions
  that rest on comparing absolute tonnages to trials are not, and need matched rates.
- **Seven of the eight verified deliveries report CDR/ha above their own drainage-
  concentration ceiling, by 0.6–7.8×** (1.3–3.9× restricting to the three
  independently measured rows). The eighth is the wettest site in the set and its
  reported CDR *is* carryable in its own drainage. On the recharge-based drainage
  used until August 2026 the range was 3–19×, and all eight exceeded — so the
  qualitative claim weakened when the drainage variable was corrected, and
  `analyse_deployments.py` asserted "EVERY deployment exceeds" for one build until
  the count was made computed. Its exceedance column also rounded to whole
  multiples, printing the 0.6× row as "1x". Reported by section 11 of `analyse_deployments.py`. This is *not*
  an over-crediting finding: those figures are dissolution-based, so the comparison
  is "how much rock dissolved" against "how much carbon the water could carry", and
  both can hold at once. What it establishes is that **dissolution-based CDR/ha
  cannot be read as export without a retention term**, which closes the standing
  question in to_do item 4, and that this delivery set therefore cannot anchor the
  map's absolute level. The map's own calibration anchor inherits the same problem.
- **The drainage-concentration ceiling is unvalidated on paddy cells.** The
  protocol's mandated 50,000 µatm lifts it to 13–18 mmol/L at the shipped Ω,
  above all five anchors, and the literature contains no measured floodwater
  alkalinity or paddy lateral DIC export flux to check it against — every
  ERW-in-paddy trial reached measured only solid-phase carbon. Reported by
  gate 13c rather than tolerance-fudged. Affects ~7.6% of cropland area, and it is
  the loosest part of the term, so it constrains those cells least. Standing
  justification for field-data ask #6.
- **Ω = 10 versus Ω = 1 is a real order-of-magnitude-adjacent choice, not a
  detail.** It moves the cropland median from 0.240 to 0.510 tCO₂/ha/yr. Both are
  reported by the build, and the shipped value is the *generous* one, so the level
  is conservative toward the model rather than against it. There is no measurement
  that discriminates between them in an amended agricultural soil.
- **Gate 12 is a tautology once the cap is applied, by design.** It cannot
  discover that the ceiling is right; it can only catch someone removing the cap,
  reordering the operations, or adding a path that writes CDR without bounding it.
  Counting it as validation evidence would be a category error.

- **No gap ledger exists.** The claim that the CO₂ gap narrowed "without being
  tuned" rests on recollection. Going forward, record per commit: median CDR, the
  field gap, and whether the change was justified by a criterion independent of
  the field comparison. If accepted changes are systematically gap-narrowing
  while independently-justified ones are sign-random, that is the signature of
  selection.
- **The field-comparison inputs are gitignored**, so a third party cannot audit
  that claim even in principle. Legitimate confidentiality, but it means the
  claim is "asserted, inputs not redistributable", not "verified".
- **The SOC exceedance probability is a far-tail extrapolation.** The threshold
  sits at z ≈ 2–4 where three central quantiles carry essentially no information,
  so the reported 0.04% excluded and 53% marginal are properties of the assumed
  lognormal tail. A distribution-family sensitivity is owed. The lognormal's
  own over-identification (log q50 should equal the mean of log q05 and log q95)
  is a free goodness-of-fit statistic and is not currently computed.
