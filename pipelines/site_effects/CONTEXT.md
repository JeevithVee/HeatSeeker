# Agent 3 handoff — completed method 0.3.0 delivery, 2026-11-14

Read CLAUDE.md and the latest MessageBoard on origin/main. You are Agent 3 — Evaluation,
branch agent-3-eval. Own core/evaluation, core/tests and pipelines/site_effects. Do not edit
frozen schema or upstream-owned pipelines. Board-only pushes to main are authorized.

## Completed
- Fixed the control selector: controls must have <=2 dated trees across the entire available
  record, not just 2015-2019. All method 0.2.0 findings/files are superseded.
- Missing placebo evidence cannot yield detected/not_detectable. Added joint source-block
  jackknife sensitivity, control-reuse diagnostics and descriptive pre-slopes. The centred
  pre mean is not a parallel-trends test; alpha*n is not a calibrated false-positive count.
- Deployed job heatseeker-site-effects, job ID 531402490679417. Immutable source hash
  a5405c5ae6f07b7954476c72720fb771ed133e3142a078323259eb120e6b0648. Test gate followed
  by four sequential city tasks. 27 tests pass locally and in the actual serverless environment.
- Final headline run 5222250658819: SUCCESS, all four cities. Final all-sensor robustness
  run 149976888548281: SUCCESS, all four cities, publish_gold=false.
- Gold heatseeker.gold.site_effects: 5,882 rows at Delta version 10. Frozen schema 1.0.0,
  unique keys, detection gates, numeric variant equality and exact CSV/Parquet parity verified.
  SQL EXCEPT ALL found zero differences between typed cloud CSVs and published gold.
  Robustness had 5,884 rows (one extra DC cell per variant); gold stayed at version 10.
- Both final runs read heatseeker.silver.panel VERSION AS OF 0. Gold panel_version='0'
  is now a real Delta version. Feature/intervention inputs are the owner's verified files,
  because those silver tables remain absent. Reports explicitly identify this mixed mode.
- Verified files, input/code provenance, runtime, configuration, run receipts and checksums
  are in out/. All four headline Parquet files are explicitly tracked despite *.parquet
  being ignored generally. RESULTS.md is the readable findings and downstream handoff.
- Source hash of local analysis code matches the successful immutable cloud snapshot.

## Corrected headline counts (per variant)
NYC: 1,111 treated, 1,785 controls, 16 detected / 1,095 inconclusive; max |SMD| 0.132.
DC: 1,010 treated, 237 controls, 66 detected / 944 inconclusive; max |SMD| 0.812.
SEA: 667 treated, 400 controls, 20 detected / 647 inconclusive; max |SMD| 0.359.
SF: 153 treated, 267 controls, 0 detected / 153 inconclusive; max |SMD| 0.507.
No not_detectable rows. Both variants agree because no window plantings are batch-flagged.

NYC's roughly -0.11 K five-year-plus difference is not robust to larger spatial blocks;
its envelope includes zero. Seattle's conditional intervals remain negative, but poor
balance and unknown-date control contamination prevent a causal claim. DC/SF have poor
balance and no convincing pooled cooling. Surface temperature is not felt temperature.
All cities are temperate. Read RESULTS.md rather than recycling prior pitch claims.

## Reproduce / refresh
- Local Python: ../.venv-agent3/bin/python. Tests: python -m pytest core/tests -q.
- CLI: ~/.local/bin/databricks, profile heatseeker. Its cached login works outside the tool
  sandbox; sandbox-only cache errors are not evidence a new login is needed. Other machines
  need their own login (Agent 2 now has one). Never put credentials in source or the board.
- Manifest: out/input_manifest.json. Volume input directory:
  /Volumes/heatseeker/gold/files/site_effects/inputs/git-3fd6870-ea5fcf0-72b5b1a
- Cloud outputs: /Volumes/heatseeker/gold/files/site_effects/runs/<run-id>/<city>/.
- deploy.py packages code only. Deployed defaults: panel_source=delta, verified file inputs,
  500 bootstrap draws, up to 800 placebo estimates, headline publication enabled.
- For all-sensor checks override sensors and publish_gold=false. Always verify headline
  Delta version preservation with verify_run.py. CLI --json requires job_id inside JSON.
- Script tasks omit __file__; entry points use sys.argv[0] as fallback. Workspace source is
  read-only: disable bytecode/pytest caches. SQL cannot read pandas nanosecond Parquet
  timestamps; audit companion CSVs with explicit types. Pandas validates Parquet equality.

## Remaining external dependencies
- Agent 1/2: publish silver.features and silver.interventions. Then run this same job with
  input_dir='' for full silver-only mode; all three reads are pinned and versioned. This is
  the only input mode not yet run live, because those tables do not exist.
- Agent 4: rebuild prior 0.2.0 model/recommendation/demo artifacts using the corrected gold.
  Read reports for poor balance and other caveats; these are not validated causal targets.
- Data-cleaning code cross-review completed: DC time-zone normalization, SEA date-only
  preservation/January-1/planned exclusions, SF missing coordinates and standing-tree
  limitation agree with the handoff. DC/SF survivorship and SEA unknown dates remain limits.
- Agent 1's independent statistical review is welcome; no other Agent 3 code/run work is
  outstanding for the currently published inputs. No additional login or model is needed.
