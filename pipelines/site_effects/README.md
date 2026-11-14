# Site effects pipeline

Agent 3's wrappers evaluate the standard silver inputs and publish the frozen
`gold.site_effects` contract. All statistics live in `core/evaluation`.

Start the next Agent 3 session with [CONTEXT.md](CONTEXT.md).

## Deploy and run on Databricks

```
python pipelines/site_effects/deploy.py --profile heatseeker
databricks jobs run-now <job-id> --no-wait -p heatseeker -o json
```

The deployer packages only the evaluation code, its tests and required wrappers. It uploads
an immutable, content-hashed source snapshot under `/Shared/heatseeker/agent3/<hash>` and
creates or updates only this component's tagged `heatseeker-site-effects` job. The deployed
job uses workspace files, so it needs no separate GitHub login. The checked-in `job.json`
also supports a Git-backed deployment from `agent-3-eval`.

The first task runs the permanent tests in the same pinned serverless environment as the
analysis: environment version 4, numpy 2.1.3, pandas 2.2.3 and pyarrow 19.0.1. Only a passing
test task enables the four city tasks. NYC, DC, Seattle and San Francisco run sequentially
to avoid concurrent replacements of the same gold table. Defaults are 500 bootstrap draws
and up to 800 control-cell placebo estimates.

`deploy.py` writes its local deployment receipt to a temporary path by default. Authentication
uses the existing CLI profile; credentials are never part of the source snapshot.

## Input modes and provenance

- **Silver tables:** leave `input_dir` empty. The runner records the versions of
  `<catalog>.silver.panel`, `.features` and `.interventions` before reading each table and
  reads those exact snapshots with `versionAsOf`. It records all three versions in the report;
  `gold.site_effects.panel_version` contains the panel's Delta version.
- **Owner-provided files:** set `input_dir` to a Volume containing the published per-city
  Parquet panel, feature/intervention CSVs and `manifest.json`. Each manifest entry names the
  file, upstream Git commit, source path and SHA256. The runner verifies every checksum before
  evaluation. Gold's panel version is `git:<panel-commit>`; it must not be described as a
  silver Delta version. This mode does not create or modify the upstream silver tables.

- **Pinned Delta panel plus files:** set `input_dir` and `panel_source=delta`. The panel is
  read from a frozen `silver.panel` version, while feature/intervention files remain
  checksum-verified upstream deliveries. Gold records the real panel Delta version; the
  report explicitly identifies the mixed input mode and the two file commits. This mode
  completes cloud evaluation while those upstream silver tables are awaiting publication.

Reports also carry the immutable code hash, runtime versions, configuration and source-data
caveats. The deployed snapshot is reproducible even if an agent branch changes later.

All three silver tables are now live. The deployed default is full silver-only mode; the
explicit override below also selects it:

```
databricks jobs run-now --no-wait -p heatseeker \
  --json '{"job_id":<job-id>,"job_parameters":{"input_dir":""}}'
```

## Outputs and cross-sensor sensitivity

Each successful city task writes CSV, Parquet and a JSON report under
`<output_dir>/<job-run-id>/<city>/`, then atomically replaces that city's rows in
`<catalog>.gold.site_effects`. The default output root is
`/Volumes/heatseeker/gold/files/site_effects/runs`.

The report includes actual control counts, balance, placebo support, event studies,
descriptive pre-trends and pooled source-block jackknife sensitivity. Surface temperature is
not felt temperature. The pooled intervals are conditional sensitivity diagnostics, not
causal confidence intervals; all four cities are temperate.

Run the all-sensor check without overwriting headline gold:

```
databricks jobs run-now --no-wait -p heatseeker \
  --json '{"job_id":<job-id>,"job_parameters":{"sensors":"LANDSAT_5 LANDSAT_7 LANDSAT_8 LANDSAT_9","publish_gold":"false","review_diagnostics":"false"}}'
```

Its output files live under its own run ID. Strict June–August filtering applies to SF too;
its September scenes are not silently included.

## Local smoke runs and CSV publication

```
python pipelines/site_effects/run_local.py \
  --panel <city-panel.parquet> --features <city-features.csv> \
  --interventions <city-interventions.csv> --out-dir <output-dir> \
  --panel-version git:<panel-commit>
```

Heavy inference runs belong on Databricks. The local runner is for samples, integration
checks and situations without a workspace.

To publish an already-produced CSV through the SQL warehouse:

```
bash pipelines/site_effects/load_gold.sh <city-gold.csv> <city-id> heatseeker heatseeker
```

The stdlib-only loader validates locally and remotely, explicitly requests JSON CLI output,
handles doubled quotes inside event-study JSON, and uses atomic `INSERT ... REPLACE WHERE`.
It checks counts, unique keys and exact typed-CSV parity in both directions after loading.
This loader publishes an artifact; it does not claim the evaluation ran in Databricks.

## Version correction

Method 0.2.0's NYC outputs are superseded: its control selector checked only 2015–2019,
allowing later-planted controls. Method 0.3.0 checks the full available record. Do not mix
older gold files or synthetic dry-run expectations into current results. Read `RESULTS.md`
for the completed runs and current output locations.

## Audit a completed run

```
python pipelines/site_effects/verify_run.py --run-id <run-id> \
  --receipt <verification.json>
```

The audit verifies keys, method version and detection gates, then compares the typed cloud
CSV with the gold table using `EXCEPT ALL` in both directions. CSV/Parquet value equality is
also checked locally. Use the CSV for SQL/Spark file ingestion: pandas' Parquet timestamp
encoding can be nanoseconds, which this SQL warehouse does not support directly.

For a cross-sensor run, pass `--robustness --expected-gold-version <headline-version>` to
verify that the headline table version was preserved. The sensitivity outputs are audited
independently; they are intentionally not equal to the headline table. The historical
`--robustness` audit flag describes that non-publication check, not scientific confirmation.

## Statistics review diagnostics

The default `review_diagnostics=true` adds specification comparisons, the same-sensor
pre-cohort fake-date diagnostic, calendar-year rematching, and combined spatial/year
sensitivity. Identical variant cohorts share the expensive diagnostic calculation, while
reports retain their own variant labels. All values are stored in the per-city JSON reports;
the frozen site-effects table is unchanged. Source caveats accompany full Delta reads too.

Use `review_diagnostics=false` for the separate cross-sensor run to avoid repeating the
headline's standing checks. Older sensors are a sensitivity exercise, not independent
robustness evidence. See the independent review and `RESULTS.md` for the failed NYC
pre-cohort diagnostic and limits on causal interpretation.
