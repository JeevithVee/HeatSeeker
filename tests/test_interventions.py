"""Cleaning and aggregation rules, on a small hand-made NYC-shaped frame."""
from datetime import date

import pandas as pd
import pytest

import schema
from ingest.us import common, nyc_tree_points
from pipelines import interventions

AS_OF = date(2026, 11, 14)


def raw_rows(rows):
    base = {"DBH": "3", "TPCondition": "Good", "GenusSpecies": "Acer rubrum - red maple"}
    out = []
    for i, (structure, planted, lon, lat, *rest) in enumerate(rows):
        row = dict(base, OBJECTID=str(i), TPStructure=structure, PlantedDate=planted,
                   Geometry=f"POINT({lon} {lat})")
        if rest:
            row["TPCondition"] = rest[0]
        out.append(row)
    return pd.DataFrame(out)


A = (-73.95, 40.70)   # two points far enough apart to sit in different cells
B = (-73.80, 40.75)


@pytest.fixture
def records():
    raw = raw_rows([
        ("Full",    "2016-05-10 04:00:00.0000000", *A),
        ("Full",    "2016-11-02 04:00:00.0000000", *A),
        ("Stump",   "2016-05-10 04:00:00.0000000", *A),
        ("Retired", "2017-04-01 04:00:00.0000000", *B),
        ("Full",    "2017-04-01 04:00:00.0000000", *B, "Dead"),
        ("Full",    None,                          *A),   # undated: not an intervention
        ("Full",    "0202-12-25 04:56:01.0000000", *A),   # typo year
        ("Full",    "2108-01-01 05:00:00.0000000", *A),   # typo year
        ("Full",    "2012-06-01 04:00:00.0000000", *A),   # before coverage
        ("Full",    "2027-06-01 04:00:00.0000000", *A),   # future
    ])
    return nyc_tree_points.to_records(nyc_tree_points.to_bronze(raw), as_of=AS_OF)


def test_bronze_keeps_every_row_and_field():
    raw = raw_rows([("Full", "0202-12-25 04:56:01.0000000", *A), ("Full", None, *B)])
    bronze = nyc_tree_points.to_bronze(raw)
    assert len(bronze) == 2
    assert bronze["date"].iloc[0] == "0202-12-25 04:56:01.0000000"
    assert '"TPStructure":"Full"' in bronze["attributes"].iloc[0]
    assert bronze["license"].notna().all()


def test_date_issues(records):
    assert records["date_issue"].tolist() == [
        None, None, None, None, None,
        common.DATE_MISSING, common.DATE_TYPO_YEAR, common.DATE_TYPO_YEAR,
        common.DATE_BEFORE_COVERAGE, common.DATE_FUTURE,
    ]
    assert records["planted_date"].notna().sum() == 5


def test_utc_timestamp_becomes_local_day():
    # 03:30 UTC on 2 June is still the evening of 1 June in New York.
    raw = raw_rows([("Full", "2018-06-02 03:30:00.0000000", *A)])
    rec = nyc_tree_points.to_records(nyc_tree_points.to_bronze(raw), as_of=AS_OF)
    assert rec["planted_date"].iloc[0] == pd.Timestamp("2018-06-01")


def test_aggregation_to_cell_years(records):
    silver = interventions.build_interventions(records)
    assert list(silver.columns) == schema.columns("silver.interventions")
    assert len(silver) == 2
    a, b = silver.sort_values("plant_year").to_dict("records")

    assert (a["plant_year"], a["trees_planted"], a["trees_removed"], a["trees_surviving"]) == (2016, 3, 1, 2)
    assert a["removed_flag"] is False
    assert (a["first_plant_date"], a["last_plant_date"]) == (date(2016, 5, 10), date(2016, 11, 2))
    assert len(a["site_id"]) == 15 and a["site_id"] == a["site_id"].lower()

    # A retired point and a dead tree: nothing survives, so the cell-year is removed.
    assert (b["plant_year"], b["trees_planted"], b["trees_removed"]) == (2017, 2, 2)
    assert b["removed_flag"] is True


def test_batch_days_are_flagged_not_dropped(records):
    silver = interventions.build_interventions(records, batch_day_threshold=2)
    by_year = silver.set_index("plant_year")
    # 2016-05-10 and 2017-04-01 each carry two records.
    assert by_year.loc[2016, "trees_batch_dated"] == 2
    assert by_year.loc[2017, "trees_batch_dated"] == 2
    assert by_year["trees_planted"].sum() == 5
