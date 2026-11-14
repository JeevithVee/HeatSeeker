"""The city grid: every H3 cell whose centroid is inside the city boundary.

Agents 1 and 2 must use the same grid, so the cell list for each city is
written once to ingest/us/grids/<city_id>_res<N>_cells.csv and read from there.
"""
from pathlib import Path

import h3
import pandas as pd

import schema

GRID_DIR = Path(__file__).resolve().parents[1] / "ingest" / "us" / "grids"


def grid_path(city_id, resolution=schema.H3_RESOLUTION):
    return GRID_DIR / f"{city_id}_res{resolution}_cells.csv"


def build_grid(polygon, *, country_code, city_id, resolution=schema.H3_RESOLUTION):
    """Cells of a city, with centroid and area. Sorted by site_id."""
    cells = sorted(h3.geo_to_cells(polygon, resolution))
    centroids = [h3.cell_to_latlng(c) for c in cells]
    return pd.DataFrame({
        "country_code": country_code,
        "city_id": city_id,
        "site_id": cells,
        "centroid_lat": [round(lat, 6) for lat, _ in centroids],
        "centroid_lon": [round(lon, 6) for _, lon in centroids],
        "area_km2": [round(h3.cell_area(c, unit="km^2"), 6) for c in cells],
    })


def read_grid(city_id, resolution=schema.H3_RESOLUTION):
    return pd.read_csv(grid_path(city_id, resolution))


if __name__ == "__main__":
    import sys

    from ingest.us import city_boundaries, common
    from pipelines import io

    city = sys.argv[1]
    boundary = city_boundaries.fetch(city, io.LOCAL_ROOT / "bronze" / city_boundaries.SOURCES[city]["source"])
    grid = build_grid(city_boundaries.read_polygon(boundary),
                      country_code=common.COUNTRY_CODE, city_id=city)
    GRID_DIR.mkdir(parents=True, exist_ok=True)
    grid.to_csv(grid_path(city), index=False)
    print(f"{city}: {len(grid)} cells, {grid['area_km2'].sum():.1f} km2 -> {grid_path(city)}")
