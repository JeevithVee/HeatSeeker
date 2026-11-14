"""Cleaned intervention records -> silver.interventions.

City-agnostic: takes the common record frame every adapter produces
(ingest.us.common.RECORD_COLUMNS) and aggregates dated plantings into H3 cells.
"""
import h3
import pandas as pd

import schema

# "Hundreds of trees dated on one day are likely batch entries."
DEFAULT_BATCH_DAY_THRESHOLD = 300


def add_site_id(records, resolution=schema.H3_RESOLUTION):
    """Add the H3 cell of each record. Records without coordinates get None."""
    out = records.copy()
    out["site_id"] = [
        h3.latlng_to_cell(lat, lon, resolution) if lat == lat and lon == lon else None
        for lat, lon in zip(out["lat"], out["lon"])
    ]
    return out


def flag_batch_days(records, threshold=DEFAULT_BATCH_DAY_THRESHOLD):
    """Mark records whose planting date is shared by `threshold` or more
    records in the same city. They are flagged, never dropped."""
    out = records.copy()
    per_day = out.groupby(["city_id", "planted_date"])["planted_date"].transform("size")
    out["batch_dated"] = out["planted_date"].notna() & (per_day >= threshold)
    return out


def build_interventions(records, *, resolution=schema.H3_RESOLUTION,
                        batch_day_threshold=DEFAULT_BATCH_DAY_THRESHOLD):
    """Aggregate records into one row per cell, planting year and type."""
    df = flag_batch_days(records, batch_day_threshold)
    df = df[df["planted_date"].notna()]
    df = add_site_id(df, resolution)
    df = df[df["site_id"].notna()]
    df = df.assign(plant_year=df["planted_date"].dt.year.astype(int))

    keys = ["country_code", "city_id", "site_id", "plant_year", "intervention_type"]
    out = df.groupby(keys, as_index=False).agg(
        trees_planted=("source_record_id", "size"),
        trees_removed=("removed", "sum"),
        removal_tracked=("removal_tracked", "all"),
        trees_batch_dated=("batch_dated", "sum"),
        first_plant_date=("planted_date", "min"),
        last_plant_date=("planted_date", "max"),
        source=("source", "first"),
    )
    for col in ("trees_planted", "trees_removed", "trees_batch_dated"):
        out[col] = out[col].astype(int)
    out["trees_surviving"] = out["trees_planted"] - out["trees_removed"]
    out["removed_flag"] = out["trees_surviving"] == 0
    out["first_plant_date"] = out["first_plant_date"].dt.date
    out["last_plant_date"] = out["last_plant_date"].dt.date
    out = out.sort_values(["city_id", "site_id", "plant_year"]).reset_index(drop=True)
    return schema.validate(out, "silver.interventions")


def cleaning_report(records):
    """Counts of what was kept and why the rest was not, for the cross-review."""
    issue = records["date_issue"].fillna("ok")
    return (records.assign(date_issue=issue)
            .groupby(["city_id", "date_issue"]).size()
            .rename("records").reset_index())
