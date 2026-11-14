"""Prediction log: every prediction is recorded, then scored once its
outcome is measured. Append-only; storage is a parquet path for the
prototype, a Delta table on Databricks."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

LOG_COLUMNS = [
    "country_code", "city_id", "site_id", "model_version",
    "pred_effect_c", "pred_effect_c_low", "pred_effect_c_high",
    "predicted_at",
]


def log_predictions(predictions: pd.DataFrame, log_path: str | Path) -> pd.DataFrame:
    """Append predictions (LOG_COLUMNS minus predicted_at) to the log."""
    log_path = Path(log_path)
    entry = predictions.copy()
    entry["predicted_at"] = datetime.now(timezone.utc).isoformat()
    entry = entry[LOG_COLUMNS]
    if log_path.exists():
        entry = pd.concat([pd.read_parquet(log_path), entry], ignore_index=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry.to_parquet(log_path, index=False)
    return entry


def score_predictions(log: pd.DataFrame, site_effects: pd.DataFrame) -> pd.DataFrame:
    """Join logged predictions to measured effects.

    Returns the log with measured_effect_c, error_c, within_interval and
    quality_label for every prediction whose site has been evaluated.
    """
    measured = site_effects[
        ["country_code", "city_id", "site_id", "effect_c", "quality_label"]
    ].rename(columns={"effect_c": "measured_effect_c"})
    scored = log.merge(measured, on=["country_code", "city_id", "site_id"])
    scored["error_c"] = scored["pred_effect_c"] - scored["measured_effect_c"]
    scored["within_interval"] = (
        (scored["measured_effect_c"] >= scored["pred_effect_c_low"])
        & (scored["measured_effect_c"] <= scored["pred_effect_c_high"])
    )
    return scored
