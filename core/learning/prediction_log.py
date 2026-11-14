"""Prediction log: every prediction is recorded, then scored once its
outcome is measured. Append-only; storage is a parquet path for the
prototype, a Delta table on Databricks. Frozen columns posted to the board
2026-11-14 (Agent 4 msg 2)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

LOG_COLUMNS = [
    "country_code", "city_id", "site_id", "model_version",
    "pred_effect_k", "pred_effect_k_low", "pred_effect_k_high",
    "predicted_at_utc",
]


def log_predictions(predictions: pd.DataFrame, log_path: str | Path) -> pd.DataFrame:
    """Append predictions (LOG_COLUMNS minus predicted_at_utc) to the log."""
    log_path = Path(log_path)
    entry = predictions.copy()
    entry["predicted_at_utc"] = datetime.now(timezone.utc).isoformat()
    entry = entry[LOG_COLUMNS]
    if log_path.exists():
        entry = pd.concat([pd.read_parquet(log_path), entry], ignore_index=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry.to_parquet(log_path, index=False)
    return entry


def score_predictions(
    log: pd.DataFrame, site_effects: pd.DataFrame, variant: str = "all"
) -> pd.DataFrame:
    """Join logged predictions to measured effects (headline variant).

    Returns the log with measured_effect_k, error_k, within_interval and
    quality_label for every prediction whose site has been evaluated.
    """
    measured = site_effects[site_effects["variant"] == variant][
        ["country_code", "city_id", "site_id", "effect_k", "quality_label"]
    ].rename(columns={"effect_k": "measured_effect_k"})
    scored = log.merge(measured, on=["country_code", "city_id", "site_id"])
    scored["error_k"] = scored["pred_effect_k"] - scored["measured_effect_k"]
    scored["within_interval"] = (
        (scored["measured_effect_k"] >= scored["pred_effect_k_low"])
        & (scored["measured_effect_k"] <= scored["pred_effect_k_high"])
    )
    return scored
