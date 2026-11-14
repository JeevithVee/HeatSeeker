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
databricks jobs create -p heatseeker --json @pipelines/site_effects/job.json
databricks jobs run-now <job_id> -p heatseeker --json '{"job_parameters": {"city_id": "nyc"}}'
```

The job reads from `agent-3-eval`; change that source after the evaluation code is merged.
It pins `silver.panel` to the Delta version recorded before the read. Defaults are 500
bootstrap and 800 placebo draws. Status: authentication works; the evaluation job has not
run in the workspace because the three upstream silver tables are not loaded yet.

## Load existing results into Databricks

The real NYC file results are already available in `heatseeker.gold.site_effects`:
2,222 rows, 1,111 cells in each variant. Their `panel_version` is the file provenance label
`agent2-8297d1c`, not a Delta version. The app can read this table while silver is being loaded.

```
bash pipelines/site_effects/load_gold.sh \
    pipelines/site_effects/out/nyc_gold_site_effects.csv nyc heatseeker heatseeker
```

The wrapper uses `load_gold.py` (Python standard library only). It finds the Databricks CLI
on PATH or in `~/.local/bin`, requests JSON output explicitly, and uses a serverless warehouse
(or `DATABRICKS_WAREHOUSE_ID`). It validates the CSV and uploaded event-study JSON, then
replaces the city's rows atomically with `INSERT ... REPLACE WHERE`. After loading it checks
row counts, unique site/variant keys, and exact equality with the typed CSV in both directions.
The NYC load and repeat-load verification both passed on 2026-11-14.

The saved report's pooled SEs assume independent sites. Shared controls and spatial
correlation are not accounted for, so the pooled values are descriptive estimates, not
spatially adjusted causal confidence intervals. Surface temperature is not felt temperature;
current observations are NYC only and the planned cities are all temperate.
