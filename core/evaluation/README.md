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
3. **Treatment** (`treatment.py`). A cell is planted in the first year it received ≥ `min_dose`
   trees (default 10). Cells with ≤ 2 trees ever are the control pool. Lightly planted cells
   are excluded from both sides. Variant `excl_batch_dated` drops planted cells where more than
   half the trees were batch-dated entries.
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

## Config

All thresholds live in `EvalConfig` (`config.py`). Prototype defaults: 200 bootstrap and 200
placebo draws. Raise both for the final run on Databricks.
