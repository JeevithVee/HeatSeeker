# Agent 1: what is left (updated 2026-11-14, after NYC delivery)

Agent 1's session is paused. Items marked **Agent 2** are handed over; the
rest wait for Agent 1 or the human.

## Done
- Shared schema frozen at v1.0.0 (`schema/tables.yaml`), all six tables.
- NYC `silver.interventions` and `silver.features`, including elevation from
  Agent 2. Interim CSVs in `ingest/us/samples/`.
- Agent 3 has run the real NYC evaluation on these tables.

## Handed to Agent 2: preload DC, San Francisco, Seattle
Work on a new branch `agent-2-city-preload` cut from `agent-1-data`. Stay
inside `ingest/us/`, `pipelines/run_interventions.py` (the `ADAPTERS` dict
only) and `tests/`. Do not edit `/schema`. Do one city fully before the next;
order DC, Seattle, San Francisco (DC has the most dated plantings).

Setup: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`,
tests with `.venv/bin/python -m pytest tests -q` (9 pass today).

Per city:
1. **Boundary and grid.** Add the city to `SOURCES` in
   `ingest/us/city_boundaries.py` (a GeoJSON URL of the city land boundary,
   clipped to the shoreline, plus its license), then
   `python -m pipelines.grid <city_id>` writes
   `ingest/us/grids/<city_id>_res9_cells.csv`. This is the grid the Earth
   Engine export must use. Sanity-check total area against the city's known
   land area (DC about 158 km2, SF about 121 km2, Seattle about 217 km2).
2. **Tree adapter.** Copy the shape of `ingest/us/nyc_tree_points.py`:
   `fetch`, `read_raw`, `to_bronze`, `to_records`, with `CITY_ID`,
   `SOURCE_ID`, `LICENSE`, `COVERAGE_START_YEAR`. `to_records` must return
   exactly `common.RECORD_COLUMNS`. Use `common.classify_dates` and pass the
   city's placeholder dates. Set `removal_tracked=False` and `removed=False`
   where the inventory lists only standing trees. Register it in `ADAPTERS`.
3. **Run** `python -m pipelines.run_interventions <city_id>` then
   `python -m pipelines.run_features <city_id>`. Canopy, impervious, land
   cover, population and vulnerability need no new code; counties are already
   in `ingest/us/census.py`. Put `<city_id>_static.csv` (elevation) at
   `pipelines/panel/out/` and the features job joins it.
4. **Publish** `ingest/us/samples/<city_id>_silver_{interventions,features}.csv`
   the same way as NYC and add a test with a few hand-made rows per adapter.
5. **Post on the MessageBoard**: row counts, the cleaning report the job
   prints, plantings per year, and how many cells reach 10 trees in 2015-2019.

City notes (from `CLAUDE.md`, sources unverified until fetched):

| City | Source | Cleaning |
|---|---|---|
| dc | 63-city dataset DC file; live Street Trees and Street Tree Archive for 2021 on. `planted_date`, lat/lon | About 109,000 rows dated 1970-01-01 are placeholders: pass as `placeholder_dates`, do not count as plantings |
| sea | 63-city dataset Seattle file; live SDOT trees layer `PLANTED_DATE` for newer years | Round-number dates such as 2000-01-01 are placeholders |
| sf | Live Street Tree List on data.sf.gov (not the 63-city copy); confirm column names | Only 27% of trees are dated; report whether dated trees cluster in a few neighbourhoods |

Things that will bite:
- Timestamps may be UTC. Convert to the city's local calendar day before
  taking the date (see `LOCAL_TZ` in the NYC adapter).
- `flag_batch_days` threshold is 300 trees per day citywide. Report the
  busiest days; do not tune the threshold to produce a contrast.
- Keep `land_cover_class` strings exactly as `mrlc.LAND_COVER_CLASSES`
  produces them; Agents 3 and 4 match on them character for character.
- If a city's planting records turn out unusable, say so on the board
  immediately. Columbus is the backup.
- Record every source's license in bronze.

## Staying with Agent 1 (on return)
- Review and merge `agent-2-city-preload` into `agent-1-data`.
- Cross-review Agent 3's statistics once, as the brief requires.
- Load the silver tables into `heatseeker.silver.*` once this session has a
  Databricks login (`pipelines/io.py` already writes Delta under Spark).
- `median_household_income`: needs a Census API key from the human.

## Needs the human
- Tell Agent 2 to pick up this file.
- Databricks login for this machine (catalog `heatseeker` exists; Agent 3
  created it).
- Census API key, optional.
