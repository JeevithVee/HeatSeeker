# /demo

Precomputed results and replay data.

**Owner:** Agent 4

## Snapshots

- `data/` — fully fake world (2,500 cells around NYC), self-contained:
  `generate_fake_data.py` then `run_pipeline.py` rebuilds it.
- `data_nyc/` — **real NYC grid** (7,414 H3 res-9 cells): Agent 1's real
  `silver.features` and `silver.interventions`, Agent 2's real
  `silver.panel` distilled into `panel_sample.parquet` (real Landsat scene
  series per evaluated site), and recommendations from
  `pipelines/recommendations/run_local.py`. **`gold_site_effects.parquet`
  here is SYNTHETIC** (Agent 3's `make_panel_for` lays a known effect over
  the real grid) until Agent 3 posts the real one — then rerun:

  ```bash
  python pipelines/recommendations/run_local.py \
      --site-effects <real gold_site_effects> \
      --features demo/data_nyc/silver_features.parquet \
      --interventions demo/data_nyc/silver_interventions.parquet \
      --out-dir demo/data_nyc
  python pipelines/recommendations/build_panel_sample.py \
      --panel <nyc_silver_panel.parquet from agent-2-satellite> \
      --site-effects <real gold_site_effects> \
      --interventions demo/data_nyc/silver_interventions.parquet \
      --out demo/data_nyc/panel_sample.parquet
  ```

Run the app on either snapshot:

```bash
HEATSEEKER_DATA_DIR=demo/data_nyc streamlit run app/app.py
```
