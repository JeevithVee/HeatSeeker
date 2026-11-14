# Samples and interim NYC tables

No agent has a Databricks workspace yet, so the real NYC silver tables are
published here as CSV so Agents 3 and 4 can read them. Once the workspace
exists these move to Delta tables and the CSVs are deleted.

| File | Contents |
|---|---|
| `nyc_forestry_tree_points_sample_100.csv` | 100 raw rows as received: all 20 rows with an unusable planting year, 65 dated rows, 15 undated |
| `nyc_silver_interventions.csv` | Full `silver.interventions` for NYC (24,436 cell-years, 5,686 cells) |
| `nyc_silver_features.csv` | Full `silver.features` for NYC (7,414 cells). `elevation_m` is from Agent 2's SRTM export; `median_household_income` is still null |
| `dc_silver_interventions.csv`, `dc_silver_features.csv` | Washington DC: 19,514 cell-years in 1,300 cells; 1,548 cells of features |
| `sea_silver_interventions.csv`, `sea_silver_features.csv` | Seattle: 19,721 cell-years in 2,000 cells; 2,339 cells of features |
| `sf_silver_interventions.csv`, `sf_silver_features.csv` | San Francisco: 8,760 cell-years in 866 cells; 1,101 cells of features |

DC, Seattle and San Francisco were preloaded by Agent 2 on branch
`agent-2-city-preload` (Agent 1 handover). `elevation_m` is filled for all
three from Agent 2's SRTM export; `median_household_income` is null.

All sources are public; licenses are recorded in bronze.
