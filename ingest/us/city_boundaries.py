"""City land boundaries (clipped to the shoreline), one source per city.

The boundary defines the city grid: every H3 cell whose centroid is inside it.
"""
import json
from pathlib import Path

import requests
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

SOURCES = {
    "nyc": {
        "source": "nyc_borough_boundaries",
        "url": "https://data.cityofnewyork.us/resource/gthc-hcne.geojson",
        "license": "NYC Open Data Terms of Use (no license named in dataset metadata); attribution: NYC Department of City Planning",
    },
    # Census sources: the city limits (TIGERweb Incorporated Places) minus
    # TIGERweb areal hydrography gives the land boundary. Checked 2026-11-14
    # against the Census land area of each place: dc 158.3 km2, sea 217.6 km2,
    # sf 120.9 km2, all matching to 0.1 km2.
    "dc": {
        "source": "census_tigerweb_place_land",
        "place_geoid": "1150000",
        "license": "Public domain (US Census Bureau TIGERweb)",
    },
    "sea": {
        "source": "census_tigerweb_place_land",
        "place_geoid": "5363000",
        "license": "Public domain (US Census Bureau TIGERweb)",
    },
    "sf": {
        "source": "census_tigerweb_place_land",
        "place_geoid": "0667000",
        "license": "Public domain (US Census Bureau TIGERweb)",
        # The city limits include the Farallon Islands, 45 km offshore and
        # uninhabited. Keep the mainland, Treasure Island and Yerba Buena.
        "clip_bbox": (-122.55, 37.68, -122.33, 37.86),
    },
}

TIGERWEB = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb"
PLACES_LAYER = f"{TIGERWEB}/tigerWMS_Current/MapServer/28/query"
AREAL_HYDRO_LAYER = f"{TIGERWEB}/Hydro/MapServer/1/query"


def _query_geojson(url, **params):
    """Page through an ArcGIS REST layer, returning GeoJSON features."""
    feats, offset = [], 0
    while True:
        r = requests.get(url, timeout=180, params={
            **params, "f": "geojson", "resultOffset": offset, "resultRecordCount": 1000})
        r.raise_for_status()
        body = r.json()
        if "error" in body:
            raise RuntimeError(f"{url}: {body['error']}")
        feats.extend(body["features"])
        more = body.get("exceededTransferLimit") or body.get("properties", {}).get("exceededTransferLimit")
        if not body["features"] or not more:
            return feats
        offset += len(body["features"])


def _fetch_census_land(src, dest):
    """City limits and water as received (place.geojson, water.geojson), and
    the derived land boundary (boundary.geojson)."""
    place_feats = _query_geojson(PLACES_LAYER, where=f"GEOID='{src['place_geoid']}'",
                                 outFields="GEOID,NAME,AREALAND,AREAWATER", outSR=4326)
    place = unary_union([shape(f["geometry"]) for f in place_feats])
    west, south, east, north = place.bounds
    water_feats = _query_geojson(
        AREAL_HYDRO_LAYER, geometry=f"{west},{south},{east},{north}",
        geometryType="esriGeometryEnvelope", inSR=4326, outSR=4326,
        spatialRel="esriSpatialRelIntersects", outFields="OID,NAME")
    water = unary_union([shape(f["geometry"]).buffer(0) for f in water_feats])
    land = place.difference(water)
    if "clip_bbox" in src:
        land = land.intersection(box(*src["clip_bbox"]))

    def collection(features):
        return json.dumps({"type": "FeatureCollection", "features": features})

    (dest.parent / "place.geojson").write_text(collection(place_feats))
    (dest.parent / "water.geojson").write_text(collection(water_feats))
    dest.write_text(collection([{
        "type": "Feature", "geometry": mapping(land),
        "properties": {"place_geoid": src["place_geoid"], "derived": "place minus areal hydrography"},
    }]))
    return dest


def fetch(city_id, dest_dir):
    """Download the boundary GeoJSON as received. Returns the file path."""
    src = SOURCES[city_id]
    dest = Path(dest_dir) / city_id / "boundary.geojson"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if "place_geoid" in src:
        return _fetch_census_land(src, dest)
    r = requests.get(src["url"], timeout=120)
    r.raise_for_status()
    dest.write_bytes(r.content)
    return dest


def read_polygon(path):
    """One (multi)polygon for the whole city, EPSG:4326."""
    features = json.loads(Path(path).read_text())["features"]
    return unary_union([shape(f["geometry"]) for f in features])
