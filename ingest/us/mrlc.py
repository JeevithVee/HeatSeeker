"""Annual NLCD rasters from the MRLC map server (USGS), 30 m, CONUS.

Fills three roles: canopy (NLCD Tree Canopy), land cover (impervious fraction
and land cover class). Rasters are requested for a city's bounding box on the
native 30 m Albers grid, so no resampling happens on the way in.

Access checked 2026-11-14: WCS 1.0.0 honours the `time` parameter; WCS 2.0.1
time subsetting fails on these layers.
"""
import logging
from pathlib import Path

import numpy as np
import requests
import tifffile
from pyproj import Transformer

WCS_URL = "https://www.mrlc.gov/geoserver/ows"
LICENSE = "Public domain (USGS / MRLC Annual NLCD)"
CRS = "EPSG:5070"

# Native grid of the Annual NLCD CONUS layers.
GRID_X0 = -2361585.0   # west edge
GRID_Y0 = 3177435.0    # north edge
PIXEL_M = 30.0

# tifffile warns about the float nodata tag on these byte rasters; harmless.
logging.getLogger("tifffile").setLevel(logging.ERROR)

LAYERS = {
    # role, MRLC layer name, units of the pixel values
    "canopy":     ("canopy",     "NLCD-Tree-Canopy-Native_conus_year_data", "percent"),
    "impervious": ("land_cover", "Fractional-Impervious-Surface-Native_conus_year_data", "percent"),
    "land_cover": ("land_cover", "Land-Cover-Native_conus_year_data", "class"),
}

LAND_COVER_CLASSES = {
    11: "open_water", 12: "perennial_ice_snow",
    21: "developed_open_space", 22: "developed_low_intensity",
    23: "developed_medium_intensity", 24: "developed_high_intensity",
    31: "barren", 41: "deciduous_forest", 42: "evergreen_forest", 43: "mixed_forest",
    52: "shrub_scrub", 71: "grassland_herbaceous", 81: "pasture_hay",
    82: "cultivated_crops", 90: "woody_wetlands", 95: "emergent_herbaceous_wetlands",
}


def source_id(layer, year):
    return f"mrlc_annual_nlcd_{layer}_{year}"


def snapped_bbox(lon_min, lat_min, lon_max, lat_max, pad_m=300):
    """Bounding box in EPSG:5070, padded and snapped outward to the 30 m grid."""
    to_albers = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
    xs, ys = to_albers.transform([lon_min, lon_min, lon_max, lon_max],
                                 [lat_min, lat_max, lat_min, lat_max])
    x_min = GRID_X0 + np.floor((min(xs) - pad_m - GRID_X0) / PIXEL_M) * PIXEL_M
    x_max = GRID_X0 + np.ceil((max(xs) + pad_m - GRID_X0) / PIXEL_M) * PIXEL_M
    y_max = GRID_Y0 - np.floor((GRID_Y0 - max(ys) - pad_m) / PIXEL_M) * PIXEL_M
    y_min = GRID_Y0 - np.ceil((GRID_Y0 - min(ys) + pad_m) / PIXEL_M) * PIXEL_M
    return x_min, y_min, x_max, y_max


def fetch(layer, year, bbox_5070, dest_dir):
    """Download one layer-year for a snapped bbox as GeoTIFF. Returns the path."""
    _, name, _ = LAYERS[layer]
    x_min, y_min, x_max, y_max = bbox_5070
    params = {
        "service": "WCS", "version": "1.0.0", "request": "GetCoverage",
        "coverage": f"mrlc_{name}:{name}",
        "format": "GeoTIFF", "crs": CRS,
        "bbox": f"{x_min},{y_min},{x_max},{y_max}",
        "width": int(round((x_max - x_min) / PIXEL_M)),
        "height": int(round((y_max - y_min) / PIXEL_M)),
        "time": f"{year}-01-01T00:00:00.000Z",
    }
    r = requests.get(WCS_URL, params=params, timeout=300)
    r.raise_for_status()
    if not r.headers.get("content-type", "").startswith("image/tiff"):
        raise RuntimeError(f"MRLC returned no raster for {layer} {year}: {r.text[:300]}")
    dest = Path(dest_dir) / f"{layer}_{year}.tif"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return dest


def read(path):
    """Read a downloaded raster. Returns (values, x_west, y_north, pixel_m)."""
    with tifffile.TiffFile(path) as tif:
        page = tif.pages[0]
        values = page.asarray()
        m = page.tags["ModelTransformationTag"].value
    pixel_x, x_west, pixel_y, y_north = m[0], m[3], -m[5], m[7]
    if abs(pixel_x - PIXEL_M) > 1e-3 or abs(pixel_y - PIXEL_M) > 1e-3:
        raise ValueError(f"{path}: pixels are {pixel_x} x {pixel_y} m, expected the native 30 m grid")
    return values, x_west, y_north, PIXEL_M


def pixel_centres_lonlat(shape, x_west, y_north, pixel_m):
    """Longitude and latitude of every pixel centre, as two flat arrays."""
    rows, cols = shape
    x = x_west + (np.arange(cols) + 0.5) * pixel_m
    y = y_north - (np.arange(rows) + 0.5) * pixel_m
    xx, yy = np.meshgrid(x, y)
    to_lonlat = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)
    lon, lat = to_lonlat.transform(xx.ravel(), yy.ravel())
    return lon, lat
