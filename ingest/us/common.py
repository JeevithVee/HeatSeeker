"""Shared helpers for US adapters.

Every adapter exposes the same three functions:

    fetch(dest_dir)      download the source as received, return the file path
    to_bronze(raw)       raw DataFrame -> rows in the standard bronze schema
    to_records(bronze)   bronze rows -> one cleaned row per intervention record

`to_records` output is the same for every city (see RECORD_COLUMNS), so the
pipeline that builds silver.interventions never sees a city-specific column.
"""
import json
from datetime import datetime, timezone

import pandas as pd

import schema

COUNTRY_CODE = "US"

# Cleaned, one row per intervention record. Internal to Agent 1's pipeline.
RECORD_COLUMNS = [
    "country_code",
    "city_id",
    "source",
    "source_record_id",
    "intervention_type",
    "lat",
    "lon",
    "planted_date",     # datetime64 (local calendar date), NaT when unusable
    "date_issue",       # None, or why planted_date is unusable
    "removed",          # the source records this tree as removed or dead
    "removal_tracked",  # False when the source lists only standing trees
]

# Values of date_issue
DATE_MISSING = "missing"
DATE_UNPARSEABLE = "unparseable"
DATE_TYPO_YEAR = "typo_year"
DATE_BEFORE_COVERAGE = "before_coverage"
DATE_FUTURE = "future"
DATE_PLACEHOLDER = "placeholder"


def bronze_frame(raw, *, city_id, role, source, license, value, units, date,
                 geometry, source_record_id, ingested_at=None):
    """Build bronze rows from a raw frame.

    `value`, `date`, `geometry` and `source_record_id` are Series aligned with
    `raw`. Every raw column is kept, unmodified, in the `attributes` JSON.
    """
    ingested_at = ingested_at or datetime.now(timezone.utc)
    attributes = [
        json.dumps({k: v for k, v in row.items() if v is not None and v == v},
                   separators=(",", ":"))
        for row in raw.to_dict(orient="records")
    ]
    out = pd.DataFrame({
        "country_code": COUNTRY_CODE,
        "city_id": city_id,
        "role": role,
        "value": value,
        "units": units,
        "date": date,
        "geometry": geometry,
        "source": source,
        "license": license,
        "source_record_id": source_record_id,
        "attributes": attributes,
        "ingested_at": pd.Timestamp(ingested_at),
    }, index=raw.index)
    return schema.validate(out, "bronze")


def classify_dates(local_dates, raw_text, *, coverage_start_year, as_of,
                   placeholder_dates=()):
    """Label why a planting date is unusable, or None when it is fine.

    local_dates  parsed local calendar dates (NaT when parsing failed)
    raw_text     the date text as received, used to tell typos from blanks
    """
    year_text = raw_text.fillna("").str.extract(r"^\s*(\d{4})", expand=False)
    year = pd.to_numeric(year_text, errors="coerce")
    blank = raw_text.isna() | (raw_text.fillna("").str.strip() == "")

    issue = pd.Series([None] * len(raw_text), index=raw_text.index, dtype="object")
    issue[local_dates.isna()] = DATE_UNPARSEABLE
    # A four-digit year far outside any plausible range is a keying error.
    issue[(year < 1900) | (year > as_of.year + 1)] = DATE_TYPO_YEAR
    issue[blank] = DATE_MISSING
    ok = issue.isna()
    issue[ok & (local_dates > pd.Timestamp(as_of))] = DATE_FUTURE
    issue[ok & (local_dates.dt.year < coverage_start_year)] = DATE_BEFORE_COVERAGE
    if len(placeholder_dates):
        placeholders = pd.to_datetime(list(placeholder_dates))
        issue[ok & local_dates.isin(placeholders)] = DATE_PLACEHOLDER
    return issue
