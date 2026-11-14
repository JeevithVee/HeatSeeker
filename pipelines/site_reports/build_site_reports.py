"""Build gold.site_reports: an LLM-phrased plain-language report per evaluated site.

Shared rule 12: every number comes from gold.site_effects and silver.features; the model only
turns them into sentences. Runs entirely on the SQL warehouse via ai_query, driven from the
Databricks CLI (no cluster, no Spark locally).

    python pipelines/site_reports/build_site_reports.py --profile heatseeker [--city nyc] [--limit 50]

Rerunnable: rows for the selected cities are replaced (INSERT ... REPLACE WHERE).
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PROMPT = (REPO / "llm" / "site_report_prompt.txt").read_text()
MODEL = "databricks-meta-llama-3-3-70b-instruct"
TABLE = "{catalog}.gold.site_reports"

CREATE = """
CREATE TABLE IF NOT EXISTS {table} (
  country_code STRING, city_id STRING, site_id STRING, variant STRING,
  report_text STRING, model STRING, site_effects_version STRING, generated_at_utc TIMESTAMP
) USING DELTA
COMMENT 'LLM-phrased site reports. Numbers come only from gold.site_effects and silver.features (shared rule 12). Surface temperature is not felt temperature.'
"""

# The prompt text is passed as a SQL string literal; the data block is assembled in SQL so the
# model sees exactly the stored values.
BUILD = """
INSERT INTO {table} REPLACE WHERE {where}
WITH s AS (
  SELECT e.country_code, e.city_id, e.site_id, e.variant, e.treatment_year, e.dose_trees, e.effect_k,
         e.ci_low_k, e.ci_high_k, e.mde_k, e.placebo_p, e.quality_label, e.n_pre_scenes, e.n_post_scenes,
         e.n_controls, f.canopy_frac_baseline, f.impervious_frac, f.land_cover_class, f.population
  FROM {catalog}.gold.site_effects e
  JOIN {catalog}.silver.features f USING (country_code, city_id, site_id)
  WHERE e.variant = 'all' AND {where}
  {limit}
)
SELECT country_code, city_id, site_id, variant,
  ai_query('{model}', CONCAT({prompt},
    'Cell ', site_id, ' in city ', upper(city_id), '. Trees planted 2015-2019: ', dose_trees,
    ', counted as planted from ', treatment_year, '. Measured effect: ', ROUND(effect_k, 2),
    ' K (95% interval ', ROUND(ci_low_k, 2), ' to ', ROUND(ci_high_k, 2), ' K). Minimum detectable effect at this cell: ',
    ROUND(mde_k, 2), ' K. Placebo p: ', ROUND(placebo_p, 3), '. Label: ', quality_label,
    '. Clear-sky scenes before/after planting: ', n_pre_scenes, '/', n_post_scenes, '. Matched unplanted control cells: ', n_controls,
    '. Cell context: tree canopy ', CAST(ROUND(canopy_frac_baseline * 100) AS INT), '%, impervious surface ',
    CAST(ROUND(impervious_frac * 100) AS INT), '%, land cover ', replace(land_cover_class, '_', ' '),
    ', residents ', CAST(ROUND(coalesce(population, 0)) AS INT), '.')) AS report_text,
  '{model}' AS model, '{version}' AS site_effects_version, current_timestamp() AS generated_at_utc
FROM s
"""


def cli(*args, profile):
    out = subprocess.run(["databricks", *args, "-p", profile, "-o", "json"], capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"databricks {' '.join(args[:2])} failed: {out.stderr[:500]}")
    return json.loads(out.stdout) if out.stdout.strip() else {}


def run_sql(statement, warehouse, profile, timeout_s=1800):
    body = {"warehouse_id": warehouse, "statement": statement, "wait_timeout": "50s", "on_wait_timeout": "CONTINUE"}
    d = cli("api", "post", "/api/2.0/sql/statements", "--json", json.dumps(body), profile=profile)
    sid, t0 = d["statement_id"], time.time()
    while d["status"]["state"] in ("PENDING", "RUNNING"):
        if time.time() - t0 > timeout_s:
            raise SystemExit(f"statement {sid} still running after {timeout_s}s")
        time.sleep(10)
        d = cli("api", "get", f"/api/2.0/sql/statements/{sid}", profile=profile)
    st = d["status"]
    if st["state"] != "SUCCEEDED":
        raise SystemExit(f"SQL {st['state']}: {(st.get('error') or {}).get('message', '')[:800]}")
    return d.get("result", {}).get("data_array") or []


def sql_literal(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n") + "'"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="heatseeker")
    ap.add_argument("--catalog", default="heatseeker")
    ap.add_argument("--warehouse", default="b646c232444bafe7")
    ap.add_argument("--city", nargs="*", default=None, help="city_id(s); default all")
    ap.add_argument("--limit", type=int, default=None, help="cap rows per run (testing)")
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args(argv)

    table = TABLE.format(catalog=args.catalog)
    where = "city_id IN (" + ", ".join(f"'{c}'" for c in args.city) + ")" if args.city else "TRUE"
    version = run_sql(f"DESCRIBE HISTORY {args.catalog}.gold.site_effects LIMIT 1", args.warehouse, args.profile)[0][0]
    print(f"[site_reports] gold.site_effects version {version}; cities: {args.city or 'all'}")

    run_sql(CREATE.format(table=table), args.warehouse, args.profile)
    stmt = BUILD.format(table=table, catalog=args.catalog, where=where, model=args.model, version=version,
                        prompt=sql_literal(PROMPT), limit=f"LIMIT {args.limit}" if args.limit else "")
    t0 = time.time()
    run_sql(stmt, args.warehouse, args.profile)
    rows = run_sql(f"SELECT city_id, COUNT(*), MIN(length(report_text)), MAX(length(report_text)) FROM {table} "
                   f"WHERE {where} GROUP BY city_id ORDER BY city_id", args.warehouse, args.profile)
    print(f"[site_reports] done in {time.time() - t0:.0f}s:")
    for r in rows:
        print(f"  {r[0]}: {r[1]} reports, text length {r[2]}-{r[3]}")


if __name__ == "__main__":
    main()
