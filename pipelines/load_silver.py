"""Databricks job: publish silver.interventions and silver.features.

Loads the per-city tables built by run_interventions / run_features (the
checksummed CSVs under ingest/us/samples) into Unity Catalog as typed Delta
tables. gold.site_effects was computed from exactly these files, so the
published silver tables match what the evaluation read; the city tree layers
are live and a rebuild from source would drift from it.

Runs as a Python script task on serverless compute from the repo's Git folder:

    load_silver.py --catalog heatseeker --cities nyc dc sea sf

Each run replaces both tables whole, as one new Delta version per table.
"""
import argparse
import hashlib
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # Workspace source snapshots are read-only on serverless.
REPO_ROOT = Path(globals().get("__file__", sys.argv[0])).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pandas as pd  # noqa: E402

import schema  # noqa: E402

SAMPLES = REPO_ROOT / "ingest" / "us" / "samples"
TABLES = ("interventions", "features")


def read_city_table(city_id, name):
    """One city's table from its CSV, validated and typed per the frozen schema."""
    table = f"silver.{name}"
    path = SAMPLES / f"{city_id}_silver_{name}.csv"
    df = schema.validate(pd.read_csv(path), table)
    if set(df["city_id"]) != {city_id}:
        raise ValueError(f"{path.name}: expected only city_id = {city_id}")
    for column, spec in schema.TABLES[table]["columns"].items():
        kind = spec["type"]
        if kind == "int":
            df[column] = df[column].astype("Int64")
        elif kind == "double":
            df[column] = df[column].astype("float64")
        elif kind == "boolean":
            df[column] = df[column].astype("boolean")
        elif kind == "date":
            df[column] = pd.to_datetime(df[column]).dt.date
        elif kind == "string":
            df[column] = df[column].astype("string")
    sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    return df, sha256


def read_table(cities, name):
    frames, checksums = [], {}
    for city_id in cities:
        df, checksums[city_id] = read_city_table(city_id, name)
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    keys = {"interventions": ["site_id", "plant_year", "intervention_type"], "features": ["site_id"]}[name]
    if out.duplicated(["city_id", *keys]).any():
        raise ValueError(f"silver.{name}: duplicate keys")
    return out, checksums


def spark_schema(table):
    from pyspark.sql import types as T

    kinds = {"string": T.StringType(), "int": T.IntegerType(), "double": T.DoubleType(),
             "boolean": T.BooleanType(), "date": T.DateType(), "timestamp": T.TimestampType()}
    return T.StructType([
        T.StructField(column, kinds[spec["type"]], spec.get("nullable", True))
        for column, spec in schema.TABLES[table]["columns"].items()
    ])


def to_rows(df):
    """Plain Python rows with None for every missing value."""
    return [tuple(None if pd.isna(v) else (v.item() if hasattr(v, "item") else v) for v in row)
            for row in df.itertuples(index=False, name=None)]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default=schema._TABLES["catalog"])
    parser.add_argument("--cities", nargs="+", default=list(schema.CITY_IDS))
    args = parser.parse_args(argv)

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    for name in TABLES:
        table = f"silver.{name}"
        target = f"{args.catalog}.{table}"
        df, checksums = read_table(args.cities, name)
        sdf = spark.createDataFrame(to_rows(df), schema=spark_schema(table))
        sdf.write.format("delta").mode("overwrite").option("overwriteSchema", True).saveAsTable(target)
        spark.sql(f"COMMENT ON TABLE {target} IS "
                  f"'HeatSeeker schema v{schema.SCHEMA_VERSION}. Writer: Agent 1. "
                  f"Loaded from ingest/us/samples CSVs (sha256 in job log).'")
        version = spark.sql(f"DESCRIBE HISTORY {target} LIMIT 1").collect()[0]["version"]
        print(f"[load_silver] {target}: {len(df):,} rows, Delta version {version}")
        counts = spark.table(target).groupBy("city_id").count().orderBy("city_id").collect()
        for row in counts:
            print(f"[load_silver]   {row['city_id']}: {row['count']:,} rows, source sha256 {checksums[row['city_id']]}")
        if sum(r["count"] for r in counts) != len(df):
            raise RuntimeError(f"{target}: row count after write does not match the source files")


if __name__ == "__main__":
    main()
