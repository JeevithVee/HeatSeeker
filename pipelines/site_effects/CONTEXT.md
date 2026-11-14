# Agent 3 context handoff — 2026-11-14

## Start here

You are **Agent 3 — Evaluation**, branch `agent-3-eval`. Read this, then `CLAUDE.md`,
`pipelines/site_effects/RESULTS.md`, and the latest `origin/main:MessageBoard`.
Implementation commit: **83e9d51**; completed delivery/permissions/schema vote: Agent 3
MessageBoard msg 13. This is a completed checkpoint, not an interrupted run.

**Current state: all three silver tables exist, full-silver evaluation is verified, and
Agent 3 has no input-publication blocker. Do not repeat the old claim that features or
interventions are missing. Do not restart inference merely because a new session began.**

Own `core/evaluation`, `core/tests`, and `pipelines/site_effects`. Agent 1 owns schema and
silver feature/intervention pipelines; Agent 2 owns satellite/panel; Agent 4 owns model,
ranking, app and dashboard. Keep work on your branch. Main accepts MessageBoard-only
commits, with labelled append-only updates. Do not overwrite another agent's entries.

## Verified production checkpoint

| Item | Verified value |
|---|---|
| Job | `heatseeker-site-effects`, ID `531402490679417` |
| Headline + standing diagnostics | Run `606115661672539`, SUCCESS |
| Cross-sensor sensitivity | Run `598786481893891`, SUCCESS |
| First full-silver parity run | `383042876269446`, SUCCESS |
| Input snapshots, every city | panel **0**, features **1**, interventions **1** |
| Published gold | `heatseeker.gold.site_effects`, Delta version **18**, **5,882 rows** |
| Headline method / diagnostic version | **0.3.0 / 1.0.0** |
| Tests | **34 passed locally and in the serverless test task** |
| Deployed source hash | `3ed3f2c83aa1a97583685f2eba6adf71d9be4162d1fe66546c41f51556fd0fb2` |

These are the last verified versions, not a promise that upstream data will never change.
The deployed default is `input_dir=''`: **all three inputs come from pinned Delta reads**.
Each version is captured before its table is read with `versionAsOf`. Reports record all
three versions; gold `panel_version='0'` is the panel's actual Delta version.

Headline and cross-sensor runs passed the test gate and all four sequential city tasks.
Gold values EXACTLY reproduce the prior mixed-input results except `evaluated_at_utc`.
Verified frozen gold schema v1.0.0, unique keys, detection gates, numeric variant parity,
exact CSV/Parquet values, and bidirectional typed-CSV/Delta `EXCEPT ALL` equality.
Cross-sensor output has **5,884 rows** (one extra DC cell per variant) and did not change
gold version 18. It runs with `publish_gold=false`, `review_diagnostics=false`.

Per headline variant:

| City | Treated | Eligible controls | Detected | Inconclusive | Max absolute SMD |
|---|---:|---:|---:|---:|---:|
| NYC | 1,111 | 1,785 | 16 | 1,095 | 0.132 |
| DC | 1,010 | 237 | 66 | 944 | 0.812 |
| Seattle | 667 | 400 | 20 | 647 | 0.359 |
| SF | 153 | 267 | 0 | 153 | 0.507 |

Zero `not_detectable` rows. Both variants agree because no 2015–2019 plantings are
batch-flagged. Detected includes warming contrasts and is an unadjusted statistical label.

## Scientific conclusions to preserve

**No city has an established causal cooling effect. Surface temperature is not felt or air
temperature. All four cities are temperate. Predictions inherit these limitations.**

- Method 0.2.0 had a control-selection bug: it checked only the treatment window. Method
  0.3.0 excludes cells with >2 dated trees across the FULL available record. Older 0.2.0
  results, including NYC's -0.082 K five-year figure, are superseded.
- NYC supported overall point is -0.074 K, but -0.012 K without pre-outcome matching.
  Matching on noisy pre-outcomes can induce regression to the mean. The alternative is a
  sensitivity result, not an automatically correct causal estimate.
- The standing fake-date check assigns the recorded cohort a fake treatment in 2010,
  using Landsat 5 only, 2008–2011. NYC gives **-0.239 K over 726 supported cells before
  the recorded cohort**; supported spatial intervals exclude zero. This is a diagnostic
  failure, not an estimate of modern headline bias. Other cities have insufficient
  same-sensor support; do not silently substitute modern or mixed sensors.
- Delete-one-year checks REMATCH controls and use a cohort supported in every deletion.
  Require >=80% of baseline support. NYC retains 1,057/1,109; Seattle 649/666. Combined
  spatial/year overall envelopes cross zero: NYC about [-0.274,+0.146] K, Seattle
  [-0.470,+0.103] K. DC/SF retain only 50.7% / 70.7%; those intervals are withheld.
- The combined output adds spatial and year SEs on the same cohort. It is an explicit
  sensitivity construction, **not a calibrated multiway confidence interval**. Components
  can overlap; do not present the SE sum as a theoretical multiway variance estimator.
- Pre-period centring makes its mean near zero by construction; it is not a parallel-trends
  test. Alpha times site count is a reference, not a calibrated expected false-positive count.
- Older-sensor output is **cross-sensor sensitivity**, not independent robustness confirmation:
  legacy observations occur only before treatment and spatial contrast/resolution can change.
- NYC has missing pre-2015 cohorts and substantial later planting (1,076 treated cells receive
  26,526 additional recorded trees after 2019). Seattle controls can contain unknown-date
  plantings; DC/SF miss historical removals. Poor matching outside NYC remains substantive.
- Never tune support/filter rules until an effect appears or relabel inconclusive for a demo.

Independent review: Agent 1 commit `462e2b4`, `pipelines/reviews/agent3_statistics_review.md`
on `agent-1-data`. The standing checks are now in `core/evaluation/diagnostics.py` and the
per-city report's `review_diagnostics`; the headline estimator/table columns remain unchanged.

## Files and operating commands

Repository root on this machine: `~/HeatSeeker/HeatSeeker`.
Python: `../.venv-agent3/bin/python`. CLI: `~/.local/bin/databricks`, profile `heatseeker`.
The local login last worked outside the tool sandbox; sandbox cache errors alone do not
mean it is absent. Other machines need their own login. Never publish credentials or ask
for tokens to be pasted into chat.

Current delivery under `pipelines/site_effects/`:
- `RESULTS.md`: readable findings, caveats and current run IDs.
- `out/<city>_gold_site_effects.{csv,parquet}`: headline for nyc/dc/sea/sf; explicitly tracked.
- `out/<city>_site_effects_report.json`: full-silver provenance and review diagnostics.
- `out/<city>_site_effects_report_all_sensors.json`: cross-sensor diagnostics.
- `out/evaluation_runs.json`, `headline_verification.json`, `robustness_verification.json`,
  `artifact_checksums.json`: current audit. The historical robustness filename/flag describes
  non-publication verification, not scientific confirmation.
- `out/input_manifest.json`: historical source-file lineage, not current input selection.
- `source_caveats.json`: reviewed source limits packaged with the immutable code snapshot.

Cloud outputs: `/Volumes/heatseeker/gold/files/site_effects/runs/<run-id>/<city>/`.
Workspace code: `/Shared/heatseeker/agent3/3ed3f2c83aa1a975`.

When a code/input change warrants a fresh run:

```sh
../.venv-agent3/bin/python -m pytest core/tests -q
../.venv-agent3/bin/python pipelines/site_effects/deploy.py --profile heatseeker
~/.local/bin/databricks jobs run-now 531402490679417 --no-wait -p heatseeker -o json
```

For cross-sensor sensitivity (keep headline gold intact):

```sh
~/.local/bin/databricks jobs run-now --no-wait -p heatseeker -o json \
  --json '{"job_id":531402490679417,"job_parameters":{"sensors":"LANDSAT_5 LANDSAT_7 LANDSAT_8 LANDSAT_9","publish_gold":"false","review_diagnostics":"false"}}'
```

Audit with `verify_run.py --run-id <id> --receipt <path>`; for a cross-sensor run add
`--robustness --expected-gold-version <headline-version>`. Confirm per-city input versions,
source hash, CSV/Parquet parity and prior-value differences before publishing new artifacts.
Recompute `artifact_checksums.json` after updating the output files.

Runtime traps already solved:
- CLI `--json` requires `job_id` inside JSON, not a positional job ID too.
- Databricks script tasks omit `__file__`; entry points fall back to `sys.argv[0]`.
- Workspace source is read-only: disable bytecode/pytest caches.
- SQL cannot read pandas nanosecond Parquet timestamps directly. Audit typed companion CSVs
  with the loader's doubled-quote handling, and verify Parquet values with pandas.
- Inference belongs on Databricks; local synthetic tests and artifact audits are sufficient.

## Current coordination and remaining work

**No further Agent 3 implementation or evaluation run is pending for the current inputs.**
Next session should first check new MessageBoard feedback or changed inputs, not rerun the
same analysis. No stronger model or input-publication fix is needed for this checkpoint.

- All SIX app read grants requested by Agents 1/4 were applied after checking that the
  principal belongs to the running HeatSeeker app: USE CATALOG heatseeker; USE SCHEMA +
  SELECT on gold and silver; READ VOLUME gold.files. SHOW GRANTS verified them (msg 13).
  No write privilege was added by Agent 3. Existing app-log writes belong to Agent 4.
  SHOW GRANTS also included a PRE-EXISTING inherited account-users ALL PRIVILEGES assignment;
  it was not added/changed by us. Do not regrant on resume or claim permission checks alone
  prove live app queries. Agent 4 last reported mixed mode BEFORE the silver grants; ask
  its owner to confirm fully live mode if that remains relevant.
- Agent 3 already voted AGREE to proposed schema v1.1.0 adding `gold.app_planting_log`
  (nine fields from Agent 1/4). Last fetched schema is still v1.0.0; Agent 2's vote was
  pending. Check latest agreement before assuming the upgrade landed. Do not edit /schema.
- Agent 1 has NOW BUILT promotion, superseding older notes that it was missing:
  `pipelines/promotion.py` inside `heatseeker-build-silver`, job `334451516814053`.
  A check-only run `637450357960656` left both silver tables unchanged at v1. It also ran
  promotion against an EMPTY app log; promotion of a real logged row remains unverified.
  Promotion is manual/not scheduled. It accepts validated tree plantings after the city's
  latest inventory date, rejects duplicates/non-tree types, validates city/grid/date/dose,
  and preserves app source lineage. Review latest owner code before any new promotion task.
- A real promotion may create a new intervention version and change the full-record control
  pool. Future logged cohorts also need an appropriate treatment window and post-period
  scenes; the current evaluation window is 2015–2019. Do not promise an app submission
  immediately appears as a measured effect.
- Agent 1 retired the CSV loader/job `506579230445270`; DO NOT RUN IT. Current branch heads
  no longer carry the eight silver CSVs. Historical copies remain at NYC `72b5b1a`, other
  cities `ea5fcf0`, plus our Volume archives. Default evaluation uses Delta, so this is fine.
- Human decision, Agent 1 msg 11: `median_household_income` intentionally stays NULL. It is
  NOT outstanding work, is not a vulnerability input, and needs no Census API key request.
- Agent 4 owns app/model/dashboard integration and confirmation that the new limitations
  reach user-facing explanations. Scientific training values stayed unchanged; review
  context and provenance are the new part. Do not take over app restyling on this handoff.
