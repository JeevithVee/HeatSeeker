# Data audit: why planting shows no temperature change (Agent 1, 2026-11-14)

Question from the humans: the evaluation does not detect a temperature change
from tree planting; is the data the reason? Short answer: yes, mostly. The
data is clean in the narrow sense (counts reconcile, tables rebuild from
bronze exactly). The problem is what it can and cannot represent.

Inputs: the silver tables at NYC 72b5b1a / other cities ea5fcf0 (the rows now
in `heatseeker.silver.*` version 1), the four panels at agent-2-satellite
3fd6870, gold from `main`, and the raw tree records in `heatseeker.bronze.*`.
Scripts: `data_audit_*.py` beside this file. "Usable scenes" means Landsat
8/9, June-August, city coverage >= 0.5, cell >= 70% clear, as in the
evaluation.

## The six problems, most important first

### 1. The planting is far too thin for the unit we measure

A site is a 10-hectare hexagon. Treated cells received:

| City | Treated cells | Median trees 2015-19 | 90th percentile | Trees per hectare |
|---|---:|---:|---:|---:|
| NYC | 1,111 | 15 | 31 | 1.4 |
| DC | 1,010 | 26 | 49 | 2.5 |
| Seattle | 667 | 18 | 38 | 1.9 |
| SF | 153 | 14 | 29 | 1.3 |

DC's records carry a measured crown area per tree. Trees planted 2015-2019
now have a median crown of about 14 to 36 m2 (2019 plantings smallest). At
25 m2 a tree, the median treated cell gained new canopy over **0.3% to 0.6%
of its area**.

Our own tables say how much surface temperature moves with canopy: across
cells, about -15 K per 100% canopy (-5 to -7 K holding paved share fixed;
SF is about twice as steep). So the expected effect in the median treated cell is:

| City | Expected cooling, median treated cell | One cell, one scene: noise | Smallest effect a single site can show (gold `mde_k`) |
|---|---:|---:|---:|
| NYC | 0.02 to 0.05 K | 1.19 K | 1.96 K |
| DC | 0.04 to 0.10 K | 1.24 K | 1.47 K |
| Seattle | 0.02 to 0.08 K | 1.17 K | 1.56 K |
| SF | 0.04 to 0.10 K | 1.22 K | 2.36 K |

The signal we are looking for is 20 to 100 times smaller than what one site
can resolve, and about the size of the pooled uncertainty (roughly 0.07 to
0.15 K). A pooled NYC estimate of -0.07 K is what this arithmetic predicts
for a real effect, and also what noise produces. Only 13 NYC cells, 51 DC,
16 Seattle and 0 SF cells received 60 or more trees.

### 2. A planting record is not a canopy gain

- **Trees die or are removed.** NYC: 20% of 2015-2019 plantings are already
  recorded as removed or dead (26% of the 2015 cohort). Seattle: 16%.
- **Many plantings are replacements.** NYC: 28% of 2015-2019 plantings went
  into a planting space that already held a removed tree, and 37% of all
  dated plantings share a space with another tree record. DC: trees planted
  2022 or later show a median recorded crown of about 45 m2 on a 2-inch
  trunk, which can only be the previous tree's crown.
- **We cannot see growth.** NYC's recorded trunk diameter is 3 inches at the
  median for every planting year from 2015 to 2026, so it is the size at
  planting, never updated.
- **The canopy layer does not register any of it.** Measured canopy
  (NLCD, 30 m) did not rise in planted cells in any city: the 2014-2024
  change by planting level runs from +0.2 to -1.5 points, and its
  correlation with trees planted is between -0.10 and +0.21.

### 3. The canopy feature is blind to street trees

Across developed cells, the number of inventory trees and the canopy fraction
are uncorrelated (NYC -0.04, DC -0.11, Seattle +0.01, SF -0.33). In NYC,
1,229 of the 2,531 cells with 150 or more street trees show under 5% canopy;
in SF, 290 of 431. The layer sees woodland and large parks, not street
trees. It is used to match controls and to choose candidates ("low canopy"),
and "canopy gain" was meant to be a model input; none of these can work
with it for street planting.

### 4. There are no comparable unplanted cells

- **Nearly every residential cell is planted.** 90% to 97% of populated,
  developed cells have dated plantings. Cells with 2 or fewer trees ever
  number 740 in NYC, 41 in DC, 196 in Seattle, 140 in SF among those.
- **So controls are a different kind of place.** 45% to 80% of control cells
  have no residents. They carry 3 to 43 inventory trees against 150 to 210 in
  treated cells, with far less pavement. Treated cells run 3.3 to 5.0 K
  hotter than the control pool, and that gap swings by 0.6 to 1.2 K from one
  scene to the next with the weather. That swing alone is ten times the
  expected signal.
- **Controls border planted cells.** 61% to 82% of control cells touch a cell
  with dated plantings.
- **Controls contain undated plantings.**
  - NYC: 75,756 standing trees with a trunk of 3 inches or less have no
    planting date, all recorded since 2015. That is more than twice the
    33,203 dated 2015-2019 plantings. 43% of control cells hold at least one;
    12% hold ten or more.
  - Seattle: about 8,300 trees dated 1 January 2015-2019 were dropped as
    placeholders but are real trees.
  - SF: 25% to 53% of trees dated 2017-2019 have no coordinates and are not
    in any cell (2018: 53%).

### 5. Planting dates are weaker than they look

- **NYC dates begin in September 2015.** "2015" is one autumn. Nothing is
  known about planting before that, though the city planted heavily from
  2007, so every cell's earlier history is invisible.
- **Planting did not stop at the window.** The median treated cell received
  more trees after 2019 than during 2015-2019 in NYC (20 against 15) and DC
  (34 against 26). The dose the evaluation uses is less than half the trees.
- **Seattle's dates may not be planting dates.** 55% to 75% of dated
  2015-2019 trees are privately owned, 41% to 65% are dated June to
  September, which is not planting season, and for 2016-2019 9% to 20% have
  a planted date identical to the last-verified date.
- **DC and SF list standing trees**, so failed plantings are missing.
- 52% of NYC cell-years are autumn plantings, which cannot affect the same
  year's summer scenes; the evaluation's one-year gap handles this.

### 6. The satellite record is thin before planting and smooth in space

- **Few scenes before planting.** Usable 2013-2014 scenes: NYC 11, Seattle
  11, DC 3, SF 3. 2018 has 1 or 2 scenes in three cities.
- **Late morning only.** Overpass is about 10:30 to 11:00 local time, before
  the hottest part of the day, when shade matters least to surface
  temperature.
- **Neighbouring cells are not independent readings.** A cell's
  scene-to-scene anomaly correlates 0.94 to 0.95 with the average of its six
  neighbours. The thermal sensor's native pixel is about 100 m and the
  weather pattern is smooth, so the noise is shared locally. Controls drawn
  from across the city do not cancel it; adjacent cells would, but they are
  planted too (see 4).
- **A little cloud remains.** 19 NYC and 142 Seattle usable rows read below
  15 C on a summer late morning. The evaluation trims cold outliers.

## What this means

The method is not failing to find something the data contains. Street-tree
planting at one to three trees per hectare, measured on 10-hectare cells with
30 m morning surface temperature and no comparable unplanted cells, should
produce a number near zero whether or not the trees cool anything.

## What would give the loop a real chance

1. **Measure where planting is concentrated.** New parks, block-scale
   plantings, or the few dozen cells with 60+ trees; or shrink the site to
   the planted street segment.
2. **Use measured canopy change as the treatment**, from lidar or high
   resolution imagery (DC already records crown area per tree), not a count
   of planting records.
3. **Compare each site with its neighbours**, which removes most of the
   noise, after fixing the undated-planting gaps that contaminate them.
4. **Add afternoon thermal data** (ECOSTRESS was the stretch goal) and more
   pre-planting scenes.
5. **Replace the canopy feature** with one that sees street trees before
   using it to match controls or choose candidates.
