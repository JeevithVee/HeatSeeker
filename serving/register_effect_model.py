"""Register the effect model in Unity Catalog and serve it (the brief's "showpiece").

Trains core.learning.EffectModel on the same inputs the recommendations used (gold.site_effects
headline variant + silver.features snapshot), wraps it as an MLflow pyfunc, registers it as
<catalog>.gold.effect_model, and creates/updates a scale-to-zero serving endpoint. A planner
can then draw a cell and get a predicted cooling range at 5 and 15 years.

    DATABRICKS_CONFIG_PROFILE=heatseeker python serving/register_effect_model.py \
        --site-effects demo/data_real/gold_site_effects.parquet \
        --features demo/data_real/silver_features.parquet

Predictions inherit every limitation of the measured effects (no established causal cooling;
surface temperature is not felt temperature); the endpoint returns them with those caveats.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import mlflow
import pandas as pd
from mlflow.models import infer_signature

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.learning.effect_model import FEATURE_COLUMNS, EffectModel, build_training_frame  # noqa: E402

INPUT_COLUMNS = ["site_id", "canopy_frac_baseline", "impervious_frac", "dose_trees", "years_since_treatment"]
CAVEAT = ("Predicted Kelvin difference in summer late-morning surface temperature vs unplanted cells; "
          "negative = cooler. Not felt temperature. Trained on observational effects with no established "
          "causal cooling; treat as a planning prior, not a guarantee.")


class EffectModelPyfunc(mlflow.pyfunc.PythonModel):
    def __init__(self, model: EffectModel):
        self.model = model

    def predict(self, context, model_input: pd.DataFrame, params=None):
        df = model_input.copy()
        if "site_id" not in df.columns:
            df["site_id"] = [f"q{i}" for i in range(len(df))]
        out = self.model.predict(df[INPUT_COLUMNS])
        out["caveat"] = CAVEAT
        return out


def cli(*args):
    r = subprocess.run(["databricks", *args, "-o", "json"], capture_output=True, text=True)
    return r.returncode, (json.loads(r.stdout) if r.stdout.strip().startswith(("{", "[")) else r.stdout), r.stderr


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-effects", default=str(REPO / "demo/data_real/gold_site_effects.parquet"))
    ap.add_argument("--features", default=str(REPO / "demo/data_real/silver_features.parquet"))
    ap.add_argument("--catalog", default="heatseeker")
    ap.add_argument("--model-name", default="effect_model")
    ap.add_argument("--endpoint", default="heatseeker-effect-model")
    ap.add_argument("--as-of-year", type=int, default=2026)
    ap.add_argument("--experiment", default="/Shared/heatseeker/effect-model")
    ap.add_argument("--skip-endpoint", action="store_true")
    args = ap.parse_args(argv)

    effects = pd.read_parquet(args.site_effects)
    features = pd.read_parquet(args.features)
    train = build_training_frame(effects, features, as_of_year=args.as_of_year)
    model = EffectModel().fit(train)
    preds = model.predict(train)
    rmse = float(((preds["pred_effect_k"] - train["effect_k"]) ** 2).mean() ** 0.5)
    print(f"[serving] trained on {len(train)} sites, train RMSE {rmse:.3f} K")

    mlflow.set_tracking_uri("databricks")
    mlflow.set_registry_uri("databricks-uc")
    mlflow.set_experiment(args.experiment)
    full_name = f"{args.catalog}.gold.{args.model_name}"
    example = train[INPUT_COLUMNS].head(3).assign(years_since_treatment=15.0)
    sig = infer_signature(example, EffectModelPyfunc(model).predict(None, example))
    with mlflow.start_run(run_name=f"effect-model-{time.strftime('%Y%m%d-%H%M')}") as run:
        mlflow.log_params({"n_train": len(train), "features": ",".join(FEATURE_COLUMNS),
                           "variant": "all", "as_of_year": args.as_of_year,
                           "site_effects_source": Path(args.site_effects).name})
        mlflow.log_metric("train_rmse_k", rmse)
        info = mlflow.pyfunc.log_model(
            name="model", python_model=EffectModelPyfunc(model), signature=sig, input_example=example,
            registered_model_name=full_name,
            # The pyfunc pickles EffectModel from the repo's core package; ship that code with the
            # model or the serving container fails at load with a missing module.
            code_paths=[str(REPO / "core")],
            pip_requirements=[f"scikit-learn=={__import__('sklearn').__version__}",
                              f"pandas=={pd.__version__}", f"numpy=={__import__('numpy').__version__}"],
        )
    version = info.registered_model_version
    print(f"[serving] registered {full_name} version {version} (run {run.info.run_id})")
    if args.skip_endpoint:
        return

    served = {"name": f"v{version}", "entity_name": full_name, "entity_version": str(version),
              "workload_size": "Small", "scale_to_zero_enabled": True}
    code, existing, _ = cli("serving-endpoints", "get", args.endpoint)
    if code == 0:
        code, out, err = cli("serving-endpoints", "update-config", args.endpoint, "--json",
                             json.dumps({"served_entities": [served]}))
        action = "updated"
    else:
        code, out, err = cli("serving-endpoints", "create", "--json",
                             json.dumps({"name": args.endpoint, "config": {"served_entities": [served]}}))
        action = "created"
    if code != 0:
        raise SystemExit(f"[serving] endpoint {action[:-1]} failed: {err[:600]}")
    print(f"[serving] endpoint {args.endpoint} {action}; waiting for READY (container build takes several minutes)")
    for _ in range(90):
        code, st, _ = cli("serving-endpoints", "get", args.endpoint)
        state = (st.get("state") or {}) if isinstance(st, dict) else {}
        print(f"  ready={state.get('ready')} config_update={state.get('config_update')}")
        if state.get("ready") == "READY" and state.get("config_update") == "NOT_UPDATING":
            break
        if state.get("config_update") == "UPDATE_FAILED":
            raise SystemExit("[serving] endpoint update failed; see the endpoint's build logs")
        time.sleep(20)
    print(f"[serving] done. Query: databricks serving-endpoints query {args.endpoint} --json "
          "'{\"dataframe_records\": [{\"site_id\": \"x\", \"canopy_frac_baseline\": 0.05, \"impervious_frac\": 0.8, "
          "\"dose_trees\": 30, \"years_since_treatment\": 15}]}'")


if __name__ == "__main__":
    main()
