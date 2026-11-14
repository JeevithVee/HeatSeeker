"""Seattle: SDOT Trees (Seattle Department of Transportation street trees).

The live layer on Seattle GeoData: one row per street tree SDOT tracks,
whoever maintains it. Checked 2026-11-14: 276,760 rows, 272,870 with a
planting date, every row located. It keeps removed trees
(CURRENT_STATUS = REMOVED, 58,137 rows), so removal is tracked. This one
layer covers the whole period; the 63-city research copy is not needed.

Three things in the dates are not plantings:
- 71,271 rows are dated 1 January. The day is unknown and the years pile up
  on round numbers (2000, 2005, 2010, 1995, 2015), so they are estimates.
  They are treated as placeholders.
- July to September 1991 carries about 900 trees a day: the first inventory
  survey, not planting. Nothing before 1993 is used.
- Rows whose status is PLANNED (or another not-yet-built status) carry the
  intended date of a tree that was not planted.
"""
import json
from datetime import date
from pathlib import Path

import pandas as pd

from . import common

CITY_ID = "sea"
SOURCE_ID = "sea_sdot_trees"
LAYER_URL = "https://services.arcgis.com/ZOyb2t4B0UYuYNYH/arcgis/rest/services/SDOT_Trees_CDL/FeatureServer/0"
# The dataset names no license; its only terms are an accuracy disclaimer.
LICENSE = "City of Seattle Open Data (no license named in dataset metadata; accuracy disclaimer only); attribution: City of Seattle, Seattle Department of Transportation"

COVERAGE_START_YEAR = 1993
REMOVED_STATUSES = {"REMOVED"}
NOT_PLANTED_STATUSES = {"PLANNED", "PTNLINSTL", "PLNRECON", "UNDERCONS"}
DATE_NOT_PLANTED = "not_planted"


def fetch(dest_dir):
    """Download every row of the layer as CSV. Returns the file path."""
    return common.fetch_arcgis_layer(LAYER_URL, Path(dest_dir) / "sdot_trees_raw.csv")


def read_raw(path):
    """Read the downloaded CSV with every column as text, exactly as received."""
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])


def to_bronze(raw, ingested_at=None):
    return common.bronze_frame(
        raw,
        city_id=CITY_ID,
        role="intervention",
        source=SOURCE_ID,
        license=LICENSE,
        value=1.0,
        units="trees",
        date=raw["PLANTED_DATE"],
        geometry="POINT (" + raw["LONGITUDE"].fillna("") + " " + raw["LATITUDE"].fillna("") + ")",
        source_record_id=raw["OBJECTID"],
        ingested_at=ingested_at,
    )


def to_records(bronze, as_of=None):
    """Bronze rows -> one cleaned record per tree (common.RECORD_COLUMNS)."""
    as_of = as_of or date.today()
    attrs = pd.DataFrame([json.loads(a) for a in bronze["attributes"]], index=bronze.index)
    if "CURRENT_STATUS" not in attrs:
        attrs["CURRENT_STATUS"] = None

    coords = bronze["geometry"].str.extract(r"POINT\s*\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\)")
    lon = pd.to_numeric(coords[0], errors="coerce")
    lat = pd.to_numeric(coords[1], errors="coerce")

    # Every timestamp is exactly 00:00 UTC: the source stores a calendar date
    # with no time. Converting to Pacific time would move it to the day before.
    dates = pd.to_datetime(bronze["date"], errors="coerce", utc=True).dt.tz_localize(None).dt.normalize()

    issue = common.classify_dates(
        dates, bronze["date"],
        coverage_start_year=COVERAGE_START_YEAR, as_of=as_of,
        placeholder_dates=[f"{y}-01-01" for y in range(COVERAGE_START_YEAR, as_of.year + 2)],
    )
    issue[issue.isna() & attrs["CURRENT_STATUS"].isin(NOT_PLANTED_STATUSES)] = DATE_NOT_PLANTED

    out = pd.DataFrame({
        "country_code": bronze["country_code"],
        "city_id": bronze["city_id"],
        "source": bronze["source"],
        "source_record_id": bronze["source_record_id"],
        "intervention_type": "tree_planting",
        "lat": lat,
        "lon": lon,
        "planted_date": dates.where(issue.isna()),
        "date_issue": issue,
        "removed": attrs["CURRENT_STATUS"].isin(REMOVED_STATUSES),
        "removal_tracked": True,
    })
    return out[common.RECORD_COLUMNS]
