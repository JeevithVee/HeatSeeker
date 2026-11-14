"""Washington DC: Urban Forestry Street Trees (DDOT Urban Forestry Division).

The live layer on DC Open Data: one row per street tree space DDOT manages.
Checked 2026-11-14: 224,097 rows, 107,122 with a planting date, every row
located. This one layer covers the whole period, so the 63-city research
copy and the Street Tree Archive (yearly snapshots without planting dates)
are not needed.

The layer lists the current inventory. A tree that died and whose space was
replanted is overwritten, so earlier removals are mostly missing: removal is
NOT fully tracked. Where the row itself says the tree is gone (the space is
no longer status "Plant", a retired date is set, or condition is Dead) it is
marked removed.
"""
import json
from datetime import date
from pathlib import Path

import pandas as pd
import requests

from . import common

CITY_ID = "dc"
SOURCE_ID = "dc_urban_forestry_street_trees"
LAYER_URL = "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Urban_Tree_Canopy/MapServer/23"
LICENSE = "CC-BY-4.0 (DC Open Data); attribution: District Department of Transportation, Urban Forestry Division"

LOCAL_TZ = "America/New_York"
# Dated plantings are sparse before 2003 (under 100 a year); see the MessageBoard.
COVERAGE_START_YEAR = 2003
# Empty values stored as dates: the spreadsheet zero date (225 rows) and the
# Unix epoch. Not plantings.
PLACEHOLDER_DATES = ("1899-12-30", "1970-01-01")
DEAD_CONDITIONS = {"Dead"}
# TBOX_STAT of a space that holds a tree. Everything else (Retired, Open,
# Proposed, Conflict, Delete, ...) is a space without a standing tree.
STANDING_STATUS = "Plant"
# Not needed and large (a binary annotation column).
SKIP_FIELDS = {"SE_ANNO_CAD_DATA", "SHAPE"}
DATE_FIELDS = ("DATE_PLANT", "RETIREDDT", "CONDITIODT", "CREATED_DATE", "LAST_EDITED_DATE")
PAGE_SIZE = 2000


def fetch(dest_dir):
    """Download every row of the layer as CSV. Returns the file path.

    Date columns arrive as milliseconds since the Unix epoch and are written
    as ISO UTC timestamps; nothing else is changed.
    """
    dest = Path(dest_dir) / "street_trees_raw.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    meta = requests.get(LAYER_URL, params={"f": "json"}, timeout=120).json()
    fields = [f["name"] for f in meta["fields"] if f["name"] not in SKIP_FIELDS]
    rows, offset = [], 0
    while True:
        r = requests.get(f"{LAYER_URL}/query", timeout=300, params={
            "where": "1=1", "outFields": ",".join(fields), "outSR": 4326,
            "orderByFields": "OBJECTID", "resultOffset": offset,
            "resultRecordCount": PAGE_SIZE, "f": "json",
        })
        r.raise_for_status()
        body = r.json()
        if "error" in body:
            raise RuntimeError(f"{SOURCE_ID}: {body['error']}")
        page = body["features"]
        for f in page:
            row = f["attributes"]
            geom = f.get("geometry") or {}
            row["LONGITUDE"], row["LATITUDE"] = geom.get("x"), geom.get("y")
            rows.append(row)
        if not page or not body.get("exceededTransferLimit"):
            break
        offset += len(page)
    raw = pd.DataFrame(rows)
    for col in DATE_FIELDS:
        if col in raw:
            raw[col] = pd.to_datetime(raw[col], unit="ms", utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    raw.to_csv(dest, index=False)
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
        date=raw["DATE_PLANT"],
        geometry="POINT (" + raw["LONGITUDE"].fillna("") + " " + raw["LATITUDE"].fillna("") + ")",
        source_record_id=raw["OBJECTID"],
        ingested_at=ingested_at,
    )


def to_records(bronze, as_of=None):
    """Bronze rows -> one cleaned record per tree space (common.RECORD_COLUMNS)."""
    as_of = as_of or date.today()
    attrs = pd.DataFrame([json.loads(a) for a in bronze["attributes"]], index=bronze.index)
    for col in ("RETIREDDT", "CONDITION", "TBOX_STAT"):
        if col not in attrs:
            attrs[col] = None

    coords = bronze["geometry"].str.extract(r"POINT\s*\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\)")
    lon = pd.to_numeric(coords[0], errors="coerce")
    lat = pd.to_numeric(coords[1], errors="coerce")

    # Timestamps are UTC and mostly local midnight, so the planting day is the
    # Washington calendar date, not the UTC one.
    utc = pd.to_datetime(bronze["date"], errors="coerce", utc=True)
    local_dates = utc.dt.tz_convert(LOCAL_TZ).dt.tz_localize(None).dt.normalize()

    issue = common.classify_dates(
        local_dates, bronze["date"],
        coverage_start_year=COVERAGE_START_YEAR, as_of=as_of,
        placeholder_dates=PLACEHOLDER_DATES,
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
        "removed": attrs["RETIREDDT"].notna() | attrs["CONDITION"].isin(DEAD_CONDITIONS)
                   | (attrs["TBOX_STAT"].notna() & (attrs["TBOX_STAT"] != STANDING_STATUS)),
        "removal_tracked": False,
    })
    return out[common.RECORD_COLUMNS]
