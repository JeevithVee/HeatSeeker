"""Effect model: predict a site's cooling effect from its features.

Country-agnostic. Takes plain dataframes and parameters; never reads config
files. Predictions are shrunk toward the training mean where similar past
sites are few.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.neighbors import NearestNeighbors

FEATURE_COLUMNS = [
    "canopy_pct",
    "impervious_pct",
    "trees_planted",
    "baseline_temp_anomaly_c",
]

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
        return (X[FEATURE_COLUMNS].to_numpy() - self._scale_mu) / self._scale_sd

    def fit(self, train: pd.DataFrame) -> "EffectModel":
        """train: one row per evaluated site with FEATURE_COLUMNS + effect_c."""
        X = train[FEATURE_COLUMNS].to_numpy()
        y = train["effect_c"].to_numpy()
        self._scale_mu = X.mean(axis=0)
        self._scale_sd = np.where(X.std(axis=0) == 0, 1.0, X.std(axis=0))
        self.model.fit(X, y)
        self._train_mean = float(y.mean())
        self._nn = NearestNeighbors().fit(self._standardize(train))
        return self

    def predict(self, sites: pd.DataFrame) -> pd.DataFrame:
        """Returns effect_c prediction with uncertainty and shrinkage applied.

        Output columns: pred_effect_c, pred_effect_c_low, pred_effect_c_high,
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
        out["pred_effect_c"] = pred
        out["pred_effect_c_low"] = pred - 1.96 * sd
        out["pred_effect_c_high"] = pred + 1.96 * sd
        out["n_similar"] = n_similar
        out["shrinkage_weight"] = w
        return out


def train_effect_model(
    site_effects: pd.DataFrame,
    features: pd.DataFrame,
    interventions: pd.DataFrame,
    mlflow_tracking_uri: str | None = None,
    model_version: str = "v0",
) -> tuple[EffectModel, pd.DataFrame]:
    """Join measured effects to features, fit, optionally log to MLflow.

    Only sites labeled `detected` or `inconclusive` train the model;
    `not_detectable` sites carry no usable magnitude.
    """
    usable = site_effects[site_effects["quality_label"] != "not_detectable"]
    train = (
        usable.merge(features, on=["country_code", "city_id", "site_id"])
        .merge(
            interventions[["country_code", "city_id", "site_id", "trees_planted"]],
            on=["country_code", "city_id", "site_id"],
        )
    )
    model = EffectModel().fit(train)

    if mlflow_tracking_uri:
        import mlflow

        mlflow.set_tracking_uri(mlflow_tracking_uri)
        mlflow.set_experiment("heatseeker-effect-model")
        with mlflow.start_run(run_name=model_version):
            mlflow.log_params(
                {"n_train": len(train), "features": ",".join(FEATURE_COLUMNS),
                 "shrinkage_k": SHRINKAGE_K, "model_version": model_version}
            )
            preds = model.predict(train)
            rmse = float(np.sqrt(np.mean(
                (preds["pred_effect_c"] - train["effect_c"]) ** 2)))
            mlflow.log_metric("train_rmse_c", rmse)

    return model, train
