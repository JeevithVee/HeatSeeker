"""Databricks job: bronze -> silver.interventions and silver.features, all cities.

For every city, reads its bronze tables and the as-received rasters in the
bronze landing volume and runs the build code (adapter cleaning, H3
aggregation, zonal statistics, census allocation, vulnerability). Plantings
logged in the app (gold.app_planting_log) are then folded in under the rules
in pipelines/promotion.py.

    build_silver.py --catalog heatseeker [--check-only]

A table is written only when the rebuilt rows differ from the live ones, so a
run on unchanged inputs creates no new Delta version and downstream pins stay
valid. --check-only never writes and fails on any difference.
"""
import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # Workspace source snapshots are read-only on serverless.
REPO_ROOT = Path(globals().get("__file__", sys.argv[0])).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import schema  # noqa: E402
from ingest.us import census, mrlc  # noqa: E402
from pipelines import features, grid, interventions, promotion  # noqa: E402
from pipelines.run_features import CANOPY_BASELINE_YEAR, LATEST_YEAR  # noqa: E402
from pipelines.run_interventions import ADAPTERS  # noqa: E402

FLOAT_TOLERANCE = 1e-6
KEYS = {"interventions": ["city_id", "site_id", "plant_year", "intervention_type"],
        "features": ["city_id", "site_id"]}


def bronze_attributes(bronze):
    """The source fields of a bronze table, as the raw frame the adapters expect."""
    return pd.DataFrame([json.loads(a) for a in bronze["attributes"]])


def rebuild(spark, catalog, city_id, landing):
    adapter = ADAPTERS[city_id]
    city_grid = grid.read_grid(city_id)

    def bronze(source):
        return spark.table(f"{catalog}.bronze.{source}").where(f"city_id = '{city_id}'").toPandas()

    trees = bronze(adapter.SOURCE_ID)
    as_of = pd.Timestamp(trees["ingested_at"].max()).date()
    records = adapter.to_records(trees, as_of=as_of)
    built_iv = interventions.build_interventions(records)
    built_iv = built_iv[built_iv["site_id"].isin(city_grid["site_id"])].reset_index(drop=True)

    site_ids, rasters = None, {}
    for layer, year in (("canopy", CANOPY_BASELINE_YEAR), ("canopy", LATEST_YEAR),
                        ("impervious", LATEST_YEAR), ("land_cover", LATEST_YEAR)):
        values, x_west, y_north, pixel_m = mrlc.read(landing / "mrlc_annual_nlcd" / f"{layer}_{year}.tif")
        if site_ids is None:
            lon, lat = mrlc.pixel_centres_lonlat(values.shape, x_west, y_north, pixel_m)
            site_ids = features.pixel_site_ids(lon, lat)
        rasters[(layer, year)] = (
            features.zonal_dominant_class(site_ids, values, mrlc.LAND_COVER_CLASSES) if layer == "land_cover"
            else features.zonal_mean_fraction(site_ids, values))

    blocks = bronze_attributes(bronze(census.BLOCKS["source"]))
    svi = bronze_attributes(bronze(census.SVI["source"]))
    population = features.population_by_cell(census.block_population(blocks, svi))

    with_cells = interventions.add_site_id(records)
    standing = with_cells[~with_cells["removed"] & with_cells["site_id"].notna()].groupby("site_id").size()
    elevation = pd.read_csv(landing / f"{city_id}_static.csv").set_index("site_id")["elevation_m"]

    built_features = features.build_features(
        city_grid,
        canopy_baseline=rasters[("canopy", CANOPY_BASELINE_YEAR)], canopy_latest=rasters[("canopy", LATEST_YEAR)],
        impervious=rasters[("impervious", LATEST_YEAR)], land_cover=rasters[("land_cover", LATEST_YEAR)],
        canopy_year_baseline=CANOPY_BASELINE_YEAR, canopy_year_latest=LATEST_YEAR, land_cover_year=LATEST_YEAR,
        population=population, elevation=elevation, existing_trees=standing,
    )
    return built_iv, built_features


def differences(built, live, keys, table):
    """List every way two frames differ; empty when they agree."""
    problems = []
    built = built.sort_values(keys).reset_index(drop=True)
    live = live.sort_values(keys).reset_index(drop=True)
    if len(built) != len(live):
        return [f"{table}: {len(built):,} rebuilt rows vs {len(live):,} live rows"]
    for column, spec in schema.TABLES[table]["columns"].items():
        b, l = built[column], live[column]
        if spec["type"] in ("double", "int"):
            b, l = pd.to_numeric(b, errors="coerce").astype(float), pd.to_numeric(l, errors="coerce").astype(float)
            bad = ~((b.isna() & l.isna()) | (np.abs(b - l) <= FLOAT_TOLERANCE))
        else:
            b, l = b.astype("string"), l.astype("string")
            bad = ~((b.isna() & l.isna()) | (b == l).fillna(False))
        if bad.any():
            problems.append(f"{table}.{column}: {int(bad.sum()):,} rows differ")
    return problems


def typed(df, table):
    """Cast a frame to the frozen schema's types."""
    df = schema.validate(df, table).copy()
    for column, spec in schema.TABLES[table]["columns"].items():
        kind = spec["type"]
        if kind == "int":
            df[column] = pd.to_numeric(df[column]).astype("Int64")
        elif kind == "double":
            df[column] = pd.to_numeric(df[column]).astype("float64")
        elif kind == "boolean":
            df[column] = df[column].astype("boolean")
        elif kind == "date":
            df[column] = pd.to_datetime(df[column]).dt.date
        elif kind == "string":
            df[column] = df[column].astype("string")
    return df


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


def planting_log(spark, catalog):
    """Rows of the app's staging table, or None when it does not exist."""
    table = f"{catalog}.gold.app_planting_log"
    if not spark.catalog.tableExists(table):
        return None
    return spark.table(table).toPandas()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default=schema._TABLES["catalog"])
    parser.add_argument("--cities", nargs="+", default=list(schema.CITY_IDS))
    parser.add_argument("--landing", default="/Volumes/heatseeker/bronze/landing/us")
    parser.add_argument("--check-only", default="false", help="true: compare with live tables, never write")
    args = parser.parse_args(argv)
    check_only = str(args.check_only).lower() == "true"

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    built = {"interventions": [], "features": []}
    grids = {}
    for city_id in args.cities:
        iv, ft = rebuild(spark, args.catalog, city_id, Path(args.landing) / city_id)
        built["interventions"].append(iv)
        built["features"].append(ft)
        grids[city_id] = set(ft["site_id"])
        print(f"[build_silver] {city_id}: {len(iv):,} cell-years, {len(ft):,} cells rebuilt from bronze")
    built = {name: pd.concat(frames, ignore_index=True) for name, frames in built.items()}

    log = planting_log(spark, args.catalog)
    if log is not None and len(log):
        built["interventions"], classified = promotion.promote(log, built["interventions"], grids)
        counts = classified["reject_reason"].fillna("promoted").value_counts().to_dict()
        print(f"[build_silver] app planting log: {len(log):,} rows -> {counts}")
    else:
        print("[build_silver] app planting log: no rows to promote")

    problems = []
    for name in ("interventions", "features"):
        table = f"silver.{name}"
        target = f"{args.catalog}.{table}"
        new = typed(built[name], table)
        exists = spark.catalog.tableExists(target)
        found = ["table does not exist"]
        if exists:
            live = spark.table(target).toPandas()
            live = live[live["city_id"].isin(args.cities)]
            found = differences(new, live, KEYS[name], table)
        if not found:
            print(f"[build_silver] {target}: {len(new):,} rows, identical to the live table, nothing written")
            continue
        print(f"[build_silver] {target}: differs from the live table: {found[:8]}")
        if check_only:
            problems.extend(found)
            continue
        if exists and set(args.cities) != set(schema.CITY_IDS):
            raise RuntimeError("refusing to replace the table from a partial city list")
        sdf = spark.createDataFrame(to_rows(new), schema=spark_schema(table))
        sdf.write.format("delta").mode("overwrite").option("overwriteSchema", True).saveAsTable(target)
        version = spark.sql(f"DESCRIBE HISTORY {target} LIMIT 1").collect()[0]["version"]
        print(f"[build_silver] {target}: wrote {len(new):,} rows, Delta version {version}")
    if problems:
        raise RuntimeError("silver does not follow from bronze:\n  " + "\n  ".join(problems))


if __name__ == "__main__":
    main()
