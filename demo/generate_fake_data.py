"""Generate fake NYC data matching the FROZEN schemas (board 2026-11-14:
Agent 1 msgs 1-3, Agent 2 msg 1, Agent 3 msg 1), so the model and app are
tested before real tables arrive (shared rule 8).

Writes parquet files under demo/data/:
  silver_features, silver_interventions, gold_site_effects, panel_sample.

The fake world has a known structure the model should recover: cooling grows
with trees planted (dose) and with years since planting (ramping in over ~5
years), and shrinks with existing canopy (less room to improve) and
impervious fraction. effect_k is the average over the post period, matching
Agent 3's semantics.

panel_sample stands in for Agent 2's silver.panel pre-joined to matched
controls: one row per evaluated site per clear-sky summer scene, with the
site's and its matched controls' temperature relative to the city baseline.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
RNG = np.random.default_rng(42)

N_CELLS = 2500
AS_OF_YEAR = 2026
NYC = {"lat": 40.7128, "lon": -74.0060}
# Placeholder vocabulary; swap for Agent 1's NLCD strings when posted.
LAND_COVER_CLASSES = [
    "developed_open", "developed_low", "developed_medium", "developed_high",
    "grass", "barren", "water", "forest",
]
RAMP_YEARS = 5


def fake_h3(i: int) -> str:
    """15-char lowercase hex, shaped like a real res-9 H3 index."""
    return f"89fake{i:06x}fff"


def make_features(n: int = N_CELLS) -> pd.DataFrame:
    canopy = RNG.beta(1.5, 4, n) * 0.6
    impervious = np.clip(0.9 - canopy + RNG.normal(0, 0.15, n), 0, 1)
    pop = np.clip(RNG.lognormal(6.5, 0.8, n), 0, 12000).round()
    age65 = np.clip(RNG.beta(2, 8, n), 0, 1).round(3)
    lowinc = np.clip(RNG.beta(2, 6, n), 0, 1).round(3)

    def scaled(v):
        return (v - v.min()) / (v.max() - v.min())

    vuln = (0.5 * scaled(age65) + 0.5 * scaled(lowinc)).round(3)
    df = pd.DataFrame({
        "country_code": "US",
        "city_id": "nyc",
        "site_id": [fake_h3(i) for i in range(n)],
        "centroid_lat": NYC["lat"] + RNG.uniform(-0.12, 0.12, n),
        "centroid_lon": NYC["lon"] + RNG.uniform(-0.14, 0.14, n),
        "area_km2": 0.105,
        "canopy_frac_baseline": canopy.round(3),
        "canopy_frac_latest": np.clip(canopy + RNG.normal(0.01, 0.02, n), 0, 1).round(3),
        "impervious_frac": impervious.round(3),
        "land_cover_class": RNG.choice(
            LAND_COVER_CLASSES, n, p=[.15, .2, .25, .15, .1, .05, .05, .05]),
        "elevation_m": np.clip(RNG.normal(20, 15, n), 0, 120).round(1),
        "population": pop,
        "share_age_65_plus": age65,
        "share_low_income": lowinc,
        "vulnerability_index": vuln,
        "vulnerable_residents": (pop * vuln).round(1),
        "median_household_income": np.clip(
            RNG.lognormal(11, 0.4, n), 20000, 250000).round(),
        # demo-only helper, not in the frozen schema
        "baseline_temp_anomaly_k": RNG.normal(0, 1.5, n).round(2),
    })
    return df


def make_interventions(features: pd.DataFrame, frac_planted: float = 0.15) -> pd.DataFrame:
    planted = features.sample(frac=frac_planted, random_state=1).copy()
    n = len(planted)
    planted["plant_year"] = RNG.integers(2015, 2020, n)
    planted["trees_planted"] = RNG.integers(5, 120, n)
    planted["trees_removed"] = (planted["trees_planted"]
                                * RNG.beta(1, 8, n)).astype(int)
    planted["trees_surviving"] = planted["trees_planted"] - planted["trees_removed"]
    planted["removed_flag"] = planted["trees_surviving"] == 0
    planted["trees_batch_dated"] = 0  # matches real NYC 2015-2019 (board, A1 msg 3)
    planted["intervention_type"] = "tree_planting"
    planted["first_plant_date"] = planted["plant_year"].astype(str) + "-04-20"
    planted["last_plant_date"] = planted["plant_year"].astype(str) + "-11-10"
    planted["source"] = "fake"
    return planted[[
        "country_code", "city_id", "site_id", "plant_year", "intervention_type",
        "trees_planted", "trees_removed", "trees_surviving", "removed_flag",
        "trees_batch_dated", "first_plant_date", "last_plant_date", "source",
    ]]


def _ramp(age: np.ndarray | float) -> np.ndarray | float:
    return np.clip(np.asarray(age, dtype=float) / RAMP_YEARS, 0, 1)


def make_site_effects(features: pd.DataFrame, interventions: pd.DataFrame) -> pd.DataFrame:
    """Mature effect: -0.012 K per tree, damped by canopy and pavement.
    effect_k = mature effect x mean ramp over the post period (A3 semantics)."""
    df = interventions.merge(features, on=["country_code", "city_id", "site_id"])
    n = len(df)
    mature = (
        -0.012 * df["trees_planted"]
        * (1 - df["canopy_frac_baseline"])
        * (1 - 0.4 * df["impervious_frac"])
    )
    mean_ramp = np.array([
        _ramp(np.arange(1, AS_OF_YEAR - y + 1)).mean() for y in df["plant_year"]
    ])
    noise = RNG.normal(0, 0.25, n)
    df["effect_k"] = (mature * mean_ramp + noise).round(3)
    df["effect_se_k"] = np.abs(RNG.normal(0.15, 0.05, n)).round(3)
    df["ci_low_k"] = (df["effect_k"] - 1.96 * df["effect_se_k"]).round(3)
    df["ci_high_k"] = (df["effect_k"] + 1.96 * df["effect_se_k"]).round(3)
    df["placebo_p"] = np.clip(RNG.beta(2, 5, n), 0.001, 1).round(3)
    df["mde_k"] = np.abs(RNG.normal(0.35, 0.1, n)).round(3)
    df["quality_label"] = np.where(
        (df["ci_high_k"] < 0) & (np.abs(df["effect_k"]) >= df["mde_k"]), "detected",
        np.where(np.abs(df["effect_k"]) < df["mde_k"], "not_detectable",
                 "inconclusive"),
    )
    df["treatment_year"] = df["plant_year"]
    df["dose_trees"] = df["trees_planted"]
    df["n_pre_scenes"] = RNG.integers(6, 20, n)
    df["n_post_scenes"] = RNG.integers(6, 20, n)
    df["n_controls"] = RNG.integers(5, 40, n)
    df["event_study_json"] = [
        json.dumps({str(a): round(float(m * _ramp(a)), 3)
                    for a in range(0, AS_OF_YEAR - y + 1)})
        for m, y in zip(mature, df["plant_year"])
    ]
    df["panel_version"] = "fake-0"
    df["method_version"] = "fake-did-v0"
    df["evaluated_at_utc"] = f"{AS_OF_YEAR}-11-14T00:00:00Z"

    cols = [
        "country_code", "city_id", "site_id", "variant", "treatment_year",
        "intervention_type", "dose_trees", "n_pre_scenes", "n_post_scenes",
        "n_controls", "effect_k", "effect_se_k", "ci_low_k", "ci_high_k",
        "placebo_p", "mde_k", "quality_label", "event_study_json",
        "panel_version", "method_version", "evaluated_at_utc",
    ]
    # Both variants identical: no batch-dated plantings in NYC 2015-2019.
    out = pd.concat([df.assign(variant="all"),
                     df.assign(variant="excl_batch_dated")], ignore_index=True)
    return out[cols]


def make_panel_sample(
    features: pd.DataFrame,
    effects: pd.DataFrame,
) -> pd.DataFrame:
    """Scene series per evaluated site: site vs matched-control relative temp
    (Kelvin), two clear-sky summer scenes per year, 2013-2026."""
    df = effects[effects["variant"] == "all"].merge(
        features[["site_id", "baseline_temp_anomaly_k"]], on="site_id")

    years = np.arange(2013, AS_OF_YEAR + 1)
    rows = []
    for _, s in df.iterrows():
        mature = (s["effect_k"] /
                  max(_ramp(np.arange(1, AS_OF_YEAR - s["treatment_year"] + 1)).mean(),
                      0.01))
        for y in years:
            for month, day in ((7, 1), (8, 15)):
                control = s["baseline_temp_anomaly_k"] + RNG.normal(0, 0.35)
                site = (control + _ramp(y - s["treatment_year"]) * mature
                        + RNG.normal(0, 0.2))
                rows.append({
                    "country_code": s["country_code"],
                    "city_id": s["city_id"],
                    "site_id": s["site_id"],
                    "scene_date": f"{y}-{month:02d}-{day:02d}",
                    "site_temp_rel_k": round(site, 3),
                    "control_temp_rel_k": round(control, 3),
                    "post": bool(y >= s["treatment_year"]),
                })
    return pd.DataFrame(rows)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    features = make_features()
    interventions = make_interventions(features)
    effects = make_site_effects(features, interventions)
    panel = make_panel_sample(features, effects)
    features.drop(columns=["baseline_temp_anomaly_k"]).to_parquet(
        DATA_DIR / "silver_features.parquet", index=False)
    interventions.to_parquet(DATA_DIR / "silver_interventions.parquet", index=False)
    effects.to_parquet(DATA_DIR / "gold_site_effects.parquet", index=False)
    panel.to_parquet(DATA_DIR / "panel_sample.parquet", index=False)
    print(f"features={len(features)} interventions={len(interventions)} "
          f"effects={len(effects)} panel_sample={len(panel)} -> {DATA_DIR}")
    print(effects[effects['variant'] == 'all']["quality_label"]
          .value_counts().to_dict())


if __name__ == "__main__":
    main()
