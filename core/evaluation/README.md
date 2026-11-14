# /core/evaluation — "Prove"

Did a planted H3 cell cool, relative to matched unplanted cells? Pure pandas/numpy; no Spark,
no H3, nothing country-specific. The Databricks job in `/pipelines/site_effects` feeds it the
silver tables and writes `gold.site_effects`.

## Method

1. **Scene filter** (`panel.py`). Keep clear-sky summer Landsat rows: June–August, sensor L8/L9,
   scene cloud ≤ 30%, cell valid-pixel fraction ≥ 70%, at least 200 cells covered. ECOSTRESS
   is never mixed in; if it is loaded later it is evaluated as its own panel.
2. **Relative temperature.** Each cell's LST minus the scene's city-wide median, in Kelvin.
   The city-wide scene effect (weather, time of year, calibration) cancels; what is left is how
   hot the cell runs relative to its city on that day.
3. **Treatment** (`treatment.py`). A cell is planted in the first year its cumulative count
   (from 2015) reaches `min_dose` trees (default 10); NYC plants a median of 5 trees per cell
   per year, so a single-year bar would miss steady planters. Only cells reaching the dose
   inside `treatment_window` (2015–2019) are evaluated; `dose_trees` is the window total. Cells
   with ≤ 2 trees over the whole record (all years to date) are the control pool, so cells
   planted after 2019 are excluded from it. Water- and wetland-dominated cells are excluded from
   both sides. Variant `excl_batch_dated` drops planted cells where more than half the trees
   were batch-dated entries (for NYC 2015–2019 nothing is flagged, so both variants agree).
4. **Matching** (`matching.py`). For each planted cell, the 10 nearest controls by standardized
   distance over canopy, impervious fraction, elevation, and the cell's pre-period relative
   temperature level and trend, with an exact match on land-cover class when enough candidates
   exist. Pre-period = scene years before the planting year.
5. **Difference-in-differences** (`did.py`). Per scene, `d = treated − mean(controls)`.
   `effect_k = mean(d | post) − mean(d | pre)`. Post starts the year after planting (the
   planting year itself is excluded: trees go in through the season and do nothing yet).
   The **event study** is the same difference grouped by years since planting.
6. **Uncertainty** (`inference.py`). Bootstrap over pre scenes, post scenes and the control set
   (200 draws) gives the standard error and 95% CI. **Placebo**: 200 unplanted cells get a fake
   planting year drawn from the real ones and are evaluated identically; `placebo_p` is the share
   of placebo effects at least as large as the site's.
7. **Labels** (`labels.py`).
   - `detected`: CI excludes zero and `placebo_p < 0.05`.
   - `not_detectable`: no effect found, and `mde_k ≤ 1.0 K` (the site had the precision to see
     a 1 K effect). `mde_k = 2.8 × SE` (80% power at 5%).
   - `inconclusive`: too few scenes (< 5 pre or post) or controls (< 3), or `mde_k > 1.0 K`.

## Sanity report

`evaluate_city_with_report` returns the gold rows plus a report (`report.py`) that the job prints
with every run: scenes kept per year, treated/matched counts, label counts, median MDE,
**pre-period pooled effect** (should be ≈ 0; if not, matching is failing), **control balance**
as standardized mean differences on the match variables (|SMD| < 0.1 good, < 0.25 acceptable),
the placebo distribution's mean and spread, and the pooled event study by years since planting.
Read it before believing the effects.

## Reading the output

- `effect_k` is the **average over the whole post period**. Tree effects ramp in over years, so
  a 2019 planting observed to 2024 shows a smaller `effect_k` than a 2015 one with the same
  trees. For the effect at a given age, use `event_study_json` (`{"years_since": effect_k}`).
- Negative = cooling. Units are Kelvin differences in **surface** temperature, not air or felt
  temperature (shared rule 14).
- With ~1 K per-cell scene noise and 10 controls, per-site MDEs are ~0.8–1.1 K. Sub-degree
  effects are real but cannot be confirmed site by site at 30 m; they show up pooled (Agent 4's
  effect model). Cells with many trees planted five or more years ago are the ones to look at.

## Permanent test

`core/tests/test_synthetic_recovery.py` builds a synthetic city (`synthetic.py`) with a known
ramping effect, zero-effect planted cells, batch-dated artifacts and rows that must be
filtered, then checks the engine recovers the effect (bias < 0.15 K, correlation > 0.7), does
not call null sites detected, and handles both variants.

```
python -m pytest core/tests -q
```

## Dry run on the real NYC grid

`synthetic.make_panel_for(features, interventions)` lays a synthetic panel (1 K noise, 6 scenes
per summer, 2013–2025, 1.5 K long-run effect per 40 trees) over Agent 1's real NYC features and
interventions. With `min_dose=10`: 1,111 treated cells, 3,872 controls, bias −0.01 K,
correlation 0.75, 1.7 s for both variants. Detection rate by dose, for a true effect of about
−0.3 K at 10 trees to −1.8 K at 50+:

| trees in cell | cells | detected |
|---|---|---|
| 10–15 | 581 | 15% |
| 15–20 | 227 | 28% |
| 20–30 | 189 | 55% |
| 30–50 | 87 | 95% |
| 50+ | 27 | 100% |

So per-site "detected" calls will concentrate in the ~300 cells with 20+ trees; the rest are
honestly `not_detectable` at the single-site level and feed the pooled model.

## Config

All thresholds live in `EvalConfig` (`config.py`). Prototype defaults: 200 bootstrap and 200
placebo draws. Raise both for the final run on Databricks.
