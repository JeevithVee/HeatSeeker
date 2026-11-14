"""Databricks job: silver.panel + silver.features + silver.interventions -> gold.site_effects.

Runs as a Python script task on serverless compute from the repo's Git folder. The heavy
lifting is pandas inside /core/evaluation; Spark only reads and writes Delta.

Parameters (job parameters or CLI flags):
  --catalog        Unity Catalog name (default: heatseeker)
  --city-id        e.g. nyc
  --n-bootstrap    default 200
  --n-placebo      default 200
  --min-dose       default 10
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.evaluation import EvalConfig, evaluate_city_all_variants_with_reports  # noqa: E402
from core.evaluation.report import format_report  # noqa: E402
from core.evaluation.run import GOLD_COLUMNS  # noqa: E402


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="heatseeker")
    ap.add_argument("--city-id", required=True)
    ap.add_argument("--n-bootstrap", type=int, default=200)
    ap.add_argument("--n-placebo", type=int, default=200)
    ap.add_argument("--min-dose", type=int, default=10)
    ap.add_argument("--report-path", default=None,
                    help="optional Volume path for the JSON sanity report, e.g. /Volumes/heatseeker/gold/reports/nyc_site_effects.json")
    return ap.parse_args(argv)


def table_version(spark, table: str) -> str:
    row = spark.sql(f"DESCRIBE HISTORY {table} LIMIT 1").collect()[0]
    return str(row["version"])


def main(argv=None):
    args = parse_args(argv)
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    cat = args.catalog
    panel_t, feat_t, iv_t = f"{cat}.silver.panel", f"{cat}.silver.features", f"{cat}.silver.interventions"
    gold_t = f"{cat}.gold.site_effects"

    where = f"city_id = '{args.city_id}'"
    panel = spark.table(panel_t).where(where).toPandas()
    features = spark.table(feat_t).where(where).toPandas()
    interventions = spark.table(iv_t).where(where).toPandas()
    panel_version = table_version(spark, panel_t)
    print(f"[site_effects] {args.city_id}: panel rows={len(panel):,} cells={features.shape[0]:,} "
          f"intervention rows={len(interventions):,} panel version={panel_version}")

    cfg = EvalConfig(n_bootstrap=args.n_bootstrap, n_placebo=args.n_placebo, min_dose=args.min_dose)
    gold, reports = evaluate_city_all_variants_with_reports(panel, features, interventions, cfg, panel_version=panel_version)
    print(f"[site_effects] rows={len(gold)}")
    for variant, rep in reports.items():
        print(f"[site_effects] --- sanity report, variant={variant} ---")
        print(format_report(rep))
    if args.report_path:
        import json
        with open(args.report_path, "w") as fh:
            json.dump({"city_id": args.city_id, "panel_version": panel_version, "reports": reports}, fh, indent=1, default=str)
        print(f"[site_effects] report written to {args.report_path}")

    sdf = spark.createDataFrame(gold[GOLD_COLUMNS])
    (sdf.write.format("delta").mode("overwrite")
        .option("replaceWhere", where)
        .option("mergeSchema", "true")
        .saveAsTable(gold_t))
    print(f"[site_effects] wrote {gold_t} for {args.city_id}")


if __name__ == "__main__":
    main()
