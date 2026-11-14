# Agent 3 handoff — full silver-only delivery and review diagnostics, 2026-11-14

Read CLAUDE.md and origin/main:MessageBoard. You are Agent 3 — Evaluation, branch
agent-3-eval. Own core/evaluation, core/tests and pipelines/site_effects. Schema remains
Agent 1's; board-only pushes to main are authorized. Current data work is complete.

## Live evaluation and audit
- Job heatseeker-site-effects: 531402490679417. Default input_dir='' now reads only Delta.
- Final headline + review diagnostics run: 606115661672539, SUCCESS (34 tests + four cities).
- Final cross-sensor sensitivity run: 598786481893891, SUCCESS (34 tests + four cities),
  publish_gold=false, review_diagnostics=false. Its legacy audit flag/file name still says
  robustness; scientifically it is sensitivity, not independent confirmation.
- Every city pins panel=0, features=1, interventions=1 before reading. Reports record all
  three snapshots. No operational dependency on staged feature/intervention CSVs remains.
- heatseeker.gold.site_effects: 5,882 rows at Delta version 18; method_version=0.3.0,
  panel_version='0'. All scientific values EXACTLY equal the prior mixed-input results;
  only evaluated_at_utc changed. Frozen schema 1.0.0, unique keys, variant parity, detection
  gates, exact CSV/Parquet values and exact typed-CSV/Delta EXCEPT ALL parity all verified.
- Cross-sensor output has 5,884 rows (one extra DC cell per variant) and preserved gold v18.
- Source hash 3ed3f2c83aa1a97583685f2eba6adf71d9be4162d1fe66546c41f51556fd0fb2 matches
  the local analysis source. The immutable workspace snapshot is under Shared/heatseeker/agent3.
- 383042876269446 was the first full-silver integration run, also SUCCESS, before diagnostics
  were added. Earlier mixed runs are historical, not current operational inputs.

## Statistical review addressed
- Agent 1 reviewed method 0.3.0 at 462e2b4; the original point estimates reproduce exactly.
- New diagnostics.py (diagnostic version 1.0.0) leaves frozen gold and estimator unchanged.
  It adds static-only matching comparison; same-sensor pre-cohort fake date; delete-year
  rematching with fixed common support; combined spatial/year SE-sum sensitivity; sensor-family
  scene support and later-planting counts. Test suite has 34 tests, local and serverless.
- NYC: overall supported point -0.074 K -> -0.012 K without pre-outcome matching.
  Fake treatment in 2010, Landsat 5 only 2008-2011, gives -0.239 K over 726 sites BEFORE
  the recorded cohort. This is a diagnostic failure, not an estimate of headline bias.
- Common-year cohorts must retain >=80% of baseline support. NYC retains 1,057/1,109;
  Seattle 649/666. Combined overall sensitivity envelopes cross zero (NYC about
  [-0.274,+0.146] K; Seattle [-0.470,+0.103] K). They add both SE components and are NOT
  calibrated multiway confidence intervals. DC and SF retain only 50.7% / 70.7%, so those
  intervals are withheld. Do not relax support rules until a desired effect appears.
- Spatial intervals alone miss shared year variation; pre-centred means are not a pre-trend
  test. Site detections are unadjusted labels, not causal proof. All-sensor output is not
  independent robustness confirmation because legacy sensors only contribute pre observations.
- NYC treated cells mostly keep receiving trees after 2019, and pre-2015 cohorts are missing.
  Seattle has unknown-date planting contamination; DC/SF miss historical removals. No city
  has an established causal cooling effect. Surface temperature is not felt temperature.
  All four cities are temperate. Model predictions inherit these limitations.

## Files and reproducibility
- Read RESULTS.md and the per-city JSON reports, not older pitch numbers.
- out/<city>_gold_site_effects.{csv,parquet}: current headline, all four cities.
- out/<city>_site_effects_report.json: full-silver provenance and standing review diagnostics.
- out/<city>_site_effects_report_all_sensors.json: cross-sensor diagnostics.
- out/evaluation_runs.json, headline_verification.json, robustness_verification.json,
  artifact_checksums.json: current audit. input_manifest.json is retained historical lineage.
- Cloud outputs: /Volumes/heatseeker/gold/files/site_effects/runs/<run-id>/<city>/.
- source_caveats.json supplies reviewed source limits to the pipeline even in Delta-only mode.
- Local Python: ../.venv-agent3/bin/python. Run python -m pytest core/tests -q.
- CLI ~/.local/bin/databricks, -p heatseeker. Sandbox-only credential-cache errors do not mean
  the login is absent. Other machines need their own login. Never publish credentials.
- Databricks script entry points fall back from __file__ to sys.argv[0]. Disable bytecode and
  pytest caches because workspace source is read-only. SQL cannot read pandas nanosecond
  Parquet timestamps; audit typed companion CSVs and verify Parquet equality with pandas.
- deploy.py packages code, tests and source caveats only. Run it without input-dir for full
  silver defaults. Legacy file and mixed modes remain available for historical reproducibility.

## App/collaboration
- Applied Agent 4 / Agent 1's six requested read grants after verifying the running app's
  service-principal identity: USE CATALOG heatseeker; USE SCHEMA + SELECT on gold; USE SCHEMA
  + SELECT on silver; READ VOLUME gold.files. SHOW GRANTS verified the direct grants.
  No write privilege was added by Agent 3. The app planting-log write grant belongs to Agent 4.
- SHOW GRANTS also listed the pre-existing inherited account-users ALL PRIVILEGES assignment;
  this was present before our read grants and was not changed. Agent 4 must verify app live
  mode under its own identity; checking permissions is not a live-app end-to-end test.
- Agent 3 agrees to the proposed gold.app_planting_log schema addition (v1.1.0), nine columns
  proposed by Agent 1/4, as staging. It does not feed evaluation until Agent 1's validated,
  idempotent promotion and suitable treatment-window/post-period data are available.
- Agent 4 owns model/app/dashboard integration. Carry the independent-review limitations
  into the UI; current scientific gold values are unchanged, so review context is the new part.
- No further input publication blocker remains for Agent 3. Future work needs new data,
  review feedback, or an explicit new task; do not keep claiming the silver tables are missing.
