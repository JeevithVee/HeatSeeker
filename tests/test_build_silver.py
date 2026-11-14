"""Typing and comparison helpers of the Databricks build job (no Spark needed)."""
import datetime

import numpy as np
import pandas as pd

import schema
from pipelines import build_silver
from tests.test_promotion import inventory


def test_typed_rows_are_plain_python_with_none_for_missing():
    df = build_silver.typed(inventory(), "silver.interventions")
    row = dict(zip(df.columns, build_silver.to_rows(df)[0]))
    assert type(row["trees_planted"]) is int and type(row["removed_flag"]) is bool
    assert isinstance(row["first_plant_date"], datetime.date)

    grid = pd.DataFrame({"country_code": ["US"], "city_id": ["nyc"], "site_id": ["892a100d2c3ffff"],
                         "centroid_lat": [40.7], "centroid_lon": [-73.9], "area_km2": [0.105]})
    from pipelines import features
    feats = build_silver.typed(features.build_features(grid), "silver.features")
    assert all(v is None or not (isinstance(v, float) and np.isnan(v)) for v in build_silver.to_rows(feats)[0])


def test_differences_tolerates_rounding_and_reports_real_changes():
    a = build_silver.typed(inventory(), "silver.interventions")
    assert build_silver.differences(a, a.copy(), build_silver.KEYS["interventions"], "silver.interventions") == []
    b = a.copy()
    b["trees_planted"] = 5
    found = build_silver.differences(a, b, build_silver.KEYS["interventions"], "silver.interventions")
    assert found == ["silver.interventions.trees_planted: 1 rows differ"]
    assert build_silver.differences(a, pd.concat([a, a]), build_silver.KEYS["interventions"],
                                    "silver.interventions")[0].startswith("silver.interventions: 1 rebuilt rows vs 2")
