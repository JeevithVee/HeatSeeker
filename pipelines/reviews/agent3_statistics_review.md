# Cross-review of Agent 3's statistics (by Agent 1, 2026-11-14)

Reviewed: `core/evaluation` at `agent-3-eval` 651b00d (method 0.3.0), on the
panels at `agent-2-satellite` 3fd6870 and the silver CSVs in
`ingest/us/samples`. Scripts are beside this file; each takes
`<agent-3 checkout> <dir with <city>_panel.parquet> <this repo>`.
Runs used 60 bootstrap and 300 placebo draws (10 and 40 for the year
jackknife), which affects labels and intervals but not point estimates.

## Verdict

The code does what it says and the published numbers reproduce exactly. The
written conclusions in `RESULTS.md` are appropriately cautious. Three things
should change what is claimed, all in the direction of claiming less:

1. NYC's pooled cooling is not robust to two reasonable specification changes.
2. A fake-date test on NYC finds a "cooling effect" three times the real one
   before any of the trees existed.
3. The pooled intervals leave out year-to-year variation shared by all sites.

Seattle's negative contrast survives every check I could run on it, but it
could not be put through the fake-date test, and its controls are
contaminated by undated plantings.

## What checks out

- **Reproduction.** `effect_k` for every site in all four cities matches the
  published gold to 0.0 K (1,111 / 1,010 / 667 / 153 sites).
- **Estimator.** Per-scene treated-minus-controls differencing cancels the
  scene's city-wide level exactly. The year-0 donut is sensible.
- **Control pool.** The full-record rule (at most 2 trees ever) is correctly
  implemented after the 0.3.0 fix.
- **Placebo gate on labels.** Requiring both the bootstrap interval and the
  placebo test is right; the bootstrap treats scenes as independent and alone
  would overcall. NYC's 16 detections out of 1,111 are below the chance rate,
  so no individual NYC cell should be shown as a proven success.
- **Block jackknife.** Formula is correct, and deleting treated and control
  trajectories together handles reused controls.

## Findings

### 1. NYC's pooled estimate depends on the specification

Pooled mean `effect_k`, sites with minimum support, headline sensors:

| City | Published spec | No matching on pre-period temperature | Outcome scaled by each scene's spatial spread |
|---|---:|---:|---:|
| NYC | -0.074 | -0.012 | -0.034 |
| DC | +0.172 | +0.168 | +0.226 |
| Seattle | -0.185 | -0.177 | -0.191 |
| SF | +0.139 | +0.199 | +0.105 |

Matching controls on the treated cell's pre-period temperature level and
slope uses the same noisy pre-period data that the estimate then differences
against. When treated cells and the control pool come from different
populations, that selects controls whose pre-period values are unusually
close by chance, and they drift back afterwards (regression to the mean).
The placebo test cannot see this, because placebo cells are drawn from the
control pool and matched to other control-pool cells, the same population.
Dropping that matching takes NYC to about zero. Scaling by scene spread
(hotter scenes stretch every contrast) halves it. Seattle, DC and SF barely
move.

### 2. Fake-date test on NYC

Every real 2015-2019 planting was pretended to happen in 2010, using
Landsat 5 only, 2008-2011 (pre 2008-2009, post 2011). None of the trees
existed. The published method gives:

- pooled "effect" **-0.239 K** over 726 cells, 33 "detected";
- block-jackknife intervals that exclude zero at all four grids
  (from [-0.375, -0.103] to [-0.426, -0.053]);
- a control-pool placebo mean of -0.148 K, so the null is not centred either.

Without pre-period temperature matching it is -0.252 K. So in this window the
method reports significant cooling where there can be none, and at three
times the size of the real NYC estimate. Caveats: only 18 scenes, a single
post year, and an older sensor with coarser thermal pixels, so this bounds
how wrong the method can be on thin data rather than measuring the bias of
the 99-scene headline. DC, Seattle and SF have too few Landsat 5 scenes to
run it. A first version that mixed sensors (pre on Landsat 5/7, post on
Landsat 8) gave -0.248 K for NYC and -0.117 K for Seattle, but there the
sensor change lines up with the pre/post split, so I do not rely on it. The
same alignment exists in the published all-sensor robustness run, whose
estimates are more negative than the headline in NYC and Seattle; it should
not be read as independent confirmation.

### 3. Year-to-year variation is missing from the pooled intervals

All sites share the same scenes. If the treated-minus-control contrast swings
with a year's weather or greenness, every site moves together, and neither
averaging over sites nor a spatial jackknife shrinks it. Leave-one-year-out
jackknife of the pooled headline (rematching each time):

| City | Point K | Year-jackknife SE | Interval K | Most influential year |
|---|---:|---:|---:|---|
| NYC | -0.074 | 0.049 | [-0.171, +0.023] | 2013, 2024 |
| DC | +0.172 | 0.166 | [-0.153, +0.497] | 2015, 2022 |
| Seattle | -0.185 | 0.082 | [-0.346, -0.024] | 2013, 2014 |
| SF | +0.139 | 0.242 | [-0.335, +0.613] | 2024 |

This is about as large as the spatial component and is separate from it, so
the two should be combined, not the wider one picked. For NYC that gives
roughly +/-0.15 K around -0.07 K. Seattle's estimate leans on its two
pre-period years, 2013 and 2014.

### 4. Things the data cannot rule out (from the data side)

- **NYC pre-2015 plantings are invisible.** Planting dates start in 2015, but
  the city planted heavily from 2007. Those trees are maturing through the
  whole study period in treated and control cells alike, and if the same
  streets were planted before and after 2015, their growth is attributed to
  the 2015-2019 plantings.
- **Dose is not fixed at the window.** NYC plantings doubled after 2020, and
  treated cells keep receiving trees. `dose_trees` counts 2015-2019 only, so
  "effect at 5+ years" mixes later plantings in, which may be why there is no
  dose gradient.
- **Seattle controls.** About 8,300 trees dated 1 January 2015-2019 were
  dropped as placeholders, so some control cells were planted.
- **DC and SF** list mostly standing trees; plantings that died are missing.
- **DC's pre-period is three scenes** for 2015 plantings (Landsat 8/9, 2013-2014).

## Recommended changes

1. Report the no-pre-outcome-matching estimate beside the headline, and treat
   the gap between them as specification uncertainty.
2. Add the fake-date test as a standing diagnostic where scenes allow, and
   say in results that it fails for NYC on 2008-2011.
3. Add a year-block component to the pooled interval.
4. Drop "robustness" from the all-sensor run's description, or restrict it to
   estimates whose pre and post periods use the same sensor family.
5. Wording for the app and pitch: no city shows an established cooling
   effect. NYC is indistinguishable from zero; Seattle shows a negative
   association that is not yet a causal estimate.

None of this needs a schema change.
