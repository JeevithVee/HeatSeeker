"""Permanent test: the evaluation engine must recover a known built-in effect.

Run: .venv/bin/python -m pytest core/tests -q
"""

import json

import numpy as np
import pandas as pd
import pytest

from core.evaluation import EvalConfig, evaluate_city, evaluate_city_all_variants
from core.evaluation.panel import filter_scenes
from core.evaluation.run import GOLD_COLUMNS
from core.evaluation.synthetic import SyntheticSpec, make_city

CFG = EvalConfig(n_bootstrap=150, n_placebo=120, seed=1)


@pytest.fixture(scope="module")
def city():
    return make_city(SyntheticSpec())


@pytest.fixture(scope="module")
def gold(city):
    return evaluate_city_all_variants(city["panel"], city["features"], city["interventions"], CFG, panel_version="synthetic")


def test_filtering_keeps_only_clean_summer_landsat(city):
    p = filter_scenes(city["panel"], CFG)
    assert set(p["sensor"]) <= {"LANDSAT_8", "LANDSAT_9"}
    months = pd.to_datetime(p["acquired_at_utc"]).dt.month
    assert months.isin([6, 7, 8]).all()
    assert (p["scene_cloud_cover_frac"] <= CFG.max_scene_cloud_frac).all()
    assert (p["valid_pixel_frac"] >= CFG.min_valid_pixel_frac).all()
    raw = city["panel"].drop_duplicates("scene_id")
    expected = raw[
        raw["sensor"].isin(["LANDSAT_8", "LANDSAT_9"])
        & pd.to_datetime(raw["acquired_at_utc"]).dt.month.isin([6, 7, 8])
        & (raw["scene_cloud_cover_frac"] <= CFG.max_scene_cloud_frac)
    ]["scene_id"].nunique()
    assert p["scene_id"].nunique() == expected
    assert expected >= 60


def test_output_schema(gold):
    assert list(gold.columns) == GOLD_COLUMNS
    assert set(gold["variant"]) == {"all", "excl_batch_dated"}
    assert set(gold["quality_label"]) <= {"detected", "not_detectable", "inconclusive"}
    assert gold.groupby(["site_id", "variant"]).size().max() == 1
    es = json.loads(gold["event_study_json"].iloc[0])
    assert all(isinstance(v, float) for v in es.values())


def test_recovers_true_effect(gold, city):
    g = gold[gold["variant"] == "all"].merge(city["truth"], on="site_id", suffixes=("", "_truth"))
    real = g[g["group"] == "real"]
    # effect_k is the post-period average; the true effect ramps in over 5 years, so compare
    # against the true post-period average, not the long-run value.
    bias = (real["effect_k"] - real["true_post_avg_k"]).mean()
    assert abs(bias) < 0.15, f"mean bias {bias:.3f} K"
    corr = np.corrcoef(real["effect_k"], real["true_post_avg_k"])[0, 1]
    assert corr > 0.7, f"correlation {corr:.3f}"
    strong = real[real["true_effect_k"] <= -1.5]
    assert (strong["quality_label"] == "detected").mean() >= 0.8
    assert (strong["effect_k"] < 0).all()


def test_null_sites_are_not_called_detected(gold, city):
    g = gold[gold["variant"] == "all"].merge(city["truth"], on="site_id")
    null = g[g["group"] == "null"]
    assert (null["quality_label"] == "detected").mean() <= 0.10
    assert (null["quality_label"] == "not_detectable").mean() >= 0.6


def test_batch_dated_variant(gold, city):
    truth = city["truth"]
    excl = gold[gold["variant"] == "excl_batch_dated"]
    batch_ids = set(truth.loc[truth["group"] == "batch", "site_id"])
    assert not (set(excl["site_id"]) & batch_ids)
    allv = gold[gold["variant"] == "all"]
    assert batch_ids <= set(allv["site_id"])


def test_controls_and_counts(gold, city):
    g = gold[gold["variant"] == "all"]
    assert (g["n_controls"] == CFG.n_controls).all()
    assert (g["n_pre_scenes"] >= CFG.min_pre_scenes).all()
    planted = set(city["truth"]["site_id"])
    assert set(g["site_id"]) == planted


def test_event_study_pre_period_is_flat(gold, city):
    g = gold[gold["variant"] == "all"].merge(city["truth"], on="site_id")
    real = g[(g["group"] == "real") & (g["true_effect_k"] <= -1.5)]
    pre_vals, post_vals = [], []
    for s in real["event_study_json"]:
        es = {int(k): v for k, v in json.loads(s).items()}
        pre_vals += [v for k, v in es.items() if k < 0]
        post_vals += [v for k, v in es.items() if k >= 5]
    assert abs(np.mean(pre_vals)) < 0.15
    assert np.mean(post_vals) < -1.0


def test_core_has_no_country_imports():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    banned = ["ingest" + ".us", "config" + ".us"]
    for f in root.rglob("*.py"):
        if f.name == "__pycache__" or f == pathlib.Path(__file__).resolve():
            continue
        text = f.read_text()
        assert not any(b in text for b in banned), f
