"""Run the Learn + Plan loop end to end on the demo data.

generate_fake_data.py must run first. Writes to demo/data/:
  gold_recommendations.parquet, prediction_log.parquet, prediction_scores.parquet
and tracks the model in a local MLflow file store under demo/mlruns.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# MLflow's file store is fine for the local demo; Databricks tracking replaces it there.
os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")

import pandas as pd
import yaml

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.learn import log_predictions, score_predictions
from core.learn.effect_model import train_effect_model
from core.plan import find_candidates, rank_candidates

DATA = REPO / "demo" / "data"
CONFIG = yaml.safe_load((REPO / "config" / "us" / "config.yaml").read_text())
MODEL_VERSION = "v0-fake-data"


def main() -> None:
    features = pd.read_parquet(DATA / "silver_features.parquet")
    interventions = pd.read_parquet(DATA / "silver_interventions.parquet")
    effects = pd.read_parquet(DATA / "gold_site_effects.parquet")

    model, train = train_effect_model(
        effects, features, interventions,
        mlflow_tracking_uri=f"file://{REPO / 'demo' / 'mlruns'}",
        model_version=MODEL_VERSION,
    )
    print(f"trained on {len(train)} evaluated sites")

    unplanted = features[~features["site_id"].isin(interventions["site_id"])]
    candidates = find_candidates(unplanted, CONFIG["candidate_rules"])
    # Assume a typical planting for prediction: median planted count from history
    candidates = candidates.assign(
        trees_planted=int(interventions["trees_planted"].median())
    )
    print(f"{len(candidates)} candidate cells")

    preds = candidates[["country_code", "city_id"]].reset_index(drop=True).join(
        model.predict(candidates).reset_index(drop=True)
    )
    log = log_predictions(
        preds.assign(model_version=MODEL_VERSION), DATA / "prediction_log.parquet"
    )
    print(f"prediction log: {len(log)} rows")

    recs = rank_candidates(
        candidates, preds[["site_id", "pred_effect_c",
                           "pred_effect_c_low", "pred_effect_c_high"]],
        costs_usd=CONFIG["costs_usd"],
        vulnerability_weights=CONFIG["vulnerability_formula"]["weights"],
        maturity=CONFIG["cooling_maturity"],
        holdout_every_n=CONFIG["ranking"]["holdout_every_n"],
        model_version=MODEL_VERSION,
    )
    recs.to_parquet(DATA / "gold_recommendations.parquet", index=False)
    print(f"gold.recommendations: {len(recs)} rows, "
          f"{recs['holdout_control'].sum()} holdout controls")
    print(recs.head(5)[["site_id", "rank", "score", "predicted_cooling_c_15y",
                        "vulnerable_residents", "suggested_intervention"]])

    scored = score_predictions(log, effects)
    scored.to_parquet(DATA / "prediction_scores.parquet", index=False)
    print(f"scored {len(scored)} predictions against measured outcomes "
          f"(0 expected until recommended sites are planted and evaluated)")


if __name__ == "__main__":
    main()
