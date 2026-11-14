# Agent 3 context handoff — 2026-11-14 ~15:50 CT

## Resumed session update — 2026-11-14

- Completed the failed gold load: `heatseeker.gold.site_effects` is live with 2,222 rows
  (1,111 per variant; each has 28 detected and 1,083 inconclusive). Repeated the load and
  verified exact typed-CSV equality in both directions, including event-study JSON.
- `load_gold.sh` now delegates to stdlib-only `load_gold.py`: explicit CLI `-o json`, SQL
  statement polling/errors, local and remote validation, doubled-quote CSV handling, atomic
  city replacement, exact post-load verification. 18 tests pass, including loader regressions.
- Existing profile `heatseeker` works outside the execution sandbox; inside it the credential
  cache appears empty. Do not initiate a new login based only on that sandbox error.
- Agent 3 msg 5 prepared/published to the shared main MessageBoard with the real output paths,
  gold-table availability, upstream requests, and interpretation caveats.
- `job.json` now sources `agent-3-eval` (main lacks the evaluation code), defaults 500/800
  draws. The runner pins `versionAsOf` before reading the panel, avoiding a provenance race.
  Workspace evaluation is still unverified: `SHOW TABLES IN heatseeker.silver` returned empty.
- Important interpretation correction to the original handoff below: pooled report SEs assume
  independent sites. Shared controls and spatial dependence are not accounted for. Describe
  the roughly -0.08 K five-year difference as provisional, not a demonstrated causal cooling
  effect. Surface temperature is not felt temperature; NYC only so far, temperate-city scope.
- Next: when Agents 1/2 publish the three silver tables, run the evaluation job and validate
  its output/provenance. Then process other cities as their inputs arrive. Do not take over
  upstream ownership or change the frozen schema to bypass missing inputs.

The original handoff below is retained as history; the update above supersedes its load
status, login caveats, job source, test count, and causal interpretation.

Read this first if you are the next Agent 3 session. Then read `CLAUDE.md` (repo root) and the
`MessageBoard` file on `main` (fetch origin/main; agents post there, labelled
`[Agent N | role | date msg k]`; pushing the board to `main` is allowed, nothing else on `main`).

## Who / where

- You are **Agent 3 — Evaluation**. Branch `agent-3-eval`. You own `/core/evaluation`,
  `/core/tests`, `/pipelines/site_effects`. Do not edit `/schema` (Agent 1 owns it; frozen).
- Local clone: `~/HeatSeeker/HeatSeeker`. Python venv: `~/HeatSeeker/.venv-agent3`
  (numpy, pandas, pytest, pyarrow, pyyaml). Tests: `../.venv-agent3/bin/python -m pytest core/tests -q`
  from the repo root. 10 tests, all passing at commit 5d2a7ed.
- Databricks CLI v1.23.0 in `~/.local/bin` (not on the tool shell's PATH: `export PATH="$HOME/.local/bin:$PATH"`).
  Profile `heatseeker` (OAuth, host dbc-f8d41fd5-0183.cloud.databricks.com). Always pass `-p heatseeker`.
  zsh does not word-split `$VAR`, so pass flags literally.
- Scratch inputs used for the runs (may be wiped on reboot; re-fetch with `git show` from the
  other agents' branches): Agent 1 `ingest/us/samples/nyc_silver_{features,interventions}.csv`
  (branch agent-1-data), Agent 2 `pipelines/panel/out/nyc_silver_panel.parquet` and
  `nyc_static.csv` (branch agent-2-satellite, commit 8297d1c, 1,317,340 rows incl. Landsat 5/7).

## What is built (all on agent-3-eval, pushed)

- `core/evaluation/`: scene filter (`panel.py`), relative temperature + per-scene cold-outlier
  trim, cumulative-dose treatment definition (`treatment.py`), matched controls (`matching.py`),
  per-site DiD + event study (`did.py`), bootstrap + stratified fake-date placebo
  (`inference.py`), labels (`labels.py`), sanity report incl. pooled dose-response
  (`report.py`), orchestration (`run.py`), synthetic city + `make_panel_for(features,
  interventions)` (`synthetic.py`). Method notes: `core/evaluation/README.md`.
- `pipelines/site_effects/run_local.py`: CSV/Parquet in → gold CSV + Parquet + report JSON.
  `run_site_effects.py` + `job.json`: Databricks version (never run on a workspace yet).
  `load_gold.sh`: loads the gold CSV into `heatseeker.gold.site_effects` via the serverless
  SQL warehouse (see "In progress" below).
- Real outputs for Agent 4 in `pipelines/site_effects/out/`:
  `nyc_gold_site_effects.{csv,parquet}`, `nyc_site_effects_report.json`,
  `nyc_site_effects_report_all_sensors.json`.

## The real NYC result (headline: Landsat 8/9, 99 scenes, panel 8297d1c)

1,111 planted cells (min_dose 10, cumulative, 2015–2019), 3,872 controls. Pre-period
−0.007 K, balance |SMD| 0.03, placebo centred (sd 0.61 K, q95 1.11 K). Per site: **28
detected (20 cooling, 8 warming) vs ~56 expected by chance** → individual cells are below
Landsat's detection limit; 1,083 `inconclusive`, 0 `not_detectable` (honest MDE median 1.62 K).
**Pooled: −0.054 ± 0.015 K overall, −0.082 ± 0.017 K at 5+ years, no dose gradient**
(15–19 trees −0.14 K; 30–49 trees +0.05 K). All-sensor robustness (L5/7/8/9, 125 scenes,
pre-period back to 2008): −0.058 ± 0.016 K; −0.086 ± 0.018 K at 5+ yr; 14 detected. Both
variants (`all`, `excl_batch_dated`) are identical for NYC: nothing is batch-flagged 2015–2019.
Message for the pitch: street-tree planting at NYC density cools SURFACE temperature by about a
tenth of a kelvin after five years, visible only pooled; say "not felt temperature" every time.

Key method decisions (do not re-litigate without reason):
- `mde_k = max(2.8 × bootstrap SE, placebo q95 + 0.84 × placebo SD)`. Bootstrap CIs alone
  would call 286 sites; the placebo gate calls 28. The placebo is the honest null.
- `city_clear_frac >= 0.5` (Agent 2 verified it removes the north-clipping path 14/row 31
  footprint; do not lower below ~0.4 without de-duplicating by date).
- Water/wetland cells excluded from both sides; controls = cells with ≤2 trees over the whole
  record; elevation joined from Agent 2's `nyc_static.csv` via `--static` (all-null in Agent 1's
  features until they fold it in).

## Databricks state (done by Agent 3 today)

- Catalog `heatseeker` created via SQL `CREATE CATALOG heatseeker` on the "Serverless Starter
  Warehouse" (CLI `catalogs create` fails: Default Storage workspace). Schemas `bronze`,
  `silver`, `gold` and volume `heatseeker.gold.files` created. No tables yet from anyone as
  of this writing. Tell the other agents the catalog name is `heatseeker` (matches the schema).
- SQL from the CLI: `databricks api post /api/2.0/sql/statements -p heatseeker --json
  '{"warehouse_id": "<id from databricks warehouses list>", "statement": "...", "wait_timeout": "50s"}'`.

## In progress / next steps, in order

1. **`load_gold.sh` failed on its first run** (a step returned non-JSON; I was checking which:
   upload with `databricks fs cp ... dbfs:/Volumes/heatseeker/gold/files/site_effects/...`
   or the `read_files` INSERT). Run the steps by hand with full output, fix the script, then
   load `pipelines/site_effects/out/nyc_gold_site_effects.csv` into
   `heatseeker.gold.site_effects`. The user interrupted while I was debugging; the upload may or
   may not have happened — check `databricks fs ls dbfs:/Volumes/heatseeker/gold/files/site_effects -p heatseeker`.
2. **Post Agent 3 msg 5 on the MessageBoard** (not posted yet!): real results above, the
   Parquet path for Agent 4 (`pipelines/site_effects/out/nyc_gold_site_effects.parquet` on
   agent-3-eval), catalog `heatseeker` + schemas created, gold table status, and the honest
   reading (per-site detections are chance-level; the pooled −0.08 K at 5+ yr is the finding).
   Ask Agent 4 to carry rule 14 wording; ask Agent 1 to update the tables.yaml description of
   treatment_year (cumulative) if not done.
3. Once Agents 1/2 write silver tables to `heatseeker.silver.*`, try the Databricks job path
   (`run_site_effects.py`, `job.json`) so `panel_version` is a real Delta version (time travel).
4. After NYC: DC / SF / Seattle through `run_local.py` as their panels land (same commands).
5. Keep `core/tests` green on every change; re-run the real NYC command after any method change:
   `python pipelines/site_effects/run_local.py --panel <panel.parquet> --features <features.csv>
   --interventions <interventions.csv> --static <nyc_static.csv> --out-dir out/nyc
   --panel-version agent2-8297d1c --n-bootstrap 500 --n-placebo 800`

## Board history (my posts so far: msgs 1–4 on main)

msg 1 schema needs + gold columns; msg 2 engine done, notes for 1/2/4; msg 3 dry run on real
grid, cumulative-dose definition; msg 4 local runner ready, interface review. Agent 4 adopted
the gold schema verbatim and waits on the Parquet. Agent 2 may push L5/7 updates and other
cities; Agent 1 is preloading DC/SF/Seattle.
