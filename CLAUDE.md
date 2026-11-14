# HeatSeeker — Plan, Plant, Prove

Shared brief for the four Claude agents building this project. Every session reads this file first.
Source of truth for scope is the project outline ("Plan, Plant, Prove: Urban Cooling Tool — Final Plan", 2026-11-14); this file is the working version of it.

## Which agent are you?

The human starting your session tells you your number ("You are Agent 2"). If they have not, ask before writing any code.
Then read **Shared rules** and your own section under **Agents**. Read the other agents' sections only for the tables they hand you.

| Agent | Branch | Owns | Delivers |
|---|---|---|---|
| 1. Data | `agent-1-data` | Four city adapters, cleaning rules, AI Functions for messy fields, the shared schema | `silver.interventions` |
| 2. Satellite and features | `agent-2-satellite` | Earth Engine Landsat surface temperature for sites and control candidates; canopy, land cover, weather, census | `silver.panel`, `silver.features` |
| 3. Evaluation and learning | `agent-3-eval` | Matched controls, difference-in-differences, placebos, quality labels, effect model, prediction log | `gold.site_effects`, effect model |
| 4. Plan, app and pitch | `agent-4-app` | Candidate sites, ranking, Model Serving, Databricks App, AI/BI dashboard, LLM site reports, demo replay, slides | `gold.recommendations`, the app |

## What we are building

A tool that tells US city planners where to plant, checks whether past plantings actually cooled anything, and uses those results to improve its next suggestions. Pitch: "Plan, plant, prove, repeat."

The product is a four-step loop:

1. **Plan** — rank candidate sites by predicted cooling, vulnerable residents, and cost.
2. **Plant** — log what the city actually did: location, date, intervention type, cost.
3. **Prove** — measure each site's effect against matched control sites using satellite surface temperature over time.
4. **Learn** — feed measured results back into the prediction model and score past predictions against what happened.

Recommending more eligible sites than the city can plant leaves the unplanted ones as ready-made controls.

First version is US-only. Every country-specific part sits in a swappable layer.
Cities, in build order: **New York (lead), Washington DC, San Francisco, Seattle**. Columbus is the backup if a city fails.

## Shared rules

These apply to all four agents.

1. **`/core` never imports from `/ingest/us` or `/config/us`.** This is the one hard architectural rule. Country-specific logic lives only in adapters and config.
2. **Modules talk only through the standard tables.** Do not call another agent's code; read their table.
3. **`/schema` changes only by agreement of all four.** Schemas freeze at hour 2. If you need a change after that, stop and ask the human to coordinate it; do not edit `/schema` on your own branch.
4. **One branch per agent** (names above). Stay inside the directories you own. Do not push to `main` or another agent's branch without the human's go-ahead.
5. **NYC end to end first.** Do not start another city until NYC works through your stage.
6. **Build against sample or synthetic data until real tables arrive.** Never block on an upstream agent.
7. **Store metric units and Celsius or Kelvin everywhere.** Fahrenheit conversion happens only in the app, driven by config.
8. **Every table carries `country_code` and `city_id`.**
9. **LLMs only extract, explain and summarize.** Every number in a site report or brief must come from a gold table. An LLM never produces a figure.
10. **Report "not detectable" honestly.** Do not tune methods until an effect appears.
11. **Surface temperature is not felt temperature.** State this on every result shown to a user.
12. **Record each source's license in bronze.**
13. **Run heavy jobs on Databricks, not inside the Claude session.** Never put tokens, keys or private data in a chat, a commit, or this repo.
14. **Verify before relying.** Sources marked `*` below came from memory and need an access check. Databricks product names may have changed; confirm them in the workspace.

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
sources -> ingest (Earth Engine + serverless jobs) -> bronze -> silver -> Prove / Learn / Plan -> gold -> app
                                                                                                         |
                              new plantings logged in the app start the next cycle <---------------------+
```

Prove, Learn and Plan all read the same silver panel and write to gold, so recommendations always use the latest measured results.

| Table | Writer | Readers | Contents |
|---|---|---|---|
| bronze (all sources) | 1, 2 | 1, 2 | Raw data as received. Common columns: role, value, units, date, geometry, source, license |
| `silver.interventions` | 1 | 2, 3, 4 | site_id, city, geometry, planted_date, type, removed flag |
| `silver.panel` | 2 | 3, 4 | One row per site per satellite scene, H3-indexed; includes control candidates |
| `silver.features` | 2 | 3, 4 | Canopy, impervious fraction, vulnerability, etc. Stored once so evaluation and recommendations read the same numbers |
| `gold.site_effects` | 3 | 4 | Measured effect per site, uncertainty, quality label |
| prediction log (MLflow + gold) | 3 | 4 | Every prediction, scored once its outcome is measured |
| `gold.recommendations` | 4 | app | Ranked candidate sites with predicted cooling ranges |

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

Usage is unlimited; time and demo reliability are the real limits.

- **Foundation:** Delta tables (bronze/silver/gold) + Unity Catalog; native spatial SQL + H3 functions; scheduled Jobs on serverless compute (meets H3's Photon/serverless requirement); MLflow.
- **Core:** Delta time travel (freeze exactly what data each recommendation used); AI Functions in SQL (`ai_query`, `ai_extract`) for messy planting records, with a second pass that flags uncertain extractions; AI/BI dashboards; LLM site reports; multi-city batch runs.
- **Showpiece:** Model Serving for live scoring; Genie **or** a custom agent for "why was this site recommended?" (pick one, not both).
- **Rigor:** large bootstrap and placebo runs.
- **Pitch-only (slides, do not build):** Delta Sharing, Asset Bundles, auto-written grant and council briefs.
- **Skipped:** Vector Search, Lakehouse Federation, Lakebase, lakehouse monitoring.

## Agents

### Agent 1 — Data

**Directories:** `/ingest/us` (city adapters), `/schema`, `/llm` (record extraction prompts), the interventions part of `/pipelines`.

**First task (hours 0–2):** pull NYC and DC, publish a 100-row sample of `silver.interventions`, and get the shared schemas drafted and frozen. Pick 10–20 older park- or block-scale sites per city. No planting data, no project: if a city's records fail, say so immediately.

**Work:**
- One adapter per source, all writing the same bronze schema.
- AI Functions extract species, date and address from messy records; a second pass flags uncertain extractions.
- Output `silver.interventions`.

**City inventory** (checked 2026-11-14):

| City | Source | Date and location columns | Dated plantings per year | Cleaning |
|---|---|---|---|---|
| New York (lead) | Forestry Tree Points; Work Orders as a cross-check only | `planteddate` (text, parse to date); `location` point, 100% filled; `tpstructure` (Full / Retired / Stump) keeps removed trees | 2,625 (2015) rising to 10,069 (2020); 10,000–20,000 a year since 2021 | Drop 9 typo years (e.g. 0202); nothing usable before 2015 |
| Washington DC | 63-city dataset DC file; live Street Trees and Street Tree Archive for 2021 onward | `planted_date`; latitude/longitude | 3,000–9,800 (2012–2019) | Drop about 109,000 rows dated 1970-01-01 |
| San Francisco | Live Street Tree List (data.sf.gov), not the 63-city copy | Planting date field; latitude/longitude (confirm column names) | 1,400–2,300 in recent years; 38,741 dated trees (27%) | Check dated trees aren't clustered in a few neighborhoods |
| Seattle | 63-city dataset Seattle file (98% dated); live SDOT trees layer with `PLANTED_DATE` for newer years | `planted_date` / `PLANTED_DATE`; latitude/longitude | 1,500–3,900 (2012–2019) | Drop round-number dates such as 2000-01-01 |

**Applies to all four cities:**
- Most inventories list only standing trees, so older plantings that died are missing. NYC is the exception from 2015 on; use `tpstructure` to set the removed flag.
- Hundreds of trees dated on one day are likely batch entries. Flag them (do not silently drop) so Agent 3 can test results with and without them.
- Dropped cities: Philadelphia (earliest snapshot 2021), Los Angeles (no date field), Phoenix (no public inventory). Phoenix's dated cool pavement locations are an optional add-on.
- Fallback if records are missing: infer plantings from jumps in canopy cover.

**Cross-review:** check Agent 3's statistics once.

### Agent 2 — Satellite and features

**Directories:** `/ingest/global` (Landsat, ECOSTRESS, ERA5), the non-city adapters in `/ingest/us` (USFS canopy, NLCD, ACS, weather), the panel and features parts of `/pipelines`.

**First task (hours 0–2):** export one summer of Landsat stats for Agent 1's sample sites.

**Work:**
- Earth Engine does cloud masking, converts Landsat values to Kelvin, and computes per-site zonal statistics. **Export tables, not rasters.**
- Cover both intervention sites and control candidates.
- Build `silver.panel`: cleaned, H3-indexed, one row per site per satellite pass.
- Build `silver.features`: canopy, impervious fraction, land cover, elevation, weather, demographics, vulnerability. Stored once.
- Keep scene metadata Agent 3 needs to filter: acquisition time, cloud cover, sensor, and weather on the day.
- ECOSTRESS is a stretch goal. If added, keep it distinguishable by sensor and time of day; it is never mixed with morning Landsat in one estimate.
- Validation data: NOAA Heat Watch for NYC (Bronx 2021, Brooklyn 2022), DC (2018), San Francisco (2021–22). Seattle needs a check.

**Deadline that matters:** real NYC panel at hour 8.

### Agent 3 — Evaluation and learning

**Directories:** `/core` (evaluation and learning model), the gold effects part of `/pipelines`.

**First task (hours 0–2):** build a synthetic panel with a known built-in effect and show the code recovers it. Keep this as a permanent test.

**Evaluation engine ("Prove"):**
- Keep clear-sky summer scenes with comparable weather. Never mix morning Landsat with afternoon or night ECOSTRESS in one estimate.
- Compute each site's temperature relative to a city baseline per scene.
- Choose matched controls on land cover, canopy, elevation and pre-intervention trend.
- Estimate with difference-in-differences and an event study.
- Quantify uncertainty with bootstraps and fake-date placebo tests (thousands of iterations, on Databricks).
- Apply a minimum detectable size; label each site `detected`, `not detectable` or `inconclusive`.
- Flag reflective surfaces whose cooling fades over time.
- Run results with and without batch-dated plantings.

**Learning model ("Learn"):**
- Model each site's effect from size, canopy gain, baseline surface, climate and intervention type. Track in MLflow.
- Pull predictions toward the average where similar past sites are few.
- Score every logged prediction once its outcome is measured.

**Output:** `gold.site_effects`, the registered effect model, the prediction log.

**Limits to state in results:** effects may be too small to see at 30 m, so use park- and block-scale sites older than about five years. All four cities are temperate; there is no hot, dry city.

**Cross-review:** check Agent 1's cleaning once.

**Deadline that matters:** first real effects at hour 14.

### Agent 4 — Plan, app and pitch

**Directories:** `/core` (ranking only), `/serving`, `/app`, `/llm` (site report and brief templates), `/demo`, `/docs`, `/config/us`.

**First task (hours 0–2):** app shell and map reading the sample tables.

**Recommendation engine ("Plan"):**
- Find candidates: low canopy, open space, feasible right-of-way.
- Rank by predicted cooling × vulnerable residents ÷ cost. Costs live in an editable config file.
- Show expected cooling at 5 and 15 years as a range, and suggest an intervention type per site.
- Leave some similarly ranked sites unplanted as future controls.
- Ranking code in `/core` takes costs and the vulnerability formula as inputs; it does not import `/config/us`.

**App:**
- Databricks App map with three views: Recommend, Track, Results.
- Site page: before/after chart, control comparison, confidence label, LLM site report.
- AI/BI dashboard for the portfolio: what worked, cooling per dollar.
- Genie or a custom agent for questions (one, not both).
- Model Serving endpoint: a planner draws a site and gets a predicted cooling range.
- Fahrenheit and US terms by default, set from config.
- Use Delta time travel to freeze the data each recommendation used, so predicted vs. actual is auditable.

**Demo script** (five beats, about three minutes):
1. "Here's where this city planted five years ago." Map of past sites.
2. "Here's what actually happened." One clear success, one "not detectable", one cool surface that faded, each with its site report.
3. "Here's what that taught the model." Dose-response chart, pooled across cities.
4. "Here are next year's top recommendations." Draw a block live, get a predicted cooling range.
5. "And here's how the tool grades itself." Predicted vs. actual, frozen with time travel.

**Keep a precomputed replay of every screen in `/demo`** in case Wi-Fi or a live call fails.

**Deadline that matters:** app on real gold tables at hour 18.

## Timeline and sync points

| Hours | Phase | Sync point |
|---|---|---|
| 0–2 | Load data and freeze schemas | **Hour 2:** schemas frozen, samples out |
| 2–8 | Build the data: Earth Engine exports, AI record cleaning, bronze and silver, the panel | **Hour 8:** real NYC panel |
| 8–14 | Prove: matched controls, DiD, placebo and bootstrap runs, quality labels | **Hour 14:** first real effects |
| 14–18 | Learn and plan: effect model, ranking, prediction log, Model Serving | **Hour 18:** app on real gold tables |
| 18–22 | App: map views, site reports, dashboard, Genie, replay | **Hour 22:** code freeze |
| 22–24 | Pitch: rehearse the demo script twice | |

At each sync point, tell the human what is done, what is not, and what you need from another agent.

## Out of scope for the build

Other countries (design for them, do not build them), ECOSTRESS views, cool roof and pavement degradation alerts, health outcome links, auto-written grant and council briefs. Mention in the pitch only.
