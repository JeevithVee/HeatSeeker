"""Candidate finding and ranking ("Plan").

Country-agnostic: costs, candidate rules, vulnerability weights and the
prediction horizons arrive as arguments, never imported from config.
Output matches the frozen gold.recommendations columns (board, Agent 4 msg 2).
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd


def compute_vulnerability(features: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    """Weighted sum of min-max-scaled share columns -> score in [0, 1].

    Matches what Agent 1's build_features computes into vulnerability_index;
    kept here so the formula is testable and reusable when only raw shares
    exist.
    """
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
        (features["canopy_frac_baseline"] <= rules["max_canopy_frac"])
        & (features["impervious_frac"] <= rules["max_impervious_frac"])
        & (features["land_cover_class"].isin(rules["allowed_land_cover_class"]))
    )
    return features[mask].copy()


def rank_candidates(
    candidates: pd.DataFrame,
    predictions_by_horizon: dict[int, pd.DataFrame],
    costs_usd: dict[str, float],
    holdout_every_n: int = 5,
    model_version: str = "v0",
) -> pd.DataFrame:
    """Build gold.recommendations.

    predictions_by_horizon: {age_years: EffectModel.predict_at_age output};
    the two keys become the 5y/15y columns (frozen names), in ascending order.
    score = predicted cooling at the long horizon (K, positive) ×
    vulnerable residents ÷ cost. Every Nth ranked site is flagged
    holdout_control so unplanted lookalikes exist as future controls.
    Intervention suggestion: street trees on mostly-paved cells, park trees
    on open ones.
    """
    short_h, long_h = sorted(predictions_by_horizon)
    df = candidates.copy()
    for h, label in ((short_h, "5y"), (long_h, "15y")):
        p = predictions_by_horizon[h]
        df = df.merge(
            p[["site_id", "pred_effect_k", "pred_effect_k_low", "pred_effect_k_high"]]
            .rename(columns={
                # negative effect = cooling; recommendations are user-facing,
                # so flip sign: positive = cooling. Low/high swap accordingly.
                "pred_effect_k": f"predicted_cooling_k_{label}",
                "pred_effect_k_high": f"predicted_cooling_k_{label}_low",
                "pred_effect_k_low": f"predicted_cooling_k_{label}_high",
            }),
            on="site_id",
        )
    for c in df.columns:
        if c.startswith("predicted_cooling_k_"):
            df[c] = -df[c]

    if "vulnerable_residents" not in df.columns:
        raise ValueError(
            "candidates must carry vulnerable_residents (from silver.features)")

    df["suggested_intervention"] = np.where(
        df["impervious_frac"] >= 0.5, "street_trees", "park_trees"
    )
    df["est_cost_usd"] = df["suggested_intervention"].map(costs_usd)

    df["score"] = (
        df["predicted_cooling_k_15y"].clip(lower=0)
        * df["vulnerable_residents"]
        / df["est_cost_usd"]
    )
    # Rank within each city: a DC cell competes with DC cells, not NYC's.
    df = df.sort_values(["country_code", "city_id", "score"],
                        ascending=[True, True, False]).reset_index(drop=True)
    df["rank"] = df.groupby(["country_code", "city_id"]).cumcount() + 1
    df["holdout_control"] = (df["rank"] % holdout_every_n) == 0
    df["model_version"] = model_version
    df["recommended_at_utc"] = datetime.now(timezone.utc).isoformat()

    cols = [
        "country_code", "city_id", "site_id", "rank", "score",
        "predicted_cooling_k_5y", "predicted_cooling_k_5y_low", "predicted_cooling_k_5y_high",
        "predicted_cooling_k_15y", "predicted_cooling_k_15y_low", "predicted_cooling_k_15y_high",
        "vulnerable_residents", "est_cost_usd", "suggested_intervention",
        "holdout_control", "model_version", "recommended_at_utc",
    ]
    return df[cols]
