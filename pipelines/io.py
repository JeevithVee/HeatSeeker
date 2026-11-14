"""Read and write the standard tables.

On Databricks (an active Spark session) tables are Delta tables in Unity
Catalog. Anywhere else they are Parquet files under ./data, which is
git-ignored, so the same pipeline code runs locally for development.
"""
import os
from pathlib import Path

import pandas as pd

import schema

CATALOG = os.environ.get("HEATSEEKER_CATALOG", schema._TABLES["catalog"])
LOCAL_ROOT = Path(os.environ.get("HEATSEEKER_DATA", Path(__file__).resolve().parents[1] / "data"))


def _spark():
    try:
        from pyspark.sql import SparkSession
    except ImportError:
        return None
    return SparkSession.getActiveSession()


def _local_path(table):
    layer, name = table.split(".", 1)
    return LOCAL_ROOT / layer / f"{name}.parquet"


def write_table(df, table, *, city_id=None):
    """Write `table` (e.g. 'silver.interventions').

    With `city_id`, only that city's rows are replaced, so cities can be
    loaded one at a time.
    """
    spark = _spark()
    if spark is not None:
        writer = spark.createDataFrame(df).write.format("delta").mode("overwrite")
        if city_id is not None:
            writer = writer.option("replaceWhere", f"city_id = '{city_id}'")
        writer.saveAsTable(f"{CATALOG}.{table}")
        return f"{CATALOG}.{table}"

    path = _local_path(table)
    path.parent.mkdir(parents=True, exist_ok=True)
    if city_id is not None and path.exists():
        keep = pd.read_parquet(path)
        df = pd.concat([keep[keep["city_id"] != city_id], df], ignore_index=True)
    df.to_parquet(path, index=False)
    return str(path)


def read_table(table):
    spark = _spark()
    if spark is not None:
        return spark.table(f"{CATALOG}.{table}").toPandas()
    return pd.read_parquet(_local_path(table))
