# HeatSeeker — Plan, Plant, Prove

A tool that tells US city planners where to plant trees, logs what they planted, measures
whether past plantings cooled anything from 13 years of Landsat surface temperature against
matched unplanted cells, and feeds the measured results back into the next recommendation.
Built on Databricks in one day by four agents working from `CLAUDE.md`; now operated as one.

**Surface temperature is not felt temperature. No city shows an established causal cooling
effect; see `pipelines/site_effects/RESULTS.md` before quoting any number.**

## Where things are

| Surface | Location |
|---|---|
| App (Recommend / Track / Results) | https://heatseeker-7474650715825059.aws.databricksapps.com |
| Dashboard "HeatSeeker Portfolio" | Databricks → Dashboards, id `01f1e080008617ff8ba3af26fa258064` |
| Genie "HeatSeeker — ask the results" | Databricks → Genie, id `01f1e087c5881f388af2ec32a1711ff3` |
| Model Serving | endpoint `heatseeker-effect-model`, model `heatseeker.gold.effect_model` |
| Tables | catalog `heatseeker`: `bronze.*` → `silver.{panel,features,interventions}` → `gold.{site_effects,site_reports,recommendations,prediction_log,app_planting_log}` |
| Pitch / demo script | `docs/pitch.md` |
| Results and caveats | `pipelines/site_effects/RESULTS.md`, `core/evaluation/README.md` |
| Schema (frozen, v1.2.0) | `schema/tables.yaml` |
| Coordination log | `MessageBoard` on `main` |

## Pipeline map

```
Earth Engine (ingest/global/landsat_export.py) ─┐
city inventories, NLCD, census (ingest/us/)     ├─► bronze ─► silver ─► gold ─► app / dashboard / Genie
                                                 │   build job 334451516814053 (silver, promotion)
app Track form ─► gold.app_planting_log ─────────┘   site-effects job 531402490679417 (gold.site_effects)
                                                     pipelines/site_reports (gold.site_reports, ai_query)
                                                     pipelines/recommendations (gold.recommendations, prediction_log)
                                                     serving/register_effect_model.py (UC model + endpoint)
```

## Run it

Prerequisites: Python 3.11+, Databricks CLI with a profile (`databricks auth login --host <workspace> --profile heatseeker`).

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt            # repo-wide deps (Agent 1); app deps in app/requirements.txt

# Evaluation (Agent 3): tests, deploy the job, run it
python -m pytest core/tests -q
python pipelines/site_effects/deploy.py --profile heatseeker
databricks jobs run-now 531402490679417 --no-wait -p heatseeker

# Silver from bronze, with promotion of app-logged plantings (Agent 1)
databricks jobs run-now -p heatseeker --json '{"job_id":334451516814053,"job_parameters":{"check_only":"false"}}'

# Learn + Plan on real tables (Agent 4), then the LLM site reports
python pipelines/recommendations/run_local.py --help
python pipelines/site_reports/build_site_reports.py --profile heatseeker

# Model Serving
DATABRICKS_CONFIG_PROFILE=heatseeker python serving/register_effect_model.py

# App, locally on the real snapshot, or deploy
HEATSEEKER_DATA_DIR=demo/data_real streamlit run app/app.py
databricks workspace import-dir <staged app dir> /Workspace/Shared/heatseeker/app -p heatseeker
databricks apps deploy heatseeker --source-code-path /Workspace/Shared/heatseeker/app -p heatseeker
```

## Branches

`main` holds the brief, the board and (once fast-forwarded) the integrated code. `integration`
is the merged result of `agent-1-data`, `agent-2-satellite`, `agent-3-eval`, `agent-4-app`.
The agent branches are frozen history.
