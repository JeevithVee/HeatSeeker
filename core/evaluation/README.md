# Evaluation engine — Prove

`core.evaluation` estimates H3-cell surface-temperature differences against matched controls.
It is country-neutral pandas/numpy code. The wrappers in `pipelines/site_effects` supply the
standard tables and publish the frozen `gold.site_effects` columns.

## Method 0.3.0

1. Keep June–August Landsat 8/9 observations with cell valid-pixel fraction >= 0.7,
   whole-scene cloud fraction <= 0.6, city clear fraction >= 0.5 and at least 200 observed
   cells. Landsat 5/7 are a separate robustness run; Landsat 7's per-cell threshold is 0.5
   because of striping gaps. ECOSTRESS is never mixed into this estimate.
2. Subtract the city median within each scene. Trim cold outliers below six scene MADs;
   retain hot roofs. Per-site contrasts use only scenes with at least half the matched
   controls observed, so partial coverage is handled on both sides.
3. Treatment year is the first year cumulative 2015–2019 plantings reach ten trees.
   Dose is the total in that window. Controls have at most two dated trees across the
   **entire available planting record**, including before 2015 and after 2019.
   Water/wetland-dominated cells are excluded from both groups. The robustness variant
   excludes treated cells with more than half their window dose batch-flagged.
4. Match ten controls by standardized canopy, impervious fraction, elevation, pre-period
   temperature level and slope. Match land-cover class exactly when at least ten same-class
   controls exist; otherwise use the broader eligible pool. There is no distance caliper:
   inspect balance rather than assuming every nearest match is substantively comparable.
5. Compute treated minus control mean within each scene, then post minus pre. The treatment
   year is excluded. The event study groups those contrasts by years since treatment.
6. Bootstrap pre scenes, post scenes and matched controls for the per-site standard error
   and 95% interval. Fake treatment dates on controls provide a second, empirical null.
   Minimum detectable effect is the maximum of `2.8 * bootstrap SE` and
   `placebo abs-q95 + 0.84 * placebo SD`.
7. `detected` requires enough observations/controls, an interval excluding zero and a finite
   placebo p-value < 0.05. Missing placebo evidence cannot produce a detection.
   `not_detectable` means no detection despite an MDE <= 1 K; otherwise the result is
   `inconclusive`. These site labels are not adjusted for multiple testing.

**Version correction:** 0.2.0 accidentally defined controls using only 2015–2019 plantings.
Its NYC findings and synthetic expectations are superseded. Version 0.3.0 fixes that bug;
regression tests explicitly exclude early, late and cumulatively planted controls. A
batch-excluded treated site is never reintroduced as a control.

## Pooled uncertainty and diagnostics

`pooled_by_dose` retains descriptive across-site means and independence-assuming SEs for
compatibility. Do not present those SEs as spatially adjusted confidence intervals.

`pooled_block_sensitivity` deletes geographic source blocks at prespecified 2 km and 5 km
sizes, each with zero and half-block shifted origins. Each deletion removes complete
trajectories of both treated and control cells, and removes a reused control from every
matched set at once. It then recomputes the fixed-match contrasts and coverage checks.
This differs from resampling treated effect rows alone, which misses reused-control effects.

For G blocks, the delete-one variance is `(G-1)/G * sum((theta_minus_g - mean(theta_minus_g))**2)`.
The report supplies conditional normal-approximation sensitivity intervals. A grid needs at
least ten blocks, finite deletion estimates, and at least 80% retention of the original
supported sites in every deletion. Unsupported grids return no interval. The pooled set
requires the same minimum scenes and controls as the per-site labels. Five-year-plus effects
first average eligible event-year effects within each site, then average sites equally.

These are **sensitivity diagnostics**, conditional on fixed matches and the observed scenes.
They do not account for rematching uncertainty, every possible correlation across block
boundaries, observational confounding, unknown planting dates or survivorship bias. Block
sizes are not chosen after looking for significance. No causal claim follows from the interval.

The report also records actual eligible-control counts, reused-control counts, matching
balance, valid placebo counts and descriptive pre-period slopes. The old pooled pre-period
mean is centred near zero by construction; it is not a parallel-trends test. Slopes use the
same pre-data used for matching, so they are descriptive rather than an independent test.
Likewise, alpha times the number of sites is a reference, not a calibrated expected false
positive count for the combined bootstrap/placebo gate.

References for the variance construction and spatial block-size limitations:
- [Efron and Stein, The Jackknife Estimate of Variance](https://statistics.stanford.edu/technical-reports/jackknife-estimate-variance)
- [Nordman and Lahiri, On optimal spatial subsample size for variance estimation](https://arxiv.org/abs/math/0503671)

## Reading results

Negative `effect_k` means cooling in Kelvin differences of **surface temperature**. Surface
temperature is not felt or air temperature. `effect_k` averages the whole post period;
`event_study_json` describes age-specific differences. A non-detection is not proof of no
cooling. Thirty-metre Landsat cannot reliably resolve individual street trees.

All four cities are temperate. Seattle controls may contain real plantings with unknown
January-1 dates. DC and San Francisco inventories miss some historical removals and can
select survivors. A cell without a dated record is not necessarily a genuinely unplanted
cell. Preserve these limitations alongside model outputs and recommendations.

## Validation

`../.venv-agent3/bin/python -m pytest core/tests -q`

The permanent synthetic recovery test checks bias, correlation and false detections against
known truth. Additional tests cover full-record controls, missing placebo evidence, source
checksums, pinned Delta reads, atomic gold loading and spatial/source-block support. The
block jackknife is tested against an analytically known independent-block mean SE and a
shared-control example whose support disappears when the common control block is deleted.
The same suite runs as the first task of the Databricks job.
