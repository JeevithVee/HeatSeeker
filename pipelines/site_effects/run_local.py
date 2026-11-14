"""Run the evaluation on local CSV/Parquet files (no Spark, no Databricks).

Agents 1 and 2 write silver tables as files until a workspace exists; this produces
gold.site_effects and the sanity report from those files so the first real result does not
wait on the platform. Same core code as the Databricks job.

Example:
  python pipelines/site_effects/run_local.py \
      --panel path/to/nyc_silver_panel_*.csv \
      --features path/to/nyc_silver_features.csv \
      --interventions path/to/nyc_silver_interventions.csv \
      --out-dir out/nyc
"""

import argparse
import glob
import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.evaluation import METHOD_VERSION, EvalConfig, evaluate_city_all_variants_with_reports  # noqa: E402
from core.evaluation.report import format_report  # noqa: E402


def read_any(paths: list[str]) -> pd.DataFrame:
    files = sorted(f for p in paths for f in glob.glob(p))
    if not files:
        raise FileNotFoundError(f"no files match {paths}")
    frames = []
    for f in files:
        if f.endswith(".parquet"):
            frames.append(pd.read_parquet(f))
        else:
            frames.append(pd.read_csv(f))
    df = pd.concat(frames, ignore_index=True)
    print(f"  read {len(files)} file(s), {len(df):,} rows")
    return df


def parse_args(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", nargs="+", required=True, help="silver.panel file(s) or globs")
    ap.add_argument("--features", nargs="+", required=True)
    ap.add_argument("--interventions", nargs="+", required=True)
    ap.add_argument("--static", nargs="*", default=None,
                    help="optional per-cell static table(s) (e.g. Agent 2's nyc_static.csv) merged into features on "
                         "site_id, filling columns that are missing or all-null there, such as elevation_m")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--city-id", default=None, help="filter all three tables to this city_id")
    ap.add_argument("--panel-version", default=None, help="label for the panel snapshot, e.g. export date")
    ap.add_argument("--n-bootstrap", type=int, default=200)
    ap.add_argument("--n-placebo", type=int, default=200)
    ap.add_argument("--min-dose", type=int, default=10)
    ap.add_argument("--sensors", nargs="+", default=None,
                    help="sensors to keep, e.g. LANDSAT_8 LANDSAT_9 LANDSAT_7 LANDSAT_5 (default: L8 + L9)")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    print("[site_effects/local] reading inputs")
    panel, features, interventions = read_any(args.panel), read_any(args.features), read_any(args.interventions)
    if args.city_id:
        panel, features, interventions = (
            df[df["city_id"] == args.city_id].reset_index(drop=True) for df in (panel, features, interventions)
        )
    if args.static:
        static = read_any(args.static).drop_duplicates("site_id").set_index("site_id")
        for col in static.columns:
            if col in ("country_code", "city_id") or col.endswith("_source"):
                continue
            if col not in features.columns or features[col].isna().all():
                features[col] = features["site_id"].map(static[col])
                print(f"  filled features.{col} from static table ({features[col].notna().sum():,} cells)")
    city = str(panel["city_id"].iloc[0])
    extra = {"sensors": tuple(args.sensors)} if args.sensors else {}
    cfg = EvalConfig(n_bootstrap=args.n_bootstrap, n_placebo=args.n_placebo, min_dose=args.min_dose, **extra)
    gold, reports = evaluate_city_all_variants_with_reports(panel, features, interventions, cfg, panel_version=args.panel_version)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    gold_path = out / f"{city}_gold_site_effects.csv"
    gold.to_csv(gold_path, index=False)
    gold.to_parquet(out / f"{city}_gold_site_effects.parquet", index=False)   # same rows, for Agent 4's pipeline
    report_path = out / f"{city}_site_effects_report.json"
    with open(report_path, "w") as fh:
        json.dump({"city_id": city, "method_version": METHOD_VERSION, "panel_version": args.panel_version,
                   "config": cfg.__dict__, "reports": reports}, fh, indent=1, default=str)
    for variant, rep in reports.items():
        print(f"[site_effects/local] --- sanity report, variant={variant} ---")
        print(format_report(rep))
    print(f"[site_effects/local] wrote {gold_path} ({len(gold)} rows) and {report_path}")


if __name__ == "__main__":
    main()
