"""Candidate finding and ranking ("Plan").

Country-agnostic: costs, candidate rules, vulnerability weights and the
cooling maturity curve arrive as arguments, never imported from config.
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd


def compute_vulnerability(features: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Weighted sum of normalized feature columns -> score in [0, 1]."""
    score = pd.Series(0.0, index=features.index)
    total_w = sum(weights.values())
    for col, w in weights.items():
        v = features[col]
        rng = v.max() - v.min()
        norm = (v - v.min()) / rng if rng > 0 else 0.0
        score = score + (w / total_w) * norm
    return score


def find_candidates(features: pd.DataFrame, rules: dict) -> pd.DataFrame:
    """Cells eligible for planting: low canopy, not fully paved, allowed cover."""
    mask = (
        (features["canopy_pct"] <= rules["max_canopy_pct"])
        & (features["impervious_pct"] <= rules["max_impervious_pct"])
        & (features["land_cover"].isin(rules["allowed_land_cover"]))
    )
    return features[mask].copy()


def rank_candidates(
    candidates: pd.DataFrame,
    predictions: pd.DataFrame,
    costs_usd: dict[str, float],
    vulnerability_weights: dict[str, float],
    maturity: dict[str, float],
    holdout_every_n: int = 5,
    model_version: str = "v0",
) -> pd.DataFrame:
    """Build gold.recommendations.

    score = predicted mature cooling (°C, positive) × vulnerable residents ÷ cost.
    Every Nth ranked site is flagged holdout_control so unplanted lookalikes
    exist as future controls. Intervention suggestion: cheapest tree option
    that fits the cell (street trees on mostly-paved cells, park trees on open).
    """
    df = candidates.merge(predictions, on="site_id")

    df["vulnerability_score"] = compute_vulnerability(df, vulnerability_weights)
    df["vulnerable_residents"] = df["population"] * df["vulnerability_score"]

    df["suggested_intervention"] = np.where(
        df["impervious_pct"] >= 50, "street_trees", "park_trees"
    )
    df["est_cost_usd"] = df["suggested_intervention"].map(costs_usd)

    cooling_mature = -df["pred_effect_c"]  # negative effect = cooling
    for horizon in ("year_5", "year_15"):
        suffix = horizon.replace("year_", "")
        df[f"predicted_cooling_c_{suffix}y"] = cooling_mature * maturity[horizon]
        df[f"predicted_cooling_c_{suffix}y_low"] = -df["pred_effect_c_high"] * maturity[horizon]
        df[f"predicted_cooling_c_{suffix}y_high"] = -df["pred_effect_c_low"] * maturity[horizon]

    df["score"] = (
        df["predicted_cooling_c_15y"].clip(lower=0)
        * df["vulnerable_residents"]
        / df["est_cost_usd"]
    )
    df = df.sort_values("score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    df["holdout_control"] = (df["rank"] % holdout_every_n) == 0
    df["model_version"] = model_version
    df["recommended_at"] = datetime.now(timezone.utc).isoformat()

    cols = [
        "country_code", "city_id", "site_id", "lat", "lon", "rank", "score",
        "predicted_cooling_c_5y", "predicted_cooling_c_5y_low", "predicted_cooling_c_5y_high",
        "predicted_cooling_c_15y", "predicted_cooling_c_15y_low", "predicted_cooling_c_15y_high",
        "vulnerable_residents", "est_cost_usd", "suggested_intervention",
        "holdout_control", "model_version", "recommended_at",
    ]
    return df[cols]
