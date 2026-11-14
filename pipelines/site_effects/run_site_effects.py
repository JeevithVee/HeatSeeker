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
import copy
import hashlib
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # Workspace source snapshots are read-only on serverless.
REPO_ROOT = Path(globals().get("__file__", sys.argv[0])).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.evaluation import EvalConfig, evaluate_city_all_variants_with_reports  # noqa: E402
from core.evaluation.report import format_report  # noqa: E402
from core.evaluation.run import GOLD_COLUMNS  # noqa: E402
from pipelines.site_effects.load_gold import SQL_TYPES  # noqa: E402


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="heatseeker")
    ap.add_argument("--city-id", required=True)
    ap.add_argument("--n-bootstrap", type=int, default=200)
    ap.add_argument("--n-placebo", type=int, default=200)
    ap.add_argument("--min-dose", type=int, default=10)
    ap.add_argument("--sensors", nargs="+", default=None, help="sensors to keep (default: LANDSAT_8 LANDSAT_9)")
    ap.add_argument("--input-dir", default="", help="optional Volume directory of owner-provided silver files + manifest.json")
    ap.add_argument("--panel-source", choices=("files", "delta"), default="files",
                    help="with input-dir, optionally read a pinned silver.panel while other roles stay file-backed")
    ap.add_argument("--output-dir", default="", help="Volume output root; each city gets its own subdirectory")
    ap.add_argument("--publish-gold", choices=("true", "false"), default="true",
                    help="false writes robustness files/reports without replacing headline gold")
    ap.add_argument("--review-diagnostics", choices=("true", "false"), default="true",
                    help="run specification, fake-date and calendar-year sensitivity diagnostics")
    ap.add_argument("--report-path", default=None,
                    help="optional Volume path for the JSON sanity report, e.g. /Volumes/heatseeker/gold/reports/nyc_site_effects.json")
    return ap.parse_args(argv)


def table_version(spark, table: str) -> str:
    row = spark.sql(f"DESCRIBE HISTORY {table} LIMIT 1").collect()[0]
    return str(row["version"])


def read_inputs(spark, catalog, city, input_dir, panel_source="files"):
    """Read verified owner-provided files, or pinned snapshots of all three silver tables."""
    import pandas as pd
    if input_dir:
        root = Path(input_dir)
        manifest = json.loads((root / "manifest.json").read_text())
        sources = manifest["cities"][city]
        frames = {}
        for role, source in sources.items():
            path = root / source["file"]
            if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
                raise ValueError(f"Input checksum mismatch: {path.name}")
            frames[role] = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
        provenance = {"mode": "owner_provided_files", "inputs": sources,
                      "source_caveats": manifest.get("city_notes", {}).get(city, [])}
        version = "git:" + sources["panel"]["git_commit"]
        if panel_source == "delta":
            table = f"{catalog}.silver.panel"
            version = table_version(spark, table)
            frames["panel"] = (spark.read.option("versionAsOf", version).table(table)
                                .where(f"city_id = '{city}'").toPandas())
            provenance["mode"] = "delta_panel_with_owner_feature_intervention_files"
            provenance["inputs"] = {**sources, "panel": {"table": table, "delta_version": version,
                                                        "owner_file_reference": sources["panel"]}}
    else:
        frames, snapshots = {}, {}
        for role in ("panel", "features", "interventions"):
            table = f"{catalog}.silver.{role}"
            version = table_version(spark, table)
            snapshots[role] = {"table": table, "delta_version": version}
            frames[role] = (spark.read.option("versionAsOf", version).table(table)
                            .where(f"city_id = '{city}'").toPandas())
        provenance = {"mode": "delta_snapshots", "inputs": snapshots}
        version = snapshots["panel"]["delta_version"]
    for role, frame in frames.items():
        if frame.empty or set(frame.city_id.astype(str)) != {city}:
            raise ValueError(f"{role}: empty input or city_id mismatch for {city}")
        if frame.country_code.nunique() != 1:
            raise ValueError(f"{role}: expected one country")
    if frames["panel"].duplicated(["site_id", "scene_id"]).any():
        raise ValueError("Duplicate panel site/scene keys")
    if frames["features"].site_id.duplicated().any():
        raise ValueError("Duplicate feature site keys")
    return frames["panel"], frames["features"], frames["interventions"], version, provenance


def main(argv=None):
    args = parse_args(argv)
    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    cat = args.catalog
    gold_t = f"{cat}.gold.site_effects"

    where = f"city_id = '{args.city_id}'"
    from pipelines.site_effects.load_gold import identifier
    identifier(cat)
    identifier(args.city_id)
    panel, features, interventions, panel_version, provenance = read_inputs(
        spark, cat, args.city_id, args.input_dir, args.panel_source)
    snapshot = REPO_ROOT / "source_snapshot.json"
    if snapshot.is_file():
        provenance["code_snapshot"] = json.loads(snapshot.read_text())
    caveats = REPO_ROOT / "pipelines/site_effects/source_caveats.json"
    if caveats.is_file():
        context = json.loads(caveats.read_text())
        provenance["review_context"] = {
            "independent_review_commit": context["independent_review_commit"],
            "reviewed_snapshot": context["reviewed_snapshot"],
            "caveats": context["all_cities"] + context["city_notes"].get(args.city_id, []),
        }
    import numpy as np
    import pandas as pd
    provenance["runtime"] = {"python": sys.version, "numpy": np.__version__, "pandas": pd.__version__}
    print(f"[site_effects] {args.city_id}: panel rows={len(panel):,} cells={features.shape[0]:,} "
          f"intervention rows={len(interventions):,} panel version={panel_version}")

    extra = {"sensors": tuple(s for value in args.sensors for s in value.split())} if args.sensors else {}
    cfg = EvalConfig(n_bootstrap=args.n_bootstrap, n_placebo=args.n_placebo, min_dose=args.min_dose, **extra)
    provenance["analysis_purpose"] = ("cross_sensor_sensitivity_not_independent_confirmation"
                                      if {"LANDSAT_5", "LANDSAT_7"}.intersection(cfg.sensors)
                                      else "headline_observational_comparison")
    gold, reports = evaluate_city_all_variants_with_reports(panel, features, interventions, cfg, panel_version=panel_version)
    if args.review_diagnostics == "true":
        from core.evaluation.diagnostics import review_diagnostics
        cache = {}
        for variant, report in reports.items():
            cohort = gold.loc[gold.variant == variant, ["site_id", "treatment_year", "dose_trees"]]
            key = tuple(cohort.sort_values("site_id").itertuples(index=False, name=None))
            if key not in cache:
                print(f"[site_effects] review diagnostics, {args.city_id}/{variant}", flush=True)
                cache[key] = review_diagnostics(panel, features, interventions, cfg, variant)
            report["review_diagnostics"] = copy.deepcopy(cache[key])
            report["review_diagnostics"]["variant"] = variant
    print(f"[site_effects] rows={len(gold)}")
    for variant, rep in reports.items():
        print(f"[site_effects] --- sanity report, variant={variant} ---")
        print(format_report(rep))
    if args.report_path:
        Path(args.report_path).parent.mkdir(parents=True, exist_ok=True)
        with open(args.report_path, "w") as fh:
            json.dump({"city_id": args.city_id, "panel_version": panel_version,
                       "provenance": provenance, "config": cfg.__dict__, "reports": reports}, fh, indent=1, default=str)
        print(f"[site_effects] report written to {args.report_path}")

    if args.output_dir:
        out = Path(args.output_dir) / args.city_id
        out.mkdir(parents=True, exist_ok=True)
        gold.to_csv(out / f"{args.city_id}_gold_site_effects.csv", index=False)
        gold.to_parquet(out / f"{args.city_id}_gold_site_effects.parquet", index=False)
        (out / f"{args.city_id}_site_effects_report.json").write_text(json.dumps({
            "city_id": args.city_id, "panel_version": panel_version, "provenance": provenance,
            "config": cfg.__dict__, "reports": reports,
        }, indent=1, default=str))
    if args.publish_gold == "false":
        print("[site_effects] robustness files written; headline gold not replaced")
        return
    schema = ", ".join(f"{name} {kind}" for name, kind in SQL_TYPES.items())
    sdf = spark.createDataFrame(gold[GOLD_COLUMNS], schema=schema)
    (sdf.write.format("delta").mode("overwrite")
        .option("replaceWhere", where)
        .option("mergeSchema", "true")
        .saveAsTable(gold_t))
    print(f"[site_effects] wrote {gold_t} for {args.city_id}")


if __name__ == "__main__":
    main()
