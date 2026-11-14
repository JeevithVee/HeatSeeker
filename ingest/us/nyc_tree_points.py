"""New York City: Forestry Tree Points (NYC Parks, NYC Open Data hn5i-inap).

One row per tree point the Parks forestry system has ever tracked. Unlike
most city inventories it keeps removed trees: `TPStructure` records whether
the point is a full tree, a stump, a standing dead shaft, or retired.

Checked 2026-11-14: 1,125,266 rows, 137,806 with a planting date, location
100% filled. Planting dates are usable from 2015 on.
"""
import json
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from . import common

CITY_ID = "nyc"
SOURCE_ID = "nyc_forestry_tree_points"
DATASET_ID = "hn5i-inap"
DOWNLOAD_URL = f"https://data.cityofnewyork.us/api/views/{DATASET_ID}/rows.csv?accessType=DOWNLOAD"
# The dataset metadata names no license; NYC Open Data's terms of use apply.
LICENSE = "NYC Open Data Terms of Use (no license named in dataset metadata); attribution: NYC Department of Parks and Recreation"

LOCAL_TZ = "America/New_York"
# Only 11 dated rows fall before 2015, so nothing earlier is usable.
COVERAGE_START_YEAR = 2015
# Tree points that no longer carry a living canopy.
REMOVED_STRUCTURES = {"Retired", "Stump", "Stump - Uprooted", "Shaft"}
DEAD_CONDITIONS = {"Dead"}


def fetch(dest_dir):
    """Download the full table as CSV. Returns the file path."""
    dest = Path(dest_dir) / "tree_points_raw.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(DOWNLOAD_URL, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    return dest


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
        date=raw["PlantedDate"],
        geometry=raw["Geometry"],
        source_record_id=raw["OBJECTID"],
        ingested_at=ingested_at,
    )


def to_records(bronze, as_of=None):
    """Bronze rows -> one cleaned record per tree point (common.RECORD_COLUMNS)."""
    as_of = as_of or date.today()
    attrs = pd.DataFrame([json.loads(a) for a in bronze["attributes"]], index=bronze.index)
    for col in ("TPStructure", "TPCondition"):
        if col not in attrs:
            attrs[col] = None

    coords = bronze["geometry"].str.extract(r"POINT\s*\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\)")
    lon = pd.to_numeric(coords[0], errors="coerce")
    lat = pd.to_numeric(coords[1], errors="coerce")

    # Timestamps are UTC and mostly local midnight (04:00 or 05:00 UTC), so
    # the planting day is the New York calendar date, not the UTC one.
    utc = pd.to_datetime(bronze["date"], errors="coerce", utc=True)
    local_dates = utc.dt.tz_convert(LOCAL_TZ).dt.tz_localize(None).dt.normalize()

    issue = common.classify_dates(
        local_dates, bronze["date"],
        coverage_start_year=COVERAGE_START_YEAR, as_of=as_of,
    )

    out = pd.DataFrame({
        "country_code": bronze["country_code"],
        "city_id": bronze["city_id"],
        "source": bronze["source"],
        "source_record_id": bronze["source_record_id"],
        "intervention_type": "tree_planting",
        "lat": lat,
        "lon": lon,
        "planted_date": local_dates.where(issue.isna()),
        "date_issue": issue,
        "removed": attrs["TPStructure"].isin(REMOVED_STRUCTURES)
                   | attrs["TPCondition"].isin(DEAD_CONDITIONS),
        "removal_tracked": True,
    })
    return out[common.RECORD_COLUMNS]
