# /pipelines/site_reports

Builds `gold.site_reports`: a 3–4 sentence plain-language report per evaluated site, phrased by
an LLM from numbers in `gold.site_effects` and `silver.features` (shared rule 12: the model never
produces a figure). Runs as `ai_query` on the SQL warehouse via the Databricks CLI.

```
python pipelines/site_reports/build_site_reports.py --profile heatseeker            # all cities
python pipelines/site_reports/build_site_reports.py --city nyc --limit 5           # smoke test
```

Prompt: `llm/site_report_prompt.txt`. Model: `databricks-meta-llama-3-3-70b-instruct`.
Rows for the selected cities are replaced on each run; `site_effects_version` records the gold
version the numbers came from. The app's Results view shows the report under the site detail.
