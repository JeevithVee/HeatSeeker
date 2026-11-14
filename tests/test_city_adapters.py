"""Each city adapter, on a few hand-made rows shaped like its source."""
from datetime import date

import pandas as pd

from ingest.us import common, dc_street_trees

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
