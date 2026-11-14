"""Audit cloud output files and, optionally, exact parity with published gold."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipelines.site_effects.load_gold import SQL_TYPES, Warehouse, identifier, source_sql


def verify(profile, catalog, run_id, receipt, robustness=False, expected_gold_version=None):
    identifier(catalog)
    cli = Warehouse(profile)
    table = f"{catalog}.gold.site_effects"
    columns = ", ".join(SQL_TYPES)
    # pandas' Parquet timestamps may use nanoseconds, which this SQL warehouse's
    # Spark reader rejects. Audit the companion CSV using the same explicit types
    # and quote handling as the loader; pandas separately checks CSV/Parquet parity.
    path = f"/Volumes/{catalog}/gold/files/site_effects/runs/{int(run_id)}/*/*_gold_site_effects.csv"
    typed = ", ".join(f"CAST({name} AS {kind}) AS {name}" for name, kind in SQL_TYPES.items())
    incoming = f"SELECT {typed} FROM {source_sql(path)}"
    counts = cli.sql(f"WITH incoming AS ({incoming}) SELECT COUNT(*), "
                     "COUNT(DISTINCT country_code, city_id, site_id, variant), "
                     "COUNT_IF(method_version IS NULL OR method_version <> '0.3.0'), "
                     "COUNT_IF(quality_label = 'detected' AND NOT COALESCE(placebo_p < 0.05 "
                     "AND (ci_high_k < 0 OR ci_low_k > 0), false)) FROM incoming")
    n, unique, old, bad_detections = map(int, counts[0])
    if n <= 0 or n != unique or old or bad_detections:
        raise RuntimeError(f"Cloud files failed verification: {counts}")
    if not robustness:
        parity = cli.sql(f"WITH incoming AS ({incoming}), "
                         f"stored AS (SELECT {columns} FROM {table} WHERE city_id IN ('nyc','dc','sea','sf')), "
                         "missing AS (SELECT * FROM incoming EXCEPT ALL SELECT * FROM stored), "
                         "extra AS (SELECT * FROM stored EXCEPT ALL SELECT * FROM incoming) "
                         "SELECT (SELECT COUNT(*) FROM missing), (SELECT COUNT(*) FROM extra)")
        if list(map(int, parity[0])) != [0, 0]:
            raise RuntimeError(f"Gold differs from cloud CSV outputs: {parity}")
    history = cli.sql(f"DESCRIBE HISTORY {table} LIMIT 1")
    gold_version = int(history[0][0])
    if expected_gold_version is not None and gold_version != expected_gold_version:
        raise RuntimeError(f"Headline gold changed during robustness run: {gold_version} != {expected_gold_version}")
    summary = cli.sql(f"WITH incoming AS ({incoming}) "
                      "SELECT city_id, variant, quality_label, COUNT(*) AS n "
                      "FROM incoming GROUP BY ALL ORDER BY ALL")
    result = {"run_id": int(run_id), "mode": "robustness" if robustness else "headline",
              "cloud_rows": n, "unique_keys": unique, "method_version": "0.3.0",
              "gold_table": table, "gold_delta_version": gold_version,
              "exact_gold_csv_parity": not robustness,
              "headline_version_preserved": expected_gold_version is not None,
              "labels": summary}
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", default="heatseeker")
    ap.add_argument("--catalog", default="heatseeker")
    ap.add_argument("--run-id", type=int, required=True)
    ap.add_argument("--receipt", type=Path, required=True)
    ap.add_argument("--robustness", action="store_true")
    ap.add_argument("--expected-gold-version", type=int)
    args = ap.parse_args()
    verify(args.profile, args.catalog, args.run_id, args.receipt, args.robustness, args.expected_gold_version)
