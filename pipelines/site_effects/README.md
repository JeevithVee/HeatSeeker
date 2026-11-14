# /pipelines/site_effects

Writes `gold.site_effects` for one city. Thin wrappers around `/core/evaluation`; all the
statistics live there. Every run prints the sanity report (pre-trend, control balance, placebo
spread, pooled event study) alongside the labels.

**Owner:** Agent 3

## Without a workspace (files)

Agents 1 and 2 deliver silver tables as files on their branches until Databricks exists.

```
python pipelines/site_effects/run_local.py \
    --panel pipelines/panel/out/nyc_silver_panel.parquet \        # Agent 2 (branch agent-2-satellite)
    --features ingest/us/samples/nyc_silver_features.csv \        # Agent 1 (branch agent-1-data)
    --interventions ingest/us/samples/nyc_silver_interventions.csv \
    --out-dir out/nyc --panel-version <export date>
```

Writes `out/nyc/nyc_gold_site_effects.csv` (both variants) and `nyc_site_effects_report.json`.
~3 s for NYC. Add `--sensors LANDSAT_8 LANDSAT_9 LANDSAT_7 LANDSAT_5` once the second export lands.

## On Databricks

`run_site_effects.py` reads `<catalog>.silver.{panel,features,interventions}` for the city,
records the panel's Delta version (time travel), and overwrites that city's rows in
`<catalog>.gold.site_effects` with `replaceWhere`. `job.json` is a serverless job definition that
runs it from the Git folder:

```
databricks jobs create --json @pipelines/site_effects/job.json
databricks jobs run-now <job_id> --json '{"job_parameters": {"city_id": "nyc"}}'
```

Status: written against the frozen schema names; not yet run on a workspace (no login yet).
