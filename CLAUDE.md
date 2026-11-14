# HeatSeeker — Plan, Plant, Prove

Shared brief for the four Claude agents building this project. Every session reads this file first.
Source of truth for scope is `HeatSeekerOutline.pdf` in this repo ("Plan, Plant, Prove: Urban Cooling Tool — Final Plan", reworked 2026-11-14); this file is the working version of it.

## Which agent are you?

The human starting your session tells you your number ("You are Agent 2"). If they have not, ask before writing any code.
Then read **Shared rules** and your own section under **Agents**. Read the other agents' sections only for the tables they hand you.

| Agent | Branch | Owns | Delivers |
|---|---|---|---|
| 1. Data and features | `agent-1-data` | City tree adapters (NYC first), cleaning rules, H3 site table, canopy, land cover and census features, the shared schema; then preloads DC, San Francisco and Seattle | `silver.interventions`, `silver.features` |
| 2. Satellite (critical path) | `agent-2-satellite` | Earth Engine Landsat summer surface temperature for every H3 cell in the city, planted or not; the panel table | `silver.panel` |
| 3. Evaluation | `agent-3-eval` | Matched controls, difference-in-differences and event study, placebo tests, minimum detectable size, quality labels | `gold.site_effects` |
| 4. Learn, plan and app | `agent-4-app` | Effect model and prediction log in MLflow, candidate cells and ranking, Databricks App and AI/BI dashboard | Effect model, `gold.recommendations`, the app |

## What we are building

A tool that tells US city planners where to plant, checks whether past plantings actually cooled anything, and uses those results to improve its next suggestions.

The product is a four-step loop:

1. **Plan** — rank candidate sites by predicted cooling, vulnerable residents, and cost.
2. **Plant** — log what the city actually did: location, date, intervention type, cost.
3. **Prove** — measure each site's effect against matched control sites using satellite surface temperature over time.
4. **Learn** — feed measured results back into the prediction model and score past predictions against what happened.

Recommending more eligible sites than the city can plant leaves the unplanted ones as ready-made controls.

First version is US-only. Every country-specific part sits in a swappable layer.
Cities: **New York (lead)**, then Washington DC, San Francisco, Seattle. Columbus is the backup if a city fails.

**The goal is a working NYC prototype, end to end, in 5–6 hours.** Everything else waits until it runs.

## Shared rules

These apply to all four agents.

1. **`/core` never imports from `/ingest/us` or `/config/us`.** This is the one hard architectural rule. Country-specific logic lives only in adapters and config.
2. **Modules talk only through the standard tables.** Do not call another agent's code; read their table.
3. **`/schema` is frozen in the first 30 minutes and changes only by agreement of all four.** If you need a change after that, stop and ask the human to coordinate it; do not edit `/schema` on your own branch.
4. **One branch per agent** (names above). Stay inside the directories you own. Do not push to `main` or another agent's branch without the human's go-ahead.
5. **Protect the critical path: satellite export → panel → evaluation → model → app.** If you finish early, move to whatever blocks this path, not to polish.
6. **NYC end to end first.** DC, San Francisco and Seattle run through the same pipeline only after the NYC prototype works.
7. **Sites are H3 cells, not single trees.** Landsat cannot resolve individual trees. `site_id` is the H3 cell everywhere.
8. **Build against synthetic or sample data until real tables arrive.** Never block on an upstream agent.
9. **Times in the timeline are ceilings, not targets.** Move to the next step the moment the current one works.
10. **Store metric units and Celsius or Kelvin everywhere.** Fahrenheit conversion happens only in the app, driven by config.
11. **Every table carries `country_code` and `city_id`.**
12. **LLMs only extract, explain and summarize.** Every number in a site report must come from a gold table. An LLM never produces a figure.
13. **Report "not detectable" honestly.** Do not tune methods until an effect appears.
14. **Surface temperature is not felt temperature.** State this on every result shown to a user.
15. **All four cities are temperate; there is no hot, dry city.** Note that limit alongside the results.
16. **Record each source's license in bronze.**
17. **Run heavy jobs on Databricks, not inside the Claude session.** Never put tokens, keys or private data in a chat, a commit, or this repo.
18. **Verify before relying.** Sources marked `*` below came from memory and need an access check. Databricks product names may have changed; confirm them in the workspace.

## Open decisions to settle at schema freeze

The outline leaves these unspecified. Agree them in the first 30 minutes and write them into `/schema`.

- **H3 resolution.** Agents 1 and 2 must use the same one from the first minute, since Agent 2's export starts before anything else.
- **Weather and elevation.** Evaluation needs comparable-weather scenes and matches controls on elevation, but neither is assigned to Agent 1's feature list or Agent 2's export.
- **Removed flag at cell level.** The outline lists a removed flag on `silver.interventions`, but a cell holds many trees; define what it means for a cell.

## Repo structure

```
/core            evaluation, learning model, ranking (country-agnostic)
/schema          standard data roles and table definitions
/ingest/us       US adapters (USFS canopy, NLCD, ACS, city records, ...)
/ingest/global   shared global sources (Landsat, ECOSTRESS, ERA5)
/config/us       units, cost assumptions, vulnerability formula, city list
/pipelines       bronze -> silver -> gold jobs
/llm             record extraction prompts, site report and brief templates
/serving         model serving endpoint
/app             Databricks App; units and labels read from config
/demo            precomputed results and replay data
/docs            methods, caveats, pitch
```

## Data flow and table contracts

```
sources -> ingest (Earth Engine + serverless jobs) -> bronze -> silver -> Prove -> Learn -> Plan -> gold -> app
                                                                                                             |
                                new plantings logged in the app start the next cycle <-----------------------+
```

Prove, Learn and Plan all read the same silver panel and write to gold, so recommendations always use the latest measured results.

| Table | Writer | Readers | Contents |
|---|---|---|---|
| bronze (all sources) | 1, 2 | 1, 2 | Raw data as received. Common columns: role, value, units, date, geometry, source, license |
| `silver.interventions` | 1 | 3, 4 | site_id = H3 cell, city, trees planted per year, removed flag |
| `silver.features` | 1 | 3, 4 | Canopy, impervious fraction, land cover, census, vulnerability per cell. Stored once so evaluation and recommendations read the same numbers |
| `silver.panel` | 2 | 3, 4 | One row per cell per scene, for every H3 cell in the city, planted or not |
| `gold.site_effects` | 3 | 4 | Measured effect per site, uncertainty, quality label |
| prediction log (MLflow + gold) | 4 | 4, app | Every prediction, scored once its outcome is measured |
| `gold.recommendations` | 4 | app | Ranked candidate cells with predicted cooling ranges |

The column lists above are the starting point from the outline. The frozen definitions live in `/schema`; once they exist, `/schema` wins over this table.

## Data inputs

Core logic depends on the role, not the source.

| Role | US source now | Global fallback later |
|---|---|---|
| Surface temperature | Landsat 8/9 Collection 2 surface temperature (30 m, 8-day revisit) | Same |
| Extra thermal views (stretch) | ECOSTRESS (70 m, afternoon and night passes) | Same, up to 52° latitude |
| Canopy | USFS tree canopy cover (annual, 30 m) | Global canopy or land cover products |
| Land cover | Annual NLCD | ESA WorldCover or similar |
| High-res imagery and height | NAIP*, USGS 3DEP lidar* | Sentinel-2, national lidar |
| Weather | NOAA stations*, PRISM or gridMET* | ERA5-Land |
| Demographics | Census ACS* (block group) | National census, WorldPop |
| Vulnerability | CDC PLACES*, Tree Equity Score*, city heat vulnerability index | Composite index from local census |
| Interventions | City tree inventories and planting records | Same template, local records |
| Feasibility | City right-of-way, parcels, utilities | OpenStreetMap |
| Ground truth | NOAA Heat Watch campaigns | Local sensor networks |

`*` = from memory, needs an access check before we rely on it.

## Databricks platform

Usage is unlimited; time is the real limit.

- **Foundation:** Delta tables (bronze/silver/gold) + Unity Catalog; native spatial SQL + H3 functions; scheduled Jobs on serverless compute (meets H3's Photon/serverless requirement); MLflow.
- **Core:** Delta time travel (freeze exactly what data each recommendation used, so predicted vs. actual is auditable); AI Functions in SQL (`ai_query`, `ai_extract`) for messy planting records, with a second pass that flags uncertain extractions; AI/BI dashboards; LLM site reports; multi-city batch runs.
- **Showpiece:** Model Serving for live scoring; Genie **or** a custom agent for "why was this site recommended?" (pick one, not both).
- **Rigor:** bootstrap and placebo runs.
- **Later (do not build now):** Delta Sharing, Asset Bundles, auto-written grant and council briefs.
- **Skipped:** Vector Search, Lakehouse Federation, Lakebase, lakehouse monitoring.

For the prototype, only Foundation plus the dashboard and time travel are needed. Model Serving, LLM site reports and Genie come after the prototype works.

## Agents

### Agent 1 — Data and features

**Directories:** `/ingest/us`, `/schema`, `/llm` (record extraction prompts), the interventions and features parts of `/pipelines`.

**First task:** start the NYC Forestry Tree Points pull at 0:00 and publish a 100-row sample. Get the shared schemas frozen by 0:30.

**Work, in order:**
1. Clean NYC plantings and aggregate 2015–2019 into H3 cells: `silver.interventions` (site_id = H3 cell, city, trees planted per year, removed flag).
2. Build `silver.features` per cell: canopy, land cover, impervious fraction, census, vulnerability.
3. Preload DC, San Francisco and Seattle so they run through the pipeline quickly once the NYC prototype works.

One adapter per source, all writing the same bronze schema. AI Functions extract species, date and address from messy records, with a second pass that flags uncertain extractions.

**City inventory** (checked 2026-11-14):

| City | Source | Date and location columns | Dated plantings per year | Cleaning |
|---|---|---|---|---|
| New York (lead) | Forestry Tree Points; Work Orders as a cross-check only | `planteddate` (text, parse to date); `location` point, 100% filled; `tpstructure` (Full / Retired / Stump) keeps removed trees | 2,625 (2015) rising to 10,069 (2020); 10,000–20,000 a year since 2021 | Drop 9 typo years (e.g. 0202); nothing usable before 2015 |
| Washington DC | 63-city dataset DC file; live Street Trees and Street Tree Archive for 2021 onward | `planted_date`; latitude/longitude | 3,000–9,800 (2012–2019) | Drop about 109,000 rows dated 1970-01-01 |
| San Francisco | Live Street Tree List (data.sf.gov), not the 63-city copy | Planting date field; latitude/longitude (confirm column names) | 1,400–2,300 in recent years; 38,741 dated trees (27%) | Check dated trees aren't clustered in a few neighborhoods |
| Seattle | 63-city dataset Seattle file (98% dated); live SDOT trees layer with `PLANTED_DATE` for newer years | `planted_date` / `PLANTED_DATE`; latitude/longitude | 1,500–3,900 (2012–2019) | Drop round-number dates such as 2000-01-01 |

**Applies to all four cities:**
- Most inventories list only standing trees, so older plantings that died are missing. NYC is the exception from 2015 on, via `tpstructure`.
- Hundreds of trees dated on one day are likely batch entries. Flag them (do not silently drop) so Agent 3 can test results with and without them.
- Dropped cities: Philadelphia (earliest snapshot 2021), Los Angeles (no date field), Phoenix (no public inventory). Phoenix's dated cool pavement locations are an optional add-on.
- Fallback if records are missing: infer plantings from jumps in canopy cover.
- The biggest risk is data, not code. If a city's planting records fail, say so immediately.

**Cross-review:** check Agent 3's statistics once.

### Agent 2 — Satellite (critical path)

**Directories:** `/ingest/global`, the panel part of `/pipelines`.

**First task:** start the Earth Engine export for the **whole NYC cell grid in the first minutes**. It needs nothing from Agent 1: every H3 cell in the city is exported, planted or not. Everything downstream waits on this job, so launch it before doing anything else.

**Work:**
- Earth Engine does cloud masking, converts Landsat values to Kelvin, and computes per-cell zonal statistics. **Export tables, not rasters.**
- Export only clear-sky summer scenes.
- Build `silver.panel` as Landsat stats arrive: one row per cell per scene.
- Keep the scene metadata Agent 3 needs to filter: acquisition date and time, cloud cover, sensor.
- After the prototype: repeat for DC, San Francisco and Seattle. ECOSTRESS is a stretch goal; if added, keep it distinguishable by sensor and time of day, since it is never mixed with morning Landsat in one estimate.
- Validation data, if time allows: NOAA Heat Watch for NYC (Bronx 2021, Brooklyn 2022), DC (2018), San Francisco (2021–22). Seattle needs a check.

**While the export runs:** help whatever blocks the critical path.

### Agent 3 — Evaluation

**Directories:** `/core` (evaluation), the site effects part of `/pipelines`.

**First task:** write and test the code on a synthetic panel with a known built-in effect, and show the code recovers it. Keep this as a permanent test. Have it finished by 2:00 so it runs on the real panel the moment it lands.

**Evaluation engine ("Prove"):**
- Keep clear-sky summer scenes with comparable weather. Never mix morning Landsat with afternoon or night ECOSTRESS in one estimate.
- Compute each site's temperature relative to a city baseline per scene.
- Choose matched controls on land cover, canopy, elevation and pre-intervention trend. Unplanted cells in the panel are the control pool.
- Estimate with difference-in-differences and an event study.
- Quantify uncertainty with bootstraps and fake-date placebo tests. **A few hundred iterations for the prototype, not thousands**; run them on Databricks.
- Apply a minimum detectable size; label each site `detected`, `not detectable` or `inconclusive`.
- Run results with and without batch-dated plantings.
- Flag reflective surfaces whose cooling fades over time (only relevant once non-tree interventions are loaded).

**Output:** `gold.site_effects` with effects and quality labels.

**Limits to state in results:** effects may be too small to see at 30 m, so favor cells with substantial plantings older than about five years.

**Cross-review:** check Agent 1's cleaning once.

### Agent 4 — Learn, plan and app

**Directories:** `/core` (learning model and ranking), `/serving`, `/app`, `/llm` (site report templates), `/demo`, `/docs`, `/config/us`.

**First task:** build the effect model and the app on fake effect data, matching the frozen `gold.site_effects` schema, so both are tested before real effects arrive.

**Learning model ("Learn"):**
- Model each site's effect from size, canopy gain, baseline surface, climate and intervention type. Keep it simple for the prototype. Track in MLflow.
- Pull predictions toward the average where similar past sites are few.
- Write the prediction log; score every logged prediction once its outcome is measured.

**Recommendation engine ("Plan"):**
- Find candidate cells: low canopy, open space, feasible right-of-way.
- Rank by predicted cooling × vulnerable residents ÷ cost. Costs live in an editable config file.
- Show expected cooling at 5 and 15 years as a range, and suggest an intervention type per site.
- Leave some similarly ranked sites unplanted as future controls.
- Model and ranking code in `/core` take costs and the vulnerability formula as inputs; they do not import `/config/us`.

**App:**
- Databricks App map with three views: Recommend, Track, Results.
- Site page: before/after chart, control comparison, confidence label.
- AI/BI dashboard for the portfolio: what worked, cooling per dollar.
- Fahrenheit and US terms by default, set from config.
- If a live query or endpoint fails, the app falls back to precomputed gold tables.
- After the prototype: Model Serving live scoring, LLM site reports, Genie or a custom agent (one, not both).

## Build timeline

| Time (ceiling) | Step | Who |
|---|---|---|
| 0:00–0:30 | **Set up.** Repo, Databricks workspace, frozen schemas. Earth Engine export for the whole NYC cell grid starts; NYC Tree Points pull starts | All; 2 and 1 start their jobs immediately |
| 0:30–2:00 | **Parallel build.** NYC plantings 2015–2019 into H3 cells, features, then preload other cities (1). Panel as Landsat stats arrive (2). Evaluation code on the synthetic panel (3). Effect model and app on fake effects (4) | All |
| 2:00–3:30 | **First real result.** Join into the NYC panel; difference-in-differences with placebo tests; site effects and quality labels to gold | 1, 2, 3 |
| 3:30–4:30 | **Learn and plan.** Simple effect model on NYC effects, rank candidate cells, write the prediction log | 4 |
| 4:30–5:30 | **Connect and test.** Point the app at real gold tables and run the whole loop once. Prototype done | All |
| After it works | DC, San Francisco and Seattle through the same pipeline; Model Serving live scoring; LLM site reports; Genie; ECOSTRESS | |

At the end of each step, tell the human what is done, what is not, and what you need from another agent.

## Out of scope for the build

Other countries (design for them, do not build them), Delta Sharing, Asset Bundles, cool roof and pavement degradation alerts, health outcome links, auto-written grant and council briefs.
