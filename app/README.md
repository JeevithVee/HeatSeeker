# /app

Databricks App: Recommend, Track and Results views. Units and labels read from config; falls back to precomputed gold tables if a live query fails.

**Owner:** Agent 4

## Run locally

```bash
python demo/generate_fake_data.py   # fake NYC world, frozen schemas
python demo/run_pipeline.py         # Learn + Plan -> gold_recommendations, prediction log, MLflow
streamlit run app/app.py            # from app/ or repo root
```

`HEATSEEKER_DATA_DIR` points the app at a different snapshot directory
(default `demo/data`). `app/data.py` is the single place that swaps parquet
snapshots for SQL against Unity Catalog on Databricks; everything else is
unchanged between local and deployed runs.

## Deploy as a Databricks App

```bash
databricks apps deploy heatseeker --source-code-path app/
```

`app.yaml` holds the command; set `HEATSEEKER_DATA_DIR` to a UC Volume with
the gold/silver snapshots, or extend `data.py` to query the tables directly.

## Views

- **Recommend** — ranked candidate map (score = predicted cooling ×
  vulnerable residents ÷ cost), site detail with predicted cooling ranges at
  5/15 years, holdout controls flagged.
- **Track** — planted cells map, totals, and a form that logs new plantings
  (the "Plant" step; starts the next Prove → Learn cycle).
- **Results** — measured effects map colored by quality label, portfolio
  cooling-per-dollar, per-site before/after chart against matched controls
  with CI, MDE and placebo p.

Storage is Kelvin; display unit comes from `config/us/config.yaml`
(temperature differences: ΔF = ΔK × 1.8). The surface-vs-felt-temperature
caveat (shared rule 14) renders on every view.
