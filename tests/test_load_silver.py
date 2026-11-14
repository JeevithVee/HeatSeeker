"""The Databricks loader's file reading and typing (no Spark needed)."""
import datetime

import pandas as pd

import schema
from pipelines import load_silver


def test_every_city_table_loads_typed_and_keyed():
    for name in load_silver.TABLES:
        df, checksums = load_silver.read_table(schema.CITY_IDS, name)
        assert list(df.columns) == schema.columns(f"silver.{name}")
        assert set(df["city_id"]) == set(schema.CITY_IDS) == set(checksums)
    assert isinstance(df["population"].iloc[0], float)


def test_rows_use_plain_python_values_and_none():
    df, _ = load_silver.read_city_table("dc", "interventions")
    row = dict(zip(df.columns, load_silver.to_rows(df.head(1))[0]))
    assert type(row["trees_planted"]) is int and type(row["removed_flag"]) is bool
    assert isinstance(row["first_plant_date"], datetime.date)

    features, _ = load_silver.read_city_table("dc", "features")
    rows = load_silver.to_rows(features)
    income = list(features.columns).index("median_household_income")
    assert all(r[income] is None for r in rows)
    assert not any(isinstance(v, float) and pd.isna(v) for r in rows for v in r)
