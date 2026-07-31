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

`python3 scripts/test_kinetics.py` runs 16 gates. As of July 2026: **14 pass, 2
fail.** The count is close to meaningless without the breakdown:

| Category | Gates | What a pass means |
|---|---|---|
| **Independent test** | 11 | The rate law reproduces measurements it was not fitted to. **Currently FAILS.** |
| Internal consistency | 6c, 8, 10 | Two parts of our own code agree with each other |
| Literature reproduction | 1, 2, 2b, 2c, 4, 4b, 6 | We transcribed a published constant correctly |
| Invariants | 5, 9, 10 | The functions behave monotonically where physics requires |
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
| Cropland area vs Potapov et al. | 2% | gate 1, FATAL |
| Stoichiometric ceiling | hard bound, no tolerance | gate 3 |

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
   - **Out-of-sample element:** the fixture carries **Si and Fe**, which gate 11
     does not use. A single surface partition must reproduce all four elements at
     a given temperature — three fractions against four elements is
     over-identified, which makes it a test rather than a fit. Do this before
     touching any activation energy.
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
interpretable** (Mati's 3 sites, Lithos's 3 bins — and confirm whether the Lithos
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
   −0.58 currently misattributes.
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
