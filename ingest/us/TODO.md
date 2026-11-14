# Agent 1: status and what is left (updated 2026-11-14, after the Databricks load)

## Done
- Shared schema frozen at v1.0.0 (`schema/tables.yaml`), all six tables.
- `silver.interventions` and `silver.features` for NYC (Agent 1) and for DC,
  Seattle and San Francisco (built by Agent 2 on handover, reviewed and merged).
- Both tables are live in Databricks: `heatseeker.silver.interventions`
  (72,431 rows) and `heatseeker.silver.features` (12,402 rows), Delta
  version 1, loaded by job `heatseeker-load-silver` (506579230445270) from the
  CSVs in `ingest/us/samples/`. Those are the same files, by checksum, that
  `gold.site_effects` was computed from.

## Done since the silver load
- Cross-review of Agent 3's statistics: `pipelines/reviews/agent3_statistics_review.md`.
- NYC bronze is in Databricks: `heatseeker.bronze.nyc_forestry_tree_points`
  (1,125,266 rows), `bronze.census_2020_blocks_tigerweb` (37,984),
  `bronze.cdc_svi_2022_tracts` (2,324), each with its license. As-received
  files (tree CSV, boundary, four NLCD rasters, census CSVs, elevation) are in
  `/Volumes/heatseeker/bronze/landing/us/nyc/`.
- NYC silver is proven to follow from bronze inside the workspace: job
  `heatseeker-verify-silver-from-bronze` (334451516814053) rebuilt both tables
  from bronze with the real build code and found them identical to the live
  tables (run 1107437999708243). It writes nothing.

- Bronze for DC, Seattle and San Francisco is in Databricks too (raw files
  uploaded by Agent 2, tables created by Agent 1): `bronze.dc_urban_forestry_street_trees`
  (224,097 rows), `bronze.sea_sdot_trees` (276,760), `bronze.sf_street_tree_list`
  (144,606); the two census bronze tables now hold all four cities.
- The verify job passed for every city: both silver tables rebuilt from bronze
  are identical to the live ones (runs 1107437999708243 nyc, 128201262853483 dc,
  614162988893915 sea, 352161324993762 sf).

## Left
- Delete the interim CSVs in `ingest/us/samples/` once nothing reads them:
  Agent 4's app snapshot and `pipelines/load_silver.py` still do. With bronze
  in place the loader could rebuild from bronze instead.
- `median_household_income` is null everywhere: needs a Census API key.
- `CLAUDE.md` city notes are stale for DC (no 1970-01-01 rows in the live
  layer; one layer covers every year). Needs the human's approval to edit.

## Known limits of the data (carry into any result text)
- Seattle: about 8,300 trees dated 1 January 2015-2019 were dropped as
  placeholder dates, so some Seattle control cells were in fact planted.
- DC and San Francisco list mostly standing trees (`removal_tracked` = false),
  so plantings that died are missing.
- San Francisco: 4,880 dated trees have no coordinates and are not in the table.
