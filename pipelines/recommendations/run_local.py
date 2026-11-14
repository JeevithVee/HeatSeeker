"""Learn + Plan on real tables, no Databricks needed (mirrors Agent 3's
pipelines/site_effects/run_local.py pattern).

    python pipelines/recommendations/run_local.py \
        --site-effects <gold_site_effects.parquet-or-csv> \
        --features <silver_features.csv-or-parquet> \
        --interventions <silver_interventions.csv-or-parquet> \
        --out-dir out/nyc [--as-of-year 2026] [--model-version v1] [--no-mlflow]

Writes gold_recommendations.parquet, prediction_log.parquet and
prediction_scores.parquet to --out-dir. The same core code runs on
Databricks with Delta tables swapped in for the file paths.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml

os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from core.learning import log_predictions, score_predictions
from core.learning.effect_model import train_effect_model
from core.ranking import find_candidates, rank_candidates


def read_any(path: str) -> pd.DataFrame:
    p = Path(path)
    return pd.read_csv(p) if p.suffix == ".csv" else pd.read_parquet(p)


def main() -> None:
    ap = argparse.ArgumentParser()
    # Each input accepts several files (e.g. one per city); the model is
    # trained pooled across all of them, ranking stays per city.
    ap.add_argument("--site-effects", required=True, nargs="+")
    ap.add_argument("--features", required=True, nargs="+")
    ap.add_argument("--interventions", required=True, nargs="+")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--config", default=str(REPO / "config" / "us" / "config.yaml"))
    ap.add_argument("--as-of-year", type=int,
                    default=datetime.now(timezone.utc).year)
    ap.add_argument("--model-version",
                    default=f"v1-{datetime.now(timezone.utc):%Y%m%d%H%M}")
    ap.add_argument("--no-mlflow", action="store_true")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text())
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    effects = pd.concat([read_any(p) for p in args.site_effects], ignore_index=True)
    features = pd.concat([read_any(p) for p in args.features], ignore_index=True)
    interventions = pd.concat(
        [read_any(p) for p in args.interventions], ignore_index=True)

    model, train = train_effect_model(
        effects, features, as_of_year=args.as_of_year,
        mlflow_tracking_uri=None if args.no_mlflow
        else f"file://{REPO / 'demo' / 'mlruns'}",
        model_version=args.model_version,
    )
    print(f"trained on {len(train)} evaluated sites (variant=all, labels pooled)")

    # Candidates: unplanted or barely-planted cells that pass the rules.
    planted = interventions.groupby("site_id")["trees_planted"].sum()
    heavily_planted = set(planted[planted > 2].index)
    pool = features[~features["site_id"].isin(heavily_planted)].copy()

    # Data-quality policy (not in core): cells with no vulnerability data
    # (e.g. no SVI tract) rank as if no vulnerable residents live there.
    n_null = pool["vulnerable_residents"].isna().sum()
    if n_null:
        print(f"note: {n_null} candidate-pool cells lack vulnerability data; "
              "treated as 0 vulnerable residents (deprioritized, not dropped)")
        pool["vulnerable_residents"] = pool["vulnerable_residents"].fillna(0)

    candidates = find_candidates(pool, cfg["candidate_rules"])
    dose = int(interventions.groupby("site_id")["trees_planted"].sum().median())
    candidates = candidates.assign(dose_trees=dose)
    print(f"{len(candidates)} candidate cells (assumed planting: {dose} trees)")

    horizons = cfg["horizons_years"]
    preds_by_h = {h: model.predict_at_age(candidates, h) for h in horizons}

    log = log_predictions(
        candidates[["country_code", "city_id"]].reset_index(drop=True)
        .join(preds_by_h[max(horizons)].reset_index(drop=True))
        .assign(model_version=args.model_version),
        out / "prediction_log.parquet",
    )
    print(f"prediction log: {len(log)} rows (at {max(horizons)}y horizon)")

    recs = rank_candidates(
        candidates, preds_by_h,
        costs_usd=cfg["costs_usd"],
        holdout_every_n=cfg["ranking"]["holdout_every_n"],
        model_version=args.model_version,
    )
    recs.to_parquet(out / "gold_recommendations.parquet", index=False)
    print(f"gold.recommendations: {len(recs)} rows, "
          f"{recs['holdout_control'].sum()} holdout controls")
    print(recs.head(10)[["site_id", "rank", "score", "predicted_cooling_k_15y",
                         "vulnerable_residents", "suggested_intervention"]]
          .to_string(index=False))

    scored = score_predictions(log, effects)
    scored.to_parquet(out / "prediction_scores.parquet", index=False)
    print(f"scored {len(scored)} predictions against measured outcomes")


if __name__ == "__main__":
    main()
