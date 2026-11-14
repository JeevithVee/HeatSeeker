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

## Left
- Cross-review Agent 3's statistics once, as the brief requires.
- Bronze for Agent 1's sources (tree inventories, census, NLCD rasters) is not
  in Databricks; the raw files exist only on the machines that built them.
- The silver tables are published from files. Rebuilding them from source
  inside Databricks (`run_interventions`, `run_features` under Spark) has not
  been run; the city tree layers are live, so a rebuild would differ from the
  tables the current gold results used.
- Delete the interim CSVs in `ingest/us/samples/` once Agents 3 and 4 read the
  Delta tables. The loader job reads them too, so it must change first.
- `median_household_income` is null everywhere: needs a Census API key.
- `CLAUDE.md` city notes are stale for DC (no 1970-01-01 rows in the live
  layer; one layer covers every year). Needs the human's approval to edit.

## Known limits of the data (carry into any result text)
- Seattle: about 8,300 trees dated 1 January 2015-2019 were dropped as
  placeholder dates, so some Seattle control cells were in fact planted.
- DC and San Francisco list mostly standing trees (`removal_tracked` = false),
  so plantings that died are missing.
- San Francisco: 4,880 dated trees have no coordinates and are not in the table.
