# Operator context handoff — 2026-11-15 ~00:20 UTC

## Start here

One session now operates **all four agent roles** (the human's instruction, 2026-11-14 ~23:50 UTC).
Read this, then `README.md` (repo root), `docs/pitch.md`, `pipelines/site_effects/RESULTS.md`, and
the tail of `origin/main:MessageBoard` (operator posts are labelled `[Operator (all agents) | ...]`).
Agent-specific history is in the earlier sections of the board and in each branch's docs.

**Work on branch `integration`** (merge of agent-1-data, agent-2-satellite, agent-3-eval,
agent-4-app, plus everything below). `main` still holds only the brief, the board and the skeleton:
fast-forwarding it to `integration` is a clean `git push origin integration:main` but needs the
human's explicit word (brief rule 4; a first attempt was also declined by the tool's safety
classifier). The board on `main` stays append-only.

## What exists and is verified (as of this handoff)

| Item | State |
|---|---|
| Tables | `heatseeker.bronze.*`, `silver.{panel v0, features v1, interventions v2}`, `gold.{site_effects v22 (5,882 rows), site_reports (2,941), recommendations (845), prediction_log (845), app_planting_log (1 demo row)}` |
| Jobs | `heatseeker-site-effects` 531402490679417 (last run 1123694992477746 SUCCESS, audited: exact gold parity); `heatseeker-build-silver` 334451516814053 (run 700137402752977 promoted the demo planting); 506579230445270 retired, never run it |
| App | `heatseeker`, https://heatseeker-7474650715825059.aws.databricksapps.com, source `/Workspace/Shared/heatseeker/app`, **live mode confirmed** (app principal queries all live tables; 33 FINISHED queries in history). Shows LLM site reports under each Results site. |
| Dashboard | "HeatSeeker Portfolio" `01f1e080008617ff8ba3af26fa258064` |
| Genie | "HeatSeeker — ask the results" `01f1e087c5881f388af2ec32a1711ff3` (definition `app/genie_space.json`) |
| Model Serving | `serving/register_effect_model.py` → UC model `heatseeker.gold.effect_model`, endpoint `heatseeker-effect-model` (scale-to-zero). READY with model version 3 (v1 failed: Python 3.15 has no orjson wheel; v2 failed: `core` package not shipped; v3 logged from `.venv-serving` (Python 3.12) with code_paths). Test query returned predictions with the caveat. |
| Schema | `schema/tables.yaml` v1.2.0 (adds gold.app_planting_log, gold.site_reports) |
| Loop demo | Plant→promote→prove ran live: app_planting_log → silver.interventions v2 → gold v22; 3 NYC effect values changed, 0 labels |

Scientific conclusions are unchanged from Agent 3's handoff (see RESULTS.md): no city has an
established causal cooling effect; per-site labels are at the 30 m detection limit; surface
temperature is not felt temperature. Never relabel inconclusive results for a demo.

## Operating commands

```sh
# evaluation
../.venv-agent3/bin/python -m pytest core/tests -q
../.venv-agent3/bin/python pipelines/site_effects/deploy.py --profile heatseeker
~/.local/bin/databricks jobs run-now 531402490679417 --no-wait -p heatseeker -o json
../.venv-agent3/bin/python pipelines/site_effects/verify_run.py --profile heatseeker --run-id <id> --receipt pipelines/site_effects/out/headline_verification.json
# silver + promotion
~/.local/bin/databricks jobs run-now -p heatseeker --json '{"job_id":334451516814053,"job_parameters":{"check_only":"false"}}'
# site reports (ai_query on the warehouse)
../.venv-agent3/bin/python pipelines/site_reports/build_site_reports.py --profile heatseeker
# serving
DATABRICKS_CONFIG_PROFILE=heatseeker ../.venv-agent3/bin/python serving/register_effect_model.py
# app redeploy: stage app/ + config/us/config.yaml (under app/config/us) + demo/data_real/*.parquet (under app/data)
~/.local/bin/databricks workspace import-dir <staged> /Workspace/Shared/heatseeker/app -p heatseeker
~/.local/bin/databricks apps deploy heatseeker --source-code-path /Workspace/Shared/heatseeker/app -p heatseeker
```

Shell traps: this tool's shell is zsh (no word-splitting of `$VAR`; pass flags literally) and
does not source ~/.zshrc (use `~/.local/bin/databricks` or `export PATH`). Always `-p heatseeker`.

## Remaining / optional

- Fast-forward `main` when the human says so; then the agent branches are frozen history.
- If wanted, add a "what if I plant here" panel to the
  app's Recommend view that calls it (the pitch's beat 4 live-scoring moment; today the ranked
  predictions come from the same model offline).
- Recommendations/prediction log were built on gold v18; gold v22 differs in 3 NYC values, so a
  rebuild is optional (`pipelines/recommendations/run_local.py`).
- CLAUDE.md city notes are stale for DC (Agent 1's TODO); editing CLAUDE.md needs the human.
- Rehearse `docs/pitch.md` twice (brief's last timeline step).
