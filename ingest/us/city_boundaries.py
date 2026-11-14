"""City land boundaries (clipped to the shoreline), one source per city.

The boundary defines the city grid: every H3 cell whose centroid is inside it.
"""
import json
from pathlib import Path

import requests
from shapely.geometry import shape
from shapely.ops import unary_union

SOURCES = {
    "nyc": {
        "source": "nyc_borough_boundaries",
        "url": "https://data.cityofnewyork.us/resource/gthc-hcne.geojson",
        "license": "NYC Open Data Terms of Use (no license named in dataset metadata); attribution: NYC Department of City Planning",
    },
}


def fetch(city_id, dest_dir):
    """Download the boundary GeoJSON as received. Returns the file path."""
    src = SOURCES[city_id]
    dest = Path(dest_dir) / "boundary.geojson"
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(src["url"], timeout=120)
    r.raise_for_status()
    dest.write_bytes(r.content)
    return dest


def read_polygon(path):
    """One (multi)polygon for the whole city, EPSG:4326."""
    features = json.loads(Path(path).read_text())["features"]
    return unary_union([shape(f["geometry"]) for f in features])
