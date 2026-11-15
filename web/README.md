# /web

The rebuilt HeatSeeker website: a landing page and a map-first tool. Plain
HTML, CSS and JavaScript served by a small FastAPI app, so it runs locally and
as a Databricks App. It reads the same tables as `/app` and does not replace
or change it.

**Owner:** built by Agent 2 at the human's request (2026-11-14). `/app`
(Streamlit) remains Agent 4's.

## Run

```bash
pip install -r web/requirements.txt
uvicorn server:app --app-dir web --port 8600
# http://localhost:8600            landing page
# http://localhost:8600/dashboard  the tool
```

## Pages

- **Landing** (`static/index.html`): three screens. The hero draws a real city
  cell by cell from Landsat surface temperature and reacts to the pointer; the
  loop section is pinned while the four steps play; the last screen states what
  the evidence shows. GSAP and ScrollTrigger drive the motion, Lenis the scroll.
  With reduced motion set, everything rests.
- **Tool** (`static/dashboard.html`): the map fills the screen and the controls
  float around it. City switch and the three steps (Plan, Plant, Prove) sit in
  the top bar; the left panel changes what the map is coloured by; clicking a
  cell opens its details on the right, including the form that logs a planting.
  The view is kept in the URL (`?city=&mode=&layer=&site=`), so it can be shared.

## Data

`build_data.py` writes `static/data/` from the standard tables. Nothing is
estimated in the site: every number is copied or aggregated from
`silver.features`, `silver.interventions`, `silver.panel`, `gold.site_effects`
and `gold.recommendations`. Storage units are kept (Kelvin, fractions); the
browser converts to the display unit named in `config/us/config.yaml`.

```bash
pip install -r web/requirements-build.txt
python web/build_data.py --snapshot demo/data_real --panel-dir data/panel
```

`--panel-dir` holds `<city>_silver_panel.parquet` (branch `agent-2-satellite`,
`pipelines/panel/out/`). The surface-heat layer is each cell's mean
`lst_median_k` minus the city median of the same scene, over Landsat 8/9 scenes
since 2022 that cover at least half the city.

Plantings logged in the tool are appended to `var/plantings.jsonl`
(`HEATSEEKER_LOG_DIR` to move it). They are not yet written to
`silver.interventions`.

## Rules the pages keep

- Surface temperature is not felt temperature: stated on the landing page, on
  the tool at all times, and beside every measured result.
- All four cities are temperate: stated alongside.
- "Detected" is shown as a statistical label that includes warming;
  inconclusive is reported as the usual outcome; predictions are labelled as
  model output with ranges.

## Third-party code in `static/vendor`

GSAP 3.12.5 and ScrollTrigger (GSAP standard licence), Lenis 1.1.14 (MIT),
MapLibre GL JS 4.7.1 (BSD-3-Clause). The basemap is loaded from CARTO
(© CARTO, © OpenStreetMap contributors); without it the cells still draw on a
plain ground. Fonts load from Google Fonts with system fallbacks.

## Not done

- Not deployed. `app.yaml` is written for a Databricks App but untested there.
- Reads a snapshot, not live SQL.
- Tested in headless Chrome at 1440 and 390 px wide; not in Safari or Firefox.
- The two design skills named in the brief (taste-skill, ui-ux-pro-max) were
  followed from their written rules; their automated checkers need Node and
  were not run.
