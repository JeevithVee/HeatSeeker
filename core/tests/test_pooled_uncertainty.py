import numpy as np
import pandas as pd
import pytest

from core.evaluation import EvalConfig
from core.evaluation.pooled import pooled_block_sensitivity
from core.evaluation.report import pre_trend_diagnostics


def example(shared=False):
    ids, values, features, matches = [], [], [], {}
    n = 12
    for i in range(n):
        treated = f"t{i}"
        controls = [f"c{j}" if shared else f"c{i}_{j}" for j in range(3)]
        matches[treated] = controls
        ids.append(treated)
        values.append([0, 0, 0] + [-0.1 * i] * 6)
        features.append((treated, 40.0, -74.0 + 0.04 * i))
        if not shared:
            for control in controls:
                ids.append(control)
                values.append([0] * 9)
                features.append((control, 40.0, -74.0 + 0.04 * i))
    if shared:
        for control in ("c0", "c1", "c2"):
            ids.append(control)
            values.append([0] * 9)
            features.append((control, 40.2, -74.0))
    wide = pd.DataFrame(values, index=ids)
    years = np.array([2012, 2013, 2014, 2021, 2022, 2023, 2024, 2025, 2026])
    gold = pd.DataFrame({"site_id": [f"t{i}" for i in range(n)], "treatment_year": 2015})
    features = pd.DataFrame(features, columns=["site_id", "centroid_lat", "centroid_lon"])
    return wide, years, gold, matches, features


def test_disjoint_block_jackknife_matches_known_mean_standard_error():
    args = example()
    result = pooled_block_sensitivity(*args, EvalConfig(min_pre_scenes=3),
                                      block_sizes_m=(1000,), offsets=(0,))
    expected = np.arange(12) * -0.1
    for metric in ("overall", "five_year_plus"):
        value = result["grids"][0][metric]
        assert value["status"] == "sensitivity_only"
        assert value["mean_effect_k"] == pytest.approx(expected.mean())
        assert value["se_k"] == pytest.approx(expected.std(ddof=1) / np.sqrt(12))


def test_shared_controls_are_deleted_jointly_and_loss_of_support_invalidates_interval():
    result = pooled_block_sensitivity(*example(shared=True), EvalConfig(min_pre_scenes=3),
                                      block_sizes_m=(1000,), offsets=(0,))
    assert result["control_reuse"]["max_treated_sites_per_control"] == 12
    value = result["grids"][0]["overall"]
    assert value["min_retained_fraction"] == 0
    assert value["status"] == "insufficient_block_support"
    assert value["se_k"] is None


def test_single_spatial_block_does_not_return_false_precision():
    args = example()
    args[-1]["centroid_lon"] = -74.0
    result = pooled_block_sensitivity(*args, EvalConfig(min_pre_scenes=3))
    assert all(grid["overall"]["se_k"] is None for grid in result["grids"])


def test_missing_coordinates_skip_sensitivity_without_inventing_locations():
    args = list(example())
    args[-1] = args[-1].drop(columns="centroid_lon")
    result = pooled_block_sensitivity(*args, EvalConfig())
    assert result["status"] == "coordinates_unavailable"


def test_pre_trend_reports_nonflat_data_even_when_pre_mean_is_zero():
    gold = pd.DataFrame({"event_study_json": ['{"-3": -1.0, "-2": 0.0, "-1": 1.0}']})
    result = pre_trend_diagnostics(gold)
    assert result["mean_slope_k_per_year"] == pytest.approx(1.0)
    assert result["mean_last_minus_first_pre_year_k"] == pytest.approx(2.0)
