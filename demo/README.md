# /demo

Precomputed results and replay data.

**Owner:** Agent 4

## Snapshots

- `data/` — fully fake world (2,500 cells around NYC), self-contained:
  `generate_fake_data.py` then `run_pipeline.py` rebuilds it. Kept as the
  no-dependencies test bed.
- `data_real/` — **all real, all four cities** (NYC, DC, Seattle, SF):
  Agent 1/2's silver features and interventions, Agent 3's corrected
  gold.site_effects (method 0.3.0, panel Delta version 0), per-site Landsat
  scene series distilled from Agent 2's panels, and recommendations +
  prediction log from the pooled effect model (v2-real-gold-0.3.0). Rebuild:

  ```bash
  python pipelines/recommendations/run_local.py \
      --site-effects <per-city gold parquets> \
      --features <per-city features CSVs> \
      --interventions <per-city interventions CSVs> \
      --out-dir demo/data_real
  python pipelines/recommendations/build_panel_sample.py \
      --panel <per-city silver panel parquets> \
      --site-effects <per-city gold parquets> \
      --interventions <per-city interventions CSVs> \
      --out demo/data_real/panel_sample.parquet
  ```

Run the app on either snapshot:

```bash
HEATSEEKER_DATA_DIR=demo/data_real streamlit run app/app.py
```
