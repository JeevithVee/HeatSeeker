"""Run the Learn + Plan loop end to end on the demo data.

generate_fake_data.py must run first. Writes to demo/data/:
  gold_recommendations.parquet, prediction_log.parquet, prediction_scores.parquet
and tracks the model in a local MLflow file store under demo/mlruns.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import yaml

# MLflow's file store is fine for the local demo; Databricks tracking replaces it there.
os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.learning import log_predictions, score_predictions
from core.learning.effect_model import train_effect_model
from core.ranking import find_candidates, rank_candidates

DATA = REPO / "demo" / "data"
CONFIG = yaml.safe_load((REPO / "config" / "us" / "config.yaml").read_text())
MODEL_VERSION = "v0-fake-data"
AS_OF_YEAR = 2026


def main() -> None:
    features = pd.read_parquet(DATA / "silver_features.parquet")
    interventions = pd.read_parquet(DATA / "silver_interventions.parquet")
    effects = pd.read_parquet(DATA / "gold_site_effects.parquet")

    model, train = train_effect_model(
        effects, features, as_of_year=AS_OF_YEAR,
        mlflow_tracking_uri=f"file://{REPO / 'demo' / 'mlruns'}",
        model_version=MODEL_VERSION,
    )
    print(f"trained on {len(train)} evaluated sites (variant=all, all labels pooled)")

    unplanted = features[~features["site_id"].isin(interventions["site_id"])]
    candidates = find_candidates(unplanted, CONFIG["candidate_rules"])
    # Assume a typical planting for prediction: median planted count from history
    candidates = candidates.assign(
        dose_trees=int(interventions["trees_planted"].median())
    )
    print(f"{len(candidates)} candidate cells")

    horizons = CONFIG["horizons_years"]
    preds_by_h = {h: model.predict_at_age(candidates, h) for h in horizons}

    log = log_predictions(
        candidates[["country_code", "city_id"]].reset_index(drop=True)
        .join(preds_by_h[max(horizons)].reset_index(drop=True))
        .assign(model_version=MODEL_VERSION),
        DATA / "prediction_log.parquet",
    )
    print(f"prediction log: {len(log)} rows (at {max(horizons)}y horizon)")

    recs = rank_candidates(
        candidates, preds_by_h,
        costs_usd=CONFIG["costs_usd"],
        holdout_every_n=CONFIG["ranking"]["holdout_every_n"],
        model_version=MODEL_VERSION,
    )
    recs.to_parquet(DATA / "gold_recommendations.parquet", index=False)
    print(f"gold.recommendations: {len(recs)} rows, "
          f"{recs['holdout_control'].sum()} holdout controls")
    print(recs.head(5)[["site_id", "rank", "score", "predicted_cooling_k_15y",
                        "vulnerable_residents", "suggested_intervention"]])

    scored = score_predictions(log, effects)
    scored.to_parquet(DATA / "prediction_scores.parquet", index=False)
    print(f"scored {len(scored)} predictions against measured outcomes "
          f"(0 expected until recommended sites are planted and evaluated)")


if __name__ == "__main__":
    main()
