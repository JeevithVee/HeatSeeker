"""Databricks job: rebuild a city's silver tables from bronze and compare with the live ones.

Reads the city's bronze tables and the as-received rasters in the bronze
landing volume, runs the same build code as run_interventions / run_features,
and checks the result against heatseeker.silver.interventions and
heatseeker.silver.features row for row. Writes nothing; fails on any difference.

    verify_silver_from_bronze.py --catalog heatseeker --city-id nyc

This is the proof that the published silver tables follow from bronze inside
the workspace, without replacing tables that gold was computed on.
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
from pipelines import features, grid, interventions  # noqa: E402
from pipelines.run_features import CANOPY_BASELINE_YEAR, LATEST_YEAR  # noqa: E402
from pipelines.run_interventions import ADAPTERS  # noqa: E402

FLOAT_TOLERANCE = 1e-6   # the published tables were rounded to six decimals


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


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", default=schema._TABLES["catalog"])
    parser.add_argument("--city-id", required=True, choices=sorted(ADAPTERS))
    parser.add_argument("--landing", default="/Volumes/heatseeker/bronze/landing/us")
    args = parser.parse_args(argv)

    from pyspark.sql import SparkSession

    spark = SparkSession.builder.getOrCreate()
    built_iv, built_features = rebuild(spark, args.catalog, args.city_id, Path(args.landing) / args.city_id)

    problems = []
    for name, built, keys in (("interventions", built_iv, ["site_id", "plant_year", "intervention_type"]),
                              ("features", built_features, ["site_id"])):
        table = f"silver.{name}"
        target = f"{args.catalog}.{table}"
        version = spark.sql(f"DESCRIBE HISTORY {target} LIMIT 1").collect()[0]["version"]
        live = spark.read.option("versionAsOf", version).table(target).where(f"city_id = '{args.city_id}'").toPandas()
        found = differences(built, live, keys, table)
        print(f"[verify] {target} version {version}, {args.city_id}: {len(live):,} live rows, "
              f"{len(built):,} rebuilt from bronze, {'IDENTICAL' if not found else 'DIFFERENT'}")
        problems.extend(found)
    if problems:
        raise RuntimeError("silver does not follow from bronze:\n  " + "\n  ".join(problems))


if __name__ == "__main__":
    main()
