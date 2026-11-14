"""Each city adapter, on a few hand-made rows shaped like its source."""
from datetime import date

import pandas as pd

from ingest.us import common, dc_street_trees, sea_sdot_trees, sf_street_tree_list

AS_OF = date(2026, 11, 14)


def dc_rows(rows):
    return pd.DataFrame([
        {"OBJECTID": str(i), "DATE_PLANT": planted, "TBOX_STAT": status, "CONDITION": condition,
         "RETIREDDT": retired, "LONGITUDE": "-77.0", "LATITUDE": "38.9", "CMMN_NM": "Red maple"}
        for i, (planted, status, condition, retired) in enumerate(rows)
    ])


def test_dc_records():
    raw = dc_rows([
        ("2016-11-02T04:30:00Z", "Plant", "Good", None),     # 00:30 local on 2 Nov
        ("2016-11-02T03:30:00Z", "Plant", "Good", None),     # 23:30 local on 1 Nov
        ("2017-04-01T15:00:00Z", "Plant", "Dead", None),
        ("2017-04-01T15:00:00Z", "Retired", "Good", "2020-01-01T05:00:00Z"),
        ("2017-04-01T15:00:00Z", "Open", None, None),        # space with no tree now
        (None, "Plant", "Good", None),                        # undated: not an intervention
        ("1899-12-30T05:00:00Z", "Plant", "Good", None),     # spreadsheet zero date
        ("1970-01-01T05:00:00Z", "Plant", "Good", None),     # Unix epoch
        ("1995-05-01T04:00:00Z", "Plant", "Good", None),     # before coverage
        ("2027-05-01T04:00:00Z", "Plant", "Good", None),     # future
    ])
    bronze = dc_street_trees.to_bronze(raw)
    assert len(bronze) == len(raw)
    assert bronze["license"].str.contains("CC-BY-4.0").all()
    rec = dc_street_trees.to_records(bronze, as_of=AS_OF)

    assert list(rec.columns) == common.RECORD_COLUMNS
    assert rec["date_issue"].tolist() == [
        None, None, None, None, None,
        common.DATE_MISSING, common.DATE_TYPO_YEAR, common.DATE_PLACEHOLDER,
        common.DATE_BEFORE_COVERAGE, common.DATE_FUTURE,
    ]
    # UTC timestamps become Washington calendar days.
    assert rec["planted_date"].iloc[0] == pd.Timestamp("2016-11-02")
    assert rec["planted_date"].iloc[1] == pd.Timestamp("2016-11-01")
    assert rec["planted_date"].iloc[5:].isna().all()
    assert rec["removed"].tolist()[:5] == [False, False, True, True, True]
    assert not rec["removal_tracked"].any()
    assert rec["lat"].iloc[0] == 38.9 and rec["lon"].iloc[0] == -77.0


def test_sea_records():
    rows = [
        ("2016-03-17T00:00:00Z", "INSVC"),       # stored as midnight UTC: the date is 17 March
        ("2016-03-17T00:00:00Z", "REMOVED"),
        ("2016-01-01T00:00:00Z", "INSVC"),       # 1 January: day unknown, year estimated
        ("2018-05-02T00:00:00Z", "PLANNED"),     # intended date of a tree not planted
        ("1991-08-30T00:00:00Z", "INSVC"),       # first inventory survey, not planting
        (None, "INSVC"),
        ("2027-02-01T00:00:00Z", "INSVC"),       # future
    ]
    raw = pd.DataFrame([
        {"OBJECTID": str(i), "PLANTED_DATE": planted, "CURRENT_STATUS": status,
         "LONGITUDE": "-122.33", "LATITUDE": "47.61"}
        for i, (planted, status) in enumerate(rows)
    ])
    rec = sea_sdot_trees.to_records(sea_sdot_trees.to_bronze(raw), as_of=AS_OF)

    assert list(rec.columns) == common.RECORD_COLUMNS
    assert rec["date_issue"].tolist() == [
        None, None, common.DATE_PLACEHOLDER, sea_sdot_trees.DATE_NOT_PLANTED,
        common.DATE_BEFORE_COVERAGE, common.DATE_MISSING, common.DATE_FUTURE,
    ]
    # No shift to the previous day.
    assert rec["planted_date"].iloc[0] == pd.Timestamp("2016-03-17")
    assert rec["planted_date"].iloc[2:].isna().all()
    assert rec["removed"].tolist()[:2] == [False, True]
    assert rec["removal_tracked"].all()


def test_sf_records():
    rows = [
        ("2017-08-22", "POINT (-122.40185 37.748486)"),
        ("2018-06-29", None),                    # dated but not located
        (None, "POINT (-122.40185 37.748486)"),
        ("1990-03-09", "POINT (-122.40185 37.748486)"),   # before coverage
    ]
    raw = pd.DataFrame([
        {"treeid": str(i), "planteddate": planted, "point": point, "legalstatus": "DPW Maintained"}
        for i, (planted, point) in enumerate(rows)
    ])
    bronze = sf_street_tree_list.to_bronze(raw)
    assert bronze["license"].str.contains("PDDL").all()
    rec = sf_street_tree_list.to_records(bronze, as_of=AS_OF)

    assert list(rec.columns) == common.RECORD_COLUMNS
    assert rec["date_issue"].tolist() == [None, None, common.DATE_MISSING, common.DATE_BEFORE_COVERAGE]
    assert rec["planted_date"].iloc[0] == pd.Timestamp("2017-08-22")
    assert rec["lat"].iloc[0] == 37.748486 and rec["lon"].iloc[0] == -122.40185
    assert pd.isna(rec["lat"].iloc[1])          # kept as a record, cannot be placed in a cell
    assert not rec["removed"].any() and not rec["removal_tracked"].any()
