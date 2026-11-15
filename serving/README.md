# /serving

Model Serving for the effect model: a planner describes a cell (canopy fraction, impervious
fraction, trees to plant, years ahead) and gets a predicted surface-cooling range. Built after
the NYC prototype worked (brief: "showpiece").

- `register_effect_model.py` trains `core.learning.EffectModel` on the headline gold effects plus
  features, wraps it as an MLflow pyfunc that returns `pred_effect_k`, `pred_effect_k_low`,
  `pred_effect_k_high`, `n_similar`, `shrinkage_weight` and a fixed caveat string, registers it
  as `heatseeker.gold.effect_model` in Unity Catalog, and creates or updates the scale-to-zero
  endpoint `heatseeker-effect-model`.

```
DATABRICKS_CONFIG_PROFILE=heatseeker python serving/register_effect_model.py
databricks serving-endpoints query heatseeker-effect-model -p heatseeker --json \
  '{"dataframe_records":[{"site_id":"x","canopy_frac_baseline":0.05,"impervious_frac":0.8,"dose_trees":30,"years_since_treatment":15}]}'
```

**Run it from Python 3.10–3.13.** MLflow records the logging interpreter's version in the
model's `python_env.yaml`; the serving container then builds that Python and installs the
`mlflowserving` wheel, which depends on `orjson`, which ships no wheel for Python 3.15. Version 1
of the model, logged from a 3.15 venv, failed to build for exactly that reason. The repo's
`.venv-serving` (pixi-installed Python 3.12) is the environment that works.

Predictions inherit every limitation of the measured effects: no established causal cooling,
surface temperature is not felt temperature, all four training cities are temperate. The
endpoint says so in every response.
