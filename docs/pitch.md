# HeatSeeker — Plan, Plant, Prove: pitch and demo script

Three minutes, five beats. Every number below comes from a gold table; say "surface temperature,
not felt temperature" at least once per beat. Precomputed replay of every screen lives in
`demo/data_real/` (the app falls back to it automatically if a live query fails).

## The one-line pitch

Cities spend millions planting trees to fight heat and almost never check whether it worked.
HeatSeeker tells a planner where to plant, logs what was planted, measures each site's effect
from 13 years of Landsat surface temperature against matched unplanted blocks, and feeds the
measured results back into the next recommendation. Plan, plant, prove, repeat.

## Where to click

| Surface | Where |
|---|---|
| App (Recommend / Track / Results) | https://heatseeker-7474650715825059.aws.databricksapps.com |
| AI/BI dashboard "HeatSeeker Portfolio" | Workspace → Dashboards (id `01f1e080008617ff8ba3af26fa258064`) |
| Genie space "HeatSeeker — ask the results" | Workspace → Genie (id `01f1e087c5881f388af2ec32a1711ff3`) |
| Model Serving endpoint | `heatseeker-effect-model` (UC model `heatseeker.gold.effect_model`) |
| Tables | `heatseeker.bronze.*` → `silver.{panel,features,interventions}` → `gold.{site_effects,site_reports,recommendations,prediction_log,app_planting_log}` |

## Beat 1 — "Here's where this city planted" (Track view, NYC)

- 1.1 million NYC tree records cleaned to 137k dated plantings, aggregated into 7,414 H3 cells
  (~0.1 km² each). 2015–2019: 1,111 cells received 10+ trees. Same pipeline ran DC, Seattle and
  San Francisco: four cities, 2,941 evaluated cells, all from bronze → silver inside Databricks.
- The Track form is the "Plant" step: a logged planting goes to a staging table and the build
  job promotes it into `silver.interventions` (we ran this loop live today: version 2 of the table).

## Beat 2 — "Here's what actually happened" (Results view)

Show three sites, each with its LLM site report (phrased from gold numbers only):

1. **A clear detection.** NYC cell `892a100d00fffff`: about 2.9 K cooler than its matched
   controls after planting (95% interval −3.6 to −2.1 K), placebo p 0.008. Label: detected.
2. **An honest "inconclusive".** Pick any inconclusive NYC cell: the report says no effect
   could be distinguished from noise and that anything smaller than ~1.9 K cannot show at 30 m.
3. **The headline truth.** Across 1,111 NYC cells only 16 are "detected", fewer than the ~56
   chance would produce. Per-cell detection is at the resolution limit; this is reported, not hidden.

Say it plainly: *no city shows an established causal cooling effect.* NYC's pooled contrast is
−0.07 K and moves to −0.01 K under alternative matching; Seattle shows a −0.19 K association that
does not survive year-deletion sensitivity. Zero rows were relabelled to look better.

## Beat 3 — "Here's what that taught the model" (dashboard)

- The effect model trains on all 2,941 evaluated cells, pooled across labels (training only on
  "detected" would select on significance). Features: canopy, impervious fraction, trees planted,
  years since planting. Predictions shrink toward the mean where similar past sites are few.
- Dashboard: what worked, cooling per dollar, and the limits panel. The model's predictions
  inherit the measurement limits; the app says so on every view.

## Beat 4 — "Here are next year's top recommendations" (Recommend view)

- 845 ranked candidate cells across four cities: low canopy, open or low-intensity developed
  land, score = predicted cooling × vulnerable residents ÷ cost (costs editable in `config/us`).
- Every fifth site is held out unplanted as a future control, so next year's "Prove" has a
  comparison group by design.
- Live scoring: the `heatseeker-effect-model` serving endpoint returns a predicted range at 5 and
  15 years for any cell a planner describes (canopy, impervious fraction, trees).
- Ask Genie: "Why was site 892a1000a2bffff recommended?"

## Beat 5 — "And here's how the tool grades itself" (prediction log + time travel)

- Every recommendation is logged in `gold.prediction_log` (845 rows) with the model version and
  the exact Delta versions of the tables it read (`panel_version` on every gold row). When a
  recommended site is planted and evaluated, the prediction is scored against the measured effect.
- Delta time travel means a planner can audit, years later, exactly what data each recommendation
  used.

## Caveats to say out loud

- Surface temperature is not air or felt temperature.
- Per-cell effects are at the detection limit of 30 m Landsat; the honest per-site label is
  usually "inconclusive".
- Reliable cooling is not established in any of the four cities; all four are temperate.
- Inventories mostly list standing trees (DC, SF), so dead plantings are missing; Seattle dropped
  ~8,300 placeholder-dated trees.

## Built on Databricks

Delta + Unity Catalog (bronze/silver/gold, time travel), serverless Jobs (Earth Engine exports →
panel; build-silver; site-effects with a test gate), SQL warehouse `ai_query` for site reports,
MLflow + UC model registry + Model Serving, Databricks App (Streamlit), AI/BI dashboard, Genie.
