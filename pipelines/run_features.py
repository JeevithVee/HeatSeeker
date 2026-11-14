"""Job: grid + NLCD rasters + census (+ elevation, tree inventory) -> silver.features.

    python -m pipelines.run_features nyc

Runs as a Databricks job or locally; see pipelines/io.py for where tables go.
Elevation comes from Agent 2's static Earth Engine export; until that table
exists the column is null.
"""
import argparse

import pandas as pd

from ingest.us import census, mrlc
from pipelines import features, grid, interventions, io
from pipelines.run_interventions import ADAPTERS

CANOPY_BASELINE_YEAR = 2014   # the last year before the first usable plantings
LATEST_YEAR = 2024


def raster_features(city_grid, raw_dir):
    """Canopy, impervious and land cover per cell from Annual NLCD."""
    bbox = mrlc.snapped_bbox(city_grid["centroid_lon"].min(), city_grid["centroid_lat"].min(),
                             city_grid["centroid_lon"].max(), city_grid["centroid_lat"].max())
    wanted = [("canopy", CANOPY_BASELINE_YEAR), ("canopy", LATEST_YEAR),
              ("impervious", LATEST_YEAR), ("land_cover", LATEST_YEAR)]
    site_ids, out = None, {}
    for layer, year in wanted:
        path = raw_dir / f"{layer}_{year}.tif"
        if not path.exists():
            mrlc.fetch(layer, year, bbox, raw_dir)
        values, x_west, y_north, pixel_m = mrlc.read(path)
        if site_ids is None:   # all layers share one pixel grid
            lon, lat = mrlc.pixel_centres_lonlat(values.shape, x_west, y_north, pixel_m)
            site_ids = features.pixel_site_ids(lon, lat)
        if layer == "land_cover":
            out[(layer, year)] = features.zonal_dominant_class(site_ids, values, mrlc.LAND_COVER_CLASSES)
        else:
            out[(layer, year)] = features.zonal_mean_fraction(site_ids, values)
    return out


def census_features(city_id, raw_root):
    """Population and vulnerability shares per cell."""
    raw = {}
    for spec in (census.BLOCKS, census.SVI):
        path = raw_root / spec["source"] / f"{city_id}.csv"
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            census.fetch(spec, city_id).to_csv(path, index=False)
        raw[spec["source"]] = pd.read_csv(path, dtype=str)
    blocks, svi = raw[census.BLOCKS["source"]], raw[census.SVI["source"]]
    io.write_table(census.blocks_to_bronze(blocks, city_id), f"bronze.{census.BLOCKS['source']}", city_id=city_id)
    io.write_table(census.svi_to_bronze(svi, city_id), f"bronze.{census.SVI['source']}", city_id=city_id)
    return features.population_by_cell(census.block_population(blocks, svi))


def existing_trees(city_id):
    """Standing inventory trees per cell, dated or not. None if bronze is absent."""
    adapter = ADAPTERS[city_id]
    try:
        bronze = io.read_table(f"bronze.{adapter.SOURCE_ID}")
    except FileNotFoundError:
        return None
    records = interventions.add_site_id(adapter.to_records(bronze))
    standing = records[~records["removed"] & records["site_id"].notna()]
    return standing.groupby("site_id").size()


def elevation(city_id):
    """elevation_m per cell from Agent 2's static export, if it has landed."""
    try:
        static = io.read_table(f"bronze.{city_id}_static")
    except Exception:
        return None
    return static.set_index("site_id")["elevation_m"]


def run(city_id):
    raw_root = io.LOCAL_ROOT / "bronze"
    city_grid = grid.read_grid(city_id)
    rasters = raster_features(city_grid, raw_root / "mrlc_annual_nlcd" / city_id)
    silver = features.build_features(
        city_grid,
        canopy_baseline=rasters[("canopy", CANOPY_BASELINE_YEAR)],
        canopy_latest=rasters[("canopy", LATEST_YEAR)],
        impervious=rasters[("impervious", LATEST_YEAR)],
        land_cover=rasters[("land_cover", LATEST_YEAR)],
        canopy_year_baseline=CANOPY_BASELINE_YEAR,
        canopy_year_latest=LATEST_YEAR,
        land_cover_year=LATEST_YEAR,
        population=census_features(city_id, raw_root),
        elevation=elevation(city_id),
        existing_trees=existing_trees(city_id),
    )
    print("silver ->", io.write_table(silver, "silver.features", city_id=city_id))
    print(silver.describe(include="all").T[["count", "mean", "min", "max"]].to_string())
    return silver


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("city_id", choices=sorted(ADAPTERS))
    run(parser.parse_args().city_id)
