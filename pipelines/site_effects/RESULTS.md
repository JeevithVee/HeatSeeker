# Verified four-city evaluation — method 0.3.0

Surface temperature is not felt or air temperature. Negative Kelvin differences mean cooler surfaces.
These observational comparisons are provisional. Site labels are not adjusted for multiple testing.
All four cities are temperate. Method 0.2.0 results and earlier synthetic expectations are superseded.

## Completed cloud runs

- Final headline run: `5222250658819`, SUCCESS; 27 tests and four city tasks passed.
- Final all-sensor run: `149976888548281`, SUCCESS; 27 tests and four city tasks passed.
- Gold: `heatseeker.gold.site_effects`, 5,882 rows, Delta version 10, method 0.3.0.
- Typed CSV matches gold exactly in both directions; companion CSV/Parquet values match exactly.
- Robustness outputs were checked independently and did not change headline gold version 10.
- Both final runs read `heatseeker.silver.panel VERSION AS OF 0`; gold `panel_version` is the string `0`.
- Features/interventions came from checksum-verified owner files: NYC commit `72b5b1a`, other cities `ea5fcf0`.
- Source snapshot: `a5405c5ae6f07b7954476c72720fb771ed133e3142a078323259eb120e6b0648`.
- Earlier file-input cloud runs `1044546343814209` / `1100247180142541` also passed. Their scientific values match the final runs; the final runs improve panel provenance.
- Full silver-only mode remains available when feature/intervention tables are published. It has unit coverage for pinning all three versions; it has not been exercised against those absent tables.

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

## All-sensor robustness

Older Landsat 5/7 add pre-period observations. They retain the same city baseline and strict June–August filter.

| City | Scenes | Treated cells | Detected | Descriptive overall K | Descriptive five-year-plus K |
|---|---:|---:|---:|---:|---:|
| NYC | 125 | 1111 | 13 | -0.112 | -0.146 |
| DC | 71 | 1011 | 59 | +0.198 | +0.209 |
| SEA | 144 | 667 | 18 | -0.263 | -0.246 |
| SF | 56 | 153 | 0 | +0.129 | +0.124 |

The extra DC cell has sufficient observed data only when older sensors are included. Robustness is not a replacement for headline gold.
NYC all-sensor source-block envelopes also cross zero at their widest choices. Full grid results are in the JSON reports.

## Delivery and downstream use

- `out/<city>_gold_site_effects.parquet` and `.csv`: headline rows for NYC/DC/SEA/SF.
- `out/<city>_site_effects_report.json`: diagnostics, source-block sensitivities, runtime, configuration and complete input/code provenance.
- `out/<city>_site_effects_report_all_sensors.json`: robustness diagnostics.
- `out/input_manifest.json`, `evaluation_runs.json`, verification receipts and `artifact_checksums.json`: audit trail.
- All-sensor site rows remain in their distinct cloud run directory; they are intentionally not published over headline gold.
- Agent 4 should rebuild outputs previously based on method 0.2.0. Inspect matching balance before learning from these differences; DC/Seattle/SF are exploratory and must not be presented as validated causal training targets.
- DC and SF can select surviving trees because historical removals are incomplete. Seattle has excluded unknown January-1 dates. No dated record does not prove a cell was never planted.
