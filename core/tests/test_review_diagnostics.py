from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from core.evaluation import EvalConfig
from core.evaluation.diagnostics import (
    combine_components, fake_date_diagnostic, point_estimates, sensor_family_diagnostic,
    supported, year_block_sensitivity,
)
from core.evaluation.panel import to_wide


def matched_fixture():
    ids, rows, features, treated, controls = [], [], [], [], []
    years = np.repeat([2010, 2011, 2012, 2016, 2017, 2018], 2)
    for group in range(18):
        for role in range(4):
            sid = f"{group}_{role}"
            ids.append(sid)
            rows.append([0] * 6 + ([0, 0, 1, 1, 3, 3] if role == 0 else [0] * 6))
            features.append((sid, group / 100, group / 100, group, f"class{group}", 40.0, -74 + .04 * group))
            if role == 0:
                treated.append((sid, 2015))
            else:
                controls.append(sid)
    cfg = EvalConfig(n_controls=3, min_pre_scenes=3, min_post_scenes=3,
                     min_cells_per_scene=1, n_placebo=3)
    feats = pd.DataFrame(features, columns=["site_id", "canopy_frac_baseline", "impervious_frac", "elevation_m",
                                           "land_cover_class", "centroid_lat", "centroid_lon"])
    return pd.DataFrame(rows, index=ids), years, pd.DataFrame(treated, columns=["site_id", "treatment_year"]), pd.Index(controls), feats, cfg


def test_year_jackknife_captures_shared_shock_when_site_variance_is_zero():
    wide, years, treated, controls, features, cfg = matched_fixture()
    baseline, _ = point_estimates(wide, years, treated, controls, features, cfg)
    assert supported(baseline, cfg).std() == pytest.approx(0)
    result, cohorts = year_block_sensitivity(wide, years, treated, controls, features, cfg, baseline)
    overall = result["overall"]
    assert overall["status"] == "sensitivity_only"
    assert len(cohorts["overall"]) == 18
    assert overall["mean_effect_k"] == pytest.approx(4 / 3)
    assert overall["se_k"] > .5
    assert result["rematched"] is True
    assert [r["year"] for r in overall["delete_one_year"]] == [2010, 2011, 2012, 2016, 2017, 2018]


def test_year_interval_withheld_when_common_cohort_loses_support():
    wide, years, treated, controls, features, cfg = matched_fixture()
    result, _ = year_block_sensitivity(wide, years, treated, controls, features, replace(cfg, min_pre_scenes=5))
    assert result["overall"]["status"] == "insufficient_common_support"
    assert result["overall"]["se_k"] is None


def test_combined_sensitivity_uses_both_components_without_independence_claim():
    result = combine_components(-.05, .1, .2)
    assert result["se_sum_k"] == pytest.approx(.3)
    assert result["sensitivity_low_k"] == pytest.approx(-.638)
    assert result["sensitivity_high_k"] == pytest.approx(.538)


def fake_fixture():
    _, _, treated, _, features, cfg = matched_fixture()
    treated_ids = set(treated.site_id)
    rows = []
    for year in (2008, 2009, 2010, 2011):
        for scene in range(6):
            for sid in features.site_id:
                rows.append({"country_code": "XX", "city_id": "test", "site_id": sid,
                             "scene_id": f"s{year}_{scene}",
                             "acquired_at_utc": pd.Timestamp(year=year, month=7, day=scene + 1, hour=15, tz="UTC"),
                             "sensor": "LANDSAT_5", "valid_pixel_frac": 1.0,
                             "scene_cloud_cover_frac": 0.0, "city_clear_frac": 1.0,
                             "lst_median_k": 300.0 - (.4 if sid in treated_ids and year == 2011 else 0)})
    iv = pd.DataFrame({"site_id": treated.site_id, "plant_year": 2015, "trees_planted": 10,
                       "trees_batch_dated": 0, "trees_surviving": 10})
    return pd.DataFrame(rows), features, iv, cfg


def test_fake_date_flags_nonzero_contrast_before_recorded_cohort():
    result = fake_date_diagnostic(*fake_fixture())
    assert result["status"] == "nonzero_pre_cohort_contrast"
    assert result["sensor"] == "LANDSAT_5"
    assert result["n_pre_scenes"] == 12 and result["n_post_scenes"] == 6
    assert result["pooled"]["overall"]["mean_effect_k"] == pytest.approx(-.4)


def test_fake_date_does_not_silently_substitute_modern_sensors():
    panel, features, iv, cfg = fake_fixture()
    panel["sensor"] = "LANDSAT_8"
    result = fake_date_diagnostic(panel, features, iv, cfg)
    assert result["status"] == "insufficient_same_sensor_scenes"
    assert result["n_pre_scenes"] == result["n_post_scenes"] == 0


def test_sensor_transition_is_marked_as_sensitivity_not_confirmation():
    panel = pd.DataFrame({"scene_id": ["a", "b", "c"], "scene_year": [2008, 2014, 2020],
                          "sensor": ["LANDSAT_5", "LANDSAT_8", "LANDSAT_9"]})
    treated = pd.DataFrame({"treatment_year": [2015]})
    result = sensor_family_diagnostic(panel, treated, EvalConfig())
    assert result["sensor_transition_sensitive"]
    assert result["cohorts"][0]["families_present_only_pre"] == ["legacy_5_7"]


def test_empty_point_support_is_reported_without_false_precision():
    wide, years, treated, controls, features, cfg = matched_fixture()
    points, matches = point_estimates(wide.iloc[:, :0], years[:0], treated, controls, features, cfg)
    assert supported(points, cfg).empty and not matches
