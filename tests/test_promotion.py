"""Promotion of app-logged plantings into silver.interventions."""
from datetime import date

import pandas as pd

import schema
from pipelines import promotion

A, B, OUTSIDE = "892a100d2c3ffff", "892a100d2c7ffff", "892a1000000ffff"
GRID = {"nyc": {A, B}}


def inventory():
    return pd.DataFrame([{
        "country_code": "US", "city_id": "nyc", "site_id": A, "plant_year": 2026,
        "intervention_type": "tree_planting", "trees_planted": 4, "trees_removed": 1, "trees_surviving": 3,
        "removed_flag": False, "removal_tracked": True, "trees_batch_dated": 0,
        "first_plant_date": date(2026, 4, 2), "last_plant_date": date(2026, 11, 3),
        "source": "nyc_forestry_tree_points",
    }])[schema.columns("silver.interventions")]


def log(rows):
    base = {"country_code": "US", "city_id": "nyc", "site_id": A, "intervention_type": "street_trees",
            "trees_planted": 5, "planted_date": date(2026, 11, 20), "cost_usd": 100.0,
            "logged_by": "planner", "logged_at_utc": pd.Timestamp("2026-11-21 15:00", tz="UTC")}
    return pd.DataFrame([dict(base, **r) for r in rows])


def test_empty_log_changes_nothing():
    out, classified = promotion.promote(log([]).reindex(columns=list(log([{}]).columns)), inventory(), GRID)
    pd.testing.assert_frame_equal(out, inventory())
    assert classified.empty


def test_rejections():
    rows = log([
        {},                                                   # promoted
        {},                                                   # same submission twice
        {"planted_date": date(2026, 10, 1)},                  # the inventory already covers this date
        {"planted_date": date(2027, 3, 1)},                   # dated after it was logged
        {"site_id": OUTSIDE},
        {"city_id": "paris"},
        {"planted_date": None},
        {"trees_planted": 0},
        {"intervention_type": "cool_roof"},
    ])
    _, classified = promotion.promote(rows, inventory(), GRID)
    assert classified["reject_reason"].tolist() == [
        None, promotion.REJECT_DUPLICATE, promotion.REJECT_COVERED, promotion.REJECT_FUTURE,
        promotion.REJECT_OUTSIDE_GRID, promotion.REJECT_UNKNOWN_CITY, promotion.REJECT_NO_DATE,
        promotion.REJECT_BAD_COUNT, promotion.REJECT_NOT_TREES,
    ]


def test_logged_rows_merge_into_the_same_cell_year_and_add_new_ones():
    rows = log([{}, {"site_id": B, "trees_planted": 12, "planted_date": date(2027, 4, 1),
                     "logged_at_utc": pd.Timestamp("2027-04-02", tz="UTC")}])
    out, _ = promotion.promote(rows, inventory(), GRID)
    assert list(out.columns) == schema.columns("silver.interventions")
    a = out[out.site_id == A].iloc[0]
    assert (a.trees_planted, a.trees_removed, a.trees_surviving) == (9, 1, 8)
    assert a.source == "nyc_forestry_tree_points+app_planting_log"
    assert a.last_plant_date == date(2026, 11, 20) and not a.removal_tracked

    b = out[out.site_id == B].iloc[0]
    assert (b.plant_year, b.trees_planted, b.source) == (2027, 12, "app_planting_log")
    assert b.intervention_type == "tree_planting" and not b.removed_flag
