# Verified four-city evaluation — method 0.3.0

Surface temperature is not felt or air temperature. Negative Kelvin differences mean cooler surfaces.
These observational comparisons are provisional. Site labels are not adjusted for multiple testing.
All four cities are temperate. Method 0.2.0 results and earlier synthetic expectations are superseded.

## Completed full-silver cloud runs

- Headline plus standing review diagnostics: `1123694992477746`, SUCCESS (34 tests and all four city tasks). It reads silver.interventions version 2, which includes one app-logged planting promoted by the build job (the Plan→Plant→Prove loop run live); versus the previous run `606115661672539` on interventions v1, 3 NYC effect values changed and no labels.
- Cross-sensor sensitivity: `598786481893891`, SUCCESS; 34 tests and all four city tasks passed.
- Gold: `heatseeker.gold.site_effects`, 5,882 rows, Delta version 22, method 0.3.0.
- Every city reads pinned Delta snapshots: panel 0, features 1, interventions 2. The job now defaults to silver-only inputs.
- Typed CSV matches gold exactly in both directions; companion CSV/Parquet values match exactly.
- Every scientific gold value exactly reproduces the prior mixed-input delivery; evaluation timestamps changed.
- Cross-sensor output contains 5,884 rows in its separate run directory and preserved headline gold version 18.
- Analysis source hash: `3ed3f2c83aa1a97583685f2eba6adf71d9be4162d1fe66546c41f51556fd0fb2`.
- Diagnostic version 1.0.0 adds review checks without changing the frozen gold columns or headline estimator.
- The first silver-only parity run `383042876269446` also succeeded and reproduced the old results exactly.
- Earlier mixed-input runs remain historical audit records; current outputs no longer depend on staged feature/intervention files.

## Headline: Landsat 8/9, June–August

Each cell has both variants. Their numeric results are identical because no treatment-window trees are batch-flagged.

| City | Treated cells | Controls | Scenes | Detected / inconclusive | Median MDE K | Max absolute SMD |
|---|---:|---:|---:|---:|---:|---:|
| NYC | 1111 | 1785 | 99 | 16 / 1095 | 1.88 | 0.132 |
| DC | 1010 | 237 | 50 | 66 / 944 | 1.47 | 0.812 |
| SEA | 667 | 400 | 117 | 20 / 647 | 1.56 | 0.359 |
| SF | 153 | 267 | 45 | 0 / 153 | 2.36 | 0.507 |

There are zero `not_detectable` rows. Preserve `inconclusive`; do not relabel it to fit a demo.

## Pooled source-block sensitivity

Points below use sites meeting minimum scene/control support. The range spans all supported normal intervals
across prespecified 2 km / 5 km blocks and two grid origins; it is a sensitivity envelope, not a calibrated
combined confidence interval. Controls and treated trajectories are removed together.

| City | Supported sites | Overall point K | Overall interval envelope K | Five-year-plus point K | Five-year-plus envelope K |
|---|---:|---:|---:|---:|---:|
| NYC | 1109 | -0.074 | [-0.187, +0.039] | -0.113 | [-0.256, +0.031] |
| DC | 971 | +0.172 | [-0.081, +0.426] | +0.198 | [-0.121, +0.517] |
| SEA | 666 | -0.185 | [-0.318, -0.052] | -0.159 | [-0.298, -0.020] |
| SF | 147 | +0.139 | [-0.182, +0.459] | +0.169 | [-0.162, +0.501] |

- NYC: overall and five-year-plus ranges cross zero under larger block choices. A reliable cooling effect is not established.
- DC: balance is poor (max absolute SMD about 0.81), and the larger-block ranges cross zero. Do not interpret the positive contrast as planting-caused warming.
- Seattle: conditional ranges stay negative, but balance is poor and unknown-date plantings can contaminate controls. This is a cooling association, not proof of a causal effect.
- SF: all site results are inconclusive, matching is poor, and 5 km grids lack enough block/support retention to return an interval. Its envelope above uses 2 km grids only.
- All intervals remain conditional on fixed matches and observed scenes; rematching uncertainty, across-block dependence and confounding are not resolved.

## Standing statistics-review checks

The independent review at `462e2b4` reproduced the original estimator exactly and identified important weaknesses. These are now standing backend diagnostics; the headline estimator stays unchanged.

### No matching on pre-period outcomes

Both points in each row use the same cohort supported under both matching specifications. Units are Kelvin surface-temperature differences.

| City | Common sites | Headline overall K | Static-feature matching only K |
|---|---:|---:|---:|
| NYC | 1109 | -0.074 | -0.012 |
| DC | 971 | +0.172 | +0.167 |
| SEA | 666 | -0.185 | -0.177 |
| SF | 147 | +0.139 | +0.199 |

NYC is near zero under the alternative specification. Matching on noisy pre-outcomes can induce regression to the mean; the alternative is a sensitivity estimate, not automatically the true causal answer.

### Same-sensor pre-cohort fake date

NYC: pretend the recorded 2015–2019 cohort was planted in 2010; use Landsat 5 only in 2008–2011, excluding 2010 from the contrast. The diagnostic reproduces **-0.239 K over 726 supported cells before the recorded cohort**, and its supported source-block intervals exclude zero. This challenges causal attribution. It does not measure the bias of the modern headline: the window is thin, has one post year, and contains other historical trees and changes.

DC, Seattle and SF lack the required same-sensor pre/post scene support. The diagnostic explicitly reports insufficient data rather than substituting another sensor family.

### Calendar-year and combined spatial/year sensitivity

Calendar-year deletions rematch controls. To compare the spatial and year components on the same estimand, the interval cohort must be supported in every deletion and retain at least 80% of baseline support.

| City | Common year-deletion sites | Retained | Year SE K | Combined overall sensitivity envelope K |
|---|---:|---:|---:|---:|
| NYC | 1057 | 95.3% | 0.048 | [-0.274, +0.146] |
| DC | 492 | 50.7% | withheld | withheld |
| SEA | 649 | 97.4% | 0.077 | [-0.470, +0.103] |
| SF | 104 | 70.7% | withheld | withheld |

The combined range adds spatial and calendar-year SEs on that common cohort (`SE_sum = SE_space + SE_year`), then spans the supported block/origin choices. It is a sensitivity construction allowing positive covariance in an additive-component interpretation. It is **not a calibrated multiway confidence interval**; components can overlap and dependence is not fully modelled. The NYC centre is -0.064 K (1,057 sites), Seattle -0.183 K (649 sites), rather than the larger headline cohort means. Both combined ranges cross zero.

DC and SF retain only 50.7% and 70.7% of baseline support across all year deletions. Their common-cohort intervals are withheld; the support rule was not relaxed to produce a number. Full all-supported deletion means remain in the JSON as descriptive diagnostics. This differs deliberately from the review’s changing-cohort jackknife.

### Later planting and interpretation

Post-window planting occurs in 1,076 NYC treated cells (26,526 additional recorded trees), 1,007 DC cells (36,817), 544 Seattle cells (5,098), and 142 SF cells (2,117). Long-horizon contrasts therefore mix later cohorts while `dose_trees` stops in 2019. NYC has unobserved pre-2015 planting history too.

No city has an established causal cooling effect under this design. Seattle retains a negative association under alternative matching, but identification, year uncertainty and source limitations remain. Model predictions inherit these limits.

## Cross-sensor sensitivity

Older Landsat 5/7 add pre-period observations. They retain the same city baseline and strict June–August filter.

| City | Scenes | Treated cells | Detected | Descriptive overall K | Descriptive five-year-plus K |
|---|---:|---:|---:|---:|---:|
| NYC | 125 | 1111 | 13 | -0.112 | -0.146 |
| DC | 71 | 1011 | 59 | +0.198 | +0.209 |
| SEA | 144 | 667 | 18 | -0.263 | -0.246 |
| SF | 56 | 153 | 0 | +0.129 | +0.124 |

The extra DC cell has sufficient observed data only when older sensors are included. This is cross-sensor sensitivity, not independent confirmation of the headline. Legacy sensor observations occur only in the pre-period, so sensor-specific spatial contrasts can align with the pre/post split.
NYC all-sensor source-block envelopes also cross zero at their widest choices. Full grid results are in the JSON reports.

## Delivery and downstream use

- `out/<city>_gold_site_effects.parquet` and `.csv`: headline rows for NYC/DC/SEA/SF.
- `out/<city>_site_effects_report.json`: diagnostics, source-block sensitivities, runtime, configuration and complete input/code provenance.
- `out/<city>_site_effects_report_all_sensors.json`: cross-sensor diagnostics.
- `out/input_manifest.json`, `evaluation_runs.json`, verification receipts and `artifact_checksums.json`: audit trail.
- Cross-sensor site rows remain in their distinct cloud run directory; they are intentionally not published over headline gold.
- Agent 4 should rebuild outputs previously based on method 0.2.0. Inspect matching balance before learning from these differences; DC/Seattle/SF are exploratory and must not be presented as validated causal training targets.
- DC and SF can select surviving trees because historical removals are incomplete. Seattle has excluded unknown January-1 dates. No dated record does not prove a cell was never planted.
