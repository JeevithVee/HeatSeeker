"""San Francisco: Street Tree List (San Francisco Public Works, data.sf.gov tkzw-k3nq).

The live list, not the 63-city research copy. Checked 2026-11-14: 144,606
rows, 38,741 (27%) with a planting date. The list holds standing trees only,
so removal is not tracked and earlier plantings that died are missing.

Dated trees are not confined to a few neighbourhoods: all 41 analysis
neighbourhoods have some, the dated share runs from 7% to 54%, and the five
neighbourhoods with the most dated trees hold 40% of them against 34% of all
trees. 4,880 dated trees have no coordinates and cannot be placed in a cell.
"""
import json
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from . import common

CITY_ID = "sf"
SOURCE_ID = "sf_street_tree_list"
DATASET_ID = "tkzw-k3nq"
DOWNLOAD_URL = f"https://data.sf.gov/api/views/{DATASET_ID}/rows.csv?accessType=DOWNLOAD"
LICENSE = "Open Data Commons Public Domain Dedication and License (PDDL 1.0); attribution: San Francisco Public Works"

# Dates are plain calendar dates with no time, so no time zone conversion.
COVERAGE_START_YEAR = 1995


def fetch(dest_dir):
    """Download the full table as CSV. Returns the file path."""
    dest = Path(dest_dir) / "street_tree_list_raw.csv"
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
        date=raw["planteddate"],
        geometry=raw["point"],
        source_record_id=raw["treeid"],
        ingested_at=ingested_at,
    )


def to_records(bronze, as_of=None):
    """Bronze rows -> one cleaned record per tree (common.RECORD_COLUMNS)."""
    as_of = as_of or date.today()
    coords = bronze["geometry"].str.extract(r"POINT\s*\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\)")
    lon = pd.to_numeric(coords[0], errors="coerce")
    lat = pd.to_numeric(coords[1], errors="coerce")

    dates = pd.to_datetime(bronze["date"], errors="coerce").dt.normalize()
    issue = common.classify_dates(
        dates, bronze["date"],
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
        "planted_date": dates.where(issue.isna()),
        "date_issue": issue,
        "removed": False,
        "removal_tracked": False,
    })
    return out[common.RECORD_COLUMNS]
