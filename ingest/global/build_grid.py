"""Build a city's H3 cell grid from a boundary polygon.

Rule (frozen on the MessageBoard): a cell belongs to the city when its
CENTROID falls inside the city boundary. site_id is the H3 index as a
15-character lowercase hex string.

Country-agnostic: the boundary file is an input. Usage:

    python ingest/global/build_grid.py BOUNDARY.geojson US nyc 9 ingest/global/grids/nyc_h3_res9.csv
"""
import csv
import json
import sys

import h3
from shapely.geometry import Point, shape
from shapely.ops import unary_union
from shapely.prepared import prep


def build_grid(boundary_geojson_path, resolution):
    with open(boundary_geojson_path) as f:
        gj = json.load(f)
    feats = gj["features"] if gj.get("type") == "FeatureCollection" else [gj]
    boundary = unary_union([shape(ft["geometry"]) for ft in feats]).buffer(0)
    inside = prep(boundary)

    west, south, east, north = boundary.bounds
    pad = 0.01
    bbox = h3.LatLngPoly(
        [
            (south - pad, west - pad),
            (south - pad, east + pad),
            (north + pad, east + pad),
            (north + pad, west - pad),
        ]
    )
    rows = []
    for cell in h3.polygon_to_cells(bbox, resolution):
        lat, lon = h3.cell_to_latlng(cell)
        if inside.contains(Point(lon, lat)):
            rows.append((cell, round(lat, 7), round(lon, 7)))
    rows.sort()
    return rows


def main():
    boundary_path, country_code, city_id, resolution, out_path = sys.argv[1:6]
    rows = build_grid(boundary_path, int(resolution))
    with open(out_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["country_code", "city_id", "site_id", "h3_resolution", "centroid_lat", "centroid_lon"])
        for cell, lat, lon in rows:
            w.writerow([country_code, city_id, cell, resolution, lat, lon])
    print(f"{city_id}: {len(rows)} cells at res {resolution} -> {out_path}")


if __name__ == "__main__":
    main()
