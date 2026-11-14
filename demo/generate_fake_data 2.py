"""Generate fake NYC data matching the working schemas, so the model and app
are tested before real tables arrive (shared rule 8).

Writes parquet files under demo/data/:
  silver_features, silver_interventions, gold_site_effects, panel_sample.

panel_sample stands in for Agent 2's silver.panel, pre-joined to matched
controls the way Agent 3's output will let the app do: one row per evaluated
site per clear-sky summer scene, with the site's and its matched controls'
temperature relative to the city baseline.

The fake world has a known structure the model should recover: cooling grows
with trees planted and shrinks with existing canopy (less room to improve)
and impervious fraction.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
RNG = np.random.default_rng(42)

N_CELLS = 2500
NYC = {"lat": 40.7128, "lon": -74.0060}
LAND_COVERS = [
    "developed_open", "developed_low", "developed_medium", "developed_high",
    "grass", "barren", "water", "forest",
]


def make_features(n: int = N_CELLS) -> pd.DataFrame:
    side = int(np.sqrt(n))
    lat = NYC["lat"] + (RNG.uniform(-0.12, 0.12, n))
    lon = NYC["lon"] + (RNG.uniform(-0.14, 0.14, n))
    canopy = RNG.beta(1.5, 4, n) * 60
    impervious = np.clip(90 - canopy + RNG.normal(0, 15, n), 0, 100)
    pop = np.clip(RNG.lognormal(6.5, 0.8, n), 0, 12000).round()
    df = pd.DataFrame({
        "country_code": "US",
        "city_id": "nyc",
        "site_id": [f"h3-9-nyc-{i:05d}" for i in range(n)],
        "lat": lat,
        "lon": lon,
        "canopy_pct": canopy.round(1),
        "impervious_pct": impervious.round(1),
        "land_cover": RNG.choice(LAND_COVERS, n, p=[.15, .2, .25, .15, .1, .05, .05, .05]),
        "population": pop,
        "heat_sensitive_share": np.clip(RNG.beta(2, 8, n), 0, 1).round(3),
        "poverty_share": np.clip(RNG.beta(2, 6, n), 0, 1).round(3),
        "no_ac_share": np.clip(RNG.beta(2, 10, n), 0, 1).round(3),
        "median_income": np.clip(RNG.lognormal(11, 0.4, n), 20000, 250000).round(),
        "baseline_temp_anomaly_c": RNG.normal(0, 1.5, n).round(2),
    })
    return df


def make_interventions(features: pd.DataFrame, frac_planted: float = 0.15) -> pd.DataFrame:
    planted = features.sample(frac=frac_planted, random_state=1).copy()
    planted["trees_planted"] = RNG.integers(5, 120, len(planted))
    planted["plant_year"] = RNG.integers(2015, 2020, len(planted))
    planted["removed"] = False
    return planted[[
        "country_code", "city_id", "site_id", "trees_planted", "plant_year", "removed",
    ]]


def make_site_effects(features: pd.DataFrame, interventions: pd.DataFrame) -> pd.DataFrame:
    """True effect: -0.012°C per tree, damped by existing canopy and pavement."""
    df = interventions.merge(features, on=["country_code", "city_id", "site_id"])
    true_effect = (
        -0.012 * df["trees_planted"]
        * (1 - df["canopy_pct"] / 100)
        * (1 - 0.4 * df["impervious_pct"] / 100)
    )
    noise = RNG.normal(0, 0.25, len(df))
    df["effect_c"] = (true_effect + noise).round(3)
    ci = np.abs(RNG.normal(0.3, 0.1, len(df)))
    df["effect_ci_low_c"] = (df["effect_c"] - ci).round(3)
    df["effect_ci_high_c"] = (df["effect_c"] + ci).round(3)
    df["quality_label"] = np.where(
        np.abs(df["effect_c"]) > 2 * ci, "detected",
        np.where(np.abs(df["effect_c"]) > ci, "inconclusive", "not_detectable"),
    )
    df["n_scenes_pre"] = RNG.integers(6, 20, len(df))
    df["n_scenes_post"] = RNG.integers(6, 20, len(df))
    df["method"] = "did_event_study"
    df["batch_dated_included"] = True
    df["evaluated_at"] = "2026-11-14T00:00:00Z"
    return df[[
        "country_code", "city_id", "site_id", "effect_c",
        "effect_ci_low_c", "effect_ci_high_c", "quality_label",
        "n_scenes_pre", "n_scenes_post", "method", "batch_dated_included",
        "evaluated_at",
    ]]


def make_panel_sample(
    features: pd.DataFrame,
    interventions: pd.DataFrame,
    effects: pd.DataFrame,
) -> pd.DataFrame:
    """Scene series for each evaluated site: site vs matched-control relative temp.

    Two clear-sky summer scenes per year, 2013-2026. The site tracks its
    control before planting, then drifts down by the site's measured effect,
    phased in over three years.
    """
    df = effects.merge(
        interventions[["site_id", "plant_year"]], on="site_id"
    ).merge(features[["site_id", "baseline_temp_anomaly_c"]], on="site_id")

    years = np.arange(2013, 2027)
    rows = []
    for _, s in df.iterrows():
        for y in years:
            for month, day in ((7, 1), (8, 15)):
                scene_noise = RNG.normal(0, 0.35)
                control = s["baseline_temp_anomaly_c"] + scene_noise
                ramp = np.clip((y - s["plant_year"]) / 3, 0, 1)
                site = control + ramp * s["effect_c"] + RNG.normal(0, 0.2)
                rows.append({
                    "country_code": s["country_code"],
                    "city_id": s["city_id"],
                    "site_id": s["site_id"],
                    "scene_date": f"{y}-{month:02d}-{day:02d}",
                    "site_temp_rel_c": round(site, 3),
                    "control_temp_rel_c": round(control, 3),
                    "post": bool(y >= s["plant_year"]),
                })
    return pd.DataFrame(rows)


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    features = make_features()
    interventions = make_interventions(features)
    effects = make_site_effects(features, interventions)
    features.to_parquet(DATA_DIR / "silver_features.parquet", index=False)
    interventions.to_parquet(DATA_DIR / "silver_interventions.parquet", index=False)
    effects.to_parquet(DATA_DIR / "gold_site_effects.parquet", index=False)
    panel = make_panel_sample(features, interventions, effects)
    panel.to_parquet(DATA_DIR / "panel_sample.parquet", index=False)
    print(f"features={len(features)} interventions={len(interventions)} "
          f"effects={len(effects)} panel_sample={len(panel)} -> {DATA_DIR}")
    print(effects["quality_label"].value_counts().to_dict())


if __name__ == "__main__":
    main()
