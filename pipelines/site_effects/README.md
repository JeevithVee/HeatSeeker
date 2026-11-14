# /pipelines/site_effects

Job that writes `gold.site_effects` for one city. Thin Spark wrapper around `/core/evaluation`.

**Owner:** Agent 3

```
python pipelines/site_effects/run_site_effects.py --catalog heatseeker --city-id nyc
```

Reads `silver.panel`, `silver.features`, `silver.interventions` filtered to the city, records the
panel's Delta version (for time travel), evaluates both variants (`all`, `excl_batch_dated`), and
overwrites that city's rows in `gold.site_effects` with `replaceWhere`.

Status: written against the frozen schema names; not yet run on a workspace.
