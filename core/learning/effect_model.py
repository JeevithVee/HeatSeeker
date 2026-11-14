"""Effect model ("Learn"): predict a site's cooling effect from its features.

Country-agnostic. Takes plain dataframes and parameters; never reads config
files. Predictions are shrunk toward the training mean where similar past
sites are few.

Trains on gold.site_effects (frozen schema, Kelvin) joined to silver.features.
All quality labels are pooled: sub-degree effects are individually
'inconclusive' or 'not_detectable' at 30 m but inform the model in aggregate,
and training only on 'detected' sites would select on significance and
overstate effects. effect_k is an average over the whole post period, so
years_since_treatment is a model feature; predictions are made at explicit
ages (predict_at_age), which replaces any hand-set maturity curve.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.neighbors import NearestNeighbors

FEATURE_COLUMNS = [
    "canopy_frac_baseline",
    "impervious_frac",
    "dose_trees",
    "years_since_treatment",
]

# Shrinkage similarity is over site characteristics only: years_since_treatment
# is part of the QUERY (we deliberately predict at ages outside the observed
# range), so including it would find zero neighbors for any 15-year horizon
# and collapse every prediction to the training mean.
SIMILARITY_COLUMNS = [
    "canopy_frac_baseline",
    "impervious_frac",
    "dose_trees",
]

HEADLINE_VARIANT = "all"

# Shrinkage: weight on the model prediction is n_similar / (n_similar + K).
SHRINKAGE_K = 5
SIMILARITY_RADIUS = 1.0  # in standardized feature space


class EffectModel:
    def __init__(self, random_state: int = 0):
        self.model = RandomForestRegressor(
            n_estimators=200, min_samples_leaf=3, random_state=random_state
        )
        self._train_mean: float | None = None
        self._nn: NearestNeighbors | None = None
        self._scale_mu: np.ndarray | None = None
        self._scale_sd: np.ndarray | None = None

    def _standardize(self, X: pd.DataFrame) -> np.ndarray:
        return (X[SIMILARITY_COLUMNS].to_numpy() - self._scale_mu) / self._scale_sd

    def fit(self, train: pd.DataFrame) -> "EffectModel":
        """train: one row per evaluated site with FEATURE_COLUMNS + effect_k."""
        X = train[FEATURE_COLUMNS].to_numpy()
        y = train["effect_k"].to_numpy()
        S = train[SIMILARITY_COLUMNS].to_numpy()
        self._scale_mu = S.mean(axis=0)
        self._scale_sd = np.where(S.std(axis=0) == 0, 1.0, S.std(axis=0))
        self.model.fit(X, y)
        self._train_mean = float(y.mean())
        self._nn = NearestNeighbors().fit(self._standardize(train))
        return self

    def predict(self, sites: pd.DataFrame) -> pd.DataFrame:
        """Effect prediction (Kelvin) with uncertainty and shrinkage applied.

        Output columns: pred_effect_k, pred_effect_k_low, pred_effect_k_high,
        n_similar, shrinkage_weight.
        """
        X = sites[FEATURE_COLUMNS].to_numpy()
        per_tree = np.stack([t.predict(X) for t in self.model.estimators_])
        raw = per_tree.mean(axis=0)
        sd = per_tree.std(axis=0)

        n_similar = np.array(
            [len(i) for i in self._nn.radius_neighbors(
                self._standardize(sites), radius=SIMILARITY_RADIUS,
                return_distance=False)]
        )
        w = n_similar / (n_similar + SHRINKAGE_K)
        pred = w * raw + (1 - w) * self._train_mean

        out = sites[["site_id"]].copy()
        out["pred_effect_k"] = pred
        out["pred_effect_k_low"] = pred - 1.96 * sd
        out["pred_effect_k_high"] = pred + 1.96 * sd
        out["n_similar"] = n_similar
        out["shrinkage_weight"] = w
        return out

    def predict_at_age(self, sites: pd.DataFrame, age_years: float) -> pd.DataFrame:
        """Predict as if every site were age_years past planting."""
        return self.predict(sites.assign(years_since_treatment=float(age_years)))


def build_training_frame(
    site_effects: pd.DataFrame,
    features: pd.DataFrame,
    as_of_year: int,
    variant: str = HEADLINE_VARIANT,
) -> pd.DataFrame:
    """Join the headline-variant effects to features; derive treatment age."""
    eff = site_effects[site_effects["variant"] == variant].copy()
    eff["years_since_treatment"] = (as_of_year - eff["treatment_year"]).clip(lower=0)
    return eff.merge(
        features[["country_code", "city_id", "site_id",
                  "canopy_frac_baseline", "impervious_frac"]],
        on=["country_code", "city_id", "site_id"],
    )


def train_effect_model(
    site_effects: pd.DataFrame,
    features: pd.DataFrame,
    as_of_year: int,
    mlflow_tracking_uri: str | None = None,
    model_version: str = "v0",
) -> tuple[EffectModel, pd.DataFrame]:
    """Build the training frame, fit, optionally log to MLflow."""
    train = build_training_frame(site_effects, features, as_of_year)
    model = EffectModel().fit(train)

    if mlflow_tracking_uri:
        import mlflow

        mlflow.set_tracking_uri(mlflow_tracking_uri)
        mlflow.set_experiment("heatseeker-effect-model")
        with mlflow.start_run(run_name=model_version):
            mlflow.log_params(
                {"n_train": len(train), "features": ",".join(FEATURE_COLUMNS),
                 "shrinkage_k": SHRINKAGE_K, "variant": HEADLINE_VARIANT,
                 "model_version": model_version}
            )
            preds = model.predict(train)
            rmse = float(np.sqrt(np.mean(
                (preds["pred_effect_k"] - train["effect_k"]) ** 2)))
            mlflow.log_metric("train_rmse_k", rmse)

    return model, train
