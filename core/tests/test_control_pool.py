import pandas as pd

from core.evaluation import EvalConfig
from core.evaluation.treatment import treatment_table
from core.evaluation.labels import quality_label


def test_control_pool_uses_all_years_and_never_reintroduces_batch_treated():
    records = pd.DataFrame([
        ("treated", 2015, 10, 0),
        ("batch", 2016, 12, 12),
        ("late", 2023, 3, 0),
        ("early", 2010, 3, 0),
        ("cumulative", 2018, 1, 0),
        ("cumulative", 2022, 2, 0),
        ("low", 2018, 1, 0),
        ("low", 2024, 1, 0),
    ], columns=["site_id", "plant_year", "trees_planted", "trees_batch_dated"])
    eligible = pd.Index(["treated", "batch", "late", "early", "cumulative", "low", "never"])
    for variant in ("all", "excl_batch_dated"):
        treated, controls = treatment_table(records, eligible, EvalConfig(), variant)
        assert set(controls) == {"low", "never"}
        assert set(treated.site_id) == ({"treated", "batch"} if variant == "all" else {"treated"})


def test_absent_placebo_cannot_produce_a_detection_or_precise_null_label():
    assert quality_label(-3, -4, -2, float("nan"), 0.1, 10, 10, 10, EvalConfig()) == "inconclusive"
    assert quality_label(0, -0.1, 0.1, float("nan"), 0.1, 10, 10, 10, EvalConfig()) == "inconclusive"
    assert quality_label(-3, -4, -2, 0.01, 0.1, 10, 10, 10, EvalConfig()) == "detected"
