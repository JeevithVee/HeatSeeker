# Samples

| File | Contents |
|---|---|
| `nyc_forestry_tree_points_sample_100.csv` | 100 raw NYC rows as received: all 20 rows with an unusable planting year, 65 dated rows, 15 undated |

The per-city silver tables that used to sit here as CSV are retired. They are
Delta tables now, `heatseeker.silver.interventions` and
`heatseeker.silver.features`, built from bronze by `pipelines/build_silver.py`.
The retired CSVs are in Git history at commit c0fc9df and earlier (NYC from
72b5b1a, the other cities from ea5fcf0), and are the files `gold.site_effects`
version 10 was first computed from; the Delta tables hold the same rows.
