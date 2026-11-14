# Samples and interim NYC tables

No agent has a Databricks workspace yet, so the real NYC silver tables are
published here as CSV so Agents 3 and 4 can read them. Once the workspace
exists these move to Delta tables and the CSVs are deleted.

| File | Contents |
|---|---|
| `nyc_forestry_tree_points_sample_100.csv` | 100 raw rows as received: all 20 rows with an unusable planting year, 65 dated rows, 15 undated |
| `nyc_silver_interventions.csv` | Full `silver.interventions` for NYC (24,436 cell-years, 5,686 cells) |
| `nyc_silver_features.csv` | Full `silver.features` for NYC (7,414 cells). `elevation_m` and `median_household_income` are still null |

All sources are public; licenses are recorded in bronze.
