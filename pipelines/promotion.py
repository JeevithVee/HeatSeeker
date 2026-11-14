"""Fold plantings logged in the app into silver.interventions.

The app's Track form writes to a staging table (gold.app_planting_log). This
module decides which logged rows count as interventions and merges them with
the rows built from city inventories. City-agnostic.

The rule that prevents double counting: a city's inventory already contains
every planting up to its latest planting date (the inventory horizon). A
logged planting is promoted only if it is dated after that horizon. When the
inventory is refreshed the horizon moves forward, and logged rows it now
covers drop out on the next build, replaced by the inventory's own records.
"""
import pandas as pd

import schema

LOG_SOURCE = "app_planting_log"
# Log values that mean trees. silver.interventions counts trees, so other
# intervention types (cool roofs, cool pavement) are not promoted.
TREE_TYPES = {"tree_planting", "street_trees", "park_trees"}

REJECT_NOT_TREES = "not_a_tree_planting"
REJECT_BAD_COUNT = "no_tree_count"
REJECT_NO_DATE = "no_planted_date"
REJECT_FUTURE = "dated_after_it_was_logged"
REJECT_UNKNOWN_CITY = "unknown_city"
REJECT_OUTSIDE_GRID = "site_not_in_city_grid"
REJECT_COVERED = "covered_by_inventory"
REJECT_DUPLICATE = "duplicate_submission"


def inventory_horizons(inventory):
    """Latest planting date per city in the inventory-built rows."""
    return pd.to_datetime(inventory["last_plant_date"]).groupby(inventory["city_id"]).max()


def classify_log(log, inventory, grid_site_ids):
    """Return the log with a `reject_reason` column (None = promote).

    grid_site_ids  {city_id: set of site_id in that city's grid}
    """
    out = log.copy()
    planted = pd.to_datetime(out["planted_date"], errors="coerce")
    logged = pd.to_datetime(out["logged_at_utc"], errors="coerce", utc=True).dt.tz_localize(None)
    horizon = out["city_id"].map(inventory_horizons(inventory))
    in_grid = pd.Series([site in grid_site_ids.get(city, ()) for city, site in zip(out["city_id"], out["site_id"])],
                        index=out.index, dtype=bool)
    count = pd.to_numeric(out["trees_planted"], errors="coerce")

    # Later rules overwrite earlier ones, so the list runs from least to most basic.
    reason = pd.Series([None] * len(out), index=out.index, dtype="object")
    reason[out.duplicated(["city_id", "site_id", "planted_date", "trees_planted", "logged_by"])] = REJECT_DUPLICATE
    reason[planted <= horizon] = REJECT_COVERED
    reason[planted > logged + pd.Timedelta(days=1)] = REJECT_FUTURE
    reason[~in_grid] = REJECT_OUTSIDE_GRID
    reason[~out["city_id"].isin(list(grid_site_ids))] = REJECT_UNKNOWN_CITY
    reason[planted.isna()] = REJECT_NO_DATE
    reason[count.isna() | (count <= 0)] = REJECT_BAD_COUNT
    reason[~out["intervention_type"].isin(TREE_TYPES)] = REJECT_NOT_TREES
    out["reject_reason"] = reason
    return out


def promote(log, inventory, grid_site_ids):
    """Merge promotable log rows into the inventory-built interventions.

    Returns (interventions, classified_log). With no promotable rows the
    interventions come back unchanged.
    """
    classified = classify_log(log, inventory, grid_site_ids)
    ok = classified[classified["reject_reason"].isna()]
    if ok.empty:
        return inventory, classified

    planted = pd.to_datetime(ok["planted_date"])
    keys = ["country_code", "city_id", "site_id", "plant_year", "intervention_type"]
    logged = (ok.assign(plant_year=planted.dt.year.astype(int), intervention_type="tree_planting",
                        planted=planted.dt.date, trees=pd.to_numeric(ok["trees_planted"]).astype(int))
              .groupby(keys, as_index=False)
              .agg(trees_planted=("trees", "sum"), first_plant_date=("planted", "min"),
                   last_plant_date=("planted", "max")))
    logged["trees_removed"] = 0
    logged["trees_batch_dated"] = 0
    logged["removal_tracked"] = False      # the log records plantings, never removals
    logged["source"] = LOG_SOURCE

    both = pd.concat([inventory, logged], ignore_index=True)
    for col in ("first_plant_date", "last_plant_date"):
        both[col] = pd.to_datetime(both[col]).dt.date
    merged = both.groupby(keys, as_index=False).agg(
        trees_planted=("trees_planted", "sum"),
        trees_removed=("trees_removed", "sum"),
        removal_tracked=("removal_tracked", "all"),
        trees_batch_dated=("trees_batch_dated", "sum"),
        first_plant_date=("first_plant_date", "min"),
        last_plant_date=("last_plant_date", "max"),
        source=("source", lambda s: "+".join(dict.fromkeys(s))),
    )
    merged["trees_surviving"] = merged["trees_planted"] - merged["trees_removed"]
    merged["removed_flag"] = merged["trees_surviving"] == 0
    merged = merged.sort_values(["city_id", "site_id", "plant_year"]).reset_index(drop=True)
    return schema.validate(merged, "silver.interventions"), classified
